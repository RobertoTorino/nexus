# SPDX-License-Identifier: MIT
"""PyQt6 front-end for bc250-acpi-override.sh (the persistent ACPI fix for the AMD BC-250)."""

import sys
from pathlib import Path

APP_NAME = "BC-250 Persistent ACPI"
APP_ID = "bc250-persistent-acpi"
ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"
REPO_URL = "https://github.com/RobertoTorino/nexus"


def _read_version() -> str:
    try:
        return (ROOT / "VERSION").read_text().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


__version__ = _read_version()


def window_title(part: str) -> str:
    """Title of a secondary window. On Linux/Windows Qt appends " — <display name>" itself."""
    return f"{APP_NAME} — {part}" if sys.platform == "darwin" else part
