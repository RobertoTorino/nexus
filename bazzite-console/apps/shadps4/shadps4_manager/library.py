# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's own game folders (owner, 03-11-2026, from the Windows Portable Suite's shadPS4 Manager, 30-10-2026:
fixed folders, no folder choosing): Games/PS4 in the user's home folder, made with its Modules folder when the app
opens, and Games/PS4 on each removable drive that has one (a USB drive or an SD card; core's drives). The games are
dropped there, each in a folder of its own; the PS4's system modules (.sprx) go in Games/PS4/Modules, and the app
copies them into shadPS4."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from bc250_core import keep
from bc250_core.drives import game_folders, removable_drives

from .games import OVERLAYS, Game

GAMES_HOME = Path("Games") / "PS4"      # the app's own game folder, in the home folder and on a removable drive
MODULES = "Modules"                     # the system modules' folder in it


def modules_home(home: Path) -> Path:
    """Where the system modules are put: Games/PS4/Modules in the home folder."""
    return home / GAMES_HOME / MODULES


def fixed(home: Path, drives: Callable[[], list[Path]] = removable_drives) -> list[Path]:
    """The app's own game folders: Games/PS4 in the home folder, made with its Modules folder when it is missing,
    then Games/PS4 on each removable drive that has one."""
    return game_folders(home, GAMES_HOME, drives, make=(MODULES,))


# --- Remove game (owner, 03-11-2026: before deleting anything, let the user decide what to keep; core's keep) -------

STEAM_ITEM = "steam"


def _is_dir(place: Path) -> bool:
    try:
        return place.is_dir()
    except OSError:
        return False


def _in_own_folder(folder: Path, chosen: list[Path], title: str) -> str:
    """Why a folder is never deleted by the app: a drive's root, or one of the app's game folders itself."""
    if folder.parent == folder:
        return f"{title} is at the top of {folder}: delete its files by hand."
    for place in chosen:
        if place == folder or folder in place.parents:
            return f"{title} is in {folder.name}, one of the app's game folders itself: delete its files by hand."
    return ""


def removal_items(game: Game, chosen: list[Path], found: list[Game], in_steam: bool) -> tuple[list[keep.Item], str]:
    """The keep page's rows for Remove game: the game's folder, then its update, patch and mods beside it, then its
    shortcut in Steam when it is in Steam. With no rows, why not: a drive, a game folder of the list (or one holding
    one) or a folder holding another game is never offered. The saves, the play time and the package stay."""
    folder = game.folder
    why = _in_own_folder(folder, chosen, game.title)
    if why:
        return [], why
    for other in found:
        if other.eboot != game.eboot and folder in other.eboot.parents:
            return [], f"{folder.name} holds another game too ({other.title}): delete {game.title}'s files by hand."
    items = [keep.Item(str(folder), f"{folder.name} (the game's folder)", (folder,))]
    for suffix, what in zip(OVERLAYS, ("its update", "its patch", "its mods")):
        beside = folder.with_name(folder.name + suffix)
        if _is_dir(beside):
            items.append(keep.Item(str(beside), f"{beside.name} ({what})", (beside,)))
    if in_steam:
        items.append(keep.Item(STEAM_ITEM, "Its shortcut in Steam"))
    return items, ""
