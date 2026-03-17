"""
GM VIP Automation Framework – Trace32 Connection Manager
=========================================================
Handles launching the Trace32 process, establishing the Remote Control Link
(RCL) connection via ``lauterbach.trace32.rcl``, auto-detecting the T32
installation, and graceful disconnection.

Key public API
--------------
- :class:`T32Connection` – context-manager and connection lifecycle object.
- :func:`connect` – convenience factory that returns a connected
  :class:`T32Connection` instance.
- :func:`auto_detect_t32` – scan standard installation directories for a
  Trace32 executable + ``config.t32``.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

from ..config import settings
from ..utils.exceptions import (
    T32AutoDetectError,
    T32ConnectionError,
    T32LaunchError,
    T32TimeoutError,
)
from ..utils.logger import get_logger
from ..utils.retry import poll_until

logger = get_logger("connection")

# Regex to extract PORT= value from a t32.ini / config.t32 file.
_PORT_RE = re.compile(r"^\s*PORT\s*=\s*(\d+)", re.MULTILINE | re.IGNORECASE)


# ---------------------------------------------------------------------------
# Auto-detection helpers
# ---------------------------------------------------------------------------

def auto_detect_t32(
    search_dirs: Optional[list] = None,
    exe_names: Optional[list] = None,
) -> Tuple[str, str]:
    """Scan *search_dirs* for a Trace32 executable and matching ``config.t32``.

    Parameters
    ----------
    search_dirs:
        Ordered list of directories to probe.  Defaults to
        :attr:`~GM_VIP_Automation_Framework.config.T32Settings.t32_search_dirs`.
    exe_names:
        Executable file names to look for.  Defaults to
        :attr:`~GM_VIP_Automation_Framework.config.T32Settings.t32_exe_names`.

    Returns
    -------
    (exe_path, config_path)
        Both as absolute path strings.

    Raises
    ------
    T32AutoDetectError
        When no valid T32 installation is found in any of the search dirs.
    """
    dirs = search_dirs or settings.t32_search_dirs
    names = exe_names or settings.t32_exe_names

    logger.debug("Auto-detecting T32 in dirs: %s", dirs)

    for directory in dirs:
        dir_path = Path(directory)
        if not dir_path.is_dir():
            continue

        for exe_name in names:
            exe = dir_path / exe_name
            if not exe.is_file():
                continue

            # Look for config.t32 first in the same dir, then one level up.
            for cfg_candidate in (dir_path / "config.t32", dir_path.parent / "config.t32"):
                if cfg_candidate.is_file():
                    logger.info(
                        "T32 auto-detected: exe='%s', config='%s'", exe, cfg_candidate
                    )
                    return str(exe), str(cfg_candidate)

    raise T32AutoDetectError(
        f"Trace32 installation not found. Searched: {dirs}. "
        "Verify that Trace32 is installed and config.t32 is present."
    )


def parse_config_port(config_path: str) -> Optional[int]:
    """Parse the ``PORT=`` value from a Trace32 config / t32.ini file.

    Parameters
    ----------
    config_path:
        Path to the config file (``config.t32`` or ``t32.ini``).

    Returns
    -------
    int or None
        The port number, or ``None`` if not found.
    """
    try:
        text = Path(config_path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("Cannot read config file '%s': %s", config_path, exc)
        return None

    match = _PORT_RE.search(text)
    if match:
        port = int(match.group(1))
        logger.debug("Parsed PORT=%d from '%s'", port, config_path)
        return port
    return None


# ---------------------------------------------------------------------------
# Connection class
# ---------------------------------------------------------------------------

class T32Connection:
    """Lifecycle manager for a Trace32 RCL (Remote Control Link) session.

    Typical use as a context manager::

        with T32Connection() as conn:
            conn.cmd("GO")
            # … test steps …

    Or manually::

        conn = T32Connection()
        conn.launch()       # optional – start the T32 process
        conn.connect()      # establish the RCL socket
        # … test steps …
        conn.disconnect()

    Attributes
    ----------
    debugger:
        The underlying ``lauterbach.trace32.rcl`` debugger object.  ``None``
        until :meth:`connect` has been called successfully.
    process:
        The :class:`subprocess.Popen` object for the launched T32 process.
        ``None`` if the process was not started by this instance.
    """

    def __init__(
        self,
        exe_path: Optional[str] = None,
        config_path: Optional[str] = None,
        port: Optional[int] = None,
        protocol: Optional[str] = None,
    ) -> None:
        self._exe_path = exe_path or settings.t32_exe_path
        self._config_path = config_path or settings.t32_config_path
        self._port = port or settings.rcl_port
        self._protocol = protocol or settings.rcl_protocol

        self.debugger = None
        self.process: Optional[subprocess.Popen] = None
        self._connected = False

    # ------------------------------------------------------------------
    # Process management
    # ------------------------------------------------------------------

    def launch(
        self,
        exe_path: Optional[str] = None,
        config_path: Optional[str] = None,
    ) -> subprocess.Popen:
        """Start the Trace32 process.

        Parameters
        ----------
        exe_path:
            Override the executable path for this call only.
        config_path:
            Override the config file path for this call only.

        Returns
        -------
        subprocess.Popen
            The spawned process.

        Raises
        ------
        T32LaunchError
            If the process cannot be started.
        """
        exe = exe_path or self._exe_path
        cfg = config_path or self._config_path

        logger.info("Launching Trace32: '%s' -c '%s'", exe, cfg)
        try:
            self.process = subprocess.Popen(
                [exe, "-c", cfg],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("Trace32 process started (PID %d).", self.process.pid)
            return self.process
        except OSError as exc:
            raise T32LaunchError(
                f"Failed to start Trace32 '{exe}': {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # RCL connection
    # ------------------------------------------------------------------

    def connect(
        self,
        port: Optional[int] = None,
        protocol: Optional[str] = None,
        timeout_s: Optional[float] = None,
        max_wait_s: Optional[float] = None,
    ) -> None:
        """Establish the RCL connection to Trace32.

        Polls for up to *max_wait_s* seconds, retrying every
        :attr:`~T32Settings.poll_interval_s` seconds until the connection
        is accepted.

        Parameters
        ----------
        port:
            Override the port number for this call.
        protocol:
            Override the protocol (``"UDP"`` or ``"TCP"``) for this call.
        timeout_s:
            Individual API call timeout.
        max_wait_s:
            Maximum seconds to wait for T32 to accept the connection.

        Raises
        ------
        T32TimeoutError
            If Trace32 does not accept the connection within *max_wait_s*.
        """
        p = port or self._port
        proto = protocol or self._protocol
        tmo = timeout_s or settings.rcl_timeout_s
        wait = max_wait_s or settings.connect_max_wait_s

        logger.info(
            "Connecting to T32 on %s port %d (max_wait=%.1fs)…", proto, p, wait
        )

        deadline = time.monotonic() + wait
        last_exc: Optional[Exception] = None

        while time.monotonic() < deadline:
            try:
                import lauterbach.trace32.rcl as pyrcl  # lazy import
                self.debugger = pyrcl.connect(port=p, protocol=proto, timeout=tmo)
                self._connected = True
                logger.info("Connected to Trace32 on port %d.", p)
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                time.sleep(settings.poll_interval_s)

        raise T32TimeoutError(
            f"T32 did not accept RCL connection on port {p} within {wait}s. "
            f"Last error: {last_exc}"
        )

    def disconnect(self) -> None:
        """Close the RCL connection gracefully."""
        if self._connected and self.debugger is not None:
            try:
                self.debugger.disconnect()
                logger.info("Disconnected from Trace32.")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error while disconnecting: %s", exc)
            finally:
                self._connected = False
                self.debugger = None

    def is_connected(self) -> bool:
        """Return ``True`` if the RCL connection is currently active."""
        return self._connected and self.debugger is not None

    # ------------------------------------------------------------------
    # Low-level command proxy
    # ------------------------------------------------------------------

    def cmd(self, command: str) -> None:
        """Send a raw PRACTICE/CMM command to Trace32.

        Parameters
        ----------
        command:
            Trace32 PRACTICE command string (e.g. ``"GO"``, ``"BREAK.DELETE"``).

        Raises
        ------
        T32ConnectionError
            If not connected.
        """
        self._assert_connected()
        logger.debug("T32 cmd: %s", command)
        self.debugger.cmd(command)

    def fnc(self, expression: str) -> str:
        """Evaluate a Trace32 PRACTICE function expression and return the result.

        Parameters
        ----------
        expression:
            PRACTICE expression string (e.g. ``"STATE.RUN()"``,
            ``"VAR.VALUE(myVar)"``).

        Returns
        -------
        str
            The string representation of the evaluated result.

        Raises
        ------
        T32ConnectionError
            If not connected.
        """
        self._assert_connected()
        logger.debug("T32 fnc: %s", expression)
        result = self.debugger.fnc(expression)
        return str(result)

    def _assert_connected(self) -> None:
        if not self.is_connected():
            raise T32ConnectionError(
                "Not connected to Trace32. Call connect() first."
            )

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "T32Connection":
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()

    def __repr__(self) -> str:
        state = "connected" if self._connected else "disconnected"
        return f"T32Connection(port={self._port}, {state})"


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def connect(
    exe_path: Optional[str] = None,
    config_path: Optional[str] = None,
    port: Optional[int] = None,
    protocol: Optional[str] = None,
    auto_launch: bool = False,
) -> T32Connection:
    """Create and return a connected :class:`T32Connection`.

    Parameters
    ----------
    exe_path:
        Path to the Trace32 executable.  Required when *auto_launch* is
        ``True`` and no default has been set in :data:`~config.settings`.
    config_path:
        Path to the T32 config file (used when *auto_launch* is ``True``).
    port:
        RCL port number.
    protocol:
        RCL protocol (``"UDP"`` or ``"TCP"``).
    auto_launch:
        When ``True`` the Trace32 process is started before connecting.

    Returns
    -------
    T32Connection
        A connected instance.
    """
    conn = T32Connection(
        exe_path=exe_path,
        config_path=config_path,
        port=port,
        protocol=protocol,
    )
    if auto_launch:
        conn.launch()
    conn.connect()
    return conn
