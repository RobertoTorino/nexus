# SPDX-License-Identifier: GPL-3.0-or-later
"""Nexus Demo Recorder: records a demo of a portal installation with OBS, from a portal release in Downloads or the
suite in the checkout it lives in. A Nexus app (dev/), run from the checkout and never released; it was the OBS part
of the BC250 Bazzite Suite's Media Tool until 02-11-2026 (owner: the tools for working on the suites are Nexus's).
Linux only: OBS and the desktop portal's global shortcut."""

from pathlib import Path

from bc250_core import AppInfo

APP_NAME = "Nexus Demo Recorder"
APP_ID = "nexus-demo-recorder"
__version__ = "0.2.0"

ROOT = Path(__file__).resolve().parent.parent
CHECKOUT = ROOT.parents[1]                  # the repository (Nexus), dev/demo/ in it
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/nexus-demo-recorder/nexus-demo-recorder.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "CHECKOUT", "INFO", "LOGO_PATH", "ROOT", "__version__"]
