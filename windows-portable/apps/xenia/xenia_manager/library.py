# SPDX-License-Identifier: GPL-3.0-or-later
"""Your games: the app's own folders (owner, 30-10-2026: fixed folders, no folder selecting; the games are put there,
nothing is browsed to; the BC250 suite's Xenia Manager keeps chosen folders): Games\\XBOX360 in your user folder,
made when it is missing, and Games\\XBOX360 on a removable drive (an SD card, a USB stick) that has one (fixed).
Xenia needs no system files, so there is no folder for them. Then the games found in them (games.scan), which have a
Steam shortcut of this app, the plan Update Steam carries out (the marked games in Steam, the others out, and the
shortcuts of games no longer found out too), and what Remove game offers to delete (removal, tidy; core's keep.py
deletes what the user leaves marked). The suite's SteamGridDB
key and the pictures found are in the suite's folders (%APPDATA%\\windows-portable-suite\\steamgriddb-key, the
app's covers\\)."""

from __future__ import annotations

import ctypes
import os
import string
import sys
from collections.abc import Callable
from pathlib import Path

from bc250_core import covers, keep, steam
from bc250_core.platform import suite_config, suite_data

from . import APP_ID, SUITE, shortcuts
from .games import PACKAGE_FOLDERS, Game

GAMES_HOME = Path("Games") / "XBOX360"  # the app's own game folder, in the user's folder and on a removable drive
DRIVE_REMOVABLE = 2                     # GetDriveTypeW


def key_file() -> Path:
    """The suite's SteamGridDB API key, the Windows Portable Suite's own (BC250's is in its ~/.config folder)."""
    return suite_config(SUITE) / "steamgriddb-key"


def covers_home() -> Path:
    return suite_data(SUITE) / APP_ID / "covers"


def removable_drives() -> list[Path]:
    """The removable drives' roots (an SD card, a USB stick); [] off Windows."""
    if sys.platform != "win32":
        return []
    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    mask = k32.GetLogicalDrives()
    found = []
    for n, letter in enumerate(string.ascii_uppercase):
        if mask & (1 << n) and k32.GetDriveTypeW(f"{letter}:\\") == DRIVE_REMOVABLE:
            found.append(Path(f"{letter}:\\"))
    return found


def fixed(home: Path | None = None, drives: Callable[[], list[Path]] = removable_drives) -> list[Path]:
    """The app's own game folders (owner, 30-10-2026: drop the games there, no browsing): Games\\XBOX360 in the
    user's folder, made when it is missing, then Games\\XBOX360 on each removable drive that has one."""
    own = (home or Path.home()) / GAMES_HOME
    try:
        own.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return [own, *[d / GAMES_HOME for d in drives() if _is_dir(d / GAMES_HOME)]]


def _is_dir(place: Path) -> bool:
    """Whether the place is a folder; a removable drive without a card (an empty SD slot keeps its letter) makes
    Windows raise rather than answer, and is no place."""
    try:
        return place.is_dir()
    except OSError:
        return False


def plan(found: list[Game], marked: set[str], in_steam: dict[str, str]) -> tuple[list[Game], list[Game]]:
    """(games to add or bring up to date, games to take out): the marked ones in, the others out, and the shortcuts
    of games no longer found out too (as the BC250 app's steam_plan)."""
    add = [g for g in found if str(g.file) in marked]
    files = {str(g.file) for g in found}
    remove = [g for g in found if str(g.file) in in_steam and str(g.file) not in marked]
    remove += [Game(Path(file), name) for file, name in in_steam.items() if file not in files]
    return add, remove


def pending(found: list[Game], marked: set[str], in_steam: dict[str, str], outdated: set[str] = frozenset()) -> bool:
    """Whether Update Steam would change anything: a game in or out, a name in Steam that differs, or a shortcut that
    does not start the play mode yet (*outdated*, shortcuts.outdated)."""
    add, remove = plan(found, marked, in_steam)
    named = shortcuts.names(add)
    return bool(remove) or any(in_steam.get(str(g.file)) != named[g.file] or str(g.file) in outdated for g in add)


