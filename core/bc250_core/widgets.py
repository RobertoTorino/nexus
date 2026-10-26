# SPDX-License-Identifier: GPL-3.0-or-later
"""Reusable widgets: status pills, metric boxes, header pills, the logo, terminal, text dialogs and the rounded tooltip.

Merged from bc250-governor-manager and bc250-bazzite-helixsr-gui: the tooltip is helixsr's (Wayland-safe parent),
set_button_active() is governor's, show_tooltip()/hide_tooltip() are bazzite-test's."""

from __future__ import annotations

from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QFontDatabase, QMouseEvent, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QPlainTextEdit, QPushButton, QSizePolicy, QTabBar, QToolTip, QVBoxLayout, QWidget,
)

from .text import plain_tooltip, window_title
from .theme import (ACTIVE_RED, ACTIVE_RED_HOVER, BLUE, GREY, STATE_COLORS, THEME, Theme, header_font, muted,
                    surface_style)

# The theme the widgets draw with: the suite's chosen one (theme.py), unless an app sets its own with set_theme()
# (Nexus Releases: Nexus's design, not a suite's). create_app() sets the theme an app passes it.
_theme: Theme = THEME


def current_theme() -> Theme:
    return _theme


def set_theme(theme: Theme) -> None:
    global _theme
    _theme = theme


def accent() -> str:
    """The accent of the theme the widgets draw with: hover and focus outlines, the main action."""
    return _theme.accent


class StatusPill(QLabel):
    """A short state word on the theme's surface, its state as a colored left edge: Active, Not mounted, ...
    Neutral has no color."""

    def __init__(self, text: str = "", parent: QWidget | None = None):
        text = text or "Unknown"
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(110)
        self.set_status(text, "neutral")

    def set_status(self, text: str, kind: str, tooltip: str = "") -> None:
        self.setText(text)
        self.setToolTip(tooltip)
        colour = STATE_COLORS.get(kind) if kind != "neutral" else None
        self.setStyleSheet(surface_style(colour, "QLabel", 6, theme=_theme)      # padding 3px 10px inside the border
                           + "QLabel { font-weight:600; padding:2px 9px 2px 6px; }")


class StatusText(QWidget):
    """A state next to an app's title: a colored dot and the state in bold, in the color of its kind, the same
    set_status() as StatusPill. Lighter than a pill in a header; neutral uses the normal text color."""

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)
        self.dot = QLabel("●")
        self.label = QLabel()
        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        self.kind = ""
        self.set_status(text or "Unknown", "neutral")

    def set_status(self, text: str, kind: str, tooltip: str = "") -> None:
        self.kind = kind
        self.label.setText(text)
        self.setToolTip(tooltip)
        colour = STATE_COLORS.get(kind) if kind != "neutral" else None
        style = f"color:{colour};" if colour else "color:palette(window-text);"
        self.dot.setStyleSheet(style + "font-size:14px;")
        self.label.setStyleSheet(style + "font-weight:700; font-size:14px;")

    def text(self) -> str:
        return self.label.text()


class MetricBox(QFrame):
    """One box of a header row: a big value with a caption, centered like the stats boxes of bc250-bazzite-test
    (centered=False: left-aligned). On the theme's surface, *color* as its left edge (GRAY: none)."""

    MIN_WIDTH = 120

    def __init__(self, caption: str, colour: str = GREY, parent: QWidget | None = None, centred: bool = True):
        super().__init__(parent)
        self.peers: list[MetricBox] = []        # same_width(): the boxes this one keeps its width with
        self.set_colour(colour)
        self.setMinimumWidth(self.MIN_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 7, 11, 7)         # 12, 8, 12, 8 inside the border
        layout.setSpacing(0)
        self.value = QLabel("—")
        self.value.setStyleSheet(header_font() + "font-size:22px; font-weight:800;")
        self.caption = QLabel(caption)
        self.caption.setStyleSheet("font-size:12px; font-weight:600;")
        for label in (self.value, self.caption):
            if centred:
                label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            layout.addWidget(label)

    def set_value(self, text: str, tooltip: str = "") -> None:
        self.value.setText(text)
        self.setToolTip(tooltip)
        if self.peers:
            _even(self.peers)

    def set_colour(self, colour: str) -> None:
        """The box's state or category color, its left edge; GRAY (neutral) shows the suite's blue, as the portal's
        pills (owner, 26-10-2026)."""
        self.setStyleSheet(surface_style(BLUE if colour == GREY else colour, theme=_theme)
                           + "QLabel { background:transparent; border:none; }")


