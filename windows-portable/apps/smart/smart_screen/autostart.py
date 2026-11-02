# SPDX-License-Identifier: GPL-3.0-or-later
"""Starting with Windows: a shortcut in the user's own Startup folder that starts the program minimized, so the screen
shows the values from sign-in on. As the BC250 suite's USB IPS3.5 writes an XDG autostart entry; nothing goes in the
registry and nothing needs an administrator. Only the installed program can start so (a checkout runs through
run.ps1)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from bc250_core import platform

from . import APP_NAME

MINIMIZED_FLAG = "--minimized"


def startup_folder() -> Path:
    """The user's Startup folder: what Windows starts at sign-in."""
    return platform.start_menu() / "Startup"


def entry_path(folder: Path | None = None) -> Path:
    return (folder or startup_folder()) / f"{APP_NAME}.lnk"


def program() -> Path | None:
    """The installed program (a release's Smart-Screen.exe); None when the app runs from the checkout."""
    return Path(sys.executable) if getattr(sys, "frozen", False) else None


def enabled(folder: Path | None = None) -> bool:
    return entry_path(folder).is_file()


def set_enabled(on: bool, folder: Path | None = None, target: Path | None = None,
                make: Callable[..., None] | None = None) -> None:
    """The shortcut written (by *make*, default core's make_shortcut) or removed. Raises RuntimeError when it cannot
    be written (from the checkout: there is no program to start)."""
    path = entry_path(folder)
    if not on:
        path.unlink(missing_ok=True)
        return
    target = target or program()
    if target is None:
        raise RuntimeError("Only the installed app starts with Windows: install it from the portal first.")
    (make or platform.make_shortcut)(path, target, MINIMIZED_FLAG, icon=target, description=f"{APP_NAME}, minimized: the values on the screen")
