# SPDX-License-Identifier: GPL-3.0-or-later
"""The game scan (games.py): PARAM.SFO, the ISO 9660 and CSO readers, EBOOT.PBPs, the memory stick, updates left
out, a game found twice, depth, and the pictures from inside the images."""

from __future__ import annotations

from pathlib import Path

from conftest import cso_bytes, game_pictures, game_sfo, iso_bytes, make_disc, make_memstick, make_pbp, make_sfo, \
    pbp_bytes

from ppsspp_manager.games import (Game, installed, iso_file, memstick_game, pbp_part, ppsspp_home, read_disc,
                                        read_pbp, read_sfo, scan)


def test_param_sfo_is_read():
    fields = read_sfo(make_sfo({"BOOTABLE": 1, "CATEGORY": "UG", "DISC_ID": "ULUS10041",
                                "DISC_VERSION": "1.01", "TITLE": "Daxter™"}))
    assert fields == {"BOOTABLE": 1, "CATEGORY": "UG", "DISC_ID": "ULUS10041", "DISC_VERSION": "1.01",
                      "TITLE": "Daxter™"}
    assert read_sfo(b"") == {} and read_sfo(b"not a param.sfo at all") == {}
    assert read_sfo(make_sfo({"TITLE": "x"})[:30]) == {}                       # cut short: nothing, no error


def test_ppsspps_own_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert ppsspp_home() == tmp_path / "config" / "ppsspp"
    assert memstick_game(ppsspp_home()) == tmp_path / "config" / "ppsspp" / "PSP" / "GAME"


def test_an_iso_is_read(tmp_path):
    iso = make_disc(tmp_path / "Daxter.iso", "Daxter", "ULUS10041", "1.01")
    game = read_disc(iso)
    assert game == Game(iso, "Daxter", "ULUS10041", "1.01", "iso") and game.folder == tmp_path
    sfo = iso_file(iso, ("PSP_GAME", "PARAM.SFO"))
    assert read_sfo(sfo)["TITLE"] == "Daxter"
    assert iso_file(iso, ("PSP_GAME", "MISSING.PNG")) is None
    assert iso_file(iso, ("UMD_VIDEO", "PARAM.SFO")) is None


def test_a_cso_holds_the_same_iso(tmp_path):
    cso = make_disc(tmp_path / "Daxter.cso", "Daxter", "ULUS10041", pictures=True, cso=True)
    game = read_disc(cso)
    assert (game.title, game.disc_id, game.kind) == ("Daxter", "ULUS10041", "cso")
    # The same files as from the plain ISO, block by block: pictures larger than one block too.
    iso = make_disc(tmp_path / "plain.iso", "Daxter", "ULUS10041", pictures=True)
    for name in ("PARAM.SFO", "ICON0.PNG", "PIC1.PNG"):
        assert iso_file(cso, ("PSP_GAME", name)) == iso_file(iso, ("PSP_GAME", name)), name


def test_a_cso_with_an_alignment(tmp_path):
    iso = iso_bytes({"PARAM.SFO": game_sfo("Aligned", "ULES00001")})
    path = tmp_path / "a.cso"
    path.write_bytes(cso_bytes(iso, align=2))
    assert read_disc(path).title == "Aligned"


def test_files_that_are_no_psp_games(tmp_path):
    video = tmp_path / "film.iso"
    video.write_bytes(iso_bytes({"PARAM.SFO": game_sfo("Film", category="UV")}, root_name=b"UMD_VIDEO"))
    assert read_disc(video) is None                                            # a UMD video: no /PSP_GAME
    empty = tmp_path / "empty.iso"
    empty.write_bytes(b"\0" * 40000)
    assert read_disc(empty) is None
    short = tmp_path / "short.cso"
    short.write_bytes(b"CISO")
    assert read_disc(short) is None
    assert read_disc(tmp_path / "gone.iso") is None


def test_a_chd_is_listed_under_its_name(tmp_path):
    chd = tmp_path / "Lumines (USA).chd"
    chd.write_bytes(b"MComprHD" + b"\0" * 100)
    assert read_disc(chd) == Game(chd, "Lumines (USA)", kind="chd")
    assert read_disc(chd).picture("ICON0.PNG") is None                         # not looked into


