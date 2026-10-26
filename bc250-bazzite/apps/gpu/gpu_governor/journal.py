# SPDX-License-Identifier: GPL-3.0-or-later
"""Live journal tail: `journalctl -u UNIT -f` in a QProcess with a text filter and a follow toggle."""

from __future__ import annotations

import re
from collections import deque

from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from . import fmt
from .widgets import Terminal, hint_label

MAX_LINES = 2000            # kept in memory; older lines fall off the top
INITIAL_LINES = 200
RESTART_DELAY_MS = 3000     # when journalctl exits on its own (e.g. journal rotated), start again


class JournalView(QWidget):
    def __init__(self, unit: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.unit = unit
        self.lines: deque[str] = deque(maxlen=MAX_LINES)
        self._partial = ""
        self._pattern: re.Pattern[str] | None = None
        self._pattern_error = ""
        self._following = False     # whether the label already says "Following …"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Filter:"))
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("text or regular expression, case-insensitive")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._filter_changed)
        bar.addWidget(self.filter, 1)
        self.follow = QCheckBox("Follow")
        self.follow.setChecked(True)
        self.follow.setToolTip("Keep scrolling to the newest line. Untick to read without being moved.")
        self.follow.toggled.connect(self._render)
        bar.addWidget(self.follow)
        self.clear = QPushButton("Clear")
        self.clear.setToolTip("Forget the lines shown so far; new entries keep coming in.")
        self.clear.clicked.connect(self._clear)
        bar.addWidget(self.clear)
        layout.addLayout(bar)

        self.terminal = Terminal()
        layout.addWidget(self.terminal, 1)
        self.state = hint_label("")
        layout.addWidget(self.state)

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(100)
        self._render_timer.timeout.connect(self._render)
        self._restart_timer = QTimer(self)
        self._restart_timer.setSingleShot(True)
        self._restart_timer.timeout.connect(self.start)

    # ------------------------------------------------------------------ process
    def start(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        # Every start re-reads the last INITIAL_LINES, so drop what is shown to avoid duplicates.
        self.lines.clear()
        self._partial = ""
        self._following = False
        self.state.setText(fmt("journalctl -u %1 -f — connecting…", self.unit))
        # -q hides the "journal begins at" notice; -o short-iso matches the old snapshot format.
        self.process.start("journalctl", ["-u", self.unit, "-n", str(INITIAL_LINES), "-f", "-q", "--no-pager",
                                          "-o", "short-iso"])

    def stop(self) -> None:
        self._restart_timer.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1500):
                self.process.kill()
                self.process.waitForFinished(500)

    def _read(self) -> None:
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        text = self._partial + data
        *complete, self._partial = text.split("\n")
        if complete:
            self.lines.extend(complete)
            self._render_timer.start()
        if not self._following:
            self.state.setText(fmt("Following journalctl -u %1; up to %2 lines are kept.",
                                    self.unit, str(MAX_LINES)))
            self._following = True

    def _finished(self, code: int, status: QProcess.ExitStatus) -> None:
        tail = self._partial.strip()
        self._following = False
        if self._partial:
            self.lines.append(self._partial)
            self._partial = ""
        self._render()
        if status == QProcess.ExitStatus.CrashExit or code != 0:
            why = tail or fmt("exit code %1", str(code))
            self.state.setText(fmt(("journalctl stopped (%1). Your user may need to be in the "
                                    "systemd-journal or wheel group to read system units. Retrying in "
                                    "%2 s…"), why, str(RESTART_DELAY_MS // 1000)))
        else:
            self.state.setText(fmt("journalctl ended; restarting in %1 s…",
                                    str(RESTART_DELAY_MS // 1000)))
        if self.isVisible():
            self._restart_timer.start(RESTART_DELAY_MS)

    def _error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._following = False
            self.state.setText(("journalctl is not available on this system; the journal cannot be "
                                "shown."))

    # ------------------------------------------------------------------ view
    def _filter_changed(self, text: str) -> None:
        self._pattern_error = ""
        if not text.strip():
            self._pattern = None
        else:
            try:
                self._pattern = re.compile(text, re.IGNORECASE)
            except re.error:
                # Not a valid regex: fall back to a plain substring match.
                self._pattern = re.compile(re.escape(text), re.IGNORECASE)
                self._pattern_error = " (taken literally, not a valid regular expression)"
        self._render()

    def _clear(self) -> None:
        self.lines.clear()
        self._render()

    def _render(self) -> None:
        shown = [l for l in self.lines if self._pattern is None or self._pattern.search(l)]
        bar = self.terminal.verticalScrollBar()
        keep = bar.value()
        self.terminal.setPlainText("\n".join(shown))
        if self.follow.isChecked():
            bar.setValue(bar.maximum())
        else:
            bar.setValue(min(keep, bar.maximum()))
        if self._pattern is not None:
            self._following = False
            self.state.setText(fmt("%1 of %2 lines match%3.",
                                    str(len(shown)), str(len(self.lines)), self._pattern_error))
        elif self.lines and self.process.state() == QProcess.ProcessState.Running:
            self.state.setText(fmt("Following journalctl -u %1; up to %2 lines are kept.",
                                    self.unit, str(MAX_LINES)))
            self._following = True

    # ------------------------------------------------------------------ lifecycle
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        # Nothing to tail for while another page is shown; the lines read so far stay.
        self.stop()
