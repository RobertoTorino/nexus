# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal's view (owner, 01-11-2026: the one view; Suite Desktop Mode, the window of tabs, is gone), as Steam's
Big Picture is for Steam: fullscreen, for a TV and a controller as much as for a desk. Large icons and type, the
header with the suite's icon, its name and the square pills, a category strip, and a focus that moves with the
arrow keys, a controller's d-pad or its stick (gamepad.py), with the mouse working as always. The Settings page (the
☰ pill or the controller's ☰ button, owner 04-11-2026, as the Windows Portable Suite's portal) takes the place of
the category strip and the tiles: the pills of the settings, each with a short line, under the same header.

A short animated intro (Intro) plays before the portal shows itself, with its sound; any key, click or button skips
it."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QEvent, QPointF, QRect, QRectF, QSize, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen, QPixmap, QRadialGradient
from PyQt6.QtWidgets import (
    QAbstractButton, QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QScroller, QStackedWidget, QTabBar,
    QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from bc250_core.theme import ACCENT, BLUE, ORANGE, OUTLINE, RED, header_font, muted, outline
from bc250_core.widgets import InfoButton, Pill, current_theme

from . import APP_ICONS, APP_NAME, CATEGORY_ICONS, INTRO_LOGO, LOGO_PATH, glyphs
from .looks import Backdrop, greyed

TILE_W, TILE_H = 244, 316
ICON_PX = 184
LOGO_PX = ICON_PX               # the suite's icon in the header: as large as a tile's icon (owner, 01-11-2026)
PILL_W = 128                    # a header pill: a rounded rectangle (owner, 01-11-2026) as wide as this, and as high as
PILL_MIN_H = 64                 # the room under the title down to the icon's bottom, at least this
PILL_RADIUS = 16
PILL_ALPHA = 150                # a pill that is not active (no focus, no mouse) shows the wallpaper through it
GAP = 20
MARGIN = 48
FULL_HEIGHT = 1000             # a window this high or higher is drawn at full size, a lower one smaller
SMALLEST = 0.68                 # 1280 x 720, the screen of a handheld, is about this
INTRO_MS = 3000                 # about three seconds (owner, 26-10-2026: two ended too abruptly)
LOGO_SHARE = 0.26               # the intro's icon: this part of the screen's shorter side
# What each category is for, short enough for the line under the title on a handheld's screen.
SHORT_HINTS = {
    "sustainable": "Test, tune, unlock and cool the board.",
    "graphics": "Upscaling, async compute and mesh shaders.",
    "gaming": "Emulators, Remote Play, Game Mode plugins.",
    "utilities": "Overlay, BIOS, Wi-Fi, HDMI-CEC, file transfer.",
}
KEYS = {Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down", Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right"}
CATEGORY_KEYS = {Qt.Key.Key_PageUp: "previous", Qt.Key.Key_Q: "previous", Qt.Key.Key_PageDown: "next",
                 Qt.Key.Key_E: "next"}
# Y and a right click update (owner, 04-11-2026, as the Windows Portable Suite's portal): the portal while a newer
# one is out, else the focused app; X and the Menu key hold the app's menu.
LEGEND = ("A / Enter  Open    Y / Right click  Update    X / Menu key  Menu    LB / RB  Category"
          "    ☰  Settings    R3  Keyboard    B / Esc  Close")
SETTINGS_LEGEND = "A / Enter  Change    ☰ / B / Esc  Back"
SETTINGS_HINT = "The portal's settings."         # the line under the title on the Settings page
SETTING_H = 96                  # a pill on the Settings page: as wide as a header pill, this high
UPDATE_BANNER = "UPDATE AVAILABLE, PRESS Y TO UPDATE"       # beside the category strip while a newer portal is out
INTRO_BANNER = "PORTAL UPDATE AVAILABLE"                    # on the intro, when the update check answers in time
BANNER_IN = 0.08                # the intro's banner fades in over this part of the intro


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


class Logo(QLabel):
    """The suite's icon in the header, drawn at the view's scale; a click opens the wiki."""

    clicked = pyqtSignal()

    def __init__(self, path):
        super().__init__()
        self.picture = QPixmap(str(path))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_side(LOGO_PX)

    def set_side(self, side: int) -> None:
        self.setFixedSize(side, side)
        if not self.picture.isNull():
            self.setPixmap(self.picture.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class HeaderPill(Pill):
    """A header pill as a rounded rectangle (owner, 01-11-2026): the value in large type over its caption, both
    centered; the row of them ends at the bottom of the suite's icon, so a pill is as high as the room under the
    title leaves. Not active (no focus, no mouse) it is half transparent, so the wallpaper shows through it; with
    the focus or under the mouse it is solid, framed in silver (the theme's outline, owner 05-11-2026), as a tile
    with the focus is. The same clicked, set_value and setEnabled as every pill."""

    scale = 1.0

    def __init__(self, value: str, caption: str, tooltip: str = "", colour: str = BLUE):
        super().__init__(value, caption, tooltip, colour)
        self.caption.setWordWrap(True)
        layout = self.layout()
        layout.insertStretch(0, 1)
        layout.addStretch(1)
        self.set_scale(1.0)

    def set_colour(self, colour: str) -> None:
        """The outline frames the active pill, whatever the color given: these pills have no colored edge."""
        theme = current_theme()
        window, edge = QColor(theme.window), QColor(theme.edge)
        radius = round(PILL_RADIUS * self.scale)
        self.setStyleSheet(
            f"#pill {{ background:rgba({window.red()},{window.green()},{window.blue()},{PILL_ALPHA});"
            f" border:2px solid rgba({edge.red()},{edge.green()},{edge.blue()},{PILL_ALPHA});"
            f" border-radius:{radius}px; }}"
            f"#pill:hover, #pill:focus {{ background:{theme.window}; border-color:{outline(theme)}; }}"
            f"#pill QLabel {{ background:transparent; border:none; color:{theme.text}; }}"
            f"#pill QLabel:disabled {{ color:{muted(theme)}; }}")

    def set_scale(self, scale: float) -> None:
        self.scale = scale
        s = scale
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)   # the row's height
        self.setFixedWidth(round(PILL_W * s))
        self.setMinimumHeight(round(PILL_MIN_H * s))
        self.setMaximumHeight(16777215)
        pad = round(6 * s)
        self.layout().setContentsMargins(pad, pad, pad, pad)
        self.value.setStyleSheet(header_font() + f"font-size:{max(14, round(22 * s))}px; font-weight:800;")
        self.caption.setStyleSheet(f"font-size:{max(11, round(13 * s))}px; font-weight:600;")
        self.set_colour("")


class BigTile(QAbstractButton):
    """One app: a large icon, its name, and its state under it. The focus is a bright frame around the whole tile.
    A click, Enter or A opens it (clicked); the Menu key or X asks for its menu (menu_requested), a right click or Y
    for an update (update_requested: the window's, owner 04-11-2026)."""

    navigate = pyqtSignal(str)
    menu_requested = pyqtSignal()
    update_requested = pyqtSignal()

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
        elif event.key() in CATEGORY_KEYS:                  # the page would scroll on Page Up and Page Down
            self.navigate.emit(CATEGORY_KEYS[event.key()])
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
        elif event.key() == Qt.Key.Key_Menu:
            self.menu_requested.emit()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.setFocus()
        self.update_requested.emit()

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
            painter.setPen(QPen(QColor(OUTLINE), 4) if focused else Qt.PenStyle.NoPen)
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


class MenuPill(HeaderPill):
    """The ☰ pill, its glyph larger than a pill's value: it opens the Settings page."""

    def set_scale(self, scale: float) -> None:
        super().set_scale(scale)
        self.value.setStyleSheet(header_font() + f"font-size:{max(22, round(36 * scale))}px; font-weight:800;")


class NoticeButton(QToolButton):
    """A short colored line beside the category strip (the updates the portal found, the ones outside the suite); a
    click, Enter or A opens the list of them as a menu. Hidden while there is nothing to say."""

    def __init__(self, colour: str):
        super().__init__()
        self.colour = colour
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_scale(1.0)
        self.hide()

    def set_scale(self, scale: float) -> None:
        self.setStyleSheet(
            f"QToolButton {{ color:{self.colour}; font-weight:700; font-size:{max(13, round(18 * scale))}px;"
            f" background:transparent; border:2px solid transparent; border-radius:{round(8 * scale)}px;"
            f" padding:{round(4 * scale)}px {round(10 * scale)}px; }}"
            f"QToolButton:hover, QToolButton:focus {{ border-color:{OUTLINE}; }}")

    def set_notice(self, text: str, tooltip: str = "") -> None:
        self.setText(text)
        self.setToolTip(tooltip)
        self.setVisible(bool(text))


class UpdateBanner(QToolButton):
    """The orange banner beside the category strip while a newer portal is out (owner, 04-11-2026, as the Windows
    Portable Suite's portal): white capitals on the suite's orange; a click, Enter or A does what Y does. While the
    update downloads and installs it says how far it is. Hidden while there is nothing to say."""

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_scale(1.0)
        self.hide()

    def set_scale(self, scale: float) -> None:
        self.setStyleSheet(
            f"QToolButton {{ color:white; background:{ORANGE}; font-weight:800; font-size:{max(13, round(18 * scale))}px;"
            f" border:2px solid {ORANGE}; border-radius:{round(8 * scale)}px;"
            f" padding:{round(4 * scale)}px {round(14 * scale)}px; }}"
            f"QToolButton:hover, QToolButton:focus {{ border-color:{OUTLINE}; }}")

    def set_banner(self, text: str, tooltip: str = "") -> None:
        self.setText(text)
        self.setToolTip(tooltip)
        self.setVisible(bool(text))


class BigPicture(Backdrop):
    """The view: the header (the suite's icon, its name with the version and the stage, the line under it, the
    square pills), the category strip with the notices beside it, the tiles of the open category, and under them
    what the buttons do. It shows what the window knows of each app (sync); a tile opens its app by
    open_requested(entry) and asks for its menu by menu_requested(entry)."""

    open_requested = pyqtSignal(object)         # an AppEntry
    menu_requested = pyqtSignal(object)         # an AppEntry
    update_requested = pyqtSignal(object)       # an AppEntry: a right click on its tile
    wiki_requested = pyqtSignal()

    def __init__(self, entries, categories: dict[str, str], hints: dict[str, str], version: str = "",
                 stage: str = "", stage_note: str = ""):
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
        self.top = top
        self.logo = Logo(LOGO_PATH)
        self.logo.setToolTip("Open the wiki in the browser")
        self.logo.clicked.connect(self.wiki_requested)
        top.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignTop)
        words = self.words = QVBoxLayout()           # as high as the icon: the pills take what the title leaves
        words.setSpacing(2)
        title_row = self.title_row = QHBoxLayout()
        self.title = QLabel(APP_NAME)
        title_row.addWidget(self.title)
        self.version = QLabel(f"v{version}" if version else "")
        title_row.addWidget(self.version, 0, Qt.AlignmentFlag.AlignBottom)
        self.stage = QLabel(stage)
        self.stage.setObjectName("stage")
        self.stage.setToolTip(stage_note)
        self.stage.setVisible(bool(stage))
        title_row.addWidget(self.stage, 0, Qt.AlignmentFlag.AlignVCenter)
        self.info = InfoButton("", "About this portal")
        title_row.addWidget(self.info, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch(1)
        words.addLayout(title_row)
        self.hint = ElidedLabel()
        words.addWidget(self.hint)
        self.pill_row = QHBoxLayout()
        self.pill_row.addStretch(1)
        words.addLayout(self.pill_row, 1)
        top.addLayout(words, 1)
        self.controls: list[QWidget] = [self.info]   # the header's widgets the focus can reach, the pills among them
        self.info.installEventFilter(self)
        self.pills: list[HeaderPill] = []
        outer.addLayout(top)

        strip = QHBoxLayout()
        self.bar = QTabBar()
        self.bar.setDrawBase(False)
        self.bar.setExpanding(False)
        self.bar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        strip.addWidget(self.bar)
        strip.addStretch(1)
        self.update_banner = UpdateBanner()         # a newer portal: Y, a click or Enter installs it
        self.outside = NoticeButton(ORANGE)         # newer programs outside the suite an installed app can install
        self.notice = NoticeButton(RED)             # the updates and reinstalls the portal found
        for button in (self.update_banner, self.outside, self.notice):
            self.add_control(button)
            strip.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.strip = QWidget()                      # hidden with the tiles on the Settings page
        self.strip.setLayout(strip)
        strip.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.strip)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.settings_page = QWidget()              # the Settings page: a row per setting (place_settings)
        page = QVBoxLayout(self.settings_page)
        page.setContentsMargins(0, 0, 0, 0)
        self.settings_heading = QTabBar()           # one tab, drawn as the open category's
        self.settings_heading.setDrawBase(False)
        self.settings_heading.setExpanding(False)
        self.settings_heading.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.settings_heading.addTab("Settings")
        page.addWidget(self.settings_heading, 0, Qt.AlignmentFlag.AlignLeft)
        self.settings_grid = QGridLayout()
        page.addLayout(self.settings_grid)
        page.addStretch(1)
        self.settings_page.hide()
        outer.addWidget(self.settings_page, 1)
        self.setting_pills: list[HeaderPill] = []
        self.setting_lines: list[QLabel] = []
        self.categories: list[str] = []
        self.labels: dict[str, str] = {}
        self.pages: dict[str, QScrollArea] = {}
        self.grids: dict[str, QGridLayout] = {}
        self.tiles: dict[str, BigTile] = {}
        for category, label in categories.items():
            keys = [entry.key for entry in entries if entry.category == category]
            if not keys:
                continue
            self.categories.append(category)
            self.labels[category] = label
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
                tile.navigate.connect(self.navigate)
                tile.clicked.connect(lambda _=False, k=key: self.open_requested.emit(self.entries[k]))
                tile.menu_requested.connect(lambda k=key: self.menu_requested.emit(self.entries[k]))
                tile.update_requested.connect(lambda k=key: self.update_requested.emit(self.entries[k]))
                self.tiles[key] = tile
        self.hints = {category: SHORT_HINTS.get(category, text) for category, text in hints.items()}
        self.full_hints = hints
        self.bar.currentChanged.connect(self._category_changed)
        self.keys = QLabel(LEGEND)
        self.keys.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(self.keys)
        self._category_changed(0)
        self.set_scale(1.0)

    # ------------------------------------------------------------------------------------------------ state
    def set_banner(self, text: str) -> None:
        self.banner.setText(text)
        self.banner.setVisible(bool(text))

    def set_about(self, text: str) -> None:
        """What the small "i" beside the title opens: where the apps install from, the versions."""
        self.info.set_text(text)

    def add_control(self, widget: QWidget) -> None:
        """A header widget the focus can reach with the arrow keys or the d-pad, and press with Enter or A."""
        widget.installEventFilter(self)
        self.controls.append(widget)

    def add_title_widget(self, widget: QWidget) -> None:
        """A button in the title row, after the stage (a newer portal, a restart)."""
        self.title_row.insertWidget(self.title_row.count() - 1, widget, 0, Qt.AlignmentFlag.AlignVCenter)
        self.add_control(widget)

    def place_pills(self, pills: list[HeaderPill]) -> None:
        """The window's pills, in a row under the title; the focus can reach them."""
        for pill in pills:
            self.pill_row.insertWidget(self.pill_row.count() - 1, pill)
            self.add_control(pill)
        self.pills = pills
        self.set_scale(self.scale)

    def place_settings(self, rows: list[tuple[HeaderPill, str]]) -> None:
        """The Settings page's rows: a pill and its short line; the focus reaches the pills there."""
        for row, (pill, line) in enumerate(rows, 1):
            label = QLabel(line)
            self.settings_grid.addWidget(pill, row, 0)
            self.settings_grid.setColumnStretch(1, 1)
            self.settings_grid.addWidget(label, row, 1, Qt.AlignmentFlag.AlignVCenter)
            self.add_control(pill)
            self.setting_pills.append(pill)
            self.setting_lines.append(label)
        self.set_scale(self.scale)

    def in_settings(self) -> bool:
        return not self.settings_page.isHidden()

    def show_settings(self, on: bool) -> None:
        """The Settings page in place of the category strip and the tiles, the focus on its first pill; off, back to
        the tiles, the focus on the first."""
        if on == self.in_settings():
            return
        self.strip.setVisible(not on)
        self.stack.setVisible(not on)
        self.settings_page.setVisible(on)
        self.keys.setText(SETTINGS_LEGEND if on else LEGEND)
        if on:
            self.hint.setText(SETTINGS_HINT)
        else:
            self._category_changed(self.bar.currentIndex())
        self.focus_first()

    def sync(self, states: dict) -> None:
        """Show each app as its tile in the window's state of it (AppState): icon, name, state."""
        for key, tile in self.tiles.items():
            state = states[key]
            entry = state.entry
            pixmap = self.art(entry.category, key, state.installed)
            marker = "update" if state.update else "reinstall" if state.reinstall else ""
            status = state.status if state.status != "Installed" else state.outside or (
                "changes the board" if entry.changes_board else "")
            colour = BLUE if state.busy else \
                RED if state.status in ("Update", "Reinstall needed", "App not available") else \
                ORANGE if status and state.status == "Installed" else muted()
            tile.set_look(state.title, pixmap, status, colour, marker)
            tile.setToolTip(state.tooltip)

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

    def set_counts(self, counts: dict[str, int]) -> None:
        """On each category's tab, in red, how many of its apps the notice names, so none goes unseen on a
        category that is not open."""
        for index, category in enumerate(self.categories):
            n = counts.get(category, 0)
            self.bar.setTabText(index, f"{self.labels[category]}  ● {n}" if n else self.labels[category])
            self.bar.setTabTextColor(index, QColor(RED) if n else QColor())

    def _category_changed(self, index: int) -> None:
        if 0 <= index < self.stack.count() and not self.in_settings():
            self.stack.setCurrentIndex(index)
            self.hint.setText(self.hints.get(self.categories[index], ""))
            self.reflow()

    def current_category(self) -> str:
        return self.categories[self.bar.currentIndex()] if self.categories else ""

    def current_page(self) -> QScrollArea | None:
        return self.stack.currentWidget()

    def current_tiles(self) -> list[BigTile]:
        if not self.categories:
            return []
        category = self.categories[self.bar.currentIndex()]
        return [self.tiles[e.key] for e in self.entries.values() if e.category == category]

    def show_app(self, key: str) -> None:
        """Open the category of the app and put the focus on its tile: a line of the notice."""
        entry = self.entries.get(key)
        if entry is None or entry.category not in self.categories:
            return
        self.show_settings(False)
        self.bar.setCurrentIndex(self.categories.index(entry.category))
        tile = self.tiles[key]
        tile.setFocus()
        self.current_page().ensureWidgetVisible(tile, 0, 24)

    # --------------------------------------------------------------------------------------------- layout
    def set_scale(self, scale: float) -> None:
        """Everything at *scale* of its size for a 1080 p screen: a handheld's 1280 x 720 or 1280 x 800 shows the
        same view smaller, so a row of icons and a second row both fit."""
        self.scale = scale
        s = scale
        self.outer.setContentsMargins(round(MARGIN * s), round(28 * s), round(MARGIN * s), round(20 * s))
        self.outer.setSpacing(round(16 * s))
        self.top.setSpacing(round(24 * s))
        self.words.setSpacing(round(6 * s))
        self.title_row.setSpacing(round(12 * s))
        self.pill_row.setSpacing(round(12 * s))
        self.logo.set_side(round(LOGO_PX * s))
        self.banner.setStyleSheet(f"background:{ORANGE}; color:white; font-weight:700; padding:6px 10px;"
                                  f" font-size:{max(12, round(16 * s))}px;")
        self.title.setStyleSheet(header_font() + f"font-size:{round(44 * s)}px; font-weight:800;")
        self.version.setStyleSheet(f"color:{muted()}; font-size:{max(13, round(20 * s))}px; padding-bottom:"
                                   f"{round(6 * s)}px;")
        self.stage.setStyleSheet(f"background:{ACCENT}; color:white; font-weight:700;"
                                 f" font-size:{max(11, round(14 * s))}px; border-radius:{round(6 * s)}px;"
                                 f" padding:{round(2 * s)}px {round(8 * s)}px;")
        self.hint.setStyleSheet(f"color:{muted()}; font-size:{max(13, round(18 * s))}px;")
        self.keys.setStyleSheet(f"color:{muted()}; font-size:{max(16, round(24 * s))}px; font-weight:700;")
        self.bar.setStyleSheet(
            f"QTabBar::tab {{ font-size:{max(15, round(24 * s))}px; font-weight:700;"
            f" padding:{round(10 * s)}px {round(26 * s)}px; margin-right:6px; background:transparent; border:none;"
            " border-bottom:4px solid transparent; }"
            f"QTabBar::tab:selected {{ border-bottom:4px solid {OUTLINE}; }}"
            "QTabBar::tab:hover { background:rgba(128,128,128,40); }")
        self.settings_heading.setStyleSheet(self.bar.styleSheet())
        for button in (self.update_banner, self.notice, self.outside):
            button.set_scale(s)
        for pill in self.pills:
            pill.set_scale(s)
        for pill in self.setting_pills:
            pill.set_scale(s)
            pill.setFixedHeight(round(SETTING_H * s))
        self.settings_grid.setHorizontalSpacing(round(24 * s))
        self.settings_grid.setVerticalSpacing(round(14 * s))
        self.settings_page.layout().setSpacing(round(16 * s))
        for label in self.setting_lines:
            label.setStyleSheet(f"font-size:{max(13, round(20 * s))}px; font-weight:600;")
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
        elif event.type() == QEvent.Type.KeyPress and watched in self.controls:
            # The arrow keys move the focus from a header control as from a tile, Page Up and Page Down change the
            # category; Enter presses a button (a pill presses itself).
            key = event.key()
            if key in KEYS or key in CATEGORY_KEYS:
                self.navigate(KEYS.get(key) or CATEGORY_KEYS[key])
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and isinstance(watched, QAbstractButton):
                watched.click()
                return True
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
        """What the focus can be on: the tiles of the open category and the header's controls (the pills, the
        notices, the buttons of the title row)."""
        controls = [c for c in self.controls if c.isVisibleTo(self) and c.isEnabled()
                    and c.focusPolicy() != Qt.FocusPolicy.NoFocus]
        return [t for t in self.current_tiles() if t.isVisibleTo(self)] + controls

    def focused_item(self) -> QWidget | None:
        focus = self.window().focusWidget()
        return focus if focus in self.focus_items() else None

    def focus_first(self) -> None:
        """The first tile; on the Settings page, its first pill."""
        if self.in_settings():
            if self.setting_pills:
                self.setting_pills[0].setFocus()
            return
        tiles = self.current_tiles()
        if tiles:
            tiles[0].setFocus()

    def navigate(self, where: str) -> None:
        """A key on a tile or a control: a direction moves the focus, previous and next change the category."""
        if where in CATEGORY_KEYS.values():
            self.change_category(-1 if where == "previous" else 1)
        else:
            self.move_focus(where)

    def move_focus(self, direction: str) -> None:
        """Move the focus to the nearest tile or control that way; with nothing focused, to the first tile."""
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
        if self.categories and not self.in_settings():
            self.bar.setCurrentIndex((self.bar.currentIndex() + step) % len(self.categories))
            self.focus_first()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        key = event.key()
        if key in KEYS or key in CATEGORY_KEYS:
            self.navigate(KEYS.get(key) or CATEGORY_KEYS[key])
        else:
            super().keyPressEvent(event)


