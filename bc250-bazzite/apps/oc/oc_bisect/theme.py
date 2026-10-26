# SPDX-License-Identifier: GPL-3.0-or-later
"""The suite's look: the theme, state colors, the bundled Inter font and shared style sheets.

These values were hard-coded in every app; they live here now and nowhere else.

The theme is one choice for every app of the suite (gunmetal, silver or warm; gunmetal when none is chosen), kept
in ~/.config/bc250-bazzite-suite/theme and read once when this module is imported, so ACCENT and the rest are the
chosen theme's from the start. A change shows the next time an app starts. apply_theme() puts the theme's palette
and style sheet on the application; create_app() does that for every app on core.

Self-contained (PyQt6 and the standard library), so an app not on core yet carries a copy;
tools/tests/test_instance_copies.py keeps the copies equal."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PyQt6.QtGui import QColor, QFontDatabase, QPalette
from PyQt6.QtWidgets import QApplication

FONT_DIR = Path(__file__).resolve().parent / "fonts"


@dataclass(frozen=True)
class Theme:
    label: str
    dark: bool
    window: str         # window and dialog background
    base: str           # text fields, lists, tables
    alt: str            # every other row
    text: str
    button: str         # button face, the top of its sheen
    button_low: str     # the bottom of the sheen
    edge: str           # borders
    accent: str         # selection, focus, hover outline, the page's main action
    accent_text: str    # text on the accent


THEMES: dict[str, Theme] = {
    "gunmetal": Theme("Gunmetal", True, "#2b2f34", "#22262a", "#292d32", "#d9dde2", "#4a5058", "#3b4048",
                      "#14171a", "#7e97ad", "#ffffff"),
    "silver": Theme("Silver", False, "#d5d8dc", "#eceef0", "#e2e5e8", "#1e2226", "#eef0f2", "#c4c8cd",
                    "#8d9298", "#5f7f9c", "#ffffff"),
    "warm": Theme("Warm", True, "#35332f", "#292826", "#302e2b", "#e3dfd8", "#57534d", "#45423d",
                  "#181716", "#b59a6e", "#1b1a18"),
}
DEFAULT_THEME = "gunmetal"


def theme_file() -> Path:
    """Where the chosen theme is kept, for every app of the suite."""
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "bc250-bazzite-suite" / "theme"


def theme_name(path: Path | None = None) -> str:
    """The chosen theme's name; the default when none is chosen or the file names no theme."""
    try:
        name = (path or theme_file()).read_text(encoding="utf-8").strip().lower()
    except OSError:
        return DEFAULT_THEME
    return name if name in THEMES else DEFAULT_THEME


def save_theme_name(name: str, path: Path | None = None) -> None:
    """Choose the theme for every app; each one takes it the next time it starts."""
    if name not in THEMES:
        raise ValueError(f"no theme {name!r}: {', '.join(THEMES)}")
    path = path or theme_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(name + "\n", encoding="utf-8")


THEME = THEMES[theme_name()]

# Result colors and the logo's purple. A state shows as a colored edge or dot on the theme's surfaces.
GREEN, ORANGE, RED, BLUE, GREY = "#2e7d32", "#ef6c00", "#c62828", "#1565c0", "#3a3f4b"
PURPLE = "#6a1b9a"
ACCENT = THEME.accent
YELLOW = "#fdd835"                      # "running": never confused with a failed (red) state
ACTIVE_RED, ACTIVE_RED_HOVER = "#8b0000", "#a00000"
STATE_COLORS = {"ok": GREEN, "warn": ORANGE, "bad": RED, "info": BLUE, "neutral": GREY}

# Accent outline on hover for every input control (the bisect and unlock GUIs apply it app-wide).
HOVER_STYLESHEET = (
    "QPushButton:hover, QCheckBox:hover, QComboBox:hover, QSpinBox:hover, QLineEdit:hover {"
    f"  border: 1px solid {ACCENT};"
    "   border-radius: 6px;"
    "}"
)


SURFACE_BORDER = (4, 1, 1, 1)           # left, top, right, bottom, in px


def _sheen(theme: Theme, reverse: bool = False) -> str:
    top, bottom = (theme.button_low, theme.button) if reverse else (theme.button, theme.button_low)
    return f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {top}, stop:1 {bottom})"


def surface_style(colour: str | None = None, selector: str = "QFrame", radius: int = 8,
                  theme: Theme = THEME) -> str:
    """A status tile or pill on the theme: its surface and edge, and *color* (a state, a category) as a thick
    left edge, in the edge's color for a neutral one. The text keeps the theme's color. The border takes
    SURFACE_BORDER of the room inside: a tile or pill gives that back from its margins or padding."""
    return (f"{selector} {{ background:{_sheen(theme)}; border:1px solid {theme.edge}; "
            f"border-left:4px solid {colour or theme.edge}; border-radius:{radius}px; color:{theme.text}; }}")


