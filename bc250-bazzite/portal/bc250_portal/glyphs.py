# SPDX-License-Identifier: GPL-3.0-or-later
"""The symbols on the portal's action buttons, drawn with QPainter: no image files, and they take the palette's
text color (or the red of an update). Drawn on a 64 x 64 grid; QIcon scales them to the button. The header's big
symbols are drawn at BIG pixels on that grid, so a 4K TV shows them sharp."""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

SIZE = 64
BIG = 256


def _icon(color: str, draw, px: int = SIZE) -> QIcon:
    pixmap = QPixmap(px, px)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(px / SIZE, px / SIZE)
    pen = QPen(QColor(color), 6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    draw(painter)
    painter.end()
    return QIcon(pixmap)


def _line(painter: QPainter, *points: tuple[float, float]) -> None:
    painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in points]))


def install(color: str) -> QIcon:
    """An arrow down into a tray."""
    def draw(p: QPainter) -> None:
        _line(p, (32, 8), (32, 40))
        _line(p, (19, 27), (32, 40), (45, 27))
        _line(p, (10, 40), (10, 54), (54, 54), (54, 40))
    return _icon(color, draw)


def reinstall(color: str) -> QIcon:
    """A circular arrow."""
    def draw(p: QPainter) -> None:
        cx = cy = 32
        r = 21
        start, span = 40, 290                   # degrees, counter-clockwise from three o'clock
        p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), start * 16, span * 16)
        end = math.radians(start + span)
        tip = (cx + r * math.cos(end), cy - r * math.sin(end))
        heading = math.atan2(-math.cos(end), -math.sin(end))       # the arc's direction at its end, on screen
        for side in (-1, 1):
            back = heading + math.pi + side * math.radians(40)
            _line(p, (tip[0] + 13 * math.cos(back), tip[1] + 13 * math.sin(back)), tip)
    return _icon(color, draw)


def uninstall(color: str) -> QIcon:
    """A waste bin."""
    def draw(p: QPainter) -> None:
        pen = p.pen()
        pen.setWidthF(5)
        p.setPen(pen)
        _line(p, (10, 16), (54, 16))
        _line(p, (25, 16), (25, 9), (39, 9), (39, 16))
        _line(p, (16, 16), (19, 55), (45, 55), (48, 16))
        _line(p, (27, 26), (27, 45))
        _line(p, (37, 26), (37, 45))
    return _icon(color, draw)


# The header's symbols (owner, 05-11-2026: big symbols in place of the pills).
def _arrow_arc(p: QPainter, cx: float, cy: float, r: float, start: float, span: float) -> None:
    """An arc of a circle with an arrowhead at its end; degrees counter-clockwise from three o'clock."""
    p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), round(start * 16), round(span * 16))
    end = math.radians(start + span)
    tip = (cx + r * math.cos(end), cy - r * math.sin(end))
    heading = math.atan2(-math.cos(end), -math.sin(end)) if span > 0 else math.atan2(math.cos(end), math.sin(end))
    for side in (-1, 1):
        back = heading + math.pi + side * math.radians(40)
        _line(p, (tip[0] + 11 * math.cos(back), tip[1] + 11 * math.sin(back)), tip)


def refresh(color: str) -> QIcon:
    """Two arrows that chase each other around a circle."""
    def draw(p: QPainter) -> None:
        _arrow_arc(p, 32, 32, 21, 20, 140)
        _arrow_arc(p, 32, 32, 21, 200, 140)
    return _icon(color, draw, BIG)


def chip(color: str) -> QIcon:
    """A processor: a square with pins on every side."""
    def draw(p: QPainter) -> None:
        pen = p.pen()
        pen.setWidthF(5)
        p.setPen(pen)
        p.drawRoundedRect(QRectF(17, 17, 30, 30), 4, 4)
        p.drawRect(QRectF(27, 27, 10, 10))
        for at in (25, 32, 39):
            _line(p, (at, 8), (at, 17))
            _line(p, (at, 47), (at, 56))
            _line(p, (8, at), (17, at))
            _line(p, (47, at), (56, at))
    return _icon(color, draw, BIG)


def install_apps(color: str) -> QIcon:
    """Three apps of a grid of four, an arrow down in the place of the fourth."""
    def draw(p: QPainter) -> None:
        pen = p.pen()
        pen.setWidthF(5)
        p.setPen(pen)
        for x, y in ((8, 8), (36, 8), (8, 36)):
            p.drawRoundedRect(QRectF(x, y, 20, 20), 5, 5)
        _line(p, (46, 34), (46, 56))
        _line(p, (37, 47), (46, 56), (55, 47))
    return _icon(color, draw, BIG)


def install_updates(color: str) -> QIcon:
    """A circular arrow around an arrow down."""
    def draw(p: QPainter) -> None:
        _arrow_arc(p, 32, 32, 24, 110, 300)
        _line(p, (32, 18), (32, 42))
        _line(p, (24, 34), (32, 42), (40, 34))
    return _icon(color, draw, BIG)


def menu(color: str) -> QIcon:
    """☰: three bars."""
    def draw(p: QPainter) -> None:
        for y in (16, 32, 48):
            _line(p, (12, y), (52, y))
    return _icon(color, draw, BIG)
