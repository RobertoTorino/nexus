# SPDX-License-Identifier: GPL-3.0-or-later
"""PyQt6 front-end for cyan-skillfish-governor-smu (AMD BC-250 on Bazzite)."""

APP_NAME = "BC-250 GPU Governor Manager"
APP_ID = "bc250-governor-manager"
__version__ = "0.4.0"

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"
WINDOW_ICON_PATH = LOGO_PATH
FONT_DIR = Path(__file__).resolve().parent / "fonts"
DISPLAY_NAME = f"{APP_NAME} {__version__}"
REPO_URL = "https://github.com/RobertoTorino/nexus/tree/main/bc250-bazzite/apps/gpu"
GOVERNOR_URL = "https://github.com/filippor/cyan-skillfish-governor/tree/smu"


def fmt(text: str, *values: object) -> str:
    """Fill the %1, %2, … placeholders of a string, as Qt's QString.arg() does (PyQt6 has no QString).

    Substitution is a single pass, so a value that itself contains "%2" is left alone."""
    import re
    return re.sub(r"%(\d+)",
                  lambda m: str(values[int(m.group(1)) - 1]) if 0 < int(m.group(1)) <= len(values) else m.group(0),
                  text)


def plain_tooltip(text: str) -> str:
    """Tooltip for text that comes from outside the app (paths, config and log contents).

    Qt renders a tooltip as HTML when it looks like HTML, so such text is escaped and shown in a
    paragraph that keeps its line breaks: it can never inject markup, links or images."""
    import html
    return f"<p style='white-space:pre-wrap; margin:0;'>{html.escape(text)}</p>"


def window_title(part: str) -> str:
    """Title of a secondary window. On Linux/Windows Qt appends " — <display name>" itself."""
    import sys
    return f"{APP_NAME} — {part}" if sys.platform == "darwin" else part
