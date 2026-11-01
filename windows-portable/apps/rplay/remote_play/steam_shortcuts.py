# SPDX-License-Identifier: AGPL-3.0-or-later
"""A Steam entry per registered console (Console Link's steam_shortcuts.py, for Windows): a non-Steam game that runs
the app's direct start, Remote-Play.exe --stream <the console's key>, with artwork of its own, so the console is
played from Steam's library and its full-screen mode like the emulator apps' games. From a checkout the entry runs
run.ps1 in a hidden PowerShell window, as core's play mode does (Steam cannot set PYTHONPATH).

The file, the entry's number and where its artwork goes are core's (bc250_core.steam); the artwork is drawn from the
app's icon by core's steam_art (owner, 16-10-2026: the icon's color, the icon, the console's name and its model, not
the console maker's images). Steam reads and rewrites these files itself, so they change with Steam closed
(steam.with_steam_closed). The other non-Steam games in the file stay as they are."""

from __future__ import annotations

import ntpath
import shlex
import sys
from pathlib import Path

from bc250_core import play, steam, steam_art

from . import APP_NAME, EXE_NAME, ROOT
from .consoles import RegisteredConsole

TAGS = ("Remote Play",)
FLAG = "--stream"


def launcher(frozen: bool | None = None, program: str | None = None) -> tuple[str, list[str]]:
    """(the program the entry starts, its arguments before --stream): the app's own program in a release, its
    run.ps1 in a hidden PowerShell window from the checkout."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if frozen:
        return program or sys.executable, []
    return play.POWERSHELL, ["-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File",
                             str(ROOT / "run.ps1")]


def shortcut_name(console: RegisteredConsole) -> str:
    return f"{console.nickname or console.target.console} (Remote Play)"


def entry(console: RegisteredConsole, logo: Path, frozen: bool | None = None, program: str | None = None) -> dict:
    """The entry's fields, in the order Steam writes them; Windows paths in double quotes, as Steam writes them."""
    exe, before = launcher(frozen, program)
    return steam.shortcut_entry(f'"{exe}"', shortcut_name(console), f'"{ntpath.dirname(exe)}\\"',
                                str(steam.shortcut_icon(logo)),
                                play.launch_options(before, f"{FLAG} {console.key}").strip(), TAGS)


def _key(item: dict) -> str:
    """The console an entry of this app streams ("" for any other entry): the word after --stream, of an entry that
    runs the app's program or PowerShell. The fields by name whatever their case (steam.field)."""
    program = ntpath.basename(str(steam.field(item, "Exe")).strip('"')).lower()
    if program not in play.programs(EXE_NAME):
        return ""
    try:
        words = shlex.split(str(steam.field(item, "LaunchOptions")).replace("\\", "/"))
    except ValueError:
        return ""
    if FLAG not in words[:-1]:
        return ""
    return words[words.index(FLAG) + 1]


def ours(console: RegisteredConsole):
    """Recognizes the console's entry (the program and the console's key), whatever its name now."""
    return lambda item: _key(item) == console.key


def in_steam(folder: Path) -> set[str]:
    """The keys of the consoles with an entry, for any Steam user."""
    return {key for item in steam.shortcuts(folder) if (key := _key(item))}


def change(console: RegisteredConsole, logo: Path, remove: bool = False) -> steam.Change:
    """The console's entry for core's write_shortcuts: added (or brought up to date), or with *remove* taken out."""
    return steam.Change(entry(console, logo), ours(console), {} if remove else draw_art(console, logo), remove)


def draw_art(console: RegisteredConsole, logo: Path) -> dict[str, bytes]:
    """The four images as PNG bytes, drawn from the app's icon by core's steam_art: the icon with the console's name
    and model, the banner with the name and the app's name; the icon is the logo."""
    name, model = console.nickname or console.target.console, console.target.console
    return steam_art.draw_icon_art(logo, name, f"{model} · {APP_NAME}", f"{APP_NAME.upper()} · {model}")
