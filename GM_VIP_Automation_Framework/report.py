"""
GM VIP Automation Framework – Test Case Report
===============================================
Records breakpoints hit, variables read/written, and symbol states for each
test case executed via the framework and serialises the results as JSON or HTML.

The :class:`TestCaseReport` class is intentionally framework-agnostic: it holds
pure Python data structures so it can be used with or without an active Trace32
connection.

Typical usage
-------------
::

    from GM_VIP_Automation_Framework.report import TestCaseReport

    report = TestCaseReport(name="MySuite")

    report.begin_test_case("TC_Reset")
    try:
        t32.reset_target()
        value = t32.read_variable("myModule.myCounter")
        report.record_variable("myModule.myCounter", value)
        report.record_breakpoint("myFunc", hit=True)
        report.record_symbol("myFunc", exists=True, address="0x80001234")
        report.pass_test_case()
    except Exception as exc:
        report.fail_test_case(str(exc))

    report.save_json("report.json")
    report.save_html("report.html")
    print(report.summary())

Public API
----------
- :class:`TestCaseReport` – accumulates results across multiple test cases.
- :class:`TestCaseResult` – immutable snapshot of a single test case.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

__all__ = ["TestCaseReport", "TestCaseResult"]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TestCaseResult:
    """Snapshot of a single test case execution.

    Attributes
    ----------
    name:
        Test case identifier (mirrors the CAPL ``testcase`` name).
    status:
        ``"PASS"``, ``"FAIL"``, or ``"ERROR"``.
    error_message:
        Non-empty string when *status* is ``"FAIL"`` or ``"ERROR"``.
    breakpoints:
        Mapping ``{symbol: hit_bool}`` for every breakpoint registered during
        this test case.
    variables:
        Mapping ``{symbol: value_string}`` for every variable read or written.
    symbols:
        Mapping ``{symbol: {"exists": bool, "address": str}}`` for every symbol
        inspected.
    started_at:
        ISO-8601 timestamp when :meth:`TestCaseReport.begin_test_case` was
        called.
    ended_at:
        ISO-8601 timestamp when :meth:`TestCaseReport.pass_test_case` /
        :meth:`TestCaseReport.fail_test_case` was called.
    """

    name: str
    status: str = "PASS"
    error_message: str = ""
    breakpoints: Dict[str, bool] = field(default_factory=dict)
    variables: Dict[str, str] = field(default_factory=dict)
    symbols: Dict[str, dict] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: _now())
    ended_at: str = ""

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dictionary."""
        return {
            "name": self.name,
            "status": self.status,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "breakpoints": self.breakpoints,
            "variables": self.variables,
            "symbols": self.symbols,
        }


# ---------------------------------------------------------------------------
# Report accumulator
# ---------------------------------------------------------------------------

