# SPDX-License-Identifier: GPL-3.0-or-later
"""A Steam shortcut per game, where a game is started (on the desktop or in Steam's Big Picture Mode): a non-Steam
game that runs the run wrapper with PCSX2's launch line,
the game alone and full screen (bc250-pcsx2-run -nogui -fullscreen -- "<game>"; -nogui also makes PCSX2 exit when
the game does).

The file and its format are core's (bc250_core.steam). The shortcut runs the wrapper, not the AppImage, so its
Steam number (from the program and the name) stays the same when the app brings another PCSX2. A PS2 disc carries
no pictures, so the artwork is drawn from the app's icon by core's steam_art (owner, 16-10-2026): a background in
the icon's color, the icon and the game's title. The pictures from SteamGridDB (core's covers), when kept for the
game, replace the drawn ones they cover: the portrait, the wide picture, the banner and the logo."""

from __future__ import annotations

import shlex
from collections.abc import Callable, Iterable
from pathlib import Path

from bc250_core import covers, steam, steam_art

from .games import Game

RUN = "~/.local/bin/bc250-pcsx2-run"
RUN_NAME = "bc250-pcsx2-run"
TAGS = ("PS2", "PCSX2 Manager")
PREFIX = f"[{TAGS[0]}] "    # before each name, so the same title on another system or on Steam itself is told apart
COVERS = covers.ALL         # from SteamGridDB: all four, in place of the drawn ones


def launch_options(game: Game) -> str:
    """Steam's usual form, the path in double quotes; a path with a character that is special inside them gets
    single quotes instead."""
    path = str(game.file)
    quoted = f'"{path}"' if not any(c in path for c in '"$`\\') else shlex.quote(path)
    return f"-nogui -fullscreen -- {quoted}"


def _file(item: dict) -> str:
    """The game a shortcut of this app starts ("" for any other shortcut): the last word of its launch options,
    after -nogui."""
    if not str(item.get("Exe", "")).strip('"').endswith(RUN_NAME):
        return ""
    try:
        words = shlex.split(str(item.get("LaunchOptions", "")))
    except ValueError:
        return ""
    if "-nogui" not in words[:-1] or not words[-1] or words[-1].startswith("-"):
        return ""
    return words[-1]


def ours(item: dict) -> bool:
    """Any shortcut this app made."""
    return bool(_file(item))


def for_game(game: Game):
    """Recognizes the game's shortcut, whatever its name now."""
    return lambda item: _file(item) == str(game.file)


def names(games: Iterable[Game]) -> dict[Path, str]:
    """The name in Steam per game: the system and its title ("[PS2] Title"), with its serial when two games have
    the same title (Steam numbers a shortcut by its program and name, so two names must differ)."""
    games = list(games)
    titles = [g.title for g in games]
    return {g.file: PREFIX + (g.title if titles.count(g.title) == 1 or not g.serial
                              else f"{g.title} ({g.serial})")
            for g in games}


def entry(game: Game, name: str, run: Path, logo: Path) -> dict:
    return steam.shortcut_entry(f'"{run}"', name, f'"{run.parent}/"', str(steam.shortcut_icon(logo)),
                                launch_options(game), TAGS)


def in_steam(folder: Path) -> dict[str, str]:
    """The game files that have a shortcut of this app, for any Steam user, with the shortcut's name."""
    return {_file(item): str(item.get("AppName", "")) for item in steam.shortcuts(folder) if ours(item)}


def cover_name(game: Game) -> str:
    """The name the game's pictures from SteamGridDB are kept under."""
    return covers.name(game.title, game.serial)


def changes(add: Iterable[Game], remove: Iterable[Game], run: Path, logo: Path, existing: dict[str, str],
            art: bool = True, found: Callable[[Game], dict[str, bytes]] = lambda _game: {}) -> list[steam.Change]:
    """The changes for core's write_shortcuts: the games to add (or bring up to date) and to take out. The names
    are made unique over the games added; a shortcut taken out is named as in Steam (*existing*, from in_steam()),
    so its artwork, numbered by the name, goes too. *found*: a game's pictures from SteamGridDB, in place of the
    drawn ones."""
    add, remove = list(add), list(remove)
    named = names(add)
    result = [steam.Change(entry(g, named[g.file], run, logo), for_game(g),
                           {**draw_art(g, logo), **found(g)} if art else {})
              for g in add]
    result += [steam.Change(entry(g, existing.get(str(g.file), g.title), run, logo), for_game(g), remove=True)
               for g in remove]
    return result


# --- The artwork -----------------------------------------------------------------------------------------------

def draw_art(game: Game, logo: Path) -> dict[str, bytes]:
    """The four images as PNG bytes, drawn from the app's icon (*logo*) by core's steam_art: a PS2 disc gives no
    pictures, so the icon with the game's title, and the icon as the logo on the banner."""
    return steam_art.draw_icon_art(logo, game.title, f"{TAGS[0]} · {TAGS[1]}", f"{TAGS[1].upper()} · {TAGS[0]}")
