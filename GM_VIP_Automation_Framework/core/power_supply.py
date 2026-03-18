"""
GM VIP Automation Framework – BK Precision 1687B Power Supply Driver
======================================================================
Serial RS-232 / USB-CDC driver for the **BK Precision 1685B / 1687B / 1688B**
family of programmable DC power supplies.  These three models share the same
ASCII serial command protocol, so this driver works with all of them.  The
class is named ``BKPrecision1687B`` because that is the specific model
installed on the test bench (COM4).

Hardware connection
-------------------
The supply's USB port enumerates as a virtual COM port (the USB-CDC driver
from BK Precision or Silicon Labs CP210x is required).  On the test bench
the supply is on **COM4** (Windows) – this is the default port used by this
module.

Communication settings (fixed by the supply firmware)::

    Baud:      9600
    Data bits: 8
    Parity:    None
    Stop bits: 1
    Flow ctrl: None

Command protocol
----------------
Commands are plain ASCII strings terminated with ``\\r``.  The supply echoes
``OK\\r`` on success or ``Error\\r`` on failure.  Query commands (``GETD``,
``GETM``) return the requested data followed by ``\\r``.

Key commands
~~~~~~~~~~~~
+------------------+--------------------------------------------+
| Command          | Description                                |
+==================+============================================+
| ``SESS``         | Enter remote-control mode                  |
+------------------+--------------------------------------------+
| ``ENDS``         | Return to local (front-panel) control      |
+------------------+--------------------------------------------+
| ``SOUT0``        | Disable output (output OFF)                |
+------------------+--------------------------------------------+
| ``SOUT1``        | Enable output (output ON)                  |
+------------------+--------------------------------------------+
| ``VOLT<V>``      | Set voltage  (e.g. ``VOLT12.00``)          |
+------------------+--------------------------------------------+
| ``CURR<A>``      | Set current limit (e.g. ``CURR2.000``)     |
+------------------+--------------------------------------------+
| ``GETD``         | Get display readback (voltage & current)   |
+------------------+--------------------------------------------+

``GETD`` response format::

    <VVVVV><CCCCC><S>\\r

    VVVVV – voltage ×100 (5 digits, zero-padded, e.g. "01200" = 12.00 V)
    CCCCC – current ×1000 (5 digits, zero-padded, e.g. "02000" = 2.000 A)
    S     – regulation mode: 0 = CV (constant voltage), 1 = CC (constant current)

Graceful degradation
--------------------
If ``pyserial`` is not installed the module still imports cleanly; every
operation raises :class:`PowerSupplyError` with an explanatory message.
Install with::

    pip install pyserial

Typical usage
-------------
::

    from GM_VIP_Automation_Framework.core.power_supply import BKPrecision1687B

    with BKPrecision1687B(port="COM4") as psu:
        psu.set_voltage(12.0)
        psu.set_current(2.0)
        psu.output_on()

        v, i = psu.measure()
        print(f"Output: {v:.2f} V  {i:.3f} A")

        psu.output_off()
"""

from __future__ import annotations

import re
import time
from typing import Optional, Tuple

from ..utils.logger import get_logger

logger = get_logger("power_supply")

__all__ = ["BKPrecision1687B", "PowerSupplyError"]


# ---------------------------------------------------------------------------
# Optional pyserial import
# ---------------------------------------------------------------------------

try:
    import serial as _serial  # type: ignore[import]
    _SERIAL_AVAILABLE = True
except ImportError:
    _serial = None  # type: ignore[assignment]
    _SERIAL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class PowerSupplyError(Exception):
    """Raised when a power supply operation fails or pyserial is not installed."""


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

