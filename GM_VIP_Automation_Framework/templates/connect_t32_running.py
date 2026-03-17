"""
Template: Connect to a Trace32 instance that is ALREADY RUNNING
================================================================
**No Python edits needed.**  All settings (paths, ports, timing) are read
from ``config.json`` and all test case definitions (breakpoints, variables
to check, expected values) are read from ``test_cases.json``.

Quick-start
-----------
1. Edit ``config.json`` – set ``t32_config_path`` and ``rcl_port`` to match
   your running Trace32 instance.
2. Edit ``test_cases.json`` – add/update test cases, breakpoint symbols,
   and expected variable values.
3. Start Trace32 manually (or verify it is already running).
4. Run this script::

       python connect_t32_running.py

   Reports are saved automatically to ``test_cases_report.json`` and
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
# Run (connect to already-running Trace32, auto_launch=False)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    report = runner.run_from_json(
        test_cases_path=str(TEST_CASES_JSON),
        config_json_path=str(CONFIG_JSON) if CONFIG_JSON.is_file() else None,
        auto_launch=False,
    )
    print(report.summary())
    if report.failed > 0 or report.errored > 0:
        sys.exit(1)

