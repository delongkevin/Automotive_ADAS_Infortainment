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
        self.assertIn("cmm_entry_script", data)

    def test_load_from_json_cmm_entry_script(self):
        s = self._fresh_settings()
        data = {"cmm_entry_script": r"C:\scripts\startup.cmm"}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            tmp_path = f.name
        try:
            s.load_from_json(tmp_path)
            self.assertEqual(s.cmm_entry_script, r"C:\scripts\startup.cmm")
        finally:
            os.unlink(tmp_path)


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
            # show_pass=True: PASS entries are rendered in the body.
            r.save_html(tmp, show_pass=True)
            content = Path(tmp).read_text(encoding="utf-8")
            self.assertIn("<!DOCTYPE html>", content)
            self.assertIn("TC1", content)
            self.assertIn("PASS", content)
        finally:
            os.unlink(tmp)

    def test_save_html_omits_pass_by_default(self):
        """By default (show_pass=False) PASS entries are excluded from the detail section."""
        r = self._report()
        r.begin_test_case("TC1")
        r.pass_test_case()
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            tmp = f.name
        try:
            r.save_html(tmp)  # show_pass=False (default)
            content = Path(tmp).read_text(encoding="utf-8")
            self.assertIn("<!DOCTYPE html>", content)
            # Summary stats must still contain "PASS" count text.
            self.assertIn("PASS", content)
            # The all-passed banner should be shown (no failure detail blocks).
            self.assertIn("All tests passed", content)
            # TC1 should not appear inside a <details> block (PASS entries are omitted).
            self.assertNotIn("<details", content)
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


# ---------------------------------------------------------------------------
# runner.load_test_cases
# ---------------------------------------------------------------------------

class TestLoadTestCases(unittest.TestCase):
    """Tests for runner.load_test_cases (pure JSON parsing, no Trace32 needed)."""

    def _write_json(self, data: dict) -> str:
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(data, f)
        f.close()
        return f.name

    def test_load_basic(self):
        from GM_VIP_Automation_Framework.runner import load_test_cases
        path = self._write_json({
            "test_suite": "S",
            "test_cases": [
                {"name": "TC1", "enabled": True, "breakpoints": ["f"]},
            ],
        })
        try:
            tcs = load_test_cases(path)
            self.assertEqual(len(tcs), 1)
            self.assertEqual(tcs[0]["name"], "TC1")
        finally:
            os.unlink(path)

    def test_load_missing_raises(self):
        from GM_VIP_Automation_Framework.runner import load_test_cases
        with self.assertRaises(FileNotFoundError):
            load_test_cases("/no/such/file.json")

    def test_load_invalid_json_raises(self):
        from GM_VIP_Automation_Framework.runner import load_test_cases
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        f.write("{ bad json")
        f.close()
        try:
            with self.assertRaises(ValueError):
                load_test_cases(f.name)
        finally:
            os.unlink(f.name)

    def test_load_missing_test_cases_key_raises(self):
        from GM_VIP_Automation_Framework.runner import load_test_cases
        path = self._write_json({"test_suite": "S"})
        try:
            with self.assertRaises(ValueError):
                load_test_cases(path)
        finally:
            os.unlink(path)

    def test_template_is_valid(self):
        """The shipped test_cases.json template must be valid JSON."""
        from GM_VIP_Automation_Framework.runner import load_test_cases
        template = Path(__file__).parent.parent / "test_cases.json"
        self.assertTrue(template.is_file(), "test_cases.json template is missing")
        tcs = load_test_cases(str(template))
        # At least the two enabled test cases should be present.
        names = [tc.get("name") for tc in tcs if "name" in tc]
        self.assertIn("TC_Reset_BasicState", names)
        self.assertIn("TC_Breakpoint_VarCheck", names)


# ---------------------------------------------------------------------------
# runner.run_from_json (mocked Trace32)
# ---------------------------------------------------------------------------

