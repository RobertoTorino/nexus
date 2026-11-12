# SPDX-License-Identifier: GPL-3.0-or-later
"""Pair your Bluetooth keyboard, mouse and controllers at boot, with no USB keyboard or mouse needed."""

APP_NAME = "BC-250 Bluetooth Pairing"
APP_ID = "bc250-bluetooth-pairing"
__version__ = "0.1.1"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-bluetooth-pairing/bc250-bluetooth-pairing.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="btpair-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
