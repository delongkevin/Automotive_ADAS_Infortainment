import argparse
import logging
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import tabulate
from natsort import natsorted

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Log types and their enabled tests
LOG_TYPE_APPL = 'appl'
LOG_TYPE_APPL_GM = 'appl_gm'
LOG_TYPE_APPL_GM_EQ = 'appl_gm_eq'

# Test enable/disable matrix per log type
TEST_CONFIG = {
    'versions': {LOG_TYPE_APPL: True, LOG_TYPE_APPL_GM: True, LOG_TYPE_APPL_GM_EQ: False},
    'power_stats': {LOG_TYPE_APPL: True, LOG_TYPE_APPL_GM: False, LOG_TYPE_APPL_GM_EQ: False},
    'log_level': {LOG_TYPE_APPL: True, LOG_TYPE_APPL_GM: False, LOG_TYPE_APPL_GM_EQ: False},
    'execution_time': {LOG_TYPE_APPL: True, LOG_TYPE_APPL_GM: False, LOG_TYPE_APPL_GM_EQ: False},
    'bad_logs': {LOG_TYPE_APPL: True, LOG_TYPE_APPL_GM: True, LOG_TYPE_APPL_GM_EQ: True},
    'task_times': {LOG_TYPE_APPL: True, LOG_TYPE_APPL_GM: False, LOG_TYPE_APPL_GM_EQ: False},
    'restarts': {LOG_TYPE_APPL: True, LOG_TYPE_APPL_GM: True, LOG_TYPE_APPL_GM_EQ: False},
    # GM/EyeQ specific tests (placeholders)
    'eyeq_vision_mode': {LOG_TYPE_APPL: False, LOG_TYPE_APPL_GM: False, LOG_TYPE_APPL_GM_EQ: True},
    'eyeq_warning_errors': {LOG_TYPE_APPL: False, LOG_TYPE_APPL_GM: False, LOG_TYPE_APPL_GM_EQ: True},
}

CLEAN_CONFIG = {
    LOG_TYPE_APPL: True,
    LOG_TYPE_APPL_GM: True,
    LOG_TYPE_APPL_GM_EQ: False,  # EQ logs export bin data to Uart, confusing the STX/ETX reconstruction.
}


def is_test_enabled(test_name: str, log_type: str) -> bool:
    """Check if a test is enabled for the given log type."""
    return TEST_CONFIG.get(test_name, {}).get(log_type, False)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', type=Path, default=None, help='Path to log file')
    parser.add_argument('--log_type', type=str, default=LOG_TYPE_APPL,
                        choices=[LOG_TYPE_APPL, LOG_TYPE_APPL_GM, LOG_TYPE_APPL_GM_EQ],
                        help='Type of log being parsed (affects which tests run)')
    return parser.parse_args()


def read_raw_log(path):
    """Read raw log file contents."""
    return path.read_text()


def clean_log(contents):
    """Clean log contents by filtering incomplete lines and removing ANSI codes."""
    re_ansi_colour = re.compile(r'\x1b\[[0-9;]*m')

    # discard lines without exactly 4 ansi colour codes, indicating a fragment or collision
    contents = '\n'.join([line for line in contents.splitlines() if any({
        len(re_ansi_colour.findall(line)) == 0,  # Regular Print statement
        len(re_ansi_colour.findall(line)) == 4,  # Out log message format
    })])

    # Remove ANSI color codes uwu
    contents = re_ansi_colour.sub('', contents)
    return contents


def parse_log_entries(contents) -> list[dict]:
    re_log_message = re.compile(
        # r'(?P<timestamp>[\d-]+\s[\d:.]+)\s'
        r'(?P<elapsed_time>\d\d:\d\d:\d\d)\s'
        r'(?P<level>\w+)\s'
        r'(?P<location>[\w.:]+)\s'
        r'(?P<message>.+)'
    )
    return [m.groupdict() for m in re_log_message.finditer(contents)]


def get_versions(contents):
    re_sw_version = re.compile(r'GM_VIP SW version : (?P<version>.+)')
    re_hsm_version = re.compile(r'HSM SW version : (?P<version>.+)')

    sw_version = re_sw_version.search(contents)
    hsm_version = re_hsm_version.search(contents)
    if not sw_version and not hsm_version:
        logger.error("No software or HSM version found in the log file.")
    return (
        sw_version.group('version') if sw_version else None,
        hsm_version.group('version') if hsm_version else None,
    )


def check_log_level(contents):
    # DCU_SW Compiled@[NA NA] Log:DEBUG
    re_log_level = re.compile(r'Log:(?P<level>\w+)')
    log_levels = re_log_level.findall(contents)
    if not log_levels:
        logger.error("No log level found in the log file???")
        return None
    log_level = [level.upper() for level in log_levels][-1]
    return log_level