def update_steam(steam_dir: Path, add: list[Game], remove: list[Game], program: Path, logo: Path,
                 existing: dict[str, str], closed: Callable[[Callable[[], None]], bool] = steam.with_steam_closed,
                 key: str = "", home: Path | None = None, get=None) -> tuple[bool, str, dict[str, str] | None]:
    """Steam's shortcuts made to match (off the window's thread): the pictures from SteamGridDB first when there is
    a key, then the shortcuts with Steam closed. (ok, what to tell, the app's games in Steam's file as read back
    right after the write, while Steam is still closed; None when nothing was written). Reading the file back then
    rather than once Steam starts again (29-10-2026: "it still says 0 games in Steam") tells whether the shortcuts
    were written as the app reads them, before Steam touches the file."""
    home = home or covers_home()
    notes = (covers.fetch([(shortcuts.cover_name(g), g.title) for g in add], shortcuts.COVERS, key, home,
                          *([get] if get else [])) if key else [])
    changes = shortcuts.changes(add, remove, program, logo, existing,
                                found=lambda g: covers.art(home, shortcuts.cover_name(g), shortcuts.COVERS))
    found: dict[str, str] = {}

    def change() -> None:
        steam.write_shortcuts(steam_dir, changes)
        found.update(shortcuts.in_steam(steam_dir))

    try:
        restarted = closed(change)
    except (steam.SteamError, steam.ShortcutError, OSError) as error:
        return False, "\n".join([*notes, f"Steam was not changed: {error}"]), None
    again = " Steam was closed for it and started again, signed in." if restarted else ""
    return True, "\n".join([*notes, f"{len(add)} game(s) in Steam, under Non-Steam in its library"
                                      f"{f'; {len(remove)} taken out' if remove else ''}.{again}"]), found


CONTENT_PARTS = {"000B0000": "Title updates", "00000002": "Add-ons"}   # a title ID folder's other content


def removal(game: Game, chosen: list[Path], found: list[Game]) -> tuple[list[keep.Item], str]:
    """What Remove game offers to delete (owner, 30-10-2026: a game that no longer plays goes; owner, 01-11-2026:
    before deleting anything, let the user decide what to keep), a row each for the keep page: an .iso, a .zar or a
    lone .xex is its file; an unpacked disc (default.xex) is its folder; a package of Games on Demand or an Arcade
    title in the console's <title ID> folder is a row per part of that folder (the game's package folder, its title
    updates, its add-ons, anything else in it), so the add-ons can be kept; a package elsewhere is the file with its
    .data folder. With no rows, why not: a drive, a game folder of the list (or one holding one) or a folder holding
    another game is never deleted by the app."""
    console = (game.kind in ("god", "xbla") and game.folder.name.upper() in PACKAGE_FOLDERS
               and game.folder.parent.name.upper() == game.title_id.upper())
    if game.kind == "xex" and game.file.name.lower() == "default.xex":
        folder = game.folder
    elif console:                                       # <title ID>\00007000\<file>: its updates and add-ons beside it
        folder = game.folder.parent
    else:
        data = game.file.with_name(game.file.name + ".data")      # a Games on Demand package's data, beside it
        paths = (game.file, *([data] if game.kind == "god" and _is_dir(data) else []))
        return [keep.Item(str(game.file), f"{game.file.name} (the game)", paths)], ""
    if folder.parent == folder:
        return [], f"{game.title} is at the top of {folder}: delete its files by hand."
    for place in chosen:
        if os.path.normcase(str(place)) == os.path.normcase(str(folder)) or folder in place.parents:
            return [], (f"{game.title} is in {folder.name}, one of the app's game folders itself: delete its files "
                        "by hand.")
    for other in found:
        if other.file != game.file and folder in other.file.parents:
            return [], f"{folder.name} holds another game too ({other.title}): delete {game.title}'s files by hand."
    if not console:
        return [keep.Item(str(folder), f"{folder.name} (the game's folder)", (folder,))], ""
    try:
        parts = sorted(folder.iterdir(), key=lambda p: (p != game.folder, p.name.upper()))
    except OSError:
        parts = [game.folder]
    items = []
    for part in parts:
        name = part.name.upper()
        label = ("the game" if part == game.folder else CONTENT_PARTS.get(name, part.name)) + f" ({part.name})"
        items.append(keep.Item(str(part), label, (part,)))
    return items, ""


def tidy(game: Game) -> None:
    """The console's <title ID> folder taken away once Remove game left it empty; one with a part kept stays."""
    folder = game.folder.parent
    if folder.name.upper() == game.title_id.upper() and game.folder.name.upper() in PACKAGE_FOLDERS:
        try:
            folder.rmdir()
        except OSError:
            pass