class Intro(QWidget):
    """The portal's intro, about three seconds, painted over the window before it shows itself: on a dark screen a
    light sweeps across, rings open from the suite's icon, the suite's name draws itself in wide letters and
    settles, and the screen clears to the portal. Any key, click or button skips it (skip(), also called by the
    gamepad)."""

    finished = pyqtSignal()
    skipped = pyqtSignal()                      # cut short: its sound stops too

    def __init__(self, parent: QWidget, duration: int = INTRO_MS):
        super().__init__(parent)
        self.progress = 0.0
        self.title = APP_NAME.upper()           # the suite's name in capitals, as the owner wrote it
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
        self.banner = ""                        # INTRO_BANNER, from set_banner()
        self.banner_at = 0.0                    # the progress when it came

    def set_banner(self, text: str) -> None:
        """A banner under the name for the rest of the intro: the portal's update check answered (owner, 04-11-2026,
        as the Windows Portable Suite's portal)."""
        self.banner, self.banner_at = text, self.progress
        self.update()

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
        # Dark from the first frame (the portal is not shown before the intro), clearing at the end.
        backdrop = QColor("#04060c")
        backdrop.setAlphaF(1 - self._phase(p, 0.86, 1.0))
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

        # The suite's name, in wide letters that close up as it lands.
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
            painter.drawText(box, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), self.title)

        # The banner under the name: white capitals on the suite's orange, fading in when the update check answers.
        if self.banner:
            font = QFont(self.font())
            font.setPixelSize(max(14, int(h * 0.03)))
            font.setWeight(QFont.Weight.ExtraBold)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, font.pixelSize() * 0.12)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            pad = font.pixelSize()
            width, height = metrics.horizontalAdvance(self.banner) + 2 * pad, metrics.height() + pad
            top = centre.y() + min(w, h) * 0.17 + max(18, int(h * 0.055)) * 2 + h * 0.03
            plate = QRectF((w - width) / 2, top, width, height)
            painter.setOpacity(min(1.0, (p - self.banner_at) / BANNER_IN) * fade)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(ORANGE))
            painter.drawRoundedRect(plate, height / 4, height / 4)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(plate, int(Qt.AlignmentFlag.AlignCenter), self.banner)
            painter.setOpacity(1.0)
        painter.end()
