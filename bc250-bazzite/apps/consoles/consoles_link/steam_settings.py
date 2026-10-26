# SPDX-License-Identifier: AGPL-3.0-or-later
"""Steam's "Guide Button Focus Steam" (Settings > Controller > Show Advanced Settings), from the app: with it on,
Steam comes to the front when the PS button is pressed, while the press also goes to the console.

Steam keeps it per Steam user as "Controller_CheckGuideButton" ("1" on, "0" off; on when it is missing) in
userdata/<user>/config/localconfig.vdf. Steam holds its settings in memory and writes that file when it exits, so a
change while it runs would be lost: set_guide_focus() closes Steam first (steam -shutdown), changes every user's
file, and starts Steam again in the background as the desktop starts it at login (Bazzite's bazzite-steam -silent,
elsewhere steam -silent). In Game Mode Steam keeps the PS button
for its own menu whatever the setting says, and it is the session itself, so nothing is changed there."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Callable

# Steam itself (finding it, closing it for a change) is core's; named here as before.
from bc250_core.steam import (SHUTDOWN_TIMEOUT, STEAM_DIRS, Run, SteamError, _run, find_steam,  # noqa: F401
                              game_mode, start_command, steam_running, with_steam_closed)

KEY = "Controller_CheckGuideButton"
_LINE = re.compile(rf'^(\t*)"{KEY}"(\s+)"(\d)"\s*$', re.MULTILINE)


def user_configs(steam: Path) -> list[Path]:
    """Every Steam user's localconfig.vdf."""
    return sorted(p for p in (steam / "userdata").glob("*/config/localconfig.vdf") if p.is_file())


def guide_focus(configs: list[Path]) -> bool | None:
    """Whether the PS button brings Steam to the front: True when it does for any Steam user (it is on when the key
    is missing), None without users."""
    if not configs:
        return None
    for config in configs:
        match = _LINE.search(config.read_text(encoding="utf-8", errors="replace"))
        if match is None or match.group(3) != "0":
            return True
    return False


def write_guide_focus(config: Path, on: bool) -> None:
    """Sets the key in one localconfig.vdf: the line replaced, or added at the end of the top block."""
    text = config.read_text(encoding="utf-8", errors="replace")
    value = "1" if on else "0"
    if _LINE.search(text):
        text = _LINE.sub(lambda m: f'{m.group(1)}"{KEY}"{m.group(2)}"{value}"', text, count=1)
    else:
        end = text.rstrip().rfind("}")
        if end < 0:
            raise SteamError(f"{config} is not a Steam configuration file.")
        text = text[:end] + f'\t"{KEY}"\t\t"{value}"\n' + text[end:]
    temporary = config.with_name(config.name + ".bc250-tmp")
    temporary.write_text(text, encoding="utf-8")
    os.chmod(temporary, config.stat().st_mode & 0o7777)
    temporary.replace(config)


def set_guide_focus(on: bool, steam: Path, run: Run = _run, running: Callable[[], bool] = steam_running,
                    timeout: float = SHUTDOWN_TIMEOUT, sleep: Callable[[float], None] = time.sleep) -> bool:
    """Changes the setting for every Steam user; Steam is closed first and started again when it was running.
    Returns whether Steam was restarted."""
    if game_mode():
        raise SteamError("In Game Mode Steam keeps the PS button for its own menu; change it in Desktop Mode.")
    configs = user_configs(steam)
    if not configs:
        raise SteamError("Steam has no users on this system yet.")

    def change() -> None:
        for config in configs:
            write_guide_focus(config, on)
    return with_steam_closed(change, run, running, timeout, sleep)
