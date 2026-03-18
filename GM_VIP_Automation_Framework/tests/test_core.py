"""
Tests for GM_VIP_Automation_Framework core modules.
All Trace32 API calls are mocked – no hardware required.
"""

import re
import sys
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# ---------------------------------------------------------------------------
# Stub out lauterbach.trace32.rcl so the tests run without the library.
# ---------------------------------------------------------------------------
_pyrcl_mock = MagicMock()
sys.modules.setdefault("lauterbach", MagicMock())
sys.modules.setdefault("lauterbach.trace32", MagicMock())
sys.modules.setdefault("lauterbach.trace32.rcl", _pyrcl_mock)
sys.modules.setdefault("lauterbach.trace32.rcl._rc", MagicMock())
sys.modules.setdefault("lauterbach.trace32.rcl._rc._error", MagicMock())


def _make_conn(running: bool = False):
    """Return a mock T32Connection whose fnc/cmd behave sensibly."""
    conn = MagicMock()
    conn.is_connected.return_value = True

    def _fnc(expr):
        if "STATE.RUN" in expr:
            return "TRUE()" if running else "FALSE()"
        if "STATE.NAME" in expr:
            return "running" if running else "stopped"
        # PC comparison expressions (check_halted_at): "(P:R(PC)==<sym>)"
        if "P:R(PC)" in expr and "==" in expr:
            return "TRUE()"
        # Simple PC/register read: R(PC) or R(R0) etc.
        if "R(PC)" in expr or re.match(r"R\(\w+\)", expr):
            return "0x80001234"
        if "VAR.VALUE" in expr:
            return "42"
        if "SYMBOL.EXIST" in expr:
            return "TRUE()"
        if "ADDRESS.OFFSET" in expr:
            return "0xA0000000"
        if "CORE()" in expr:
            return "TRUE()"
        return "0"

    conn.fnc.side_effect = _fnc
    conn.cmd.return_value = None
    return conn


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

class TestConfig(unittest.TestCase):
    def test_settings_defaults(self):
        from GM_VIP_Automation_Framework.config import settings
        self.assertIsInstance(settings.rcl_port, int)
        self.assertIsInstance(settings.halt_timeout_s, float)
        self.assertGreater(settings.bp_max_retries, 0)


# ---------------------------------------------------------------------------
# connection
# ---------------------------------------------------------------------------

