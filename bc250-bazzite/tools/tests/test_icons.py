# SPDX-License-Identifier: GPL-3.0-or-later
"""Every installer that points its menu entry at images/$APP_ID-128.png has that file and the WebP icon beside it: a
renamed icon otherwise leaves the menu entry and the Desktop icon without one, and nothing else fails. And every app
icon is a copy of its category's icon in icons/ (icons/categories.toml)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sync_icons  # noqa: E402

SUITE = Path(__file__).resolve().parent.parent.parent
INSTALLERS = sorted([SUITE / "portal" / "install.sh", *SUITE.glob("apps/*/install.sh")])


@pytest.mark.parametrize("installer", INSTALLERS, ids=lambda p: p.parent.name)
def test_installer_icon_exists(installer):
    text = installer.read_text(encoding="utf-8")
    app_id = re.search(r'^APP_ID="([^"]+)"', text, re.M)
    if app_id is None or "images/$APP_ID-128.png" not in text:
        pytest.skip("no images/$APP_ID-128.png icon")
    assert (installer.parent / "images" / f"{app_id.group(1)}-128.png").is_file()
    assert (installer.parent / "images" / f"{app_id.group(1)}.webp").is_file()


def test_icon_copies_match_their_category():
    """Every copy in icons/categories.toml is its category's icon: run tools/sync_icons.py after changing icons/."""
    assert [p.relative_to(SUITE).as_posix() for p in sync_icons.stale()] == []


@pytest.mark.parametrize("category", sorted(p.name for p in (SUITE / "icons").iterdir() if p.is_dir()))
def test_category_has_every_size(category):
    """WebP for Qt and the wiki; the 128 px one PNG, for menu entries, Steam and notifications."""
    for size, kind in ((1024, "webp"), (512, "webp"), (256, "webp"), (128, "png")):
        with Image.open(SUITE / "icons" / category / f"{category}-{size}.{kind}") as image:
            assert image.size == (size, size) and image.format == kind.upper()


def test_every_app_icon_comes_from_a_category():
    """No app icon or portal tile outside icons/categories.toml: one left there keeps an old icon. An app's icons
    are found by their PNG (the screenshots beside them are WebP too). A Nexus app's tile (nexus = true in
    portal/apps.toml: Nexus Releases) is the Nexus icon, written by tools/make_icons.py, not a category's."""
    import tomllib
    checkout = tomllib.loads((SUITE / "portal" / "apps.toml").read_text(encoding="utf-8")).get("checkout", {})
    nexus = {f"{key}.webp" for key, entry in checkout.items() if entry.get("nexus")}
    assert nexus == {"releases.webp"}
    icons = {*SUITE.glob("apps/*/images/*.png"), *SUITE.glob("tools/installer-tests/gui/images/*.png"),
             *(p for p in SUITE.glob("portal/images/apps/*.*") if p.name != "portal.webp" and p.name not in nexus)}
    assert sorted(p.relative_to(SUITE).as_posix() for p in icons - set(sync_icons.copies())) == []


def test_portal_tabs_follow_the_icon_categories():
    """An app's tab in the portal (category in portal/apps.toml) is the category of its icon, and the portal knows
    every category of icons/."""
    import tomllib
    import check_manifest
    table = tomllib.loads((SUITE / "icons" / "categories.toml").read_text(encoding="utf-8"))
    path = SUITE / check_manifest.MANIFEST
    entries = check_manifest.manifest.load(path) + check_manifest.manifest.load_checkout(path)
    assert [e.key for e in entries if e.nexus] == ["releases"]           # a Nexus app: the Nexus icon, no category icon
    entries = [e for e in entries if not e.nexus]
    assert {e.key: e.category for e in entries} == {e.key: table[e.key]["category"] for e in entries}
    assert set(check_manifest.manifest.CATEGORIES) == {p.name for p in (SUITE / "icons").iterdir() if p.is_dir()}


def _suite(tmp_path):
    """A checkout with one category, its four icons and one app: what sync_icons reads."""
    (tmp_path / "icons" / "leaf").mkdir(parents=True)
    (tmp_path / "icons" / "categories.toml").write_text(
        '[app]\ncategory = "leaf"\nicons = ["apps/app/images/app"]\ntile = "portal/images/apps/app.webp"\n',
        encoding="utf-8")
    for size in sync_icons.SIZES:
        _image(sync_icons.icon_path(tmp_path / "icons" / "leaf", size), size, "red")
    return tmp_path


def _image(path, size, color, width=None):
    Image.new("RGBA", (width or size, size), color).save(path)
    return path


