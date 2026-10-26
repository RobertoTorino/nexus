# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's look: the suite's theme with DatStation's PlayStation blue (its BlueTheme: #003791 and #0072CE) as
the accent, in one style sheet, app-wide, applied over core's start-up. Properties on widgets pick the variants: a
tile, a card, a primary button, a muted or a title label."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QWidget

from bc250_core import theme

PS_BLUE = "#003791"
PS_LIGHT_BLUE = "#0072CE"
BLUE_HOVER = "#1A85E0"
BLUE_PRESSED = "#00589F"
# The theme's surfaces and text.
CARD = theme.THEME.alt
CARD_LINE = theme.THEME.edge
CONTROL = theme.THEME.base
TEXT = theme.THEME.text
MUTED = theme.muted()
LINK = "#4DA3EF" if theme.THEME.dark else PS_LIGHT_BLUE      # the light blue reads on a dark window only
SHEEN = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {theme.THEME.button}, stop:1 {theme.THEME.button_low})"
GREEN = "#2E7D32"
RED = "#C62828"
GOLD = "#FFD700"
SILVER = "#C0C0C0"
BRONZE = "#CD7F32"
DISABLED = MUTED

STYLESHEET = f"""
QWidget {{ color: {TEXT}; }}
QLabel {{ background: transparent; }}
QLabel[muted="true"] {{ color: {MUTED}; }}
QLabel[title="true"] {{ font-size: 22px; font-weight: 800; }}
QLabel[big="true"] {{ font-size: 34px; font-weight: 900; }}
QLabel[huge="true"] {{ font-size: 64px; font-weight: 900; }}
QFrame[card="true"] {{
    background: {CARD}; border: 1px solid {CARD_LINE}; border-radius: 12px;
}}
QPushButton, QToolButton {{
    background: {SHEEN}; color: {TEXT}; font-weight: 700;
    border: 1px solid {CARD_LINE}; border-radius: 10px; padding: 8px 16px;
}}
QPushButton:hover, QToolButton:hover {{ border-color: {PS_LIGHT_BLUE}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {CONTROL}; }}
QPushButton:focus, QToolButton:focus {{ border: 2px solid {PS_LIGHT_BLUE}; }}
QPushButton:disabled, QToolButton:disabled {{ background: {CONTROL}; color: {DISABLED}; border-color: {CARD_LINE}; }}
QPushButton[primary="true"] {{ background: {PS_LIGHT_BLUE}; color: white; border-color: {PS_LIGHT_BLUE}; }}
QPushButton[primary="true"]:hover {{ background: {BLUE_HOVER}; border-color: {BLUE_HOVER}; }}
QPushButton[primary="true"]:pressed {{ background: {BLUE_PRESSED}; }}
QPushButton[quiet="true"], QToolButton[quiet="true"] {{ background: transparent; border: 1px solid {CARD_LINE}; }}
QPushButton[quiet="true"]:hover, QToolButton[quiet="true"]:hover {{ border-color: {PS_LIGHT_BLUE}; }}
QPushButton[link="true"] {{
    background: transparent; border: none; color: {LINK}; text-align: left; padding: 2px 0; font-weight: 700;
}}
QPushButton[link="true"]:hover {{ text-decoration: underline; }}
QPushButton[tile="true"] {{
    background: {CARD}; border: 1px solid {CARD_LINE}; border-radius: 14px; padding: 0; text-align: left;
}}
QPushButton[tile="true"]:hover {{ background: {SHEEN}; border-color: {PS_LIGHT_BLUE}; }}
QPushButton[tile="true"]:focus {{ border: 2px solid {PS_LIGHT_BLUE}; }}
QPushButton[tile="true"]:pressed {{ background: {CONTROL}; border-color: {PS_LIGHT_BLUE}; }}
QPushButton[soon="true"]:disabled {{
    background: transparent; border: 1px dashed {CARD_LINE}; color: {DISABLED};
    font-size: 15px; font-weight: 700; text-align: center;
}}
QPushButton[option="true"] {{ font-size: 15px; padding: 12px 16px; text-align: left; }}
QPushButton[option="true"][result="right"] {{ background: {GREEN}; border-color: {GREEN}; }}
QPushButton[option="true"][result="wrong"] {{ background: {RED}; border-color: {RED}; }}
QPushButton[option="true"]:disabled[result="right"] {{ background: {GREEN}; color: white; }}
QPushButton[option="true"]:disabled[result="wrong"] {{ background: {RED}; color: white; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QProgressBar {{
    background: {CONTROL}; border: none; border-radius: 4px; height: 8px; text-align: center;
}}
QProgressBar::chunk {{ background: {PS_LIGHT_BLUE}; border-radius: 4px; }}
QProgressBar[low="true"]::chunk {{ background: {RED}; }}
QListWidget, QTextBrowser, QTableWidget, QPlainTextEdit {{
    background: {CONTROL}; border: 1px solid {CARD_LINE}; border-radius: 10px; padding: 6px;
    selection-background-color: {PS_LIGHT_BLUE}; selection-color: white;
}}
QListWidget::item {{ padding: 2px 6px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {PS_LIGHT_BLUE}; color: white; }}
QListWidget::item:hover {{ background: {CARD}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {CARD_LINE}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {CARD_LINE}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QMenu {{ background: {CARD}; border: 1px solid {CARD_LINE}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {PS_LIGHT_BLUE}; color: white; }}
QMenu::separator {{ height: 1px; background: {CARD_LINE}; margin: 4px 8px; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {LINK}; }}
QStatusBar {{ color: {MUTED}; }}
"""