class TestConnection(unittest.TestCase):

    def test_auto_detect_no_dirs_raises(self):
        from GM_VIP_Automation_Framework.core.connection import auto_detect_t32
        from GM_VIP_Automation_Framework.utils.exceptions import T32AutoDetectError
        with self.assertRaises(T32AutoDetectError):
            auto_detect_t32(search_dirs=["/nonexistent_dir_xyzzy"])

    def test_parse_config_port(self):
        from GM_VIP_Automation_Framework.core.connection import parse_config_port
        import tempfile, os
        with tempfile.NamedTemporaryFile("w", suffix=".t32", delete=False) as f:
            f.write("[CONNECTIONMODE]\nPORT=20001\n")
            name = f.name
        try:
            port = parse_config_port(name)
            self.assertEqual(port, 20001)
        finally:
            os.unlink(name)

    def test_parse_config_port_missing(self):
        from GM_VIP_Automation_Framework.core.connection import parse_config_port
        import tempfile, os
        with tempfile.NamedTemporaryFile("w", suffix=".t32", delete=False) as f:
            f.write("[CONNECTIONMODE]\nNO_PORT=here\n")
            name = f.name
        try:
            self.assertIsNone(parse_config_port(name))
        finally:
            os.unlink(name)

    def test_t32connection_not_connected_raises(self):
        from GM_VIP_Automation_Framework.core.connection import T32Connection
        from GM_VIP_Automation_Framework.utils.exceptions import T32ConnectionError
        conn = T32Connection()
        with self.assertRaises(T32ConnectionError):
            conn.cmd("GO")

    def test_t32connection_context_manager_disconnects(self):
        from GM_VIP_Automation_Framework.core.connection import T32Connection
        conn = T32Connection()
        conn._connected = True
        conn.debugger = MagicMock()
        with conn:
            pass
        # After __exit__, should be disconnected.
        self.assertFalse(conn.is_connected())

    def test_t32connection_cmm_entry_script_stored(self):
        from GM_VIP_Automation_Framework.core.connection import T32Connection
        conn = T32Connection(cmm_entry_script=r"C:\scripts\startup.cmm")
        self.assertEqual(conn._cmm_entry_script, r"C:\scripts\startup.cmm")

    def test_launch_with_cmm_script(self):
        """launch() should include '-s <script>' in the Popen command when cmm_entry_script is set."""
        from GM_VIP_Automation_Framework.core.connection import T32Connection
        conn = T32Connection(
            exe_path="t32marm64.exe",
            config_path="config.t32",
            cmm_entry_script="startup.cmm",
        )
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 1234
            mock_popen.return_value = mock_proc
            conn.launch()
        args = mock_popen.call_args[0][0]
        self.assertIn("-s", args)
        self.assertIn("startup.cmm", args)

    def test_launch_without_cmm_script(self):
        """launch() should NOT include '-s' when cmm_entry_script is empty."""
        from GM_VIP_Automation_Framework.core.connection import T32Connection
        conn = T32Connection(
            exe_path="t32marm64.exe",
            config_path="config.t32",
            cmm_entry_script="",
        )
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 1234
            mock_popen.return_value = mock_proc
            conn.launch()
        args = mock_popen.call_args[0][0]
        self.assertNotIn("-s", args)

    def test_try_connect_success(self):
        """try_connect() should return True and set _connected when pyrcl.connect succeeds."""
        from GM_VIP_Automation_Framework.core.connection import T32Connection
        conn = T32Connection()
        mock_debugger = MagicMock()
        with patch.object(
            sys.modules["lauterbach.trace32.rcl"], "connect", return_value=mock_debugger
        ):
            result = conn.try_connect()
        self.assertTrue(result)
        self.assertTrue(conn.is_connected())

    def test_try_connect_failure_returns_false(self):
        """try_connect() should return False without raising when the connection is refused."""
        from GM_VIP_Automation_Framework.core.connection import T32Connection
        conn = T32Connection()
        with patch.object(
            sys.modules["lauterbach.trace32.rcl"], "connect",
            side_effect=OSError("connection refused"),
        ):
            result = conn.try_connect()
        self.assertFalse(result)
        self.assertFalse(conn.is_connected())


# ---------------------------------------------------------------------------
# debugger
# ---------------------------------------------------------------------------

class TestDebugger(unittest.TestCase):

    def setUp(self):
        from GM_VIP_Automation_Framework.core import debugger as dbg
        self.dbg = dbg

    def test_is_running_true(self):
        conn = _make_conn(running=True)
        self.assertTrue(self.dbg.is_running(conn))

    def test_is_running_false(self):
        conn = _make_conn(running=False)
        self.assertFalse(self.dbg.is_running(conn))

    def test_go_no_op_when_running(self):
        conn = _make_conn(running=True)
        self.dbg.go(conn)
        # cmd should not have been called for GO because already running.
        calls = [str(c) for c in conn.cmd.call_args_list]
        self.assertFalse(any("GO" in c for c in calls))

    def test_go_sends_go_when_halted(self):
        conn = _make_conn(running=False)
        # After GO, make is_running return True for wait_for_running.
        call_count = [0]
        def _fnc(expr):
            if "STATE.RUN" in expr:
                call_count[0] += 1
                return "TRUE()" if call_count[0] > 1 else "FALSE()"
            return "FALSE()"
        conn.fnc.side_effect = _fnc
        self.dbg.go(conn)
        conn.cmd.assert_any_call("GO")

    def test_break_execution(self):
        conn = _make_conn(running=False)
        self.dbg.break_execution(conn)
        conn.cmd.assert_any_call("BREAK")

    def test_get_state(self):
        conn = _make_conn(running=True)
        state = self.dbg.get_state(conn)
        self.assertEqual(state, "running")

    def test_get_pp_register(self):
        conn = _make_conn(running=False)
        pc = self.dbg.get_pp_register(conn)
        self.assertEqual(pc, "0x80001234")

    def test_wait_for_halt_already_halted(self):
        conn = _make_conn(running=False)
        result = self.dbg.wait_for_halt(timeout_s=0.5, connection=conn)
        self.assertTrue(result)

    def test_wait_for_halt_timeout(self):
        conn = _make_conn(running=True)
        result = self.dbg.wait_for_halt(timeout_s=0.05, connection=conn)
        self.assertFalse(result)

    def test_reset_target(self):
        conn = _make_conn(running=False)
        result = self.dbg.reset_target(conn)
        conn.cmd.assert_any_call("SYStem.RESetTarget")
        self.assertTrue(result)

    def test_go_up(self):
        conn = _make_conn(running=False)
        self.dbg.go_up(conn)
        conn.cmd.assert_any_call("Go.Up")

    def test_step_over(self):
        conn = _make_conn(running=False)
        self.dbg.step_over(conn)
        conn.cmd.assert_any_call("STEP.OVER")

    def test_no_default_connection_raises(self):
        from GM_VIP_Automation_Framework.core.debugger import _conn
        from GM_VIP_Automation_Framework.utils.exceptions import T32ConnectionError
        import GM_VIP_Automation_Framework.core.debugger as dbg
        old = dbg.default_connection
        dbg.default_connection = None
        try:
            with self.assertRaises(T32ConnectionError):
                dbg.go()
        finally:
            dbg.default_connection = old


