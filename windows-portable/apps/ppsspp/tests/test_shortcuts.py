# SPDX-License-Identifier: GPL-3.0-or-later
"""The Steam shortcuts (shortcuts.py) on Windows: PPSSPP's program with the game alone and full screen, paths in
double quotes as Steam writes them, "[PSP] <title>" names made unique, the app's own shortcuts told from others,
adding and taking out beside other shortcuts in a Steam folder made in a temp folder, and the artwork from the game's
own pictures (the BC250 suite's PPSSPP Manager's tests)."""

from __future__ import annotations

from pathlib import Path

from conftest import make_disc, make_pbp

from bc250_core import steam
from ppsspp_manager import LOGO_PATH, shortcuts
from ppsspp_manager.games import Game, read_disc, read_pbp

PROGRAM = Path(r"C:\Users\me\AppData\Local\windows-portable-suite\windows-portable-ppsspp\emulator\PPSSPPWindows64.exe")
DAXTER = Game(Path(r"D:\PSP Games\Daxter.iso"), "Daxter", "ULUS10044")
OTHER = {"appid": -1234, "AppName": "RetroArch", "Exe": '"C:\\RetroArch\\retroarch.exe"',
         "LaunchOptions": "--fullscreen x"}


def _steam(tmp_path: Path) -> Path:
    config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    config.mkdir(parents=True)
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": OTHER}}))
    return tmp_path / "Steam"


def test_a_shortcut_starts_ppsspp_with_the_game(tmp_path):
    item = shortcuts.entry(DAXTER, "[PSP] Daxter", PROGRAM, LOGO_PATH)
    assert item["Exe"] == f'"{PROGRAM}"' and item["StartDir"] == f'"{PROGRAM.parent}\\"'
    assert item["LaunchOptions"] == '--fullscreen --pause-menu-exit "D:\\PSP Games\\Daxter.iso"'
    assert item["tags"] == {"0": "PSP", "1": "PPSSPP Manager"}
    assert shortcuts.ours(item) and shortcuts.for_game(DAXTER)(item)
    assert shortcuts.for_game(Game(Path(r"d:\psp games\DAXTER.iso"), "x"))(item)          # Windows ignores case
    assert not shortcuts.for_game(Game(Path(r"D:\PSP Games\Other.iso"), "Other"))(item)
    lower = {key.lower(): value for key, value in item.items()}                            # as some Steam writes it
    assert shortcuts.ours(lower)


def test_other_shortcuts_are_not_ours():
    assert not shortcuts.ours(OTHER)
    assert not shortcuts.ours({"Exe": '"C:\\Games\\other.exe"', "LaunchOptions": '--pause-menu-exit "x.iso"'})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": ""})              # PPSSPP alone, no game
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": '--fullscreen "a.iso"'})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": "--fullscreen --pause-menu-exit"})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": '--pause-menu-exit "unclosed'})


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
