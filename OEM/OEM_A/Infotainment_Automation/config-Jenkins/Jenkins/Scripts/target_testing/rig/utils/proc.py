import time
import psutil
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def kill_process_by_name(name: str, grace_sleep_s: float = 4.0) -> bool:
    """Kill all processes whose name contains the given string."""
    name = name.lower()
    killed = False
    retrys = 3

    procs = [p for p in psutil.process_iter(['name']) if p.info['name'] and name in p.info['name'].lower()]
    for p in procs:
        logger.info(f"Terminating process {p.pid} ({p.info['name']})")
        for _ in range(retrys):
            try:
                p.terminate()
                killed = True
                p.wait(timeout=2)
                break
            except psutil.AccessDenied:
                logger.debug(f"\tAccess denied when trying to terminate process {p.pid} ({p.info['name']})")
            except psutil.TimeoutExpired:
                logger.debug(f"\tProcess {p.pid} ({p.info['name']}) did not terminate in time, retrying...")
    if killed and grace_sleep_s > 0:
        time.sleep(grace_sleep_s)
    return killed
