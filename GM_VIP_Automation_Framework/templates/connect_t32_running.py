"""
Template: Connect to a Trace32 instance that is ALREADY RUNNING
================================================================
Copy this file into your test project and edit the paths / symbol names to
match your ECU target.  The script reads all Trace32 settings from
``config.json`` so you never have to hard-code paths.

Quick-start
-----------
1. Edit ``config.json`` in your project root (copy the template from the
   ``GM_VIP_Automation_Framework`` package directory).
2. Set ``t32_config_path`` to your ``config.t32`` and ``rcl_port`` to the
   ``PORT=`` value inside that file.
3. Start Trace32 manually (or verify it is already running).
4. Run this script::

       python connect_t32_running.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Configure framework from config.json
# ---------------------------------------------------------------------------
import GM_VIP_Automation_Framework as t32
from GM_VIP_Automation_Framework.config import settings
from GM_VIP_Automation_Framework.report import TestCaseReport

# Path to the config file – adjust if your config.json is elsewhere.
CONFIG_JSON = Path(__file__).parent / "config.json"

if CONFIG_JSON.is_file():
    settings.load_from_json(str(CONFIG_JSON))
else:
    print(
        f"[WARNING] config.json not found at {CONFIG_JSON}. "
        "Using default / environment-variable settings."
    )

# ---------------------------------------------------------------------------
# 2. Connect to the already-running Trace32 (no launch)
# ---------------------------------------------------------------------------
# T32Connection uses settings.rcl_port / rcl_protocol automatically.
# Pass port= or protocol= here only if you need to override the JSON config.

def run_tests() -> None:
    """Execute the test sequence against the already-running Trace32."""

    report = TestCaseReport(name="MyTestSuite")

    with t32.T32Connection(
        port=settings.rcl_port,
        protocol=settings.rcl_protocol,
    ) as conn:
        # Make the connection available module-wide so helper functions can
        # use it without passing it explicitly to every call.
        import GM_VIP_Automation_Framework.core.debugger as dbg
        dbg.default_connection = conn

        # ------------------------------------------------------------------
        # Test case 1: Reset and basic state check
        # ------------------------------------------------------------------
        report.begin_test_case("TC_Reset_BasicState")
        try:
            t32.reset_target(connection=conn)
            t32.delete_all_breakpoints(connection=conn)

            state = t32.get_state(connection=conn)
            report.record_variable("ECU_State", state)

            report.pass_test_case()
        except Exception as exc:  # noqa: BLE001
            report.fail_test_case(str(exc))

        # ------------------------------------------------------------------
        # Test case 2: Breakpoint + variable read
        # ------------------------------------------------------------------
        report.begin_test_case("TC_Breakpoint_VariableRead")
        try:
            t32.set_breakpoint("myTargetFunction", connection=conn)
            t32.go(connection=conn)
            t32.check_halted_at("myTargetFunction", connection=conn)

            value = t32.read_variable("myModule.myCounter", connection=conn)
            report.record_variable("myModule.myCounter", value)
            report.record_breakpoint("myTargetFunction", hit=True)

            t32.delete_all_breakpoints(connection=conn)
            report.pass_test_case()
        except Exception as exc:  # noqa: BLE001
            t32.delete_all_breakpoints(connection=conn)
            report.fail_test_case(str(exc))

        # ------------------------------------------------------------------
        # Additional test cases: add more report.begin_test_case(...) blocks
        # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 3. Save reports
    # ------------------------------------------------------------------
    report.save_json("test_report.json")
    report.save_html("test_report.html")
    print(report.summary())


if __name__ == "__main__":
    run_tests()
