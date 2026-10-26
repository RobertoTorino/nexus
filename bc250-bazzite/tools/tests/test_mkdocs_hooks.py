# SPDX-License-Identifier: GPL-3.0-or-later
"""The wiki's hook: a WebP copy of each app picture a page shows, the pages pointed at it, and the PNG kept for
pictures without a copy (no Pillow, or not shown)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("mkdocs.structure.files")   # the real MkDocs: tools/mkdocs/ (this hook's folder) is importable as "mkdocs" too
SUITE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("wiki_hooks", SUITE / "tools" / "mkdocs" / "hooks.py")
hooks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hooks)


def test_webp_copy_keeps_the_picture(tmp_path):
    image = pytest.importorskip("PIL.Image")
    png = tmp_path / "icon.png"
    image.new("RGBA", (64, 64), (88, 53, 206, 0)).save(png)
    data = hooks.to_webp(png, png.stat().st_mtime)
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    out = tmp_path / "icon.webp"
    out.write_bytes(data)
    with image.open(out) as copy:
        assert copy.size == (64, 64) and copy.getpixel((1, 1))[3] == 0      # transparency kept


def test_pages_point_at_the_copies_only(monkeypatch):
    monkeypatch.setattr(hooks, "_webp", {"assets/apps/gpu.png", "assets/ace/bc250-ace-queues.png"})
    text = ("![](../assets/apps/gpu.png) ![](../assets/ace/bc250-ace-queues.png){ .app-logo } "
            "![](../assets/apps/portal.png) ![](../images/home/portal.webp)")
    assert hooks.on_page_markdown(text, None, None, None) == (
        "![](../assets/apps/gpu.webp) ![](../assets/ace/bc250-ace-queues.webp){ .app-logo } "
        "![](../assets/apps/portal.png) ![](../images/home/portal.webp)")


def test_only_pictures_a_page_names_are_converted():
    wanted = hooks.shown(str(SUITE / "docs"))
    assert "assets/suite/bc250-release-128.png" in wanted
    assert not any("/steam/" in uri for uri in wanted)      # Console Link's Steam artwork is not on any page


def test_every_app_chapter_shows_its_icon():
    """An app's chapter starts with the app's icon beside its heading (two chapters once lacked it)."""
    docs = SUITE / "docs"
    chapters = [p for folder in ("apps", "other-tools") for p in (docs / folder).glob("*.md") if p.name not in ("index.md", "categories.md", "covers.md")]
    missing = [p.relative_to(docs).as_posix() for p in sorted(chapters) if "{ .app-logo }" not in p.read_text("utf-8")]
    assert not missing, f"no icon beside the heading: {', '.join(missing)}"


def test_the_next_controller_at_each_portal_release(tmp_path):
    (tmp_path / "controllers.toml").write_text(
        '[[controller]]\nfile = "a.webp"\nalt = "A"\n\n[[controller]]\nfile = "b.webp"\nalt = "B"\n')
    changelog = tmp_path / "CHANGELOG"
    chosen = []
    for release in range(4):
        changelog.write_text("".join(f"Changelog: x\n\nRelease 1.{n}.0. Pins a.\n\n" for n in range(release))
                             + "Changelog: x\n\nAdded. Not a release.\n")
        chosen.append(hooks.controller(tmp_path, changelog)[0])
    assert chosen == ["a.webp", "b.webp", "a.webp", "b.webp"]


def test_the_home_page_gets_the_controller_of_this_release(monkeypatch):
    monkeypatch.setattr(hooks, "controller", lambda: ("b.webp", "A DualSense controller"))
    text = "![A DualShock 4 controller](images/home/controllers/ds4.webp){ .home-hero__controller }"
    assert hooks.on_page_markdown(text, None, None, None) == (
        "![A DualSense controller](images/home/controllers/b.webp){ .home-hero__controller }")
    assert "images/home/controllers/" in (SUITE / "docs" / "index.md").read_text(encoding="utf-8")


def test_every_controller_picture_fits_beside_the_board():
    """Listed once each, every picture in the folder listed, WebP with transparency at the size of the first."""
    image = pytest.importorskip("PIL.Image")
    listed = hooks.controllers()
    files = [file for file, _ in listed]
    assert len(files) == len(set(files)) and all(alt.strip() for _, alt in listed)
    assert sorted(files) == sorted(p.name for p in hooks.CONTROLLERS.iterdir() if p.name != "controllers.toml")
    for file in files:
        with image.open(hooks.CONTROLLERS / file) as picture:
            assert (picture.format, picture.mode, picture.size) == ("WEBP", "RGBA", (1295, 1600)), file
