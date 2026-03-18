"""
GM VIP Automation Framework – Debugger Execution-Control API
=============================================================
Provides high-level wrappers around the Trace32 execution-control commands:
GO, BREAK, SYStem.RESetTarget, Go.Up, and STEP.OVER.  Each function mirrors
the corresponding CAPL ``export testfunction`` in ``tsT32.cin`` but operates
entirely through the ``lauterbach.trace32.rcl`` (pyrcl) Python library.

All functions accept an optional :class:`T32Connection` object.  When one is
not supplied the module-level :data:`default_connection` is used.  This
pattern allows test scripts to set a global connection once and call module
functions without threading it through every call.

Public API
----------
- :func:`go` – resume ECU execution (mirrors ``A_DBGR_Go``).
- :func:`go_safe` – resume with soft-reset detection and retry.
- :func:`break_execution` – halt ECU execution (mirrors ``A_DBGR_Break``).
- :func:`reset_target` – reset ECU without reloading symbols (mirrors ``A_DBGR_R``).
- :func:`reset_and_go` – reset ECU and resume execution (mirrors ``A_DBGR_RnGo``).
- :func:`go_up` – step out of function (mirrors ``A_DBGR_GoUp``).
- :func:`step_over` – single-step over one source line (mirrors ``A_DBGR_StepOver``).
- :func:`is_running` – return ``True`` when ECU is in running state.
- :func:`wait_for_halt` – block until ECU halts or timeout.
- :func:`wait_for_running` – block until ECU is running or timeout.
"""

from __future__ import annotations

import time
from typing import Optional

from ..config import settings
from ..utils.exceptions import (
    T32CommandError,
    T32ConnectionError,
    T32TimeoutError,
)
from ..utils.logger import get_logger
from ..utils.retry import poll_until

logger = get_logger("debugger")

# Module-level default connection – set this once in your test setup.
default_connection = None  # type: Optional[object]

# Reset-vector address for soft-reset detection (Aurix TC4 / general ARM).
# Stored as a bare hex string (without 0x prefix) to match Trace32 R(PC) output.
_RESET_VECTOR_HEX = "0A0000000"
_MAX_SAFE_RETRIES = 25


def _conn(connection):
    """Return *connection* if given, else :data:`default_connection`."""
    c = connection or default_connection
    if c is None:
        raise T32ConnectionError(
            "No T32Connection provided and default_connection is not set."
        )
    return c


# ---------------------------------------------------------------------------
# State query helpers
# ---------------------------------------------------------------------------

def is_running(connection=None) -> bool:
    """Return ``True`` when the ECU is currently in the *running* state.

    Uses the PRACTICE expression ``STATE.RUN()`` which returns ``TRUE()``
    when the target CPU is executing code.

    Parameters
    ----------
    connection:
        :class:`~GM_VIP_Automation_Framework.core.connection.T32Connection`
        instance.  Falls back to :data:`default_connection`.
    """
    conn = _conn(connection)
    try:
        result = conn.fnc("STATE.RUN()")
        return result.strip().upper() in ("TRUE()", "TRUE", "1")
    except Exception as exc:  # noqa: BLE001
        logger.debug("is_running() query failed: %s", exc)
        return False


def get_state(connection=None) -> str:
    """Return the raw Trace32 state string (e.g. ``"running"``, ``"stopped"``).

    Uses the PRACTICE expression ``STATE.NAME()`` which produces a
    human-readable description of the current target state.
    """
    conn = _conn(connection)
    try:
        return conn.fnc("STATE.NAME()").strip()
    except Exception as exc:  # noqa: BLE001
        logger.debug("get_state() query failed: %s", exc)
        return "unknown"


def get_pp_register(connection=None) -> str:
    """Return the current program-pointer (PC) register value as a hex string."""
    conn = _conn(connection)
    try:
        return conn.fnc("R(PC)").strip()
    except Exception as exc:  # noqa: BLE001
        logger.debug("get_pp_register() query failed: %s", exc)
        return ""