class TestRunFromJson(unittest.TestCase):
    """Tests for runner.run_from_json using fully mocked Trace32 calls."""

    def _build_tc_json(self, test_cases: list, suite: str = "Suite") -> str:
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"test_suite": suite, "test_cases": test_cases}, f)
        f.close()
        return f.name

    def _mock_conn(self):
        """Return a mock T32Connection."""
        from unittest.mock import MagicMock
        conn = MagicMock()
        conn.is_connected.return_value = True
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)

        def _fnc(expr):
            if "STATE.RUN" in expr:
                return "FALSE()"
            if "SYMBOL.EXIST" in expr:
                return "TRUE()"
            if "ADDRESS.OFFSET" in expr:
                return "0x80001234"
            if "VAR.VALUE" in expr:
                return "42"
            if "P:R(PC)" in expr and "==" in expr:
                return "TRUE()"
            return "0"

        conn.fnc.side_effect = _fnc
        conn.cmd.return_value = None
        return conn

    def test_run_skips_disabled(self):
        from GM_VIP_Automation_Framework import runner as r
        tcs = [
            {"name": "TC_Skip", "enabled": False, "breakpoints": [],
             "variables_write": {}, "variables_check": {}, "symbols_inspect": []},
        ]
        path = self._build_tc_json(tcs)
        mock_conn = self._mock_conn()
        try:
            with (
                patch("GM_VIP_Automation_Framework.runner.t32.T32Connection",
                      return_value=mock_conn),
                patch("GM_VIP_Automation_Framework.runner.settings.load_from_json"),
            ):
                report = r.run_from_json(path, config_json_path="", auto_launch=False,
                                         report_json="/tmp/_r.json",
                                         report_html="/tmp/_r.html")
            self.assertEqual(report.total, 0)
        finally:
            os.unlink(path)

    def test_run_passes_enabled(self):
        from GM_VIP_Automation_Framework import runner as r
        tcs = [
            {"name": "TC1", "enabled": True, "reset_before": False,
             "breakpoints": [], "variables_write": {},
             "variables_check": {"myVar": {"expected": None}},
             "symbols_inspect": ["myFunc"]},
        ]
        path = self._build_tc_json(tcs)
        mock_conn = self._mock_conn()
        try:
            with (
                patch("GM_VIP_Automation_Framework.runner.t32.T32Connection",
                      return_value=mock_conn),
                patch("GM_VIP_Automation_Framework.runner.settings.load_from_json"),
            ):
                report = r.run_from_json(path, config_json_path="", auto_launch=False,
                                         report_json="/tmp/_r2.json",
                                         report_html="/tmp/_r2.html")
            self.assertEqual(report.total, 1)
            self.assertEqual(report.passed, 1)
        finally:
            os.unlink(path)

    def test_run_records_capl_reference(self):
        from GM_VIP_Automation_Framework import runner as r
        tcs = [
            {"name": "TC1", "enabled": True, "capl_reference": "MyFeature.can::TC1",
             "reset_before": False, "breakpoints": [],
             "variables_write": {}, "variables_check": {}, "symbols_inspect": []},
        ]
        path = self._build_tc_json(tcs)
        mock_conn = self._mock_conn()
        try:
            with (
                patch("GM_VIP_Automation_Framework.runner.t32.T32Connection",
                      return_value=mock_conn),
                patch("GM_VIP_Automation_Framework.runner.settings.load_from_json"),
            ):
                report = r.run_from_json(path, config_json_path="", auto_launch=False,
                                         report_json="/tmp/_r3.json",
                                         report_html="/tmp/_r3.html")
            result = report.results[0]
            self.assertIn("_capl_reference", result.variables)
            self.assertEqual(result.variables["_capl_reference"], "MyFeature.can::TC1")
        finally:
            os.unlink(path)

    def test_resilient_connect_uses_already_running(self):
        """run_from_json with resilient_connect=True should skip launch when try_connect succeeds."""
        from GM_VIP_Automation_Framework import runner as r
        tcs = [
            {"name": "TC1", "enabled": True, "reset_before": False,
             "breakpoints": [], "variables_write": {}, "variables_check": {},
             "symbols_inspect": []},
        ]
        path = self._build_tc_json(tcs)
        mock_conn = self._mock_conn()
        # Simulate try_connect() returning True (already-running T32 found).
        mock_conn.try_connect.return_value = True
        try:
            with (
                patch("GM_VIP_Automation_Framework.runner.t32.T32Connection",
                      return_value=mock_conn),
                patch("GM_VIP_Automation_Framework.runner.settings.load_from_json"),
            ):
                report = r.run_from_json(
                    path,
                    config_json_path="",
                    auto_launch=True,    # even with auto_launch=True, launch should be skipped
                    resilient_connect=True,
                    report_json="/tmp/_r4.json",
                    report_html="/tmp/_r4.html",
                )
            # launch() should NOT have been called because try_connect succeeded.
            mock_conn.launch.assert_not_called()
            self.assertEqual(report.total, 1)
            self.assertEqual(report.passed, 1)
        finally:
            os.unlink(path)

    def test_resilient_connect_launches_when_not_running(self):
        """run_from_json with resilient_connect=True should launch when try_connect fails."""
        from GM_VIP_Automation_Framework import runner as r
        tcs = [
            {"name": "TC1", "enabled": True, "reset_before": False,
             "breakpoints": [], "variables_write": {}, "variables_check": {},
             "symbols_inspect": []},
        ]
        path = self._build_tc_json(tcs)
        mock_conn = self._mock_conn()
        # try_connect() fails → framework should call launch() + connect().
        mock_conn.try_connect.return_value = False
        try:
            with (
                patch("GM_VIP_Automation_Framework.runner.t32.T32Connection",
                      return_value=mock_conn),
                patch("GM_VIP_Automation_Framework.runner.settings.load_from_json"),
            ):
                report = r.run_from_json(
                    path,
                    config_json_path="",
                    auto_launch=True,
                    resilient_connect=True,
                    report_json="/tmp/_r5.json",
                    report_html="/tmp/_r5.html",
                )
            mock_conn.launch.assert_called_once()
            self.assertEqual(report.total, 1)
        finally:
            os.unlink(path)

    def test_resilient_connect_no_auto_launch_raises(self):
        """run_from_json with resilient_connect=True and auto_launch=False should raise when not running."""
        from GM_VIP_Automation_Framework import runner as r
        from GM_VIP_Automation_Framework.utils.exceptions import T32ConnectionError
        tcs = [{"name": "TC1", "enabled": True, "breakpoints": [],
                "variables_write": {}, "variables_check": {}, "symbols_inspect": []}]
        path = self._build_tc_json(tcs)
        mock_conn = self._mock_conn()
        mock_conn.try_connect.return_value = False
        try:
            with (
                patch("GM_VIP_Automation_Framework.runner.t32.T32Connection",
                      return_value=mock_conn),
                patch("GM_VIP_Automation_Framework.runner.settings.load_from_json"),
            ):
                with self.assertRaises(T32ConnectionError):
                    r.run_from_json(
                        path,
                        config_json_path="",
                        auto_launch=False,
                        resilient_connect=True,
                        report_json="/tmp/_r6.json",
                        report_html="/tmp/_r6.html",
                    )
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# runner.discover_test_case_files
# ---------------------------------------------------------------------------

