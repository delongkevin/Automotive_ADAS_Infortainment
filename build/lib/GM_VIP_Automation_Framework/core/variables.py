"""
GM VIP Automation Framework – Variable Read / Write / Check API
================================================================
Provides Python equivalents of the CAPL ``A_DBGR_Variable*`` and
``E_DBGR_Variable*`` functions from ``tsT32.cin``.

All variable operations that modify memory require the ECU to be halted
first.  Each mutating function calls :func:`~debugger.wait_for_halt`
automatically before issuing the command.

Public API
----------
- :func:`read_variable` – read a variable value from target memory.
- :func:`set_variable` – write a value to a target variable.
- :func:`check_variable` – assert a variable equals an expected value.
- :func:`check_variable_until` – poll until a variable reaches expected value.
- :func:`check_array_element` – assert a single array element value.
"""

from __future__ import annotations

import time
from typing import Any, Optional, Union

from ..config import settings
from ..utils.exceptions import (
    T32ConnectionError,
    T32TimeoutError,
    T32VariableError,
)
from ..utils.logger import get_logger
from ..utils.retry import poll_until
from .debugger import _conn, wait_for_halt

logger = get_logger("variables")

# Shared default_connection reference.
default_connection = None  # type: Optional[object]


def _resolve_conn(connection):
    return _conn(connection or default_connection)


# ---------------------------------------------------------------------------
# Variable read
# ---------------------------------------------------------------------------

def read_variable(
    symbol: str,
    connection=None,
) -> str:
    """Read the current value of *symbol* from target memory.

    Mirrors CAPL ``A_DBGR_VariableRead``.  The ECU must be halted; the
    function waits up to :attr:`~config.T32Settings.halt_timeout_s` seconds
    for a halt before reading.

    Parameters
    ----------
    symbol:
        C-style variable name or address expression understood by Trace32
        (e.g. ``"myModule.myVar"``, ``"\\myFile.c\\localVar"``).
    connection:
        Optional connection override.

    Returns
    -------
    str
        The value returned by ``VAR.VALUE(<symbol>)`` as a string.

    Raises
    ------
    T32VariableError
        On failure.
    """
    conn = _resolve_conn(connection)
    wait_for_halt(connection=conn)

    logger.info("VAR.VALUE '%s'.", symbol)
    try:
        result = conn.fnc(f"VAR.VALUE({symbol})")
        value = str(result).strip()
        logger.debug("Read '%s' = %s.", symbol, value)
        return value
    except Exception as exc:  # noqa: BLE001
        raise T32VariableError(
            f"Failed to read variable '{symbol}': {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Variable write
# ---------------------------------------------------------------------------

def set_variable(
    symbol: str,
    value: Union[str, int, float],
    connection=None,
) -> None:
    """Write *value* to the target variable *symbol*.

    Mirrors CAPL ``A_DBGR_VariableSet``.  The ECU must be halted; the
    function waits automatically.

    Parameters
    ----------
    symbol:
        Variable name or address expression.
    value:
        Value to write.  Numeric types are formatted as decimal integers;
        strings are passed verbatim (useful for hex literals like
        ``"0x1A"``).
    connection:
        Optional connection override.

    Raises
    ------
    T32VariableError
        On failure.
    """
    conn = _resolve_conn(connection)
    wait_for_halt(connection=conn)

    value_str = str(value)
    logger.info("VAR.SET %s = %s.", symbol, value_str)
    try:
        conn.cmd(f"VAR.SET {symbol}={value_str}")
        logger.debug("Set '%s' = %s.", symbol, value_str)
    except Exception as exc:  # noqa: BLE001
        raise T32VariableError(
            f"Failed to set variable '{symbol}' to '{value_str}': {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Variable check (single shot)
# ---------------------------------------------------------------------------

def check_variable(
    symbol: str,
    expected: Union[str, int, float],
    connection=None,
) -> bool:
    """Assert that *symbol* equals *expected*.

    Mirrors CAPL ``E_DBGR_VariableCheck``.

    Parameters
    ----------
    symbol:
        Variable name.
    expected:
        Expected value (compared as string after stripping whitespace).
    connection:
        Optional connection override.

    Returns
    -------
    bool
        ``True`` when the value matches *expected*.

    Raises
    ------
    T32VariableError
        On read failure or value mismatch.
    """
    actual = read_variable(symbol, connection=connection)
    expected_str = str(expected).strip()

    if actual == expected_str:
        logger.info("Variable check PASS: '%s' == %s.", symbol, expected_str)
        return True

    logger.error(
        "Variable check FAIL: '%s' expected=%s actual=%s.", symbol, expected_str, actual
    )
    raise T32VariableError(
        f"Variable '{symbol}': expected '{expected_str}', got '{actual}'."
    )


# ---------------------------------------------------------------------------
# Variable check with timeout (poll until)
# ---------------------------------------------------------------------------

def check_variable_until(
    symbol: str,
    expected: Union[str, int, float],
    timeout_s: Optional[float] = None,
    connection=None,
) -> bool:
    """Poll *symbol* until it equals *expected* or *timeout_s* elapses.

    Mirrors CAPL ``E_DBGR_VariableCheck_until``.

    Parameters
    ----------
    symbol:
        Variable name.
    expected:
        Expected value.
    timeout_s:
        Maximum seconds to poll.  Defaults to
        :attr:`~config.T32Settings.halt_timeout_s`.
    connection:
        Optional connection override.

    Returns
    -------
    bool
        ``True`` when the value matched within the timeout.

    Raises
    ------
    T32TimeoutError
        When the value did not match within *timeout_s*.
    """
    conn = _resolve_conn(connection)
    tmo = timeout_s if timeout_s is not None else settings.halt_timeout_s
    expected_str = str(expected).strip()

    logger.info(
        "Polling '%s' for value=%s (timeout=%.1fs).", symbol, expected_str, tmo
    )

    def _check() -> bool:
        try:
            return read_variable(symbol, connection=conn) == expected_str
        except Exception:  # noqa: BLE001
            return False

    reached = poll_until(
        condition=_check,
        timeout_s=tmo,
        interval_s=settings.poll_interval_s,
        description=f"variable '{symbol}' == {expected_str}",
    )

    if reached:
        logger.info(
            "Variable poll PASS: '%s' reached %s.", symbol, expected_str
        )
        return True

    # Read actual for the error message.
    try:
        actual = read_variable(symbol, connection=conn)
    except Exception:  # noqa: BLE001
        actual = "<read error>"

    raise T32TimeoutError(
        f"Variable '{symbol}' did not reach '{expected_str}' within {tmo}s. "
        f"Last value: '{actual}'."
    )


# ---------------------------------------------------------------------------
# Array-element check
# ---------------------------------------------------------------------------

def check_array_element(
    symbol: str,
    index: int,
    expected: Union[str, int, float],
    connection=None,
) -> bool:
    """Assert that ``symbol[index]`` equals *expected*.

    Mirrors CAPL ``E_DBGR_VariableCheckArrayElement``.

    Parameters
    ----------
    symbol:
        Array variable name (without index brackets).
    index:
        Zero-based array index.
    expected:
        Expected value of the element.
    connection:
        Optional connection override.

    Returns
    -------
    bool
        ``True`` when ``symbol[index] == expected``.

    Raises
    ------
    T32VariableError
        On mismatch or read failure.
    """
    element_symbol = f"{symbol}[{index}]"
    logger.info("Array element check: %s == %s.", element_symbol, expected)
    return check_variable(element_symbol, expected, connection=connection)
