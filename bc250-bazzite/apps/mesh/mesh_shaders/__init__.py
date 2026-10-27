# SPDX-License-Identifier: GPL-3.0-or-later
"""Mesh shaders for games on the BC-250: builds RADV with DirectMesh on the board, installs it beside the system
Mesa, tests it and lets chosen games use it."""

APP_NAME = "BC-250 Mesh Shaders"
APP_ID = "bc250-mesh-shaders"
__version__ = "0.17.0"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"
SCRIPT = ROOT / "bc250-mesh-shaders.sh"

# Settings in ~/.config/bc250-mesh-shaders/bc250-mesh-shaders.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="mesh-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "SCRIPT", "__version__"]
