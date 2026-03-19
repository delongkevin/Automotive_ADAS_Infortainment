"""
GM VIP Automation Framework – Breakpoint Operations
====================================================
Provides all breakpoint management functions that mirror the CAPL
``A_DBGR_Breakpoint*`` and ``E_DBGR_Breakpoint*`` functions in ``tsT32.cin``.

All functions accept an optional *connection* argument.  When omitted the
module-level :data:`default_connection` (or
:data:`~debugger.default_connection`) is used.

Public API
----------
- :func:`set_breakpoint` – set an execution breakpoint at a symbol / address.
- :func:`set_breakpoint_write` – set a data-write watchpoint.
- :func:`set_breakpoint_read` – set a data-read watchpoint.
- :func:`delete_breakpoint` – delete a specific breakpoint.
- :func:`delete_all_breakpoints` – remove all breakpoints.
- :func:`check_halted_at` – verify the ECU is halted at the expected address.
- :func:`check_halted_at_core` – same check scoped to a specific core.
"""

from __future__ import annotations

import sys
import time
from typing import Optional

from ..config import settings
from ..utils.exceptions import (
    T32BreakpointError,
    T32BreakpointNotReachedError,
    T32CommandError,
    T32ConnectionError,
    T32SymbolError,
)
from ..utils.logger import get_logger
from .debugger import (
    ECUState,
    _conn,
    get_ecu_state,
    get_pp_register,
    is_reset,
    is_running,
    wait_for_halt,
    wait_for_running,
)

logger = get_logger("breakpoints")


def _print(msg: str) -> None:
    """Write a timestamped diagnostic line to stderr (always visible)."""
    ts = time.strftime("%H:%M:%S")
    print(f"[BP  {ts}] {msg}", file=sys.stderr, flush=True)

# Shared default_connection reference – callers may set this directly.
default_connection = None  # type: Optional[object]


def _resolve_conn(connection):
    return _conn(connection or default_connection)


# ---------------------------------------------------------------------------
# Breakpoint set helpers
# ---------------------------------------------------------------------------

def set_breakpoint(
    address: str,
    connection=None,
    max_retries: Optional[int] = None,
    retry_interval_s: Optional[float] = None,
    symbol_reload_at: Optional[int] = None,
    symbol_reload_wait_s: Optional[float] = None,
) -> None:
    """Set an execution breakpoint at *address* (symbol name or memory address).

    Mirrors CAPL ``A_DBGR_BreakpointSet``.  Retries up to *max_retries* times
    with *retry_interval_s* delay to handle slow ELF symbol-table loading.
    After *symbol_reload_at* failed attempts a ``SYMBOL.RELOAD`` command is
    issued once before continuing to retry.

    Parameters
    ----------
    address:
        Symbol name or ``0xNNNN`` hex address (e.g. ``"myFunc"``,
        ``"0x80001234"``).
    connection:
        Optional connection override.
    max_retries:
        Override :attr:`~config.T32Settings.bp_max_retries`.
    retry_interval_s:
        Override :attr:`~config.T32Settings.bp_retry_interval_s`.
    symbol_reload_at:
        Override :attr:`~config.T32Settings.bp_symbol_reload_at`.
    symbol_reload_wait_s:
        Override :attr:`~config.T32Settings.symbol_reload_wait_s`.

    Raises
    ------
    T32SymbolError
        When *address* cannot be resolved after all retries.
    T32BreakpointError
        For other breakpoint-set failures.
    """
    conn = _resolve_conn(connection)

    retries = max_retries if max_retries is not None else settings.bp_max_retries
    interval = retry_interval_s if retry_interval_s is not None else settings.bp_retry_interval_s
    reload_at = symbol_reload_at if symbol_reload_at is not None else settings.bp_symbol_reload_at
    reload_wait = symbol_reload_wait_s if symbol_reload_wait_s is not None else settings.symbol_reload_wait_s

    # Clamp reload threshold so at least one retry occurs after SYMBOL.RELOAD.
    effective_reload_at = min(reload_at, retries - 1) if retries > 1 else retries

    logger.info("BREAK.SET '%s' (max_retries=%d).", address, retries)

    symbol_reload_done = False
    last_error: str = ""

    for attempt in range(1, retries + 1):
        # Issue SYMBOL.RELOAD once after effective_reload_at failed attempts.
        if not symbol_reload_done and attempt > effective_reload_at:
            logger.warning(
                "BREAK.SET still failing after %d attempts for '%s'. "
                "Issuing SYMBOL.RELOAD and waiting %.1fs…",
                effective_reload_at,
                address,
                reload_wait,
            )
            try:
                conn.cmd("SYMBOL.RELOAD")
            except Exception as exc:  # noqa: BLE001
                logger.warning("SYMBOL.RELOAD failed: %s", exc)
            time.sleep(reload_wait)
            symbol_reload_done = True

        try:
            conn.cmd(f"BREAK.SET {address}")
            logger.info("Breakpoint '%s' set (attempt %d/%d).", address, attempt, retries)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt < retries:
                logger.debug(
                    "BREAK.SET attempt %d/%d failed for '%s': %s. Retrying in %.2fs…",
                    attempt, retries, address, last_error, interval,
                )
                time.sleep(interval)

    # All retries exhausted.
    if "symbol" in last_error.lower() or "not found" in last_error.lower():
        raise T32SymbolError(address, last_error)
    raise T32BreakpointError(
        f"BREAK.SET '{address}' failed after {retries} attempt(s). Last error: {last_error}"
    )


