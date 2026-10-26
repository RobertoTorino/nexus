# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/make_icons.py: ICONS.md is what the script writes, every picture it shows is in the checkout, and the icons
the wikis use are all listed: a Material icon on a page, and every file of the Nexus icon. Neither needs Qt: only
rendering the drawn icons does."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import make_icons  # noqa: E402

SUITE = Path(__file__).resolve().parent.parent.parent


def test_icons_md_is_up_to_date():
    assert (SUITE / "ICONS.md").read_text(encoding="utf-8") == make_icons.build(), \
        "run python3 tools/make_icons.py"


def test_every_picture_shown_is_in_the_checkout():
    sources = re.findall(r'<img src="([^"]+)"', make_icons.build())
    local = [s for s in sources if not s.startswith("https://")]
    assert local and not [s for s in local if not (SUITE / s).is_file()]


def material_icons(folder: Path) -> set[str]:
    """The :material-name: icons the pages in *folder* use."""
    return {m for p in folder.rglob("*.md") for m in re.findall(r":material-([\w-]+):", p.read_text(encoding="utf-8"))}


def test_every_material_icon_of_each_wiki_is_listed():
    """What the wiki's pages use is what its section lists, no more and no less."""
    assert material_icons(SUITE / make_icons.SUITE_DIR / "docs") == {name for name, _ in make_icons.MATERIAL}
    assert material_icons(SUITE / "nexus" / "docs") == {name for name, _ in make_icons.NEXUS_MATERIAL}
    for config in (SUITE / make_icons.SUITE_DIR / "mkdocs.yml", SUITE / "nexus" / "mkdocs.yml"):   # no placeholder logo from Material
        assert "material/" not in re.sub(r"#.*", "", config.read_text(encoding="utf-8"))


def test_every_file_of_the_nexus_icon_is_listed():
    text = make_icons.build()
    files = [*(SUITE / "nexus" / "images").iterdir(), *(SUITE / "nexus" / "docs" / "images").iterdir()]
    assert len(files) >= 5
    for path in files:
        name, rel = path.name, path.relative_to(SUITE).as_posix()
        pattern = re.sub(r"-\d+(?=\.\w+$)", "-<size>", rel)
        assert rel in text or pattern in text or f"`{rel.rsplit('.', 1)[0]}.webp`, `.{path.suffix[1:]}`" in text, name


def test_the_nexus_page_shows_the_nexus_icon():
    """The page's logo and favicon (nexus/docs/images/nexus.*) are copies of the Nexus icon at 256 px, compared by
    their pixels at 32 px as tests/test_portal_icons.py does for the wiki's icon."""
    from PIL import Image, ImageChops, ImageStat

    def small(path):
        return Image.open(path).convert("RGBA").resize((32, 32), Image.Resampling.LANCZOS)

    icon = small(SUITE / "nexus" / "images" / "nexus-256.png")
    for name in ("nexus.webp", "nexus.png"):
        copy = SUITE / "nexus" / "docs" / "images" / name
        assert Image.open(copy).size == (256, 256), name
        assert sum(ImageStat.Stat(ImageChops.difference(icon, small(copy))).mean) / 4 <= 4, name
    config = (SUITE / "nexus" / "mkdocs.yml").read_text(encoding="utf-8")
    home = (SUITE / "nexus" / "overrides" / "home.html").read_text(encoding="utf-8")
    assert "logo: images/nexus.webp" in config and "favicon: images/nexus.png" in config
    assert "images/nexus.webp" in home


def test_every_category_is_listed():
    text = make_icons.build()
    for category in (p.name for p in (SUITE / make_icons.SUITE_DIR / "icons").iterdir() if p.is_dir()):
        assert f"{make_icons.SUITE_DIR}/icons/{category}/{category}-128.png" in text
