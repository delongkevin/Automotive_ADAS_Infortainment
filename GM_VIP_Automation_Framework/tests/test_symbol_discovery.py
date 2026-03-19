"""
Tests for GM_VIP_Automation_Framework.core.symbol_discovery
============================================================
Runs in two modes controlled by the ``USE_LIVE_T32`` flag:

  USE_LIVE_T32 = False  (default)
      All 43 tests run with fully mocked Trace32 connections.  No hardware,
      no ``lauterbach.trace32.rcl`` install required.

  USE_LIVE_T32 = True
      Connects to a real running Trace32 instance, discovers all symbols,
      and generates two artefacts in the framework directory:

        • ``test_symbol_discovery_test_cases.json``  – runnable with
          ``python main.py --json test_symbol_discovery``
        • ``test_symbol_discovery_session_script.py`` – standalone script

      Additional live-mode tests verify that the inventory is populated and
      the JSON file was written correctly.

──────────────────────────────────────────────────────────────────────────────
HOW TO RUN
──────────────────────────────────────────────────────────────────────────────

Mock mode (default – no hardware needed)
-----------------------------------------
  python tests/test_symbol_discovery.py
  python main.py --suite test_symbol_discovery

Live mode (Trace32 required)
------------------------------
  Pre-requisites:
    1. pip install lauterbach.trace32.rcl
    2. Open Trace32 with your ELF loaded (RCL port open).
    3. Confirm config.t32:  RCL=NETASSIST  PACKLEN=1024  PORT=20000

  Run via main.py (recommended):
    python main.py --suite test_symbol_discovery --mode live
    python main.py --suite test_symbol_discovery --mode live --module "\\\\src\\\\main.c\\\\*"
    python main.py --suite test_symbol_discovery --mode live --pattern "g_*"

  Or directly:
    python tests/test_symbol_discovery.py live
    python tests/test_symbol_discovery.py live --module "\\\\src\\\\main.c\\\\*"
    python tests/test_symbol_discovery.py live --pattern "g_*"

  After running in live mode two files appear in the framework directory:
    test_symbol_discovery_test_cases.json   ← edit to match your symbols, then run
    test_symbol_discovery_session_script.py ← standalone Trace32 exercise script

──────────────────────────────────────────────────────────────────────────────
FILTERING (live mode)
──────────────────────────────────────────────────────────────────────────────

  --module MODULE_GLOB   Filter symbols to those whose module path contains
                         MODULE_GLOB.  Example: --module "main.c"
  --pattern SYM_GLOB     Trace32 SYMBOL.LIST wildcard.  Default is "*" (all).
                         Example: --pattern "g_*" for global variables only.
  --breakpoint SYMBOL    Set a one-shot breakpoint on SYMBOL after discovery
                         to confirm the function is reachable.

  These flags can also be supplied as environment variables:
    T32_DISC_MODULE   T32_DISC_PATTERN   T32_DISC_BREAKPOINT
"""

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

