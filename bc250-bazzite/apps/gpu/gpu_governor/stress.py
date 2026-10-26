# SPDX-License-Identifier: GPL-3.0-or-later
"""Stress helper for safe-point tests: finds a GPU load generator on PATH and runs it for the duration of a
TestMode test, so the pinned frequency/voltage pair is exercised instead of idling."""

from __future__ import annotations

import shutil

from PyQt6.QtCore import QObject, QProcess, pyqtSignal

from . import fmt

# name, arguments: each runs until killed. The first one found is the default.
LOAD_TOOLS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("vkmark", ("--run-forever",)),
    ("glmark2-wayland", ("--run-forever",)),
    ("glmark2", ("--run-forever",)),
    ("vkcube", ()),
    ("glxgears", ()),
)
# Sentinel value: also used as a dict/combo-box key elsewhere, so the text itself must not change.
NO_TOOL = "None (load the GPU yourself)"
KILL_GRACE_MS = 1500


def available_tools() -> list[str]:
    return [name for name, _ in LOAD_TOOLS if shutil.which(name)]


def tool_arguments(name: str) -> list[str]:
    return next((list(args) for tool, args in LOAD_TOOLS if tool == name), [])


class StressRunner(QObject):
    """Runs one load tool as a child process; `finished(exit_code, crashed)` only fires when the tool ends on
    its own, not when stop() kills it."""

    finished = pyqtSignal(int, bool)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._process: QProcess | None = None
        self._stopping = False
        self.tool = ""

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning

    def start(self, name: str) -> tuple[bool, str]:
        if self.running:
            return False, "A load tool is already running."
        program = shutil.which(name)
        if not program:
            return False, fmt("%1 was not found on PATH.", name)
        self.tool = name
        self._stopping = False
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._error)
        process.start(program, tool_arguments(name))
        if not process.waitForStarted(3000):
            self._process = None
            return False, fmt("%1 did not start: %2", name, process.errorString())
        self._process = process
        return True, ""

    def stop(self) -> None:
        process = self._process
        if process is None:
            return
        self._stopping = True
        if process.state() != QProcess.ProcessState.NotRunning:
            process.terminate()
            if not process.waitForFinished(KILL_GRACE_MS):
                process.kill()
                process.waitForFinished(500)
        self._process = None

    def _finished(self, code: int, status: QProcess.ExitStatus) -> None:
        if self._stopping:
            return
        self._process = None
        self.finished.emit(code, status == QProcess.ExitStatus.CrashExit)

    def _error(self, error: QProcess.ProcessError) -> None:
        if self._stopping or error == QProcess.ProcessError.FailedToStart:
            return
        if error == QProcess.ProcessError.Crashed:
            return                      # finished() follows with CrashExit
        self._process = None
        self.finished.emit(-1, True)
