# SPDX-License-Identifier: GPL-3.0-or-later
"""A game renamed or moved after it was put in Steam (renamed.py): what a game is (its code, else its file's size),
what the app keeps of its games in Steam, and the game found again taking the mark of the one no longer found, only
when it is the one game that matches."""

from __future__ import annotations

from PyQt6.QtCore import QSettings

from bc250_core import renamed


def test_a_game_is_its_code_else_its_size(tmp_path):
    iso = tmp_path / "Halo 3.iso"
    iso.write_bytes(b"x" * 1234)
    assert renamed.identity("4d5307e6", iso) == "code:4D5307E6"
    assert renamed.identity("", iso) == "size:1234"
    assert renamed.identity("", tmp_path / "gone.iso") == ""


def test_the_games_in_steam_are_kept_and_the_ones_no_longer_in_steam_forgotten(tmp_path):
    settings = QSettings(str(tmp_path / "app.ini"), QSettings.Format.IniFormat)
    assert renamed.load(settings) == {}
    renamed.remember(settings, {}, {"A.iso": "size:1", "B.iso": "size:2"}, {"A.iso"})
    assert renamed.load(settings) == {"A.iso": "size:1"}                # B is not in Steam
    renamed.remember(settings, renamed.load(settings), {}, {"A.iso", "C.iso"})
    assert renamed.load(settings) == {"A.iso": "size:1"}                # A not found now: kept, to be looked for
    renamed.remember(settings, renamed.load(settings), {}, set())
    assert renamed.load(settings) == {}                                 # taken out of Steam: forgotten
    settings.setValue(renamed.KEY, "not json")
    assert renamed.load(settings) == {}


def test_a_game_found_again_takes_the_mark_when_it_is_the_only_match():
    known = {"Old.iso": "size:5", "Game\EBOOT.BIN": "code:CUSA1", "Twin.iso": "size:9"}
    found = {"New.iso": "size:5", "Moved\EBOOT.BIN": "code:CUSA1", "Other.iso": "size:7",
             "Twin A.iso": "size:9", "Twin B.iso": "size:9"}
    in_steam = {"Old.iso", "Game\EBOOT.BIN", "Twin.iso"}
    assert renamed.follow(known, found, in_steam) == {"New.iso": "Old.iso", "Moved\EBOOT.BIN": "Game\EBOOT.BIN"}
    assert renamed.follow(known, {**found, "Old.iso": "size:5"}, in_steam)["Moved\EBOOT.BIN"]   # Old still there
    assert "New.iso" not in renamed.follow(known, {**found, "Old.iso": "size:5"}, in_steam)
    assert renamed.follow(known, found, {"Old.iso", "New.iso"}) == {}  # the new one is in Steam itself
    assert renamed.follow({}, found, in_steam) == {}                    # nothing known: nothing follows
    assert renamed.said(["Halo 3", "Braid"]).startswith("Found again under a new name or in another folder, with "
                                                        "its Steam mark: Halo 3, Braid.")
