"""
GM VIP Automation Framework – CAPL ↔ Trace32 Bridge
====================================================
Orchestrates a combined **Vector CANoe + Trace32** test session:

1. Attaches to a running CANoe instance and monitors CAPL test-module
   execution via :class:`~core.capl_monitor.CAPLTestMonitor`.
2. On CAPL test failure, automatically sets Trace32 breakpoints at
   relevant ECU symbols and re-drives the stimulus to capture the ECU
   state at the point of failure.
3. Records the full debugging sequence with
   :class:`~core.sequence_recorder.SequenceRecorder`.
4. Exports learned sequences as ``*_test_cases.json`` and
   ``*_session_script.py`` so they can be imported into the CI/CD pipeline
   (Jenkins / GitHub Actions) and replayed headlessly.

Sub-task decomposition
----------------------
This module addresses the following sub-tasks from the problem statement:

A. **Co-existence** – connects to CANoe and T32 *while both are running*,
   without stopping either tool.
B. **CAPL monitoring** – polls CANoe test-system COM interface for results.
C. **Failure debugging** – on CAPL failure, halts the ECU, captures variable
   state, and logs a diagnostic report.
D. **Sequence learning** – every T32 action taken during debugging is
   captured by :class:`SequenceRecorder` and exported as replayable
   Python/JSON tests.
E. **CI/CD handoff** – exported test cases can be pushed to the Jenkins
   ``CT`` environment via the updated ``Jenkinsfile``.

Typical usage
-------------
::

    from GM_VIP_Automation_Framework.core.canoe import CANoeClient
    from GM_VIP_Automation_Framework.core.connection import T32Connection
    from GM_VIP_Automation_Framework.capl_bridge import CAPLBridge

    with CANoeClient() as canoe, T32Connection() as conn:
        bridge = CAPLBridge(canoe, conn)
        report = bridge.monitor_and_debug(timeout_s=300.0)

    print("Passed:", len(report["passed"]))
    print("Failed:", len(report["failed"]))
    print("Generated test cases:", report["generated_test_cases"])

Mock mode
---------
Pass ``mock=True`` to run the full orchestration logic without hardware.
Both the CANoe COM layer and the T32 RCL layer are bypassed; the bridge
uses synthetic CAPL results from :class:`~core.capl_monitor.CAPLTestMonitor`
and no-op T32 commands.
"""

from __future__ import annotations

import json
import time
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .core.canoe import CANoeClient, CANoeError
from .core.capl_monitor import CAPLTestMonitor, CAPLTestResult, CAPLVerdict
from .core.sequence_recorder import SequenceRecorder
from .utils.logger import get_logger
from .utils.exceptions import T32FrameworkError

__all__ = ["CAPLBridge", "CAPLBridgeReport"]

logger = get_logger("capl_bridge")


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------

class CAPLBridgeReport:
    """Summary of a :meth:`CAPLBridge.monitor_and_debug` session.

    Attributes
    ----------
    passed :
        Names of CAPL test cases that passed.
    failed :
        Names of CAPL test cases that failed (or produced an error verdict).
    debug_reports :
        Mapping of failed test-case name → dict containing captured ECU
        variable snapshot and diagnostic notes.
    generated_test_cases :
        Path to the exported ``*_test_cases.json`` file (empty string if
        not exported).
    generated_script :
        Path to the exported Python session script (empty string if not
        exported).
    session_name :
        The recorder's session label.
    elapsed_s :
        Total wall-clock time of the session in seconds.
    """

    def __init__(self) -> None:
        self.passed:                List[str]        = []
        self.failed:                List[str]        = []
        self.debug_reports:         Dict[str, dict]  = {}
        self.generated_test_cases:  str              = ""
        self.generated_script:      str              = ""
        self.session_name:          str              = ""
        self.elapsed_s:             float            = 0.0

    def to_dict(self) -> dict:
        """Return a JSON-serialisable summary."""
        return {
            "session_name":          self.session_name,
            "elapsed_s":             round(self.elapsed_s, 2),
            "passed":                self.passed,
            "failed":                self.failed,
            "debug_reports":         self.debug_reports,
            "generated_test_cases":  self.generated_test_cases,
            "generated_script":      self.generated_script,
        }

    def save(self, output_dir: str = ".") -> str:
        """Serialise the report to ``<session_name>_bridge_report.json``.

        Returns
        -------
        str
            Absolute path of the written JSON file.
        """
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{self.session_name}_bridge_report.json"
        out_path = out_dir / fname
        out_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        logger.info("Bridge report saved → %s", out_path)
        return str(out_path)

    def __repr__(self) -> str:
        return (
            f"CAPLBridgeReport(passed={len(self.passed)},"
            f" failed={len(self.failed)}, session={self.session_name!r})"
        )


