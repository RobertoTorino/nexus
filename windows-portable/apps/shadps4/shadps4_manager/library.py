# SPDX-License-Identifier: GPL-3.0-or-later
"""Your games, as RPCS3 Manager and PCSX2 Manager on Windows keep them: the game folders (the app's settings; the BC250
suite's shadPS4 Manager keeps them in shadPS4's config.json, which only shadPS4's own window reads), the games found
in them (games.scan), which have a Steam shortcut of this app, and the plan Update Steam carries out: the marked games
in Steam, the others out, and the shortcuts of games no longer found out too.

On a handheld a folder is mostly one of a few places, so the usual ones are offered as they are (Games, Downloads and
Documents in your user folder) with every removable drive (an SD card, a USB stick); any other folder is chosen in
core's browser, made for the controller. Extract PKG offers the same places to unpack a package into (targets). The
suite's SteamGridDB key and the pictures found are in the suite's folders
(%APPDATA%\\windows-portable-suite\\steamgriddb-key, the app's covers\\)."""

from __future__ import annotations

import ctypes
import os
import string
import sys
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QSettings

from bc250_core import covers, steam
from bc250_core.platform import suite_config, suite_data

from . import APP_ID, SUITE, shortcuts
from .games import Game

FOLDERS_KEY = "games/folders"
DRIVE_REMOVABLE = 2                     # GetDriveTypeW


def key_file() -> Path:
    """The suite's SteamGridDB API key, the Windows Portable Suite's own (BC250's is in its ~/.config folder)."""
    return suite_config(SUITE) / "steamgriddb-key"


def covers_home() -> Path:
    return suite_data(SUITE) / APP_ID / "covers"


def folders(settings: QSettings) -> list[Path]:
    stored = settings.value(FOLDERS_KEY, [])
    stored = [stored] if isinstance(stored, str) else list(stored or [])
    return [Path(f) for f in stored if f]


def set_folders(settings: QSettings, chosen: list[Path]) -> None:
    settings.setValue(FOLDERS_KEY, [str(f) for f in chosen])


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


def suggested(chosen: list[Path], home: Path | None = None,
              drives: Callable[[], list[Path]] = removable_drives) -> list[Path]:
    """The usual places for games that are there and not chosen yet: Games, Downloads and Documents in the user's
    folder, then each removable drive."""
    home = home or Path.home()
    taken = {os.path.normcase(str(f)) for f in chosen}
    places = [home / "Games", home / "Downloads", home / "Documents", *drives()]
    return [p for p in places if _is_dir(p) and os.path.normcase(str(p)) not in taken]


def targets(chosen: list[Path], package: Path, home: Path | None = None,
            drives: Callable[[], list[Path]] = removable_drives) -> list[Path]:
    """Where Extract PKG may unpack *package*: the game folders first, then the usual places that are not one yet
    (suggested), then the package's own folder; each once."""
    places, seen = [], set()
    for place in [*chosen, *suggested(chosen, home, drives), package.parent]:
        key = os.path.normcase(str(place))
        if key not in seen and _is_dir(place):
            seen.add(key)
            places.append(place)
    return places


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
    again = " Steam was closed for it and starts again in the background." if restarted else ""
    return True, "\n".join([*notes, f"{len(add)} game(s) in Steam, under Non-Steam in its library"
                                      f"{f'; {len(remove)} taken out' if remove else ''}.{again}"]), found