def get_pwr_stats(contents):
    re_pwr_voltage = re.compile(r'Battery Voltage in volts\s*:\s*(?P<voltage>[\d.]+)')
    voltage_values = re_pwr_voltage.findall(contents)
    if not voltage_values:
        return None
    voltage_values = [float(v) for v in voltage_values]
    return {
        'min': min(voltage_values),
        'max': max(voltage_values),
        'average': sum(voltage_values) / len(voltage_values),
        'std_dev': math.sqrt(sum((x - (sum(voltage_values) / len(voltage_values))) ** 2 for x in voltage_values) / len(voltage_values)),
        'range': max(voltage_values) - min(voltage_values),
    }


def find_non_negligible_logs(log_entries: list[dict]) -> list[dict]:
    valid_levels = {'TRACE', 'DEBUG', 'INFO', 'WARN', 'WARNING', 'ERR', 'ERROR', 'FATAL', 'OFF'}
    ok_levels = {'TRACE', 'DEBUG', 'INFO'}
    invalid_messages = [log for log in log_entries if log['level'] not in valid_levels]
    if invalid_messages:
        _invalid_message_strs = [f"{log['elapsed_time']} - {log['level']} - {log['location']} - {log['message']}" for log in invalid_messages]
        logger.debug(f'Invalid log entries found, assumed to concurrent output conflicts:\n\t- ' + "\n\t- ".join(_invalid_message_strs))
    valid_messages = [log for log in log_entries if log['level'] in valid_levels]
    non_negligible_messages = [log for log in valid_messages if log['level'] not in ok_levels]
    return non_negligible_messages


def capture_task_times(log_entries: list[dict]) -> None:
    # Task: Core0_50ms_Task, Periodicity: 49.991000 ms
    # Task: Core0_50ms_Task, Total Execution Time: 60919.569000 ms
    # Task: Core0_50ms_Task, Average Time: 0.044854 us
    # Task: Core0_50ms_Task, Maximum Time: 51 us
    # Task: Core0_50ms_Task, Invocation count: 1358186
    re_task_action = re.compile(r'Task:\s*(?P<task>[\w_]+),\s*(?P<action>[\w\s]+):\s*(?P<value>[\d.]+)\s*(?P<unit>[\w%]+)?')
    task_dict = dict()
    for log in log_entries:
        match = re_task_action.search(log['message'])
        if match:
            task = match.group('task')
            action = match.group('action').strip()
            value = float(match.group('value'))
            unit = match.group('unit')
            if task not in task_dict:
                task_dict[task] = dict()
            if unit:
                action = f"{action} ({unit})"
            task_dict[task][action] = value

    for task, actions in task_dict.items():
        max_time = actions.get('Maximum Time (us)', None)
        periodicity = actions.get('Periodicity (ms)', None)
        if max_time and periodicity:
            if max_time > (periodicity * 1000) * 0.7:  # Periodicity is in ms, max_time in us.  70% threshold
                logger.warning(f"Task '{task}' has a maximum execution time of {max_time / 1000:.1f}ms, which exceeds 70% of its periodicity of {periodicity:.1f}ms. Perhaps a task overrun?  Please observe.")

    headers = set()
    for task, actions in task_dict.items():
        headers.update(actions.keys())
    headers = sorted(headers)

    table = []
    for task, actions in natsorted(task_dict.items()):
        row = [task]
        for action in headers:
            if action in actions:
                value = round(actions[action], 3)
                value = str(value).rstrip('0').rstrip('.') if '.' in str(value) else str(int(value))  # Remove trailing 0s
                row.append(value)
            else:
                row.append("")
        table.append(row)
    tabulation = tabulate.tabulate(table, headers=list(headers), tablefmt='github', floatfmt=".03f")
    logger.info(f'Task Timing Summary:\n{tabulation}')


def remove_host_timestamps(contents: str) -> str:
    """
    Remove host-side timestamps from log contents.
    Assumes timestamps are in the format 'YYYY-MM-DD HH:MM:SS.ssssss: ' at the start of lines.
    """
    return re.sub(r'^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\.\d{6}:\s*', '', contents, flags=re.MULTILINE)


