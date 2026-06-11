import re
from pathlib import Path
from ..config import logger

RE_STACK_USAGE = re.compile(
    r'(?P<cpu>CPU\S+):\s+'
    r'Used\s+=\s+(?P<used>0x[0-9A-Fa-f]+)\s+bytes,\s+'
    r'Free\s+=\s+(?P<free>0x[0-9A-Fa-f]+)\s+bytes,\s+'
    r'Percent\s+Used\s+=\s+(?P<percent_used>\d+)%'
)

def run_and_parse_stack_usage(dbg, cmm_path: Path, report_folder: Path, run_cmm_func, end_marker="STACK USAGE CHECK DONE"):
    dbg.cmd(f"cd {cmm_path.parent}")
    log_lines = run_cmm_func(debugger=dbg, command=f'run {cmm_path.name}', timeout_s=60, end_string=end_marker)
    (report_folder / "stack-usage.txt").write_text('\n'.join(log_lines), encoding='utf-8')

    msgs = [m.groupdict() for m in RE_STACK_USAGE.finditer("\n".join(log_lines))]
    for msg in msgs:
        logger.info(f"CPU: {msg['cpu']}, Used: {msg['used']}, Free: {msg['free']}, Percent Used: {msg['percent_used']}%")
    return msgs, log_lines
