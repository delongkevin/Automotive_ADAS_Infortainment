"""
GM VIP Automation Framework – core package
"""
from .connection import T32Connection, connect, auto_detect_t32, parse_config_port
from .debugger import (
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
    default_connection as debugger_default_connection,
)
from .breakpoints import (
    set_breakpoint,
    set_breakpoint_or_abort,
    set_breakpoint_write,
    set_breakpoint_read,
    delete_breakpoint,
    delete_all_breakpoints,
    check_halted_at,
    check_halted_at_core,
)
from .variables import (
    read_variable,
    set_variable,
    check_variable,
    check_variable_until,
    check_array_element,
)
from .registers import (
    read_register,
    set_register,
    set_register_by_mask,
    check_register,
    check_register_bit,
)
from .symbols import (
    reload_symbols,
    symbol_exists,
    get_symbol_address,
    list_symbols,
    search_symbol,
)
from .symbol_discovery import (
    SymbolKind,
    DiscoveredSymbol,
    SymbolInventory,
    discover_symbols,
    discover_modules,
    discover_functions,
    discover_variables,
)
from .cmm import (
    run_cmm_command,
    run_cmm_script,
    check_cmm_script_result,
)
from .can_bus import CANBusClient, CANBusError, CANFrame
from .canoe import CANoeClient, CANoeError
from .power_supply import BKPrecision1687B, PowerSupplyError
from .capl_monitor import CAPLTestMonitor, CAPLTestResult, CAPLVerdict
from .sequence_recorder import SequenceRecorder, ExecutionEvent

__all__ = [
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
    "debugger_default_connection",
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
    # symbol discovery
    "SymbolKind",
    "DiscoveredSymbol",
    "SymbolInventory",
    "discover_symbols",
    "discover_modules",
    "discover_functions",
    "discover_variables",
    # cmm
    "run_cmm_command",
    "run_cmm_script",
    "check_cmm_script_result",
    # CAN bus (direct python-can interface)
    "CANBusClient",
    "CANBusError",
    "CANFrame",
    # Vector CANoe COM interface
    "CANoeClient",
    "CANoeError",
    # BK Precision 1687B power supply
    "BKPrecision1687B",
    "PowerSupplyError",
    # CAPL test monitoring
    "CAPLTestMonitor",
    "CAPLTestResult",
    "CAPLVerdict",
    # Execution sequence recording
    "SequenceRecorder",
    "ExecutionEvent",
]