def reconstruct_from_STX_ETX(contents: str) -> str:
    """
    Reconstruct log messages that were interleaved by preemption.
    Uses a stack to handle nested STX/ETX pairs - when a new STX is found
    while already inside a message, the current (interrupted) message is
    pushed to the stack and resumed after the inner message completes.

    If no STX/ETX framing is found, returns the original content unchanged.
    """
    STX = '\x02'
    ETX = '\x03'

    class msg:
        def __init__(self):
            self.message = ""
            self.parent = None

    messages = []
    current_msg = None

    contents = contents.lstrip(ETX)

    for char in contents:
        if char == ETX:
            if current_msg:
                messages.append(current_msg.message)
                current_msg = current_msg.parent
            else:
                logger.warning("ETX found without matching STX. Ignoring.")
        elif char == STX:
            new_msg = msg()
            if current_msg:
                new_msg.parent = current_msg
            current_msg = new_msg
        else:
            if current_msg:
                current_msg.message += char
    return '\n'.join(messages)


# ======================== Test Functions ======================== #

def test_versions(contents: str) -> Optional[int]:
    """Test: Check software and HSM versions are present."""
    sw_version, hsm_version = get_versions(contents)
    if not all([sw_version, hsm_version]):
        logger.error("Software or HSM version not found in the log file.")
        return 1
    logger.info(f"Software Version: {sw_version or 'Not found'}")
    logger.info(f"HSM Version: {hsm_version or 'Not found'}")
    return 0


def test_power_stats(contents: str) -> Optional[int]:
    """Test: Check power/battery stats are present and report them."""
    pwr_stats = get_pwr_stats(contents)
    if not pwr_stats:
        logger.error(f'Battery stats not found..?')
        return 1
    for stat, value in pwr_stats.items():
        logger.info(f"Power {stat.capitalize()}: {value:.2f}v")
    return 0


def test_log_level(contents: str, log_entries: list[dict]) -> Optional[int]:
    """Test: Ensure appropriate minimum log messages on debug builds."""
    if check_log_level(contents) == 'DEBUG':
        if len(log_entries) < 200:
            logger.warning(f"There are unexpectedly few log entries ({len(log_entries)}). This may indicate an issue with the logging system.  Please Observe")
            return 1
    return 0


def test_execution_time(log_entries: list[dict]) -> Optional[int]:
    """Test: Ensure total execution time is reasonable (restart/log check)."""
    if not log_entries:
        logger.warning("No log entries to check execution time")
        return 1
    fmt = "%H:%M:%S"
    first = datetime.strptime(log_entries[0]['elapsed_time'], fmt)
    last = datetime.strptime(log_entries[-1]['elapsed_time'], fmt)
    delta = timedelta(
        hours=last.hour - first.hour,
        minutes=last.minute - first.minute,
        seconds=last.second - first.second
    )
    if delta.seconds < 10:
        logger.warning(f"Total execution time is unexpectedly short: {delta.seconds} seconds. Please observe.")
        return 1
    logger.info(f"ECU Ran Total Execution Time: {delta.seconds}")
    return 0


def test_bad_logs(log_entries: list[dict]) -> Optional[int]:
    """Test: Find logs that are WARN level or worse."""
    bad_logs = find_non_negligible_logs(log_entries)
    if bad_logs:
        logger.warning(f"Found {len(bad_logs)} non-negligible log entries OwO:")
        for log in bad_logs:
            logger.warning(f"Timestamp: '{log['elapsed_time']}'. Level: '{log['level']}'. Location: '{log['location']}'\n\tMessage: '{log['message']}'")
        return 1
    return 0


def test_restarts(contents: str) -> Optional[int]:
    """Test: Check for unexpected restarts."""
    start_string = "++++++++++++++++++++++++++++++++++++++++"
    restarts = contents.count(start_string) // 2
    if restarts > 3:
        logger.warning(f"Soft restarts may be found, with the start string `+++...` found {restarts} times. Please observe.")
        return 1
    return 0


def test_eyeq_vision_mode(contents: str) -> Optional[int]:
    """
    Test: Check EyeQ vision mode status (GM EyeQ UART only).
    """
    modes = {
        'EyeQ': {'burn-code'},
        'APP': {'pending', 'running'}
    }
    retval = 0

    # APP is running in pending mode
    # APP is running in running mode
    # EyeQ is running in burn-code mode
    for mode, statuses in modes.items():
        for status in statuses:
            re_mode = re.compile(rf'{mode} is running in {status} mode', re.IGNORECASE)
            if re_mode.search(contents):
                logger.info(f"Detected {mode}'s mode: {status}")
                continue
            else:
                logger.warning(f"Did not detect expected {mode}'s status '{status}'. Please observe.")
                retval = 1
    return retval


