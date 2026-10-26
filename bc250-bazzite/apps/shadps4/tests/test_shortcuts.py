# SPDX-License-Identifier: GPL-3.0-or-later
"""The Steam shortcuts for the games (shortcuts.py) on Steam folders made in a temp folder: the launch line, which
shortcuts are the app's, unique names, adding and removing beside other shortcuts, and the artwork."""

from __future__ import annotations

import shlex
from pathlib import Path

from conftest import make_game

from bc250_core import steam
from shadps4_manager import LOGO_PATH, shortcuts
from shadps4_manager.games import Game, read_game

PNG_ICON = LOGO_PATH.with_name(f"{LOGO_PATH.stem}-128.png")      # Steam gets the PNG beside the WebP icon
RUN = Path("/home/u/.local/bin/bc250-shadps4-run")
OTHER = {"appid": -1234, "AppName": "RetroArch", "Exe": '"/usr/bin/retroarch"', "LaunchOptions": "-g x"}


def _steam(tmp_path: Path) -> Path:
    config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    config.mkdir(parents=True)
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": OTHER}}))
    return tmp_path / "Steam"


def test_the_launch_line_and_whose_shortcut_it_is():
    game = Game(Path("/games/My Game/eboot.bin"), "My Game")
    options = shortcuts.launch_options(game)
    assert options == '-f true -g "/games/My Game/eboot.bin"'
    assert shlex.split(options) == ["-f", "true", "-g", "/games/My Game/eboot.bin"]
    odd = Game(Path('/games/A "B" $C/eboot.bin'), "Odd")
    assert shlex.split(shortcuts.launch_options(odd))[-1] == str(odd.eboot)       # single quotes then
    item = shortcuts.entry(game, "My Game", RUN, LOGO_PATH)
    assert item["Exe"] == f'"{RUN}"' and item["StartDir"] == f'"{RUN.parent}/"' and item["icon"] == str(PNG_ICON)
    assert item["tags"] == {"0": "PS4", "1": "shadPS4 Manager"}
    assert shortcuts.ours(item) and shortcuts.for_game(game)(item)
    assert not shortcuts.for_game(Game(Path("/games/Other/eboot.bin"), "Other"))(item)
    assert not shortcuts.ours(OTHER) and not shortcuts.ours({**item, "LaunchOptions": "-b"})
    assert not shortcuts.ours({**item, "LaunchOptions": '-g "unclosed'})


def test_names_are_unique():
    a = Game(Path("/1/eboot.bin"), "Game", "CUSA00001")
    b = Game(Path("/2/eboot.bin"), "Game", "CUSA00002")
    c = Game(Path("/3/eboot.bin"), "Other", "CUSA00003")
    assert shortcuts.names([a, b, c]) == {a.eboot: "[PS4] Game (CUSA00001)", b.eboot: "[PS4] Game (CUSA00002)", c.eboot: "[PS4] Other"}


def test_add_then_take_out(tmp_path, qapp):
    folder = _steam(tmp_path)
    first = read_game(make_game(tmp_path / "games" / "one", "One", "CUSA00001", pictures=True))
    second = read_game(make_game(tmp_path / "games" / "two", "Two", "CUSA00002"))
    numbers = steam.write_shortcuts(folder, shortcuts.changes([first, second], [], RUN, LOGO_PATH, {}))
    assert shortcuts.in_steam(folder) == {str(first.eboot): "[PS4] One", str(second.eboot): "[PS4] Two"}
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
    a = Game(Path("/1/eboot.bin"), "Game", "CUSA00001")
    b = Game(Path("/2/eboot.bin"), "Game", "CUSA00002")
    steam.write_shortcuts(folder, shortcuts.changes([a, b], [], RUN, LOGO_PATH, {}, art=False))
    grid = steam.user_folders(folder)[0] / "grid"
    grid.mkdir()
    named = steam.appid(f'"{RUN}"', "[PS4] Game (CUSA00001)")
    (grid / f"{named}p.png").write_bytes(b"P")
    steam.write_shortcuts(folder, shortcuts.changes([], [a], RUN, LOGO_PATH, shortcuts.in_steam(folder)))
    assert shortcuts.in_steam(folder) == {"/2/eboot.bin": "[PS4] Game (CUSA00002)"} and not list(grid.iterdir())


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
    logo = QImage.fromData(art["_logo"], "PNG")
    assert (logo.width(), logo.height()) == (512, 512) and logo.pixelColor(10, 10).name() == "#ff0000"  # icon0.png


def test_pictures_from_steamgriddb_in_place_of_the_drawn_ones(tmp_path, qapp):
    game = read_game(make_game(tmp_path / "a", "A", "CUSA01234", pictures=True))
    assert shortcuts.COVERS == ("p",) and shortcuts.cover_name(game) == "CUSA01234"
    drawn = shortcuts.draw_art(game, LOGO_PATH)
    change = shortcuts.changes([game], [], RUN, LOGO_PATH, {}, found=lambda _g: {"p": b"cover"})[0]
    assert change.art == {**drawn, "p": b"cover"}
    assert shortcuts.changes([game], [], RUN, LOGO_PATH, {})[0].art == drawn


def test_a_shortcut_made_without_a_logo(tmp_path, qapp):
    folder = _steam(tmp_path)
    game = read_game(make_game(tmp_path / "games" / "one", "One", "CUSA00001", pictures=True))
    bare = read_game(make_game(tmp_path / "games" / "two", "Two", "CUSA00002"))
    steam.write_shortcuts(folder, shortcuts.changes([game, bare], [], RUN, LOGO_PATH, {}, art=False))
    assert shortcuts.logo_missing(folder, game, "[PS4] One", RUN)
    assert not shortcuts.logo_missing(folder, bare, "[PS4] Two", RUN)                  # no icon0.png: no logo to miss
    steam.write_shortcuts(folder, shortcuts.changes([game], [], RUN, LOGO_PATH, shortcuts.in_steam(folder)))
    assert not shortcuts.logo_missing(folder, game, "[PS4] One", RUN)


def test_a_shortcut_with_the_tags_of_the_old_name(tmp_path):
    folder = _steam(tmp_path)
    game = Game(Path("/games/One/eboot.bin"), "One")
    steam.write_shortcuts(folder, shortcuts.changes([game], [], RUN, LOGO_PATH, {}, art=False))
    assert shortcuts.old_tags(folder) == set()                                  # the other shortcut is not ours
    config = steam.user_folders(folder)[0]
    values = steam.read_vdf((config / "shortcuts.vdf").read_bytes())
    values["shortcuts"]["1"]["tags"] = {"0": "PS4", "1": "BC-250 shadPS4 Manager"}
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf(values))
    assert shortcuts.old_tags(folder) == {str(game.eboot)}
    steam.write_shortcuts(folder, shortcuts.changes([game], [], RUN, LOGO_PATH, {}, art=False))
    assert shortcuts.old_tags(folder) == set() and len(steam.shortcuts(folder)) == 2
