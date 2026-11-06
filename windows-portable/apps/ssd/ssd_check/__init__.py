# SPDX-License-Identifier: GPL-3.0-or-later
"""SSD Check: The health, power cycles and power-on hours of the handheld's SSD and the drives on it."""

APP_NAME = "SSD Check"
APP_ID = "windows-portable-ssd"
EXE_NAME = "SSD-Check"   # the program's file name in a release
SUITE = "windows-portable-suite"
__version__ = "0.1.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-ssd.ini, the log in %LOCALAPPDATA%\windows-portable-suite\windows-portable-ssd\ (bc250_core.applog)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-ssd-v",
               settings_org=SUITE, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "EXE_NAME", "INFO", "LOGO_PATH", "ROOT", "SUITE", "__version__"]
