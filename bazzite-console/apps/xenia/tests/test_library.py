# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's own game folders and Remove game's rows (library.py; owner, 03-11-2026)."""

from __future__ import annotations

from xenia_manager import library
from xenia_manager.games import Game


def test_fixed_folders(tmp_path):
    assert library.fixed(tmp_path, drives=lambda: []) == [tmp_path / "Games" / "XBOX360"]


def test_removal_rows(tmp_path):
    games = tmp_path / "Games" / "XBOX360"
    iso = Game(games / "One.iso", "One", "4D5307E6", kind="iso")
    items, why = library.removal_items(iso, [games], [iso], in_steam=True)
    assert why == "" and [i.label for i in items] == ["One.iso (the game)", "Its shortcut in Steam"]
    unpacked = Game(games / "Two" / "default.xex", "Two", "4D5307E7", kind="xex")
    items, _ = library.removal_items(unpacked, [games], [unpacked], False)
    assert [i.paths for i in items] == [(games / "Two",)]
    console = games / "4D5307E8"
    for part in ("00007000", "000B0000", "00000002"):
        (console / part).mkdir(parents=True)
    god = Game(console / "00007000" / "ABCDEF0123456789", "Three", "4D5307E8", kind="god")
    items, _ = library.removal_items(god, [games], [god], False)
    assert [i.label for i in items] == ["the game (4D5307E8/00007000)", "its add-ons (4D5307E8/00000002)",
                                        "its title updates (4D5307E8/000B0000)"]
    for part in ("00007000", "000B0000", "00000002"):
        (console / part).rmdir()
    library.tidy(god)
    assert not console.exists()
    top = Game(games / "default.xex", "Top", "4D5307E9", kind="xex")
    assert "one of the app's game folders itself" in library.removal_items(top, [games], [top], False)[1]
