# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's own game folders (owner, 03-11-2026, from the Windows Portable Suite's Xenia Manager, 30-10-2026: fixed
folders, no folder choosing): Games/XBOX360 in the user's home folder, made when the app opens, and Games/XBOX360 on
each removable drive that has one (a USB drive or an SD card; core's drives). The games are dropped there."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from bc250_core import keep
from bc250_core.drives import game_folders, removable_drives

from .games import PACKAGE_FOLDERS, Game

GAMES_HOME = Path("Games") / "XBOX360"      # the app's own game folder, in the home folder and on a removable drive


def fixed(home: Path, drives: Callable[[], list[Path]] = removable_drives) -> list[Path]:
    """The app's own game folders: Games/XBOX360 in the home folder, made when it is missing, then Games/XBOX360 on each
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

CONTENT_PARTS = {"000B0000": "its title updates", "00000002": "its add-ons"}   # a title ID folder's other content


def removal_items(game: Game, chosen: list[Path], found: list[Game], in_steam: bool) -> tuple[list[keep.Item], str]:
    """The keep page's rows for Remove game: an .iso, a .zar or a lone .xex is its file; an unpacked disc
    (default.xex) is its folder; a package of Games on Demand or an Arcade title in the console's <title ID> folder
    is a row per part of that folder (the game's package folder, its title updates, its add-ons, anything else in
    it), so the add-ons can be kept; a package elsewhere is the file with its .data folder; then its shortcut in
    Steam when it is in Steam. With no rows, why not: a drive, a game folder of the list (or one holding one) or a
    folder holding another game is never deleted by the app. Xenia's content folder, with the saves, is never
    among them."""
    console = (game.kind in ("god", "xbla") and game.folder.name.upper() in PACKAGE_FOLDERS
               and game.folder.parent.name.upper() == game.title_id.upper())
    if game.kind == "xex" and game.file.name.lower() == "default.xex":
        folder = game.folder
    elif console:                                       # <title ID>/00007000/<file>: its updates and add-ons beside it
        folder = game.folder.parent
    else:
        data = game.file.with_name(game.file.name + ".data")      # a Games on Demand package's data, beside it
        paths = (game.file, *([data] if game.kind == "god" and _is_dir(data) else []))
        items = [keep.Item(str(game.file), f"{game.file.name} (the game)", paths)]
        if in_steam:
            items.append(keep.Item(STEAM_ITEM, "Its shortcut in Steam"))
        return items, ""
    why = _in_own_folder(folder, chosen, game.title)
    if why:
        return [], why
    for other in found:
        if other.file != game.file and folder in other.file.parents:
            return [], f"{folder.name} holds another game too ({other.title}): delete {game.title}'s files by hand."
    if not console:
        items = [keep.Item(str(folder), f"{folder.name} (the game's folder)", (folder,))]
    else:
        try:
            parts = sorted(folder.iterdir(), key=lambda p: (p != game.folder, p.name.upper()))
        except OSError:
            parts = [game.folder]
        items = [keep.Item(str(part), ("the game" if part == game.folder else CONTENT_PARTS.get(part.name.upper(),
                                                                                                  part.name))
                           + f" ({folder.name}/{part.name})", (part,)) for part in parts]
    if in_steam:
        items.append(keep.Item(STEAM_ITEM, "Its shortcut in Steam"))
    return items, ""


def tidy(game: Game) -> None:
    """The console's <title ID> folder taken away once Remove game left it empty; one with a part kept stays."""
    folder = game.folder.parent
    if folder.name.upper() == game.title_id.upper() and game.folder.name.upper() in PACKAGE_FOLDERS:
        try:
            folder.rmdir()
        except OSError:
            pass
