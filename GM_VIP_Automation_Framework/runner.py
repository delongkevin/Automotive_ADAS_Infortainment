"""
GM VIP Automation Framework – JSON-driven Test Runner
======================================================
Loads two JSON files and executes an entire test suite against Trace32
without any changes to Python source code:

- **config.json** – Trace32 paths, ports, and timing settings.
- **test_cases.json** – test case definitions: breakpoints, variable
  writes, variable checks with expected values, symbol inspections, and
  CAPL references.

Typical workflow
----------------
1. Edit ``config.json`` to point at your ``t32marm64.exe`` and
   ``config.t32``.
2. Edit ``test_cases.json`` to describe your CAPL test cases (one JSON
   object per test case).
3. Run the tests in one line::

       python -c "
       from GM_VIP_Automation_Framework import runner
       runner.run_from_json('test_cases.json', connect_only=True)
       "

   Or connect and launch T32 automatically::

       runner.run_from_json('test_cases.json', auto_launch=True)

Public API
----------
- :func:`run_from_json` – load both JSON files and execute the suite.
- :func:`load_test_cases` – parse a ``test_cases.json`` into a list of
  :class:`TestCaseDef` dicts (useful for inspection / custom runners).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import GM_VIP_Automation_Framework as t32
from .config import settings
from .report import TestCaseReport

__all__ = ["run_from_json", "load_test_cases"]


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def load_test_cases(path: str) -> List[Dict[str, Any]]:
    """Parse a ``test_cases.json`` file and return the list of test-case dicts.

    Parameters
    ----------
    path:
        Path to the ``test_cases.json`` file.

    Returns
    -------
    list[dict]
        Each element is a raw test-case definition dict (keys: ``name``,
        ``capl_reference``, ``enabled``, ``reset_before``, ``breakpoints``,
        ``variables_write``, ``variables_check``, ``symbols_inspect``).

    Raises
    ------
    FileNotFoundError
        When *path* does not exist.
    ValueError
        When the file is not valid JSON or is missing the ``test_cases`` key.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"test_cases.json not found: {path}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in '{path}': {exc}") from exc

    if "test_cases" not in raw:
        raise ValueError(f"'{path}' must contain a top-level 'test_cases' list.")
    return raw["test_cases"]


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

def run_from_json(
    test_cases_path: str,
    config_json_path: Optional[str] = None,
    auto_launch: bool = False,
    report_json: Optional[str] = None,
    report_html: Optional[str] = None,
) -> TestCaseReport:
    """Load ``test_cases.json`` (and optionally ``config.json``) and run all
    enabled test cases against Trace32.

    Parameters
    ----------
    test_cases_path:
        Path to the ``test_cases.json`` file that defines the test suite.
    config_json_path:
        Path to ``config.json``.  When *None* the function looks for a
        ``config.json`` file in the same directory as *test_cases_path*.
        Pass ``""`` to skip JSON config loading entirely (use current
        :data:`~config.settings` values or environment variables).
    auto_launch:
        When ``True`` the Trace32 process is started before connecting,
        using :attr:`~config.T32Settings.t32_exe_path` and
        :attr:`~config.T32Settings.t32_config_path`.  When ``False``
        (default) the framework connects to an already-running Trace32.
    report_json:
        Output path for the JSON report.  Defaults to
        ``<test_cases_path_stem>_report.json``.
    report_html:
        Output path for the HTML report.  Defaults to
        ``<test_cases_path_stem>_report.html``.

    Returns
    -------
    TestCaseReport
        The completed report object (results already saved to disk when
        *report_json* / *report_html* are not ``None``).
    """
    tc_path = Path(test_cases_path)

    # ------------------------------------------------------------------
    # 1. Load config.json into settings
    # ------------------------------------------------------------------
    if config_json_path is None:
        candidate = tc_path.parent / "config.json"
        if candidate.is_file():
            config_json_path = str(candidate)

    if config_json_path:
        settings.load_from_json(config_json_path)

    # ------------------------------------------------------------------
    # 2. Parse test_cases.json
    # ------------------------------------------------------------------
    raw_json = json.loads(tc_path.read_text(encoding="utf-8"))
    suite_name = raw_json.get("test_suite", tc_path.stem)
    test_case_defs = raw_json.get("test_cases", [])

    # ------------------------------------------------------------------
    # 3. Connect to Trace32
    # ------------------------------------------------------------------
    report = TestCaseReport(name=suite_name)
    conn = t32.T32Connection(
        exe_path=settings.t32_exe_path,
        config_path=settings.t32_config_path,
        port=settings.rcl_port,
        protocol=settings.rcl_protocol,
    )
    if auto_launch:
        conn.launch()

    with conn:
        conn.connect()

        import GM_VIP_Automation_Framework.core.debugger as _dbg
        _dbg.default_connection = conn

        # ------------------------------------------------------------------
        # 4. Execute each test case
        # ------------------------------------------------------------------
        for tc_def in test_case_defs:
            # Skip disabled or comment-only entries.
            if not tc_def.get("enabled", True):
                continue
            # Skip entries that are just _comment lines (no "name" key).
            if "name" not in tc_def:
                continue

            _run_one(tc_def, conn, report)

        # Clean up default connection reference.
        _dbg.default_connection = None

    # ------------------------------------------------------------------
    # 5. Save reports
    # ------------------------------------------------------------------
    stem = str(tc_path.with_suffix(""))
    if report_json is None:
        report_json = f"{stem}_report.json"
    if report_html is None:
        report_html = f"{stem}_report.html"

    report.save_json(report_json)
    report.save_html(report_html)
    return report


