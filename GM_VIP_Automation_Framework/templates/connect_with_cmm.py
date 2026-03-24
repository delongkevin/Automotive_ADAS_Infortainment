"""
Template: Connect to Trace32 using a CMM (*.cmm) entry-point script
====================================================================
This template demonstrates the **CMM-first** workflow, which is the
recommended approach when your Trace32 environment is driven by a single
``*.cmm`` PRACTICE macro script:

1. The framework first tries to connect to a Trace32 instance that is
   **already running** on the configured RCL port (``rcl_port`` in
   ``config.json``).  If Trace32 is already open (e.g. you ran your
   ``*.cmm`` script manually), the connection succeeds immediately – no
   ``exe_path`` or ``config.t32`` path is required.

2. If no running instance is found **and** ``AUTO_LAUNCH = True``, the
   framework launches Trace32 using the paths from ``config.json`` and
   passes your CMM script via the ``-s`` flag::

       t32marm64.exe -c config.t32 -s tc4d9xe_debug.cmm

   The CMM script then handles all hardware configuration (loading
   symbols, opening the API port, etc.).

3. Once connected, the Python framework executes the test cases defined
   in ``test_cases.json`` and saves an HTML + JSON report.

Quick-start
-----------
1. Install the Lauterbach Python library (one-time)::

       pip install lauterbach.trace32.rcl

2. Set ``CMM_ENTRY_SCRIPT`` below to the absolute path of your ``*.cmm``
   startup script.
3. Edit ``config.json`` – set ``rcl_port`` to match the API port your
   CMM script opens in Trace32.  (``t32_exe_path`` / ``t32_config_path``
   are only needed when ``AUTO_LAUNCH = True``.)
4. Edit ``test_cases.json`` with your test case definitions.
5. Start Trace32 and run your CMM script (or set ``AUTO_LAUNCH = True``
   to let the framework launch Trace32 for you).
6. Run this script from **any** directory::

       python connect_with_cmm.py
       # or double-click in Windows Explorer
       # or open and run in IDLE / VS Code

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
#   templates/connect_with_cmm.py  →  parent = templates/
#   parent.parent                  →  GM_VIP_Automation_Framework/
#   parent.parent.parent           →  <repo root / SWTest dir>  ← add this
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
# Edit these paths to match your environment.
# ---------------------------------------------------------------------------

#: Absolute path to the *.cmm startup script.
#: Defaults to the bundled SMP demo script (scripts/smp_demo_multisieve.cmm)
#: shipped with the framework.  Override with your own absolute path when
#: a project-specific script is needed, or set to empty string ("") or None
#: to launch Trace32 without a startup script.
_DEFAULT_CMM_PATH = _FRAMEWORK_DIR / "scripts" / "smp_demo_multisieve.cmm"
CMM_ENTRY_SCRIPT: str = str(_DEFAULT_CMM_PATH) if _DEFAULT_CMM_PATH.is_file() else ""

#: Set to True to allow the framework to launch Trace32 automatically when
#: no running instance is found on the configured port.  Requires
#: t32_exe_path and t32_config_path to be set in config.json.
AUTO_LAUNCH: bool = False

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    report = runner.run_from_json(
        test_cases_path=str(TEST_CASES_JSON),
        config_json_path=str(CONFIG_JSON) if CONFIG_JSON.is_file() else None,
        cmm_entry_script=CMM_ENTRY_SCRIPT if CMM_ENTRY_SCRIPT else None,
        auto_launch=AUTO_LAUNCH,
        # resilient_connect=True (default): try to connect to a running
        # Trace32 first; only launch if no running instance is found and
        # AUTO_LAUNCH is True.
    )
    print(report.summary())
    if report.failed > 0 or report.errored > 0:
        sys.exit(1)
