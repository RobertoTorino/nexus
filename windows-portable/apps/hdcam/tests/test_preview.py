# SPDX-License-Identifier: GPL-3.0-or-later
"""How the full-screen picture is shown (preview.Look and shown()): the zoom steps through ZOOMS, the zoomed part is
moved but never past the picture's edge, and a frame is cut to the part that shows, at the camera's pixels, gray in
black and white; PictureView passes a drag on as a part of the picture drawn."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QImage, QMouseEvent

from usb_hd_cam import preview
from usb_hd_cam.preview import Look


def test_the_zoom_steps_and_stops_at_its_ends():
    look = Look()
    assert not look.step_zoom(-1) and look.zoom == 1.0
    assert look.step_zoom(1) and look.zoom == 1.5
    for _ in range(10):
        look.step_zoom(1)
    assert look.zoom == preview.ZOOMS[-1] and not look.step_zoom(1)


def test_the_zoomed_part_moves_within_the_picture():
    look = Look()
    assert not look.pan(preview.PAN_STEP, 0)           # at 1x the whole picture shows
    look.step_zoom(1)
    look.step_zoom(1)                                  # 2x: the middle from 0.25 to 0.75
    assert look.pan(preview.PAN_STEP, 0) and look.x == 0.55
    for _ in range(10):
        look.pan(0, -preview.PAN_STEP)
    assert look.y == 0.25 and not look.pan(0, -preview.PAN_STEP)
    look.x = 0.75
    look.step_zoom(-1)                                 # zoomed out at the edge: pulled back inside
    assert look.zoom == 1.5 and round(look.x, 4) == round(1 - 0.5 / 1.5, 4)


def test_the_area_that_shows():
    look = Look()
    assert look.area(1920, 1080).getRect() == (0, 0, 1920, 1080)
    look.step_zoom(1)
    look.step_zoom(1)
    assert look.area(1920, 1080).getRect() == (480, 270, 960, 540)
    look.pan(1, 1)                                     # as far as it goes: the bottom right quarter
    assert look.area(1920, 1080).getRect() == (960, 540, 960, 540)


def test_shown_cuts_and_grays():
    image = QImage(400, 200, QImage.Format.Format_RGB32)
    image.fill(0xFFCC3366)
    look = Look()
    assert preview.shown(image, look) is image         # nothing to do: the same picture
    look.step_zoom(1)
    look.step_zoom(1)
    look.gray = True
    out = preview.shown(image, look)
    assert (out.width(), out.height()) == (200, 100) and out.format() == QImage.Format.Format_Grayscale8
    assert look.label == "2x, black and white"


def test_a_drag_is_a_part_of_the_picture_drawn(qapp):
    view = preview.PictureView()
    view.resize(800, 400)
    image = QImage(400, 100, QImage.Format.Format_RGB32)
    view.show_image(image)                             # drawn 800 x 200, centered
    assert view.drawn().getRect() == (0.0, 100.0, 800.0, 200.0)
    dragged = []
    view.dragged.connect(lambda dx, dy: dragged.append((dx, dy)))

    def mouse(kind, x, y):
        return QMouseEvent(kind, QPointF(x, y), QPointF(view.mapToGlobal(QPoint(x, y))), Qt.MouseButton.LeftButton,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    view.mousePressEvent(mouse(QMouseEvent.Type.MouseButtonPress, 400, 200))
    view.mouseMoveEvent(mouse(QMouseEvent.Type.MouseMove, 600, 250))
    view.mouseReleaseEvent(mouse(QMouseEvent.Type.MouseButtonRelease, 600, 250))
    view.mouseMoveEvent(mouse(QMouseEvent.Type.MouseMove, 700, 250))      # released: nothing
    assert dragged == [(0.25, 0.25)]
