# GM VIP Automation Framework

A standalone Python framework for interacting with the **Lauterbach Trace32**
debugger in GM VIP (Vehicle Integration Platform) automation test environments.

This framework is the **Python-native replacement** for the CAPL-based T32
control and test-support libraries (`cT32.cin` / `tsT32.cin`) found in the
`GM_VIP_Automation` directory.  It provides the same logical operations
(breakpoints, variable read/write, register operations, symbol search, CMM
script execution) but:

- Uses only the official `lauterbach.trace32.rcl` Python library.
- Runs as a standalone Python package – no CANoe / DLL dependency.
- Is fully unit-testable without hardware via `unittest.mock`.
- Exposes a clean, documented public API with typed signatures.
- **Auto-discovers** all modules, functions, and variables from a live T32
  session and generates runnable test-case suites with zero manual editing.

> **Version 1.3.0** – adds live symbol auto-discovery (`core/symbol_discovery.py`),
> JSON test-case generator (`generator.py`), and the `ModuleStatusReport` HTML
> dashboard (`report.py`).

---

## Directory Structure

```
GM_VIP_Automation_Framework/
├── __init__.py            # Top-level package – re-exports entire public API
├── config.py              # Centralised T32Settings dataclass + singleton
├── config.json            # Editable configuration template
├── test_cases.json        # Editable test-cases template
├── generator.py           # Live-session test-case generator (NEW v1.3)
├── report.py              # TestCaseReport + ModuleStatusReport (HTML/JSON)
├── runner.py              # JSON-driven test runner (run_from_json, run_all_discovered)
├── html_report.py         # Pytest plugin: HTML report after each test session
├── requirements.txt       # Python runtime dependencies
├── README.md              # This file
│
├── core/
│   ├── __init__.py          # Re-exports all core functions
│   ├── connection.py        # T32Connection class, connect(), auto_detect_t32(), try_connect()
│   ├── debugger.py          # go(), break_execution(), reset_target(), step_over(), …
│   ├── breakpoints.py       # set_breakpoint(), check_halted_at(), …
│   ├── variables.py         # read_variable(), set_variable(), check_variable_until(), …
│   ├── registers.py         # read_register(), set_register(), check_register_bit(), …
│   ├── symbols.py           # reload_symbols(), symbol_exists(), get_symbol_address(), …
│   ├── symbol_discovery.py  # discover_symbols(), SymbolInventory, DiscoveredSymbol (NEW v1.3)
│   └── cmm.py               # run_cmm_command(), run_cmm_script(), check_cmm_script_result()
│
├── templates/
│   ├── connect_t32_running.py   # Connect to already-running T32 (no launch)
│   ├── connect_t32_launch.py    # Launch T32 from config.json paths
│   └── connect_with_cmm.py      # CMM-first: connect to running T32 or launch via *.cmm
│
├── utils/
│   ├── __init__.py
│   ├── exceptions.py      # T32FrameworkError hierarchy
│   ├── logger.py          # Coloured, rotating-file logger
│   └── retry.py           # @retry decorator, poll_until() helper
│
└── tests/
    ├── __init__.py
    ├── conftest.py                # Pytest plugin – mocks lauterbach library + HTML report
    ├── test_utils.py              # Tests for exceptions, logger, retry utilities
    ├── test_core.py               # Tests for all core modules (mocked hardware)
    ├── test_config_and_report.py  # Tests for config I/O and report generation
    ├── test_hardware.py           # Tests for CAN bus, CANoe, power supply (mock mode)
    ├── test_sanity.py             # Full end-to-end sanity suite (mock + live T32 toggle)
    ├── test_symbol_discovery.py   # Tests for symbol auto-discovery (NEW v1.3)
    └── test_generator.py          # Tests for test-case generator (NEW v1.3)
```

---

## Installation

```bash
# From the repository root
pip install -r GM_VIP_Automation_Framework/requirements.txt
```

The only runtime dependency is the official Lauterbach library:

