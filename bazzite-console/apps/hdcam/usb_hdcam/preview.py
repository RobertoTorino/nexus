# SPDX-License-Identifier: GPL-3.0-or-later
"""The camera's picture: frames read through V4L2 (v4l2.py) in a thread of its own, turned into pictures by Qt's
YUYV conversion and handed to the window, at most 30 a second. Every mode the camera reports can be chosen, at each
of its rates. A frame the driver could not complete is not shown: when only those come, the mode needs more USB
bandwidth than the camera has, and the preview says so. While the preview runs, the app holds the camera, and other
apps cannot use it: it runs only when asked, and stops when the window closes.

A Look is how the full-screen picture is shown (zoomed in, moved, black and white) and shown() makes a picture so;
PictureView draws the result, whole and centered on black, and passes a drag and the mouse wheel on (owner,
03-11-2026, from the Windows Portable Suite's USB HD Cam, 01-11-2026)."""

from __future__ import annotations

import errno
import threading
import time
from collections.abc import Callable

from PyQt6.QtCore import QObject, QPointF, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtMultimedia import QVideoFrame, QVideoFrameFormat
from PyQt6.QtWidgets import QWidget

from . import v4l2
from .modes import Mode

FIRST_FRAME_S = 5.0                     # no complete frame for this long: the preview stops and says why
READ_TIMEOUT_S = 0.5
SHOWN_PER_S = 30
# Some camera modes may send no usable frame. The preview reports this separately from a damaged frame.
NO_PICTURE = ("The camera sends no picture in this mode. Choose another mode or rate; if none gives a picture, unplug "
              "the camera and plug it in again.")
DAMAGED = ("The frames arrive damaged: this mode may need more USB bandwidth than the system provides. Choose a slower rate "
           "or a smaller mode; with Full bandwidth, try Reduced and plug the camera in again.")
BUSY = "Another app is using the camera. Close it, then start the preview again."
FORMATS = {"YUYV": QVideoFrameFormat.PixelFormat.Format_YUYV}
ZOOMS = (1.0, 1.5, 2.0, 3.0, 4.0)           # Zoom − and Zoom + go through these
PAN_STEP = 0.1                              # an arrow key moves the picture this much of what shows


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
        """Moves the middle by *dx*, *dy* of what shows (an arrow key: PAN_STEP); whether it moved. At 1x there is
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


class PictureView(QWidget):
    """The newest picture, whole and centered on black; a line of text when there is none. The mouse dragged over it
    sends dragged(dx, dy), how far as a part of the picture drawn; the mouse wheel sends wheeled(+1 or -1)."""

    dragged = pyqtSignal(float, float)
    wheeled = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.image: QImage | None = None
        self.text = ""
        self.pressed_at: QPointF | None = None
        self.setMinimumHeight(200)

    def drawn(self) -> QRectF:
        """Where the picture is drawn: whole, as large as fits, centered."""
        if self.image is None or self.image.isNull():
            return QRectF()
        scale = min(self.width() / self.image.width(), self.height() / self.image.height())
        width, height = self.image.width() * scale, self.image.height() * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.pressed_at = event.position()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        area = self.drawn()
        if self.pressed_at is None or area.isEmpty():
            return
        moved = event.position() - self.pressed_at
        self.pressed_at = event.position()
        self.dragged.emit(moved.x() / area.width(), moved.y() / area.height())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.pressed_at = None

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt override)
        turned = event.angleDelta().y()
        if turned:
            self.wheeled.emit(1 if turned > 0 else -1)
        event.accept()

    def show_image(self, image: QImage) -> None:
        self.image, self.text = image, ""
        self.update()

    def clear(self, text: str = "") -> None:
        self.image, self.text = None, text
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("black"))
        if self.image is None:
            painter.setPen(QColor("#bdbdbd"))
            font = painter.font()
            font.setPointSize(14)
            painter.setFont(font)
            painter.drawText(self.rect().adjusted(32, 0, -32, 0),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.text)
            return
        painter.drawImage(self.drawn(), self.image)


def to_image(data: bytes, width: int, height: int, pixel_format: str = "YUYV") -> QImage:
    """A YUYV frame as a picture, through Qt's own conversion."""
    frame = QVideoFrame(QVideoFrameFormat(QSize(width, height), FORMATS[pixel_format]))
    if not frame.map(QVideoFrame.MapMode.WriteOnly):
        return QImage()
    try:
        pointer = frame.bits(0)
        pointer.setsize(frame.mappedBytes(0))
        target = memoryview(pointer)
        row, line = width * 2, frame.bytesPerLine(0)
        if line == row:
            size = min(len(data), len(target))
            target[:size] = data[:size]
        else:                               # Qt pads its rows for alignment (a 5148-wide frame, or a small one)
            for y in range(min(height, len(data) // row)):
                target[y * line:y * line + row] = data[y * row:(y + 1) * row]
    finally:
        frame.unmap()
    return frame.toImage()


def why(exc: OSError) -> str:
    if exc.errno == errno.EBUSY:
        return BUSY
    return f"The preview could not start: {exc.strerror or exc}."


class Preview(QObject):
    frame = pyqtSignal(QImage)
    failed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None, open_camera: Callable[[str], v4l2.Camera] = v4l2.Camera,
                 clock: Callable[[], float] = time.monotonic):
        super().__init__(parent)
        self.open_camera = open_camera
        self.clock = clock
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def modes(self, node: str) -> list[Mode]:
        """The modes the camera reports that this preview can show (YUYV)."""
        try:
            camera = self.open_camera(node)
        except OSError:
            return []
        try:
            return [mode for mode in camera.modes() if mode.pixel_format in FORMATS]
        except OSError:
            return []
        finally:
            camera.close()

    def start(self, node: str, mode: Mode | None) -> bool:
        self.stop()
        if mode is None:
            self.failed.emit("The camera reports no mode the preview can show.")
            return False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(node, mode, self._stop), name="hdcam-preview",
                                        daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        thread, self._thread = self._thread, None
        if thread is not None:
            self._stop.set()
            if thread is not threading.current_thread():
                thread.join(2.0)

    def _run(self, node: str, mode: Mode, stop: threading.Event) -> None:
        """The capture thread: reads frames until stopped, or until no complete frame comes for FIRST_FRAME_S."""
        try:
            camera = self.open_camera(node)
        except OSError as exc:
            self.failed.emit(why(exc))
            return
        try:
            try:
                camera.start(mode)
            except OSError as exc:
                self.failed.emit(why(exc))
                return
            width, height = camera.mode.width, camera.mode.height
            last_good = self.clock()
            last_shown = 0.0
            damaged = 0
            while not stop.is_set():
                try:
                    frame = camera.read(READ_TIMEOUT_S)
                except OSError as exc:
                    self.failed.emit(f"The camera stopped: {exc.strerror or exc}.")
                    return
                now = self.clock()
                if frame is not None and not frame.damaged:
                    last_good, damaged = now, 0
                    if now - last_shown >= 1 / SHOWN_PER_S:
                        last_shown = now
                        image = to_image(frame.data, width, height, mode.pixel_format)
                        if not image.isNull():
                            self.frame.emit(image)
                elif frame is not None:
                    damaged += 1
                if now - last_good >= FIRST_FRAME_S:
                    self.failed.emit(DAMAGED if damaged else NO_PICTURE)
                    return
        finally:
            camera.close()
