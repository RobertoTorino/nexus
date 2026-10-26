# SPDX-License-Identifier: GPL-3.0-or-later
"""The app as a non-Steam game, for Game Mode: a shortcut that runs the launcher install.sh wrote
(~/.local/bin/bazzite-datstation), with artwork drawn from the app's logo by core's steam_art. The file and its format are core's
(bc250_core.steam); the pattern is the shadPS4 Manager's."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from bc250_core import steam, steam_art
from bc250_core.platform import bin_home

from . import APP_ID, APP_NAME

TAGS = ("PlayStation", APP_NAME)


class NotInstalled(Exception):
    """The launcher is missing: the app runs from a checkout and install.sh was not run."""


def launcher_path() -> Path:
    return bin_home() / APP_ID


def ours(item: dict) -> bool:
    """Any shortcut this app made: it runs the launcher (named after the app, wherever it is)."""
    exe = str(item.get("Exe", "")).strip('"').replace("\\", "/")
    return exe.rsplit("/", 1)[-1] == APP_ID


def entry(launcher: Path, logo: Path) -> dict:
    return steam.shortcut_entry(f'"{launcher}"', APP_NAME, f'"{launcher.parent}/"', str(steam.shortcut_icon(logo)),
                                "", TAGS)


def in_steam(folder: Path) -> bool:
    return steam.has_shortcut(folder, ours)


def changes(launcher: Path, logo: Path, remove: bool = False, art: bool = True) -> list[steam.Change]:
    """The change for core's write_shortcuts: the shortcut added (or brought up to date), or taken out."""
    if remove:
        return [steam.Change(entry(launcher, logo), ours, remove=True)]
    return [steam.Change(entry(launcher, logo), ours, draw_art(logo) if art else {})]


def _apply(remove: bool, launcher: Path | None, logo: Path, steam_dir: Path | None,
           closed: Callable[[Callable[[], None]], bool], art: bool) -> bool:
    launcher = launcher or launcher_path()
    if not launcher.is_file():
        raise NotInstalled(f"The launcher {launcher} does not exist: run install.sh first, so Steam has a program "
                           "to start.")
    folder = steam_dir or steam.find_steam()
    if folder is None:
        raise steam.SteamError("Steam was not found on this system (no userdata folder).")
    return closed(lambda: steam.write_shortcuts(folder, changes(launcher, logo, remove=remove, art=art)))


def add(logo: Path, launcher: Path | None = None, steam_dir: Path | None = None,
        closed: Callable[[Callable[[], None]], bool] = steam.with_steam_closed, art: bool = True) -> bool:
    """Add the shortcut for every Steam user, Steam closed meanwhile; returns whether Steam was restarted.
    Raises NotInstalled, steam.SteamError or steam.ShortcutError with the reason."""
    return _apply(False, launcher, logo, steam_dir, closed, art)


def remove(logo: Path, launcher: Path | None = None, steam_dir: Path | None = None,
           closed: Callable[[Callable[[], None]], bool] = steam.with_steam_closed) -> bool:
    return _apply(True, launcher, logo, steam_dir, closed, False)


# --- The artwork -----------------------------------------------------------------------------------------------

def draw_art(logo: Path) -> dict[str, bytes]:
    """The four images as PNG bytes, drawn from the app's icon by core's steam_art: the icon with the app's name, and
    the icon file itself as the logo on the banner."""
    return steam_art.draw_icon_art(logo, APP_NAME, TAGS[0])
