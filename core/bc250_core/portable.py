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
from pathlib import Path
from collections.abc import Callable, Sequence

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QKeyEvent, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QHBoxLayout,
                             QLabel, QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from . import appinfo
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
FONT = "Inter"

_scale = 1.0
_pinned = False                         # pin_scale(): the windows keep the scale given
MIN_SCALE = 0.6                         # text smaller than this is too small to read in the hands
_glass = 255                            # the cards' and panes' opacity: glass()
# The wallpaper behind every window of the suite (owner, 28-10-2026: the portal's first; 29-10-2026: "available
# throughout the suite"), on or off for the whole suite in the portal's Settings: <suite>\suite.ini, look/wallpaper
WALLPAPER = Path(__file__).resolve().parent / "images" / "wallpaper.webp"
SHADE = 150                             # of 255: how much of the background lies over the wallpaper
GLASS = 200                             # of 255: the cards' and panes' opacity over it, so it shines through
LOOK_KEY = "look/wallpaper"
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
    """Whether the suite's apps show the wallpaper: on unless switched off in the portal's Settings."""
    return str(look_settings(suite).value(LOOK_KEY, "true")).lower() != "false"


def set_wallpaper_on(suite: str, on: bool) -> None:
    settings = look_settings(suite)
    settings.setValue(LOOK_KEY, "true" if on else "false")
    settings.sync()


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

    def set_status(self, parts: Sequence[str], second: Sequence[str] = ()) -> None:
        """The status line's *parts* joined by bars; *second* on a line of its own under it (owner, 28-10-2026: the
        test app's temperatures under the battery, the date and the time)."""
        self.status.setText("  |  ".join(part for part in parts if part))
        below = "  |  ".join(part for part in second if part)
        self.second.setText(below)
        self.second.setVisible(bool(below))


DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def status_clock(now: datetime.datetime | None = None) -> list[str]:
    """The date and the time for the header's status line, after the battery: "Monday 27/10/2026", "17:04" (owner,
    28-10-2026). The day's name is English whatever Windows' language, as the apps' text is."""
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
        self._paint(False)

    def set_text(self, text: str, color: str = DIM) -> None:
        """The line under the title, in *color* (amber for an update on a tile)."""
        self.text.setText(text)
        self.text.setStyleSheet(f"color: {color}; background: transparent;")

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


class Pane(QFrame):
    """The detail pane: a card's surface without the focus, for what the focused card is and does (the test app's
    right side, the portal's strip under the tiles). *column* is its layout."""

    def __init__(self, parent: QWidget | None = None, solid: bool = False):
        super().__init__(parent)
        self.setObjectName("pane")
        self.solid = solid                              # never see-through (an InfoPopup's panel)
        self.active = False                             # the focus is inside it: the focused card's edge and glow
        self.restyle()
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(px(24), px(22), px(24), px(22))

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
    opens a popup with the rest, text or controls (owner, 29-10-2026). Focused, it is dimmed like every pill."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("", parent=parent)
        self.label.hide()
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.setMinimumSize(px(32), px(32))
        self.setFixedSize(px(32), px(32))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        line = max(2.0, side / 14)
        ring = QRectF(line / 2, line / 2, side - line, side - line)
        painter.setPen(QPen(QColor(TEXT), line))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(ring)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(TEXT))
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
        window = self.window()
        if isinstance(window, PortableWindow):
            window.show_popup(self.title, self.info, self)


