# SPDX-License-Identifier: GPL-3.0-or-later
"""PS Vita games on the BC-250 with Vita3K: installs a pinned Vita3K build, installs the PS Vita firmware and the
games through it, finds the games Vita3K has installed and adds them to Steam for Game Mode."""

APP_NAME = "Vita3K Manager"
APP_ID = "bc250-vita3k-manager"
__version__ = "0.16.1"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-vita3k-manager/bc250-vita3k-manager.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="vita3k-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
