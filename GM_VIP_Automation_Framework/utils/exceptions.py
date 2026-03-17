"""
GM VIP Automation Framework – Custom Exception Hierarchy
=========================================================
All framework-specific exceptions are derived from ``T32FrameworkError``
so callers can catch them with a single ``except T32FrameworkError`` clause.
"""

from __future__ import annotations


class T32FrameworkError(Exception):
    """Base class for all GM VIP Automation Framework exceptions."""


# ---------------------------------------------------------------------------
# Connection errors
# ---------------------------------------------------------------------------

class T32ConnectionError(T32FrameworkError):
    """Raised when a connection to Trace32 cannot be established or is lost."""


class T32TimeoutError(T32FrameworkError):
    """Raised when a blocking operation does not complete within its timeout."""


class T32LaunchError(T32FrameworkError):
    """Raised when the Trace32 process cannot be started."""


# ---------------------------------------------------------------------------
# Command errors
# ---------------------------------------------------------------------------

class T32CommandError(T32FrameworkError):
    """Raised when a Trace32 API command returns a non-zero exit code."""

    def __init__(self, command: str, exit_code: int, message: str = "") -> None:
        self.command = command
        self.exit_code = exit_code
        self.api_message = message
        super().__init__(
            f"T32 command '{command}' failed (exit={exit_code}): {message}"
        )


# ---------------------------------------------------------------------------
# Symbol / variable errors
# ---------------------------------------------------------------------------

class T32SymbolError(T32FrameworkError):
    """Raised when a requested symbol cannot be found in the T32 symbol table."""

    def __init__(self, symbol: str, message: str = "") -> None:
        self.symbol = symbol
        super().__init__(
            f"Symbol '{symbol}' not found in T32 symbol table. {message}".rstrip()
        )


class T32VariableError(T32FrameworkError):
    """Raised when a variable read or write operation fails."""


class T32RegisterError(T32FrameworkError):
    """Raised when a register read or write operation fails."""


# ---------------------------------------------------------------------------
# Breakpoint errors
# ---------------------------------------------------------------------------

class T32BreakpointError(T32FrameworkError):
    """Raised when a breakpoint operation fails."""


class T32BreakpointNotReachedError(T32BreakpointError):
    """Raised when an expected breakpoint halt is not observed within the timeout."""

    def __init__(self, address: str, timeout_ms: int) -> None:
        self.address = address
        self.timeout_ms = timeout_ms
        super().__init__(
            f"Breakpoint '{address}' was not reached within {timeout_ms} ms."
        )


# ---------------------------------------------------------------------------
# Configuration errors
# ---------------------------------------------------------------------------

class T32ConfigError(T32FrameworkError):
    """Raised when framework configuration is invalid or incomplete."""


class T32AutoDetectError(T32FrameworkError):
    """Raised when auto-detection of the Trace32 installation fails."""
