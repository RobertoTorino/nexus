# SPDX-License-Identifier: GPL-3.0-or-later
"""The app as a non-Steam game (the BC250 app's Add to Steam, on Windows), so it starts from Steam's library and its
full-screen mode: a shortcut that runs DatStation itself, its program in a release (DatStation.exe) and its run.ps1 in
a hidden PowerShell window from the checkout (Steam cannot set PYTHONPATH), as Remote Play's console entries do. The
artwork is drawn from the app's icon by core's steam_art, as the BC250 app draws it.

The file, the shortcut's number and where its artwork goes are core's (bc250_core.steam). Steam reads and rewrites
these files itself, so they change with Steam closed (steam.with_steam_closed); the other non-Steam games in the file
stay as they are. Windows paths are quoted the way Steam writes them, in double quotes."""

from __future__ import annotations

import ntpath
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from bc250_core import play, steam, steam_art

from . import APP_NAME, EXE_NAME, ROOT

TAGS = ("PlayStation", APP_NAME)


def launcher(frozen: bool | None = None, program: str | None = None) -> tuple[str, list[str]]:
    """(the program the shortcut starts, its arguments): the app's own program in a release (*frozen*: built with
    PyInstaller), its run.ps1 in a hidden PowerShell window from the checkout."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if frozen:
        return program or sys.executable, []
    return play.POWERSHELL, ["-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File",
                             str(ROOT / "run.ps1")]


def entry(logo: Path, frozen: bool | None = None, program: str | None = None) -> dict:
    """The shortcut's fields, in the order Steam writes them."""
    exe, arguments = launcher(frozen, program)
    return steam.shortcut_entry(f'"{exe}"', APP_NAME, f'"{ntpath.dirname(exe)}\\"', str(steam.shortcut_icon(logo)),
                                subprocess.list2cmdline(arguments), TAGS)


def ours(item: dict) -> bool:
    """Any shortcut this app made: one that runs DatStation.exe (wherever it is), or PowerShell with this app's
    run.ps1. The fields by name whatever their case (steam.field)."""
    program = ntpath.basename(str(steam.field(item, "Exe")).strip('"')).lower()
    if program == f"{EXE_NAME}.exe".lower():
        return True
    if program != ntpath.basename(play.POWERSHELL).lower():
        return False
    try:
        words = shlex.split(str(steam.field(item, "LaunchOptions")).replace("\\", "/"))
    except ValueError:
        return False
    return bool(words) and words[-1].lower().endswith(f"/{ROOT.name}/run.ps1".lower())


def in_steam(folder: Path) -> bool:
    return steam.has_shortcut(folder, ours)


def changes(logo: Path, remove: bool = False, art: bool = True) -> list[steam.Change]:
    """The change for core's write_shortcuts: the shortcut added (or brought up to date), or taken out."""
    if remove:
        return [steam.Change(entry(logo), ours, remove=True)]
    return [steam.Change(entry(logo), ours, draw_art(logo) if art else {})]


def apply(logo: Path, steam_dir: Path, remove: bool = False,
          closed: Callable[[Callable[[], None]], bool] = steam.with_steam_closed, art: bool = True) -> bool:
    """The shortcut added for every Steam user (or with *remove* taken out), Steam closed meanwhile; returns whether
    Steam was started again. Raises steam.SteamError or steam.ShortcutError with the reason."""
    return closed(lambda: steam.write_shortcuts(steam_dir, changes(logo, remove=remove, art=art and not remove)))


def draw_art(logo: Path) -> dict[str, bytes]:
    """The four images as PNG bytes, drawn from the app's icon by core's steam_art: the icon with the app's name, and
    the icon file itself as the logo on the banner."""
    return steam_art.draw_icon_art(logo, APP_NAME, TAGS[0])
