# SPDX-License-Identifier: GPL-3.0-or-later
"""The portable window: the Windows Portable Suite's design and the widgets its apps are built of (owner,
26-10-2026: direction D, B's amber on C's cards; a small screen held in the hands, used by touch and a controller,
often without a keyboard).

The design: a near-black window, cards a step lighter, one amber for focus and the main action (PORTABLE, a theme for
core's widgets, set with create_app(theme=PORTABLE)). The focused card is raised, with an amber edge and an amber
glow under it. Sizes are the mock-up's at 1280 x 720 and scale with the screen (scale()), read from the device
rather than assumed: the Ally's own screen at 150 % is 1280 x 720, a TV at 125 % is 1536 x 864.

The widgets: PortableHeader (title, version, a status line; an icon only when given), Card (a focusable card with a title and a line of
text), Pane (the detail pane), Pill (a big button that shows its controller button: A Open, Y Update), InfoPill and
InfoPopup (an "i" that shows more text than fits, over the window), Legend (the
buttons that have no pill: X Details, B Back) and PortableWindow, which moves the focus between the cards and pills
with the d-pad, the left stick or the arrow keys, and turns A or Enter into the focused card's or pill's action, B or
Escape into back."""

from __future__ import annotations

import datetime
import html
import math
import os
import subprocess
import sys
from pathlib import Path
from collections.abc import Callable, Sequence

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QKeyEvent, QPainter, QPen, QPixmap, QScreen, QTextDocument
from PyQt6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QHBoxLayout,
                             QLabel, QLayout, QPlainTextEdit, QPushButton, QScroller, QSizePolicy, QStackedWidget,
                             QVBoxLayout, QWidget)

from . import appinfo, platform
from .gamepad import Gamepad
from .theme import Theme, load_fonts

# Direction D (the owner's, 26-10-2026; mockups_d.py)
BACKGROUND = "#121214"      # the window
SURFACE = "#1d1e22"         # a card, the detail pane, a pill that is not the main action
RAISED = "#292b31"          # the focused card; a glyph's circle
EDGE = "#35383f"            # borders of fields and lists
TEXT = "#f5f4f0"            # the text
DIM = "#a5a5ab"             # the second line: what a card does, the version, the status
AMBER = "#f5a524"           # the accent: focus, the main action, the selected tab, an update
ON_AMBER = "#141414"        # text on the amber
BUTTON = "#cd8b22"          # the main pill (owner, 27-10-2026, a trial), with its glyph's letter

PORTABLE = Theme("Portable", True, window=BACKGROUND, base=SURFACE, alt=RAISED, text=TEXT, button=RAISED,
                 button_low=SURFACE, edge=EDGE, accent=AMBER, accent_text=ON_AMBER)

BASE_WIDTH, BASE_HEIGHT = 1280, 720     # the mock-up's logical screen: every size below is at this one
RADIUS = 14
TITLE, SUBTITLE, TAB, CARD, BODY, PILL, GLYPH, LEGEND, STATUS = 28, 15, 19, 20, 13, 15, 10, 12, 18   # pt
GLOW_BLUR, GLOW_OFFSET = 36, 8
WIDE_ICON = 1.25                        # a wide icon on a tile: this much taller than a square one
ICON = 64                               # a tile's icon (logical px at 1280 x 720)
DIMMED = 0.6                            # a focused pill, drawn at this opacity, and one under the mouse
PILL_HEIGHT, PILL_WIDTH = 48, 150       # every pill: the same height, at least this wide (owner, 29-10-2026)
ROW_HEIGHT = 40                         # a row of a list or of the settings
ROW_FOCUS = "#3a3d45"                   # the focused row: raised above the others, with the amber edge
DOT = "#e5484d"                         # Card.set_dot(): something new is out (owner, 29-10-2026: a red dot)
DOT_SIZE, DOT_INSET = 14, 12            # its size, and its distance from the card's top right corner
POPUP_TEXT = 0.7                        # a popup's text: at most this part of the window high, then it scrolls
POPUP_WIDTH = 900                       # a popup's panel (owner, 30-10-2026: 640 by half the window was cramped)
FONT = "Inter"

_scale = 1.0
_pinned = False                         # pin_scale(): the windows keep the scale given
MIN_SCALE = 0.6                         # text smaller than this is too small to read in the hands
_glass = 255                            # the cards' and panes' opacity: glass()
# The wallpaper behind every window of the suite (owner, 28-10-2026: the portal's first; 29-10-2026: "available
# throughout the suite"), on or off for the whole suite on the portal's Settings page: <suite>\suite.ini, look/wallpaper
WALLPAPER = Path(__file__).resolve().parent / "images" / "wallpaper.webp"
SHADE = 150                             # of 255: how much of the background lies over the wallpaper
GLASS = 160                             # of 255: the cards' and panes' opacity over it, so it shines through (200
                                        # read as solid on the Ally: owner, 29-10-2026)
LOOK_KEY = "look/wallpaper"
# Which wallpaper (owner, 30-10-2026: a selector, only pictures dropped in the suite's wallpaper folder): its file name
# in <suite data>\wallpapers, "" the suite's own; and its transparency, the % of the background over it (as the BC250
# portal's veil), SHADE's when never set
PICTURE_KEY = "look/wallpaper_picture"
VEIL_KEY = "look/wallpaper_transparency"
VEIL_MAX, VEIL_STEP = 90, 10            # 90 %: the picture still shows; Wallpaper: Off takes it away
PICTURE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
PICTURE_MIN = (1280, 720)               # the Ally's screen: a smaller picture blurs when it fills the window
PICTURE_RULES = "PNG, JPEG or WebP, wider than high, at least 1280 x 720 pixels"
SOUND_KEY = "look/sound"                # the suite's sounds (the portal's intro) on or off: sound_on()
SCREEN_KEY = "look/screen"              # the screen the suite's apps start on: start_screen() (owner, 31-10-2026)
RESTARTED = "PORTABLE_RESTARTED"        # set for an app started again on another screen: no intro the second time
_fonts_loaded = False


def scale(screen_size: tuple[int, int] | None = None) -> float:
    """How much larger (or smaller) than the mock-up everything is drawn: the screen's logical size against
    1280 x 720, the smaller ratio, so the layout fits a larger screen and a smaller one alike (owner, 28-10-2026: it
    adapts to the screen it is on; a 1080p screen at 175 % is 1097 x 617), at least MIN_SCALE. Set for the app when
    called with a size; read otherwise."""
    global _scale
    if screen_size is not None:
        width, height = screen_size
        _scale = max(MIN_SCALE, min(width / BASE_WIDTH, height / BASE_HEIGHT))
    return _scale


def pin_scale(screen_size: tuple[int, int] | None) -> float:
    """The scale of *screen_size*, kept: a PortableWindow made afterwards does not read its screen (tests, and pictures
    rendered for the wiki, at the Ally's 1280 x 720 whatever screen the machine has). None reads the screen again."""
    global _pinned
    _pinned = screen_size is not None
    return scale(screen_size) if screen_size is not None else _scale


def glass(alpha: int | None = None) -> int:
    """How opaque the cards and panes are, 0 to 255: 255 (solid) unless a window with a wallpaper behind it sets it,
    before it builds its cards, so the picture shines through (owner, 28-10-2026). Set when given; read otherwise."""
    global _glass
    if alpha is not None:
        _glass = max(0, min(255, alpha))
    return _glass


def look_settings(suite: str):
    """The suite's own settings, shared by its apps: %APPDATA%\\<suite>\\suite.ini (~/.config/<suite>/suite.ini)."""
    from PyQt6.QtCore import QSettings
    return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, suite, "suite")


def wallpaper_on(suite: str) -> bool:
    """Whether the suite's apps show the wallpaper: on unless switched off on the portal's Settings page."""
    return str(look_settings(suite).value(LOOK_KEY, "true")).lower() != "false"


