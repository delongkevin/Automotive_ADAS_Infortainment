"""
Template: Launch Trace32 from config.json THEN connect
=======================================================
**No Python edits needed.**  All settings (paths, ports, timing) are read
from ``config.json`` and all test case definitions (breakpoints, variables
to check, expected values) are read from ``test_cases.json``.

Quick-start
-----------
1. Edit ``config.json`` – set ``t32_exe_path``, ``t32_config_path``, and
   ``rcl_port``.
2. Edit ``test_cases.json`` – add/update test cases, breakpoint symbols,
   and expected variable values.
3. Run this script::

       python connect_t32_launch.py

   Trace32 will start automatically, the framework will wait up to
   ``connect_max_wait_s`` seconds (set in ``config.json``) for it to
   become ready, run the test suite, then shut Trace32 down on exit.
   Reports are saved to ``test_cases_report.json`` and
   ``test_cases_report.html``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from GM_VIP_Automation_Framework import runner

# ---------------------------------------------------------------------------
# Paths – edit only if your files are in a different location.
# ---------------------------------------------------------------------------
CONFIG_JSON = Path(__file__).parent / "config.json"
TEST_CASES_JSON = Path(__file__).parent / "test_cases.json"

# ---------------------------------------------------------------------------
# Run (launch Trace32 from config.json paths, auto_launch=True)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    report = runner.run_from_json(
        test_cases_path=str(TEST_CASES_JSON),
        config_json_path=str(CONFIG_JSON) if CONFIG_JSON.is_file() else None,
        auto_launch=True,
    )
    print(report.summary())
    if report.failed > 0 or report.errored > 0:
        sys.exit(1)

