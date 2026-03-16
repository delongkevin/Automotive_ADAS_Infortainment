import argparse
import logging
import re
import shutil
import time
import xml.etree.ElementTree as ET
from contextlib import suppress
from pathlib import Path
from typing import Iterable, Optional

from tqdm.auto import tqdm

from rig.canoe.canoe import CanoeController
from rig.config import (
    project_root, LOG_FOLDER, FOLDER_TEMP,
    OUTLET_LAUTERBACH, OUTLET_POWER_SUPPLY,
    UART_SETTINGS,
    CMM_APPL_FILE, CMM_HSM_FILE, CMM_DEBUG_FILE, CMM_STACK_USAGE,
    ExitCode,
)
from rig.hw.relay import RelayControl
from rig.io.uart import UARTConsole
from rig.tests.stack_usage import run_and_parse_stack_usage
from rig.tools.t32 import launch_t32, connect_t32, run_cmm
from rig.utils.proc import kill_process_by_name

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
log_map = {"pass": logger.info, "fail": logger.error, "n/a": logger.warning}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--report_folder",
        type=Path,
        default=Path(__file__).resolve().parent / "Output",
        help="Copy UART log to this folder after run",
    )
    p.add_argument(
        "--t32_cfg",
        type=Path,
        default=project_root / "config/Jenkins/Scripts/target_testing/config.t32",
    )
    p.add_argument(
        "--t32_conn",
        type=Path,
        default=project_root
                / "config/Jenkins/Scripts/target_testing/connection-arm.cmm",
    )
    p.add_argument("--t32_port", type=int, default=20000)
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


def _flash_and_debug_setup(dbg) -> None:
    # Flash + debug setup
    dbg.cmd(f"cd {CMM_APPL_FILE.parent}")
    run_cmm(dbg, f'run {CMM_APPL_FILE.name}  "TRUE"', timeout_s=15)
    run_cmm(dbg, f'run {CMM_HSM_FILE.name}   "TRUE"', timeout_s=15)
    time.sleep(1)

    # Remove the boot symbols as they conflict with APPL symbols.
    debug_contents = CMM_DEBUG_FILE.read_text().splitlines()
    debug_contents = '\n'.join([line if '"&elfFile_Boot"' not in line else f";{line}" for line in debug_contents])
    CMM_DEBUG_FILE.write_text(debug_contents)

    dbg.cmd(f"cd {CMM_DEBUG_FILE.parent}")
    run_cmm(dbg, f'run {CMM_DEBUG_FILE.name} "TRUE"', timeout_s=15)


def _reset_target(dbg) -> None:
    dbg.cmd("SYStem.RESetTarget")
    dbg.cmd("Register.RESet")
    time.sleep(0.5)


def _parse_and_log_canoe_reports(reports: Iterable[Path], report_folder: Optional[Path] = None) -> bool:
    flag_test_fail = False
    for report in reports:
        if report_folder:
            dst = report_folder / 'canoe' / report.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(report, dst)
        if report.suffix.lower() != ".xml":
            continue
        logger.info(f"Parsing CANoe report: {report}")

        tree = ET.parse(report)
        root = tree.getroot()
        for testgroup in root.findall("testgroup"):
            group_title_el = testgroup.find("title")
            group_title = group_title_el.text if group_title_el is not None else "N/A"
            for testcase in testgroup.findall("testcase"):
                title_el = testcase.find("title")
                desc_el = testcase.find("description")
                verdict_el = testcase.find("verdict")
                tc_title = title_el.text if title_el is not None else "N/A"
                tc_desc = desc_el.text if desc_el is not None else "N/A"
                verdict = (verdict_el.attrib["result"] or "N/A") if verdict_el is not None else "N/A"

                log_fn = log_map.get(verdict.lower(), logger.debug)
                log_fn(f"\t{verdict} - Testgroup: {group_title} | Testcase Title: {tc_title} | Description: {tc_desc}")
                if verdict == "fail":
                    flag_test_fail = True
    return flag_test_fail


UART_LOG_KEY = 'uart_appl'


def _copy_uart_log_to(report_folder: Path) -> None:
    default_uart_log = LOG_FOLDER / f'{UART_LOG_KEY}.log'
    if default_uart_log.exists():
        dst = report_folder / "uart.log"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(default_uart_log, dst)


class _CounterChecker:
    """Checks test/lockstep counters for failures and stalls."""

    # Counter definitions: (variable_name, display_name)
    PASS_COUNTERS = [
        ("testPassCountTest", "Test Pass Counter"),
        ("retval_LockStepPassCounter", "LockStep Pass Counter"),
    ]
    FAIL_COUNTERS = [
        ("testFailCountTest", "Test Fail Counter"),
        ("retval_LockStepFailCounter", "LockStep Fail Counter"),
    ]

    def __init__(self, stall_threshold=10):
        self.stall_threshold = stall_threshold
        self._prev_values = {}
        self._stall_counts = {}

    def check(self, dbg):
        """
        Check counters once. Returns ExitCode on failure, 0 if OK.
        Logs errors/warnings as they occur.
        """
        ret = 0

        # Check fail counters (should always be 0)
        for var_name, display_name in self.FAIL_COUNTERS:
            try:
                value = dbg.variable.read(var_name).value
            except Exception as e:
                logger.warning(f"Failed to read variable {var_name}: {e}")
                return ret
            time.sleep(0.1)  # Arbitrary small delay to avoid overwhelming the target with reads
            if value != 0:
                logger.error(f"{display_name} is non-zero: {value}")
                ret = ExitCode.COUNTER_FAIL_NONZERO

        # Check pass counters for stalling
        for var_name, display_name in self.PASS_COUNTERS:
            try:
                value = dbg.variable.read(var_name).value
            except Exception as e:
                logger.warning(f"Failed to read variable {var_name}: {e}")
                continue
            time.sleep(0.1)  # Arbitrary small delay to avoid overwhelming the target with reads
            prev = self._prev_values.get(var_name)

            if prev is not None:
                if value == prev:
                    self._stall_counts[var_name] = self._stall_counts.get(var_name, 0) + 1
                    if self._stall_counts[var_name] == self.stall_threshold:
                        logger.warning(f"{display_name} appears stalled at value: {value}")
                        ret = ret or ExitCode.COUNTER_STALL
                else:
                    self._stall_counts[var_name] = 0

            self._prev_values[var_name] = value

        return ret