# ---------------------------------------------------------------------------
# breakpoints
# ---------------------------------------------------------------------------

class TestBreakpoints(unittest.TestCase):

    def test_set_breakpoint_success(self):
        from GM_VIP_Automation_Framework.core import breakpoints as bp
        conn = _make_conn(running=False)
        bp.set_breakpoint("myFunc", connection=conn, max_retries=2)
        conn.cmd.assert_any_call("BREAK.SET myFunc")

    def test_set_breakpoint_retries_on_exception(self):
        from GM_VIP_Automation_Framework.core import breakpoints as bp
        from GM_VIP_Automation_Framework.utils.exceptions import T32BreakpointError
        conn = _make_conn(running=False)
        call_count = [0]

        def _cmd(c):
            if "BREAK.SET" in c:
                call_count[0] += 1
                if call_count[0] < 3:
                    raise Exception("not found")
            # Other cmds (halt wait, SYMBOL.RELOAD, etc.) are no-ops.

        conn.cmd.side_effect = _cmd
        # 3 retries should succeed on the 3rd.
        bp.set_breakpoint(
            "myFunc",
            connection=conn,
            max_retries=5,
            retry_interval_s=0.01,
            symbol_reload_at=3,
            symbol_reload_wait_s=0.01,
        )
        self.assertEqual(call_count[0], 3)

    def test_set_breakpoint_exhausted_raises(self):
        from GM_VIP_Automation_Framework.core import breakpoints as bp
        from GM_VIP_Automation_Framework.utils.exceptions import T32BreakpointError
        conn = _make_conn(running=False)
        conn.cmd.side_effect = lambda c: (_ for _ in ()).throw(Exception("fail")) if "BREAK.SET" in c else None
        with self.assertRaises(T32BreakpointError):
            bp.set_breakpoint(
                "badSym",
                connection=conn,
                max_retries=2,
                retry_interval_s=0.01,
                symbol_reload_at=1,
                symbol_reload_wait_s=0.01,
            )

    def test_delete_all_breakpoints(self):
        from GM_VIP_Automation_Framework.core import breakpoints as bp
        conn = _make_conn(running=False)
        bp.delete_all_breakpoints(connection=conn)
        conn.cmd.assert_any_call("BREAK.DELETE /ALL")

    def test_delete_breakpoint(self):
        from GM_VIP_Automation_Framework.core import breakpoints as bp
        conn = _make_conn(running=False)
        bp.delete_breakpoint("myFunc", connection=conn)
        conn.cmd.assert_any_call("BREAK.DELETE myFunc")

    def test_check_halted_at_pass(self):
        from GM_VIP_Automation_Framework.core import breakpoints as bp
        conn = _make_conn(running=False)
        result = bp.check_halted_at("myFunc", timeout_s=0.5, connection=conn)
        self.assertTrue(result)

    def test_check_halted_at_timeout_raises(self):
        from GM_VIP_Automation_Framework.core import breakpoints as bp
        from GM_VIP_Automation_Framework.utils.exceptions import T32BreakpointNotReachedError
        conn = _make_conn(running=True)  # never halts
        with self.assertRaises(T32BreakpointNotReachedError):
            bp.check_halted_at("myFunc", timeout_s=0.05, connection=conn)

    def test_check_halted_at_intermediate_halt_retry(self):
        """check_halted_at() issues GO and retries when ECU halts at wrong address.

        Models the real-hardware scenario (Aurix/ARM) where startup code causes
        an intermediate halt before the test breakpoint is reached.
        intermediate_halt_max_gos=1, delay=0 → one retry, no sleep.
        """
        from GM_VIP_Automation_Framework.core import breakpoints as bp
        from GM_VIP_Automation_Framework.config import settings

        orig_max = settings.intermediate_halt_max_gos
        orig_delay = settings.intermediate_halt_go_delay_s
        orig_run_tmo = settings.run_timeout_s
        try:
            settings.intermediate_halt_max_gos = 1
            settings.intermediate_halt_go_delay_s = 0.0
            # After the retry GO, wait_for_running() needs to succeed quickly.
            settings.run_timeout_s = 0.1

            pc_checks = [0]
            run_polls = [0]

            def _fnc(expr):
                if "STATE.RUN" in expr:
                    run_polls[0] += 1
                    # Running only on the poll immediately after retry GO.
                    return "TRUE()" if run_polls[0] == 1 else "FALSE()"
                if "P:R(PC)" in expr and "==" in expr:
                    pc_checks[0] += 1
                    # First check: wrong address (intermediate halt).
                    # Second check: target address reached.
                    return "TRUE()" if pc_checks[0] > 1 else "FALSE()"
                if "R(PC)" in expr:
                    return "0xA0000000"  # intermediate halt address
                return "0"

            conn = MagicMock()
            conn.is_connected.return_value = True
            conn.fnc.side_effect = _fnc
            conn.cmd.return_value = None

            result = bp.check_halted_at("myFunc", timeout_s=0.5, connection=conn)
            self.assertTrue(result)
            # GO must have been issued during the intermediate-halt retry.
            conn.cmd.assert_any_call("GO")
            # PC comparison was called twice (wrong once, correct once).
            self.assertEqual(pc_checks[0], 2)
        finally:
            settings.intermediate_halt_max_gos = orig_max
            settings.intermediate_halt_go_delay_s = orig_delay
            settings.run_timeout_s = orig_run_tmo

    def test_check_halted_at_intermediate_halt_exhausted_raises(self):
        """check_halted_at() raises T32BreakpointError after exhausting retries."""
        from GM_VIP_Automation_Framework.core import breakpoints as bp
        from GM_VIP_Automation_Framework.utils.exceptions import T32BreakpointError
        from GM_VIP_Automation_Framework.config import settings

        orig_max = settings.intermediate_halt_max_gos
        orig_delay = settings.intermediate_halt_go_delay_s
        orig_run_tmo = settings.run_timeout_s
        try:
            settings.intermediate_halt_max_gos = 1
            settings.intermediate_halt_go_delay_s = 0.0
            settings.run_timeout_s = 0.05

            def _fnc(expr):
                if "STATE.RUN" in expr:
                    return "FALSE()"
                if "P:R(PC)" in expr and "==" in expr:
                    return "FALSE()"  # always wrong address
                if "R(PC)" in expr:
                    return "0xA0000000"
                return "0"

            conn = MagicMock()
            conn.is_connected.return_value = True
            conn.fnc.side_effect = _fnc
            conn.cmd.return_value = None

            with self.assertRaises(T32BreakpointError):
                bp.check_halted_at("myFunc", timeout_s=0.2, connection=conn)
        finally:
            settings.intermediate_halt_max_gos = orig_max
            settings.intermediate_halt_go_delay_s = orig_delay
            settings.run_timeout_s = orig_run_tmo

    def test_check_halted_at_max_gos_zero_disables_retry(self):
        """Setting intermediate_halt_max_gos=0 disables intermediate-halt retry."""
        from GM_VIP_Automation_Framework.core import breakpoints as bp
        from GM_VIP_Automation_Framework.utils.exceptions import T32BreakpointError
        from GM_VIP_Automation_Framework.config import settings

        orig_max = settings.intermediate_halt_max_gos
        orig_delay = settings.intermediate_halt_go_delay_s
        try:
            settings.intermediate_halt_max_gos = 0
            settings.intermediate_halt_go_delay_s = 0.0

            def _fnc(expr):
                if "STATE.RUN" in expr:
                    return "FALSE()"
                if "P:R(PC)" in expr and "==" in expr:
                    return "FALSE()"  # wrong address, no retry allowed
                if "R(PC)" in expr:
                    return "0xA0000000"
                return "0"

            conn = MagicMock()
            conn.is_connected.return_value = True
            conn.fnc.side_effect = _fnc
            conn.cmd.return_value = None

            with self.assertRaises(T32BreakpointError):
                bp.check_halted_at("myFunc", timeout_s=0.2, connection=conn)
            # GO should NOT have been issued (retries disabled).
            go_calls = [c for c in conn.cmd.call_args_list if "GO" in str(c)]
            self.assertEqual(go_calls, [])
        finally:
            settings.intermediate_halt_max_gos = orig_max
            settings.intermediate_halt_go_delay_s = orig_delay

    def test_set_breakpoint_write(self):
        from GM_VIP_Automation_Framework.core import breakpoints as bp
        conn = _make_conn(running=False)
        bp.set_breakpoint_write("myVar", connection=conn)
        conn.cmd.assert_any_call("VAR.BREAK.SET myVar /W")

    def test_set_breakpoint_read(self):
        from GM_VIP_Automation_Framework.core import breakpoints as bp
        conn = _make_conn(running=False)
        bp.set_breakpoint_read("myVar", connection=conn)
        conn.cmd.assert_any_call("VAR.BREAK.SET myVar /R")


