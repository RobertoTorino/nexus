# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's own game folders and Remove game's rows (library.py; owner, 03-11-2026)."""

from __future__ import annotations

from pathlib import Path

from ppsspp_manager import library
from ppsspp_manager.games import Game


def test_fixed_folders(tmp_path):
    (tmp_path / "sd" / "Games" / "PSP").mkdir(parents=True)
    assert library.fixed(tmp_path, drives=lambda: [tmp_path / "sd", tmp_path / "x"]) == [
        tmp_path / "Games" / "PSP", tmp_path / "sd" / "Games" / "PSP"]


def test_removal_rows(tmp_path):
    games = tmp_path / "Games" / "PSP"
    iso = Game(games / "one.iso", "One", "ULUS00001", kind="iso")
    items, why = library.removal_items(iso, [games], [iso], in_steam=True)
    assert why == "" and [i.label for i in items] == ["one.iso (the disc image)", "Its shortcut in Steam"]
    pbp = Game(games / "Homebrew" / "EBOOT.PBP", "Brew", kind="pbp")
    items, why = library.removal_items(pbp, [games], [pbp], in_steam=False)
    assert [i.paths for i in items] == [(games / "Homebrew",)]
    top = Game(games / "EBOOT.PBP", "Top", kind="pbp")                          # in the game folder itself
    assert library.removal_items(top, [games], [top], False) == ([], "Top is in PSP, one of the app's game folders itself: delete its files by hand.")
    other = Game(games / "Homebrew" / "more" / "EBOOT.PBP", "More", kind="pbp")
    items, why = library.removal_items(pbp, [games], [pbp, other], False)
    assert items == [] and why == "Homebrew holds another game too (More): delete Brew's files by hand."
