# SPDX-License-Identifier: GPL-3.0-or-later
"""BC250 Suite Releases: the file edits of a suite release (versions, CHANGELOG entries, pins, the portal bump) and
the board checks of a portal release. It works on the suite checkout it lives in, so it is not part of the portal
and has no releases of its own."""

APP_NAME = "BC250 Suite Releases"
APP_ID = "bc250-release"
__version__ = "0.1.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
SUITE = ROOT.parents[2]                     # the checkout it edits: the repository (Nexus), the suite in bc250-bazzite/
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-release/bc250-release.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "SUITE", "__version__"]
