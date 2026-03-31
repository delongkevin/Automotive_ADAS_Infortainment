"""
GM VIP Automation Framework – CAPL Test Case Monitor
=====================================================
Monitors CAPL test module execution in a running **Vector CANoe** instance
and surfaces per-test-case PASS/FAIL verdicts so that the Python framework
can react to failures in real time (e.g. trigger Trace32 debugging).

Design goals
------------
* **Non-invasive** – attaches to a *running* CANoe instance without
  stopping or restarting the measurement.
* **Mock-safe** – every COM operation is guarded so the module imports and
  runs cleanly in CI (Linux) where neither CANoe nor ``pywin32`` is present.
* **Polling-based** – periodically queries the CANoe Test System COM
  interface; does not require any CAPL-side instrumentation.

CANoe COM interfaces used
-------------------------
``CANoe.Application``
    Top-level COM object, obtained via ``win32com.client.Dispatch``.

``Application.TestSystem``
    The test-system root; exposes ``TestModules`` and ``TestSetup`` under
    later CANoe versions.

``TestModules.Item(i)``
    Individual ``ITestModule`` objects with attributes:

    * ``Name``    – module name string
    * ``Verdict`` – integer verdict code (see :class:`CAPLVerdict`)

``ITestModule.TestCases``
    Collection of ``ITestCase`` objects with the same
    ``Name`` / ``Verdict`` / ``ExecTime`` attributes.

Typical usage
-------------
::

    from GM_VIP_Automation_Framework.core.canoe import CANoeClient
    from GM_VIP_Automation_Framework.core.capl_monitor import CAPLTestMonitor

    with CANoeClient(mock=False) as canoe:
        monitor = CAPLTestMonitor(canoe)
        canoe.start_measurement()

        # Wait until every test module has finished, then collect results.
        results = monitor.wait_for_completion(timeout_s=120.0)
        for r in results:
            print(r.module, r.name, r.verdict)
        failures = monitor.get_failed_tests()

Mock mode
---------
Pass ``mock=True`` (or use ``CANoeClient(mock=True)``) to return canned
results without touching COM objects.  The mock produces one PASS and one
FAIL per poll cycle so the CI test suite can exercise all code paths.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional

from .canoe import CANoeClient, CANoeError
from ..utils.logger import get_logger

__all__ = [
    "CAPLVerdict",
    "CAPLTestResult",
    "CAPLTestMonitor",
]

logger = get_logger("capl_monitor")


# ---------------------------------------------------------------------------
# Verdict mapping
# ---------------------------------------------------------------------------

class CAPLVerdict(IntEnum):
    """Numeric verdict codes returned by the CANoe Test System COM interface."""
    NONE    = 0   # Test has not been executed yet
    PASS    = 1   # All checks in the test case passed
    FAIL    = 2   # At least one check failed
    ERROR   = 3   # Test infrastructure error (e.g. timeout, exception)
    NOTRUN  = 4   # Test was explicitly skipped

    @classmethod
    def from_int(cls, value: int) -> "CAPLVerdict":
        """Return the enum member for *value*, defaulting to NONE."""
        try:
            return cls(value)
        except ValueError:
            return cls.NONE

    @property
    def label(self) -> str:
        """Human-readable uppercase label, e.g. ``"PASS"``, ``"FAIL"``."""
        return self.name


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CAPLTestResult:
    """Holds the result of a single CAPL test case after execution.

    Attributes
    ----------
    module :
        Name of the CANoe test module that owns this test case.
    name :
        Test case identifier as declared in CAPL (the ``TestCase`` name).
    verdict :
        Execution verdict (PASS, FAIL, ERROR, NONE, NOTRUN).
    error_message :
        Optional failure description captured from CAPL output or derived
        from the verdict code.
    exec_time_s :
        Execution wall-clock time in seconds (0.0 if not available via COM).
    timestamp :
        Unix timestamp of when the result was captured.
    """

    module: str
    name: str
    verdict: CAPLVerdict = CAPLVerdict.NONE
    error_message: str = ""
    exec_time_s: float = 0.0
    timestamp: float = field(default_factory=time.time)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def passed(self) -> bool:
        """``True`` when the verdict is PASS."""
        return self.verdict == CAPLVerdict.PASS

    @property
    def failed(self) -> bool:
        """``True`` when the verdict is FAIL or ERROR."""
        return self.verdict in (CAPLVerdict.FAIL, CAPLVerdict.ERROR)

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation of this result."""
        return {
            "module":        self.module,
            "name":          self.name,
            "verdict":       self.verdict.label,
            "error_message": self.error_message,
            "exec_time_s":   self.exec_time_s,
            "timestamp":     self.timestamp,
        }

    def __repr__(self) -> str:
        return (
            f"CAPLTestResult(module={self.module!r}, name={self.name!r},"
            f" verdict={self.verdict.label})"
        )


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

