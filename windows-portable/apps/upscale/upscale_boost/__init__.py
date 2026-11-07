# SPDX-License-Identifier: GPL-3.0-or-later
"""Upscale Boost: HelixSR, the DLSS-like upscaler for AMD graphics, in your games: its build, deployed per game and set."""

APP_NAME = "Upscale Boost"
APP_ID = "windows-portable-upscale"
EXE_NAME = "Upscale-Boost"   # the program's file name in a release
SUITE = "windows-portable-suite"
__version__ = "0.3.1"

from pathlib import Path

from bc250_core import AppInfo
from bc250_core.platform import suite_data

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"
HELIXSR_URL = "https://github.com/lonewolf0622/HelixSR"
HELIXSR_RELEASES_URL = f"{HELIXSR_URL}/releases"
OPTISCALER_URL = "https://github.com/OptiScaler/OptiScaler"

# Settings in %APPDATA%\windows-portable-suite\windows-portable-upscale.ini, the log in %LOCALAPPDATA%\windows-portable-suite\windows-portable-upscale\ (bc250_core.applog)
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="wp-upscale-v",
               settings_org=SUITE, settings_ini=True)


def app_home() -> Path:
    """%LOCALAPPDATA%\\windows-portable-suite\\windows-portable-upscale: the program (app\\), the log, and HelixSR:
    the payload (payload\\), the downloaded releases (work\\), the builder's Python and shader compiler (HelixSR\\)
    and the list of games HelixSR was put in (deployments.json). Updating or uninstalling the app keeps them."""
    return suite_data(SUITE) / APP_ID


__all__ = ["APP_ID", "APP_NAME", "EXE_NAME", "HELIXSR_RELEASES_URL", "HELIXSR_URL", "INFO", "LOGO_PATH",
           "OPTISCALER_URL", "ROOT", "SUITE", "__version__", "app_home"]