```
lauterbach.trace32.rcl>=1.0.0
```

---

## Quick Start

### 1 – Configure Trace32 settings

```python
from GM_VIP_Automation_Framework.config import settings

settings.t32_exe_path    = r"C:\T32\bin\t32marm.exe"
settings.t32_config_path = r"C:\T32\config.t32"
settings.rcl_port        = 20000
settings.halt_timeout_s  = 20.0
```

All settings can also be provided via environment variables:

| Environment variable         | Default                                      | Description                                                   |
|------------------------------|----------------------------------------------|---------------------------------------------------------------|
| `T32_EXE_PATH`               | `C:\T32\bin\windows64\t32marm64.exe`         | Path to Trace32 executable (only needed when launching T32)   |
| `T32_CONFIG_PATH`            | `C:\T32\config.t32`                          | Path to Trace32 config file (only needed when launching T32)  |
| `T32_CMM_ENTRY_SCRIPT`       | *(empty – no startup script)*                | CMM startup script passed to T32 via `-s` when launching      |
| `T32_RCL_PORT`               | `20000`                                      | RCL socket port                                               |
| `T32_RCL_PROTOCOL`           | `UDP`                                        | RCL protocol (`UDP` or `TCP`)                                 |
| `T32_HALT_TIMEOUT_S`         | `20.0`                                       | Seconds to wait for ECU halt                                  |
| `T32_RUN_TIMEOUT_S`          | `3.0`                                        | Seconds to wait for ECU run                                   |
| `T32_BP_MAX_RETRIES`         | `10`                                         | BREAK.SET retry count                                         |
| `T32_BP_RETRY_INTERVAL_S`    | `0.5`                                        | Delay between BREAK.SET retries                               |
| `T32_SYMBOL_RELOAD_WAIT_S`   | `5.0`                                        | Wait after `SYMBOL.RELOAD`                                    |
| `T32_LOG_LEVEL`              | `DEBUG`                                      | Logger level                                                  |
| `T32_LOG_FILE`               | *(empty – stdout only)*                      | Log file path                                                 |

### 2 – Connect and run a basic test sequence

```python
import GM_VIP_Automation_Framework as t32
from GM_VIP_Automation_Framework import core

# --- Option A: context manager (auto-disconnect) ---
with t32.T32Connection(port=20000) as conn:
    core.debugger.default_connection = conn

    t32.reset_target()                      # SYStem.RESetTarget
    t32.delete_all_breakpoints()            # BREAK.DELETE /ALL
    t32.set_breakpoint("myFunction")        # BREAK.SET myFunction  (with retry)
    t32.go()                                # GO
    t32.check_halted_at("myFunction")       # EVAL P:R(PC)==myFunction

    value = t32.read_variable("myModule.myCounter")
    print(f"myCounter = {value}")

    t32.set_variable("myModule.myFlag", 1)
    t32.check_variable("myModule.myFlag", "1")

    t32.go()
```

### 3 – Auto-discover symbols and generate test cases *(v1.3)*

Connect to a running Trace32 session, query every module / function /
variable from the loaded ELF, and write a ready-to-run test suite in one
call – **no manual editing required**.

```python
from GM_VIP_Automation_Framework import generate_from_live_session, T32Connection

with T32Connection(port=20000) as conn:
    result = generate_from_live_session(
        output_dir="./generated",   # where to write the artefacts
        suite_name="MyECU",         # label used in file names and reports
        connection=conn,
    )
    print(result["inventory"].summary())
    # → SymbolInventory: 12 module(s), 87 function(s), 43 variable(s), 130 total.
    print("JSON suite :", result["json_path"])
    print("Run script :", result["script_path"])
```

This produces two files in `./generated/`:

| File | Purpose |
|------|---------|
| `MyECU_test_cases.json` | Test suite with one breakpoint TC per function, variable-inspect TCs, and per-module inventory TCs; run with `runner.run_from_json` |
| `MyECU_session_script.py` | Standalone Python script that connects, verifies symbols, sets breakpoints, reads variables, and saves HTML+JSON reports |

