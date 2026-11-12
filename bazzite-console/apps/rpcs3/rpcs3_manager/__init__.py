# SPDX-License-Identifier: GPL-3.0-or-later
"""PS3 games on the system with RPCS3: installs a pinned RPCS3 build, takes the PS3 firmware, finds the games in
RPCS3 and the chosen folders and adds them to Steam, where a game is started."""

APP_NAME = "RPCS3 Manager"
APP_ID = "ps5-rpcs3-manager"
__version__ = "0.2.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/ps5-rpcs3-manager/ps5-rpcs3-manager.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="ps5-rpcs3-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
