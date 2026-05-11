"""
GM VIP Automation Framework – Vector CANoe Integration
=======================================================
Python interface for controlling a running **Vector CANoe** instance via its
COM (Windows Automation / win32com) API.  CANoe must already be open with the
correct configuration loaded before calling any method in this module.

This module provides two integration paths:

1. **COM automation** (primary, Windows only)
   Uses ``win32com.client`` to connect to a running CANoe instance.  Supports
   starting/stopping measurement, sending CAN messages through CAPL environment
   variables, reading/writing environment variables, and invoking CAPL test
   functions.

2. **python-can** (fallback / parallel)
   When CANoe is running but you need to inject raw CAN frames *alongside* the
   CANoe simulation, use :class:`~can_bus.CANBusClient` (see ``can_bus.py``).
   Both can be used simultaneously on different bus channels.

Graceful degradation
--------------------
If ``pywin32`` is not installed (e.g. on Linux CI) the module still imports
cleanly; every COM operation raises :class:`CANoeError` with a clear message.
Install with::

    pip install pywin32

Typical usage
-------------
::

    from GM_VIP_Automation_Framework.core.canoe import CANoeClient

    with CANoeClient() as canoe:
        canoe.start_measurement()

        # Trigger CAN init by setting a CAPL environment variable
        canoe.set_env_var("TriggerCanInit", 1)

        # Or send a raw CAN message (requires CANoe to have a GeneratorBlock
        # or a CAPL node that forwards env-var signals to the bus)
        canoe.send_can_message(channel=1, can_id=0x401, data=[0]*8)

        # Read back a signal value from the running measurement
        val = canoe.get_env_var("CanStatus")
        print("CanStatus =", val)

        canoe.stop_measurement()

CAN stimulus for T32 breakpoint tests
--------------------------------------
The helper methods :meth:`trigger_can_init`, :meth:`trigger_can_rx`, and
:meth:`trigger_can_tx_confirm` send the precise CAN stimuli required to drive
the ECU through its CAN initialisation path and hit the T32 breakpoints set
in :class:`~tests.test_sanity.TestSanityGroup1CAN`::

    # In a live test after set_breakpoint("TestCan_Init") and go():
    canoe.trigger_can_init(channel=1, can_id=0x401)
    _bp.check_halted_at("TestCan_Init", connection=conn)
"""

from __future__ import annotations

import time
from typing import Any, List, Optional

from ..utils.logger import get_logger

logger = get_logger("canoe")

__all__ = ["CANoeClient", "CANoeError"]


# ---------------------------------------------------------------------------
# Optional win32com import
# ---------------------------------------------------------------------------

try:
    import win32com.client as _win32  # type: ignore[import]
    _WIN32_AVAILABLE = True
except ImportError:
    _win32 = None  # type: ignore[assignment]
    _WIN32_AVAILABLE = False


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class CANoeError(Exception):
    """Raised when a CANoe operation fails or win32com is not available."""


# ---------------------------------------------------------------------------
# CANoeClient
# ---------------------------------------------------------------------------

