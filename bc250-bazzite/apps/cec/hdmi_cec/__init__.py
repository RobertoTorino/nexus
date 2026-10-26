# SPDX-License-Identifier: GPL-3.0-or-later
"""HDMI-CEC for the BC-250: the board's CEC adapter, the TV on the other end, buttons to turn the TV on or off and
switch it to the board, and the automatic behavior of Valve's CEC daemon (cecd) that Bazzite ships."""

APP_NAME = "HDMI CEC Manager"
APP_ID = "bc250-hdmi-cec"
__version__ = "0.15.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-hdmi-cec/bc250-hdmi-cec.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="cec-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
