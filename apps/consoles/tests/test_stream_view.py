# SPDX-License-Identifier: AGPL-3.0-or-later
"""stream_view.py: the shader's colors, the plane layout and the orientation, drawn into an offscreen framebuffer
and read back (skipped where no OpenGL context opens, as on CI's runners without a GPU); the letterbox; the
window's handling of pictures, full screen and closing; the pointer hiding over the picture."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QOffscreenSurface, QOpenGLContext
from PyQt6.QtOpenGL import QOpenGLFramebufferObject

from consoles_link.stream_view import Renderer, RendererError, StreamWindow, letterbox
from consoles_link.video import BT709, SMPTE170M, Picture, to_rgb

TOP = (63, 102, 240)            # red, BT.709 limited
BOTTOM = (173, 42, 26)          # green


@pytest.fixture
def gl(qapp):
    context = QOpenGLContext()
    if not context.create():
        pytest.skip("no OpenGL context here")
    surface = QOffscreenSurface()
    surface.create()
    if not context.makeCurrent(surface):
        pytest.skip("no OpenGL context here")
    renderer = Renderer()
    try:
        renderer.initialize(context)
    except RendererError as error:
        pytest.skip(f"OpenGL here cannot run the renderer: {error}")
    yield renderer
    context.doneCurrent()


def halves(fmt: str, width: int, height: int, top=TOP, bottom=BOTTOM, **kw) -> Picture:
    """A picture whose top half is one color and bottom half another."""
    cw, ch = width // 2, height // 2
    y = bytes([top[0]] * width * (height // 2) + [bottom[0]] * width * (height // 2))
    rows = lambda value: [value] * cw * (ch // 2)                                 # noqa: E731
    if fmt == "yuv420p":
        chroma = bytes(rows(top[1]) + rows(bottom[1])) + bytes(rows(top[2]) + rows(bottom[2]))
    else:
        chroma = bytes([top[1], top[2]] * cw * (ch // 2) + [bottom[1], bottom[2]] * cw * (ch // 2))
    return Picture(fmt, width, height, y + chroma, **kw)


def draw(renderer: Renderer, picture: Picture, width: int, height: int):
    fbo = QOpenGLFramebufferObject(width, height)
    fbo.bind()
    renderer.upload(picture)
    renderer.paint(width, height)
    image = fbo.toImage()
    fbo.release()
    return lambda x, y: image.pixelColor(x, y).getRgb()[:3]


def close(a, b, tolerance=2):
    return all(abs(x - y) <= tolerance for x, y in zip(a, b))


@pytest.mark.parametrize("fmt", ["yuv420p", "nv12"])
def test_colours_planes_and_orientation(gl, fmt):
    pixel = draw(gl, halves(fmt, 16, 16, colorspace=BT709), 16, 16)
    for x in (0, 7, 15):
        assert close(pixel(x, 0), to_rgb(*TOP)) and close(pixel(x, 15), to_rgb(*BOTTOM)), x


def test_full_range_bt601(gl):
    top, bottom = (128, 90, 200), (200, 160, 60)
    pixel = draw(gl, halves("yuv420p", 16, 16, top, bottom, colorspace=SMPTE170M, full_range=True), 16, 16)
    assert close(pixel(4, 1), to_rgb(*top, "bt601", True)) and close(pixel(4, 14), to_rgb(*bottom, "bt601", True))


def test_wide_picture_is_letterboxed(gl):
    pixel = draw(gl, halves("yuv420p", 16, 8, colorspace=BT709), 16, 16)        # 2:1 in a square: bars above and below
    assert pixel(8, 0) == (0, 0, 0) and pixel(8, 15) == (0, 0, 0)
    assert close(pixel(8, 5), to_rgb(*TOP)) and close(pixel(8, 10), to_rgb(*BOTTOM))


def test_letterbox_arithmetic():
    assert letterbox((1280, 720), (1280, 720)) == (0, 0, 1280, 720)
    assert letterbox((1280, 720), (1000, 1000)) == (0, 219, 1000, 562)
    assert letterbox((1280, 720), (2000, 720)) == (360, 0, 1280, 720)
    assert letterbox((0, 0), (100, 50)) == (0, 0, 100, 50)
    # The stream settings' other fits: the whole area, distorted; or the whole area with the edges cut off.
    assert letterbox((1280, 720), (1000, 1000), "stretch") == (0, 0, 1000, 1000)
    assert letterbox((1280, 720), (1000, 1000), "fill") == (-389, 0, 1778, 1000)
    assert letterbox((1280, 720), (2000, 720), "fill") == (0, -203, 2000, 1125)


def test_window_takes_pictures_and_ends_the_stream_on_close(qapp):
    closed = []
    window = StreamWindow("PS5", lambda: closed.append(True))
    picture = halves("nv12", 16, 16)
    assert window.wanted()
    window.deliver(picture)
    assert not window.wanted() and window.slot.take() is picture
    window.show()
    window.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_F11, Qt.KeyboardModifier.NoModifier))
    assert window.isFullScreen() and window.status.isHidden()
    window.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert not window.isFullScreen() and not window.status.isHidden()
    window.close()
    assert closed == [True]


def test_pointer_hides_over_a_still_picture_and_comes_back_when_moved(qapp):
    window = StreamWindow("PS4", lambda: None)
    view = window.view
    assert view.cursor_timer.isActive() and view.cursor().shape() != Qt.CursorShape.BlankCursor
    view.cursor_timer.timeout.emit()                                    # 2 s without a movement
    assert view.cursor().shape() == Qt.CursorShape.BlankCursor
    view.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, QPointF(5, 5), QPointF(5, 5), Qt.MouseButton.NoButton,
                                    Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    assert view.cursor().shape() != Qt.CursorShape.BlankCursor and view.cursor_timer.isActive()
    window.close()