def set_wallpaper_on(suite: str, on: bool) -> None:
    settings = look_settings(suite)
    settings.setValue(LOOK_KEY, "true" if on else "false")
    settings.sync()


def sound_on(suite: str) -> bool:
    """Whether the suite's apps play their sounds (the portal's intro): on unless switched off on the portal's Suite
    page (owner, 29-10-2026)."""
    return str(look_settings(suite).value(SOUND_KEY, "true")).lower() != "false"


def set_sound_on(suite: str, on: bool) -> None:
    settings = look_settings(suite)
    settings.setValue(SOUND_KEY, "true" if on else "false")
    settings.sync()


def start_screen(suite: str) -> QScreen | None:
    """The screen the suite's apps open on: the one an app was last moved to (by name), while it is attached, else
    Windows' main display (owner, 31-10-2026: moved to the Ally's own screen, it stays there)."""
    name = str(look_settings(suite).value(SCREEN_KEY, "")) if suite else ""
    return next((screen for screen in QGuiApplication.screens() if name and screen.name() == name),
                QGuiApplication.primaryScreen())


def set_start_screen(suite: str, screen: QScreen) -> None:
    if suite:
        settings = look_settings(suite)
        settings.setValue(SCREEN_KEY, screen.name())
        settings.sync()


def screen_label(screen: QScreen) -> str:
    """A screen's name for a person: its model as Windows names it (Mi TV), or Display 1 for one without a name (the
    device's own screen, DISPLAY1 in Windows)."""
    name = screen.name()
    if name.startswith("\\\\.\\"):
        return name[4:].replace("DISPLAY", "Display ")
    if not name:                                        # no name at all: its place among the screens
        screens = QGuiApplication.screens()
        return f"Display {screens.index(screen) + 1}" if screen in screens else "Display"
    return name


def restart_command(pid: int, argv: Sequence[str], cwd: str) -> list[str]:
    """PowerShell that waits for this app (*pid*) to end, then starts it again with its own command line (*argv*:
    the program and its arguments), RESTARTED set: the new one finds no running instance to hand over to."""
    def quote(text: str) -> str:
        return "'" + text.replace("'", "''") + "'"
    program, args = argv[0], list(argv[1:])
    start = f"Start-Process -FilePath {quote(program)} -WorkingDirectory {quote(cwd)}"
    if args:
        start += " -ArgumentList " + ", ".join(quote(arg) for arg in args)
    line = f"Wait-Process -Id {pid} -ErrorAction SilentlyContinue; $env:{RESTARTED} = '1'; {start}"
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", line]


def own_command() -> list[str]:
    """This app's command line, to start it again: the installed program with its arguments, or from a checkout
    Python's windowless pythonw.exe with the module (no console window)."""
    argv = list(getattr(sys, "orig_argv", sys.argv))
    if not getattr(sys, "frozen", False):
        program = Path(sys.executable)
        windowless = program.with_name("pythonw.exe")
        argv[0] = str(windowless if windowless.is_file() else program)
    return argv


def wallpaper_folder(suite: str) -> Path:
    """Where the suite's wallpapers are dropped: %LOCALAPPDATA%\\<suite>\\wallpapers (the portal's installer makes it)."""
    from .platform import suite_data
    return suite_data(suite) / "wallpapers"


def picture_problem(path: Path) -> str:
    """Why *path* cannot be a wallpaper (PICTURE_RULES), "" when it can; its size read without decoding it."""
    from PyQt6.QtGui import QImageReader
    if path.suffix.lower() not in PICTURE_SUFFIXES:
        return "not a PNG, JPEG or WebP picture"
    size = QImageReader(str(path)).size()
    if not size.isValid():
        return "not a picture that can be read"
    if size.width() < PICTURE_MIN[0] or size.height() < PICTURE_MIN[1]:
        return f"{size.width()} x {size.height()}, smaller than {PICTURE_MIN[0]} x {PICTURE_MIN[1]}"
    if size.width() <= size.height():
        return f"{size.width()} x {size.height()}, not wider than high"
    return ""


def wallpapers(suite: str) -> tuple[list[Path], dict[str, str]]:
    """The pictures in the suite's wallpaper folder that can be one, by name; and the others' names, each with why
    not. The folder is made when it is missing."""
    folder = wallpaper_folder(suite)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        files = sorted((p for p in folder.iterdir() if p.is_file()), key=lambda p: p.name.lower())
    except OSError:
        return [], {}
    usable, refused = [], {}
    for path in files:
        problem = picture_problem(path)
        if problem:
            refused[path.name] = problem
        else:
            usable.append(path)
    return usable, refused


def wallpaper_picture(suite: str, default: Path | None = WALLPAPER) -> Path | None:
    """The picture the suite's apps show: the one chosen on the portal's Settings page while it is still in the
    folder and can be one, else *default* (the suite's own)."""
    name = str(look_settings(suite).value(PICTURE_KEY, "") or "")
    if name:
        path = wallpaper_folder(suite) / Path(name).name
        if path.is_file() and not picture_problem(path):
            return path
    return default


def set_wallpaper_picture(suite: str, path: Path | None) -> None:
    """*path*, a picture in the suite's wallpaper folder, as the suite's wallpaper; None: the suite's own."""
    settings = look_settings(suite)
    settings.setValue(PICTURE_KEY, path.name if path is not None else "")
    settings.sync()


def wallpaper_veil(suite: str) -> int | None:
    """The wallpaper's transparency in %, 0 to VEIL_MAX: how much of the background lies over it; None when never set
    (SHADE's then)."""
    value = look_settings(suite).value(VEIL_KEY)
    try:
        return max(0, min(VEIL_MAX, int(value))) if value is not None else None
    except (TypeError, ValueError):
        return None


def set_wallpaper_veil(suite: str, percent: int) -> None:
    settings = look_settings(suite)
    settings.setValue(VEIL_KEY, max(0, min(VEIL_MAX, percent)))
    settings.sync()


def shade(veil: int | None) -> int:
    """The background's alpha over the wallpaper, 0 to 255, for a transparency in % (None: SHADE)."""
    return SHADE if veil is None else round(veil * 255 / 100)


def surface(color: str) -> str:
    """*color* (SURFACE, RAISED) as a style sheet color at glass()'s opacity."""
    if _glass >= 255:
        return color
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {_glass})"


def px(value: float) -> int:
    """A size of the mock-up (logical px or pt at 1280 x 720) on this screen."""
    return round(value * _scale)


def font(size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont(FONT)
    f.setPointSizeF(size * _scale)
    f.setWeight(weight)
    return f


def text_label(text: str, size: float, weight: QFont.Weight = QFont.Weight.Normal, color: str = TEXT,
               wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setFont(font(size, weight))
    label.setStyleSheet(f"color: {color}; background: transparent;")
    label.setWordWrap(wrap)
    return label


def lift(widget: QWidget, focus: bool) -> None:
    """The focused card's or pill's amber glow under it (direction D's lift), or none."""
    if not focus:
        widget.setGraphicsEffect(None)
        return
    glow = QGraphicsDropShadowEffect(widget)
    glow.setBlurRadius(px(GLOW_BLUR))
    glow.setOffset(0, px(GLOW_OFFSET))
    glow.setColor(QColor(AMBER))
    widget.setGraphicsEffect(glow)


def one_page(stack: QStackedWidget) -> None:
    """Every page of *stack* but its current one hidden. A switch away from the page that holds the focus hands the
    focus on (to a card), and a card that switches the stack to its own pane in that moment runs a switch inside the
    first one: QStackedLayout then showed both pages, the see-through one over the other (the text of one pane on
    another, owner 29-10-2026)."""
    current = stack.currentWidget()
    for n in range(stack.count()):
        page = stack.widget(n)
        if page is not current and not page.isHidden():
            page.hide()


class Glyph(QLabel):
    """A controller button as the legend and the pills show it: its letter in a circle, amber for the main one. It
    paints itself (owner, 29-10-2026: on the Ally a stylesheet's border-radius on a QLabel showed a square):
    set_colors() sets the letter's and the circle's color."""

    def __init__(self, button: str, filled: bool = False, parent: QWidget | None = None):
        super().__init__(button, parent)
        self.setFont(font(GLYPH, QFont.Weight.Bold))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(px(30 if len(button) == 1 else 40), px(26))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.colors = (ON_AMBER, AMBER) if filled else (TEXT, RAISED)

    def set_colors(self, color: str, background: str) -> None:
        if (color, background) != self.colors:
            self.colors = (color, background)
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.colors[1]))
        radius = self.height() / 2
        painter.drawRoundedRect(QRectF(self.rect()), radius, radius)
        painter.setPen(QColor(self.colors[0]))
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())