# ---------------------------------------------------------------------------
# variables
# ---------------------------------------------------------------------------

class TestVariables(unittest.TestCase):

    def test_read_variable(self):
        from GM_VIP_Automation_Framework.core import variables as var
        conn = _make_conn(running=False)
        value = var.read_variable("myVar", connection=conn)
        self.assertEqual(value, "42")

    def test_set_variable(self):
        from GM_VIP_Automation_Framework.core import variables as var
        conn = _make_conn(running=False)
        var.set_variable("myVar", 100, connection=conn)
        conn.cmd.assert_any_call("VAR.SET myVar=100")

    def test_check_variable_pass(self):
        from GM_VIP_Automation_Framework.core import variables as var
        conn = _make_conn(running=False)
        result = var.check_variable("myVar", "42", connection=conn)
        self.assertTrue(result)

    def test_check_variable_fail_raises(self):
        from GM_VIP_Automation_Framework.core import variables as var
        from GM_VIP_Automation_Framework.utils.exceptions import T32VariableError
        conn = _make_conn(running=False)
        with self.assertRaises(T32VariableError):
            var.check_variable("myVar", "99", connection=conn)

    def test_check_variable_until_success(self):
        from GM_VIP_Automation_Framework.core import variables as var
        conn = _make_conn(running=False)
        # Mock returns "42" immediately, so expected="42" should pass.
        result = var.check_variable_until("myVar", "42", timeout_s=1.0, connection=conn)
        self.assertTrue(result)

    def test_check_variable_until_timeout_raises(self):
        from GM_VIP_Automation_Framework.core import variables as var
        from GM_VIP_Automation_Framework.utils.exceptions import T32TimeoutError
        conn = _make_conn(running=False)
        # Mock returns "42" but we expect "99" – should timeout.
        with self.assertRaises(T32TimeoutError):
            var.check_variable_until("myVar", "99", timeout_s=0.05, connection=conn)

    def test_check_array_element(self):
        from GM_VIP_Automation_Framework.core import variables as var
        conn = _make_conn(running=False)
        # VAR.VALUE returns "42" for any expr, so this should pass.
        result = var.check_array_element("myArr", 2, "42", connection=conn)
        self.assertTrue(result)