class BKPrecision1687B:
    """Driver for the BK Precision 1685B / 1687B / 1688B power supply.

    Parameters
    ----------
    port:
        Serial port name.  On the test bench the supply is on **``"COM4"``**
        (Windows).  Use ``"/dev/ttyUSB0"`` style names on Linux.
    baudrate:
        Must match the supply's front-panel setting (default 9600).
    timeout_s:
        Per-command read timeout in seconds.
    mock:
        When ``True``, skip all serial I/O and log operations instead.
        Useful for unit tests and CI environments that lack the hardware.
    """

    # BK Precision 1687B default serial port on the test bench.
    DEFAULT_PORT = "COM4"

    # Fixed serial parameters (not configurable on the supply).
    _BAUDRATE    = 9600
    _BYTESIZE    = 8
    _PARITY      = "N"
    _STOPBITS    = 1

    # Regex for GETD response: 5 voltage digits + 5 current digits + 1 mode char.
    _GETD_RE = re.compile(r"^(\d{5})(\d{5})([01])\r?$")

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baudrate: int = _BAUDRATE,
        timeout_s: float = 2.0,
        mock: bool = False,
    ) -> None:
        self._port      = port
        self._baudrate  = baudrate
        self._timeout_s = timeout_s
        self._mock      = mock
        self._ser: Optional[object] = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "BKPrecision1687B":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        try:
            self.output_off()
            self._end_session()
        except Exception:  # noqa: BLE001
            pass
        self.disconnect()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the serial port and enter remote-control mode.

        Raises
        ------
        PowerSupplyError
            When ``pyserial`` is not installed, or the port cannot be opened.
        """
        if self._mock:
            logger.info("[MOCK] BKPrecision1687B.connect() – port=%s.", self._port)
            return

        if not _SERIAL_AVAILABLE:
            raise PowerSupplyError(
                "pyserial is not installed.  Run:  pip install pyserial  then retry."
            )

        logger.info(
            "Opening serial port %s at %d baud for BK Precision 1687B.",
            self._port, self._baudrate,
        )
        try:
            self._ser = _serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                bytesize=self._BYTESIZE,
                parity=self._PARITY,
                stopbits=self._STOPBITS,
                timeout=self._timeout_s,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
        except Exception as exc:
            raise PowerSupplyError(
                f"Could not open serial port {self._port!r}: {exc}"
            ) from exc

        # Small delay to let the USB-CDC adapter settle.
        time.sleep(0.2)
        self._start_session()

    def disconnect(self) -> None:
        """Close the serial port."""
        if self._ser is not None:
            try:
                self._ser.close()  # type: ignore[union-attr]
            except Exception as exc:  # noqa: BLE001
                logger.warning("Serial close raised: %s", exc)
            finally:
                self._ser = None
        logger.info("BK Precision 1687B disconnected.")

    @property
    def is_connected(self) -> bool:
        """``True`` when the port is open (or in mock mode)."""
        if self._mock:
            return True
        return self._ser is not None and getattr(self._ser, "is_open", False)

    # ------------------------------------------------------------------
    # Output control
    # ------------------------------------------------------------------

    def output_on(self) -> None:
        """Enable the supply output (SOUT1).

        Raises
        ------
        PowerSupplyError
            If the command is rejected by the supply.
        """
        logger.info("PSU output ON.")
        self._cmd("SOUT1")

    def output_off(self) -> None:
        """Disable the supply output (SOUT0).

        Raises
        ------
        PowerSupplyError
            If the command is rejected by the supply.
        """
        logger.info("PSU output OFF.")
        self._cmd("SOUT0")

    # ------------------------------------------------------------------
    # Setpoint control
    # ------------------------------------------------------------------

    def set_voltage(self, volts: float) -> None:
        """Set the output voltage setpoint.

        Parameters
        ----------
        volts:
            Target voltage in volts (e.g. ``12.0`` for 12 V).
            The 1687B main output supports 0–30 V.

        Raises
        ------
        PowerSupplyError
            If the command fails or the value is out of range.
        ValueError
            If *volts* is negative.
        """
        if volts < 0:
            raise ValueError(f"Voltage must be ≥ 0 V, got {volts!r}.")
        logger.info("PSU set voltage → %.3f V.", volts)
        self._cmd(f"VOLT{volts:.2f}")

    def set_current(self, amps: float) -> None:
        """Set the output current limit.

        Parameters
        ----------
        amps:
            Current limit in amperes (e.g. ``2.0`` for 2 A).
            The 1687B main output supports 0–3 A.

        Raises
        ------
        PowerSupplyError
            If the command fails or the value is out of range.
        ValueError
            If *amps* is negative.
        """
        if amps < 0:
            raise ValueError(f"Current must be ≥ 0 A, got {amps!r}.")
        logger.info("PSU set current limit → %.3f A.", amps)
        self._cmd(f"CURR{amps:.3f}")

    def set_output(self, volts: float, amps: float) -> None:
        """Convenience: set voltage and current in one call.

        Parameters
        ----------
        volts:
            Target voltage in volts.
        amps:
            Current limit in amperes.
        """
        self.set_voltage(volts)
        self.set_current(amps)

    # ------------------------------------------------------------------
    # Measurement / readback
    # ------------------------------------------------------------------

    def measure(self) -> Tuple[float, float]:
        """Read back the actual output voltage and current (GETD).

        Returns
        -------
        tuple[float, float]
            ``(voltage_V, current_A)`` as measured at the supply output
            terminals.

        Raises
        ------
        PowerSupplyError
            On communication error or unexpected response format.
        """
        if self._mock:
            logger.debug("[MOCK] PSU measure() → (0.0, 0.0).")
            return (0.0, 0.0)

        self._require_connected()
        raw = self._query("GETD")
        m = self._GETD_RE.match(raw.strip())
        if m is None:
            raise PowerSupplyError(
                f"Unexpected GETD response from PSU: {raw!r}.  "
                "Expected 11-character string (5V + 5I + 1mode)."
            )
        voltage = int(m.group(1)) / 100.0    # VVVVV → volts
        current = int(m.group(2)) / 1000.0   # CCCCC → amps
        mode    = "CV" if m.group(3) == "0" else "CC"
        logger.info(
            "PSU readback: %.2f V  %.3f A  [%s].", voltage, current, mode
        )
        return (voltage, current)

    def measure_voltage(self) -> float:
        """Return the measured output voltage in volts."""
        return self.measure()[0]

    def measure_current(self) -> float:
        """Return the measured output current in amperes."""
        return self.measure()[1]

    # ------------------------------------------------------------------
    # Power-cycle helpers (useful for ECU resets during T32 testing)
    # ------------------------------------------------------------------

    def power_cycle(
        self,
        off_duration_s: float = 1.0,
        on_settle_s: float = 2.0,
        volts: Optional[float] = None,
        amps: Optional[float] = None,
    ) -> None:
        """Power-cycle the ECU: turn off, wait, turn on, wait to settle.

        Parameters
        ----------
        off_duration_s:
            Seconds to keep the output OFF before turning it back on.
        on_settle_s:
            Seconds to wait after turning the output back on, allowing the
            ECU to boot and the T32 USB enumeration to stabilise.
        volts:
            If provided, re-apply this voltage setpoint before turning the
            output back on (e.g. after a fault that changed the setpoint).
        amps:
            If provided, re-apply this current limit before turning back on.
        """
        logger.info(
            "Power cycling ECU: off %.1f s, on settle %.1f s.",
            off_duration_s, on_settle_s,
        )
        self.output_off()
        time.sleep(off_duration_s)

        if volts is not None:
            self.set_voltage(volts)
        if amps is not None:
            self.set_current(amps)

        self.output_on()
        logger.info("PSU output re-enabled; waiting %.1f s for ECU to settle.", on_settle_s)
        time.sleep(on_settle_s)

    def safe_startup(
        self,
        volts: float,
        amps: float,
        ramp_steps: int = 10,
        ramp_step_delay_s: float = 0.05,
        settle_s: float = 1.0,
    ) -> None:
        """Ramp the voltage up gradually then enable the output.

        Useful for ECUs that are sensitive to inrush current or voltage
        transients.  The voltage is programmed in *ramp_steps* equal steps
        from 0 V to *volts* before the output is enabled.

        Parameters
        ----------
        volts:
            Final output voltage.
        amps:
            Current limit (applied before ramping).
        ramp_steps:
            Number of intermediate voltage steps.
        ramp_step_delay_s:
            Delay between each ramp step in seconds.
        settle_s:
            Final delay after enabling the output.
        """
        logger.info(
            "PSU safe startup: %.2f V / %.3f A  (%d steps).",
            volts, amps, ramp_steps,
        )
        self.set_current(amps)
        self.set_voltage(0.0)
        self.output_on()

        step_v = volts / ramp_steps
        for step in range(1, ramp_steps + 1):
            self.set_voltage(step_v * step)
            time.sleep(ramp_step_delay_s)

        logger.info("Voltage ramp complete; settling for %.1f s.", settle_s)
        time.sleep(settle_s)

    # ------------------------------------------------------------------
    # Internal serial helpers
    # ------------------------------------------------------------------

    def _start_session(self) -> None:
        """Enter remote-control mode (SESS)."""
        logger.debug("PSU: entering remote control mode (SESS).")
        self._cmd("SESS")

    def _end_session(self) -> None:
        """Return to local control mode (ENDS)."""
        logger.debug("PSU: returning to local mode (ENDS).")
        self._cmd("ENDS")

    def _cmd(self, command: str) -> None:
        """Send *command* and assert that the supply acknowledges with ``OK``.

        Parameters
        ----------
        command:
            ASCII command string (without the trailing ``\\r``).

        Raises
        ------
        PowerSupplyError
            On communication error or a non-OK response.
        """
        if self._mock:
            logger.debug("[MOCK] PSU cmd: %s → OK", command)
            return

        self._require_connected()
        raw = self._exchange(command)
        resp = raw.strip().upper()
        if resp not in ("OK", ""):
            raise PowerSupplyError(
                f"PSU rejected command {command!r} – response: {raw!r}"
            )

    def _query(self, command: str) -> str:
        """Send *command* and return the raw response string.

        Parameters
        ----------
        command:
            ASCII query command (without ``\\r``).

        Returns
        -------
        str
            Raw response from the supply (``\\r``-terminated).
        """
        self._require_connected()
        return self._exchange(command)

    def _exchange(self, command: str) -> str:
        """Write *command*``\\r`` and read back the response line.

        Parameters
        ----------
        command:
            ASCII command (without terminator).

        Returns
        -------
        str
            Decoded response (may include trailing ``\\r``).

        Raises
        ------
        PowerSupplyError
            On write/read I/O errors.
        """
        ser = self._ser
        try:
            payload = (command + "\r").encode("ascii")
            ser.write(payload)  # type: ignore[union-attr]
            ser.flush()         # type: ignore[union-attr]
            logger.debug("PSU → %r", payload)

            # Read until carriage-return or timeout.
            response_bytes = ser.read_until(b"\r")  # type: ignore[union-attr]
            response = response_bytes.decode("ascii", errors="replace")
            logger.debug("PSU ← %r", response)
            return response
        except PowerSupplyError:
            raise
        except Exception as exc:
            raise PowerSupplyError(
                f"Serial I/O error on port {self._port!r}: {exc}"
            ) from exc

    def _require_connected(self) -> None:
        if self._ser is None:
            raise PowerSupplyError(
                "Power supply not connected.  "
                "Call connect() or use as a context manager."
            )
