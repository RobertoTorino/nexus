# SPDX-License-Identifier: GPL-3.0-or-later
"""The Steam shortcuts for the games (shortcuts.py) on Steam folders made in a temp folder: the launch line, which
shortcuts are the app's, unique names, adding and removing beside other shortcuts, and the artwork."""

from __future__ import annotations

import shlex
from pathlib import Path

from conftest import make_disc, make_pbp

from bc250_core import steam
from ppsspp_manager import LOGO_PATH, shortcuts
from ppsspp_manager.games import Game, read_disc, read_pbp

PNG_ICON = LOGO_PATH.with_name(f"{LOGO_PATH.stem}-128.png")      # Steam gets the PNG beside the WebP icon
RUN = Path("/home/u/.local/bin/bc250-ppsspp-run")
OTHER = {"appid": -1234, "AppName": "RetroArch", "Exe": '"/usr/bin/retroarch"', "LaunchOptions": "--fullscreen x"}


def _steam(tmp_path: Path) -> Path:
    config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    config.mkdir(parents=True)
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": OTHER}}))
    return tmp_path / "Steam"


def test_the_launch_line_and_whose_shortcut_it_is():
    game = Game(Path("/games/My Game.iso"), "My Game")
    options = shortcuts.launch_options(game)
    assert options == '--fullscreen --pause-menu-exit "/games/My Game.iso"'
    assert shlex.split(options) == ["--fullscreen", "--pause-menu-exit", "/games/My Game.iso"]
    odd = Game(Path('/games/A "B" $C.iso'), "Odd")
    assert shlex.split(shortcuts.launch_options(odd))[-1] == str(odd.file)        # single quotes then
    item = shortcuts.entry(game, "My Game", RUN, LOGO_PATH)
    assert item["Exe"] == f'"{RUN}"' and item["StartDir"] == f'"{RUN.parent}/"' and item["icon"] == str(PNG_ICON)
    assert item["tags"] == {"0": "PSP", "1": "PPSSPP Manager"}
    assert shortcuts.ours(item) and shortcuts.for_game(game)(item)
    assert not shortcuts.for_game(Game(Path("/games/Other.iso"), "Other"))(item)
    assert not shortcuts.ours(OTHER) and not shortcuts.ours({**item, "LaunchOptions": ""})
    assert not shortcuts.ours({**item, "LaunchOptions": "/games/My Game.iso"})
    assert not shortcuts.ours({**item, "LaunchOptions": "--fullscreen --pause-menu-exit"})
    assert not shortcuts.ours({**item, "LaunchOptions": '--fullscreen "unclosed'})


def test_names_are_unique():
    a = Game(Path("/1.iso"), "Game", "ULUS00001")
    b = Game(Path("/2.iso"), "Game", "ULES00002")
    c = Game(Path("/3.iso"), "Other", "ULUS00003")
    assert shortcuts.names([a, b, c]) == {a.file: "[PSP] Game (ULUS00001)", b.file: "[PSP] Game (ULES00002)",
                                          c.file: "[PSP] Other"}


def test_add_then_take_out(tmp_path, qapp):
    folder = _steam(tmp_path)
    first = read_disc(make_disc(tmp_path / "games" / "one.iso", "One", "ULUS00001", pictures=True))
    second = read_pbp(make_pbp(tmp_path / "games" / "two", "Two"))
    numbers = steam.write_shortcuts(folder, shortcuts.changes([first, second], [], RUN, LOGO_PATH, {}))
    assert shortcuts.in_steam(folder) == {str(first.file): "[PSP] One", str(second.file): "[PSP] Two"}
    config = steam.user_folders(folder)[0]
    assert sorted(p.name for p in (config / "grid").iterdir()) == sorted(
        [f"{n}{suffix}.png" for n in numbers for suffix in ("p", "", "_hero")] + [f"{numbers[0]}_logo.png"])
    existing = shortcuts.in_steam(folder)
    steam.write_shortcuts(folder, shortcuts.changes([], [first, second], RUN, LOGO_PATH, existing))
    assert shortcuts.in_steam(folder) == {} and steam.shortcuts(folder) == [OTHER]
    assert not list((config / "grid").iterdir())                                 # their artwork went too


def test_a_shortcut_taken_out_under_the_name_it_has(tmp_path):
    folder = _steam(tmp_path)
    a = Game(Path("/1.iso"), "Game", "ULUS00001")
    b = Game(Path("/2.iso"), "Game", "ULES00002")
    steam.write_shortcuts(folder, shortcuts.changes([a, b], [], RUN, LOGO_PATH, {}, art=False))
    grid = steam.user_folders(folder)[0] / "grid"
    grid.mkdir()
    named = steam.appid(f'"{RUN}"', "[PSP] Game (ULUS00001)")
    (grid / f"{named}p.png").write_bytes(b"P")
    steam.write_shortcuts(folder, shortcuts.changes([], [a], RUN, LOGO_PATH, shortcuts.in_steam(folder)))
    assert shortcuts.in_steam(folder) == {"/2.iso": "[PSP] Game (ULES00002)"} and not list(grid.iterdir())


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
    hero = QImage.fromData(art["_hero"], "PNG")
    assert hero.pixelColor(10, 10).name() == "#00ff00"                            # PIC1.PNG fills the banner
    wide = QImage.fromData(art[""], "PNG")
    assert wide.pixelColor(460, 215).name() == "#ff0000"                          # ICON0.PNG in the middle
    logo = QImage.fromData(art["_logo"], "PNG")
    assert (logo.width(), logo.height()) == (144, 80) and logo.pixelColor(10, 10).name() == "#ff0000"


def test_a_cover_from_steamgriddb_in_place_of_the_drawn_portrait(tmp_path, qapp):
    game = read_disc(make_disc(tmp_path / "one.iso", "One", "ULUS00001"))
    assert shortcuts.COVERS == ("p",) and shortcuts.cover_name(game) == "ULUS00001"
    drawn = shortcuts.draw_art(game, LOGO_PATH)
    change = shortcuts.changes([game], [], RUN, LOGO_PATH, {}, found=lambda _g: {"p": b"cover"})[0]
    assert change.art == {**drawn, "p": b"cover"}
    assert shortcuts.changes([game], [], RUN, LOGO_PATH, {})[0].art == drawn
