# SPDX-License-Identifier: GPL-3.0-or-later
"""The Steam shortcuts (shortcuts.py) on Windows: the app's play mode with the game alone and full screen (owner,
30-10-2026: View, LB and RB held quit it), one made before it that starts RPCS3 itself still the game's, paths in
double quotes as Steam writes them, "[PS3] <title>" names made unique, the app's own shortcuts told from others,
adding and taking out beside other shortcuts in a Steam folder made in a temp folder, and the artwork from the game's
own pictures (the BC250 suite's RPCS3 Manager's tests)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from conftest import make_disc_game, make_hdd_game

from bc250_core import play, steam
from rpcs3_manager import LOGO_PATH, ROOT, shortcuts
from rpcs3_manager.games import Game, read_game

MANAGER = r"C:\Users\me\AppData\Local\windows-portable-suite\windows-portable-rpcs3\app\RPCS3-Manager.exe"
PROGRAM = Path(r"C:\Users\me\AppData\Local\windows-portable-suite\windows-portable-rpcs3\emulator\rpcs3.exe")
DEMON = Game(Path(r"D:\PS3\Demon's Souls\PS3_GAME\USRDIR\EBOOT.BIN"), "Demon's Souls", "BLUS30443", disc=True)
OTHER = {"appid": -1234, "AppName": "RetroArch", "Exe": '"C:\\RetroArch\\retroarch.exe"',
         "LaunchOptions": "--fullscreen x"}


def _steam(tmp_path: Path) -> Path:
    config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    config.mkdir(parents=True)
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": OTHER}}))
    return tmp_path / "Steam"


@pytest.fixture
def release(monkeypatch):
    """The app as a release runs it: PyInstaller's program."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", MANAGER)


def test_a_shortcut_starts_the_play_mode_with_the_game(release):
    item = shortcuts.entry(DEMON, "[PS3] Demon's Souls", PROGRAM, LOGO_PATH)
    assert item["Exe"] == f'"{MANAGER}"' and item["StartDir"] == f'"{PROGRAM.parent}\\"'
    assert item["LaunchOptions"] == ('--play --no-gui --fullscreen '
                                     '"D:\\PS3\\Demon\'s Souls\\PS3_GAME\\USRDIR\\EBOOT.BIN"')
    assert shortcuts.command(DEMON) == [MANAGER, "--play", "--no-gui", "--fullscreen", str(DEMON.eboot)]
    assert item["tags"] == {"0": "PS3", "1": "RPCS3 Manager"}
    assert shortcuts.ours(item) and shortcuts.for_game(DEMON)(item)
    assert shortcuts.for_game(Game(Path(r"d:\ps3\DEMON'S SOULS\PS3_GAME\USRDIR\eboot.bin"), "x"))(item)   # case
    assert not shortcuts.for_game(Game(Path(r"D:\PS3\Other\PS3_GAME\USRDIR\EBOOT.BIN"), "Other"))(item)
    lower = {key.lower(): value for key, value in item.items()}                            # as some Steam writes it
    assert shortcuts.ours(lower)


def test_a_shortcut_made_before_the_play_mode_is_the_games_and_outdated(tmp_path, release):
    """A shortcut that starts rpcs3.exe itself (1.0.1 and before) is the game's, so Update Steam replaces it, and
    outdated() names it; one made from the checkout (PowerShell and run.ps1) is outdated in a release too."""
    folder = _steam(tmp_path)
    old = steam.shortcut_entry(f'"{PROGRAM}"', "[PS3] Demon's Souls", f'"{PROGRAM.parent}\\"', "",
                               f'--no-gui --fullscreen "{DEMON.eboot}"', shortcuts.TAGS)
    assert shortcuts.ours(old) and shortcuts.for_game(DEMON)(old)
    two = r"D:\Two\PS3_GAME\USRDIR\EBOOT.BIN"
    before = play.launcher(ROOT, frozen=False)[1]
    checkout = steam.shortcut_entry(f'"{play.POWERSHELL}"', "[PS3] Two", '"x\\"', "",
                                    play.launch_options(before, f'--no-gui --fullscreen "{two}"'), shortcuts.TAGS)
    three = Game(Path(r"D:\Three\PS3_GAME\USRDIR\EBOOT.BIN"), "Three", "BLUS00003", disc=True)
    config = steam.user_folders(folder)[0]
    values = steam.read_vdf((config / "shortcuts.vdf").read_bytes())
    values["shortcuts"].update({"1": old, "2": checkout,
                                "3": shortcuts.entry(three, "[PS3] Three", PROGRAM, LOGO_PATH)})
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf(values))
    assert set(shortcuts.in_steam(folder)) == {str(DEMON.eboot), two, str(three.eboot)}
    assert shortcuts.outdated(folder) == {str(DEMON.eboot), two}
    steam.write_shortcuts(folder, shortcuts.changes([DEMON], [], PROGRAM, LOGO_PATH, {}, art=False))
    assert shortcuts.outdated(folder) == {two} and len(steam.shortcuts(folder)) == 4


