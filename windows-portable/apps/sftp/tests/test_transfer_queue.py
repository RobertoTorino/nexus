# SPDX-License-Identifier: GPL-3.0-or-later
"""The transfer queue (transfer_queue.py): one job at a time in the order asked for, its bytes counted so it shows
how far it is, a failed one tried again, the done and failed ones cleared, and nothing moving without a
connection."""

from __future__ import annotations

import time

import pytest

from fake_sftp import FakeSFTP
from sftp_tools.transfer_queue import DONE, FAILED, QUEUED, TransferJob, TransferQueue, speed_text


def wait(qapp, until, seconds: float = 10) -> None:
    end = time.monotonic() + seconds
    while not until() and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)
    assert until()


@pytest.fixture
def queue(qapp, tmp_path):
    queue = TransferQueue()
    queue.set_sftp(FakeSFTP(tmp_path / "server"))
    yield queue
    queue.shutdown()


def test_jobs_run_one_after_the_other(qapp, queue, tmp_path):
    (tmp_path / "a.bin").write_bytes(b"a" * 300)
    folder = tmp_path / "saves"
    folder.mkdir()
    (folder / "one").write_bytes(b"1" * 100)
    finished = []
    queue.finished.connect(finished.append)
    first = TransferJob("upload", str(tmp_path / "a.bin"), "/var/home/me/a.bin", False)
    second = TransferJob("upload", str(folder), "/var/home/me/saves", True)
    queue.enqueue(first)
    queue.enqueue(second)
    assert second.state == QUEUED                               # it waits its turn
    wait(qapp, lambda: len(finished) == 2)
    assert finished == [first, second] and first.state == second.state == DONE
    assert (first.done, first.total, first.percent, first.files) == (300, 300, 100, 1)
    assert (second.files, second.total, second.name, second.arrow) == (1, 100, "saves", "↑")
    down = TransferJob("download", "/var/home/me/a.bin", str(tmp_path / "back.bin"), False)
    queue.enqueue(down)
    wait(qapp, lambda: down.state == DONE)
    assert (tmp_path / "back.bin").read_bytes() == b"a" * 300 and down.arrow == "↓"
    assert queue.clear_finished() == 3 and queue.jobs == []


def test_a_failed_job_is_tried_again(qapp, queue, tmp_path):
    job = TransferJob("upload", str(tmp_path / "later.txt"), "/var/home/me/later.txt", False)
    queue.enqueue(job)
    wait(qapp, lambda: job.state == FAILED)
    assert job.error
    (tmp_path / "later.txt").write_text("now it is there")
    assert queue.retry(job)
    wait(qapp, lambda: job.state == DONE)
    assert not queue.retry(job)                                 # only a failed one


def test_nothing_moves_without_a_connection(qapp, tmp_path):
    queue = TransferQueue()
    job = TransferJob("upload", str(tmp_path), "/x", True)
    queue.enqueue(job)
    assert (job.state, job.error) == (FAILED, "Not connected")
    waiting = TransferJob("upload", str(tmp_path), "/y", True)
    queue.jobs.append(waiting)
    assert queue.cancel_all() == 1 and waiting.error == "Canceled"


def test_the_speed_reads_for_a_person():
    assert [speed_text(n) for n in (500, 2048, 5 * 1024 ** 2, 3 * 1024 ** 3)] == [
        "500.0 B/s", "2.0 KB/s", "5.0 MB/s", "3.0 GB/s"]
