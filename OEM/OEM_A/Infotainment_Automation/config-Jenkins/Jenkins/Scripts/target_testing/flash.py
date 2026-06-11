import argparse
import datetime
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from tqdm.auto import tqdm
import git
import lauterbach.trace32.rcl as pyrcl
import lauterbach.trace32.rcl._rc._error
import psutil
import serial

# ==== CONFIG ====
RELAY_PORT = os.getenv('Serial_Relay', 'COM1')
POWER_SUPPLY_PORT = os.getenv('Serial_Power_Supply', 'COM4')
OUTLET_POWER_SUPPLY = 2
OUTLET_LAUTERBACH = 1
UART_SETTINGS = {
    'key': 'GM_VIP',
    'port': "COM3",
    'baudrate': 115200,
    'data': 8,
    'parity': serial.PARITY_NONE,
    'stop': 1
}
UNIQUE_STRING_START = 'Unique String At Start Of Flashing'
UNIQUE_STRING_END = 'Programming Script Completed.'

# ==== PATHS ====
_script_repo = git.Repo(__file__, search_parent_directories=True)
_rev_parse = _script_repo.git.rev_parse("--show-superproject-working-tree").strip()
project_root = Path(_rev_parse or _script_repo.working_tree_dir)

T32_INSTALL_DIR = Path('C:/T32')
T32_REMOTE_BIN = T32_INSTALL_DIR / 'bin/windows64/t32mtc.exe'
CMM_HSM_FILE = project_root / 'tools/00_TRACE32/flash/tc4d9xe_flash_hsm.cmm'
CMM_APPL_FILE = project_root / 'tools/00_TRACE32/flash/tc4d9xe_flash_boot_rpgm_app.cmm'
CMM_DEBUG_FILE = project_root / 'tools/00_TRACE32/debug/tc4d9xe_debug.cmm'
CMM_STACK_USAGE = project_root / 'tools/00_TRACE32/debug/calcStackUsage.cmm'

FOLDER_TEMP = Path(__file__).parent / 'temp'

log_folder = Path(__file__).parent / "logs"
log_folder.mkdir(parents=True, exist_ok=True)

# ==== LOGGER ====
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ==== ARGPARSE ====
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--report_folder', type=Path, default=Path(__file__).parent / "Output", help='Copy UART log to this file after run')
    args = parser.parse_args()
    args.report_folder.mkdir(parents=True, exist_ok=True)
    return args



# ==== UTILITY CLASSES ====
class RelayControl:
    ON, OFF = 1, 0

    def __init__(self):
        self.serial = serial.Serial(
            port=RELAY_PORT, baudrate=9600, bytesize=8,
            parity=serial.PARITY_NONE, stopbits=1)

    def select_port_power(self, state, port):
        logger.debug(f"Powering port {port} {'On' if state else 'Off'}")
        if state not in [0, 1]:
            raise ValueError('State must be 0 for off; or 1 for on.')
        self.serial.write(f'$A3 {port} {state}\r\n'.encode('utf-8'))

    def __del__(self):
        if hasattr(self, 'serial') and self.serial.is_open:
            self.serial.close()


class UARTConsole(serial.Serial):
    def __init__(self, com_definition):
        self.key = com_definition['key']
        logger.debug(f'Initializing UART Console on {com_definition["port"]}')
        super().__init__(
            port=com_definition['port'],
            baudrate=com_definition['baudrate'],
            bytesize=com_definition['data'],
            parity=com_definition['parity'],
            stopbits=com_definition['stop'],
        )
        self.log_file = log_folder / f'{self.key}.log'
        self.log_file.unlink(missing_ok=True)
        self.buffer, self.finish_this_log = [], False
        self.lock = threading.Lock()
        self.read_thread = threading.Thread(target=self.read_from_port, daemon=True)
        self.read_thread.start()

    def read_from_port(self):
        with open(self.log_file, 'a', encoding='utf-8', errors='ignore') as f:
            while not self.finish_this_log:
                line = self.readline().decode('utf-8', 'ignore').strip()
                if line:
                    logger.debug(f'UART {self.key}: {line}')
                    f.write(f'{datetime.datetime.now()}: {line}\n')
                    f.flush()
                    with self.lock:
                        self.buffer.append(line)

    def get_data(self):
        with self.lock:
            data = self.buffer.copy()
            self.buffer.clear()
            return data

    def __del__(self):
        self.finish_this_log = True
        self.close()


# ==== UTILS ====
def kill_process_by_name(name):
    found = False
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and name.lower() in proc.info['name'].lower():
            proc.kill()
            found = True
    if found:
        time.sleep(4)


def t32_cmm(debugger, command, timeout_s=10.0, end_string=UNIQUE_STRING_END) -> list[str]:
    logger.info(f"Executing T32 cmm script with command: {command}")
    re_script_name = re.compile(r'\s(.*?.cmm)')
    script_name = re_script_name.search(command)
    log_file = (FOLDER_TEMP / f'{script_name.group(1)}.log') if script_name else (FOLDER_TEMP / 'some_command.log')

    debugger.cmd('AREA')
    log_file.write_text('')
    logger.debug(f"Running command: {command}")
    debugger.cmd("AREA.CLEAR")
    debugger.print(UNIQUE_STRING_START)
    debugger.cmd(command)
    _start_time = time.time()
    while time.time() - _start_time < timeout_s:
        time.sleep(0.2)
        try:
            debugger.cmd(f"AREA.SAVE {log_file}")
        except lauterbach.trace32.rcl._rc._error.ApiConnectionError:
            continue
        cmd_out = log_file.read_text()
        if end_string in cmd_out:
            debugger.cmd("AREA.CLEAR")
            lines = cmd_out.replace(UNIQUE_STRING_START, '').replace(end_string, '').splitlines()
            return [l for l in lines if l.strip()]
    logger.error(f"Command '{command}' timed out after {timeout_s}s. Log file contents:\n{log_file.read_text()}")
    raise TimeoutError(f"Command '{command}' timed out after {timeout_s}s.")