def _color(path):
    """The color in the middle, each channel 0 or 255: WebP is lossy."""
    with Image.open(path) as image:
        pixel = image.convert("RGB").getpixel((image.width // 2, image.height // 2))
    return tuple(255 if channel > 127 else 0 for channel in pixel)


def test_category_icons_need_no_conversion(tmp_path):
    assert sync_icons.dropped(_suite(tmp_path)) == {}


def test_an_image_by_another_name_becomes_every_size(tmp_path):
    root = _suite(tmp_path)
    source = _image(root / "icons" / "leaf" / "new leaf.png", 700, "blue")

    written = sync_icons.convert_dropped(root)

    assert written == [sync_icons.icon_path(root / "icons" / "leaf", size) for size in sync_icons.SIZES]
    assert not source.exists()
    for size in sync_icons.SIZES:
        assert sync_icons.is_icon(sync_icons.icon_path(root / "icons" / "leaf", size))
        assert _color(sync_icons.icon_path(root / "icons" / "leaf", size)) == (0, 0, 255)
    assert sync_icons.dropped(root) == {}


def test_an_image_named_by_its_size_replaces_only_that_size(tmp_path):
    """leaf-512.png becomes leaf-512.webp; a 128 px PNG at the wrong size is scaled in place; the rest stays."""
    root = _suite(tmp_path)
    folder = root / "icons" / "leaf"
    _image(folder / "leaf-512.png", 512, "blue")
    _image(folder / "leaf-128.png", 300, "lime")

    sync_icons.convert_dropped(root)

    assert sorted(p.name for p in folder.iterdir()) == ["leaf-1024.webp", "leaf-128.png", "leaf-256.webp",
                                                        "leaf-512.webp"]
    assert all(sync_icons.is_icon(p) for p in folder.iterdir())
    assert _color(folder / "leaf-512.webp") == (0, 0, 255)
    assert _color(folder / "leaf-128.png") == (0, 255, 0)
    assert _color(folder / "leaf-1024.webp") == _color(folder / "leaf-256.webp") == (255, 0, 0)


def test_a_size_of_its_own_wins_over_the_whole_set(tmp_path):
    root = _suite(tmp_path)
    folder = root / "icons" / "leaf"
    _image(folder / "set.png", 1024, "blue")
    _image(folder / "leaf-256.png", 256, "lime")

    sync_icons.convert_dropped(root)

    assert _color(folder / "leaf-1024.webp") == (0, 0, 255)
    assert _color(folder / "leaf-256.webp") == (0, 255, 0)


def test_two_images_for_every_size_are_refused(tmp_path):
    root = _suite(tmp_path)
    _image(root / "icons" / "leaf" / "a.png", 512, "blue")
    _image(root / "icons" / "leaf" / "b.png", 512, "lime")
    with pytest.raises(SystemExit, match="more than one image for all sizes: a.png, b.png"):
        sync_icons.dropped(root)


def test_a_wide_image_is_refused(tmp_path):
    root = _suite(tmp_path)
    source = _image(tmp_path / "wide.png", 256, "blue", width=512)
    with pytest.raises(SystemExit, match="512 x 256 px, an icon must be square"):
        sync_icons.convert(source, root / "icons" / "leaf")


def test_from_converts_the_sizes_named_and_writes_the_copies(tmp_path, capsys):
    root = _suite(tmp_path)
    source = _image(tmp_path / "outside.png", 1024, "blue")

    assert sync_icons.main(["--category", "leaf", "--from", str(source), "--size", "256", "--size", "128"], root) == 0

    assert source.exists()   # an image from outside icons/ is left where it is
    assert _color(root / "icons" / "leaf" / "leaf-256.webp") == (0, 0, 255)
    assert _color(root / "icons" / "leaf" / "leaf-1024.webp") == (255, 0, 0)
    assert _color(root / "portal" / "images" / "apps" / "app.webp") == (0, 0, 255)
    assert _color(root / "apps" / "app" / "images" / "app-128.png") == (0, 0, 255)
    assert "updated: portal/images/apps/app.webp" in capsys.readouterr().out
    assert sync_icons.main(["--check"], root) == 0


@pytest.mark.parametrize("argv", [["--from", "x.png"], ["--category", "leaf"], ["--size", "512"],
                                  ["--check", "--category", "leaf", "--from", "x.png"], ["--size", "64"]])
def test_from_options_that_do_not_go_together_are_refused(argv):
    with pytest.raises(SystemExit) as stop:
        sync_icons.main(argv)
    assert stop.value.code == 2


def test_check_lists_what_is_not_converted(tmp_path, capsys):
    root = _suite(tmp_path)
    assert sync_icons.main([], root) == 0
    _image(root / "icons" / "leaf" / "leaf-512.png", 512, "blue")
    (root / "icons" / "leaf" / "leaf-512.webp").unlink()

    assert sync_icons.main(["--check"], root) == 1
    out = capsys.readouterr()
    assert "not converted: icons/leaf/leaf-512.png" in out.out
    assert "missing: icons/leaf/leaf-512.webp" in out.err
    assert (root / "icons" / "leaf" / "leaf-512.png").exists()
    assert sync_icons.main([], root) == 0
    assert sync_icons.main(["--check"], root) == 0
