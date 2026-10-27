# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal window: the notice of updates above the tabs, on every tab; then a tab per category (the category of
the apps' icons, apps.toml), each with the tiles of its apps; check is the first tile on Sustainable (owner,
20-10-2026). The portal always opens on the first tab (owner, 20-10-2026). Each tab is as large as a header pill
(owner, 21-10-2026).

Install, update and uninstall run the app's own installer in a terminal window (they may ask for the sudo
password and print what they do); the portal watches for the exit file the terminal writes and then refreshes. A
terminal whose installer ended well closes by itself (owner, 26-10-2026); one that failed stays open with what
happened until Enter is pressed.
An app that changes the board (unlocks, governor, ACPI) gets a warning before it is installed or opened.

Updates: a red dot marks every tile whose installed app differs from the version this portal pins, a red circular
arrow every installed app the portal has no record of (installed by hand, or under an earlier name of the app: its
version is unknown, so it needs a reinstall). An app installed from a checkout is recorded with the checkout's
version of it: a portal from a release compares that with the version it pins, as it does a tag (an older record
without the version needs a reinstall); a portal from a checkout shows it as installed, whatever the pin, since the
checkout is what it installs. The notice beside check names each of them, with a link to its tile,
and a tab's name counts those on it, so none goes unseen on a tab that is not open. At start the portal looks for a
newer portal release on GitHub (which is how newer app versions arrive).

The header, as an app's header with pills (owner, 20-10-2026): the portal's icon as large as the tiles' icons; beside
it the name, where the apps install from, and a row of pills (rows, on a window too narrow for one; owner,
21-10-2026), as the apps' status boxes: Refresh, Installed apps
(installed / listed), Install all updates, the Desktop icons (Yes or No; a click switches), the theme (a click goes
to the next one), the wallpaper and Sys info (a small window with what the system reports about the board,
sysinfo.py).

Install all updates: every app the notice names (an update or a reinstall), one after the other, each in its own
terminal as a single install. An installer that asks for the sudo password waits for it in its terminal, and so
does the batch: the next one starts when it has ended. One question first, with the board warning when one of them
changes the board; one message at the end names those that failed. Install all apps (owner, 26-10-2026): the last
tab is a button that looks like a tab (PillTabBar.action_index); it installs the same way every app of the open
category that is not installed yet, so a portal installed for the first time fills a category with one click.

Desktop icons: the portal's own icon is enough to reach every app, so the apps' icons on the Desktop are the user's
choice ("Icons on Desktop", desktop_icons.py). The first start asks when app icons are there; off, the portal
removes them at start and after each install (the installers write one), on, it adds one for every installed app.

Wallpaper: none until the user chooses one, the portal's example picture or one of their own, behind the window (wallpaper.py), under a veil of
the theme's window color so the text stays readable. A slider in the Wallpaper pill's menu sets the veil, the
picture's transparency (owner, 20-10-2026): a dark picture can take a stronger one, so the icons on it stand out.

Sound and Suite Big Picture Mode (owner, 21-10-2026): a swoosh plays when the portal opens, and the Sound pill turns
it, and the Big Picture sounds, off (the choice is kept; without an audio output the pill is disabled and the portal
silent). The Suite mode pill switches between Suite Desktop Mode, this window, and Suite Big Picture Mode
(bigpicture.py): fullscreen with large icons, for a TV and a controller (gamepad.py), opened by a short animated
intro with its own sound. F11 switches too. The last mode is kept: the portal opens in it."""

from __future__ import annotations

import shlex
import subprocess
from html import escape
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePath

from PyQt6.QtCore import QCoreApplication, QEvent, QProcess, QSize, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QKeyEvent, QKeySequence, QPainter, QPalette, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea,
    QSlider, QStackedWidget, QTabBar, QTabWidget, QToolButton, QVBoxLayout, QWidget, QWidgetAction,
)

from bc250_core import SUITE_MANUAL_URL, __version__ as CORE_VERSION, upstream
from bc250_core.platform import bin_home, expand, launch_in_terminal
from bc250_core.settings import GEOMETRY_KEY, open_settings, restore_geometry, save_geometry
from bc250_core.theme import ACCENT, BLUE, GREY, ORANGE, RED, THEMES, header_font, muted, save_theme_name, theme_name
from bc250_core.updates import ReleaseInfo, UpdateChecker, version_tuple
from bc250_core.widgets import ClickableLogo, Pill, hint_label, same_width

from . import audio, desktop_icons, glyphs, sysinfo, wallpaper
from .bigpicture import DESKTOP_NAME, NAME as BIG_NAME, BigPicture, Intro
from .gamepad import Gamepad
from .looks import HOVER_OPACITY, VEIL, Backdrop, dimmed, greyed  # noqa: F401 (HOVER_OPACITY: the tests)
from . import APP_ICONS, APP_ID, APP_NAME, INFO, LOGO_PATH, STAGE, STAGE_NOTE, __version__
from .manifest import CATEGORIES, AppEntry
from .portal_update import PortalUpdate
from .sources import Records, SourceError, Sources, installed_from, is_installed, is_local, local_record, local_version

POLL_MS = 1000
ICON_PX = 128                   # the app icon on its tile (the icon files are 128 x 128), and the portal's in the header
SYMBOL_PX = 28                  # the Install / Uninstall / Reinstall symbols beside it
DOT_PX = 16                     # the red update dot inside the icon
BADGE_PX = 24                   # the red circular arrow inside the icon: a reinstall is needed
TILE_WIDTH = 216                # the tiles flow left to right, as many to a row as fit
TILE_SPACING = 12
PAGE_MARGIN = 24                # a tab's margins take this much of its width
VEIL_MAX = 90                   # the slider's end: the picture still shows; "No wallpaper" takes it away
VEIL_STEP = 5
VEIL_KEY = "portal/wallpaper_transparency"
DESKTOP_ICONS_KEY = "portal/desktop_icons"
SOUND_KEY = "portal/sound"
MODE_KEY = "portal/mode"                # "desktop" or "bigpicture": the mode the portal opens in
VALUE_PX = 300                  # a value in the Sys info window wraps beyond this width
SYSINFO_OPACITY = 85            # % of the window color behind the Sys info text: what lies behind shows through
PILL_COLOUR = BLUE              # the header pills' left edge, as the apps' status boxes (owner, 20-10-2026)
LAUNCH_ICON_FILES = {("compute", "Unlock"): "cu-unlock", ("cores", "Unlock"): "cores-unlock"}  # else the app's
# What each tab holds, at its top (docs/apps/categories.md says the same).
CATEGORY_HINTS = {
    "sustainable": "The board itself: test it, tune it, unlock it, cool it, and keep it running well for a long time.",
    "graphics": "Graphics features for games: upscaling, async compute and mesh shaders on the board's GPU.",
    "gaming": "Playing: emulators, Remote Play with your console, plugins in Game Mode, and PlayStation trivia.",
    "utilities": "Handy tools around the board: an overlay, a USB stats screen, the PS5 HD Camera as a webcam, the "
                 "DualSense's firmware, the BIOS settings, Wi-Fi, the TV over HDMI-CEC, file transfer, a graphical "
                 "netcat, demo recordings, and the suite's dependencies.",
}

BOARD_WARNING = (
    "<p><b>{name} changes how your BC-250 runs</b> (clocks, voltages, unlocked units or firmware tables).</p>"
    "<p>A wrong setting can make the board unstable or stop it from booting until the change is undone. Read the "
    "app's manual first, know how to undo the change, and keep a way to reach the board without its desktop.</p>"
    "<p>{action}?</p>")


@dataclass
class Pending:
    entry: AppEntry
    action: str                 # "install" | "uninstall"
    exit_file: Path
    tag: str


def red_dot(size: int = 10, tooltip: str = "") -> QLabel:
    """The small red dot that marks an available update."""
    dot = QLabel()
    dot.setFixedSize(size, size)
    dot.setStyleSheet(f"background:{RED}; border-radius:{size // 2}px; border:2px solid palette(window);")
    dot.setToolTip(tooltip)
    dot.hide()
    return dot


def reinstall_badge(size: int = BADGE_PX) -> QLabel:
    """The red circular arrow that marks an app the portal has no record of: it needs a reinstall."""
    badge = QLabel()
    badge.setFixedSize(size, size)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(f"background:{RED}; border-radius:{size // 2}px; border:2px solid palette(window);")
    badge.setPixmap(glyphs.reinstall("white").pixmap(size - 8, size - 8))
    badge.hide()
    return badge


def shell_line(folder: PurePath, commands: tuple[str, ...]) -> str:
    """cd into the extracted app and run its commands in order, stopping at the first failure."""
    return " && ".join([f"cd {shlex.quote(str(folder))}", *commands])


def short_name(name: str) -> str:
    """The name on a tile: the suite's prefix is understood in the portal ("BC-250 Bazzite Test": "Bazzite Test")."""
    for prefix in ("BC-250 ", "BC250 "):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def placeholder_icon(name: str) -> QPixmap:
    """For an app without an icon file: its initial on a gray tile."""
    pixmap = QPixmap(ICON_PX, ICON_PX)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(GREY))
    painter.drawRoundedRect(4, 4, ICON_PX - 8, ICON_PX - 8, 20, 20)
    font = painter.font()
    font.setPixelSize(ICON_PX // 2)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("white"))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, short_name(name)[:1].upper())
    painter.end()
    return pixmap


def still_icon(pixmap: QPixmap) -> QIcon:
    """An icon that looks the same on a disabled button: the tile chooses itself when it is grayed."""
    icon = QIcon()
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Disabled, QIcon.Mode.Active):
        icon.addPixmap(pixmap, mode)
    return icon


