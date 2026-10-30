# SPDX-License-Identifier: GPL-3.0-or-later
"""PPSSPP Manager: installs PPSSPP, the PSP emulator, on the handheld (one tested release, in portable mode), offers
its settings, and plays the games in the chosen folders and on its memory stick, alone and full screen; puts them in
Steam; the log. The BC250 suite's PPSSPP Manager's parts in the portable window."""

APP_NAME = "PPSSPP Manager"
APP_ID = "windows-portable-ppsspp"
EXE_NAME = "PPSSPP-Manager"   # the program's file name in a release
SUITE = "windows-portable-suite"
__version__ = "3.1.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-ppsspp.ini, the log in %LOCALAPPDATA%\windows-portable-suite\windows-portable-ppsspp\ (bc250_core.applog)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-ppsspp-v",
               settings_org=SUITE, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "EXE_NAME", "INFO", "LOGO_PATH", "ROOT", "SUITE", "__version__"]
