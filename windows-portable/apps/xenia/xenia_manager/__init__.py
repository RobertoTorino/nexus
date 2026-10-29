# SPDX-License-Identifier: GPL-3.0-or-later
"""Xenia Manager: installs Xenia, the Xbox 360 emulator, on the handheld (one tested Xenia Canary build, its files beside
it), offers its settings, finds your games in the folders you choose and puts them in Steam, where they are played full
screen; the log. The BC250 suite's Xenia Manager's parts in the portable window."""

APP_NAME = "Xenia Manager"
APP_ID = "windows-portable-xenia"
EXE_NAME = "Xenia-Manager"   # the program's file name in a release
SUITE = "windows-portable-suite"
__version__ = "1.0.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-xenia.ini, the log in %LOCALAPPDATA%\windows-portable-suite\windows-portable-xenia\ (bc250_core.applog)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-xenia-v",
               settings_org=SUITE, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "EXE_NAME", "INFO", "LOGO_PATH", "ROOT", "SUITE", "__version__"]
