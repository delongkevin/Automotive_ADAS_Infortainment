"""
GM VIP Automation Framework – CMM Script Execution Helpers
===========================================================
Provides utilities for executing Trace32 CMM (PRACTICE macro) scripts and
capturing their output, mirroring the ``lFctn_G_T32_RUN_CMM_CORE`` CAPL
function in ``cT32.cin`` and the ``run_cmm`` helper in the existing
``t32.py`` pipeline script.

The output-capture approach uses Trace32's ``AREA`` command buffer:
1. The AREA is cleared and a unique sentinel is printed.
2. The CMM command / script is executed.
3. The AREA contents are saved to a temp file and polled until the sentinel
   appears (confirming the script has finished printing output).
4. The captured lines (between sentinels) are returned to the caller.

Public API
----------
- :func:`run_cmm_command` – execute a single PRACTICE command and return output.
- :func:`run_cmm_script` – run a ``.cmm`` file and return its AREA output.
- :func:`check_cmm_script_result` – run a CMM script and assert its result
  line matches an expected value.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import List, Optional

from ..config import settings
from ..utils.exceptions import T32CommandError, T32TimeoutError
from ..utils.logger import get_logger
from .debugger import _conn

logger = get_logger("cmm")

# Sentinel strings that bracket CMM output in the AREA buffer.
_SENTINEL_START = "GMVIPFwStart_SENTINEL"
_SENTINEL_END   = "GMVIPFwEnd_SENTINEL"

# Shared default_connection reference.
default_connection = None  # type: Optional[object]


def _resolve_conn(connection):
    return _conn(connection or default_connection)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _capture_area_output(
    conn,
    timeout_s: float,
    tmp_file: Path,
) -> List[str]:
    """Poll AREA.SAVE until the end sentinel appears, then return content lines."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(settings.poll_interval_s)
        try:
            conn.cmd(f"AREA.SAVE {tmp_file}")
        except Exception:  # noqa: BLE001
            continue
        text = tmp_file.read_text(encoding="utf-8", errors="replace")
        if _SENTINEL_END in text:
            conn.cmd("AREA.CLEAR")
            content = (
                text
                .replace(_SENTINEL_START, "")
                .replace(_SENTINEL_END, "")
            )
            return [ln for ln in content.splitlines() if ln.strip()]

    logger.error("CMM area capture timed out after %.1fs.", timeout_s)
    raise T32TimeoutError(
        f"CMM output did not contain end sentinel within {timeout_s}s."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_cmm_command(
    command: str,
    timeout_s: Optional[float] = None,
    connection=None,
) -> List[str]:
    """Execute a single PRACTICE command and return its AREA output lines.

    The command is sent directly via :meth:`~connection.T32Connection.cmd`.
    Any output the command writes to the AREA buffer is captured and returned.

    Parameters
    ----------
    command:
        PRACTICE command string (e.g. ``"SYStem.Up"``, ``"Data.List R0"``).
    timeout_s:
        Maximum seconds to wait for output.  Defaults to
        :attr:`~config.T32Settings.cmm_timeout_s`.
    connection:
        Optional connection override.

    Returns
    -------
    list[str]
        Non-empty output lines captured from the AREA buffer.

    Raises
    ------
    T32TimeoutError
        If output is not available within *timeout_s*.
    T32CommandError
        If the command itself raises an error.
    """
    conn = _resolve_conn(connection)
    tmo = timeout_s if timeout_s is not None else settings.cmm_timeout_s

    logger.info("CMM command: %s", command)
    with tempfile.NamedTemporaryFile(
        suffix="_cmm.log", delete=False, mode="w", encoding="utf-8"
    ) as _tf:
        tmp = Path(_tf.name)

    try:
        conn.cmd("AREA")
        tmp.write_text("", encoding="utf-8")
        conn.cmd("AREA.CLEAR")
        conn.cmd(f"PRINT \"{_SENTINEL_START}\"")
        try:
            conn.cmd(command)
        except Exception as exc:  # noqa: BLE001
            raise T32CommandError(command, -1, str(exc)) from exc
        conn.cmd(f"PRINT \"{_SENTINEL_END}\"")

        lines = _capture_area_output(conn, tmo, tmp)
        logger.debug("CMM command '%s' output (%d lines).", command, len(lines))
        return lines
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def run_cmm_script(
    script_path: str,
    arguments: str = "",
    timeout_s: Optional[float] = None,
    connection=None,
) -> List[str]:
    """Execute a ``.cmm`` script file and return its AREA output lines.

    Constructs a ``DO <script_path> [arguments]`` PRACTICE command and
    delegates to :func:`run_cmm_command`.

    Parameters
    ----------
    script_path:
        Absolute or relative path to the CMM script file.
    arguments:
        Optional space-separated argument string to pass to the script.
    timeout_s:
        Maximum seconds to wait.  Defaults to
        :attr:`~config.T32Settings.cmm_timeout_s`.
    connection:
        Optional connection override.

    Returns
    -------
    list[str]
        Non-empty output lines from the CMM script.

    Raises
    ------
    FileNotFoundError
        If *script_path* does not exist on the local filesystem.
    T32TimeoutError
        If the script does not complete within *timeout_s*.
    """
    p = Path(script_path)
    if not p.exists():
        raise FileNotFoundError(f"CMM script not found: {script_path}")

    cmd = f"DO {p}"
    if arguments:
        cmd = f"{cmd} {arguments}"
    return run_cmm_command(cmd, timeout_s=timeout_s, connection=connection)


def check_cmm_script_result(
    script_path: str,
    expected_result_line: str,
    arguments: str = "",
    timeout_s: Optional[float] = None,
    connection=None,
) -> bool:
    """Run *script_path* and assert that *expected_result_line* appears in its output.

    Mirrors CAPL ``E_DBGR_CheckCmmScriptResult``.

    Parameters
    ----------
    script_path:
        Path to the CMM script.
    expected_result_line:
        String that must appear (case-sensitive substring match) in at least
        one output line of the script.
    arguments:
        Optional arguments string passed to the script.
    timeout_s:
        Script execution timeout.
    connection:
        Optional connection override.

    Returns
    -------
    bool
        ``True`` when *expected_result_line* is found in the output.

    Raises
    ------
    T32CommandError
        When the expected result is NOT found in any output line.
    """
    lines = run_cmm_script(
        script_path,
        arguments=arguments,
        timeout_s=timeout_s,
        connection=connection,
    )

    for line in lines:
        if expected_result_line in line:
            logger.info(
                "CMM script result PASS: '%s' found in output.", expected_result_line
            )
            return True

    logger.error(
        "CMM script result FAIL: '%s' not found in output.\nOutput:\n%s",
        expected_result_line,
        "\n".join(lines),
    )
    raise T32CommandError(
        script_path,
        -1,
        f"Expected result line '{expected_result_line}' not found in CMM script output.",
    )
