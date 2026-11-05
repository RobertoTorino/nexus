# SPDX-License-Identifier: GPL-3.0-or-later
"""HD Controller: Sony's DualSense and DualSense Edge controllers on a Windows handheld: their battery and firmware,
the firmware update Sony offers on a PS5 and in its own app, the face buttons and the motors tested, and the Edge's
profiles. The BC250 Bazzite Suite's USB HD Control on the suite's portable window; it talks to the controller through
hidapi where the BC250 app uses Linux's hidraw."""

APP_NAME = "HD Controller"
APP_ID = "windows-portable-hdcontrol"
EXE_NAME = "HD-Controller"   # the program's file name in a release
SUITE = "windows-portable-suite"
__version__ = "0.1.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-hdcontrol.ini; the log, the firmware images and the
# profiles' backups in %LOCALAPPDATA%\windows-portable-suite\windows-portable-hdcontrol\ (bc250_core.applog)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-hdcontrol-v",
               settings_org=SUITE, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "EXE_NAME", "INFO", "LOGO_PATH", "ROOT", "SUITE", "__version__"]
