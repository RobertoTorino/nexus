# SPDX-License-Identifier: GPL-3.0-or-later
"""The Steam shortcuts for the games (shortcuts.py) on Steam folders made in a temp folder: the launch line, which
shortcuts are the app's, unique names, adding and removing beside other shortcuts, and the artwork."""

from __future__ import annotations

import shlex
from pathlib import Path

from conftest import make_disc_game, make_hdd_game

from bc250_core import steam
from rpcs3_manager import LOGO_PATH, shortcuts
from rpcs3_manager.games import Game, read_game

PNG_ICON = LOGO_PATH.with_name(f"{LOGO_PATH.stem}-128.png")      # Steam gets the PNG beside the WebP icon
RUN = Path("/home/u/.local/bin/bc250-rpcs3-run")
OTHER = {"appid": -1234, "AppName": "RetroArch", "Exe": '"/usr/bin/retroarch"', "LaunchOptions": "--no-gui x"}


def _steam(tmp_path: Path) -> Path:
    config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    config.mkdir(parents=True)
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": OTHER}}))
    return tmp_path / "Steam"


def test_the_launch_line_and_whose_shortcut_it_is():
    game = Game(Path("/games/My Game/PS3_GAME/USRDIR/EBOOT.BIN"), "My Game", disc=True)
    options = shortcuts.launch_options(game)
    assert options == '--no-gui --fullscreen "/games/My Game/PS3_GAME/USRDIR/EBOOT.BIN"'
    assert shlex.split(options) == ["--no-gui", "--fullscreen", "/games/My Game/PS3_GAME/USRDIR/EBOOT.BIN"]
    odd = Game(Path('/games/A "B" $C/USRDIR/EBOOT.BIN'), "Odd")
    assert shlex.split(shortcuts.launch_options(odd))[-1] == str(odd.eboot)       # single quotes then
    item = shortcuts.entry(game, "My Game", RUN, LOGO_PATH)
    assert item["Exe"] == f'"{RUN}"' and item["StartDir"] == f'"{RUN.parent}/"' and item["icon"] == str(PNG_ICON)
    assert item["tags"] == {"0": "PS3", "1": "RPCS3 Manager"}
    assert shortcuts.ours(item) and shortcuts.for_game(game)(item)
    assert not shortcuts.for_game(Game(Path("/games/Other/USRDIR/EBOOT.BIN"), "Other"))(item)
    assert not shortcuts.ours(OTHER) and not shortcuts.ours({**item, "LaunchOptions": ""})
    assert not shortcuts.ours({**item, "LaunchOptions": "--installfw /x/PS3UPDAT.PUP"})
    assert not shortcuts.ours({**item, "LaunchOptions": "--no-gui --fullscreen"})
    assert not shortcuts.ours({**item, "LaunchOptions": '--no-gui "unclosed'})


def test_names_are_unique():
    a = Game(Path("/1/USRDIR/EBOOT.BIN"), "Game", "BLUS00001")
    b = Game(Path("/2/USRDIR/EBOOT.BIN"), "Game", "BLES00002")
    c = Game(Path("/3/USRDIR/EBOOT.BIN"), "Other", "BLUS00003")
    assert shortcuts.names([a, b, c]) == {a.eboot: "[PS3] Game (BLUS00001)", b.eboot: "[PS3] Game (BLES00002)",
                                          c.eboot: "[PS3] Other"}


def test_add_then_take_out(tmp_path, qapp):
    folder = _steam(tmp_path)
    make_disc_game(tmp_path / "games" / "one", "One", "BLUS00001", pictures=True)
    first = read_game(tmp_path / "games" / "one" / "PS3_GAME", disc=True)
    second = read_game(make_hdd_game(tmp_path / "hdd0" / "NPUB00002", "Two", "NPUB00002").parent.parent)
    numbers = steam.write_shortcuts(folder, shortcuts.changes([first, second], [], RUN, LOGO_PATH, {}))
    assert shortcuts.in_steam(folder) == {str(first.eboot): "[PS3] One", str(second.eboot): "[PS3] Two"}
    config = steam.user_folders(folder)[0]
    assert sorted(p.name for p in (config / "grid").iterdir()) == sorted(
        [f"{n}{suffix}.png" for n in numbers for suffix in ("p", "", "_hero")] + [f"{numbers[0]}_logo.png"])
    item = steam.shortcuts(folder)[1]
    assert item["icon"] == str(first.picture("ICON0.PNG"))                      # the game's own icon
    existing = shortcuts.in_steam(folder)
    steam.write_shortcuts(folder, shortcuts.changes([], [first, second], RUN, LOGO_PATH, existing))
    assert shortcuts.in_steam(folder) == {} and steam.shortcuts(folder) == [OTHER]
    assert not list((config / "grid").iterdir())                                 # their artwork went too


def test_a_shortcut_taken_out_under_the_name_it_has(tmp_path):
    folder = _steam(tmp_path)
    a = Game(Path("/1/USRDIR/EBOOT.BIN"), "Game", "BLUS00001")
    b = Game(Path("/2/USRDIR/EBOOT.BIN"), "Game", "BLES00002")
    steam.write_shortcuts(folder, shortcuts.changes([a, b], [], RUN, LOGO_PATH, {}, art=False))
    grid = steam.user_folders(folder)[0] / "grid"
    grid.mkdir()
    named = steam.appid(f'"{RUN}"', "[PS3] Game (BLUS00001)")
    (grid / f"{named}p.png").write_bytes(b"P")
    steam.write_shortcuts(folder, shortcuts.changes([], [a], RUN, LOGO_PATH, shortcuts.in_steam(folder)))
    assert shortcuts.in_steam(folder) == {"/2/USRDIR/EBOOT.BIN": "[PS3] Game (BLES00002)"} and not list(grid.iterdir())


def test_artwork_sizes_with_and_without_the_games_pictures(tmp_path, qapp):
    from PyQt6.QtGui import QImage
    make_disc_game(tmp_path / "a", "A", pictures=True)
    with_pictures = read_game(tmp_path / "a" / "PS3_GAME", disc=True)
    without = read_game(make_hdd_game(tmp_path / "b", "B").parent.parent)
    for game, logo in ((with_pictures, {"_logo"}), (without, set())):
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
    assert (logo.width(), logo.height()) == (320, 176) and logo.pixelColor(10, 10).name() == "#ff0000"


def test_pictures_from_steamgriddb_in_place_of_the_drawn_ones(tmp_path, qapp):
    game = read_game(make_hdd_game(tmp_path / "a", "A", "NPUB01234", pictures=True).parent.parent)
    assert shortcuts.COVERS == ("p",) and shortcuts.cover_name(game) == "NPUB01234"
    drawn = shortcuts.draw_art(game, LOGO_PATH)
    change = shortcuts.changes([game], [], RUN, LOGO_PATH, {}, found=lambda _g: {"p": b"cover"})[0]
    assert change.art == {**drawn, "p": b"cover"}
    assert shortcuts.changes([game], [], RUN, LOGO_PATH, {})[0].art == drawn