def test_eyeq_warning_errors(contents: str) -> Optional[int]:
    """
    Test: Check for EyeQ-specific warning or error messages (GM EyeQ UART only).
    """
    # find all lines with the word "warning" in it, case insensitive
    lines = contents.splitlines()
    eyeq_warnings = [line for line in lines if re.search(r'warning', line, re.IGNORECASE)]
    eyeq_errors = [line for line in lines if re.search(r'error', line, re.IGNORECASE) and not any([
        'total_errors' in line.lower(),
    ])]
    retval = 0
    repeat_concern_threshold = 20
    if eyeq_warnings:
        _sorted_set = sorted(set(eyeq_warnings))
        if (len(eyeq_warnings) - len(_sorted_set)) > repeat_concern_threshold:
            logger.warning(f"Found {len(eyeq_warnings)} EyeQ warning messages, with {len(eyeq_warnings) - len(_sorted_set)} repeats. This may indicate a recurring issue. Please observe.")
            retval = 1
        warnings = '\n\t - '.join(_sorted_set)
        logger.warning(f"Found {len(_sorted_set)} unique EyeQ warning messages. Please observe.\n\t - {warnings}")
    if eyeq_errors:
        if (len(eyeq_errors) - len(set(eyeq_errors))) > repeat_concern_threshold:
            logger.warning(f"Found {len(eyeq_errors)} EyeQ error messages, with {len(eyeq_errors) - len(set(eyeq_errors))} repeats. This may indicate a recurring issue. Please observe.")
            retval = 1
        _sorted_set = sorted(set(eyeq_errors))
        errors = '\n\t - '.join(_sorted_set)
        logger.warning(f"Found {len(_sorted_set)} EyeQ error messages. Please observe.\n\t - {errors}")
        # retval = 1  # Initial implementation has warnings and errors included
    if not eyeq_warnings and not eyeq_errors:
        logger.info("No EyeQ warnings or errors found.")
    else:
        logger.warning(f"EyeQ warnings or errors found.")
    return retval


# ======================== Main Function ======================== #

def main():
    args = parse_args()
    log_type = args.log_type

    # Determine default log file based on log type
    default_log_files = {
        LOG_TYPE_APPL: "uart_appl.log",
        LOG_TYPE_APPL_GM: "uart_appl_gm.log",
        LOG_TYPE_APPL_GM_EQ: "uart_appl_gm_EQ.log",
    }
    log_file = Path(args.log) if args.log else Path(__file__).parent / "Output" / default_log_files.get(log_type, "uart_appl.log")

    # Set up output log file
    parsed_log_name = f'parsed_{log_type}.log'
    log_file.parent.mkdir(exist_ok=True, parents=True)
    logger.addHandler(logging.FileHandler(log_file.parent / parsed_log_name, 'w'))

    logger.info(f"Parsing {log_type} log: {log_file}")

    retval = 0
    contents = read_raw_log(log_file)

    if not log_file.exists():
        logger.error(f"Log file not found: {log_file}")
        return 1

    # Test: Restarts check (must run before trimming to last boot cycle)
    if is_test_enabled('restarts', log_type):
        if test_restarts(contents):
            retval = 1

    # Action: Only keep the last boot cycle (for APPL logs)
    start_string = "++++++++++++++++++++++++++++++++++++++++"
    if start_string in contents:
        contents = '\n'.join(contents.split(start_string)[-2:])

    if CLEAN_CONFIG.get(log_type, False):
        contents = reconstruct_from_STX_ETX(contents)

    contents = remove_host_timestamps(contents)

    # Clean log (filter incomplete lines, remove ANSI codes) AFTER reconstruction
    contents = clean_log(contents)
    log_file.with_suffix('.cleaned.log').write_text(contents)  # Save cleaned log for reference

    log_entries = parse_log_entries(contents)

    # Test pipeline: (config_key, callable)
    # Each callable receives (contents, log_entries) and must return 0/None on
    # success or non-zero on failure.  Wrapping individual signatures with
    # lambdas keeps the test functions themselves unchanged.
    tests = [
        ('versions', lambda c, le: test_versions(c)),
        ('power_stats', lambda c, le: test_power_stats(c)),
        ('log_level', lambda c, le: test_log_level(c, le)),
        ('execution_time', lambda c, le: test_execution_time(le)),
        ('bad_logs', lambda c, le: test_bad_logs(le)),
        ('task_times', lambda c, le: capture_task_times(le)),
        ('eyeq_vision_mode', lambda c, le: test_eyeq_vision_mode(c)),
        ('eyeq_warning_errors', lambda c, le: test_eyeq_warning_errors(c)),
    ]

    for test_name, test_fn in tests:
        if is_test_enabled(test_name, log_type):
            if test_fn(contents, log_entries):
                retval = 1

    return retval


if __name__ == "__main__":
    script_result = main()
    if script_result == 0:
        logger.info("No issues found in the log file.")
    exit(script_result)