# ==== MAIN ====
def main() -> int:
    retVal = 0
    args = parse_args()
    FOLDER_TEMP.mkdir(exist_ok=True, parents=True)
    relay = RelayControl()

    for attempt in range(10):
        try:
            relay.select_port_power(relay.OFF, OUTLET_LAUTERBACH)
            relay.select_port_power(relay.OFF, OUTLET_POWER_SUPPLY)
            kill_process_by_name('t32mtc.exe')
            time.sleep(2)
            relay.select_port_power(relay.ON, OUTLET_LAUTERBACH)
            relay.select_port_power(relay.ON, OUTLET_POWER_SUPPLY)
            # TODO: consider setting and using a port number via this file in config.32 instead of hardcoding it in two locations
            cmd = [
                str(T32_REMOTE_BIN),
                '-c', str(project_root / 'config/Jenkins/Scripts/target_testing/config.t32'),
                '-e', str(project_root / 'config/Jenkins/Scripts/target_testing/connection-arm.cmm')
            ]
            subprocess.Popen(cmd, shell=True)

            # Wait for T32 to be up
            port = 20000
            while True:
                try:
                    dbg = pyrcl.connect(port=port, protocol="UDP", timeout=1)
                    break
                except lauterbach.trace32.rcl._rc._error.ApiConnectionError:
                    time.sleep(0.5)
                    continue
            dbg.cmd(f"cd {CMM_APPL_FILE.parent}")
            t32_cmm(dbg, f'run {CMM_APPL_FILE.name}  "TRUE"', timeout_s=15)
            t32_cmm(dbg, f'run {CMM_HSM_FILE.name}   "TRUE"', timeout_s=15)
            time.sleep(1)
            dbg.cmd(f"cd {CMM_DEBUG_FILE.parent}")
            t32_cmm(dbg, f'run {CMM_DEBUG_FILE.name} "TRUE"', timeout_s=15)  # Causes T32 connection to crash on occasional flashing
            time.sleep(1)
            break
        except ConnectionResetError:
            logger.warning(f"ConnectionResetError encountered during setup (attempt {attempt + 1}/10). Retrying...")
            continue
    else:
        logger.error("Failed to initialize Trace32 after retries")
        return 1

    dbg.cmd('SYStem.Option.RESetBehavior RunRestore')
    dbg.cmd('SYStem.RESetTarget')
    dbg.cmd('Register.RESet')
    time.sleep(0.5)
    uart_console = UARTConsole(UART_SETTINGS)
    dbg.cmd('go')

    sleep_period = 15  # seconds
    requested_sleep_time = 5.5 * 60  # seconds
    for _ in tqdm(range(int(requested_sleep_time / sleep_period)), desc="Running ECU"):
        time.sleep(sleep_period)

    # Run Tests
    ##  Stack Usage Check
    ### CPU3.ustack: Used = 0x110 bytes, Free = 0x62F0 bytes, Percent Used = 2%
    re_stack_usage = re.compile(
        r'(?P<cpu>CPU\S+):\s+'
        r'Used\s+=\s+(?P<used>0x[0-9A-Fa-f]+)\s+bytes,\s+'
        r'Free\s+=\s+(?P<free>0x[0-9A-Fa-f]+)\s+bytes,\s+'
        r'Percent\s+Used\s+=\s+(?P<percent_used>\d+)%'
    )
    dbg.cmd(f"cd {CMM_STACK_USAGE.parent}")
    stack_log = t32_cmm(debugger=dbg, command=f'run {CMM_STACK_USAGE.name}', timeout_s=60, end_string="STACK USAGE CHECK DONE")
    (args.report_folder / "stack-usage.txt").write_text('\n'.join(stack_log))

    cpu_messages = [match.groupdict() for match in re_stack_usage.finditer("\n".join(stack_log))]
    for msg in cpu_messages:
        _output_str = f"CPU: {msg['cpu']}, Used: {msg['used']}, Free: {msg['free']}, Percent Used: {msg['percent_used']}%"
        logger.info(_output_str)
        if int(msg['percent_used']) > 70:
            logger.error(f"Stack usage for {msg['cpu']} is too high: {msg['percent_used']}%")
            # retVal = 1  # TODO: Checks for Metrics should be done in a separate script

    dbg.disconnect()
    logger.debug("Finished Flashing")
    kill_process_by_name('t32mtc.exe')
    relay.select_port_power(relay.OFF, OUTLET_LAUTERBACH)
    relay.select_port_power(relay.OFF, OUTLET_POWER_SUPPLY)
    del uart_console
    if args.report_folder:
        uart_log: Path = args.report_folder / 'uart.log'
        default_uart_log = log_folder / f'{UART_SETTINGS["key"]}.log'
        uart_log.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(default_uart_log, uart_log)
    return retVal


if __name__ == '__main__':
    start = time.time()
    _retVal = main()

    # print((log_folder / f'{UART_SETTINGS["key"]}.log').read_text())

    logger.info(f"Took {round(time.time() - start)} seconds")
    exit(_retVal)
