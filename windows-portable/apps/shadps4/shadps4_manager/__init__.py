# SPDX-License-Identifier: GPL-3.0-or-later
"""shadPS4 Manager: installs shadPS4, the PlayStation 4 emulator, on the handheld (one tested release, its files in
its portable folder beside it), takes the system modules of your PS4, unpacks your packages (.pkg), offers its
settings and the shadNet account it signs in with, finds your games and puts them in Steam, where they are played
full screen; the log. The BC250 suite's shadPS4 Manager's parts in the portable window."""

APP_NAME = "shadPS4 Manager"
APP_ID = "windows-portable-shadps4"
EXE_NAME = "shadPS4-Manager"   # the program's file name in a release
SUITE = "windows-portable-suite"
__version__ = "2.1.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-shadps4.ini, the log in %LOCALAPPDATA%\windows-portable-suite\windows-portable-shadps4\ (bc250_core.applog)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-shadps4-v",
               settings_org=SUITE, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "EXE_NAME", "INFO", "LOGO_PATH", "ROOT", "SUITE", "__version__"]
