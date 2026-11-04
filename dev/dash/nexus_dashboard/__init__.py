# SPDX-License-Identifier: GPL-3.0-or-later
"""Nexus Dashboard: the one door to the tools for working on the suites (owner, 02-11-2026: they were spread over
the suites and the root). It starts the Nexus apps of the checkout (Nexus Release Tool, Nexus Installer Tests,
Nexus Demo Recorder, Nexus Sound Lab) and opens the tours and the icons of the suite chosen in its header. A Nexus app (dev/), run
from the checkout and never released."""

from pathlib import Path

from bc250_core import AppInfo

APP_NAME = "Nexus Dashboard"
APP_ID = "nexus-dashboard"
__version__ = "0.2.0"

ROOT = Path(__file__).resolve().parent.parent
CHECKOUT = ROOT.parents[1]                  # the repository (Nexus), dev/dash/ in it
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/nexus-dashboard/nexus-dashboard.ini: the suite chosen last
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "CHECKOUT", "INFO", "LOGO_PATH", "ROOT", "__version__"]
