# SPDX-License-Identifier: GPL-3.0-or-later
"""The portable window: the Windows Portable Suite's design and the widgets its apps are built of (owner,
26-10-2026: direction D, B's amber on C's cards; a small screen held in the hands, used by touch and a controller,
often without a keyboard).

The design: a near-black window, cards a step lighter, one amber for focus and the main action (PORTABLE, a theme for
core's widgets, set with create_app(theme=PORTABLE)). The focused card is raised, with an amber edge and an amber
glow under it. Sizes are the mock-up's at 1280 x 720 and scale with the screen (scale()), read from the device
rather than assumed: the Ally's own screen at 150 % is 1280 x 720, a TV at 125 % is 1536 x 864.

The widgets: PortableHeader (icon, title, version, a status line), Card (a focusable card with a title and a line of
text), Pane (the detail pane), Pill (a big button that shows its controller button: A Open, Y Update), Legend (the
buttons that have no pill: X Details, B Back) and PortableWindow, which moves the focus between the cards and pills
with the d-pad, the left stick or the arrow keys, and turns A or Enter into the focused card's or pill's action, B or
Escape into back."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PyQt6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QKeyEvent, QPainter, QPixmap
from PyQt6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                             QPushButton, QSizePolicy, QVBoxLayout, QWidget)

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

PORTABLE = Theme("Portable", True, window=BACKGROUND, base=SURFACE, alt=RAISED, text=TEXT, button=RAISED,
                 button_low=SURFACE, edge=EDGE, accent=AMBER, accent_text=ON_AMBER)

BASE_WIDTH, BASE_HEIGHT = 1280, 720     # the mock-up's logical screen: every size below is at this one
RADIUS = 14
TITLE, SUBTITLE, TAB, CARD, BODY, PILL, GLYPH, LEGEND, STATUS = 28, 15, 19, 20, 13, 15, 10, 12, 18   # pt
GLOW_BLUR, GLOW_OFFSET = 36, 8
DIMMED = 0.6                            # a focused pill, drawn at this opacity
FONT = "Inter"

_scale = 1.0
_fonts_loaded = False


def scale(screen_size: tuple[int, int] | None = None) -> float:
    """How much larger than the mock-up everything is drawn: the screen's logical size against 1280 x 720 (the
    smaller ratio, so the layout fits), at least 1. Set for the app when called with a size; read otherwise."""
    global _scale
    if screen_size is not None:
        width, height = screen_size
        _scale = max(1.0, min(width / BASE_WIDTH, height / BASE_HEIGHT))
    return _scale


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


class Glyph(QLabel):
    """A controller button as the legend and the pills show it: its letter in a circle, amber for the main one."""

    def __init__(self, button: str, filled: bool = False, parent: QWidget | None = None):
        super().__init__(button, parent)
        self.setFont(font(GLYPH, QFont.Weight.Bold))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(px(30 if len(button) == 1 else 40), px(26))
        self.setStyleSheet(f"color: {ON_AMBER if filled else TEXT}; background: {AMBER if filled else RAISED};"
                           f" border-radius: {px(13)}px;")


class Legend(QWidget):
    """The line at the bottom: the controller buttons the page answers to that have no pill of their own."""

    def __init__(self, items: Sequence[tuple[str, str]] = (), parent: QWidget | None = None):
        super().__init__(parent)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.set_items(items)

    def set_items(self, items: Sequence[tuple[str, str]]) -> None:
        while self.row.count():
            item = self.row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()                           # gone now, not when Qt deletes it later
                widget.deleteLater()
        self.row.addStretch()
        for button, text in items:                       # the amber one, A, is on the page's main pill
            self.row.addWidget(Glyph(button))
            self.row.addWidget(text_label(text, LEGEND, QFont.Weight.DemiBold))
            self.row.addSpacing(px(18))
        self.items = list(items)


class PortableHeader(QWidget):
    """The app's icon, its name large with the version under it, and a status line on the right (battery, time)."""

    def __init__(self, title: str, version: str, icon: QPixmap | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.icon = QLabel()
        self.icon.setFixedSize(px(60), px(60))
        if icon is not None and not icon.isNull():
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
        self.status = text_label("", STATUS, QFont.Weight.Bold)      # owner, 26-10-2026: 13 pt dimmed was too small
        row.addWidget(self.status, 0, Qt.AlignmentFlag.AlignTop)       # level with the top of the title (owner)

    def set_status(self, parts: Sequence[str]) -> None:
        self.status.setText("  |  ".join(part for part in parts if part))


class Card(QFrame):
    """A card with a title and a line of text, focusable: raised with an amber edge and glow while it has the
    focus. A tap or a click gives it the focus (focused); A, Enter or a second tap acts (activated)."""

    focused = pyqtSignal()
    activated = pyqtSignal()

    def __init__(self, title: str, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        column = QVBoxLayout(self)
        column.setContentsMargins(px(20), px(12), px(20), px(12))
        self.title = text_label(title, CARD, QFont.Weight.Bold)
        self.text = text_label(text, BODY, color=DIM, wrap=True)
        column.addWidget(self.title)
        column.addWidget(self.text)
        self._paint(False)

    def _paint(self, focus: bool) -> None:
        edge = f"{px(2)}px solid {AMBER}" if focus else f"{px(2)}px solid transparent"
        self.setStyleSheet(f"QFrame#card {{ background: {RAISED if focus else SURFACE}; border: {edge};"
                           f" border-radius: {px(RADIUS)}px; }}")
        lift(self, focus)

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


class Pane(QFrame):
    """The detail pane: a card's surface without the focus, for what the focused card is and does (the test app's
    right side, the portal's strip under the tiles). *column* is its layout."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("pane")
        self.setStyleSheet(f"QFrame#pane {{ background: {SURFACE}; border-radius: {px(RADIUS)}px; }}")
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(px(24), px(22), px(24), px(22))


class Pill(QPushButton):
    """A big button with the cards' corners that shows its controller button: amber for the page's main action (A),
    a raised gray for the others (Y Update). The focus dims it (owner, 26-10-2026: a ring or a glow on the amber was
    too much or too little). Its button press is the window's: PortableWindow.bind()."""

    activated = pyqtSignal()

    def __init__(self, text: str, button: str = "", main: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.button, self.main = button, main
        row = QHBoxLayout(self)
        row.setContentsMargins(px(10), 0, px(20), 0)
        row.setSpacing(px(10))
        if button:
            self.glyph = Glyph(button, filled=False)
            self.glyph.setStyleSheet(f"color: {AMBER if main else TEXT};"
                                     f" background: {ON_AMBER if main else BACKGROUND}; border-radius: {px(13)}px;")
            row.addWidget(self.glyph)
        self.label = text_label(text, PILL, QFont.Weight.Bold, ON_AMBER if main else TEXT)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.label, 1)
        self.setMinimumSize(px(150), px(48))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.clicked.connect(self.activated.emit)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(AMBER if self.main else RAISED))
        painter.drawRoundedRect(QRectF(self.rect()), px(RADIUS), px(RADIUS))

    def sizeHint(self) -> QSize:
        # QPushButton measures its own text, which is empty: the glyph and the label are in the layout.
        return self.layout().sizeHint().expandedTo(self.minimumSize())

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        dim = QGraphicsOpacityEffect(self)               # the pill with its glyph and label
        dim.setOpacity(DIMMED)
        self.setGraphicsEffect(dim)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.setGraphicsEffect(None)

    def set_text(self, text: str) -> None:
        self.label.setText(text)


class PortableWindow(QWidget):
    """The portable app's window: the design, the controller and the keyboard. Moves the focus between the visible
    cards and pills (the nearest one in the direction pressed), turns A or Enter into the focused one's action,
    B or Escape into back(), and a page's own buttons (X, Y, LB, RB, Start) into the handlers bound with bind().
    The controller only counts while the window is active, so a game's input never moves it."""

    back = pyqtSignal()

    def __init__(self, gamepad: Gamepad | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        global _fonts_loaded
        if not _fonts_loaded:                           # Inter, bundled with core, once per app
            load_fonts()
            _fonts_loaded = True
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            size = screen.availableGeometry().size()
            scale((size.width(), size.height()))
        self.setObjectName("portable")
        self.setStyleSheet(f"QWidget#portable {{ background: {BACKGROUND}; }}")
        self.setAutoFillBackground(True)
        self.handlers: dict[str, Callable[[], None]] = {}
        self.gamepad = gamepad if gamepad is not None else Gamepad(self)
        self.gamepad.action.connect(self.on_action)

    def margins(self) -> tuple[int, int, int, int]:
        """The window's margins around header, page and legend: the mock-up's 32, 20, 32, 16."""
        return px(32), px(20), px(32), px(16)

    def bind(self, action: str, handler: Callable[[], None]) -> None:
        """What a controller button does on this page: x, y, previous, next, menu or view."""
        self.handlers[action] = handler

    def start_gamepad(self) -> bool:
        return self.gamepad.start()

    def focusables(self) -> list[QWidget]:
        return [w for w in self.findChildren(QWidget) if isinstance(w, (Card, Pill)) and w.isVisible()
                and w.isEnabled()]

    def move_focus(self, direction: str) -> QWidget | None:
        """Give the focus to the nearest card or pill in *direction* from the focused one (or the first, when none
        has it); stays when there is none that way. Returns the one that has the focus."""
        candidates = self.focusables()
        if not candidates:
            return None
        current = QGuiApplication.focusObject()
        if current not in candidates:
            candidates[0].setFocus(Qt.FocusReason.OtherFocusReason)
            return candidates[0]
        best = nearest(current, candidates, direction)
        if best is not None:
            best.setFocus(Qt.FocusReason.OtherFocusReason)
            return best
        return current

    def accept(self) -> None:
        focus = QGuiApplication.focusObject()
        if isinstance(focus, (Card, Pill)) and focus in self.focusables():
            focus.activated.emit()

    def on_action(self, action: str) -> None:
        if not self.isActiveWindow():
            return
        if action in ("up", "down", "left", "right"):
            self.move_focus(action)
        elif action == "accept":
            self.accept()
        elif action == "back":
            self.back.emit()
        elif action in self.handlers:
            self.handlers[action]()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        keys = {Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down", Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right"}
        if event.key() in keys:
            self.move_focus(keys[event.key()])
        elif event.key() == Qt.Key.Key_Escape:
            self.back.emit()
        else:
            super().keyPressEvent(event)

    def event(self, event) -> bool:
        # The arrow keys move between the cards rather than through Qt's tab order.
        if event.type() == QEvent.Type.ShortcutOverride and isinstance(event, QKeyEvent) and \
                event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right):
            event.accept()
        return super().event(event)

    def closeEvent(self, event) -> None:
        self.gamepad.stop()
        super().closeEvent(event)


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
