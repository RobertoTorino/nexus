# SPDX-License-Identifier: GPL-3.0-or-later
"""Stores the output of every run as a timestamped log file."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from . import APP_ID


def log_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    path = base / APP_ID / "logs"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    for folder in (path.parent, path):           # logs and history are private to this user
        try:
            if folder.stat().st_mode & 0o077:
                folder.chmod(0o700)
        except OSError:
            pass
    return path


class RunLog:
    """One log file per run: <YYYYmmdd-HHMMSS>_<scope>.log"""

    def __init__(self, scope: str, redact: Callable[[str], str] | None = None):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.path = log_dir() / f"{stamp}_{scope}.log"
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        self._fh = os.fdopen(fd, "w", encoding="utf-8")
        self._redact = redact

    def write(self, line: str) -> None:
        self._fh.write((self._redact(line) if self._redact else line) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


# Absolute paths to log/data/config files mentioned in a report, e.g. the script's own report in
# /var/log/bc250-bazzite-test/, the stress CSV, the GPU load tool log or the governor config.
_FILE_REF = re.compile(
    r"(?<![\w.~/:])(~?/(?:[\w.+@-]+/)*[\w.+@-]+\.(?:log|csv|txt|json|toml|conf|cfg|ini|yaml|yml))(?![\w/])")
MAX_VIEW_BYTES = 2 * 1024 * 1024


def referenced_files(text: str) -> list[str]:
    """Unique file paths mentioned in text, in order of first appearance."""
    # Masked logs (Settings > Privacy) write the home folder as ~.
    return list(dict.fromkeys(os.path.expanduser(p) for p in _FILE_REF.findall(text)))


def read_for_view(path: Path) -> str:
    """File contents for the viewer: the last MAX_VIEW_BYTES, or a readable explanation."""
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > MAX_VIEW_BYTES:
                fh.seek(size - MAX_VIEW_BYTES)
                head = f"[showing the last {MAX_VIEW_BYTES // 1048576} MiB of {size / 1048576:.1f} MiB]\n"
            else:
                head = ""
            return head + fh.read().decode("utf-8", errors="replace")
    except FileNotFoundError:
        return (f"{path} does not exist on this machine.\n\n"
                "Files in /tmp are removed at reboot, and the report may come from another machine.")
    except PermissionError:
        return (f"No permission to read {path}.\n\n"
                f"Open it from a terminal instead: sudo less {path}")
    except OSError as exc:
        return f"Could not read {path}: {exc}"


def list_logs(scope: str | list[str] | None = None) -> list[Path]:
    """Stored GUI logs, newest first. scope: one scope name, a list of them, or None for all."""
    files = sorted(log_dir().glob("*.log"), reverse=True)
    if scope:
        wanted = {scope} if isinstance(scope, str) else set(scope)
        files = [f for f in files if f.stem.split("_", 1)[-1] in wanted]
    return files
