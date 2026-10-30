# SPDX-License-Identifier: GPL-3.0-or-later
"""Vita3K Manager: installs Vita3K, the PS Vita emulator, on the handheld (one tested build, its files in its
portable folder beside it), has Vita3K install the PS Vita's firmware and your games, offers its settings, puts the
games installed in it in Steam, where they are played full screen; the log. The BC250 suite's Vita3K Manager's parts
in the portable window."""

APP_NAME = "Vita3K Manager"
APP_ID = "windows-portable-vita3k"
EXE_NAME = "Vita3K-Manager"   # the program's file name in a release
SUITE = "windows-portable-suite"
__version__ = "2.1.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-vita3k.ini, the log in %LOCALAPPDATA%\windows-portable-suite\windows-portable-vita3k\ (bc250_core.applog)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-vita3k-v",
               settings_org=SUITE, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "EXE_NAME", "INFO", "LOGO_PATH", "ROOT", "SUITE", "__version__"]