You can also work from a pre-built `SymbolInventory`:

```python
from GM_VIP_Automation_Framework import discover_symbols, generate_from_inventory

inventory = discover_symbols(connection=conn, pattern="\\\\myModule.c\\\\*")
print(inventory.summary())

# Inspect discovered symbols directly
for func in inventory.functions:
    print(f"  FUNC  {func.name}  @ {func.address}")
for var in inventory.variables:
    print(f"  VAR   {var.name}  @ {var.address}")

generate_from_inventory(inventory, output_dir="./generated", suite_name="myModule")
```

### 4 – Generate a module status HTML dashboard *(v1.3)*

After running a test suite you can produce a professional HTML status page
that shows every module, symbol, breakpoint result, and variable value in a
single view.

```python
from GM_VIP_Automation_Framework import discover_symbols, generate_from_live_session
from GM_VIP_Automation_Framework.report import ModuleStatusReport
from GM_VIP_Automation_Framework import runner

# 1. Discover all symbols.
inventory = discover_symbols(connection=conn)

# 2. Run the generated test suite.
report = runner.run_from_json("MyECU_test_cases.json")

# 3. Build the status dashboard and merge run-time results.
msr = ModuleStatusReport.from_inventory(inventory, suite_name="MyECU Status")
msr.merge_test_case_report(report)   # overlays BP hit/miss + variable values

msr.save_html("module_status.html")
msr.save_json("module_status.json")
print(msr.summary())
# → MyECU Status: 12 module(s), 130 symbol(s), 87 breakpoint(s) HIT, 0 MISS
```

### 5 – CMM-first workflow (connect to already-running Trace32)

This is the **recommended workflow** when your Trace32 environment is
managed by a single ``*.cmm`` PRACTICE macro script.

**How it works:**

1. You run your ``*.cmm`` script in Trace32 (manually or via another
   tool).  The script handles all hardware configuration and opens the
   Trace32 API port.
2. The Python framework connects to the **already-running** Trace32 on
   the configured port – no ``exe_path`` update required.
3. If Trace32 is not yet running and ``auto_launch=True``, the framework
   launches it automatically using the CMM script as the startup script.

```python
from GM_VIP_Automation_Framework import runner

# Trace32 is already running – the framework will connect automatically.
# No exe_path is needed.
report = runner.run_from_json(
    "test_cases.json",
    config_json_path="config.json",  # only rcl_port matters here
)
print(report.summary())
```

To also handle the case where Trace32 is not yet running:

```python
report = runner.run_from_json(
    "test_cases.json",
    cmm_entry_script=r"C:\workspace\tc4d9xe_debug.cmm",
    auto_launch=True,   # launch T32 with the CMM script if not running
)
```

Or using the convenience ``connect()`` factory:

```python
from GM_VIP_Automation_Framework import connect

# Try to connect to running T32; launch via CMM script if not found.
with connect(
    port=20000,
    cmm_entry_script=r"C:\workspace\tc4d9xe_debug.cmm",
    auto_launch=True,
    resilient_connect=True,
) as conn:
    from GM_VIP_Automation_Framework import core
    core.debugger.default_connection = conn
    # … test steps …
```

See ``templates/connect_with_cmm.py`` for a full ready-to-run example.

### 6 – Auto-detect Trace32 installation

```python
from GM_VIP_Automation_Framework import auto_detect_t32, T32Connection
from GM_VIP_Automation_Framework import core

exe, cfg = auto_detect_t32()   # scans C:\T32\bin, C:\T32, C:\t32\bin, C:\t32

with T32Connection(exe_path=exe, config_path=cfg) as conn:
    core.debugger.default_connection = conn
    # … test steps …
```

### 7 – Launch Trace32 automatically

