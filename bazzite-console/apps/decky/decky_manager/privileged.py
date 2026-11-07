# SPDX-License-Identifier: GPL-3.0-or-later
"""Running the root part (loader.py) through polkit, as vram runs its CMOS helper.

The helper runs with the system Python in isolated mode (-I), so nothing from the user's environment or the
current folder is imported into the root process; it needs only the standard library."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from . import loader

LOADER_SCRIPT = Path(loader.__file__).resolve()
SYSTEM_PYTHON = Path("/usr/bin/python3")


@dataclass(frozen=True)
class Result:
    ok: bool
    message: str


def command(args: list[str]) -> list[str]:
    python = str(SYSTEM_PYTHON) if SYSTEM_PYTHON.is_file() else sys.executable
    return ["pkexec", python, "-I", str(LOADER_SCRIPT), *args]


def parse(code: int, stdout: str) -> Result:
    """The helper prints one JSON object; pkexec exits with 126 or 127 when the password dialog is canceled."""
    if code in (126, 127):
        return Result(False, "Not authorized: the password dialog was canceled or refused.")
    for line in reversed(stdout.strip().splitlines()):
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict):
            ok = bool(data.get("ok"))
            return Result(ok, str(data.get("message" if ok else "error", "")))
    return Result(False, f"The helper stopped with exit code {code} without an answer:\n{stdout.strip()}")


def run(args: list[str]) -> Result:
    """Runs the helper and waits for it, keeping the window responsive while the password dialog is up."""
    from PyQt6.QtCore import QEventLoop, QProcess
    process = QProcess()
    loop = QEventLoop()
    process.finished.connect(loop.quit)
    process.errorOccurred.connect(lambda _e: loop.quit())
    cmd = command(args)
    process.start(cmd[0], cmd[1:])
    if not process.waitForStarted(5000):
        return Result(False, f"Could not start pkexec: {process.errorString()}")
    loop.exec()
    out = bytes(process.readAllStandardOutput()).decode("utf-8", "replace")
    err = bytes(process.readAllStandardError()).decode("utf-8", "replace")
    return parse(process.exitCode(), out + ("\n" + err if err.strip() and not out.strip() else ""))
