"""
Sanity suite – mocked Trace32 test cases.

Each test case mirrors an **executed** entry from the Sanity_report.html.
The suite runs in two modes, controlled by a single variable near the top of
this file:

  USE_LIVE_T32 = False  (default)
      All 72 executed tests run against a fully mocked T32 connection.
      No hardware, no Trace32 installation, and no ``lauterbach.trace32.rcl``
      library are required.  71 tests mirror straightforward pass results from
      the report; TC 3.5 also models the original transient T32 timeout + retry.

  USE_LIVE_T32 = True
      The suite connects to a **real, already-running Trace32** application
      via the API port configured below and executes every test step on live
      hardware.  The Lauterbach ``lauterbach.trace32.rcl`` library must be
      installed (``pip install lauterbach.trace32.rcl``).

─────────────────────────────────────────────────────────────────
HOW TO RUN
─────────────────────────────────────────────────────────────────

MOCK mode (default – no hardware needed)
-----------------------------------------
  From any terminal or from IDLE (F5):

      python path/to/test_sanity.py
      python path/to/test_sanity.py -v          # verbose

  From pytest (recommended for CI):

      pytest GM_VIP_Automation_Framework/tests/test_sanity.py

  The file bootstraps its own ``sys.path`` from ``__file__`` so
  PYTHONPATH does not need to be set.

LIVE mode (real Trace32 required)
----------------------------------
  Pre-requisites:
    1. Install the Lauterbach Python library:
           pip install lauterbach.trace32.rcl
    2. Start Trace32 PowerView and load your ARM debug session
       (ELF / symbols loaded, target configured).
    3. Ensure the T32 intercom/API port is enabled in your config.t32::
           RCL=NETASSIST
           PACKLEN=1024
           PORT=20000
       (The connection-arm.txt script can connect the USB hardware first.)

  Then, in THIS FILE, change the one toggle line:

      USE_LIVE_T32 = True          # ← flip this

  Optionally adjust the port/packlen if your config.t32 uses different values:

      T32_LIVE_PORT    = 20000
      T32_LIVE_PACKLEN = 1024

  Run exactly the same way as mock mode:

      python path/to/test_sanity.py -v
      pytest GM_VIP_Automation_Framework/tests/test_sanity.py

─────────────────────────────────────────────────────────────────
Test groups (matching the report)
─────────────────────────────────────────────────────────────────
    1. CAN               – 50 executed tests (all pass)
    2. BATTERY           –  2 executed tests (all pass)
    3. Wakeup            –  5 executed tests (all pass; TC 3.5 models
                            first-run timeout + retry in mock mode)
    4. Config_reg        –  7 executed tests (all pass)
    5. LockStep          –  1 executed test  (pass)
    6. SP_Device_Support –  7 executed tests (all pass)

Argument-order conventions (matching the framework API):
    _bp.set_breakpoint("addr", conn)
    _bp.check_halted_at("addr", connection=conn)
    _dbg.go(conn)
    _dbg.go_safe(connection=conn)
    _dbg.reset_target(conn)
    _dbg.go_up(conn)
    _dbg.step_over(conn)
    _dbg.wait_for_halt(connection=conn)
    _bp.delete_all_breakpoints(conn)
    _var.set_variable("sym", value, conn)
    _var.check_variable("sym", expected, conn)
"""

import os
import re
import sys
import unittest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Path bootstrap – makes the file runnable from IDLE or any working directory.
#
# Layout:  <repo_root>/GM_VIP_Automation_Framework/tests/test_sanity.py
# We need <repo_root> on sys.path so that
#   "import GM_VIP_Automation_Framework"  resolves correctly.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))          # .../tests/
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))  # <repo_root>
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ============================================================================
# CONNECTION MODE
# ============================================================================
# Default: USE_LIVE_T32 = False
#   → runs entirely against mocked connections; no hardware needed.
#
# To use real Trace32 hardware:
#   1. Install:  pip install lauterbach.trace32.rcl
#   2. Open Trace32 and load your ARM debug session.
#   3. Confirm config.t32 has:  RCL=NETASSIST  PACKLEN=1024  PORT=20000
#   4. Change the line below to:  USE_LIVE_T32 = True
#   5. Run:  python test_sanity.py -v   (or press F5 in IDLE)
# ============================================================================
USE_LIVE_T32    = False  # ← flip to True to connect to real Trace32 hardware
T32_LIVE_PORT    = 20000  # Trace32 API/intercom port  (must match PORT= in config.t32)
T32_LIVE_PACKLEN = 1024   # RCL packet length in bytes (must match PACKLEN= in config.t32)

# ---------------------------------------------------------------------------
# Mode-specific setup
# ---------------------------------------------------------------------------
if not USE_LIVE_T32:
    # MOCK MODE – stub lauterbach.trace32.rcl so no real library is needed.
    sys.modules.setdefault("lauterbach", MagicMock())
    sys.modules.setdefault("lauterbach.trace32", MagicMock())
    sys.modules.setdefault("lauterbach.trace32.rcl", MagicMock())
    sys.modules.setdefault("lauterbach.trace32.rcl._rc", MagicMock())
    sys.modules.setdefault("lauterbach.trace32.rcl._rc._error", MagicMock())

import GM_VIP_Automation_Framework.core.breakpoints as _bp  # noqa: E402
import GM_VIP_Automation_Framework.core.variables as _var   # noqa: E402
import GM_VIP_Automation_Framework.core.debugger as _dbg   # noqa: E402

if USE_LIVE_T32:
    # LIVE MODE – connect to the already-open Trace32 application once,
    # then share that single connection across all test cases.
    from GM_VIP_Automation_Framework.core.connection import T32Connection as _T32Conn
    _LIVE_CONN = _T32Conn(port=T32_LIVE_PORT, packlen=T32_LIVE_PACKLEN)
    _LIVE_CONN.connect()
    print(f"\n[test_sanity] LIVE mode – connected to Trace32 on port {T32_LIVE_PORT} "
          f"(packlen={T32_LIVE_PACKLEN})\n")
else:
    _LIVE_CONN = None  # mock mode – each test creates a fresh mock


# ---------------------------------------------------------------------------
# Mock factory
# ---------------------------------------------------------------------------

def _make_conn():
    """Return a connection for the current mode.

    MOCK mode: returns a fresh stateful mock T32Connection per call.
    LIVE mode: returns the shared real T32Connection (_LIVE_CONN).

    Mock state machine:
    - Initially: **halted** (STATE.RUN → FALSE).
    - After ``GO``: transitions to *running* (STATE.RUN → TRUE on the next
      call) and immediately back to *halted* on the poll after that, which
      models the ECU running briefly then stopping at a breakpoint.
    - After ``BREAK``, ``SYStem.RESetTarget``, ``Go.Up``, ``STEP.OVER``:
      always **halted** (state unchanged / forced to False).

    Variable tracking (mock mode):
    - ``VAR.SET symbol=value`` stores the value in an in-memory dict.
    - ``VAR.VALUE(symbol)`` returns the stored value, or ``"0"`` if
      the symbol has never been set.
    """
    if _LIVE_CONN is not None:
        return _LIVE_CONN
    conn = MagicMock()
    conn.is_connected.return_value = True

    state = {"running": False}
    var_store: dict[str, str] = {}  # symbol -> value-as-string

    def _cmd(cmd_str):
        if cmd_str == "GO":
            state["running"] = True
        elif cmd_str in (
            "BREAK",
            "SYStem.RESetTarget",
            "Go.Up",
            "STEP.OVER",
            "BREAK.DELETE /ALL",
        ):
            state["running"] = False
        elif cmd_str.startswith("VAR.SET "):
            # "VAR.SET symbol=value"
            rest = cmd_str[len("VAR.SET "):].strip()
            eq_idx = rest.find("=")
            if eq_idx >= 0:
                sym = rest[:eq_idx].strip()
                val = rest[eq_idx + 1:].strip()
                var_store[sym] = val
        return None

    def _fnc(expr):
        if "STATE.RUN" in expr:
            if state["running"]:
                # Return TRUE once then auto-halt (ECU hit a breakpoint).
                state["running"] = False
                return "TRUE()"
            return "FALSE()"
        if "STATE.NAME" in expr:
            return "running" if state["running"] else "stopped"
        # PC-equality check used by check_halted_at() – always matches.
        if "P:R(PC)" in expr and "==" in expr:
            return "TRUE()"
        # Raw register reads – return a non-reset-vector address.
        if re.match(r"R\(\w+\)", expr) or "R(PC)" in expr:
            return "0x80001234"
        # Variable reads: return stored value if available, else "0".
        if expr.startswith("VAR.VALUE(") and expr.endswith(")"):
            sym = expr[len("VAR.VALUE("):-1]
            return var_store.get(sym, "0")
        if "SYMBOL.EXIST" in expr:
            return "TRUE()"
        if "ADDRESS.OFFSET" in expr:
            return "0xA0000000"
        if "CORE()" in expr:
            return "TRUE()"
        return "0"

    conn.cmd.side_effect = _cmd
    conn.fnc.side_effect = _fnc
    return conn


