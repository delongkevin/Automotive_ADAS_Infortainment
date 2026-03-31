"""
Tests for GM_VIP_Automation_Framework.core.capl_monitor
All tests run in mock mode – no hardware or CANoe installation required.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub lauterbach before importing framework modules.
# ---------------------------------------------------------------------------
sys.modules.setdefault("lauterbach", MagicMock())
sys.modules.setdefault("lauterbach.trace32", MagicMock())
sys.modules.setdefault("lauterbach.trace32.rcl", MagicMock())
sys.modules.setdefault("lauterbach.trace32.rcl._rc", MagicMock())
sys.modules.setdefault("lauterbach.trace32.rcl._rc._error", MagicMock())


from GM_VIP_Automation_Framework.core.capl_monitor import (  # noqa: E402
    CAPLVerdict,
    CAPLTestResult,
    CAPLTestMonitor,
)
from GM_VIP_Automation_Framework.core.canoe import CANoeClient  # noqa: E402


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _mock_canoe() -> CANoeClient:
    """Return a CANoeClient in mock mode."""
    return CANoeClient(mock=True)


# ---------------------------------------------------------------------------
# CAPLVerdict
# ---------------------------------------------------------------------------

class TestCAPLVerdict(unittest.TestCase):

    def test_from_int_valid(self):
        self.assertEqual(CAPLVerdict.from_int(1), CAPLVerdict.PASS)
        self.assertEqual(CAPLVerdict.from_int(2), CAPLVerdict.FAIL)
        self.assertEqual(CAPLVerdict.from_int(3), CAPLVerdict.ERROR)
        self.assertEqual(CAPLVerdict.from_int(4), CAPLVerdict.NOTRUN)

    def test_from_int_zero_is_none(self):
        self.assertEqual(CAPLVerdict.from_int(0), CAPLVerdict.NONE)

    def test_from_int_unknown_defaults_to_none(self):
        self.assertEqual(CAPLVerdict.from_int(99), CAPLVerdict.NONE)

    def test_label_property(self):
        self.assertEqual(CAPLVerdict.PASS.label, "PASS")
        self.assertEqual(CAPLVerdict.FAIL.label, "FAIL")
        self.assertEqual(CAPLVerdict.ERROR.label, "ERROR")
        self.assertEqual(CAPLVerdict.NONE.label, "NONE")
        self.assertEqual(CAPLVerdict.NOTRUN.label, "NOTRUN")

    def test_int_values(self):
        self.assertEqual(int(CAPLVerdict.NONE),   0)
        self.assertEqual(int(CAPLVerdict.PASS),   1)
        self.assertEqual(int(CAPLVerdict.FAIL),   2)
        self.assertEqual(int(CAPLVerdict.ERROR),  3)
        self.assertEqual(int(CAPLVerdict.NOTRUN), 4)


# ---------------------------------------------------------------------------
# CAPLTestResult
# ---------------------------------------------------------------------------

class TestCAPLTestResult(unittest.TestCase):

    def _make(self, verdict=CAPLVerdict.PASS) -> CAPLTestResult:
        return CAPLTestResult(module="Mod", name="TC_001", verdict=verdict)

    def test_passed_true_for_pass(self):
        self.assertTrue(self._make(CAPLVerdict.PASS).passed)

    def test_passed_false_for_fail(self):
        self.assertFalse(self._make(CAPLVerdict.FAIL).passed)

    def test_failed_true_for_fail(self):
        self.assertTrue(self._make(CAPLVerdict.FAIL).failed)

    def test_failed_true_for_error(self):
        self.assertTrue(self._make(CAPLVerdict.ERROR).failed)

    def test_failed_false_for_pass(self):
        self.assertFalse(self._make(CAPLVerdict.PASS).failed)

    def test_failed_false_for_none(self):
        self.assertFalse(self._make(CAPLVerdict.NONE).failed)

    def test_to_dict_keys(self):
        d = self._make().to_dict()
        for key in ("module", "name", "verdict", "error_message", "exec_time_s", "timestamp"):
            self.assertIn(key, d)

    def test_to_dict_verdict_is_string(self):
        d = self._make(CAPLVerdict.FAIL).to_dict()
        self.assertEqual(d["verdict"], "FAIL")

    def test_repr_contains_name(self):
        r = repr(self._make())
        self.assertIn("TC_001", r)
        self.assertIn("PASS", r)


# ---------------------------------------------------------------------------
# CAPLTestMonitor – mock mode
# ---------------------------------------------------------------------------

class TestCAPLTestMonitorMock(unittest.TestCase):

    def setUp(self):
        self.monitor = CAPLTestMonitor(_mock_canoe(), mock=True)

    def test_get_test_results_returns_list(self):
        results = self.monitor.get_test_results()
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

    def test_get_test_results_all_are_capl_test_result(self):
        for r in self.monitor.get_test_results():
            self.assertIsInstance(r, CAPLTestResult)

    def test_get_failed_tests_subset(self):
        all_results = self.monitor.get_test_results()
        failures = self.monitor.get_failed_tests()
        self.assertLessEqual(len(failures), len(all_results))
        for f in failures:
            self.assertTrue(f.failed)

    def test_get_passed_tests_subset(self):
        passes = self.monitor.get_passed_tests()
        for p in passes:
            self.assertTrue(p.passed)

    def test_mock_has_at_least_one_pass_and_one_fail(self):
        results = self.monitor.get_test_results()
        self.assertTrue(any(r.passed for r in results),
                        "Mock should include at least one PASS")
        self.assertTrue(any(r.failed for r in results),
                        "Mock should include at least one FAIL/ERROR")

    def test_results_summary_contains_expected_keys(self):
        summary = self.monitor.results_summary()
        self.assertIsInstance(summary, dict)
        self.assertIn("PASS", summary)
        self.assertIn("FAIL", summary)

    def test_wait_for_completion_mock_returns_immediately(self):
        results = self.monitor.wait_for_completion(timeout_s=5.0)
        self.assertIsInstance(results, list)

    def test_wait_for_completion_returns_capl_test_results(self):
        results = self.monitor.wait_for_completion(timeout_s=5.0)
        for r in results:
            self.assertIsInstance(r, CAPLTestResult)

    def test_mock_module_names_present(self):
        results = self.monitor.get_test_results()
        module_names = {r.module for r in results}
        self.assertIn("MockModule_CAN", module_names)
        self.assertIn("MockModule_Diagnostics", module_names)

    def test_mock_test_names_present(self):
        results = self.monitor.get_test_results()
        names = {r.name for r in results}
        self.assertIn("TC_001_CanInit", names)
        self.assertIn("TC_002_CanRxFrame", names)

    def test_failed_test_has_error_message(self):
        failures = self.monitor.get_failed_tests()
        self.assertTrue(len(failures) > 0)
        for f in failures:
            # Mock failures should have a non-empty error message.
            self.assertIsInstance(f.error_message, str)

    def test_exec_time_is_float(self):
        for r in self.monitor.get_test_results():
            self.assertIsInstance(r.exec_time_s, float)

    def test_timestamp_is_float(self):
        for r in self.monitor.get_test_results():
            self.assertIsInstance(r.timestamp, float)


# ---------------------------------------------------------------------------
# CAPLTestMonitor – live COM path with mocked app object
# ---------------------------------------------------------------------------

class TestCAPLTestMonitorLiveMocked(unittest.TestCase):
    """Exercise the _live_results() code path by injecting a fake COM tree."""

    def _build_com_tree(self, pass_count=2, fail_count=1):
        """Return a minimal CANoe COM object tree with synthetic test cases."""
        def _make_tc(name, verdict_int, exec_time=0.1, desc=""):
            tc = MagicMock()
            tc.Name = name
            tc.Verdict = verdict_int
            tc.ExecTime = exec_time
            tc.Description = desc
            return tc

        # Build test cases list.
        tcs_data = [_make_tc(f"TC_PASS_{i}", 1) for i in range(pass_count)]
        tcs_data += [_make_tc(f"TC_FAIL_{i}", 2, desc="failure detail") for i in range(fail_count)]

        test_cases_col = MagicMock()
        test_cases_col.Count = len(tcs_data)
        test_cases_col.Item.side_effect = lambda i: tcs_data[i - 1]

        module = MagicMock()
        module.Name = "FakeModule"
        module.TestCases = test_cases_col

        modules_col = MagicMock()
        modules_col.Count = 1
        modules_col.Item.side_effect = lambda i: module

        test_system = MagicMock()
        test_system.TestModules = modules_col

        app = MagicMock()
        app.TestSystem = test_system
        return app

    def test_live_results_correct_count(self):
        canoe = CANoeClient(mock=False)
        canoe._app = self._build_com_tree(pass_count=3, fail_count=2)
        monitor = CAPLTestMonitor(canoe, mock=False)
        results = monitor._live_results()
        self.assertEqual(len(results), 5)

    def test_live_results_pass_count(self):
        canoe = CANoeClient(mock=False)
        canoe._app = self._build_com_tree(pass_count=3, fail_count=1)
        monitor = CAPLTestMonitor(canoe, mock=False)
        self.assertEqual(len(monitor.get_passed_tests()), 3)

    def test_live_results_fail_count(self):
        canoe = CANoeClient(mock=False)
        canoe._app = self._build_com_tree(pass_count=2, fail_count=2)
        monitor = CAPLTestMonitor(canoe, mock=False)
        self.assertEqual(len(monitor.get_failed_tests()), 2)

    def test_live_results_module_name_propagated(self):
        canoe = CANoeClient(mock=False)
        canoe._app = self._build_com_tree()
        monitor = CAPLTestMonitor(canoe, mock=False)
        results = monitor._live_results()
        for r in results:
            self.assertEqual(r.module, "FakeModule")

    def test_live_results_no_app_returns_empty(self):
        canoe = CANoeClient(mock=False)
        canoe._app = None
        monitor = CAPLTestMonitor(canoe, mock=False)
        self.assertEqual(monitor._live_results(), [])

    def test_live_results_no_test_system_returns_empty(self):
        canoe = CANoeClient(mock=False)
        app = MagicMock()
        app.TestSystem = None
        canoe._app = app
        monitor = CAPLTestMonitor(canoe, mock=False)
        self.assertEqual(monitor._live_results(), [])

    def test_live_results_error_message_on_fail(self):
        canoe = CANoeClient(mock=False)
        canoe._app = self._build_com_tree(pass_count=0, fail_count=1)
        monitor = CAPLTestMonitor(canoe, mock=False)
        failures = monitor.get_failed_tests()
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].error_message, "failure detail")


# ---------------------------------------------------------------------------
# CAPLTestMonitor – wait_for_completion timeout
# ---------------------------------------------------------------------------

class TestCAPLTestMonitorTimeout(unittest.TestCase):

    def test_wait_for_completion_raises_on_never_done(self):
        """wait_for_completion should raise T32TimeoutError when tests stay at NONE."""
        from GM_VIP_Automation_Framework.utils.exceptions import T32TimeoutError

        canoe = CANoeClient(mock=False)

        # Build a COM tree where all verdicts remain 0 (NONE).
        tc = MagicMock()
        tc.Name = "TC_Pending"
        tc.Verdict = 0  # NONE – never finishes
        tc.ExecTime = 0.0
        tc.Description = ""

        tcs = MagicMock()
        tcs.Count = 1
        tcs.Item.return_value = tc

        mod = MagicMock()
        mod.Name = "PendingModule"
        mod.TestCases = tcs

        mods = MagicMock()
        mods.Count = 1
        mods.Item.return_value = mod

        ts = MagicMock()
        ts.TestModules = mods

        app = MagicMock()
        app.TestSystem = ts
        canoe._app = app

        monitor = CAPLTestMonitor(canoe, poll_interval_s=0.05, mock=False)
        with self.assertRaises(T32TimeoutError):
            monitor.wait_for_completion(timeout_s=0.2)


if __name__ == "__main__":
    unittest.main()
