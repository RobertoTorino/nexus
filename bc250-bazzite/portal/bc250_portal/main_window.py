# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal window: one fullscreen view (bigpicture.py; owner, 01-11-2026: Suite Desktop Mode, the window of
tabs, is gone), opened by a short animated intro with its own sound. The header, as an app's header: the suite's
icon (a click opens the wiki), spanning the name with the version and the stage, a line that says what the open
category is for, and a row of square pills: Refresh, Installed apps (installed / listed), Install all updates,
Install all apps (both read Install, the counts in their tooltips), the Desktop icons (Yes or No; a click switches),
Sound, the theme (a click goes to the next one), the wallpaper and Sys info (a small window with what the system reports about the board, sysinfo.py). Then a
category strip (the category of the apps' icons, apps.toml) with the notice of updates beside it, and the tiles of
the open category; check is the first tile on Sustainable (owner, 20-10-2026). The portal always opens on the
first category (owner, 20-10-2026). Everything is reached with the keyboard, the mouse or a controller
(gamepad.py).

A tile: a click, Enter or A opens the app (an app with two windows asks which one), or offers to install one that
is not installed. Its menu (a right click, the Menu key or X) holds every action: Open, Install (Update, Reinstall)
and Uninstall. Install, update and uninstall run the app's own installer in a terminal window (they may ask for the
sudo password and print what they do); the portal watches for the exit file the terminal writes and then refreshes.
A terminal whose installer ended well closes by itself (owner, 26-10-2026); one that failed stays open with what
happened until Enter is pressed. An app that changes the board (unlocks, governor, ACPI) gets a warning before it
is installed or opened.

Updates: a red dot marks every tile whose installed app differs from the version this portal pins, a red circular
arrow every installed app the portal has no record of (installed by hand, or under an earlier name of the app: its
version is unknown, so it needs a reinstall). An app installed from a checkout is recorded with the checkout's
version of it: a portal from a release compares that with the version it pins, as it does a tag (an older record
without the version needs a reinstall); a portal from a checkout shows it as installed, whatever the pin, since the
checkout is what it installs. The red notice beside the category strip counts them; a click lists each one, and
choosing one goes to its tile. A category's name counts those on it, so none goes unseen on a category that is not
open. At start the portal looks for a newer portal release on GitHub (which is how newer app versions arrive).

Install all updates: every app the notice names (an update or a reinstall), one after the other, each in its own
terminal as a single install. An installer that asks for the sudo password waits for it in its terminal, and so
does the batch: the next one starts when it has ended. One question first, with the board warning when one of them
changes the board; one message at the end names those that failed. Install all apps (owner, 26-10-2026) installs
the same way every app of the open category that is not installed yet, so a portal installed for the first time
fills a category with one click.

Desktop icons: the portal's own icon is enough to reach every app, so the apps' icons on the Desktop are the user's
choice ("Icons on Desktop", desktop_icons.py). The first start asks when app icons are there; off, the portal
removes them at start and after each install (the installers write one), on, it adds one for every installed app.

Wallpaper: none until the user chooses one, the portal's example picture or one of their own, behind the view
(wallpaper.py), under a veil of the theme's window color so the text stays readable. A slider in the Wallpaper
pill's menu sets the veil, the picture's transparency (owner, 20-10-2026): a dark picture can take a stronger one,
so the icons on it stand out. A pill that is not active is half transparent, so the picture shows through it.