# ---------------------------------------------------------------------------
# Path bootstrap (runnable from any working directory)
# ---------------------------------------------------------------------------
_HERE      = os.path.dirname(os.path.abspath(__file__))          # .../tests/
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))    # <repo_root>
_FW_DIR    = os.path.abspath(os.path.join(_HERE, ".."))          # GM_VIP_Automation_Framework/
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _print(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[DSC {ts}] {msg}", file=sys.stderr, flush=True)


# ============================================================================
# CONNECTION MODE
# ============================================================================
USE_LIVE_T32     = False   # ← flip or pass "live" on the command line
T32_LIVE_PORT    = 20000
T32_LIVE_PACKLEN = 1024

# Symbol discovery filters (override via argv or env vars)
DISCOVER_PATTERN    = os.environ.get("T32_DISC_PATTERN",    "*")
DISCOVER_MODULE     = os.environ.get("T32_DISC_MODULE",     "")
DISCOVER_BREAKPOINT = os.environ.get("T32_DISC_BREAKPOINT", "")

# ---------------------------------------------------------------------------
# Parse extra argv flags before unittest sees them:
#   live  (or True / 1 / yes)         → activate live mode
#   --pattern=X / --pattern X         → symbol glob
#   --module=X  / --module  X         → module filter
#   --breakpoint=X / --breakpoint X   → one-shot BP symbol
# ---------------------------------------------------------------------------
_LIVE_FLAGS = {"true", "1", "live", "yes"}
_consumed: list = []
_argv_remaining: list = []
_i = 1
while _i < len(sys.argv):
    _arg = sys.argv[_i]
    if _arg.lower() in _LIVE_FLAGS:
        USE_LIVE_T32 = True
        _consumed.append(_arg)
        _i += 1
    elif _arg.startswith("--pattern="):
        DISCOVER_PATTERN = _arg.split("=", 1)[1]
        _consumed.append(_arg)
        _i += 1
    elif _arg == "--pattern" and _i + 1 < len(sys.argv):
        DISCOVER_PATTERN = sys.argv[_i + 1]
        _consumed += [_arg, sys.argv[_i + 1]]
        _i += 2
    elif _arg.startswith("--module="):
        DISCOVER_MODULE = _arg.split("=", 1)[1]
        _consumed.append(_arg)
        _i += 1
    elif _arg == "--module" and _i + 1 < len(sys.argv):
        DISCOVER_MODULE = sys.argv[_i + 1]
        _consumed += [_arg, sys.argv[_i + 1]]
        _i += 2
    elif _arg.startswith("--breakpoint="):
        DISCOVER_BREAKPOINT = _arg.split("=", 1)[1]
        _consumed.append(_arg)
        _i += 1
    elif _arg == "--breakpoint" and _i + 1 < len(sys.argv):
        DISCOVER_BREAKPOINT = sys.argv[_i + 1]
        _consumed += [_arg, sys.argv[_i + 1]]
        _i += 2
    else:
        _argv_remaining.append(_arg)
        _i += 1
sys.argv = [sys.argv[0]] + _argv_remaining   # let unittest see only its own args

# ============================================================================
# Mode-specific setup
# ============================================================================
if not USE_LIVE_T32:
    # MOCK MODE – stub lauterbach so no real library is needed.
    _pyrcl_mock = MagicMock()
    sys.modules.setdefault("lauterbach", MagicMock())
    sys.modules.setdefault("lauterbach.trace32", MagicMock())
    sys.modules.setdefault("lauterbach.trace32.rcl", _pyrcl_mock)
    sys.modules.setdefault("lauterbach.trace32.rcl._rc", MagicMock())
    sys.modules.setdefault("lauterbach.trace32.rcl._rc._error", MagicMock())

_LIVE_CONN     = None   # real connection; set below in live mode
_LIVE_INVENTORY = None  # discovered SymbolInventory; set below in live mode
_LIVE_JSON_PATH = None  # path to the generated JSON; set below in live mode

if USE_LIVE_T32:
    from GM_VIP_Automation_Framework.core.connection import T32Connection as _T32Conn
    from GM_VIP_Automation_Framework.generator import generate_from_inventory

    _print(f"LIVE mode – connecting to Trace32 on port {T32_LIVE_PORT} …")
    _LIVE_CONN = _T32Conn(port=T32_LIVE_PORT, packlen=T32_LIVE_PACKLEN)
    _LIVE_CONN.connect()
    _print(f"Connected.  Discovering symbols (pattern={DISCOVER_PATTERN!r}) …")

    from GM_VIP_Automation_Framework.core.symbol_discovery import discover_symbols
    _LIVE_INVENTORY = discover_symbols(
        pattern=DISCOVER_PATTERN,
        connection=_LIVE_CONN,
        resolve_addresses=True,
    )
    _print(_LIVE_INVENTORY.summary())

    # Optionally filter by module
    if DISCOVER_MODULE:
        _print(f"Applying module filter: {DISCOVER_MODULE!r}")
        from GM_VIP_Automation_Framework.core.symbol_discovery import (
            DiscoveredSymbol, SymbolInventory,
        )
        _filtered = [
            s for s in _LIVE_INVENTORY
            if DISCOVER_MODULE.lower() in s.module.lower()
        ]
        _LIVE_INVENTORY = SymbolInventory(_filtered)
        _print(f"Filtered inventory: {_LIVE_INVENTORY.summary()}")

    # One-shot breakpoint verification (--breakpoint argument)
    if DISCOVER_BREAKPOINT:
        from GM_VIP_Automation_Framework.core import breakpoints as _bp_mod
        _print(f"Setting one-shot breakpoint on '{DISCOVER_BREAKPOINT}' …")
        try:
            _bp_mod.set_breakpoint(DISCOVER_BREAKPOINT, _LIVE_CONN)
            _print(f"Breakpoint set on '{DISCOVER_BREAKPOINT}'.")
        except Exception as _e:
            _print(f"WARNING: Could not set breakpoint on '{DISCOVER_BREAKPOINT}': {_e}")

    # Write test-case JSON and session script to TestScripts/ in the CWD
    # so the files always appear next to wherever the script was launched.
    _OUT_DIR = Path.cwd() / "TestScripts"
    _GEN_RESULT = generate_from_inventory(
        _LIVE_INVENTORY,
        output_dir=str(_OUT_DIR),
        suite_name="test_symbol_discovery",
        port=T32_LIVE_PORT,
    )
    _LIVE_JSON_PATH = _GEN_RESULT["json_path"]
    _LIVE_SCRIPT_PATH = _GEN_RESULT["script_path"]
    _print(f"Generated JSON  → {_LIVE_JSON_PATH}")
    _print(f"Generated script→ {_LIVE_SCRIPT_PATH}")
    _print(f"Run tests from JSON:  python main.py --json {_LIVE_JSON_PATH}")
    _print(f"Run standalone script: python {_LIVE_SCRIPT_PATH}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_SYMBOL_LIST = """\
; Symbol list generated by SYMBOL.LIST *
\\src\\main.c\\main         0x80001000 0x40 CODE
\\src\\main.c\\g_counter    0x80004000 0x04 DATA
\\src\\main.c\\helperFunc   0x80001040 0x20 CODE
\\src\\utils.c\\utilFunc    0x80002000 0x30 CODE
\\src\\utils.c\\g_flag      0x80005000 0x01 DATA
flatFunction               0x80003000 0x10 CODE
G_GLOBAL_VAR               0x80006000 0x04 DATA
"""

_SAMPLE_NO_TYPE = """\
; Symbol list (stripped binary – no type column)
main         0x80001000
g_counter    0x80004000
helperFunc   0x80001040
"""


def _make_conn(area_text: str = _SAMPLE_SYMBOL_LIST):
    """Return a mock T32Connection that simulates SYMBOL.LIST output."""
    conn = MagicMock()
    conn.is_connected.return_value = True

    # Both SYMBOL.LIST.SAVE (primary strategy) and AREA.SAVE (fallback) write
    # a temp file; simulate both by writing text ourselves.
    _saved_tmp = {}

    def _cmd(c):
        if c.startswith("SYMBOL.LIST.SAVE"):
            tmp_path = c.split(None, 1)[1].strip()
            import pathlib
            pathlib.Path(tmp_path).write_text(area_text, encoding="utf-8")
            _saved_tmp["path"] = tmp_path
        elif c.startswith("AREA.SAVE"):
            tmp_path = c.split(None, 1)[1].strip()
            import pathlib
            pathlib.Path(tmp_path).write_text(area_text, encoding="utf-8")
            _saved_tmp["path"] = tmp_path
        # All other commands are no-ops.

    def _fnc(expr):
        if "SYMBOL.EXIST" in expr:
            # Symbols that contain "missing" do not exist.
            return "FALSE()" if "missing" in expr.lower() else "TRUE()"
        if "ADDRESS.OFFSET" in expr:
            return "0x80001234"
        return "0"

    conn.cmd.side_effect = _cmd
    conn.fnc.side_effect = _fnc
    return conn


# ---------------------------------------------------------------------------
# SymbolKind
# ---------------------------------------------------------------------------

class TestSymbolKind(unittest.TestCase):

    def test_values(self):
        from GM_VIP_Automation_Framework.core.symbol_discovery import SymbolKind
        self.assertEqual(SymbolKind.FUNCTION.value, "FUNCTION")
        self.assertEqual(SymbolKind.VARIABLE.value, "VARIABLE")
        self.assertEqual(SymbolKind.MODULE.value,   "MODULE")
        self.assertEqual(SymbolKind.UNKNOWN.value,  "UNKNOWN")


# ---------------------------------------------------------------------------
# DiscoveredSymbol
# ---------------------------------------------------------------------------

class TestDiscoveredSymbol(unittest.TestCase):

    def test_to_dict(self):
        from GM_VIP_Automation_Framework.core.symbol_discovery import (
            DiscoveredSymbol, SymbolKind,
        )
        sym = DiscoveredSymbol(
            name="\\src\\main.c\\myFunc",
            short_name="myFunc",
            module="src\\main.c",
            kind=SymbolKind.FUNCTION,
            address="0x80001000",
            size=64,
            exists=True,
        )
        d = sym.to_dict()
        self.assertEqual(d["name"],       "\\src\\main.c\\myFunc")
        self.assertEqual(d["short_name"], "myFunc")
        self.assertEqual(d["module"],     "src\\main.c")
        self.assertEqual(d["kind"],       "FUNCTION")
        self.assertEqual(d["address"],    "0x80001000")
        self.assertEqual(d["size"],       64)
        self.assertTrue(d["exists"])

    def test_frozen(self):
        from GM_VIP_Automation_Framework.core.symbol_discovery import (
            DiscoveredSymbol,
        )
        sym = DiscoveredSymbol(name="myFunc")
        with self.assertRaises(Exception):
            sym.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# _parse_symbol_list  (unit tests for the parser directly)
# ---------------------------------------------------------------------------

class TestParseSymbolList(unittest.TestCase):

    def setUp(self):
        from GM_VIP_Automation_Framework.core import symbol_discovery as sd
        self.sd = sd

    def test_module_qualified_function(self):
        parsed = self.sd._parse_symbol_list(_SAMPLE_SYMBOL_LIST)
        names = [s.short_name for s in parsed]
        self.assertIn("main", names)
        self.assertIn("helperFunc", names)

    def test_module_qualified_variable(self):
        parsed = self.sd._parse_symbol_list(_SAMPLE_SYMBOL_LIST)
        vars_ = [s for s in parsed if s.kind == self.sd.SymbolKind.VARIABLE]
        var_names = [s.short_name for s in vars_]
        self.assertIn("g_counter", var_names)
        self.assertIn("g_flag", var_names)

    def test_module_extraction(self):
        parsed = self.sd._parse_symbol_list(_SAMPLE_SYMBOL_LIST)
        main_sym = next(s for s in parsed if s.short_name == "main")
        self.assertIn("main.c", main_sym.module)

    def test_flat_symbol_has_empty_module(self):
        parsed = self.sd._parse_symbol_list(_SAMPLE_SYMBOL_LIST)
        flat = next(s for s in parsed if s.short_name == "flatFunction")
        self.assertEqual(flat.module, "")

    def test_no_type_column_heuristic(self):
        """When no section-kind column is present the name heuristic kicks in."""
        parsed = self.sd._parse_symbol_list(_SAMPLE_NO_TYPE)
        by_name = {s.short_name: s for s in parsed}
        # g_counter starts with g_ → VARIABLE heuristic
        self.assertEqual(by_name["g_counter"].kind, self.sd.SymbolKind.VARIABLE)
        # main → FUNCTION heuristic (default)
        self.assertEqual(by_name["main"].kind, self.sd.SymbolKind.FUNCTION)

    def test_global_caps_variable_heuristic(self):
        parsed = self.sd._parse_symbol_list(_SAMPLE_SYMBOL_LIST)
        by_name = {s.short_name: s for s in parsed}
        self.assertEqual(by_name["G_GLOBAL_VAR"].kind, self.sd.SymbolKind.VARIABLE)

    def test_duplicate_symbols_skipped(self):
        doubled = _SAMPLE_SYMBOL_LIST + _SAMPLE_SYMBOL_LIST
        parsed = self.sd._parse_symbol_list(doubled)
        names = [s.short_name for s in parsed]
        self.assertEqual(len(names), len(set(names)))

    def test_comment_lines_ignored(self):
        text = "; this is a comment\n// another comment\n"
        parsed = self.sd._parse_symbol_list(text)
        self.assertEqual(parsed, [])

    def test_empty_input(self):
        parsed = self.sd._parse_symbol_list("")
        self.assertEqual(parsed, [])


# ---------------------------------------------------------------------------
# SymbolInventory
# ---------------------------------------------------------------------------

class TestSymbolInventory(unittest.TestCase):

    def _make_inventory(self):
        from GM_VIP_Automation_Framework.core.symbol_discovery import (
            DiscoveredSymbol, SymbolInventory, SymbolKind,
        )
        syms = [
            DiscoveredSymbol("\\a.c\\funcA", "funcA", "a.c", SymbolKind.FUNCTION, "0x100", 0x20),
            DiscoveredSymbol("\\a.c\\varA",  "varA",  "a.c", SymbolKind.VARIABLE, "0x200", 0x04),
            DiscoveredSymbol("\\b.c\\funcB", "funcB", "b.c", SymbolKind.FUNCTION, "0x300", 0x10),
        ]
        return SymbolInventory(syms)

    def test_modules(self):
        inv = self._make_inventory()
        self.assertIn("a.c", inv.modules)
        self.assertIn("b.c", inv.modules)

    def test_functions(self):
        inv = self._make_inventory()
        self.assertEqual(len(inv.functions), 2)

    def test_variables(self):
        inv = self._make_inventory()
        self.assertEqual(len(inv.variables), 1)

    def test_functions_in(self):
        inv = self._make_inventory()
        self.assertEqual(len(inv.functions_in("a.c")), 1)
        self.assertEqual(inv.functions_in("a.c")[0].short_name, "funcA")

    def test_variables_in(self):
        inv = self._make_inventory()
        self.assertEqual(len(inv.variables_in("a.c")), 1)

    def test_len(self):
        inv = self._make_inventory()
        self.assertEqual(len(inv), 3)

    def test_iter(self):
        inv = self._make_inventory()
        self.assertEqual(len(list(inv)), 3)

    def test_summary_format(self):
        inv = self._make_inventory()
        s = inv.summary()
        self.assertIn("module", s.lower())
        self.assertIn("function", s.lower())
        self.assertIn("variable", s.lower())

    def test_to_dict_keys(self):
        inv = self._make_inventory()
        d = inv.to_dict()
        self.assertIn("session_timestamp", d)
        self.assertIn("total_symbols", d)
        self.assertIn("symbols", d)
        self.assertEqual(d["total_functions"], 2)
        self.assertEqual(d["total_variables"], 1)

    def test_empty_inventory(self):
        from GM_VIP_Automation_Framework.core.symbol_discovery import SymbolInventory
        inv = SymbolInventory()
        self.assertEqual(len(inv), 0)
        self.assertEqual(inv.modules, [])


# ---------------------------------------------------------------------------
# _classify_kind
# ---------------------------------------------------------------------------

class TestClassifyKind(unittest.TestCase):

    def setUp(self):
        from GM_VIP_Automation_Framework.core import symbol_discovery as sd
        self.classify = sd._classify_kind
        self.SymbolKind = sd.SymbolKind

    def test_code_column(self):
        self.assertEqual(self.classify("foo", "CODE"), self.SymbolKind.FUNCTION)

    def test_proc_column(self):
        self.assertEqual(self.classify("foo", "PROC"), self.SymbolKind.FUNCTION)

    def test_data_column(self):
        self.assertEqual(self.classify("foo", "DATA"), self.SymbolKind.VARIABLE)

    def test_bss_column(self):
        self.assertEqual(self.classify("foo", "BSS"), self.SymbolKind.VARIABLE)

    def test_g_prefix_heuristic(self):
        self.assertEqual(self.classify("g_myVar", ""), self.SymbolKind.VARIABLE)

    def test_s_prefix_heuristic(self):
        self.assertEqual(self.classify("s_count", ""), self.SymbolKind.VARIABLE)

    def test_allcaps_heuristic(self):
        self.assertEqual(self.classify("MY_GLOBAL", ""), self.SymbolKind.VARIABLE)

    def test_default_function(self):
        self.assertEqual(self.classify("myFunc", ""), self.SymbolKind.FUNCTION)


# ---------------------------------------------------------------------------
# discover_symbols (integration over mock conn)
# ---------------------------------------------------------------------------

class TestDiscoverSymbols(unittest.TestCase):

    def test_returns_inventory(self):
        from GM_VIP_Automation_Framework.core.symbol_discovery import (
            discover_symbols, SymbolInventory,
        )
        conn = _make_conn()
        inv = discover_symbols(pattern="*", connection=conn, resolve_addresses=False)
        self.assertIsInstance(inv, SymbolInventory)

    def test_discovers_functions(self):
        from GM_VIP_Automation_Framework.core.symbol_discovery import discover_symbols
        conn = _make_conn()
        inv = discover_symbols(connection=conn, resolve_addresses=False)
        self.assertGreater(len(inv.functions), 0)

    def test_discovers_variables(self):
        from GM_VIP_Automation_Framework.core.symbol_discovery import discover_symbols
        conn = _make_conn()
        inv = discover_symbols(connection=conn, resolve_addresses=False)
        self.assertGreater(len(inv.variables), 0)

    def test_modules_extracted(self):
        from GM_VIP_Automation_Framework.core.symbol_discovery import discover_symbols
        conn = _make_conn()
        inv = discover_symbols(connection=conn, resolve_addresses=False)
        mods = inv.modules
        self.assertTrue(any("main.c" in m for m in mods))

    def test_resolve_addresses_calls_symbol_exist(self):
        from GM_VIP_Automation_Framework.core.symbol_discovery import discover_symbols
        conn = _make_conn()
        discover_symbols(connection=conn, resolve_addresses=True, max_symbols=5)
        calls_str = [str(c) for c in conn.fnc.call_args_list]
        self.assertTrue(any("SYMBOL.EXIST" in c for c in calls_str))

    def test_empty_area_returns_empty_inventory(self):
        from GM_VIP_Automation_Framework.core.symbol_discovery import discover_symbols
        conn = _make_conn(area_text="")
        inv = discover_symbols(connection=conn, resolve_addresses=False)
        self.assertEqual(len(inv), 0)

    def test_discover_modules_helper(self):
        from GM_VIP_Automation_Framework.core.symbol_discovery import discover_modules
        conn = _make_conn()
        mods = discover_modules(connection=conn)
        self.assertIsInstance(mods, list)
        self.assertTrue(any("main.c" in m for m in mods))

    def test_discover_functions_helper(self):
        from GM_VIP_Automation_Framework.core.symbol_discovery import (
            discover_functions, SymbolKind,
        )
        conn = _make_conn()
        funcs = discover_functions(connection=conn)
        self.assertTrue(all(f.kind == SymbolKind.FUNCTION for f in funcs))

    def test_discover_variables_helper(self):
        from GM_VIP_Automation_Framework.core.symbol_discovery import (
            discover_variables, SymbolKind,
        )
        conn = _make_conn()
        varis = discover_variables(connection=conn)
        self.assertTrue(all(v.kind == SymbolKind.VARIABLE for v in varis))

    def test_cmd_symbol_list_save_or_area_clear_issued(self):
        """Verify that at least one capture strategy is attempted.

        The primary strategy issues ``SYMBOL.LIST.SAVE``; the fallback uses
        ``AREA`` + ``AREA.CLEAR``.  In mock mode the primary strategy succeeds,
        so only ``SYMBOL.LIST.SAVE`` is expected.  Either command proves that
        the discovery pipeline ran.
        """
        from GM_VIP_Automation_Framework.core.symbol_discovery import discover_symbols
        conn = _make_conn()
        discover_symbols(connection=conn, resolve_addresses=False)
        cmd_calls = [str(c) for c in conn.cmd.call_args_list]
        self.assertTrue(
            any("SYMBOL.LIST.SAVE" in c for c in cmd_calls)
            or any("AREA.CLEAR" in c for c in cmd_calls),
            "Expected SYMBOL.LIST.SAVE (primary) or AREA.CLEAR (fallback) to be called.",
        )

    def test_cmd_symbol_list_issued(self):
        from GM_VIP_Automation_Framework.core.symbol_discovery import discover_symbols
        conn = _make_conn()
        discover_symbols(connection=conn, resolve_addresses=False)
        cmd_calls = [str(c) for c in conn.cmd.call_args_list]
        self.assertTrue(any("SYMBOL.LIST" in c for c in cmd_calls))


# ---------------------------------------------------------------------------
# Public exports from the package
# ---------------------------------------------------------------------------

class TestPublicExports(unittest.TestCase):

    def test_top_level_imports(self):
        import GM_VIP_Automation_Framework as fw
        self.assertTrue(hasattr(fw, "discover_symbols"))
        self.assertTrue(hasattr(fw, "discover_modules"))
        self.assertTrue(hasattr(fw, "discover_functions"))
        self.assertTrue(hasattr(fw, "discover_variables"))
        self.assertTrue(hasattr(fw, "SymbolInventory"))
        self.assertTrue(hasattr(fw, "DiscoveredSymbol"))
        self.assertTrue(hasattr(fw, "SymbolKind"))

    def test_core_exports(self):
        from GM_VIP_Automation_Framework import core
        self.assertTrue(hasattr(core, "discover_symbols"))
        self.assertTrue(hasattr(core, "SymbolInventory"))


# ---------------------------------------------------------------------------
# Live-mode tests  (only executed when USE_LIVE_T32 = True)
# ---------------------------------------------------------------------------

if USE_LIVE_T32:

    class TestLiveDiscovery(unittest.TestCase):
        """Exercises real Trace32 discovery; requires USE_LIVE_T32 = True."""

        @classmethod
        def setUpClass(cls):
            # These are populated by the module-level setup above.
            cls.conn      = _LIVE_CONN
            cls.inventory = _LIVE_INVENTORY
            cls.json_path = Path(_LIVE_JSON_PATH) if _LIVE_JSON_PATH else None

        def test_connection_is_active(self):
            """T32Connection.is_connected() must return True after module setup."""
            self.assertTrue(self.conn.is_connected(),
                            "Trace32 connection dropped before tests started.")

        def test_inventory_not_empty(self):
            """At least one symbol must be discovered from the live session."""
            self.assertGreater(
                len(self.inventory), 0,
                "No symbols discovered. "
                "Check that the ELF is loaded in Trace32 and "
                f"the pattern {DISCOVER_PATTERN!r} matches your symbols.",
            )

        def test_functions_discovered(self):
            """At least one FUNCTION-kind symbol must be present."""
            from GM_VIP_Automation_Framework.core.symbol_discovery import SymbolKind
            funcs = [s for s in self.inventory if s.kind == SymbolKind.FUNCTION]
            self.assertGreater(
                len(funcs), 0,
                f"No functions found among {len(self.inventory)} discovered symbol(s). "
                "Verify ELF load and code-section symbols are visible.",
            )

        def test_modules_extracted(self):
            """Module list is populated (or empty for stripped binaries — both are valid)."""
            mods = self.inventory.modules
            self.assertIsInstance(mods, list, "modules must return a list")
            _print(f"Modules found ({len(mods)}): {mods}")

        def test_json_file_written(self):
            """The generated JSON must exist and parse correctly."""
            import json as _json
            self.assertIsNotNone(self.json_path,
                                 "JSON path not recorded (generator may have failed).")
            self.assertTrue(
                self.json_path.exists(),
                f"Expected generated JSON at {self.json_path} but file not found.",
            )
            with open(self.json_path, encoding="utf-8") as fh:
                data = _json.load(fh)
            self.assertIn("test_suite", data,
                          "Generated JSON is missing 'test_suite' key.")
            self.assertIn("test_cases", data,
                          "Generated JSON is missing 'test_cases' key.")
            _print(f"JSON contains {len(data['test_cases'])} test case(s).")

        def test_json_matches_inventory(self):
            """Number of generated breakpoint TCs must equal discovered functions."""
            import json as _json
            if not (self.json_path and self.json_path.exists()):
                self.skipTest("JSON file not available.")
            with open(self.json_path, encoding="utf-8") as fh:
                data = _json.load(fh)
            bp_tcs = [tc for tc in data["test_cases"]
                      if tc.get("breakpoints")]
            n_funcs = len(self.inventory.functions)
            _print(f"Functions in inventory: {n_funcs}, "
                   f"breakpoint TCs in JSON: {len(bp_tcs)}")
            # One TC per discovered function; must not exceed the function count.
            self.assertEqual(
                len(bp_tcs), n_funcs,
                f"Expected exactly {n_funcs} breakpoint TC(s) — one per function — "
                f"but found {len(bp_tcs)} in the generated JSON.",
            )

        def test_session_summary_printable(self):
            """summary() must return a non-empty string."""
            s = self.inventory.summary()
            self.assertIsInstance(s, str)
            self.assertGreater(len(s), 0)
            _print(s)

        def test_symbol_breakpoint_arg(self):
            """If --breakpoint was supplied, the symbol must exist in the inventory."""
            if not DISCOVER_BREAKPOINT:
                self.skipTest("No --breakpoint argument supplied.")
            names = [s.name for s in self.inventory] + \
                    [s.short_name for s in self.inventory]
            self.assertIn(
                DISCOVER_BREAKPOINT, names,
                f"--breakpoint symbol '{DISCOVER_BREAKPOINT}' not found in inventory. "
                "Ensure the symbol name matches exactly (case-sensitive).",
            )


if __name__ == "__main__":
    unittest.main()
