# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal's own tile icon and the wiki's icon are copies of the suite's icon: a lagging copy shows the old icon
(seen 15-10-2026: ten tile copies lagged). The apps' tiles are copies of their category's icon, which
tests/test_icons.py checks."""

from __future__ import annotations

from pathlib import Path

SUITE = Path(__file__).resolve().parents[2]


def small(path: Path):
    from PIL import Image
    return Image.open(path).convert("RGBA").resize((32, 32), Image.Resampling.LANCZOS)


def test_the_portal_tile_is_the_suites_icon():
    """portal.webp is the suite's own icon, by its pixels at 32 px as below; the other tiles are category icons
    (tests/test_icons.py)."""
    from PIL import ImageChops, ImageStat

    tile, icon = (small(SUITE / "portal" / "images" / name)
                  for name in ("apps/portal.webp", "bc250-bazzite-suite-128.png"))
    assert sum(ImageStat.Stat(ImageChops.difference(tile, icon)).mean) / 4 <= 4


def test_the_wiki_icon_is_the_portals():
    """The wiki's logo and favicon (docs/images/wiki-icon.*) are scaled copies of the portal's icon, so they are
    compared by their pixels at 32 px: they lagged once after the icon changed (seen 16-10-2026)."""
    from PIL import ImageChops, ImageStat

    portal = small(SUITE / "portal" / "images" / "bc250-bazzite-suite.webp")
    off = {name: sum(ImageStat.Stat(ImageChops.difference(portal, small(SUITE / "docs" / "images" / name))).mean) / 4
           for name in ("wiki-icon.png", "wiki-icon.webp")}
    stale = [name for name, mean in off.items() if mean > 4]
    assert not stale, f"these no longer show the portal's icon: {', '.join(stale)}"
