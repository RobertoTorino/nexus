# SPDX-License-Identifier: GPL-3.0-or-later
"""SFTP tools for the PlayStation 5 Bazzite host: browse and transfer files over SFTP, and manage the OpenSSH server (sshd) of a
Bazzite host from another computer."""

APP_NAME = "Bazzite SFTP Tools"
APP_ID = "ps5-sftp-tools"
__version__ = "0.1.1"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings, profiles in ~/.config/ps5-sftp-tools/, the log in ~/.local/share/ps5-sftp-tools/
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="ps5-sftp-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
