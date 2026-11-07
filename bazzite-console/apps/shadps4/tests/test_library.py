# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's own game folders and Remove game's rows (library.py; owner, 03-11-2026)."""

from __future__ import annotations

from shadps4_manager import library
from shadps4_manager.games import Game


def test_fixed_folders(tmp_path):
    assert library.fixed(tmp_path, drives=lambda: []) == [tmp_path / "Games" / "PS4"]
    assert library.modules_home(tmp_path) == tmp_path / "Games" / "PS4" / "Modules" and library.modules_home(tmp_path).is_dir()


def test_removal_rows(tmp_path):
    games = tmp_path / "Games" / "PS4"
    game = Game(games / "one" / "eboot.bin", "One", "CUSA00001")
    (games / "one-UPDATE").mkdir(parents=True)
    (games / "one-mods").mkdir()
    items, why = library.removal_items(game, [games], [game], in_steam=True)
    assert why == "" and [i.label for i in items] == ["one (the game's folder)", "one-UPDATE (its update)",
                                                       "one-mods (its mods)", "Its shortcut in Steam"]
    top = Game(games / "eboot.bin", "Top", "CUSA00009")
    assert library.removal_items(top, [games], [top], False)[1].startswith("Top is in PS4, one of the app's game folders itself")
    inner = Game(games / "one" / "dlc" / "eboot.bin", "Inner", "CUSA00002")
    assert library.removal_items(game, [games], [game, inner], False) == ([], "one holds another game too (Inner): delete One's files by hand.")
