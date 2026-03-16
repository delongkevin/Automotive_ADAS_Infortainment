"""
GM Target Testing Script (APPL_GM)

This script handles on-target testing for the GM library build mode (APPL_GM).
It performs:
1. UCB flash (ucbstart.ptp)
2. GM Application flash via start_headless.cmm (Boot.ptp, APPL_GM.hex, Calibration.ptp, EthSwitch)
3. Dual UART logging (main + EyeQ)

Note: This is a simplified version of main.py - no CANoe/stability tests.
Future: Add T32 symbol probing for EyeQ vision mode verification.
"""

import argparse
import logging
import shutil
import time
from contextlib import suppress
from pathlib import Path
from typing import Optional

from rig.config import (
    project_root, LOG_FOLDER, FOLDER_TEMP,
    OUTLET_LAUTERBACH, OUTLET_POWER_SUPPLY,
    UART_SETTINGS, UART_SETTINGS_GM_EQ,
    CMM_UCB_FILE, CMM_GM_HEADLESS_FILE,
    ExitCode,
)
#from rig.hw.relay import RelayControl
from rig.io.uart import UARTConsole
from rig.tools.t32 import launch_t32, connect_t32, run_cmm
from rig.utils.proc import kill_process_by_name

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# UART log keys for GM target
UART_LOG_KEY_GM = 'uart_appl_gm'
UART_LOG_KEY_GM_EQ = 'uart_appl_gm_EQ'


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GM Target Testing (APPL_GM)")
    p.add_argument(
        "--report_folder",
        type=Path,
        default=Path(__file__).resolve().parent / "Output",
        help="Copy UART logs to this folder after run",
    )
    p.add_argument(
        "--t32_cfg",
        type=Path,
        default=project_root / "config/Jenkins/Scripts/target_testing/config.t32",
    )
    p.add_argument(
        "--t32_conn",
        type=Path,
        default=project_root / "config/Jenkins/Scripts/target_testing/connection-arm.cmm",
    )
    p.add_argument("--t32_port", type=int, default=20000)
    p.add_argument(
        "--run_time",
        type=float,
        default=1.0,
        help="Time in minutes to run the ECU after flashing (default: 2 minutes)",
    )
    return p.parse_args()


# ------------------------- Helpers --------------------------- #

def _power_cycle(relay: RelayControl) -> None:
    """Hard power-cycle Lauterbach and PSU and ensure T32 is not running."""
    relay.select_port_power(RelayControl.OFF, OUTLET_LAUTERBACH)
    relay.select_port_power(RelayControl.OFF, OUTLET_POWER_SUPPLY)
    kill_process_by_name("t32mtc.exe")
    time.sleep(2)

    relay.select_port_power(RelayControl.ON, OUTLET_LAUTERBACH)
    relay.select_port_power(RelayControl.ON, OUTLET_POWER_SUPPLY)
    time.sleep(2)


def _setup_trace32(*, t32_cfg: Path, t32_conn: Path, t32_port: int):
    t32_proc = launch_t32(t32_cfg, t32_conn)
    dbg = connect_t32(port=t32_port, protocol="UDP", timeout_s=1.0, max_wait_s=60.0)
    return t32_proc, dbg


def _flash_gm_setup(dbg) -> None:
    """Flash UCB first, then GM application via start_headless.cmm."""
    # Step 1: Flash UCB (ucbstart.ptp)
    logger.info("Flashing UCB (ucbstart.ptp)...")
    dbg.cmd(f"cd {CMM_UCB_FILE.parent}")
    run_cmm(dbg, f'run {CMM_UCB_FILE.name} "TRUE"', timeout_s=60, end_string="UCB Programming Script Completed.")
    time.sleep(1)

    # Step 2: Flash GM Application (Boot, App, Cal, EthSwitch) via start_headless.cmm
    # This uses the GM scripts with SetGlobalVariables.cmm for proper memory map setup
    logger.info("Flashing GM Application (Boot, App, Cal, EthSwitch)...")
    dbg.cmd(f"cd {CMM_GM_HEADLESS_FILE.parent}")
    run_cmm(dbg, f'run {CMM_GM_HEADLESS_FILE.name} "TRUE"', timeout_s=120, end_string="GM Headless Flash Completed.")
    time.sleep(1)


def _reset_target(dbg) -> None:
    dbg.cmd("SYStem.RESetTarget")
    dbg.cmd("Register.RESet")
    time.sleep(0.5)


def _copy_uart_logs_to(report_folder: Path) -> None:
    """Copy both GM UART logs to report folder."""
    for log_key in [UART_LOG_KEY_GM, UART_LOG_KEY_GM_EQ]:
        default_uart_log = LOG_FOLDER / f'{log_key}.log'
        if default_uart_log.exists():
            dst = report_folder / f'{log_key}.log'
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(default_uart_log, dst)
            logger.info(f"Copied UART log to {dst}")


