# SPDX-License-Identifier: GPL-3.0-or-later
"""PS4 games on the BC-250 with shadPS4: installs a pinned shadPS4 release, checks the system modules, finds the
games in the chosen folders and adds them to Steam, so a game starts from Steam on the desktop or in Big Picture
Mode."""

APP_NAME = "shadPS4 Manager"
APP_ID = "bc250-shadps4-manager"
__version__ = "2.3.2"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-shadps4-manager/bc250-shadps4-manager.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="shadps4-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
