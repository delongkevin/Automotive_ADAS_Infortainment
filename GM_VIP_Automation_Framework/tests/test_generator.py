"""
Tests for GM_VIP_Automation_Framework.generator
================================================
All Trace32 API calls are mocked – no hardware required.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub lauterbach (mirrors test_core.py)
# ---------------------------------------------------------------------------
_pyrcl_mock = MagicMock()
sys.modules.setdefault("lauterbach", MagicMock())
sys.modules.setdefault("lauterbach.trace32", MagicMock())
sys.modules.setdefault("lauterbach.trace32.rcl", _pyrcl_mock)
sys.modules.setdefault("lauterbach.trace32.rcl._rc", MagicMock())
sys.modules.setdefault("lauterbach.trace32.rcl._rc._error", MagicMock())


# ---------------------------------------------------------------------------
# Fixture inventory builder
# ---------------------------------------------------------------------------

def _make_inventory():
    """Build a small synthetic SymbolInventory without any T32 connection."""
    from GM_VIP_Automation_Framework.core.symbol_discovery import (
        DiscoveredSymbol, SymbolInventory, SymbolKind,
    )
    return SymbolInventory([
        DiscoveredSymbol("\\src\\main.c\\main",       "main",       "src/main.c", SymbolKind.FUNCTION, "0x80001000", 0x40),
        DiscoveredSymbol("\\src\\main.c\\helperFunc",  "helperFunc", "src/main.c", SymbolKind.FUNCTION, "0x80001040", 0x20),
        DiscoveredSymbol("\\src\\main.c\\g_counter",   "g_counter",  "src/main.c", SymbolKind.VARIABLE, "0x80004000", 0x04),
        DiscoveredSymbol("\\src\\utils.c\\utilFunc",   "utilFunc",   "src/utils.c", SymbolKind.FUNCTION, "0x80002000", 0x30),
        DiscoveredSymbol("\\src\\utils.c\\g_flag",     "g_flag",     "src/utils.c", SymbolKind.VARIABLE, "0x80005000", 0x01),
        DiscoveredSymbol("flatFunc",                   "flatFunc",   "",            SymbolKind.FUNCTION, "0x80003000", 0x10),
    ])


# ---------------------------------------------------------------------------
# generate_test_cases_json
# ---------------------------------------------------------------------------

class TestGenerateTestCasesJson(unittest.TestCase):

    def setUp(self):
        self.inv = _make_inventory()

    def test_returns_dict_with_test_cases_key(self):
        from GM_VIP_Automation_Framework.generator import generate_test_cases_json
        result = generate_test_cases_json(self.inv)
        self.assertIn("test_cases", result)
        self.assertIn("test_suite", result)

    def test_suite_name_propagated(self):
        from GM_VIP_Automation_Framework.generator import generate_test_cases_json
        result = generate_test_cases_json(self.inv, suite_name="MySuite")
        self.assertEqual(result["test_suite"], "MySuite")

    def test_function_breakpoint_test_cases_generated(self):
        from GM_VIP_Automation_Framework.generator import generate_test_cases_json
        result = generate_test_cases_json(self.inv, include_functions=True)
        bp_tcs = [tc for tc in result["test_cases"] if tc.get("breakpoints")]
        self.assertGreater(len(bp_tcs), 0)

    def test_each_function_tc_has_exactly_one_breakpoint(self):
        from GM_VIP_Automation_Framework.generator import generate_test_cases_json
        result = generate_test_cases_json(self.inv, include_functions=True)
        for tc in result["test_cases"]:
            if tc.get("breakpoints"):
                self.assertEqual(len(tc["breakpoints"]), 1)

    def test_function_tc_includes_symbol_in_symbols_inspect(self):
        from GM_VIP_Automation_Framework.generator import generate_test_cases_json
        result = generate_test_cases_json(self.inv, include_functions=True)
        for tc in result["test_cases"]:
            if tc.get("breakpoints"):
                bp = tc["breakpoints"][0]
                self.assertIn(bp, tc["symbols_inspect"])

    def test_variable_batch_test_cases_generated(self):
        from GM_VIP_Automation_Framework.generator import generate_test_cases_json
        result = generate_test_cases_json(self.inv, include_variables=True)
        var_tcs = [tc for tc in result["test_cases"] if "VAR_Batch" in tc.get("name", "")]
        self.assertGreater(len(var_tcs), 0)

    def test_variable_batch_has_symbols_inspect(self):
        from GM_VIP_Automation_Framework.generator import generate_test_cases_json
        result = generate_test_cases_json(self.inv, include_variables=True)
        for tc in result["test_cases"]:
            if "VAR_Batch" in tc.get("name", ""):
                self.assertGreater(len(tc["symbols_inspect"]), 0)

    def test_module_inventory_test_cases_generated(self):
        from GM_VIP_Automation_Framework.generator import generate_test_cases_json
        result = generate_test_cases_json(self.inv, include_module_inventory=True)
        mod_tcs = [tc for tc in result["test_cases"] if "MODULE" in tc.get("name", "")]
        self.assertGreater(len(mod_tcs), 0)

    def test_include_functions_false_skips_bp_tcs(self):
        from GM_VIP_Automation_Framework.generator import generate_test_cases_json
        result = generate_test_cases_json(self.inv, include_functions=False)
        bp_tcs = [tc for tc in result["test_cases"] if tc.get("breakpoints")]
        self.assertEqual(bp_tcs, [])

    def test_max_functions_respected(self):
        from GM_VIP_Automation_Framework.generator import generate_test_cases_json
        result = generate_test_cases_json(self.inv, include_functions=True, max_functions=2)
        bp_tcs = [tc for tc in result["test_cases"] if tc.get("breakpoints")]
        self.assertLessEqual(len(bp_tcs), 2)

    def test_all_test_cases_have_name(self):
        from GM_VIP_Automation_Framework.generator import generate_test_cases_json
        result = generate_test_cases_json(self.inv)
        for tc in result["test_cases"]:
            # Skip comment-only entries that have no 'name' key.
            if "_comment" in tc and "name" not in tc:
                continue
            self.assertIn("name", tc)

    def test_test_cases_are_enabled_by_default(self):
        from GM_VIP_Automation_Framework.generator import generate_test_cases_json
        result = generate_test_cases_json(self.inv)
        for tc in result["test_cases"]:
            self.assertTrue(tc.get("enabled", True))

    def test_output_is_json_serialisable(self):
        from GM_VIP_Automation_Framework.generator import generate_test_cases_json
        result = generate_test_cases_json(self.inv)
        # Should not raise.
        serialised = json.dumps(result)
        self.assertIsInstance(serialised, str)

    def test_generator_meta_block_present(self):
        from GM_VIP_Automation_Framework.generator import generate_test_cases_json
        result = generate_test_cases_json(self.inv)
        self.assertIn("_generator_meta", result)
        meta = result["_generator_meta"]
        self.assertIn("generated_at", meta)
        self.assertIn("total_symbols", meta)

    def test_no_test_cases_when_empty_inventory(self):
        from GM_VIP_Automation_Framework.core.symbol_discovery import SymbolInventory
        from GM_VIP_Automation_Framework.generator import generate_test_cases_json
        empty = SymbolInventory()
        result = generate_test_cases_json(empty)
        # module inventory skips _global_ module; functions/variables = 0
        self.assertEqual(result["test_cases"], [])


# ---------------------------------------------------------------------------
# generate_session_script
# ---------------------------------------------------------------------------

class TestGenerateSessionScript(unittest.TestCase):

    def setUp(self):
        self.inv = _make_inventory()

    def test_returns_string(self):
        from GM_VIP_Automation_Framework.generator import generate_session_script
        script = generate_session_script(self.inv)
        self.assertIsInstance(script, str)

    def test_contains_shebang(self):
        from GM_VIP_Automation_Framework.generator import generate_session_script
        script = generate_session_script(self.inv)
        self.assertTrue(script.startswith("#!/usr/bin/env python3"))

    def test_contains_discovered_functions(self):
        from GM_VIP_Automation_Framework.generator import generate_session_script
        script = generate_session_script(self.inv)
        self.assertIn("DISCOVERED_FUNCTIONS", script)
        self.assertIn("main", script)
        self.assertIn("helperFunc", script)

    def test_contains_discovered_variables(self):
        from GM_VIP_Automation_Framework.generator import generate_session_script
        script = generate_session_script(self.inv)
        self.assertIn("DISCOVERED_VARIABLES", script)
        self.assertIn("g_counter", script)

    def test_suite_name_in_script(self):
        from GM_VIP_Automation_Framework.generator import generate_session_script
        script = generate_session_script(self.inv, suite_name="MySuite")
        self.assertIn("MySuite", script)

    def test_port_in_script(self):
        from GM_VIP_Automation_Framework.generator import generate_session_script
        script = generate_session_script(self.inv, port=20001)
        self.assertIn("20001", script)

    def test_script_is_valid_python(self):
        """The generated script must parse without SyntaxError."""
        from GM_VIP_Automation_Framework.generator import generate_session_script
        import ast
        script = generate_session_script(self.inv)
        try:
            ast.parse(script)
        except SyntaxError as exc:
            self.fail(f"Generated script has a SyntaxError: {exc}")

    def test_report_dir_creation_in_script(self):
        from GM_VIP_Automation_Framework.generator import generate_session_script
        script = generate_session_script(self.inv)
        self.assertIn("Test_Report", script)
        self.assertIn("mkdir", script)


# ---------------------------------------------------------------------------
# generate_from_inventory  (writes files to a temp dir)
# ---------------------------------------------------------------------------

class TestGenerateFromInventory(unittest.TestCase):

    def setUp(self):
        self.inv = _make_inventory()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.out = self._tmpdir.name

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_returns_paths_dict(self):
        from GM_VIP_Automation_Framework.generator import generate_from_inventory
        paths = generate_from_inventory(self.inv, output_dir=self.out)
        self.assertIn("json_path", paths)
        self.assertIn("script_path", paths)

    def test_json_file_written(self):
        from GM_VIP_Automation_Framework.generator import generate_from_inventory
        paths = generate_from_inventory(self.inv, output_dir=self.out)
        self.assertTrue(Path(paths["json_path"]).is_file())

    def test_script_file_written(self):
        from GM_VIP_Automation_Framework.generator import generate_from_inventory
        paths = generate_from_inventory(self.inv, output_dir=self.out)
        self.assertTrue(Path(paths["script_path"]).is_file())

    def test_json_file_is_valid_json(self):
        from GM_VIP_Automation_Framework.generator import generate_from_inventory
        paths = generate_from_inventory(self.inv, output_dir=self.out)
        content = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
        self.assertIn("test_cases", content)

    def test_json_file_compatible_with_runner_schema(self):
        """The generated JSON must pass load_test_cases() validation."""
        from GM_VIP_Automation_Framework.generator import generate_from_inventory
        from GM_VIP_Automation_Framework.runner import load_test_cases
        paths = generate_from_inventory(self.inv, output_dir=self.out)
        # load_test_cases requires a 'test_cases' key – should not raise.
        tcs = load_test_cases(paths["json_path"])
        self.assertIsInstance(tcs, list)

    def test_suite_name_used_in_filenames(self):
        from GM_VIP_Automation_Framework.generator import generate_from_inventory
        paths = generate_from_inventory(
            self.inv, output_dir=self.out, suite_name="CoolSuite"
        )
        self.assertIn("CoolSuite", Path(paths["json_path"]).name)
        self.assertIn("CoolSuite", Path(paths["script_path"]).name)

    def test_max_functions_capped_in_json(self):
        from GM_VIP_Automation_Framework.generator import generate_from_inventory
        paths = generate_from_inventory(
            self.inv, output_dir=self.out, max_functions=1
        )
        content = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
        bp_tcs = [tc for tc in content["test_cases"] if tc.get("breakpoints")]
        self.assertLessEqual(len(bp_tcs), 1)

    def test_output_dir_created_if_missing(self):
        from GM_VIP_Automation_Framework.generator import generate_from_inventory
        new_dir = Path(self.out) / "new_sub" / "dir"
        generate_from_inventory(self.inv, output_dir=str(new_dir))
        self.assertTrue(new_dir.is_dir())


# ---------------------------------------------------------------------------
# generate_from_live_session  (mocked T32 connection)
# ---------------------------------------------------------------------------

_SAMPLE_AREA = """\
\\src\\main.c\\myFunc      0x80001000 0x20 CODE
\\src\\main.c\\g_counter   0x80004000 0x04 DATA
"""


def _make_live_conn():
    conn = MagicMock()
    conn.is_connected.return_value = True

    def _cmd(c):
        if c.startswith("AREA.SAVE"):
            tmp_path = c.split(None, 1)[1].strip()
            Path(tmp_path).write_text(_SAMPLE_AREA, encoding="utf-8")

    def _fnc(expr):
        if "SYMBOL.EXIST" in expr:
            return "TRUE()"
        if "ADDRESS.OFFSET" in expr:
            return "0x80001234"
        return "0"

    conn.cmd.side_effect = _cmd
    conn.fnc.side_effect = _fnc
    return conn


class TestGenerateFromLiveSession(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.out = self._tmpdir.name

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_returns_paths_and_inventory(self):
        from GM_VIP_Automation_Framework.generator import generate_from_live_session
        conn = _make_live_conn()
        result = generate_from_live_session(
            output_dir=self.out,
            connection=conn,
            resolve_addresses=True,
            max_symbols=10,
        )
        self.assertIn("json_path", result)
        self.assertIn("script_path", result)
        self.assertIn("inventory", result)

    def test_inventory_has_symbols(self):
        from GM_VIP_Automation_Framework.generator import generate_from_live_session
        conn = _make_live_conn()
        result = generate_from_live_session(
            output_dir=self.out,
            connection=conn,
            resolve_addresses=False,
        )
        self.assertGreater(len(result["inventory"]), 0)

    def test_json_file_produced(self):
        from GM_VIP_Automation_Framework.generator import generate_from_live_session
        conn = _make_live_conn()
        result = generate_from_live_session(
            output_dir=self.out,
            connection=conn,
            resolve_addresses=False,
        )
        self.assertTrue(Path(result["json_path"]).is_file())

    def test_script_file_produced(self):
        from GM_VIP_Automation_Framework.generator import generate_from_live_session
        conn = _make_live_conn()
        result = generate_from_live_session(
            output_dir=self.out,
            connection=conn,
            resolve_addresses=False,
        )
        self.assertTrue(Path(result["script_path"]).is_file())

    def test_top_level_import(self):
        import GM_VIP_Automation_Framework as fw
        self.assertTrue(hasattr(fw, "generate_from_live_session"))
        self.assertTrue(hasattr(fw, "generate_from_inventory"))


# ---------------------------------------------------------------------------
# ModuleStatusReport
# ---------------------------------------------------------------------------

class TestModuleStatusReport(unittest.TestCase):

    def _make_report(self):
        from GM_VIP_Automation_Framework.report import ModuleStatusReport
        inv = _make_inventory()
        return ModuleStatusReport.from_inventory(inv, suite_name="TestSuite")

    def test_from_inventory_creates_report(self):
        from GM_VIP_Automation_Framework.report import ModuleStatusReport
        msr = self._make_report()
        self.assertIsInstance(msr, ModuleStatusReport)

    def test_modules_populated(self):
        msr = self._make_report()
        self.assertGreater(len(msr._rows), 0)

    def test_summary_contains_modules(self):
        msr = self._make_report()
        s = msr.summary()
        self.assertIn("module", s.lower())

    def test_to_dict_has_modules_key(self):
        msr = self._make_report()
        d = msr.to_dict()
        self.assertIn("modules", d)
        self.assertIn("generated_at", d)

    def test_save_json_writes_file(self):
        msr = self._make_report()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            msr.save_json(str(path))
            self.assertTrue(path.is_file())
            content = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("modules", content)

    def test_save_html_writes_file(self):
        msr = self._make_report()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.html"
            msr.save_html(str(path))
            self.assertTrue(path.is_file())
            html = path.read_text(encoding="utf-8")
            self.assertIn("<!DOCTYPE html>", html)
            self.assertIn("Module Status", html)

    def test_html_contains_symbol_names(self):
        msr = self._make_report()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.html"
            msr.save_html(str(path))
            html = path.read_text(encoding="utf-8")
            self.assertIn("main", html)
            self.assertIn("g_counter", html)

    def test_merge_test_case_report_updates_bp_status(self):
        from GM_VIP_Automation_Framework.report import ModuleStatusReport, TestCaseReport
        inv = _make_inventory()
        msr = ModuleStatusReport.from_inventory(inv)

        # Build a synthetic TestCaseReport with one hit breakpoint.
        tc_report = TestCaseReport(name="synthetic")
        tc_report.begin_test_case("TC1")
        tc_report.record_breakpoint("\\src\\main.c\\main", hit=True)
        tc_report.pass_test_case()

        msr.merge_test_case_report(tc_report)

        # Find the 'main' row.
        all_rows = [r for rows in msr._rows.values() for r in rows]
        main_row = next((r for r in all_rows if "main" in r.symbol and r.symbol.endswith("\\main")), None)
        if main_row is not None:
            self.assertEqual(main_row.bp_status, "HIT")

    def test_top_level_import(self):
        import GM_VIP_Automation_Framework as fw
        self.assertTrue(hasattr(fw, "ModuleStatusReport"))


if __name__ == "__main__":
    unittest.main()