class CANoeClient:
    """Context-manager client for a running Vector CANoe instance.

    Parameters
    ----------
    app_version:
        CANoe ProgID suffix (e.g. ``""`` for the default installation,
        ``".10"`` for CANoe 10).  Leave as ``""`` to use whichever version is
        registered as the default COM server.
    startup_delay_s:
        Seconds to wait after starting a measurement before returning to the
        caller (allows CANoe to initialise its network nodes).
    stop_delay_s:
        Seconds to wait after stopping a measurement.
    mock:
        When ``True``, all COM operations are skipped and logged instead.
        Use this for unit tests and CI environments where CANoe is absent.
    """

    _CANOE_PROGID = "CANoe.Application"

    def __init__(
        self,
        app_version: str = "",
        startup_delay_s: float = 2.0,
        stop_delay_s: float = 0.5,
        mock: bool = False,
    ) -> None:
        self._app_version    = app_version
        self._startup_delay  = startup_delay_s
        self._stop_delay     = stop_delay_s
        self._mock           = mock
        self._app: Optional[Any] = None          # CANoe.Application COM object
        self._measurement: Optional[Any] = None  # CANoe.Measurement COM object
        self._env: Optional[Any] = None          # CANoe.Environment COM object

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "CANoeClient":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        try:
            if self.is_measuring:
                self.stop_measurement()
        except Exception:  # noqa: BLE001
            pass
        self.disconnect()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Attach to a running CANoe instance via COM.

        CANoe **must already be open** with your configuration loaded before
        calling this method.  The framework never launches CANoe itself – use
        the normal CANoe startup procedure (double-click the ``.cfg`` file, or
        run the ``*.cmm`` initialisation script from T32 which may open CANoe
        via a SYStem call).

        Raises
        ------
        CANoeError
            When ``pywin32`` is not installed, or CANoe is not running.
        """
        if self._mock:
            logger.info("[MOCK] CANoeClient.connect() – no COM object created.")
            return

        if not _WIN32_AVAILABLE:
            raise CANoeError(
                "pywin32 is not installed (Windows only).  "
                "Run:  pip install pywin32  then retry."
            )

        progid = self._CANOE_PROGID + self._app_version
        logger.info("Attaching to CANoe via COM ProgID '%s'.", progid)
        try:
            self._app = _win32.Dispatch(progid)
            self._measurement = self._app.Measurement
            self._env = self._app.Environment
        except Exception as exc:
            raise CANoeError(
                f"Could not connect to CANoe ({progid}): {exc}.  "
                "Ensure CANoe is open and the COM server is registered."
            ) from exc
        logger.info("CANoe connected.  Version: %s.", self._safe_version())

    def disconnect(self) -> None:
        """Release the COM references (does not close CANoe)."""
        self._app = None
        self._measurement = None
        self._env = None
        logger.info("CANoe COM references released.")

    @property
    def is_connected(self) -> bool:
        """``True`` when attached to a CANoe instance (or in mock mode)."""
        return self._mock or self._app is not None

    @property
    def is_measuring(self) -> bool:
        """``True`` when CANoe's measurement is currently running."""
        if self._mock:
            return False
        if self._measurement is None:
            return False
        try:
            return bool(self._measurement.Running)
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------
    # Measurement control
    # ------------------------------------------------------------------

    def start_measurement(self) -> None:
        """Start the CANoe measurement.

        Waits :attr:`startup_delay_s` seconds after issuing the start command
        to allow CANoe's CAPL nodes to initialise and begin transmitting.

        Raises
        ------
        CANoeError
            If the measurement cannot be started.
        """
        if self._mock:
            logger.info("[MOCK] CANoe measurement started.")
            return

        self._require_connected()
        if self.is_measuring:
            logger.info("CANoe measurement is already running.")
            return
        logger.info("Starting CANoe measurement.")
        try:
            self._measurement.Start()
        except Exception as exc:
            raise CANoeError(f"CANoe measurement start failed: {exc}") from exc
        time.sleep(self._startup_delay)
        logger.info("CANoe measurement running.")

    def stop_measurement(self) -> None:
        """Stop the CANoe measurement.

        Raises
        ------
        CANoeError
            If the stop command fails.
        """
        if self._mock:
            logger.info("[MOCK] CANoe measurement stopped.")
            return

        self._require_connected()
        if not self.is_measuring:
            logger.info("CANoe measurement is already stopped.")
            return
        logger.info("Stopping CANoe measurement.")
        try:
            self._measurement.Stop()
        except Exception as exc:
            raise CANoeError(f"CANoe measurement stop failed: {exc}") from exc
        time.sleep(self._stop_delay)

    # ------------------------------------------------------------------
    # Environment variables
    # ------------------------------------------------------------------

    def set_env_var(self, name: str, value: Any) -> None:
        """Write a CANoe environment variable.

        Environment variables are the primary signal channel between external
        Python code and running CAPL nodes.  A CAPL ``on envVar`` handler in
        your CANoe configuration reacts to the value change and sends the
        appropriate CAN message on the bus.

        Parameters
        ----------
        name:
            Environment variable name as defined in the CANoe ``*.dbc`` /
            ``*.arxml`` / Symbol Editor.
        value:
            New value.  Numeric or string types are accepted.

        Raises
        ------
        CANoeError
            If the variable cannot be written.
        """
        if self._mock:
            logger.debug("[MOCK] CANoe env var '%s' ← %r.", name, value)
            return

        self._require_connected()
        try:
            var = self._env.GetVariable(name)
            var.Value = value
            logger.debug("CANoe env var '%s' ← %r.", name, value)
        except Exception as exc:
            raise CANoeError(
                f"Could not set CANoe environment variable '{name}': {exc}"
            ) from exc

    def get_env_var(self, name: str) -> Any:
        """Read a CANoe environment variable.

        Parameters
        ----------
        name:
            Environment variable name.

        Returns
        -------
        Any
            Current value.

        Raises
        ------
        CANoeError
            If the variable cannot be read.
        """
        if self._mock:
            logger.debug("[MOCK] CANoe get env var '%s' → 0.", name)
            return 0

        self._require_connected()
        try:
            var = self._env.GetVariable(name)
            value = var.Value
            logger.debug("CANoe env var '%s' → %r.", name, value)
            return value
        except Exception as exc:
            raise CANoeError(
                f"Could not read CANoe environment variable '{name}': {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Direct CAN message transmission
    # ------------------------------------------------------------------

    def send_can_message(
        self,
        channel: int,
        can_id: int,
        data: List[int],
        is_extended_id: bool = False,
    ) -> None:
        """Transmit a CAN message through CANoe's GeneratorBlock.

        Requires a **GeneratorBlock** or **Interactive Generator** configured
        in the CANoe network node to be available on *channel*.  The message
        is sent as a one-shot frame; for periodic transmissions use
        :meth:`set_env_var` to trigger a CAPL ``on envVar`` cyclic sender.

        .. note::
            This method uses the CANoe ``BusStatistics`` / ``Scheduler`` COM
            interface which is only available when a GeneratorBlock exists in
            the configuration.  If your setup differs, use
            :class:`~can_bus.CANBusClient` with a hardware CAN adapter
            instead.

        Parameters
        ----------
        channel:
            1-based CAN channel index in the CANoe configuration.
        can_id:
            CAN arbitration ID (11-bit standard or 29-bit extended).
        data:
            Payload bytes (list of ints, 0–8 bytes for Classic CAN).
        is_extended_id:
            ``True`` for 29-bit extended frame format.

        Raises
        ------
        CANoeError
            If the message cannot be sent.
        """
        if self._mock:
            logger.debug(
                "[MOCK] CANoe TX  ch=%d  0x%03X  [%s].",
                channel, can_id,
                " ".join(f"{b:02X}" for b in data),
            )
            return

        self._require_connected()
        try:
            # CANoe COM: app.Networks.Item(channel).Scheduler.Objects
            # This approach uses the Scheduler COM interface which is only
            # available when a network channel exists in the CANoe
            # configuration.  The Scheduler dynamically creates a one-shot
            # message object rather than requiring a pre-existing
            # GeneratorBlock node – the CANoe configuration does NOT need a
            # GeneratorBlock for this to work.  If your setup uses a CAPL
            # node to forward messages instead, call set_env_var() to trigger
            # the CAPL sender rather than using this method directly.
            networks = self._app.Networks
            net = networks.Item(channel)
            scheduler = net.Scheduler
            # Create a transient one-shot frame definition.
            msg_def = scheduler.Objects.AddMessage()
            msg_def.ID = can_id
            msg_def.DLC = len(data)
            for i, byte_val in enumerate(data):
                msg_def.SetByteValue(i, byte_val)
            msg_def.IsExtendedId = is_extended_id
            msg_def.SendCount = 1
            scheduler.Start()
            logger.debug(
                "CANoe TX  ch=%d  0x%03X  [%s].",
                channel, can_id, " ".join(f"{b:02X}" for b in data),
            )
        except Exception as exc:
            raise CANoeError(
                f"CANoe send_can_message failed (ch={channel}, id=0x{can_id:03X}): {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # CAPL function invocation
    # ------------------------------------------------------------------

    def call_capl_function(self, function_name: str, *args: Any) -> Any:
        """Call a CAPL function exposed via the CANoe COM interface.

        CAPL functions can be made callable from Python by adding a
        ``export`` declaration in the CAPL node::

            export testfunction TriggerCanInit(int channel)

        Parameters
        ----------
        function_name:
            Name of the exported CAPL function.
        *args:
            Positional arguments forwarded to the CAPL function.

        Returns
        -------
        Any
            Return value of the CAPL function, or ``None``.

        Raises
        ------
        CANoeError
            If the function call fails.
        """
        if self._mock:
            logger.debug("[MOCK] CAPL %s(%s).", function_name, args)
            return None

        self._require_connected()
        try:
            capl = self._app.CAPL
            func = capl.GetFunction(function_name)
            result = func.Call(*args)
            logger.debug("CAPL %s(%s) → %r.", function_name, args, result)
            return result
        except Exception as exc:
            raise CANoeError(
                f"CAPL function call '{function_name}' failed: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # T32 test-case stimulus helpers
    # ------------------------------------------------------------------

    def trigger_can_init(
        self,
        channel: int = 1,
        can_id: int = 0x401,
        data: Optional[List[int]] = None,
        env_var: Optional[str] = None,
        delay_after_s: float = 0.05,
    ) -> None:
        """Send the CAN stimulus that drives the ECU into its init routine.

        This is the trigger needed so that the ECU reaches ``TestCan_Init``
        (and subsequently ``MngCNDD_CanRxInit``, ``SetCNDD_e_CanControllerMode``)
        where T32 breakpoints are set in
        :class:`~tests.test_sanity.TestSanityGroup1CAN`.

        Two delivery modes are supported:

        * **env_var mode** (preferred): write *env_var* to ``1``; a CAPL
          ``on envVar`` handler in your CANoe configuration sends the frame.
        * **direct mode** (fallback): call :meth:`send_can_message` directly.

        Parameters
        ----------
        channel:
            CAN channel index (1-based, direct mode only).
        can_id:
            Standard CAN ID of the init-trigger frame.  Default: ``0x401``
            (CANA CAN2 in TC 1.1).
        data:
            8-byte payload (defaults to ``[0x00]*8``).
        env_var:
            CANoe environment variable name to set (env_var mode).  When
            *None*, falls back to :meth:`send_can_message`.
        delay_after_s:
            Short delay after sending to let the CAN frame propagate before
            T32 resumes polling.
        """
        if data is None:
            data = [0x00] * 8
        logger.info(
            "CAN init stimulus: ch=%d  id=0x%03X  env_var=%s.",
            channel, can_id, env_var,
        )
        if env_var:
            self.set_env_var(env_var, 1)
        else:
            self.send_can_message(channel=channel, can_id=can_id, data=data)
        time.sleep(delay_after_s)

    def trigger_can_rx(
        self,
        channel: int = 1,
        can_id: int = 0x401,
        data: Optional[List[int]] = None,
        is_extended_id: bool = False,
        env_var: Optional[str] = None,
        delay_after_s: float = 0.05,
    ) -> None:
        """Send a CAN frame to simulate an ECU Rx indication event.

        Parameters
        ----------
        channel:
            CAN channel (1-based).
        can_id:
            CAN arbitration ID.
        data:
            Payload bytes (defaults to ``[0x00]*8``).
        is_extended_id:
            ``True`` for 29-bit extended IDs.
        env_var:
            Optional CANoe environment variable to set instead of sending
            a raw frame.
        delay_after_s:
            Post-send delay.
        """
        if data is None:
            data = [0x00] * 8
        logger.info("CAN Rx stimulus: ch=%d  id=0x%08X.", channel, can_id)
        if env_var:
            self.set_env_var(env_var, 1)
        else:
            self.send_can_message(
                channel=channel,
                can_id=can_id,
                data=data,
                is_extended_id=is_extended_id,
            )
        time.sleep(delay_after_s)

    def trigger_can_tx_confirm(
        self,
        channel: int = 1,
        can_id: int = 0x18FF4001,
        env_var: Optional[str] = None,
    ) -> None:
        """Trigger a Tx confirmation event on the ECU (``SetCANR_h_CanIfRxIndication``).

        Parameters
        ----------
        channel:
            CAN channel (1-based).
        can_id:
            CAN ID of the Tx confirmation message.
        env_var:
            Optional CANoe environment variable to signal the event.
        """
        logger.info("CAN Tx confirm stimulus: ch=%d  id=0x%08X.", channel, can_id)
        if env_var:
            self.set_env_var(env_var, 1)
        else:
            self.send_can_message(
                channel=channel,
                can_id=can_id,
                data=[0x00] * 8,
                is_extended_id=True,
            )

    def trigger_bus_stop(
        self,
        env_var: str = "BusStop",
        resume_delay_s: float = 0.1,
    ) -> None:
        """Signal the CANoe CAPL node to momentarily stop CAN bus transmission.

        This is used to validate ``SetCNDD_e_CanControllerMode`` Bus-Off and
        Bus-Stop handling.  The CAPL node must have an ``on envVar BusStop``
        handler that calls ``resetCan()`` or equivalent.

        Parameters
        ----------
        env_var:
            Environment variable name that the CAPL bus-stop handler watches.
        resume_delay_s:
            Delay before signalling resume (setting the var back to 0).
        """
        logger.info("CAN bus stop stimulus: env_var='%s'.", env_var)
        self.set_env_var(env_var, 1)
        time.sleep(resume_delay_s)
        self.set_env_var(env_var, 0)

    def trigger_wakeup_frame(
        self,
        channel: int = 1,
        can_id: int = 0x100,
        data: Optional[List[int]] = None,
        delay_after_s: float = 0.1,
    ) -> None:
        """Send a wakeup CAN frame for the Wakeup test group (Group 3).

        Parameters
        ----------
        channel:
            CAN channel (1-based).
        can_id:
            Wakeup frame CAN ID.
        data:
            Payload (defaults to ``[0xFF]*8``).
        delay_after_s:
            Post-send delay.
        """
        if data is None:
            data = [0xFF] * 8
        logger.info(
            "Wakeup frame stimulus: ch=%d  id=0x%03X.", channel, can_id,
        )
        self.send_can_message(channel=channel, can_id=can_id, data=data)
        time.sleep(delay_after_s)

    # ------------------------------------------------------------------
    # Diagnostics / status
    # ------------------------------------------------------------------

    def get_measurement_state(self) -> str:
        """Return a human-readable measurement state string.

        Returns
        -------
        str
            ``"RUNNING"``, ``"STOPPED"``, or ``"UNKNOWN"``.
        """
        if self._mock:
            return "MOCK"
        try:
            return "RUNNING" if self._measurement.Running else "STOPPED"
        except Exception:  # noqa: BLE001
            return "UNKNOWN"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_connected(self) -> None:
        if self._app is None:
            raise CANoeError(
                "Not connected to CANoe.  Call connect() or use as a context manager."
            )

    def _safe_version(self) -> str:
        try:
            v = self._app.Version
            return f"{v.major}.{v.minor}.{v.build} SP{v.servicePack}"
        except Exception:  # noqa: BLE001
            return "unknown"
