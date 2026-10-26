# SPDX-License-Identifier: GPL-3.0-or-later
"""Console LinkB for the BC-250: signs in with a Microsoft account, lists the Xbox consoles on it and the games of
Xbox Cloud Gaming, wakes a console and streams it or a cloud game to the board. The protocol code is ported from
Greenlight and xal-node (MIT; see the README's License section)."""

APP_NAME = "Console LinkB"
APP_ID = "bc250-console-linkb"
__version__ = "0.10.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-console-linkb/bc250-console-linkb.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="clb-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
