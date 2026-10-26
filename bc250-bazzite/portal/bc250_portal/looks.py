# SPDX-License-Identifier: GPL-3.0-or-later
"""How the portal draws its pictures, shared by the desktop window and Suite Big Picture Mode: the wallpaper behind
the window, and an app's icon grayed (not installed) or dimmed (under the mouse)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPalette, QPixmap
from PyQt6.QtWidgets import QWidget

HOVER_OPACITY = 0.75            # an app icon under the mouse is dimmed this much: no border
VEIL = 60                       # % of the theme's window color over the wallpaper, so the text on it stays readable


def greyed(pixmap: QPixmap) -> QPixmap:
    """The icon of an app that is not installed: gray and faded, with its own transparency kept."""
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    grey = image.convertToFormat(QImage.Format.Format_Grayscale8).convertToFormat(QImage.Format.Format_ARGB32)
    grey.setAlphaChannel(image.convertToFormat(QImage.Format.Format_Alpha8))
    out = QPixmap(pixmap.size())
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setOpacity(0.45)
    painter.drawImage(0, 0, grey)
    painter.end()
    return out


def dimmed(pixmap: QPixmap, opacity: float = HOVER_OPACITY) -> QPixmap:
    """The icon under the mouse: a little fainter, so the window's color shows through."""
    out = QPixmap(pixmap.size())
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setOpacity(opacity)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return out


class Backdrop(QWidget):
    """The window's background: the wallpaper, scaled to fill and cropped in the middle, under a veil of the theme's
    window color (*veil*, 0 to 100 %); without one, the window color."""

    def __init__(self):
        super().__init__()
        self.picture = QPixmap()
        self.veil = VEIL

    def set_picture(self, path: Path | None) -> None:
        self.picture = QPixmap(str(path)) if path else QPixmap()
        self.update()

    def set_veil(self, percent: int) -> None:
        self.veil = percent
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self.picture.isNull():
            return super().paintEvent(event)
        painter = QPainter(self)
        scaled = self.picture.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                     Qt.TransformationMode.SmoothTransformation)
        x, y = (scaled.width() - self.width()) // 2, (scaled.height() - self.height()) // 2
        painter.drawPixmap(0, 0, scaled, x, y, self.width(), self.height())
        veil = QColor(self.palette().color(QPalette.ColorRole.Window))
        veil.setAlphaF(self.veil / 100)
        painter.fillRect(QRect(0, 0, self.width(), self.height()), veil)
        painter.end()
