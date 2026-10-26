# SPDX-License-Identifier: GPL-3.0-or-later
"""Bazzite DatStation: the PlayStation knowledge part of the DatStation Android app, on Bazzite. The quiz, the
PlayStation history, the system version history, the region codes explained, the user guides and the PlayStation
news, from a front page of tiles. A Python + Qt port of github.com/RobertoTorino/DatStation, built the way the
BC250 Bazzite Suite builds its apps (bc250_core, the same installer and launcher)."""

APP_NAME = "Bazzite DatStation"
APP_ID = "bazzite-datstation"
__version__ = "1.10.0"

from pathlib import Path  # noqa: E402  (constants first, as the suite's apps do)

from bc250_core import AppInfo  # noqa: E402

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"
DATA_DIR = PACKAGE_DIR / "data"                 # the questions and the system software versions, as JSON
SOUNDS_DIR = PACKAGE_DIR / "sounds"             # the quiz music
REPO_URL = "https://github.com/RobertoTorino/nexus"

# Settings in ~/.config/bazzite-datstation/bazzite-datstation.ini; scores in ~/.local/share/bazzite-datstation/.
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH,
               tag_prefix="datstation-v", settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "DATA_DIR", "INFO", "LOGO_PATH", "PACKAGE_DIR", "REPO_URL",
           "ROOT", "SOUNDS_DIR", "__version__"]
