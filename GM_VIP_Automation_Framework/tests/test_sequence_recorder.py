"""
Tests for GM_VIP_Automation_Framework.core.sequence_recorder
All tests run without hardware.
"""

import json
import os
import sys
import tempfile
import unittest

sys.modules.setdefault("lauterbach", __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock())
sys.modules.setdefault("lauterbach.trace32", __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock())
sys.modules.setdefault("lauterbach.trace32.rcl", __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock())
sys.modules.setdefault("lauterbach.trace32.rcl._rc", __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock())
sys.modules.setdefault("lauterbach.trace32.rcl._rc._error", __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock())

from GM_VIP_Automation_Framework.core.sequence_recorder import (  # noqa: E402
    ExecutionEvent,
    SequenceRecorder,
)


# ---------------------------------------------------------------------------
# ExecutionEvent
# ---------------------------------------------------------------------------

class TestExecutionEvent(unittest.TestCase):

    def test_default_fields(self):
        e = ExecutionEvent(event_type="go")
        self.assertEqual(e.event_type, "go")
        self.assertEqual(e.symbol, "")
        self.assertIsNone(e.value)
        self.assertIsInstance(e.timestamp, float)
        self.assertEqual(e.metadata, {})

    def test_to_dict_has_all_keys(self):
        e = ExecutionEvent(event_type="variable_read", symbol="g_Var", value=42)
        d = e.to_dict()
        for key in ("event_type", "symbol", "value", "timestamp", "metadata"):
            self.assertIn(key, d)

    def test_to_dict_values(self):
        e = ExecutionEvent(event_type="halt", symbol="TestFunc", value=None)
        d = e.to_dict()
        self.assertEqual(d["event_type"], "halt")
        self.assertEqual(d["symbol"], "TestFunc")
        self.assertIsNone(d["value"])

    def test_repr_contains_type(self):
        e = ExecutionEvent(event_type="breakpoint_set", symbol="MyFn")
        r = repr(e)
        self.assertIn("breakpoint_set", r)
        self.assertIn("MyFn", r)

    def test_metadata_stored(self):
        e = ExecutionEvent(event_type="custom", metadata={"core": 1})
        self.assertEqual(e.metadata["core"], 1)


# ---------------------------------------------------------------------------
# SequenceRecorder – recording lifecycle
# ---------------------------------------------------------------------------

class TestSequenceRecorderLifecycle(unittest.TestCase):

    def setUp(self):
        self.rec = SequenceRecorder(session_name="test_session")

    def test_not_recording_initially(self):
        self.assertFalse(self.rec.is_recording)

    def test_recording_after_start(self):
        self.rec.start_recording()
        self.assertTrue(self.rec.is_recording)
        self.rec.stop_recording()

    def test_not_recording_after_stop(self):
        self.rec.start_recording()
        self.rec.stop_recording()
        self.assertFalse(self.rec.is_recording)

    def test_stop_returns_event_list(self):
        self.rec.start_recording()
        self.rec.record_event("go")
        events = self.rec.stop_recording()
        self.assertEqual(len(events), 1)

    def test_events_cleared_on_start(self):
        self.rec.start_recording()
        self.rec.record_event("go")
        self.rec.stop_recording()

        self.rec.start_recording()
        events = self.rec.stop_recording()
        self.assertEqual(len(events), 0)

    def test_event_not_stored_when_not_recording(self):
        self.rec.record_event("go")
        self.assertEqual(len(self.rec.events), 0)

    def test_events_property_returns_copy(self):
        self.rec.start_recording()
        self.rec.record_event("go")
        ev = self.rec.events
        ev.append(ExecutionEvent("custom"))  # mutate copy
        self.assertEqual(len(self.rec.events), 1)  # original unchanged
        self.rec.stop_recording()


# ---------------------------------------------------------------------------
# SequenceRecorder – event capture
# ---------------------------------------------------------------------------

