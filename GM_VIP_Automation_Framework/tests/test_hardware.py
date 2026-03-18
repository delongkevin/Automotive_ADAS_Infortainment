"""
Tests for the hardware interface modules:
  - GM_VIP_Automation_Framework.core.can_bus   (CANBusClient mock mode)
  - GM_VIP_Automation_Framework.core.canoe     (CANoeClient mock mode)
  - GM_VIP_Automation_Framework.core.power_supply (BKPrecision1687B mock mode)

All tests run in mock/no-hardware mode so no physical devices are needed.
"""

import sys
import types
import unittest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub lauterbach before any framework import (same pattern as conftest.py)
# ---------------------------------------------------------------------------
sys.modules.setdefault("lauterbach", MagicMock())
sys.modules.setdefault("lauterbach.trace32", MagicMock())
sys.modules.setdefault("lauterbach.trace32.rcl", MagicMock())
sys.modules.setdefault("lauterbach.trace32.rcl._rc", MagicMock())
sys.modules.setdefault("lauterbach.trace32.rcl._rc._error", MagicMock())


# ===========================================================================
# CANBusClient – mock mode
# ===========================================================================

class TestCANBusClientMock(unittest.TestCase):
    """CANBusClient in mock=True mode – no python-can needed."""

    def _client(self):
        from GM_VIP_Automation_Framework.core.can_bus import CANBusClient
        return CANBusClient(mock=True)

    def test_connect_disconnect(self):
        c = self._client()
        c.connect()
        self.assertTrue(c.is_connected)
        c.disconnect()
        self.assertTrue(c.is_connected)  # mock always returns True

    def test_context_manager(self):
        from GM_VIP_Automation_Framework.core.can_bus import CANBusClient
        with CANBusClient(mock=True) as bus:
            self.assertTrue(bus.is_connected)

    def test_send_no_error(self):
        with self._client() as bus:
            bus.send(arbitration_id=0x401, data=[0x00]*8)

    def test_send_extended(self):
        with self._client() as bus:
            bus.send(arbitration_id=0x18FF4001, data=[0xAA]*8, is_extended_id=True)

    def test_send_periodic_no_error(self):
        with self._client() as bus:
            bus.send_periodic(
                arbitration_id=0x401,
                data=[0x01]*8,
                period_s=0.01,
                duration_s=0.0,
            )

    def test_receive_returns_none_in_mock(self):
        with self._client() as bus:
            result = bus.receive(timeout_s=0.1)
            self.assertIsNone(result)

    def test_receive_many_yields_nothing_in_mock(self):
        with self._client() as bus:
            frames = list(bus.receive_many(count=5, timeout_s=0.1))
            self.assertEqual(frames, [])

    def test_flush_rx_returns_zero_in_mock(self):
        with self._client() as bus:
            self.assertEqual(bus.flush_rx(), 0)

    def test_trigger_can_init(self):
        with self._client() as bus:
            bus.trigger_can_init(can_id=0x401, repeat=3)

    def test_trigger_can_rx(self):
        with self._client() as bus:
            bus.trigger_can_rx(can_id=0x456)

    def test_trigger_can_tx_confirm(self):
        with self._client() as bus:
            bus.trigger_can_tx_confirm(can_id=0x18FF4001, is_extended_id=True)

    def test_trigger_bus_off_recovery(self):
        with self._client() as bus:
            bus.trigger_bus_off_recovery(error_frame_count=3)

    def test_error_raised_without_pycan_in_live_mode(self):
        from GM_VIP_Automation_Framework.core.can_bus import CANBusClient, CANBusError
        # Temporarily remove python-can from sys.modules if it exists.
        import GM_VIP_Automation_Framework.core.can_bus as _mod
        original = _mod._CAN_AVAILABLE
        _mod._CAN_AVAILABLE = False
        try:
            bus = CANBusClient(mock=False)
            with self.assertRaises(CANBusError):
                bus.connect()
        finally:
            _mod._CAN_AVAILABLE = original


# ===========================================================================
# CANoeClient – mock mode
# ===========================================================================

class TestCANoeClientMock(unittest.TestCase):
    """CANoeClient in mock=True mode – no win32com needed."""

    def _client(self):
        from GM_VIP_Automation_Framework.core.canoe import CANoeClient
        return CANoeClient(mock=True)

    def test_connect_disconnect(self):
        c = self._client()
        c.connect()
        self.assertTrue(c.is_connected)
        c.disconnect()

    def test_context_manager(self):
        from GM_VIP_Automation_Framework.core.canoe import CANoeClient
        with CANoeClient(mock=True) as canoe:
            self.assertTrue(canoe.is_connected)

    def test_start_stop_measurement(self):
        with self._client() as canoe:
            canoe.start_measurement()
            canoe.stop_measurement()

    def test_set_get_env_var(self):
        with self._client() as canoe:
            canoe.set_env_var("MyVar", 42)
            val = canoe.get_env_var("MyVar")
            self.assertEqual(val, 0)   # mock always returns 0

    def test_send_can_message(self):
        with self._client() as canoe:
            canoe.send_can_message(channel=1, can_id=0x401, data=[0]*8)

    def test_call_capl_function(self):
        with self._client() as canoe:
            result = canoe.call_capl_function("TriggerCanInit", 1)
            self.assertIsNone(result)

    def test_trigger_can_init(self):
        with self._client() as canoe:
            canoe.trigger_can_init(channel=1, can_id=0x401)

    def test_trigger_can_rx(self):
        with self._client() as canoe:
            canoe.trigger_can_rx(channel=1, can_id=0x456, data=[0xAA]*8)

    def test_trigger_can_tx_confirm(self):
        with self._client() as canoe:
            canoe.trigger_can_tx_confirm(channel=1, can_id=0x18FF4001)

    def test_trigger_bus_stop(self):
        with self._client() as canoe:
            canoe.trigger_bus_stop(env_var="BusStop", resume_delay_s=0.0)

    def test_trigger_wakeup_frame(self):
        with self._client() as canoe:
            canoe.trigger_wakeup_frame(channel=1, can_id=0x100)

    def test_get_measurement_state_mock(self):
        with self._client() as canoe:
            state = canoe.get_measurement_state()
            self.assertEqual(state, "MOCK")

    def test_is_measuring_false_in_mock(self):
        with self._client() as canoe:
            self.assertFalse(canoe.is_measuring)

    def test_error_raised_without_win32_in_live_mode(self):
        from GM_VIP_Automation_Framework.core.canoe import CANoeClient, CANoeError
        import GM_VIP_Automation_Framework.core.canoe as _mod
        original = _mod._WIN32_AVAILABLE
        _mod._WIN32_AVAILABLE = False
        try:
            c = CANoeClient(mock=False)
            with self.assertRaises(CANoeError):
                c.connect()
        finally:
            _mod._WIN32_AVAILABLE = original


