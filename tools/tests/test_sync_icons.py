# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/sync_icons.py: a suite's category icons in icons/<category>/, converted from dropped images, and their
copies in the suite's apps and portal (icons/categories.toml). A Nexus tool since 02-11-2026: --suite names the
suite, and every function takes the suite's folder."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import sync_icons  # noqa: E402


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
    with pytest.raises(SystemExit, match="512 x 256 px, an icon of leaf must be square"):
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
def test_from_options_that_do_not_go_together_are_refused(argv, tmp_path):
    with pytest.raises(SystemExit) as stop:
        sync_icons.main(argv, _suite(tmp_path))
    assert stop.value.code == 2


def test_suite_picks_the_suite_and_one_without_category_icons_is_refused(tmp_path, monkeypatch, capsys):
    """--suite names the suite as every Nexus tool does (tools/suites.py); the default is the checkout's default
    suite. A suite whose apps take no category icons has no icons/categories.toml."""
    root = tmp_path / "nexus"
    suite = _suite(root / "bc250-bazzite")
    (suite / "portal").mkdir(exist_ok=True)
    (suite / "portal" / "apps.toml").write_text("", encoding="utf-8")
    other = root / "windows-portable"
    (other / "portal").mkdir(parents=True)
    (other / "portal" / "apps.toml").write_text("", encoding="utf-8")
    (other / "TAG_PREFIX").write_text("wp-\n", encoding="utf-8")
    monkeypatch.setattr(sync_icons.suites, "ROOT", root)

    assert sync_icons.main(["--check"]) == 0                       # the default suite: the one without a prefix
    assert sync_icons.main(["--check", "--suite", "bc250-bazzite"]) == 0
    with pytest.raises(SystemExit) as stop:                         # suites.suite() looks in the real checkout:
        sync_icons.main(["--check", "--root", str(other)])          # this one by its folder
    assert stop.value.code == 2 and "no icons/categories.toml" in capsys.readouterr().err
    with pytest.raises(SystemExit) as stop:
        sync_icons.main(["--check", "--suite", "nope"])
    assert stop.value.code == 2 and "no suite 'nope'" in capsys.readouterr().err


def _portable(tmp_path):
    """A checkout with a suite laid out as the Windows Portable Suite (05-11-2026): PNG icons, the gaming ones 2:1,
    no app tables (apps = "portal"), an app per category in the portal's apps.toml and the test app; its folder."""
    suite = tmp_path / "windows-portable"
    (suite / "icons" / "gaming").mkdir(parents=True)
    (suite / "icons" / "utilities").mkdir()
    (suite / "icons" / "categories.toml").write_text(
        '[icons]\nformat = "png"\napps = "portal"\n\n[icons.wide]\ngaming = 2\n', encoding="utf-8")
    for size in sync_icons.SIZES:
        Image.new("RGBA", (size, size // 2), "red").save(suite / "icons" / "gaming" / f"gaming-{size}.png")
        Image.new("RGBA", (size, size), "green").save(suite / "icons" / "utilities" / f"utilities-{size}.png")
    (suite / "portal").mkdir()
    (suite / "portal" / "apps.toml").write_text(
        '[apps.test]\ncategory = "utilities"\nrequired = true\n\n[apps.emu]\nname = "Emu"\ncategory = "gaming"\n\n'
        '[apps.tool]\nname = "Tool"\ncategory = "utilities"\n', encoding="utf-8")
    for key in ("emu", "tool"):
        package = suite / "apps" / key / f"{key}_manager"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text(f'APP_ID = "windows-portable-{key}"\n', encoding="utf-8")
    return suite


def test_a_suite_of_png_icons_and_wide_ones(tmp_path, capsys):
    """[icons] format = "png": every size a PNG; wide = {gaming = 2}: a 2:1 picture, each size its width, and a
    square one refused there; apps = "portal": tools/make_icons.py writes the copies, checked by their pixels (the
    wide icon centered on a transparent square for the window and Start-menu icons)."""
    suite = _portable(tmp_path)
    assert sync_icons.main(["--check"], suite) == 1                 # no copies yet
    assert "out of date: windows-portable/apps/emu/images/windows-portable-emu.webp" in capsys.readouterr().out
    assert sync_icons.main([], suite) == 0 and sync_icons.main(["--check"], suite) == 0
    with Image.open(suite / "apps" / "emu" / "images" / "windows-portable-emu-128.png") as icon:
        assert icon.size == (128, 128) and icon.getpixel((64, 10))[3] == 0 and icon.getpixel((64, 64))[:3] == (255, 0, 0)
    with Image.open(suite / "portal" / "images" / "apps" / "emu.webp") as tile:
        assert tile.size == (256, 128)                              # the tile keeps the wide picture

    _image(suite / "icons" / "gaming" / "new.png", 256, "blue", width=512)     # a wide picture dropped
    assert sync_icons.main([], suite) == 0
    for size in sync_icons.SIZES:
        with Image.open(suite / "icons" / "gaming" / f"gaming-{size}.png") as icon:
            assert icon.format == "PNG" and icon.size == (size, size // 2)
    assert not (suite / "icons" / "gaming" / "new.png").exists() and not list(suite.glob("icons/gaming/*.webp"))
    assert _color(suite / "apps" / "emu" / "images" / "windows-portable-emu.webp") == (0, 0, 255)
    assert sync_icons.main(["--check"], suite) == 0

    square = _image(tmp_path / "square.png", 512, "blue")
    with pytest.raises(SystemExit, match="an icon of gaming must be 2 times as wide as high"):
        sync_icons.main(["--category", "gaming", "--from", str(square)], suite)
    assert sync_icons.main(["--category", "utilities", "--from", str(square), "--size", "512"], suite) == 0
    with Image.open(suite / "icons" / "utilities" / "utilities-512.png") as icon:
        assert icon.format == "PNG" and icon.size == (512, 512)
    assert _color(suite / "apps" / "tool" / "images" / "windows-portable-tool.webp") == (0, 0, 255)

    _image(suite / "apps" / "tool" / "images" / "windows-portable-tool.webp", 512, "red")   # a copy changed by hand
    assert sync_icons.main(["--check"], suite) == 1
    assert "out of date: windows-portable/apps/tool/images/windows-portable-tool.webp" in capsys.readouterr().out


def test_the_real_suites_are_in_step():
    for name in ("bc250-bazzite", "windows-portable"):
        assert sync_icons.main(["--check"], ROOT / name) == 0, name


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
