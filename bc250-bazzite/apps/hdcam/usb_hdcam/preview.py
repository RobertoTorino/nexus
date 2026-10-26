# SPDX-License-Identifier: GPL-3.0-or-later
"""The camera's picture: frames read through V4L2 (v4l2.py) in a thread of its own, turned into pictures by Qt's
YUYV conversion and handed to the window, at most 30 a second. Every mode the camera reports can be chosen, at each
of its rates. A frame the driver could not complete is not shown: when only those come, the mode needs more USB
bandwidth than the camera has, and the preview says so. While the preview runs, the app holds the camera, and other
apps cannot use it: it runs only when asked, and stops when the window closes."""

from __future__ import annotations

import errno
import threading
import time
from collections.abc import Callable

from PyQt6.QtCore import QObject, QSize, pyqtSignal
from PyQt6.QtGui import QImage
from PyQt6.QtMultimedia import QVideoFrame, QVideoFrameFormat

from . import v4l2
from .modes import Mode

FIRST_FRAME_S = 5.0                     # no complete frame for this long: the preview stops and says why
READ_TIMEOUT_S = 0.5
SHOWN_PER_S = 30
# The camera sends nothing at all in some modes, damaged or not: on the owner's board every 1080-line mode at 15 fps
# (1920x1080, 3840x1080, 5148x1088; 23-10-2026), while the same sizes work at 30 or 8 fps.
NO_PICTURE = ("The camera sends no picture in this mode. Choose another mode or rate; if none gives a picture, unplug "
              "the camera and plug it in again.")
DAMAGED = ("The frames arrive damaged: this mode needs more USB bandwidth than the camera has. Choose a slower rate "
           "or a smaller mode; with Full bandwidth, try Reduced and plug the camera in again.")
BUSY = "Another app is using the camera. Close it, then start the preview again."
FORMATS = {"YUYV": QVideoFrameFormat.PixelFormat.Format_YUYV}


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
        """The modes the camera reports that the preview can show (YUYV, the PS5 HD Camera's only format)."""
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