class AppTile(QFrame):
    """One app, compact: its short name, its icon (click: open; hover: what it does; gray: not installed; red dot:
    an update; red circular arrow: a reinstall is needed), "changes the board" under it when so, and beside it the
    symbol buttons: Install and Uninstall, or only Install (which reinstalls it) for check."""

    install_clicked = pyqtSignal(object)
    uninstall_clicked = pyqtSignal(object)
    open_clicked = pyqtSignal(object, str)

    def __init__(self, entry: AppEntry, parent: QWidget | None = None):
        super().__init__(parent)
        self.entry = entry
        self.status = ""
        self.setFixedWidth(TILE_WIDTH)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)
        self.title = QLabel(entry.short or short_name(entry.name))
        self.title.setWordWrap(True)
        self.title.setStyleSheet(header_font() + "font-size:15px; font-weight:700;")
        outer.addWidget(self.title)
        row = QHBoxLayout()
        row.setSpacing(6)
        outer.addLayout(row)
        under = QVBoxLayout()
        under.setSpacing(2)
        row.addLayout(under)

        file = APP_ICONS / f"{entry.key}.webp"
        loaded = QPixmap(str(file)) if file.is_file() else QPixmap()
        self.has_icon = not loaded.isNull()
        pixmap = loaded.scaled(ICON_PX, ICON_PX, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation) if self.has_icon \
            else placeholder_icon(entry.name)
        # installed, not installed, installed under the mouse
        self._icons = (still_icon(pixmap), still_icon(greyed(pixmap)), still_icon(dimmed(pixmap)))
        self.installed = False
        self.icon = QToolButton()
        self.icon.setIconSize(QSize(ICON_PX, ICON_PX))
        self.icon.setFixedSize(ICON_PX + 8, ICON_PX + 8)
        self.icon.setAutoRaise(True)
        # The icon alone, at its full size: no face, no padding (the theme gives every tool button both). Under the
        # mouse it dims a little, no border (owner, 20-10-2026); a press nudges the icon down-right, as a real button
        # sinks, with no color behind it (owner, 20-10-2026: no purple flash on a click).
        self.icon.setStyleSheet("QToolButton { background:transparent; border:2px solid transparent;"
                                " border-radius:18px; padding:0; }"
                                "QToolButton:hover { background:transparent; border-color:transparent; }"
                                "QToolButton:pressed:enabled { background:transparent; padding-top:2px;"
                                " padding-left:2px; }"
                                "QToolButton::menu-indicator { image:none; width:0; }")
        self.icon.installEventFilter(self)
        self.open_button = self.icon                    # clicking the icon opens the app
        if len(entry.launch) > 1:
            menu = QMenu(self.icon)
            for label, command in entry.launch:
                action = menu.addAction(label, lambda c=command: self.open_clicked.emit(self.entry, c))
                own = APP_ICONS / f"{LAUNCH_ICON_FILES.get((entry.key, label), '')}.webp"
                action.setIcon(QIcon(str(own)) if (entry.key, label) in LAUNCH_ICON_FILES and own.is_file()
                               else QIcon(pixmap))
            self.icon.setMenu(menu)
            self.icon.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        elif entry.launch:
            self.icon.clicked.connect(lambda: self.open_clicked.emit(self.entry, entry.launch[0][1]))
        under.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignHCenter)
        self.dot = red_dot(DOT_PX)
        self.dot.setParent(self.icon)
        self.dot.move(ICON_PX - DOT_PX - 4, ICON_PX - DOT_PX - 4)          # inside the icon, bottom right
        self.badge = reinstall_badge()
        self.badge.setParent(self.icon)
        self.badge.move(ICON_PX - BADGE_PX - 4, ICON_PX - BADGE_PX - 4)    # in the same corner
        self.board = QLabel("changes the board")
        self.board.setStyleSheet(f"color:{ORANGE}; font-size:11px; font-weight:700;")
        self.board.setToolTip("It changes how the board runs; the portal asks first before installing or opening it.")
        self.board.setVisible(entry.changes_board and not entry.withdrawn)
        under.addWidget(self.board, 0, Qt.AlignmentFlag.AlignHCenter)
        self.withdrawn = QLabel("App not available")
        self.withdrawn.setStyleSheet(f"color:{RED}; font-size:11px; font-weight:700;")
        self.withdrawn.setToolTip(f"Its release was withdrawn: {entry.withdrawn}" if entry.withdrawn else "")
        self.withdrawn.setVisible(bool(entry.withdrawn))
        under.addWidget(self.withdrawn, 0, Qt.AlignmentFlag.AlignHCenter)
        self.busy_label = QLabel()
        self.busy_label.setStyleSheet(f"color:{BLUE}; font-size:11px; font-weight:700;")
        self.busy_label.hide()
        under.addWidget(self.busy_label, 0, Qt.AlignmentFlag.AlignHCenter)
        under.addStretch(1)

        buttons = QVBoxLayout()
        buttons.setSpacing(6)
        buttons.addStretch(1)
        self.install_button = self._symbol_button()
        self.install_button.clicked.connect(lambda: self.install_clicked.emit(self.entry))
        self.uninstall_button = self._symbol_button()
        self.uninstall_button.setIcon(glyphs.uninstall(self._ink()))
        self.uninstall_button.setToolTip(f"Uninstall {entry.name}")
        self.uninstall_button.clicked.connect(lambda: self.uninstall_clicked.emit(self.entry))
        # check is part of the suite: it goes when the portal is uninstalled (packaging/install.sh --uninstall).
        self.uninstall_button.setVisible(not entry.required)
        buttons.addWidget(self.install_button)
        buttons.addWidget(self.uninstall_button)
        buttons.addStretch(1)
        row.addLayout(buttons)
        row.addStretch(1)
        outer.addStretch(1)

    def _symbol_button(self) -> QToolButton:
        button = QToolButton()
        button.setFixedSize(SYMBOL_PX + 12, SYMBOL_PX + 12)
        button.setIconSize(QSize(SYMBOL_PX, SYMBOL_PX))
        button.setAutoRaise(True)
        # No face and no padding: the theme's padding of every tool button left the symbol a third of its size.
        button.setStyleSheet(f"QToolButton {{ background:transparent; border:1px solid transparent;"
                             f" border-radius:8px; padding:0; }}"
                             f"QToolButton:hover:enabled {{ border:1px solid {ACCENT}; }}")
        return button

    def eventFilter(self, watched, event) -> bool:
        """The icon under the mouse dims a little, while it opens the app."""
        if watched is self.icon and event.type() in (QEvent.Type.Enter, QEvent.Type.Leave):
            self._show_icon(hovered=event.type() == QEvent.Type.Enter)
        return super().eventFilter(watched, event)

    def _show_icon(self, hovered: bool = False) -> None:
        hovered = hovered and self.icon.isEnabled()
        self.icon.setIcon(self._icons[2 if hovered else 0 if self.installed else 1])

    def _ink(self) -> str:
        return self.palette().color(QPalette.ColorRole.ButtonText).name()

    def show_state(self, installed: bool, installed_tag: str, busy: str = "", from_checkout: bool = False) -> str:
        """Show the app's state; "update" when an update is available, "reinstall" when a reinstall is needed, else
        "". *from_checkout*: this portal runs from a checkout."""
        entry = self.entry
        # An update needs a known, different version. An app installed some other way (by hand, or under an earlier
        # name of the app) has none recorded: its version is unknown, so it needs a reinstall. An app installed from
        # a checkout is recorded with the checkout's version of it: a portal from a release compares that with the
        # version it pins (a record from before the version was kept, "local" alone, is unknown too); a portal from
        # a checkout installs from the checkout, so what it installed is what it has.
        local = is_local(installed_tag)
        from_other_checkout = local and bool(entry.tag) and not from_checkout
        if from_other_checkout:
            version = local_version(installed_tag)
            differs, unknown = bool(version) and version != entry.version, not version
        else:
            differs, unknown = bool(installed_tag) and not local and installed_tag != entry.tag, not installed_tag
        update = installed and differs and bool(entry.tag) and not entry.withdrawn
        reinstall = installed and unknown and not entry.withdrawn
        self.dot.setVisible(update)
        self.dot.setToolTip(f"Update available: {entry.tag} (installed {installed_from(installed_tag)})."
                            if update else "")
        self.badge.setVisible(reinstall)
        self.badge.setToolTip(("Reinstall needed: installed from a suite checkout, its version unknown."
                               if from_other_checkout else
                               "Reinstall needed: the portal did not install it, so its version is unknown.")
                              if reinstall else "")
        if busy:
            self.status, detail = busy, busy
        elif entry.withdrawn:
            self.status = "App not available"
            detail = (f"App not available: its release was withdrawn ({entry.withdrawn}). "
                      + ("The portal removes it from the board." if installed else "It cannot be installed."))
        elif not installed:
            self.status, detail = "Not installed", "Not installed: install it with the button beside the icon."
        elif update:
            self.status = "Update"
            detail = f"Update available: installed {installed_from(installed_tag)}, this portal pins {entry.tag}."
        elif reinstall:
            self.status = "Reinstall needed"
            detail = (("Reinstall needed: an earlier portal installed it from a suite checkout without recording "
                       "its version, so it is unknown. ") if from_other_checkout else
                      ("Reinstall needed: it is installed, but not by this portal (by hand, or under an earlier name "
                       "of the app), so its version is unknown. ")
                      ) + "Reinstall it with the red button beside the icon."
        else:
            self.status = "Installed"
            detail = f"Installed {installed_from(installed_tag)}."
        self.busy_label.setText(busy)
        self.busy_label.setVisible(bool(busy))
        self.installed = installed
        opens = installed and not busy and bool(entry.launch) and not entry.withdrawn
        self.icon.setEnabled(opens)
        self._show_icon(self.icon.underMouse())
        self.icon.setCursor(Qt.CursorShape.PointingHandCursor if opens else Qt.CursorShape.ArrowCursor)
        how = ("Click to open it." if len(entry.launch) == 1 else
               "Click to open: " + ", ".join(label for label, _ in entry.launch) + "." if entry.launch else
               "Not a program: nothing to open.")
        source = entry.tag or "runs from the suite checkout"
        self.icon.setToolTip(f"<p><b>{escape(entry.name)}</b></p><p>{escape(entry.summary)}</p>"
                             f"<p style='color:gray;'>{escape(detail)}<br>{escape(source)}"
                             + (f"<br>{escape(how)}" if installed else "") + "</p>")

        action, ink = ("Update", RED) if update else ("Reinstall", RED) if reinstall else \
            ("Reinstall", self._ink()) if installed else ("Install", self._ink())
        # The arrow into a tray for every app, Bazzite Test too (owner, 14-10-2026); the circular arrow only when the
        # version is unknown.
        draw = glyphs.reinstall if reinstall else glyphs.install
        self.install_button.setIcon(draw(ink))
        self.install_button.setToolTip(f"{action} {entry.name}" + (f" v{entry.version}" if entry.tag else "")
                                       if not entry.withdrawn else f"App not available: {entry.withdrawn}")
        self.install_button.setEnabled(not busy and not entry.withdrawn)
        self.uninstall_button.setEnabled(installed and not busy)
        return "update" if update else "reinstall" if reinstall else ""


