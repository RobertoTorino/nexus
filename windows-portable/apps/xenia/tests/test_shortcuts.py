# SPDX-License-Identifier: GPL-3.0-or-later
"""The Steam shortcuts (shortcuts.py) on Windows, as shadPS4 Manager's are tested: Xenia's program with the game full
screen, started in its folder, paths in double quotes as Steam writes them, "[X360] <title>" names made unique, the
app's own shortcuts told from others, adding and taking out beside other shortcuts in a Steam folder made in a temp
folder, and the artwork drawn from the app's icon (the BC250 suite's Xenia Manager's tests)."""

from __future__ import annotations

from pathlib import Path

from conftest import make_iso

from bc250_core import steam
from xenia_manager import LOGO_PATH, shortcuts
from xenia_manager.games import Game, read_game

PROGRAM = Path(r"C:\Users\me\AppData\Local\windows-portable-suite\windows-portable-xenia\emulator\xenia_canary.exe")
HALO = Game(Path(r"D:\X360\Halo 3.iso"), "Halo 3", "4D5307E6")
OTHER = {"appid": -1234, "AppName": "RetroArch", "Exe": '"C:\\RetroArch\\retroarch.exe"',
         "LaunchOptions": "--fullscreen x"}


def _steam(tmp_path: Path) -> Path:
    config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    config.mkdir(parents=True)
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": OTHER}}))
    return tmp_path / "Steam"


def test_a_shortcut_starts_xenia_full_screen_with_the_game():
    item = shortcuts.entry(HALO, "[X360] Halo 3", PROGRAM, LOGO_PATH)
    assert item["Exe"] == f'"{PROGRAM}"' and item["StartDir"] == f'"{PROGRAM.parent}\\"'
    assert item["LaunchOptions"] == '--fullscreen=true "D:\\X360\\Halo 3.iso"'
    assert item["tags"] == {"0": "X360", "1": "Xenia Manager"}
    assert shortcuts.ours(item) and shortcuts.for_game(HALO)(item)
    assert shortcuts.for_game(Game(Path(r"d:\x360\HALO 3.ISO"), "x"))(item)                # case
    assert not shortcuts.for_game(Game(Path(r"D:\X360\Other.iso"), "Other"))(item)
    lower = {key.lower(): value for key, value in item.items()}                            # as some Steam writes it
    assert shortcuts.ours(lower)


def test_other_shortcuts_are_not_ours():
    assert not shortcuts.ours(OTHER)
    assert not shortcuts.ours({"Exe": '"C:\\Games\\other.exe"', "LaunchOptions": '--fullscreen=true "x.iso"'})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": ""})              # Xenia alone, no game
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": '"D:\\x.iso"'})   # no full screen
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": "--fullscreen=true --gpu=vulkan"})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": '--fullscreen=true "unclosed'})


def test_names_are_unique():
    a = Game(Path(r"D:\1.iso"), "Game", "4D530001")
    b = Game(Path(r"D:\2.iso"), "Game", "4D530002")
    c = Game(Path(r"D:\3.iso"), "Other")
    assert shortcuts.names([a, b, c]) == {a.file: "[X360] Game (4D530001)", b.file: "[X360] Game (4D530002)",
                                          c.file: "[X360] Other"}


def test_add_then_take_out(tmp_path, qapp):
    folder = _steam(tmp_path)
    first = read_game(make_iso(tmp_path / "games" / "One.iso"))
    second = read_game(make_iso(tmp_path / "games" / "Two.iso"))
    numbers = steam.write_shortcuts(folder, shortcuts.changes([first, second], [], PROGRAM, LOGO_PATH, {}))
    assert shortcuts.in_steam(folder) == {str(first.file): "[X360] One", str(second.file): "[X360] Two"}
    config = steam.user_folders(folder)[0]
    assert sorted(p.name for p in (config / "grid").iterdir()) == sorted(
        f"{n}{suffix}.png" for n in numbers for suffix in ("p", "", "_hero", "_logo"))
    existing = shortcuts.in_steam(folder)
    steam.write_shortcuts(folder, shortcuts.changes([], [first, second], PROGRAM, LOGO_PATH, existing))
    assert shortcuts.in_steam(folder) == {} and steam.shortcuts(folder) == [OTHER]
    assert not list((config / "grid").iterdir())                                 # their artwork went too


def test_the_artwork_is_drawn_from_the_apps_icon(qapp):
    from PyQt6.QtGui import QImage
    art = shortcuts.draw_art(HALO, LOGO_PATH)
    assert set(art) == {"p", "", "_hero", "_logo"}
    for suffix in ("p", "", "_hero"):
        image = QImage.fromData(art[suffix], "PNG")
        assert (image.width(), image.height()) == steam.ART[suffix], suffix


def test_pictures_from_steamgriddb_in_place_of_the_drawn_ones(qapp):
    assert shortcuts.COVERS == ("p", "", "_hero", "_logo") and shortcuts.cover_name(HALO) == "4D5307E6"
    drawn = shortcuts.draw_art(HALO, LOGO_PATH)
    change = shortcuts.changes([HALO], [], PROGRAM, LOGO_PATH, {}, found=lambda _g: {"p": b"cover"})[0]
    assert change.art == {**drawn, "p": b"cover"}
