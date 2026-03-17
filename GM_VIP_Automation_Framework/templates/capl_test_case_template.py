"""
Template: CAPL Test Case → Python (JSON-driven)
================================================
**No Python edits needed.**  All test case parameters — breakpoints,
variables to write/check, expected values, CAPL references — are defined in
``test_cases.json``.  Only edit the JSON files:

- ``config.json``     – Trace32 paths, ports, timing settings.
- ``test_cases.json`` – one entry per CAPL test case: breakpoints, variable
  writes, variable checks with expected values, symbol inspections.

CAPL → JSON → Python mapping guide
-------------------------------------
+------------------------------------------+------------------------------------------+
| CAPL (tsT32.cin / testSupportLib)        | test_cases.json key                      |
+==========================================+==========================================+
| testcase TC_MyFeature { … }              | "name": "TC_MyFeature"                   |
| A_DBGR_BreakpointSet("myFunc")          | "breakpoints": ["myFunc"]                |
| A_DBGR_VariableWrite("myFlag", 1)        | "variables_write":                       |
|                                          |   {"myFlag": {"value":"1", …}}           |
| A_DBGR_VariableRead("myCounter")         | "variables_check":                       |
|                                          |   {"myCounter": {"expected": null, …}}   |
| A_DBGR_VariableCheck("myStatus","0x01")  | "variables_check":                       |
|                                          |   {"myStatus": {"expected":"0x01", …}}   |
| SYMBOL.EXIST("myFunc")                   | "symbols_inspect": ["myFunc"]            |
| A_DBGR_Reset()                           | "reset_before": true                     |
+------------------------------------------+------------------------------------------+

Usage
-----
1. Copy ``test_cases.json`` template to your project root and fill in your
   CAPL test case names, breakpoints, and expected variable values.
2. Copy ``config.json`` template and set ``t32_exe_path``, ``t32_config_path``,
   and ``rcl_port``.
3. Run::

       python capl_test_case_template.py

   Reports are written to ``test_cases_report.json`` and
   ``test_cases_report.html`` automatically.
"""

from __future__ import annotations

import sys
from pathlib import Path

from GM_VIP_Automation_Framework import runner

# ---------------------------------------------------------------------------
# Paths – edit only if your files are in a different location.
# ---------------------------------------------------------------------------
TEST_CASES_JSON = Path(__file__).parent / "test_cases.json"
CONFIG_JSON = Path(__file__).parent / "config.json"

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Connect to an already-running Trace32 (auto_launch=False is default).
    # Set auto_launch=True to have the framework start Trace32 itself.
    report = runner.run_from_json(
        test_cases_path=str(TEST_CASES_JSON),
        config_json_path=str(CONFIG_JSON) if CONFIG_JSON.is_file() else None,
        auto_launch=False,
    )
    print(report.summary())
    if report.failed > 0 or report.errored > 0:
        sys.exit(1)

