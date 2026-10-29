# SPDX-License-Identifier: GPL-3.0-or-later
"""The Windows Portable Suite's portal: it installs, updates, opens and removes the apps its manifest (apps.toml)
pins, from their GitHub releases, on the portable window (direction D: tiles, a detail pane under them, pills that
show their controller button). Windows Portable Test is always installed and listed first. The manifest's parser
(manifest.py) is also what tools/check_manifest.py checks apps.toml with."""

APP_NAME = "Windows Portable Suite"
APP_ID = "windows-portable-suite"
EXE_NAME = "Windows-Portable-Suite"     # the program's file name in a release (owner, 28-10-2026)
SUITE = "windows-portable-suite"
__version__ = "1.6.0"

from pathlib import Path

from bc250_core import AppInfo
from bc250_core.platform import suite_data

ROOT = Path(__file__).resolve().parent.parent       # portal/ in the checkout; program\_internal installed
MANIFEST = ROOT / "apps.toml"
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"
APP_ICONS = ROOT / "images" / "apps"                # <key>.webp: the icon on each app's tile
WALLPAPER = ROOT / "images" / "wallpaper.webp"      # behind the page, darkened (owner, 28-10-2026: to try out)
INTRO_SOUND = ROOT / "sounds" / "intro.wav"         # the BC250 portal's sounds/bigpicture.wav (owner, 28-10-2026)
# Settings in %APPDATA%\windows-portable-suite\portal.ini; the state (which release of each app the portal
# installed, the extracted releases it installed from, its log) in %LOCALAPPDATA%\windows-portable-suite\portal\,
# where install.ps1 puts the program too (app\).
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-portal-v",
               settings_org=SUITE, settings_app="portal", settings_ini=True)


def state_dir() -> Path:
    """The portal's own folder in the suite's: installed.json, releases\\ (the extracted releases, kept so the
    matching uninstaller is at hand), the log, and app\\ with the program."""
    return suite_data(SUITE) / "portal"


__all__ = ["APP_ICONS", "APP_ID", "APP_NAME", "EXE_NAME", "INFO", "INTRO_SOUND", "LOGO_PATH", "MANIFEST", "ROOT", "SUITE",
           "WALLPAPER", "__version__", "state_dir"]