Sound (owner, 21-10-2026): the intro plays with its sound, and the Sound pill turns it off (the choice is kept;
without an audio output the pill is disabled and the portal silent)."""

from __future__ import annotations

import shlex
import subprocess
from html import escape
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePath

from PyQt6.QtCore import QCoreApplication, QEvent, QProcess, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QKeyEvent, QKeySequence, QPainter, QPalette, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QMenu,
    QMessageBox, QPushButton, QSlider, QVBoxLayout, QWidget, QWidgetAction,
)

from bc250_core import SUITE_MANUAL_URL, __version__ as CORE_VERSION, upstream
from bc250_core.platform import bin_home, expand, launch_in_terminal
from bc250_core.settings import open_settings
from bc250_core.theme import ORANGE, RED, THEMES, muted, save_theme_name, theme_name
from bc250_core.updates import ReleaseInfo, UpdateChecker, version_tuple
from bc250_core.widgets import Pill

from . import audio, desktop_icons, glyphs, sysinfo, wallpaper
from .bigpicture import BigPicture, HeaderPill, Intro
from .gamepad import Gamepad
from .looks import VEIL
from . import APP_ICONS, APP_ID, APP_NAME, INFO, STAGE, STAGE_NOTE, __version__
from .manifest import CATEGORIES, AppEntry
from .portal_update import PortalUpdate
from .sources import Records, SourceError, Sources, installed_from, is_installed, is_local, local_record, local_version

POLL_MS = 1000
VEIL_MAX = 90                   # the slider's end: the picture still shows; "No wallpaper" takes it away
VEIL_STEP = 5
VEIL_KEY = "portal/wallpaper_transparency"
DESKTOP_ICONS_KEY = "portal/desktop_icons"
SOUND_KEY = "portal/sound"
VALUE_PX = 300                  # a value in the Sys info window wraps beyond this width
SYSINFO_OPACITY = 85            # % of the window color behind the Sys info text: what lies behind shows through
LAUNCH_ICON_FILES = {("compute", "Unlock"): "cu-unlock", ("cores", "Unlock"): "cores-unlock"}  # else the app's
# What each category holds (docs/apps/categories.md says the same): the tooltip of its tab.
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


def shell_line(folder: PurePath, commands: tuple[str, ...]) -> str:
    """cd into the extracted app and run its commands in order, stopping at the first failure."""
    return " && ".join([f"cd {shlex.quote(str(folder))}", *commands])


def short_name(name: str) -> str:
    """The name on a tile: the suite's prefix is understood in the portal ("BC-250 Bazzite Test": "Bazzite Test")."""
    for prefix in ("BC-250 ", "BC250 "):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