# ---------------------------------------------------------------------------
# registers
# ---------------------------------------------------------------------------

class TestRegisters(unittest.TestCase):

    def test_read_register(self):
        from GM_VIP_Automation_Framework.core import registers as reg
        conn = _make_conn(running=False)
        val = reg.read_register("R0", connection=conn)
        # The mock returns "0x80001234" for R(PC), but R0 also goes through fnc.
        self.assertIsInstance(val, str)

    def test_set_register(self):
        from GM_VIP_Automation_Framework.core import registers as reg
        conn = _make_conn(running=False)
        reg.set_register("R0", 0x1234, connection=conn)
        conn.cmd.assert_any_call("Register.Set R0 0x1234")

    def test_check_register_pass(self):
        from GM_VIP_Automation_Framework.core import registers as reg
        conn = _make_conn(running=False)
        # Mock returns "0x80001234" for R(PC) expression.
        # check_register("PC", "0x80001234") should pass.
        result = reg.check_register("PC", "0x80001234", connection=conn)
        self.assertTrue(result)

    def test_check_register_fail_raises(self):
        from GM_VIP_Automation_Framework.core import registers as reg
        from GM_VIP_Automation_Framework.utils.exceptions import T32RegisterError
        conn = _make_conn(running=False)
        with self.assertRaises(T32RegisterError):
            reg.check_register("R0", "0xDEAD", connection=conn)

    def test_check_register_bit_pass(self):
        from GM_VIP_Automation_Framework.core import registers as reg
        conn = _make_conn(running=False)
        # 0x80001234 bit 2 = 1
        result = reg.check_register_bit("PC", 2, 1, connection=conn)
        self.assertTrue(result)

    def test_check_register_bit_invalid_expected(self):
        from GM_VIP_Automation_Framework.core import registers as reg
        conn = _make_conn(running=False)
        with self.assertRaises(ValueError):
            reg.check_register_bit("PC", 0, 2, connection=conn)