# The Ally's View and Menu buttons as it shows them: two squares, three lines (owner, 28-10-2026: not "Menu")
VIEW, MENU = "⧉", "☰"
# The legend's buttons and the window's actions they stand for (Gamepad's names)
LEGEND_ACTIONS = {"A": "accept", "B": "back", "X": "x", "Y": "y", "LB": "previous", "RB": "next", "LT": "lt",
                  "RT": "rt", "R3": "keyboard", MENU: "menu", VIEW: "view", "View": "view"}
KEYBOARD = ("R3", "Keyboard")   # the legend's entry for Windows' touch keyboard, where a page has a field to type in
KEYBOARD_TRIES, KEYBOARD_WAIT = 12, 250   # its host just started: asked this often, so many ms apart
# Every window's last entries (owner, 29-10-2026: "Close" on B was not clear): Menu the pane's information, B back,
# View leaves the app
INFO, BACK, EXIT = (MENU, "Info"), ("B", "Back"), (VIEW, "Exit app")


# The Windows key as a KeyCap shows it: its four panes, drawn (no font has the logo)
WINDOWS_KEY = "Win"


class KeyCap(Glyph):
    """A keyboard key as the legend shows it (owner, 31-10-2026: "with icons, not a long line of text"): its name on
    a key cap, a rounded square where a controller button is a circle; WINDOWS_KEY draws the Windows key's panes."""

    def __init__(self, key: str, parent: QWidget | None = None):
        super().__init__(key, parent=parent)
        self.setFixedSize(max(px(26), self.fontMetrics().horizontalAdvance(key) + px(14)) if key != WINDOWS_KEY
                          else px(26), px(26))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.colors[1]))
        painter.drawRoundedRect(QRectF(self.rect()), px(5), px(5))
        if self.text() == WINDOWS_KEY:
            side, gap = self.height() * 0.2, self.height() * 0.06
            left, top = (self.width() - 2 * side - gap) / 2, (self.height() - 2 * side - gap) / 2
            painter.setBrush(QColor(self.colors[0]))
            for col in (0, 1):
                for row in (0, 1):
                    painter.drawRect(QRectF(left + col * (side + gap), top + row * (side + gap), side, side))
            return
        painter.setPen(QColor(self.colors[0]))
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())


class KeyHint(QWidget):
    """The legend's keyboard shortcut at its left: what it does, then its keys ("Switch screen", Win + Shift + ← →);
    "+" and "/" between them are written, every other one is a KeyCap."""

    def __init__(self, text: str, keys: Sequence[str], parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, px(2), 0, px(2))
        row.setSpacing(px(4))
        row.addWidget(text_label(text, LEGEND, QFont.Weight.DemiBold, DIM))
        row.addSpacing(px(4))
        self.caps = []
        for key in keys:
            if key in ("+", "/"):
                row.addWidget(text_label(key, LEGEND, QFont.Weight.DemiBold, DIM))
            else:
                cap = KeyCap(key)
                row.addWidget(cap)
                self.caps.append(cap)


class LegendItem(QWidget):
    """One entry of the legend, the glyph and its text: tapped, it does what its button does (owner, 29-10-2026:
    the bottom row is for actions), so an action with a controller button needs no pill of its own."""

    pressed = pyqtSignal()

    def __init__(self, button: str, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, px(2), 0, px(2))      # a finger's target, a little taller than the glyph
        row.setSpacing(px(8))
        self.glyph = Glyph(button)
        row.addWidget(self.glyph)
        self.label = text_label(text, LEGEND, QFont.Weight.DemiBold)
        row.addWidget(self.label)

    def mousePressEvent(self, event) -> None:
        self.pressed.emit()
        event.accept()


class Legend(QWidget):
    """The row at the bottom: the controller buttons the page answers to, each with what it does (X Steam mark,
    Y Update Steam, B Close). An action with a button is here, not on a pill too (owner, 29-10-2026: "we have
    update steam 2 times"); a tap on an entry does the same as its button, through the window's on_action(), so
    every action stays reachable by touch. A, the amber one, belongs to the page's main pill."""

    activated = pyqtSignal(str)                         # the button tapped ("X")

    def __init__(self, items: Sequence[tuple[str, str]] = (), parent: QWidget | None = None):
        super().__init__(parent)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.entries: dict[str, LegendItem] = {}
        self.items: list[tuple[str, str]] | None = None  # None: nothing built yet
        self.keys: tuple[str, tuple[str, ...]] | None = None
        self.hint: KeyHint | None = None
        self.set_items(items)

    def set_items(self, items: Sequence[tuple[str, str]], keys: tuple[str, Sequence[str]] | None = None) -> None:
        """The entries, in order, with *keys* (what a keyboard shortcut does, and its keys: KeyHint) at the left;
        the same ones again change nothing (a page refreshes while it downloads)."""
        keys = (keys[0], tuple(keys[1])) if keys else None
        if list(items) == self.items and keys == self.keys:
            return
        while self.row.count():
            item = self.row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()                           # gone now, not when Qt deletes it later
                widget.deleteLater()
        self.hint = KeyHint(*keys) if keys else None
        if self.hint is not None:
            self.row.addWidget(self.hint)
        self.row.addStretch()
        self.entries = {}
        for button, text in items:
            entry = LegendItem(button, text)
            entry.pressed.connect(lambda button=button: self._tapped(button))
            self.row.addWidget(entry)
            self.row.addSpacing(px(18))
            self.entries[button] = entry
        self.items, self.keys = list(items), keys

    def _tapped(self, button: str) -> None:
        self.activated.emit(button)
        window = self.window()
        action = LEGEND_ACTIONS.get(button)
        if action and isinstance(window, PortableWindow):
            window.act(action)


class TabLabel(QLabel):
    """One tab: its name, amber with a line under it while selected, dimmed otherwise; a tap selects it."""

    pressed = pyqtSignal(str)

    def __init__(self, key: str, name: str):
        super().__init__(name)
        self.key = key
        self.setFont(font(TAB, QFont.Weight.Bold))
        self.setContentsMargins(px(4), 0, px(4), px(6))
        self.paint(False)

    def paint(self, selected: bool) -> None:
        line = f"{px(3)}px solid {AMBER if selected else 'transparent'}"
        self.setStyleSheet(f"color: {AMBER if selected else DIM}; background: transparent; border-bottom: {line};")

    def mousePressEvent(self, event) -> None:
        self.pressed.emit(self.key)
        event.accept()


