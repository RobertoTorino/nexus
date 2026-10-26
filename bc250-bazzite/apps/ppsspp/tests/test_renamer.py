# SPDX-License-Identifier: GPL-3.0-or-later
"""The rename logic (renamer.py), as the standalone Bazzite UMD File Renamer had it: the eight naming templates,
the filename cleaning, the translation, the careful rename, which files may be renamed at all, and the standalone's
saved template read once."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import make_disc, make_pbp

from ppsspp_manager.games import Game, read_disc
from ppsspp_manager.renamer import (NamingTemplate, formatted_name, old_template_index, renamable,
                                          rename_file)


@pytest.mark.parametrize("template, expected", [
    (NamingTemplate.ID_TITLE, "ULJM05437 - Ever17"),
    (NamingTemplate.ID_TITLE_SPACE, "ULJM05437 Ever17"),
    (NamingTemplate.ID_TITLE_VERSION, "ULJM05437 - Ever17 - v1.01"),
    (NamingTemplate.TITLE_ID, "Ever17 - ULJM05437"),
    (NamingTemplate.TITLE_ID_SPACE, "Ever17 ULJM05437"),
    (NamingTemplate.TITLE_ONLY, "Ever17"),
    (NamingTemplate.TITLE_BRACKET_ID, "Ever17 [ULJM05437]"),
    (NamingTemplate.TITLE_BRACKET_ID_VERSION, "Ever17 [ULJM05437] [v1.01]"),
])
def test_formatted_name_templates(template, expected):
    game = Game(Path("/x/a.iso"), "Ever17", "ULJM05437", "1.01")
    assert formatted_name(game, template) == expected
    assert NamingTemplate.from_index(template.index) is template


def test_formatted_name_cleans_and_prefers_the_translation():
    game = Game(Path("/x/a.iso"), 'Crisis Core: Final Fantasy VII™ <dir|ty>?*"\\/', "ULUS10336", "v1.00")
    assert formatted_name(game) == "ULUS10336 - Crisis Core Final Fantasy VII dirty"
    assert formatted_name(game, NamingTemplate.ID_TITLE_VERSION).endswith(" - v1.00")   # no second "v"
    translated = "  Ever17: The Out of Infinity  "
    assert formatted_name(game, NamingTemplate.TITLE_ONLY, translated) == "Ever17 The Out of Infinity"
    assert NamingTemplate.from_index(99) is NamingTemplate.ID_TITLE


def test_what_may_be_renamed(tmp_path):
    iso = read_disc(make_disc(tmp_path / "a.iso", "A", "ULUS00001"))
    cso = read_disc(make_disc(tmp_path / "b.cso", "B", "ULUS00002", cso=True))
    chd = Game(tmp_path / "c.chd", "c", kind="chd")
    pbp = Game(make_pbp(tmp_path / "hb", "Homebrew"), "Homebrew", kind="pbp")
    assert renamable([iso, chd, cso, pbp]) == [iso, cso]        # a CHD is not read, a PBP must stay EBOOT.PBP


def test_rename_file(tmp_path):
    first = make_disc(tmp_path / "download (1).iso", "Crisis Core", "ULUS10336")
    make_disc(tmp_path / "ever17.iso", "Ever17", "ULJM05437")
    target = rename_file(first, "ULUS10336 - Crisis Core")
    assert target == tmp_path / "ULUS10336 - Crisis Core.iso"
    assert target.is_file() and not first.exists()

    # The same name again is fine; another file's name is never taken over.
    assert rename_file(target, "ULUS10336 - Crisis Core") == target
    assert rename_file(target, "ever17") is None
    assert (tmp_path / "ever17.iso").is_file() and target.is_file()

    # The extension is kept as it was, upper case included.
    ridge = make_disc(tmp_path / "ridge.ISO", "RIDGE RACER", "UCUS98604")
    assert rename_file(ridge, "UCUS98604 - RIDGE RACER") == tmp_path / "UCUS98604 - RIDGE RACER.ISO"


def test_the_standalones_template_is_read(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert old_template_index() is None                         # the standalone was never there
    ini = tmp_path / "config" / "bazzite-umd-file-renamer" / "bazzite-umd-file-renamer.ini"
    ini.parent.mkdir(parents=True)
    ini.write_text("[ui]\nnamingTemplate=7\n\n[paths]\nlastFolder=/games\n", encoding="utf-8")
    assert old_template_index() == 7
    ini.write_text("[ui]\nnamingTemplate=weird\n", encoding="utf-8")
    assert old_template_index() is None
