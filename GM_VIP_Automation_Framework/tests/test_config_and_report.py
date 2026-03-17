"""
Tests for the JSON config loading and TestCaseReport functionality.
All tests are pure Python – no hardware or external dependencies required.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Stub out lauterbach.trace32.rcl (must happen before any framework import)
# ---------------------------------------------------------------------------
from unittest.mock import MagicMock

sys.modules.setdefault("lauterbach", MagicMock())
sys.modules.setdefault("lauterbach.trace32", MagicMock())
sys.modules.setdefault("lauterbach.trace32.rcl", MagicMock())
sys.modules.setdefault("lauterbach.trace32.rcl._rc", MagicMock())
sys.modules.setdefault("lauterbach.trace32.rcl._rc._error", MagicMock())


# ---------------------------------------------------------------------------
# config JSON load / save
# ---------------------------------------------------------------------------

class TestConfigJson(unittest.TestCase):
    """Tests for T32Settings.load_from_json / save_to_json."""

    def _fresh_settings(self):
        """Return a new T32Settings instance (avoids mutating the singleton)."""
        from GM_VIP_Automation_Framework.config import T32Settings
        return T32Settings()

    def test_load_from_json_updates_fields(self):
        s = self._fresh_settings()
        data = {
            "rcl_port": 30000,
            "rcl_protocol": "TCP",
            "halt_timeout_s": 99.0,
            "t32_exe_path": r"C:\custom\t32marm.exe",
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            tmp_path = f.name
        try:
            s.load_from_json(tmp_path)
            self.assertEqual(s.rcl_port, 30000)
            self.assertEqual(s.rcl_protocol, "TCP")
            self.assertAlmostEqual(s.halt_timeout_s, 99.0)
            self.assertEqual(s.t32_exe_path, r"C:\custom\t32marm.exe")
        finally:
            os.unlink(tmp_path)

    def test_load_from_json_ignores_unknown_keys(self):
        s = self._fresh_settings()
        data = {"unknown_key_xyz": "should be ignored", "rcl_port": 12345}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            tmp_path = f.name
        try:
            s.load_from_json(tmp_path)  # must not raise
            self.assertEqual(s.rcl_port, 12345)
        finally:
            os.unlink(tmp_path)

    def test_load_from_json_list_field(self):
        s = self._fresh_settings()
        dirs = ["C:\\T32", "C:\\custom"]
        data = {"t32_search_dirs": dirs}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            tmp_path = f.name
        try:
            s.load_from_json(tmp_path)
            self.assertEqual(s.t32_search_dirs, dirs)
        finally:
            os.unlink(tmp_path)

    def test_load_from_json_path_field(self):
        s = self._fresh_settings()
        data = {"temp_dir": "/tmp/my_t32_tmp"}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            tmp_path = f.name
        try:
            s.load_from_json(tmp_path)
            self.assertEqual(s.temp_dir, Path("/tmp/my_t32_tmp"))
        finally:
            os.unlink(tmp_path)

    def test_load_from_json_missing_file_raises(self):
        s = self._fresh_settings()
        with self.assertRaises(FileNotFoundError):
            s.load_from_json("/nonexistent/path/config.json")

    def test_load_from_json_invalid_json_raises(self):
        s = self._fresh_settings()
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{ not valid json }")
            tmp_path = f.name
        try:
            with self.assertRaises(ValueError):
                s.load_from_json(tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_save_to_json_round_trip(self):
        s = self._fresh_settings()
        s.rcl_port = 55555
        s.rcl_protocol = "TCP"
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            tmp_path = f.name
        try:
            s.save_to_json(tmp_path)
            s2 = self._fresh_settings()
            s2.load_from_json(tmp_path)
            self.assertEqual(s2.rcl_port, 55555)
            self.assertEqual(s2.rcl_protocol, "TCP")
        finally:
            os.unlink(tmp_path)

    def test_config_json_template_is_valid(self):
        """The shipped config.json template must be valid JSON."""
        template = Path(__file__).parent.parent / "config.json"
        self.assertTrue(template.is_file(), "config.json template is missing")
        data = json.loads(template.read_text(encoding="utf-8"))
        self.assertIn("rcl_port", data)
        self.assertIn("t32_exe_path", data)


# ---------------------------------------------------------------------------
# TestCaseReport
# ---------------------------------------------------------------------------

class TestTestCaseReport(unittest.TestCase):
    """Tests for the report.TestCaseReport class."""

    def _report(self, name="Suite"):
        from GM_VIP_Automation_Framework.report import TestCaseReport
        return TestCaseReport(name=name)

    def test_pass_increments_passed(self):
        r = self._report()
        r.begin_test_case("TC1")
        r.pass_test_case()
        self.assertEqual(r.passed, 1)
        self.assertEqual(r.failed, 0)
        self.assertEqual(r.total, 1)

    def test_fail_increments_failed(self):
        r = self._report()
        r.begin_test_case("TC1")
        r.fail_test_case("something went wrong")
        self.assertEqual(r.failed, 1)
        self.assertEqual(r.passed, 0)
        self.assertEqual(r.results[0].error_message, "something went wrong")

    def test_multiple_test_cases(self):
        r = self._report()
        r.begin_test_case("TC1")
        r.pass_test_case()
        r.begin_test_case("TC2")
        r.fail_test_case("oops")
        r.begin_test_case("TC3")
        r.pass_test_case()
        self.assertEqual(r.total, 3)
        self.assertEqual(r.passed, 2)
        self.assertEqual(r.failed, 1)

    def test_record_breakpoint(self):
        r = self._report()
        r.begin_test_case("TC1")
        r.record_breakpoint("myFunc", hit=True)
        r.pass_test_case()
        self.assertTrue(r.results[0].breakpoints["myFunc"])

    def test_record_variable(self):
        r = self._report()
        r.begin_test_case("TC1")
        r.record_variable("myVar", "42")
        r.pass_test_case()
        self.assertEqual(r.results[0].variables["myVar"], "42")

    def test_record_symbol(self):
        r = self._report()
        r.begin_test_case("TC1")
        r.record_symbol("myFunc", exists=True, address="0x80001234")
        r.pass_test_case()
        sym = r.results[0].symbols["myFunc"]
        self.assertTrue(sym["exists"])
        self.assertEqual(sym["address"], "0x80001234")

    def test_no_begin_raises(self):
        r = self._report()
        with self.assertRaises(RuntimeError):
            r.record_variable("x", "1")

    def test_begin_without_close_auto_errors(self):
        r = self._report()
        r.begin_test_case("TC1")
        # start a new one without closing TC1
        r.begin_test_case("TC2")
        r.pass_test_case()
        # TC1 should have been auto-closed as ERROR
        self.assertEqual(r.results[0].status, "ERROR")
        self.assertEqual(r.results[1].status, "PASS")

    def test_summary_string(self):
        r = self._report("MySuite")
        r.begin_test_case("TC1")
        r.pass_test_case()
        self.assertIn("MySuite", r.summary())
        self.assertIn("PASS", r.summary())

    def test_to_dict_structure(self):
        r = self._report("DS")
        r.begin_test_case("TC1")
        r.record_variable("v", "1")
        r.pass_test_case()
        d = r.to_dict()
        self.assertEqual(d["suite"], "DS")
        self.assertIn("test_cases", d)
        self.assertEqual(len(d["test_cases"]), 1)
        tc = d["test_cases"][0]
        self.assertEqual(tc["status"], "PASS")
        self.assertIn("v", tc["variables"])

    def test_save_json(self):
        r = self._report()
        r.begin_test_case("TC1")
        r.pass_test_case()
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            tmp = f.name
        try:
            r.save_json(tmp)
            data = json.loads(Path(tmp).read_text())
            self.assertEqual(data["passed"], 1)
        finally:
            os.unlink(tmp)

    def test_save_html(self):
        r = self._report()
        r.begin_test_case("TC1")
        r.pass_test_case()
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            tmp = f.name
        try:
            r.save_html(tmp)
            content = Path(tmp).read_text(encoding="utf-8")
            self.assertIn("<!DOCTYPE html>", content)
            self.assertIn("TC1", content)
            self.assertIn("PASS", content)
        finally:
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# TestCaseResult.to_dict
# ---------------------------------------------------------------------------

class TestTestCaseResult(unittest.TestCase):
    def test_to_dict_keys(self):
        from GM_VIP_Automation_Framework.report import TestCaseResult
        tc = TestCaseResult(name="MyTC")
        tc.breakpoints["f"] = True
        tc.variables["v"] = "99"
        tc.symbols["s"] = {"exists": True, "address": "0x0"}
        d = tc.to_dict()
        for key in ("name", "status", "error_message", "started_at", "breakpoints",
                    "variables", "symbols"):
            self.assertIn(key, d)


if __name__ == "__main__":
    unittest.main()
