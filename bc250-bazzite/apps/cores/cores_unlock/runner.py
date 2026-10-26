# SPDX-License-Identifier: GPL-3.0-or-later

"""Runs bc250-cores-unlock.sh through QProcess; install/uninstall go through sudo."""

from __future__ import annotations

import os
import shutil
import subprocess

from PyQt6.QtCore import QObject, QProcess, pyqtSignal

_SUDO_AUTH_FAIL = ("incorrect password", "Sorry, try again", "no password was provided",
                   "a password is required")


class UnlockRunner(QObject):
    line = pyqtSignal(str)           # one line of output
    finished = pyqtSignal(int)       # exit code (0 = success)
    auth_failed = pyqtSignal()

    def __init__(self, script: str, parent: QObject | None = None):
        super().__init__(parent)
        self.script = os.path.realpath(script)
        self._proc: QProcess | None = None
        self._buf = ""
        self._saw_output = False

    @property
    def busy(self) -> bool:
        return self._proc is not None

    @staticmethod
    def sudo_ready() -> bool:
        """True when sudo needs no password right now (cached credentials or NOPASSWD)."""
        if not shutil.which("sudo"):
            return False
        return subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode == 0

    def run(self, args: list[str], pw: str | None = None) -> None:
        """Run the script as root. Without pw, sudo must not prompt (-n)."""
        mode = ["-S", "-p", ""] if pw is not None else ["-n"]
        self._start("sudo", [*mode, "--", "bash", self.script, *args], pw)

    def run_unprivileged(self, args: list[str]) -> None:
        self._start("bash", [self.script, *args], None)

    def _start(self, program: str, argv: list[str], pw: str | None) -> None:
        if self.busy:
            raise RuntimeError("An action is already in progress")
        self._buf = ""
        self._saw_output = False
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.readyReadStandardOutput.connect(self._on_output)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)
        self._proc = proc
        proc.start(program, argv)
        if pw is not None:
            # Handed straight to sudo's stdin; never kept on this object or written anywhere.
            proc.write((pw + "\n").encode())
        proc.closeWriteChannel()

    def _on_output(self) -> None:
        assert self._proc is not None
        self._buf += bytes(self._proc.readAllStandardOutput()).decode(errors="replace")
        *lines, self._buf = self._buf.split("\n")
        for raw in lines:
            raw = raw.rstrip("\r")
            if not self._saw_output and any(s in raw for s in _SUDO_AUTH_FAIL):
                self.auth_failed.emit()
                continue
            self._saw_output = True
            self.line.emit(raw)

    def _on_error(self, err: QProcess.ProcessError) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self.line.emit(f"Failed to start: {self._proc.program() if self._proc else '?'}")
            self._finish(-1)

    def _on_finished(self, code: int, _status: QProcess.ExitStatus) -> None:
        self._finish(code)

    def _finish(self, code: int) -> None:
        if self._proc is None:
            return  # already finished via errorOccurred
        if self._buf:
            self.line.emit(self._buf)
            self._buf = ""
        self._proc = None
        self.finished.emit(code)