# ===========================================================================
# BKPrecision1687B – mock mode
# ===========================================================================

class TestBKPrecision1687BMock(unittest.TestCase):
    """BKPrecision1687B in mock=True mode – no serial port needed."""

    def _psu(self, port="COM4"):
        from GM_VIP_Automation_Framework.core.power_supply import BKPrecision1687B
        return BKPrecision1687B(port=port, mock=True)

    def test_default_port_is_com4(self):
        from GM_VIP_Automation_Framework.core.power_supply import BKPrecision1687B
        self.assertEqual(BKPrecision1687B.DEFAULT_PORT, "COM4")

    def test_connect_disconnect(self):
        psu = self._psu()
        psu.connect()
        self.assertTrue(psu.is_connected)
        psu.disconnect()

    def test_context_manager(self):
        from GM_VIP_Automation_Framework.core.power_supply import BKPrecision1687B
        with BKPrecision1687B(port="COM4", mock=True) as psu:
            self.assertTrue(psu.is_connected)

    def test_set_voltage(self):
        with self._psu() as psu:
            psu.set_voltage(12.0)   # must not raise

    def test_set_voltage_negative_raises(self):
        with self._psu() as psu:
            with self.assertRaises(ValueError):
                psu.set_voltage(-1.0)

    def test_set_current(self):
        with self._psu() as psu:
            psu.set_current(2.0)

    def test_set_current_negative_raises(self):
        with self._psu() as psu:
            with self.assertRaises(ValueError):
                psu.set_current(-0.5)

    def test_set_output(self):
        with self._psu() as psu:
            psu.set_output(12.0, 2.0)

    def test_output_on_off(self):
        with self._psu() as psu:
            psu.output_on()
            psu.output_off()

    def test_measure_returns_zeros_in_mock(self):
        with self._psu() as psu:
            v, i = psu.measure()
            self.assertEqual(v, 0.0)
            self.assertEqual(i, 0.0)

    def test_measure_voltage(self):
        with self._psu() as psu:
            self.assertEqual(psu.measure_voltage(), 0.0)

    def test_measure_current(self):
        with self._psu() as psu:
            self.assertEqual(psu.measure_current(), 0.0)

    def test_power_cycle_no_error(self):
        with self._psu() as psu:
            psu.power_cycle(off_duration_s=0.0, on_settle_s=0.0)

    def test_safe_startup_no_error(self):
        with self._psu() as psu:
            psu.safe_startup(
                volts=12.0,
                amps=2.0,
                ramp_steps=3,
                ramp_step_delay_s=0.0,
                settle_s=0.0,
            )

    def test_getd_regex_parse(self):
        """Unit-test the GETD response regex independently of serial I/O.

        GETD response format: VVVVVCCCCCM  (11 chars + optional \\r)
          VVVVV – voltage × 100, zero-padded 5 digits (e.g. "01200" = 12.00 V)
          CCCCC – current × 1000, zero-padded 5 digits (e.g. "02000" = 2.000 A)
          M     – mode: 0 = CV (constant voltage), 1 = CC (constant current)
        """
        from GM_VIP_Automation_Framework.core.power_supply import BKPrecision1687B
        pattern = BKPrecision1687B._GETD_RE
        # 12.00 V → "01200" (1200 = 12.00 × 100), 2.000 A → "02000" (2000 = 2.000 × 1000), CV = "0"
        response = "01200" + "02000" + "0"   # 11-char GETD response string
        m = pattern.match(response)
        self.assertIsNotNone(m, f"Regex did not match response {response!r}")
        voltage = int(m.group(1)) / 100.0    # VVVVV ÷ 100 → volts
        current = int(m.group(2)) / 1000.0   # CCCCC ÷ 1000 → amps
        self.assertAlmostEqual(voltage, 12.0)
        self.assertAlmostEqual(current, 2.0)
        self.assertEqual(m.group(3), "0")    # CV mode

    def test_error_raised_without_pyserial_in_live_mode(self):
        from GM_VIP_Automation_Framework.core.power_supply import (
            BKPrecision1687B, PowerSupplyError,
        )
        import GM_VIP_Automation_Framework.core.power_supply as _mod
        original = _mod._SERIAL_AVAILABLE
        _mod._SERIAL_AVAILABLE = False
        try:
            psu = BKPrecision1687B(port="COM4", mock=False)
            with self.assertRaises(PowerSupplyError):
                psu.connect()
        finally:
            _mod._SERIAL_AVAILABLE = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
