"""
GM VIP Automation Framework – Framework Configuration
=====================================================
All tunable constants are centralised here so that they can be overridden
at runtime (e.g. from a test-bench configuration file or environment
variables) without touching source code.

Usage
-----
Import the singleton :data:`settings` object and read / write attributes::

    from GM_VIP_Automation_Framework.config import settings

    settings.t32_exe_path = r"C:\\T32\\t32marm.exe"
    settings.rcl_port = 20001

Alternatively, override individual settings via environment variables before
importing the framework::

    T32_EXE_PATH=C:/T32/t32marm.exe
    T32_RCL_PORT=20001
    T32_RCL_PROTOCOL=UDP

JSON Config File
----------------
All settings can also be persisted to / loaded from a ``config.json`` file::

    from GM_VIP_Automation_Framework.config import settings

    # Load from a file (merges values over any defaults / env-var overrides):
    settings.load_from_json("config.json")

    # Save current settings back to a file for editing:
    settings.save_to_json("config.json")

The JSON keys mirror the dataclass field names (e.g. ``"t32_exe_path"``,
``"rcl_port"``).  Unknown keys in the JSON file are silently ignored so that
hand-edited files remain forward-compatible.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class T32Settings:
    """Mutable settings bag for the GM VIP Automation Framework.

    All attributes can be overridden by the corresponding environment variable
    (see *env_var* comments next to each field).
    """

    # ------------------------------------------------------------------
    # Trace32 process / installation
    # ------------------------------------------------------------------

    #: Full path to the Trace32 executable (e.g. ``t32marm.exe``).
    #: env: T32_EXE_PATH
    t32_exe_path: str = field(
        default_factory=lambda: os.environ.get("T32_EXE_PATH", r"C:\T32\bin\windows64\t32marm64.exe")
    )

    #: Full path to the Trace32 config file (``config.t32``).
    #: env: T32_CONFIG_PATH
    t32_config_path: str = field(
        default_factory=lambda: os.environ.get("T32_CONFIG_PATH", r"C:\T32\config.t32")
    )

    #: Ordered list of directories to probe during auto-detect.
    #: env: T32_SEARCH_DIRS  (colon-separated on Unix, semicolon-separated on Windows)
    t32_search_dirs: List[str] = field(
        default_factory=lambda: _parse_search_dirs(
            os.environ.get(
                "T32_SEARCH_DIRS",
                r"C:\T32\bin\windows64\t32marm64.exe;C:\T32;C:\t32\bin;C:\t32",
            )
        )
    )

    #: Trace32 executable file names to look for during auto-detect.
    t32_exe_names: List[str] = field(
        default_factory=lambda: [
            "t32marm.exe",
            "t32marm64.exe",
            "t32mppc.exe",
            "t32mrisc.exe",
            "t32mrisc64.exe",
        ]
    )

    # ------------------------------------------------------------------
    # Remote Control Link (RCL / pyrcl) connection
    # ------------------------------------------------------------------

    #: Port number for the Trace32 RCL connection.
    #: env: T32_RCL_PORT
    rcl_port: int = field(
        default_factory=lambda: int(os.environ.get("T32_RCL_PORT", "20000"))
    )

    #: Protocol for the RCL connection (``"UDP"`` or ``"TCP"``).
    #: env: T32_RCL_PROTOCOL
    rcl_protocol: str = field(
        default_factory=lambda: os.environ.get("T32_RCL_PROTOCOL", "UDP")
    )

    #: Timeout in seconds for individual RCL API calls.
    #: env: T32_RCL_TIMEOUT_S
    rcl_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("T32_RCL_TIMEOUT_S", "1.0"))
    )

    #: RCL packet length in bytes.  1024 is the standard value for most
    #: Trace32 ARM/Aurix configurations.  Larger values can improve throughput
    #: on fast networks; must match the value configured in the T32 config file.
    #: env: T32_RCL_PACKLEN
    rcl_packlen: int = field(
        default_factory=lambda: int(os.environ.get("T32_RCL_PACKLEN", "1024"))
    )

    #: Maximum seconds to wait for T32 to accept a connection after launch.
    #: env: T32_CONNECT_MAX_WAIT_S
    connect_max_wait_s: float = field(
        default_factory=lambda: float(os.environ.get("T32_CONNECT_MAX_WAIT_S", "60.0"))
    )

    # ------------------------------------------------------------------
    # ECU state poll timeouts (seconds)
    # ------------------------------------------------------------------

    #: Maximum seconds to wait for the ECU to enter a *not-running* (halted)
    #: state (used by breakpoint-check and variable operations).
    #: env: T32_HALT_TIMEOUT_S
    halt_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("T32_HALT_TIMEOUT_S", "20.0"))
    )

    #: Maximum seconds to wait for the ECU to enter *running* state after GO.
    #: env: T32_RUN_TIMEOUT_S
    run_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("T32_RUN_TIMEOUT_S", "3.0"))
    )

    #: Poll interval in seconds when waiting for ECU state transitions.
    #: env: T32_POLL_INTERVAL_S
    poll_interval_s: float = field(
        default_factory=lambda: float(os.environ.get("T32_POLL_INTERVAL_S", "0.2"))
    )

    #: Extra settle time in seconds added after the ECU confirms a halted state
    #: following ``SYStem.RESetTarget``.  A non-zero value lets T32 finish
    #: rebuilding its internal state (register map, symbol accessibility, etc.)
    #: before the next command is issued.  Increase when variable reads or
    #: symbol lookups fail immediately after a reset.
    #: env: T32_POST_RESET_SETTLE_S
    post_reset_settle_s: float = field(
        default_factory=lambda: float(os.environ.get("T32_POST_RESET_SETTLE_S", "1.0"))
    )

    #: Brief pause in seconds after a ``GO`` command before the framework
    #: begins polling ``STATE.RUN()``.  Prevents a false "not running" reading
    #: in the milliseconds before the CPU has actually started executing.
    #: env: T32_GO_SETTLE_S
    go_settle_s: float = field(
        default_factory=lambda: float(os.environ.get("T32_GO_SETTLE_S", "0.3"))
    )

    # ------------------------------------------------------------------
    # Intermediate-halt retry (real hardware with multi-phase startup)
    # ------------------------------------------------------------------

    #: Maximum number of additional GO commands issued by :func:`check_halted_at`
    #: when the ECU halts at an unexpected address before reaching the target
    #: breakpoint.  This happens on Aurix / ARM hardware where startup
    #: initialization code executes (and may halt) between the reset and the
    #: first test function.  Set to ``0`` to disable the retry logic entirely.
    #: env: T32_INTERMEDIATE_HALT_MAX_GOS
    intermediate_halt_max_gos: int = field(
        default_factory=lambda: int(os.environ.get("T32_INTERMEDIATE_HALT_MAX_GOS", "3"))
    )

    #: Delay in seconds before each retry GO command issued during an
    #: intermediate-halt retry.  Matches the ~800 ms settle time observed on
    #: Aurix TC4 hardware after reset before the startup code yields control
    #: to the test application.
    #: env: T32_INTERMEDIATE_HALT_GO_DELAY_S
    intermediate_halt_go_delay_s: float = field(
        default_factory=lambda: float(os.environ.get("T32_INTERMEDIATE_HALT_GO_DELAY_S", "0.8"))
    )

    # ------------------------------------------------------------------
    # Breakpoint set retry logic  (mirrors CAPL cc_nT32_BP* constants)
    # ------------------------------------------------------------------

    #: Maximum number of BREAK.SET attempts before giving up.
    #: env: T32_BP_MAX_RETRIES
    bp_max_retries: int = field(
        default_factory=lambda: int(os.environ.get("T32_BP_MAX_RETRIES", "10"))
    )

    #: Delay in seconds between BREAK.SET retry attempts.
    #: env: T32_BP_RETRY_INTERVAL_S
    bp_retry_interval_s: float = field(
        default_factory=lambda: float(os.environ.get("T32_BP_RETRY_INTERVAL_S", "0.5"))
    )

    #: Attempt number at which a ``SYMBOL.RELOAD`` is issued mid-retry to
    #: recover from slow ELF symbol-table loading.
    #: env: T32_BP_SYMBOL_RELOAD_AT
    bp_symbol_reload_at: int = field(
        default_factory=lambda: int(os.environ.get("T32_BP_SYMBOL_RELOAD_AT", "5"))
    )

    #: Seconds to wait after issuing ``SYMBOL.RELOAD`` before retrying.
    #: env: T32_SYMBOL_RELOAD_WAIT_S
    symbol_reload_wait_s: float = field(
        default_factory=lambda: float(os.environ.get("T32_SYMBOL_RELOAD_WAIT_S", "5.0"))
    )

    # ------------------------------------------------------------------
    # CMM script execution
    # ------------------------------------------------------------------

    #: Default timeout in seconds for CMM script execution.
    #: env: T32_CMM_TIMEOUT_S
    cmm_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("T32_CMM_TIMEOUT_S", "60.0"))
    )

    #: Temporary directory used for CMM area log files.
    #: env: T32_TEMP_DIR
    temp_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("T32_TEMP_DIR", ""))
        if os.environ.get("T32_TEMP_DIR")
        else Path(__file__).parent / "_tmp"
    )

    # ------------------------------------------------------------------
    # CMM entry-point script
    # ------------------------------------------------------------------

    #: Optional path to a CMM (PRACTICE macro) script that serves as the
    #: Trace32 entry-point.  When set and Trace32 is launched by the
    #: framework, the process is started with ``-s <cmm_entry_script>`` so
    #: that the script executes at startup and can perform all T32
    #: setup (loading symbols, opening the API port, etc.).
    #: Leave empty (``""``) when Trace32 is already running or when no
    #: startup script is needed.
    #: env: T32_CMM_ENTRY_SCRIPT
    cmm_entry_script: str = field(
        default_factory=lambda: os.environ.get("T32_CMM_ENTRY_SCRIPT", "")
    )

    # ------------------------------------------------------------------
    # JSON config file I/O
    # ------------------------------------------------------------------

    def load_from_json(self, path: str) -> "T32Settings":
        """Load settings from a JSON config file, merging over current values.

        Only keys that exist as dataclass fields are applied; unknown keys in
        the JSON file are silently ignored so that hand-edited files remain
        forward-compatible.

        Parameters
        ----------
        path:
            Path to the ``config.json`` file.

        Returns
        -------
        T32Settings
            ``self`` (for chaining).

        Raises
        ------
        FileNotFoundError
            If *path* does not exist.
        ValueError
            If the file cannot be parsed as JSON.
        """
        config_path = Path(path)
        if not config_path.is_file():
            raise FileNotFoundError(f"Config file not found: {path}")

        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in '{path}': {exc}") from exc

        _field_names = {f.name for f in self.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        for key, value in raw.items():
            if key not in _field_names:
                continue
            current = getattr(self, key)
            if isinstance(current, Path):
                setattr(self, key, Path(value))
            elif isinstance(current, list):
                if isinstance(value, list):
                    setattr(self, key, [str(v) for v in value])
                elif isinstance(value, str):
                    setattr(self, key, _parse_search_dirs(value))
            elif isinstance(current, bool):
                setattr(self, key, bool(value))
            elif isinstance(current, int):
                setattr(self, key, int(value))
            elif isinstance(current, float):
                setattr(self, key, float(value))
            else:
                setattr(self, key, value)
        return self

    def save_to_json(self, path: str) -> None:
        """Serialize current settings to a JSON config file.

        The file is human-readable and can be edited then reloaded with
        :meth:`load_from_json`.

        Parameters
        ----------
        path:
            Destination file path.  Parent directories must exist.
        """
        data = {}
        for f in self.__dataclass_fields__.values():  # type: ignore[attr-defined]
            val = getattr(self, f.name)
            if isinstance(val, Path):
                data[f.name] = str(val)
            elif isinstance(val, list):
                data[f.name] = list(val)
            else:
                data[f.name] = val
        Path(path).write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )


def _parse_search_dirs(raw: str) -> List[str]:
    """Split a semicolon or colon-delimited string into a list of paths."""
    sep = ";" if ";" in raw else ":"
    return [d.strip() for d in raw.split(sep) if d.strip()]


# Module-level singleton – import and modify this object to configure the framework.
settings = T32Settings()

__all__ = ["T32Settings", "settings"]