def test_other_shortcuts_are_not_ours():
    assert not shortcuts.ours(OTHER)
    assert not shortcuts.ours({"Exe": '"C:\\Games\\other.exe"', "LaunchOptions": '--no-gui "x\\EBOOT.BIN"'})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": ""})              # RPCS3 alone, no game
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": '--fullscreen "a\\EBOOT.BIN"'})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": "--no-gui --fullscreen"})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": '--no-gui "unclosed'})
    assert not shortcuts.ours({"Exe": f'"{play.POWERSHELL}"', "LaunchOptions": '-File x.ps1 --no-gui "x\\EBOOT.BIN"'})


def test_names_are_unique():
    a = Game(Path(r"D:\1\PS3_GAME\USRDIR\EBOOT.BIN"), "Game", "BLUS00001")
    b = Game(Path(r"D:\2\PS3_GAME\USRDIR\EBOOT.BIN"), "Game", "BLES00002")
    c = Game(Path(r"D:\3\PS3_GAME\USRDIR\EBOOT.BIN"), "Other", "BLUS00003")
    assert shortcuts.names([a, b, c]) == {a.eboot: "[PS3] Game (BLUS00001)", b.eboot: "[PS3] Game (BLES00002)",
                                          c.eboot: "[PS3] Other"}


def test_add_then_take_out(tmp_path, qapp):
    folder = _steam(tmp_path)
    make_disc_game(tmp_path / "games" / "one", "One", "BLUS00001", pictures=True)
    first = read_game(tmp_path / "games" / "one" / "PS3_GAME", disc=True)
    make_hdd_game(tmp_path / "hdd" / "NPUB30001", "Two", "NPUB30001")
    second = read_game(tmp_path / "hdd" / "NPUB30001")
    numbers = steam.write_shortcuts(folder, shortcuts.changes([first, second], [], PROGRAM, LOGO_PATH, {}))
    assert shortcuts.in_steam(folder) == {str(first.eboot): "[PS3] One", str(second.eboot): "[PS3] Two"}
    item = next(i for i in steam.shortcuts(folder) if i.get("AppName") == "[PS3] One")
    assert item["icon"] == str(first.picture("ICON0.PNG"))                       # the game's own icon
    config = steam.user_folders(folder)[0]
    assert sorted(p.name for p in (config / "grid").iterdir()) == sorted(
        [f"{n}{suffix}.png" for n in numbers for suffix in ("p", "", "_hero")] + [f"{numbers[0]}_logo.png"])
    existing = shortcuts.in_steam(folder)
    steam.write_shortcuts(folder, shortcuts.changes([], [first, second], PROGRAM, LOGO_PATH, existing))
    assert shortcuts.in_steam(folder) == {} and steam.shortcuts(folder) == [OTHER]
    assert not list((config / "grid").iterdir())                                 # their artwork went too


def test_artwork_sizes_with_and_without_the_games_pictures(tmp_path, qapp):
    from PyQt6.QtGui import QImage
    make_disc_game(tmp_path / "a", "A", pictures=True)
    make_disc_game(tmp_path / "b", "B")
    with_pictures = read_game(tmp_path / "a" / "PS3_GAME", disc=True)
    without = read_game(tmp_path / "b" / "PS3_GAME", disc=True)
    for game, logo in ((with_pictures, {"_logo"}), (without, set())):
        art = shortcuts.draw_art(game, LOGO_PATH)
        assert set(art) == {"p", "", "_hero"} | logo                             # a logo only from ICON0.PNG
        for suffix in ("p", "", "_hero"):
            image = QImage.fromData(art[suffix], "PNG")
            assert (image.width(), image.height()) == steam.ART[suffix], suffix
    art = shortcuts.draw_art(with_pictures, LOGO_PATH)
    assert QImage.fromData(art["_hero"], "PNG").pixelColor(10, 10).name() == "#00ff00"   # PIC1.PNG fills the banner
    assert QImage.fromData(art[""], "PNG").pixelColor(460, 215).name() == "#ff0000"      # ICON0.PNG in the middle


def test_a_cover_from_steamgriddb_in_place_of_the_drawn_portrait(tmp_path, qapp):
    make_disc_game(tmp_path / "one", "One", "BLUS00001")
    game = read_game(tmp_path / "one" / "PS3_GAME", disc=True)
    assert shortcuts.COVERS == ("p",) and shortcuts.cover_name(game) == "BLUS00001"
    drawn = shortcuts.draw_art(game, LOGO_PATH)
    change = shortcuts.changes([game], [], PROGRAM, LOGO_PATH, {}, found=lambda _g: {"p": b"cover"})[0]
    assert change.art == {**drawn, "p": b"cover"}
