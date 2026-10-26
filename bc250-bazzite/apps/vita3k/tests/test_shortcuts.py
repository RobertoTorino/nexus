# SPDX-License-Identifier: GPL-3.0-or-later
"""The Steam shortcuts for the games (shortcuts.py) on Steam folders made in a temp folder: the launch line, which
shortcuts are the app's, unique names, adding and removing beside other shortcuts, and the artwork."""

from __future__ import annotations

import shlex
from pathlib import Path

from conftest import make_game

from bc250_core import steam
from vita3k_manager import LOGO_PATH, shortcuts
from vita3k_manager.games import Game, read_game

PNG_ICON = LOGO_PATH.with_name(f"{LOGO_PATH.stem}-128.png")      # Steam gets the PNG beside the WebP icon
RUN = Path("/home/u/.local/bin/bc250-vita3k-run")
OTHER = {"appid": -1234, "AppName": "RetroArch", "Exe": '"/usr/bin/retroarch"', "LaunchOptions": "-r PCSB00245"}


def _steam(tmp_path: Path) -> Path:
    config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    config.mkdir(parents=True)
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": OTHER}}))
    return tmp_path / "Steam"


def test_the_launch_line_and_whose_shortcut_it_is():
    game = Game(Path("/vita/ux0/app/PCSB00245"), "Persona 4 Golden", "PCSB00245")
    options = shortcuts.launch_options(game)
    assert options == "--frontend sdl -r PCSB00245"                                # the game alone, no --fullscreen
    odd = Game(Path("/vita/ux0/app/my homebrew"), "Odd")
    assert shlex.split(shortcuts.launch_options(odd)) == ["--frontend", "sdl", "-r", "my homebrew"]
    item = shortcuts.entry(game, "[PS Vita] Persona 4 Golden", RUN, LOGO_PATH)
    assert item["Exe"] == f'"{RUN}"' and item["StartDir"] == f'"{RUN.parent}/"' and item["icon"] == str(PNG_ICON)
    assert item["tags"] == {"0": "PS Vita", "1": "Vita3K Manager"}
    assert shortcuts.ours(item) and shortcuts.for_game(game)(item)
    assert not shortcuts.for_game(Game(Path("/vita/ux0/app/PCSE00001"), "Other"))(item)
    assert not shortcuts.ours(OTHER) and not shortcuts.ours({**item, "LaunchOptions": ""})
    assert not shortcuts.ours({**item, "LaunchOptions": "--firmware /x/PSP2UPDAT.PUP"})
    assert not shortcuts.ours({**item, "LaunchOptions": "--frontend sdl -r"})
    assert not shortcuts.ours({**item, "LaunchOptions": '-r "unclosed'})


def test_names_are_unique():
    a = Game(Path("/a/PCSB00001"), "Game", "PCSB00001")
    b = Game(Path("/a/PCSE00002"), "Game", "PCSE00002")
    c = Game(Path("/a/PCSB00003"), "Other", "PCSB00003")
    assert shortcuts.names([a, b, c]) == {"PCSB00001": "[PS Vita] Game (PCSB00001)",
                                          "PCSE00002": "[PS Vita] Game (PCSE00002)", "PCSB00003": "[PS Vita] Other"}


def test_add_then_take_out(tmp_path, qapp):
    folder = _steam(tmp_path)
    first = read_game(make_game(tmp_path / "vita", "One", "PCSB00001", pictures=True))
    second = read_game(make_game(tmp_path / "vita", "Two", "PCSE00002"))
    numbers = steam.write_shortcuts(folder, shortcuts.changes([first, second], [], RUN, LOGO_PATH, {}))
    assert shortcuts.in_steam(folder) == {"PCSB00001": "[PS Vita] One", "PCSE00002": "[PS Vita] Two"}
    config = steam.user_folders(folder)[0]
    assert sorted(p.name for p in (config / "grid").iterdir()) == sorted(
        [f"{n}{suffix}.png" for n in numbers for suffix in ("p", "", "_hero")] + [f"{numbers[0]}_logo.png"])
    item = steam.shortcuts(folder)[1]
    assert item["icon"] == str(first.picture("icon0.png"))                      # the game's own icon
    existing = shortcuts.in_steam(folder)
    steam.write_shortcuts(folder, shortcuts.changes([], [first, second], RUN, LOGO_PATH, existing))
    assert shortcuts.in_steam(folder) == {} and steam.shortcuts(folder) == [OTHER]
    assert not list((config / "grid").iterdir())                                 # their artwork went too


def test_a_shortcut_taken_out_under_the_name_it_has(tmp_path):
    folder = _steam(tmp_path)
    a = Game(Path("/a/PCSB00001"), "Game", "PCSB00001")
    b = Game(Path("/a/PCSE00002"), "Game", "PCSE00002")
    steam.write_shortcuts(folder, shortcuts.changes([a, b], [], RUN, LOGO_PATH, {}, art=False))
    grid = steam.user_folders(folder)[0] / "grid"
    grid.mkdir()
    named = steam.appid(f'"{RUN}"', "[PS Vita] Game (PCSB00001)")
    (grid / f"{named}p.png").write_bytes(b"P")
    steam.write_shortcuts(folder, shortcuts.changes([], [a], RUN, LOGO_PATH, shortcuts.in_steam(folder)))
    assert shortcuts.in_steam(folder) == {"PCSE00002": "[PS Vita] Game (PCSE00002)"} and not list(grid.iterdir())


def test_artwork_sizes_with_and_without_the_games_pictures(tmp_path, qapp):
    from PyQt6.QtGui import QImage
    with_pictures = read_game(make_game(tmp_path, "A", "PCSB00001", pictures=True))
    without = read_game(make_game(tmp_path, "B", "PCSB00002"))
    for game, logo in ((with_pictures, {"_logo"}), (without, set())):
        art = shortcuts.draw_art(game, LOGO_PATH)
        assert set(art) == {"p", "", "_hero"} | logo                             # a logo only from icon0.png
        for suffix in ("p", "", "_hero"):
            image = QImage.fromData(art[suffix], "PNG")
            assert (image.width(), image.height()) == steam.ART[suffix], suffix
    art = shortcuts.draw_art(with_pictures, LOGO_PATH)
    hero = QImage.fromData(art["_hero"], "PNG")
    assert hero.pixelColor(10, 10).name() == "#00ff00"                            # pic0.png fills the banner
    wide = QImage.fromData(art[""], "PNG")
    assert wide.pixelColor(460, 215).name() == "#ff0000"                          # icon0.png in the middle
    logo = QImage.fromData(art["_logo"], "PNG")
    assert (logo.width(), logo.height()) == (128, 128) and logo.pixelColor(10, 10).name() == "#ff0000"


def test_pictures_from_steamgriddb_in_place_of_the_drawn_ones(tmp_path, qapp):
    game = read_game(make_game(tmp_path, "A", "PCSB01234", pictures=True))
    assert shortcuts.COVERS == ("p",) and shortcuts.cover_name(game) == "PCSB01234"
    drawn = shortcuts.draw_art(game, LOGO_PATH)
    change = shortcuts.changes([game], [], RUN, LOGO_PATH, {}, found=lambda _g: {"p": b"cover"})[0]
    assert change.art == {**drawn, "p": b"cover"}
    assert shortcuts.changes([game], [], RUN, LOGO_PATH, {})[0].art == drawn
