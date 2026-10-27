# SPDX-License-Identifier: GPL-3.0-or-later
"""Decky Loader on the BC-250: installs a pinned Decky Loader release with its system service, shows whether it runs
and which plugins it has, and links /home/deck for plugins that need it. Decky's own menu is in Game Mode."""

APP_NAME = "Decky Loader Manager"
APP_ID = "bc250-decky-manager"
__version__ = "0.17.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-decky-manager/bc250-decky-manager.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="decky-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