```python
with T32Connection() as conn:
    conn.launch()    # starts t32marm.exe
    conn.connect()   # waits up to connect_max_wait_s for the RCL socket
    core.debugger.default_connection = conn
    # … test steps …
```

---

## API Reference

### Connection (`core.connection`)

| Function / Class                              | Description                                                        |
|-----------------------------------------------|--------------------------------------------------------------------|
| `T32Connection(exe_path, config_path, port, cmm_entry_script)` | Connection lifecycle manager (context manager supported) |
| `T32Connection.launch(cmm_entry_script)`      | Start the Trace32 process; passes `-s <script>` when `cmm_entry_script` is set |
| `T32Connection.connect()`                     | Establish the RCL socket (polls until timeout)                     |
| `T32Connection.try_connect() → bool`          | Non-raising probe: returns `True` if a running T32 is found        |
| `T32Connection.disconnect()`                  | Close the RCL socket gracefully                                    |
| `T32Connection.cmd(command)`                  | Send a raw PRACTICE command                                        |
| `T32Connection.fnc(expression)`               | Evaluate a PRACTICE expression and return the result string        |
| `connect(exe_path, port, auto_launch, cmm_entry_script, resilient_connect)` | Factory – returns a connected `T32Connection` |
| `auto_detect_t32(search_dirs, exe_names)`     | Scan for T32 installation, return `(exe_path, config_path)`        |
| `parse_config_port(config_path)`              | Parse `PORT=` from a `config.t32` / `t32.ini` file                |

### Debugger Control (`core.debugger`)

| Function                                    | CAPL equivalent          | Description                                    |
|---------------------------------------------|--------------------------|------------------------------------------------|
| `go(connection)`                            | `A_DBGR_Go()`            | Resume ECU execution                           |
| `go_safe(max_retries, connection)`          | `A_DBGR_Go_Safe()`       | Resume with soft-reset detection / retry       |
| `break_execution(connection)`               | `A_DBGR_Break()`         | Halt ECU execution                             |
| `reset_target(connection)`                  | `A_DBGR_R()`             | Reset ECU (no symbol reload)                   |
| `reset_and_go(connection)`                  | `A_DBGR_RnGo()`          | Reset + clear all BPs + GO                     |
| `go_up(connection)`                         | `A_DBGR_GoUp()`          | Step out of current function                   |
| `step_over(connection)`                     | `A_DBGR_StepOver()`      | Source-level step over                         |
| `is_running(connection) → bool`             | `isRunning()`            | True when ECU is executing                     |
| `get_state(connection) → str`               | —                        | Human-readable state string                    |
| `get_pp_register(connection) → str`         | `readPPRegister()`       | Current PC value as hex string                 |
| `wait_for_halt(timeout_s, connection)`      | `waitForNotRunning()`    | Block until ECU halts                          |
| `wait_for_running(timeout_s, connection)`   | `waitForRunning()`       | Block until ECU runs                           |

### Breakpoints (`core.breakpoints`)

| Function                                              | CAPL equivalent                       | Description                                       |
|-------------------------------------------------------|---------------------------------------|---------------------------------------------------|
| `set_breakpoint(address, …)`                          | `A_DBGR_BreakpointSet()`             | Set execution BP with retry + SYMBOL.RELOAD       |
| `set_breakpoint_or_abort(address, connection)`        | `A_DBGR_BreakpointSet_AbortOnFail()` | Set BP, raise immediately on failure              |
| `set_breakpoint_write(address, connection)`           | `A_DBGR_BreakpointWrite()`           | Set data-write watchpoint                         |
| `set_breakpoint_read(address, connection)`            | `A_DBGR_BreakpointRead()`            | Set data-read watchpoint                          |
| `delete_breakpoint(address, connection)`              | `A_DBGR_BreakpointDelete()`          | Delete a specific breakpoint                      |
| `delete_all_breakpoints(connection)`                  | `A_DBGR_BreakpointDeleteAll()`       | Remove all breakpoints                            |
| `check_halted_at(address, timeout_s, connection)`     | `E_DBGR_BreakpointCheckForHalt()`    | Assert ECU halted at expected address             |
| `check_halted_at_core(address, core, …)`              | `E_DBGR_BreakpointCheckForHaltCore()`| Assert ECU halted at address on specific core     |