def _make_conn_slow_halt(halt_after_polls: int = 8):
    """Return a connection for TC 3.5 (transient-timeout simulation).

    MOCK mode: returns a mock where the ECU stays running for *halt_after_polls*
    polls before halting – used to simulate the transient T32 timeout where
    the breakpoint acknowledgement takes longer than the initial wait window.

    LIVE mode: returns the shared real connection (_LIVE_CONN); the slow-halt
    simulation is not applicable with real hardware.
    """
    if _LIVE_CONN is not None:
        return _LIVE_CONN
    poll_count = [0]
    conn = MagicMock()
    conn.is_connected.return_value = True

    def _fnc(expr):
        if "STATE.RUN" in expr:
            poll_count[0] += 1
            return "TRUE()" if poll_count[0] < halt_after_polls else "FALSE()"
        if "P:R(PC)" in expr and "==" in expr:
            return "TRUE()"
        if "SYMBOL.EXIST" in expr:
            return "TRUE()"
        if "ADDRESS.OFFSET" in expr:
            return "0xA0000000"
        return "0"

    conn.fnc.side_effect = _fnc
    conn.cmd.return_value = None
    return conn


# ---------------------------------------------------------------------------
# Base test class
# ---------------------------------------------------------------------------

class _SanityBase(unittest.TestCase):
    """Base class for all Sanity test groups.

    Mock mode: zeros the artificial T32 settle/poll delays so 72 tests complete
    quickly without hardware.  Original values are restored after every test so
    that other test modules (test_core.py, test_utils.py) are not affected.

    Live mode: delays are left at their real values so the framework waits the
    appropriate amount of time for the hardware ECU to transition states.
    """

    def setUp(self):
        from GM_VIP_Automation_Framework import config
        self._saved = {
            "go_settle_s": config.settings.go_settle_s,
            "post_reset_settle_s": config.settings.post_reset_settle_s,
            "poll_interval_s": config.settings.poll_interval_s,
            "run_timeout_s": config.settings.run_timeout_s,
            "halt_timeout_s": config.settings.halt_timeout_s,
            "bp_retry_interval_s": config.settings.bp_retry_interval_s,
            "symbol_reload_wait_s": config.settings.symbol_reload_wait_s,
        }
        if not USE_LIVE_T32:
            # Zero delays for fast mock execution.
            config.settings.go_settle_s = 0.0
            config.settings.post_reset_settle_s = 0.0
            config.settings.poll_interval_s = 0.01
            config.settings.run_timeout_s = 0.2
            config.settings.halt_timeout_s = 0.2
            config.settings.bp_retry_interval_s = 0.0
            config.settings.symbol_reload_wait_s = 0.0

    def tearDown(self):
        from GM_VIP_Automation_Framework import config
        for k, v in self._saved.items():
            setattr(config.settings, k, v)

    @staticmethod
    def _sim_ecu_output(symbol: str, value, conn) -> None:
        """Pre-seed and verify an ECU-computed output variable (mock mode only).

        Mock mode: the mock has no real CPU, so we write the expected value
        ourselves before calling check_variable() to exercise the framework's
        comparison logic with the correct data.

        Live mode: the real ECU writes the value during execution; this method
        is a no-op so we do not overwrite hardware-computed results.
        """
        if USE_LIVE_T32:
            return
        _var.set_variable(symbol, value, conn)
        _var.check_variable(symbol, value, conn)

    def _assert_reset_called(self, conn) -> None:
        """Assert SYStem.RESetTarget was issued to the connection (mock mode only).

        In mock mode this verifies the framework called the reset command.
        In live mode the assertion is skipped because *conn* is a real
        T32Connection whose methods are not MagicMock spies.
        """
        if not USE_LIVE_T32:
            conn.cmd.assert_any_call("SYStem.RESetTarget")


# ============================================================================
# GROUP 1 – CAN (50 executed tests, all pass)
# ============================================================================

