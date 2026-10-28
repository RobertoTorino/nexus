# SPDX-License-Identifier: AGPL-3.0-or-later
"""Console Link for the BC-250: find the consoles on the network, wake them, register the board with one, and start
and close a Remote Play session and its stream with it. The protocol code is ported from the reference implementation
(AGPL-3.0; see the README's License section)."""

from . import steam_env

steam_env.settle()                      # before Qt loads: started by Steam, the app leaves Steam's libraries

APP_NAME = "Console Link"
APP_ID = "bc250-console-link"
__version__ = "1.17.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-console-link/bc250-console-link.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="consoles-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
