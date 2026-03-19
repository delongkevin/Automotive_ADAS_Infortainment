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

ECU State model
---------------
Trace32 exposes several PRACTICE boolean functions that together describe the
full target execution state.  :func:`get_ecu_state` queries all of them and
returns a typed :class:`ECUState` value that the framework uses to drive
control-flow decisions:

+-------------------+---------------------------+--------------------------------------------------+
| ECUState          | T32 expression            | What it means                                    |
+===================+===========================+==================================================+
| ``DOWN``          | SYStem.Mode() == "DOWN"   | Target powered off or debug probe disconnected.  |
|                   |                           | No commands will reach the ECU.                  |
|                   |                           | (Note: STATE.DOWN is a PRACTICE *command* —      |
|                   |                           | using STATE.DOWN() as a function produces the    |
|                   |                           | Trace32 message "don't use commands as           |
|                   |                           | functions".  Use SYStem.Mode() instead.)         |
+-------------------+---------------------------+--------------------------------------------------+
| ``RESET``         | STATE.RESET()             | T32 is holding the ECU in hardware reset.        |
|                   |                           | Wait ~800 ms (intermediate_halt_go_delay_s)      |
|                   |                           | before issuing GO.                               |
+-------------------+---------------------------+--------------------------------------------------+
| ``RUNNING``       | STATE.RUN()               | ECU is executing code.  Send stimulus or wait    |
|                   |                           | for a breakpoint halt.                           |
+-------------------+---------------------------+--------------------------------------------------+
| ``HALTED``        | all FALSE                 | ECU stopped at breakpoint or BREAK command.      |
|                   |                           | Safe to read/write variables and inspect the PC. |
+-------------------+---------------------------+--------------------------------------------------+
| ``UNKNOWN``       | (error)                   | Unable to determine state (comm error, T32 not   |
|                   |                           | connected).                                      |
+-------------------+---------------------------+--------------------------------------------------+

Public API
----------
- :class:`ECUState` – enum of all Trace32 target execution states.
- :func:`get_ecu_state` – query T32 and return a typed :class:`ECUState`.
- :func:`is_running` – ``True`` when ECU is in running state.
- :func:`is_reset` – ``True`` when ECU is held in hardware reset.
- :func:`is_down` – ``True`` when target is powered off / disconnected.
- :func:`go` – resume ECU execution (mirrors ``A_DBGR_Go``).
- :func:`go_safe` – resume with soft-reset / DOWN detection and retry.
- :func:`break_execution` – halt ECU execution (mirrors ``A_DBGR_Break``).
- :func:`reset_target` – reset ECU without reloading symbols (mirrors ``A_DBGR_R``).
- :func:`reset_and_go` – reset ECU and resume execution (mirrors ``A_DBGR_RnGo``).
- :func:`go_up` – step out of function (mirrors ``A_DBGR_GoUp``).
- :func:`step_over` – single-step over one source line (mirrors ``A_DBGR_StepOver``).
- :func:`wait_for_halt` – block until ECU halts or timeout.
- :func:`wait_for_running` – block until ECU is running or timeout.
"""

from __future__ import annotations

import sys
import time
from enum import Enum
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


def _print(msg: str) -> None:
    """Write a timestamped diagnostic line to stderr (always visible).

    Uses stderr so the message is not swallowed by stdout redirection or
    unittest's output capture.  Each line is prefixed with ``[T32]`` and a
    wall-clock timestamp so that timing relationships between commands are
    easy to read in failure logs.
    """
    ts = time.strftime("%H:%M:%S")
    print(f"[T32 {ts}] {msg}", file=sys.stderr, flush=True)

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
# ECU State model
# ---------------------------------------------------------------------------

class ECUState(Enum):
    """All possible Trace32 target execution states.

    Use :func:`get_ecu_state` to query the live state.  The enum values are
    plain strings so they produce readable log output without extra
    formatting.

    Priority when multiple T32 flags are set simultaneously:
    ``DOWN`` > ``RESET`` > ``RUNNING`` > ``HALTED`` > ``UNKNOWN``.
    """

    RUNNING = "running"
    """ECU is executing code (``STATE.RUN()`` is TRUE).
    Send CAN/power stimulus or wait for a breakpoint halt."""

    HALTED  = "halted"
    """ECU is stopped at a breakpoint or after a BREAK command.
    Variables and registers are safe to read/write.
    Issue GO to resume execution."""

    RESET   = "reset"
    """T32 is actively holding the ECU in hardware reset (``STATE.RESET()``
    is TRUE).  Wait ``intermediate_halt_go_delay_s`` (~800 ms) before
    issuing GO so the reset line has time to de-assert."""

    DOWN    = "down"
    """Target is powered off or the debug probe is disconnected.

    Detected via ``SYStem.Mode()`` returning ``"DOWN"``.

    .. note::
        ``STATE.DOWN`` is a PRACTICE **command** (not a function).  Using it
        as ``STATE.DOWN()`` in an expression produces the Trace32 status-window
        warning *"STATE.DOWN exists – don't use commands as functions"*.
        Always use ``SYStem.Mode()`` for connection-state queries.
    """

    UNKNOWN = "unknown"
    """State cannot be determined (T32 communication error or not connected).
    Check the RCL port and retry."""


# ---------------------------------------------------------------------------
# State query helpers
# ---------------------------------------------------------------------------

def _is_true(raw: str) -> bool:
    """Return ``True`` when a Trace32 PRACTICE boolean expression evaluates TRUE.

    Trace32 returns boolean results as the string ``"TRUE()"`` (with
    parentheses) or occasionally as ``"TRUE"`` or ``"1"``.  This helper
    normalises all three forms so callers do not need to repeat the
    comparison logic.
    """
    return raw.strip().upper() in ("TRUE()", "TRUE", "1")


def is_reset(connection=None) -> bool:
    """Return ``True`` when the ECU is being held in hardware reset by T32.

    Uses the PRACTICE expression ``STATE.RESET()`` which returns ``TRUE()``
    when Trace32 is actively holding the target CPU in reset (via the reset
    line).  In this state ``STATE.RUN()`` is ``FALSE`` and a plain ``GO``
    command has no effect until the reset line is released.

    After ``SYStem.RESetTarget`` T32 may hold the CPU in reset for ~800 ms
    while it rebuilds its internal state tables.  Callers should wait at
    least :attr:`~config.T32Settings.intermediate_halt_go_delay_s` (0.8 s
    by default) before issuing GO when ``is_reset()`` returns ``True``.

    Parameters
    ----------
    connection:
        Optional :class:`~connection.T32Connection` override.
    """
    conn = _conn(connection)
    try:
        result = conn.fnc("STATE.RESET()")
        return _is_true(result)
    except Exception as exc:  # noqa: BLE001
        logger.debug("is_reset() query failed: %s", exc)
        return False


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
        return _is_true(result)
    except Exception as exc:  # noqa: BLE001
        logger.debug("is_running() query failed: %s", exc)
        return False


def is_down(connection=None) -> bool:
    """Return ``True`` when the target is powered off or the probe is disconnected.

    Uses the PRACTICE **function** ``SYStem.Mode()`` which returns the current
    debug-connection mode as a string.  When the string is ``"DOWN"`` the target
    is not reachable and no ECU commands are possible.

    .. warning::
        ``STATE.DOWN`` is a PRACTICE **command**, not a function.  Evaluating
        ``STATE.DOWN()`` in an expression (via ``conn.fnc()``) causes the Trace32
        status-window message::

            STATE.DOWN exists – don't use commands as functions – Press F1 for more details.

        Use ``SYStem.Mode()`` instead, which is a proper function and returns the
        connection state as a readable string (``"DOWN"``, ``"UP"``, ``"ATTACH"``,
        ``"STANDBY"``, …).

    Parameters
    ----------
    connection:
        Optional :class:`~connection.T32Connection` override.
    """
    conn = _conn(connection)
    try:
        # SYStem.Mode() returns the debug-connection mode as a string.
        # Strip surrounding quotes that Trace32 sometimes includes.
        mode = conn.fnc("SYStem.Mode()").strip().strip('"').strip("'").upper()
        return mode == "DOWN"
    except Exception as exc:  # noqa: BLE001
        logger.debug("is_down() query failed: %s", exc)
        return False


def get_ecu_state(connection=None) -> "ECUState":
    """Query all Trace32 state expressions and return a typed :class:`ECUState`.

    This is the single authoritative state query for the framework.  It
    evaluates the T32 PRACTICE state functions in priority order and
    maps them to the appropriate :class:`ECUState` value:

    1. ``SYStem.Mode()=="DOWN"``  → :attr:`ECUState.DOWN`   – target not reachable
    2. ``STATE.RESET()``          → :attr:`ECUState.RESET`  – held in hardware reset
    3. ``STATE.RUN()``            → :attr:`ECUState.RUNNING` – actively executing
    4. all FALSE                  → :attr:`ECUState.HALTED`  – stopped at breakpoint
    5. error                      → :attr:`ECUState.UNKNOWN` – comm / query failure

    .. note::
        ``STATE.DOWN`` is a PRACTICE **command**, not a function.  Using it as
        ``STATE.DOWN()`` in an expression triggers the Trace32 status-window
        message *"STATE.DOWN exists – don't use commands as functions"*.
        The correct function for connection-state queries is ``SYStem.Mode()``,
        which returns a string (``"DOWN"``, ``"UP"``, ``"ATTACH"``, etc.).

    Use this function wherever the control-flow decision depends on the full
    target state (e.g. before issuing GO, after reset, after a breakpoint
    halt).

    Parameters
    ----------
    connection:
        Optional :class:`~connection.T32Connection` override.

    Returns
    -------
    ECUState
        One of the five typed state values described above.

    Examples
    --------
    ::

        state = get_ecu_state(conn)
        if state == ECUState.DOWN:
            raise RuntimeError("ECU is powered off – check PSU")
        if state == ECUState.RESET:
            time.sleep(0.8)          # wait for reset line to clear
            go(conn)
        elif state == ECUState.HALTED:
            v, i = psu.measure()     # safe to read variables now
            check_halted_at("myFunc", connection=conn)
    """
    conn = _conn(connection)
    try:
        # Query each flag directly so that any T32 communication error
        # propagates to the outer except clause and returns UNKNOWN.

        def _q(expr: str) -> bool:
            return _is_true(conn.fnc(expr))

        # DOWN: SYStem.Mode() is the correct PRACTICE *function* for the
        # debug-connection state.  STATE.DOWN is a PRACTICE *command* and
        # cannot be used as STATE.DOWN() in an expression – doing so produces
        # the Trace32 status-window message:
        #   "STATE.DOWN exists – don't use commands as functions"
        mode = conn.fnc("SYStem.Mode()").strip().strip('"').strip("'").upper()
        if mode == "DOWN":
            logger.debug("get_ecu_state() → DOWN (SYStem.Mode()=DOWN)")
            return ECUState.DOWN

        if _q("STATE.RESET()"):
            logger.debug("get_ecu_state() → RESET")
            return ECUState.RESET
        if _q("STATE.RUN()"):
            logger.debug("get_ecu_state() → RUNNING")
            return ECUState.RUNNING
        logger.debug("get_ecu_state() → HALTED (stopped at breakpoint)")
        return ECUState.HALTED
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_ecu_state() failed: %s – returning UNKNOWN.", exc)
        return ECUState.UNKNOWN


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

    Hard-reset handling
    ~~~~~~~~~~~~~~~~~~~
    If T32 is holding the ECU in reset (``STATE.RESET()`` is ``TRUE``),
    this function waits :attr:`~config.T32Settings.intermediate_halt_go_delay_s`
    (0.8 s by default) for the reset line to clear before issuing the ``GO``
    command.  Without this wait, ``GO`` is silently ignored and the ECU
    never starts executing, causing :func:`wait_for_running` to time out.

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

    # Query full state once so we can give a precise response.
    state = get_ecu_state(conn)
    _print(f"GO: pre-GO state = {state.value}")

    if state == ECUState.DOWN:
        raise T32ConnectionError(
            "GO: ECU is powered down or disconnected (STATE.DOWN). "
            "Verify the power supply is on and the debug probe is connected "
            "before issuing GO."
        )

    if state == ECUState.RESET:
        # T32 is holding the ECU in reset.  Wait for the reset line to clear
        # (~800 ms on Aurix TC4) before issuing GO, otherwise GO is ignored.
        _print(
            f"GO: ECU in RESET – waiting {settings.intermediate_halt_go_delay_s:.2f}s "
            "for reset line to clear before issuing GO."
        )
        logger.warning(
            "GO: ECU is in RESET state – waiting %.2fs for reset line to "
            "clear before issuing GO (intermediate_halt_go_delay_s).",
            settings.intermediate_halt_go_delay_s,
        )
        time.sleep(settings.intermediate_halt_go_delay_s)

    logger.info("GO: resuming ECU execution (state was %s).", state.value)
    _print("GO: issuing GO command …")
    conn.cmd("GO")

    # Brief pause before polling so the CPU bus has time to leave the halted
    # state.  Without this, STATE.RUN() can return FALSE immediately after GO
    # because the ECU hasn't been released yet (go_settle_s).
    if settings.go_settle_s > 0:
        time.sleep(settings.go_settle_s)

    # Wait until the ECU is confirmed running before returning.
    reached = wait_for_running(timeout_s=settings.run_timeout_s, connection=conn)
    if not reached:
        # The ECU may have run and immediately halted at a breakpoint — this
        # is not a failure.  Check the full state: if HALTED the ECU did
        # execute (it just hit a BP faster than our poll window), so we return
        # normally.  Only DOWN / UNKNOWN / still-RESET after the wait window
        # are treated as real failures.
        post_state = get_ecu_state(conn)
        if post_state == ECUState.HALTED:
            current_pc = get_pp_register(conn) or "unknown"
            _print(
                f"GO: ECU halted immediately at PC={current_pc} "
                "(hit breakpoint within go_settle_s window – this is normal)."
            )
            logger.warning(
                "GO: ECU did not show running state but is now HALTED at PC=%s. "
                "It ran and hit a breakpoint within the go_settle_s window (%.2fs). "
                "Treating as success.",
                current_pc, settings.go_settle_s,
            )
            return
        _print(
            f"GO: ECU did not enter running state within {settings.run_timeout_s}s "
            f"(post-GO state = {post_state.value})."
        )
        raise T32TimeoutError(
            f"ECU did not enter running state within {settings.run_timeout_s}s after GO. "
            "Check that the target is powered, the debug connection is active, and "
            "no breakpoint is set at the current PC."
        )

    _print("GO: ECU confirmed running.")


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
    _print(f"GO_SAFE: starting (max_retries={max_retries}) …")

    for attempt in range(1, max_retries + 1):
        # Query full state before issuing GO so we can react appropriately.
        state = get_ecu_state(conn)

        if state == ECUState.DOWN:
            _print(f"GO_SAFE: ECU is DOWN (attempt {attempt}/{max_retries}) – aborting.")
            logger.error(
                "GO_SAFE: ECU is powered down or disconnected (STATE.DOWN) "
                "on attempt %d/%d – aborting.", attempt, max_retries,
            )
            return False

        if state == ECUState.RESET:
            # T32 is holding the ECU in reset.  Wait for the reset line to
            # clear before issuing GO, otherwise GO is silently ignored.
            _print(
                f"GO_SAFE: ECU in RESET (attempt {attempt}/{max_retries}) – "
                f"waiting {settings.intermediate_halt_go_delay_s:.2f}s then GO."
            )
            logger.warning(
                "GO_SAFE: ECU in RESET state (attempt %d/%d). "
                "Waiting %.2fs for reset to complete before GO.",
                attempt, max_retries, settings.intermediate_halt_go_delay_s,
            )
            time.sleep(settings.intermediate_halt_go_delay_s)

        _print(f"GO_SAFE: issuing GO (attempt {attempt}/{max_retries}, state={state.value}) …")
        conn.cmd("GO")
        time.sleep(0.2)  # allow ECU to hit soft-reset if it will

        if is_running(conn):
            if attempt > 1:
                _print(f"GO_SAFE: ECU running (after {attempt - 1} retries).")
                logger.info("GO_SAFE: ECU running after %d retries.", attempt - 1)
            else:
                _print("GO_SAFE: ECU running.")
                logger.info("GO_SAFE: ECU running.")
            return True

        pp = get_pp_register(conn)
        if pp.lstrip("0").upper() == _RESET_VECTOR_HEX.lstrip("0").upper() or pp == "":
            _print(
                f"GO_SAFE: soft-reset detected (PC={pp}) on attempt {attempt}/{max_retries}."
            )
            logger.warning(
                "GO_SAFE: soft-reset detected (PC=%s) on attempt %d/%d.",
                pp, attempt, max_retries,
            )
        else:
            _print(
                f"GO_SAFE: ECU stopped at PC={pp} (non-reset) – continuing to check_halted_at."
            )
            logger.info(
                "GO_SAFE: ECU stopped at PC=%s (non-reset address) – "
                "returning; check_halted_at() will retry GO if not at target.",
                pp,
            )
            return True

    _print(f"GO_SAFE: giving up after {max_retries} retries (indefinite soft-resets).")
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
    _print("BREAK: halting ECU execution.")
    conn.cmd("BREAK")
    wait_for_halt(connection=conn)
    _print("BREAK: ECU halted.")


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
    _print("RESET: issuing SYStem.RESetTarget …")
    conn.cmd("SYStem.RESetTarget")

    # The ECU transitions through a brief RESET state immediately after the
    # reset command.  On Aurix TC4 this can last 200–500 ms.  Wait that time
    # before polling, otherwise wait_for_halt() may see the transient reset
    # phase as "still running" and time out prematurely.
    time.sleep(0.25)

    # If the ECU is still in RESET after the brief wait, give it more time.
    # This handles slower hardware where the reset release takes longer.
    reset_poll_count = 0
    while is_reset(conn) and reset_poll_count < 5:
        reset_poll_count += 1
        _print(
            f"RESET: ECU still in RESET state (poll {reset_poll_count}/5) – "
            f"waiting {settings.intermediate_halt_go_delay_s:.2f}s …"
        )
        logger.warning(
            "RESET: ECU still in RESET after initial wait (poll %d/5). "
            "Waiting %.2fs for reset line to clear.",
            reset_poll_count, settings.intermediate_halt_go_delay_s,
        )
        time.sleep(settings.intermediate_halt_go_delay_s)

    halted = wait_for_halt(connection=conn)
    if not halted:
        _print(
            f"RESET: ECU did not halt after reset within {settings.halt_timeout_s:.1f}s. "
            "Verify hardware and debug connection."
        )
        logger.error(
            "RESET: ECU did not halt after reset within %.1fs. "
            "The test case may fail — verify hardware and debug connection.",
            settings.halt_timeout_s,
        )
        return False

    _print("RESET: ECU halted (at reset vector).")

    # Extra settle time: lets T32 finish rebuilding its internal state
    # (register map, symbol table, memory map) after the reset sequence
    # completes.  Without this pause, subsequent variable reads or
    # breakpoint-set commands can fail because T32 is still processing.
    if settings.post_reset_settle_s > 0:
        _print(
            f"RESET: settling for {settings.post_reset_settle_s:.2f}s "
            "(post_reset_settle_s) …"
        )
        logger.debug(
            "RESET: waiting %.2fs for T32 post-reset settle (post_reset_settle_s).",
            settings.post_reset_settle_s,
        )
        time.sleep(settings.post_reset_settle_s)

    _print("RESET: complete – ECU ready.")
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
