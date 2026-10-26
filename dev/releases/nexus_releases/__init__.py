# SPDX-License-Identifier: GPL-3.0-or-later
"""Nexus Releases: the file edits of a release (versions, CHANGELOG entries, pins, the portal bump) of any suite in
the repository, and the board checks of a portal release. It works on the checkout it lives in (Nexus, with a
suite chooser when the checkout holds several), so it is not part of a portal's releases and has none of its own."""

APP_NAME = "Nexus Releases"
APP_ID = "nexus-releases"
__version__ = "0.1.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
CHECKOUT = ROOT.parents[1]                  # the checkout it edits: the repository (Nexus), dev/releases/ in it
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/nexus-releases/nexus-releases.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "CHECKOUT", "INFO", "LOGO_PATH", "ROOT", "__version__"]