# The text colors of the HTML pages (QTextBrowser does not take them from the style sheet).
HTML_CSS = f"""
body {{ color: {TEXT}; font-size: 14px; }}
h2 {{ color: {TEXT}; font-size: 20px; margin-bottom: 4px; }}
h3 {{ color: {LINK}; font-size: 16px; margin-top: 18px; margin-bottom: 4px; }}
p {{ margin-top: 2px; margin-bottom: 6px; }}
a {{ color: {LINK}; text-decoration: none; font-weight: bold; }}
.muted {{ color: {MUTED}; }}
.accent {{ color: {LINK}; font-weight: bold; }}
.card {{ background-color: {CARD}; }}
th {{ background-color: {PS_LIGHT_BLUE}; color: white; padding: 4px 10px; text-align: left; }}
td {{ padding: 4px 10px; border-bottom: 1px solid {CARD_LINE}; }}
"""


def apply_theme(app: QApplication) -> None:
    """The suite's theme with the blue as its accent and the style sheet after it, for every window of the app."""
    theme.apply_theme(app, STYLESHEET)
    palette = app.palette()
    palette.setColor(palette.ColorRole.Highlight, QColor(PS_LIGHT_BLUE))
    palette.setColor(palette.ColorRole.HighlightedText, QColor("white"))
    palette.setColor(palette.ColorRole.Link, QColor(LINK))
    app.setPalette(palette)


def html_page(body: str) -> str:
    """A page for a QTextBrowser, with the app's text colors."""
    return f"<html><head><style>{HTML_CSS}</style></head><body>{body}</body></html>"


def flag(widget: QWidget, name: str, value: object = True) -> None:
    """Set a style property and have the widget redrawn with it (a property set after the first show is only
    picked up after unpolish/polish)."""
    widget.setProperty(name, value)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def primary_button(text: str, tooltip: str = "") -> QPushButton:
    button = QPushButton(text)
    button.setToolTip(tooltip)
    button.setProperty("primary", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def quiet_button(text: str, tooltip: str = "") -> QPushButton:
    button = QPushButton(text)
    button.setToolTip(tooltip)
    button.setProperty("quiet", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def link_button(text: str, tooltip: str = "") -> QPushButton:
    button = QPushButton(text)
    button.setToolTip(tooltip)
    button.setProperty("link", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def card() -> QFrame:
    frame = QFrame()
    frame.setProperty("card", True)
    return frame


def label(text: str = "", *, muted: bool = False, title: bool = False, big: bool = False, huge: bool = False,
          wrap: bool = False, align: Qt.AlignmentFlag | None = None) -> QLabel:
    widget = QLabel(text)
    if muted:
        widget.setProperty("muted", True)
    if title:
        widget.setProperty("title", True)
    if big:
        widget.setProperty("big", True)
    if huge:
        widget.setProperty("huge", True)
    widget.setWordWrap(wrap)
    if align is not None:
        widget.setAlignment(align)
    return widget