class TestSequenceRecorderEvents(unittest.TestCase):

    def setUp(self):
        self.rec = SequenceRecorder(session_name="events_session")
        self.rec.start_recording()

    def tearDown(self):
        if self.rec.is_recording:
            self.rec.stop_recording()

    def test_record_go(self):
        e = self.rec.record_go()
        self.assertEqual(e.event_type, "go")

    def test_record_halt(self):
        e = self.rec.record_halt("TestFn")
        self.assertEqual(e.event_type, "halt")
        self.assertEqual(e.symbol, "TestFn")

    def test_record_reset(self):
        e = self.rec.record_reset()
        self.assertEqual(e.event_type, "reset")

    def test_record_breakpoint_set(self):
        e = self.rec.record_breakpoint_set("TestCanInit")
        self.assertEqual(e.event_type, "breakpoint_set")
        self.assertEqual(e.symbol, "TestCanInit")

    def test_record_breakpoint_cleared(self):
        e = self.rec.record_breakpoint_cleared("TestCanInit")
        self.assertEqual(e.event_type, "breakpoint_cleared")

    def test_record_variable_read(self):
        e = self.rec.record_variable_read("g_Status", 1)
        self.assertEqual(e.event_type, "variable_read")
        self.assertEqual(e.symbol, "g_Status")
        self.assertEqual(e.value, 1)

    def test_record_variable_write(self):
        e = self.rec.record_variable_write("g_Flag", 0xFF)
        self.assertEqual(e.event_type, "variable_write")
        self.assertEqual(e.value, 0xFF)

    def test_record_capl_result_pass(self):
        e = self.rec.record_capl_result("TC_001", "PASS", "Module_CAN")
        self.assertEqual(e.event_type, "capl_result")
        self.assertEqual(e.symbol, "TC_001")
        self.assertEqual(e.value, "PASS")
        self.assertEqual(e.metadata["module"], "Module_CAN")

    def test_record_capl_result_fail(self):
        e = self.rec.record_capl_result("TC_002", "FAIL")
        self.assertEqual(e.event_type, "capl_result")
        self.assertEqual(e.value, "FAIL")

    def test_unknown_event_type_stored_as_custom(self):
        e = self.rec.record_event("totally_unknown_type")
        self.assertEqual(e.event_type, "custom")

    def test_get_events_by_type(self):
        self.rec.record_go()
        self.rec.record_go()
        self.rec.record_reset()
        goes = self.rec.get_events_by_type("go")
        self.assertEqual(len(goes), 2)

    def test_get_capl_failures_excludes_pass(self):
        self.rec.record_capl_result("TC_001", "PASS")
        self.rec.record_capl_result("TC_002", "FAIL")
        self.rec.record_capl_result("TC_003", "ERROR")
        failures = self.rec.get_capl_failures()
        self.assertEqual(len(failures), 2)
        names = {e.symbol for e in failures}
        self.assertIn("TC_002", names)
        self.assertIn("TC_003", names)

    def test_get_capl_failures_excludes_none(self):
        self.rec.record_capl_result("TC_001", "NONE")
        self.rec.record_capl_result("TC_002", "NOTRUN")
        self.assertEqual(len(self.rec.get_capl_failures()), 0)


# ---------------------------------------------------------------------------
# SequenceRecorder – JSON export
# ---------------------------------------------------------------------------

