# SPDX-License-Identifier: GPL-3.0-or-later
"""The camera's picture in the window, through Qt Multimedia (QCamera into a QVideoSink; PyQt6 brings it): Preview
starts the camera in a mode and hands over its frames as pictures, at most 30 a second however fast the mode is, and
says when the camera sends nothing. A Look is how the picture is shown (zoomed in, moved, black and white) and
shown() makes a frame so; PictureView draws the result, whole and centered, and passes a finger's drag and the mouse
wheel on. While the preview runs, other apps can show the camera too, as the camera sends it."""

from __future__ import annotations

import time
from collections.abc import Callable

from PyQt6.QtCore import QObject, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QWidget

from bc250_core.portable import DIM, font, px

from .modes import Mode

DEVICE_ID = "vid_05a9&pid_058c"             # in the webcam's Windows device path
FRAME_GAP_S = 1 / 30                        # the most pictures a second the window draws
SILENT_MS = 4000                            # no frame by then: the camera sends nothing in this mode
ZOOMS = (1.0, 1.5, 2.0, 3.0, 4.0)           # LT and RT go through these
PAN_STEP = 0.1                              # a d-pad press moves the picture this much of what shows


class Look:
    """How the picture is shown: *zoom* (ZOOMS), the middle of what shows (*x*, *y*: 0 to 1 of the picture's width
    and height, kept so that the zoomed part stays inside the picture) and *gray* (black and white)."""

    def __init__(self, gray: bool = False):
        self.zoom, self.x, self.y, self.gray = 1.0, 0.5, 0.5, gray

    def step_zoom(self, delta: int) -> bool:
        """The next zoom in (+1) or out (-1); whether it changed (not past the first or the last)."""
        at = ZOOMS.index(self.zoom) if self.zoom in ZOOMS else 0
        picked = ZOOMS[max(0, min(len(ZOOMS) - 1, at + delta))]
        changed, self.zoom = picked != self.zoom, picked
        self._keep_inside()
        return changed

    def pan(self, dx: float, dy: float) -> bool:
        """Moves the middle by *dx*, *dy* of what shows (a d-pad press: PAN_STEP); whether it moved. At 1x there is
        nothing to move."""
        before = (self.x, self.y)
        self.x += dx / self.zoom
        self.y += dy / self.zoom
        self._keep_inside()
        return (self.x, self.y) != before

    def _keep_inside(self) -> None:
        half = 0.5 / self.zoom
        self.x = min(max(self.x, half), 1 - half)
        self.y = min(max(self.y, half), 1 - half)

    def area(self, width: int, height: int) -> QRect:
        """The part of a *width* x *height* picture that shows, in its pixels."""
        w, h = max(1, round(width / self.zoom)), max(1, round(height / self.zoom))
        left = min(max(0, round(self.x * width - w / 2)), width - w)
        top = min(max(0, round(self.y * height - h / 2)), height - h)
        return QRect(left, top, w, h)

    @property
    def label(self) -> str:
        zoom = f"{self.zoom:g}x"
        return f"{zoom}, black and white" if self.gray else zoom


def shown(image: QImage, look: Look) -> QImage:
    """*image* as *look* shows it: the zoomed part only, at the camera's own pixels, gray when it is black and white."""
    if look.zoom != 1.0:
        image = image.copy(look.area(image.width(), image.height()))
    if look.gray:
        image = image.convertToFormat(QImage.Format.Format_Grayscale8)
    return image


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
    """The newest picture, whole and centered on black; a line of text when there is none. A finger (or the mouse)
    dragged over it sends dragged(dx, dy), how far as a part of the picture drawn; the mouse wheel sends wheeled(+1
    or -1)."""

    dragged = pyqtSignal(float, float)
    wheeled = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.image: QImage | None = None
        self.text = ""
        self.pressed_at: QPointF | None = None
        self.setMinimumHeight(px(200))

    def drawn(self) -> QRectF:
        """Where the picture is drawn: whole, as large as fits, centered."""
        if self.image is None or self.image.isNull():
            return QRectF()
        scale = min(self.width() / self.image.width(), self.height() / self.image.height())
        width, height = self.image.width() * scale, self.image.height() * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def mousePressEvent(self, event) -> None:
        self.pressed_at = event.position()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        area = self.drawn()
        if self.pressed_at is None or area.isEmpty():
            return
        moved = event.position() - self.pressed_at
        self.pressed_at = event.position()
        self.dragged.emit(moved.x() / area.width(), moved.y() / area.height())

    def mouseReleaseEvent(self, event) -> None:
        self.pressed_at = None

    def wheelEvent(self, event) -> None:
        turned = event.angleDelta().y()
        if turned:
            self.wheeled.emit(1 if turned > 0 else -1)
        event.accept()

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
        painter.drawImage(self.drawn(), self.image)
