# SPDX-License-Identifier: GPL-3.0-or-later
"""The preview's capture thread against a fake camera: complete frames become pictures, a mode that only sends
damaged frames stops with the bandwidth message, no frames at all with its own, and a busy camera says so."""

from __future__ import annotations

import errno
import time

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QImage

from usb_hdcam import preview, v4l2
from usb_hdcam.modes import Mode


def yuyv(width: int, height: int, y: int) -> bytes:
    """A flat gray YUYV frame of luma *y* (no color: U and V at 128)."""
    return bytes([y, 128, y, 128]) * (width * height // 2)


class FakeCamera:
    def __init__(self, frames=(), fail_start=None, modes=()):
        self.frames = list(frames)
        self.fail_start = fail_start
        self.listed = list(modes)
        self.mode = None
        self.closed = False

    def modes(self):
        return self.listed

    def start(self, mode):
        if self.fail_start:
            raise OSError(self.fail_start, "error")
        self.mode = mode

    def read(self, timeout):
        if self.frames:
            return self.frames.pop(0)
        time.sleep(0.01)
        return None

    def close(self):
        self.closed = True


class Clock:
    """Each reading a second later, so the 5 s without a complete frame pass in a few reads."""
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        self.now += 1.0
        return self.now


def run(qapp, camera, mode=Mode(4, 2, 30, "YUYV"), clock=None):
    shown, failed = [], []
    view = preview.Preview(open_camera=lambda node: camera, clock=clock or time.monotonic)
    view.frame.connect(shown.append)
    view.failed.connect(failed.append)
    assert view.start("/dev/video1", mode)
    end = time.monotonic() + 3
    while time.monotonic() < end and (view.running or not (shown or failed)):
        qapp.processEvents()
        if shown and not failed and clock is None:
            break
        time.sleep(0.01)
    qapp.processEvents()
    view.stop()
    qapp.processEvents()
    return view, shown, failed


def test_to_image_converts_yuyv(qapp):
    image = preview.to_image(yuyv(4, 2, 235), 4, 2)
    assert (image.width(), image.height()) == (4, 2) and image.pixelColor(0, 0).lightness() > 240
    dark = preview.to_image(yuyv(4, 2, 16), 4, 2)
    assert dark.pixelColor(3, 1).lightness() < 20


def test_complete_frames_are_shown(qapp):
    camera = FakeCamera([v4l2.Frame(yuyv(4, 2, 128), False)])
    view, shown, failed = run(qapp, camera)
    assert len(shown) == 1 and shown[0].width() == 4 and failed == []
    assert camera.closed and not view.running


def test_only_damaged_frames_stop_with_the_bandwidth_message(qapp):
    camera = FakeCamera([v4l2.Frame(b"\0" * 8, True) for _ in range(20)])
    view, shown, failed = run(qapp, camera, clock=Clock())
    assert shown == [] and failed == [preview.DAMAGED] and camera.closed


def test_no_frames_at_all(qapp):
    view, shown, failed = run(qapp, FakeCamera(), clock=Clock())
    assert shown == [] and failed == [preview.NO_PICTURE]


def test_a_busy_camera(qapp):
    view, shown, failed = run(qapp, FakeCamera(fail_start=errno.EBUSY))
    assert failed == [preview.BUSY]


def test_modes_are_the_yuyv_ones(qapp):
    camera = FakeCamera(modes=[Mode(1920, 1080, 30, "YUYV"), Mode(1920, 1080, 30, "MJPG")])
    view = preview.Preview(open_camera=lambda node: camera)
    assert view.modes("/dev/video1") == [Mode(1920, 1080, 30, "YUYV")] and camera.closed

    def gone(node):
        raise OSError(errno.ENOENT, "gone")
    assert preview.Preview(open_camera=gone).modes("/dev/video1") == []


def test_no_mode(qapp):
    failed = []
    view = preview.Preview(open_camera=lambda node: FakeCamera())
    view.failed.connect(failed.append)
    assert not view.start("/dev/video1", None) and failed and not view.running


def test_the_zoom_steps_and_stops_at_its_ends():
    look = preview.Look()
    assert look.zoom == 1.0 and look.label == "1x" and not look.step_zoom(-1)
    assert look.step_zoom(1) and look.zoom == 1.5 and look.label == "1.5x"
    for _ in range(10):
        look.step_zoom(1)
    assert look.zoom == 4.0 and not look.step_zoom(1)
    look.gray = True
    assert look.label == "4x, black and white"


def test_the_zoomed_part_moves_within_the_picture():
    look = preview.Look()
    assert not look.pan(0.1, 0) and (look.x, look.y) == (0.5, 0.5)       # at 1x nothing moves
    look.step_zoom(1)                                                     # 2x: a third of the width each side
    look.step_zoom(1)
    assert look.pan(1, 0) and look.x == 0.75 and look.y == 0.5             # as far right as it goes
    assert not look.pan(1, 0)
    assert look.area(1920, 1080) == QRect(960, 270, 960, 540)
    look.step_zoom(-1)
    look.step_zoom(-1)
    assert look.area(1920, 1080) == QRect(0, 0, 1920, 1080) and (look.x, look.y) == (0.5, 0.5)


def test_shown_cuts_and_grays(qapp):
    image = QImage(400, 200, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    look = preview.Look()
    assert preview.shown(image, look).size() == image.size()
    look.step_zoom(1)
    cut = preview.shown(image, look)
    assert (cut.width(), cut.height()) == (267, 133) and cut.pixelColor(0, 0) == QColor("red")
    look.gray = True
    gray = preview.shown(image, look)
    assert gray.format() == QImage.Format.Format_Grayscale8 and gray.width() == 267


def test_a_drag_is_a_part_of_the_picture_drawn(qapp):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QMouseEvent
    view = preview.PictureView()
    view.resize(400, 300)
    dragged, wheeled = [], []
    view.dragged.connect(lambda dx, dy: dragged.append((round(dx, 2), round(dy, 2))))
    view.wheeled.connect(wheeled.append)
    image = QImage(200, 100, QImage.Format.Format_RGB32)
    view.show_image(image)
    assert view.drawn() == QRectF(0, 50, 400, 200)                       # whole, as large as fits, centered
    press = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(100, 100), Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    move = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(140, 120), Qt.MouseButton.LeftButton,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    view.mousePressEvent(press)
    view.mouseMoveEvent(move)
    assert dragged == [(0.1, 0.1)]
    view.clear("No picture.")
    assert view.image is None and view.text == "No picture." and view.drawn().isEmpty()
