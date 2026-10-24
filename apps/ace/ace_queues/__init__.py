# SPDX-License-Identifier: GPL-3.0-or-later
"""Opens the dedicated compute (ACE) queues of the BC-250 for games: builds a patched RADV on the board, installs
it beside the system Mesa, tests the queues and lets chosen games (or every app) use it."""

APP_NAME = "BC-250 ACE Queues"
APP_ID = "bc250-ace-queues"
__version__ = "0.11.1"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"
SCRIPT = ROOT / "bc250-ace-queues.sh"

# Settings in ~/.config/bc250-ace-queues/bc250-ace-queues.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="ace-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "SCRIPT", "__version__"]
