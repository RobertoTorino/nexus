# SPDX-License-Identifier: GPL-3.0-or-later
"""PCSX2 Manager: installs PCSX2, the PlayStation 2 emulator, on the handheld (one tested release, in portable
mode), sets it up to open ready to play with the handheld's controller, offers its settings, and opens it; the games
in the chosen folders, played and put in Steam; the memory cards; the log. The BC250 suite's PCSX2 Manager's parts in
the portable window."""

APP_NAME = "PCSX2 Manager"
APP_ID = "windows-portable-pcsx2"
EXE_NAME = "PCSX2-Manager"   # the program's file name in a release
SUITE = "windows-portable-suite"
__version__ = "0.2.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-pcsx2.ini, the log in %LOCALAPPDATA%\windows-portable-suite\windows-portable-pcsx2\ (bc250_core.applog)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-pcsx2-v",
               settings_org=SUITE, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "EXE_NAME", "INFO", "LOGO_PATH", "ROOT", "SUITE", "__version__"]
