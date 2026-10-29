# SPDX-License-Identifier: GPL-3.0-or-later
"""The Steam shortcuts (shortcuts.py) on Windows, as shadPS4 Manager's are tested: Vita3K's program with the game's
title ID, started in its folder, paths in double quotes as Steam writes them, "[PS Vita] <title>" names made unique,
the app's own shortcuts told from others, adding and taking out beside other shortcuts in a Steam folder made in a
temp folder, and the artwork from the game's own pictures (the BC250 suite's Vita3K Manager's tests)."""

from __future__ import annotations

from pathlib import Path

from conftest import make_game

from bc250_core import steam
from vita3k_manager import LOGO_PATH, shortcuts
from vita3k_manager.games import Game, read_game

PROGRAM = Path(r"C:\Users\me\AppData\Local\windows-portable-suite\windows-portable-vita3k\emulator\Vita3K.exe")
PERSONA = Game(Path(r"C:\x\portable\fs\ux0\app\PCSB00245"), "Persona 4 Golden", "PCSB00245")
OTHER = {"appid": -1234, "AppName": "RetroArch", "Exe": '"C:\\RetroArch\\retroarch.exe"',
         "LaunchOptions": "--fullscreen x"}


def _steam(tmp_path: Path) -> Path:
    config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    config.mkdir(parents=True)
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": OTHER}}))
    return tmp_path / "Steam"


def test_a_shortcut_starts_vita3k_with_the_game():
    item = shortcuts.entry(PERSONA, "[PS Vita] Persona 4 Golden", PROGRAM, LOGO_PATH)
    assert item["Exe"] == f'"{PROGRAM}"' and item["StartDir"] == f'"{PROGRAM.parent}\\"'
    assert item["LaunchOptions"] == "-r PCSB00245"
    assert item["tags"] == {"0": "PS Vita", "1": "Vita3K Manager"}
    assert shortcuts.ours(item) and shortcuts.for_game(PERSONA)(item)
    assert not shortcuts.for_game(Game(Path(r"C:\x\PCSE00001"), "Other"))(item)
    lower = {key.lower(): value for key, value in item.items()}                            # as some Steam writes it
    assert shortcuts.ours(lower)
    bc250 = {"Exe": '"/home/me/.local/bin/bc250-vita3k-run"', "LaunchOptions": "--frontend sdl -r PCSB00245"}
    assert not shortcuts.ours(bc250)                                             # the BC250 suite's is not this app's


def test_other_shortcuts_are_not_ours():
    assert not shortcuts.ours(OTHER)
    assert not shortcuts.ours({"Exe": '"C:\\Games\\other.exe"', "LaunchOptions": "-r PCSB00245"})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": ""})              # Vita3K alone, no game
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": "-r"})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": "-r --fullscreen"})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": '-r "unclosed'})


def test_names_are_unique():
    a = Game(Path(r"C:\fs\ux0\app\PCSB00001"), "Game", "PCSB00001")
    b = Game(Path(r"C:\fs\ux0\app\PCSE00002"), "Game", "PCSE00002")
    c = Game(Path(r"C:\fs\ux0\app\PCSB00003"), "Other", "PCSB00003")
    assert shortcuts.names([a, b, c]) == {"PCSB00001": "[PS Vita] Game (PCSB00001)",
                                          "PCSE00002": "[PS Vita] Game (PCSE00002)", "PCSB00003": "[PS Vita] Other"}


def test_add_then_take_out(tmp_path, qapp):
    folder = _steam(tmp_path)
    first = read_game(make_game(tmp_path / "fs", "One", "PCSB00001", pictures=True))
    second = read_game(make_game(tmp_path / "fs", "Two", "PCSB00002"))
    numbers = steam.write_shortcuts(folder, shortcuts.changes([first, second], [], PROGRAM, LOGO_PATH, {}))
    assert shortcuts.in_steam(folder) == {"PCSB00001": "[PS Vita] One", "PCSB00002": "[PS Vita] Two"}
    item = next(i for i in steam.shortcuts(folder) if i.get("AppName") == "[PS Vita] One")
    assert item["icon"] == str(first.picture("icon0.png"))                       # the game's own icon
    config = steam.user_folders(folder)[0]
    assert sorted(p.name for p in (config / "grid").iterdir()) == sorted(
        [f"{n}{suffix}.png" for n in numbers for suffix in ("p", "", "_hero")] + [f"{numbers[0]}_logo.png"])
    existing = shortcuts.in_steam(folder)
    steam.write_shortcuts(folder, shortcuts.changes([], [first, second], PROGRAM, LOGO_PATH, existing))
    assert shortcuts.in_steam(folder) == {} and steam.shortcuts(folder) == [OTHER]
    assert not list((config / "grid").iterdir())                                 # their artwork went too


def test_artwork_sizes_with_and_without_the_games_pictures(tmp_path, qapp):
    from PyQt6.QtGui import QImage
    with_pictures = read_game(make_game(tmp_path / "a", "A", pictures=True))
    without = read_game(make_game(tmp_path / "b", "B"))
    for game, logo in ((with_pictures, {"_logo"}), (without, set())):
        art = shortcuts.draw_art(game, LOGO_PATH)
        assert set(art) == {"p", "", "_hero"} | logo                             # a logo only from icon0.png
        for suffix in ("p", "", "_hero"):
            image = QImage.fromData(art[suffix], "PNG")
            assert (image.width(), image.height()) == steam.ART[suffix], suffix
    art = shortcuts.draw_art(with_pictures, LOGO_PATH)
    assert QImage.fromData(art["_hero"], "PNG").pixelColor(10, 10).name() == "#00ff00"   # pic0.png fills the banner
    assert QImage.fromData(art[""], "PNG").pixelColor(460, 215).name() == "#ff0000"      # icon0.png in the middle


def test_a_cover_from_steamgriddb_in_place_of_the_drawn_portrait(tmp_path, qapp):
    game = read_game(make_game(tmp_path / "fs", "One", "PCSB00001"))
    assert shortcuts.COVERS == ("p",) and shortcuts.cover_name(game) == "PCSB00001"
    drawn = shortcuts.draw_art(game, LOGO_PATH)
    change = shortcuts.changes([game], [], PROGRAM, LOGO_PATH, {}, found=lambda _g: {"p": b"cover"})[0]
    assert change.art == {**drawn, "p": b"cover"}