# ---------------------------------------------------------------------------
# Single test-case executor
# ---------------------------------------------------------------------------

def _run_one(tc_def: dict, conn: t32.T32Connection, report: TestCaseReport) -> None:
    """Execute a single test case defined by *tc_def* and record results."""
    name = tc_def["name"]
    capl_ref = tc_def.get("capl_reference", "")
    reset_before = tc_def.get("reset_before", False)
    breakpoints: List[str] = tc_def.get("breakpoints", [])
    variables_write: Dict[str, Any] = tc_def.get("variables_write", {})
    variables_check: Dict[str, Any] = tc_def.get("variables_check", {})
    symbols_inspect: List[str] = tc_def.get("symbols_inspect", [])

    report.begin_test_case(name)
    # Store CAPL reference as a special variable entry for traceability.
    if capl_ref:
        report.record_variable("_capl_reference", capl_ref)

    try:
        # -- Optional reset -------------------------------------------------
        if reset_before:
            t32.reset_target(connection=conn)
        t32.delete_all_breakpoints(connection=conn)

        # -- Inspect symbols ------------------------------------------------
        for sym in symbols_inspect:
            exists = t32.symbol_exists(sym, connection=conn)
            addr = ""
            if exists:
                try:
                    addr = t32.get_symbol_address(sym, connection=conn)
                except Exception:  # noqa: BLE001
                    addr = "N/A"
            report.record_symbol(sym, exists=exists, address=addr)

        # -- Write pre-condition variables ----------------------------------
        for sym, spec in variables_write.items():
            # Accept both {"value": "1", ...} dict and plain string "1".
            val = spec["value"] if isinstance(spec, dict) else str(spec)
            t32.set_variable(sym, val, connection=conn)
            report.record_variable(f"{sym} (write)", val)

        # -- Set breakpoints and run ----------------------------------------
        if breakpoints:
            for sym in breakpoints:
                t32.set_breakpoint(sym, connection=conn)

            t32.go(connection=conn)

            for sym in breakpoints:
                t32.check_halted_at(sym, connection=conn)
                report.record_breakpoint(sym, hit=True)

        # -- Read / validate variables --------------------------------------
        for sym, spec in variables_check.items():
            # Accept both {"expected": "0x01", ...} dict and plain None/string.
            if isinstance(spec, dict):
                expected = spec.get("expected")
            else:
                expected = spec  # None or a string value

            value = t32.read_variable(sym, connection=conn)
            report.record_variable(sym, value)

            if expected is not None:
                t32.check_variable(sym, str(expected), connection=conn)

        # -- Clean up -------------------------------------------------------
        t32.delete_all_breakpoints(connection=conn)
        report.pass_test_case()

    except Exception as exc:  # noqa: BLE001
        try:
            t32.delete_all_breakpoints(connection=conn)
        except Exception:  # noqa: BLE001
            pass
        report.fail_test_case(str(exc))
