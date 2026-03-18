"""
GM VIP Automation Framework – Direct CAN Bus Interface
=======================================================
Thin wrapper around the ``python-can`` library for sending and receiving CAN
frames directly on a physical bus (e.g. via a Vector VN-series or PEAK PCAN
adapter).  This module complements :mod:`canoe` – use **this** module when you
want to inject raw CAN frames from Python without going through Vector CANoe,
or when you need a second bus observer while CANoe is running.

Graceful degradation
--------------------
If ``python-can`` is not installed the module still imports successfully; all
operations raise :class:`CANBusError` with an explanatory message instead of
crashing with an ``ImportError``.  This allows the test framework to import the
module in CI environments (where the CAN hardware is absent) without changes.

Install the optional dependency with::

    pip install python-can

Typical usage
-------------
::

    from GM_VIP_Automation_Framework.core.can_bus import CANBusClient

    # Vector VN1610 adapter, channel 0, 500 kbit/s
    with CANBusClient(interface="vector", channel=0, bitrate=500_000) as bus:
        # Send a single frame
        bus.send(arbitration_id=0x401, data=[0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

        # Receive up to 5 frames with a 1 s timeout
        for frame in bus.receive_many(count=5, timeout_s=1.0):
            print(f"  RX  0x{frame['id']:03X}  {frame['data'].hex()}")

        # Send the same frame every 10 ms for 2 seconds
        bus.send_periodic(
            arbitration_id=0x18FF4001,
            data=[0xAA] * 8,
            period_s=0.01,
            duration_s=2.0,
            is_extended_id=True,
        )

CAN stimulus patterns for T32 breakpoint tests
-----------------------------------------------
Several helper methods encode the exact CAN sequences required to trigger the
CAN init / Rx / Tx breakpoints in the ECU firmware::

    bus.trigger_can_init()                         # CAN init handshake
    bus.trigger_can_rx(can_id=0x401, data=[...])   # CAN Rx indication
    bus.trigger_can_tx_confirm(can_id=0x18FF4001)  # Tx confirmation

These are intentionally *simple* and send only the minimal frames described in
the Sanity report; adapt them to match your actual ECU's CAN matrix as needed.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Generator, List, Optional

from ..utils.logger import get_logger

logger = get_logger("can_bus")

__all__ = ["CANBusClient", "CANBusError", "CANFrame"]


# ---------------------------------------------------------------------------
# Optional python-can import
# ---------------------------------------------------------------------------

try:
    import can as _can  # type: ignore[import]
    _CAN_AVAILABLE = True
except ImportError:
    _can = None  # type: ignore[assignment]
    _CAN_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public exceptions / types
# ---------------------------------------------------------------------------

class CANBusError(Exception):
    """Raised when a CAN bus operation fails or python-can is not installed."""


# A CAN frame represented as a plain dict so callers never depend on can.Message.
CANFrame = Dict[str, Any]


def _frame(msg: Any) -> CANFrame:
    """Convert a ``can.Message`` to a :data:`CANFrame` dict."""
    return {
        "id":             msg.arbitration_id,
        "data":           bytes(msg.data),
        "dlc":            msg.dlc,
        "is_extended_id": msg.is_extended_id,
        "timestamp":      msg.timestamp,
        "is_error_frame": msg.is_error_frame,
        "is_remote_frame": msg.is_remote_frame,
    }


# ---------------------------------------------------------------------------
# CANBusClient
# ---------------------------------------------------------------------------

class CANBusClient:
    """Context-manager wrapper around a ``python-can`` bus.

    Parameters
    ----------
    interface:
        python-can interface plugin name (e.g. ``"vector"``, ``"pcan"``,
        ``"socketcan"``, ``"kvaser"``, ``"usb2can"``).
    channel:
        Channel identifier (meaning depends on *interface*).  For Vector
        hardware this is the channel index (0-based); for SocketCAN this is
        the interface name (e.g. ``"can0"``).
    bitrate:
        CAN bus bitrate in bits per second.  Common values: 125000, 250000,
        500000, 1000000.
    app_name:
        Application name registered in CANdb++ / Vector Hardware Config
        (Vector interface only).  Defaults to ``"GM_VIP_Framework"``.
    fd:
        When ``True``, open as a CAN FD bus.  *data_bitrate* must also be
        set.
    data_bitrate:
        CAN FD data-phase bitrate.  Ignored when *fd* is ``False``.
    rx_queue_size:
        Receive queue depth (frames).  ``None`` uses the python-can default.
    mock:
        When ``True``, skip hardware initialisation and operate in a no-op
        simulation mode.  Useful for unit tests and CI.
    """

    def __init__(
        self,
        interface: str = "vector",
        channel: int = 0,
        bitrate: int = 500_000,
        app_name: str = "GM_VIP_Framework",
        fd: bool = False,
        data_bitrate: int = 2_000_000,
        rx_queue_size: Optional[int] = None,
        mock: bool = False,
    ) -> None:
        self._interface    = interface
        self._channel      = channel
        self._bitrate      = bitrate
        self._app_name     = app_name
        self._fd           = fd
        self._data_bitrate = data_bitrate
        self._rx_queue_sz  = rx_queue_size
        self._mock         = mock
        self._bus: Optional[Any] = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "CANBusClient":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the CAN bus interface.

        Raises
        ------
        CANBusError
            When python-can is not installed, or when the hardware cannot be
            opened (e.g. driver not installed, channel busy).
        """
        if self._mock:
            logger.info("[MOCK] CANBusClient.connect() – no hardware opened.")
            return

        if not _CAN_AVAILABLE:
            raise CANBusError(
                "python-can is not installed.  "
                "Run:  pip install python-can  then retry."
            )

        kwargs: Dict[str, Any] = {
            "interface": self._interface,
            "channel":   self._channel,
            "bitrate":   self._bitrate,
        }
        if self._interface == "vector":
            kwargs["app_name"] = self._app_name
        if self._fd:
            kwargs["fd"]           = True
            kwargs["data_bitrate"] = self._data_bitrate
        if self._rx_queue_sz is not None:
            kwargs["rx_queue_size"] = self._rx_queue_sz

        logger.info(
            "Opening CAN bus: interface=%s channel=%s bitrate=%d bps.",
            self._interface, self._channel, self._bitrate,
        )
        try:
            self._bus = _can.Bus(**kwargs)
        except Exception as exc:
            raise CANBusError(
                f"Could not open CAN bus ({self._interface}/{self._channel}): {exc}"
            ) from exc

    def disconnect(self) -> None:
        """Close the CAN bus interface."""
        if self._bus is not None:
            try:
                self._bus.shutdown()
            except Exception as exc:  # noqa: BLE001
                logger.warning("CAN bus shutdown raised: %s", exc)
            finally:
                self._bus = None
        logger.info("CAN bus disconnected.")

    @property
    def is_connected(self) -> bool:
        """``True`` when the bus is open (or in mock mode)."""
        return self._mock or self._bus is not None

    # ------------------------------------------------------------------
    # Transmit
    # ------------------------------------------------------------------

    def send(
        self,
        arbitration_id: int,
        data: List[int],
        is_extended_id: bool = False,
        timeout_s: float = 1.0,
    ) -> None:
        """Transmit a single CAN frame.

        Parameters
        ----------
        arbitration_id:
            11-bit (standard) or 29-bit (extended) CAN ID.
        data:
            Payload bytes (list of ints, 0–8 bytes for classic CAN).
        is_extended_id:
            ``True`` for 29-bit extended frame format.
        timeout_s:
            Transmit timeout in seconds.
        """
        if self._mock:
            logger.debug(
                "[MOCK] TX  0x%03X  [%s]",
                arbitration_id, " ".join(f"{b:02X}" for b in data),
            )
            return

        self._require_connected()
        msg = _can.Message(
            arbitration_id=arbitration_id,
            data=data,
            is_extended_id=is_extended_id,
        )
        logger.debug(
            "TX  0x%03X  [%s]",
            arbitration_id, " ".join(f"{b:02X}" for b in data),
        )
        try:
            self._bus.send(msg, timeout=timeout_s)
        except Exception as exc:
            raise CANBusError(f"CAN send failed (id=0x{arbitration_id:03X}): {exc}") from exc

    def send_periodic(
        self,
        arbitration_id: int,
        data: List[int],
        period_s: float,
        duration_s: float,
        is_extended_id: bool = False,
    ) -> None:
        """Send a CAN frame periodically for *duration_s* seconds.

        Parameters
        ----------
        arbitration_id:
            CAN ID.
        data:
            Payload bytes.
        period_s:
            Interval between frames in seconds (e.g. ``0.01`` for 10 ms).
        duration_s:
            Total transmission time in seconds.
        is_extended_id:
            ``True`` for 29-bit extended frame.
        """
        if self._mock:
            logger.debug(
                "[MOCK] TX periodic 0x%03X every %.3f s for %.1f s.",
                arbitration_id, period_s, duration_s,
            )
            return

        self._require_connected()
        msg = _can.Message(
            arbitration_id=arbitration_id,
            data=data,
            is_extended_id=is_extended_id,
        )
        logger.info(
            "Periodic TX  0x%03X  period=%.3f s  duration=%.1f s.",
            arbitration_id, period_s, duration_s,
        )
        task = self._bus.send_periodic(msg, period_s)
        try:
            time.sleep(duration_s)
        finally:
            task.stop()

    # ------------------------------------------------------------------
    # Receive
    # ------------------------------------------------------------------

    def receive(self, timeout_s: float = 2.0) -> Optional[CANFrame]:
        """Wait for a single CAN frame.

        Parameters
        ----------
        timeout_s:
            Maximum wait time.

        Returns
        -------
        CANFrame or None
            ``None`` when the timeout expires without a frame.
        """
        if self._mock:
            logger.debug("[MOCK] RX – returning None (no hardware).")
            return None

        self._require_connected()
        msg = self._bus.recv(timeout=timeout_s)
        if msg is None:
            return None
        fr = _frame(msg)
        logger.debug("RX  0x%03X  [%s]", fr["id"], fr["data"].hex())
        return fr

    def receive_many(
        self,
        count: int = 10,
        timeout_s: float = 2.0,
    ) -> Generator[CANFrame, None, None]:
        """Yield up to *count* CAN frames received within *timeout_s* seconds.

        Parameters
        ----------
        count:
            Maximum number of frames to collect.
        timeout_s:
            Per-frame receive timeout.
        """
        collected = 0
        while collected < count:
            frame = self.receive(timeout_s=timeout_s)
            if frame is None:
                break
            yield frame
            collected += 1

    def flush_rx(self) -> int:
        """Discard all pending frames in the receive queue.

        Returns
        -------
        int
            Number of frames discarded.
        """
        count = 0
        while self.receive(timeout_s=0.0) is not None:
            count += 1
        logger.debug("Flushed %d queued RX frames.", count)
        return count

    # ------------------------------------------------------------------
    # ECU / test-case stimulus helpers
    # ------------------------------------------------------------------

    def trigger_can_init(
        self,
        can_id: int = 0x401,
        data: Optional[List[int]] = None,
        repeat: int = 1,
        interval_s: float = 0.01,
    ) -> None:
        """Send the CAN frame(s) that trigger the ECU's CAN initialisation path.

        This is the minimal stimulus needed to drive the ECU through
        ``TestCan_Init`` → ``MngCNDD_CanRxInit`` → ``SetCNDD_e_CanControllerMode``
        so that Trace32 breakpoints in those functions are hit.

        Parameters
        ----------
        can_id:
            Standard (11-bit) CAN ID of the init-trigger frame.  Defaults to
            ``0x401`` (CANA CAN2 as used in TC 1.1).
        data:
            8-byte payload.  Defaults to ``[0x00]*8``.
        repeat:
            Number of times to send the frame (some ECUs need several frames).
        interval_s:
            Delay between repeated frames.
        """
        if data is None:
            data = [0x00] * 8
        logger.info(
            "CAN init stimulus: id=0x%03X  data=[%s]  repeat=%d.",
            can_id, " ".join(f"{b:02X}" for b in data), repeat,
        )
        for i in range(repeat):
            self.send(arbitration_id=can_id, data=data)
            if i < repeat - 1:
                time.sleep(interval_s)

    def trigger_can_rx(
        self,
        can_id: int,
        data: Optional[List[int]] = None,
        is_extended_id: bool = False,
    ) -> None:
        """Send a CAN frame to simulate an ECU Rx indication.

        Parameters
        ----------
        can_id:
            CAN ID of the Rx message.
        data:
            Payload bytes (defaults to ``[0x00]*8``).
        is_extended_id:
            ``True`` for extended 29-bit IDs (e.g. ``0x18FF4001``).
        """
        if data is None:
            data = [0x00] * 8
        logger.info("CAN Rx stimulus: id=0x%08X  ext=%s.", can_id, is_extended_id)
        self.send(arbitration_id=can_id, data=data, is_extended_id=is_extended_id)

    def trigger_can_tx_confirm(
        self,
        can_id: int,
        is_extended_id: bool = False,
    ) -> None:
        """Send a remote-frame (RTR) to trigger a Tx confirmation on the ECU.

        Parameters
        ----------
        can_id:
            CAN ID to request.
        is_extended_id:
            ``True`` for 29-bit IDs.
        """
        if self._mock:
            logger.debug("[MOCK] TX RTR 0x%08X.", can_id)
            return
        self._require_connected()
        msg = _can.Message(
            arbitration_id=can_id,
            is_remote_frame=True,
            is_extended_id=is_extended_id,
            dlc=8,
        )
        logger.info("CAN TX confirm RTR: id=0x%08X.", can_id)
        try:
            self._bus.send(msg, timeout=1.0)
        except Exception as exc:
            raise CANBusError(
                f"CAN TX confirm RTR failed (id=0x{can_id:08X}): {exc}"
            ) from exc

    def trigger_bus_off_recovery(
        self,
        error_frame_count: int = 11,
        interval_s: float = 0.001,
    ) -> None:
        """Simulate a Bus-Off condition by flooding the bus with dominant bits.

        Sends a sequence of frames with the maximum DLC to generate error
        frames; the ECU's CAN controller should detect this and enter
        Bus-Off recovery.  Used to validate ``SetCNDD_e_CanControllerMode``
        Bus-Off handling.

        Parameters
        ----------
        error_frame_count:
            Number of error-inducing frames to send.
        interval_s:
            Interval between frames.
        """
        logger.warning(
            "Triggering Bus-Off recovery stimulus (%d frames).", error_frame_count,
        )
        for _ in range(error_frame_count):
            # Send with an ID that will conflict on a real bus.
            self.send(arbitration_id=0x000, data=[0xFF] * 8)
            time.sleep(interval_s)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_connected(self) -> None:
        if self._bus is None:
            raise CANBusError(
                "CAN bus not connected.  Call connect() or use as a context manager."
            )
