# SPDX-License-Identifier: GPL-3.0-or-later
"""steam_art.py: the artwork drawn from an app's icon, at Steam's sizes, in the icon's color, the icon as the logo,
a long title, and no icon."""

from __future__ import annotations

from bc250_core import steam_art
from bc250_core.steam import ART


def _icon(tmp_path, colour: str):
    from PyQt6.QtGui import QColor, QImage
    icon = QImage(512, 512, QImage.Format.Format_ARGB32)
    icon.fill(QColor(colour))
    path = tmp_path / f"icon-{colour[1:]}.png"
    icon.save(str(path))
    return path


def test_steams_sizes_and_the_icon_as_logo(qapp, tmp_path):
    from PyQt6.QtGui import QImage
    icon = _icon(tmp_path, "#d4a017")
    art = steam_art.draw_icon_art(icon, "PS4-728", "PS4 · Remote Play", "CONSOLE LINK · PS4")
    assert set(art) == set(ART) and art["_logo"] == icon.read_bytes()
    for suffix in ("p", "", "_hero"):
        image = QImage.fromData(art[suffix], "PNG")
        assert (image.width(), image.height()) == ART[suffix], suffix


def test_a_webp_icon_is_the_logo_as_png(qapp, tmp_path):
    """Steam's grid files are PNG: an app's WebP icon goes in as PNG, the same picture."""
    from PyQt6.QtGui import QImage
    icon = tmp_path / "icon.webp"
    QImage(str(_icon(tmp_path, "#d4a017"))).save(str(icon), "WEBP")
    logo = steam_art.draw_icon_art(icon, "Title")["_logo"]
    assert logo.startswith(b"\x89PNG") and QImage.fromData(logo, "PNG").size() == QImage(str(icon)).size()


def test_the_background_takes_the_icons_colour(qapp, tmp_path):
    from PyQt6.QtGui import QColor, QImage
    for colour, warm in (("#d4a017", True), ("#1e64c8", False)):
        assert steam_art.accent_colour(QImage(str(_icon(tmp_path, colour)))).name() == colour
        hero = QImage.fromData(steam_art.draw_icon_art(_icon(tmp_path, colour), "Title")["_hero"], "PNG")
        corner = hero.pixelColor(20, 20)                                      # the dark background, in its hue
        assert corner.value() < 60 and (corner.red() > corner.blue()) == warm, colour
    grey = QImage(64, 64, QImage.Format.Format_ARGB32)
    grey.fill(QColor("#808080"))
    assert steam_art.accent_colour(grey).name() == steam_art.FALLBACK         # no bright color to take


def test_a_long_title_fits(qapp, tmp_path):
    from PyQt6.QtGui import QImage
    title = "Shin Megami Tensei: Digital Devil Saga 2 – Avatar Tuner Special Edition (Disc 2)"
    art = steam_art.draw_icon_art(_icon(tmp_path, "#1e64c8"), title, "PS2 · PCSX2 Manager")
    portrait = QImage.fromData(art["p"], "PNG")
    width, height = ART["p"]
    edges = [portrait.pixelColor(x, y).value() for x in (2, width - 3) for y in range(height // 2, height, 7)]
    assert max(edges) < 120                                                   # no text runs off the sides


def test_without_the_icon(qapp, tmp_path):
    from PyQt6.QtGui import QImage
    art = steam_art.draw_icon_art(tmp_path / "none.png", "Bazzite DatStation")
    logo = QImage.fromData(art["_logo"], "PNG")                               # the title instead
    assert (logo.width(), logo.height()) == ART["_logo"] and logo.pixelColor(0, 0).alpha() == 0
    corner = QImage.fromData(art["_hero"], "PNG").pixelColor(20, 20)
    assert corner.blue() > corner.red()                                      # the dark blue fallback
