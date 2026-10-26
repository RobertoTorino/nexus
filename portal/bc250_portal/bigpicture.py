# SPDX-License-Identifier: GPL-3.0-or-later
"""Suite Big Picture Mode: the portal for a TV and a controller (owner, 21-10-2026), as Steam's Big Picture is for
Steam. Fullscreen, large icons and type, a category strip, and a focus that moves with the arrow keys, a controller's
d-pad or its stick (gamepad.py). Suite Desktop Mode is the portal's window as it always was; a pill switches between
the two, and the portal remembers the last one.

A short animated intro (Intro) plays when the mode opens, with its sound; any key, click or button skips it."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QEvent, QPointF, QRect, QRectF, QSize, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen, QPixmap, QRadialGradient
from PyQt6.QtWidgets import (
    QAbstractButton, QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QScroller, QStackedWidget, QTabBar,
    QSizePolicy, QVBoxLayout, QWidget,
)

from bc250_core.theme import ACCENT, ORANGE, RED, header_font, muted

from . import APP_ICONS, CATEGORY_ICONS, INTRO_LOGO, LOGO_PATH, glyphs
from .looks import Backdrop, greyed

NAME = "Suite Big Picture Mode"
DESKTOP_NAME = "Suite Desktop Mode"
TILE_W, TILE_H = 244, 316
ICON_PX = 184
GAP = 20
MARGIN = 48
FULL_HEIGHT = 1000             # a window this high or higher is drawn at full size, a lower one smaller
SMALLEST = 0.68                 # 1280 x 720, the screen of a handheld, is about this
INTRO_MS = 2000
LOGO_SHARE = 0.26               # the intro's icon: this part of the screen's shorter side
# What each category is for, short enough for the line under the title on a handheld's screen.
SHORT_HINTS = {
    "sustainable": "Test, tune, unlock and cool the board.",
    "graphics": "Upscaling, async compute and mesh shaders.",
    "gaming": "Emulators, Remote Play, Game Mode plugins.",
    "utilities": "Overlay, BIOS, Wi-Fi, HDMI-CEC, file transfer.",
    "development": "Tools for working on the suite.",
}
KEYS = {Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down", Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right"}


def next_in_direction(current: QRect, others: list[QRect], direction: str) -> int | None:
    """The index of the rectangle nearest *current* in *direction* (up, down, left, right), None when nothing lies
    that way. A tile in line counts more than one off to the side."""
    best, best_cost = None, 0.0
    cx, cy = current.center().x(), current.center().y()
    for i, rect in enumerate(others):
        dx, dy = rect.center().x() - cx, rect.center().y() - cy
        ahead, aside = {"right": (dx, dy), "left": (-dx, dy), "down": (dy, dx), "up": (-dy, dx)}[direction]
        if ahead <= 4:
            continue
        cost = ahead + 3 * abs(aside)
        if best is None or cost < best_cost:
            best, best_cost = i, cost
    return best


class ElidedLabel(QLabel):
    """A line of text that ends in … when it does not fit, instead of being cut off."""

    def __init__(self, text: str = ""):
        super().__init__()
        self.full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt override)
        self.full = text
        self.setToolTip(text)
        self.update()

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(self.palette().windowText().color())
        text = QFontMetrics(self.font()).elidedText(self.full, Qt.TextElideMode.ElideRight, self.width())
        painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), text)
        painter.end()


class BigTile(QAbstractButton):
    """One app: a large icon, its name, and its state under it. The focus is a bright frame around the whole tile."""

    navigate = pyqtSignal(str)

    def __init__(self, key: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.key = key
        self.name = key
        self.status = ""
        self.status_colour = muted()
        self.pixmap = QPixmap()
        self._shown: tuple[int, float, int] | None = None   # what the scaled copy was made for: side, ratio, picture
        self._scaled = QPixmap()
        self.scale = 1.0
        self.marker = ""                    # "update": a red dot on the icon; "reinstall": the red circular arrow
        self.setFixedSize(self.sizeHint())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def set_look(self, name: str, pixmap: QPixmap, status: str, colour: str, marker: str) -> None:
        self.name, self.pixmap, self.status, self.status_colour, self.marker = name, pixmap, status, colour, marker
        self.update()

    def _picture(self, side: int) -> QPixmap:
        """The icon at the tile's size in the screen's own pixels (a 4K TV at 200 % wants twice the pixels), scaled
        once from the large original, not on every paint: a 512 px icon drawn straight to 184 px would alias."""
        ratio = self.devicePixelRatioF()
        key = (side, ratio, self.pixmap.cacheKey())
        if key != self._shown:
            self._scaled = self.pixmap.scaled(round(side * ratio), round(side * ratio),
                                              Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation)
            self._scaled.setDevicePixelRatio(ratio)
            self._shown = key
        return self._scaled

    def set_scale(self, scale: float) -> None:
        self.scale = scale
        self.setFixedSize(self.sizeHint())
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        return QSize(round(TILE_W * self.scale), round(TILE_H * self.scale))

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.key() in KEYS:
            self.navigate.emit(KEYS[event.key()])
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().focusOutEvent(event)
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        s = self.scale
        width, height = self.width(), self.height()
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
                               | QPainter.RenderHint.TextAntialiasing)
        frame = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        focused = self.hasFocus()
        if focused or self.underMouse():
            fill = QColor(ACCENT)
            fill.setAlpha(60 if focused else 28)
            painter.setBrush(fill)
            painter.setPen(QPen(QColor(ACCENT), 4) if focused else Qt.PenStyle.NoPen)
            painter.drawRoundedRect(frame, 22 * s, 22 * s)
        side = round(ICON_PX * s)
        icon = QRect((width - side) // 2, round(18 * s), side, side)
        if not self.pixmap.isNull():
            painter.drawPixmap(icon.topLeft(), self._picture(side))
        dot = round(28 * s)
        painter.setPen(QPen(QColor("#1b1b1b"), 3))
        painter.setBrush(QColor(RED))
        if self.marker == "update":
            painter.drawEllipse(QRectF(icon.right() - dot - 2, icon.bottom() - dot - 2, dot, dot))
        elif self.marker == "reinstall":
            badge = round(36 * s)
            painter.drawEllipse(QRectF(icon.right() - badge - 2, icon.bottom() - badge - 2, badge, badge))
            glyph = badge - 12
            painter.drawPixmap(QRect(icon.right() - badge + 4, icon.bottom() - badge + 4, glyph, glyph),
                               glyphs.reinstall("white").pixmap(glyph, glyph))
        font = QFont(self.font())
        font.setPixelSize(max(15, round(22 * s)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(self.palette().buttonText().color())
        painter.drawText(QRect(10, icon.bottom() + round(12 * s), width - 20, round(56 * s)),
                         int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
                         self.name)
        if self.status:
            small = QFont(font)
            small.setPixelSize(max(12, round(15 * s)))
            painter.setFont(small)
            painter.setPen(QColor(self.status_colour))
            elided = QFontMetrics(small).elidedText(self.status, Qt.TextElideMode.ElideRight, width - 20)
            painter.drawText(QRect(10, height - round(38 * s), width - 20, round(24 * s)),
                             int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), elided)
        painter.end()


class BigPicture(Backdrop):
    """The Big Picture view: the header (the window's own pills move into it), the category strip, the tiles of the
    open category, and under them what the buttons do. It shows what the window's tiles know (sync); a tile opens
    its app by open_requested(entry)."""

    open_requested = pyqtSignal(object)         # an AppEntry

    def __init__(self, entries, categories: dict[str, str], hints: dict[str, str]):
        super().__init__()
        self.setAutoFillBackground(True)
        self.setMinimumSize(640, 360)               # the layout's own minimum is for a big screen: it scales down
        self.entries = {entry.key: entry for entry in entries}
        self.columns: dict[str, int] = {}                # per category: the columns its tiles are laid out in
        self.scale = 1.0
        self._art: dict[tuple[str, bool], QPixmap] = {}
        outer = self.outer = QVBoxLayout(self)
        self.banner = QLabel()                      # the orange line of a portal that runs from a checkout
        self.banner.setWordWrap(True)
        self.banner.hide()
        outer.addWidget(self.banner)

        top = QHBoxLayout()
        top.setSpacing(24)
        self.top = top
        self.logo = QLabel()
        self.logo_picture = QPixmap(str(LOGO_PATH))
        top.addWidget(self.logo)
        words = self.words = QVBoxLayout()
        words.setSpacing(2)
        self.title = QLabel(NAME)
        words.addWidget(self.title)
        self.hint = ElidedLabel()
        words.addWidget(self.hint)
        top.addLayout(words, 1)
        self.pills: list[QWidget] = []
        outer.addLayout(top)

        self.bar = QTabBar()
        self.bar.setDrawBase(False)
        self.bar.setExpanding(False)
        self.bar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        outer.addWidget(self.bar)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.categories: list[str] = []
        self.pages: dict[str, QScrollArea] = {}
        self.grids: dict[str, QGridLayout] = {}
        self.tiles: dict[str, BigTile] = {}
        for category, label in categories.items():
            keys = [entry.key for entry in entries if entry.category == category]
            if not keys:
                continue
            self.categories.append(category)
            content = QWidget()
            column = QVBoxLayout(content)
            column.setContentsMargins(4, 8, 4, 8)
            grid = QGridLayout()
            grid.setSpacing(GAP)
            grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            column.addLayout(grid)
            column.addStretch(1)
            page = QScrollArea()
            page.setWidgetResizable(True)
            page.setFrameShape(QFrame.Shape.NoFrame)
            page.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            page.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background:transparent; }")
            page.setWidget(content)
            # a touch screen swipes the page
            QScroller.grabGesture(page.viewport(), QScroller.ScrollerGestureType.TouchGesture)
            page.installEventFilter(self)               # reflow when the page itself gets its new width
            self.pages[category], self.grids[category] = page, grid
            self.stack.addWidget(page)
            self.bar.addTab(label)
            self.bar.setTabToolTip(self.bar.count() - 1, hints.get(category, ""))
            for key in keys:
                tile = BigTile(key)
                tile.navigate.connect(self.move_focus)
                tile.clicked.connect(lambda _=False, k=key: self.open_requested.emit(self.entries[k]))
                self.tiles[key] = tile
        self.hints = {category: SHORT_HINTS.get(category, text) for category, text in hints.items()}
        self.full_hints = hints
        self.bar.currentChanged.connect(self._category_changed)
        self.keys = QLabel("A / Enter  Open      B  Back      LB / RB  Category      Y / F11  " + DESKTOP_NAME)
        self.keys.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(self.keys)
        self._category_changed(0)
        self.set_scale(1.0)

    # ------------------------------------------------------------------------------------------------ state
    def set_banner(self, text: str) -> None:
        self.banner.setText(text)
        self.banner.setVisible(bool(text))

    def place_pills(self, box: QWidget, pills: list[QWidget]) -> None:
        """The window's row of pills (*box*, holding *pills*) goes under the title: the same pills as in Suite Desktop
        Mode, and the focus can reach them."""
        self.words.addWidget(box)
        self.pills = pills

    def release_pills(self, box: QWidget) -> None:
        self.words.removeWidget(box)
        self.pills = []

    def sync(self, cards: dict) -> None:
        """Show each app as its tile in the desktop window knows it: icon, name, state."""
        for key, tile in self.tiles.items():
            card = cards[key]
            entry = card.entry
            pixmap = self.art(entry.category, key, card.installed)
            marker = "update" if not card.dot.isHidden() else "reinstall" if not card.badge.isHidden() else ""
            status = card.status if card.status != "Installed" else ("changes the board" if entry.changes_board else "")
            colour = RED if card.status in ("Update", "Reinstall needed", "App not available") else \
                ORANGE if status == "changes the board" else muted()
            tile.set_look(card.title.text(), pixmap, status, colour, marker)
            tile.setToolTip(card.icon.toolTip())

    def art(self, category: str, key: str, installed: bool) -> QPixmap:
        """The app's picture, from its category's 512 px icon (else the app's own 256 px tile), gray when not
        installed; kept, as it is the same for every app of a category."""
        name = (category, installed)
        if name not in self._art:
            file = CATEGORY_ICONS / f"{category}.webp"
            if not file.is_file():
                file = APP_ICONS / f"{key}.webp"
            pixmap = QPixmap(str(file))
            self._art[name] = pixmap if installed or pixmap.isNull() else greyed(pixmap)
        return self._art[name]

    def _category_changed(self, index: int) -> None:
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
            self.hint.setText(self.hints.get(self.categories[index], ""))
            self.reflow()

    def current_page(self) -> QScrollArea | None:
        return self.stack.currentWidget()

    def current_tiles(self) -> list[BigTile]:
        if not self.categories:
            return []
        category = self.categories[self.bar.currentIndex()]
        return [self.tiles[e.key] for e in self.entries.values() if e.category == category]

    # --------------------------------------------------------------------------------------------- layout
    def set_scale(self, scale: float) -> None:
        """Everything at *scale* of its size for a 1080 p screen: a handheld's 1280 x 720 or 1280 x 800 shows the
        same view smaller, so a row of icons and a second row both fit."""
        self.scale = scale
        s = scale
        self.outer.setContentsMargins(round(MARGIN * s), round(28 * s), round(MARGIN * s), round(20 * s))
        self.outer.setSpacing(round(16 * s))
        self.top.setSpacing(round(24 * s))
        side = round(96 * s)
        if not self.logo_picture.isNull():
            self.logo.setPixmap(self.logo_picture.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation))
        self.banner.setStyleSheet(f"background:{ORANGE}; color:white; font-weight:700; padding:6px 10px;"
                                  f" font-size:{max(12, round(16 * s))}px;")
        self.title.setStyleSheet(header_font() + f"font-size:{round(44 * s)}px; font-weight:800;")
        self.hint.setStyleSheet(f"color:{muted()}; font-size:{max(13, round(18 * s))}px;")
        self.keys.setStyleSheet(f"color:{muted()}; font-size:{max(13, round(18 * s))}px; font-weight:600;")
        self.bar.setStyleSheet(
            f"QTabBar::tab {{ font-size:{max(15, round(24 * s))}px; font-weight:700;"
            f" padding:{round(10 * s)}px {round(26 * s)}px; margin-right:6px; background:transparent; border:none;"
            " border-bottom:4px solid transparent; }"
            f"QTabBar::tab:selected {{ border-bottom:4px solid {ACCENT}; }}"
            "QTabBar::tab:hover { background:rgba(128,128,128,40); }")
        for grid in self.grids.values():
            grid.setSpacing(round(GAP * s))
        for tile in self.tiles.values():
            tile.set_scale(s)
        self.columns.clear()
        self.reflow()

    def reflow(self) -> None:
        page = self.current_page()
        if page is None:
            return
        tile = round(TILE_W * self.scale)
        gap = round(GAP * self.scale)
        width = page.width() - page.verticalScrollBar().sizeHint().width() - 8
        columns = max(1, (width + gap) // (tile + gap))
        category = self.categories[self.bar.currentIndex()]
        grid = self.grids[category]
        if columns == self.columns.get(category) and grid.count():
            return
        self.columns[category] = columns
        while grid.count():
            grid.takeAt(0)
        for i, tile in enumerate(self.current_tiles()):
            grid.addWidget(tile, i // columns, i % columns)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 (Qt override)
        if event.type() == QEvent.Type.Resize and watched in self.pages.values():
            self.columns.clear()
            self.reflow()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        scale = round(max(SMALLEST, min(1.0, event.size().height() / FULL_HEIGHT)), 2)
        if scale != self.scale:
            self.set_scale(scale)
        else:
            self.columns.clear()
            self.reflow()

    # ------------------------------------------------------------------------------------------ navigation
    def focused_tile(self) -> BigTile | None:
        focus = self.window().focusWidget()
        return focus if isinstance(focus, BigTile) and focus in self.current_tiles() else None

    def focus_items(self) -> list[QWidget]:
        """What the focus can be on: the tiles of the open category and the header's pills."""
        pills = [p for p in self.pills if p.isVisibleTo(self) and p.isEnabled()
                and p.focusPolicy() != Qt.FocusPolicy.NoFocus]
        return [t for t in self.current_tiles() if t.isVisibleTo(self)] + pills

    def focused_item(self) -> QWidget | None:
        focus = self.window().focusWidget()
        return focus if focus in self.focus_items() else None

    def focus_first(self) -> None:
        tiles = self.current_tiles()
        if tiles:
            tiles[0].setFocus()

    def move_focus(self, direction: str) -> None:
        """Move the focus to the nearest tile or pill that way; with nothing focused, to the first tile."""
        current = self.focused_item()
        if current is None:
            self.focus_first()
            return
        others = [item for item in self.focus_items() if item is not current]
        pos = lambda w: QRect(w.mapTo(self, w.rect().topLeft()), w.size())  # noqa: E731
        found = next_in_direction(pos(current), [pos(item) for item in others], direction)
        if found is not None:
            others[found].setFocus()
            if isinstance(others[found], BigTile):
                self.current_page().ensureWidgetVisible(others[found], 0, 24)

    def change_category(self, step: int) -> None:
        if self.categories:
            self.bar.setCurrentIndex((self.bar.currentIndex() + step) % len(self.categories))
            self.focus_first()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        key = event.key()
        if key in KEYS:
            self.move_focus(KEYS[key])
        elif key in (Qt.Key.Key_PageUp, Qt.Key.Key_Q):
            self.change_category(-1)
        elif key in (Qt.Key.Key_PageDown, Qt.Key.Key_E):
            self.change_category(1)
        else:
            super().keyPressEvent(event)


class Intro(QWidget):
    """The intro of Suite Big Picture Mode, about two seconds, painted over the window: a light sweeps across a dark
    screen, rings open from the portal's icon, the name draws itself in wide letters and settles, and the screen
    clears to the mode. Any key, click or button skips it (skip(), also called by the gamepad)."""

    finished = pyqtSignal()
    skipped = pyqtSignal()                      # cut short: its sound stops too

    def __init__(self, parent: QWidget, duration: int = INTRO_MS):
        super().__init__(parent)
        self.progress = 0.0
        self.logo = QPixmap(str(INTRO_LOGO if INTRO_LOGO.is_file() else LOGO_PATH))
        self._logo_at: tuple[int, float] | None = None
        self._logo_scaled = QPixmap()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(duration)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.valueChanged.connect(self._step)
        self.animation.finished.connect(self._done)
        self.done = False

    def begin(self) -> None:
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()
        self.setFocus()
        self.animation.start()

    def skip(self) -> None:
        if not self.done:
            self.skipped.emit()
        self.animation.stop()
        self._done()

    def _step(self, value) -> None:
        self.progress = float(value)
        self.update()

    def _done(self) -> None:
        if self.done:
            return
        self.done = True
        self.hide()
        self.finished.emit()
        self.deleteLater()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.skip()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.skip()

    def _logo_for(self, full: int) -> QPixmap:
        """The icon scaled once to its largest size on this screen's own pixels: drawing the 1024 px picture straight
        to a few hundred pixels, 60 times a second, would alias."""
        ratio = self.devicePixelRatioF()
        if self._logo_at != (full, ratio):
            self._logo_scaled = self.logo.scaled(round(full * ratio), round(full * ratio),
                                                 Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation)
            self._logo_scaled.setDevicePixelRatio(ratio)
            self._logo_at = (full, ratio)
        return self._logo_scaled

    @staticmethod
    def _phase(p: float, start: float, end: float) -> float:
        return min(1.0, max(0.0, (p - start) / (end - start)))

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        p = self.progress
        w, h = self.width(), self.height()
        ease = QEasingCurve(QEasingCurve.Type.OutCubic)
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        backdrop = QColor("#04060c")
        backdrop.setAlphaF(min(1.0, p / 0.12) * (1 - self._phase(p, 0.86, 1.0)))
        painter.fillRect(self.rect(), backdrop)
        centre = QPointF(w / 2, h / 2 - h * 0.06)
        accent = QColor(ACCENT)

        # The grid of the floor, rushing toward the viewer.
        floor = self._phase(p, 0.05, 0.4) * (1 - self._phase(p, 0.8, 0.97))
        if floor > 0:
            horizon = centre.y() + h * 0.12
            line = QColor(accent)
            line.setAlphaF(0.35 * floor)
            painter.setPen(QPen(line, 1.5))
            for i in range(-12, 13):
                painter.drawLine(QPointF(w / 2 + i * w * 0.02, horizon), QPointF(w / 2 + i * w * 0.14, h))
            slide = (p * 3.0) % 1.0
            for i in range(9):
                t = ((i + slide) / 9) ** 2
                y = horizon + (h - horizon) * t
                painter.drawLine(QPointF(0, y), QPointF(w, y))

        # The sweep of light.
        sweep = self._phase(p, 0.08, 0.5)
        if 0 < sweep < 1:
            x = -w * 0.2 + ease.valueForProgress(sweep) * w * 1.4
            beam = QLinearGradient(x - w * 0.18, 0, x + w * 0.18, 0)
            clear, bright = QColor(accent), QColor("#ffffff")
            clear.setAlpha(0)
            bright.setAlpha(230)
            beam.setColorAt(0.0, clear)
            beam.setColorAt(0.5, bright)
            beam.setColorAt(1.0, clear)
            painter.fillRect(QRectF(x - w * 0.18, centre.y() - 3, w * 0.36, 6), beam)
            halo = QRadialGradient(QPointF(0, 0), w * 0.18)
            glow = QColor(accent)
            glow.setAlpha(120)
            halo.setColorAt(0, glow)
            glow.setAlpha(0)
            halo.setColorAt(1, glow)
            painter.save()
            painter.translate(x, centre.y())
            painter.scale(1, 0.18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(QPointF(0, 0), w * 0.18, w * 0.18)
            painter.restore()

        # The rings.
        for i in range(3):
            ring = self._phase(p, 0.22 + i * 0.07, 0.72 + i * 0.05)
            if 0 < ring < 1:
                radius = ease.valueForProgress(ring) * min(w, h) * (0.32 + 0.12 * i)
                colour = QColor(accent)
                colour.setAlphaF((1 - ring) * 0.8)
                painter.setPen(QPen(colour, 3 - i * 0.7))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(centre, radius, radius)

        # The icon.
        appear = ease.valueForProgress(self._phase(p, 0.2, 0.5))
        fade = 1 - self._phase(p, 0.86, 1.0)
        if not self.logo.isNull() and appear > 0:
            size = int(min(w, h) * LOGO_SHARE * (0.7 + 0.3 * appear))
            glow = QRadialGradient(centre, size)
            tint = QColor(accent)
            tint.setAlphaF(0.5 * appear * fade)
            glow.setColorAt(0, tint)
            tint.setAlpha(0)
            glow.setColorAt(1, tint)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(centre, size, size)
            painter.setOpacity(appear * fade)
            painter.drawPixmap(QRect(int(centre.x() - size / 2), int(centre.y() - size / 2), size, size),
                               self._logo_for(int(min(w, h) * LOGO_SHARE)))
            painter.setOpacity(1.0)

        # The name, in wide letters that close up as it lands.
        text = self._phase(p, 0.38, 0.75)
        if text > 0:
            font = QFont(self.font())
            font.setPixelSize(max(18, int(h * 0.055)))
            font.setBold(True)
            spacing = 0.9 - 0.7 * ease.valueForProgress(text)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, font.pixelSize() * spacing)
            painter.setFont(font)
            colour = QColor("#ffffff")
            colour.setAlphaF(ease.valueForProgress(text) * fade)
            painter.setPen(colour)
            box = QRect(0, int(centre.y() + min(w, h) * 0.17), w, font.pixelSize() * 2)
            painter.drawText(box, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), NAME.upper())
        painter.end()
