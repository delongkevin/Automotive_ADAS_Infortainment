import subprocess
import time
from pathlib import Path
import lauterbach.trace32.rcl as pyrcl
from lauterbach.trace32.rcl._rc._error import ApiConnectionError

from ..config import (T32_REMOTE_BIN, FOLDER_TEMP, UNIQUE_STRING_START, UNIQUE_STRING_END,
                      logger, RE_SCRIPT_NAME)

def launch_t32(remote_cfg: Path, connect_cmm: Path) -> subprocess.Popen:
    cmd = [
        str(T32_REMOTE_BIN),
        '-c', str(remote_cfg),
        '-e', str(connect_cmm),
    ]
    logger.info(f"Launching T32: {' '.join(cmd)}")
    return subprocess.Popen(cmd, shell=True)

def connect_t32(port: int = 20000, protocol: str = "UDP", timeout_s: float = 1.0, max_wait_s: float = 60.0):
    t0 = time.time()
    while time.time() - t0 < max_wait_s:
        try:
            return pyrcl.connect(port=port, protocol=protocol, timeout=timeout_s)
        except ApiConnectionError:
            time.sleep(0.5)
    raise TimeoutError("T32 did not accept RCL connection in time.")

def run_cmm(debugger, command: str, timeout_s: float = 10.0, end_string: str = UNIQUE_STRING_END) -> list[str]:
    logger.info(f"Executing T32 CMM: {command}")
    m = RE_SCRIPT_NAME.search(command)
    log_file = (FOLDER_TEMP / f'{m.group(1)}.log') if m else (FOLDER_TEMP / 'some_command.log')
    logger.info(f"Writing log file for command '{command}' to: {log_file}")

    debugger.cmd('AREA')
    log_file.write_text('')
    debugger.cmd("AREA.CLEAR")
    debugger.print(UNIQUE_STRING_START)
    debugger.cmd(command)

    t0 = time.time()
    while time.time() - t0 < timeout_s:
        time.sleep(0.2)
        try:
            debugger.cmd(f"AREA.SAVE {log_file}")
        except ApiConnectionError:
            continue
        cmd_out = log_file.read_text(encoding='utf-8', errors='ignore')
        if end_string in cmd_out:
            debugger.cmd("AREA.CLEAR")
            lines = cmd_out.replace(UNIQUE_STRING_START, '').replace(end_string, '').splitlines()
            return [l for l in lines if l.strip()]
    logger.error(f"Command timed out after {timeout_s}s. Log:\n{log_file.read_text(encoding='utf-8', errors='ignore')}")
    raise TimeoutError(f"CMM '{command}' timeout {timeout_s}s")
