from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

try:
    import win32com.client as win32
except Exception:  # pywin32 may not be available on non-Windows dev hosts
    win32 = None


class CanoeController:
    def __init__(self):
        if not win32:
            raise RuntimeError("pywin32 not available; CANoe control disabled.")
        self.app = win32.Dispatch("CANoe.Application")

    def open_config(self, cfg_path: Path):
        logger.info(f"Opening CANoe config: {cfg_path}")
        self.app.Open(str(cfg_path))

    def start_measurement(self):
        m = self.app.Measurement
        if not m.Running:
            m.Start()

    def stop_measurement(self):
        m = self.app.Measurement
        if m.Running:
            m.Stop()

    def set_measurement_on_off(self, on: bool):
        is_running = self.app.Measurement.Running
        if on and not is_running:
            self.app.Measurement.Start()
        elif not on and is_running:
            self.app.Measurement.Stop()

    @staticmethod
    def _execute_test_module(test_module, timeout: int = 60 * 30, poll: int = 60, settle: int = 30):
        module_report_path = Path(test_module.Report.Path)
        get_reports = lambda: set(module_report_path.glob('*.xml')) | set(module_report_path.glob('*.html'))
        logger.info(f"  Running test module '{getattr(test_module, 'Name', 'module')}'")

        reports = get_reports()
        for _report in reports:
            _report.unlink(missing_ok=True)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            test_module.Start()
            logger.debug(f"    Waiting for {module_report_path} reports...")
            time.sleep(poll)
            reports = get_reports()
            if reports:
                time.sleep(settle)  # let writers finish
                confirm = get_reports()
                if confirm:
                    return confirm
        raise TimeoutError(f"  No reports found in {module_report_path} within {timeout}s")

    def select_and_run_tests(self, env_names: list[str] | str | None = None):
        _testEnvironments = self.app.Configuration.TestSetup.TestEnvironments
        testEnvironments = {env.Name: env for env in _testEnvironments}

        if not env_names:
            logger.info(f'No Test Environment name provided.  Seen environments for selection are : {list(testEnvironments.keys())}. Assuming all are wanted.')
        elif isinstance(env_names, str):
            env_names = [env_names]
        running = set()
        for env_name in env_names:
            if env_name not in testEnvironments:
                raise RuntimeError(f"Test Environment '{env_name}' not found.  Seen environments for selection are : {list(testEnvironments.keys())}.")
            running.add(env_name)

        return_reports = set()
        for env_name in running:
            logger.info(f"Running CANoe Test Environment: {env_name}")
            env = testEnvironments[env_name]
            # testModules = {tm.Name: tm for tm in env.Items}
            testModules = {tm.Name: tm for tm in env.TestModules}
            for testModule in testModules.values():
                reports = self._execute_test_module(testModule)
                return_reports.update(reports)
        return return_reports

    def fetch_results(self, report_html: Path):
        rep = self.app.Report
        rep.Clear()
        rep.Filename = str(report_html)
        rep.GenerateReport()
        return Path(rep.Filename)

    def close(self):
        self.stop_measurement()
        self.app.Quit()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
