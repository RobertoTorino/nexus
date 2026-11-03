# SPDX-License-Identifier: GPL-3.0-or-later
"""Screenshots and recordings (record.py; owner, 03-11-2026): the files' names, a screenshot as a PNG, and a real
recording through Qt Multimedia's encoder, of pictures of two sizes, read back with its size and length."""

from __future__ import annotations

import time
from datetime import datetime

import pytest
from PyQt6.QtGui import QImage

from usb_hdcam import APP_NAME, record

NOW = datetime(2026, 11, 1, 21, 4, 9)


def test_a_new_file_is_named_after_the_app_and_the_time(tmp_path):
    first = record.new_path(tmp_path, ".png", NOW)
    assert first == tmp_path / f"{APP_NAME} 2026-11-01 21-04-09.png"
    first.write_bytes(b"")
    assert record.new_path(tmp_path, ".png", NOW).name == f"{APP_NAME} 2026-11-01 21-04-09 (2).png"


def test_the_folders_are_the_users_pictures_and_videos():
    assert record.pictures().name == APP_NAME and record.pictures().parent.name
    assert record.videos().name == APP_NAME and record.videos() != record.pictures()


def test_a_screenshot_is_a_png_in_a_new_folder(qapp, tmp_path):
    image = QImage(32, 16, QImage.Format.Format_Grayscale8)
    image.fill(128)
    path = record.save_picture(image, tmp_path / "Pictures" / APP_NAME / "shot.png")
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and QImage(str(path)).width() == 32


def test_a_screenshot_that_cannot_be_written_says_so(qapp, tmp_path):
    (tmp_path / "taken").write_text("a file, not a folder")
    with pytest.raises(OSError):
        record.save_picture(QImage(4, 4, QImage.Format.Format_RGB32), tmp_path / "taken" / "shot.png")


def test_a_recording_is_written_and_reads_back(qapp, tmp_path):
    from PyQt6.QtCore import QUrl
    from PyQt6.QtMultimedia import QMediaPlayer
    if record.video_codec() is None:
        pytest.skip("this Qt has no video encoder")
    recording = record.Recording()
    done, failed = [], []
    recording.finished.connect(done.append)
    recording.failed.connect(failed.append)
    path = tmp_path / "Videos" / "clip.mp4"
    assert recording.start(path, 320, 240) == "" and recording.running and recording.seconds() == 0
    assert recording.start(path, 320, 240) == "The recording before is still being written."
    big, small = QImage(320, 240, QImage.Format.Format_RGB32), QImage(160, 120, QImage.Format.Format_Grayscale8)
    big.fill(0xFF2040C0)
    small.fill(200)
    end = time.monotonic() + 1.0
    while time.monotonic() < end:                                           # a second of pictures, both sizes
        recording.add(big)
        recording.add(small)
        qapp.processEvents()
        time.sleep(1 / 30)
    recording.stop(wait_s=10.0)
    assert done == [str(path)] and not failed and not recording.busy
    assert path.stat().st_size > 1000

    player = QMediaPlayer()
    player.setSource(QUrl.fromLocalFile(str(path)))
    end = time.monotonic() + 10.0
    while player.mediaStatus() not in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.InvalidMedia) \
            and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.02)
    assert player.mediaStatus() == QMediaPlayer.MediaStatus.LoadedMedia, player.errorString()
    assert player.hasVideo() and 500 <= player.duration() <= 3000
    player.setSource(QUrl())
