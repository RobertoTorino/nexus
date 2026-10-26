# SPDX-License-Identifier: GPL-3.0-or-later

"""PyQt6 front-end for bc250-cu-unlock.sh (persisting a validated BC-250 CU unlock)."""

APP_NAME = "BC-250 CU Unlock"
APP_ID = "bc250-cu-unlock"
__version__ = "0.3.0"

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / "bc250-cu-bisect-unlock.webp"
WINDOW_ICON_PATH = LOGO_PATH
REPO_URL = "https://github.com/RobertoTorino/nexus/tree/main/apps/compute"


def window_title(part: str) -> str:
    """Title of a secondary window. On Linux/Windows Qt appends " — <display name>" itself."""
    import sys
    return f"{APP_NAME} — {part}" if sys.platform == "darwin" else part
