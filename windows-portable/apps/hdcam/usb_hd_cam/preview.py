# SPDX-License-Identifier: GPL-3.0-or-later
"""The camera's picture in the window, through Qt Multimedia (QCamera into a QVideoSink; PyQt6 brings it): Preview
starts the camera in a mode and hands over its frames as pictures, at most 30 a second however fast the mode is, and
says when the camera sends nothing. PictureView draws the newest one, whole and centered. While the preview runs,
other apps can show the camera too."""

from __future__ import annotations

import time
from collections.abc import Callable

from PyQt6.QtCore import QObject, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QWidget

from bc250_core.portable import DIM, font, px

from .modes import Mode

DEVICE_ID = "vid_05a9&pid_058c"             # in the webcam's Windows device path
FRAME_GAP_S = 1 / 30                        # the most pictures a second the window draws
SILENT_MS = 4000                            # no frame by then: the camera sends nothing in this mode


def camera_modes() -> list[Mode]:
    """The modes the webcam reports, as Qt reads them; none when it is not there."""
    device = _device()
    if device is None:
        return []
    return [Mode(f.resolution().width(), f.resolution().height(), round(f.maxFrameRate()))
            for f in device.videoFormats()]


def _device():
    from PyQt6.QtMultimedia import QMediaDevices
    return next((device for device in QMediaDevices.videoInputs()
                 if DEVICE_ID in bytes(device.id()).decode(errors="replace").lower()), None)


class Preview(QObject):
    """The camera, started in a mode: picture(QImage) for each frame drawn, failed(str) when it stops on its own."""

    picture = pyqtSignal(QImage)
    failed = pyqtSignal(str)

    def __init__(self, clock: Callable[[], float] = time.monotonic, parent: QObject | None = None):
        super().__init__(parent)
        self.clock = clock
        self.camera = self.session = self.sink = None
        self.frames = 0
        self.last = 0.0
        self.silence = QTimer(self)
        self.silence.setSingleShot(True)
        self.silence.setInterval(SILENT_MS)
        self.silence.timeout.connect(self._silent)

    @property
    def running(self) -> bool:
        return self.camera is not None

    def start(self, mode: Mode) -> str:
        """Starts the camera in *mode*; "" when it started, else why not."""
        from PyQt6.QtMultimedia import QCamera, QMediaCaptureSession, QVideoSink
        self.stop()
        device = _device()
        if device is None:
            return "Windows does not list the webcam: look for the camera again on the Camera card."
        found = next((f for f in device.videoFormats() if f.resolution().width() == mode.width
                      and f.resolution().height() == mode.height and round(f.maxFrameRate()) == mode.fps), None)
        if found is None:
            return f"The camera does not offer {mode.label}."
        self.camera = QCamera(device)
        self.camera.setCameraFormat(found)
        self.sink = QVideoSink()
        self.session = QMediaCaptureSession()
        self.session.setCamera(self.camera)
        self.session.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self._frame)
        self.camera.errorOccurred.connect(self._error)
        self.frames, self.last = 0, 0.0
        self.camera.start()
        self.silence.start()
        return ""

    def stop(self) -> None:
        self.silence.stop()
        if self.camera is not None:
            self.camera.stop()
            self.sink.videoFrameChanged.disconnect(self._frame)
        self.camera = self.session = self.sink = None

    def _frame(self, frame) -> None:
        self.frames += 1
        now = self.clock()
        if now - self.last < FRAME_GAP_S:
            return
        self.last = now
        image = frame.toImage()
        if not image.isNull():
            self.picture.emit(image)

    def _silent(self) -> None:
        if self.running and self.frames == 0:
            self.stop()
            self.failed.emit("The camera sends nothing in this mode: choose another with LB or RB.")

    def _error(self, _error, text: str) -> None:
        self.stop()
        self.failed.emit(f"The camera stopped: {text or 'it is gone'}.")


class PictureView(QWidget):
    """The newest picture, whole and centered on black; a line of text when there is none."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.image: QImage | None = None
        self.text = ""
        self.setMinimumHeight(px(200))

    def show_image(self, image: QImage) -> None:
        self.image = image
        self.update()

    def clear(self, text: str = "") -> None:
        self.image, self.text = None, text
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("black"))
        if self.image is None:
            painter.setPen(QColor(DIM))
            painter.setFont(font(15))
            painter.drawText(self.rect().adjusted(px(16), 0, -px(16), 0),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.text)
            return
        scale = min(self.width() / self.image.width(), self.height() / self.image.height())
        width, height = self.image.width() * scale, self.image.height() * scale
        painter.drawImage(QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height), self.image)