class InfoPopup(QWidget):
    """The window darkened, with a panel in the middle: a title, the text and a Close pill. A, B, Escape or a tap
    beside the panel closes it, and the focus goes back to where it came from. With *content* (a widget with pills,
    owner 29-10-2026: a popup holds the controls that do not fit a pane) it shows under the text, the d-pad moves
    between its pills and A presses one; B, Escape, Close or a tap beside it still closes it."""

    closed = pyqtSignal()

    def __init__(self, window: QWidget, title: str, text: str, back_to: QWidget | None = None,
                 content: QWidget | None = None):
        super().__init__(window)
        self.back_to, self.content = back_to, content
        self.setGeometry(window.rect())
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.panel = Pane(solid=True)
        self.panel.setFixedWidth(px(640))
        inner = px(640 - 48)                            # the pane's margins: a wrapped label needs its width to be tall
        heading = text_label(title, 24, QFont.Weight.ExtraBold, wrap=True)
        heading.setFixedWidth(inner)
        self.panel.column.addWidget(heading)
        self.panel.column.addSpacing(px(8))
        self.text = text_label(text, BODY + 1, wrap=True)
        self.text.setFixedWidth(inner)
        self.panel.column.addWidget(self.text)
        self.panel.column.addSpacing(px(16))
        if content is not None:
            content.setFixedWidth(inner)
            self.panel.column.addWidget(content)
            self.panel.column.addSpacing(px(16))
        self.close_pill = Pill("Close", "B", main=True)
        self.close_pill.activated.connect(self.dismiss)
        self.panel.column.addLayout(pill_row(self.close_pill))
        outer.addWidget(self.panel)
        self.show()
        self.raise_()
        first = content.findChildren(Pill)[0] if content is not None and content.findChildren(Pill) else None
        (first or self.close_pill).setFocus(Qt.FocusReason.OtherFocusReason)

    def pills(self) -> list[Pill]:
        return [pill for pill in self.findChildren(Pill) if pill.isVisible() and pill.isEnabled()]

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
        screen = QGuiApplication.primaryScreen()
        if screen is not None and not _pinned:          # the whole screen: the apps run full screen, over the taskbar
            size = screen.geometry().size()
            scale((size.width(), size.height()))
        self.setObjectName("portable")
        self.setStyleSheet(f"QWidget#portable {{ background: {BACKGROUND}; }}")
        self.setAutoFillBackground(True)
        self.handlers: dict[str, Callable[[], None]] = {}
        self.gamepad = gamepad if gamepad is not None else Gamepad(self)
        self.gamepad.action.connect(self.on_action)
        self.popup: InfoPopup | None = None
        info = appinfo.current()
        self.suite = suite or (info.settings_org if info is not None else "") or ""
        self.wallpaper = QPixmap(str(wallpaper)) if wallpaper is not None else QPixmap()
        self.wallpaper_on = bool(self.suite) and wallpaper_on(self.suite)
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

    def shows_wallpaper(self) -> bool:
        return self.wallpaper_on and not self.wallpaper.isNull()

    def set_wallpaper(self, on: bool) -> None:
        """The wallpaper on or off, for the whole suite (the next start of every app), and in this window at once."""
        self.wallpaper_on = on
        if self.suite:
            set_wallpaper_on(self.suite, on)
        glass(GLASS if self.shows_wallpaper() else 255)
        self.restyle()
        QWidget.update(self)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """The wallpaper filling the window (cropped, never stretched), under the background at SHADE so the cards
        and the text stay easy to read."""
        if not self.shows_wallpaper():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        scaled = self.wallpaper.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                       Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap((self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2, scaled)
        shade = QColor(BACKGROUND)
        shade.setAlpha(SHADE)
        painter.fillRect(self.rect(), shade)

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

    def restyle(self) -> None:
        """Every card and pane drawn again at glass()'s opacity, after it changed (a wallpaper switched on or off)."""
        for card in self.findChildren(Card):
            card._paint(card.hasFocus())
        for pane in self.findChildren(Pane):
            pane.restyle()

    def show_popup(self, title: str, text: str, back_to: QWidget | None = None,
                   content: QWidget | None = None) -> InfoPopup:
        """*text* under *title* over the window (an InfoPill's); while it shows, A and B close it and the other
        buttons do nothing. With *content*, its pills: the d-pad moves between them and Close, A presses the one
        with the focus, B closes; the focus stays inside the popup."""
        if self.popup is not None:
            self.popup.dismiss()
        self.popup = InfoPopup(self, title, text, back_to, content)
        self.popup.closed.connect(self._popup_closed)
        return self.popup

    def _popup_closed(self) -> None:
        self.popup = None

    def on_action(self, action: str) -> None:
        if not self.isActiveWindow():
            return
        if self.popup is not None:
            if action == "back" or (action == "accept" and self.popup.content is None):
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