# ---------------------------------------------------------------------------
# symbols
# ---------------------------------------------------------------------------

class TestSymbols(unittest.TestCase):

    def test_symbol_exists_true(self):
        from GM_VIP_Automation_Framework.core import symbols as sym
        conn = _make_conn(running=False)
        self.assertTrue(sym.symbol_exists("myFunc", connection=conn))

    def test_symbol_exists_false(self):
        from GM_VIP_Automation_Framework.core import symbols as sym
        conn = _make_conn(running=False)
        # side_effect takes priority over return_value, so clear it first.
        conn.fnc.side_effect = None
        conn.fnc.return_value = "FALSE()"
        self.assertFalse(sym.symbol_exists("missingFunc", connection=conn))

    def test_get_symbol_address(self):
        from GM_VIP_Automation_Framework.core import symbols as sym
        conn = _make_conn(running=False)
        addr = sym.get_symbol_address("myFunc", connection=conn)
        self.assertEqual(addr, "0xA0000000")

    def test_get_symbol_address_not_found_raises(self):
        from GM_VIP_Automation_Framework.core import symbols as sym
        from GM_VIP_Automation_Framework.utils.exceptions import T32SymbolError
        conn = _make_conn(running=False)
        # side_effect takes priority over return_value, so clear it first.
        conn.fnc.side_effect = None
        conn.fnc.return_value = "FALSE()"
        with self.assertRaises(T32SymbolError):
            sym.get_symbol_address("missing", connection=conn)

    def test_reload_symbols(self):
        from GM_VIP_Automation_Framework.core import symbols as sym
        conn = _make_conn(running=False)
        sym.reload_symbols(wait_s=0.01, connection=conn)
        conn.cmd.assert_any_call("SYMBOL.RELOAD")


# ---------------------------------------------------------------------------
# Synchronization: post_reset_settle_s and go_settle_s / go() error
# ---------------------------------------------------------------------------