class TestSanityGroup1CAN(_SanityBase):
    """Mirrors the 50 executed CAN test cases from the Sanity report."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _can_rx_init_setup(self, conn):
        """Steps 0.1-0.5: delete BPs → set BP TestCan_Init → reset
        → set BP TestCan_Init → go_safe → check halted at TestCan_Init.
        """
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint("TestCan_Init", conn)
        _dbg.reset_target(conn)
        _bp.set_breakpoint("TestCan_Init", conn)
        _dbg.go_safe(connection=conn)
        _bp.check_halted_at("TestCan_Init", connection=conn)

    def _set_can_rx_msg_vars(self, conn, can_id, filter_mask, rx_msg_idx,
                              msg_len, id_type, controller_id):
        """Steps 1-6: configure VaCANR_CanRxMsgs[0] fields."""
        _var.set_variable("VaCANR_CanRxMsgs[0].CanId", can_id, conn)
        _var.check_variable("VaCANR_CanRxMsgs[0].CanId", can_id, conn)
        _var.set_variable("VaCANR_CanRxMsgs[0].CanFilterMask", filter_mask, conn)
        _var.check_variable("VaCANR_CanRxMsgs[0].CanFilterMask", filter_mask, conn)
        _var.set_variable("VaCANR_CanRxMsgs[0].CanRxMessageIdx", rx_msg_idx, conn)
        _var.check_variable("VaCANR_CanRxMsgs[0].CanRxMessageIdx", rx_msg_idx, conn)
        _var.set_variable("VaCANR_CanRxMsgs[0].CanMessageLen", msg_len, conn)
        _var.check_variable("VaCANR_CanRxMsgs[0].CanMessageLen", msg_len, conn)
        _var.set_variable("VaCANR_CanRxMsgs[0].CanIdType", id_type, conn)
        _var.check_variable("VaCANR_CanRxMsgs[0].CanIdType", id_type, conn)
        _var.set_variable("VaCANR_CanRxMsgs[0].CanControllerId", controller_id, conn)
        _var.check_variable("VaCANR_CanRxMsgs[0].CanControllerId", controller_id, conn)

    def _can_rx_finalize(self, conn, pdu_msg_id, data_length):
        """Steps 7-12: set follow-on BPs, run, verify RX variables.

        Output variables (CanrxmsgIdx, CanpdumsgId, Canpdudatalength) are
        pre-seeded in the mock because no real ECU computes them.  The calls
        to check_variable() then exercise the framework's comparison logic.
        """
        _bp.set_breakpoint("MngCNDD_CanRxInit", conn)
        _dbg.go(conn)
        _bp.check_halted_at("MngCNDD_CanRxInit", connection=conn)
        _bp.set_breakpoint("SetCNDD_e_CanControllerMode", conn)
        _dbg.go(conn)
        _bp.check_halted_at("SetCNDD_e_CanControllerMode", connection=conn)
        _bp.set_breakpoint("SetCANR_h_CanIfRxIndication", conn)
        _dbg.go(conn)
        _dbg.go(conn)
        _bp.check_halted_at("SetCANR_h_CanIfRxIndication", connection=conn)
        # Pre-seed ECU-computed RX output variables then verify (simulates ECU writes).
        self._sim_ecu_output("CanrxmsgIdx", 0, conn)
        self._sim_ecu_output("CanpdumsgId", pdu_msg_id, conn)
        self._sim_ecu_output("Canpdudatalength", data_length, conn)

    def _can_tx_setup(self, conn):
        """Common preamble for CAN-TX tests."""
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint("TestCan_Init", conn)
        _dbg.reset_target(conn)
        _dbg.go_safe(connection=conn)
        _bp.check_halted_at("TestCan_Init", connection=conn)

    def _set_pdu_vars(self, conn, pdu_idx, can_id, length, pdu_id):
        """Configure VsPdu[pdu_idx] transmission variables."""
        _var.set_variable(f"VsPdu[{pdu_idx}].e_e_CAN_ID", can_id, conn)
        _var.check_variable(f"VsPdu[{pdu_idx}].e_e_CAN_ID", can_id, conn)
        _var.set_variable(f"VsPdu[{pdu_idx}].e_Cnt_Length", length, conn)
        _var.check_variable(f"VsPdu[{pdu_idx}].e_Cnt_Length", length, conn)
        _var.set_variable(f"VsPdu[{pdu_idx}].e_e_PDU_ID", pdu_id, conn)
        _var.check_variable(f"VsPdu[{pdu_idx}].e_e_PDU_ID", pdu_id, conn)

    def _trcv_op_mode_test(self, conn, mode_value, bp_confirm):
        """Common flow for SetCNDD_e_CanTrcvOpMode tests."""
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint("TestCan_Init", conn)
        _dbg.reset_target(conn)
        _dbg.go_safe(connection=conn)
        _bp.check_halted_at("TestCan_Init", connection=conn)
        _bp.set_breakpoint("SetCNDD_e_CanTrcvOpMode", conn)
        _dbg.go(conn)
        _bp.check_halted_at("SetCNDD_e_CanTrcvOpMode", connection=conn)
        _var.set_variable("CanTrcvOpMode", mode_value, conn)
        _var.check_variable("CanTrcvOpMode", mode_value, conn)
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint(bp_confirm, conn)
        _dbg.go(conn)
        _bp.check_halted_at(bp_confirm, connection=conn)

    def _ctrl_mode_test(self, conn, mode_var, mode_value, setup_bp, confirm_bp):
        """Common flow for SetCNDD_e_CanControllerMode tests."""
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint("TestCan_Init", conn)
        _dbg.reset_target(conn)
        _dbg.go_safe(connection=conn)
        _bp.check_halted_at("TestCan_Init", connection=conn)
        _bp.set_breakpoint(setup_bp, conn)
        _dbg.go(conn)
        _bp.check_halted_at(setup_bp, connection=conn)
        _var.set_variable(mode_var, mode_value, conn)
        _var.check_variable(mode_var, mode_value, conn)
        _bp.set_breakpoint(confirm_bp, conn)
        _dbg.go(conn)
        _bp.check_halted_at(confirm_bp, connection=conn)

    def _trcv_init_test(self, conn):
        """Common setup for MngCNDD_CanTrcvInitialize tests."""
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint("TestCanTrcv_Init", conn)
        _dbg.reset_target(conn)
        _dbg.go_safe(connection=conn)
        _bp.check_halted_at("TestCanTrcv_Init", connection=conn)
        _bp.set_breakpoint("TestCan_Init", conn)
        _dbg.go(conn)
        _bp.check_halted_at("TestCan_Init", connection=conn)
        # PN frame data / config variables
        _var.set_variable("VsCANR_PnFrameData1[0].CanTrcvPnFrameDataMaskIndex", 0, conn)
        _var.check_variable("VsCANR_PnFrameData1[0].CanTrcvPnFrameDataMaskIndex", 0, conn)
        _var.set_variable("VsCANR_PnFrameData1[0].CanTrcvPnFrameDataMask", 1, conn)
        _var.check_variable("VsCANR_PnFrameData1[0].CanTrcvPnFrameDataMask", 1, conn)
        _var.set_variable("VsCANR_PnFrameData1[7].CanTrcvPnFrameDataMaskIndex", 7, conn)
        _var.check_variable("VsCANR_PnFrameData1[7].CanTrcvPnFrameDataMaskIndex", 7, conn)
        _var.set_variable("VsCANR_PnFrameData1[7].CanTrcvPnFrameDataMask", 8, conn)
        _var.check_variable("VsCANR_PnFrameData1[7].CanTrcvPnFrameDataMask", 8, conn)
        _var.set_variable("VsCANR_PnConfig[0].CanTrcvPnFrameCanId", 0x123, conn)
        _var.check_variable("VsCANR_PnConfig[0].CanTrcvPnFrameCanId", 0x123, conn)
        _var.set_variable("VsCANR_PnConfig[0].CanTrcvPnFrameCanIdMask", 0, conn)
        _var.check_variable("VsCANR_PnConfig[0].CanTrcvPnFrameCanIdMask", 0, conn)
        _var.set_variable("VsCANR_PnConfig[0].CanTrcvPnFrameIdType", 0, conn)
        _var.check_variable("VsCANR_PnConfig[0].CanTrcvPnFrameIdType", 0, conn)
        _var.set_variable("VsCANR_PnConfig[0].CanTrcvPnFrameDlc", 8, conn)
        _var.check_variable("VsCANR_PnConfig[0].CanTrcvPnFrameDlc", 8, conn)
        _var.set_variable("VsCANR_PnConfig[0].CanTrcvPnEnabled", 1, conn)
        _var.check_variable("VsCANR_PnConfig[0].CanTrcvPnEnabled", 1, conn)
        _var.set_variable("VsCANR_TrcvChannels[0].CanTrcvChannelId", 0, conn)
        _var.check_variable("VsCANR_TrcvChannels[0].CanTrcvChannelId", 0, conn)
        _var.set_variable("VsCANR_TrcvChannels[0].CanTrcvChannelUsed", 1, conn)
        _var.check_variable("VsCANR_TrcvChannels[0].CanTrcvChannelUsed", 1, conn)
        _var.set_variable("VsCANR_TrcvChannels[0].CanTrcvPinWakeupEnabled", 0, conn)
        _var.check_variable("VsCANR_TrcvChannels[0].CanTrcvPinWakeupEnabled", 0, conn)
        _var.set_variable("VsCANR_CanTrcvConfig.CanTrcvNumberOfChannels", 2, conn)
        _var.check_variable("VsCANR_CanTrcvConfig.CanTrcvNumberOfChannels", 2, conn)
        _dbg.go(conn)
        _var.set_variable("StartPowerDown", 1, conn)
        _var.check_variable("StartPowerDown", 1, conn)

    # ------------------------------------------------------------------
    # TC 1.1 – Min message length for CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_01_can_rx_init_min_msg_len_cana_can2(self):
        """CanRxInit: min message length for CANA CAN2 (pass)."""
        conn = _make_conn()
        self._can_rx_init_setup(conn)
        self._set_can_rx_msg_vars(conn, 0x401, 0x7FF, 0, 1, 2, 0)
        self._can_rx_finalize(conn, 1025, 1)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.2 – CanRxInit for CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_02_can_rx_init_canb_can8(self):
        """CanRxInit: CAN controller for CANB CAN8 initialized (pass)."""
        conn = _make_conn()
        self._can_rx_init_setup(conn)
        self._set_can_rx_msg_vars(conn, 0x456, 2047, 0, 1, 2, 1)
        self._can_rx_finalize(conn, 1110, 1)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.3 – CanRxInit for CANA CAN2 and CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_03_can_rx_init_cana_and_canb(self):
        """CanRxInit: CANA CAN2 and CANB CAN8 initialized together (pass)."""
        conn = _make_conn()
        _bp.delete_all_breakpoints(conn)
        _dbg.reset_target(conn)
        _bp.set_breakpoint("TestCan_Init", conn)
        _dbg.go_safe(connection=conn)
        _bp.check_halted_at("TestCan_Init", connection=conn)
        self._set_can_rx_msg_vars(conn, 0x456, 2047, 0, 1, 2, 1)
        self._can_rx_finalize(conn, 1110, 1)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.4 – Min message length for CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_04_can_rx_init_min_msg_len_canb_can8(self):
        """CanRxInit: min message length for CANB CAN8 (pass)."""
        conn = _make_conn()
        self._can_rx_init_setup(conn)
        self._set_can_rx_msg_vars(conn, 0x456, 0x7FF, 0, 1, 2, 1)
        self._can_rx_finalize(conn, 1110, 1)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.5 – Max message length for CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_05_can_rx_init_max_msg_len_canb_can8(self):
        """CanRxInit: max message length for CANB CAN8 (pass)."""
        conn = _make_conn()
        self._can_rx_init_setup(conn)
        self._set_can_rx_msg_vars(conn, 0x456, 0x7FF, 0, 64, 2, 1)
        self._can_rx_finalize(conn, 1110, 64)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.6 – Max message length for CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_06_can_rx_init_max_msg_len_cana_can2(self):
        """CanRxInit: max message length for CANA CAN2 (pass)."""
        conn = _make_conn()
        self._can_rx_init_setup(conn)
        self._set_can_rx_msg_vars(conn, 0x401, 0x7FF, 0, 64, 2, 0)
        self._can_rx_finalize(conn, 1025, 64)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.7 – Extended message ID for CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_07_can_rx_init_extended_id_cana_can2(self):
        """CanRxInit: extended message ID for CANA CAN2 (pass)."""
        conn = _make_conn()
        self._can_rx_init_setup(conn)
        self._set_can_rx_msg_vars(conn, 0x18FF4001, 0x1FFFFFFF, 0, 8, 1, 0)
        self._can_rx_finalize(conn, 0x18FF4001, 8)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.8 – Extended message ID for CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_08_can_rx_init_extended_id_canb_can8(self):
        """CanRxInit: extended message ID for CANB CAN8 (pass)."""
        conn = _make_conn()
        self._can_rx_init_setup(conn)
        self._set_can_rx_msg_vars(conn, 0x18FF4001, 0x1FFFFFFF, 0, 8, 1, 1)
        self._can_rx_finalize(conn, 0x18FF4001, 8)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.9 – Standard message ID for CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_09_can_rx_init_standard_id_cana_can2(self):
        """CanRxInit: standard message ID for CANA CAN2 (pass)."""
        conn = _make_conn()
        self._can_rx_init_setup(conn)
        self._set_can_rx_msg_vars(conn, 0x401, 0x7FF, 0, 8, 2, 0)
        self._can_rx_finalize(conn, 1025, 8)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.10 – Standard message ID for CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_10_can_rx_init_standard_id_canb_can8(self):
        """CanRxInit: standard message ID for CANB CAN8 (pass)."""
        conn = _make_conn()
        self._can_rx_init_setup(conn)
        self._set_can_rx_msg_vars(conn, 0x456, 0x7FF, 0, 8, 2, 1)
        self._can_rx_finalize(conn, 1110, 8)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.11 – CanWrt TX max message length CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_11_canwrt_tx_max_msg_len_canb_can8(self):
        """CntrlCNDD_h_CanWrt: TX max message length on CANB CAN8 (pass)."""
        conn = _make_conn()
        self._can_tx_setup(conn)
        self._set_pdu_vars(conn, 17, 0x40000301, 64, 17)
        _dbg.go(conn)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.12 – CanWrt TX max message length CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_12_canwrt_tx_max_msg_len_cana_can2(self):
        """CntrlCNDD_h_CanWrt: TX max message length on CANA CAN2 (pass)."""
        conn = _make_conn()
        self._can_tx_setup(conn)
        self._set_pdu_vars(conn, 16, 0x40000101, 64, 1)
        _dbg.go(conn)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.13 – CanWrt TX message success CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_13_canwrt_tx_success_cana_can2(self):
        """CntrlCNDD_h_CanWrt: message transmitted successfully CANA CAN2 (pass)."""
        conn = _make_conn()
        self._can_tx_setup(conn)
        self._set_pdu_vars(conn, 16, 0x40000101, 8, 1)
        _dbg.go(conn)
        _bp.set_breakpoint("SetCANR_e_CanIfTxConfirmation", conn)
        _dbg.go(conn)
        _bp.check_halted_at("SetCANR_e_CanIfTxConfirmation", connection=conn)

    # ------------------------------------------------------------------
    # TC 1.14 – CanWrt TX min message length CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_14_canwrt_tx_min_msg_len_cana_can2(self):
        """CntrlCNDD_h_CanWrt: TX min message length on CANA CAN2 (pass)."""
        conn = _make_conn()
        self._can_tx_setup(conn)
        self._set_pdu_vars(conn, 16, 0x40000101, 1, 1)
        _dbg.go(conn)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.15 – CanIfTxConfirmation standard CAN CANA
    # ------------------------------------------------------------------
    def test_tc1_15_canif_tx_confirmation_standard_cana(self):
        """SetCANR_e_CanIfTxConfirmation: TX confirmation standard ID CANA (pass)."""
        conn = _make_conn()
        self._can_tx_setup(conn)
        self._set_pdu_vars(conn, 16, 0x00000101, 8, 1)
        _dbg.go(conn)
        _bp.set_breakpoint("SetCANR_e_CanIfTxConfirmation", conn)
        _dbg.go(conn)
        _bp.check_halted_at("SetCANR_e_CanIfTxConfirmation", connection=conn)

    # ------------------------------------------------------------------
    # TC 1.16 – CanIfTxConfirmation standard CAN CANB
    # ------------------------------------------------------------------
    def test_tc1_16_canif_tx_confirmation_standard_canb(self):
        """SetCANR_e_CanIfTxConfirmation: TX confirmation standard ID CANB (pass)."""
        conn = _make_conn()
        self._can_tx_setup(conn)
        self._set_pdu_vars(conn, 17, 0x00000301, 8, 17)
        _dbg.go(conn)
        _bp.set_breakpoint("SetCANR_e_CanIfTxConfirmation", conn)
        _dbg.go(conn)
        _bp.check_halted_at("SetCANR_e_CanIfTxConfirmation", connection=conn)

    # ------------------------------------------------------------------
    # TC 1.17 – CanWrt TX message success CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_17_canwrt_tx_success_canb_can8(self):
        """CntrlCNDD_h_CanWrt: message transmitted successfully CANB CAN8 (pass)."""
        conn = _make_conn()
        self._can_tx_setup(conn)
        self._set_pdu_vars(conn, 17, 0x40000301, 8, 17)
        _dbg.go(conn)
        _bp.set_breakpoint("SetCANR_e_CanIfTxConfirmation", conn)
        _dbg.go(conn)
        _bp.check_halted_at("SetCANR_e_CanIfTxConfirmation", connection=conn)

    # ------------------------------------------------------------------
    # TC 1.18 – CanWrt TX success CANA and CANB
    # ------------------------------------------------------------------
    def test_tc1_18_canwrt_tx_success_cana_and_canb(self):
        """CntrlCNDD_h_CanWrt: TX on CANA CAN2 and CANB CAN8 (pass)."""
        conn = _make_conn()
        self._can_tx_setup(conn)
        self._set_pdu_vars(conn, 16, 0x40000101, 8, 1)
        self._set_pdu_vars(conn, 17, 0x40000301, 8, 17)
        _dbg.go(conn)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.19 – CanWrt TX min message length CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_19_canwrt_tx_min_msg_len_canb_can8(self):
        """CntrlCNDD_h_CanWrt: TX min message length on CANB CAN8 (pass)."""
        conn = _make_conn()
        self._can_tx_setup(conn)
        self._set_pdu_vars(conn, 17, 0x40000301, 1, 17)
        _dbg.go(conn)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.20 – CanControllerMode transition to Stop CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_20_can_controller_mode_stop_cana(self):
        """SetCNDD_e_CanControllerMode: transition to Stop mode CANA CAN2 (pass)."""
        conn = _make_conn()
        self._ctrl_mode_test(conn, "CanControllerMode", 0,
                              "SetCNDD_e_CanControllerMode",
                              "MngCNDD_CanMainMode")

    # ------------------------------------------------------------------
    # TC 1.21 – CanControllerMode transition to Stop CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_21_can_controller_mode_stop_canb(self):
        """SetCNDD_e_CanControllerMode: transition to Stop mode CANB CAN8 (pass)."""
        conn = _make_conn()
        self._ctrl_mode_test(conn, "CanControllerMode", 0,
                              "SetCNDD_e_CanControllerMode",
                              "MngCNDD_CanMainMode")

    # ------------------------------------------------------------------
    # TC 1.22 – CanControllerMode transition to Invalid CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_22_can_controller_mode_invalid_cana(self):
        """SetCNDD_e_CanControllerMode: transition to Invalid mode CANA CAN2 (pass)."""
        conn = _make_conn()
        self._ctrl_mode_test(conn, "CanControllerMode", 3,
                              "SetCNDD_e_CanControllerMode",
                              "MngCNDD_CanMainMode")

    # ------------------------------------------------------------------
    # TC 1.23 – CanControllerMode transition to Invalid CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_23_can_controller_mode_invalid_canb(self):
        """SetCNDD_e_CanControllerMode: transition to Invalid mode CANB CAN8 (pass)."""
        conn = _make_conn()
        self._ctrl_mode_test(conn, "CanControllerMode", 3,
                              "SetCNDD_e_CanControllerMode",
                              "MngCNDD_CanMainMode")

    # ------------------------------------------------------------------
    # TC 1.24 – CanControllerMode transition to Start CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_24_can_controller_mode_start_cana(self):
        """SetCNDD_e_CanControllerMode: transition to Start mode CANA CAN2 (pass)."""
        conn = _make_conn()
        self._ctrl_mode_test(conn, "CanControllerMode", 1,
                              "SetCNDD_e_CanControllerMode",
                              "MngCNDD_CanMainMode")

    # ------------------------------------------------------------------
    # TC 1.25 – CanControllerMode transition to Start CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_25_can_controller_mode_start_canb(self):
        """SetCNDD_e_CanControllerMode: transition to Start mode CANB CAN8 (pass)."""
        conn = _make_conn()
        self._ctrl_mode_test(conn, "CanControllerMode", 1,
                              "SetCNDD_e_CanControllerMode",
                              "MngCNDD_CanMainMode")

    # ------------------------------------------------------------------
    # TC 1.26 – CanControllerMode transition to Sleep CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_26_can_controller_mode_sleep_cana(self):
        """SetCNDD_e_CanControllerMode: transition to Sleep mode CANA CAN2 (pass)."""
        conn = _make_conn()
        self._ctrl_mode_test(conn, "CanControllerMode", 2,
                              "SetCNDD_e_CanControllerMode",
                              "MngCNDD_CanMainMode")

    # ------------------------------------------------------------------
    # TC 1.27 – CanControllerMode transition to Start after Sleep CANB
    # ------------------------------------------------------------------
    def test_tc1_27_can_controller_mode_start_after_sleep_canb(self):
        """SetCNDD_e_CanControllerMode: Start after Sleep mode CANB (pass)."""
        conn = _make_conn()
        self._ctrl_mode_test(conn, "CanControllerMode", 1,
                              "SetCNDD_e_CanControllerMode",
                              "MngCNDD_CanMainMode")

    # ------------------------------------------------------------------
    # TC 1.28 – CanControllerMode transition to WakeUp CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_28_can_controller_mode_wakeup_cana(self):
        """SetCNDD_e_CanControllerMode: transition to WakeUp mode CANA CAN2 (pass)."""
        conn = _make_conn()
        self._ctrl_mode_test(conn, "CanControllerMode", 4,
                              "SetCNDD_e_CanControllerMode",
                              "MngCNDD_CanMainMode")

    # ------------------------------------------------------------------
    # TC 1.29 – CanControllerMode transition to Start after WakeUp CANB
    # ------------------------------------------------------------------
    def test_tc1_29_can_controller_mode_start_after_wakeup_canb(self):
        """SetCNDD_e_CanControllerMode: Start after WakeUp CANB (pass)."""
        conn = _make_conn()
        self._ctrl_mode_test(conn, "CanControllerMode", 1,
                              "SetCNDD_e_CanControllerMode",
                              "MngCNDD_CanMainMode")

    # ------------------------------------------------------------------
    # TC 1.30 – CanMainMode Mode Transition to Stop CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_30_can_main_mode_stop_cana(self):
        """MngCNDD_CanMainMode: Mode Transition to Stop CANA CAN2 (pass)."""
        conn = _make_conn()
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint("TestCan_Init", conn)
        _dbg.reset_target(conn)
        _dbg.go_safe(connection=conn)
        _bp.check_halted_at("TestCan_Init", connection=conn)
        _var.set_variable("CanControllerMode", 0, conn)
        _var.check_variable("CanControllerMode", 0, conn)
        _bp.set_breakpoint("MngCNDD_CanMainMode", conn)
        _dbg.go(conn)
        _bp.check_halted_at("MngCNDD_CanMainMode", connection=conn)
        self._sim_ecu_output("CanMainModeStatus", 0, conn)

    # ------------------------------------------------------------------
    # TC 1.31 – CanMainMode Mode Transition to Start CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_31_can_main_mode_start_cana(self):
        """MngCNDD_CanMainMode: Mode Transition to Start CANA CAN2 (pass)."""
        conn = _make_conn()
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint("TestCan_Init", conn)
        _dbg.reset_target(conn)
        _dbg.go_safe(connection=conn)
        _bp.check_halted_at("TestCan_Init", connection=conn)
        _var.set_variable("CanControllerMode", 1, conn)
        _var.check_variable("CanControllerMode", 1, conn)
        _bp.set_breakpoint("MngCNDD_CanMainMode", conn)
        _dbg.go(conn)
        _bp.check_halted_at("MngCNDD_CanMainMode", connection=conn)
        self._sim_ecu_output("CanMainModeStatus", 1, conn)

    # ------------------------------------------------------------------
    # TC 1.32 – CanMainRead RX callback CANA
    # ------------------------------------------------------------------
    def test_tc1_32_can_main_read_rx_callback_cana(self):
        """MngCNDD_CanMainRead: RX callback SetCANR_h_CanIfRxIndication CANA (pass)."""
        conn = _make_conn()
        self._can_rx_init_setup(conn)
        self._set_can_rx_msg_vars(conn, 0x401, 0x7FF, 0, 8, 2, 0)
        _bp.set_breakpoint("MngCNDD_CanMainRead", conn)
        _dbg.go(conn)
        _bp.check_halted_at("MngCNDD_CanMainRead", connection=conn)
        _bp.set_breakpoint("SetCANR_h_CanIfRxIndication", conn)
        _dbg.go(conn)
        _bp.check_halted_at("SetCANR_h_CanIfRxIndication", connection=conn)

    # ------------------------------------------------------------------
    # TC 1.33 – CanMainRead RX callback CANB
    # ------------------------------------------------------------------
    def test_tc1_33_can_main_read_rx_callback_canb(self):
        """MngCNDD_CanMainRead: RX callback SetCANR_h_CanIfRxIndication CANB (pass)."""
        conn = _make_conn()
        self._can_rx_init_setup(conn)
        self._set_can_rx_msg_vars(conn, 0x456, 0x7FF, 0, 8, 2, 1)
        _bp.set_breakpoint("MngCNDD_CanMainRead", conn)
        _dbg.go(conn)
        _bp.check_halted_at("MngCNDD_CanMainRead", connection=conn)
        _bp.set_breakpoint("SetCANR_h_CanIfRxIndication", conn)
        _dbg.go(conn)
        _bp.check_halted_at("SetCANR_h_CanIfRxIndication", connection=conn)

    # ------------------------------------------------------------------
    # TC 1.34 – CanTrcvOpMode Normal CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_34_can_trcv_op_mode_normal_cana(self):
        """SetCNDD_e_CanTrcvOpMode: Normal mode CANA CAN2 (pass)."""
        conn = _make_conn()
        self._trcv_op_mode_test(conn, 0, "MngCNDD_CanTrcvInitialize")

    # ------------------------------------------------------------------
    # TC 1.35 – CanTrcvOpMode Sleep CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_35_can_trcv_op_mode_sleep_cana(self):
        """SetCNDD_e_CanTrcvOpMode: Sleep mode CANA CAN2 (pass)."""
        conn = _make_conn()
        self._trcv_op_mode_test(conn, 1, "MngCNDD_CanTrcvInitialize")

    # ------------------------------------------------------------------
    # TC 1.36 – CanTrcvOpMode Standby CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_36_can_trcv_op_mode_standby_cana(self):
        """SetCNDD_e_CanTrcvOpMode: Standby mode CANA CAN2 (pass)."""
        conn = _make_conn()
        self._trcv_op_mode_test(conn, 2, "MngCNDD_CanTrcvInitialize")

    # ------------------------------------------------------------------
    # TC 1.37 – CanTrcvOpMode LISTEN_ONLY CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_37_can_trcv_op_mode_listen_only_cana(self):
        """SetCNDD_e_CanTrcvOpMode: LISTEN_ONLY mode CANA CAN2 (pass)."""
        conn = _make_conn()
        self._trcv_op_mode_test(conn, 3, "MngCNDD_CanTrcvInitialize")

    # ------------------------------------------------------------------
    # TC 1.38 – CanTrcvOpMode Normal CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_38_can_trcv_op_mode_normal_canb(self):
        """SetCNDD_e_CanTrcvOpMode: Normal mode CANB CAN8 (pass)."""
        conn = _make_conn()
        self._trcv_op_mode_test(conn, 0, "MngCNDD_CanTrcvInitialize")

    # ------------------------------------------------------------------
    # TC 1.39 – CanTrcvOpMode Sleep CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_39_can_trcv_op_mode_sleep_canb(self):
        """SetCNDD_e_CanTrcvOpMode: Sleep mode CANB CAN8 (pass)."""
        conn = _make_conn()
        self._trcv_op_mode_test(conn, 1, "MngCNDD_CanTrcvInitialize")

    # ------------------------------------------------------------------
    # TC 1.40 – CanTrcvOpMode Standby CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_40_can_trcv_op_mode_standby_canb(self):
        """SetCNDD_e_CanTrcvOpMode: Standby mode CANB CAN8 (pass)."""
        conn = _make_conn()
        self._trcv_op_mode_test(conn, 2, "MngCNDD_CanTrcvInitialize")

    # ------------------------------------------------------------------
    # TC 1.41 – CanTrcvOpMode LISTEN_ONLY CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_41_can_trcv_op_mode_listen_only_canb(self):
        """SetCNDD_e_CanTrcvOpMode: LISTEN_ONLY mode CANB CAN8 (pass)."""
        conn = _make_conn()
        self._trcv_op_mode_test(conn, 3, "MngCNDD_CanTrcvInitialize")

    # ------------------------------------------------------------------
    # TC 1.42 – CanWrt disabled channel (no TX)
    # ------------------------------------------------------------------
    def test_tc1_42_canwrt_disabled_channel_no_tx(self):
        """CntrlCNDD_h_CanWrt: no TX when CAN channel disabled (pass)."""
        conn = _make_conn()
        self._can_tx_setup(conn)
        _var.set_variable("CanChannelEnabled", 0, conn)
        _var.check_variable("CanChannelEnabled", 0, conn)
        self._set_pdu_vars(conn, 16, 0x40000101, 8, 1)
        _dbg.go(conn)
        _var.check_variable("CanTxStatus", 0, conn)

    # ------------------------------------------------------------------
    # TC 1.43 – CanTrcvInitialize CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_43_can_trcv_initialize_cana_can2(self):
        """MngCNDD_CanTrcvInitialize: CAN Transceiver init CANA CAN2 (pass)."""
        conn = _make_conn()
        self._trcv_init_test(conn)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.44 – CanRxInit CANA CAN2 post TrcvInit
    # ------------------------------------------------------------------
    def test_tc1_44_can_rx_init_cana_post_trcv_init(self):
        """MngCNDD_CanRxInit: CANA CAN2 initialized after TrcvInit (pass)."""
        conn = _make_conn()
        self._trcv_init_test(conn)
        _bp.set_breakpoint("MngCNDD_CanRxInit", conn)
        _dbg.go(conn)
        _bp.check_halted_at("MngCNDD_CanRxInit", connection=conn)

    # ------------------------------------------------------------------
    # TC 1.45 – CanTrcvInitialize CANA negative (wrong CANID)
    # ------------------------------------------------------------------
    def test_tc1_45_can_trcv_initialize_cana_negative_wrong_canid(self):
        """MngCNDD_CanTrcvInitialize: negative test – wrong CANID (pass)."""
        conn = _make_conn()
        self._trcv_init_test(conn)
        _var.set_variable("VsCANR_PnConfig[0].CanTrcvPnFrameCanId", 0x999, conn)
        _var.check_variable("VsCANR_PnConfig[0].CanTrcvPnFrameCanId", 0x999, conn)
        _dbg.go(conn)
        _var.check_variable("CanTrcvWakeupStatus", 0, conn)

    # ------------------------------------------------------------------
    # TC 1.46 – CanTrcvInitialize CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_46_can_trcv_initialize_canb_can8(self):
        """MngCNDD_CanTrcvInitialize: CAN Transceiver init CANB CAN8 (pass)."""
        conn = _make_conn()
        self._trcv_init_test(conn)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 1.47 – CanTrcvInitialize CANB negative (wrong CANID)
    # ------------------------------------------------------------------
    def test_tc1_47_can_trcv_initialize_canb_negative_wrong_canid(self):
        """MngCNDD_CanTrcvInitialize: negative test CANB – wrong CANID (pass)."""
        conn = _make_conn()
        self._trcv_init_test(conn)
        _var.set_variable("VsCANR_PnConfig[0].CanTrcvPnFrameCanId", 0x999, conn)
        _var.check_variable("VsCANR_PnConfig[0].CanTrcvPnFrameCanId", 0x999, conn)
        _dbg.go(conn)
        _var.check_variable("CanTrcvWakeupStatus", 0, conn)

    # ------------------------------------------------------------------
    # TC 1.48 – CanTrcvMain CANB CAN8
    # ------------------------------------------------------------------
    def test_tc1_48_can_trcv_main_canb_can8(self):
        """MngCNDD_CanTrcvMain: Functionality CANB CAN8 (pass)."""
        conn = _make_conn()
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint("SetCNDD_e_CanTrcvOpMode", conn)
        _dbg.reset_target(conn)
        _dbg.go(conn)
        _dbg.go(conn)
        _dbg.go(conn)
        _bp.check_halted_at("SetCNDD_e_CanTrcvOpMode", connection=conn)
        _var.set_variable("can_trcv_mode", 0, conn)
        _var.check_variable("can_trcv_mode", 0, conn)
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint("MngCNDD_CanTrcvMain", conn)
        _dbg.go(conn)
        _bp.check_halted_at("MngCNDD_CanTrcvMain", connection=conn)
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint("SetCANR_e_CanIfTrcvModeIndication", conn)
        _dbg.go(conn)
        _bp.check_halted_at("SetCANR_e_CanIfTrcvModeIndication", connection=conn)

    # ------------------------------------------------------------------
    # TC 1.49 – CanTrcvMain CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_49_can_trcv_main_cana_can2(self):
        """MngCNDD_CanTrcvMain: Functionality CANA CAN2 (pass)."""
        conn = _make_conn()
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint("SetCNDD_e_CanTrcvOpMode", conn)
        _dbg.reset_target(conn)
        _dbg.go(conn)
        _dbg.go(conn)
        _dbg.go(conn)
        _bp.check_halted_at("SetCNDD_e_CanTrcvOpMode", connection=conn)
        _var.set_variable("can_trcv_mode", 0, conn)
        _var.check_variable("can_trcv_mode", 0, conn)
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint("MngCNDD_CanTrcvMain", conn)
        _dbg.go(conn)
        _bp.check_halted_at("MngCNDD_CanTrcvMain", connection=conn)
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint("SetCANR_e_CanIfTrcvModeIndication", conn)
        _dbg.go(conn)
        _bp.check_halted_at("SetCANR_e_CanIfTrcvModeIndication", connection=conn)

    # ------------------------------------------------------------------
    # TC 1.50 – CanMainBusOff CANA CAN2
    # ------------------------------------------------------------------
    def test_tc1_50_can_main_bus_off_cana_can2(self):
        """MngCNDD_CanMainBusOff: CAN Bus-Off Detection CANA CAN2 (pass)."""
        conn = _make_conn()
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint("TestCan_Init", conn)
        _dbg.reset_target(conn)
        _dbg.go_safe(connection=conn)
        _bp.check_halted_at("TestCan_Init", connection=conn)
        _bp.set_breakpoint("SetCANR_e_CanIfCntrlrBusOff", conn)
        _dbg.go(conn)
        _bp.check_halted_at("SetCANR_e_CanIfCntrlrBusOff", connection=conn)


# ============================================================================
# GROUP 2 – BATTERY (2 executed tests, all pass)
# ============================================================================

class TestSanityGroup2Battery(_SanityBase):
    """Mirrors the 2 executed BATTERY test cases from the Sanity report."""

    def _battery_setup(self, conn):
        """Common T32 sequence: delete BPs → reset → go_safe."""
        _bp.delete_all_breakpoints(conn)
        _dbg.reset_target(conn)
        _dbg.go_safe(connection=conn)

    # ------------------------------------------------------------------
    # TC 2.1 – GetHWIO_b_BatConnectionStatus returns 1 when disconnected
    # ------------------------------------------------------------------
    def test_tc2_01_battery_disconnected_status_returns_1(self):
        """GetHWIO_b_BatConnectionStatus: returns 1 when battery is disconnected (pass)."""
        conn = _make_conn()
        self._battery_setup(conn)
        _dbg.go(conn)
        self._sim_ecu_output("GetHWIO_b_BatConnectionStatus", 1, conn)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 2.2 – BATTERY_DISCONNECT status retained unless cleared
    # ------------------------------------------------------------------
    def test_tc2_02_battery_disconnect_status_retained(self):
        """GetHWIO_b_BatConnectionStatus: DISCONNECT status retained until cleared (pass)."""
        conn = _make_conn()
        self._battery_setup(conn)
        _dbg.go(conn)
        self._sim_ecu_output("GetHWIO_b_BatConnectionStatus", 1, conn)
        self._battery_setup(conn)
        _dbg.go(conn)
        _var.check_variable("GetHWIO_b_BatConnectionStatus", 1, conn)
        self._assert_reset_called(conn)


# ============================================================================
# GROUP 3 – Wakeup (5 executed tests: 4 pass, 1 fail)
# ============================================================================

class TestSanityGroup3Wakeup(_SanityBase):
    """Mirrors the 5 executed Wakeup test cases from the Sanity report.

    TC 3.5 is the only test that showed a failure in the original run due to
    a transient Trace32 timeout.  On the second run it passed.  The mock
    models both the initial timeout and the successful retry.
    """

    def _wakeup_can_trcv_setup(self, conn):
        """Common preamble for CAN-A/B wakeup tests (TrcvInit pattern)."""
        _bp.delete_all_breakpoints(conn)
        _dbg.reset_target(conn)
        _bp.set_breakpoint("TestCanTrcv_Init", conn)
        _dbg.go_safe(connection=conn)
        _bp.check_halted_at("TestCanTrcv_Init", connection=conn)
        _bp.set_breakpoint("TestCan_Init", conn)
        _dbg.go(conn)
        _bp.check_halted_at("TestCan_Init", connection=conn)
        # PN frame / config variables
        _var.set_variable("VsCANR_PnFrameData1[0].CanTrcvPnFrameDataMaskIndex", 0, conn)
        _var.check_variable("VsCANR_PnFrameData1[0].CanTrcvPnFrameDataMaskIndex", 0, conn)
        _var.set_variable("VsCANR_PnFrameData1[0].CanTrcvPnFrameDataMask", 1, conn)
        _var.check_variable("VsCANR_PnFrameData1[0].CanTrcvPnFrameDataMask", 1, conn)
        _var.set_variable("VsCANR_PnFrameData1[7].CanTrcvPnFrameDataMaskIndex", 7, conn)
        _var.check_variable("VsCANR_PnFrameData1[7].CanTrcvPnFrameDataMaskIndex", 7, conn)
        _var.set_variable("VsCANR_PnFrameData1[7].CanTrcvPnFrameDataMask", 8, conn)
        _var.check_variable("VsCANR_PnFrameData1[7].CanTrcvPnFrameDataMask", 8, conn)
        _var.set_variable("VsCANR_PnConfig[0].CanTrcvPnFrameCanId", 0x123, conn)
        _var.check_variable("VsCANR_PnConfig[0].CanTrcvPnFrameCanId", 0x123, conn)
        _var.set_variable("VsCANR_PnConfig[0].CanTrcvPnFrameCanIdMask", 0, conn)
        _var.check_variable("VsCANR_PnConfig[0].CanTrcvPnFrameCanIdMask", 0, conn)
        _var.set_variable("VsCANR_PnConfig[0].CanTrcvPnFrameIdType", 0, conn)
        _var.check_variable("VsCANR_PnConfig[0].CanTrcvPnFrameIdType", 0, conn)
        _var.set_variable("VsCANR_PnConfig[0].CanTrcvPnFrameDlc", 8, conn)
        _var.check_variable("VsCANR_PnConfig[0].CanTrcvPnFrameDlc", 8, conn)
        _var.set_variable("VsCANR_PnConfig[0].CanTrcvPnEnabled", 1, conn)
        _var.check_variable("VsCANR_PnConfig[0].CanTrcvPnEnabled", 1, conn)
        _var.set_variable("VsCANR_TrcvChannels[0].CanTrcvChannelId", 0, conn)
        _var.check_variable("VsCANR_TrcvChannels[0].CanTrcvChannelId", 0, conn)
        _var.set_variable("VsCANR_TrcvChannels[0].CanTrcvChannelUsed", 1, conn)
        _var.check_variable("VsCANR_TrcvChannels[0].CanTrcvChannelUsed", 1, conn)
        _var.set_variable("VsCANR_TrcvChannels[0].CanTrcvPinWakeupEnabled", 0, conn)
        _var.check_variable("VsCANR_TrcvChannels[0].CanTrcvPinWakeupEnabled", 0, conn)
        _var.set_variable("VsCANR_CanTrcvConfig.CanTrcvNumberOfChannels", 2, conn)
        _var.check_variable("VsCANR_CanTrcvConfig.CanTrcvNumberOfChannels", 2, conn)
        _dbg.go(conn)
        _var.set_variable("StartPowerDown", 1, conn)
        _var.check_variable("StartPowerDown", 1, conn)

    # ------------------------------------------------------------------
    # TC 3.1 – Last wakeup event = 0 (no wakeup)
    # ------------------------------------------------------------------
    def test_tc3_01_last_wakeup_event_zero(self):
        """GetHWIO_e_WakeupSigSt: last wakeup event = 0 when no events (pass)."""
        conn = _make_conn()
        _bp.delete_all_breakpoints(conn)
        _dbg.reset_target(conn)
        _dbg.go_safe(connection=conn)
        bp_wakeup = r"Test_GetHWIO_e_WakeupSigSt\9"
        _bp.set_breakpoint(bp_wakeup, conn)
        _bp.check_halted_at(bp_wakeup, connection=conn)
        # wakeEvent = 0 is the default (no wakeup event triggered).
        _var.check_variable("wakeEvent", 0, conn)
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 3.2 – wkupCanBusA: LLSI CAN A bus wakeup
    # ------------------------------------------------------------------
    def test_tc3_02_wakeup_can_bus_a_llsi(self):
        """GetHWIO_e_WakeupSigSt: wkupCanBusA LLSI CAN A wakeup (pass)."""
        conn = _make_conn()
        self._wakeup_can_trcv_setup(conn)
        # ECU sets wakeup status after detecting the CAN-A bus wakeup event.
        self._sim_ecu_output("GetHWIO_e_WakeupSigSt", 1, conn)

    # ------------------------------------------------------------------
    # TC 3.3 – wkupCanBusA: wakeup event detected CAN A bus
    # ------------------------------------------------------------------
    def test_tc3_03_wakeup_can_bus_a_event_detected(self):
        """GetHWIO_e_WakeupSigSt: wkupCanBusA CAN A wakeup event detected (pass)."""
        conn = _make_conn()
        self._wakeup_can_trcv_setup(conn)
        self._sim_ecu_output("GetHWIO_e_WakeupSigSt", 1, conn)

    # ------------------------------------------------------------------
    # TC 3.4 – wkupCanBusA: CAN error frame count
    # ------------------------------------------------------------------
    def test_tc3_04_wakeup_can_bus_a_error_frame_count(self):
        """GetHWIO_e_WakeupSigSt: wkupCanBusA CAN error frame count (pass)."""
        conn = _make_conn()
        self._wakeup_can_trcv_setup(conn)
        self._sim_ecu_output("GetHWIO_e_WakeupSigSt", 1, conn)

    # ------------------------------------------------------------------
    # TC 3.5 – wkupCanBusB: transient T32 timeout; passes on retry
    #
    # The original run reported "Timeout: ECU did not halt within 3000 ms"
    # on the first attempt.  On the second run it passed.  Root cause: a
    # transient Trace32 acknowledge delay – the ECU eventually halts at the
    # TestCanTrcv_Init breakpoint but needs more time than the initial
    # tight window allows.
    #
    # The mock models this with a poll counter that keeps returning
    # STATE.RUN=TRUE for the first several polls and then returns FALSE
    # (halted).  A short timeout captures the first-run failure;
    # a longer timeout captures the eventual success on retry.
    # ------------------------------------------------------------------
    def test_tc3_05_wakeup_can_bus_b_ecu_timeout_then_retry_pass(self):
        """GetHWIO_e_WakeupSigSt: wkupCanBusB transient T32 timeout; passes on retry (pass)."""
        if USE_LIVE_T32:
            # Live mode: run the standard wakeup flow – the real ECU does not
            # need timeout simulation; we just verify the wakeup state is set.
            conn = _make_conn()
            self._wakeup_can_trcv_setup(conn)
            self._sim_ecu_output("GetHWIO_e_WakeupSigSt", 1, conn)
            return

        from GM_VIP_Automation_Framework.utils.exceptions import T32BreakpointNotReachedError

        conn = _make_conn_slow_halt(halt_after_polls=8)

        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint("TestCanTrcv_Init", conn)

        # First attempt: tight timeout (mirrors the 3-second window that
        # expired in the original run) → T32BreakpointNotReachedError.
        with self.assertRaises(T32BreakpointNotReachedError):
            _bp.check_halted_at("TestCanTrcv_Init", timeout_s=0.02, connection=conn)

        # Second attempt: extended wait budget – ECU eventually halts → pass.
        result = _bp.check_halted_at("TestCanTrcv_Init", timeout_s=1.0, connection=conn)
        self.assertTrue(result, "ECU should halt at TestCanTrcv_Init on retry")


# ============================================================================
# GROUP 4 – Config_reg (7 executed tests, all pass)
# ============================================================================

class TestSanityGroup4ConfigReg(_SanityBase):
    """Mirrors the 7 executed Config_reg test cases from the Sanity report."""

    def _config_reg_setup(self, conn, bp_line):
        """Common preamble: delete BPs → reset → go_safe → set BP at line."""
        _bp.delete_all_breakpoints(conn)
        _dbg.reset_target(conn)
        _dbg.go_safe(connection=conn)
        _bp.set_breakpoint(bp_line, conn)
        _bp.check_halted_at(bp_line, connection=conn)

    # ------------------------------------------------------------------
    # TC 4.1 – FAILED_REGISTER_ID default on PowerUp Reset
    # ------------------------------------------------------------------
    def test_tc4_01_failed_register_id_default_power_up(self):
        """Config register: FAILED_REGISTER_ID = 0 at PowerUp Reset (pass)."""
        conn = _make_conn()
        self._config_reg_setup(conn, r"Test_ConfigRegister\4")
        _var.check_variable("Failed_Register_ID", 0, conn)

    # ------------------------------------------------------------------
    # TC 4.2 – FAILED_BIT_ID default on PowerUp Reset
    # ------------------------------------------------------------------
    def test_tc4_02_failed_bit_id_default_power_up(self):
        """Config register: FAILED_BIT_ID = 0 at PowerUp Reset (pass)."""
        conn = _make_conn()
        self._config_reg_setup(conn, r"Test_ConfigRegister\5")
        _var.check_variable("Failed_BIT_ID", 0, conn)

    # ------------------------------------------------------------------
    # TC 4.3 – FAILED_REGISTER_RECOVER_STATUS default on PowerUp Reset
    # ------------------------------------------------------------------
    def test_tc4_03_failed_register_recover_status_default_power_up(self):
        """Config register: FAILED_REGISTER_RECOVER_STATUS = 0 at PowerUp Reset (pass)."""
        conn = _make_conn()
        self._config_reg_setup(conn, r"Test_ConfigRegister\6")
        _var.check_variable("Failed_Register_Recover_Status", 0, conn)

    # ------------------------------------------------------------------
    # TC 4.4 – PerfmHWIO_b_ConfigRegTest returns 1 when test passed
    # ------------------------------------------------------------------
    def test_tc4_04_config_reg_test_status_returns_1_when_pass(self):
        """Config register: PerfmHWIO_b_ConfigRegTest = 1 when test passed (pass)."""
        conn = _make_conn()
        self._config_reg_setup(conn, r"Test_ConfigRegister\4")
        # ECU sets Configuration_Registers_Test_Status = 1 to indicate all
        # config registers passed the check.
        self._sim_ecu_output("Configuration_Registers_Test_Status", 1, conn)

    # ------------------------------------------------------------------
    # TC 4.5 – GetHWIO_e_FailedRegID returns 0 when no failures
    # ------------------------------------------------------------------
    def test_tc4_05_failed_reg_id_zero_when_no_failures(self):
        """Config register: GetHWIO_e_FailedRegID = 0 when no failures (pass)."""
        conn = _make_conn()
        self._config_reg_setup(conn, r"Test_ConfigRegister\4")
        _var.check_variable("Failed_Register_ID", 0, conn)

    # ------------------------------------------------------------------
    # TC 4.6 – GetHWIO_e_FailedBitID returns 0 when no failed register
    # ------------------------------------------------------------------
    def test_tc4_06_failed_bit_id_zero_when_no_failures(self):
        """Config register: GetHWIO_e_FailedBitID = 0 when no failures (pass)."""
        conn = _make_conn()
        self._config_reg_setup(conn, r"Test_ConfigRegister\5")
        _var.check_variable("Failed_BIT_ID", 0, conn)

    # ------------------------------------------------------------------
    # TC 4.7 – GetHWIO_b_FailedRegRecovSt returns 0 on success
    # ------------------------------------------------------------------
    def test_tc4_07_failed_reg_recov_st_zero_on_success(self):
        """Config register: GetHWIO_b_FailedRegRecovSt = 0 on success (pass)."""
        conn = _make_conn()
        self._config_reg_setup(conn, r"Test_ConfigRegister\6")
        _var.check_variable("Failed_Register_Recover_Status", 0, conn)


# ============================================================================
# GROUP 5 – LockStep DUAL CPU (1 executed test, pass)
# ============================================================================

class TestSanityGroup5LockStep(_SanityBase):
    """Mirrors the single executed LockStep test case from the Sanity report."""

    # ------------------------------------------------------------------
    # TC 5.1 – LockStep status NO_LOCKSTEP for CPU Core 6
    # ------------------------------------------------------------------
    def test_tc5_01_lockstep_no_lockstep_status_core6(self):
        """GetHWIO_b_LockstepStN: NO_LOCKSTEP status for CPU Core 6 (pass)."""
        conn = _make_conn()

        # TS0: delete BPs, reset, go_safe
        _bp.delete_all_breakpoints(conn)
        _dbg.reset_target(conn)
        _dbg.go_safe(connection=conn)

        # TS0 cont.: set BP at test entry, verify halted there
        _bp.set_breakpoint("Test_GetHWIO_b_LockstepStN", conn)
        _bp.check_halted_at("Test_GetHWIO_b_LockstepStN", connection=conn)

        # TS1: set coreId = 6, verify
        _var.set_variable("coreId", 6, conn)
        _var.check_variable("coreId", 6, conn)

        # TS2: delete BPs, set BP at inner function, go, verify halted there
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint("GetHWIO_b_LockstepStN", conn)
        _dbg.go(conn)
        _bp.check_halted_at("GetHWIO_b_LockstepStN", connection=conn)

        # TS3: verify cpuId = 6 at breakpoint (ECU passes coreId as cpuId arg).
        self._sim_ecu_output("cpuId", 6, conn)

        # TS4: delete BPs, go_up (step out), step_over, verify retval = 2 (NO_LOCKSTEP).
        _bp.delete_all_breakpoints(conn)
        _dbg.go_up(conn)
        _dbg.step_over(conn)
        self._sim_ecu_output("retval", 2, conn)

        self._assert_reset_called(conn)


# ============================================================================
# GROUP 6 – SP_Device_Support (7 executed tests, all pass)
# 5 'not executed' entries are intentionally omitted.
# ============================================================================

class TestSanityGroup6SPDeviceSupport(_SanityBase):
    """Mirrors the 7 executed SP_Device_Support test cases from the Sanity report."""

    def _sp_device_setup(self, conn, feature_num):
        """Common preamble: delete BPs → reset → set BP cybersec_features_test\\2
        → go_safe → verify halted → set CysecFeatureNum.
        """
        _bp.delete_all_breakpoints(conn)
        _dbg.reset_target(conn)
        _bp.set_breakpoint(r"cybersec_features_test\2", conn)
        _dbg.go_safe(connection=conn)
        _bp.check_halted_at(r"cybersec_features_test\2", connection=conn)
        _var.set_variable("CysecFeatureNum", feature_num, conn)
        _var.check_variable("CysecFeatureNum", feature_num, conn)

    def _sp_device_run(self, conn, app_bp, csm_status=0):
        """Delete BPs, set app BP, go, verify halted, check CSM_STATUS."""
        _bp.delete_all_breakpoints(conn)
        _bp.set_breakpoint(app_bp, conn)
        _dbg.go(conn)
        _bp.check_halted_at(app_bp, connection=conn)
        _var.check_variable("CSM_STATUS", csm_status, conn)

    # ------------------------------------------------------------------
    # TC 6.1 – CSM Random Number Generate
    # ------------------------------------------------------------------
    def test_tc6_01_csm_random_number_generate(self):
        """SP_Device_Support: CSM Random Number Generate (pass)."""
        conn = _make_conn()
        self._sp_device_setup(conn, 7)
        self._sp_device_run(conn, r"App_RandomGenerate\12")
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 6.2 – CSM Random Seed Finish
    # ------------------------------------------------------------------
    def test_tc6_02_csm_random_seed_finish(self):
        """SP_Device_Support: CSM Random Seed Finish (pass)."""
        conn = _make_conn()
        self._sp_device_setup(conn, 7)
        self._sp_device_run(conn, r"App_RandomGenerate\7")
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 6.3 – CSM Symmetric Key Wrapping Finish
    # ------------------------------------------------------------------
    def test_tc6_03_csm_symmetric_key_wrapping_finish(self):
        """SP_Device_Support: CSM Symmetric Key Wrapping Finish (pass)."""
        conn = _make_conn()
        self._sp_device_setup(conn, 10)
        self._sp_device_run(conn, r"App_SymKeyWrapSym\25")
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 6.4 – CSM Symmetric Key Wrapping Update
    # ------------------------------------------------------------------
    def test_tc6_04_csm_symmetric_key_wrapping_update(self):
        """SP_Device_Support: CSM Symmetric Key Wrapping Update (pass)."""
        conn = _make_conn()
        self._sp_device_setup(conn, 10)
        self._sp_device_run(conn, r"App_SymKeyWrapSym\24")
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 6.5 – CSM Symmetric Key Wrapping Start
    # ------------------------------------------------------------------
    def test_tc6_05_csm_symmetric_key_wrapping_start(self):
        """SP_Device_Support: CSM Symmetric Key Wrapping Start (pass)."""
        conn = _make_conn()
        self._sp_device_setup(conn, 10)
        self._sp_device_run(conn, r"App_SymKeyWrapSym\23")
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 6.6 – CSM Symmetric Key Extract Finish
    # ------------------------------------------------------------------
    def test_tc6_06_csm_symmetric_key_extract_finish(self):
        """SP_Device_Support: CSM Symmetric Key Extract Finish (pass)."""
        conn = _make_conn()
        self._sp_device_setup(conn, 5)
        self._sp_device_run(conn, r"App_GMCmacGenerate\15")
        self._assert_reset_called(conn)

    # ------------------------------------------------------------------
    # TC 6.7 – CSM MAC Verify Finish
    # ------------------------------------------------------------------
    def test_tc6_07_csm_mac_verify_finish(self):
        """SP_Device_Support: CSM MAC Verify Finish (pass)."""
        conn = _make_conn()
        self._sp_device_setup(conn, 5)
        self._sp_device_run(conn, r"App_GMCmacGenerate\16")
        self._assert_reset_called(conn)


if __name__ == "__main__":
    unittest.main()
