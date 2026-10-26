# SPDX-License-Identifier: GPL-3.0-or-later
"""The game scan (games.py): param.sfo, titles from it or from the folder, updates and mods left out, depth."""

from __future__ import annotations

from conftest import make_game, make_sfo

from shadps4_manager.games import Game, read_game, read_sfo, scan


def test_param_sfo_is_read():
    fields = read_sfo(make_sfo({"APP_VER": "01.05", "ATTRIBUTE": 32, "TITLE": "Bloodborne™", "TITLE_ID": "CUSA00900"}))
    assert fields == {"APP_VER": "01.05", "ATTRIBUTE": 32, "TITLE": "Bloodborne™", "TITLE_ID": "CUSA00900"}
    assert read_sfo(b"") == {} and read_sfo(b"not a param.sfo at all") == {}
    assert read_sfo(make_sfo({"TITLE": "x"})[:30]) == {}                       # cut short: nothing, no error


def test_a_game_from_its_param_sfo_or_its_folder(tmp_path):
    eboot = make_game(tmp_path / "CUSA00900", "Bloodborne", "CUSA00900", "01.09")
    assert read_game(eboot) == Game(eboot, "Bloodborne", "CUSA00900", "01.09")
    bare = make_game(tmp_path / "[PS4] Some Game", None)
    assert read_game(bare) == Game(bare, "Some Game")                           # as Nexus: the folder, no tag


def test_updates_mods_and_add_ons_are_not_games(tmp_path):
    assert read_game(make_game(tmp_path / "b", "DLC", category="ac")) is None
    assert read_game(make_game(tmp_path / "CUSA00900-UPDATE", "Bloodborne")) is None
    assert read_game(make_game(tmp_path / "CUSA00900-patch", None)) is None
    assert read_game(make_game(tmp_path / "CUSA00900-mods", None)) is None


def test_scan_finds_games_sorted_once_and_not_too_deep(tmp_path):
    root = tmp_path / "games"
    make_game(root / "zeta", "Zeta", "CUSA00003")
    make_game(root / "set" / "alpha", "alpha", "CUSA00001")
    make_game(root / "a" / "b" / "c" / "d" / "deep", "Five deep", "CUSA00004")          # root/1/2/3/4/5/eboot.bin
    make_game(root / "a" / "b" / "c" / "d" / "e" / "deeper", "Too deep", "CUSA00005")
    make_game(root / "zeta-UPDATE", "Zeta", "CUSA00003", category="gp")
    make_game(root / ".hidden" / "x", "Hidden")
    (tmp_path / "link").symlink_to(root / "zeta")
    games = scan([root, root / "zeta", tmp_path / "link", tmp_path / "missing"])
    assert [g.title for g in games] == ["alpha", "Five deep", "Zeta"]           # by title, case aside


def test_an_update_beside_its_game_is_left_out(tmp_path):
    root = tmp_path / "games"
    make_game(root / "base", "Bloodborne", "CUSA00900", "01.00")
    make_game(root / "update", "Bloodborne", "CUSA00900", "01.09", category="gp")
    assert [(g.title, g.version) for g in scan([root])] == [("Bloodborne", "01.00")]


def test_a_game_with_its_update_in_it_is_a_game(tmp_path):
    """Dumped from a PS4 with the update installed: param.sfo says "gp", and there is no other game with its ID
    (LUMINES REMASTERED, CUSA11624, on the owner's board, 14-10-2026)."""
    eboot = make_game(tmp_path / "games" / "CUSA11624", "LUMINES REMASTERED", "CUSA11624", "01.05", category="gp")
    assert scan([tmp_path / "games"]) == [Game(eboot, "LUMINES REMASTERED", "CUSA11624", "01.05")]
    assert read_game(eboot).patched


def test_the_games_own_pictures(tmp_path, qapp):
    game = read_game(make_game(tmp_path / "g", "Game", pictures=True))
    assert game.picture("icon0.png") == tmp_path / "g" / "sce_sys" / "icon0.png"
    assert game.picture("pic0.png") is None and game.folder == tmp_path / "g"
