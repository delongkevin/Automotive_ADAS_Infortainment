"""
Template: Connect to a Trace32 instance that is ALREADY RUNNING
================================================================
**No Python edits needed.**  All settings (paths, ports, timing) are read
from ``config.json`` and all test case definitions (breakpoints, variables
to check, expected values) are read from ``test_cases.json``.

Quick-start
-----------
1. Install the Lauterbach Python library (one-time)::

       pip install lauterbach.trace32.rcl

2. Edit ``config.json`` – set ``rcl_port`` to match your running Trace32
   instance.  (``t32_exe_path`` / ``t32_config_path`` are NOT needed when
   Trace32 is already running.)
3. Edit ``test_cases.json`` – add/update test cases, breakpoint symbols,
   and expected variable values.
4. Start Trace32 manually (or verify it is already running with the API
   port open).
5. Run this script from **any** directory::

       python connect_t32_running.py
       # or double-click in Windows Explorer
       # or open and run in IDLE / VS Code

   Reports are saved automatically to ``test_cases_report.json`` and
   ``test_cases_report.html`` next to this script.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: make GM_VIP_Automation_Framework importable from any working
# directory or when launched from IDLE / Windows Explorer.
# The package lives two directories above this template file:
#   templates/connect_t32_running.py  →  parent = templates/
#   parent.parent                     →  GM_VIP_Automation_Framework/
#   parent.parent.parent              →  <repo root / SWTest dir>  ← add this
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

