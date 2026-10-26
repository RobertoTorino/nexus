# SPDX-License-Identifier: GPL-3.0-or-later
"""The still picture of a save's 3D icon (memcard_icon.py): Rez's icon from mymc++'s test card against the picture
mymc++'s own OpenGL viewer draws of it, and a small icon made here for the colors, the back faces and the
mipmaps.

fixtures/rez-icon-opengl.png is mymc++'s IconRenderer at the pinned commit (its shaders and matrices, unchanged)
drawing that icon at 256 x 256 into an offscreen framebuffer (Mesa, OpenGL 4.6, on the owner's machine, 16-10-2026),
with the camera, the light and the background its window opens with, composited over black as its window shows
it."""

from __future__ import annotations

import struct

from PyQt6.QtGui import QImage

from conftest import FIXTURES

from pcsx2_manager import memcard_icon, memcards
from pcsx2_manager.mymc.ps2icon import Icon
from pcsx2_manager.mymc.ps2iconsys import IconSys


def _difference(a: QImage, b: QImage) -> tuple[float, float]:
    """(the mean difference of the largest channel per pixel, the share of pixels off by more than 24 of 255)."""
    diffs = []
    for y in range(a.height()):
        for x in range(a.width()):
            pa, pb = a.pixel(x, y), b.pixel(x, y)
            diffs.append(max(abs(((pa >> s) & 255) - ((pb >> s) & 255)) for s in (16, 8, 0)))
    return sum(diffs) / len(diffs), sum(d > 24 for d in diffs) / len(diffs)


def test_rez_as_mymcs_opengl_viewer_draws_it(qapp, cards):
    icon_sys, icon = memcards.save_icon(cards / "mc01.ps2", "BESCES-50501REZ")
    ours = memcard_icon.render(icon_sys, icon, 256)
    reference = QImage(str(FIXTURES / "rez-icon-opengl.png")).convertToFormat(QImage.Format.Format_RGB32)
    assert ours.size() == reference.size()
    mean, off = _difference(ours, reference)
    # Measured 16-10-2026: 1.40 and 0.85 %, along the edges (smoothed here, OpenGL's are not).
    assert mean < 2.5 and off < 0.015
    assert ours.pixel(2, 2) & 0xFFFFFF == 0x24246B                     # the background, as OpenGL: 0x23236B


def _icon_sys(ambient: float = 1.0) -> IconSys:
    """icon.sys with no background and no lights, only ambient light."""
    data = struct.pack("<4sHHII", b"PS2D", 0, 0, 0, 0) + b"\0" * 64             # background colors
    data += struct.pack("<12f", *[0.0] * 12) + struct.pack("<12f", *[0.0] * 12)   # light directions, colors
    data += struct.pack("<4f", ambient, ambient, ambient, 0.0)
    data += b"Test".ljust(68, b"\0") + b"icon.ico".ljust(64, b"\0") * 3 + b"\0" * 512
    return IconSys(data)


def _icon(corners: list[tuple[float, float]], colour: tuple[int, int, int], texture: bytes | None = None) -> Icon:
    """One triangle at the depth of the model's center, given as (x, y) on the screen with y up, -1 to 1 the
    model's units; facing the camera."""
    data = struct.pack("<IIIII", 0x010000, 1, 0x07 if texture else 0x03, 0, 3)
    for (x, y), (u, v) in zip(corners, [(0, 0), (4096, 0), (0, 4096)]):
        data += struct.pack("<hhhH", round(x * 4096), round(-(y + memcard_icon.LOWER) * 4096), 0, 0)
        data += struct.pack("<hhhHhhBBBB", 0, 0, -4096, 0, u, v, *colour, 255)
    data += struct.pack("<IIfII", 1, 1, 1.0, 0, 1) + struct.pack("<II", 0, 1) + struct.pack("<ff", 0.0, 1.0)
    return Icon(data + (texture or b""))


FRONT = [(-1.0, -1.0), (1.0, -1.0), (0.0, 1.0)]         # counter-clockwise with y up: the front


def test_vertex_colours_and_light(qapp):
    image = memcard_icon.render(_icon_sys(), _icon(FRONT, (255, 0, 0)))
    assert image.pixel(64, 70) & 0xFFFFFF == 0xFF0000                 # inside: the color, at full light
    assert image.pixel(5, 5) & 0xFFFFFF == 0x000000                    # outside: the background (black here)
    dim = memcard_icon.render(_icon_sys(0.5), _icon(FRONT, (255, 0, 0)))
    assert (dim.pixel(64, 70) >> 16) & 255 in (127, 128)               # half the light, half the red


def test_back_faces_are_left_out(qapp):
    back = [FRONT[0], FRONT[2], FRONT[1]]                               # clockwise: seen from behind
    image = memcard_icon.render(_icon_sys(), _icon(back, (255, 0, 0)))
    assert image.pixel(64, 70) & 0xFFFFFF == 0x000000


def test_the_texture_and_its_mipmaps(qapp):
    green = struct.pack("<H", 31 << 5) * (128 * 128)                    # 5 bits a color: all green
    image = memcard_icon.render(_icon_sys(), _icon(FRONT, (255, 255, 255), green))
    assert image.pixel(64, 70) & 0xFFFFFF == 0x00FF00
    texels = memcard_icon._texels(struct.pack("<H", 31) * (128 * 64) + b"\0\0" * (128 * 64))   # red over black
    levels = memcard_icon._mipmaps(texels)
    assert [len(level) for level in levels] == [4 ** (7 - n) for n in range(8)]                   # 128 to 1
    assert levels[-1][0] == (0.5, 0.0, 0.0)                              # the whole texture's mean
    assert memcard_icon._texels([0xFFFF]) is None                       # an icon without one: its colors
