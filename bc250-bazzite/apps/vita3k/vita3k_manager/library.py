# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's own folders (owner, 03-11-2026, from the Windows Portable Suite's Vita3K Manager, 30-10-2026: fixed
folders, no folder choosing): Games/Vita in the user's home folder, made with its Firmware folder when the app opens,
and Games/Vita on each removable drive that has one (a USB drive or an SD card; core's drives). The PS Vita's
firmware files (PSP2UPDAT.PUP, Sony names all three so) go in Games/Vita/Firmware, or in a folder right below it,
and the app gives them to Vita3K; the games to install are picked from Games/Vita."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from bc250_core import keep
from bc250_core.drives import game_folders, removable_drives

from .games import Game

GAMES_HOME = Path("Games") / "Vita"     # the app's own folder, in the home folder and on a removable drive
FIRMWARE = "Firmware"                   # the firmware files' folder in it
FIRMWARE_SUFFIXES = (".pup",)


def firmware_home(home: Path) -> Path:
    """Where the firmware files are put: Games/Vita/Firmware in the home folder."""
    return home / GAMES_HOME / FIRMWARE


def fixed(home: Path, drives: Callable[[], list[Path]] = removable_drives) -> list[Path]:
    """The app's own folders: Games/Vita in the home folder, made with its Firmware folder when it is missing, then
    Games/Vita on each removable drive that has one."""
    return game_folders(home, GAMES_HOME, drives, make=(FIRMWARE,))


def firmware_files(home: Path) -> list[Path]:
    """The .PUP files in Games/Vita/Firmware and in the folders right below it (Sony names all three
    PSP2UPDAT.PUP), the largest first: the system software, then the font package, then the preinstalled apps."""
    folder = firmware_home(home)
    found = []
    try:
        for entry in folder.iterdir():
            if entry.is_file() and entry.suffix.lower() in FIRMWARE_SUFFIXES:
                found.append(entry)
            elif entry.is_dir():
                found += [p for p in entry.iterdir() if p.is_file() and p.suffix.lower() in FIRMWARE_SUFFIXES]
    except OSError:
        return []
    return sorted(found, key=lambda p: (-p.stat().st_size, str(p)))


def file_key(path: Path) -> str:
    """A file as it is now (its place, size and time): the same key, the same file."""
    try:
        stat = path.stat()
    except OSError:
        return ""
    return f"{path}|{stat.st_size}|{int(stat.st_mtime)}"


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

PARTS = {"app": "The game", "patch": "Its update", "addcont": "Its extra content"}


def removal_items(game: Game, vita_fs: Path, in_steam: bool) -> tuple[list[keep.Item], str]:
    """The keep page's rows for Remove game: the game in Vita3K's storage (ux0/app/<title ID>), then its update and
    extra content (ux0/patch, ux0/addcont) when they are there, then its shortcut in Steam when it is in Steam. The
    saves (ux0/user/00/savedata) are never among them. No rows for a game that is not in ux0/app."""
    app = vita_fs / "ux0" / "app"
    if game.folder.parent != app or not game.name:
        return [], f"{game.title} is not in Vita3K's storage ({app}): delete it by hand."
    folders = [game.folder, *[f for f in (vita_fs / "ux0" / kind / game.name for kind in ("patch", "addcont"))
                              if _is_dir(f)]]
    items = [keep.Item(str(f), f"{PARTS.get(f.parent.name, f.parent.name)}, ux0/{f.parent.name}/{f.name}", (f,))
             for f in folders]
    if in_steam:
        items.append(keep.Item(STEAM_ITEM, "Its shortcut in Steam"))
    return items, ""
