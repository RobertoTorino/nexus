# SPDX-License-Identifier: GPL-3.0-or-later
"""The health, power cycles and power-on hours of drives exposed by the Bazzite host."""

APP_NAME = "SSD Check"
APP_ID = "ps5-ssd-check"
__version__ = "0.1.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/ps5-ssd-check/ps5-ssd-check.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="ps5-ssd-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
