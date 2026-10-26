# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's look: the copper and cyan of its icon (owner, 16-10-2026) in place of the suite's purple. The header's
boxes are a dark copper and a dark teal that keep white text readable; outlines take the icon's cyan. widgets.py keeps
the suite's palette: it is the copy core's widgets replace (step 5), and core/tests/test_parity.py holds it to them."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QPushButton

COPPER = "#8A5A2E"                      # boxes: white text on it reads at 5.9:1
TEAL = "#0E6F75"                        # boxes: white text on it reads at 5.9:1
CYAN = "#26A9B0"                        # the icon's cyan: outlines (5.5:1 on a dark window)
LINK_ON_DARK = "#3FC8CF"                # the bright cyan as link text on a dark window; TEAL on a light one


def accent_button(text: str, tooltip: str = "") -> QPushButton:
    """The page's main action, outlined in the cyan (widgets.accent_button in the app's color)."""
    button = QPushButton(text)
    button.setToolTip(tooltip)
    button.setMinimumHeight(36)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(f"QPushButton {{ border:2px solid {CYAN}; border-radius:6px; padding:4px 16px; "
                         "font-weight:700; }"
                         "QPushButton:disabled { border-color:palette(mid); color:palette(mid); }")
    return button


def set_link_colour(app: QApplication) -> None:
    """Links in the cyan. On the application's palette: rich text takes its link color from there when the HTML is
    loaded, not from the widget's palette."""
    palette = app.palette()
    dark = palette.color(QPalette.ColorRole.Window).lightness() < 128
    palette.setColor(QPalette.ColorRole.Link, QColor(LINK_ON_DARK if dark else TEAL))
    app.setPalette(palette)