class TestSequenceRecorderJsonExport(unittest.TestCase):

    def _record_simple_sequence(self) -> SequenceRecorder:
        rec = SequenceRecorder(session_name="export_seq")
        rec.start_recording()
        rec.record_breakpoint_set("TestCanInit")
        rec.record_variable_write("g_Timeout", 500)
        rec.record_go()
        rec.record_halt("TestCanInit")
        rec.record_variable_read("g_Status", 1)
        rec.record_capl_result("TC_001", "PASS", "Module_CAN")
        rec.stop_recording()
        return rec

    def test_export_test_cases_json_creates_file(self):
        rec = self._record_simple_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_test_cases_json(output_dir=tmpdir)
            self.assertTrue(os.path.isfile(path))

    def test_export_test_cases_json_valid_json(self):
        rec = self._record_simple_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_test_cases_json(output_dir=tmpdir)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        self.assertIn("test_cases", data)
        self.assertIsInstance(data["test_cases"], list)

    def test_export_test_cases_json_nonempty(self):
        rec = self._record_simple_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_test_cases_json(output_dir=tmpdir)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        self.assertGreater(len(data["test_cases"]), 0)

    def test_export_test_cases_json_entries_have_name(self):
        rec = self._record_simple_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_test_cases_json(output_dir=tmpdir)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        for tc in data["test_cases"]:
            self.assertIn("name", tc)
            self.assertIsInstance(tc["name"], str)

    def test_export_test_cases_json_entries_have_enabled_flag(self):
        rec = self._record_simple_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_test_cases_json(output_dir=tmpdir)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        for tc in data["test_cases"]:
            self.assertIn("enabled", tc)

    def test_export_events_json_creates_file(self):
        rec = self._record_simple_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_events_json(output_dir=tmpdir)
            self.assertTrue(os.path.isfile(path))

    def test_export_events_json_contains_events(self):
        rec = self._record_simple_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_events_json(output_dir=tmpdir)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        self.assertIn("events", data)
        self.assertGreater(len(data["events"]), 0)

    def test_export_events_json_session_name(self):
        rec = self._record_simple_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_events_json(output_dir=tmpdir)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        self.assertEqual(data["session"], "export_seq")

    def test_custom_filename(self):
        rec = self._record_simple_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_test_cases_json(
                output_dir=tmpdir, filename="custom_output.json"
            )
            self.assertTrue(path.endswith("custom_output.json"))
            self.assertTrue(os.path.isfile(path))


# ---------------------------------------------------------------------------
# SequenceRecorder – Python script export
# ---------------------------------------------------------------------------

class TestSequenceRecorderPythonExport(unittest.TestCase):

    def _record_sequence(self) -> SequenceRecorder:
        rec = SequenceRecorder(session_name="py_export_seq")
        rec.start_recording()
        rec.record_breakpoint_set("TestCanInit")
        rec.record_go()
        rec.record_halt("TestCanInit")
        rec.record_variable_read("g_Status", 1)
        rec.stop_recording()
        return rec

    def test_export_python_script_creates_file(self):
        rec = self._record_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_python_script(output_dir=tmpdir)
            self.assertTrue(os.path.isfile(path))

    def test_export_python_script_has_py_extension(self):
        rec = self._record_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_python_script(output_dir=tmpdir)
            self.assertTrue(path.endswith(".py"))

    def test_export_python_script_contains_unittest(self):
        rec = self._record_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_python_script(output_dir=tmpdir)
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
        self.assertIn("unittest", content)

    def test_export_python_script_contains_session_name(self):
        rec = self._record_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_python_script(output_dir=tmpdir)
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
        self.assertIn("py_export_seq", content)

    def test_export_python_script_contains_framework_import(self):
        rec = self._record_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_python_script(output_dir=tmpdir)
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
        self.assertIn("GM_VIP_Automation_Framework", content)

    def test_export_python_script_contains_mock_flag(self):
        rec = self._record_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_python_script(output_dir=tmpdir)
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
        self.assertIn("MOCK", content)

    def test_export_python_script_breakpoint_in_output(self):
        rec = self._record_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_python_script(output_dir=tmpdir)
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
        self.assertIn("TestCanInit", content)

    def test_empty_recording_produces_valid_script(self):
        rec = SequenceRecorder(session_name="empty_seq")
        rec.start_recording()
        rec.stop_recording()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_python_script(output_dir=tmpdir)
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
        self.assertIn("unittest", content)


if __name__ == "__main__":
    unittest.main()
