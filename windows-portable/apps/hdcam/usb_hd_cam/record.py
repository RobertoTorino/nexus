# SPDX-License-Identifier: GPL-3.0-or-later
"""Screenshots and recordings of the full-screen picture, as it shows (zoomed in, moved, black and white): a
screenshot is a PNG in the user's Pictures folder, a recording an MP4 (H.264) in the Videos folder, each in a folder
named after the app, with the date and the time in the file's name.

A recording is made from the pictures the window draws (preview.Preview: at most 30 a second), handed to Qt
Multimedia through a QVideoFrameInput, so it is what the screen shows, at the mode's size; Qt's FFmpeg backend writes
it with Windows' own H.264 encoder (Media Foundation). PyQt6 6.12 cannot connect QMediaRecorder's signals that carry
one of its enums (recorderStateChanged, errorOccurred), so the end of a recording is read with a timer and an error
through errorChanged."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QObject, QSize, QStandardPaths, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QImage

from . import APP_NAME

VIDEO_FPS = 30                              # preview.FRAME_GAP_S: the most pictures a second the window draws
STOP_POLL_MS = 100                          # how often a stopping recording is asked whether its file is written
CLOSE_WAIT_S = 5.0                          # the app closing waits this long for the file


def pictures() -> Path:
    """The user's Pictures folder (Windows' own, wherever it was moved to), the app's folder in it."""
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)) / APP_NAME


def videos() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation)) / APP_NAME


def new_path(folder: Path, suffix: str, now: datetime | None = None) -> Path:
    """A file in *folder* named after the app and the time ("USB HD Cam 2026-11-01 21-04-09.png"), not one there
    already: two in one second get (2), (3) and so on."""
    stem = f"{APP_NAME} {(now or datetime.now()):%Y-%m-%d %H-%M-%S}"
    path, n = folder / f"{stem}{suffix}", 1
    while path.exists():
        n += 1
        path = folder / f"{stem} ({n}){suffix}"
    return path


def save_picture(image: QImage, path: Path) -> Path:
    """*image* as a PNG at *path*, its folder made first; raises OSError with what went wrong."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(path), "PNG"):
        raise OSError(f"The screenshot could not be written to {path.parent.name}.")
    return path


class Recording(QObject):
    """A video made of the pictures add() gets, at one size: finished(path) once its file is written, failed(text)
    when Windows stops it."""

    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, clock: Callable[[], float] = time.monotonic, parent: QObject | None = None):
        super().__init__(parent)
        self.clock = clock
        self.session = self.input = self.recorder = None
        self.path: Path | None = None
        self.size = QSize()
        self.began = 0.0
        self.stopping = False
        self.poll = QTimer(self)
        self.poll.setInterval(STOP_POLL_MS)
        self.poll.timeout.connect(self._check)

    @property
    def running(self) -> bool:
        return self.recorder is not None and not self.stopping

    @property
    def busy(self) -> bool:
        """Recording, or still writing the file."""
        return self.recorder is not None

    def seconds(self) -> int:
        return int(self.clock() - self.began) if self.running else 0

    def start(self, path: Path, width: int, height: int) -> str:
        """Records to *path* (an .mp4) at *width* x *height*; "" when it started, else why not."""
        from PyQt6.QtMultimedia import QMediaCaptureSession, QMediaFormat, QMediaRecorder, QVideoFrameInput
        if self.busy:
            return "The recording before is still being written."
        media = QMediaFormat(QMediaFormat.FileFormat.MPEG4)
        if QMediaFormat.VideoCodec.H264 not in media.supportedVideoCodecs(QMediaFormat.ConversionMode.Encode):
            return "Windows has no H.264 video encoder here, so nothing can be recorded."
        media.setVideoCodec(QMediaFormat.VideoCodec.H264)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            return f"The Videos folder could not be made: {error.strerror or error}."
        self.input = QVideoFrameInput()
        self.recorder = QMediaRecorder()
        self.session = QMediaCaptureSession()
        self.session.setVideoFrameInput(self.input)
        self.session.setRecorder(self.recorder)
        self.recorder.setMediaFormat(media)
        self.recorder.setVideoResolution(QSize(width, height))
        self.recorder.setVideoFrameRate(VIDEO_FPS)
        self.recorder.setQuality(QMediaRecorder.Quality.VeryHighQuality)
        self.recorder.setOutputLocation(QUrl.fromLocalFile(str(path)))
        self.recorder.errorChanged.connect(self._error)
        self.path, self.size, self.stopping = path, QSize(width, height), False
        self.began = self.clock()
        self.recorder.record()
        return ""

    def add(self, image: QImage) -> None:
        """The next picture, at the recording's size (a zoomed one is scaled up to it), with the time it came."""
        from PyQt6.QtMultimedia import QVideoFrame
        if not self.running or image.isNull():
            return
        if image.size() != self.size:
            image = image.scaled(self.size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        frame = QVideoFrame(image.convertToFormat(QImage.Format.Format_RGB32))     # one format, gray or not
        at = int((self.clock() - self.began) * 1_000_000)
        frame.setStartTime(at)
        frame.setEndTime(at + 1_000_000 // VIDEO_FPS)
        self.input.sendVideoFrame(frame)            # False while the encoder is behind: that picture is left out

    def stop(self, wait_s: float = 0.0) -> None:
        """Ends the recording; finished(path) follows once the file is written, within *wait_s* when given (the app
        closing)."""
        if self.recorder is None:
            return
        if not self.stopping:
            self.stopping = True
            self.recorder.stop()
            self.poll.start()
        end = time.monotonic() + wait_s
        while self.recorder is not None and time.monotonic() < end:
            QCoreApplication.processEvents()
            self._check()
            time.sleep(0.02)

    def _check(self) -> None:
        from PyQt6.QtMultimedia import QMediaRecorder
        if self.recorder is None or self.recorder.recorderState() != QMediaRecorder.RecorderState.StoppedState:
            return
        path = self.path
        self._clear()
        self.finished.emit(str(path))

    def _error(self) -> None:
        from PyQt6.QtMultimedia import QMediaRecorder
        if self.recorder is None or self.recorder.error() == QMediaRecorder.Error.NoError:
            return
        text = self.recorder.errorString() or "Windows stopped it"
        self.recorder.stop()
        self._clear()
        self.failed.emit(f"The recording stopped: {text.rstrip('.')}.")

    def _clear(self) -> None:
        self.poll.stop()
        self.session = self.input = self.recorder = None
        self.path, self.stopping = None, False