class Pill(MetricBox):
    """A header pill that is a button, as the apps' status boxes look: the value in large type, what it is under
    it; the accent edge under the mouse or the keyboard focus. A click, Enter or Space emits clicked."""

    clicked = pyqtSignal()

    def __init__(self, value: str, caption: str, tooltip: str = "", colour: str = GREY):
        super().__init__(caption, colour)
        self.setObjectName("pill")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)      # never cut off
        self.set_value(value, tooltip)

    def set_colour(self, colour: str) -> None:
        super().set_colour(colour)
        # A pill that cannot be clicked (setEnabled(False)) shows its text muted, as a disabled button does.
        # The rule is on the labels' own state: Qt ignores an ancestor's pseudo-state in a selector, so
        # "#pill:disabled QLabel" would mute every pill.
        self.setStyleSheet(self.styleSheet() + f"#pill:hover, #pill:focus {{ border-color:{accent()}; }}"
                           f"#pill QLabel:disabled {{ color:{muted(_theme)}; }}")

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)

    def click(self) -> None:
        self.clicked.emit()


def same_width(boxes: list[MetricBox]) -> None:
    """A row of boxes or pills all as wide as the widest, and again whenever a value changes."""
    for box in boxes:
        box.peers = boxes
        box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    _even(boxes)


def _even(boxes: list[MetricBox]) -> None:
    width = max([MetricBox.MIN_WIDTH, *(box.sizeHint().width() for box in boxes)])
    for box in boxes:
        box.setMinimumWidth(width)