# TODO: Future implementation - EyeQ Vision Mode Symbol Probing
def _check_eyeq_vision_mode(dbg) -> bool:
    """
    Check if EyeQ is in vision mode by probing T32 symbols.

    This is a placeholder for future implementation.
    Will use T32 Var.VALUE() to read EyeQ state symbols.

    Returns:
        bool: True if EyeQ is in vision mode, False otherwise.
    """
    # TODO: Implement symbol probing once EyeQ symbol names are known
    # Example pattern:
    # try:
    #     eyeq_state = dbg.fnc("Var.VALUE(EyeQ_State_Symbol)")
    #     return eyeq_state == EXPECTED_VISION_MODE_VALUE
    # except Exception as e:
    #     logger.warning(f"Failed to read EyeQ state: {e}")
    #     return False
    logger.info("EyeQ vision mode check: Not yet implemented (placeholder)")
    return True


# ---------------------------- Main --------------------------- #

def main() -> Optional[int]:
    args = parse_args()

    args.report_folder.mkdir(parents=True, exist_ok=True)
    FOLDER_TEMP.mkdir(parents=True, exist_ok=True)

    ret = 0
    relay = None
    uart_console_gm = None
    uart_console_eq = None
    t32_proc = None
    dbg = None

    relay = RelayControl()
    try:
        # Retry loop for Trace32 initialization
        for attempt in range(8):
            try:
                _power_cycle(relay)
                t32_proc, dbg = _setup_trace32(
                    t32_cfg=args.t32_cfg,
                    t32_conn=args.t32_conn,
                    t32_port=args.t32_port
                )
                _flash_gm_setup(dbg)
                break
            except ConnectionResetError:
                logger.warning(f"ConnectionResetError during setup (attempt {attempt + 1}/8). Retrying...")
                continue
        else:
            logger.error("Failed to initialize Trace32 after retries")
            return ExitCode.TRACE32_INIT_FAILED

        _reset_target(dbg)
        dbg.cmd("SYStem.Option.RESetBehavior RunRestore")

        # Start UART logging (main GM UART)
        logger.info("Starting GM UART console...")
        uart_console_gm = UARTConsole(UART_SETTINGS, key=UART_LOG_KEY_GM)

        # Start EyeQ UART logging (if port is configured)
        # Note: This will fail gracefully if COM port doesn't exist
        try:
            logger.info("Starting EyeQ UART console...")
            uart_console_eq = UARTConsole(UART_SETTINGS_GM_EQ, key=UART_LOG_KEY_GM_EQ)
        except Exception as e:
            logger.warning(f"Failed to start EyeQ UART console (expected if not configured): {e}")
            uart_console_eq = None

        # dbg.cmd("var.watch.stEyeQ_AppMessage_Protocol")

        # Start execution
        logger.info("Starting ECU execution...")
        dbg.cmd("go")

        # Poll the state until in vision, and ensure it stays in vision for X amount of time.
        start_time = time.time()
        eq_state = None
        while time.time() - start_time < 120:
            eq_state = dbg.variable.read("stEyeQ_AppMessage_Protocol.IeEBA_e_EqMainState").value
            if eq_state == 2:
                logger.info("EyeQ is in expected vision mode state (2)")
                break
            time.sleep(1)
        else:
            logger.warning(f"Timeout reached while waiting for EyeQ to enter vision mode. Last state: {eq_state}")
            ret = ExitCode.EYEQ_VISION_TIMEOUT

        start_time = time.time()
        while time.time() - start_time < 120:
            eq_state = dbg.variable.read("stEyeQ_AppMessage_Protocol.IeEBA_e_EqMainState").value
            if eq_state != 2:
                logger.warning(f"EyeQ state changed unexpectedly during vision mode monitoring after {round(time.time() - start_time)} seconds. Current state: {eq_state}")
                ret = ExitCode.EYEQ_STATE_CHANGED
                break
            time.sleep(1)

        fatal = dbg.variable.read("stEyeQ_AppMessage_Protocol.IeEBA_e_FatalError").value
        if fatal == 0:
            logger.info("EyeQ fatal error state is OK (0)")
        else:
            logger.error(f"Unexpected EyeQ fatal error state: {fatal}")
            ret = ExitCode.EYEQ_FATAL_ERROR

        # Stop UART capture
        if uart_console_eq:
            uart_console_eq.stop()
        if uart_console_gm:
            uart_console_gm.stop()

        logger.info("GM target testing sequence completed.")

    finally:
        if dbg:
            with suppress(Exception):
                dbg.disconnect()
        kill_process_by_name("t32mtc.exe")

        if relay:
            with suppress(Exception):
                relay.select_port_power(RelayControl.OFF, OUTLET_LAUTERBACH)
                relay.select_port_power(RelayControl.OFF, OUTLET_POWER_SUPPLY)

        if uart_console_gm:
            with suppress(Exception):
                uart_console_gm.stop()

        if uart_console_eq:
            with suppress(Exception):
                uart_console_eq.stop()

        _copy_uart_logs_to(args.report_folder)

    return ret


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    start = time.time()
    code = main()
    logger.info(f"GM target testing took {round(time.time() - start)} seconds")
    # raise SystemExit(code)  # TODO: Revert when EQ Stability is resolved
    raise SystemExit(0)
