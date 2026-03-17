"""
Template: Launch Trace32 from config.json THEN connect
=======================================================
Copy this file into your test project and edit the paths / symbol names to
match your ECU target.  The script reads the Trace32 executable path and
config file from ``config.json`` so you never have to hard-code paths.

Quick-start
-----------
1. Edit ``config.json`` in your project root (copy the template from the
   ``GM_VIP_Automation_Framework`` package directory).
2. Set ``t32_exe_path`` to your ``t32marm64.exe`` (or equivalent).
3. Set ``t32_config_path`` to your ``config.t32``.
4. Set ``rcl_port`` to the ``PORT=`` value inside that config file.
5. Run this script::

       python connect_t32_launch.py

   Trace32 will start automatically, the framework will wait up to
   ``connect_max_wait_s`` seconds for it to become ready, then run
   the test sequence and shut Trace32 down on exit.
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
# 2. Launch Trace32 from config, connect, run tests, auto-disconnect
# ---------------------------------------------------------------------------

def run_tests() -> None:
    """Launch Trace32, connect, execute the test sequence, then disconnect."""

    report = TestCaseReport(name="MyTestSuite")

    # T32Connection.__exit__ calls disconnect(); the subprocess is NOT killed
    # automatically – Trace32 stays open after the test run unless you call
    # conn.process.terminate() explicitly (see the finally block below).
    with t32.T32Connection(
        exe_path=settings.t32_exe_path,
        config_path=settings.t32_config_path,
        port=settings.rcl_port,
        protocol=settings.rcl_protocol,
    ) as conn:
        # Launch and wait for Trace32 to be ready.
        conn.launch()
        conn.connect()

        # Make the connection available module-wide.
        import GM_VIP_Automation_Framework.core.debugger as dbg
        dbg.default_connection = conn

        try:
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
            # Test case 2: Symbol existence check
            # ------------------------------------------------------------------
            report.begin_test_case("TC_Symbol_Exists")
            try:
                exists = t32.symbol_exists("myTargetFunction", connection=conn)
                report.record_symbol("myTargetFunction", exists=exists)
                if not exists:
                    report.fail_test_case("Symbol 'myTargetFunction' not found.")
                else:
                    report.pass_test_case()
            except Exception as exc:  # noqa: BLE001
                report.fail_test_case(str(exc))

            # ------------------------------------------------------------------
            # Test case 3: Breakpoint + variable write + read
            # ------------------------------------------------------------------
            report.begin_test_case("TC_Breakpoint_VarWriteRead")
            try:
                t32.set_breakpoint("myTargetFunction", connection=conn)
                t32.set_variable("myModule.myFlag", 1, connection=conn)
                report.record_variable("myModule.myFlag (write)", "1")

                t32.go(connection=conn)
                t32.check_halted_at("myTargetFunction", connection=conn)
                report.record_breakpoint("myTargetFunction", hit=True)

                value = t32.read_variable("myModule.myCounter", connection=conn)
                report.record_variable("myModule.myCounter", value)

                t32.delete_all_breakpoints(connection=conn)
                report.pass_test_case()
            except Exception as exc:  # noqa: BLE001
                t32.delete_all_breakpoints(connection=conn)
                report.fail_test_case(str(exc))

            # ------------------------------------------------------------------
            # Additional test cases: add more report.begin_test_case(...) blocks
            # ------------------------------------------------------------------

        finally:
            # Optionally terminate the T32 process when done.
            # Comment out the next two lines to leave Trace32 open.
            if conn.process is not None:
                conn.process.terminate()

    # ------------------------------------------------------------------
    # 3. Save reports
    # ------------------------------------------------------------------
    report.save_json("test_report.json")
    report.save_html("test_report.html")
    print(report.summary())


if __name__ == "__main__":
    run_tests()
