# SPDX-License-Identifier: GPL-3.0-or-later
"""The BC-250's live system values on a Turzx USB IPS screen (the Turing Smart Screen 3.5" and its family): CPU, GPU,
memory, fan, temperatures, network and disk."""

APP_NAME = "USB IPS3.5"
APP_ID = "bc250-usb-ips35"
__version__ = "0.6.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-usb-ips35/bc250-usb-ips35.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="ips35-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