# ---------------------------- Main --------------------------- #

def main() -> Optional[int]:
    args = parse_args()

    args.report_folder.mkdir(parents=True, exist_ok=True)
    FOLDER_TEMP.mkdir(parents=True, exist_ok=True)

    ret = 0
    relay = None
    uart_console = None
    t32_proc = None
    dbg = None
    canoe_ctrl = None

    relay = RelayControl()
    try:
        for attempt in range(8):  # Retry loop for Trace32 initialization
            try:
                _power_cycle(relay)
                t32_proc, dbg = _setup_trace32(t32_cfg=args.t32_cfg, t32_conn=args.t32_conn, t32_port=args.t32_port)
                _flash_and_debug_setup(dbg)
                break
            except ConnectionResetError:
                logger.warning(f"ConnectionResetError encountered during setup (attempt {attempt + 1}/8). Retrying...")
                continue
        else:
            logger.error("Failed to initialize Trace32 after retries")
            return ExitCode.TRACE32_INIT_FAILED

        _reset_target(dbg)
        dbg.cmd("SYStem.Option.RESetBehavior RunRestore")

        # UART logging
        uart_console = UARTConsole(UART_SETTINGS, key=UART_LOG_KEY)

        # Start execution
        dbg.cmd("go")

        # Monitor counters for 5.5 minutes
        duration = int(5.5 * 60)
        start_time = time.time()
        counter_checker = _CounterChecker(stall_threshold=10)
        pbar = tqdm(total=duration, desc=f"Running ECU [0s / {duration}s]", unit="s")
        last_pbar_update = 0

        while time.time() - start_time < duration:
            check_result = counter_checker.check(dbg)
            if check_result:
                ret = check_result

            time.sleep(1)

            elapsed = int(time.time() - start_time)
            if elapsed - last_pbar_update >= 30:
                pbar.set_description(f"Running ECU [{elapsed}s / {duration}s]", refresh=False)
                pbar.update(elapsed - last_pbar_update)
                last_pbar_update = elapsed

        pbar.update(duration - pbar.n)
        pbar.close()

        # Stack usage check
        msgs, _ = run_and_parse_stack_usage(dbg, CMM_STACK_USAGE, args.report_folder, run_cmm_func=run_cmm)
        for msg in msgs:
            percent_used = int(msg['percent_used'])
            if percent_used > 70:
                logging.error(f"High stack usage: {msg['cpu']} = {msg['percent_used']}%")
                if percent_used > 75:
                    ret = ExitCode.STACK_USAGE_HIGH  # enable if you want to fail the run on threshold

        # Stop UART capture before CANoe tests
        uart_console.stop()

        pat = re.compile(r'".*L2H7890_Software')
        CANOE_CONFIG = project_root / 'SWTest/GM_VIP_Automation/config.cin'
        project_root_backslash = project_root.as_posix().replace('/', re.escape('\\\\'))
        CANOE_CONFIG.write_text(pat.sub(f'"{project_root_backslash}', CANOE_CONFIG.read_text()))

        # Run CANoe tests
        kill_process_by_name("CANoe64.exe")
        canoe_ctrl = CanoeController()
        canoe_ctrl.open_config(
            project_root / "SWTest/GM_VIP_Automation/GM_VIP_RBS/GM_VIP_SWtest.cfg"
        )
        canoe_ctrl.start_measurement()
        reports = canoe_ctrl.select_and_run_tests(env_names="GM_VIP_Sanity")
        canoe_result = _parse_and_log_canoe_reports(reports, report_folder=args.report_folder)
        ret = ExitCode.CANOE_TEST_FAILED if canoe_result else ret

        logger.info("Finished sequence.")
    finally:
        if dbg:
            with suppress(Exception):
                dbg.disconnect()
        kill_process_by_name("t32mtc.exe")

        if canoe_ctrl:
            with suppress(Exception):
                canoe_ctrl.close()
        kill_process_by_name("CANoe64.exe")

        if relay:
            with suppress(Exception):
                relay.select_port_power(RelayControl.OFF, OUTLET_LAUTERBACH)
                relay.select_port_power(RelayControl.OFF, OUTLET_POWER_SUPPLY)

        if uart_console:
            with suppress(Exception):
                uart_console.stop()

        _copy_uart_log_to(args.report_folder)

    return ret


if __name__ == "__main__":
    start = time.time()
    code = main()
    logger.info(f"Took {round(time.time() - start)} seconds")
    raise SystemExit(code)
