# SPDX-License-Identifier: GPL-3.0-or-later
"""Starting with the desktop: an XDG autostart entry that runs the launcher minimized, so the screen shows the
values from login on. Only the user's own ~/.config/autostart; nothing needs root."""

from __future__ import annotations

import os
from pathlib import Path

from . import APP_ID, APP_NAME, ROOT

MINIMIZED_FLAG = "--minimized"


def entry_path(config_home: Path | None = None) -> Path:
    config_home = config_home or Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return config_home / "autostart" / f"{APP_ID}.desktop"


def launcher(home: Path | None = None) -> Path:
    """The launcher install.sh writes."""
    return (home or Path.home()) / ".local" / "bin" / APP_ID


def enabled(config_home: Path | None = None) -> bool:
    return entry_path(config_home).is_file()


def set_enabled(on: bool, config_home: Path | None = None, home: Path | None = None) -> None:
    path = entry_path(config_home)
    if not on:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[Desktop Entry]\n"
                    "Type=Application\n"
                    f"Name={APP_NAME}\n"
                    f"Exec={launcher(home)} {MINIMIZED_FLAG}\n"
                    f"Icon={ROOT / 'images' / f'{APP_ID}-128.png'}\n"
                    "Terminal=false\n"
                    "X-GNOME-Autostart-enabled=true\n"
                    "X-KDE-autostart-after=panel\n", encoding="utf-8")
