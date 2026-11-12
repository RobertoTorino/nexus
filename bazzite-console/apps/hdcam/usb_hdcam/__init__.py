# SPDX-License-Identifier: GPL-3.0-or-later
"""A firmware loader and viewer for supported Sony USB cameras on Bazzite.

The Console Suite port has not been validated on PS5 hardware.
"""

APP_NAME = "USB HD Cam"
APP_ID = "ps5-usb-hdcam"
__version__ = "0.2.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/ps5-usb-hdcam/ps5-usb-hdcam.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="ps5-hdcam-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
