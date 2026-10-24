# SPDX-License-Identifier: GPL-3.0-or-later
"""The PS5 HD Camera (CFI-ZEY1) on Bazzite: it starts as a boot loader without firmware, which the
app uploads; then it is an ordinary USB video camera (uvcvideo)."""

APP_NAME = "USB HD Cam"
APP_ID = "bc250-usb-hdcam"
__version__ = "0.6.1"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-usb-hdcam/bc250-usb-hdcam.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="hdcam-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
