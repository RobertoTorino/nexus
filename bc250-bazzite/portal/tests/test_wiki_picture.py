# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/portal_screenshot.py: the portal's picture on the wiki's home page, taken from the portal itself."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from bc250_portal import MANIFEST
from bc250_portal.manifest import load
from conftest import SUITE

spec = importlib.util.spec_from_file_location("portal_screenshot", SUITE / "tools" / "portal_screenshot.py")
shot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shot)


def test_an_older_version_for_the_update():
    assert [shot.older(v) for v in ("0.1.10", "0.3.0", "2.0.0")] == ["0.1.9", "0.2.0", "1.0.0"]


def test_the_picture_shows_the_window_in_the_demo_state(qapp, home, settings_dir):
    image = shot.render(home)
    assert (image.width(), image.height()) == (round(shot.SIZE[0] * shot.SCALE), round(shot.SIZE[1] * shot.SCALE))
    assert len({image.pixel(x, y) for x in range(0, image.width(), 40) for y in range(0, image.height(), 40)}) > 50
    detect = {e.key: Path(e.detect[0].replace("~", str(home), 1)) for e in load(MANIFEST)}
    assert detect["gpu"].is_file() and not detect["oc"].exists()            # one installed, one not


def test_the_default_picture_is_the_one_the_wiki_shows():
    assert shot.OUT.relative_to(SUITE / "docs").as_posix() in (SUITE / "docs" / "index.md").read_text(encoding="utf-8")
