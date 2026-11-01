# SPDX-License-Identifier: GPL-3.0-or-later
"""USB HD Cam: Makes the PS5 HD Camera a webcam: its driver once, then its firmware with the A button."""

APP_NAME = "USB HD Cam"
APP_ID = "windows-portable-hdcam"
EXE_NAME = "USB-HD-Cam"   # the program's file name in a release
SUITE = "windows-portable-suite"
__version__ = "0.1.1"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-hdcam.ini, the log in %LOCALAPPDATA%\windows-portable-suite\windows-portable-hdcam\ (bc250_core.applog)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-hdcam-v",
               settings_org=SUITE, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "EXE_NAME", "INFO", "LOGO_PATH", "ROOT", "SUITE", "__version__"]
