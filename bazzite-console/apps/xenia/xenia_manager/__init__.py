# SPDX-License-Identifier: GPL-3.0-or-later
"""XBOX 360 games on the system with Xenia: installs a tested Xenia Canary build, finds the games in the chosen
folders and adds them to Steam for Game Mode."""

APP_NAME = "Xenia Manager"
APP_ID = "ps5-xenia-manager"
__version__ = "0.2.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/ps5-xenia-manager/ps5-xenia-manager.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="ps5-xenia-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
