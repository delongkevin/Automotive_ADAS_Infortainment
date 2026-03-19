"""
GM VIP Automation Framework – Live Test-Case Generator
=======================================================
Converts a :class:`~core.symbol_discovery.SymbolInventory` (or a live
Trace32 session) into ready-to-run artefacts:

1. **``*_test_cases.json``** – a suite that the existing
   :func:`~runner.run_from_json` can execute directly.  One test case is
   generated per function (breakpoint + symbol-existence check) and one
   "inventory" test case per module (existence check for every symbol in
   that module).

2. **``*_session_script.py``** – a standalone Python script that, when run
   against a live Trace32, re-creates the entire test session: connects,
   discovers, exercises breakpoints, reads variables, and writes a report.

Public API
----------
- :func:`generate_from_live_session` – one-shot: discover + write JSON + script.
- :func:`generate_from_inventory` – write artefacts from a pre-built inventory.
- :func:`generate_test_cases_json` – return the JSON dict (without writing).
- :func:`generate_session_script` – return the Python script text (without writing).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

from .core.symbol_discovery import (
    DiscoveredSymbol,
    SymbolInventory,
    SymbolKind,
    discover_symbols,
)

__all__ = [
    "generate_from_live_session",
    "generate_from_inventory",
    "generate_test_cases_json",
    "generate_session_script",
]

# Maximum functions / variables per generated test case to keep suites
# manageable; callers can override via the public API parameters.
_DEFAULT_MAX_FUNCS_PER_TC: int = 1        # one breakpoint TC per function
_DEFAULT_MAX_VARS_PER_TC:  int = 10       # group variables into batch TCs


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _print(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[GEN {ts}] {msg}", file=sys.stderr, flush=True)


def _safe_tc_name(text: str) -> str:
    """Turn an arbitrary string into a safe JSON test-case name."""
    import re
    return re.sub(r"[^A-Za-z0-9_]", "_", text).strip("_") or "TC"


# ---------------------------------------------------------------------------
# JSON test-case builder
# ---------------------------------------------------------------------------

def generate_test_cases_json(
    inventory: SymbolInventory,
    suite_name: str = "AutoDiscovered",
    include_functions: bool = True,
    include_variables: bool = True,
    include_module_inventory: bool = True,
    max_functions: Optional[int] = None,
    max_variables_per_tc: int = _DEFAULT_MAX_VARS_PER_TC,
) -> dict:
    """Build a test-suite dict (JSON-serialisable) from *inventory*.

    The returned dict matches the schema understood by
    :func:`~runner.run_from_json`.  Each function gets its own test case
    with a ``breakpoints`` entry.  Variables are grouped into batch test
    cases (``symbols_inspect``).  One per-module inventory test case lists
    all symbols found in that module.

    Parameters
    ----------
    inventory:
        Pre-built :class:`~core.symbol_discovery.SymbolInventory`.
    suite_name:
        Value written to the ``test_suite`` key.
    include_functions:
        When ``True`` (default) emit one breakpoint test case per function.
    include_variables:
        When ``True`` (default) emit variable-inspect test cases.
    include_module_inventory:
        When ``True`` (default) emit one per-module symbol-inventory test
        case that lists all symbols in the module.
    max_functions:
        Maximum number of function test cases to emit.  ``None`` = no limit.
    max_variables_per_tc:
        Maximum symbols per variable-batch test case.

    Returns
    -------
    dict
        Top-level dict with keys ``test_suite`` and ``test_cases``.
    """
    test_cases = []

    # -- 1. Function breakpoint test cases -----------------------------------
    if include_functions:
        funcs = inventory.functions
        if max_functions is not None:
            funcs = funcs[:max_functions]

        for sym in funcs:
            tc_name = _safe_tc_name(
                f"TC_BP_{sym.module.replace('.', '_')}_{sym.short_name}"
                if sym.module else f"TC_BP_{sym.short_name}"
            )
            tc = {
                "_comment": (
                    f"Auto-generated: breakpoint on '{sym.name}' "
                    f"(module: {sym.module or 'global'})"
                ),
                "name": tc_name,
                "enabled": True,
                "reset_before": False,
                "go_before_check": False,
                "breakpoints": [sym.name],
                "variables_write": {},
                "variables_check": {},
                "symbols_inspect": [sym.name],
            }
            if sym.address:
                tc["_symbol_address"] = sym.address
            test_cases.append(tc)

    # -- 2. Variable inspect test cases (batched) ----------------------------
    if include_variables:
        variables = inventory.variables
        for batch_start in range(0, len(variables), max_variables_per_tc):
            batch = variables[batch_start: batch_start + max_variables_per_tc]
            batch_idx = batch_start // max_variables_per_tc + 1
            tc_name = _safe_tc_name(f"TC_VAR_Batch_{batch_idx:03d}")
            tc = {
                "_comment": f"Auto-generated: variable symbol inspection batch {batch_idx}",
                "name": tc_name,
                "enabled": True,
                "reset_before": False,
                "go_before_check": False,
                "breakpoints": [],
                "variables_write": {},
                "variables_check": {},
                "symbols_inspect": [v.name for v in batch],
            }
            test_cases.append(tc)

    # -- 3. Per-module inventory test cases ----------------------------------
    if include_module_inventory:
        for module in sorted(inventory.modules):
            if module == "_global_":
                continue
            syms_in_mod = inventory.by_module.get(module, [])
            if not syms_in_mod:
                continue
            safe_mod = _safe_tc_name(module.replace(".", "_"))
            tc_name = f"TC_MODULE_{safe_mod}"
            tc = {
                "_comment": (
                    f"Auto-generated: full symbol inventory for module '{module}' "
                    f"({len(syms_in_mod)} symbol(s))"
                ),
                "name": tc_name,
                "enabled": True,
                "reset_before": False,
                "go_before_check": False,
                "breakpoints": [],
                "variables_write": {},
                "variables_check": {},
                "symbols_inspect": [s.name for s in syms_in_mod],
            }
            test_cases.append(tc)

    return {
        "test_suite": suite_name,
        "_generator_meta": {
            "generated_at": inventory.session_timestamp,
            "total_symbols": len(inventory),
            "total_modules": len(inventory.modules),
            "total_functions": len(inventory.functions),
            "total_variables": len(inventory.variables),
        },
        "test_cases": test_cases,
    }


# ---------------------------------------------------------------------------
# Python session-script builder
# ---------------------------------------------------------------------------

def generate_session_script(
    inventory: SymbolInventory,
    suite_name: str = "AutoDiscovered",
    port: int = 20000,
    max_functions: int = 100,
    max_variables: int = 100,
) -> str:
    """Return a standalone Python script that exercises the inventory symbols.

    The generated script:
    - Connects to a running Trace32 on *port*.
    - Iterates over every discovered function, sets a breakpoint, issues GO,
      and checks that the ECU halts at the expected address.
    - Reads every discovered variable and logs its value.
    - Writes a JSON + HTML report under ``Test_Report/``.

    Parameters
    ----------
    inventory:
        Pre-built :class:`~core.symbol_discovery.SymbolInventory`.
    suite_name:
        Suite label used in report titles and file names.
    port:
        Trace32 RCL port.
    max_functions:
        Maximum number of function symbols to embed in the script (default
        100).  Large symbol tables would produce unwieldy scripts; increase
        as needed or split sessions across multiple generated scripts.
    max_variables:
        Maximum number of variable symbols to embed in the script (default
        100).

    Returns
    -------
    str
        Full Python source text; write to a ``.py`` file and run directly.
    """
    safe_name   = _safe_tc_name(suite_name)
    generated   = inventory.session_timestamp
    total_sym   = len(inventory)
    total_mod   = len(inventory.modules)
    total_fun   = len(inventory.functions)
    total_var   = len(inventory.variables)

    # Build indented item lists (4 spaces each) for the literal arrays.
    # Caps are applied so the generated file stays manageable; callers can
    # increase max_functions / max_variables as needed.
    func_items = "\n".join(
        f"    {json.dumps(sym.name)},"
        for sym in inventory.functions[:max_functions]
    ) or "    # (none discovered)"

    var_items = "\n".join(
        f"    {json.dumps(sym.name)},"
        for sym in inventory.variables[:max_variables]
    ) or "    # (none discovered)"

    # Build the script as a list of lines and join them; this avoids any
    # interaction between textwrap.dedent and multi-line interpolations.
    lines = [
        "#!/usr/bin/env python3",
        '"""',
        f"Auto-generated GM VIP Automation Framework session script",
        f"Suite  : {suite_name}",
        f"Created: {generated}",
        f"Symbols: {total_sym} total  |  {total_mod} module(s)",
        f"         {total_fun} function(s)  |  {total_var} variable(s)",
        "",
        "Usage",
        "-----",
        "1. Start Trace32 and load the ELF / symbols.",
        f"2. Run: python {safe_name}_session_script.py",
        "",
        f"The script connects to Trace32 on port {port}, verifies every symbol,",
        "sets breakpoints on functions, reads variable values, and writes a",
        "professional HTML/JSON report under Test_Report/.",
        '"""',
        "",
        "import sys",
        "from pathlib import Path",
        "",
        "# --- locate the framework (adjust as needed) ---",
        "_FRAMEWORK_ROOT = Path(__file__).resolve().parent",
        "if str(_FRAMEWORK_ROOT) not in sys.path:",
        "    sys.path.insert(0, str(_FRAMEWORK_ROOT))",
        "",
        "import GM_VIP_Automation_Framework as t32",
        "from GM_VIP_Automation_Framework.report import TestCaseReport",
        "from GM_VIP_Automation_Framework import core",
        "import datetime, os",
        "",
        "# --------------------------------------------------------------------------",
        "# Discovered symbols",
        "# --------------------------------------------------------------------------",
        "",
        "DISCOVERED_FUNCTIONS = [",
        func_items,
        "]",
        "",
        "DISCOVERED_VARIABLES = [",
        var_items,
        "]",
        "",
        "# --------------------------------------------------------------------------",
        "# Report output directory",
        "# --------------------------------------------------------------------------",
        "",
        '_NOW = datetime.datetime.now().strftime("%Y%m%d_%H%M")',
        '_REPORT_DIR = Path(__file__).parent / "Test_Report" / _NOW',
        "_REPORT_DIR.mkdir(parents=True, exist_ok=True)",
        "",
        "# --------------------------------------------------------------------------",
        "# Main test session",
        "# --------------------------------------------------------------------------",
        "",
        "def main() -> int:",
        f'    report = TestCaseReport(name="{suite_name}")',
        "",
        f"    conn = t32.T32Connection(port={port})",
        "    if not conn.try_connect():",
        f'        print("ERROR: Could not connect to Trace32 on port {port}.")',
        '        print("       Ensure Trace32 is running with the RCL API port open.")',
        "        return 1",
        "",
        "    with conn:",
        "        core.debugger.default_connection = conn",
        "",
        "        # -- Symbol existence check ----------------------------------",
        '        report.begin_test_case("TC_SymbolExistence")',
        "        try:",
        "            all_syms = DISCOVERED_FUNCTIONS + DISCOVERED_VARIABLES",
        "            fail_syms = []",
        "            for sym in all_syms:",
        "                exists = t32.symbol_exists(sym, connection=conn)",
        "                addr = \"\"",
        "                if exists:",
        "                    try:",
        "                        addr = t32.get_symbol_address(sym, connection=conn)",
        "                    except Exception:",
        '                        addr = "N/A"',
        "                report.record_symbol(sym, exists=exists, address=addr)",
        "                if not exists:",
        "                    fail_syms.append(sym)",
        "            if fail_syms:",
        "                report.fail_test_case(",
        '                    f"{len(fail_syms)} symbol(s) not found: "',
        '                    + ", ".join(fail_syms[:5])',
        "                )",
        "            else:",
        "                report.pass_test_case()",
        "        except Exception as exc:",
        "            report.fail_test_case(str(exc))",
        "",
        "        # -- Variable read -------------------------------------------",
        '        report.begin_test_case("TC_VariableRead")',
        "        try:",
        "            t32.wait_for_halt(connection=conn)",
        "            for var in DISCOVERED_VARIABLES:",
        "                try:",
        "                    val = t32.read_variable(var, connection=conn)",
        "                    report.record_variable(var, val)",
        "                except Exception as exc:",
        '                    report.record_variable(var, f"ERROR: {exc}")',
        "            report.pass_test_case()",
        "        except Exception as exc:",
        "            report.fail_test_case(str(exc))",
        "",
        "        # -- Function breakpoints ------------------------------------",
        "        for func in DISCOVERED_FUNCTIONS:",
        '            tc_name = "TC_BP_" + func.replace("\\\\", "__").replace("/", "__").strip("_")',
        "            report.begin_test_case(tc_name)",
        "            try:",
        "                t32.delete_all_breakpoints(connection=conn)",
        "                t32.set_breakpoint(func, connection=conn)",
        "                t32.go(connection=conn)",
        "                t32.check_halted_at(func, connection=conn)",
        "                report.record_breakpoint(func, hit=True)",
        "                t32.delete_all_breakpoints(connection=conn)",
        "                report.pass_test_case()",
        "            except Exception as exc:",
        "                report.record_breakpoint(func, hit=False)",
        "                report.fail_test_case(str(exc))",
        "                try:",
        "                    t32.delete_all_breakpoints(connection=conn)",
        "                except Exception:",
        "                    pass",
        "",
        "        core.debugger.default_connection = None",
        "",
        "    # -- Save reports ------------------------------------------------",
        f'    json_path = _REPORT_DIR / "{safe_name}_report.json"',
        f'    html_path = _REPORT_DIR / "{safe_name}_report.html"',
        "    report.save_json(str(json_path))",
        "    report.save_html(str(html_path))",
        "    print(report.summary())",
        '    print(f"JSON report → {json_path}")',
        '    print(f"HTML report → {html_path}")',
        "    return 0 if report.failed == 0 and report.errored == 0 else 1",
        "",
        "",
        'if __name__ == "__main__":',
        "    sys.exit(main())",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# High-level convenience wrappers
