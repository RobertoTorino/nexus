# SPDX-License-Identifier: GPL-3.0-or-later
"""A log file per app (owner, 24-10-2026): ~/.local/share/<app id>/<app id>.log, one line per thing the app says or
does, with the time, and every uncaught error with its traceback. The file turns over at 1 MB, with three older
ones kept, so it never grows past a few MB. An app calls setup() once at start and logger() wherever it logs; what
the file holds the app also shows in its window, so the log is what happened in words, not a debug trace.

Personal data stays out of it as it stays out of everything else the suite writes: an app logs what it did, not
keys or account details.

An app of a suite with a folder of its own (the Windows Portable Suite) names it, and its log goes there:
%LOCALAPPDATA%\\windows-portable-suite\\<app id>\\<app id>.log (platform.suite_data()). The BC250 suite's apps name
none, and their logs stay where they are."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .platform import data_home, suite_data

MAX_BYTES = 1_000_000
KEPT = 3
FORMAT = "%(asctime)s %(levelname)s %(message)s"
DATE = "%d-%m-%Y %H:%M:%S"


def log_file(app_id: str, suite: str = "") -> Path:
    """The app's log: in its *suite*'s folder when it names one, else ~/.local/share/<app id>/."""
    return (suite_data(suite) if suite else data_home()) / app_id / f"{app_id}.log"


def logger(app_id: str) -> logging.Logger:
    return logging.getLogger(app_id)


def setup(app_id: str, path: Path | None = None, suite: str = "") -> Path:
    """The app's log, in *path* (its own file, log_file(app_id, suite), when not given): every record of
    logger(app_id) goes there, and an uncaught exception is written before Python reports it. A second call changes
    nothing. Returns the file; when it cannot be made, the log goes to stderr and the file is still what is
    returned."""
    path = path or log_file(app_id, suite)
    log = logger(app_id)
    if log.handlers:
        return path
    log.setLevel(logging.INFO)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=KEPT,
                                                       encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(FORMAT, DATE))
    log.addHandler(handler)
    previous = sys.excepthook

    def excepthook(kind, error, trace) -> None:
        log.critical("Uncaught error", exc_info=(kind, error, trace))
        previous(kind, error, trace)
    sys.excepthook = excepthook
    return path


def tail(path: Path, lines: int = 200) -> str:
    """The last *lines* of the log, "" when there is none yet."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.rstrip("\n").split("\n")[-lines:]) if text.strip() else ""
