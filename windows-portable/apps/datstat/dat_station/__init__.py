# SPDX-License-Identifier: GPL-3.0-or-later
"""DatStation: PlayStation knowledge on your handheld: a quiz against the clock, the consoles' history, system software versions, region codes, user guides and PS news.
The BC250 Bazzite Suite's Bazzite DatStation (the PlayStation knowledge part of the DatStation Android app), on the
Windows Portable Suite's handheld window."""

APP_NAME = "DatStation"
APP_ID = "windows-portable-datstat"
EXE_NAME = "DatStation"   # the program's file name in a release
SUITE = "windows-portable-suite"
__version__ = "1.1.0"

from pathlib import Path

from bc250_core import AppInfo

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"
DATA_DIR = PACKAGE_DIR / "data"                 # the questions and the system software versions, as JSON
SOUNDS_DIR = PACKAGE_DIR / "sounds"             # the quiz music
REPO_URL = "https://github.com/RobertoTorino/nexus"
ANDROID_URL = "https://github.com/RobertoTorino/DatStation"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-datstat.ini, the log in %LOCALAPPDATA%\windows-portable-suite\windows-portable-datstat\ (bc250_core.applog)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-datstat-v",
               settings_org=SUITE, settings_ini=True)

__all__ = ["ANDROID_URL", "APP_ID", "APP_NAME", "DATA_DIR", "EXE_NAME", "INFO", "LOGO_PATH", "PACKAGE_DIR",
           "REPO_URL", "ROOT", "SOUNDS_DIR", "SUITE", "__version__"]
