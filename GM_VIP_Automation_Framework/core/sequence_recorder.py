"""
GM VIP Automation Framework – Execution Sequence Recorder
==========================================================
Records all significant test-execution events that occur during a combined
CANoe + Trace32 test run, then converts the captured trace into:

1. A ``*_test_cases.json`` file that the existing
   :func:`~GM_VIP_Automation_Framework.runner.run_from_json` engine can
   replay in future runs.
2. A standalone Python test script (``*_session_script.py``) that can be
   committed to the CI repository and run headlessly via ``pytest``.

Why this matters
----------------
When a SW test engineer runs CAPL tests interactively on their local bench
with Vector CANoe, the *sequence* of breakpoints set, variable reads/writes,
GO/reset commands, and expected CAPL verdicts encodes valuable test
knowledge.  The recorder captures that knowledge automatically so it can
be replayed in a Jenkins CT environment without the engineer being present.

Recorded event types
--------------------
``go``
    ECU resumed execution (via GO command or reset-and-go).
``halt``
    ECU halted (breakpoint hit or manual BREAK).
``breakpoint_set``
    A software breakpoint was placed at a symbol.
``breakpoint_cleared``
    A breakpoint was removed.
``variable_read``
    A variable was read from ECU memory.
``variable_write``
    A variable was written to ECU memory.
``reset``
    ECU was reset.
``capl_result``
    A CAPL test case result was captured from CANoe.
``custom``
    Free-form annotation added by the caller.

Usage
-----
::

    from GM_VIP_Automation_Framework.core.sequence_recorder import SequenceRecorder

    recorder = SequenceRecorder()
    recorder.start_recording()

    # ... drive the bench (go, break, read variables, watch CAPL results) ...

    recorder.record_event("breakpoint_set", symbol="TestCan_Init")
    recorder.record_event("go")
    recorder.record_event("halt", symbol="TestCan_Init")
    recorder.record_event("variable_read", symbol="g_CanStatus", value=1)
    recorder.record_event("capl_result", symbol="TC_001_CanInit", value="PASS")

    events = recorder.stop_recording()
    json_path = recorder.export_test_cases_json(output_dir="./output")
    py_path   = recorder.export_python_script(output_dir="./output")
"""

from __future__ import annotations

import datetime
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger

__all__ = [
    "ExecutionEvent",
    "SequenceRecorder",
]

logger = get_logger("sequence_recorder")

# ---------------------------------------------------------------------------
# Allowed event types
# ---------------------------------------------------------------------------

_VALID_EVENT_TYPES = frozenset({
    "go",
    "halt",
    "breakpoint_set",
    "breakpoint_cleared",
    "variable_read",
    "variable_write",
    "reset",
    "capl_result",
    "custom",
})


# ---------------------------------------------------------------------------
# ExecutionEvent
# ---------------------------------------------------------------------------

