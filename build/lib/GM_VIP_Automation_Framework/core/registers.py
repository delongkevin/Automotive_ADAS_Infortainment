"""
GM VIP Automation Framework – Register Read / Write / Check API
================================================================
Python equivalents of the CAPL ``A_DBGR_Register*`` and
``E_DBGR_Register*`` functions from ``tsT32.cin``.

Register operations require the ECU to be halted.  Mutating functions call
:func:`~debugger.wait_for_halt` automatically before issuing commands.

Public API
----------
- :func:`read_register` – read a CPU register value.
- :func:`set_register` – write a value to a CPU register.
- :func:`set_register_by_mask` – modify selected bits of a register.
- :func:`check_register` – assert a register equals an expected value.
- :func:`check_register_bit` – assert a specific bit of a register.
"""

from __future__ import annotations

from typing import Optional, Union

from ..config import settings
from ..utils.exceptions import T32RegisterError
from ..utils.logger import get_logger
from .debugger import _conn, wait_for_halt

logger = get_logger("registers")

# Shared default_connection reference.
default_connection = None  # type: Optional[object]


def _resolve_conn(connection):
    return _conn(connection or default_connection)


# ---------------------------------------------------------------------------
# Register read
# ---------------------------------------------------------------------------

def read_register(
    register: str,
    connection=None,
) -> str:
    """Read the current value of *register*.

    Mirrors CAPL ``A_DBGR_RegisterRead``.  Uses the PRACTICE expression
    ``R(<register>)`` which works for general-purpose registers (``R0``–``R15``,
    ``PC``, ``SP``, ``LR``, etc.) as well as SFR names on Aurix targets.

    Parameters
    ----------
    register:
        Register name as understood by Trace32 (e.g. ``"R0"``, ``"PC"``,
        ``"PSW"``).
    connection:
        Optional connection override.

    Returns
    -------
    str
        The register value as a hexadecimal string (as returned by Trace32).

    Raises
    ------
    T32RegisterError
        On failure.
    """
    conn = _resolve_conn(connection)
    wait_for_halt(connection=conn)

    logger.info("Read register '%s'.", register)
    try:
        result = conn.fnc(f"R({register})")
        value = str(result).strip()
        logger.debug("Register '%s' = %s.", register, value)
        return value
    except Exception as exc:  # noqa: BLE001
        raise T32RegisterError(
            f"Failed to read register '{register}': {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Register write
# ---------------------------------------------------------------------------

def set_register(
    register: str,
    value: Union[str, int],
    connection=None,
) -> None:
    """Write *value* to *register*.

    Mirrors CAPL ``A_DBGR_RegisterSet``.

    Parameters
    ----------
    register:
        Register name (e.g. ``"R0"``, ``"PC"``).
    value:
        Value to write.  Integers are formatted as hex (``0x…``); strings
        are passed verbatim.
    connection:
        Optional connection override.

    Raises
    ------
    T32RegisterError
        On failure.
    """
    conn = _resolve_conn(connection)
    wait_for_halt(connection=conn)

    value_str = hex(value) if isinstance(value, int) else str(value)
    logger.info("Set register '%s' = %s.", register, value_str)
    try:
        conn.cmd(f"Register.Set {register} {value_str}")
        logger.debug("Set register '%s' = %s.", register, value_str)
    except Exception as exc:  # noqa: BLE001
        raise T32RegisterError(
            f"Failed to set register '{register}' to '{value_str}': {exc}"
        ) from exc


def set_register_by_mask(
    register: str,
    mask: Union[str, int],
    value: Union[str, int],
    connection=None,
) -> None:
    """Modify selected bits of *register* according to *mask*.

    Mirrors CAPL ``A_DBGR_RegisterSetByMask``.  The operation performed is::

        new_value = (current_value & ~mask) | (value & mask)

    Parameters
    ----------
    register:
        Register name.
    mask:
        Bit mask selecting which bits to update.  Only the bits set to ``1``
        in *mask* are modified.
    value:
        New value for the masked bits.
    connection:
        Optional connection override.

    Raises
    ------
    T32RegisterError
        On failure.
    """
    conn = _resolve_conn(connection)
    wait_for_halt(connection=conn)

    mask_int = int(mask, 0) if isinstance(mask, str) else mask
    val_int = int(value, 0) if isinstance(value, str) else value

    logger.info(
        "Set register '%s' by mask=0x%X value=0x%X.", register, mask_int, val_int
    )
    try:
        current_str = read_register(register, connection=conn)
        current = int(current_str, 16) if current_str.startswith("0x") else int(current_str, 0)
        new_val = (current & ~mask_int) | (val_int & mask_int)
        conn.cmd(f"Register.Set {register} 0x{new_val:X}")
        logger.debug(
            "Register '%s': 0x%X -> 0x%X (mask=0x%X).",
            register, current, new_val, mask_int,
        )
    except T32RegisterError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise T32RegisterError(
            f"Failed to set register '{register}' by mask: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Register check
# ---------------------------------------------------------------------------

def check_register(
    register: str,
    expected: Union[str, int],
    connection=None,
) -> bool:
    """Assert that *register* equals *expected*.

    Mirrors CAPL ``E_DBGR_RegisterCheck``.

    Parameters
    ----------
    register:
        Register name.
    expected:
        Expected value.  Integers are compared numerically after parsing
        both the actual and expected as integers (base 0).
    connection:
        Optional connection override.

    Returns
    -------
    bool
        ``True`` when the value matches.

    Raises
    ------
    T32RegisterError
        On mismatch or read failure.
    """
    actual_str = read_register(register, connection=connection)
    expected_str = str(expected)

    # Numeric comparison to handle different representations (hex vs decimal).
    try:
        actual_int = int(actual_str, 0)
        expected_int = int(expected_str, 0)
        match = actual_int == expected_int
    except (ValueError, TypeError):
        match = actual_str.strip().upper() == expected_str.strip().upper()

    if match:
        logger.info("Register check PASS: '%s' == %s.", register, expected_str)
        return True

    logger.error(
        "Register check FAIL: '%s' expected=%s actual=%s.", register, expected_str, actual_str
    )
    raise T32RegisterError(
        f"Register '{register}': expected '{expected_str}', got '{actual_str}'."
    )


def check_register_bit(
    register: str,
    bit_position: int,
    expected_bit: int,
    connection=None,
) -> bool:
    """Assert that bit *bit_position* of *register* equals *expected_bit*.

    Mirrors CAPL ``E_DBGR_RegisterCheckBitStatus``.

    Parameters
    ----------
    register:
        Register name.
    bit_position:
        Zero-based bit position to check (0 = LSB).
    expected_bit:
        Expected bit value: ``0`` or ``1``.
    connection:
        Optional connection override.

    Returns
    -------
    bool
        ``True`` when the bit matches *expected_bit*.

    Raises
    ------
    T32RegisterError
        On mismatch or read failure.
    ValueError
        If *expected_bit* is not 0 or 1.
    """
    if expected_bit not in (0, 1):
        raise ValueError(f"expected_bit must be 0 or 1, got {expected_bit!r}.")

    actual_str = read_register(register, connection=connection)
    try:
        actual_int = int(actual_str, 0)
    except ValueError as exc:
        raise T32RegisterError(
            f"Cannot parse register value '{actual_str}' as integer."
        ) from exc

    actual_bit = (actual_int >> bit_position) & 1

    if actual_bit == expected_bit:
        logger.info(
            "Register bit check PASS: '%s' bit[%d] == %d.",
            register, bit_position, expected_bit,
        )
        return True

    logger.error(
        "Register bit check FAIL: '%s' bit[%d] expected=%d actual=%d.",
        register, bit_position, expected_bit, actual_bit,
    )
    raise T32RegisterError(
        f"Register '{register}' bit[{bit_position}]: expected {expected_bit}, got {actual_bit}."
    )