def test_a_memory_stick_game_and_an_update(tmp_path):
    pbp = make_pbp(tmp_path / "GAME" / "Homebrew", "A Homebrew", version="2.00")
    game = read_pbp(pbp)
    assert game == Game(pbp, "A Homebrew", "", "2.00", "pbp")
    update = make_pbp(tmp_path / "GAME" / "ULUS10041", "Daxter", "ULUS10041", category="PG")
    assert read_pbp(update) is None                                            # PPSSPP lays it over the disc game
    (tmp_path / "GAME" / "broken").mkdir()
    (tmp_path / "GAME" / "broken" / "EBOOT.PBP").write_bytes(b"\0PBP cut short")
    assert read_pbp(tmp_path / "GAME" / "broken" / "EBOOT.PBP") is None
    assert read_pbp(tmp_path / "GAME" / "gone" / "EBOOT.PBP") is None


def test_a_title_with_line_breaks(tmp_path):
    iso = make_disc(tmp_path / "g.iso", "Metal Gear:\nPortable Ops")
    assert read_disc(iso).title == "Metal Gear: Portable Ops"


def test_the_memory_stick_games(memstick):
    game_dir = memstick_game(memstick)
    make_pbp(game_dir / "Homebrew", "A Homebrew")
    make_pbp(game_dir / "ULUS10041", "Daxter update", category="PG")
    (game_dir / "empty").mkdir()
    assert [g.title for g in installed(game_dir)] == ["A Homebrew"]
    assert installed(memstick / "missing") == []


def test_scan_finds_games_sorted_once_and_not_too_deep(tmp_path, memstick):
    root = tmp_path / "PSP"
    make_disc(root / "Zeta.iso", "Zeta", "ULUS00003")
    make_disc(root / "set" / "alpha.cso", "alpha", "ULUS00001", cso=True)
    make_disc(root / "a" / "b" / "c" / "d" / "e" / "five.iso", "Five deep", "ULUS00004")
    make_disc(root / "a" / "b" / "c" / "d" / "e" / "f" / "six.iso", "Too deep", "ULUS00005")
    make_disc(root / ".hidden" / "x.iso", "Hidden")
    make_pbp(root / "homebrew", "A Homebrew")
    (tmp_path / "link.iso").symlink_to(root / "Zeta.iso")
    game_dir = memstick_game(memstick)
    make_pbp(game_dir / "MSTICK", "Stick game")
    games = scan([root, tmp_path, tmp_path / "missing"], game_dir)
    assert [g.title for g in games] == ["A Homebrew", "alpha", "Five deep", "Stick game", "Zeta"]
    assert [g.kind for g in games] == ["pbp", "cso", "iso", "pbp", "iso"]


def test_the_games_own_pictures(tmp_path, qapp):
    iso = make_disc(tmp_path / "g.iso", "Game", pictures=True)
    game = read_disc(iso)
    pictures = game_pictures()
    assert game.picture("ICON0.PNG") == pictures["ICON0.PNG"]
    assert game.picture("PIC1.PNG") == pictures["PIC1.PNG"]
    assert read_disc(make_disc(tmp_path / "bare.iso", "Bare")).picture("ICON0.PNG") is None
    pbp = make_pbp(tmp_path / "hb", "Homebrew", pictures=True)
    assert read_pbp(pbp).picture("ICON0.PNG") == pictures["ICON0.PNG"]
    assert read_pbp(pbp).picture("PIC1.PNG") == pictures["PIC1.PNG"]
    bare = make_pbp(tmp_path / "bare", "Bare")
    assert read_pbp(bare).picture("ICON0.PNG") is None


def test_a_pbp_part_by_name():
    data = pbp_bytes(b"SFO", b"ICON", b"PIC")
    assert pbp_part(data, "PARAM.SFO") == b"SFO"
    assert pbp_part(data, "ICON0.PNG") == b"ICON"
    assert pbp_part(data, "PIC1.PNG") == b"PIC"
    assert pbp_part(data, "PIC0.PNG") is None
    assert pbp_part(b"no pbp", "PARAM.SFO") is None
