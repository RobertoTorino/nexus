# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's own game folders (owner, 03-11-2026, from the Windows Portable Suite's PPSSPP Manager, 30-10-2026: fixed
folders, no folder choosing): Games/PSP in the user's home folder, made when the app opens, and Games/PSP on
each removable drive that has one (a USB drive or an SD card; core's drives). The games are dropped there."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from bc250_core import keep
from bc250_core.drives import game_folders, removable_drives

from .games import Game

GAMES_HOME = Path("Games") / "PSP"      # the app's own game folder, in the home folder and on a removable drive


def fixed(home: Path, drives: Callable[[], list[Path]] = removable_drives) -> list[Path]:
    """The app's own game folders: Games/PSP in the home folder, made when it is missing, then Games/PSP on each
    removable drive that has one."""
    return game_folders(home, GAMES_HOME, drives)


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
    """The keep page's rows for Remove game: a disc image (ISO, CSO, CHD) is its file alone; a memory stick game (an
    EBOOT.PBP) is its own folder, in a game folder or in PSP/GAME on PPSSPP's memory stick (*chosen* holds that
    folder too); then its shortcut in Steam when it is in Steam. With no rows, why not: a drive, a game folder of
    the list (or one holding one) or a folder holding another game is never deleted by the app. The saves are in
    PSP/SAVEDATA on the memory stick and are never among them."""
    if game.kind != "pbp":
        items = [keep.Item(str(game.file), f"{game.file.name} (the disc image)", (game.file,))]
    else:
        folder = game.folder
        why = _in_own_folder(folder, chosen, game.title)
        if why:
            return [], why
        for other in found:
            if other.file != game.file and folder in other.file.parents:
                return [], f"{folder.name} holds another game too ({other.title}): delete {game.title}'s files by hand."
        items = [keep.Item(str(folder), f"{folder.name} (the game's folder)", (folder,))]
    if in_steam:
        items.append(keep.Item(STEAM_ITEM, "Its shortcut in Steam"))
    return items, ""
