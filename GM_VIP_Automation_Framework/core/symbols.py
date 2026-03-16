"""
GM VIP Automation Framework – Symbol Search API
================================================
Provides helpers for searching the Trace32 symbol database, reloading the
symbol table, and looking up symbol addresses.  These functions mirror the
symbol-related operations referenced in ``tsT32.cin`` (e.g. ``SYMBOL.RELOAD``
triggered inside the breakpoint-set retry loop).

Public API
----------
- :func:`reload_symbols` – force Trace32 to re-read the ELF symbol table.
- :func:`symbol_exists` – test whether a symbol is known to Trace32.
- :func:`get_symbol_address` – return the address of a named symbol.
- :func:`list_symbols` – return all symbols matching a pattern.
- :func:`search_symbol` – search for symbols whose names contain *pattern*.
"""

from __future__ import annotations

import re
import time
from typing import Dict, List, Optional

from ..config import settings
from ..utils.exceptions import T32CommandError, T32SymbolError
from ..utils.logger import get_logger
from .debugger import _conn

logger = get_logger("symbols")

# Shared default_connection reference.
default_connection = None  # type: Optional[object]


def _resolve_conn(connection):
    return _conn(connection or default_connection)


# ---------------------------------------------------------------------------
# Symbol table management
# ---------------------------------------------------------------------------

def reload_symbols(
    wait_s: Optional[float] = None,
    connection=None,
) -> None:
    """Reload the ELF symbol table in Trace32.

    Equivalent to the manual *Reload Symbols* action in the T32 IDE and the
    ``SYMBOL.RELOAD`` PRACTICE command.  This is called automatically by
    :func:`~breakpoints.set_breakpoint` when symbol-not-found failures
    persist after the first few retries.

    Parameters
    ----------
    wait_s:
        Seconds to wait after issuing ``SYMBOL.RELOAD`` for the symbol table
        to be rebuilt.  Defaults to
        :attr:`~config.T32Settings.symbol_reload_wait_s`.
    connection:
        Optional connection override.

    Raises
    ------
    T32CommandError
        When the ``SYMBOL.RELOAD`` command fails.
    """
    conn = _resolve_conn(connection)
    wait = wait_s if wait_s is not None else settings.symbol_reload_wait_s

    logger.info("SYMBOL.RELOAD – rebuilding symbol table (then waiting %.1fs).", wait)
    try:
        conn.cmd("SYMBOL.RELOAD")
    except Exception as exc:  # noqa: BLE001
        raise T32CommandError("SYMBOL.RELOAD", -1, str(exc)) from exc

    time.sleep(wait)
    logger.debug("SYMBOL.RELOAD wait complete.")


# ---------------------------------------------------------------------------
# Symbol existence query
# ---------------------------------------------------------------------------

def symbol_exists(symbol: str, connection=None) -> bool:
    """Return ``True`` when *symbol* is known to Trace32.

    Uses the PRACTICE expression ``SYMBOL.EXIST(<symbol>)`` which evaluates
    to ``TRUE()`` when the symbol is in the loaded ELF debug information.

    Parameters
    ----------
    symbol:
        Symbol name (e.g. ``"myFunc"``, ``"myModule.myVar"``).
    connection:
        Optional connection override.
    """
    conn = _resolve_conn(connection)
    logger.debug("Checking existence of symbol '%s'.", symbol)
    try:
        result = conn.fnc(f"SYMBOL.EXIST({symbol})")
        return str(result).strip().upper() in ("TRUE()", "TRUE", "1")
    except Exception as exc:  # noqa: BLE001
        logger.debug("SYMBOL.EXIST('%s') raised: %s", symbol, exc)
        return False


# ---------------------------------------------------------------------------
# Symbol address lookup
# ---------------------------------------------------------------------------

def get_symbol_address(symbol: str, connection=None) -> str:
    """Return the address of *symbol* as a hexadecimal string.

    Uses the PRACTICE expression ``ADDRESS.OFFSET(sYmbol.BEGIN(<symbol>))``
    to obtain the linear (non-class) address of the symbol's first byte.

    Parameters
    ----------
    symbol:
        Symbol name.
    connection:
        Optional connection override.

    Returns
    -------
    str
        Hexadecimal address string (e.g. ``"0x80001234"``).

    Raises
    ------
    T32SymbolError
        When the symbol does not exist or the address cannot be determined.
    """
    conn = _resolve_conn(connection)
    logger.debug("Looking up address for symbol '%s'.", symbol)

    if not symbol_exists(symbol, connection=conn):
        raise T32SymbolError(symbol, "SYMBOL.EXIST() returned FALSE.")

    try:
        result = conn.fnc(f"ADDRESS.OFFSET(SYMBOL.BEGIN({symbol}))")
        addr = str(result).strip()
        logger.info("Symbol '%s' address = %s.", symbol, addr)
        return addr
    except Exception as exc:  # noqa: BLE001
        raise T32SymbolError(symbol, str(exc)) from exc


# ---------------------------------------------------------------------------
# Symbol list / search
# ---------------------------------------------------------------------------

def list_symbols(
    pattern: str = "*",
    connection=None,
) -> List[str]:
    """Return a list of symbol names matching a wildcard *pattern*.

    Uses ``SYMBOL.LIST <pattern>`` piped through Trace32's AREA buffer.
    Note: this is a potentially slow operation on large symbol tables.

    Parameters
    ----------
    pattern:
        Wildcard pattern (Trace32 syntax).  ``"*"`` returns all symbols.
    connection:
        Optional connection override.

    Returns
    -------
    list[str]
        Sorted list of matching symbol names.
    """
    conn = _resolve_conn(connection)
    logger.info("SYMBOL.LIST '%s'.", pattern)

    try:
        # Write the symbol list to an AREA buffer, then read it back.
        conn.cmd("AREA")
        conn.cmd("AREA.CLEAR")
        conn.cmd(f"SYMBOL.LIST {pattern}")

        # Poll the AREA for content.
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(
            suffix=".txt", delete=False, mode="w", encoding="utf-8"
        ) as _tf:
            tmp = Path(_tf.name)
        deadline = time.monotonic() + settings.cmm_timeout_s
        while time.monotonic() < deadline:
            time.sleep(0.2)
            try:
                conn.cmd(f"AREA.SAVE {tmp}")
            except Exception:  # noqa: BLE001
                continue
            if tmp.stat().st_size > 0:
                break

        text = tmp.read_text(encoding="utf-8", errors="replace") if tmp.exists() else ""
        if tmp.exists():
            tmp.unlink(missing_ok=True)

        # Parse symbol names: lines that start with a symbol address/name.
        symbols: List[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("//") and not stripped.startswith(";"):
                parts = stripped.split()
                if parts:
                    symbols.append(parts[0])
        return sorted(set(symbols))
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_symbols('%s') failed: %s", pattern, exc)
        return []


def search_symbol(
    name_fragment: str,
    connection=None,
) -> List[str]:
    """Search for symbols whose names contain *name_fragment* (case-insensitive).

    This is a convenience wrapper around :func:`list_symbols` that filters
    results client-side using a Python ``in`` check.

    Parameters
    ----------
    name_fragment:
        Sub-string to search for in symbol names.
    connection:
        Optional connection override.

    Returns
    -------
    list[str]
        Symbols whose names contain *name_fragment*.
    """
    all_symbols = list_symbols(f"*{name_fragment}*", connection=connection)
    fragment_lower = name_fragment.lower()
    matched = [s for s in all_symbols if fragment_lower in s.lower()]
    logger.info(
        "search_symbol('%s'): found %d match(es).", name_fragment, len(matched)
    )
    return matched
