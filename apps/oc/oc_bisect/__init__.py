# SPDX-License-Identifier: GPL-3.0-or-later

"""PyQt6 front-end for bc250-gpu-oc-bisect.sh: a menu-driven launcher for the initial setup/start
of a GPU OC/UV sweep. It only assembles the command line and starts it in a terminal; the actual
sweeping still happens in bc250-gpu-oc-bisect.sh itself, exactly as if typed by hand."""

APP_NAME = "BC-250 GPU OC Bisect"
APP_ID = "bc250-gpu-oc-bisect-gui"
__version__ = "0.2.2"

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / "bc250-gpu-oc-bisect.webp"
WINDOW_ICON_PATH = LOGO_PATH
REPO_URL = "https://github.com/RobertoTorino/nexus/tree/main/apps/oc"


def window_title(part: str) -> str:
    """Title of a secondary window. On Linux/Windows Qt appends " — <display name>" itself."""
    import sys
    return f"{APP_NAME} — {part}" if sys.platform == "darwin" else part