def set_breakpoint_or_abort(address: str, connection=None) -> None:
    """Set breakpoint at *address*, raising immediately on failure.

    Convenience wrapper that converts any :class:`T32BreakpointError` /
    :class:`T32SymbolError` into a test-fatal exception.  Mirrors CAPL
    ``A_DBGR_BreakpointSet_AbortOnFail``.

    Raises
    ------
    T32BreakpointError
        On any breakpoint-set failure (caller should not catch this in a
        recoverable way – it signals a fatal test-setup issue).
    """
    set_breakpoint(address, connection=connection)


def set_breakpoint_write(address: str, connection=None) -> None:
    """Set a data-write watchpoint at *address*.

    Mirrors CAPL ``A_DBGR_BreakpointWrite``.  The ECU must be halted before
    setting hardware watchpoints on most Aurix targets.

    Parameters
    ----------
    address:
        Symbol name or address to watch for writes.
    connection:
        Optional connection override.

    Raises
    ------
    T32BreakpointError
        On failure.
    """
    conn = _resolve_conn(connection)
    wait_for_halt(connection=conn)
    logger.info("VAR.BREAK.SET '%s' /W (write watchpoint).", address)
    try:
        conn.cmd(f"VAR.BREAK.SET {address} /W")
    except Exception as exc:  # noqa: BLE001
        raise T32BreakpointError(
            f"Write watchpoint on '{address}' failed: {exc}"
        ) from exc


def set_breakpoint_read(address: str, connection=None) -> None:
    """Set a data-read watchpoint at *address*.

    Mirrors CAPL ``A_DBGR_BreakpointRead``.

    Parameters
    ----------
    address:
        Symbol name or address to watch for reads.
    connection:
        Optional connection override.

    Raises
    ------
    T32BreakpointError
        On failure.
    """
    conn = _resolve_conn(connection)
    wait_for_halt(connection=conn)
    logger.info("VAR.BREAK.SET '%s' /R (read watchpoint).", address)
    try:
        conn.cmd(f"VAR.BREAK.SET {address} /R")
    except Exception as exc:  # noqa: BLE001
        raise T32BreakpointError(
            f"Read watchpoint on '{address}' failed: {exc}"
        ) from exc


def delete_breakpoint(address: str, connection=None) -> None:
    """Delete the breakpoint at *address*.

    Mirrors CAPL ``A_DBGR_BreakpointDelete``.

    Parameters
    ----------
    address:
        Symbol name or address of the breakpoint to remove.
    connection:
        Optional connection override.

    Raises
    ------
    T32BreakpointError
        On failure.
    """
    conn = _resolve_conn(connection)
    logger.info("BREAK.DELETE '%s'.", address)
    try:
        conn.cmd(f"BREAK.DELETE {address}")
    except Exception as exc:  # noqa: BLE001
        raise T32BreakpointError(
            f"BREAK.DELETE '{address}' failed: {exc}"
        ) from exc