class TestDiscoverTestCaseFiles(unittest.TestCase):
    """Tests for runner.discover_test_case_files (pure filesystem, no Trace32)."""

    def test_finds_wildcard_json_files(self):
        from GM_VIP_Automation_Framework.runner import discover_test_case_files
        with tempfile.TemporaryDirectory() as tmp:
            # Create three *_test_cases.json files and one unrelated file.
            Path(tmp, "sanity_test_cases.json").write_text("{}")
            Path(tmp, "stress_test_cases.json").write_text("{}")
            Path(tmp, "powercycle_test_cases.json").write_text("{}")
            Path(tmp, "config.json").write_text("{}")          # should NOT match
            Path(tmp, "test_cases_old.json").write_text("{}")  # should NOT match

            found = discover_test_case_files(tmp)
            names = [f.name for f in found]
            self.assertIn("sanity_test_cases.json", names)
            self.assertIn("stress_test_cases.json", names)
            self.assertIn("powercycle_test_cases.json", names)
            self.assertNotIn("config.json", names)
            self.assertNotIn("test_cases_old.json", names)

    def test_returns_sorted_list(self):
        from GM_VIP_Automation_Framework.runner import discover_test_case_files
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "z_test_cases.json").write_text("{}")
            Path(tmp, "a_test_cases.json").write_text("{}")
            found = discover_test_case_files(tmp)
            names = [f.name for f in found]
            self.assertEqual(names, sorted(names))

    def test_empty_directory_returns_empty_list(self):
        from GM_VIP_Automation_Framework.runner import discover_test_case_files
        with tempfile.TemporaryDirectory() as tmp:
            found = discover_test_case_files(tmp)
            self.assertEqual(found, [])

    def test_sanity_json_is_discovered_in_framework_dir(self):
        """The shipped sanity_test_cases.json must be discoverable."""
        from GM_VIP_Automation_Framework.runner import discover_test_case_files
        framework_dir = Path(__file__).parent.parent
        found = discover_test_case_files(str(framework_dir))
        names = [f.name for f in found]
        self.assertIn("sanity_test_cases.json", names)


# ---------------------------------------------------------------------------
# runner.run_all_discovered
# ---------------------------------------------------------------------------

