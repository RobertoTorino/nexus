# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import codecs
import os
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal

HOMEBREW_BIN_DIRS = (
    Path("/home/linuxbrew/.linuxbrew/bin"),
    Path("/var/home/linuxbrew/.linuxbrew/bin"),
    Path.home() / ".linuxbrew" / "bin",
)


def _path_with_fakeroot(path: str) -> str:
    path_entries = path.split(os.pathsep) if path else []
    for directory in HOMEBREW_BIN_DIRS:
        executable = directory / "fakeroot"
        if executable.is_file() and os.access(executable, os.X_OK) and str(directory) not in path_entries:
            path_entries.insert(0, str(directory))
    return os.pathsep.join(path_entries)


def discover_tests(directory: Path) -> list[Path]:
    """Return runnable shell tests in a stable order, excluding the shared shim helper."""
    resolved_directory = directory.resolve()
    return sorted(
        (
            path.resolve()
            for path in directory.glob("*.sh")
            if path.name != "shims.sh" and path.is_file() and path.resolve().parent == resolved_directory
        ),
        key=lambda path: path.name,
    )


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
        if path.parent != self.tests_directory or path.suffix != ".sh" or path.name == "shims.sh":
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
        process.start("bash", [str(self._current)])

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