class Tabs(QWidget):
    """Tabs between the LB and RB glyphs, the portal's categories first (29-10-2026: a page's parts too, PCSX2
    Manager's settings): those buttons step through them (step(), bound to previous and next), a tap picks one;
    the selected tab is amber with a line under it. changed(key) when another is selected."""

    changed = pyqtSignal(str)

    def __init__(self, tabs: Sequence[tuple[str, str]], parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(px(14))
        self.keys = [key for key, _ in tabs]
        self.labels: dict[str, TabLabel] = {}
        self.current = ""
        row.addWidget(Glyph("LB"))
        for key, name in tabs:
            label = TabLabel(key, name)
            label.pressed.connect(self.select)
            self.labels[key] = label
            row.addWidget(label)
        row.addWidget(Glyph("RB"))
        row.addStretch()
        if self.keys:
            self.select(self.keys[0])

    def select(self, key: str) -> None:
        if key not in self.labels or key == self.current:
            return
        self.current = key
        for other, label in self.labels.items():
            label.paint(other == key)
        self.changed.emit(key)

    def step(self, delta: int) -> None:
        """LB (-1) or RB (+1): the next tab round."""
        if not self.keys:
            return
        at = self.keys.index(self.current) if self.current in self.keys else 0
        self.select(self.keys[(at + delta) % len(self.keys)])


class PortableHeader(QWidget):
    """The app's name large with the version under it, and a status line on the right (battery, time). The icon
    before the name only when one is given (owner, 27-10-2026: the test app's screen is too small for it)."""

    def __init__(self, title: str, version: str, icon: QPixmap | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.icon: QLabel | None = None
        if icon is not None and not icon.isNull():
            self.icon = QLabel()
            self.icon.setFixedSize(px(60), px(60))
            self.icon.setPixmap(icon.scaled(self.icon.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))
            row.addWidget(self.icon)
            row.addSpacing(px(16))
        column = QVBoxLayout()
        column.setSpacing(0)
        self.title = text_label(title, TITLE, QFont.Weight.ExtraBold)
        self.version = text_label(version, SUBTITLE, color=DIM)
        column.addWidget(self.title)
        column.addWidget(self.version)
        row.addLayout(column)
        row.addStretch()
        lines = QVBoxLayout()
        lines.setSpacing(0)
        self.status = text_label("", STATUS, QFont.Weight.Bold)      # owner, 26-10-2026: 13 pt dimmed was too small
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight)
        lines.addWidget(self.status)                                   # level with the top of the title (owner)
        self.second = text_label("", STATUS, QFont.Weight.Bold)      # a second line under it, when one is given
        self.second.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.second.hide()
        lines.addWidget(self.second)
        lines.addStretch()
        row.addLayout(lines)

    def set_status(self, parts: Sequence[str | tuple[str, str]],
                   second: Sequence[str | tuple[str, str]] = ()) -> None:
        """The status line's *parts* joined by bars; *second* on a line of its own under it (owner, 28-10-2026: the
        test app's temperatures under the battery, the date and the time). A part may be (text, color), in that
        color (owner, 31-10-2026: the portal's Turbo letter red)."""
        _set_line(self.status, parts)
        self.second.setVisible(_set_line(self.second, second))


def _set_line(label: QLabel, parts: Sequence[str | tuple[str, str]]) -> bool:
    """*parts* on *label* joined by bars, plain text unless a part has a color of its own; whether there is any."""
    parts = [part for part in parts if part and (isinstance(part, str) or part[0])]
    if all(isinstance(part, str) for part in parts):
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setText("  |  ".join(parts))
    else:
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText("&nbsp;&nbsp;|&nbsp;&nbsp;".join(
            html.escape(part) if isinstance(part, str) else
            f'<span style="color: {part[1]}">{html.escape(part[0])}</span>' for part in parts))
    return bool(parts)


DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def status_clock(now: datetime.datetime | None = None) -> list[str]:
    """The date and the time for the header's status line, before the battery (owner, 30-10-2026: the battery last):
    "Monday 27/10/2026", "17:04" (owner, 28-10-2026). The day's name is English whatever Windows' language, as the apps' text is."""
    now = now or datetime.datetime.now()
    return [f"{DAYS[now.weekday()]} {now:%d/%m/%Y}", f"{now:%H:%M}"]


def trimmed(pixmap: QPixmap) -> QPixmap:
    """*pixmap* without its fully transparent edges: a picture padded to a square shows at its own size."""
    image = pixmap.toImage()
    rows = [y for y in range(image.height()) if any(image.pixelColor(x, y).alpha() for x in range(0, image.width(), 2))]
    cols = [x for x in range(image.width()) if any(image.pixelColor(x, y).alpha() for y in range(0, image.height(), 2))]
    if not rows or not cols:
        return pixmap
    return pixmap.copy(cols[0], rows[0], cols[-1] - cols[0] + 1, rows[-1] - rows[0] + 1)


class Card(QFrame):
    """A card with a title and a line of text, focusable: raised with an amber edge and glow while it has the
    focus. A tap or a click gives it the focus (focused); A, Enter or a second tap acts (activated). With an
    *icon* it is a tile (the portal's apps): the icon centered above the title and the text, both centered."""

    focused = pyqtSignal()
    activated = pyqtSignal()

    def __init__(self, title: str, text: str = "", icon: QPixmap | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.selected = False                           # the focus is in this card's pane: the edge, no glow
        self.setObjectName("card")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        column = QVBoxLayout(self)
        self.icon: QLabel | None = None
        self.title = text_label(title, CARD, QFont.Weight.Bold)
        self.text = text_label(text, BODY, color=DIM, wrap=True)
        if icon is not None and not icon.isNull():
            column.setContentsMargins(px(16), px(14), px(16), px(12))
            self.icon = QLabel()
            # Its transparent edges trimmed, and a wide picture (the Gaming icon's handheld, 2:1) as wide as twice
            # the icon's height, so it does not end up half the size of a square one (owner, 28-10-2026)
            icon = trimmed(icon)
            ratio = min(2.0, max(1.0, icon.width() / max(1, icon.height())))
            high = ICON * (WIDE_ICON if ratio > 1.2 else 1)          # the tile has room for a taller wide one
            self.icon.setFixedSize(px(high * ratio), px(high))
            self.icon.setPixmap(icon.scaled(self.icon.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))
            self.icon.setStyleSheet("background: transparent;")
            column.addStretch()
            column.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignHCenter)
            column.addSpacing(px(6))
            for label in (self.title, self.text):
                label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        else:
            column.setContentsMargins(px(20), px(12), px(20), px(12))
        column.addWidget(self.title)
        column.addWidget(self.text)
        if self.icon is not None:
            column.addStretch()
        self.dot = False                                # set_dot(): something new is out for it
        self._paint(False)

    def set_text(self, text: str, color: str = DIM) -> None:
        """The line under the title, in *color* (amber for an update on a tile)."""
        self.text.setText(text)
        self.text.setStyleSheet(f"color: {color}; background: transparent;")

    def set_dot(self, on: bool) -> None:
        """A red dot at the top right corner: something new is out for it (owner, 29-10-2026: an app's update on
        its portal tile)."""
        if on != self.dot:
            self.dot = on
            self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.dot:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(DOT))
            radius = px(DOT_SIZE) / 2
            painter.drawEllipse(QPointF(self.width() - px(DOT_INSET) - radius, px(DOT_INSET) + radius), radius, radius)

    def _paint(self, focus: bool) -> None:
        edge = f"{px(2)}px solid {AMBER}" if focus or self.selected else f"{px(2)}px solid transparent"
        # Focused it stays solid: its amber glow under a see-through card would tint it (glass())
        self.setStyleSheet(f"QFrame#card {{ background: {RAISED if focus or self.selected else surface(SURFACE)};"
                           f" border: {edge}; border-radius: {px(RADIUS)}px; }}")
        lift(self, focus)

    def set_selected(self, selected: bool) -> None:
        """The card whose pane has the focus: its amber edge without the glow, so card and pane read as one (owner,
        29-10-2026: hardly visible where you are)."""
        if selected != self.selected:
            self.selected = selected
            self._paint(self.hasFocus())

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._paint(True)
        self.focused.emit()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._paint(False)

    def mousePressEvent(self, event) -> None:
        if self.hasFocus():
            self.activated.emit()
        else:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activated.emit()
            return
        super().keyPressEvent(event)


