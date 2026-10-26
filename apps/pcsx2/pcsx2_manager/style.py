# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's look: one blue, #0A55B0, the blue of the app's icon (owner, 17-10-2026), on core's widgets. The style
sheet goes on the main window, so everything in it takes the blue and the rest of the suite keeps core's purple.
The tabs are the size of the pills above them, the chosen one filled blue, and the choice boxes (the table's
screen settings, the Settings tab) are flat, outlined like the buttons, on no background of their own (owner,
24-10-2026)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget

from bc250_core.theme import THEME
from bc250_core.widgets import Pill

BLUE = "#0A55B0"
ARROW = (Path(__file__).resolve().parent / "arrow-down.svg").as_posix()     # a choice box's arrow, a thin chevron
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
QTableWidget {{ border:1px solid {BLUE_LINE}; border-radius:6px; gridline-color:{BLUE_TINT};
                alternate-background-color:{BLUE_TINT}; selection-background-color:{BLUE};
                selection-color:white; }}
QHeaderView::section {{ background:{BLUE}; color:white; font-weight:700; border:none;
                        border-right:1px solid {BLUE_HOVER}; padding:5px 8px; }}
QPlainTextEdit {{ border:1px solid {BLUE_LINE}; border-radius:6px; }}
QComboBox {{ border:1px solid {BLUE_LINE}; border-radius:6px; padding:3px 8px; background:transparent; }}
QComboBox:hover {{ border-color:{BLUE}; background:{BLUE_TINT}; }}
QComboBox:disabled {{ color:{DISABLED}; border-color:{DISABLED}; background:palette(window); }}
QComboBox::drop-down {{ border:none; width:24px; subcontrol-origin:padding; subcontrol-position:center right; }}
QComboBox::down-arrow {{ image:url({ARROW}); width:10px; height:10px; }}
QComboBox QAbstractItemView {{ border:1px solid {BLUE_LINE}; selection-background-color:{BLUE};
                               selection-color:white; }}
QTabWidget::pane {{ border:none; }}
QTabBar::tab {{ padding:17px 26px; min-width:120px; font-size:17px; font-weight:700; border:1px solid {BLUE_LINE};
                border-bottom:none; border-top-left-radius:8px; border-top-right-radius:8px; margin-right:6px;
                background:palette(button); }}
QTabBar::tab:selected {{ background:{BLUE}; color:white; border-color:{BLUE}; }}
QTabBar::tab:hover:!selected {{ background:{BLUE_TINT}; border-color:{BLUE}; }}
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


def tinted(colour: str, amount: float = 0.1) -> str:
    """*color* with *amount* of the blue mixed in, opaque: a tint that keeps the surface it is on."""
    base, blue = QColor(colour), QColor(BLUE)
    mixed = QColor.fromRgbF(*(b * (1 - amount) + a * amount for a, b in zip(blue.getRgbF()[:3], base.getRgbF()[:3])))
    return mixed.name()


# The pill's surface under the mouse: the theme's sheen with the blue tint mixed into both of its stops, so it
# stays a sheen (a translucent tint over the pill showed the window behind it instead; owner, 24-10-2026).
HOVER_SHEEN = (f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {tinted(THEME.button)}, "
               f"stop:1 {tinted(THEME.button_low)})")


def action_pill(value: str, caption: str, tooltip: str) -> Pill:
    """A pill that does something (Refresh, Install PCSX2…), as the boxes beside it: the blue left edge only,
    also under the mouse and the keyboard focus (owner, 24-10-2026: no border all round); the blue tint under the
    mouse says it can be clicked, as a button's hover does. The keyboard focus alone changes nothing: the first
    pill has it when the window opens, and showed another background than the boxes beside it (owner,
    24-10-2026)."""
    pill = Pill(value, caption, tooltip, BLUE)
    pill.setStyleSheet(pill.styleSheet()
                       + f"#pill:focus {{ border-color:{THEME.edge}; border-left-color:{BLUE}; }}"
                       f"#pill:hover {{ border-color:{THEME.edge}; border-left-color:{BLUE}; "
                       f"background:{HOVER_SHEEN}; }}")
    return pill
