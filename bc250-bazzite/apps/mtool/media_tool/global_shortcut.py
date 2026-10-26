# SPDX-License-Identifier: GPL-3.0-or-later
"""Manage the desktop-portal process that owns the global recording shortcut."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt6.QtCore import QProcess, pyqtSignal
from PyQt6.QtWidgets import QWidget


class GlobalShortcutManager(QWidget):
    registered = pyqtSignal(str)
    activated = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.errorOccurred.connect(self._process_error)
        self.process.finished.connect(self._process_finished)
        self.process.setWorkingDirectory(str(Path(__file__).resolve().parents[1]))
        self._is_registered = False
        self._request_pending = False
        self._failed = False
        self._stopping = False

    def register(self) -> None:
        if self._is_registered:
            self.registered.emit(self.trigger_description)
            return
        if self._request_pending:
            return
        self._request_pending = True
        self._failed = False
        self._stopping = False
        self.trigger_description = ""
        self.process.start(sys.executable, ["-m", "media_tool.shortcut_service"])

    def stop(self) -> None:
        self._request_pending = False
        self._is_registered = False
        self._stopping = True
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1000):
                self.process.kill()
                self.process.waitForFinished(1000)

    def _read_output(self) -> None:
        while self.process.canReadLine():
            raw_line = bytes(self.process.readLine().data()).decode("utf-8").strip()
            if not raw_line:
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                self._fail(f"The shortcut service returned invalid data: {exc}")
                continue
            if event.get("event") == "registered":
                trigger_description = event.get("trigger")
                if not isinstance(trigger_description, str) or not trigger_description:
                    self._fail("The desktop registered the shortcut without describing its trigger.")
                    continue
                self._request_pending = False
                self._is_registered = True
                self.trigger_description = trigger_description
                self.registered.emit(trigger_description)
            elif event.get("event") == "activated":
                self.activated.emit()
            elif event.get("event") == "error":
                self._fail(str(event.get("message", "Unknown global-shortcut error")))

    def _process_error(self) -> None:
        if self._request_pending or self._is_registered:
            self._fail("Could not start or keep running the global-shortcut service.")

    def _process_finished(self) -> None:
        if not self._stopping and (self._request_pending or self._is_registered):
            self._fail("The global-shortcut service stopped unexpectedly.")

    def _fail(self, message: str) -> None:
        if self._failed:
            return
        self._failed = True
        self._request_pending = False
        self._is_registered = False
        self.failed.emit(message)
