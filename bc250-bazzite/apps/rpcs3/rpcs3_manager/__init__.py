# SPDX-License-Identifier: GPL-3.0-or-later
"""PS3 games on the BC-250 with RPCS3: installs a pinned RPCS3 build, takes the PS3 firmware, finds the games in
RPCS3 and the chosen folders and adds them to Steam, where a game is started."""

APP_NAME = "RPCS3 Manager"
APP_ID = "bc250-rpcs3-manager"
__version__ = "2.3.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-rpcs3-manager/bc250-rpcs3-manager.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="rpcs3-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
