"""
GM VIP Automation Framework – Logging Utility
==============================================
Provides a pre-configured :class:`logging.Logger` for the framework.
By default a coloured ``StreamHandler`` (stdout) and a rotating
``FileHandler`` are attached.  Both handlers can be configured via
:func:`configure_logger` or by setting environment variables.

Environment variables
---------------------
``T32_LOG_LEVEL``
    Root log level (default: ``DEBUG``).  Accepts any :mod:`logging` level
    name, e.g. ``INFO``, ``WARNING``.
``T32_LOG_FILE``
    Path to the log file.  If empty / unset no file handler is created.
``T32_LOG_MAX_BYTES``
    Maximum size in bytes before the log file is rotated (default: 5 MB).
``T32_LOG_BACKUP_COUNT``
    Number of backup log files to keep (default: 3).
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_LOGGER_NAME = "gm_vip_t32"

# ANSI colour codes used only when writing to a TTY.
_COLOURS = {
    logging.DEBUG:    "\033[36m",   # cyan
    logging.INFO:     "\033[32m",   # green
    logging.WARNING:  "\033[33m",   # yellow
    logging.ERROR:    "\033[31m",   # red
    logging.CRITICAL: "\033[35m",   # magenta
}
_RESET = "\033[0m"


class _ColouredFormatter(logging.Formatter):
    """Logging formatter that adds ANSI colours to level names on TTYs."""

    _FMT = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    _DATE_FMT = "%Y-%m-%d %H:%M:%S"

    def __init__(self, use_colour: bool = True) -> None:
        super().__init__(fmt=self._FMT, datefmt=self._DATE_FMT)
        self._use_colour = use_colour

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        formatted = super().format(record)
        if self._use_colour:
            colour = _COLOURS.get(record.levelno, "")
            return f"{colour}{formatted}{_RESET}"
        return formatted


def configure_logger(
    level: Optional[str] = None,
    log_file: Optional[str] = None,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> logging.Logger:
    """Create and configure the framework logger.

    Parameters
    ----------
    level:
        Log level name (e.g. ``"DEBUG"``).  Defaults to the value of the
        ``T32_LOG_LEVEL`` environment variable or ``"DEBUG"``.
    log_file:
        Path to a log file.  If ``None`` the value of the ``T32_LOG_FILE``
        environment variable is used; if that is also empty no file handler
        is added.
    max_bytes:
        Rotating-file maximum size in bytes.
    backup_count:
        Number of backup files to keep when rotating.

    Returns
    -------
    logging.Logger
        The configured logger instance.
    """
    logger = logging.getLogger(_LOGGER_NAME)

    # Avoid duplicate handlers if called multiple times.
    if logger.handlers:
        return logger

    resolved_level = level or os.environ.get("T32_LOG_LEVEL", "DEBUG")
    numeric_level = getattr(logging, resolved_level.upper(), logging.DEBUG)
    logger.setLevel(numeric_level)

    # Stream handler (stdout).
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(numeric_level)
    use_colour = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    stream_handler.setFormatter(_ColouredFormatter(use_colour=use_colour))
    logger.addHandler(stream_handler)

    # Optional rotating file handler.
    resolved_file = log_file or os.environ.get("T32_LOG_FILE", "")
    if resolved_file:
        file_path = Path(resolved_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(_ColouredFormatter(use_colour=False))
        logger.addHandler(file_handler)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a child logger for the given *name* under the framework root.

    Parameters
    ----------
    name:
        Sub-module name appended to the root logger name, e.g. ``"breakpoints"``.
        If ``None`` the root framework logger is returned.
    """
    root = logging.getLogger(_LOGGER_NAME)
    # Ensure the root logger has been initialised.
    if not root.handlers:
        configure_logger()
    return root.getChild(name) if name else root
