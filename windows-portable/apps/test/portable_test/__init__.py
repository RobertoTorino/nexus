# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows Portable Test: getting to know the handheld. What Windows reports about the device, how its network does,
and every button, stick and trigger of its controller as you press them. It reads and shows; it changes nothing on
the device."""

APP_NAME = "Windows Portable Test"
APP_ID = "windows-portable-test"
EXE_NAME = "Windows-Portable-Test"   # the program's file name in a release (owner, 28-10-2026; was Windows-PT)
SUITE = "windows-portable-suite"
__version__ = "4.3.1"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-test.ini, the log in
# %LOCALAPPDATA%\windows-portable-suite\windows-portable-test\ (bc250_core.applog)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-test-v",
               settings_org=SUITE, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "EXE_NAME", "INFO", "LOGO_PATH", "ROOT", "SUITE", "__version__"]