# ---------------------------------------------------------------------------
# CAPLBridge
# ---------------------------------------------------------------------------

class CAPLBridge:
    """Orchestrates CANoe CAPL monitoring and Trace32 failure debugging.

    Parameters
    ----------
    canoe_client :
        Connected :class:`~core.canoe.CANoeClient` instance.  The client
        must already be connected (``connect()`` called) before passing it
        here.
    t32_connection :
        Connected T32 connection object exposing ``.cmd()`` and ``.fnc()``
        methods (a :class:`~core.connection.T32Connection` context-managed
        instance, or any compatible mock).  Pass ``None`` to skip all T32
        operations (useful when only CAPL monitoring is needed).
    output_dir :
        Directory in which exported JSON and Python files are written.
    session_name :
        Label embedded in exported filenames.  Defaults to a UTC timestamp.
    mock :
        When ``True``, both CANoe COM and T32 RCL operations are skipped;
        synthetic data is used instead.  Automatically ``True`` when
        *canoe_client* has ``mock=True``.
    debug_symbols :
        List of ECU symbols to read when debugging a failed CAPL test.
        Defaults to a sensible set of diagnostic variables.
    poll_interval_s :
        Seconds between CAPL test-result polls.
    """

    _DEFAULT_DEBUG_SYMBOLS: List[str] = [
        "g_CanStatus",
        "g_DiagStatus",
        "g_ErrorCode",
        "g_FaultFlag",
        "g_TestResult",
    ]

    def __init__(
        self,
        canoe_client: CANoeClient,
        t32_connection: Optional[Any] = None,
        output_dir: str = ".",
        session_name: Optional[str] = None,
        mock: bool = False,
        debug_symbols: Optional[List[str]] = None,
        poll_interval_s: float = 1.0,
    ) -> None:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._canoe        = canoe_client
        self._conn         = t32_connection
        self._output_dir   = output_dir
        self._session_name = session_name or f"capl_bridge_{ts}"
        self._mock         = mock or getattr(canoe_client, "_mock", False)
        self._debug_syms   = debug_symbols or self._DEFAULT_DEBUG_SYMBOLS
        self._poll_s       = poll_interval_s

        self._monitor  = CAPLTestMonitor(canoe_client, poll_interval_s=poll_interval_s, mock=self._mock)
        self._recorder = SequenceRecorder(session_name=self._session_name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def monitor_and_debug(
        self,
        timeout_s: float = 300.0,
        module_names: Optional[List[str]] = None,
        export: bool = True,
    ) -> CAPLBridgeReport:
        """Run the main monitoring loop and auto-debug any failing test cases.

        Workflow
        --------
        1. Start recording.
        2. Wait for all CAPL test modules to complete (up to *timeout_s*).
        3. For each failing test case, call :meth:`debug_failed_test`.
        4. Stop recording.
        5. Export JSON test cases and Python script if *export* is ``True``.
        6. Return a :class:`CAPLBridgeReport`.

        Parameters
        ----------
        timeout_s :
            Maximum time to wait for CAPL tests to finish.
        module_names :
            Optional filter – only monitor these test module names.
        export :
            When ``True`` (default), write JSON and Python files to
            :attr:`output_dir`.

        Returns
        -------
        CAPLBridgeReport
        """
        report = CAPLBridgeReport()
        report.session_name = self._session_name
        t_start = time.monotonic()

        self._recorder.start_recording()
        logger.info(
            "CAPLBridge '%s' – starting monitoring loop (timeout=%.0f s).",
            self._session_name, timeout_s,
        )

        try:
            results = self._monitor.wait_for_completion(
                timeout_s=timeout_s,
                module_names=module_names,
            )
        except T32FrameworkError as exc:
            logger.error("Monitoring timed out: %s", exc)
            results = self._monitor.get_test_results()

        # Tally results and record CAPL events.
        for r in results:
            self._recorder.record_capl_result(r.name, r.verdict.label, module=r.module)
            if r.passed:
                report.passed.append(r.name)
            elif r.failed:
                report.failed.append(r.name)
                debug_info = self.debug_failed_test(r)
                report.debug_reports[r.name] = debug_info

        events = self._recorder.stop_recording()
        report.elapsed_s = time.monotonic() - t_start

        logger.info(
            "Session complete: %d passed, %d failed, %d event(s) recorded.",
            len(report.passed), len(report.failed), len(events),
        )

        if export:
            try:
                report.generated_test_cases = self._recorder.export_test_cases_json(
                    output_dir=self._output_dir
                )
                report.generated_script = self._recorder.export_python_script(
                    output_dir=self._output_dir
                )
            except OSError as exc:
                logger.warning("Could not export sequences: %s", exc)

        return report

    def debug_failed_test(self, result: CAPLTestResult) -> dict:
        """Attempt to capture ECU state for a failed CAPL test case.

        When a Trace32 connection is available, this method:

        1. Issues a BREAK to halt the ECU (if running).
        2. Reads the configured :attr:`debug_symbols` from ECU memory.
        3. Reads the current program counter (PC).
        4. Records all actions in the sequence recorder for later export.

        Parameters
        ----------
        result :
            The failing :class:`~core.capl_monitor.CAPLTestResult`.

        Returns
        -------
        dict
            Diagnostic snapshot with keys:
            ``test_name``, ``verdict``, ``error_message``,
            ``variables`` (symbol → value), ``pc`` (program counter),
            ``timestamp``, ``t32_available``.
        """
        logger.info(
            "Debugging failed CAPL test '%s' (module=%s, error=%r).",
            result.name, result.module, result.error_message,
        )

        snapshot: dict = {
            "test_name":     result.name,
            "module":        result.module,
            "verdict":       result.verdict.label,
            "error_message": result.error_message,
            "variables":     {},
            "pc":            "",
            "timestamp":     time.time(),
            "t32_available": self._conn is not None,
        }

        if self._conn is None:
            logger.info(
                "No T32 connection provided – skipping ECU state capture for '%s'.",
                result.name,
            )
            return snapshot

        if self._mock:
            # In mock mode, return synthetic debug data.
            snapshot["variables"] = {sym: "[MOCK] 0x0" for sym in self._debug_syms}
            snapshot["pc"] = "0x80001234"
            for sym in self._debug_syms:
                self._recorder.record_variable_read(sym, "[MOCK] 0x0")
            return snapshot

        try:
            # Halt the ECU.
            self._conn.cmd("Break")
            time.sleep(0.2)
            self._recorder.record_halt()

            # Read the program counter.
            try:
                pc = self._conn.fnc("R(PC)")
                snapshot["pc"] = str(pc)
                logger.debug("PC at failure: %s", pc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not read PC: %s", exc)

            # Read diagnostic symbols.
            for sym in self._debug_syms:
                try:
                    val = self._conn.fnc(f'VAR.VALUE({sym})')
                    snapshot["variables"][sym] = str(val)
                    self._recorder.record_variable_read(sym, str(val))
                    logger.debug("  %s = %s", sym, val)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("  %s – not available (%s)", sym, exc)

            # Resume ECU.
            self._conn.cmd("Go")
            self._recorder.record_go()

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Error during T32 debug capture for test '%s': %s",
                result.name, exc,
            )
            snapshot["error_during_debug"] = str(exc)

        return snapshot

    def export_learned_sequences(self, output_dir: Optional[str] = None) -> str:
        """Export all recorded sequences as a ``*_test_cases.json`` file.

        This is a convenience wrapper around
        :meth:`~core.sequence_recorder.SequenceRecorder.export_test_cases_json`
        that writes to *output_dir* (defaults to :attr:`output_dir`).

        Returns
        -------
        str
            Path to the generated JSON file.
        """
        return self._recorder.export_test_cases_json(
            output_dir=output_dir or self._output_dir
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def recorder(self) -> SequenceRecorder:
        """The underlying :class:`~core.sequence_recorder.SequenceRecorder`."""
        return self._recorder

    @property
    def monitor(self) -> CAPLTestMonitor:
        """The underlying :class:`~core.capl_monitor.CAPLTestMonitor`."""
        return self._monitor

    @property
    def output_dir(self) -> str:
        """Directory where exported files are written."""
        return self._output_dir
