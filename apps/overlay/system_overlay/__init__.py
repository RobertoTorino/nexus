# SPDX-License-Identifier: GPL-3.0-or-later
"""A small always-on-top window with the BC-250's live system values: CPU, GPU, refresh rate, fan and
temperatures."""

APP_NAME = "System Overlay"
APP_ID = "bc250-system-overlay"
__version__ = "0.13.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-system-overlay/bc250-system-overlay.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="overlay-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