class ClickableLogo(QLabel):
    clicked = pyqtSignal()

    def __init__(self, path: str | Path, size: int, parent: QWidget | None = None):
        super().__init__(parent)
        pix = QPixmap(str(path))
        if not pix.isNull():
            self.setPixmap(pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class Terminal(QPlainTextEdit):
    """Read-only monospace output (systemctl status, journal, raw config, script output)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

    def set_text(self, text: str) -> None:
        """Replace the text; stays scrolled to the end if it was there, so a growing log can be followed."""
        bar = self.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 2
        self.setPlainText(text)
        if at_end:
            bar.setValue(bar.maximum())


class TextDialog(QDialog):
    """A title, a block of monospace text and a Close button."""

    def __init__(self, title: str, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(window_title(title))
        self.resize(820, 520)
        layout = QVBoxLayout(self)
        self.terminal = Terminal()
        self.terminal.setPlainText(text)
        self.terminal.setToolTip(plain_tooltip(title))
        layout.addWidget(self.terminal, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class AppHeader(QHBoxLayout):
    """The first line of every app window: the app's icon at 96 px on the left, spanning the title row (the name
    with the version, then the app's states and, on the right, its actions) and a second row below it (status
    boxes or the app's main controls). Bazzite Test's and the Governor Manager's header, shared."""

    LOGO_PX = 96

    def __init__(self, logo: str | Path, name: str, version: str = ""):
        super().__init__()
        self.setSpacing(14)
        self.logo = ClickableLogo(logo, self.LOGO_PX)
        self.logo.setCursor(Qt.CursorShape.ArrowCursor)
        self.addWidget(self.logo)
        right = QVBoxLayout()
        right.setSpacing(6)
        version_text = f"  <span style='color:{muted(_theme)}; font-size:14px;'>v{version}</span>" if version else ""
        self.title = QLabel(f"{name}{version_text}")
        self.title.setStyleSheet(header_font() + "font-size:24px; font-weight:800;")
        self.title_row = QHBoxLayout()
        self.title_row.addWidget(self.title)
        self.title_row.addStretch(1)
        self._states = 0
        self.second_row = QHBoxLayout()
        self.second_row.setSpacing(8)
        right.addLayout(self.title_row)
        right.addLayout(self.second_row)
        self.addLayout(right, 1)

    def add_state(self, widget: QWidget) -> None:
        """Beside the title: a StatusText, a badge."""
        self._states += 1
        self.title_row.insertWidget(self._states, widget)

    def add_action(self, widget: QWidget) -> None:
        """At the right end of the title row: Refresh, Check again."""
        self.title_row.addWidget(widget)

    def add_second(self, item: QWidget | QHBoxLayout, stretch: int = 0) -> None:
        """Left to right on the second row."""
        if isinstance(item, QWidget):
            self.second_row.addWidget(item, stretch)
        else:
            self.second_row.addLayout(item, stretch)


def page_header(title: str) -> tuple[QHBoxLayout, QLabel]:
    header = QHBoxLayout()
    label = QLabel(title)
    label.setStyleSheet("font-size:20px; font-weight:700;")
    header.addWidget(label)
    header.addStretch(1)
    return header, label


class WrappedLabel(QLabel):
    """A word-wrapped label whose minimum height follows its width. A wrapped QLabel tells its layout a minimum of
    one line, whatever it wraps to, so a window at its minimum height takes the extra lines from the widget below
    with the stretch (owner, 24-10-2026: RPCS3 Manager's Settings tab, its Sound box squeezed unreadable under the
    three-line introduction). Here the minimum is the height the text needs at the label's width."""

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setWordWrap(True)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._follow()

    def setText(self, text: str) -> None:  # noqa: N802 (Qt override)
        super().setText(text)
        if self.width() > 0:
            self._follow()

    def _follow(self) -> None:
        self.setMinimumHeight(0)                # QLabel measures no lower than the minimum it has: let go first
        self.setMinimumHeight(max(0, self.heightForWidth(self.width())))


def hint_label(text: str, follow_height: bool = False) -> QLabel:
    """Secondary, word-wrapped explanation text under a control. *follow_height*: a WrappedLabel, whose minimum
    height follows its width, for a text above a widget that must not be squeezed."""
    label = WrappedLabel(text) if follow_height else QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color:palette(placeholder-text);")
    label.setOpenExternalLinks(True)
    return label


def set_button_active(button: QPushButton, active: bool) -> None:
    """Fill a plain toggle button red while the state it switches is on; otherwise leave it in the native look.
    The height is frozen at the native size hint on first use, so the red style cannot change the size."""
    if button.property("activeRed") is None:
        button.setFixedHeight(button.sizeHint().height())
    if button.property("activeRed") == active:
        return
    button.setProperty("activeRed", active)
    if active:
        # Setting the border makes the stylesheet paint the whole button, so the fill is solid instead of being
        # blended over the native gradient. No font change, so the text weight matches the neighbors.
        button.setStyleSheet(f"QPushButton {{ background:{ACTIVE_RED}; color:white; border:1px solid {ACTIVE_RED}; "
                             "border-radius:3px; }"
                             f"QPushButton:hover {{ background:{ACTIVE_RED_HOVER}; border-color:{ACTIVE_RED_HOVER}; }}")
    else:
        button.setStyleSheet("")


def accent_button(text: str, tooltip: str = "") -> QPushButton:
    """The page's main action, outlined in the accent color like the selected nav item."""
    button = QPushButton(text)
    button.setToolTip(tooltip)
    button.setMinimumHeight(36)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(f"QPushButton {{ border:2px solid {accent()}; border-radius:6px; padding:4px 16px; font-weight:700; }}"
                         f"QPushButton:disabled {{ border-color:palette(mid); color:palette(mid); }}")
    return button


class RoundedToolTip(QObject):
    """Every tooltip of the app with rounded corners and a thin border in the accent.

    Qt's own tooltip window cannot have transparent corners, so this shows a translucent frameless label
    instead. RoundedToolTip.install(app) filters the tooltip events of all widgets, list/table items, header
    sections and tabs; show_tooltip()/hide_tooltip() are for tooltips shown by hand (chart hovers)."""

    MAX_WIDTH = 380
    _instance: RoundedToolTip | None = None
    _HIDE_ON = (QEvent.Type.MouseButtonPress, QEvent.Type.Wheel, QEvent.Type.KeyPress,
                QEvent.Type.WindowDeactivate)
    _FLAGS = Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._owner: QWidget | None = None      # the widget the tooltip belongs to
        self._area = QRect()                    # where in the owner the text applies (an item, a section)
        self._build_popup(None)

    def _build_popup(self, top: QWidget | None) -> None:
        # Wayland can only map a popup relative to a parent surface, so the popup is a child of the hovered
        # widget's window (Qt's own QToolTip does the same); the window flags keep it a top-level window.
        # A translucent window paints no style sheet of its own, so the styled label sits inside one.
        self.popup = QWidget(top, self._FLAGS)
        self.popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        box = QVBoxLayout(self.popup)
        box.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setTextFormat(Qt.TextFormat.AutoText)
        self.label.setStyleSheet(
            f"QLabel {{ background:palette(window); color:palette(window-text); border:1px solid {accent()}; "
            "border-radius:6px; padding:6px 8px; }")
        box.addWidget(self.label)
        self.destroyed.connect(self.popup.deleteLater)

    @classmethod
    def install(cls, app: QApplication) -> RoundedToolTip:
        tip = cls(app)
        app.installEventFilter(tip)
        # Off again when the app quits: the filter sees every event, also those of widgets and sockets that are
        # destroyed after the event loop has ended, when Python is tearing down (Bazzite NetcatGUI crashed at
        # exit on them, 15-10-2026).
        app.aboutToQuit.connect(lambda: app.removeEventFilter(tip))
        cls._instance = tip
        return tip

    def show_text(self, pos: QPoint, text: str, owner: QWidget | None = None, area: QRect | None = None) -> None:
        if not text:
            self.hide()
            return
        self._owner = owner
        self._area = area if area is not None else (owner.rect() if owner is not None else QRect())
        top = owner.window() if owner is not None else None
        if sip.isdeleted(self.popup):                       # died with the window it was last shown over
            self._build_popup(top)
        elif top is not self.popup.parentWidget():
            self.popup.setParent(top, self._FLAGS)
            self.popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.label.setText(text)
        self.label.setWordWrap(False)
        self.label.setMinimumWidth(0)
        self.label.setMaximumWidth(16777215)
        if self.label.sizeHint().width() > self.MAX_WIDTH:
            self.label.setWordWrap(True)
            self.label.setFixedWidth(self.MAX_WIDTH)
        self.label.adjustSize()
        self.popup.adjustSize()
        pos = pos + QPoint(12, 16)
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            pos.setX(max(geo.left(), min(pos.x(), geo.right() - self.popup.width())))
            pos.setY(max(geo.top(), min(pos.y(), geo.bottom() - self.popup.height())))
        self.popup.move(pos)
        self.popup.show()
        self.popup.raise_()

    def hide(self) -> None:
        self._owner = None
        if not sip.isdeleted(self.popup) and self.popup.isVisible():
            self.popup.hide()

    @staticmethod
    def _text_at(obj: QWidget, pos: QPoint) -> tuple[str | None, QRect]:
        """Tooltip text at pos in obj and the area it applies to; None when obj has no tooltip handling."""
        view = obj.parent()
        if isinstance(view, QAbstractItemView) and obj is view.viewport():
            if isinstance(view, QHeaderView):
                section = view.logicalIndexAt(pos)
                model = view.model()
                if section < 0 or model is None:
                    return "", QRect()
                text = model.headerData(section, view.orientation(), Qt.ItemDataRole.ToolTipRole)
                start, size = view.sectionViewportPosition(section), view.sectionSize(section)
                area = (QRect(start, 0, size, obj.height()) if view.orientation() == Qt.Orientation.Horizontal
                        else QRect(0, start, obj.width(), size))
                return str(text or ""), area
            index = view.indexAt(pos)
            if not index.isValid():
                return "", QRect()
            return str(index.data(Qt.ItemDataRole.ToolTipRole) or ""), view.visualRect(index)
        if isinstance(obj, QTabBar):                    # a tab's own tooltip (setTabToolTip), not the bar's
            index = obj.tabAt(pos)
            if index < 0:
                return obj.toolTip() or None, obj.rect()
            return obj.tabToolTip(index) or obj.toolTip() or "", obj.tabRect(index)
        return obj.toolTip() or None, obj.rect()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        kind = event.type()
        if kind == QEvent.Type.ToolTip:
            if not isinstance(obj, QWidget):
                return False
            text, area = self._text_at(obj, event.pos())
            if text is None:
                return False            # nothing here: Qt passes the event on to the parent widget
            self.show_text(event.globalPos(), text, obj, area)
            return True
        if self._owner is not None or (not sip.isdeleted(self.popup) and self.popup.isVisible()):
            if kind in self._HIDE_ON:
                self.hide()
            elif obj is self._owner:
                if kind in (QEvent.Type.Leave, QEvent.Type.Hide):
                    self.hide()
                elif kind in (QEvent.Type.MouseMove, QEvent.Type.HoverMove) and not self._area.contains(event.position().toPoint()):
                    self.hide()
        return False


def show_tooltip(pos: QPoint, text: str, owner: QWidget | None = None) -> None:
    """Show a tooltip by hand (chart hovers), in the app's style when RoundedToolTip is installed."""
    tip = RoundedToolTip._instance
    if tip is not None:
        tip.show_text(pos, text, owner)
    else:
        QToolTip.showText(pos, text)


def hide_tooltip() -> None:
    tip = RoundedToolTip._instance
    if tip is not None:
        tip.hide()
    else:
        QToolTip.hideText()
