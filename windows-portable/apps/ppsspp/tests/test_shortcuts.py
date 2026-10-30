# SPDX-License-Identifier: GPL-3.0-or-later
"""The Steam shortcuts (shortcuts.py) on Windows: the app's play mode with the game alone and full screen (owner,
30-10-2026: View, LB and RB held quit it), one made before it that starts PPSSPP itself still the game's, paths in
double quotes as Steam writes them, "[PSP] <title>" names made unique, the app's own shortcuts told from others,
adding and taking out beside other shortcuts in a Steam folder made in a temp folder, and the artwork from the game's
own pictures (the BC250 suite's PPSSPP Manager's tests)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from conftest import make_disc, make_pbp

from bc250_core import play, steam
from ppsspp_manager import LOGO_PATH, ROOT, shortcuts
from ppsspp_manager.games import Game, read_disc, read_pbp

MANAGER = r"C:\Users\me\AppData\Local\windows-portable-suite\windows-portable-ppsspp\app\PPSSPP-Manager.exe"
PROGRAM = Path(r"C:\Users\me\AppData\Local\windows-portable-suite\windows-portable-ppsspp\emulator\PPSSPPWindows64.exe")
DAXTER = Game(Path(r"D:\PSP Games\Daxter.iso"), "Daxter", "ULUS10044")
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


def test_a_shortcut_starts_the_play_mode_in_ppssps_folder(release):
    item = shortcuts.entry(DAXTER, "[PSP] Daxter", PROGRAM, LOGO_PATH)
    assert item["Exe"] == f'"{MANAGER}"' and item["StartDir"] == f'"{PROGRAM.parent}\\"'
    assert item["LaunchOptions"] == '--play --fullscreen --pause-menu-exit "D:\\PSP Games\\Daxter.iso"'
    assert shortcuts.command(DAXTER) == [MANAGER, "--play", "--fullscreen", "--pause-menu-exit", str(DAXTER.file)]
    assert item["tags"] == {"0": "PSP", "1": "PPSSPP Manager"}
    assert shortcuts.ours(item) and shortcuts.for_game(DAXTER)(item)
    assert shortcuts.for_game(Game(Path(r"d:\psp games\DAXTER.iso"), "x"))(item)          # Windows ignores case
    assert not shortcuts.for_game(Game(Path(r"D:\PSP Games\Other.iso"), "Other"))(item)
    lower = {key.lower(): value for key, value in item.items()}                            # as some Steam writes it
    assert shortcuts.ours(lower)


def test_a_shortcut_made_before_the_play_mode_is_the_games_and_outdated(tmp_path, release):
    """A shortcut that starts PPSSPPWindows64.exe itself (1.0.1 and before) is the game's, so Update Steam replaces
    it, and outdated() names it; one made from the checkout (PowerShell and run.ps1) is outdated in a release too."""
    folder = _steam(tmp_path)
    old = steam.shortcut_entry(f'"{PROGRAM}"', "[PSP] Daxter", f'"{PROGRAM.parent}\\"', "",
                               '--fullscreen --pause-menu-exit "D:\\PSP Games\\Daxter.iso"', shortcuts.TAGS)
    assert shortcuts.ours(old) and shortcuts.for_game(DAXTER)(old)
    before = play.launcher(ROOT, frozen=False)[1]
    checkout = steam.shortcut_entry(f'"{play.POWERSHELL}"', "[PSP] Two", '"x\\"', "",
                                    play.launch_options(before, '--fullscreen --pause-menu-exit "D:\\Two.iso"'),
                                    shortcuts.TAGS)
    three = Game(Path(r"D:\Three.iso"), "Three", "ULUS00003")
    config = steam.user_folders(folder)[0]
    values = steam.read_vdf((config / "shortcuts.vdf").read_bytes())
    values["shortcuts"].update({"1": old, "2": checkout,
                                "3": shortcuts.entry(three, "[PSP] Three", PROGRAM, LOGO_PATH)})
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf(values))
    assert set(shortcuts.in_steam(folder)) == {str(DAXTER.file), r"D:\Two.iso", str(three.file)}
    assert shortcuts.outdated(folder) == {str(DAXTER.file), r"D:\Two.iso"}
    steam.write_shortcuts(folder, shortcuts.changes([DAXTER], [], PROGRAM, LOGO_PATH, {}, art=False))
    assert shortcuts.outdated(folder) == {r"D:\Two.iso"} and len(steam.shortcuts(folder)) == 4


def test_other_shortcuts_are_not_ours():
    assert not shortcuts.ours(OTHER)
    assert not shortcuts.ours({"Exe": '"C:\\Games\\other.exe"', "LaunchOptions": '--pause-menu-exit "x.iso"'})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": ""})              # PPSSPP alone, no game
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": '--fullscreen "a.iso"'})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": "--fullscreen --pause-menu-exit"})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": '--pause-menu-exit "unclosed'})
    assert not shortcuts.ours({"Exe": f'"{play.POWERSHELL}"', "LaunchOptions": '-File x.ps1 --pause-menu-exit "x.iso"'})


def test_names_are_unique():
    a = Game(Path(r"D:\1.iso"), "Game", "ULUS00001")
    b = Game(Path(r"D:\2.iso"), "Game", "ULES00002")
    c = Game(Path(r"D:\3.iso"), "Other", "ULUS00003")
    assert shortcuts.names([a, b, c]) == {a.file: "[PSP] Game (ULUS00001)", b.file: "[PSP] Game (ULES00002)",
                                          c.file: "[PSP] Other"}


def test_add_then_take_out(tmp_path, qapp):
    folder = _steam(tmp_path)
    first = read_disc(make_disc(tmp_path / "games" / "one.iso", "One", "ULUS00001", pictures=True))
    second = read_pbp(make_pbp(tmp_path / "games" / "two", "Two"))
    numbers = steam.write_shortcuts(folder, shortcuts.changes([first, second], [], PROGRAM, LOGO_PATH, {}))
    assert shortcuts.in_steam(folder) == {str(first.file): "[PSP] One", str(second.file): "[PSP] Two"}
    config = steam.user_folders(folder)[0]
    assert sorted(p.name for p in (config / "grid").iterdir()) == sorted(
        [f"{n}{suffix}.png" for n in numbers for suffix in ("p", "", "_hero")] + [f"{numbers[0]}_logo.png"])
    existing = shortcuts.in_steam(folder)
    steam.write_shortcuts(folder, shortcuts.changes([], [first, second], PROGRAM, LOGO_PATH, existing))
    assert shortcuts.in_steam(folder) == {} and steam.shortcuts(folder) == [OTHER]
    assert not list((config / "grid").iterdir())                                 # their artwork went too


def test_artwork_sizes_with_and_without_the_games_pictures(tmp_path, qapp):
    from PyQt6.QtGui import QImage
    with_pictures = read_disc(make_disc(tmp_path / "a.iso", "A", pictures=True))
    without = read_disc(make_disc(tmp_path / "b.iso", "B"))
    chd = tmp_path / "c.chd"
    chd.write_bytes(b"MComprHD")
    for game, logo in ((with_pictures, {"_logo"}), (without, set()), (read_disc(chd), set())):
        art = shortcuts.draw_art(game, LOGO_PATH)
        assert set(art) == {"p", "", "_hero"} | logo                             # a logo only from ICON0.PNG
        for suffix in ("p", "", "_hero"):
            image = QImage.fromData(art[suffix], "PNG")
            assert (image.width(), image.height()) == steam.ART[suffix], suffix
    art = shortcuts.draw_art(with_pictures, LOGO_PATH)
    assert QImage.fromData(art["_hero"], "PNG").pixelColor(10, 10).name() == "#00ff00"   # PIC1.PNG fills the banner
    assert QImage.fromData(art[""], "PNG").pixelColor(460, 215).name() == "#ff0000"      # ICON0.PNG in the middle


def test_a_cover_from_steamgriddb_in_place_of_the_drawn_portrait(tmp_path, qapp):
    game = read_disc(make_disc(tmp_path / "one.iso", "One", "ULUS00001"))
    assert shortcuts.COVERS == ("p",) and shortcuts.cover_name(game) == "ULUS00001"
    drawn = shortcuts.draw_art(game, LOGO_PATH)
    change = shortcuts.changes([game], [], PROGRAM, LOGO_PATH, {}, found=lambda _g: {"p": b"cover"})[0]
    assert change.art == {**drawn, "p": b"cover"}
