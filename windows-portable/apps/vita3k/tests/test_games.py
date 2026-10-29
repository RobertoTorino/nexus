# SPDX-License-Identifier: GPL-3.0-or-later
"""The games Vita3K has installed (games.py), as the BC250 suite's Vita3K Manager's are tested: param.sfo read, the
title as Vita3K shows it, a folder without its param.sfo or eboot.bin left out, the sort order, and a picture that
cannot be read."""

from __future__ import annotations

from pathlib import Path

from conftest import make_game, make_sfo

from vita3k_manager.games import Game, installed, read_game, read_sfo


def test_read_sfo():
    sfo = read_sfo(make_sfo({"APP_VER": "01.05", "ATTRIBUTE": 32768, "TITLE": "Gravity Rush"}))
    assert sfo == {"APP_VER": "01.05", "ATTRIBUTE": 32768, "TITLE": "Gravity Rush"}
    assert read_sfo(b"") == {} and read_sfo(b"\0PSF" + b"\xff" * 30) == {} and read_sfo(b"not one at all, no") == {}


def test_a_game_as_vita3k_shows_it(tmp_path):
    folder = make_game(tmp_path, "Persona 4\nGolden", "PCSB00245", "01.01")
    game = read_game(folder)
    assert (game.title, game.title_id, game.version, game.name) == ("Persona 4 Golden", "PCSB00245", "1.01",
                                                                     "PCSB00245")
    assert game.picture("icon0.png") is None
    pictured = read_game(make_game(tmp_path, "Two", "PCSE00002", pictures=True))
    assert pictured.picture("icon0.png") == pictured.folder / "sce_sys" / "icon0.png"
    assert pictured.picture("pic0.png").is_file()


def test_a_picture_that_cannot_be_read_is_none(monkeypatch):
    """Windows raises for a drive it cannot read (an empty card slot keeps its letter: WinError 1005) rather than
    answer; the game then has no picture, and Update Steam still takes its shortcut out."""
    def unreadable(self):
        raise OSError(1005, "The volume does not contain a recognized file system")
    monkeypatch.setattr(Path, "is_file", unreadable)
    assert Game(Path("E:/ux0/app/PCSB00245"), "Gone").picture("icon0.png") is None


def test_what_is_not_a_game(tmp_path):
    assert read_game(make_game(tmp_path, "No eboot", "PCSB00003", eboot=False)) is None
    broken = tmp_path / "ux0" / "app" / "PCSB00004"
    (broken / "sce_sys").mkdir(parents=True)
    (broken / "eboot.bin").write_bytes(b"SCE\0")
    assert read_game(broken) is None                                               # no param.sfo
    (broken / "sce_sys" / "param.sfo").write_bytes(b"rubbish")
    assert read_game(broken) is None


def test_the_installed_games(tmp_path):
    assert installed(tmp_path) == []                                              # no ux0\app yet
    make_game(tmp_path, "zeta", "PCSB00010")
    make_game(tmp_path, "Alpha", "PCSE00020")
    make_game(tmp_path, "Homebrew", "VITASHELL", folder="VITASHELL")
    make_game(tmp_path, "Half", "PCSB00030", eboot=False)
    make_game(tmp_path, "An update", "PCSB00010", kind="patch")                   # not a game to start
    (tmp_path / "ux0" / "app" / "stray.txt").write_text("")
    assert [g.title for g in installed(tmp_path)] == ["Alpha", "Homebrew", "zeta"]