class CAPLTestMonitor:
    """Polls a running CANoe instance for CAPL test-module results.

    Parameters
    ----------
    canoe_client :
        An already-connected :class:`~canoe.CANoeClient` instance.  The
        client must be in the connected state (``canoe_client.is_connected``
        must be ``True``).
    poll_interval_s :
        Seconds between consecutive COM polls of the test system.
    mock :
        When ``True`` the monitor never touches COM objects and instead
        returns synthetic results for testing.
    """

    # Synthetic test data used in mock mode.
    _MOCK_MODULES: List[Dict] = [
        {
            "name": "MockModule_CAN",
            "test_cases": [
                {"name": "TC_001_CanInit",     "verdict": CAPLVerdict.PASS, "exec_time_s": 0.12},
                {"name": "TC_002_CanRxFrame",  "verdict": CAPLVerdict.FAIL, "exec_time_s": 0.08,
                 "error_message": "[MOCK] Expected DLC=8, got DLC=7"},
                {"name": "TC_003_CanTxConfirm","verdict": CAPLVerdict.PASS, "exec_time_s": 0.15},
            ],
        },
        {
            "name": "MockModule_Diagnostics",
            "test_cases": [
                {"name": "TC_010_UdsSession",   "verdict": CAPLVerdict.PASS, "exec_time_s": 0.33},
                {"name": "TC_011_ReadDTC",      "verdict": CAPLVerdict.PASS, "exec_time_s": 0.21},
                {"name": "TC_012_ClearDTC",     "verdict": CAPLVerdict.ERROR,"exec_time_s": 0.05,
                 "error_message": "[MOCK] Response timeout after 500 ms"},
            ],
        },
    ]

    def __init__(
        self,
        canoe_client: CANoeClient,
        poll_interval_s: float = 0.5,
        mock: bool = False,
    ) -> None:
        self._canoe   = canoe_client
        self._poll_s  = poll_interval_s
        self._mock    = mock or canoe_client._mock  # type: ignore[attr-defined]
        self._results: List[CAPLTestResult] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_test_results(self) -> List[CAPLTestResult]:
        """Snapshot the current PASS/FAIL state of all CAPL test cases.

        In *live* mode this queries the CANoe ``TestSystem.TestModules``
        COM collection.  In *mock* mode a static set of synthetic results
        is returned (suitable for unit tests).

        Returns
        -------
        List[CAPLTestResult]
            One entry per test case across all test modules.  Results whose
            verdict is still NONE (not yet executed) are included so callers
            can distinguish "not run" from "passed".
        """
        if self._mock:
            return self._mock_results()

        return self._live_results()

    def get_failed_tests(self) -> List[CAPLTestResult]:
        """Return only test cases whose verdict is FAIL or ERROR.

        This is a convenience wrapper around :meth:`get_test_results`.
        """
        return [r for r in self.get_test_results() if r.failed]

    def get_passed_tests(self) -> List[CAPLTestResult]:
        """Return only test cases whose verdict is PASS."""
        return [r for r in self.get_test_results() if r.passed]

    def wait_for_completion(
        self,
        timeout_s: float = 300.0,
        module_names: Optional[List[str]] = None,
    ) -> List[CAPLTestResult]:
        """Block until all (or specified) test modules have finished running.

        A module is considered *finished* when every one of its test cases
        has a verdict other than NONE (i.e. the module has been executed at
        least once).

        Parameters
        ----------
        timeout_s :
            Maximum wall-clock time to wait.  Raises :exc:`~utils.exceptions.T32TimeoutError`
            if this elapses before all modules finish.
        module_names :
            Optional allowlist of module names to wait on.  When ``None``,
            all discovered modules must finish.

        Returns
        -------
        List[CAPLTestResult]
            Final snapshot of all results after completion.

        Raises
        ------
        T32TimeoutError
            If the test modules do not finish within *timeout_s*.
        """
        from ..utils.exceptions import T32TimeoutError

        if self._mock:
            logger.info("[MOCK] wait_for_completion – returning synthetic results immediately.")
            return self._mock_results()

        deadline = time.monotonic() + timeout_s
        logger.info(
            "Waiting up to %.0f s for CAPL test modules to complete.", timeout_s
        )

        while time.monotonic() < deadline:
            results = self._live_results()
            pending = [
                r for r in results
                if r.verdict == CAPLVerdict.NONE
                and (module_names is None or r.module in module_names)
            ]
            if not pending:
                logger.info(
                    "All CAPL test cases completed (%d results).", len(results)
                )
                self._results = results
                return results

            logger.debug(
                "%d test case(s) still pending (verdict=NONE).", len(pending)
            )
            time.sleep(self._poll_s)

        raise T32TimeoutError(
            f"CAPL test modules did not complete within {timeout_s:.0f} s."
        )

    def results_summary(self) -> Dict[str, int]:
        """Return a ``{verdict_label: count}`` tally of the latest snapshot.

        Returns
        -------
        dict
            Keys are verdict labels (``"PASS"``, ``"FAIL"``, etc.); values
            are the number of test cases with that verdict.
        """
        results = self.get_test_results()
        tally: Dict[str, int] = {}
        for r in results:
            tally[r.verdict.label] = tally.get(r.verdict.label, 0) + 1
        return tally

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _live_results(self) -> List[CAPLTestResult]:
        """Query the CANoe COM test system and return a flat list of results."""
        results: List[CAPLTestResult] = []
        try:
            app = self._canoe._app  # type: ignore[attr-defined]
            if app is None:
                logger.warning("CANoe COM object is None – cannot query test system.")
                return results

            test_system = getattr(app, "TestSystem", None)
            if test_system is None:
                logger.warning(
                    "CANoe Application.TestSystem is not available "
                    "(requires CANoe 10+)."
                )
                return results

            modules = getattr(test_system, "TestModules", None)
            if modules is None:
                return results

            count = int(getattr(modules, "Count", 0))
            for idx in range(1, count + 1):
                try:
                    module = modules.Item(idx)
                    module_name = str(getattr(module, "Name", f"Module_{idx}"))
                    test_cases = getattr(module, "TestCases", None)
                    if test_cases is None:
                        continue
                    tc_count = int(getattr(test_cases, "Count", 0))
                    for tc_idx in range(1, tc_count + 1):
                        try:
                            tc = test_cases.Item(tc_idx)
                            verdict = CAPLVerdict.from_int(
                                int(getattr(tc, "Verdict", 0))
                            )
                            exec_time = float(getattr(tc, "ExecTime", 0.0))
                            tc_name = str(getattr(tc, "Name", f"TC_{tc_idx}"))
                            error_msg = ""
                            if verdict in (CAPLVerdict.FAIL, CAPLVerdict.ERROR):
                                error_msg = str(
                                    getattr(tc, "Description", "") or ""
                                )
                            results.append(
                                CAPLTestResult(
                                    module=module_name,
                                    name=tc_name,
                                    verdict=verdict,
                                    error_message=error_msg,
                                    exec_time_s=exec_time,
                                )
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "Error reading test case %d from module '%s': %s",
                                tc_idx, module_name, exc,
                            )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Error reading test module %d: %s", idx, exc)

        except CANoeError as exc:
            logger.error("CANoe error while querying test system: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error querying CANoe test system: %s", exc)

        return results

    def _mock_results(self) -> List[CAPLTestResult]:
        """Return a fixed synthetic result set for unit-testing purposes."""
        results: List[CAPLTestResult] = []
        for mod in self._MOCK_MODULES:
            for tc in mod["test_cases"]:
                results.append(
                    CAPLTestResult(
                        module=mod["name"],
                        name=tc["name"],
                        verdict=tc["verdict"],
                        error_message=tc.get("error_message", ""),
                        exec_time_s=tc.get("exec_time_s", 0.0),
                        timestamp=time.time(),
                    )
                )
        return results
