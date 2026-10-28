# SPDX-License-Identifier: GPL-3.0-or-later
"""PS2 games on the BC-250 with PCSX2: installs a pinned PCSX2 release and sets it up, takes the PS2 BIOS, finds the
games in the chosen folders and adds them to Steam, where a game is started."""

APP_NAME = "PCSX2 Manager"
APP_ID = "bc250-pcsx2-manager"
__version__ = "2.3.1"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-pcsx2-manager/bc250-pcsx2-manager.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="pcsx2-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
