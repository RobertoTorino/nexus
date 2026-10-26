# SPDX-License-Identifier: GPL-3.0-or-later
"""Running the CMOS helper (cmos.py) as root through polkit, and the report of a CMOS read.

The helper runs with the system Python in isolated mode (-I), so nothing from the user's environment or the
current folder is imported into the root process; it needs only the standard library."""

from __future__ import annotations

import json
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import cmos

CMOS_SCRIPT = Path(cmos.__file__).resolve()
SYSTEM_PYTHON = Path("/usr/bin/python3")


@dataclass(frozen=True)
class Result:
    ok: bool
    data: dict
    error: str


def command(args: list[str]) -> list[str]:
    python = str(SYSTEM_PYTHON) if SYSTEM_PYTHON.is_file() else sys.executable
    return ["pkexec", python, "-I", str(CMOS_SCRIPT), *args]


def parse(code: int, stdout: str) -> Result:
    """The helper prints one JSON object; pkexec exits with 126 or 127 when the password dialog is canceled."""
    if code in (126, 127):
        return Result(False, {}, "Not authorized: the password dialog was canceled or refused.")
    for line in reversed(stdout.strip().splitlines()):
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict):
            return Result(bool(data.get("ok")), data, data.get("error", ""))
    return Result(False, {}, f"The helper stopped with exit code {code} without an answer:\n{stdout.strip()}")


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
        return Result(False, {}, f"Could not start pkexec: {process.errorString()}")
    loop.exec()
    out = bytes(process.readAllStandardOutput()).decode("utf-8", "replace")
    err = bytes(process.readAllStandardError()).decode("utf-8", "replace")
    return parse(process.exitCode(), out + ("\n" + err if err.strip() and not out.strip() else ""))


def report(data: dict, sys_root: Path = Path("/sys"), now: float | None = None) -> str:
    """A CMOS read as text: where it comes from, the decoded block and the whole of bank 2."""
    def dmi(name: str) -> str:
        return cmos.read_text(sys_root / "class/dmi/id" / name)

    block = data["block"]
    bank = bytes.fromhex(data["bank"])
    match = "match" if block["checksum"] == block["computed_checksum"] else "MISMATCH"
    lines = [
        f"host       {socket.gethostname()}",
        f"time       {time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(now))}",
        f"bios       {dmi('bios_vendor')} {dmi('bios_version')} {dmi('bios_date')}",
        f"board      {dmi('board_name')}",
        "",
        f"signature  {block['signature']} ({block['signature_name']})",
        f"checksum   {block['checksum']} stored, {block['computed_checksum']} computed ({match})",
        f"UMA_SIZE   {block['uma_mb']} MB",
    ]
    lines += [f"{name:<10} {value}" for name, value in block["fields"].items()]
    lines += [f"problem    {p}" for p in block["problems"]]
    lines += ["", "bank 2:", "     " + " ".join(f"{i:02X}" for i in range(16))]
    lines += [f"{row:02X}0  " + " ".join(f"{b:02X}" for b in bank[row * 16:row * 16 + 16]) for row in range(16)]
    return "\n".join(lines) + "\n"