### Variables (`core.variables`)

| Function                                                      | CAPL equivalent                      | Description                                  |
|---------------------------------------------------------------|--------------------------------------|----------------------------------------------|
| `read_variable(symbol, connection) → str`                     | `A_DBGR_VariableRead()`              | Read a target variable                       |
| `set_variable(symbol, value, connection)`                     | `A_DBGR_VariableSet()`               | Write a value to a target variable           |
| `check_variable(symbol, expected, connection) → bool`         | `E_DBGR_VariableCheck()`             | Assert variable == expected                  |
| `check_variable_until(symbol, expected, timeout_s, …)`        | `E_DBGR_VariableCheck_until()`       | Poll until variable reaches expected         |
| `check_array_element(symbol, index, expected, connection)`    | `E_DBGR_VariableCheckArrayElement()` | Assert `symbol[index] == expected`           |

### Registers (`core.registers`)

| Function                                                       | CAPL equivalent                   | Description                                    |
|----------------------------------------------------------------|-----------------------------------|------------------------------------------------|
| `read_register(register, connection) → str`                    | `A_DBGR_RegisterRead()`           | Read a CPU register                            |
| `set_register(register, value, connection)`                    | `A_DBGR_RegisterSet()`            | Write a value to a CPU register                |
| `set_register_by_mask(register, mask, value, connection)`      | `A_DBGR_RegisterSetByMask()`      | Modify selected bits of a register             |
| `check_register(register, expected, connection) → bool`        | `E_DBGR_RegisterCheck()`          | Assert register == expected (numeric)          |
| `check_register_bit(register, bit_pos, expected, connection)`  | `E_DBGR_RegisterCheckBitStatus()` | Assert a specific bit of a register            |

### Symbols (`core.symbols`)

| Function                                         | Description                                               |
|--------------------------------------------------|-----------------------------------------------------------|
| `reload_symbols(wait_s, connection)`             | Issue `SYMBOL.RELOAD` and wait for rebuild                |
| `symbol_exists(symbol, connection) → bool`       | Return True when symbol is in ELF debug info              |
| `get_symbol_address(symbol, connection) → str`   | Return the linear address of a symbol as hex string       |
| `list_symbols(pattern, connection) → list[str]`  | Return all symbols matching a wildcard pattern            |
| `search_symbol(name_fragment, connection)`       | Search for symbols containing a sub-string               |

### Symbol Auto-Discovery (`core.symbol_discovery`) *(v1.3)*

Queries the active Trace32 session via `SYMBOL.LIST` and classifies every
symbol in the loaded ELF.  Classification uses the T32 section-kind column
(`CODE`/`PROC` → FUNCTION, `DATA`/`BSS` → VARIABLE) with a name-heuristic
fallback for stripped binaries.

#### Data Classes

| Class | Description |
|-------|-------------|
| `SymbolKind` | Enum – `FUNCTION`, `VARIABLE`, `MODULE`, `UNKNOWN` |
| `DiscoveredSymbol` | Frozen dataclass – `name`, `short_name`, `module`, `kind`, `address`, `size`, `exists` |
| `SymbolInventory` | Aggregated results, per-module index; provides `.functions`, `.variables`, `.modules`, `.functions_in(mod)`, `.variables_in(mod)`, `.summary()`, `.to_dict()` |

#### Functions

| Function | Description |
|----------|-------------|
| `discover_symbols(pattern, connection, resolve_addresses, max_symbols) → SymbolInventory` | **Main entry** – run `SYMBOL.LIST`, parse output, optionally verify each symbol via `SYMBOL.EXIST` / `ADDRESS.OFFSET(SYMBOL.BEGIN(…))` |
| `discover_modules(connection) → list[str]` | Return unique source-module names (sorted) |
| `discover_functions(module_pattern, connection) → list[DiscoveredSymbol]` | Return function symbols only (sorted by module + name) |
| `discover_variables(module_pattern, connection) → list[DiscoveredSymbol]` | Return variable symbols only (sorted by module + name) |

