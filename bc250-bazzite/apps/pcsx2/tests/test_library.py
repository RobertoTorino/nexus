# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's own game folders (library.py): Games/PS2 in the home folder, made with its BIOS folder, and on each
removable drive that has one (owner, 03-11-2026: fixed folders, no folder choosing; the drives are core's)."""

from __future__ import annotations

from pcsx2_manager import library


def test_fixed_folders_are_made_and_found(tmp_path):
    (tmp_path / "sd" / "Games" / "PS2").mkdir(parents=True)
    (tmp_path / "stick").mkdir()
    folders = library.fixed(tmp_path, drives=lambda: [tmp_path / "sd", tmp_path / "stick", tmp_path / "gone"])
    assert folders == [tmp_path / "Games" / "PS2", tmp_path / "sd" / "Games" / "PS2"]
    assert library.bios_home(tmp_path) == tmp_path / "Games" / "PS2" / "BIOS" and library.bios_home(tmp_path).is_dir()
    assert library.fixed(tmp_path, drives=lambda: []) == [tmp_path / "Games" / "PS2"]


def test_removal_items_are_the_image_and_the_shortcut(tmp_path):
    from pcsx2_manager.games import Game
    game = Game(tmp_path / "Games" / "PS2" / "Two.iso", "Two", "SLUS-00002")
    items, why = library.removal_items(game, in_steam=False)
    assert why == "" and [(i.key, i.label, i.paths) for i in items] == [(str(game.file), "Two.iso (the disc image)", (game.file,))]
    items, _ = library.removal_items(game, in_steam=True)
    assert [i.key for i in items] == [str(game.file), library.STEAM_ITEM] and items[1].paths == ()
