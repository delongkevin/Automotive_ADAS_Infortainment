"""
Template: CAPL Test Case → Python
==================================
Copy this file for **each** CAPL test function you want to replicate in Python.
Fill in the *CONFIGURE* sections and the framework will:

- Set all required breakpoints.
- Manipulate the same variables your CAPL testcase reads/writes.
- Query the same symbols.
- Build a detailed per-test-case report (breakpoints hit, variable values,
  symbol addresses).

CAPL → Python mapping guide
----------------------------
+-------------------------------------+-----------------------------------------+
| CAPL (tsT32.cin / testSupportLib)   | Python (GM_VIP_Automation_Framework)    |
+=====================================+=========================================+
| A_DBGR_BreakpointSet(sym)           | t32.set_breakpoint(sym, connection=conn)|
| A_DBGR_BreakpointDelete(sym)        | t32.delete_breakpoint(sym, …)           |
| A_DBGR_BreakpointDeleteAll()        | t32.delete_all_breakpoints(…)           |
| A_DBGR_Go()                         | t32.go(connection=conn)                 |
| A_DBGR_Break()                      | t32.break_execution(connection=conn)    |
| A_DBGR_Reset()                      | t32.reset_target(connection=conn)       |
| A_DBGR_CheckHaltedAt(sym)           | t32.check_halted_at(sym, …)             |
| A_DBGR_VariableRead(sym)            | t32.read_variable(sym, …)               |
| A_DBGR_VariableWrite(sym, val)      | t32.set_variable(sym, val, …)           |
| A_DBGR_VariableCheck(sym, exp)      | t32.check_variable(sym, exp, …)         |
| A_DBGR_RegisterRead(reg)            | t32.read_register(reg, …)               |
| A_DBGR_RegisterCheck(reg, exp)      | t32.check_register(reg, exp, …)         |
| SYMBOL.EXIST(sym)                   | t32.symbol_exists(sym, …)               |
| ADDRESS.OFFSET(SYMBOL.BEGIN(sym))   | t32.get_symbol_address(sym, …)          |
+-------------------------------------+-----------------------------------------+

Usage
-----
1. Copy this file to your test project and rename it to match your CAPL
   test function, e.g. ``tc_my_feature.py``.
2. Edit the CONFIGURE sections below.
3. Integrate :func:`run` into your test suite or call it directly::

       python tc_my_feature.py
"""

from __future__ import annotations

from pathlib import Path

import GM_VIP_Automation_Framework as t32
from GM_VIP_Automation_Framework.config import settings
from GM_VIP_Automation_Framework.report import TestCaseReport

# ---------------------------------------------------------------------------
# CONFIGURE – edit these values to match your CAPL test case
# ---------------------------------------------------------------------------

#: Name of this test case (mirrors the CAPL testcase name).
TEST_CASE_NAME = "TC_MyFeature"

#: Path to config.json.  Adjust if your file is in a different location.
CONFIG_JSON = Path(__file__).parent / "config.json"

# Symbols / functions used as breakpoints.
BREAKPOINT_SYMBOLS = [
    "myTargetFunction",          # e.g. A_DBGR_BreakpointSet("myTargetFunction")
    # "anotherFunction",         # add more as needed
]

# Variables read after halt (mirrors A_DBGR_VariableRead in CAPL).
# Keys are symbol names; values are the expected values (or None to skip check).
VARIABLES_TO_READ = {
    "myModule.myCounter": None,   # just read, no assertion
    "myModule.myStatus": "0x01",  # read and assert equals "0x01"
}

# Variables to write before GO (mirrors A_DBGR_VariableWrite in CAPL).
# Keys are symbol names; values are what to write.
VARIABLES_TO_WRITE = {
    "myModule.myFlag": "1",
}

# Symbols whose existence and address will be recorded in the report.
SYMBOLS_TO_INSPECT = [
    "myTargetFunction",
    "myModule",
]

# ---------------------------------------------------------------------------
# Test-case implementation
# ---------------------------------------------------------------------------

def run(conn: t32.T32Connection, report: TestCaseReport) -> bool:
    """Execute this test case using *conn* and record results in *report*.

    Parameters
    ----------
    conn:
        An established :class:`~GM_VIP_Automation_Framework.T32Connection`.
    report:
        The :class:`~GM_VIP_Automation_Framework.report.TestCaseReport` instance
        that accumulates results across all test cases.

    Returns
    -------
    bool
        ``True`` if the test case passed, ``False`` otherwise.
    """
    report.begin_test_case(TEST_CASE_NAME)
    try:
        # -- Reset target and clean slate ------------------------------------
        t32.reset_target(connection=conn)
        t32.delete_all_breakpoints(connection=conn)

        # -- Inspect symbols -------------------------------------------------
        for sym in SYMBOLS_TO_INSPECT:
            exists = t32.symbol_exists(sym, connection=conn)
            addr = t32.get_symbol_address(sym, connection=conn) if exists else "N/A"
            report.record_symbol(sym, exists=exists, address=addr)

        # -- Write pre-condition variables -----------------------------------
        for sym, val in VARIABLES_TO_WRITE.items():
            t32.set_variable(sym, val, connection=conn)
            report.record_variable(f"{sym} (write)", val)

        # -- Set all breakpoints ---------------------------------------------
        for sym in BREAKPOINT_SYMBOLS:
            t32.set_breakpoint(sym, connection=conn)

        # -- Run until first breakpoint --------------------------------------
        t32.go(connection=conn)

        for sym in BREAKPOINT_SYMBOLS:
            t32.check_halted_at(sym, connection=conn)
            report.record_breakpoint(sym, hit=True)

        # -- Read and optionally assert variables ----------------------------
        for sym, expected in VARIABLES_TO_READ.items():
            value = t32.read_variable(sym, connection=conn)
            report.record_variable(sym, value)
            if expected is not None:
                t32.check_variable(sym, expected, connection=conn)

        # -- Clean up --------------------------------------------------------
        t32.delete_all_breakpoints(connection=conn)
        report.pass_test_case()
        return True

    except Exception as exc:  # noqa: BLE001
        t32.delete_all_breakpoints(connection=conn)
        report.fail_test_case(str(exc))
        return False


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def _main() -> None:
    """Run this test case standalone (loads config.json, connects, reports)."""
    if CONFIG_JSON.is_file():
        settings.load_from_json(str(CONFIG_JSON))

    report = TestCaseReport(name=TEST_CASE_NAME)

    with t32.T32Connection(
        port=settings.rcl_port,
        protocol=settings.rcl_protocol,
    ) as conn:
        conn.connect()
        run(conn, report)

    report.save_json(f"{TEST_CASE_NAME}_report.json")
    report.save_html(f"{TEST_CASE_NAME}_report.html")
    print(report.summary())


if __name__ == "__main__":
    _main()