### Test-Case Generator (`generator`) *(v1.3)*

Converts a `SymbolInventory` (or a live session) into ready-to-run
artefacts with a single call.

| Function | Description |
|----------|-------------|
| `generate_from_live_session(output_dir, suite_name, pattern, connection, …) → dict` | **One-shot**: discover symbols + write JSON suite + Python script; returns `{"json_path", "script_path", "inventory"}` |
| `generate_from_inventory(inventory, output_dir, suite_name, port, …) → dict` | Write artefacts from a pre-built `SymbolInventory`; returns `{"json_path", "script_path"}` |
| `generate_test_cases_json(inventory, suite_name, …) → dict` | Return the JSON suite dict (without writing to disk) |
| `generate_session_script(inventory, suite_name, port, max_functions, max_variables) → str` | Return the Python session script as a string (without writing) |

**Generated JSON schema** (compatible with `runner.run_from_json`):

```json
{
  "test_suite": "MyECU",
  "_generator_meta": { "generated_at": "…", "total_symbols": 130 },
  "test_cases": [
    {
      "name": "TC_BP_main_c_myFunc",
      "enabled": true,
      "breakpoints": ["\\\\src\\\\main.c\\\\myFunc"],
      "symbols_inspect": ["\\\\src\\\\main.c\\\\myFunc"],
      "variables_write": {},
      "variables_check": {}
    }
  ]
}
```

### Reports (`report`)

#### `TestCaseReport`

| Method | Description |
|--------|-------------|
| `begin_test_case(name)` | Start a new test case |
| `pass_test_case()` / `fail_test_case(message)` | Close the current test case |
| `record_breakpoint(symbol, hit)` | Log a breakpoint hit/miss |
| `record_variable(symbol, value)` | Log a variable read/write value |
| `record_symbol(symbol, exists, address)` | Log symbol existence and address |
| `save_json(path)` / `save_html(path)` | Serialise the report |
| `summary() → str` | One-line text summary |

#### `ModuleStatusReport` *(v1.3)*

Professional HTML status dashboard aggregated from a `SymbolInventory` and
enriched with run-time evidence from a `TestCaseReport`.

| Method | Description |
|--------|-------------|
| `ModuleStatusReport.from_inventory(inventory, suite_name) → ModuleStatusReport` | Factory – populate per-module symbol rows from a `SymbolInventory` |
| `merge_test_case_report(tc_report)` | Overlay breakpoint HIT/MISS and variable values from a completed `TestCaseReport` |
| `summary() → str` | One-line text summary (modules, symbols, BP hit/miss counts) |
| `save_html(path)` | Write a self-contained HTML dashboard (stat cards + per-module collapsible tables) |
| `save_json(path)` | Write the report as JSON |
| `to_dict() → dict` | Return a JSON-serialisable dict |

### CMM Script Execution (`core.cmm`)

| Function                                                                           | CAPL equivalent              | Description                                  |
|------------------------------------------------------------------------------------|------------------------------|----------------------------------------------|
| `run_cmm_command(command, timeout_s, connection) → list[str]`                      | `lFctn_G_T32_RUN_CMM_CORE()` | Execute a PRACTICE command, capture output   |
| `run_cmm_script(script_path, arguments, timeout_s, connection) → list[str]`        | —                            | Execute a `.cmm` file, capture output        |
| `check_cmm_script_result(script_path, expected_result_line, …) → bool`             | `E_DBGR_CheckCmmScriptResult()` | Run CMM script and assert result line     |

---

## Exception Hierarchy