class TestSynchronization(unittest.TestCase):
    """Tests for the new synchronization / handshaking improvements."""

    def setUp(self):
        from GM_VIP_Automation_Framework import config
        self._orig_post_reset = config.settings.post_reset_settle_s
        self._orig_go_settle = config.settings.go_settle_s
        self._orig_run_timeout = config.settings.run_timeout_s
        self._orig_poll = config.settings.poll_interval_s
        config.settings.poll_interval_s = 0.01

    def tearDown(self):
        from GM_VIP_Automation_Framework import config
        config.settings.post_reset_settle_s = self._orig_post_reset
        config.settings.go_settle_s = self._orig_go_settle
        config.settings.run_timeout_s = self._orig_run_timeout
        config.settings.poll_interval_s = self._orig_poll

    def test_post_reset_settle_applied_after_reset(self):
        """reset_target() should sleep post_reset_settle_s after the ECU halts."""
        import time
        from GM_VIP_Automation_Framework import config
        from GM_VIP_Automation_Framework.core import debugger as dbg

        config.settings.post_reset_settle_s = 0.05  # short but measurable

        conn = _make_conn(running=False)
        start = time.monotonic()
        dbg.reset_target(conn)
        elapsed = time.monotonic() - start

        # Should have slept at least post_reset_settle_s (0.05s).
        # Use 60% of the target as the lower bound to avoid flakiness under load.
        self.assertGreaterEqual(elapsed, 0.03)

    def test_post_reset_settle_zero_no_extra_delay(self):
        """reset_target() should not add any delay when post_reset_settle_s=0."""
        import time
        from GM_VIP_Automation_Framework import config
        from GM_VIP_Automation_Framework.core import debugger as dbg

        config.settings.post_reset_settle_s = 0.0

        conn = _make_conn(running=False)
        start = time.monotonic()
        dbg.reset_target(conn)
        elapsed = time.monotonic() - start

        # reset_target() always includes a fixed 0.25s transient-phase sleep.
        # With post_reset_settle_s=0 there should be no additional delay beyond
        # that 0.25s + poll overhead, so the total should stay well under 0.5s.
        self.assertLess(elapsed, 0.5)

    def test_go_raises_timeout_when_ecu_does_not_run(self):
        """go() should raise T32TimeoutError when the ECU never starts running."""
        from GM_VIP_Automation_Framework import config
        from GM_VIP_Automation_Framework.core import debugger as dbg
        from GM_VIP_Automation_Framework.utils.exceptions import T32TimeoutError

        config.settings.run_timeout_s = 0.05
        config.settings.go_settle_s = 0.0

        # ECU stays halted even after GO.
        conn = _make_conn(running=False)

        with self.assertRaises(T32TimeoutError) as ctx:
            dbg.go(conn)

        self.assertIn("running state", str(ctx.exception).lower())

    def test_go_succeeds_when_ecu_starts_running(self):
        """go() should complete without error when ECU enters running state."""
        from GM_VIP_Automation_Framework import config
        from GM_VIP_Automation_Framework.core import debugger as dbg

        config.settings.go_settle_s = 0.0

        # ECU transitions to running after the first STATE.RUN() poll.
        call_count = [0]
        def _fnc(expr):
            if "STATE.RUN" in expr:
                call_count[0] += 1
                return "TRUE()" if call_count[0] > 1 else "FALSE()"
            return "FALSE()"

        conn = _make_conn(running=False)
        conn.fnc.side_effect = _fnc

        dbg.go(conn)  # must not raise
        conn.cmd.assert_any_call("GO")

    def test_new_settings_have_correct_defaults(self):
        """post_reset_settle_s and go_settle_s defaults should be sensible."""
        from GM_VIP_Automation_Framework.config import T32Settings
        fresh = T32Settings()
        self.assertGreater(fresh.post_reset_settle_s, 0)
        self.assertGreaterEqual(fresh.go_settle_s, 0)


# ---------------------------------------------------------------------------
# Runner: go_before_check workflow
# ---------------------------------------------------------------------------

