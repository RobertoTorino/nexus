# SPDX-License-Identifier: AGPL-3.0-or-later
"""A Steam shortcut per registered console, for Game Mode: a non-Steam game that runs the app's direct start
(bc250-console-link --stream <the console's host id>), with artwork of its own.

The file, the shortcut's number and where its artwork goes are core's (bc250_core.steam). The artwork is drawn here
from the app's icon by core's steam_art (owner, 16-10-2026): a background in the icon's color, the icon, the
console's name and its model, not the console maker's images; the icon is the logo Steam lays over the banner.

Steam reads and rewrites these files itself, so add_shortcut() changes them with Steam closed
(steam_settings.with_steam_closed). The other non-Steam games in the file stay as they are."""

from __future__ import annotations

from pathlib import Path

from bc250_core import steam as core_steam
from bc250_core import steam_art
from bc250_core.steam import ART, ShortcutError, appid, as_int32, read_vdf, user_folders, write_vdf  # noqa: F401

from . import APP_NAME
from .consoles import RegisteredConsole

LAUNCHER = "~/.local/bin/bc250-console-link"
TAG = "Console Link"


# --- The shortcut ----------------------------------------------------------------------------------------------

def shortcut_name(console: RegisteredConsole) -> str:
    return f"{console.nickname or console.target.console} (Console Link)"


def entry(console: RegisteredConsole, launcher: Path, icon: Path) -> dict:
    """The shortcut's fields, in the order Steam writes them."""
    return core_steam.shortcut_entry(f'"{launcher}"', shortcut_name(console), f'"{launcher.parent}/"',
                                     str(core_steam.shortcut_icon(icon)), f"--stream {console.key}", [TAG])


def ours(item: dict, console: RegisteredConsole) -> bool:
    """A shortcut this app made for this console (the program and the console's key), whatever its name now."""
    return (str(item.get("Exe", "")).strip('"').endswith("bc250-console-link")
            and str(item.get("LaunchOptions", "")).split() == ["--stream", console.key])


def put_shortcut(values: dict, new: dict, console: RegisteredConsole) -> dict:
    """The file's contents with the console's shortcut added, or replacing the one made before (the play time
    kept); the other shortcuts stay, numbered 0, 1, ... in their order."""
    return core_steam.put_shortcut(values, new, lambda item: ours(item, console))


def remove_shortcut(values: dict, console: RegisteredConsole) -> dict:
    return core_steam.remove_shortcut(values, lambda item: ours(item, console))


def has_shortcut(steam: Path, console: RegisteredConsole) -> bool:
    return core_steam.has_shortcut(steam, lambda item: ours(item, console))


def write_shortcut(steam: Path, console: RegisteredConsole, launcher: Path, icon: Path,
                   art: dict[str, bytes], remove: bool = False) -> int:
    """For every Steam user: the console's shortcut in shortcuts.vdf and its artwork in grid/ (or, with *remove*,
    both taken out). Steam must be closed. Returns the shortcut's appid."""
    change = core_steam.Change(entry(console, launcher, icon), lambda item: ours(item, console), art, remove)
    return core_steam.write_shortcuts(steam, [change])[0]


# --- The artwork -----------------------------------------------------------------------------------------------

def draw_art(console: RegisteredConsole, logo: Path) -> dict[str, bytes]:
    """The four images as PNG bytes, drawn from the app's icon (*logo*, 512 px) by core's steam_art: the icon with
    the console's name and model, the banner with the name and the app's name; the icon is the logo."""
    name, model = console.nickname or console.target.console, console.target.console
    return steam_art.draw_icon_art(logo, name, f"{model} · Remote Play", f"{APP_NAME.upper()} · {model}")
