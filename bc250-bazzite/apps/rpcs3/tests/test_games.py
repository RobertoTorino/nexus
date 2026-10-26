# SPDX-License-Identifier: GPL-3.0-or-later
"""The game scan (games.py): PARAM.SFO, disc games and installed games, updates left out, games RPCS3 knows, a game
found twice, depth, and PS3_DISC.SFB."""

from __future__ import annotations

from conftest import make_disc_game, make_hdd_game, make_sfo

from rpcs3_manager.games import Game, installed, known, read_game, read_sfo, scan


def test_param_sfo_is_read():
    fields = read_sfo(make_sfo({"APP_VER": "01.02", "ATTRIBUTE": 32, "CATEGORY": "DG",
                                "TITLE": "Demon's Souls™", "TITLE_ID": "BLUS30443"}))
    assert fields == {"APP_VER": "01.02", "ATTRIBUTE": 32, "CATEGORY": "DG", "TITLE": "Demon's Souls™",
                      "TITLE_ID": "BLUS30443"}
    assert read_sfo(b"") == {} and read_sfo(b"not a param.sfo at all") == {}
    assert read_sfo(make_sfo({"TITLE": "x"})[:30]) == {}                       # cut short: nothing, no error


def test_a_disc_game_and_an_installed_game(tmp_path):
    eboot = make_disc_game(tmp_path / "Demon's Souls", "Demon's Souls", "BLUS30443", "01.02")
    game = read_game(tmp_path / "Demon's Souls" / "PS3_GAME", disc=True)
    assert game == Game(eboot, "Demon's Souls", "BLUS30443", "01.02", disc=True)
    assert game.folder == tmp_path / "Demon's Souls" and game.content == tmp_path / "Demon's Souls" / "PS3_GAME"
    eboot = make_hdd_game(tmp_path / "NPUB30001", "Flower", "NPUB30001")
    game = read_game(tmp_path / "NPUB30001")
    assert game == Game(eboot, "Flower", "NPUB30001", "01.00") and game.folder == tmp_path / "NPUB30001"


def test_a_title_with_line_breaks(tmp_path):
    make_hdd_game(tmp_path / "g", "Uncharted:\nDrake's Fortune")
    assert read_game(tmp_path / "g").title == "Uncharted: Drake's Fortune"


def test_updates_and_unfinished_folders_are_not_games(tmp_path):
    make_hdd_game(tmp_path / "BLUS30443", "Demon's Souls", "BLUS30443", "01.04", category="GD")   # its update
    assert read_game(tmp_path / "BLUS30443") is None
    make_hdd_game(tmp_path / "half", eboot=False)
    assert read_game(tmp_path / "half") is None
    assert read_game(tmp_path / "nothing") is None


def test_the_installed_games_and_those_rpcs3_knows(tmp_path):
    hdd0 = tmp_path / "rpcs3" / "dev_hdd0" / "game"
    make_hdd_game(hdd0 / "NPUB30001", "Flower", "NPUB30001")
    make_hdd_game(hdd0 / "BLUS30443", "Demon's Souls", "BLUS30443", category="GD")
    hdd0.joinpath("$locks").mkdir()
    assert [g.title for g in installed(hdd0)] == ["Flower"]
    assert installed(tmp_path / "missing") == []
    disc = make_disc_game(tmp_path / "discs" / "DeS", "Demon's Souls", "BLUS30443")
    # games.yml as RPCS3 writes it: the disc's folder, or its PS3_GAME as "<folder>/./" when it started from dev_hdd0
    games = known([f"{tmp_path}/discs/DeS/", f"{tmp_path}/discs/DeS/PS3_GAME/./", f"{tmp_path}/gone/",
                   f"{tmp_path}/game.iso"])
    assert [g.eboot for g in games] == [disc, disc]


def test_scan_finds_games_sorted_once_and_not_too_deep(tmp_path):
    root = tmp_path / "PS3"
    make_disc_game(root / "zeta", "Zeta", "BLUS00003")
    make_disc_game(root / "set" / "alpha", "alpha", "BLUS00001")
    make_disc_game(root / "a" / "b" / "c" / "d" / "deep", "Five deep", "BLUS00004")     # root/1/2/3/4/5/PS3_GAME
    make_disc_game(root / "a" / "b" / "c" / "d" / "e" / "deeper", "Too deep", "BLUS00005")
    make_disc_game(root / ".hidden" / "x", "Hidden")
    (tmp_path / "link").symlink_to(root / "zeta")
    hdd0 = tmp_path / "dev_hdd0" / "game"
    make_hdd_game(hdd0 / "NPUB30001", "Flower", "NPUB30001")
    games = scan([root, root / "zeta", tmp_path / "link", tmp_path / "missing"], hdd0, [f"{root}/zeta/"])
    assert [g.title for g in games] == ["alpha", "Five deep", "Flower", "Zeta"]      # by title, case aside
    assert [g.disc for g in games] == [True, True, False, True]


def test_a_disc_game_needs_its_ps3_disc_sfb(tmp_path):
    for name, sfb in (("good", b".SFB\0\0\0\x01"), ("none", None), ("damaged", b"\0\0\0\0")):
        make_disc_game(tmp_path / name, name, sfb=sfb)
    startable = {g.title: g.startable for g in scan([tmp_path])}
    assert startable == {"good": True, "none": False, "damaged": False}
    make_hdd_game(tmp_path / "hdd" / "NPUB30001")
    assert read_game(tmp_path / "hdd" / "NPUB30001").startable                     # an installed game has none


def test_the_games_own_pictures(tmp_path, qapp):
    make_disc_game(tmp_path / "g", "Game", pictures=True)
    game = read_game(tmp_path / "g" / "PS3_GAME", disc=True)
    assert game.picture("ICON0.PNG") == tmp_path / "g" / "PS3_GAME" / "ICON0.PNG"
    assert game.picture("PIC0.PNG") is None
