# SPDX-License-Identifier: GPL-3.0-or-later
"""Your games: the app's own folders (owner, 30-10-2026: the games are put there, nothing is browsed to; the BC250
suite's PPSSPP Manager keeps chosen folders): Games\\PSP in your user folder, made when it is missing, and Games\\PSP
on a removable drive (an SD card, a USB stick) that has one (fixed). PPSSPP needs no files from the console, so there
is no folder for them. Then the games found in them and on PPSSPP's memory stick (games.scan), which have a Steam
shortcut of this app, the plan Update Steam carries out (the marked games in Steam, the others out, and the shortcuts
of games no longer found out too), and what Remove game may delete (removal; the page of what to keep and the
deleting are core's keep). The suite's SteamGridDB key and the pictures found are in the suite's folders
(%APPDATA%\\windows-portable-suite\\steamgriddb-key, the app's covers\\)."""

from __future__ import annotations

import ctypes
import os
import string
import sys
from collections.abc import Callable
from pathlib import Path

from bc250_core import covers, steam
from bc250_core.platform import suite_config, suite_data

from . import APP_ID, SUITE, shortcuts
from .games import Game

GAMES_HOME = Path("Games") / "PSP"      # the app's own game folder, in the user's folder and on a removable drive
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
    """The app's own game folders (owner, 30-10-2026: put the games there, no browsing): Games\\PSP in the user's
    folder, made when it is missing, then Games\\PSP on each removable drive that has one."""
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


def removal(game: Game, chosen: list[Path], found: list[Game]) -> tuple[list[Path], str]:
    """What Remove game offers to delete (owner, 30-10-2026: a game that no longer plays goes, files and all): a disc
    image (ISO, CSO, CHD) is its file alone; a memory stick game (an EBOOT.PBP) is its own folder, in a game folder or
    in PSP\\GAME on PPSSPP's memory stick (*chosen* holds that folder too). With none, why not: a drive, a game folder of
    the list (or one holding one) or a folder holding another game is never deleted by the app. The saves are in
    PSP\\SAVEDATA on the memory stick and are never among them."""
    if game.kind != "pbp":
        return [game.file], ""
    folder = game.folder
    if folder.parent == folder:
        return [], f"{game.title} is at the top of {folder}: delete its files by hand."
    for place in chosen:
        if os.path.normcase(str(place)) == os.path.normcase(str(folder)) or folder in place.parents:
            return [], (f"{game.title} is in {folder.name}, one of the app's game folders itself: delete its files "
                        "by hand.")
    for other in found:
        if other.file != game.file and folder in other.file.parents:
            return [], f"{folder.name} holds another game too ({other.title}): delete {game.title}'s files by hand."
    return [folder], ""

