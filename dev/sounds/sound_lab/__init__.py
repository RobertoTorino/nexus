# SPDX-License-Identifier: GPL-3.0-or-later
"""Nexus Sound Lab: a window that makes and tries short sound effects for the suites' windows (the tick a menu
makes when the controller moves the focus) from sliders, plays each change at once, lets you try it while moving
between buttons, and saves the sound as a WAV. A Nexus app (dev/), run from the checkout and never released
(owner, 03-11-2026: a sound generator with sliders, grown from a click-sound demo)."""

from pathlib import Path

from bc250_core import AppInfo

APP_NAME = "Nexus Sound Lab"
APP_ID = "nexus-sound-lab"
__version__ = "0.1.0"

ROOT = Path(__file__).resolve().parent.parent
CHECKOUT = ROOT.parents[1]                  # the repository (Nexus), dev/sounds/ in it
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/nexus-sound-lab/nexus-sound-lab.ini: the last sound, preset and save folder
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "CHECKOUT", "INFO", "LOGO_PATH", "ROOT", "__version__"]
