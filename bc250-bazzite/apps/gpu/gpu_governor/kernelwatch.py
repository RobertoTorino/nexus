# SPDX-License-Identifier: GPL-3.0-or-later
"""Kernel-log watch for GPU trouble while a safe point is pinned.

`journalctl -k -f` is tailed in a QProcess and every new line is matched against the amdgpu / SMU messages that
precede or accompany a GPU hang (ring timeouts, GPU resets, *ERROR* lines, SMU failures). The first match is
reported through `event`; the main window aborts the test on it, so the pinned pair is released as soon as the
kernel complains rather than after the board has frozen. Reading the kernel ring needs the systemd-journal
group (or wheel) on most systems; without it `unavailable` fires and the test runs unobserved.
"""

from __future__ import annotations

import re

from PyQt6.QtCore import QObject, QProcess, pyqtSignal

from . import fmt

HANG_PATTERNS: tuple[re.Pattern[str], ...] = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"amdgpu.*\bGPU reset\b",
    r"amdgpu.*\bring \S+ timeout\b",
    r"amdgpu.*\b(hang|hung)\b",
    r"\[drm:[^\]]*\] \*ERROR\*",
    r"amdgpu.*\bsoft recovery\b",
    r"amdgpu.*\bfailed to (set|send|read|write|load|init)\b",
    r"\bSMU\b.*\b(failed|timed? ?out|timeout)\b",
    r"\bSMU\b.*not done with your previous command",
    r"amdgpu.*\bfence fallback\b",
    r"amdgpu.*\bMODE[12] reset\b",
))

# No -q: it would also hide the "not seeing messages from the kernel" hint that tells us the watch is blind.
JOURNAL_ARGS = ["-k", "-n", "0", "-f", "--no-pager", "-o", "short-iso"]
BLIND_HINTS = ("not seeing messages", "insufficient permissions", "permission denied")


def matches(line: str) -> bool:
    return any(p.search(line) for p in HANG_PATTERNS)


class KernelWatch(QObject):
    trouble = pyqtSignal(str)           # a kernel line that looks like GPU trouble
    unavailable = pyqtSignal(str)       # the kernel log cannot be read; why

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.events: list[str] = []
        self.reason = ""                # last `unavailable` text, "" while the watch works
        self._partial = ""
        self._stderr = ""
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self._process.readyReadStandardOutput.connect(self._read)
        self._process.readyReadStandardError.connect(self._read_error)
        self._process.finished.connect(self._finished)
        self._process.errorOccurred.connect(self._error)

    @property
    def running(self) -> bool:
        return self._process.state() != QProcess.ProcessState.NotRunning

    def start(self) -> None:
        if self.running:
            return
        self.events.clear()
        self.reason = ""
        self._partial = self._stderr = ""
        self._process.start("journalctl", JOURNAL_ARGS)

    def stop(self) -> None:
        if not self.running:
            return
        self._process.terminate()
        if not self._process.waitForFinished(1500):
            self._process.kill()
            self._process.waitForFinished(500)

    # ------------------------------------------------------------------ process
    def _read(self) -> None:
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        *lines, self._partial = (self._partial + data).split("\n")
        for line in lines:
            self.feed(line)

    def feed(self, line: str) -> None:
        """Consider one kernel line; split out so tests can drive the watch without journalctl."""
        if line and matches(line):
            self.events.append(line)
            self.trouble.emit(line)

    def _read_error(self) -> None:
        text = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        self._stderr += text
        # journalctl keeps following with no access to the kernel ring; it only says so once on stderr.
        if not self.reason and any(h in text.lower() for h in BLIND_HINTS):
            self._fail(("the kernel log is not readable by this user (add it to the systemd-journal "
                        "group)"))

    def _finished(self, code: int, status: QProcess.ExitStatus) -> None:
        if self._partial:
            self.feed(self._partial)
            self._partial = ""
        # terminate() from stop() ends with SIGTERM: that is not a failure worth reporting.
        if status == QProcess.ExitStatus.CrashExit:
            return
        if code != 0 and not self.reason:
            why = self._stderr.strip().splitlines()
            self._fail(why[-1] if why else fmt("journalctl -k exited with code %1", str(code)))

    def _error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._fail("journalctl is not available")

    def _fail(self, why: str) -> None:
        self.reason = why
        self.unavailable.emit(why)
