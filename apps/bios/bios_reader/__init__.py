# SPDX-License-Identifier: GPL-3.0-or-later
"""Reads the BIOS settings of the BC-250 and shows them like the BIOS setup screen, hidden menus included.
Read-only: nothing on the board or in the BIOS changes."""

APP_NAME = "BC-250 BIOS Reader"
APP_ID = "bc250-bios-reader"
__version__ = "0.11.1"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-bios-reader/bc250-bios-reader.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="bios-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
