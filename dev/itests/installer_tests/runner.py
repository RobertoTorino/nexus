# SPDX-License-Identifier: GPL-3.0-or-later
"""The installer tests of a suite and how they run: each script in its own process, one after another, with its
output as it comes. A Bazzite suite's tests are bash scripts (fakeroot from Homebrew on Bazzite), a Windows suite's
PowerShell scripts; which kind a suite has says where its tests run (tools/suites.py: SYSTEM)."""

from __future__ import annotations

import codecs
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal

HOMEBREW_BIN_DIRS = (
    Path("/home/linuxbrew/.linuxbrew/bin"),
    Path("/var/home/linuxbrew/.linuxbrew/bin"),
    Path.home() / ".linuxbrew" / "bin",
)
HELPERS = {"shims.sh", "test.ps1"}                  # beside the tests: the shims, the Windows release test's helper
KINDS = {".sh": "bash", ".ps1": "powershell"}        # a test script's kind by its suffix, and what runs it


def _path_with_fakeroot(path: str) -> str:
    path_entries = path.split(os.pathsep) if path else []
    for directory in HOMEBREW_BIN_DIRS:
        executable = directory / "fakeroot"
        if executable.is_file() and os.access(executable, os.X_OK) and str(directory) not in path_entries:
            path_entries.insert(0, str(directory))
    return os.pathsep.join(path_entries)


def tests_dir(suite: Path) -> Path:
    """Where a suite keeps its installer tests."""
    return suite / "tools" / "installer-tests"


def suffix_here(platform: str = sys.platform) -> str:
    """The kind of test script this system runs: .ps1 on Windows, .sh elsewhere."""
    return ".ps1" if platform == "win32" else ".sh"


def discover_tests(directory: Path, suffix: str | None = None) -> list[Path]:
    """The runnable test scripts in *directory* in a stable order, the helpers left out: the scripts of *suffix*
    (default: this system's kind)."""
    suffix = suffix or suffix_here()
    resolved_directory = directory.resolve()
    return sorted(
        (
            path.resolve()
            for path in directory.glob(f"*{suffix}")
            if path.name not in HELPERS and path.is_file() and path.resolve().parent == resolved_directory
        ),
        key=lambda path: path.name,
    )


def command_for(script: Path) -> list[str]:
    """What runs *script*: bash for a .sh, PowerShell (without the profile, every script allowed) for a .ps1."""
    if script.suffix == ".ps1":
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    return ["bash", str(script)]


class InstallerTestRunner(QObject):
    output = pyqtSignal(str)
    test_started = pyqtSignal(str)
    test_finished = pyqtSignal(str, int, bool)
    run_finished = pyqtSignal(bool)

    def __init__(self, tests_directory: Path, working_directory: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.tests_directory = tests_directory.resolve()
        self.working_directory = working_directory.resolve()
        self._queue: list[Path] = []
        self._current: Path | None = None
        self._process: QProcess | None = None
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._cancelled = False
        self._kill_timer = QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.timeout.connect(self._kill_if_running)

    @property
    def busy(self) -> bool:
        return self._process is not None

    def start(self, scripts: list[Path]) -> None:
        if self.busy:
            raise RuntimeError("An installer test run is already in progress")
        if not scripts:
            raise ValueError("Select at least one installer test")

        validated = [self._validate_script(script) for script in scripts]
        self._queue = validated
        self._cancelled = False
        self._start_next()

    def cancel(self) -> None:
        if self._process is None:
            return
        self._cancelled = True
        self._queue.clear()
        self._process.terminate()
        self._kill_timer.start(2000)

    def shutdown(self) -> None:
        process = self._process
        if process is None:
            return
        self.cancel()
        if not process.waitForFinished(3000):
            process.kill()
            process.waitForFinished(1000)
        self._kill_timer.stop()

    def _validate_script(self, script: Path) -> Path:
        path = script.resolve(strict=True)
        if path.parent != self.tests_directory or path.suffix not in KINDS or path.name in HELPERS:
            raise ValueError(f"Not an installer test script: {script}")
        if not path.is_file():
            raise ValueError(f"Not a regular file: {script}")
        return path

    def _start_next(self) -> None:
        if self._cancelled or not self._queue:
            self.run_finished.emit(self._cancelled)
            return

        self._current = self._queue.pop(0)
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        process = QProcess(self)
        process.setWorkingDirectory(str(self.working_directory))
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PATH", _path_with_fakeroot(environment.value("PATH")))
        process.setProcessEnvironment(environment)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(lambda: self._read_output(process))
        process.finished.connect(lambda code, _status: self._finish_process(process, code))
        process.errorOccurred.connect(lambda error: self._process_error(process, error))
        self._process = process
        self.test_started.emit(self._current.name)
        command = command_for(self._current)
        process.start(command[0], command[1:])

    def _read_output(self, process: QProcess) -> None:
        text = self._decoder.decode(bytes(process.readAllStandardOutput()))
        if text:
            self.output.emit(text)

    def _process_error(self, process: QProcess, error: QProcess.ProcessError) -> None:
        if process is self._process and error == QProcess.ProcessError.FailedToStart:
            self.output.emit(f"Could not start {process.program()}: {process.errorString()}\n")
            self._finish_process(process, 127)

    def _finish_process(self, process: QProcess, exit_code: int) -> None:
        if process is not self._process:
            return
        self._read_output(process)
        remainder = self._decoder.decode(b"", final=True)
        if remainder:
            self.output.emit(remainder)
        self._kill_timer.stop()

        name = self._current.name if self._current else process.program()
        cancelled = self._cancelled
        self._process = None
        self._current = None
        process.deleteLater()
        self.test_finished.emit(name, exit_code, cancelled)
        self._start_next()

    def _kill_if_running(self) -> None:
        if self._process is not None:
            self._process.kill()