```
T32FrameworkError
├── T32ConnectionError      – connection not established or lost
├── T32TimeoutError         – operation did not complete in time
├── T32LaunchError          – Trace32 process could not be started
├── T32CommandError         – Trace32 command returned non-zero exit code
├── T32SymbolError          – symbol not found in ELF debug info
├── T32VariableError        – variable read/write/check failed
├── T32RegisterError        – register read/write/check failed
├── T32BreakpointError      – breakpoint operation failed
│   └── T32BreakpointNotReachedError  – expected halt did not occur
├── T32ConfigError          – framework configuration invalid
└── T32AutoDetectError      – T32 installation not found
```

---

## Running Tests

```bash
# From the repository root
python -m pytest GM_VIP_Automation_Framework/tests/ -v
# or
python -m unittest discover GM_VIP_Automation_Framework/tests/
```

All tests run **without a physical Trace32 connection** – the `lauterbach.trace32.rcl`
library is completely mocked via `unittest.mock`.

The test suite currently covers **357 test cases** across:

| File | Test Cases | Scope |
|------|-----------|-------|
| `test_utils.py` | 12 | Exceptions, logger, retry utilities |
| `test_core.py` | 80 | All core modules – connection, debugger, breakpoints, variables, registers, symbols, CMM, runner |
| `test_config_and_report.py` | 54 | Config I/O, `TestCaseReport`, HTML rendering |
| `test_hardware.py` | 12 | CAN bus, CANoe, power supply (mock mode) |
| `test_sanity.py` | 76 | Full end-to-end sanity suite (mock mode; toggle `USE_LIVE_T32=True` for real hardware) |
| `test_symbol_discovery.py` | 43 | `SymbolInventory`, `DiscoveredSymbol`, parser, classification heuristics, `discover_*` helpers |
| `test_generator.py` | 45 | JSON generation, Python script generation (AST-valid check), file writing, runner schema compatibility, `ModuleStatusReport` |

---

## Design Principles

1. **No CANoe / DLL dependency** – all Trace32 interaction goes through `lauterbach.trace32.rcl`.
2. **Mirror CAPL logic** – every function name maps 1-to-1 to a CAPL equivalent for easy porting.
3. **Retry-resilient** – `set_breakpoint` retries up to `bp_max_retries` times and issues `SYMBOL.RELOAD` automatically when symbols are not yet loaded.
4. **Configurable via `settings`** – all timeouts and retry counts live in one place and can be overridden per-bench via environment variables.
5. **Testable without hardware** – no global state that prevents mocking; every function accepts an explicit `connection` parameter.
6. **Structured logging** – all operations log at `DEBUG`/`INFO` level with a consistent format; coloured console output when connected to a TTY.
7. **CMM-first / resilient connect** – `run_from_json` (and the `connect()` factory with `resilient_connect=True`) probes for a running Trace32 instance before deciding whether to launch one.  When Trace32 is already running (your `*.cmm` script opened the port), no `exe_path` or `config.t32` path is required.  The launch paths in `config.json` serve only as a fallback when `auto_launch=True`.
8. **Auto-discovery** – `discover_symbols` queries `SYMBOL.LIST` from the live session, classifies every symbol using section-kind columns and name heuristics, and returns a typed `SymbolInventory`.  `generate_from_live_session` then turns that inventory into a full test suite without any manual editing.

---

## Changelog

| Version | Highlights |
|---------|-----------|
| **1.3.0** | Live symbol auto-discovery (`core/symbol_discovery.py`), test-case generator (`generator.py`), `ModuleStatusReport` HTML dashboard, 88 new unit tests |
| **1.2.0** | `go_safe()`, `check_halted_at_core()`, `run_all_discovered()`, HTML reports, `intermediate_halt_max_gos` |
| **1.1.0** | `T32Connection` packlen, `post_reset_settle_s` / `go_settle_s` synchronisation, resilient connect |
| **1.0.0** | Initial release – connection, debugger, breakpoints, variables, registers, symbols, CMM, JSON runner |
