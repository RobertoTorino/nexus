# SPDX-License-Identifier: GPL-3.0-or-later
"""Your games: the app's own folders (owner, 30-10-2026: the games, the packages and the firmware are put there,
nothing is browsed to; the BC250 suite's RPCS3 Manager keeps chosen folders): Games\\PS3 in your user folder, made
when it is missing, and Games\\PS3 on a removable drive (an SD card, a USB stick) that has one (fixed), with
Games\\PS3\\Firmware for the PS3's firmware (firmware_home). Then the games found in them, installed in RPCS3 and
known to it (games.scan), which have a Steam shortcut of this app, and the plan Update Steam carries out: the marked
games in Steam, the others out, and the shortcuts of games no longer found out too. The suite's SteamGridDB key and
the pictures found are in the suite's folders (%APPDATA%\\windows-portable-suite\\steamgriddb-key, the app's
covers\\)."""

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

GAMES_HOME = Path("Games") / "PS3"      # the app's own game folder, in the user's folder and on a removable drive
FIRMWARE = "Firmware"                   # the firmware's folder in it
FIRMWARE_SUFFIXES = (".pup",)
FIRMWARE_NAME = "ps3updat.pup"          # the PS3's own name for it, taken first
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


def firmware_home(home: Path | None = None) -> Path:
    """Where the firmware is put: Games\\PS3\\Firmware in the user's folder."""
    return (home or Path.home()) / GAMES_HOME / FIRMWARE


def fixed(home: Path | None = None, drives: Callable[[], list[Path]] = removable_drives) -> list[Path]:
    """The app's own game folders (owner, 30-10-2026: drop the games and packages there, no browsing): Games\\PS3 in
    the user's folder, made with its Firmware folder when they are missing, then Games\\PS3 on each removable drive
    that has one."""
    own = (home or Path.home()) / GAMES_HOME
    try:
        firmware_home(home).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return [own, *[d / GAMES_HOME for d in drives() if _is_dir(d / GAMES_HOME)]]


def firmware_file(home: Path | None = None) -> Path | None:
    """The firmware file put in Games\\PS3\\Firmware: PS3UPDAT.PUP, else the first .PUP by name; None without one."""
    try:
        found = sorted((p for p in firmware_home(home).iterdir()
                        if p.suffix.lower() in FIRMWARE_SUFFIXES and p.is_file()), key=lambda p: p.name.casefold())
    except OSError:
        return None
    return next((p for p in found if p.name.casefold() == FIRMWARE_NAME), found[0] if found else None)


def file_key(path: Path) -> str:
    """A file as it is now (its name, size and time): another key means another or a changed file; "" when it
    cannot be read."""
    try:
        info = path.stat()
    except OSError:
        return ""
    return f"{path.name}|{info.st_size}|{info.st_mtime_ns}"


def kept_path(path: Path) -> str:
    """A package's place as the kept packages note it, the same however Windows spells its case."""
    return os.path.normcase(str(path))


def kept_key(path: Path) -> str:
    """An installed package the user kept (owner, 01-11-2026: before deleting anything, let the user decide what to
    keep), as it is now: its place, size and time; the same file changed is another key, and waits again."""
    try:
        info = path.stat()
    except OSError:
        return ""
    return f"{kept_path(path)}|{info.st_size}|{info.st_mtime_ns}"


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


def pending(found: list[Game], marked: set[str], in_steam: dict[str, str], outdated: set[str] = frozenset()) -> bool:
    """Whether Update Steam would change anything: a game in or out, a name in Steam that differs, or a shortcut that
    does not start the play mode yet (*outdated*, shortcuts.outdated)."""
    add, remove = plan(found, marked, in_steam)
    named = shortcuts.names(add)
    return bool(remove) or any(in_steam.get(str(g.eboot)) != named[g.eboot] or str(g.eboot) in outdated for g in add)


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


def removal(game: Game, chosen: list[Path], found: list[Game], hdd0_game: Path) -> tuple[list[Path], str]:
    """The folders Remove game offers to delete (owner, 30-10-2026: a game that no longer plays goes, files and all;
    the keep page lets the user keep any of them, owner, 01-11-2026): a game installed from a package, its folder in
    RPCS3's dev_hdd0\\game (its update and add-ons are in it); a disc game in the app's Games\\PS3 folders, its
    folder, then its update in dev_hdd0\\game (the game data in a folder named by its ID). With none, why not: a drive, a game folder of the list (or one holding one), a folder holding another
    game, or a disc game outside the app's folders is never deleted by the app."""
    folder = game.folder
    if not game.disc:
        if os.path.normcase(str(folder.parent)) != os.path.normcase(str(hdd0_game)):
            return [], f"{game.title} is installed in {folder.parent}, not in RPCS3's dev_hdd0: delete it by hand."
        return [folder], ""
    if folder.parent == folder:
        return [], f"{game.title} is at the top of {folder}: delete its files by hand."
    for place in chosen:
        if os.path.normcase(str(place)) == os.path.normcase(str(folder)) or folder in place.parents:
            return [], (f"{game.title} is in {folder.name}, one of the app's game folders itself: delete its files "
                        "by hand.")
    if not any(place in folder.parents for place in chosen):
        return [], f"{game.title} is in {folder.parent}, outside the app's Games\\PS3 folders: delete it by hand."
    for other in found:
        if other.eboot != game.eboot and folder in other.eboot.parents:
            return [], f"{folder.name} holds another game too ({other.title}): delete {game.title}'s files by hand."
    data = hdd0_game / game.title_id if game.title_id else None
    if data is not None and (not _is_dir(data) or any(data in other.eboot.parents for other in found)):
        data = None                                     # no update, or a game of its own
    return [folder, *([data] if data is not None else [])], ""