def muted(theme: Theme = THEME) -> str:
    """Secondary text (a version, a hint): the text color toned down towards the window."""
    text, window = QColor(theme.text), QColor(theme.window)
    return QColor.fromRgbF(*((a + b) / 2 for a, b in zip(text.getRgbF()[:3], window.getRgbF()[:3]))).name()


def palette(theme: Theme = THEME) -> QPalette:
    p = QPalette()
    role = QPalette.ColorRole
    for r, colour in (
        (role.Window, theme.window), (role.WindowText, theme.text), (role.Base, theme.base),
        (role.AlternateBase, theme.alt), (role.Text, theme.text), (role.Button, theme.button_low),
        (role.ButtonText, theme.text), (role.ToolTipBase, theme.base), (role.ToolTipText, theme.text),
        (role.Highlight, theme.accent), (role.HighlightedText, theme.accent_text), (role.Link, theme.accent),
        (role.BrightText, "#ffffff"), (role.Light, QColor(theme.button).lighter(130).name()),
        (role.Midlight, theme.button), (role.Mid, muted(theme)), (role.Dark, theme.edge),
        (role.Shadow, theme.edge),
        (role.PlaceholderText, muted(theme)),
    ):
        p.setColor(r, QColor(colour))
    disabled = QColor(theme.text)
    disabled.setAlpha(110)
    for r in (role.Text, role.WindowText, role.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, r, disabled)
    return p


def stylesheet(theme: Theme = THEME) -> str:
    """The theme's controls: buttons and tabs with a sheen, thin borders, the accent on focus and selection."""
    return f"""
QPushButton, QToolButton {{
    background:{_sheen(theme)}; border:1px solid {theme.edge}; border-radius:5px; padding:4px 14px;
    color:{theme.text};
}}
QPushButton:hover, QToolButton:hover {{ border-color:{theme.accent}; }}
QPushButton:pressed, QToolButton:pressed, QToolButton:checked {{ background:{_sheen(theme, reverse=True)}; }}
QPushButton:disabled, QToolButton:disabled {{ color:{muted(theme)}; }}
QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QSpinBox, QDoubleSpinBox, QComboBox, QListView, QTreeView,
QTableView {{ border:1px solid {theme.edge}; border-radius:4px; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color:{theme.accent};
}}
QTabWidget::pane {{ border:1px solid {theme.edge}; border-radius:4px; top:-1px; }}
QTabBar::tab {{
    background:{_sheen(theme)}; border:1px solid {theme.edge}; border-bottom:none; padding:6px 16px;
    border-top-left-radius:5px; border-top-right-radius:5px; margin-right:2px; color:{theme.text};
}}
QTabBar::tab:selected {{ background:{theme.window}; border-top:2px solid {theme.accent}; }}
QHeaderView::section {{
    background:{_sheen(theme)}; border:none; border-right:1px solid {theme.edge}; padding:4px 8px;
    color:{theme.text};
}}
QProgressBar {{ border:1px solid {theme.edge}; border-radius:4px; background:{theme.base}; text-align:center; }}
QProgressBar::chunk {{ background:{theme.accent}; border-radius:3px; }}
QScrollBar:vertical {{ background:{theme.base}; width:12px; }}
QScrollBar::handle:vertical {{
    background:{theme.button}; border:1px solid {theme.edge}; border-radius:5px; min-height:24px;
}}
QScrollBar:horizontal {{ background:{theme.base}; height:12px; }}
QScrollBar::handle:horizontal {{
    background:{theme.button}; border:1px solid {theme.edge}; border-radius:5px; min-width:24px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:none; }}
"""


def apply_theme(app: QApplication, extra: str = "", theme: Theme = THEME) -> None:
    """The theme's palette and style sheet on *app*, with *extra* (the app's own app-wide sheet) after it."""
    app.setPalette(palette(theme))
    app.setStyleSheet(stylesheet(theme) + extra)


def load_fonts(font_dir: Path = FONT_DIR) -> set[str]:
    """Register the bundled Inter TTFs with Qt; returns the font families that were added."""
    families: set[str] = set()
    for ttf in sorted(font_dir.glob("Inter-*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(ttf))
        if font_id >= 0:
            families.update(QFontDatabase.applicationFontFamilies(font_id))
    return families


@lru_cache(maxsize=1)
def header_font() -> str:
    """CSS font-family for titles and metric boxes. macOS uses SF Pro, which has a real heavy weight;
    elsewhere the bundled Inter (SIL OFL) gives the same look instead of a thinner fallback."""
    if sys.platform == "darwin":
        return ""
    return "font-family:'Inter';" if "Inter" in load_fonts() else ""
