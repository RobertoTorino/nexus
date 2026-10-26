# SPDX-License-Identifier: GPL-3.0-or-later
"""Sony's DualSense and DualSense Edge controllers on Bazzite: their battery and firmware, the firmware update that
Sony offers only for Windows, and the Edge's profiles. The kernel's hid-playstation drives the controller; the app
talks to it through its hidraw node, with the standard library only."""

APP_NAME = "USB HD Control"
APP_ID = "bc250-usb-hdcontrol"
__version__ = "0.10.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-usb-hdcontrol/bc250-usb-hdcontrol.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="hdcontrol-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
