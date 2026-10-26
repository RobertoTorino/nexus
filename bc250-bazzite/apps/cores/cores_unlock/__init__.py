# SPDX-License-Identifier: GPL-3.0-or-later

"""PyQt6 front-end for bc250-cores-unlock.sh (persisting a validated BC-250 8C/16T core unlock)."""

from pathlib import Path

APP_NAME = "BC-250 Cores Unlock"
APP_ID = "bc250-cores-unlock"
ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / "bc250-cores-unlock.webp"
WINDOW_ICON_PATH = LOGO_PATH
REPO_URL = "https://github.com/RobertoTorino/nexus/tree/main/bc250-bazzite/apps/cores"


def _read_version() -> str:
    try:
        return (ROOT / "VERSION").read_text().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


__version__ = _read_version()


def window_title(part: str) -> str:
    """Title of a secondary window. On Linux/Windows Qt appends " — <display name>" itself."""
    import sys
    return f"{APP_NAME} — {part}" if sys.platform == "darwin" else part