class TestRunAllDiscovered(unittest.TestCase):
    """Tests for runner.run_all_discovered (mocked Trace32)."""

    def _mock_conn(self):
        conn = MagicMock()
        conn.is_connected.return_value = True
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)

        def _fnc(expr):
            if "STATE.RUN" in expr:
                return "FALSE()"
            if "SYMBOL.EXIST" in expr:
                return "TRUE()"
            if "ADDRESS.OFFSET" in expr:
                return "0x80001234"
            if "VAR.VALUE" in expr:
                return "42"
            if "P:R(PC)" in expr and "==" in expr:
                return "TRUE()"
            return "0"

        conn.fnc.side_effect = _fnc
        conn.cmd.return_value = None
        return conn

    def test_no_json_files_raises(self):
        from GM_VIP_Automation_Framework.runner import run_all_discovered
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                run_all_discovered(tmp)

    def test_runs_all_found_suites(self):
        from GM_VIP_Automation_Framework import runner as r
        with tempfile.TemporaryDirectory() as tmp:
            # Create two minimal *_test_cases.json files.
            for label in ("alpha", "beta"):
                Path(tmp, f"{label}_test_cases.json").write_text(json.dumps({
                    "test_suite": label.capitalize(),
                    "test_cases": [
                        {"name": f"TC_{label}_1", "enabled": True,
                         "reset_before": False, "breakpoints": [],
                         "variables_write": {}, "variables_check": {},
                         "symbols_inspect": []},
                    ],
                }))
            mock_conn = self._mock_conn()
            with (
                patch("GM_VIP_Automation_Framework.runner.t32.T32Connection",
                      return_value=mock_conn),
                patch("GM_VIP_Automation_Framework.runner.settings.load_from_json"),
                patch("GM_VIP_Automation_Framework.report.TestCaseReport.save_json"),
                patch("GM_VIP_Automation_Framework.report.TestCaseReport.save_html"),
            ):
                results = r.run_all_discovered(tmp, config_json_path="")
            self.assertIn("alpha", results)
            self.assertIn("beta", results)
            self.assertEqual(results["alpha"].total, 1)
            self.assertEqual(results["beta"].total, 1)


# ---------------------------------------------------------------------------
# main._ensure_t32_running
# ---------------------------------------------------------------------------

class TestEnsureT32Running(unittest.TestCase):
    """Tests for main._ensure_t32_running (mocked T32Connection)."""

    def _mock_conn_cls(self, try_connect_returns: bool):
        """Return a mock T32Connection class whose try_connect returns a fixed value."""
        conn = MagicMock()
        conn.try_connect.return_value = try_connect_returns
        conn.disconnect.return_value = None
        cls = MagicMock(return_value=conn)
        return cls, conn

    def test_already_running_returns_immediately(self):
        """When T32 is already open, _ensure_t32_running should detect and return."""
        import sys as _sys
        # Ensure main module can be imported (repo root on path).
        framework_dir = Path(__file__).parent.parent
        repo_root = framework_dir.parent
        if str(repo_root) not in _sys.path:
            _sys.path.insert(0, str(repo_root))
        import importlib
        main_mod = importlib.import_module("GM_VIP_Automation_Framework.main")

        mock_cls, mock_conn = self._mock_conn_cls(try_connect_returns=True)
        with patch(
            "GM_VIP_Automation_Framework.core.connection.T32Connection", mock_cls,
        ):
            # Should not raise.
            main_mod._ensure_t32_running(auto_launch=False)
        mock_conn.disconnect.assert_called_once()
        mock_conn.launch.assert_not_called()

    def test_not_running_no_auto_launch_raises(self):
        """When T32 is not open and auto_launch=False, must raise T32ConnectionError."""
        import importlib
        main_mod = importlib.import_module("GM_VIP_Automation_Framework.main")
        from GM_VIP_Automation_Framework.utils.exceptions import T32ConnectionError

        mock_cls, mock_conn = self._mock_conn_cls(try_connect_returns=False)
        with patch(
            "GM_VIP_Automation_Framework.core.connection.T32Connection", mock_cls,
        ):
            with self.assertRaises(T32ConnectionError):
                main_mod._ensure_t32_running(auto_launch=False)
        mock_conn.launch.assert_not_called()

    def test_not_running_auto_launch_launches_and_waits(self):
        """When auto_launch=True and T32 is not open, must launch then poll."""
        import importlib
        main_mod = importlib.import_module("GM_VIP_Automation_Framework.main")
        from GM_VIP_Automation_Framework.config import settings

        # First call (initial probe) → False; second call (post-launch poll) → True.
        conn = MagicMock()
        conn.try_connect.side_effect = [False, True]
        conn.disconnect.return_value = None
        mock_cls = MagicMock(return_value=conn)

        with (
            patch("GM_VIP_Automation_Framework.core.connection.T32Connection", mock_cls),
            patch("GM_VIP_Automation_Framework.main._time.monotonic",
                  side_effect=[0.0, 0.5, settings.connect_max_wait_s + 1]),
            patch("GM_VIP_Automation_Framework.main._time.sleep"),
        ):
            main_mod._ensure_t32_running(auto_launch=True)

        conn.launch.assert_called_once()
        conn.disconnect.assert_called_once()