class TextView(QPlainTextEdit):
    """A long text to read on the page (owner, 29-10-2026: the log in the app, not in Notepad, which no button
    closes): read-only, the d-pad's up and down scroll it a few lines, a finger drags it; left and right move the focus
    on as everywhere. The focus shows with the amber edge."""

    STEP = 6                                            # lines a press scrolls

    def __init__(self, parent: QWidget | None = None, background: str = RAISED):
        super().__init__(parent)
        self.background = background                    # transparent in a popup's panel
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFont(font(BODY))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        QScroller.grabGesture(self.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        self._style(False)

    def _style(self, focus: bool) -> None:
        edge = AMBER if focus else "transparent"
        self.setStyleSheet(f"QPlainTextEdit {{ color: {TEXT}; background: {self.background};"
                           f" border: {px(2)}px solid {edge};"
                           f" border-radius: {px(10)}px; padding: {px(8)}px; }}"
                           # A thin bar of where in the text it is, no arrows: the d-pad and a finger scroll
                           f" QScrollBar:vertical {{ background: transparent; width: {px(6)}px; margin: 0; }}"
                           f" QScrollBar::handle:vertical {{ background: {DIM}; border-radius: {px(3)}px;"
                           f" min-height: {px(24)}px; }}"
                           " QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
                           " QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }")

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._style(True)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._style(False)

    def scroll(self, direction: str) -> bool:
        """Up or down a few lines; False at that end already (the focus may move on then)."""
        bar = self.verticalScrollBar()
        before = bar.value()
        bar.setValue(before + (-1 if direction == "up" else 1) * self.STEP * bar.singleStep())
        return bar.value() != before

    def show_end(self) -> None:
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def scrolls(self) -> bool:
        """Whether the text is longer than the view shows."""
        return self.verticalScrollBar().maximum() > 0


class Pane(QFrame):
    """The detail pane: a card's surface without the focus, for what the focused card is and does (the test app's
    right side, the portal's strip under the tiles). *column* is its layout. tapped() when a finger or the mouse
    presses the pane itself (not a row or a pill in it): a page connects it to its A action where a tap should do
    that (owner, 29-10-2026: a tap on the Log pane shows the log)."""

    tapped = pyqtSignal()

    def __init__(self, parent: QWidget | None = None, solid: bool = False):
        super().__init__(parent)
        self.setObjectName("pane")
        self.solid = solid                              # never see-through (an InfoPopup's panel)
        self.active = False                             # the focus is inside it: the focused card's edge and glow
        self.restyle()
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(px(24), px(22), px(24), px(22))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.tapped.emit()
        super().mousePressEvent(event)

    def restyle(self) -> None:
        """Its surface at glass()'s opacity (solid when *solid*, and while active, as a focused card), again after
        glass() changed; the amber edge while active."""
        color = SURFACE if self.solid or self.active else surface(SURFACE)
        edge = AMBER if self.active else "transparent"
        self.setStyleSheet(f"QFrame#pane {{ background: {color}; border: {px(2)}px solid {edge};"
                           f" border-radius: {px(RADIUS)}px; }}")

    def set_active(self, active: bool) -> None:
        """The focus moved into the pane, or out of it (PortableWindow follows the focus): where you are reads at a
        glance (owner, 29-10-2026)."""
        if active != self.active:
            self.active = active
            self.restyle()
            lift(self.glow_holder(), active)

    def glow_holder(self) -> QWidget:
        """The widget the glow is put on: a pane in a QStackedWidget, which is as big as the pane and would cut the
        glow off at its edges, lends it the stack's (the stack draws the pane, and the glow under it)."""
        parent = self.parentWidget()
        return parent if isinstance(parent, QStackedWidget) else self


class Pill(QPushButton):
    """A big button with the cards' corners, one kind everywhere (owner, 29-10-2026: "why are the buttons not the same
    everywhere"): amber with dark text, the same height and at least PILL_WIDTH wide, with its controller button's
    glyph when it answers to one (A Open, Y Update), the same without one (touch only). The focus, and the mouse over
    it, dim it (owner, 26-10-2026: a ring or a glow on the amber was too much or too little); disabled it is gray,
    though the suite never disables one (owner, 29-10-2026): a pill that cannot act now says why when pressed.
    *main* is kept for the callers: every pill looks like the main one now. Its button press is the window's:
    PortableWindow.bind(). pill_row() puts a pane's pills in a row at its bottom, right-aligned, A last."""

    activated = pyqtSignal()

    def __init__(self, text: str, button: str = "", main: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.button, self.main = button, main
        row = QHBoxLayout(self)
        row.setContentsMargins(px(10), 0, px(20), 0)
        row.setSpacing(px(10))
        self.glyph: Glyph | None = None
        if button:
            self.glyph = Glyph(button, filled=False)
            row.addWidget(self.glyph)
        self.label = text_label(text, PILL, QFont.Weight.Bold, ON_AMBER)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.label, 1)
        self.setMinimumSize(px(PILL_WIDTH), px(PILL_HEIGHT))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.clicked.connect(self.activated.emit)
        self._colors()

    def _colors(self) -> None:
        """The label's and the glyph's colors: dark on amber, gray when disabled."""
        on = self.isEnabled()
        self.label.setStyleSheet(f"color: {ON_AMBER if on else DIM}; background: transparent;")
        if self.glyph is not None:
            self.glyph.set_colors(BUTTON if on else DIM, ON_AMBER if on else BACKGROUND)

    def _dim(self) -> None:
        """Dimmed while it has the focus or the mouse over it (not when disabled)."""
        if self.isEnabled() and (self.hasFocus() or self.underMouse()):
            if not isinstance(self.graphicsEffect(), QGraphicsOpacityEffect):
                dim = QGraphicsOpacityEffect(self)       # the pill with its glyph and label
                dim.setOpacity(DIMMED)
                self.setGraphicsEffect(dim)
        else:
            self.setGraphicsEffect(None)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(BUTTON if self.isEnabled() else RAISED))
        painter.drawRoundedRect(QRectF(self.rect()), px(RADIUS), px(RADIUS))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange:
            self._colors()
            self._dim()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._dim()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._dim()

    def sizeHint(self) -> QSize:
        # QPushButton measures its own text, which is empty: the glyph and the label are in the layout.
        return self.layout().sizeHint().expandedTo(self.minimumSize())

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._dim()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._dim()

    def set_text(self, text: str) -> None:
        self.label.setText(text)


def pill_row(*pills: Pill) -> QHBoxLayout:
    """A pane's pills in a row at its bottom, right-aligned, in the order given: the A pill last, rightmost (owner,
    29-10-2026: the same place in every pane)."""
    row = QHBoxLayout()
    row.setSpacing(px(12))
    row.addStretch()
    for pill in pills:
        pill.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row.addWidget(pill)
    return row


class Row(Pill):
    """A row of a list or of the settings (a game, a folder, a memory card, "Renderer: Automatic"): focusable and
    acted on with A like a pill, but drawn as a row, text on the left; the focused one raised with the amber edge,
    clearly apart from the others (owner, 29-10-2026)."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent=parent)
        self.layout().setContentsMargins(px(14), 0, px(14), 0)
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.label.setFont(font(PILL - 1, QFont.Weight.DemiBold))
        self.setMinimumSize(px(60), px(ROW_HEIGHT))
        self.setFixedHeight(px(ROW_HEIGHT))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _colors(self) -> None:
        self.label.setStyleSheet(f"color: {TEXT if self.isEnabled() else DIM}; background: transparent;")

    def _dim(self) -> None:
        self.update()                                   # no dimming: the focus is drawn (paintEvent)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        focus = self.hasFocus()
        painter.setBrush(QColor(ROW_FOCUS if focus else EDGE if self.underMouse() and self.isEnabled() else RAISED))
        painter.setPen(QPen(QColor(AMBER), px(2)) if focus else Qt.PenStyle.NoPen)
        inset = px(1) if focus else 0
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(inset, inset, -inset, -inset), px(10), px(10))


class IconPill(Pill):
    """A small round icon at a pane's top right, a ring with a sign drawn in it (draw()): where space is short, it
    opens a popup with the rest, text or controls (owner, 29-10-2026). With the focus, the ring and the sign are
    amber (owner, 29-10-2026: dimmed, as a pill is, it was hard to see which one was active)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("", parent=parent)
        self.label.hide()
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.setMinimumSize(px(32), px(32))
        self.setFixedSize(px(32), px(32))
        # Touch only (owner, 29-10-2026): Menu opens the information, so the d-pad never lands here and A in a pane
        # is always the pane's own action
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _dim(self) -> None:
        self.setGraphicsEffect(None)
        self.update()                                   # the focus is drawn (paintEvent), not dimmed

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        line = max(2.0, side / 14)
        ring = QRectF(line / 2, line / 2, side - line, side - line)
        color = QColor(AMBER if self.hasFocus() else TEXT)
        painter.setPen(QPen(color, line))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(ring)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        self.draw(painter, side)

    def draw(self, painter: QPainter, side: float) -> None:
        """The sign in the ring, in the text color (the pen off, the brush set)."""


