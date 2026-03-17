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
1. Set ``CMM_ENTRY_SCRIPT`` below to the absolute path of your ``*.cmm``
   startup script.
2. Edit ``config.json`` – set ``rcl_port`` to match the API port your
   CMM script opens in Trace32.  (``t32_exe_path`` / ``t32_config_path``
   are only needed when ``AUTO_LAUNCH = True``.)
3. Edit ``test_cases.json`` with your test case definitions.
4. Start Trace32 and run your CMM script (or set ``AUTO_LAUNCH = True``
   to let the framework launch Trace32 for you).
5. Run this script::

       python connect_with_cmm.py

   Reports are saved to ``test_cases_report.json`` and
   ``test_cases_report.html``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from GM_VIP_Automation_Framework import runner

# ---------------------------------------------------------------------------
# Edit these paths to match your environment.
# ---------------------------------------------------------------------------

#: Absolute path to your *.cmm startup script.
#: Used only when Trace32 needs to be launched (AUTO_LAUNCH=True) and no
#: running instance is found on rcl_port.  Set to empty string ("") or None
#: to launch Trace32 without a startup script.
CMM_ENTRY_SCRIPT: str = r"C:\workspace\tc4d9xe_debug.cmm"

#: Set to True to allow the framework to launch Trace32 automatically when
#: no running instance is found on the configured port.  Requires
#: t32_exe_path and t32_config_path to be set in config.json.
AUTO_LAUNCH: bool = False

CONFIG_JSON = Path(__file__).parent / "config.json"
TEST_CASES_JSON = Path(__file__).parent / "test_cases.json"

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