class TogglePill(Pill):
    """A pill that is on or off, Yes or No: a click switches it (as a check box, with its isChecked, setChecked and
    toggled)."""

    toggled = pyqtSignal(bool)

    def __init__(self, caption: str, tooltip: str = "", checked: bool = False):
        self.checked = checked
        super().__init__("Yes" if checked else "No", caption, tooltip, PILL_COLOUR)
        self.clicked.connect(lambda: self.setChecked(not self.checked))

    def isChecked(self) -> bool:  # noqa: N802 (as QCheckBox)
        return self.checked

    def setChecked(self, checked: bool) -> None:  # noqa: N802 (as QCheckBox)
        if checked == self.checked:
            return
        self.checked = checked
        self.set_value("Yes" if checked else "No", self.toolTip())
        self.toggled.emit(checked)


class PillTabBar(QTabBar):
    """The category tabs, each as large as a header pill (owner, 21-10-2026); wider where a name needs it. A gap
    above them, so the line over the tabs divides them from the notice. The tab at action_index is a button that
    looks like a tab (owner, 26-10-2026: Install all apps): a click on it emits action_clicked and never opens it."""

    GAP = 10
    action_clicked = pyqtSignal()

    def __init__(self, pill: Pill):
        super().__init__()
        self.pill = pill
        self.action_index = -1
        self.setStyleSheet(f"QTabBar::tab {{ font-size:15px; font-weight:700; margin-top:{self.GAP}px; }}")

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        index = self.tabAt(event.position().toPoint())
        if index >= 0 and index == self.action_index:
            if event.button() == Qt.MouseButton.LeftButton and self.isTabEnabled(index):
                self.action_clicked.emit()
            return
        super().mousePressEvent(event)

    def tabSizeHint(self, index: int) -> QSize:  # noqa: N802 (Qt override)
        hint = super().tabSizeHint(index)          # the margin included
        return QSize(max(hint.width(), self.pill.minimumWidth()),
                     max(hint.height(), self.pill.sizeHint().height() + self.GAP))

    def refit(self) -> None:
        """Lay the tabs out again, after the pills changed size (setTabText makes QTabBar measure them anew)."""
        if self.count():
            self.setTabText(0, self.tabText(0))


