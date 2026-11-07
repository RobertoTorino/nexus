# SPDX-License-Identifier: GPL-3.0-or-later
"""Support Checker: What the suite's apps need on this handheld: Windows' updates, the tools and runtimes, the apps' versions."""

APP_NAME = "Support Checker"
APP_ID = "windows-portable-support"
EXE_NAME = "Support-Checker"   # the program's file name in a release
SUITE = "windows-portable-suite"
__version__ = "1.1.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-support.ini, the log in %LOCALAPPDATA%\windows-portable-suite\windows-portable-support\ (bc250_core.applog)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-support-v",
               settings_org=SUITE, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "EXE_NAME", "INFO", "LOGO_PATH", "ROOT", "SUITE", "__version__"]
