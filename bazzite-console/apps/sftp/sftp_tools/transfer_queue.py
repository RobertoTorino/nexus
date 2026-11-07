# SPDX-License-Identifier: GPL-3.0-or-later
"""Sequential transfer queue with progress and speed reporting."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Literal

import paramiko
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from .app_logging import get_logger
from .transfers import download_tree, get_file, put_file, upload_tree

Direction = Literal["upload", "download"]
QUEUED, RUNNING, FAILED, DONE = "queued", "running", "failed", "done"


@dataclass
class TransferJob:
    direction: Direction
    source: str
    destination: str
    is_dir: bool
    skip_existing: bool = False
    limit_kbps: int = 0
    state: str = QUEUED
    error: str = ""

    @property
    def label(self) -> str:
        arrow = "↑" if self.direction == "upload" else "↓"
        return f"{arrow} {self.source} → {self.destination}"


class _JobThread(QThread):
    progressed = pyqtSignal(int)

    def __init__(
        self,
        sftp: paramiko.SFTPClient,
        job: TransferJob,
        filter_invalid_chars: bool = True,
        char_replacement: str = "_",
        preserve_timestamps: bool = True,
    ) -> None:
        super().__init__()
        self.sftp = sftp
        self.job = job
        self.filter_invalid_chars = filter_invalid_chars
        self.char_replacement = char_replacement
        self.preserve_timestamps = preserve_timestamps
        self.cancelled = False
        self.error = ""
        self._started = time.monotonic()
        self._sent = 0

    def _progress(self, delta: int) -> None:
        if self.cancelled:
            raise InterruptedError("Transfer canceled")
        self.progressed.emit(delta)
        limit = self.job.limit_kbps * 1024
        if limit > 0:
            self._sent += delta
            due = self._started + self._sent / limit
            while (wait := due - time.monotonic()) > 0:
                if self.cancelled:
                    raise InterruptedError("Transfer canceled")
                time.sleep(min(wait, 0.1))

    def run(self) -> None:
        job = self.job
        try:
            if job.direction == "upload":
                (upload_tree if job.is_dir else put_file)(
                    self.sftp, job.source, job.destination,
                    self._progress, job.skip_existing,
                )
            else:
                if job.is_dir:
                    download_tree(
                        self.sftp, job.source, job.destination,
                        self._progress, job.skip_existing,
                        self.filter_invalid_chars, self.char_replacement,
                        self.preserve_timestamps,
                    )
                else:
                    get_file(
                        self.sftp, job.source, job.destination,
                        self._progress, job.skip_existing,
                        self.preserve_timestamps,
                    )
        except Exception as error:
            get_logger().error("Transfer failed: %s", job.label, exc_info=True)
            self.error = str(error) or type(error).__name__


class TransferQueue(QObject):
    changed = pyqtSignal()
    job_finished = pyqtSignal(object)
    speed_changed = pyqtSignal(str)
    beep_requested = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.jobs: list[TransferJob] = []
        self._sftp: paramiko.SFTPClient | None = None
        self._thread: _JobThread | None = None
        self._bytes = 0
        self._last_tick = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self.filter_invalid_chars = True
        self.char_replacement = "_"
        self.queue_autoclear = True
        self.preserve_timestamps = True

    @property
    def is_busy(self) -> bool:
        return self._thread is not None

    def jobs_in(self, state: str) -> list[TransferJob]:
        return [job for job in self.jobs if job.state == state]

    def set_sftp(self, sftp: paramiko.SFTPClient | None) -> None:
        self._sftp = sftp

    def enqueue(self, job: TransferJob) -> None:
        self.jobs.append(job)
        self.changed.emit()
        self._start_next()

    def abort_all(self, reason: str = "Disconnected") -> None:
        self._sftp = None
        for job in self.jobs_in(QUEUED):
            job.state, job.error = FAILED, reason
        if self._thread is not None:
            self._thread.cancelled = True
        self.changed.emit()

    def shutdown(self, timeout_ms: int = 5000) -> None:
        """Cancel everything and wait for the running transfer to stop."""
        thread = self._thread
        self.abort_all("Application closed")
        if thread is not None:
            thread.wait(timeout_ms)

    def clear_done_jobs(self) -> None:
        """Remove all completed jobs from the queue."""
        self.jobs = [job for job in self.jobs if job.state != DONE]
        self.changed.emit()

    def _start_next(self) -> None:
        if self._thread is not None:
            return
        queued = self.jobs_in(QUEUED)
        if not queued:
            return
        job = queued[0]
        if self._sftp is None:
            job.state, job.error = FAILED, "Not connected"
            self.changed.emit()
            self._start_next()
            return
        job.state = RUNNING
        thread = _JobThread(
            self._sftp, job,
            self.filter_invalid_chars, self.char_replacement,
            self.preserve_timestamps
        )
        thread.progressed.connect(self._add_bytes)
        thread.finished.connect(lambda: self._finished(thread))
        self._thread = thread
        self._bytes = 0
        self._last_tick = time.monotonic()
        self._timer.start()
        self.changed.emit()
        thread.start()

    def _add_bytes(self, delta: int) -> None:
        self._bytes += delta

    def _tick(self) -> None:
        now = time.monotonic()
        rate = self._bytes / max(now - self._last_tick, 1e-6)
        self._bytes, self._last_tick = 0, now
        direction = self._thread.job.direction if self._thread else None
        arrow = "↑" if direction == "upload" else "↓"
        self.speed_changed.emit(f"{arrow} {format_speed(rate)}")

    def _finished(self, thread: _JobThread) -> None:
        self._timer.stop()
        self._thread = None
        job = thread.job
        job.state, job.error = (FAILED, thread.error) if thread.error else (DONE, "")
        thread.deleteLater()
        self.speed_changed.emit("Idle")
        self.changed.emit()
        self.job_finished.emit(job)
        if not thread.error:
            self.beep_requested.emit()
            if self.queue_autoclear:
                self.clear_done_jobs()
        self._start_next()


def format_speed(bytes_per_second: float) -> str:
    value = float(bytes_per_second)
    for unit in ("B/s", "KB/s", "MB/s"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB/s"