def wait_for_halt(
    timeout_s: Optional[float] = None,
    connection=None,
) -> bool:
    """Block until the ECU enters a halted (not-running) state.

    Parameters
    ----------
    timeout_s:
        Maximum seconds to wait.  Defaults to
        :attr:`~config.T32Settings.halt_timeout_s`.
    connection:
        Optional connection override.

    Returns
    -------
    bool
        ``True`` if the ECU halted within *timeout_s*, ``False`` on timeout.
    """
    tmo = timeout_s if timeout_s is not None else settings.halt_timeout_s
    conn = _conn(connection)
    logger.debug("Waiting for ECU to halt (timeout=%.1fs)…", tmo)

    reached = poll_until(
        condition=lambda: not is_running(conn),
        timeout_s=tmo,
        interval_s=settings.poll_interval_s,
        description="ECU halt",
    )
    if not reached:
        logger.warning("ECU did not halt within %.1fs.", tmo)
    return reached


def wait_for_running(
    timeout_s: Optional[float] = None,
    connection=None,
) -> bool:
    """Block until the ECU enters the running state.

    Parameters
    ----------
    timeout_s:
        Maximum seconds to wait.  Defaults to
        :attr:`~config.T32Settings.run_timeout_s`.
    connection:
        Optional connection override.

    Returns
    -------
    bool
        ``True`` if the ECU started running within *timeout_s*.
    """
    tmo = timeout_s if timeout_s is not None else settings.run_timeout_s
    conn = _conn(connection)
    logger.debug("Waiting for ECU to start running (timeout=%.1fs)…", tmo)

    reached = poll_until(
        condition=lambda: is_running(conn),
        timeout_s=tmo,
        interval_s=settings.poll_interval_s,
        description="ECU running",
    )
    if not reached:
        logger.debug("ECU did not enter running state within %.1fs.", tmo)
    return reached


# ---------------------------------------------------------------------------
# Execution-control commands
# ---------------------------------------------------------------------------

def go(connection=None) -> None:
    """Resume ECU execution (equivalent to CAPL ``A_DBGR_Go``).

    If the ECU is already running the call is a no-op.

    Parameters
    ----------
    connection:
        Optional :class:`~connection.T32Connection` override.

    Raises
    ------
    T32CommandError
        If the GO command fails.
    T32TimeoutError
        If the ECU does not enter the running state within
        :attr:`~config.T32Settings.run_timeout_s` seconds.
    """
    conn = _conn(connection)

    if is_running(conn):
        logger.debug("GO: ECU already running.")
        return

    logger.info("GO: resuming ECU execution.")
    conn.cmd("GO")

    # Brief pause before polling so the CPU bus has time to leave the halted
    # state.  Without this, STATE.RUN() can return FALSE immediately after GO
    # because the ECU hasn't been released yet (go_settle_s).
    if settings.go_settle_s > 0:
        time.sleep(settings.go_settle_s)

    # Wait until the ECU is confirmed running before returning.  Raise a clear
    # error if it doesn't start — this prevents downstream checks from falsely
    # "passing" because the ECU is still halted at the reset vector.
    reached = wait_for_running(timeout_s=settings.run_timeout_s, connection=conn)
    if not reached:
        raise T32TimeoutError(
            f"ECU did not enter running state within {settings.run_timeout_s}s after GO. "
            "Check that the target is powered, the debug connection is active, and "
            "no breakpoint is set at the current PC."
        )


def go_safe(
    max_retries: int = _MAX_SAFE_RETRIES,
    connection=None,
) -> bool:
    """Resume ECU execution with soft-reset detection and retry.

    After each GO command the function checks whether the ECU stops
    immediately at the reset vector (``0A0000000``).  If so it retries GO
    automatically up to *max_retries* times before failing.

    Parameters
    ----------
    max_retries:
        Maximum number of GO retries before reporting failure.
    connection:
        Optional connection override.

    Returns
    -------
    bool
        ``True`` if the ECU is running (or stopped at a non-reset address),
        ``False`` if soft-resets exhausted all retries.
    """
    conn = _conn(connection)

    if is_running(conn):
        logger.debug("GO_SAFE: ECU already running.")
        return True

    logger.info("GO_SAFE: resuming ECU execution (max_retries=%d).", max_retries)

    for attempt in range(1, max_retries + 1):
        conn.cmd("GO")
        time.sleep(0.2)  # allow ECU to hit soft-reset if it will

        if is_running(conn):
            if attempt > 1:
                logger.info("GO_SAFE: ECU running after %d retries.", attempt - 1)
            else:
                logger.info("GO_SAFE: ECU running.")
            return True

        pp = get_pp_register(conn)
        if pp.lstrip("0").upper() == _RESET_VECTOR_HEX.lstrip("0").upper() or pp == "":
            logger.warning(
                "GO_SAFE: soft-reset detected (PC=%s) on attempt %d/%d.",
                pp, attempt, max_retries,
            )
        else:
            logger.info(
                "GO_SAFE: ECU stopped at PC=%s (non-reset address) – "
                "returning; check_halted_at() will retry GO if not at target.",
                pp,
            )
            return True

    logger.error(
        "GO_SAFE: indefinite soft-resets after %d retries – giving up.", max_retries
    )
    return False


