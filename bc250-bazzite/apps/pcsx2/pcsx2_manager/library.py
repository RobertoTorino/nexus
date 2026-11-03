# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's own game folders (owner, 03-11-2026, from the Windows Portable Suite's PCSX2 Manager, 30-10-2026: fixed
folders, no folder choosing): Games/PS2 in the user's home folder, made with its BIOS folder when the app opens, and
Games/PS2 on each removable drive that has one (a USB drive or an SD card; core's drives). The games are dropped
there; the BIOS dump goes in Games/PS2/BIOS, and the app copies it into PCSX2."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from bc250_core import keep
from bc250_core.drives import game_folders, removable_drives

from .games import Game

GAMES_HOME = Path("Games") / "PS2"      # the app's own game folder, in the home folder and on a removable drive
BIOS = "BIOS"                           # the BIOS dump's folder in it


def bios_home(home: Path) -> Path:
    """Where the BIOS dump is put: Games/PS2/BIOS in the home folder."""
    return home / GAMES_HOME / BIOS


def fixed(home: Path, drives: Callable[[], list[Path]] = removable_drives) -> list[Path]:
    """The app's own game folders: Games/PS2 in the home folder, made with its BIOS folder when it is missing, then
    Games/PS2 on each removable drive that has one."""
    return game_folders(home, GAMES_HOME, drives, make=(BIOS,))


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


def removal_items(game: Game, in_steam: bool) -> tuple[list[keep.Item], str]:
    """The keep page's rows for Remove game: the disc image, then its shortcut in Steam when it is in Steam, every
    row marked Delete at first. The memory cards and PCSX2's own files are never among them."""
    items = [keep.Item(str(game.file), f"{game.file.name} (the disc image)", (game.file,))]
    if in_steam:
        items.append(keep.Item(STEAM_ITEM, "Its shortcut in Steam"))
    return items, ""
