# SPDX-License-Identifier: GPL-3.0-or-later
"""The transfer queue, as the BC250 suite's SFTP Tools runs it (transfer_queue.py there): one transfer at a time, in
the order asked for, each on a thread of its own with the queue's own SFTP channel, so the server's folders can be
listed meanwhile. A job first counts its bytes, so the Transfers card can show how far it is; the speed limit holds
the transfer back to the KB/s set."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Literal

import paramiko
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from .transfers import download_tree, get_file, local_size, put_file, remote_size, upload_tree

Direction = Literal["upload", "download"]
QUEUED, RUNNING, FAILED, DONE = "queued", "running", "failed", "done"
CANCELED = "Canceled"
TICK_MS = 1000                  # the speed, and the progress shown


@dataclass
class TransferJob:
    direction: Direction
    source: str
    destination: str
    is_dir: bool
    skip_existing: bool = False
    preserve_times: bool = True
    limit_kbps: int = 0
    state: str = QUEUED
    error: str = ""                     # why it failed, as its row shows it
    reason: str = ""                    # the same without a path or a name in it: the log's
    done: int = 0                       # bytes moved so far
    total: int = 0                      # bytes in all, once counted
    files: int = 0                      # files moved (a skipped one does not count)

    @property
    def name(self) -> str:
        source = self.source.rstrip("/\\") or self.source
        return os.path.basename(source.replace("\\", "/")) or source

    @property
    def arrow(self) -> str:
        return "↑" if self.direction == "upload" else "↓"

    @property
    def percent(self) -> int | None:
        if self.total <= 0:
            return None
        return min(100, self.done * 100 // self.total)


class _JobThread(QThread):
    def __init__(self, sftp: paramiko.SFTPClient, job: TransferJob) -> None:
        super().__init__()
        self.sftp = sftp
        self.job = job
        self.cancelled = False
        self.error = ""
        self.reason = ""
        self._started = 0.0

    def _progress(self, delta: int) -> None:
        if self.cancelled:
            raise InterruptedError(CANCELED)
        self.job.done += delta
        limit = self.job.limit_kbps * 1024
        if limit > 0:
            due = self._started + self.job.done / limit
            while (wait := due - time.monotonic()) > 0:
                if self.cancelled:
                    raise InterruptedError(CANCELED)
                time.sleep(min(wait, 0.1))

    def run(self) -> None:
        job = self.job
        try:
            if job.direction == "upload":
                job.total = local_size(job.source)
                self._started = time.monotonic()
                if job.is_dir:
                    job.files = upload_tree(self.sftp, job.source, job.destination, self._progress, job.skip_existing)
                else:
                    job.files = int(put_file(self.sftp, job.source, job.destination, self._progress,
                                             job.skip_existing))
            else:
                job.total = remote_size(self.sftp, job.source)
                self._started = time.monotonic()
                if job.is_dir:
                    job.files = download_tree(self.sftp, job.source, job.destination, self._progress,
                                              job.skip_existing, job.preserve_times)
                else:
                    job.files = int(get_file(self.sftp, job.source, job.destination, self._progress,
                                             job.skip_existing, job.preserve_times))
        except InterruptedError:
            self.error = self.reason = CANCELED
        except Exception as error:  # noqa: BLE001  (the job's row says why)
            self.error = str(error) or type(error).__name__
            self.reason = getattr(error, "strerror", None) or type(error).__name__


class TransferQueue(QObject):
    """changed() whenever a job's state or progress changes (every second while one runs), finished(job) when one
    ends, done or failed."""

    changed = pyqtSignal()
    finished = pyqtSignal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.jobs: list[TransferJob] = []
        self._sftp: paramiko.SFTPClient | None = None
        self._thread: _JobThread | None = None
        self.speed = 0.0                                # bytes/s of the running job, the last second
        self._last_bytes = 0
        self._last_tick = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)

    @property
    def busy(self) -> bool:
        return self._thread is not None

    @property
    def running(self) -> TransferJob | None:
        return self._thread.job if self._thread is not None else None

    def jobs_in(self, *states: str) -> list[TransferJob]:
        return [job for job in self.jobs if job.state in states]

    def set_sftp(self, sftp: paramiko.SFTPClient | None) -> None:
        self._sftp = sftp

    def enqueue(self, job: TransferJob) -> None:
        self.jobs.append(job)
        self.changed.emit()
        self._start_next()

    def retry(self, job: TransferJob) -> bool:
        """A failed job queued again from the start; False for one that did not fail."""
        if job.state != FAILED or job not in self.jobs:
            return False
        job.state, job.error, job.reason, job.done, job.total, job.files = QUEUED, "", "", 0, 0, 0
        self.jobs.remove(job)
        self.jobs.append(job)
        self.changed.emit()
        self._start_next()
        return True

    def cancel_all(self, reason: str = CANCELED) -> int:
        """The waiting jobs failed with *reason*, the running one stopped at its next block; how many there were."""
        waiting = self.jobs_in(QUEUED)
        for job in waiting:
            job.state, job.error, job.reason = FAILED, reason, reason
        stopped = int(self._thread is not None)
        if self._thread is not None:
            self._thread.cancelled = True
        self.changed.emit()
        return len(waiting) + stopped

    def abort_all(self, reason: str = "Disconnected") -> None:
        self._sftp = None
        self.cancel_all(reason)

    def shutdown(self, timeout_ms: int = 5000) -> None:
        """Everything canceled, and the running transfer waited for."""
        thread = self._thread
        self.abort_all("The app closed")
        if thread is not None:
            thread.wait(timeout_ms)

    def clear_finished(self) -> int:
        """The done and the failed jobs taken off the list; how many."""
        before = len(self.jobs)
        self.jobs = self.jobs_in(QUEUED, RUNNING)
        self.changed.emit()
        return before - len(self.jobs)

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
        thread = _JobThread(self._sftp, job)
        thread.finished.connect(lambda: self._finished(thread))
        self._thread = thread
        self.speed, self._last_bytes, self._last_tick = 0.0, 0, time.monotonic()
        self._timer.start()
        self.changed.emit()
        thread.start()

    def _tick(self) -> None:
        job = self.running
        if job is None:
            return
        now = time.monotonic()
        self.speed = max(0, job.done - self._last_bytes) / max(now - self._last_tick, 1e-6)
        self._last_bytes, self._last_tick = job.done, now
        self.changed.emit()

    def _finished(self, thread: _JobThread) -> None:
        self._timer.stop()
        self._thread = None
        self.speed = 0.0
        job = thread.job
        if thread.error:
            job.state, job.error, job.reason = FAILED, thread.error, thread.reason
        else:
            job.state, job.error = DONE, ""
        thread.deleteLater()
        self.changed.emit()
        self.finished.emit(job)
        self._start_next()


def speed_text(bytes_per_second: float) -> str:
    value = float(bytes_per_second)
    for unit in ("B/s", "KB/s", "MB/s"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB/s"
