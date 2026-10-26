# SPDX-License-Identifier: GPL-3.0-or-later
"""Running the driver's helper (driver.py install / uninstall / load) as root through polkit.

The helper runs with the system Python in isolated mode (-I), so nothing from the user's environment or the
current folder is imported into the root process; it needs only the standard library."""

from __future__ import annotations

from . import driver


def run(args: list[str]) -> str:
    """Runs the helper and waits for it, keeping the window responsive while the password dialog is up. Returns
    what went wrong, "" when nothing did."""
    from PyQt6.QtCore import QEventLoop, QProcess
    process = QProcess()
    loop = QEventLoop()
    process.finished.connect(loop.quit)
    process.errorOccurred.connect(lambda _e: loop.quit())
    cmd = driver.command(args)
    process.start(cmd[0], cmd[1:])
    if not process.waitForStarted(5000):
        return f"Could not start pkexec: {process.errorString()}"
    loop.exec()
    out = bytes(process.readAllStandardOutput()).decode("utf-8", "replace")
    err = bytes(process.readAllStandardError()).decode("utf-8", "replace")
    return driver.answer(process.exitCode(), out + ("\n" + err if err.strip() and not out.strip() else ""))