# ---------------------------------------------------------------------------
# main argument wiring: --mode and --auto-launch
# ---------------------------------------------------------------------------

class TestMainArgWiring(unittest.TestCase):
    """Smoke tests that verify argparse wiring in main.main()."""

    def _import_main(self):
        import importlib
        return importlib.import_module("GM_VIP_Automation_Framework.main")

    def test_mode_default_is_mock(self):
        main_mod = self._import_main()
        parser = main_mod._build_parser()
        args = parser.parse_args(["--suite", "test_sanity"])
        self.assertEqual(args.mode, "mock")

    def test_mode_live_parsed(self):
        main_mod = self._import_main()
        parser = main_mod._build_parser()
        args = parser.parse_args(["--suite", "test_sanity", "--mode", "live"])
        self.assertEqual(args.mode, "live")

    def test_auto_launch_default_false(self):
        main_mod = self._import_main()
        parser = main_mod._build_parser()
        args = parser.parse_args(["--json", "sanity"])
        self.assertFalse(args.auto_launch)

    def test_auto_launch_flag_sets_true(self):
        main_mod = self._import_main()
        parser = main_mod._build_parser()
        args = parser.parse_args(["--json", "sanity", "--auto-launch"])
        self.assertTrue(args.auto_launch)

    def test_cmm_script_default_none(self):
        main_mod = self._import_main()
        parser = main_mod._build_parser()
        args = parser.parse_args(["--json", "sanity"])
        self.assertIsNone(args.cmm_script)

    def test_cmm_script_parsed(self):
        main_mod = self._import_main()
        parser = main_mod._build_parser()
        args = parser.parse_args(["--json", "sanity", "--cmm", r"C:\my\script.cmm"])
        self.assertEqual(args.cmm_script, r"C:\my\script.cmm")

    def test_main_list_exits_cleanly(self):
        main_mod = self._import_main()
        # Should not raise.
        main_mod.main(["--list"])

    def test_main_no_args_exits_cleanly(self):
        main_mod = self._import_main()
        main_mod.main([])

    def test_main_suite_mock_runs_sanity(self):
        """--suite test_sanity --mode mock must complete all 72 tests."""
        main_mod = self._import_main()
        result = main_mod._run_python_suite(
            Path(__file__).parent / "test_sanity.py",
            mode="mock",
        )
        self.assertEqual(result.testsRun, 72)
        self.assertEqual(len(result.failures) + len(result.errors), 0)

    def test_runner_resilient_connect_prints_status(self):
        """run_from_json with resilient_connect=True should print detection status."""
        import io
        from GM_VIP_Automation_Framework import runner as r

        tcs = [{"name": "TC1", "enabled": True, "reset_before": False,
                "breakpoints": [], "variables_write": {},
                "variables_check": {}, "symbols_inspect": []}]
        path = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False
        )
        json.dump({"test_suite": "S", "test_cases": tcs}, path)
        path.close()

        conn = MagicMock()
        conn.is_connected.return_value = True
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)
        conn.try_connect.return_value = True  # T32 is "already running"

        def _fnc(expr):
            if "STATE.RUN" in expr:
                return "FALSE()"
            if "SYMBOL.EXIST" in expr:
                return "TRUE()"
            if "ADDRESS.OFFSET" in expr:
                return "0x80001234"
            if "VAR.VALUE" in expr:
                return "42"
            return "0"

        conn.fnc.side_effect = _fnc
        conn.cmd.return_value = None

        captured = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            report_json = os.path.join(tmp, "rw.json")
            report_html = os.path.join(tmp, "rw.html")
            try:
                with (
                    patch("GM_VIP_Automation_Framework.runner.t32.T32Connection",
                          return_value=conn),
                    patch("GM_VIP_Automation_Framework.runner.settings.load_from_json"),
                    patch("sys.stdout", captured),
                ):
                    r.run_from_json(
                        path.name,
                        config_json_path="",
                        resilient_connect=True,
                        report_json=report_json,
                        report_html=report_html,
                    )
            finally:
                os.unlink(path.name)

        output = captured.getvalue()
        self.assertIn("detected", output.lower())


if __name__ == "__main__":
    unittest.main()
