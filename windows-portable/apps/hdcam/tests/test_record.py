# SPDX-License-Identifier: GPL-3.0-or-later
"""Screenshots and recordings (record.py): the files' names, a screenshot as a PNG, and a real recording through Qt
Multimedia and Windows' H.264 encoder, of pictures of two sizes, read back with its size, codec and length."""

from __future__ import annotations

import sys
import time
from datetime import datetime

import pytest
from PyQt6.QtGui import QImage

from usb_hd_cam import APP_NAME, record

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


def _h264() -> bool:
    from PyQt6.QtMultimedia import QMediaFormat
    return QMediaFormat.VideoCodec.H264 in QMediaFormat(QMediaFormat.FileFormat.MPEG4).supportedVideoCodecs(
        QMediaFormat.ConversionMode.Encode)


@pytest.mark.skipif(sys.platform != "win32", reason="the recording is Windows' own H.264 encoder")
def test_a_recording_is_written_and_reads_back(qapp, tmp_path):
    from PyQt6.QtCore import QUrl
    from PyQt6.QtMultimedia import QMediaPlayer
    if not _h264():
        pytest.skip("this Windows has no H.264 encoder (Media Foundation)")
    recording = record.Recording()
    done, failed = [], []
    recording.finished.connect(done.append)
    recording.failed.connect(failed.append)
    path = tmp_path / "Videos" / "clip.mp4"
    assert recording.start(path, 320, 180) == "" and recording.running
    assert recording.start(path, 320, 180) == "The recording before is still being written."
    gray = QImage(160, 90, QImage.Format.Format_Grayscale8)        # a zoomed part, black and white: scaled up
    color = QImage(320, 180, QImage.Format.Format_RGB32)
    end = time.monotonic() + 1.5
    n = 0
    while time.monotonic() < end:
        n += 1
        gray.fill(n % 256)
        color.fill(0xFF000000 | (n * 4 % 256) << 16)
        recording.add(gray if n % 2 else color)
        qapp.processEvents()
        time.sleep(1 / record.VIDEO_FPS)
    recording.stop(wait_s=record.CLOSE_WAIT_S)
    assert failed == [] and done == [str(path)] and not recording.busy
    assert path.stat().st_size > 1000

    player = QMediaPlayer()
    player.setSource(QUrl.fromLocalFile(str(path)))
    end = time.monotonic() + 5
    while player.mediaStatus() != QMediaPlayer.MediaStatus.LoadedMedia and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.02)
    meta = player.metaData()
    assert meta.value(meta.Key.Resolution).width() == 320 and meta.value(meta.Key.Resolution).height() == 180
    assert "264" in meta.stringValue(meta.Key.VideoCodec)
    assert 1000 <= player.duration() <= 2500