class LightPill(IconPill):
    """A light bulb in the ring: a page's light test (the test app's stick lights, owner 29-10-2026)."""

    def draw(self, painter: QPainter, side: float) -> None:
        center = side / 2
        painter.drawEllipse(QPointF(center, side * 0.40), side * 0.17, side * 0.17)        # the bulb
        neck = side * 0.18
        painter.drawRect(QRectF(center - neck / 2, side * 0.52, neck, side * 0.12))
        painter.drawRoundedRect(QRectF(center - neck / 2, side * 0.67, neck, side * 0.07), side * 0.03, side * 0.03)


class InfoPill(IconPill):
    """An information icon (a ring with an "i" drawn in it), for more text than fits on the page (owner, 28-10-2026:
    an icon rather than the letter, at the top right of its pane): A or a tap shows *text* under *title* in an
    InfoPopup over the window."""

    def __init__(self, title: str, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.title, self.info = title, text
        self.activated.connect(self.show_info)

    def draw(self, painter: QPainter, side: float) -> None:
        center = side / 2
        dot = side * 0.085
        painter.drawEllipse(QPointF(center, side * 0.30), dot, dot)
        stem = side * 0.13
        painter.drawRoundedRect(QRectF(center - stem / 2, side * 0.43, stem, side * 0.33), stem / 2, stem / 2)

    def show_info(self) -> None:
        """The popup; closed, the focus goes back to where it was (the icon itself never holds it)."""
        window = self.window()
        if isinstance(window, PortableWindow):
            window.show_popup(self.title, self.info, window.focusWidget())


class InfoPopup(QWidget):
    """The window darkened, with a panel in the middle: a title, the text and a legend at its bottom, B Close (owner,
    29-10-2026: no big amber buttons, the buttons in a legend). A long text scrolls: the d-pad's up and down, or a
    finger (owner, 29-10-2026: a long text was cut off). A, B, Escape, a tap on B Close or beside the panel closes it,
    and the focus goes back to where it came from. With *content* (a widget with rows, owner 29-10-2026: a popup holds
    the controls that do not fit a pane) it shows under the text, the d-pad moves between its rows and A presses one
    (*actions*: the legend's entries for them, before B Close); B, Escape or a tap beside it still closes it."""

    closed = pyqtSignal()

    def __init__(self, window: QWidget, title: str, text: str, back_to: QWidget | None = None,
                 content: QWidget | None = None, actions: Sequence[tuple[str, str]] = ()):
        super().__init__(window)
        self.back_to, self.content = back_to, content
        self.setGeometry(window.rect())
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.panel = Pane(solid=True)
        self.panel.setFixedWidth(px(POPUP_WIDTH))
        inner = px(POPUP_WIDTH - 48)                            # the pane's margins: a wrapped label needs its width to be tall
        heading = text_label(title, 24, QFont.Weight.ExtraBold, wrap=True)
        heading.setFixedWidth(inner)
        self.panel.column.addWidget(heading)
        self.panel.column.addSpacing(px(8))
        self.text = TextView(background="transparent")
        self.text.setFont(font(BODY + 1))
        self.text.setPlainText(text)
        self.text.setFixedWidth(inner)
        # The height the whole text needs, laid out as the view lays it out: its font, its width less the padding, the
        # edge and the scroll bar, as plain text (owner, 30-10-2026: a label measured "[PS4] <title>" as HTML, so it
        # left out what followed, and the text box stayed four lines high with the window's room to spare)
        measure = QTextDocument()
        measure.setDefaultFont(self.text.font())
        measure.setDocumentMargin(self.text.document().documentMargin())
        measure.setPlainText(text)
        measure.setTextWidth(inner - px(20) - px(6))
        needed = math.ceil(measure.size().height()) + px(22)
        self.text.setFixedHeight(max(px(40), min(needed, round(window.height() * POPUP_TEXT))))
        self.panel.column.addWidget(self.text)
        self.panel.column.addSpacing(px(16))
        if content is not None:
            content.setFixedWidth(inner)
            self.panel.column.addWidget(content)
            self.panel.column.addSpacing(px(16))
        self.legend = Legend([*actions, ("B", "Close")])
        self.panel.column.addWidget(self.legend)
        self.panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)    # as high as it needs
        outer.addWidget(self.panel)
        self.show()
        self.raise_()
        self.text.verticalScrollBar().setValue(0)
        if not self.text.scrolls():                     # nothing to scroll: the d-pad never lands on it
            self.text.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        first = content.findChildren(Pill)[0] if content is not None and content.findChildren(Pill) else None
        if first is not None:
            first.setFocus(Qt.FocusReason.OtherFocusReason)
        elif self.text.scrolls():
            self.text.setFocus(Qt.FocusReason.OtherFocusReason)

    def pills(self) -> list[QWidget]:
        """What the d-pad moves between: the text while it scrolls, and the content's rows."""
        text = [self.text] if self.text.focusPolicy() != Qt.FocusPolicy.NoFocus else []
        return [*text, *(pill for pill in self.findChildren(Pill) if pill.isVisible() and pill.isEnabled())]

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        backdrop = QColor(BACKGROUND)
        backdrop.setAlpha(220)
        painter.fillRect(self.rect(), backdrop)

    def mousePressEvent(self, event) -> None:
        if not self.panel.geometry().contains(event.position().toPoint()):
            self.dismiss()
        event.accept()

    def dismiss(self) -> None:
        if self.back_to is not None:                    # first: hidden with the focus, Qt would hand it to a card
            self.back_to.setFocus(Qt.FocusReason.OtherFocusReason)
        self.hide()
        self.closed.emit()
        self.deleteLater()


