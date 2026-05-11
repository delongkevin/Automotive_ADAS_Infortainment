"""
Template: Launch Trace32 from config.json THEN connect
=======================================================
**No Python edits needed.**  All settings (paths, ports, timing) are read
from ``config.json`` and all test case definitions (breakpoints, variables
to check, expected values) are read from ``test_cases.json``.

Quick-start
-----------
1. Install the Lauterbach Python library (one-time)::

       pip install lauterbach.trace32.rcl

2. Edit ``config.json`` – set ``t32_exe_path``, ``t32_config_path``, and
   ``rcl_port``.
3. Edit ``test_cases.json`` – add/update test cases, breakpoint symbols,
   and expected variable values.
4. Run this script from **any** directory::

       python connect_t32_launch.py
       # or double-click in Windows Explorer
       # or open and run in IDLE / VS Code

   Trace32 will start automatically, the framework will wait up to
   ``connect_max_wait_s`` seconds (set in ``config.json``) for it to
   become ready, run the test suite, then shut Trace32 down on exit.
   Reports are saved to ``test_cases_report.json`` and
   ``test_cases_report.html`` next to this script.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: make GM_VIP_Automation_Framework importable from any working
# directory or when launched from IDLE / Windows Explorer.
# The package lives two directories above this template file:
#   templates/connect_t32_launch.py  →  parent = templates/
#   parent.parent                    →  GM_VIP_Automation_Framework/
#   parent.parent.parent             →  <repo root / SWTest dir>  ← add this
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from GM_VIP_Automation_Framework import runner  # noqa: E402

# ---------------------------------------------------------------------------
# Paths – config.json and test_cases.json live in the GM_VIP_Automation_Framework
# root, one level above this templates/ folder.
# ---------------------------------------------------------------------------
_FRAMEWORK_DIR = Path(__file__).resolve().parent.parent
CONFIG_JSON = _FRAMEWORK_DIR / "config.json"
TEST_CASES_JSON = _FRAMEWORK_DIR / "test_cases.json"

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

