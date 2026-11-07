# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only system details for PlayStation 5 hardware running Bazzite."""

APP_NAME = "Bazzite Test"
APP_ID = "bazzite-test"
__version__ = "0.1.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bazzite-test/bazzite-test.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="ps5-bazzite-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
