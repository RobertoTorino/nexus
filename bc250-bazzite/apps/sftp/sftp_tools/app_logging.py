# SPDX-License-Identifier: GPL-3.0-or-later
"""File logging for the application."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "bc250-bazzite-sftp-tools"


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def setup_logging(log_file: Path, log_max_mb: int = 10) -> None:
    """Log to a rotating file and record uncaught exceptions.

    Args:
        log_file: Path to the log file
        log_max_mb: Maximum log file size in MB before rotation (1-100)
    """
    logger = get_logger()
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # Convert MB to bytes (ensure at least 1KB minimum)
        max_bytes = max(1_000_000 * log_max_mb, 1024)
        handler: logging.Handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=3, encoding="utf-8"
        )
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(handler)

    def excepthook(exc_type, exc, tb) -> None:
        logger.critical("Uncaught exception", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = excepthook


def set_log_level(level: str) -> None:
    get_logger().setLevel(getattr(logging, level, logging.INFO))


class ErrorCallbackHandler(logging.Handler):
    """Calls ``callback`` for every ERROR or higher record (any thread)."""

    def __init__(self, callback) -> None:
        super().__init__(level=logging.ERROR)
        self.callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        self.callback()