def delete_all_breakpoints(connection=None) -> None:
    """Remove all breakpoints from Trace32.

    Mirrors CAPL ``A_DBGR_BreakpointDeleteAll``.

    Parameters
    ----------
    connection:
        Optional connection override.

    Raises
    ------
    T32BreakpointError
        On failure.
    """
    conn = _resolve_conn(connection)
    logger.info("BREAK.DELETE (all breakpoints).")
    try:
        conn.cmd("BREAK.DELETE /ALL")
    except Exception as exc:  # noqa: BLE001
        raise T32BreakpointError(f"BREAK.DELETE /ALL failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Halt-check functions
# ---------------------------------------------------------------------------

def check_halted_at(
    address: str,
    timeout_s: Optional[float] = None,
    connection=None,
) -> bool:
    """Assert the ECU halted at *address* within *timeout_s*.

    Mirrors CAPL ``E_DBGR_BreakpointCheckForHalt``.  Waits for the ECU to
    halt and then evaluates whether ``P:R(PC) == address``.

    On real hardware, startup / initialization code may cause the ECU to halt
    at an intermediate address (e.g. the application entry point) *before*
    reaching the target breakpoint.  When this happens the function
    automatically issues GO again and retries, up to
    :attr:`~config.T32Settings.intermediate_halt_max_gos` times, with a
    :attr:`~config.T32Settings.intermediate_halt_go_delay_s` delay before
    each retry.  Set ``intermediate_halt_max_gos = 0`` to disable.

    Parameters
    ----------
    address:
        Expected symbol name or address at which the ECU should have stopped.
    timeout_s:
        Maximum seconds to wait for the ECU to halt.  Defaults to
        :attr:`~config.T32Settings.halt_timeout_s`.
    connection:
        Optional connection override.

    Returns
    -------
    bool
        ``True`` when the ECU halted at *address*.

    Raises
    ------
    T32BreakpointNotReachedError
        When the ECU did not halt within *timeout_s*.
    T32BreakpointError
        When the ECU halted but at a different address (and all retries
        have been exhausted).
    """
    conn = _resolve_conn(connection)
    tmo = timeout_s if timeout_s is not None else settings.halt_timeout_s
    max_intermediate = settings.intermediate_halt_max_gos
    go_delay = settings.intermediate_halt_go_delay_s

    _print(f"check_halted_at '{address}' (timeout={tmo:.1f}s, max_gos={max_intermediate})")

    for go_attempt in range(max_intermediate + 1):
        halted = wait_for_halt(timeout_s=tmo, connection=conn)
        if not halted:
            _print(f"check_halted_at '{address}': ECU did not halt within {tmo:.1f}s – FAIL.")
            raise T32BreakpointNotReachedError(address, int(tmo * 1000))

        # Evaluate EVAL (P:R(PC)==<address>)
        try:
            result = conn.fnc(f"(P:R(PC)=={address})")
            matched = str(result).strip().upper() in ("TRUE()", "TRUE", "1")
        except Exception as exc:  # noqa: BLE001
            raise T32BreakpointError(
                f"PC comparison for '{address}' failed: {exc}"
            ) from exc

        if matched:
            _print(f"check_halted_at '{address}': PASS ✓")
            logger.info("Breakpoint check PASS: halted at '%s'.", address)
            return True

        # ECU halted at the wrong address – query the full state so we can
        # give a precise log message and choose the right recovery action.
        if go_attempt < max_intermediate:
            state = get_ecu_state(conn)
            current_pc = get_pp_register(conn) or "unknown"

            if state == ECUState.DOWN:
                raise T32BreakpointError(
                    f"ECU powered down or disconnected (STATE.DOWN) while "
                    f"waiting for breakpoint at '{address}'. "
                    "Check power supply and debug-probe connection."
                )

            if state == ECUState.RESET:
                _print(
                    f"check_halted_at '{address}': ECU in RESET at PC={current_pc} – "
                    f"waiting {go_delay:.2f}s then re-issuing GO "
                    f"(retry {go_attempt + 1}/{max_intermediate})."
                )
                logger.warning(
                    "Breakpoint check: ECU in RESET state (PC=%s) – waiting "
                    "%.2fs for reset to complete, then re-issuing GO "
                    "(retry %d/%d).",
                    current_pc, go_delay, go_attempt + 1, max_intermediate,
                )
            elif state == ECUState.HALTED:
                _print(
                    f"check_halted_at '{address}': intermediate halt at PC={current_pc} – "
                    f"issuing GO (retry {go_attempt + 1}/{max_intermediate}, "
                    f"delay={go_delay:.2f}s)."
                )
                logger.warning(
                    "Breakpoint check: NOT at '%s' (PC=%s, state=halted) – "
                    "intermediate halt. Issuing GO to continue "
                    "(retry %d/%d, delay=%.2fs).",
                    address, current_pc, go_attempt + 1, max_intermediate, go_delay,
                )
            else:
                _print(
                    f"check_halted_at '{address}': unexpected state={state.value} "
                    f"at PC={current_pc} – re-issuing GO "
                    f"(retry {go_attempt + 1}/{max_intermediate})."
                )
                logger.warning(
                    "Breakpoint check: unexpected state %s (PC=%s) – "
                    "re-issuing GO (retry %d/%d).",
                    state.value, current_pc, go_attempt + 1, max_intermediate,
                )

            if go_delay > 0:
                time.sleep(go_delay)
            try:
                conn.cmd("GO")
            except Exception as exc:  # noqa: BLE001
                raise T32BreakpointError(
                    f"GO failed during {state.value} retry at PC={current_pc}: {exc}"
                ) from exc
            # Give the ECU time to leave the halted state before polling again.
            wait_for_running(connection=conn)
        else:
            current_pc = get_pp_register(conn) or "unknown"
            _print(
                f"check_halted_at '{address}': FAIL – halted at PC={current_pc}, "
                f"not at '{address}'."
            )
            logger.error("Breakpoint check FAIL: NOT halted at '%s'.", address)
            raise T32BreakpointError(f"ECU halted but NOT at '{address}'.")


def check_halted_at_core(
    address: str,
    core: str,
    timeout_s: Optional[float] = None,
    connection=None,
) -> bool:
    """Assert the ECU halted at *address* on *core*.

    Mirrors CAPL ``E_DBGR_BreakpointCheckForHaltCore``.  Like
    :func:`check_halted_at`, issues GO and retries on intermediate halts up to
    :attr:`~config.T32Settings.intermediate_halt_max_gos` times.

    Parameters
    ----------
    address:
        Expected symbol name or hex address.
    core:
        Core number as a string (e.g. ``"0"``, ``"1"``).
    timeout_s:
        Maximum seconds to wait.
    connection:
        Optional connection override.

    Returns
    -------
    bool
        ``True`` when the ECU halted at *address* on *core*.

    Raises
    ------
    T32BreakpointNotReachedError
        If the halt did not occur within *timeout_s*.
    T32BreakpointError
        If the ECU halted but at the wrong address or wrong core (and all
        intermediate-halt retries are exhausted).
    """
    conn = _resolve_conn(connection)
    tmo = timeout_s if timeout_s is not None else settings.halt_timeout_s
    max_intermediate = settings.intermediate_halt_max_gos
    go_delay = settings.intermediate_halt_go_delay_s

    for go_attempt in range(max_intermediate + 1):
        halted = wait_for_halt(timeout_s=tmo, connection=conn)
        if not halted:
            raise T32BreakpointNotReachedError(address, int(tmo * 1000))

        try:
            result = conn.fnc(f"(P:R(PC)=={address}&&CORE()=={core})")
            matched = str(result).strip().upper() in ("TRUE()", "TRUE", "1")
        except Exception as exc:  # noqa: BLE001
            raise T32BreakpointError(
                f"PC+core comparison for '{address}' core {core} failed: {exc}"
            ) from exc

        if matched:
            logger.info(
                "Breakpoint check PASS: halted at '%s' on core %s.", address, core
            )
            return True

        if go_attempt < max_intermediate:
            state = get_ecu_state(conn)
            current_pc = get_pp_register(conn) or "unknown"

            if state == ECUState.DOWN:
                raise T32BreakpointError(
                    f"ECU powered down or disconnected (STATE.DOWN) while "
                    f"waiting for breakpoint at '{address}' on core {core}. "
                    "Check power supply and debug-probe connection."
                )

            if state == ECUState.RESET:
                logger.warning(
                    "Breakpoint check: ECU in RESET state (PC=%s, core %s) – "
                    "waiting %.2fs for reset, then re-issuing GO "
                    "(retry %d/%d).",
                    current_pc, core, go_delay, go_attempt + 1, max_intermediate,
                )
            elif state == ECUState.HALTED:
                logger.warning(
                    "Breakpoint check: NOT at '%s' core %s (PC=%s, state=halted) – "
                    "intermediate halt. Issuing GO to continue "
                    "(retry %d/%d, delay=%.2fs).",
                    address, core, current_pc, go_attempt + 1, max_intermediate, go_delay,
                )
            else:
                logger.warning(
                    "Breakpoint check: unexpected state %s core %s (PC=%s) – "
                    "re-issuing GO (retry %d/%d).",
                    state.value, core, current_pc, go_attempt + 1, max_intermediate,
                )

            if go_delay > 0:
                time.sleep(go_delay)
            try:
                conn.cmd("GO")
            except Exception as exc:  # noqa: BLE001
                raise T32BreakpointError(
                    f"GO failed during {state.value} retry at PC={current_pc} "
                    f"core {core}: {exc}"
                ) from exc
            wait_for_running(connection=conn)
        else:
            logger.error(
                "Breakpoint check FAIL: NOT halted at '%s' on core %s.", address, core
            )
            raise T32BreakpointError(
                f"ECU halted but NOT at '{address}' on core {core}."
            )
