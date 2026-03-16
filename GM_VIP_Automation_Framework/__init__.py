"""
GM VIP Automation Framework
============================
Standalone Python API framework for interacting with the Lauterbach Trace32
debugger in GM VIP Automation test environments.

Provides Python equivalents of the CAPL ``tsT32.cin`` / ``cT32.cin``
functions with a clean, object-oriented design built on the official
``lauterbach.trace32.rcl`` Python library.

Quick start
-----------
::

    from GM_VIP_Automation_Framework import (
        T32Connection,
        go, break_execution, reset_target,
        set_breakpoint, check_halted_at,
        read_variable, set_variable,
        read_register, check_register,
        reload_symbols, symbol_exists,
    )

    # Connect (T32 already running)
    with T32Connection(port=20000) as conn:
        from GM_VIP_Automation_Framework import core
        core.debugger.default_connection = conn

        reset_target()
        set_breakpoint("myFunc")
        go()
        check_halted_at("myFunc")
        val = read_variable("myModule.myVar")
        print("myVar =", val)
"""

from .config import settings, T32Settings
from .utils import (
    T32FrameworkError,
    T32ConnectionError,
    T32TimeoutError,
    T32LaunchError,
    T32CommandError,
    T32SymbolError,
    T32VariableError,
    T32RegisterError,
    T32BreakpointError,
    T32BreakpointNotReachedError,
    T32ConfigError,
    T32AutoDetectError,
    configure_logger,
    get_logger,
)
from .core import (
    # connection
    T32Connection,
    connect,
    auto_detect_t32,
    parse_config_port,
    # debugger
    go,
    go_safe,
    break_execution,
    reset_target,
    reset_and_go,
    go_up,
    step_over,
    is_running,
    get_state,
    get_pp_register,
    wait_for_halt,
    wait_for_running,
    # breakpoints
    set_breakpoint,
    set_breakpoint_or_abort,
    set_breakpoint_write,
    set_breakpoint_read,
    delete_breakpoint,
    delete_all_breakpoints,
    check_halted_at,
    check_halted_at_core,
    # variables
    read_variable,
    set_variable,
    check_variable,
    check_variable_until,
    check_array_element,
    # registers
    read_register,
    set_register,
    set_register_by_mask,
    check_register,
    check_register_bit,
    # symbols
    reload_symbols,
    symbol_exists,
    get_symbol_address,
    list_symbols,
    search_symbol,
    # cmm
    run_cmm_command,
    run_cmm_script,
    check_cmm_script_result,
)

__version__ = "1.0.0"

__all__ = [
    "__version__",
    # config
    "settings",
    "T32Settings",
    # exceptions
    "T32FrameworkError",
    "T32ConnectionError",
    "T32TimeoutError",
    "T32LaunchError",
    "T32CommandError",
    "T32SymbolError",
    "T32VariableError",
    "T32RegisterError",
    "T32BreakpointError",
    "T32BreakpointNotReachedError",
    "T32ConfigError",
    "T32AutoDetectError",
    # logging
    "configure_logger",
    "get_logger",
    # connection
    "T32Connection",
    "connect",
    "auto_detect_t32",
    "parse_config_port",
    # debugger
    "go",
    "go_safe",
    "break_execution",
    "reset_target",
    "reset_and_go",
    "go_up",
    "step_over",
    "is_running",
    "get_state",
    "get_pp_register",
    "wait_for_halt",
    "wait_for_running",
    # breakpoints
    "set_breakpoint",
    "set_breakpoint_or_abort",
    "set_breakpoint_write",
    "set_breakpoint_read",
    "delete_breakpoint",
    "delete_all_breakpoints",
    "check_halted_at",
    "check_halted_at_core",
    # variables
    "read_variable",
    "set_variable",
    "check_variable",
    "check_variable_until",
    "check_array_element",
    # registers
    "read_register",
    "set_register",
    "set_register_by_mask",
    "check_register",
    "check_register_bit",
    # symbols
    "reload_symbols",
    "symbol_exists",
    "get_symbol_address",
    "list_symbols",
    "search_symbol",
    # cmm
    "run_cmm_command",
    "run_cmm_script",
    "check_cmm_script_result",
]
