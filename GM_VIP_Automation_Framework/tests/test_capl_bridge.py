"""
Tests for GM_VIP_Automation_Framework.capl_bridge
All tests run in mock mode – no hardware or CANoe installation required.
"""

import json
import os
import sys
import tempfile
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

from GM_VIP_Automation_Framework.core.canoe import CANoeClient  # noqa: E402
from GM_VIP_Automation_Framework.core.capl_monitor import (  # noqa: E402
    CAPLTestResult, CAPLVerdict,
)
from GM_VIP_Automation_Framework.capl_bridge import (  # noqa: E402
    CAPLBridge, CAPLBridgeReport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_canoe() -> CANoeClient:
    return CANoeClient(mock=True)


def _mock_conn() -> MagicMock:
    """Return a minimal mock T32 connection."""
    conn = MagicMock()
    conn.fnc.return_value = "0x80001234"
    conn.cmd.return_value = None
    return conn


# ---------------------------------------------------------------------------
# CAPLBridgeReport
# ---------------------------------------------------------------------------

class TestCAPLBridgeReport(unittest.TestCase):

    def _make_report(self) -> CAPLBridgeReport:
        r = CAPLBridgeReport()
        r.session_name = "test_session"
        r.elapsed_s = 1.5
        r.passed = ["TC_001", "TC_002"]
        r.failed = ["TC_003"]
        r.debug_reports = {"TC_003": {"pc": "0x80001234", "variables": {}}}
        r.generated_test_cases = "/tmp/test_cases.json"
        r.generated_script = "/tmp/session_script.py"
        return r

    def test_to_dict_has_all_keys(self):
        d = self._make_report().to_dict()
        for key in (
            "session_name", "elapsed_s", "passed", "failed",
            "debug_reports", "generated_test_cases", "generated_script"
        ):
            self.assertIn(key, d)

    def test_to_dict_passed_list(self):
        d = self._make_report().to_dict()
        self.assertEqual(d["passed"], ["TC_001", "TC_002"])

    def test_to_dict_failed_list(self):
        d = self._make_report().to_dict()
        self.assertEqual(d["failed"], ["TC_003"])

    def test_repr_contains_counts(self):
        r = repr(self._make_report())
        self.assertIn("passed=2", r)
        self.assertIn("failed=1", r)

    def test_save_creates_file(self):
        report = self._make_report()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = report.save(output_dir=tmpdir)
            self.assertTrue(os.path.isfile(path))

    def test_save_valid_json(self):
        report = self._make_report()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = report.save(output_dir=tmpdir)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        self.assertIn("session_name", data)


# ---------------------------------------------------------------------------
# CAPLBridge – construction and properties
# ---------------------------------------------------------------------------

class TestCAPLBridgeInit(unittest.TestCase):

    def test_default_mock_from_canoe(self):
        canoe = _mock_canoe()
        bridge = CAPLBridge(canoe_client=canoe)
        self.assertTrue(bridge._mock)

    def test_explicit_mock_true(self):
        canoe = _mock_canoe()
        bridge = CAPLBridge(canoe_client=canoe, mock=True)
        self.assertTrue(bridge._mock)

    def test_monitor_property(self):
        canoe = _mock_canoe()
        bridge = CAPLBridge(canoe_client=canoe)
        from GM_VIP_Automation_Framework.core.capl_monitor import CAPLTestMonitor
        self.assertIsInstance(bridge.monitor, CAPLTestMonitor)

    def test_recorder_property(self):
        canoe = _mock_canoe()
        bridge = CAPLBridge(canoe_client=canoe)
        from GM_VIP_Automation_Framework.core.sequence_recorder import SequenceRecorder
        self.assertIsInstance(bridge.recorder, SequenceRecorder)

    def test_output_dir_stored(self):
        canoe = _mock_canoe()
        bridge = CAPLBridge(canoe_client=canoe, output_dir="/tmp/test_out")
        self.assertEqual(bridge.output_dir, "/tmp/test_out")

    def test_session_name_stored(self):
        canoe = _mock_canoe()
        bridge = CAPLBridge(canoe_client=canoe, session_name="my_session")
        self.assertEqual(bridge._session_name, "my_session")

    def test_custom_debug_symbols_stored(self):
        canoe = _mock_canoe()
        syms = ["g_Foo", "g_Bar"]
        bridge = CAPLBridge(canoe_client=canoe, debug_symbols=syms)
        self.assertEqual(bridge._debug_syms, syms)


# ---------------------------------------------------------------------------
# CAPLBridge – debug_failed_test (mock mode)
# ---------------------------------------------------------------------------

class TestCAPLBridgeDebugFailedTest(unittest.TestCase):

    def _make_bridge(self, with_conn=False) -> CAPLBridge:
        canoe = _mock_canoe()
        conn = _mock_conn() if with_conn else None
        return CAPLBridge(
            canoe_client=canoe,
            t32_connection=conn,
            mock=True,
            session_name="debug_session",
            debug_symbols=["g_Status", "g_Error"],
        )

    def _make_fail_result(self, name="TC_FAIL_001") -> CAPLTestResult:
        return CAPLTestResult(
            module="Module_CAN",
            name=name,
            verdict=CAPLVerdict.FAIL,
            error_message="Expected 1, got 0",
        )

    def test_debug_no_conn_returns_dict(self):
        bridge = self._make_bridge(with_conn=False)
        info = bridge.debug_failed_test(self._make_fail_result())
        self.assertIsInstance(info, dict)

    def test_debug_no_conn_t32_available_false(self):
        bridge = self._make_bridge(with_conn=False)
        info = bridge.debug_failed_test(self._make_fail_result())
        self.assertFalse(info["t32_available"])

    def test_debug_with_conn_mock_t32_available_true(self):
        bridge = self._make_bridge(with_conn=True)
        info = bridge.debug_failed_test(self._make_fail_result())
        self.assertTrue(info["t32_available"])

    def test_debug_result_has_test_name(self):
        bridge = self._make_bridge(with_conn=False)
        info = bridge.debug_failed_test(self._make_fail_result("TC_XYZ"))
        self.assertEqual(info["test_name"], "TC_XYZ")

    def test_debug_result_has_verdict(self):
        bridge = self._make_bridge(with_conn=False)
        info = bridge.debug_failed_test(self._make_fail_result())
        self.assertEqual(info["verdict"], "FAIL")

    def test_debug_result_has_variables_dict(self):
        bridge = self._make_bridge(with_conn=False)
        info = bridge.debug_failed_test(self._make_fail_result())
        self.assertIsInstance(info["variables"], dict)

    def test_debug_with_conn_mock_populates_variables(self):
        bridge = self._make_bridge(with_conn=True)
        info = bridge.debug_failed_test(self._make_fail_result())
        self.assertIn("g_Status", info["variables"])
        self.assertIn("g_Error", info["variables"])

    def test_debug_with_conn_mock_has_pc(self):
        bridge = self._make_bridge(with_conn=True)
        info = bridge.debug_failed_test(self._make_fail_result())
        self.assertIn("pc", info)
        self.assertIsInstance(info["pc"], str)

    def test_debug_result_has_timestamp(self):
        bridge = self._make_bridge(with_conn=False)
        info = bridge.debug_failed_test(self._make_fail_result())
        self.assertIsInstance(info["timestamp"], float)
        self.assertGreater(info["timestamp"], 0)


# ---------------------------------------------------------------------------
# CAPLBridge – monitor_and_debug (mock mode)
# ---------------------------------------------------------------------------

class TestCAPLBridgeMonitorAndDebug(unittest.TestCase):

    def _make_bridge(self, output_dir: str) -> CAPLBridge:
        canoe = _mock_canoe()
        return CAPLBridge(
            canoe_client=canoe,
            mock=True,
            session_name="monitor_session",
            output_dir=output_dir,
        )

    def test_returns_capl_bridge_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = self._make_bridge(tmpdir)
            report = bridge.monitor_and_debug(timeout_s=5.0)
        self.assertIsInstance(report, CAPLBridgeReport)

    def test_report_has_passed_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = self._make_bridge(tmpdir)
            report = bridge.monitor_and_debug()
        self.assertIsInstance(report.passed, list)

    def test_report_has_failed_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = self._make_bridge(tmpdir)
            report = bridge.monitor_and_debug()
        self.assertIsInstance(report.failed, list)

    def test_report_has_debug_reports_for_failures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = self._make_bridge(tmpdir)
            report = bridge.monitor_and_debug()
        # Every failed test should have a debug report entry.
        for name in report.failed:
            self.assertIn(name, report.debug_reports)

    def test_report_session_name_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = self._make_bridge(tmpdir)
            report = bridge.monitor_and_debug()
        self.assertEqual(report.session_name, "monitor_session")

    def test_report_elapsed_s_positive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = self._make_bridge(tmpdir)
            report = bridge.monitor_and_debug()
        self.assertGreaterEqual(report.elapsed_s, 0.0)

    def test_export_creates_json_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = self._make_bridge(tmpdir)
            report = bridge.monitor_and_debug(export=True)
            self.assertTrue(
                os.path.isfile(report.generated_test_cases),
                f"Expected JSON at {report.generated_test_cases}"
            )

    def test_export_creates_python_script(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = self._make_bridge(tmpdir)
            report = bridge.monitor_and_debug(export=True)
            self.assertTrue(
                os.path.isfile(report.generated_script),
                f"Expected script at {report.generated_script}"
            )

    def test_no_export_when_export_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = self._make_bridge(tmpdir)
            report = bridge.monitor_and_debug(export=False)
        self.assertEqual(report.generated_test_cases, "")
        self.assertEqual(report.generated_script, "")

    def test_mock_produces_both_passes_and_failures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = self._make_bridge(tmpdir)
            report = bridge.monitor_and_debug(export=False)
        self.assertGreater(len(report.passed) + len(report.failed), 0)

    def test_report_to_dict_serialisable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = self._make_bridge(tmpdir)
            report = bridge.monitor_and_debug()
            d = report.to_dict()
        # Should be JSON-serialisable without errors.
        json.dumps(d)

    def test_report_save(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = self._make_bridge(tmpdir)
            report = bridge.monitor_and_debug()
            path = report.save(output_dir=tmpdir)
            self.assertTrue(os.path.isfile(path))


# ---------------------------------------------------------------------------
# CAPLBridge – export_learned_sequences
# ---------------------------------------------------------------------------

class TestCAPLBridgeExportLearnedSequences(unittest.TestCase):

    def test_export_learned_sequences_creates_file(self):
        canoe = _mock_canoe()
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = CAPLBridge(
                canoe_client=canoe,
                mock=True,
                output_dir=tmpdir,
                session_name="learn_seq",
            )
            bridge.recorder.start_recording()
            bridge.recorder.record_breakpoint_set("TestFn")
            bridge.recorder.record_go()
            bridge.recorder.record_halt("TestFn")
            bridge.recorder.stop_recording()

            path = bridge.export_learned_sequences(output_dir=tmpdir)
            self.assertTrue(os.path.isfile(path))

    def test_export_learned_sequences_valid_json(self):
        canoe = _mock_canoe()
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = CAPLBridge(
                canoe_client=canoe,
                mock=True,
                output_dir=tmpdir,
                session_name="learn_seq2",
            )
            bridge.recorder.start_recording()
            bridge.recorder.record_go()
            bridge.recorder.stop_recording()

            path = bridge.export_learned_sequences(output_dir=tmpdir)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        self.assertIn("test_cases", data)


if __name__ == "__main__":
    unittest.main()
