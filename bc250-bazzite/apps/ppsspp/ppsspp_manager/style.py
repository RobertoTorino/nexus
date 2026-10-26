# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's look: one blue, #0A55B0, the blue of the app's icon (owner, 17-10-2026), on core's widgets. The style
sheet goes on the main window, so everything in it takes the blue and the rest of the suite keeps core's purple."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget

BLUE = "#0A55B0"
BLUE_HOVER = "#2A6CC4"
BLUE_PRESSED = "#08448D"
BLUE_TINT = "#1A0A55B0"                 # #AARRGGBB: 10 % blue, for hover and every other table row
BLUE_LINE = "#590A55B0"                 # 35 % blue, for outlines
LINK_ON_DARK = "#5B93DA"                # #0A55B0 is too dark to read as a link on a dark window
DISABLED = "#80808080"                  # 50 % gray: a disabled button, readable as such on light and dark

STYLESHEET = f"""
QPushButton {{ border:1px solid {BLUE_LINE}; border-radius:6px; padding:5px 14px; background:palette(button); }}
QPushButton:hover {{ border-color:{BLUE}; background:{BLUE_TINT}; }}
QPushButton:pressed {{ background:{BLUE_LINE}; }}
QPushButton:disabled {{ color:{DISABLED}; border-color:{DISABLED}; background:palette(window); }}
QPushButton[primary="true"] {{ background:{BLUE}; border-color:{BLUE}; color:white; font-weight:700;
                               padding:5px 18px; }}
QPushButton[primary="true"]:hover {{ background:{BLUE_HOVER}; border-color:{BLUE_HOVER}; }}
QPushButton[primary="true"]:pressed {{ background:{BLUE_PRESSED}; border-color:{BLUE_PRESSED}; }}
QPushButton[primary="true"]:disabled {{ background:palette(window); border-color:{DISABLED};
                                        color:{DISABLED}; }}
QLabel[step="true"] {{ background:{BLUE}; color:white; font-weight:800; border-radius:12px; }}
QTableWidget {{ border:1px solid {BLUE_LINE}; border-radius:6px; gridline-color:{BLUE_TINT};
                alternate-background-color:{BLUE_TINT}; selection-background-color:{BLUE};
                selection-color:white; }}
QHeaderView::section {{ background:{BLUE}; color:white; font-weight:700; border:none;
                        border-right:1px solid {BLUE_HOVER}; padding:5px 8px; }}
QPlainTextEdit {{ border:1px solid {BLUE_LINE}; border-radius:6px; }}
"""


def apply(window: QWidget) -> None:
    """The style sheet, and the blue as the window's selection color."""
    window.setStyleSheet(STYLESHEET)
    palette = window.palette()
    palette.setColor(QPalette.ColorRole.Highlight, QColor(BLUE))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    window.setPalette(palette)


def link(widget: QWidget, url: str, text: str) -> str:
    """A link in rich text, in the blue (lighter on a dark window). Colored in the HTML: a QLabel under a style
    sheet draws links in the default blue, whatever its palette says."""
    dark = widget.palette().color(QPalette.ColorRole.Window).lightness() < 128
    return f"<a href='{url}' style='color:{LINK_ON_DARK if dark else BLUE};'>{text}</a>"


def primary_button(text: str, tooltip: str = "") -> QPushButton:
    """A main action, filled blue (in place of core's accent_button, outlined in the suite's purple)."""
    button = QPushButton(text)
    button.setToolTip(tooltip)
    button.setProperty("primary", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def step_badge(number: int) -> QLabel:
    """The number of a step in a blue circle."""
    badge = QLabel(str(number))
    badge.setProperty("step", True)
    badge.setFixedSize(24, 24)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return badge
