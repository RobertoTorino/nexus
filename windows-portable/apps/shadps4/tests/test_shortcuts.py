# SPDX-License-Identifier: GPL-3.0-or-later
"""The Steam shortcuts (shortcuts.py) on Windows, as RPCS3 Manager's are tested: shadPS4's program with the game full
screen, started in its folder (shadPS4's portable folder beside it), paths in double quotes as Steam writes them,
"[PS4] <title>" names made unique, the app's own shortcuts told from others, adding and taking out beside other
shortcuts in a Steam folder made in a temp folder, and the artwork from the game's own pictures (the BC250 suite's
shadPS4 Manager's tests)."""

from __future__ import annotations

from pathlib import Path

from conftest import make_game

from bc250_core import steam
from shadps4_manager import LOGO_PATH, shortcuts
from shadps4_manager.games import Game, read_game

PROGRAM = Path(r"C:\Users\me\AppData\Local\windows-portable-suite\windows-portable-shadps4\emulator\shadPS4.exe")
BLOODBORNE = Game(Path(r"D:\PS4\Bloodborne\CUSA00900\eboot.bin"), "Bloodborne", "CUSA00900")
OTHER = {"appid": -1234, "AppName": "RetroArch", "Exe": '"C:\\RetroArch\\retroarch.exe"',
         "LaunchOptions": "--fullscreen x"}


def _steam(tmp_path: Path) -> Path:
    config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    config.mkdir(parents=True)
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": OTHER}}))
    return tmp_path / "Steam"


def test_a_shortcut_starts_shadps4_with_the_game_in_its_folder(tmp_path):
    item = shortcuts.entry(BLOODBORNE, "[PS4] Bloodborne", PROGRAM, LOGO_PATH)
    assert item["Exe"] == f'"{PROGRAM}"' and item["StartDir"] == f'"{PROGRAM.parent}\\"'   # where user\ is
    assert item["LaunchOptions"] == '-f true -g "D:\\PS4\\Bloodborne\\CUSA00900\\eboot.bin"'
    assert item["tags"] == {"0": "PS4", "1": "shadPS4 Manager"}
    assert shortcuts.ours(item) and shortcuts.for_game(BLOODBORNE)(item)
    assert shortcuts.for_game(Game(Path(r"d:\ps4\BLOODBORNE\cusa00900\EBOOT.BIN"), "x"))(item)       # case
    assert not shortcuts.for_game(Game(Path(r"D:\PS4\Other\eboot.bin"), "Other"))(item)
    lower = {key.lower(): value for key, value in item.items()}                            # as some Steam writes it
    assert shortcuts.ours(lower)


def test_other_shortcuts_are_not_ours():
    assert not shortcuts.ours(OTHER)
    assert not shortcuts.ours({"Exe": '"C:\\Games\\other.exe"', "LaunchOptions": '-g "x\\eboot.bin"'})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": ""})              # shadPS4 alone, no game
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": "-b"})            # its Big Picture
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": "-f true -g"})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": '-g "unclosed'})


def test_names_are_unique():
    a = Game(Path(r"D:\1\eboot.bin"), "Game", "CUSA00001")
    b = Game(Path(r"D:\2\eboot.bin"), "Game", "CUSA00002")
    c = Game(Path(r"D:\3\eboot.bin"), "Other", "CUSA00003")
    assert shortcuts.names([a, b, c]) == {a.eboot: "[PS4] Game (CUSA00001)", b.eboot: "[PS4] Game (CUSA00002)",
                                          c.eboot: "[PS4] Other"}


def test_add_then_take_out(tmp_path, qapp):
    folder = _steam(tmp_path)
    first = read_game(make_game(tmp_path / "games" / "CUSA00001", "One", "CUSA00001", pictures=True))
    second = read_game(make_game(tmp_path / "games" / "CUSA00002", "Two", "CUSA00002"))
    numbers = steam.write_shortcuts(folder, shortcuts.changes([first, second], [], PROGRAM, LOGO_PATH, {}))
    assert shortcuts.in_steam(folder) == {str(first.eboot): "[PS4] One", str(second.eboot): "[PS4] Two"}
    item = next(i for i in steam.shortcuts(folder) if i.get("AppName") == "[PS4] One")
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
    assert QImage.fromData(art["_hero"], "PNG").pixelColor(10, 10).name() == "#00ff00"   # pic1.png fills the banner
    assert QImage.fromData(art[""], "PNG").pixelColor(460, 215).name() == "#ff0000"      # icon0.png in the middle


def test_a_cover_from_steamgriddb_in_place_of_the_drawn_portrait(tmp_path, qapp):
    game = read_game(make_game(tmp_path / "one", "One", "CUSA00001"))
    assert shortcuts.COVERS == ("p",) and shortcuts.cover_name(game) == "CUSA00001"
    drawn = shortcuts.draw_art(game, LOGO_PATH)
    change = shortcuts.changes([game], [], PROGRAM, LOGO_PATH, {}, found=lambda _g: {"p": b"cover"})[0]
    assert change.art == {**drawn, "p": b"cover"}