# ---------------------------------------------------------------------------

def generate_from_inventory(
    inventory: SymbolInventory,
    output_dir: str = ".",
    suite_name: str = "AutoDiscovered",
    port: int = 20000,
    include_functions: bool = True,
    include_variables: bool = True,
    include_module_inventory: bool = True,
    max_functions: Optional[int] = None,
) -> dict:
    """Write JSON test suite and Python session script from *inventory*.

    Parameters
    ----------
    inventory:
        Pre-built :class:`~core.symbol_discovery.SymbolInventory`.
    output_dir:
        Directory where artefacts are written.
    suite_name:
        Suite label (used for file names and report headers).
    port:
        Trace32 RCL port embedded into the session script.
    include_functions:
        Emit breakpoint test cases for discovered functions.
    include_variables:
        Emit variable-inspect test cases for discovered variables.
    include_module_inventory:
        Emit per-module inventory test cases.
    max_functions:
        Cap the number of function test cases (``None`` = no limit).

    Returns
    -------
    dict
        ``{"json_path": str, "script_path": str}`` with the written paths.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    safe = _safe_tc_name(suite_name)

    # 1. JSON test suite
    suite_dict = generate_test_cases_json(
        inventory,
        suite_name=suite_name,
        include_functions=include_functions,
        include_variables=include_variables,
        include_module_inventory=include_module_inventory,
        max_functions=max_functions,
    )
    json_path = out / f"{safe}_test_cases.json"
    json_path.write_text(
        json.dumps(suite_dict, indent=2) + "\n", encoding="utf-8"
    )
    _print(f"Wrote JSON test suite → {json_path}")

    # 2. Python session script
    script_text = generate_session_script(inventory, suite_name=suite_name, port=port)
    script_path = out / f"{safe}_session_script.py"
    script_path.write_text(script_text, encoding="utf-8")
    _print(f"Wrote session script  → {script_path}")

    return {"json_path": str(json_path), "script_path": str(script_path)}


def generate_from_live_session(
    output_dir: str = ".",
    suite_name: str = "AutoDiscovered",
    pattern: str = "*",
    connection=None,
    port: int = 20000,
    resolve_addresses: bool = True,
    max_symbols: int = 500,
    include_functions: bool = True,
    include_variables: bool = True,
    include_module_inventory: bool = True,
    max_functions: Optional[int] = None,
) -> dict:
    """Discover symbols from the live T32 session and write test artefacts.

    This is the main entry point for **one-shot** usage: it runs
    :func:`~core.symbol_discovery.discover_symbols`, then calls
    :func:`generate_from_inventory` to produce the JSON suite and Python
    script in a single call.

    Parameters
    ----------
    output_dir:
        Directory where artefacts are written.
    suite_name:
        Suite label.
    pattern:
        Trace32 wildcard passed to ``SYMBOL.LIST``.
    connection:
        Active :class:`~connection.T32Connection`.
    port:
        Trace32 RCL port embedded into the generated session script.
    resolve_addresses:
        Verify each symbol with ``SYMBOL.EXIST`` (recommended; slower).
    max_symbols:
        Maximum individually verified symbols.
    include_functions:
        Emit breakpoint test cases.
    include_variables:
        Emit variable-inspect test cases.
    include_module_inventory:
        Emit per-module inventory test cases.
    max_functions:
        Cap on function test cases.

    Returns
    -------
    dict
        ``{"json_path": str, "script_path": str, "inventory": SymbolInventory}``
    """
    _print("Discovering symbols from live Trace32 session …")
    inventory = discover_symbols(
        pattern=pattern,
        connection=connection,
        resolve_addresses=resolve_addresses,
        max_symbols=max_symbols,
    )
    _print(inventory.summary())

    paths = generate_from_inventory(
        inventory,
        output_dir=output_dir,
        suite_name=suite_name,
        port=port,
        include_functions=include_functions,
        include_variables=include_variables,
        include_module_inventory=include_module_inventory,
        max_functions=max_functions,
    )
    paths["inventory"] = inventory
    return paths
