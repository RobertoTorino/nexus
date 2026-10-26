# SPDX-License-Identifier: GPL-3.0-or-later
"""Artwork for a Steam shortcut drawn from an app's icon, for apps with no pictures of their own (owner, 16-10-2026):
the four images of steam.ART as PNG bytes. The background is near black in the icon's own color (the mean of its
bright, saturated pixels), lighter towards the middle, with a glow of that color; the portrait and the wide picture
have the icon with a title and a line under it, the banner the title and its own line centered, as a game's banner has
its title; the logo Steam lays over the banner (bottom left) is the icon file itself (as PNG). So the artwork follows
the icon when the icon changes. Without the icon: a dark blue background and the title as the logo.

Moved here from BC250 Console Link (16-10-2026), which drew it first."""

from __future__ import annotations

from pathlib import Path

from .steam import ART

FALLBACK = "#1d4f91"                    # the accent without an icon, or with one that has no bright color


def draw_icon_art(icon: Path, title: str, subtitle: str = "", hero_subtitle: str | None = None) -> dict[str, bytes]:
    """The four images (steam.ART's suffixes) as PNG bytes. *subtitle* goes under the title on the portrait and the
    wide picture, *hero_subtitle* (*subtitle* when None) under it on the banner; a long title wraps and shrinks."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QColor, QImage, QPainter

    source = QImage(str(icon))
    accent = accent_colour(source)
    images = {}
    for suffix, (width, height) in ART.items():
        if suffix == "_logo":
            images[suffix] = (_png(_text_logo(title, width, height)) if source.isNull()
                              else icon.read_bytes() if icon.suffix.lower() == ".png" else _png(source))
            continue
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        hero = suffix == "_hero"
        if hero:
            _background(painter, width, height, accent, width / 2, height * 0.42)
            title_top, title_height = height * 0.27, height * 0.17
            under = subtitle if hero_subtitle is None else hero_subtitle
        else:
            side = min(width, height) * (0.45 if suffix == "p" else 0.5)
            top = height * (0.18 if suffix == "p" else 0.12)
            _background(painter, width, height, accent, width / 2, top + side / 2)
            if not source.isNull():
                painter.drawImage(QRectF((width - side) / 2, top, side, side), source)
            title_top, title_height = top + side + height * 0.04, height * 0.14
            under = subtitle
        box = QRectF(width * 0.05, title_top, width * 0.9, title_height)
        _fitted_text(painter, box, title, int(title_height * 0.64), bold=True, colour=QColor("#ffffff"))
        if under:
            _fitted_text(painter, QRectF(width * 0.05, title_top + title_height * 0.95, width * 0.9,
                                         title_height * 0.55),
                         under, int(title_height * (0.3 if hero else 0.36)), bold=False, colour=accent.lighter(170))
        painter.end()
        images[suffix] = _png(image)
    return images


def accent_colour(icon):
    """The icon's own color: the mean of its bright, saturated pixels (a sample of them); FALLBACK without one."""
    from PyQt6.QtGui import QColor
    if icon.isNull():
        return QColor(FALLBACK)
    step = max(1, min(icon.width(), icon.height()) // 64)
    total, count = [0, 0, 0], 0
    for y in range(0, icon.height(), step):
        for x in range(0, icon.width(), step):
            color = icon.pixelColor(x, y)
            if color.alpha() > 200 and color.hsvSaturation() > 80 and color.value() > 80:
                total = [total[0] + color.red(), total[1] + color.green(), total[2] + color.blue()]
                count += 1
    if not count:
        return QColor(FALLBACK)
    return QColor(*(round(t / count) for t in total))


def _background(painter, width: int, height: int, accent, cx: float, cy: float) -> None:
    """Near black in the accent's hue, lighter towards the middle, and a soft glow of the accent behind (cx, cy)."""
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QColor, QLinearGradient, QRadialGradient
    hue = accent.hsvHue() if accent.hsvHue() >= 0 else 215
    vertical = QLinearGradient(0, 0, 0, height)
    vertical.setColorAt(0, QColor.fromHsv(hue, 200, 34))
    vertical.setColorAt(0.55, QColor.fromHsv(hue, 210, 22))
    vertical.setColorAt(1, QColor.fromHsv(hue, 220, 8))
    painter.fillRect(0, 0, width, height, vertical)
    radius = max(width, height) * 0.45 if width > height * 2 else max(width, height) * 0.6
    glow = QRadialGradient(QPointF(cx, cy), radius)
    for at, alpha in ((0, 120), (0.35, 50), (1, 0)):
        color = QColor(accent)
        color.setAlpha(alpha)
        glow.setColorAt(at, color)
    painter.fillRect(0, 0, width, height, glow)


def _fitted_text(painter, box, text: str, size: int, bold: bool, colour) -> None:
    """*text* centered in *box*, wrapped at word breaks, at *size* px or smaller until it fits."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont, QFontMetricsF
    flags = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap
    font = QFont()
    font.setBold(bold)
    while True:
        font.setPixelSize(max(size, 1))
        bounds = QFontMetricsF(font).boundingRect(box, int(flags), text)
        if size <= 8 or (bounds.width() <= box.width() and bounds.height() <= box.height()):
            break
        size = int(size * 0.9)
    painter.setFont(font)
    painter.setPen(colour)
    painter.drawText(box, flags, text)


def _text_logo(title: str, width: int, height: int):
    """Without the icon: the title on a transparent background, as the logo."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QColor, QImage, QPainter
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _fitted_text(painter, QRectF(0, 0, width, height), title, height // 3, bold=True, colour=QColor("#ffffff"))
    painter.end()
    return image


def _png(image) -> bytes:
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)
