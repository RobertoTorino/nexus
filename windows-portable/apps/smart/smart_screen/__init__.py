# SPDX-License-Identifier: GPL-3.0-or-later
"""Smart Screen: the handheld's live values on a Turzx USB IPS screen (the Turing Smart Screen 3.5" and its family):
CPU, GPU, temperatures, power, memory, battery, network and disk, with the time, the date and the weather, in your
look. The BC250 suite's USB IPS3.5 made for the Windows Portable Suite."""

APP_NAME = "Smart Screen"
APP_ID = "windows-portable-smart"
EXE_NAME = "Smart-Screen"   # the program's file name in a release
SUITE = "windows-portable-suite"
__version__ = "0.2.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-smart.ini, the log in %LOCALAPPDATA%\windows-portable-suite\windows-portable-smart\ (bc250_core.applog)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-smart-v",
               settings_org=SUITE, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "EXE_NAME", "INFO", "LOGO_PATH", "ROOT", "SUITE", "__version__"]
