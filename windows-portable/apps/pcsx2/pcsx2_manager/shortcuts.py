# SPDX-License-Identifier: GPL-3.0-or-later
"""A Steam shortcut per game, as the BC250 suite's PCSX2 Manager makes them (its shortcuts.py): a non-Steam game that
starts PCSX2 with the game alone and full screen, pcsx2-qt.exe -nogui -fullscreen -- "<game>" (-nogui also makes
PCSX2 exit when the game does), named "[PS2] <title>", in Steam's library and its Big Picture mode.

On Windows the shortcut runs the app's own program in its play mode (core's play.py; owner, 30-10-2026: one way out
of every game, View and Menu held): PCSX2-Manager.exe --play -nogui -fullscreen -- "<game>" starts PCSX2 in the
app's emulator folder, watches the controller and ends with the game. The app's program stays where it is when the
app is updated, so the shortcut's Steam number, from the program and the name, stays the same. A shortcut made
before, which runs pcsx2-qt.exe itself, is still the game's (outdated(): Update Steam brings it to the play mode).
Windows paths are quoted the way Steam writes them, in double quotes (a Windows path holds no
double quote). The file and its format are core's (bc250_core.steam); a PS2 disc carries no pictures, so the artwork
is drawn from the app's icon by core's steam_art, and the pictures from SteamGridDB (core's covers), when kept for
the game, replace the drawn ones they cover."""

from __future__ import annotations

import ntpath
import shlex
from collections.abc import Callable, Iterable
from pathlib import Path

from bc250_core import covers, play, steam, steam_art

from . import EXE_NAME, ROOT, emulator
from .games import Game

TAGS = ("PS2", "PCSX2 Manager")
PREFIX = f"[{TAGS[0]}] "    # before each name, so the same title on another system or on Steam itself is told apart
COVERS = covers.ALL         # from SteamGridDB: all four, in place of the drawn ones


def launch_options(game: Game) -> str:
    """PCSX2's launch line after its program: the game in double quotes, as Steam writes a path on Windows."""
    return f'{" ".join(emulator.GAME_ARGS)} -- "{game.file}"'


def command(game: Game) -> list[str]:
    """The game in the play mode, as its shortcut starts it: for a device without Steam (owner, 30-10-2026)."""
    program, before = play.launcher(ROOT)
    return [program, *before, *emulator.GAME_ARGS, "--", str(game.file)]


def _file(item: dict) -> str:
    """The game a shortcut of this app starts ("" for any other shortcut): the last word of its launch options,
    after -nogui, of a shortcut that runs the app's play mode, or pcsx2-qt.exe itself (one made before it). The
    fields by name whatever their case (steam.field): Steam has written them in lower case in some versions."""
    program = ntpath.basename(str(steam.field(item, "Exe")).strip('"')).lower()
    if program != emulator.EXE.lower() and program not in play.programs(EXE_NAME):
        return ""
    try:
        words = shlex.split(str(steam.field(item, "LaunchOptions")).replace("\\", "/"))
    except ValueError:
        return ""
    if "-nogui" not in words[:-1] or not words[-1] or words[-1].startswith("-"):
        return ""
    if program != emulator.EXE.lower() and play.FLAG not in words:
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
    """The name in Steam per game: the system and its title ("[PS2] Title"), with its serial when two games have
    the same title (Steam numbers a shortcut by its program and name, so two names must differ)."""
    games = list(games)
    titles = [g.title for g in games]
    return {g.file: PREFIX + (g.title if titles.count(g.title) == 1 or not g.serial
                              else f"{g.title} ({g.serial})")
            for g in games}


def entry(game: Game, name: str, program: Path, logo: Path) -> dict:
    """The game's shortcut: the play mode (play.launcher), started in PCSX2's folder, *program*'s."""
    launcher, before = play.launcher(ROOT)
    return steam.shortcut_entry(f'"{launcher}"', name, f'"{program.parent}\\"', str(steam.shortcut_icon(logo)),
                                play.launch_options(before, launch_options(game)), TAGS)


def in_steam(folder: Path) -> dict[str, str]:
    """The game files that have a shortcut of this app, for any Steam user, with the shortcut's name."""
    return {_file(item): str(steam.field(item, "AppName")) for item in steam.shortcuts(folder) if ours(item)}


def outdated(folder: Path) -> set[str]:
    """The game files whose shortcut does not start the play mode as it is now (one made before it, or one made from
    the checkout on a device with the release): Update Steam writes them again."""
    return {_file(item) for item in steam.shortcuts(folder) if ours(item)
            and not play.played(str(steam.field(item, "Exe")), str(steam.field(item, "LaunchOptions")), ROOT)}


def numbers(folder: Path) -> dict[str, int]:
    """The game files that have a shortcut of this app, with the appid Steam starts it by (steam.play_url): the one
    in Steam's file, else the one Steam gives its program and name (owner, 29-10-2026: a game started from the app,
    through Steam)."""
    found = {}
    for item in steam.shortcuts(folder):
        if ours(item):
            number = steam.field(item, "appid", None)
            if not isinstance(number, int):
                number = steam.appid(str(steam.field(item, "Exe")), str(steam.field(item, "AppName")))
            found[_file(item)] = number & 0xFFFFFFFF
    return found


def cover_name(game: Game) -> str:
    """The name the game's pictures from SteamGridDB are kept under."""
    return covers.name(game.title, game.serial)


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
    """The four images as PNG bytes, drawn from the app's icon (*logo*) by core's steam_art: a PS2 disc gives no
    pictures, so the icon with the game's title, and the icon as the logo on the banner."""
    return steam_art.draw_icon_art(logo, game.title, f"{TAGS[0]} · {TAGS[1]}", f"{TAGS[1].upper()} · {TAGS[0]}")
