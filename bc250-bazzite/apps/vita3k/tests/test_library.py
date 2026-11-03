# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's own folder, the firmware files and Remove game's rows (library.py; owner, 03-11-2026)."""

from __future__ import annotations

from vita3k_manager import library
from vita3k_manager.games import Game


def test_fixed_folder_and_the_firmware_files(tmp_path):
    assert library.fixed(tmp_path, drives=lambda: []) == [tmp_path / "Games" / "Vita"]
    home = library.firmware_home(tmp_path)
    assert home.is_dir() and library.firmware_files(tmp_path) == []
    (home / "fonts").mkdir()
    (home / "fonts" / "PSP2UPDAT.PUP").write_bytes(b"\0" * 10)
    (home / "PSP2UPDAT.PUP").write_bytes(b"\0" * 30)
    (home / "notes.txt").write_text("")
    assert [p.stat().st_size for p in library.firmware_files(tmp_path)] == [30, 10]     # the largest first


def test_removal_rows(tmp_path):
    fs = tmp_path / "storage"
    game = Game(fs / "ux0" / "app" / "PCSE00002", "Two", "PCSE00002")
    (fs / "ux0" / "patch" / "PCSE00002").mkdir(parents=True)
    items, why = library.removal_items(game, fs, in_steam=True)
    assert why == "" and [i.label for i in items] == ["The game, ux0/app/PCSE00002", "Its update, ux0/patch/PCSE00002",
                                                       "Its shortcut in Steam"]
    elsewhere = Game(tmp_path / "dump" / "PCSE00003", "Three", "PCSE00003")
    items, why = library.removal_items(elsewhere, fs, False)
    assert items == [] and "is not in Vita3K's storage" in why