class PortableWindow(QWidget):
    """The portable app's window: the design, the controller and the keyboard. Moves the focus between the visible
    cards and pills (the nearest one in the direction pressed), turns A or Enter into the focused one's action,
    B or Escape into back(), and a page's own buttons (X, Y, LB, RB, Start) into the handlers bound with bind().
    The controller only counts while the window is active, so a game's input never moves it."""

    back = pyqtSignal()

    def __init__(self, gamepad: Gamepad | None = None, parent: QWidget | None = None, suite: str | None = None,
                 wallpaper: Path | None = WALLPAPER):
        """*suite*: whose look it follows, the wallpaper on or off (default the app's, its AppInfo settings_org; none:
        no wallpaper). *wallpaper*: the picture (None: none)."""
        super().__init__(parent)
        global _fonts_loaded
        if not _fonts_loaded:                           # Inter, bundled with core, once per app
            load_fonts()
            _fonts_loaded = True
        info = appinfo.current()
        self.suite = suite or (info.settings_org if info is not None else "") or ""
        # The screen the suite's apps were last moved to, else the main display: the whole of it, as the apps run full
        # screen over the taskbar. Everything is sized for it once; on a screen of another size the app starts again
        # (screen_moved).
        screen = start_screen(self.suite) if not _pinned else None
        if screen is not None:
            size = screen.geometry().size()
            scale((size.width(), size.height()))
            self.move(screen.geometry().topLeft())      # full screen on that screen, not on the main display
        self.screen_size = screen.geometry().size() if screen is not None else QSize()
        self.move_pending = False                       # moved to a screen of another size while busy: started again
        self.move_timer = QTimer(self)                  # once done
        self.move_timer.setInterval(1000)
        self.move_timer.timeout.connect(self._move_when_free)
        self.setObjectName("portable")
        self.setStyleSheet(f"QWidget#portable {{ background: {BACKGROUND}; }}")
        self.setAutoFillBackground(True)
        self.handlers: dict[str, Callable[[], None]] = {}
        self.toggle_keyboard, self.start_keyboard = platform.toggle_touch_keyboard, platform.start_touch_keyboard
        self.keyboard_tries = 0                         # its host started: tries left
        self.keyboard_timer = QTimer(self)
        self.keyboard_timer.setInterval(KEYBOARD_WAIT)
        self.keyboard_timer.timeout.connect(self._keyboard_again)
        self.gamepad = gamepad if gamepad is not None else Gamepad(self)
        self.gamepad.action.connect(self.on_action)
        self.popup: InfoPopup | None = None
        if self.suite and wallpaper == WALLPAPER:       # the suite's own picture, or the one chosen for the suite
            wallpaper = wallpaper_picture(self.suite)
        self.wallpaper = QPixmap(str(wallpaper)) if wallpaper is not None else QPixmap()
        self.wallpaper_on = bool(self.suite) and wallpaper_on(self.suite)
        self.shade = shade(wallpaper_veil(self.suite)) if self.suite else SHADE
        glass(GLASS if self.shows_wallpaper() else 255)              # before the subclass makes its cards
        self.pane_card: Card | None = None              # the card the focus was on last: selected while in its pane
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._focus_moved)

    def _focus_moved(self, _old: QWidget | None, new: QWidget | None) -> None:
        """Where the focus is, shown (owner, 29-10-2026): a pane with the focus inside it gets the amber edge and glow,
        the card whose pane it is keeps its edge (selected); back on a card, the panes are plain again."""
        if new is None or not self.isAncestorOf(new):
            return
        pane = new
        while pane is not None and pane is not self and not isinstance(pane, Pane):
            pane = pane.parentWidget()
        inside = pane if isinstance(pane, Pane) else None
        if isinstance(new, Card):
            if self.pane_card is not None and self.pane_card is not new:
                self.pane_card.set_selected(False)
            self.pane_card = new
        panes = self.findChildren(Pane)
        for each in panes:                              # the others first: a stack's glow is its current pane's
            if each is not inside:
                each.set_active(False)
        if inside is not None:
            inside.set_active(True)
        if self.pane_card is not None:
            self.pane_card.set_selected(inside is not None and not isinstance(new, Card))
        self.update_legend()                            # B Back only while there is somewhere to go back to

    # The buttons every window shares (owner, 29-10-2026): B goes back, View exits the app, Menu shows the information
    # of the pane that shows. A subclass binds its own with bind() (the portal's Menu: its Settings page).

    def update_legend(self) -> None:
        """The legend for where the focus is now: a subclass with a legend sets it here (called on every move of the
        focus), ending with common_items()."""

    def common_items(self, back: bool | None = None) -> list[tuple[str, str]]:
        """The legend's last entries: Menu Info while the pane that shows has an information icon, B Back when B
        does something (*back*; default: the focus is in a pane, can_go_back()), and View Exit app."""
        back = self.can_go_back() if back is None else back
        return [*([INFO] if self.info_pill() is not None else []), *([BACK] if back else []), EXIT]

    def info_pill(self) -> InfoPill | None:
        """The information icon of what shows: the one in the pane with the focus, else the first one shown (a
        window shows one pane at a time beside its cards); never one in a popup."""
        shown = [pill for pill in self.findChildren(InfoPill) if pill.isVisible()
                 and (self.popup is None or not self.popup.isAncestorOf(pill))]
        pane = _pane_of(self.focusWidget())
        inside = [pill for pill in shown if pane is not None and _pane_of(pill) is pane]
        return (inside or shown or [None])[0]

    def show_info(self) -> bool:
        """Menu: the information of the pane that shows, as its icon would; whether there was one."""
        pill = self.info_pill()
        if pill is None:
            return False
        pill.show_info()
        return True

    def can_go_back(self) -> bool:
        """Whether B has somewhere to go: the focus is in a pane, and the card whose pane it is shows."""
        focus = self.focusWidget()
        return (focus is not None and not isinstance(focus, Card) and _pane_of(focus) is not None
                and self.pane_card is not None and self.pane_card.isVisible())

    def go_back(self) -> bool:
        """B in a pane: the focus back to its card on the left; on a card there is nowhere to go (nothing happens).
        Whether it went."""
        if not self.can_go_back():
            return False
        self.pane_card.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def exit_app(self) -> None:
        """View: the app closes. A subclass that is busy (a download) asks first."""
        self.close()

    def show_keyboard(self) -> None:
        """R3 (owner, 31-10-2026): Windows' touch keyboard shown, or hidden when it shows, over the window; what is
        typed goes to the field with the focus. Its host is started first when it does not run; keyboard_problem()
        says why when it cannot open."""
        if self.keyboard_timer.isActive():
            return
        try:
            self.toggle_keyboard()
            return
        except OSError:
            pass
        try:
            self.start_keyboard()
        except OSError as exc:
            self.keyboard_problem(str(exc))
            return
        self.keyboard_tries = KEYBOARD_TRIES
        self.keyboard_timer.start()

    def _keyboard_again(self) -> None:
        self.keyboard_tries -= 1
        try:
            self.toggle_keyboard()
        except OSError as exc:
            if self.keyboard_tries <= 0:
                self.keyboard_timer.stop()
                self.keyboard_problem(str(exc))
            return
        self.keyboard_timer.stop()

    def keyboard_problem(self, text: str) -> None:
        """Why the touch keyboard did not open, in a popup; a subclass may say it on its page instead."""
        self.show_popup("Touch keyboard", f"Windows' touch keyboard could not be opened. {text}")

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Every stack of the window, as the subclass made them, keeps to one visible page after each switch
        (one_page). The screen sizes the window, never its layout: Qt takes a layout's minimum height with wrapped
        text at the window's narrowest width, more lines than at the screen's, and made a full-screen window taller
        than its screen (owner, 31-10-2026: the portal 1920 x 1099 on a 1080p TV, its bottom on the screen under it)."""
        if self.layout() is not None:
            self.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        handle = self.windowHandle()
        if handle is not None and not self.property("follows_screen"):
            self.setProperty("follows_screen", True)
            handle.screenChanged.connect(self.screen_moved)
        for stack in self.findChildren(QStackedWidget):
            if not stack.property("one_page"):
                stack.setProperty("one_page", True)
                stack.currentChanged.connect(lambda _index, stack=stack: one_page(stack))
        super().showEvent(event)

    def shows_wallpaper(self) -> bool:
        return self.wallpaper_on and not self.wallpaper.isNull()

    # The screen it is on (owner, 31-10-2026): moved to another screen (Win + Shift + an arrow, or the portal's Screen
    # row), the suite's apps open there from then on; on a screen of another size the app starts again there, as
    # everything is sized for its screen once.

    def screen_moved(self, screen: QScreen | None) -> None:
        if screen is None or _pinned:
            return
        set_start_screen(self.suite, screen)
        if screen.geometry().size() != self.screen_size and self.isFullScreen():
            self.move_to(screen)

    def move_to(self, screen: QScreen) -> None:
        """Start again on *screen*, remembered for the suite: at once, or once the app is no longer busy (a download
        or an install), saying so meanwhile (waiting_to_move)."""
        set_start_screen(self.suite, screen)
        self.move_pending = True
        self._move_when_free()

    def can_restart(self) -> bool:
        """Whether the app may end now to start again: not while it downloads or installs (the managers' busy)."""
        return not getattr(self, "busy", False)

    def waiting_to_move(self) -> None:
        """Said while a move waits for the app to finish what it does; a subclass shows it on its page."""

    def _move_when_free(self) -> None:
        if not self.move_pending:
            self.move_timer.stop()
            return
        if not self.can_restart():
            if not self.move_timer.isActive():
                self.waiting_to_move()
                self.move_timer.start()
            return
        self.move_pending = False
        self.move_timer.stop()
        self.restart()

    def restart(self) -> None:
        """End and start again (Windows: PowerShell waits for this process, then starts the same command line)."""
        if sys.platform == "win32":
            subprocess.Popen(restart_command(os.getpid(), own_command(), os.getcwd()),
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
        self.close()

    def set_wallpaper(self, on: bool) -> None:
        """The wallpaper on or off, for the whole suite (the next start of every app), and in this window at once."""
        self.wallpaper_on = on
        if self.suite:
            set_wallpaper_on(self.suite, on)
        glass(GLASS if self.shows_wallpaper() else 255)
        self.restyle()
        QWidget.update(self)

    def set_wallpaper_picture(self, path: Path | None) -> None:
        """*path* (None: the suite's own picture) as the suite's wallpaper, and in this window at once."""
        if self.suite:
            set_wallpaper_picture(self.suite, path)
        self.wallpaper = QPixmap(str(path if path is not None else WALLPAPER))
        QWidget.update(self)

    def set_wallpaper_veil(self, percent: int) -> None:
        """The wallpaper's transparency in % for the suite, and in this window at once."""
        if self.suite:
            set_wallpaper_veil(self.suite, percent)
        self.shade = shade(max(0, min(VEIL_MAX, percent)))
        QWidget.update(self)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """The wallpaper filling the window (cropped, never stretched), under the background at the transparency set
        (SHADE until one is) so the cards and the text stay easy to read."""
        if not self.shows_wallpaper():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        scaled = self.wallpaper.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                       Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap((self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2, scaled)
        veil = QColor(BACKGROUND)
        veil.setAlpha(self.shade)
        painter.fillRect(self.rect(), veil)

    def margins(self) -> tuple[int, int, int, int]:
        """The window's margins around header, page and legend: the mock-up's 32, 20, 32, 16."""
        return px(32), px(20), px(32), px(16)

    def bind(self, action: str, handler: Callable[[], None]) -> None:
        """What a controller button does on this page: x, y, previous, next, menu or view."""
        self.handlers[action] = handler

    def start_gamepad(self) -> bool:
        return self.gamepad.start()

    def focusables(self) -> list[QWidget]:
        """The cards and pills the focus can move to: only the popup's while one shows."""
        if self.popup is not None:
            return self.popup.pills()
        return [w for w in self.findChildren(QWidget) if isinstance(w, (Card, Pill, TextView)) and w.isVisible()
                and w.isEnabled() and w.focusPolicy() != Qt.FocusPolicy.NoFocus]

    def move_focus(self, direction: str) -> QWidget | None:
        """Give the focus to the nearest card or pill in *direction* from the focused one (or the first, when none
        has it); stays when there is none that way. Returns the one that has the focus. In a pane the focus stays in
        it (owner, 29-10-2026: the focus jumped back to the cards at the top or bottom of a list): only what is in
        the same pane is a candidate, and B goes back to the cards."""
        candidates = self.focusables()
        if not candidates:
            return None
        current = QGuiApplication.focusObject()
        if isinstance(current, TextView) and direction in ("up", "down") and current.scroll(direction):
            return current
        pane = _pane_of(current) if isinstance(current, QWidget) and not isinstance(current, Card) else None
        if pane is not None and self.popup is None:
            candidates = [w for w in candidates if _pane_of(w) is pane]
            if current not in candidates:              # a text field, an emptied list: stay, B leaves
                return current
        if current not in candidates:
            candidates[0].setFocus(Qt.FocusReason.OtherFocusReason)
            return candidates[0]
        best = nearest(current, candidates, direction)
        if best is not None:
            best.setFocus(Qt.FocusReason.OtherFocusReason)
            return best
        return current

    def accept(self) -> None:
        """A: the focused card or pill acts; elsewhere (a text field, a text view) the page's own A, bind("accept")."""
        focus = QGuiApplication.focusObject()
        if isinstance(focus, (Card, Pill)) and focus in self.focusables():
            focus.activated.emit()
        elif "accept" in self.handlers:
            self.handlers["accept"]()

    def restyle(self) -> None:
        """Every card and pane drawn again at glass()'s opacity, after it changed (a wallpaper switched on or off)."""
        for card in self.findChildren(Card):
            card._paint(card.hasFocus())
        for pane in self.findChildren(Pane):
            pane.restyle()

    def show_popup(self, title: str, text: str, back_to: QWidget | None = None,
                   content: QWidget | None = None, actions: Sequence[tuple[str, str]] = ()) -> InfoPopup:
        """*text* under *title* over the window (an InfoPill's); while it shows, A and B close it, the d-pad scrolls
        a long text and the other buttons do nothing. With *content*, its rows: the d-pad moves between them, A
        presses the one with the focus, B closes; the focus stays inside the popup. *actions*: the popup legend's
        entries before B Close."""
        if self.popup is not None:
            self.popup.dismiss()
        self.popup = InfoPopup(self, title, text, back_to, content, actions)
        self.popup.closed.connect(self._popup_closed)
        return self.popup

    def _popup_closed(self) -> None:
        self.popup = None

    def on_action(self, action: str) -> None:
        if not self.isActiveWindow():
            return
        self.act(action)

    def act(self, action: str) -> None:
        """*action* done, whoever asks: the controller (on_action, in the active window only) or a tap on the
        legend's entry for it."""
        if self.popup is not None:
            if action in ("back", "menu") or (action == "accept" and self.popup.content is None):
                self.popup.dismiss()
            elif action == "accept":
                self.accept()
            elif action in ("up", "down", "left", "right"):
                self.move_focus(action)
            return
        if action in ("up", "down", "left", "right"):
            self.move_focus(action)
        elif action == "accept":
            self.accept()
        elif action == "back":
            self.back.emit()
        elif action in self.handlers:
            self.handlers[action]()
        elif action == "view":
            self.exit_app()
        elif action == "menu":
            self.show_info()
        elif action == "keyboard":
            self.show_keyboard()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        keys = {Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down", Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right"}
        if event.key() in keys:
            self.move_focus(keys[event.key()])
        elif event.key() == Qt.Key.Key_Escape:
            if self.popup is not None:
                self.popup.dismiss()
            else:
                self.back.emit()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        if self.popup is not None:
            self.popup.setGeometry(self.rect())

    def event(self, event) -> bool:
        # The arrow keys move between the cards rather than through Qt's tab order.
        if event.type() == QEvent.Type.ShortcutOverride and isinstance(event, QKeyEvent) and \
                event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right):
            event.accept()
        return super().event(event)

    def closeEvent(self, event) -> None:
        self.gamepad.stop()
        super().closeEvent(event)


def _pane_of(widget: QWidget | None) -> Pane | None:
    """The Pane *widget* is in (itself included), None outside one; a popup's panel does not count."""
    while widget is not None and not isinstance(widget, Pane):
        widget = widget.parentWidget()
    return None if widget is None or widget.solid else widget


def _center(widget: QWidget) -> QPoint:
    return widget.mapToGlobal(widget.rect().center())


def nearest(current: QWidget, candidates: Sequence[QWidget], direction: str) -> QWidget | None:
    """The candidate nearest to *current* in *direction*: ahead of it, the distance along the direction counted
    once and the distance across it twice, so the d-pad goes straight before it goes sideways."""
    here = _center(current)
    best, best_cost = None, None
    for widget in candidates:
        if widget is current:
            continue
        there = _center(widget)
        dx, dy = there.x() - here.x(), there.y() - here.y()
        along, across = {"up": (-dy, dx), "down": (dy, dx), "left": (-dx, dy), "right": (dx, dy)}[direction]
        if along <= 0:
            continue
        cost = along + 2 * abs(across)
        if best_cost is None or cost < best_cost:
            best, best_cost = widget, cost
    return best
