# SPDX-License-Identifier: GPL-3.0-or-later
"""A Steam shortcut per game, as the BC250 suite's Xenia Manager makes them (its shortcuts.py): a non-Steam game that
starts Xenia with the game full screen, xenia_canary.exe --fullscreen=true "<game>", named "[X360] <title>", in Steam's
library and its Big Picture mode.

On Windows the shortcut runs Xenia's own program in the app's emulator folder, as shadPS4 Manager's do: that folder
stays the same when the app brings another Xenia (one folder, emulator.py), so the shortcut's Steam number, from the
program and the name, stays the same too. Windows paths are quoted the way Steam writes them, in double quotes (a
Windows path holds no double quote). The file and its format are core's (bc250_core.steam).

The app reads no pictures from a game (an Xbox 360 game keeps them inside its disc or package), so the artwork is
drawn from the app's icon by core's steam_art, as the BC250 app draws it: a background in the icon's color, the icon
and the game's title. The pictures from SteamGridDB (core's covers), when they are kept for the game, replace the
drawn ones they cover: all four."""

from __future__ import annotations

import ntpath
import shlex
from collections.abc import Callable, Iterable
from pathlib import Path

from bc250_core import covers, steam, steam_art

from . import emulator
from .games import Game

TAGS = ("X360", "Xenia Manager")
PREFIX = f"[{TAGS[0]}] "    # before each name, so the same title on another system or on Steam itself is told apart
COVERS = covers.ALL         # from SteamGridDB: all four, the app draws them from its icon otherwise
FULLSCREEN = emulator.GAME_ARGS[0]


def launch_options(game: Game) -> str:
    """Xenia's launch line after its program: --fullscreen=true, then the game's file in double quotes, as Steam writes
    a path on Windows."""
    return f'{" ".join(emulator.GAME_ARGS)} "{game.file}"'


def _file(item: dict) -> str:
    """The game a shortcut of this app starts ("" for any other shortcut): the last word of the launch options of a
    shortcut that runs xenia_canary.exe, after --fullscreen=true. The fields by name whatever their case (steam.field):
    Steam has written them in lower case in some versions."""
    if ntpath.basename(str(steam.field(item, "Exe")).strip('"')).lower() != emulator.EXE.lower():
        return ""
    try:
        words = shlex.split(str(steam.field(item, "LaunchOptions")).replace("\\", "/"))
    except ValueError:
        return ""
    if FULLSCREEN not in words[:-1] or not words[-1] or words[-1].startswith("-"):
        return ""
    return words[-1].replace("/", "\\")


def ours(item: dict) -> bool:
    """Any shortcut this app made."""
    return bool(_file(item))


def _key(path: str) -> str:
    return ntpath.normcase(path.replace("/", "\\"))


def for_game(game: Game):
    """Recognizes the game's shortcut, whatever its name now."""
    return lambda item: bool(_file(item)) and _key(_file(item)) == _key(str(game.file))


def names(games: Iterable[Game]) -> dict[Path, str]:
    """The name in Steam per game: the system and its title ("[X360] Title"), with its title ID when two games have
    the same title (Steam numbers a shortcut by its program and name, so two names must differ)."""
    games = list(games)
    titles = [g.title for g in games]
    return {g.file: PREFIX + (g.title if titles.count(g.title) == 1 or not g.title_id
                              else f"{g.title} ({g.title_id})")
            for g in games}


def entry(game: Game, name: str, program: Path, logo: Path) -> dict:
    return steam.shortcut_entry(f'"{program}"', name, f'"{program.parent}\\"', str(steam.shortcut_icon(logo)),
                                launch_options(game), TAGS)


def in_steam(folder: Path) -> dict[str, str]:
    """The game files that have a shortcut of this app, for any Steam user, with the shortcut's name."""
    return {_file(item): str(steam.field(item, "AppName")) for item in steam.shortcuts(folder) if ours(item)}


def cover_name(game: Game) -> str:
    """The name the game's pictures from SteamGridDB are kept under."""
    return covers.name(game.title, game.title_id)


def changes(add: Iterable[Game], remove: Iterable[Game], program: Path, logo: Path, existing: dict[str, str],
            art: bool = True, found: Callable[[Game], dict[str, bytes]] = lambda _game: {}) -> list[steam.Change]:
    """The changes for core's write_shortcuts: the games to add (or bring up to date) and to take out. The names
    are made unique over the games added; a shortcut taken out is named as in Steam (*existing*, from in_steam()),
    so its artwork, numbered by the name, goes too. *found*: a game's pictures from SteamGridDB, in place of the
    drawn ones."""
    add, remove = list(add), list(remove)
    named = names(add)
    result = [steam.Change(entry(g, named[g.file], program, logo), for_game(g),
                           {**draw_art(g, logo), **found(g)} if art else {})
              for g in add]
    result += [steam.Change(entry(g, existing.get(str(g.file), g.title), program, logo), for_game(g), remove=True)
               for g in remove]
    return result


def draw_art(game: Game, logo: Path) -> dict[str, bytes]:
    """The four images as PNG bytes, drawn from the app's icon (*logo*) by core's steam_art: the app reads no
    pictures from a game, so the icon with the game's title, and the icon as the logo on the banner."""
    return steam_art.draw_icon_art(logo, game.title, f"{TAGS[0]} · {TAGS[1]}", f"{TAGS[1].upper()} · {TAGS[0]}")
