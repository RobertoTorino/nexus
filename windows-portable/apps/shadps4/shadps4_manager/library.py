# SPDX-License-Identifier: GPL-3.0-or-later
"""Your games: the app's own folders (owner, 30-10-2026: the games, the packages and the system modules are put
there, nothing is browsed to; the BC250 suite's shadPS4 Manager keeps chosen folders in shadPS4's config.json):
Games\\PS4 in your user folder, made when it is missing, and Games\\PS4 on a removable drive (an SD card, a USB
stick) that has one (fixed), with Games\\PS4\\Modules for the system modules (modules_home). Then the games found in
them (games.scan), which have a Steam shortcut of this app, and the plan Update Steam carries out: the marked games
in Steam, the others out, and the shortcuts of games no longer found out too. The suite's SteamGridDB key and the
pictures found are in the suite's folders (%APPDATA%\\windows-portable-suite\\steamgriddb-key, the app's covers\\)."""

from __future__ import annotations

import ctypes
import os
import shutil
import stat
import string
import sys
from collections.abc import Callable
from pathlib import Path

from bc250_core import covers, steam
from bc250_core.platform import suite_config, suite_data

from . import APP_ID, SUITE, shortcuts
from .games import OVERLAYS, Game

GAMES_HOME = Path("Games") / "PS4"      # the app's own game folder, in the user's folder and on a removable drive
MODULES = "Modules"                     # the system modules' folder in it
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


def modules_home(home: Path | None = None) -> Path:
    """Where the system modules are put: Games\\PS4\\Modules in the user's folder."""
    return (home or Path.home()) / GAMES_HOME / MODULES


def fixed(home: Path | None = None, drives: Callable[[], list[Path]] = removable_drives) -> list[Path]:
    """The app's own game folders (owner, 30-10-2026: drop the games and packages there, no browsing): Games\\PS4 in
    the user's folder, made with its Modules folder when they are missing, then Games\\PS4 on each removable drive
    that has one."""
    own = (home or Path.home()) / GAMES_HOME
    try:
        modules_home(home).mkdir(parents=True, exist_ok=True)
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
    add = [g for g in found if str(g.eboot) in marked]
    files = {str(g.eboot) for g in found}
    remove = [g for g in found if str(g.eboot) in in_steam and str(g.eboot) not in marked]
    remove += [Game(Path(file), name) for file, name in in_steam.items() if file not in files]
    return add, remove


def pending(found: list[Game], marked: set[str], in_steam: dict[str, str]) -> bool:
    """Whether Update Steam would change anything: a game in or out, or a name in Steam that differs."""
    add, remove = plan(found, marked, in_steam)
    named = shortcuts.names(add)
    return bool(remove) or any(in_steam.get(str(g.eboot)) != named[g.eboot] for g in add)


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
    """The folders Remove game deletes (owner, 30-10-2026: a game that no longer plays goes, files and all): the
    game's folder, then its update, patch and mods beside it. With none, why not: a drive, a game folder of the list
    (or one holding one) or a folder holding another game is never deleted by the app."""
    folder = game.folder
    if folder.parent == folder:
        return [], f"{game.title} is at the top of {folder}: delete its files by hand."
    for place in chosen:
        if os.path.normcase(str(place)) == os.path.normcase(str(folder)) or folder in place.parents:
            return [], (f"{game.title} is in {folder.name}, one of the app's game folders itself: delete its files "
                        "by hand.")
    for other in found:
        if other.eboot != game.eboot and folder in other.eboot.parents:
            return [], f"{folder.name} holds another game too ({other.title}): delete {game.title}'s files by hand."
    overlays = [folder.with_name(folder.name + suffix) for suffix in OVERLAYS]
    return [folder, *[f for f in overlays if _is_dir(f)]], ""


def delete(folders: list[Path]) -> list[str]:
    """The folders deleted, read-only files too (an unpacked game's may be); what could not be, each with why."""
    def writable(function, path, _error) -> None:
        os.chmod(path, stat.S_IWRITE)
        function(path)
    failed = []
    for folder in folders:
        try:
            shutil.rmtree(folder, onexc=writable)
        except OSError as error:
            failed.append(f"{folder.name} ({error.strerror or error})")
    return failed
