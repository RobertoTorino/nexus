# SPDX-License-Identifier: AGPL-3.0-or-later
"""Remote Play for the handheld: find the PS4 and PS5 consoles on the network, register the handheld with one, wake
it and stream it full screen. The BC250 Bazzite Suite's Console Link made for the handheld; its protocol code is
ported from the reference implementation, chiaki-ng (AGPL-3.0; see the README's License section)."""

APP_NAME = "Remote Play"
APP_ID = "windows-portable-rplay"
EXE_NAME = "Remote-Play"   # the program's file name in a release
SUITE = "windows-portable-suite"
__version__ = "0.9.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-rplay.ini; the log and the registered consoles in
# %LOCALAPPDATA%\windows-portable-suite\windows-portable-rplay\ (bc250_core.applog, consoles.py)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-rplay-v",
               settings_org=SUITE, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "EXE_NAME", "INFO", "LOGO_PATH", "ROOT", "SUITE", "__version__"]
