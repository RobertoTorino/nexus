# SPDX-License-Identifier: GPL-3.0-or-later
"""Running the access helper as root through pkexec: its exit code and output, keeping the window responsive while
the password dialog waits for the user."""

from __future__ import annotations

from dataclasses import dataclass

ROOT_TIMEOUT_MS = 300000                # pkexec: the password dialog waits for the user


@dataclass(frozen=True)
class Result:
    code: int
    out: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def run(argv: list[str], timeout_ms: int) -> Result:
    """Runs *argv* and waits for it; stdout and stderr together, as a terminal would show them."""
    from PyQt6.QtCore import QEventLoop, QProcess, QTimer
    process = QProcess()
    process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
    loop = QEventLoop()
    process.finished.connect(loop.quit)
    process.errorOccurred.connect(lambda _e: loop.quit())
    QTimer.singleShot(timeout_ms, loop.quit)
    process.start(argv[0], argv[1:])
    if not process.waitForStarted(5000):
        return Result(127, f"Could not start {argv[0]}: {process.errorString()}")
    loop.exec()
    if process.state() != QProcess.ProcessState.NotRunning:
        process.kill()
        process.waitForFinished(2000)
        return Result(124, f"{argv[0]} did not finish within {timeout_ms // 1000} s.")
    out = bytes(process.readAllStandardOutput()).decode("utf-8", "replace")
    return Result(process.exitCode(), out)


def run_root(argv: list[str]) -> Result:
    """*argv* starts with pkexec: it waits for the password before it runs."""
    return run(argv, ROOT_TIMEOUT_MS)