def break_execution(connection=None) -> None:
    """Halt ECU execution (equivalent to CAPL ``A_DBGR_Break``).

    Parameters
    ----------
    connection:
        Optional connection override.
    """
    conn = _conn(connection)
    logger.info("BREAK: halting ECU execution.")
    conn.cmd("BREAK")
    wait_for_halt(connection=conn)


def reset_target(connection=None) -> bool:
    """Reset the ECU without reloading symbols (equivalent to CAPL ``A_DBGR_R``).

    Parameters
    ----------
    connection:
        Optional connection override.

    Returns
    -------
    bool
        ``True`` when the ECU reached a halted state after the reset.
        ``False`` when the ECU did not halt within
        :attr:`~config.T32Settings.halt_timeout_s` seconds — the caller
        should treat this as a non-fatal warning and decide whether to
        abort the test case.  No exception is raised because some targets
        (e.g. powertrain ECUs) require explicit GO+breakpoint sequences to
        reach a stable halted state after reset.
    """
    conn = _conn(connection)
    logger.info("RESET: sending SYStem.RESetTarget.")
    conn.cmd("SYStem.RESetTarget")
    # Brief wait for the transient "running" phase right after reset to pass.
    time.sleep(0.25)
    halted = wait_for_halt(connection=conn)
    if not halted:
        logger.error(
            "RESET: ECU did not halt after reset within %.1fs. "
            "The test case may fail — verify hardware and debug connection.",
            settings.halt_timeout_s,
        )
        return False

    # Extra settle time: lets T32 finish rebuilding its internal state
    # (register map, symbol table, memory map) after the reset sequence
    # completes.  Without this pause, subsequent variable reads or
    # breakpoint-set commands can fail because T32 is still processing.
    if settings.post_reset_settle_s > 0:
        logger.debug(
            "RESET: waiting %.2fs for T32 post-reset settle (post_reset_settle_s).",
            settings.post_reset_settle_s,
        )
        time.sleep(settings.post_reset_settle_s)

    return True


def reset_and_go(connection=None) -> bool:
    """Reset the ECU and immediately resume execution.

    Equivalent to CAPL ``A_DBGR_RnGo``.  All breakpoints are deleted before
    GO to prevent an immediate re-halt at a previously set breakpoint.

    Parameters
    ----------
    connection:
        Optional connection override.

    Returns
    -------
    bool
        ``True`` when the ECU entered the running state after the sequence.
    """
    conn = _conn(connection)
    logger.info("RESET_AND_GO: reset target, delete all breakpoints, then GO.")
    conn.cmd("SYStem.RESetTarget")
    time.sleep(0.25)
    conn.cmd("BREAK.DELETE /ALL")
    conn.cmd("GO")
    running = wait_for_running(connection=conn)
    if not running:
        logger.error("RESET_AND_GO: ECU did not start running.")
    return running


def go_up(connection=None) -> None:
    """Execute until the current function returns (equivalent to CAPL ``A_DBGR_GoUp``).

    Parameters
    ----------
    connection:
        Optional connection override.
    """
    conn = _conn(connection)
    logger.info("GO.UP: stepping out of current function.")
    conn.cmd("Go.Up")
    wait_for_halt(connection=conn)


def step_over(connection=None) -> None:
    """Execute a single source-level step over (equivalent to CAPL ``A_DBGR_StepOver``).

    Parameters
    ----------
    connection:
        Optional connection override.
    """
    conn = _conn(connection)
    logger.info("STEP.OVER: single source-level step.")
    conn.cmd("STEP.OVER")
    wait_for_halt(connection=conn)
