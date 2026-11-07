# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's own game folders (owner, 03-11-2026, from the Windows Portable Suite's RPCS3 Manager, 30-10-2026: fixed
folders, no folder choosing): Games/PS3 in the user's home folder, made with its Firmware folder when the app opens,
and Games/PS3 on each removable drive that has one (a USB drive or an SD card; core's drives). The disc games are
dropped there; the PS3's firmware (PS3UPDAT.PUP) goes in Games/PS3/Firmware, and the app gives it to RPCS3."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from bc250_core import keep
from bc250_core.drives import game_folders, removable_drives

from .games import Game

GAMES_HOME = Path("Games") / "PS3"      # the app's own game folder, in the home folder and on a removable drive
FIRMWARE = "Firmware"                   # the firmware's folder in it
FIRMWARE_SUFFIXES = (".pup",)
FIRMWARE_NAME = "ps3updat.pup"          # the PS3's own name for it, taken first


def firmware_home(home: Path) -> Path:
    """Where the firmware is put: Games/PS3/Firmware in the home folder."""
    return home / GAMES_HOME / FIRMWARE


def fixed(home: Path, drives: Callable[[], list[Path]] = removable_drives) -> list[Path]:
    """The app's own game folders: Games/PS3 in the home folder, made with its Firmware folder when it is missing,
    then Games/PS3 on each removable drive that has one."""
    return game_folders(home, GAMES_HOME, drives, make=(FIRMWARE,))


def firmware_file(home: Path) -> Path | None:
    """The firmware file put in Games/PS3/Firmware: PS3UPDAT.PUP, else the first .PUP by name; None without one."""
    try:
        found = sorted((p for p in firmware_home(home).iterdir()
                        if p.suffix.lower() in FIRMWARE_SUFFIXES and p.is_file()), key=lambda p: p.name.casefold())
    except OSError:
        return None
    return next((p for p in found if p.name.casefold() == FIRMWARE_NAME), found[0] if found else None)


def file_key(path: Path) -> str:
    """A file as it is now (its name, size and time): the same key, the same file."""
    try:
        stat = path.stat()
    except OSError:
        return ""
    return f"{path.name}|{stat.st_size}|{int(stat.st_mtime)}"


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


def removal_items(game: Game, chosen: list[Path], found: list[Game], hdd0_game: Path,
                  in_steam: bool) -> tuple[list[keep.Item], str]:
    """The keep page's rows for Remove game: a game installed from a package, its folder in RPCS3's dev_hdd0/game
    (its update and add-ons are in it); a disc game in the app's Games/PS3 folders, its folder, then its update in
    dev_hdd0/game (the game data in a folder named by its ID); then its shortcut in Steam when it is in Steam. With
    no rows, why not: a drive, a game folder of the list (or one holding one), a folder holding another game, or a
    disc game outside the app's folders is never deleted by the app. The saves and the licenses are never among
    them."""
    folder = game.folder
    if not game.disc:
        if folder.parent != hdd0_game:
            return [], f"{game.title} is installed in {folder.parent}, not in RPCS3's dev_hdd0: delete it by hand."
        items = [keep.Item(str(folder), f"{folder.name} (the game, in RPCS3's games folder)", (folder,))]
    else:
        why = _in_own_folder(folder, chosen, game.title)
        if why:
            return [], why
        if not any(place in folder.parents for place in chosen):
            return [], f"{game.title} is in {folder.parent}, outside the app's Games/PS3 folders: delete it by hand."
        for other in found:
            if other.eboot != game.eboot and folder in other.eboot.parents:
                return [], f"{folder.name} holds another game too ({other.title}): delete {game.title}'s files by hand."
        items = [keep.Item(str(folder), f"{folder.name} (the disc game's folder)", (folder,))]
        data = hdd0_game / game.title_id if game.title_id else None
        if data is not None and _is_dir(data) and not any(data in other.eboot.parents for other in found):
            items.append(keep.Item(str(data), f"{data.name} (its update, in RPCS3's games folder)", (data,)))
    if in_steam:
        items.append(keep.Item(STEAM_ITEM, "Its shortcut in Steam"))
    return items, ""