class SysInfoDialog(QDialog):
    """What the system reports about the board (sysinfo.py): a section per part in two columns of about the same
    length, the names muted, the values selectable; Copy puts it all on the clipboard as plain text. Its background
    is the window color at SYSINFO_OPACITY (owner, 20-10-2026); the text stays opaque, so it reads as well."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME}: Sys info")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.sections: list[sysinfo.Section] = []
        layout = QVBoxLayout(self)
        self.grids = (QGridLayout(), QGridLayout())     # each column its own, so their rows need not line up
        columns = QHBoxLayout()
        columns.setSpacing(32)
        for grid in self.grids:
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(2)
            grid.setAlignment(Qt.AlignmentFlag.AlignTop)
            columns.addLayout(grid)
        layout.addLayout(columns)
        layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.copy_button = buttons.addButton("Copy", QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button.setToolTip("Copy everything as text, for an issue or a forum post.")
        self.copy_button.clicked.connect(self.copy)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def fill(self, sections: list[sysinfo.Section]) -> None:
        self.sections = sections
        for grid in self.grids:
            while grid.count():
                item = grid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        half = sum(len(rows) + 1 for _, rows in sections) / 2
        grid, row = self.grids[0], 0
        for title, rows in sections:
            if grid is self.grids[0] and row and row + (len(rows) + 1) / 2 > half:     # the rest on the right
                grid, row = self.grids[1], 0
            heading = QLabel(title)
            heading.setStyleSheet("font-weight:700;" + (" margin-top:8px;" if row else ""))
            grid.addWidget(heading, row, 0, 1, 2)
            row += 1
            for key, value in rows:
                name = QLabel(key)
                name.setStyleSheet(f"color:{muted()};")
                text = QLabel(value)
                text.setWordWrap(True)
                text.setFixedWidth(VALUE_PX)            # a long name wraps, at a height the layout knows
                text.setMinimumHeight(text.heightForWidth(VALUE_PX))
                text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                grid.addWidget(name, row, 0, Qt.AlignmentFlag.AlignTop)
                grid.addWidget(text, row, 1, Qt.AlignmentFlag.AlignTop)
                row += 1
        self.adjustSize()

    def copy(self) -> None:
        QApplication.clipboard().setText(sysinfo.as_text(self.sections))

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)    # replace, not blend
        colour = QColor(self.palette().color(QPalette.ColorRole.Window))
        colour.setAlphaF(SYSINFO_OPACITY / 100)
        painter.fillRect(self.rect(), colour)
        painter.end()


class MainWindow(QMainWindow):
    def __init__(self, entries: list[AppEntry], sources: Sources, records: Records,
                 portal_check: Callable[[], ReleaseInfo] | None = None, local_build: Path | None = None,
                 desktop: Path | None = None, menu: Path | None = None, parent: QWidget | None = None,
                 installed: Path | None = None, launch: Callable[[list[str]], bool] | None = None,
                 sounds: audio.Sounds | None = None, gamepad: Gamepad | None = None):
        """*portal_check* returns the newest portal release (run once, off the GUI thread); None: no check.
        *local_build* is the suite checkout this portal runs from or was installed from: a banner says so.
        *desktop* and *menu* are the Desktop folder and the app menu entries' folder (default: the user's).
        *installed* is where the installed portal is (installed_copy()): a newer one there offers a restart; None: no
        check. *launch* starts a program detached (default QProcess.startDetached; tests pass a fake). *sounds* and
        *gamepad* are the portal's sound player and controller reader (tests pass fakes)."""
        super().__init__(parent)
        self.entries = entries
        self.desktop = desktop or desktop_icons.desktop_dir()
        self.menu = menu or desktop_icons.menu_dir()
        self.sources = sources
        self.records = records
        self.pending: Pending | None = None
        self.worker = UpdateChecker(self)               # generic: runs one job off the GUI thread
        self.worker.finished.connect(self._prepared)
        self._job: tuple[AppEntry, str] | None = None
        self._withdrawal_tried: set[str] = set()        # withdrawn apps the portal tried to remove this time
        self.batch: list[AppEntry] | None = None        # Install all updates: the apps still to go; None: no batch
        self.batch_what = "updates"                     # the batch's word: "updates" or "apps" (Install all apps)
        self.batch_pill: Pill | None = None             # the pill that shows the batch's progress
        self.batch_size = 0
        self.batch_failed: list[str] = []
        self.settings = open_settings(INFO, self)
        self.sounds = sounds or audio.Sounds()
        self.sounds.enabled = self.settings.value(SOUND_KEY, True, type=bool)
        self.gamepad = gamepad or Gamepad(self)
        self.gamepad.action.connect(self._gamepad_action)
        self.intro: Intro | None = None
        self.installed = installed
        self.launch = launch or (lambda argv: QProcess.startDetached(argv[0], argv[1:])[0])
        self.setWindowTitle(INFO.display_name)
        screen = QApplication.primaryScreen()
        self.resize(min(1180, screen.availableGeometry().width()) if screen else 1180, 720)

        central = self.backdrop = Backdrop()
        central.set_veil(self.transparency())
        root = QVBoxLayout(central)
        self.local_banner = QLabel()
        self.local_banner.setWordWrap(True)
        self.local_banner.setStyleSheet(f"background:{ORANGE}; color:white; font-weight:700; padding:6px 10px;")
        if local_build is not None:
            self.local_banner.setText(f"Local build: this portal comes from the checkout {local_build}, "
                                      "not from a published release.")
        self.local_banner.setVisible(local_build is not None)
        root.addWidget(self.local_banner)
        # The header, as an app's (owner, 20-10-2026): the icon as large as the tiles' icons, spanning the name,
        # where the apps install from and the row of pills.
        header = QHBoxLayout()
        header.setSpacing(14)
        if LOGO_PATH.is_file():
            self.logo = ClickableLogo(LOGO_PATH, ICON_PX)
            self.logo.setToolTip("Open the wiki in the browser")
            self.logo.clicked.connect(self.open_wiki)
            header.addWidget(self.logo)
        words = self.header_words = QVBoxLayout()
        words.setSpacing(4)
        title_row = QHBoxLayout()
        title = QLabel(f"{APP_NAME}  <span style='color:{muted()}; font-size:16px;'>v{__version__}</span>")
        title.setStyleSheet(header_font() + "font-size:32px; font-weight:800;")
        title.setToolTip(f"{APP_NAME} {__version__} · core {CORE_VERSION}")
        title_row.addWidget(title)
        self.stage = QLabel(STAGE)
        self.stage.setObjectName("stage")
        self.stage.setStyleSheet(f"background:{ACCENT}; color:white; font-weight:700; font-size:12px; "
                                 "border-radius:6px; padding:2px 8px;")
        self.stage.setToolTip(STAGE_NOTE)
        self.stage.setVisible(bool(STAGE))
        title_row.addWidget(self.stage, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch(1)
        words.addLayout(title_row)
        title_row.addLayout(updates := QHBoxLayout())   # a newer portal: shown only when there is one
        source = ("Development: apps install from the local checkout " + str(sources.checkout) if sources.local
                  else "Apps install from the releases this portal version pins, verified by checksum.")
        self.source_label = hint_label(source)
        words.addWidget(self.source_label)
        self.portal_button = QPushButton()
        self.portal_button.setStyleSheet(f"color:{RED}; font-weight:700;")
        self.portal_button.clicked.connect(self._open_portal_release)
        self.portal_button.hide()
        updates.addWidget(self.portal_button)
        self.portal_release: ReleaseInfo | None = None
        self.restart_button = QPushButton()
        self.restart_button.setStyleSheet(f"color:{RED}; font-weight:700;")
        self.restart_button.clicked.connect(self.restart_portal)
        self.restart_button.hide()
        updates.addWidget(self.restart_button)
        words.addStretch(1)
        self.pill_box = QWidget()                       # the pills: one row where it fits, else as many as do
        self.pill_grid = QGridLayout(self.pill_box)
        self.pill_grid.setContentsMargins(0, 0, 0, 0)
        self.pill_grid.setSpacing(8)
        self.pill_columns = 0
        words.addWidget(self.pill_box)
        header.addLayout(words, 1)
        self.refresh_pill = Pill("Refresh", "Click to refresh", "Look again at which apps are installed.",
                                 PILL_COLOUR)
        self.refresh_pill.clicked.connect(self._on_refresh)
        self.installed_pill = Pill("0/0", "Installed apps", colour=PILL_COLOUR)
        self.installed_pill.setCursor(Qt.CursorShape.ArrowCursor)      # it only shows
        self.installed_pill.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.updates_pill = Pill("0", "Install all updates", colour=PILL_COLOUR)
        self.updates_pill.clicked.connect(self.install_all)
        self.icons_box = TogglePill(
            "Icons on Desktop", "On: every installed app gets an icon on the Desktop. Off: only the portal's icon is "
            "there, and you start the apps from here. The apps stay in the app menu either way. Click to switch.",
            self.settings.value(DESKTOP_ICONS_KEY, False, type=bool))
        self.icons_box.toggled.connect(self._show_icons)
        self.theme_pill = Pill(THEMES[theme_name()].label, "Theme switcher",
                               "The look of every app in the suite. Click for the next theme; an app takes it the "
                               "next time it starts.", PILL_COLOUR)
        self.theme_pill.clicked.connect(self._next_theme)
        self.wallpaper_pill = Pill("None", "Wallpaper", colour=PILL_COLOUR)
        self.wallpaper_pill.clicked.connect(self._wallpaper_menu)
        self.sysinfo_pill = Pill("Sys info", "Click to view",
                                 "The board, BIOS, CPU, GPU, memory, drives and OS, as the system reports them.",
                                 PILL_COLOUR)
        self.sysinfo_pill.clicked.connect(self.show_sysinfo)
        self.sysinfo_window: SysInfoDialog | None = None
        self.sound_tip = ("A swoosh when the portal opens, and the sound of the intro of " + BIG_NAME +
                          ". Click to switch.")
        self.sound_box = TogglePill("Sound", self.sound_tip, self.sounds.enabled)
        self.sound_box.toggled.connect(self._set_sound)
        self.mode_pill = Pill("Desktop", "Suite mode", colour=PILL_COLOUR)
        self.mode_pill.clicked.connect(self.toggle_mode)
        header_pills = [self.refresh_pill, self.installed_pill, self.updates_pill, self.icons_box, self.sound_box,
                        self.theme_pill, self.wallpaper_pill, self.mode_pill, self.sysinfo_pill]
        self.header_pills = header_pills
        same_width(header_pills)                        # owner, 20-10-2026
        self.theme_note = hint_label("The theme changes in each app the next time it starts, the portal too.")
        self.theme_note.hide()
        self.pill_box.installEventFilter(self)
        self.pill_box.setMinimumWidth(1)                # the window may be as narrow as one pill: the rest wraps
        self.reflow_pills(len(header_pills))
        root.addLayout(header)

        self.columns = 0
        self.cards: dict[str, AppTile] = {}
        for entry in entries:
            card = AppTile(entry)
            card.install_clicked.connect(self.install)
            card.uninstall_clicked.connect(self.uninstall)
            card.open_clicked.connect(self.open_app)
            self.cards[entry.key] = card

        # The notice of updates, above the tabs: on every tab (owner, 18-10-2026). Bazzite Test is the first tile on
        # its own tab, Sustainable (owner, 20-10-2026): the manifest lists the required app first.
        top = QHBoxLayout()
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setTextFormat(Qt.TextFormat.RichText)
        self.notice.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.notice.linkActivated.connect(self.show_app)
        top.addWidget(self.notice, 1)
        root.addLayout(top)

        # A tab per category with apps on it, in the order of CATEGORIES.
        self.tabs = QTabWidget()
        self.tabs.setTabBar(PillTabBar(self.refresh_pill))
        self.tabs.setDocumentMode(True)
        self.pages: dict[str, QScrollArea] = {}
        self.grids: dict[str, QGridLayout] = {}
        for category, label in CATEGORIES.items():
            if not any(e.category == category for e in entries):
                continue
            content = QWidget()
            column = QVBoxLayout(content)
            column.setContentsMargins(PAGE_MARGIN // 2, PAGE_MARGIN // 2, PAGE_MARGIN // 2, PAGE_MARGIN // 2)
            column.addWidget(hint_label(CATEGORY_HINTS[category]))
            grid = self._tile_grid()
            column.addLayout(grid)
            column.addStretch(1)
            page = QScrollArea()
            page.setWidgetResizable(True)
            page.setFrameShape(QFrame.Shape.NoFrame)
            page.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background:transparent; }")
            page.setWidget(content)
            page.installEventFilter(self)               # reflow when the page itself gets its new width
            self.pages[category], self.grids[category] = page, grid
            self.tabs.addTab(page, label)
            self.tabs.setTabToolTip(self.tabs.count() - 1, CATEGORY_HINTS[category])
        # The last tab is a button (owner, 26-10-2026): Install all apps, for the open category.
        self.install_tab = self.tabs.addTab(QWidget(), "Install all apps")
        self.tabs.setTabIcon(self.install_tab, glyphs.install(self.palette().color(QPalette.ColorRole.WindowText).name()))
        self.tabs.tabBar().action_index = self.install_tab
        self.tabs.tabBar().action_clicked.connect(self.install_missing)
        self._shown_tab = 0
        self.tabs.currentChanged.connect(self._tab_changed)
        self.tabs.currentChanged.connect(self.reflow)
        root.addWidget(self.tabs, 1)
        self.reflow()
        self.big = BigPicture(entries, CATEGORIES, CATEGORY_HINTS)
        self.big.set_veil(self.transparency())
        self.big.open_requested.connect(self._big_open)
        self.big.set_banner(self.local_banner.text())
        self.stack = QStackedWidget()               # Suite Desktop Mode (the window above), Suite Big Picture Mode
        self.stack.addWidget(central)
        self.stack.addWidget(self.big)
        self.stack.installEventFilter(self)         # the intro follows its size
        self.setCentralWidget(self.stack)
        QShortcut(QKeySequence("F11"), self, self.toggle_mode)
        self._desktop_geometry = None
        self._pill_index = 0
        self._show_sound()
        self._show_mode()
        self._show_wallpaper()

        self.poll = QTimer(self)
        self.poll.setInterval(POLL_MS)
        self.poll.timeout.connect(self._check_pending)
        restore_geometry(self, self.settings)
        self.marked: list[tuple[AppEntry, str]] = []
        self.refresh()
        self.portal_checker = UpdateChecker(self)
        self.portal_checker.finished.connect(self._portal_checked)
        if portal_check is not None:
            self.portal_checker.start(portal_check)
        QTimer.singleShot(0, self.settle_icons)          # once the window shows: it may ask
        QTimer.singleShot(0, self.remove_withdrawn)

    # ------------------------------------------------------------------------------------------- layout
    @staticmethod
    def _tile_grid() -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(TILE_SPACING)
        grid.setVerticalSpacing(TILE_SPACING)
        grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        return grid

    def column_count(self, width: int) -> int:
        return max(1, (width + TILE_SPACING) // (TILE_WIDTH + TILE_SPACING))

    def tab_of(self, entry: AppEntry) -> str:
        """The category of the tab that shows the app."""
        return entry.category

    def reflow(self) -> None:
        """Each tab's tiles in file order, left to right and then down, in as many columns as fit."""
        # The page's width less a scroll bar, whether one shows or not: a bar that comes and goes cannot switch the
        # layout back and forth. Every page has the width of the open one once it is shown.
        page = self.tabs.currentWidget()
        if page is None:
            return
        width = page.width() - page.verticalScrollBar().sizeHint().width() - PAGE_MARGIN
        columns = self.column_count(width)
        if columns == self.columns:
            return
        self.columns = columns
        for category, grid in self.grids.items():
            while grid.count():
                grid.takeAt(0)
            tiles = [c for c in self.cards.values() if self.tab_of(c.entry) == category]
            for i, tile in enumerate(tiles):
                grid.addWidget(tile, i // columns, i % columns)

    def reflow_pills(self, columns: int = 0) -> None:
        """The header's pills in a row when the window is wide enough (a TV, a desktop), else in as many rows as it
        takes (a 1280 px handheld screen), of the same length: as many columns as the width holds. The theme note follows
        the last pill."""
        width = max(pill.minimumWidth() for pill in self.header_pills)
        spacing = self.pill_grid.horizontalSpacing()
        count = len(self.header_pills)
        columns = columns or max(1, min(count, (self.pill_box.width() + spacing) // (width + spacing)))
        columns = -(-count // (-(-count // columns)))      # the rows are as even as can be: 5 and 4, not 8 and 1
        if columns == self.pill_columns:
            return
        self.pill_columns = columns
        while self.pill_grid.count():
            self.pill_grid.takeAt(0)
        for i, pill in enumerate(self.header_pills):
            self.pill_grid.addWidget(pill, i // columns, i % columns)
        last = len(self.header_pills)
        self.pill_grid.addWidget(self.theme_note, last // columns, last % columns, 1, columns - last % columns)

    def show_app(self, key: str) -> None:
        """Open the tab of the app and scroll to its tile: a link in the notice."""
        card = self.cards.get(key)
        page = self.pages.get(self.tab_of(card.entry)) if card else None
        if page is not None:
            self.tabs.setCurrentWidget(page)
            page.ensureWidgetVisible(card)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.pill_box:
            if event.type() == QEvent.Type.Resize:
                self.reflow_pills()
            elif event.type() == QEvent.Type.LayoutRequest and hasattr(self, "tabs"):
                self.tabs.tabBar().refit()          # a pill's new value made the pills wider or narrower
        elif watched in self.pages.values() and event.type() == QEvent.Type.Resize:
            self.reflow()
        elif self.intro is not None and watched is self.stack and event.type() == QEvent.Type.Resize:
            self.intro.setGeometry(self.stack.rect())
        return super().eventFilter(watched, event)

    # ------------------------------------------------------------------------------------------- state
    def busy(self) -> bool:
        return self.pending is not None or self._job is not None

    def refresh(self) -> None:
        marked: list[tuple[AppEntry, str]] = []
        for entry in self.entries:
            busy = ""
            if self._job and self._job[0] is entry:
                busy = "Downloading…" if not self.sources.local else "Preparing…"
            elif self.pending and self.pending.entry is entry:
                busy = "Installing…" if self.pending.action == "install" else "Removing…"
            card = self.cards[entry.key]
            state = card.show_state(is_installed(entry), self.records.get(entry.key), busy,
                                    from_checkout=self.sources.local)
            if state:
                marked.append((entry, state))
            if self.busy() and not busy:
                card.install_button.setEnabled(False)
                card.uninstall_button.setEnabled(False)
        self.marked = marked
        self.show_notice(marked)
        self.show_counts()
        self.check_installed()
        self.big.sync(self.cards)

    def show_counts(self) -> None:
        """The Installed apps pill (installed / listed, a withdrawn app not counted), the Install all updates pill
        (how many the notice names; during its batch, which one of how many) and the Install all apps tab."""
        listed = [entry for entry in self.entries if not entry.withdrawn]
        installed = sum(is_installed(entry) for entry in listed)
        self.installed_pill.set_value(f"{installed}/{len(listed)}", f"{installed} of the {len(listed)} apps in this "
                                      "portal are installed.")
        batch = self.batch is not None
        if batch and self.batch_pill is self.updates_pill:
            self._show_batch()
        else:
            count = len(self.marked)
            self.updates_pill.set_value(str(count), (
                f"Click to install {'all ' * (count > 1)}{count} the notice names (updates and reinstalls), one after "
                "the other. When an installer asks for your password, the next one waits "
                "until you typed it in its terminal and it has ended.") if count else
                "No updates: every installed app is the version this portal pins.")
            self.updates_pill.setEnabled(bool(count) and not self.busy())
        self._show_install_tab()

    def _show_batch(self) -> None:
        """The batch's progress: on the Install all updates pill, or on the Install all apps tab."""
        assert self.batch is not None
        done = self.batch_size - len(self.batch)
        tip = (f"Installing {self.batch_what[:-1]} {done} of {self.batch_size}, each in its own terminal. When one asks "
               "for your password, type it there: the next one starts when it has ended.")
        if self.batch_pill is None:
            self.tabs.setTabText(self.install_tab, f"Installing {done} of {self.batch_size}")
            self.tabs.setTabToolTip(self.install_tab, tip)
            self.tabs.setTabEnabled(self.install_tab, False)
            return
        self.batch_pill.set_value(f"{done}/{self.batch_size}", tip)
        self.batch_pill.setEnabled(False)

    def shown_category(self) -> str:
        """The category of the open tab (the action tab never opens)."""
        page = self.tabs.widget(self._shown_tab)
        return next((category for category, p in self.pages.items() if p is page), "")

    def _tab_changed(self, index: int) -> None:
        """The Install all apps tab never opens (the keyboard can land on it): back to the tab shown before. Its
        text follows the open category."""
        if index == self.install_tab:
            self.tabs.setCurrentIndex(self._shown_tab)
            return
        self._shown_tab = index
        self._show_install_tab()

    def _show_install_tab(self) -> None:
        """The Install all apps tab: enabled when the open category has apps not installed yet, disabled when every
        app of the category is installed; during its batch, which one of how many."""
        if self.batch is not None and self.batch_pill is None:
            self._show_batch()
            return
        category = self.shown_category()
        label = CATEGORIES.get(category, category)
        count = len(self.missing(category))
        self.tabs.setTabText(self.install_tab, "Install all apps")
        if count:
            tip = (f"Click to install {'all ' * (count > 1)}{count} app{'s' * (count != 1)} on {label} not installed "
                   "yet, one after the other, each in its own terminal. When an installer asks for your password, the "
                   "next one waits until you typed it there and it has ended.")
        else:
            tip = f"Every app on {label} is installed."
        self.tabs.setTabToolTip(self.install_tab, tip)
        self.tabs.setTabEnabled(self.install_tab, bool(count) and not self.busy())

    def missing(self, category: str) -> list[AppEntry]:
        """Install all apps: the listed apps of *category* that are not installed."""
        return [entry for entry in self.entries if self.tab_of(entry) == category and not entry.withdrawn
                and not is_installed(entry)]

    def outside_updates(self) -> list[tuple[AppEntry, upstream.Outside]]:
        """Updates outside the suite that an installed app can install now, as the apps last recorded them
        (bc250_core.upstream), in the order of the tiles."""
        recorded = upstream.read_all()
        return [(entry, outside) for entry in self.entries if entry.key in recorded and is_installed(entry)
                for outside in recorded[entry.key]]

    def show_notice(self, marked: list[tuple[AppEntry, str]]) -> None:
        """The notice beside check: each app with an update or a reinstall, linked to its tile; and on each tab's name
        the number of them on it. Below them the updates outside the suite an installed app can install now."""
        updates = sum(state == "update" for _, state in marked)
        reinstalls = len(marked) - updates
        outside = self.outside_updates()
        if not marked and outside:
            self.notice.setText("")
            self.notice.setToolTip("")
        elif not marked:
            self.notice.setText("<span style='color:gray;'>No updates: every installed app is the version this "
                                "portal pins.</span>")
            self.notice.setToolTip("")
        else:
            count = ", ".join([f"{updates} update{'s' if updates != 1 else ''}"] * bool(updates)
                              + [f"{reinstalls} reinstall{'s' if reinstalls != 1 else ''}"] * bool(reinstalls))
            lines = []
            for entry, state in marked:
                tab = self.tab_of(entry)
                where = f" ({CATEGORIES[tab]})" if tab else ""
                what = (f"update to v{entry.version}, installed {installed_from(self.records.get(entry.key))}"
                        if state == "update" else "reinstall needed, its version is unknown")
                lines.append(f"<a href='{escape(entry.key)}'>{escape(entry.short or short_name(entry.name))}</a>"
                             f"{escape(where)}: {escape(what)}")
            self.notice.setText(f"<b style='color:{RED};'>\u25cf {count}</b><br>" + "<br>".join(lines))
            self.notice.setToolTip(
                "Updates: apps whose installed version differs from the one this portal pins; each has a red dot in "
                "its icon, and its Install button updates it. Reinstalls: apps the portal did not install (by hand, "
                "or under an earlier name of the app), so their version is unknown; each has a red circular arrow in "
                "its icon, and its red button reinstalls it. Click a name to go to its tile.")
        if outside:
            lines = []
            for entry, update in outside:
                when = f" ({update.published})" if update.published else ""
                had = f", installed {update.installed}" if update.installed else ""
                tab = self.tab_of(entry)
                where = f" ({CATEGORIES[tab]})" if tab else ""
                lines.append(f"<a href='{escape(entry.key)}'>{escape(entry.short or short_name(entry.name))}</a>"
                             f"{escape(where)}: "
                             f"{escape(update.name)} {escape(update.latest)} is out{escape(when)}{escape(had)}. "
                             f"{escape(update.action)}")
            text = self.notice.text()
            self.notice.setText((text + "<br>" if text else "")
                                + f"<b style='color:{ORANGE};'>● Outside the suite</b><br>" + "<br>".join(lines))
            self.notice.setToolTip(((self.notice.toolTip() + "\n\n") if self.notice.toolTip() else "")
                                   + "Outside the suite: a newer release of a program an app installs in its newest "
                                   "version (not one it pins), as the app found when it last checked. The app "
                                   "installs it; click a name to go to its tile and open the app there.")
        for category, page in self.pages.items():
            n = sum(self.tab_of(entry) == category for entry, _ in marked)
            index = self.tabs.indexOf(page)
            self.tabs.setTabText(index, f"{CATEGORIES[category]}  \u25cf {n}" if n else CATEGORIES[category])
            self.tabs.tabBar().setTabTextColor(index, QColor(RED) if n else QColor())

    def _portal_checked(self, result: object) -> None:
        """A newer portal release brings newer pinned app versions; name them and offer its release page."""
        update = result if isinstance(result, PortalUpdate) else PortalUpdate(result) \
            if isinstance(result, ReleaseInfo) else None
        release = update.release if update else None
        if release is None or release.error or not release.version:
            return                                      # offline or no release yet: nothing to announce
        if version_tuple(release.version) <= version_tuple(__version__):
            return
        self.portal_release = release
        summary = update.summary()
        self.portal_button.setText(f"\u25cf Portal {release.version}" + (f": {summary}" if summary else " available"))
        if update.changes:
            tip = (f"Released {release.published}. App updates come with the portal: once it is updated, the "
                   f"installed apps among these show Update.\n\n{update.details()}\n\nClick to open its release page.")
        elif update.changes == []:
            tip = f"Released {release.published}. It pins the same app versions as this portal. Click to open its page."
        else:
            tip = (f"Released {release.published}. A new portal version pins newer app versions; "
                   "click to open its release page.")
        self.portal_button.setToolTip(tip)
        self.portal_button.setVisible(self.restart_button.isHidden())

    def check_installed(self) -> None:
        """A newer portal installed while this one runs (its install.sh, in a terminal): this window still runs the
        old one, with the old pins, and starting the portal again only brings this window to the front. So offer to
        restart into the new one; not while an install or uninstall runs."""
        try:
            version = (self.installed / "VERSION").read_text(encoding="utf-8").strip() if self.installed else ""
        except OSError:
            version = ""
        if not version or version == __version__:
            self.restart_button.hide()
            return
        self.restart_button.setText(f"\u25cf Restart: portal {version} is installed")
        busy = self.busy()
        self.restart_button.setEnabled(not busy)
        self.restart_button.setToolTip(
            f"Portal {version} was installed while this window runs portal {__version__}. Restart to use it: its "
            "app versions, and the red dot on the apps it updates."
            + ("\n\nAfter the install or uninstall that is running now." if busy else ""))
        self.restart_button.show()
        self.portal_button.hide()                       # the newer portal is here already

    def restart_portal(self) -> None:
        """Start the portal again, after this one is gone (it allows one window), and close this one."""
        if self.busy():
            return
        launcher = bin_home() / APP_ID
        if not self.launch(["sh", "-c", 'sleep 1; exec "$0"', str(launcher)]):
            QMessageBox.warning(self, APP_NAME, f"The portal could not be started again ({launcher}). Close this "
                                "window and start it from the app menu.")
            return
        self.close()
        QCoreApplication.quit()

    def changeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.check_installed()                      # back from the terminal that installed a new portal
            self.show_notice(self.marked)               # back from an app that checked its program's newest
        super().changeEvent(event)

    def _open_portal_release(self) -> None:
        if self.portal_release is not None:
            QDesktopServices.openUrl(QUrl(self.portal_release.url))

    @staticmethod
    def open_wiki() -> None:
        """The wiki's home page, from a click on the suite's logo."""
        QDesktopServices.openUrl(QUrl(SUITE_MANUAL_URL))

    # ----------------------------------------------------------------------------------------- actions
    def _confirm_board_change(self, entry: AppEntry, action: str) -> bool:
        if not entry.changes_board:
            return True
        answer = QMessageBox.warning(
            self, APP_NAME, BOARD_WARNING.format(name=entry.name, action=action),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        return answer == QMessageBox.StandardButton.Yes

    def settle_icons(self) -> None:
        """At start: ask the first time, when app icons are on the Desktop, whether to keep them; then, when they are
        switched off, remove the ones installers added since (an update of the portal puts Bazzite Test's back)."""
        if not self.settings.contains(DESKTOP_ICONS_KEY):
            show = bool(desktop_icons.on_desktop(self.desktop, self.menu)) and QMessageBox.question(
                self, APP_NAME, "Keep the app icons on the Desktop?\n\nThe portal starts every app, so its own icon "
                "is enough. The apps stay in the app menu either way, and you can change this any time with the "
                "\"Icons on Desktop\" pill at the top of the portal.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes) == QMessageBox.StandardButton.Yes
            self.settings.setValue(DESKTOP_ICONS_KEY, show)
            self.icons_box.blockSignals(True)
            self.icons_box.setChecked(show)
            self.icons_box.blockSignals(False)
        if not self.icons_box.isChecked():
            desktop_icons.remove(self.desktop, self.menu)

    def _next_theme(self) -> None:
        """The theme pill: the next theme, for every app; each takes it the next time it starts."""
        names = list(THEMES)
        name = names[(names.index(theme_name()) + 1) % len(names)]
        save_theme_name(name)
        self.theme_pill.set_value(THEMES[name].label, self.theme_pill.toolTip())
        self.theme_note.show()

    def _show_wallpaper(self) -> None:
        shown = wallpaper.shown()
        self.backdrop.set_picture(shown)
        self.big.set_picture(shown)
        value, what = ("None", "No picture behind the portal. ") if shown is None else \
            ("Example", "The portal's example picture behind it. ") if wallpaper.current() is None else \
            ("Custom", "Your own picture behind the portal. ")
        if shown is not None:
            what += f"Transparency {self.backdrop.veil} %. "
        self.wallpaper_pill.set_value(value, what + "Click to choose one, one used before, the example, or none, "
                                      "or to set its transparency. " + wallpaper.RULES)

    def transparency(self) -> int:
        """The wallpaper's transparency in %: how much of the theme's window color lies over it."""
        value = self.settings.value(VEIL_KEY, VEIL, type=int)
        return min(max(value, 0), VEIL_MAX)

    def set_transparency(self, percent: int) -> None:
        self.settings.setValue(VEIL_KEY, percent)
        self.backdrop.set_veil(percent)
        self.big.set_veil(percent)
        self._show_wallpaper()

    def _transparency_action(self, menu: QMenu) -> QWidgetAction:
        """The menu's slider for the wallpaper's transparency, which changes the window while it moves."""
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(12, 4, 12, 4)
        line.addWidget(QLabel("Transparency"))
        slider = self.transparency_slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, VEIL_MAX)
        slider.setSingleStep(VEIL_STEP)
        slider.setPageStep(VEIL_STEP * 2)
        slider.setTickInterval(VEIL_STEP * 2)
        slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        slider.setMinimumWidth(160)
        slider.setValue(self.backdrop.veil)
        slider.setToolTip("More: the theme's color over the picture, for a dark or busy one. Less: more of the "
                          "picture.")
        shown = QLabel(f"{slider.value()} %")
        shown.setMinimumWidth(shown.fontMetrics().horizontalAdvance("100 %"))
        line.addWidget(slider, 1)
        line.addWidget(shown)

        def moved(value: int) -> None:
            value = round(value / VEIL_STEP) * VEIL_STEP
            shown.setText(f"{value} %")
            self.set_transparency(value)

        slider.valueChanged.connect(moved)
        action = QWidgetAction(menu)
        action.setDefaultWidget(row)
        action.setText("Transparency")
        action.setEnabled(wallpaper.shown() is not None)
        return action

    def show_sysinfo(self) -> None:
        """The Sys info window, read again each time it opens; one at a time."""
        if self.sysinfo_window is None:
            self.sysinfo_window = SysInfoDialog(self)
        self.sysinfo_window.fill(sysinfo.collect())
        self.sysinfo_window.show()
        self.sysinfo_window.raise_()
        self.sysinfo_window.activateWindow()

    def _wallpaper_menu(self) -> None:
        self.wallpaper_menu().exec(self.wallpaper_pill.mapToGlobal(self.wallpaper_pill.rect().bottomLeft()))

    def wallpaper_menu(self) -> QMenu:
        """The Wallpaper pill's menu: choose a picture, the example, none, or one of those used before (newest
        first, under "Used before"): the current one ticked, one no longer where it was grayed out."""
        menu = QMenu(self)
        menu.addAction("Choose a picture…", self.choose_wallpaper)
        example = menu.addAction("Example wallpaper", self.example_wallpaper)
        example.setCheckable(True)
        example.setChecked(wallpaper.current() is None and wallpaper.shown() is not None)
        example.setEnabled(wallpaper.EXAMPLE.is_file() and not example.isChecked())
        menu.addAction("No wallpaper", self.remove_wallpaper).setEnabled(wallpaper.shown() is not None)
        menu.addSeparator()
        menu.addAction(self._transparency_action(menu))
        paths = wallpaper.saved()
        if not paths:
            return menu
        menu.addSection("Used before")
        current = wallpaper.current() is not None
        for index, path in enumerate(paths):
            here = path.is_file()
            action = menu.addAction(path.name if here else f"{path.name} (not found)",
                                    lambda p=path: self.apply_wallpaper(p))
            action.setToolTip(str(path) if here else f"{path}: moved or deleted since.")
            action.setCheckable(True)
            action.setChecked(current and index == 0)
            action.setEnabled(here and not action.isChecked())
        menu.setToolTipsVisible(True)
        return menu

    def choose_wallpaper(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, "Choose a wallpaper", str(Path.home()),
                                              "Pictures (*.png *.jpg *.jpeg *.webp)")
        if file:
            self.apply_wallpaper(Path(file))

    def apply_wallpaper(self, path: Path) -> None:
        """*path* as the wallpaper, first among the ones used before; a warning when it cannot be."""
        try:
            wallpaper.choose(path)
        except ValueError as exc:
            QMessageBox.warning(self, APP_NAME, f"This picture cannot be the wallpaper:\n\n{exc}")
            return
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"The wallpaper could not be saved:\n\n{exc}")
            return
        self._show_wallpaper()

    def remove_wallpaper(self) -> None:
        wallpaper.remove()
        self._show_wallpaper()

    def example_wallpaper(self) -> None:
        wallpaper.use_example()
        self._show_wallpaper()

    def _show_icons(self, show: bool) -> None:
        self.settings.setValue(DESKTOP_ICONS_KEY, show)
        try:
            desktop_icons.apply(show, self.desktop, self.menu)
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"The Desktop icons could not be changed:\n\n{exc}")

    # --------------------------------------------------------------------------------- sound and the modes
    def _show_sound(self) -> None:
        """The Sound pill and the Big Picture one: the user's choice, or No and disabled without an audio output."""
        available = self.sounds.available()
        on = self.sounds.enabled and available
        self.sound_box.blockSignals(True)
        self.sound_box.setChecked(on)
        self.sound_box.blockSignals(False)
        self.sound_box.set_value("Yes" if on else "No", self.sound_tip if available else audio.NO_OUTPUT)
        self.sound_box.setEnabled(available)

    def _set_sound(self, on: bool) -> None:
        self.sounds.enabled = on
        self.settings.setValue(SOUND_KEY, on)
        if not on:
            self.sounds.stop()
        self._show_sound()

    def in_big_picture(self) -> bool:
        return self.stack.currentWidget() is self.big

    def _show_mode(self) -> None:
        big = self.in_big_picture()
        self.mode_pill.set_value("BPM mode" if big else "Desktop", (
            f"You are in {BIG_NAME}. Click for {DESKTOP_NAME}, the window of apps in tabs (F11)." if big else
            f"You are in {DESKTOP_NAME}. Click for {BIG_NAME}: fullscreen, with large icons, for a TV and a "
            "controller (F11)."))

    def start_up(self) -> None:
        """Once the window shows: the swoosh, or the intro of Big Picture Mode when the portal last ran in it."""
        self._show_sound()
        if self.settings.value(MODE_KEY, "desktop", type=str) == "bigpicture":
            self.enter_big_picture()
        else:
            self.sounds.play(audio.SWOOSH)

    def toggle_mode(self) -> None:
        if self.in_big_picture():
            self.leave_big_picture()
        else:
            self.enter_big_picture()

    def enter_big_picture(self) -> None:
        if self.in_big_picture():
            return
        self._desktop_geometry = self.saveGeometry()
        self.settings.setValue(MODE_KEY, "bigpicture")
        self.big.sync(self.cards)
        self._pill_index = self.header_words.indexOf(self.pill_box)
        self.header_words.removeWidget(self.pill_box)
        self.big.place_pills(self.pill_box, self.header_pills)       # the same pills, under the title
        self.stack.setCurrentWidget(self.big)
        self.showFullScreen()
        self._show_mode()
        self._show_sound()
        self.gamepad.start()
        self.intro = Intro(self.stack)
        self.intro.finished.connect(self._intro_done)
        self.intro.skipped.connect(self.sounds.stop)
        self.intro.begin()
        self.sounds.play(audio.INTRO)

    def _intro_done(self) -> None:
        self.intro = None
        if self.in_big_picture():
            self.big.focus_first()

    def leave_big_picture(self) -> None:
        if not self.in_big_picture():
            return
        if self.intro is not None:
            self.intro.skip()
        self.gamepad.stop()
        self.sounds.stop()
        self.settings.setValue(MODE_KEY, "desktop")
        self.big.release_pills(self.pill_box)
        self.header_words.insertWidget(self._pill_index, self.pill_box)
        self.stack.setCurrentWidget(self.backdrop)
        self.showNormal()
        self._show_mode()
        self.sounds.play(audio.SWOOSH)                  # as when the portal opens in Suite Desktop Mode

    def _big_open(self, entry: AppEntry) -> None:
        """A tile in Big Picture Mode: open the app, ask for the installer of one that is not installed (it runs in a
        terminal, so the portal goes back to the desktop first)."""
        card = self.cards[entry.key]
        if entry.withdrawn or not card.busy_label.isHidden():
            return
        if not card.installed:
            answer = QMessageBox.question(
                self, APP_NAME, f"{entry.name} is not installed.\n\nInstalling runs its installer in a terminal, so "
                f"the portal switches to {DESKTOP_NAME} first. Install it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
            if answer == QMessageBox.StandardButton.Yes:
                self.leave_big_picture()
                self.install(entry)
            return
        if not entry.launch:
            return
        if len(entry.launch) == 1:
            self.open_app(entry, entry.launch[0][1])
            return
        menu = QMenu(self)
        for label, command in entry.launch:
            menu.addAction(label, lambda c=command: self.open_app(entry, c))
        tile = self.big.tiles[entry.key]
        menu.exec(tile.mapToGlobal(tile.rect().bottomLeft()))

    def _gamepad_action(self, action: str) -> None:
        """What the controller does reaches the portal as the keys it would press: in a menu or a dialog the keys
        Qt knows, in Big Picture Mode its own moves. Only while the portal's window has the focus."""
        if QApplication.activeWindow() is None:
            return
        if self.intro is not None:
            self.intro.skip()
            return
        popup, dialog = QApplication.activePopupWidget(), QApplication.activeModalWidget()
        if popup is not None or dialog is not None:
            target = popup or QApplication.focusWidget() or dialog
            keys = {"up": Qt.Key.Key_Up, "down": Qt.Key.Key_Down, "left": Qt.Key.Key_Left,
                    "right": Qt.Key.Key_Right, "back": Qt.Key.Key_Escape,
                    "accept": Qt.Key.Key_Return if popup is not None else Qt.Key.Key_Space}
            if popup is None:                           # a dialog's buttons: the focus moves with Tab
                keys.update(up=Qt.Key.Key_Backtab, left=Qt.Key.Key_Backtab, down=Qt.Key.Key_Tab,
                            right=Qt.Key.Key_Tab)
            key = keys.get(action)
            if key is not None and target is not None:
                for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                    QApplication.sendEvent(target, QKeyEvent(kind, key, Qt.KeyboardModifier.NoModifier))
            return
        if not self.in_big_picture():
            return
        if action in ("up", "down", "left", "right"):
            self.big.move_focus(action)
        elif action == "accept":
            item = self.big.focused_item()
            if item is not None:
                item.click()
            else:
                self.big.focus_first()
        elif action in ("previous", "next"):
            self.big.change_category(-1 if action == "previous" else 1)
        elif action == "mode":
            self.leave_big_picture()

    def remove_withdrawn(self) -> None:
        """A withdrawn app still on the board goes, one at a time, with its own uninstaller (the portal's uninstall,
        without the question): the next one when this one has ended. One that cannot be removed stays listed with
        its Uninstall button."""
        if self.busy():
            return
        for entry in self.entries:
            if entry.withdrawn and is_installed(entry) and entry.key not in self._withdrawal_tried:
                self._withdrawal_tried.add(entry.key)
                QMessageBox.information(
                    self, APP_NAME, f"{entry.name} is not available any more: its release was withdrawn.\n\n"
                    f"{entry.withdrawn}\n\nThe portal removes it now; its uninstaller runs in a terminal.")
                self._start(entry, "uninstall")
                return

    def install(self, entry: AppEntry) -> None:
        if self.busy() or not self._confirm_board_change(entry, f"Install {entry.name}"):
            return
        self._start(entry, "install")

    def uninstall(self, entry: AppEntry) -> None:
        if self.busy():
            return
        answer = QMessageBox.question(self, APP_NAME, f"Uninstall {entry.name}? Its own uninstaller runs in a "
                                      "terminal; settings and results are kept unless it asks otherwise.")
        if answer == QMessageBox.StandardButton.Yes:
            self._start(entry, "uninstall")

    def install_all(self) -> None:
        """Install all updates: every app the notice names, after one question (with the board warning when one of
        them changes the board), one after the other."""
        self._start_batch([entry for entry, _ in self.marked], "updates", self.updates_pill)

    def install_missing(self) -> None:
        """Install all apps: every app of the open category that is not installed yet, the same way (owner,
        26-10-2026); the tab shows the batch's progress."""
        category = self.shown_category()
        self._start_batch(self.missing(category), "apps", None, CATEGORIES.get(category, ""))

    def _start_batch(self, entries: list[AppEntry], what: str, pill: Pill | None, where: str = "") -> None:
        if self.busy() or not entries:
            return
        names = "".join(f"<li>{escape(entry.name)}"
                        + (f" <b style='color:{ORANGE};'>(changes the board)</b>" if entry.changes_board else "")
                        + "</li>" for entry in entries)
        board = [entry.name for entry in entries if entry.changes_board]
        warning = ("<p><b>Some of them change how your BC-250 runs</b> (clocks, voltages, unlocked units or firmware "
                   "tables). A wrong setting can make the board unstable or stop it from booting until the change is "
                   "undone: read their manuals first.</p>") if board else ""
        answer = QMessageBox.question(
            self, APP_NAME, f"<p>Install these {len(entries)} {what}{f' on {where}' if where else ''}, one after the "
            f"other?</p><ul>{names}</ul>{warning}<p>Each runs its installer in a terminal. When one asks for your "
            "password, type it there: the next one waits until it has ended.</p>",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.batch, self.batch_size, self.batch_failed = entries, len(entries), []
        self.batch_what, self.batch_pill = what, pill
        self._next_in_batch()

    def _next_in_batch(self) -> None:
        """The batch's next install; at its end, the ones that failed in one message."""
        if self.batch is None:
            return
        if self.batch:
            self._start(self.batch.pop(0), "install")
            return
        failed, self.batch = self.batch_failed, None
        self.refresh()
        if failed:
            QMessageBox.warning(self, APP_NAME, f"{len(failed)} of the {self.batch_size} {self.batch_what} did not "
                                "install:\n\n" + "\n".join(failed) + "\n\nTheir terminal windows show what happened; "
                                "the Install button on each tile tries again.")
        self.remove_withdrawn()

    def _start(self, entry: AppEntry, action: str) -> None:
        if self.in_big_picture():                       # the installer runs in a terminal: on the desktop
            self.leave_big_picture()
        self._job = (entry, action)
        self.refresh()
        self.worker.start(lambda: self._prepare(entry))

    def _prepare(self, entry: AppEntry) -> Path | Exception:
        """Worker thread: fetch or stage the app. Returns the folder, or the error to show."""
        try:
            return self.sources.prepare(entry)
        except (SourceError, OSError) as exc:
            return exc

    def _prepared(self, result: object) -> None:
        entry, action = self._job or (None, "")
        self._job = None
        if entry is None:
            return
        if isinstance(result, Exception):
            if self.batch is not None:
                self.batch_failed.append(f"{entry.name}: could not be prepared ({result})")
                self._next_in_batch()
                return
            QMessageBox.critical(self, APP_NAME, f"{entry.name} could not be prepared:\n\n{result}")
            self.refresh()
            return
        folder = Path(result)
        commands = entry.install if action == "install" else entry.uninstall
        # A fresh name; the terminal creates the file when the commands end.
        exit_file = Path(tempfile.gettempdir()) / f"bc250-portal-{entry.key}-{uuid.uuid4().hex}.exit"
        try:
            launch_in_terminal(shell_line(folder, commands), exit_file=exit_file, keep_open="on_error")
        except (RuntimeError, OSError) as exc:
            self.batch = None                           # no terminal for the next one either
            QMessageBox.critical(self, APP_NAME, f"Could not open a terminal for the installer:\n\n{exc}\n\n"
                                 f"Run it by hand instead:\n{shell_line(folder, commands)}")
            self.refresh()
            return
        self.pending = Pending(entry, action, exit_file, self._record_for(entry, folder))
        self.poll.start()
        self.refresh()

    def _record_for(self, entry: AppEntry, folder: Path) -> str:
        """What a finished install records: the release's tag; from a checkout, "local" with the staged app's
        version."""
        if not self.sources.local:
            return entry.tag
        try:
            return local_record((folder / "VERSION").read_text(encoding="utf-8").strip())
        except OSError:
            return local_record()

    def _check_pending(self) -> None:
        pending = self.pending
        if pending is None:
            self.poll.stop()
            return
        try:
            status = pending.exit_file.read_text(encoding="utf-8").strip()
        except OSError:
            return                                      # still running (or the terminal was closed: see Refresh)
        self.poll.stop()
        self.pending = None
        pending.exit_file.unlink(missing_ok=True)
        entry = pending.entry
        ok = status == "0"
        if ok and pending.action == "install":
            self.records.set(entry.key, pending.tag)
            self.sources.prune(entry)                   # an update: the previous release's folder goes
            if not self.icons_box.isChecked():          # the installer put its icon on the Desktop
                desktop_icons.remove(self.desktop, self.menu)
        elif ok:
            self.records.remove(entry.key)
            self.sources.forget(entry)
        if self.batch is not None:
            if not ok:
                self.batch_failed.append(f"{entry.name}: exit status {status or '?'}")
            self._next_in_batch()
            return
        self.refresh()
        if not ok:
            QMessageBox.warning(self, APP_NAME, f"The {pending.action} of {entry.name} ended with exit status "
                                f"{status or '?'}. Its terminal window shows what happened.")
        self.remove_withdrawn()                         # the next withdrawn app, if any

    def _on_refresh(self) -> None:
        if self.pending is not None:
            rest = f" The rest of the batch ({len(self.batch)}) is not installed then." if self.batch else ""
            answer = QMessageBox.question(
                self, APP_NAME, f"Still waiting for the {self.pending.action} of {self.pending.entry.name} to end in "
                f"its terminal window. Stop waiting (for example because that window was closed)?{rest}")
            if answer == QMessageBox.StandardButton.Yes:
                self.cancel_pending()
                return
        self.refresh()

    def cancel_pending(self) -> None:
        """Stop waiting for a terminal that was closed before its installer finished, and for the rest of a batch."""
        self.batch = None
        if self.pending is not None:
            self.pending.exit_file.unlink(missing_ok=True)
            self.pending = None
            self.poll.stop()
        self.refresh()

    def open_app(self, entry: AppEntry, command: str) -> None:
        if not self._confirm_board_change(entry, f"Open {entry.name}"):
            return
        argv = shlex.split(command)
        argv[0] = str(expand(argv[0]))
        try:
            subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"{entry.name} could not be started:\n\n{exc}")

    def closeEvent(self, event) -> None:
        if self.in_big_picture():                   # the window's own size, not the screen's
            self.settings.setValue(GEOMETRY_KEY, self._desktop_geometry)
        else:
            save_geometry(self, self.settings)
        self.gamepad.stop()
        self.sounds.stop()
        self.worker.stop(2000)
        self.portal_checker.stop(2000)
        super().closeEvent(event)