class TestRunnerGoBeforeCheck(unittest.TestCase):
    """Tests for the go_before_check JSON key in the test runner."""

    def _make_runner_conn(self, halt_after_go: bool = True):
        """Return a mock connection that starts halted, goes to running on GO,
        then halts again (simulating a natural halt after init code runs).
        The mock also responds to all RCL functions used by the runner."""
        conn = MagicMock()
        conn.is_connected.return_value = True

        go_issued = [False]

        def _fnc(expr):
            if "STATE.RUN" in expr:
                # Running only briefly right after GO.
                if go_issued[0] and halt_after_go:
                    go_issued[0] = False  # reset so next poll returns halted
                    return "TRUE()"       # one "running" poll after GO
                return "FALSE()"          # otherwise halted
            if "P:R(PC)" in expr and "==" in expr:
                return "TRUE()"
            if "R(PC)" in expr:
                return "0x80001234"
            if "VAR.VALUE" in expr:
                return "42"
            if "SYMBOL.EXIST" in expr:
                return "TRUE()"
            if "ADDRESS.OFFSET" in expr:
                return "0xA0000000"
            if "CORE()" in expr:
                return "TRUE()"
            return "0"

        def _cmd(c):
            if c == "GO":
                go_issued[0] = True

        conn.fnc.side_effect = _fnc
        conn.cmd.side_effect = _cmd
        return conn

    def test_go_before_check_issues_go_then_reads_variable(self):
        """Runner should issue GO + wait-for-halt before variable checks when
        go_before_check=True and no breakpoints are defined."""
        import sys
        from pathlib import Path
        from unittest.mock import patch, MagicMock

        from GM_VIP_Automation_Framework import runner, config

        # Use very short timeouts.
        config.settings.halt_timeout_s = 1.0
        config.settings.run_timeout_s = 0.5
        config.settings.poll_interval_s = 0.01
        config.settings.go_settle_s = 0.0
        config.settings.post_reset_settle_s = 0.0

        tc_def = {
            "name": "TC_GoBeforeCheck",
            "enabled": True,
            "reset_before": False,
            "go_before_check": True,
            "breakpoints": [],
            "variables_write": {},
            "variables_check": {
                "myModule.myStatus": {"expected": None, "description": "just log"}
            },
            "symbols_inspect": [],
        }

        conn = self._make_runner_conn(halt_after_go=True)
        from GM_VIP_Automation_Framework.report import TestCaseReport
        report = TestCaseReport(name="test")

        runner._run_one(tc_def, conn, report)

        # GO must have been issued.
        go_calls = [str(a) for a in conn.cmd.call_args_list if "GO" in str(a)]
        self.assertTrue(any("GO" in c for c in go_calls), "GO was not issued")
        # VAR.VALUE must have been read.
        fnc_calls = [str(a) for a in conn.fnc.call_args_list]
        self.assertTrue(
            any("VAR.VALUE" in c for c in fnc_calls),
            "VAR.VALUE not called after go_before_check GO",
        )

    def test_go_before_check_false_does_not_issue_go(self):
        """Runner should NOT issue GO when go_before_check=False and no breakpoints."""
        from GM_VIP_Automation_Framework import runner, config

        config.settings.halt_timeout_s = 1.0
        config.settings.run_timeout_s = 0.5
        config.settings.poll_interval_s = 0.01
        config.settings.go_settle_s = 0.0
        config.settings.post_reset_settle_s = 0.0

        tc_def = {
            "name": "TC_NoGo",
            "enabled": True,
            "reset_before": False,
            "go_before_check": False,
            "breakpoints": [],
            "variables_write": {},
            "variables_check": {
                "myModule.myStatus": {"expected": None}
            },
            "symbols_inspect": [],
        }

        conn = self._make_runner_conn(halt_after_go=False)
        from GM_VIP_Automation_Framework.report import TestCaseReport
        report = TestCaseReport(name="test")

        runner._run_one(tc_def, conn, report)

        # cmd should not have received a bare "GO" call
        go_calls = [str(a) for a in conn.cmd.call_args_list if str(a) == "call('GO')"]
        self.assertEqual(len(go_calls), 0, "GO should NOT have been issued")


if __name__ == "__main__":
    unittest.main()
