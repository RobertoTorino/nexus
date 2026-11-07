# SPDX-License-Identifier: GPL-3.0-or-later
"""A save's 3D icon as a still picture, drawn in Python without OpenGL: what mymc++'s icon viewer shows when it
opens (its icon_renderer.py), the first shape of the model unanimated. The same camera (5 units back, 80 degrees,
the model lowered by 2.5), the icon's own lighting from icon.sys (ambient light and three lights, Lambert), its
background (the four corner colors over black) and its texture (128 x 128, 5 bits a color) with mipmaps, with
back faces left out and a depth buffer as OpenGL has them.

The mipmaps matter: many icons draw their outlines with a texture's border (Rez: black with an orange edge), which
OpenGL's mipmaps blend into small triangles; the nearest texel alone would miss it. Simplifications a picture this
small does not show: the light is worked out per corner and shaded across (OpenGL: per pixel), the mipmap level
per triangle (OpenGL: per pixel), and the edges are smoothed by drawing at twice the size."""

from __future__ import annotations

import math

from PyQt6.QtGui import QImage

from .mymc import ps2icon
from .mymc.ps2iconsys import IconSys

SIZE = 128
SUPERSAMPLE = 2                                 # drawn at twice the size, then averaged down
FIXED = 4096.0                                  # the icon's fixed point: 4096 is 1.0
CAMERA = 5.0
LOWER = 2.5
FOV = 80.0
TEXTURE = ps2icon.TEXTURE_WIDTH                 # 128, square

Colour = tuple[float, float, float]


def _texels(texture) -> list[Colour] | None:
    """The texture as (r, g, b) from 0 to 1, row by row; None for an icon without one (its colors alone)."""
    if not isinstance(texture, (bytes, bytearray)) or len(texture) < TEXTURE * TEXTURE * 2:
        return None
    out = []
    for i in range(TEXTURE * TEXTURE):
        pixel = texture[2 * i] | (texture[2 * i + 1] << 8)
        out.append(((pixel & 31) / 31.0, ((pixel >> 5) & 31) / 31.0, ((pixel >> 10) & 31) / 31.0))
    return out


def _mipmaps(texels: list[Colour]) -> list[list[Colour]]:
    """The texture and each half-size average of it down to one texel, as glGenerateMipmap makes them."""
    levels = [texels]
    size = TEXTURE
    while size > 1:
        last, size = levels[-1], size // 2
        level = []
        for y in range(size):
            for x in range(size):
                four = (last[2 * y * 2 * size + 2 * x], last[2 * y * 2 * size + 2 * x + 1],
                        last[(2 * y + 1) * 2 * size + 2 * x], last[(2 * y + 1) * 2 * size + 2 * x + 1])
                level.append(tuple(sum(t[c] for t in four) / 4.0 for c in range(3)))
        levels.append(level)
    return levels


def _normalised(v: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / length, v[1] / length, v[2] / length) if length > 0.0001 else (0.0, 0.0, 0.0)


def _background(icon_sys: IconSys, size: int) -> list[list[float]]:
    """The four corner colors (0x80 is full), blended over black with the icon's background alpha, as a
    gradient: the first top left, the second top right, the third bottom left, the fourth bottom right, as
    mymc++ lays them out."""
    alpha = min(icon_sys.background_transparency / 0x80, 1.0)
    tl, tr, bl, br = ([min(c / 0x80, 1.0) * alpha for c in icon_sys.bg_colors[i][:3]] for i in range(4))
    pixels = []
    for y in range(size):
        fy = y / (size - 1)
        for x in range(size):
            fx = x / (size - 1)
            pixels.append([(tl[c] * (1 - fx) + tr[c] * fx) * (1 - fy) + (bl[c] * (1 - fx) + br[c] * fx) * fy
                           for c in range(3)])
    return pixels


def render(icon_sys: IconSys, icon: ps2icon.Icon, size: int = SIZE) -> QImage:
    big = size * SUPERSAMPLE
    pixels = _background(icon_sys, big)
    depth = [0.0] * (big * big)                 # 1 / w of the nearest surface so far; 0 is nothing yet
    count = icon.vertex_count - icon.vertex_count % 3
    if count and icon.vertex_data is not None:
        _draw(icon_sys, icon, count, big, pixels, depth)
    image = QImage(size, size, QImage.Format.Format_RGB32)
    n = SUPERSAMPLE * SUPERSAMPLE
    for y in range(size):
        for x in range(size):
            block = [pixels[(SUPERSAMPLE * y + dy) * big + SUPERSAMPLE * x + dx]
                     for dy in range(SUPERSAMPLE) for dx in range(SUPERSAMPLE)]
            r, g, b = (max(0, min(255, round(sum(p[c] for p in block) / n * 255))) for c in range(3))
            image.setPixel(x, y, 0xFF000000 | (r << 16) | (g << 8) | b)
    return image


