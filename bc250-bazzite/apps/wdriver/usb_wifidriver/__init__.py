# SPDX-License-Identifier: GPL-3.0-or-later
"""The driver for AIC8800D80 USB Wi-Fi sticks (the UGREEN AX900 and others) on the BC-250: built for the running
kernel from pinned sources, loaded at boot by a system service that rebuilds it after a kernel update. The board
changes only when you install the driver."""

APP_NAME = "BC-250 USB Wi-Fi"
APP_ID = "bc250-usb-wifi"
__version__ = "0.15.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-usb-wifi/bc250-usb-wifi.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wdriver-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