class TestCaseReport:
    """Accumulate results for multiple test cases and export reports.

    Parameters
    ----------
    name:
        Human-readable suite / test-module name (used in report headers).
    """

    def __init__(self, name: str = "TestSuite") -> None:
        self.name = name
        self._results: List[TestCaseResult] = []
        self._current: Optional[TestCaseResult] = None
        self._started_at: str = _now()

    # ------------------------------------------------------------------
    # Test-case lifecycle
    # ------------------------------------------------------------------

    def begin_test_case(self, name: str) -> None:
        """Start recording a new test case.

        If a test case is already in progress it is automatically closed as
        ``"ERROR"`` before the new one begins.

        Parameters
        ----------
        name:
            Test case identifier.
        """
        if self._current is not None:
            self._current.status = "ERROR"
            self._current.error_message = "Test case not closed before next begin_test_case()."
            self._current.ended_at = _now()
            self._results.append(self._current)
        self._current = TestCaseResult(name=name)

    def pass_test_case(self) -> None:
        """Mark the current test case as **PASS** and close it."""
        self._close_current("PASS")

    def fail_test_case(self, message: str = "") -> None:
        """Mark the current test case as **FAIL** and close it.

        Parameters
        ----------
        message:
            Description of the failure reason.
        """
        tc = self._ensure_current()
        tc.error_message = message
        self._close_current("FAIL")

    # ------------------------------------------------------------------
    # Recording helpers
    # ------------------------------------------------------------------

    def record_breakpoint(self, symbol: str, hit: bool) -> None:
        """Record whether a breakpoint on *symbol* was hit.

        Parameters
        ----------
        symbol:
            Symbol / function name used as the breakpoint target.
        hit:
            ``True`` when the ECU halted at the symbol; ``False`` otherwise.
        """
        self._ensure_current().breakpoints[symbol] = hit

    def record_variable(self, symbol: str, value: str) -> None:
        """Record a variable read or write value.

        Parameters
        ----------
        symbol:
            Variable symbol name (or a descriptive label like ``"myVar (write)"``).
        value:
            The value as a string.
        """
        self._ensure_current().variables[symbol] = str(value)

    def record_symbol(
        self,
        symbol: str,
        exists: bool,
        address: str = "",
    ) -> None:
        """Record the existence and address of a symbol.

        Parameters
        ----------
        symbol:
            Symbol name.
        exists:
            ``True`` when the symbol is in the loaded ELF debug information.
        address:
            Hexadecimal address string (empty when *exists* is ``False``).
        """
        self._ensure_current().symbols[symbol] = {
            "exists": exists,
            "address": address,
        }

    # ------------------------------------------------------------------
    # Aggregated results
    # ------------------------------------------------------------------

    @property
    def results(self) -> List[TestCaseResult]:
        """All completed :class:`TestCaseResult` objects (read-only list)."""
        return list(self._results)

    @property
    def passed(self) -> int:
        """Number of test cases with status ``"PASS"``."""
        return sum(1 for r in self._results if r.status == "PASS")

    @property
    def failed(self) -> int:
        """Number of test cases with status ``"FAIL"``."""
        return sum(1 for r in self._results if r.status == "FAIL")

    @property
    def errored(self) -> int:
        """Number of test cases with status ``"ERROR"``."""
        return sum(1 for r in self._results if r.status == "ERROR")

    @property
    def total(self) -> int:
        """Total number of completed test cases."""
        return len(self._results)

    def summary(self) -> str:
        """Return a one-line text summary of the report."""
        return (
            f"{self.name}: {self.total} test(s) – "
            f"{self.passed} PASS, {self.failed} FAIL, {self.errored} ERROR"
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dictionary of the full report."""
        return {
            "suite": self.name,
            "started_at": self._started_at,
            "ended_at": _now(),
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errored": self.errored,
            "test_cases": [r.to_dict() for r in self._results],
        }

    def save_json(self, path: str) -> None:
        """Write the full report as a JSON file.

        Parameters
        ----------
        path:
            Destination file path.
        """
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

    def save_html(self, path: str) -> None:
        """Write the report as a self-contained HTML file.

        Parameters
        ----------
        path:
            Destination file path.
        """
        Path(path).write_text(_render_html(self), encoding="utf-8")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_current(self) -> TestCaseResult:
        if self._current is None:
            raise RuntimeError(
                "No active test case. Call begin_test_case() first."
            )
        return self._current

    def _close_current(self, status: str) -> None:
        tc = self._ensure_current()
        tc.status = status
        tc.ended_at = _now()
        self._results.append(tc)
        self._current = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.now(tz=datetime.timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

def _render_html(report: TestCaseReport) -> str:
    """Produce a self-contained HTML report string."""

    def _badge(status: str) -> str:
        colour = {"PASS": "#28a745", "FAIL": "#dc3545", "ERROR": "#fd7e14"}.get(
            status, "#6c757d"
        )
        return (
            f'<span style="background:{colour};color:#fff;padding:2px 8px;'
            f'border-radius:4px;font-weight:bold">{status}</span>'
        )

    def _table(mapping: dict, headers: tuple) -> str:
        if not mapping:
            return "<em>none</em>"
        rows = ""
        for k, v in mapping.items():
            if isinstance(v, dict):
                rows += (
                    f"<tr><td>{k}</td>"
                    + "".join(f"<td>{v.get(h, '')}</td>" for h in headers[1:])
                    + "</tr>"
                )
            elif isinstance(v, bool):
                rows += f"<tr><td>{k}</td><td>{'✔' if v else '✘'}</td></tr>"
            else:
                rows += f"<tr><td>{k}</td><td>{v}</td></tr>"
        th = "".join(f"<th>{h}</th>" for h in headers)
        return f"<table border='1' cellpadding='4'><tr>{th}</tr>{rows}</table>"

    tcs_html = ""
    for tc in report.results:
        bp_html = _table(tc.breakpoints, ("Symbol", "Hit"))
        var_html = _table(tc.variables, ("Symbol", "Value"))
        sym_html = _table(tc.symbols, ("Symbol", "Exists", "Address"))
        tcs_html += f"""
        <details {"open" if tc.status != "PASS" else ""}>
          <summary>{_badge(tc.status)} {tc.name}
            &nbsp;<small style="color:#888">{tc.started_at} → {tc.ended_at}</small>
          </summary>
          {"<p style='color:red'>" + tc.error_message + "</p>" if tc.error_message else ""}
          <h4>Breakpoints</h4>{bp_html}
          <h4>Variables</h4>{var_html}
          <h4>Symbols</h4>{sym_html}
        </details>
        """

    overall_colour = "#28a745" if report.failed == 0 and report.errored == 0 else "#dc3545"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>T32 Test Report – {report.name}</title>
  <style>
    body {{ font-family: sans-serif; margin: 20px; }}
    table {{ border-collapse: collapse; margin-bottom: 10px; }}
    th {{ background: #e9ecef; }}
    td, th {{ padding: 4px 8px; text-align: left; }}
    details {{ border: 1px solid #dee2e6; border-radius: 4px;
               margin-bottom: 8px; padding: 8px; }}
    summary {{ cursor: pointer; font-size: 1.05em; }}
  </style>
</head>
<body>
  <h1>T32 Test Report</h1>
  <h2 style="color:{overall_colour}">{report.name}</h2>
  <p>
    Generated: {_now()}<br>
    Total: <strong>{report.total}</strong> &nbsp;
    Pass: <strong style="color:#28a745">{report.passed}</strong> &nbsp;
    Fail: <strong style="color:#dc3545">{report.failed}</strong> &nbsp;
    Error: <strong style="color:#fd7e14">{report.errored}</strong>
  </p>
  {tcs_html}
</body>
</html>
"""
