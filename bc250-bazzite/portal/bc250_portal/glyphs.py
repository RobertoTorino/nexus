# SPDX-License-Identifier: GPL-3.0-or-later
"""The symbols on the portal's action buttons, drawn with QPainter: no image files, and they take the palette's
text color (or the red of an update). Drawn on a 64 x 64 grid; QIcon scales them to the button."""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

SIZE = 64


def _icon(color: str, draw) -> QIcon:
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
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
