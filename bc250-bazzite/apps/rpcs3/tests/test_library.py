# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's own game folders, the firmware file and Remove game's rows (library.py; owner, 03-11-2026)."""

from __future__ import annotations

from pathlib import Path

from rpcs3_manager import library
from rpcs3_manager.games import Game


def test_fixed_folders_and_the_firmware_file(tmp_path):
    assert library.fixed(tmp_path, drives=lambda: []) == [tmp_path / "Games" / "PS3"]
    assert library.firmware_home(tmp_path).is_dir() and library.firmware_file(tmp_path) is None
    (library.firmware_home(tmp_path) / "b.pup").write_bytes(b"x")
    (library.firmware_home(tmp_path) / "PS3UPDAT.PUP").write_bytes(b"y")
    assert library.firmware_file(tmp_path).name == "PS3UPDAT.PUP"               # the PS3's own name first
    assert library.file_key(library.firmware_file(tmp_path)).startswith("PS3UPDAT.PUP|1|")


def test_removal_rows(tmp_path):
    games, hdd0 = tmp_path / "Games" / "PS3", tmp_path / "rpcs3" / "dev_hdd0" / "game"
    disc = Game(games / "one" / "PS3_GAME" / "USRDIR" / "EBOOT.BIN", "One", "BLUS00001", disc=True)
    items, why = library.removal_items(disc, [games], [disc], hdd0, in_steam=True)
    assert why == "" and [i.label for i in items] == ["one (the disc game's folder)", "Its shortcut in Steam"]
    (hdd0 / "BLUS00001").mkdir(parents=True)                                   # its update in RPCS3's games folder
    items, _ = library.removal_items(disc, [games], [disc], hdd0, False)
    assert [i.paths for i in items] == [(games / "one",), (hdd0 / "BLUS00001",)]
    pkg = Game(hdd0 / "NPUB00002" / "USRDIR" / "EBOOT.BIN", "Two", "NPUB00002")
    items, _ = library.removal_items(pkg, [games], [pkg], hdd0, False)
    assert [i.paths for i in items] == [(hdd0 / "NPUB00002",)]
    elsewhere = Game(tmp_path / "other" / "three" / "PS3_GAME" / "USRDIR" / "EBOOT.BIN", "Three", "BLUS00003", disc=True)
    items, why = library.removal_items(elsewhere, [games], [elsewhere], hdd0, False)
    assert items == [] and "outside the app's Games/PS3 folders" in why
