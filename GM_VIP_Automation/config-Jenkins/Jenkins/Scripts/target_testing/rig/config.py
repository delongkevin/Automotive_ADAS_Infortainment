import os
import logging
import re
from enum import IntEnum
from pathlib import Path

import git
import serial


class ExitCode(IntEnum):
    """
    Exit codes for target testing scripts.

    Ranges:
      1-9:   Script failures (initialization, setup issues)
      10-19: Monitoring failures (counter checks, stall detection)
      20-29: Stack usage issues
      30-39: EyeQ/CANoe test failures
    """
    # Script failures (1-9)
    TRACE32_INIT_FAILED = 1

    # Monitoring failures (10-19)
    COUNTER_FAIL_NONZERO = 10
    COUNTER_STALL = 11

    # Stack usage issues (20-29)
    STACK_USAGE_HIGH = 20

    # EyeQ/CANoe test failures (30-39)
    CANOE_TEST_FAILED = 30
    EYEQ_VISION_TIMEOUT = 31
    EYEQ_STATE_CHANGED = 32
    EYEQ_FATAL_ERROR = 33

# ==== PORTS / DEVICES ====
RELAY_PORT = os.getenv('Serial_Relay', 'COM1')
POWER_SUPPLY_PORT = os.getenv('Serial_Power_Supply', 'COM4')  # reserved if you add PSU control
OUTLET_POWER_SUPPLY = 2
OUTLET_LAUTERBACH = 1

# UART settings for APPL/APPL_GM targets (same physical UART)
UART_SETTINGS = {
    'port': "COM3",
    'baudrate': 115200,
    'data': 8,
    'parity': serial.PARITY_NONE,
    'stop': 1,
}

# UART settings for GM APPL_GM target (EyeQ messaging - second UART line)
# TODO: Update COM port and baudrate when hardware setup is known
UART_SETTINGS_GM_EQ = {
    'port': "COM7",  # Placeholder - update with actual EyeQ UART port
    'baudrate': 921600,  # Placeholder - update with actual EyeQ baud rate
    'data': 8,
    'parity': serial.PARITY_NONE,
    'stop': 1,
}

UNIQUE_STRING_START = 'Unique String At Start Of Flashing'
UNIQUE_STRING_END = 'Programming Script Completed.'

# ==== PATHS ====
_script_repo = git.Repo(__file__, search_parent_directories=True)
_rev_parse = _script_repo.git.rev_parse("--show-superproject-working-tree").strip()
project_root = Path(_rev_parse or _script_repo.working_tree_dir).resolve()

T32_INSTALL_DIR = Path('C:/T32')
T32_REMOTE_BIN = T32_INSTALL_DIR / 'bin/windows64/t32mtc.exe'
CMM_HSM_FILE = project_root / 'tools/00_TRACE32/flash/tc4d9xe_flash_hsm.cmm'
CMM_APPL_FILE = project_root / 'tools/00_TRACE32/flash/tc4d9xe_flash_boot_rpgm_app.cmm'
CMM_DEBUG_FILE = project_root / 'tools/00_TRACE32/debug/tc4d9xe_debug.cmm'
CMM_STACK_USAGE = project_root / 'tools/00_TRACE32/debug/calcStackUsage.cmm'

# GM-specific CMM flash scripts
CMM_UCB_FILE = project_root / 'sw/customer/doc/tc4d9xe_flash_srec.cmm'
CMM_GM_HEADLESS_FILE = project_root / 'tools/00_TRACE32/debug/GM_Scripts/start_headless.cmm'

FOLDER_TEMP = Path(__file__).parent.parent / 'temp'
LOG_FOLDER = (project_root / "logs")

FOLDER_TEMP.mkdir(parents=True, exist_ok=True)
LOG_FOLDER.mkdir(parents=True, exist_ok=True)

# ==== LOGGER ====
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("rig")

# ==== COMMON ====
RE_SCRIPT_NAME = re.compile(r'\s(.*?.cmm)')