def _draw(icon_sys: IconSys, icon: ps2icon.Icon, count: int, size: int, pixels: list[list[float]],
          depth: list[float]) -> None:
    f = 1.0 / math.tan(math.radians(FOV) / 2.0)
    texels = _texels(icon.texture)
    mipmaps = _mipmaps(texels) if texels is not None else None
    lights = [(_normalised(tuple(d[:3])), tuple(c[:3])) for d, c in zip(icon_sys.light_dirs, icon_sys.light_colors)]
    ambient = tuple(icon_sys.ambient_light_color[:3])
    blend = icon.enable_alpha
    v, nuv, colours = icon.vertex_data, icon.normal_uv_data, icon.color_data

    # Each vertex: screen x and y, 1/w, its lit color, alpha, and its texture coordinates.
    points = []
    for i in range(count):
        x = v[3 * i] / FIXED
        y = -v[3 * i + 1] / FIXED - LOWER
        z = -v[3 * i + 2] / FIXED
        w = CAMERA - z                          # the distance in front of the camera
        if w <= 0.1:
            points.append(None)
            continue
        sx = (f * x / w + 1.0) * 0.5 * size
        sy = (1.0 - f * y / w) * 0.5 * size
        normal = _normalised((nuv[5 * i] / FIXED, -nuv[5 * i + 1] / FIXED, -nuv[5 * i + 2] / FIXED))
        r, g, b, a = (colours[4 * i + c] / 255.0 for c in range(4))
        light = [ambient[c] for c in range(3)]
        for direction, colour in lights:
            lambert = max(direction[0] * normal[0] + direction[1] * normal[1] + direction[2] * normal[2], 0.0)
            for c in range(3):
                light[c] += lambert * colour[c]
        points.append((sx, sy, 1.0 / w, r * light[0], g * light[1], b * light[2], a if blend else 1.0,
                       nuv[5 * i + 3] / FIXED, nuv[5 * i + 4] / FIXED))

    for t in range(0, count, 3):
        p0, p1, p2 = points[t], points[t + 1], points[t + 2]
        if p0 is None or p1 is None or p2 is None:
            continue
        # Counter-clockwise on screen with y up is the front, as OpenGL takes it; screen y runs down here.
        area = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1])
        if area >= 0:
            continue
        texture = None
        if mipmaps is not None:
            texture = mipmaps[_level(p0, p1, p2, area, len(mipmaps) - 1)]
        _triangle(p0, p1, p2, area, size, pixels, depth, texture)


def _level(p0, p1, p2, area: float, deepest: int) -> int:
    """The mipmap level for a triangle as OpenGL picks it: log2 of the texels one pixel of the final picture
    spans, along the screen direction that squeezes the texture most (a face seen edge on: the deepest level)."""
    ex1, ey1, ex2, ey2 = p1[0] - p0[0], p1[1] - p0[1], p2[0] - p0[0], p2[1] - p0[1]
    across: list[float] = []                            # d/dx of u and v, then d/dy of u and v
    down: list[float] = []
    for k in (7, 8):                                    # u, v
        d1, d2 = p1[k] - p0[k], p2[k] - p0[k]
        across.append((d1 * ey2 - d2 * ey1) / area)
        down.append((d2 * ex1 - d1 * ex2) / area)
    # Texture coordinates are 0 to 1 over 128 texels; the screen here is SUPERSAMPLE times the picture.
    rho = max(math.hypot(*across), math.hypot(*down)) * TEXTURE * SUPERSAMPLE
    return max(0, min(deepest, round(math.log2(rho)))) if rho > 1 else 0


def _triangle(p0, p1, p2, area: float, size: int, pixels: list[list[float]], depth: list[float],
              texture: list[Colour] | None) -> None:
    x0 = max(int(min(p0[0], p1[0], p2[0])), 0)
    x1 = min(int(max(p0[0], p1[0], p2[0])) + 1, size - 1)
    y0 = max(int(min(p0[1], p1[1], p2[1])), 0)
    y1 = min(int(max(p0[1], p1[1], p2[1])) + 1, size - 1)
    if x0 > x1 or y0 > y1:
        return
    side = int(math.sqrt(len(texture))) if texture is not None else 0
    # Per vertex, over w (for perspective): the lit color, alpha and texture coordinates; and 1/w itself.
    q = [[p[2]] + [p[k] * p[2] for k in range(3, 9)] for p in (p0, p1, p2)]
    inv = 1.0 / area
    for y in range(y0, y1 + 1):
        py = y + 0.5
        for x in range(x0, x1 + 1):
            px = x + 0.5
            w0 = ((p1[0] - px) * (p2[1] - py) - (p2[0] - px) * (p1[1] - py)) * inv
            w1 = ((p2[0] - px) * (p0[1] - py) - (p0[0] - px) * (p2[1] - py)) * inv
            w2 = 1.0 - w0 - w1
            if w0 < 0 or w1 < 0 or w2 < 0:
                continue
            one_w = w0 * q[0][0] + w1 * q[1][0] + w2 * q[2][0]
            at = y * size + x
            if one_w <= depth[at]:
                continue
            r, g, b, a, u, v = ((w0 * q[0][k] + w1 * q[1][k] + w2 * q[2][k]) / one_w for k in range(1, 7))
            if texture is not None:
                tx = min(max(int(u * side), 0), side - 1)
                ty = min(max(int(v * side), 0), side - 1)
                tr, tg, tb = texture[ty * side + tx]
                r, g, b = r * tr, g * tg, b * tb
            a = min(max(a, 0.0), 1.0)
            old = pixels[at]
            pixels[at] = [min(c, 1.0) * a + o * (1.0 - a) for c, o in zip((r, g, b), old)]
            depth[at] = one_w
