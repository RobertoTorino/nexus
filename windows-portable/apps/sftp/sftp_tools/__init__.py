# SPDX-License-Identifier: GPL-3.0-or-later
"""sFTP Tools: Moves files to and from another computer over SFTP, and starts or stops its SSH server."""

APP_NAME = "sFTP Tools"
APP_ID = "windows-portable-sftp"
EXE_NAME = "sFTP-Tools"   # the program's file name in a release
SUITE = "windows-portable-suite"
__version__ = "1.1.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-sftp.ini, the log in %LOCALAPPDATA%\windows-portable-suite\windows-portable-sftp\ (bc250_core.applog)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-sftp-v",
               settings_org=SUITE, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "EXE_NAME", "INFO", "LOGO_PATH", "ROOT", "SUITE", "__version__"]