class AppState:
    """What the portal knows of one app, as its tile shows it: its short name, whether it is installed, its state
    (Not installed, Installed, Update, Reinstall needed, App not available, or what runs on it), the red dot (an
    update) or the red circular arrow (a reinstall is needed), what its menu offers, and the text on hover."""

    def __init__(self, entry: AppEntry):
        self.entry = entry
        self.title = entry.short or short_name(entry.name)
        self.installed = False
        self.status = ""
        self.detail = ""
        self.busy = ""                      # "Downloading…", "Installing…", ...: what runs on it
        self.update = False
        self.reinstall = False
        self.opens = False                  # installed, idle, a program: a click opens it
        self.action = "Install"             # the menu's install entry: Install, Update or Reinstall
        self.action_tip = ""
        self.tooltip = ""
        self.outside = ""                   # a newer program outside the suite the app can install: on its tile
        file = APP_ICONS / f"{entry.key}.webp"
        self.icon = QIcon(str(file)) if file.is_file() else QIcon()      # the small icon, for the menu's Open
        self.has_icon = not self.icon.isNull()

    def launch_icon(self, label: str) -> QIcon:
        """The icon of one way to open the app (CU Bisect's Unlock has its own), else the app's."""
        own = APP_ICONS / f"{LAUNCH_ICON_FILES.get((self.entry.key, label), '')}.webp"
        return QIcon(str(own)) if (self.entry.key, label) in LAUNCH_ICON_FILES and own.is_file() else self.icon

    def show_state(self, installed: bool, installed_tag: str, busy: str = "", from_checkout: bool = False) -> str:
        """Take the app's state; "update" when an update is available, "reinstall" when a reinstall is needed, else
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
        self.update, self.reinstall = update, reinstall
        if busy:
            self.status, detail = busy, busy
        elif entry.withdrawn:
            self.status = "App not available"
            detail = (f"App not available: its release was withdrawn ({entry.withdrawn}). "
                      + ("The portal removes it from the board." if installed else "It cannot be installed."))
        elif not installed:
            self.status, detail = "Not installed", "Not installed: Install in its menu, or press it."
        elif update:
            self.status = "Update"
            detail = f"Update available: installed {installed_from(installed_tag)}, this portal pins {entry.tag}."
        elif reinstall:
            self.status = "Reinstall needed"
            detail = (("Reinstall needed: an earlier portal installed it from a suite checkout without recording "
                       "its version, so it is unknown. ") if from_other_checkout else
                      ("Reinstall needed: it is installed, but not by this portal (by hand, or under an earlier name "
                       "of the app), so its version is unknown. ")
                      ) + "Reinstall it from its menu."
        else:
            self.status = "Installed"
            detail = f"Installed {installed_from(installed_tag)}."
        self.detail = detail
        self.busy = busy
        self.installed = installed
        self.opens = installed and not busy and bool(entry.launch) and not entry.withdrawn
        how = ("Press it to open it." if len(entry.launch) == 1 else
               "Press it to open: " + ", ".join(label for label, _ in entry.launch) + "." if entry.launch else
               "Not a program: nothing to open.")
        source = entry.tag or "runs from the suite checkout"
        self.tooltip = (f"<p><b>{escape(entry.name)}</b></p><p>{escape(entry.summary)}</p>"
                        f"<p style='color:gray;'>{escape(detail)}<br>{escape(source)}"
                        + (f"<br>{escape(how)}" if installed else "") + "</p>")
        self.action = "Update" if update else "Reinstall" if (reinstall or installed) else "Install"
        self.action_tip = (f"{self.action} {entry.name}" + (f" v{entry.version}" if entry.tag else "")
                           if not entry.withdrawn else f"App not available: {entry.withdrawn}")
        return "update" if update else "reinstall" if reinstall else ""


class TogglePill(HeaderPill):
    """A pill that is on or off, Yes or No: a click switches it (as a check box, with its isChecked, setChecked and
    toggled)."""

    toggled = pyqtSignal(bool)

    def __init__(self, caption: str, tooltip: str = "", checked: bool = False):
        self.checked = checked
        super().__init__("Yes" if checked else "No", caption, tooltip)
        self.clicked.connect(lambda: self.setChecked(not self.checked))

    def isChecked(self) -> bool:  # noqa: N802 (as QCheckBox)
        return self.checked

    def setChecked(self, checked: bool) -> None:  # noqa: N802 (as QCheckBox)
        if checked == self.checked:
            return
        self.checked = checked
        self.set_value("Yes" if checked else "No", self.toolTip())
        self.toggled.emit(checked)


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
        self.resize(1600, 900)                          # the portal runs fullscreen; this when it is not

        self.states: dict[str, AppState] = {entry.key: AppState(entry) for entry in entries}
        self.big = BigPicture(entries, CATEGORIES, CATEGORY_HINTS, __version__, STAGE, STAGE_NOTE)
        self.big.set_veil(self.transparency())
        self.big.open_requested.connect(self._open_tile)
        self.big.menu_requested.connect(self._tile_menu)
        self.big.wiki_requested.connect(self.open_wiki)
        self.big.bar.currentChanged.connect(self._category_changed)
        self.big.notice.clicked.connect(self._notice_menu)
        self.big.outside.clicked.connect(self._outside_menu)
        self.big.installEventFilter(self)               # the intro follows its size
        self.setCentralWidget(self.big)
        # Escape closes the portal (owner, 01-11-2026), as B does; a menu or a question takes it first, and during
        # the intro it skips the intro.
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.escape)
        if local_build is not None:
            self.big.set_banner(f"Local build: this portal comes from the checkout {local_build}, "
                                "not from a published release.")
        source = ("Development: apps install from the local checkout " + str(sources.checkout) if sources.local
                  else "Apps install from the releases this portal version pins, verified by checksum.")
        self.source_text = source
        self.big.set_about(f"<p><b>{APP_NAME} {__version__}</b> · core {CORE_VERSION}"
                           + (f"<br>{escape(STAGE_NOTE)}" if STAGE else "") + f"</p><p>{escape(source)}</p>")

        # The title row's red buttons: a newer portal release on GitHub, and a restart into a portal installed
        # while this one runs.
        self.portal_button = QPushButton()
        self.portal_button.setStyleSheet(f"color:{RED}; font-weight:700; font-size:16px;")
        self.portal_button.clicked.connect(self._open_portal_release)
        self.portal_button.hide()
        self.big.add_title_widget(self.portal_button)
        self.portal_release: ReleaseInfo | None = None
        self.restart_button = QPushButton()
        self.restart_button.setStyleSheet(f"color:{RED}; font-weight:700; font-size:16px;")
        self.restart_button.clicked.connect(self.restart_portal)
        self.restart_button.hide()
        self.big.add_title_widget(self.restart_button)

        self.refresh_pill = HeaderPill("Refresh", "Click to refresh", "Look again at which apps are installed.")
        self.refresh_pill.clicked.connect(self._on_refresh)
        self.installed_pill = HeaderPill("0/0", "Installed apps")
        self.installed_pill.setCursor(Qt.CursorShape.ArrowCursor)      # it only shows
        self.installed_pill.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.updates_pill = HeaderPill("Install", "All updates")    # the count in its tooltip (owner, 01-11-2026)
        self.updates_pill.clicked.connect(self.install_all)
        self.apps_pill = HeaderPill("Install", "All apps")
        self.apps_pill.clicked.connect(self.install_missing)
        self.icons_box = TogglePill(
            "Icons on Desktop", "On: every installed app gets an icon on the Desktop. Off: only the portal's icon is "
            "there, and you start the apps from here. The apps stay in the app menu either way. Click to switch.",
            self.settings.value(DESKTOP_ICONS_KEY, False, type=bool))
        self.icons_box.toggled.connect(self._show_icons)
        self.sound_tip = "The sound of the intro when the portal opens. Click to switch."
        self.sound_box = TogglePill("Sound", self.sound_tip, self.sounds.enabled)
        self.sound_box.toggled.connect(self._set_sound)
        self.theme_pill = HeaderPill(THEMES[theme_name()].label, "Theme switcher",
                                     "The look of every app in the suite. Click for the next theme; each app takes "
                                     "it the next time it starts, the portal too.")
        self.theme_pill.clicked.connect(self._next_theme)
        self.wallpaper_pill = HeaderPill("None", "Wallpaper")
        self.wallpaper_pill.clicked.connect(self._wallpaper_menu)
        self.sysinfo_pill = HeaderPill("Sys info", "Click to view",
                                       "The board, BIOS, CPU, GPU, memory, drives and OS, as the system reports them.")
        self.sysinfo_pill.clicked.connect(self.show_sysinfo)
        self.sysinfo_window: SysInfoDialog | None = None
        self.header_pills = [self.refresh_pill, self.installed_pill, self.updates_pill, self.apps_pill,
                             self.icons_box, self.sound_box, self.theme_pill, self.wallpaper_pill, self.sysinfo_pill]
        self.big.place_pills(self.header_pills)

        self._show_sound()
        self._show_wallpaper()
        self.poll = QTimer(self)
        self.poll.setInterval(POLL_MS)
        self.poll.timeout.connect(self._check_pending)
        self.marked: list[tuple[AppEntry, str]] = []
        self.notice_lines: list[tuple[str, str]] = []       # the notice's menu: the app's key, its line
        self.outside_lines: list[tuple[str, str]] = []
        self.refresh()
        self.portal_checker = UpdateChecker(self)
        self.portal_checker.finished.connect(self._portal_checked)
        if portal_check is not None:
            self.portal_checker.start(portal_check)
        QTimer.singleShot(0, self.settle_icons)          # once the window shows: it may ask
        QTimer.singleShot(0, self.remove_withdrawn)

    # ------------------------------------------------------------------------------------------- layout
    def show_app(self, key: str) -> None:
        """Open the category of the app and put the focus on its tile: a line of the notice."""
        self.big.show_app(key)

    def eventFilter(self, watched, event) -> bool:
        if self.intro is not None and watched is self.big and event.type() == QEvent.Type.Resize:
            self.intro.setGeometry(self.big.rect())
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
            state = self.states[entry.key].show_state(is_installed(entry), self.records.get(entry.key), busy,
                                                      from_checkout=self.sources.local)
            if state:
                marked.append((entry, state))
        self.marked = marked
        self.show_notice(marked)
        self.show_counts()
        self.check_installed()

    def show_counts(self) -> None:
        """The Installed apps pill (installed / listed, a withdrawn app not counted), the Install all updates pill
        (enabled when the notice names any; during its batch, which one of how many) and the Install all apps pill."""
        listed = [entry for entry in self.entries if not entry.withdrawn]
        installed = sum(is_installed(entry) for entry in listed)
        self.installed_pill.set_value(f"{installed}/{len(listed)}", f"{installed} of the {len(listed)} apps in this "
                                      "portal are installed.")
        if self.batch is not None and self.batch_pill is self.updates_pill:
            self._show_batch()
        else:
            count = len(self.marked)
            self.updates_pill.set_value("Install", (
                f"Click to install {'all ' * (count > 1)}{count} the notice names (updates and reinstalls), one after "
                "the other. When an installer asks for your password, the next one waits "
                "until you typed it in its terminal and it has ended.") if count else
                "No updates: every installed app is the version this portal pins.")
            self.updates_pill.setEnabled(bool(count) and not self.busy())
        self._show_apps_pill()

    def _show_batch(self) -> None:
        """The batch's progress, on its pill: Install all updates or Install all apps."""
        assert self.batch is not None and self.batch_pill is not None
        done = self.batch_size - len(self.batch)
        self.batch_pill.set_value(f"{done}/{self.batch_size}", (
            f"Installing {self.batch_what[:-1]} {done} of {self.batch_size}, each in its own terminal. When one asks "
            "for your password, type it there: the next one starts when it has ended."))
        self.batch_pill.setEnabled(False)

    def shown_category(self) -> str:
        """The category that is open."""
        return self.big.current_category()

    def _category_changed(self, _index: int) -> None:
        # A bound method, not a lambda over self: a lambda would keep the window in a reference cycle, alive until
        # the interpreter's shutdown, where Qt is gone already (tools/portal_screenshot.py crashed at exit).
        self._show_apps_pill()

    def _show_apps_pill(self) -> None:
        """The Install all apps pill: enabled when the open category has apps not installed yet (how many, in its
        tooltip), disabled when every app of the category is installed; during its batch, which one of how many."""
        if self.batch is not None and self.batch_pill is self.apps_pill:
            self._show_batch()
            return
        category = self.shown_category()
        label = CATEGORIES.get(category, category)
        count = len(self.missing(category))
        if count:
            tip = (f"Click to install {'all ' * (count > 1)}{count} app{'s' * (count != 1)} on {label} not installed "
                   "yet, one after the other, each in its own terminal. When an installer asks for your password, the "
                   "next one waits until you typed it there and it has ended.")
        else:
            tip = f"Every app on {label} is installed."
        self.apps_pill.set_value("Install", tip)
        self.apps_pill.setEnabled(bool(count) and not self.busy())

    def missing(self, category: str) -> list[AppEntry]:
        """Install all apps: the listed apps of *category* that are not installed."""
        return [entry for entry in self.entries if entry.category == category and not entry.withdrawn
                and not is_installed(entry)]

    def outside_updates(self) -> list[tuple[AppEntry, upstream.Outside]]:
        """Updates outside the suite that an installed app can install now, as the apps last recorded them
        (bc250_core.upstream), in the order of the tiles."""
        recorded = upstream.read_all()
        return [(entry, outside) for entry in self.entries if entry.key in recorded and is_installed(entry)
                for outside in recorded[entry.key]]

    def show_notice(self, marked: list[tuple[AppEntry, str]]) -> None:
        """The red notice beside the category strip: how many apps have an update or need a reinstall; its menu
        names each one, and choosing one goes to its tile. On each category's name the number of them on it. Beside
        it, in orange, the updates outside the suite an installed app can install now, each on its tile too."""
        updates = sum(state == "update" for _, state in marked)
        reinstalls = len(marked) - updates
        self.notice_lines = []
        for entry, state in marked:
            where = f" ({CATEGORIES[entry.category]})" if entry.category in CATEGORIES else ""
            what = (f"update to v{entry.version}, installed {installed_from(self.records.get(entry.key))}"
                    if state == "update" else "reinstall needed, its version is unknown")
            self.notice_lines.append((entry.key, f"{entry.short or short_name(entry.name)}{where}: {what}"))
        count = ", ".join([f"{updates} update{'s' if updates != 1 else ''}"] * bool(updates)
                          + [f"{reinstalls} reinstall{'s' if reinstalls != 1 else ''}"] * bool(reinstalls))
        self.big.notice.set_notice(f"● {count}" if marked else "", (
            "Updates: apps whose installed version differs from the one this portal pins; each has a red dot in "
            "its icon, and Update in its menu installs the pinned version. Reinstalls: apps the portal did not "
            "install (by hand, or under an earlier name of the app), so their version is unknown; each has a red "
            "circular arrow in its icon, and Reinstall in its menu. Click to list them; choose one to go to its tile.")
            if marked else "")
        for state in self.states.values():
            state.outside = ""
        self.outside_lines = []
        for entry, update in self.outside_updates():
            when = f" ({update.published})" if update.published else ""
            had = f", installed {update.installed}" if update.installed else ""
            where = f" ({CATEGORIES[entry.category]})" if entry.category in CATEGORIES else ""
            self.outside_lines.append((entry.key, f"{entry.short or short_name(entry.name)}{where}: "
                                       f"{update.name} {update.latest} is out{when}{had}. {update.action}"))
            self.states[entry.key].outside = f"{update.name} {update.latest} is out"
        n = len(self.outside_lines)
        self.big.outside.set_notice(f"● {n} outside the suite" if n else "", (
            "Outside the suite: a newer release of a program an app installs in its newest version (not one it "
            "pins), as the app found when it last checked. The app installs it; click to list them, and choose one "
            "to go to its tile and open the app there.") if n else "")
        counts: dict[str, int] = {}
        for entry, _ in marked:
            counts[entry.category] = counts.get(entry.category, 0) + 1
        self.big.set_counts(counts)
        self.big.sync(self.states)

    def notice_menu(self) -> QMenu:
        """The notice's list: each app with an update or a reinstall; choosing one goes to its tile."""
        return self._lines_menu(self.notice_lines)

    def outside_menu(self) -> QMenu:
        return self._lines_menu(self.outside_lines)

    def _lines_menu(self, lines: list[tuple[str, str]]) -> QMenu:
        menu = QMenu(self)
        for key, line in lines:
            menu.addAction(self.states[key].icon, line).setData(("show", key, ""))
        menu.triggered.connect(self._menu_action)
        return menu

    def _notice_menu(self) -> None:
        self._show_menu(self.notice_menu(), self.big.notice)

    def _outside_menu(self) -> None:
        self._show_menu(self.outside_menu(), self.big.outside)

    def _show_menu(self, menu: QMenu, under: QWidget) -> None:
        menu.exec(under.mapToGlobal(under.rect().bottomLeft()))
        menu.deleteLater()

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
        self.portal_button.setText(f"● Portal {release.version}" + (f": {summary}" if summary else " available"))
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
        self.restart_button.setText(f"● Restart: portal {version} is installed")
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
        """The wiki's home page, from a click on the suite's icon."""
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

    def _show_wallpaper(self) -> None:
        shown = wallpaper.shown()
        self.big.set_picture(shown)
        value, what = ("None", "No picture behind the portal. ") if shown is None else \
            ("Example", "The portal's example picture behind it. ") if wallpaper.current() is None else \
            ("Custom", "Your own picture behind the portal. ")
        if shown is not None:
            what += f"Transparency {self.big.veil} %. "
        self.wallpaper_pill.set_value(value, what + "Click to choose one, one used before, the example, or none, "
                                      "or to set its transparency. " + wallpaper.RULES)

    def transparency(self) -> int:
        """The wallpaper's transparency in %: how much of the theme's window color lies over it."""
        value = self.settings.value(VEIL_KEY, VEIL, type=int)
        return min(max(value, 0), VEIL_MAX)

    def set_transparency(self, percent: int) -> None:
        self.settings.setValue(VEIL_KEY, percent)
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
        slider.setValue(self.big.veil)
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

    # --------------------------------------------------------------------------------- sound and the intro
    def _show_sound(self) -> None:
        """The Sound pill: the user's choice, or No and disabled without an audio output."""
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

    def start_up(self) -> None:
        """Once the window is shown: the intro over it, with its sound, and the controller; when the intro ends,
        the focus is on the first tile."""
        self._show_sound()
        self.gamepad.start()
        self.intro = Intro(self.big)
        self.intro.finished.connect(self._intro_done)
        self.intro.skipped.connect(self.sounds.stop)
        self.intro.begin()
        self.sounds.play(audio.INTRO)

    def _intro_done(self) -> None:
        self.intro = None
        self.big.focus_first()

    def escape(self) -> None:
        """Escape, or B with nothing open: skip the intro while it plays, else close the portal."""
        if self.intro is not None:
            self.intro.skip()
        else:
            self.close()

    # ---------------------------------------------------------------------------------------- the tiles
    def _open_tile(self, entry: AppEntry) -> None:
        """A tile pressed: open the app (one with two windows asks which one), or offer to install one that is not
        installed."""
        state = self.states[entry.key]
        if entry.withdrawn or state.busy:
            return
        if not state.installed:
            self.install_from_tile(entry)
            return
        if not entry.launch:
            return
        if len(entry.launch) == 1:
            self.open_app(entry, entry.launch[0][1])
            return
        menu = QMenu(self)
        for label, command in entry.launch:
            menu.addAction(state.launch_icon(label), label).setData(("open", entry.key, command))
        menu.triggered.connect(self._menu_action)
        tile = self.big.tiles[entry.key]
        menu.exec(tile.mapToGlobal(tile.rect().bottomLeft()))
        menu.deleteLater()

    def install_from_tile(self, entry: AppEntry) -> None:
        """A tile of an app that is not installed: install it after one question; for an app that changes the board
        the board warning is that question."""
        if self.busy() or entry.withdrawn:
            return
        if entry.changes_board:
            self.install(entry)
            return
        answer = QMessageBox.question(
            self, APP_NAME, f"Install {entry.name}?\n\nIts installer runs in a terminal window; the portal refreshes "
            "when it has ended.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if answer == QMessageBox.StandardButton.Yes:
            self._start(entry, "install")

    def tile_menu(self, entry: AppEntry) -> QMenu:
        """A tile's menu, every action on the app: Open (each window of an app with two), Install (Update,
        Reinstall) and, for every app but check, Uninstall. What cannot be done now is grayed out."""
        # The actions carry what to do as data and one bound method does it (_menu_action): a lambda over self in
        # a menu that is the window's child would keep the window in a reference cycle.
        state = self.states[entry.key]
        ink = self.palette().color(QPalette.ColorRole.WindowText).name()
        menu = QMenu(self)
        if entry.launch:
            for label, command in entry.launch:
                action = menu.addAction(state.launch_icon(label), label if len(entry.launch) > 1 else "Open")
                action.setData(("open", entry.key, command))
                action.setEnabled(state.opens)
            menu.addSeparator()
        install = menu.addAction(glyphs.reinstall(RED) if state.reinstall else
                                 glyphs.install(RED if state.update else ink), state.action)
        install.setData(("install", entry.key, ""))
        install.setToolTip(state.action_tip)
        install.setEnabled(not self.busy() and not entry.withdrawn)
        if not entry.required:                          # check goes with the portal (install.sh --uninstall)
            uninstall = menu.addAction(glyphs.uninstall(ink), "Uninstall")
            uninstall.setData(("uninstall", entry.key, ""))
            uninstall.setEnabled(state.installed and not self.busy())
        menu.setToolTipsVisible(True)
        menu.triggered.connect(self._menu_action)
        return menu

    def _menu_action(self, action) -> None:
        """What an entry of a tile's menu, the launch menu or a notice's menu does, from the entry's data."""
        kind, key, command = action.data()
        entry = self.states[key].entry
        if kind == "open":
            self.open_app(entry, command)
        elif kind == "install":
            self.install(entry)
        elif kind == "uninstall":
            self.uninstall(entry)
        elif kind == "show":
            self.show_app(key)

    def _tile_menu(self, entry: AppEntry) -> None:
        tile = self.big.tiles[entry.key]
        menu = self.tile_menu(entry)
        menu.exec(tile.mapToGlobal(tile.rect().bottomLeft()))
        menu.deleteLater()

    def _gamepad_action(self, action: str) -> None:
        """What the controller does reaches the portal as the keys it would press: in a menu or a dialog the keys
        Qt knows, in the view its own moves. Only while the portal's window has the focus."""
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
        if action in ("up", "down", "left", "right"):
            self.big.move_focus(action)
        elif action == "accept":
            item = self.big.focused_item()
            if item is not None:
                item.click()
            else:
                self.big.focus_first()
        elif action == "menu":
            tile = self.big.focused_tile()
            if tile is not None:
                self._tile_menu(self.states[tile.key].entry)
        elif action in ("previous", "next"):
            self.big.change_category(-1 if action == "previous" else 1)
        elif action == "back":
            self.escape()

    def remove_withdrawn(self) -> None:
        """A withdrawn app still on the board goes, one at a time, with its own uninstaller (the portal's uninstall,
        without the question): the next one when this one has ended. One that cannot be removed stays listed with
        Uninstall in its menu."""
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
        26-10-2026); its pill shows the batch's progress."""
        category = self.shown_category()
        self._start_batch(self.missing(category), "apps", self.apps_pill, CATEGORIES.get(category, ""))

    def _start_batch(self, entries: list[AppEntry], what: str, pill: Pill, where: str = "") -> None:
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
                                "Install in each tile's menu tries again.")
        self.remove_withdrawn()

    def _start(self, entry: AppEntry, action: str) -> None:
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
        if self.intro is not None:
            self.intro.skip()
        self.gamepad.stop()
        self.sounds.stop()
        self.worker.stop(2000)
        self.portal_checker.stop(2000)
        super().closeEvent(event)
