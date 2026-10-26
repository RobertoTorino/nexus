# SPDX-License-Identifier: GPL-3.0-or-later
"""Watches the temperatures of the BC-250 and its fans: a thermal guard that runs as a system service warns, cools
and, at a critical temperature, shuts the board down cleanly. The board changes only when you turn the guard on."""

APP_NAME = "BC-250 Fan Control"
APP_ID = "bc250-fan-control"
__version__ = "0.12.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-fan-control/bc250-fan-control.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="fan-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
