# SPDX-License-Identifier: GPL-3.0-or-later
"""Reusable widgets: status pills, metric boxes, the logo, text dialogs and the rounded tooltip."""

from __future__ import annotations

import sys
from functools import lru_cache

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QFontDatabase, QMouseEvent, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from . import FONT_DIR, plain_tooltip, window_title

# The suite's theme and colors (a copy of core's theme.py): result colors, the logo's purple, the theme's accent.
from .theme import ACCENT, BLUE, GREEN, GREY, ORANGE, PURPLE, RED, STATE_COLORS, surface_style


@lru_cache(maxsize=1)
def header_font() -> str:
    """CSS font-family for the title and metric boxes. macOS uses SF Pro, which has a real heavy weight;
    elsewhere the bundled Inter (SIL OFL) gives the same look instead of a thinner fallback."""
    if sys.platform == "darwin":
        return ""
    families: set[str] = set()
    for ttf in sorted(FONT_DIR.glob("Inter-*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(ttf))
        if font_id >= 0:
            families.update(QFontDatabase.applicationFontFamilies(font_id))
    return "font-family:'Inter';" if "Inter" in families else ""


class StatusPill(QLabel):
    """A short state word on the theme's surface, its state as a colored left edge: Active, Not mounted, ...
    Neutral has no color."""

    def __init__(self, text: str | None = None, parent: QWidget | None = None):
        super().__init__(text or "", parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(110)
        self.set_status(text if text is not None else "Unknown", "neutral")

    def set_status(self, text: str, kind: str, tooltip: str = "") -> None:
        self.setText(text)
        self.setToolTip(tooltip)
        colour = STATE_COLORS.get(kind) if kind != "neutral" else None
        self.setStyleSheet(surface_style(colour, "QLabel", 6)      # padding 3px 10px inside the border
                           + "QLabel { font-weight:600; padding:2px 9px 2px 6px; }")


class MetricBox(QFrame):
    """One box of the header row: a big value with a caption, centered like the stats boxes of bc250-bazzite-test
    (centered=False: left-aligned)."""

    def __init__(self, caption: str, colour: str = GREY, parent: QWidget | None = None, centred: bool = True):
        super().__init__(parent)
        self.set_colour(colour)
        self.setMinimumWidth(120)
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

    def set_colour(self, colour: str) -> None:
        """The box's state or category color, its left edge; GRAY (neutral) has none."""
        self.setStyleSheet(surface_style(None if colour == GREY else colour)
                           + "QLabel { background:transparent; border:none; }")


class ClickableLogo(QLabel):
    clicked = pyqtSignal()

    def __init__(self, path: str, size: int, parent: QWidget | None = None):
        super().__init__(parent)
        pix = QPixmap(path)
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
    """Read-only monospace output (systemctl status, journal, raw config)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

    def set_text(self, text: str) -> None:
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


def page_header(title: str) -> tuple[QHBoxLayout, QLabel]:
    header = QHBoxLayout()
    label = QLabel(title)
    label.setStyleSheet("font-size:20px; font-weight:700;")
    header.addWidget(label)
    header.addStretch(1)
    return header, label


def hint_label(text: str) -> QLabel:
    """Secondary, word-wrapped explanation text under a control."""
    label = QLabel(text)
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
        button.setStyleSheet("QPushButton { background:#8b0000; color:white; border:1px solid #8b0000; "
                             "border-radius:3px; }"
                             "QPushButton:hover { background:#a00000; border-color:#a00000; }")
    else:
        button.setStyleSheet("")


def accent_button(text: str, tooltip: str = "") -> QPushButton:
    """The page's main action, outlined in the accent color like the selected nav item."""
    button = QPushButton(text)
    button.setToolTip(tooltip)
    button.setMinimumHeight(36)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(f"QPushButton {{ border:2px solid {ACCENT}; border-radius:6px; padding:4px 16px; font-weight:700; }}"
                         f"QPushButton:disabled {{ border-color:palette(mid); color:palette(mid); }}")
    return button


class RoundedToolTip(QObject):
    """Every tooltip of the app with rounded corners and a thin border in the accent.

    Qt's own tooltip window cannot have transparent corners, so this shows a translucent frameless label
    instead. RoundedToolTip.install(app) filters the tooltip events of all widgets and item views."""

    MAX_WIDTH = 380
    _instance: RoundedToolTip | None = None
    _HIDE_ON = (QEvent.Type.MouseButtonPress, QEvent.Type.Wheel, QEvent.Type.KeyPress,
                QEvent.Type.WindowDeactivate)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.popup = QWidget(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        box = QVBoxLayout(self.popup)
        box.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setTextFormat(Qt.TextFormat.AutoText)
        self.label.setStyleSheet(
            f"QLabel {{ background:palette(window); color:palette(window-text); border:1px solid {ACCENT}; "
            "border-radius:6px; padding:6px 8px; }")
        box.addWidget(self.label)
        self._owner: QWidget | None = None
        self._area = QRect()
        self.destroyed.connect(self.popup.deleteLater)

    @classmethod
    def install(cls, app: QApplication) -> RoundedToolTip:
        tip = cls(app)
        app.installEventFilter(tip)
        # Off again when the app quits: the filter sees every event, also those of widgets destroyed after the
        # event loop has ended, when Python is tearing down (the Governor Manager crashed at exit on them, 15-10-2026).
        app.aboutToQuit.connect(lambda: app.removeEventFilter(tip))
        cls._instance = tip
        return tip

    def show_text(self, pos: QPoint, text: str, owner: QWidget | None = None, area: QRect | None = None) -> None:
        if not text or sip.isdeleted(self.popup):
            self.hide()
            return
        self._owner = owner
        self._area = area if area is not None else (owner.rect() if owner is not None else QRect())
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
        return obj.toolTip() or None, obj.rect()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        kind = event.type()
        if kind == QEvent.Type.ToolTip:
            if not isinstance(obj, QWidget):
                return False
            text, area = self._text_at(obj, event.pos())
            if text is None:
                return False
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
