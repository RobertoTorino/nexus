# SPDX-License-Identifier: GPL-3.0-or-later
"""RPCS3 Manager: installs RPCS3, the PlayStation 3 emulator, on the handheld (one tested build, beside which RPCS3
keeps everything), takes the PS3's firmware and your packages, offers its settings, finds your games and puts them in
Steam, where they are played alone and full screen; the log. The BC250 suite's RPCS3 Manager's parts in the portable
window."""

APP_NAME = "RPCS3 Manager"
APP_ID = "windows-portable-rpcs3"
EXE_NAME = "RPCS3-Manager"   # the program's file name in a release
SUITE = "windows-portable-suite"
__version__ = "3.3.1"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-rpcs3.ini, the log in %LOCALAPPDATA%\windows-portable-suite\windows-portable-rpcs3\ (bc250_core.applog)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-rpcs3-v",
               settings_org=SUITE, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "EXE_NAME", "INFO", "LOGO_PATH", "ROOT", "SUITE", "__version__"]