@dataclass
class ExecutionEvent:
    """A single captured execution event.

    Attributes
    ----------
    event_type :
        One of the recognised event type strings (see module docstring).
    symbol :
        The T32 symbol, variable, or CAPL test case name associated with
        the event.  Empty string when not applicable (e.g. ``"go"``).
    value :
        The associated value at the time of the event (variable value,
        CAPL verdict string, etc.).  ``None`` when not applicable.
    timestamp :
        Unix wall-clock time when the event was recorded.
    metadata :
        Optional free-form dict for extra context (e.g. ``{"core": 0}``).
    """

    event_type: str
    symbol: str = ""
    value: Any = None
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict of this event."""
        return {
            "event_type": self.event_type,
            "symbol":     self.symbol,
            "value":      self.value,
            "timestamp":  self.timestamp,
            "metadata":   self.metadata,
        }

    def __repr__(self) -> str:
        parts = [f"type={self.event_type!r}"]
        if self.symbol:
            parts.append(f"symbol={self.symbol!r}")
        if self.value is not None:
            parts.append(f"value={self.value!r}")
        return f"ExecutionEvent({', '.join(parts)})"


# ---------------------------------------------------------------------------
# SequenceRecorder
# ---------------------------------------------------------------------------

class SequenceRecorder:
    """Records T32 + CANoe execution events and exports them as replayable tests.

    Parameters
    ----------
    session_name :
        Label used in generated filenames (e.g. ``"can_init_sequence"``).
        Defaults to a UTC timestamp string.
    """

    def __init__(self, session_name: Optional[str] = None) -> None:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._session_name = session_name or f"recorded_{ts}"
        self._events: List[ExecutionEvent] = []
        self._recording = False
        self._t_start: float = 0.0

    # ------------------------------------------------------------------
    # Recording control
    # ------------------------------------------------------------------

    def start_recording(self) -> None:
        """Begin capturing events.

        Clears any previously recorded events and marks the recorder as
        active.  Subsequent calls to :meth:`record_event` will be stored.
        """
        self._events = []
        self._recording = True
        self._t_start = time.monotonic()
        logger.info("SequenceRecorder '%s' started.", self._session_name)

    def stop_recording(self) -> List[ExecutionEvent]:
        """Stop capturing and return the complete event list.

        Returns
        -------
        List[ExecutionEvent]
            All events recorded since the last :meth:`start_recording` call,
            in chronological order.
        """
        self._recording = False
        elapsed = time.monotonic() - self._t_start
        logger.info(
            "SequenceRecorder '%s' stopped after %.1f s – %d event(s) captured.",
            self._session_name, elapsed, len(self._events),
        )
        return list(self._events)

    @property
    def is_recording(self) -> bool:
        """``True`` when the recorder is actively capturing events."""
        return self._recording

    # ------------------------------------------------------------------
    # Event capture
    # ------------------------------------------------------------------

    def record_event(
        self,
        event_type: str,
        symbol: str = "",
        value: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionEvent:
        """Record a single execution event.

        Parameters
        ----------
        event_type :
            Event category (see :data:`_VALID_EVENT_TYPES`).  An unknown
            type is accepted but logged as a warning.
        symbol :
            Associated symbol / test-case name.
        value :
            Associated value at event time.
        metadata :
            Optional extra dict merged into the event.

        Returns
        -------
        ExecutionEvent
            The newly created event (also stored internally).
        """
        if event_type not in _VALID_EVENT_TYPES:
            logger.warning(
                "Unknown event type %r – recording as 'custom'.", event_type
            )
            event_type = "custom"

        event = ExecutionEvent(
            event_type=event_type,
            symbol=symbol,
            value=value,
            metadata=metadata or {},
        )

        if self._recording:
            self._events.append(event)
            logger.debug("Recorded: %r", event)
        else:
            logger.debug(
                "Event recorded outside active session (not stored): %r", event
            )

        return event

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    def record_go(self) -> ExecutionEvent:
        """Record an ECU GO event."""
        return self.record_event("go")

    def record_halt(self, symbol: str = "") -> ExecutionEvent:
        """Record an ECU HALT event at an optional symbol."""
        return self.record_event("halt", symbol=symbol)

    def record_reset(self) -> ExecutionEvent:
        """Record an ECU RESET event."""
        return self.record_event("reset")

    def record_breakpoint_set(self, symbol: str) -> ExecutionEvent:
        """Record that a breakpoint was set at *symbol*."""
        return self.record_event("breakpoint_set", symbol=symbol)

    def record_breakpoint_cleared(self, symbol: str) -> ExecutionEvent:
        """Record that a breakpoint was cleared at *symbol*."""
        return self.record_event("breakpoint_cleared", symbol=symbol)

    def record_variable_read(self, symbol: str, value: Any) -> ExecutionEvent:
        """Record a variable read result."""
        return self.record_event("variable_read", symbol=symbol, value=value)

    def record_variable_write(self, symbol: str, value: Any) -> ExecutionEvent:
        """Record a variable write operation."""
        return self.record_event("variable_write", symbol=symbol, value=value)

    def record_capl_result(self, test_name: str, verdict: str, module: str = "") -> ExecutionEvent:
        """Record a CAPL test case result.

        Parameters
        ----------
        test_name : CAPL test case name.
        verdict   : ``"PASS"``, ``"FAIL"``, ``"ERROR"``, etc.
        module    : Parent test module name (optional).
        """
        return self.record_event(
            "capl_result",
            symbol=test_name,
            value=verdict,
            metadata={"module": module} if module else {},
        )

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    @property
    def events(self) -> List[ExecutionEvent]:
        """Read-only copy of all recorded events."""
        return list(self._events)

    def get_events_by_type(self, event_type: str) -> List[ExecutionEvent]:
        """Return all events of a specific type."""
        return [e for e in self._events if e.event_type == event_type]

    def get_capl_failures(self) -> List[ExecutionEvent]:
        """Return all CAPL result events with a non-PASS verdict."""
        return [
            e for e in self._events
            if e.event_type == "capl_result"
            and str(e.value).upper() not in ("PASS", "NONE", "NOTRUN")
        ]

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_test_cases_json(
        self,
        output_dir: str = ".",
        filename: Optional[str] = None,
    ) -> str:
        """Export the recorded sequence as a ``*_test_cases.json`` file.

        The generated JSON is compatible with the
        :func:`~GM_VIP_Automation_Framework.runner.run_from_json` engine.
        Each group of ``breakpoint_set`` → ``go`` → ``halt`` →
        ``variable_read`` events is collapsed into a single test-case entry.

        Parameters
        ----------
        output_dir :
            Directory in which to write the JSON file.
        filename :
            Override the default ``<session_name>_test_cases.json`` name.

        Returns
        -------
        str
            Absolute path of the written JSON file.
        """
        test_cases = self._events_to_test_cases()
        payload = {"test_cases": test_cases}

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = filename or f"{self._session_name}_test_cases.json"
        out_path = out_dir / fname
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Exported %d test case(s) → %s", len(test_cases), out_path)
        return str(out_path)

    def export_python_script(
        self,
        output_dir: str = ".",
        filename: Optional[str] = None,
    ) -> str:
        """Export the recorded sequence as a standalone Python test script.

        The generated script can be imported by pytest or run directly.  It
        uses the ``GM_VIP_Automation_Framework`` public API so it works in
        both mock (CI) and live (bench) modes.

        Parameters
        ----------
        output_dir :
            Directory in which to write the ``.py`` file.
        filename :
            Override the default ``<session_name>_session_script.py`` name.

        Returns
        -------
        str
            Absolute path of the written Python file.
        """
        script = self._events_to_python_script()

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = filename or f"{self._session_name}_session_script.py"
        out_path = out_dir / fname
        out_path.write_text(script, encoding="utf-8")
        logger.info("Exported Python session script → %s", out_path)
        return str(out_path)

    def export_events_json(
        self,
        output_dir: str = ".",
        filename: Optional[str] = None,
    ) -> str:
        """Export the raw event list as a JSON trace file.

        Unlike :meth:`export_test_cases_json`, this preserves the full
        event timeline (useful for post-mortem debugging).

        Returns
        -------
        str
            Absolute path of the written JSON trace file.
        """
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = filename or f"{self._session_name}_trace.json"
        out_path = out_dir / fname
        payload = {
            "session": self._session_name,
            "events": [e.to_dict() for e in self._events],
        }
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Exported raw event trace → %s", out_path)
        return str(out_path)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _events_to_test_cases(self) -> List[dict]:
        """Convert the event list into runner-compatible test-case dicts."""
        test_cases: List[dict] = []
        current: Optional[dict] = None

        for evt in self._events:
            etype = evt.event_type

            if etype == "reset":
                if current is not None:
                    test_cases.append(current)
                name = f"TC_{len(test_cases) + 1:03d}_reset"
                current = {
                    "name": name,
                    "enabled": True,
                    "reset_before": True,
                    "go_before_check": False,
                    "breakpoints": [],
                    "variables_write": {},
                    "variables_check": {},
                    "symbols_inspect": [],
                }

            elif etype == "breakpoint_set":
                if current is None:
                    name = f"TC_{len(test_cases) + 1:03d}_{_sanitise(evt.symbol)}"
                    current = _empty_test_case(name)
                current["breakpoints"].append(evt.symbol)

            elif etype == "go":
                if current is not None:
                    current["go_before_check"] = True

            elif etype == "variable_write":
                if current is None:
                    current = _empty_test_case(
                        f"TC_{len(test_cases) + 1:03d}_write_{_sanitise(evt.symbol)}"
                    )
                if evt.value is not None:
                    current["variables_write"][evt.symbol] = evt.value

            elif etype == "variable_read":
                if current is None:
                    current = _empty_test_case(
                        f"TC_{len(test_cases) + 1:03d}_read_{_sanitise(evt.symbol)}"
                    )
                if evt.value is not None:
                    current["variables_check"][evt.symbol] = evt.value
                else:
                    current["symbols_inspect"].append(evt.symbol)

            elif etype == "halt":
                # Finalise and store the current test case.
                if current is not None:
                    if evt.symbol and evt.symbol not in current["breakpoints"]:
                        current["symbols_inspect"].append(evt.symbol)
                    test_cases.append(current)
                    current = None

            elif etype == "capl_result":
                # CAPL results become standalone test case entries tagged
                # as symbols_inspect so they appear in reports.
                tc = _empty_test_case(
                    f"TC_{len(test_cases) + 1:03d}_capl_{_sanitise(evt.symbol)}"
                )
                tc["symbols_inspect"].append(evt.symbol)
                tc["metadata"] = {"capl_verdict": evt.value}
                test_cases.append(tc)

        # Flush any open test case at end of recording.
        if current is not None:
            test_cases.append(current)

        return test_cases

    def _events_to_python_script(self) -> str:
        """Generate a Python pytest script from the recorded events."""
        lines: List[str] = [
            '"""',
            f"Auto-generated session script: {self._session_name}",
            f"Generated: {datetime.datetime.now(datetime.timezone.utc).isoformat()} UTC",
            "",
            "Replay this recorded CANoe + Trace32 test sequence.",
            "Run with:  pytest " + f"{self._session_name}_session_script.py",
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "import unittest",
            "",
            "import GM_VIP_Automation_Framework as t32",
            "from GM_VIP_Automation_Framework.core.canoe import CANoeClient",
            "from GM_VIP_Automation_Framework.core.capl_monitor import CAPLTestMonitor",
            "",
            "",
            f"class Test_{_to_class_name(self._session_name)}(unittest.TestCase):",
            '    """Recorded sequence from session: ' + self._session_name + '."""',
            "",
            "    MOCK = True  # Set to False for live bench execution",
            "",
            "    @classmethod",
            "    def setUpClass(cls):",
            "        cls.canoe = CANoeClient(mock=cls.MOCK)",
            "        cls.canoe.connect()",
            "",
        ]

        # Group events into test methods.
        test_methods = self._group_events_as_methods()
        for method_name, method_lines in test_methods:
            lines.append(f"    def {method_name}(self):")
            lines.extend(f"        {l}" for l in method_lines)
            lines.append("")

        lines += [
            "    @classmethod",
            "    def tearDownClass(cls):",
            "        cls.canoe.disconnect()",
            "",
            "",
            'if __name__ == "__main__":',
            "    unittest.main()",
            "",
        ]
        return "\n".join(lines)

    def _group_events_as_methods(self) -> List[tuple]:
        """Yield (method_name, code_lines) pairs for each test method."""
        methods: List[tuple] = []
        tc_idx = 0
        current_lines: List[str] = []
        current_name = ""
        bps: List[str] = []

        def _flush():
            nonlocal current_name, current_lines, bps
            if current_lines:
                methods.append((current_name, list(current_lines)))
            current_lines = []
            bps = []

        for evt in self._events:
            etype = evt.event_type
            if etype == "breakpoint_set":
                if not current_lines:
                    tc_idx += 1
                    current_name = f"test_{tc_idx:03d}_{_sanitise(evt.symbol)}"
                    current_lines.append("# Set breakpoints")
                current_lines.append(
                    f't32.set_breakpoint("{evt.symbol}")'
                )
                bps.append(evt.symbol)

            elif etype == "go":
                if not current_lines:
                    tc_idx += 1
                    current_name = f"test_{tc_idx:03d}_go"
                current_lines.append("t32.go()")

            elif etype == "halt":
                if evt.symbol:
                    current_lines.append(
                        f't32.check_halted_at("{evt.symbol}")'
                    )
                _flush()

            elif etype == "variable_write":
                if not current_lines:
                    tc_idx += 1
                    current_name = f"test_{tc_idx:03d}_write_{_sanitise(evt.symbol)}"
                current_lines.append(
                    f't32.set_variable("{evt.symbol}", {evt.value!r})'
                )

            elif etype == "variable_read":
                if not current_lines:
                    tc_idx += 1
                    current_name = f"test_{tc_idx:03d}_read_{_sanitise(evt.symbol)}"
                if evt.value is not None:
                    current_lines.append(
                        f'self.assertEqual(t32.read_variable("{evt.symbol}"), {evt.value!r})'
                    )
                else:
                    current_lines.append(
                        f't32.read_variable("{evt.symbol}")'
                    )

            elif etype == "reset":
                if not current_lines:
                    tc_idx += 1
                    current_name = f"test_{tc_idx:03d}_reset"
                current_lines.append("t32.reset_target()")
                _flush()

            elif etype == "capl_result":
                if not current_lines:
                    tc_idx += 1
                    current_name = f"test_{tc_idx:03d}_capl_{_sanitise(evt.symbol)}"
                current_lines.append(
                    f'# CAPL verdict for {evt.symbol!r}: {evt.value}'
                )
                current_lines.append(
                    "monitor = CAPLTestMonitor(self.canoe)"
                )
                current_lines.append(
                    f'failures = [r for r in monitor.get_test_results() '
                    f'if r.name == {evt.symbol!r} and r.failed]'
                )
                current_lines.append(
                    f'self.assertFalse(failures, f"CAPL test {evt.symbol!r} failed")'
                )
                _flush()

        _flush()
        return methods


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitise(name: str) -> str:
    """Convert a symbol name to a safe Python identifier fragment."""
    out = []
    for ch in name:
        out.append(ch if ch.isalnum() else "_")
    result = "".join(out).strip("_")
    return result[:40] if result else "sym"


def _to_class_name(name: str) -> str:
    """Convert a session name to a PascalCase class name fragment."""
    parts = name.replace("-", "_").split("_")
    return "".join(p.capitalize() for p in parts if p)


def _empty_test_case(name: str) -> dict:
    return {
        "name": name,
        "enabled": True,
        "reset_before": False,
        "go_before_check": False,
        "breakpoints": [],
        "variables_write": {},
        "variables_check": {},
        "symbols_inspect": [],
    }
