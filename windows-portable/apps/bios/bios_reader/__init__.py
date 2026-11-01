# SPDX-License-Identifier: GPL-3.0-or-later
"""BIOS Reader: The BIOS's setup screens and defaults, hidden menus included, from a BIOS file. It only reads."""

APP_NAME = "BIOS Reader"
APP_ID = "windows-portable-bios"
EXE_NAME = "BIOS-Reader"   # the program's file name in a release
SUITE = "windows-portable-suite"
__version__ = "0.4.1"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-bios.ini, the log in %LOCALAPPDATA%\windows-portable-suite\windows-portable-bios\ (bc250_core.applog)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-bios-v",
               settings_org=SUITE, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "EXE_NAME", "INFO", "LOGO_PATH", "ROOT", "SUITE", "__version__"]
