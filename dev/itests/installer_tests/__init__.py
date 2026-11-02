# SPDX-License-Identifier: GPL-3.0-or-later
"""Nexus Installer Tests: a window that runs a suite's installer tests (<suite>/tools/installer-tests/*.sh on
Linux, *.ps1 on Windows) one at a time, with their live output. A Nexus app (dev/), run from the checkout and never
released; it was the BC250 Bazzite Suite's BC-250 Installer Tests (tools/installer-tests/gui) until 02-11-2026
(owner: the tools for working on the suites are Nexus's, in one place)."""

from pathlib import Path

from bc250_core import AppInfo

APP_NAME = "Nexus Installer Tests"
APP_ID = "nexus-installer-tests"
__version__ = "0.1.0"

ROOT = Path(__file__).resolve().parent.parent
CHECKOUT = ROOT.parents[1]                  # the repository (Nexus), dev/itests/ in it
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/nexus-installer-tests/nexus-installer-tests.ini: the suite chosen last
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "CHECKOUT", "INFO", "LOGO_PATH", "ROOT", "__version__"]
