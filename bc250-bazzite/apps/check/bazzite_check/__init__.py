# SPDX-License-Identifier: GPL-3.0-or-later
"""PyQt6 front-end for test-bazzite.sh (AMD BC-250 on Bazzite)."""

APP_NAME = "BC-250 Bazzite Test"
APP_ID = "bc250-bazzite-test"
__version__ = "0.16.0"

from pathlib import Path

from bc250_core import SUITE_REPO_URL, AppInfo
from bc250_core.text import plain_tooltip
from bc250_core.text import window_title as _window_title

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"
ICON_PATH = ROOT / "images" / f"{APP_ID}-128.png"      # for notify-send: a desktop may not read WebP
WINDOW_ICON_PATH = LOGO_PATH
DISPLAY_NAME = f"{APP_NAME} {__version__}"
REPO_URL = SUITE_REPO_URL

# Settings stay where they always were: ~/.config/bc250-bazzite-test/bc250-bazzite-test.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="check-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "DISPLAY_NAME", "ICON_PATH", "INFO", "LOGO_PATH", "REPO_URL", "ROOT",
           "WINDOW_ICON_PATH", "__version__", "plain_tooltip", "window_title"]


def window_title(part: str) -> str:
    """Title of a secondary window. On Linux/Windows Qt appends " — <display name>" itself."""
    return _window_title(part, APP_NAME)
