# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the cards on the left (BIOS file, Setup screens, This device), what the focused one shows on the right,
the controller's buttons at the bottom. A on the BIOS file card picks a file in core's browser and reads its setup
screens; the Setup screens card lists the BIOS's pages, A opens a page or a menu, B goes back, LB and RB go to the
page before or the next one, Y shows what the BIOS hides; A on This device reads the device's BIOS version, then,
with Windows' administrator prompt, its settings (device.py: only read). Nothing runs before A asks for it (owner,
28-10-2026). Slow steps run off the window's thread."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, QTimer, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, browse, power
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private, suite_data
from bc250_core.portable import Card, Legend, PortableHeader, PortableWindow, px, status_clock

from . import APP_ID, APP_NAME, SUITE, __version__, bios, device, screens
from .bios import Bios, Identity, Key, Screens
from .hii import Form, FormSet
from .panes import InfoPane, ListPane, ScreenPane
from .screens import Entry, Page

STATUS_MS = 30_000              # the header's time and battery
CARDS_WIDTH = 360
HIDDEN_KEY = "show_hidden"      # the setting: Y shows what the BIOS hides
BROWSED = "bios"                # the browser's folder kept for next time (browse.remember)

FILE_INFO = (
    "The A button reads this device's own BIOS: the copy Windows keeps of the BIOS it installed, when the device's "
    "maker delivers its BIOS through Windows Update (ASUS does). No download and no administrator are needed.\n\n"
    "A BIOS file is the update the device's maker publishes: for the ROG Xbox Ally X, ASUS's zip with RC73XAAS.319 "
    "in it. The X button picks one with the controller: the zip itself, a .cap, .bin or .rom, or a file named like "
    "RC73XAAS.319. The app reads its setup screens, the BIOS's menus with every setting, and their defaults.\n\n"
    "It only reads: nothing is written, not to the file and not to the device. The file holds the defaults, not "
    "your own settings: the This device card reads those.")
SCREENS_INFO = (
    "The BIOS's menus, as its setup screen has them, hidden ones included. The A button opens a page or a menu, the "
    "B button goes back a menu, LB and RB go to the page before or the next one, and the Y button shows or hides "
    "what the BIOS hides: a hidden line is dimmed and in italics, and the page \"Not linked\" lists the menus no "
    "menu leads to.\n\n"
    "Each setting shows its value: this device's, once the This device card read it, else the file's default. The "
    "Menu button shows the focused line's help, its options, its default and where it is stored. Nothing can be "
    "changed here.")
DEVICE_INFO = (
    "The A button reads the device's BIOS version, as Windows reports it, and whether the BIOS file is that version. "
    "On an ASUS device it also asks ASUS's support site for the newest BIOS, so the card says whether this one is "
    "up to date; only the model the BIOS version starts with goes to the site. "
    "Then the A button reads the device's own settings: Windows keeps them for an administrator, so it asks each "
    "time. The app only reads them; it never writes one.\n\n"
    "A BIOS keeps many settings to itself once Windows runs; those stay unknown and show the file's default. The app "
    "never reads a variable that may hold personal data: Wi-Fi networks, network and boot entries, keys and "
    "passwords.\n\n"
    "When the file is another version than the device's BIOS, a setting may sit elsewhere in the device's BIOS, so a "
    "value read may be wrong: use the file of the version the device runs.")
BROWSE_INFO = (
    "Find the BIOS file. The A button opens the folder the focus is on, or takes the file; the B button goes a "
    "level up, and from the places back to the BIOS file card. The places are your usual folders and every drive.")


class _Worker(QObject):
    """Runs a slow step off the window's thread; done or failed arrive on the window's."""

    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.busy = False

    def start(self, work: Callable[[], object]) -> bool:
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=self._run, args=(work,), daemon=True).start()
        return True

    def _run(self, work: Callable[[], object]) -> None:
        try:
            result = work()
        except Exception as error:  # noqa: BLE001  (shown in the pane, not raised)
            self.busy = False
            self.failed.emit(str(error) or type(error).__name__)
            return
        self.busy = False
        self.done.emit(result)


class MainWindow(PortableWindow):
    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery,
                 load: Callable[[Path], Bios] = bios.load_file,
                 identify: Callable[[], tuple[Identity, str]] = device.identity,
                 read_settings: Callable[[Iterable[Key], Path], tuple[dict[Key, bytes], list[Key]]] =
                 device.read_settings,
                 settings: QSettings | None = None, folder: Path | None = None,
                 roots: Callable[[], list[Path]] = browse.drives, user_home: Path | None = None,
                 installed: Callable[[], Path] = device.installed_bios,
                 newest: Callable[[Identity], device.Newest] = device.newest_bios):
        """*installed*: the file of the BIOS this device runs, as Windows keeps it (raises DeviceError without one);
        *newest*: the maker's newest BIOS for the device (raises DeviceError when it is not known)."""
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.load, self.identify, self.read_settings = load, identify, read_settings
        self.installed, self.newest_of = installed, newest
        self.settings = settings or QSettings()
        self.folder = folder or suite_data(SUITE) / APP_ID          # the elevated read's two files
        self.roots, self.user_home = roots, user_home
        self.bios: Bios | None = None
        self.screens: Screens | None = None
        self.pages: list[Page] = []
        self.page = 0                                   # the page the open menu belongs to
        self.page_title = ""
        self.stack: list[tuple[FormSet, Form]] = []     # the open menus, the page's first
        self.entries: list[Entry] = []                  # the open menu's lines
        self.identity: Identity | None = None           # the device's BIOS, once A read it
        self.model = ""
        self.missing: list[Key] = []                    # the device's variables the BIOS keeps to itself
        self.read_done = False                          # the device's settings were read for this file
        self.from_device = False                        # the file is the BIOS this device runs (Windows' copy)
        self.loading_device = False                     # the file being read is
        self.newest: device.Newest | None = None        # the maker's newest BIOS, once looked up
        self.newest_error = ""                          # why it is not known
        self.looking = False                            # being looked up
        self.browser: browse.Browser | None = None

        page = QVBoxLayout(self)
        page.setContentsMargins(*self.margins())
        self.header = PortableHeader(APP_NAME, __version__)
        page.addWidget(self.header)
        page.addSpacing(px(14))
        body = QHBoxLayout()
        column = QWidget()
        column.setFixedWidth(px(CARDS_WIDTH))
        cards = QVBoxLayout(column)
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(px(12))
        self.file_card = Card("BIOS file", "")
        self.screens_card = Card("Setup screens", "")
        self.device_card = Card("This device", "")
        for card in (self.file_card, self.screens_card, self.device_card):
            card.setFixedHeight(px(100))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()
        self.file_pane = InfoPane("BIOS file", "This device's BIOS, or the maker's BIOS update: its setup screens "
                                  "and their defaults.", FILE_INFO, "This device's BIOS")
        self.browse_pane = ListPane("Pick the BIOS file", BROWSE_INFO)
        self.pages_pane = ListPane("Setup screens", SCREENS_INFO)
        self.screen_pane = ScreenPane(SCREENS_INFO)
        self.device_pane = InfoPane("This device", "The BIOS this device runs, and its own settings.", DEVICE_INFO,
                                    "Read")
        for pane in (self.file_pane, self.browse_pane, self.pages_pane, self.screen_pane, self.device_pane):
            self.panes.addWidget(pane)
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend()
        page.addWidget(self.legend)
        self.cards = {self.file_pane: self.file_card, self.browse_pane: self.file_card,
                      self.pages_pane: self.screens_card, self.screen_pane: self.screens_card,
                      self.device_pane: self.device_card}

        self.file_worker = _Worker()
        self.file_worker.done.connect(self.file_done)
        self.file_worker.failed.connect(self.file_failed)
        self.device_worker = _Worker()
        self.device_worker.done.connect(self.device_done)
        self.device_worker.failed.connect(self.device_failed)
        self.newest_worker = _Worker()
        self.newest_worker.done.connect(self.newest_done)
        self.newest_worker.failed.connect(self.newest_failed)
        self.file_card.focused.connect(lambda: self.show_pane(self.file_pane))
        self.file_card.activated.connect(self.file_action)
        self.screens_card.focused.connect(lambda: self.show_pane(self.screen_pane if self.stack else self.pages_pane))
        self.screens_card.activated.connect(self.enter_screens)
        self.device_card.focused.connect(lambda: self.show_pane(self.device_pane))
        self.device_card.activated.connect(self.device_step)
        self.browse_pane.list.picked.connect(self.browse_picked)
        self.pages_pane.list.picked.connect(lambda key: self.open_page(int(key)))
        self.screen_pane.list.picked.connect(self.entry_picked)
        self.screen_pane.list.current.connect(self.entry_focused)
        self.bind("accept", self.a_action)
        self.bind("y", self.toggle_hidden)
        self.bind("x", self.x_action)
        self.bind("previous", lambda: self.step_page(-1))
        self.bind("next", lambda: self.step_page(1))
        self.back.connect(self.on_back)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(self.update_status)
        self.show_file()
        self.show_pages()
        self.show_device()
        self.show_pane(self.file_pane)

    def start(self) -> None:
        """After the window is shown: the controller and the status line; nothing is read before A asks."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.file_card.setFocus()

    def update_status(self) -> None:
        self.header.set_status([*status_clock(), power.text(self.battery())])   # the battery last (owner, 30-10-2026)

    @property
    def show_hidden(self) -> bool:
        return str(self.settings.value(HIDDEN_KEY, "false")).lower() == "true"

    def show_pane(self, pane) -> None:
        """*pane* shows; when the focus was inside the pane before, it goes to *pane*'s card first: hidden with the
        focus, Qt would hand it to the first card, and B would go back there."""
        current = self.panes.currentWidget()
        if current is not pane and self.in_pane(current):
            self.cards[pane].setFocus()
        self.panes.setCurrentWidget(pane)
        self.update_legend()

    def focus_list(self, pane) -> None:
        """The list's first row, or the pane's card while the list is empty."""
        (pane.list.first() or self.cards[pane]).setFocus()

    def in_pane(self, pane) -> bool:
        focus = self.focusWidget()
        return focus is not None and pane.isAncestorOf(focus)

    def update_legend(self) -> None:
        """The pane's buttons, then core's Menu Info, B Back and View Exit (the suite's rule)."""
        if not hasattr(self, "legend"):
            return
        pane = self.panes.currentWidget()
        hidden = ("Y", "Hide hidden" if self.show_hidden else "Show hidden")
        back = None
        if pane is self.file_pane:
            items = [("A", self.file_pane.action), *([] if self.from_device else [("X", "Pick a file")])]
        elif pane is self.browse_pane:
            items, back = [("A", "Open")], True
        elif pane is self.pages_pane:
            items = [("A", "Open"), hidden]
        elif pane is self.screen_pane:
            entry = self.focused_entry()
            opens = [("A", "Open")] if entry is None or entry.link else []
            items = [*opens, ("LB", "Page before"), ("RB", "Next page"), hidden]
            back = True if self.in_pane(self.screen_pane) else None
        else:
            items = [("A", self.device_pane.action)]
        self.legend.set_items([*items, *self.common_items(back=back)])

    def a_action(self) -> None:
        """A beside a card (a tap on the legend's A, A in a pane): the pane's action, as A on its card."""
        pane = self.panes.currentWidget()
        if pane is self.file_pane:
            self.file_action()
        elif pane is self.browse_pane:
            self.focus_list(self.browse_pane)
        elif pane in (self.pages_pane, self.screen_pane):
            self.enter_screens()
        elif pane is self.device_pane:
            self.device_step()

    def on_back(self) -> None:
        """B: in the browser a level up, from its places back to the BIOS file card; in a menu the menu above it,
        from a page's first menu back to the pages; in a pane back to its card."""
        if self.panes.currentWidget() is self.browse_pane and self.browser is not None:
            if self.browser.up():
                self.show_browse()
            else:
                self.leave_browser()
            return
        if self.panes.currentWidget() is self.screen_pane and self.in_pane(self.screen_pane):
            if len(self.stack) > 1:
                fs, form = self.stack.pop()
                self.show_menu(back_from=form)
            else:
                self.stack = []
                self.show_pages()
                self.show_pane(self.pages_pane)
                row = self.pages_pane.list.pills.get(str(self.page))
                (row or self.pages_pane.list.first() or self.screens_card).setFocus()
            return
        self.go_back()

    # The BIOS file card

    def file_action(self) -> None:
        """A: this device's own BIOS (owner, 01-11-2026: no download needed), or, once that is read, another file."""
        if self.from_device and self.bios is not None:
            self.show_browser()
        else:
            self.read_device_bios()

    def x_action(self) -> None:
        """X on the BIOS file card: a file picked in the browser (A reads this device's own BIOS there)."""
        if self.panes.currentWidget() is self.file_pane and not self.from_device:
            self.show_browser()

    def read_device_bios(self) -> None:
        """The BIOS Windows installed on this device, found and read off the window's thread."""
        if self.file_worker.busy:
            self.file_pane.status.setText("Still reading the file before …")
            return
        self.loading_device = True
        self.file_pane.status.setText("Looking for the BIOS Windows installed on this device …")
        self.log.info("Looking for this device's BIOS in Windows' driver store.")
        self.file_worker.start(lambda: self.load(self.installed()))

    def show_file(self) -> None:
        loaded = self.bios
        if loaded is None:
            self.file_card.set_text("None yet: the A button reads this device's.")
            self.file_pane.show_rows([("File", "None yet")])
            self.file_pane.action = "This device's BIOS"
        else:
            version = loaded.identity.version or "version not named"
            self.file_card.set_text(f"This device's BIOS, {version}" if self.from_device else
                                    f"{loaded.name}, {version}")
            sc = self.screens
            settings = sum(1 for fs in loaded.formsets for form in fs.forms for st in form.statements
                           if st.is_question)
            hidden = sum(1 for _ in sc.hidden_forms()) if sc is not None else 0
            unlinked = len(sc.unlinked_forms()) if sc is not None else 0
            rows = [("File", loaded.name), ("Version", loaded.identity.version or "Not named in the file")]
            if self.from_device:
                rows.append(("From", "Windows' copy of the BIOS it installed on this device"))
            if loaded.identity.vendor:
                rows.append(("Maker of the BIOS", loaded.identity.vendor))
            rows += [("Setup screens", f"{len(loaded.formsets)} modules, {settings:,} settings"),
                     ("Hidden", f"{hidden} menus the BIOS hides, {unlinked} no menu links to"),
                     ("Defaults", f"{len(loaded.defaults)} variables" if loaded.defaults else "None in the file"),
                     ("SHA-256", loaded.sha256[:16] + " …")]
            self.file_pane.show_rows(rows)
            self.file_pane.action = "Pick another file" if self.from_device else "This device's BIOS"
        self.update_legend()

    def file_done(self, loaded: Bios) -> None:
        self.bios, self.from_device = loaded, self.loading_device
        self.read_done, self.missing = False, []
        self.stack, self.page = [], 0
        self.rebuild()
        self.file_pane.status.setText("Read: the Setup screens card shows its menus.")
        self.log.info(f"BIOS file read{' (this device' + chr(39) + 's, from Windows)' if self.from_device else ''}: "
                      f"{loaded.name}, version {loaded.identity.version or 'not named'}, "
                      f"{len(loaded.formsets)} modules, SHA-256 {loaded.sha256}.")
        self.show_device()

    def file_failed(self, error: str) -> None:
        if self.loading_device:                     # no copy found, or it could not be read: the error says which
            self.file_pane.status.setText(error)
            self.log.info(f"This device's BIOS: {error}")
            return
        self.file_pane.status.setText(f"That file could not be read: {error}")
        self.log.error(f"Reading a BIOS file failed: {error}")

    def rebuild(self) -> None:
        """The screens anew, after a file was read or the device's values came in."""
        self.screens = Screens(self.bios) if self.bios is not None else None
        self.show_file()
        self.show_pages()
        if self.stack:
            self.show_menu(focus=False)

    # The file browser (core's browse)

    def show_browser(self) -> None:
        if self.file_worker.busy:
            self.file_pane.status.setText("Still reading the file before …")
            return
        self.browser = browse.Browser(browse.places(self.user_home, self.roots), bios.SUFFIXES,
                                      path=browse.remembered(self.settings, BROWSED))
        self.browse_pane.status.setText("")
        self.show_pane(self.browse_pane)
        self.show_browse()

    def show_browse(self) -> None:
        path = self.browser.path if self.browser is not None else None
        self.browse_pane.summary.setText(private(path) if path is not None else
                                         "Where is the BIOS file? Open a place, then the folder it is in.")
        self.browse_pane.list.set_items(self.browser.rows() if self.browser is not None else [])
        self.focus_list(self.browse_pane)
        self.update_legend()

    def browse_picked(self, key: str) -> None:
        if self.browser is None:
            return
        picked = self.browser.open(key)
        if picked is None:
            self.show_browse()
            return
        browse.remember(self.settings, BROWSED, picked.parent)
        self.loading_device = False
        self.leave_browser()
        self.file_pane.status.setText(f"Reading {picked.name} …")
        self.file_worker.start(lambda: self.load(picked))

    def leave_browser(self) -> None:
        self.browser = None
        self.show_file()
        self.show_pane(self.file_pane)
        self.file_card.setFocus()

    # The Setup screens card

    def show_pages(self) -> None:
        self.pages = screens.pages(self.screens, self.show_hidden) if self.screens is not None else []
        if self.stack:                                  # the open page's place in the list, while it is in it
            self.page = next((n for n, p in enumerate(self.pages) if p.form is self.stack[0][1]),
                             min(self.page, max(len(self.pages) - 1, 0)))
        if self.bios is None:
            self.screens_card.set_text("Pick a BIOS file first.")
            self.pages_pane.summary.setText("The BIOS file card picks the file whose menus show here.")
        else:
            self.screens_card.set_text(f"{len(self.pages)} pages" + (", hidden ones too" if self.show_hidden else ""))
            self.pages_pane.summary.setText("The BIOS's pages, as its setup screen has them." +
                                            ("" if self.show_hidden else " The Y button shows the hidden ones too."))
        self.pages_pane.list.set_items([(str(n), page.title + ("  (hidden)" if page.hidden_reason else ""))
                                        for n, page in enumerate(self.pages)])

    def enter_screens(self) -> None:
        """A on the card: into the open menu, or the pages."""
        if self.bios is None:
            self.pages_pane.status.setText("Pick a BIOS file on the BIOS file card first.")
            return
        if self.stack:
            self.show_pane(self.screen_pane)
            self.focus_list(self.screen_pane)
        else:
            self.show_pane(self.pages_pane)
            self.focus_list(self.pages_pane)

    def open_page(self, index: int) -> None:
        if not self.pages:
            return
        self.page = index % len(self.pages)
        chosen = self.pages[self.page]
        self.page_title = chosen.title
        self.stack = [(chosen.formset, chosen.form)]
        self.show_pane(self.screen_pane)
        self.show_menu()

    def step_page(self, delta: int) -> None:
        """LB and RB in a menu: the page before or the next one."""
        if self.panes.currentWidget() is self.screen_pane and self.pages:
            self.open_page(self.page + delta)

    def show_menu(self, back_from: Form | None = None, focus: bool = True) -> None:
        """The open menu's lines; with *focus*, the focus on the first row, or, back from a menu, on the link that
        opened it (a refresh while another card shows leaves the focus where it is)."""
        if self.screens is None or not self.stack:
            return
        fs, form = self.stack[-1]
        self.entries = screens.entries(self.screens, fs, form, self.show_hidden, self.identity)
        self.screen_pane.title.setText(screens.short(form.title) or f"Form 0x{form.id:X}")
        trail = [self.page_title]
        trail += [screens.short(f.title) or f"Form 0x{f.id:X}" for _, f in self.stack[1:]]
        hidden = screens.form_hidden(self.screens, fs, form)
        note = screens.note(fs)
        self.screen_pane.path.setText("  ›  ".join(t for t in trail if t) +
                                      (f"  ·  hidden in the BIOS: {hidden}" if hidden else "") +
                                      (f"  ·  {note}" if note else ""))
        self.screen_pane.status.setText("" if self.entries else
                                        "Nothing to show here" + ("." if self.show_hidden else
                                                                  ": the Y button shows the hidden lines."))
        self.screen_pane.list.set_entries(self.entries)
        back = next((str(n) for n, e in enumerate(self.entries) if back_from is not None and e.link
                     and e.statement.target_form == back_from.id), "")
        row = self.screen_pane.list.pills.get(back) or self.screen_pane.list.first()
        if focus:
            (row or self.screens_card).setFocus()
        if row is None or not focus:
            self.screen_pane.line.setText("")
            self.screen_pane.set_detail("", "")
        self.update_legend()

    def focused_entry(self) -> Entry | None:
        key = self.screen_pane.list.focused()
        return self.entries[int(key)] if key and int(key) < len(self.entries) else None

    def entry_focused(self, key: str) -> None:
        entry = self.entries[int(key)] if int(key) < len(self.entries) else None
        if entry is None or entry.statement is None or self.screens is None or not self.stack:
            return
        fs, form = self.stack[-1]
        self.screen_pane.line.setText(screens.summary(self.screens, fs, form, entry.statement))
        self.screen_pane.set_detail(entry.prompt, screens.detail(self.screens, fs, form, entry.statement))
        self.update_legend()

    def entry_picked(self, key: str) -> None:
        entry = self.entries[int(key)] if int(key) < len(self.entries) else None
        if entry is None or self.screens is None or not self.stack:
            return
        if not entry.link:
            self.screen_pane.status.setText("Read only: the Menu button shows this setting's options.")
            return
        opened = screens.target(self.screens, self.stack[-1][0], entry.statement)
        if opened is None:
            self.screen_pane.status.setText("That menu is not in this file.")
            return
        self.stack.append(opened)
        self.show_menu()

    def toggle_hidden(self) -> None:
        """Y: what the BIOS hides, shown or not; the open menu stays open, the focus on its line when it still
        shows."""
        if self.panes.currentWidget() not in (self.pages_pane, self.screen_pane):
            return
        self.settings.setValue(HIDDEN_KEY, "false" if self.show_hidden else "true")
        focused = self.focused_entry()
        self.show_pages()
        if self.panes.currentWidget() is self.screen_pane and self.stack:
            self.show_menu()
            if focused is not None:
                at = next((str(n) for n, e in enumerate(self.entries) if e.statement is focused.statement), "")
                if (row := self.screen_pane.list.pills.get(at)) is not None:
                    row.setFocus()
        elif self.in_pane(self.pages_pane) or self.panes.currentWidget() is self.pages_pane:
            self.focus_list(self.pages_pane)
        self.update_legend()

    # The This device card

    def device_step(self) -> None:
        """A: the device's BIOS version first; then, with a file, its settings through Windows' prompt."""
        if self.device_worker.busy:
            self.device_pane.status.setText("Still reading the device's settings …")
            return
        if self.identity is None or self.bios is None:
            self.identity, self.model = self.identify()
            self.log.info(f"This device: {self.model or 'model not reported'}, BIOS "
                          f"{self.identity.version or 'not reported'} of {self.identity.date or 'no date'}.")
            self.device_pane.status.setText(self.next_text())
            self.look_up_newest()
            self.show_device()
            if self.stack:
                self.show_menu(focus=False)             # the BIOS's version texts show the device's
            return
        keys = device.wanted(self.bios.stores())
        self.device_pane.status.setText("Windows asks for an administrator: its prompt may be behind this window. "
                                        "The app only reads the settings.")
        self.log.info(f"Reading the device's settings: {len(keys)} variables, asking Windows for an administrator.")
        self.device_worker.start(lambda: self.read_settings(keys, self.folder))

    def look_up_newest(self) -> None:
        """The maker's newest BIOS, asked for off the window's thread (with the version, on A)."""
        found = self.identity
        if found is None or self.newest_worker.busy:
            return
        self.looking, self.newest, self.newest_error = True, None, ""    # before the answer can come
        self.newest_worker.start(lambda: self.newest_of(found))

    def newest_done(self, newest: device.Newest) -> None:
        self.looking, self.newest = False, newest
        self.log.info(f"The maker's newest BIOS: {newest.version}" + (f" of {newest.date}." if newest.date else "."))
        self.show_device()

    def newest_failed(self, error: str) -> None:
        self.looking, self.newest_error = False, error
        self.log.info(f"The maker's newest BIOS is not known: {error}.")
        self.show_device()

    def newest_text(self) -> str:
        """The Newest BIOS row: looking, up to date, an update out, or why it is not known."""
        if self.looking:
            return "Looking it up on the maker's site …"
        if self.newest is None:
            return f"Not known: {self.newest_error}" if self.newest_error else ""
        newest = self.newest.version + (f" of {self.newest.date}" if self.newest.date else "")
        current = device.up_to_date(self.identity, self.newest) if self.identity is not None else None
        if current is None:
            return f"{newest}: not compared, the device's version has no number"
        return f"{newest}: up to date" if current else f"{newest}: an update is out, from the maker's site"

    def next_text(self) -> str:
        if self.bios is None:
            return "Pick a BIOS file on the BIOS file card: its setup screens say which settings to read."
        return "The A button reads its settings: Windows asks for an administrator."

    def device_done(self, result) -> None:
        read, missing = result
        if self.bios is None:
            return
        self.bios.device = read
        self.missing, self.read_done = missing, True
        self.rebuild()
        self.show_device()
        self.device_pane.status.setText(f"Read {len(read)} of {len(read) + len(missing)}: the setup screens show "
                                        "this device's values where it has them.")
        self.log.info(f"The device's settings: {len(read)} variables read, {len(missing)} kept by the BIOS.")

    def device_failed(self, error: str) -> None:
        self.device_pane.status.setText(error)
        self.log.error(f"Reading the device's settings failed: {error}")

    def match_text(self) -> str:
        if self.identity is None or self.bios is None:
            return ""
        mine, theirs = self.identity.version, self.bios.identity.version
        if not mine or not theirs:
            return "Not known: " + ("the file names no version" if not theirs else "Windows reports no version")
        if mine == theirs:
            return f"Yes: both are {mine}"
        return f"No: the file is {theirs}, this device runs {mine}"

    def show_device(self) -> None:
        found = self.identity
        if found is None:
            self.device_card.set_text("The A button reads its BIOS version.")
            self.device_pane.show_rows([("BIOS", "Not read yet")])
            self.device_pane.action = "Read"
            self.update_legend()
            return
        current = device.up_to_date(found, self.newest) if self.newest is not None else None
        state = ", up to date" if current else f": {self.newest.version} is out" if current is False else ""
        self.device_card.set_text(f"BIOS {found.version}{state}" if found.version else
                                  "Its BIOS version is not reported.")
        rows = [("Device", self.model or "Not reported"), ("BIOS version", found.version or "Not reported"),
                ("BIOS date", found.date or "Not reported")]
        if newest := self.newest_text():
            rows.append(("Newest BIOS", newest))
        if found.vendor:
            rows.append(("Maker of the BIOS", found.vendor))
        if self.bios is not None:
            rows.append(("The file's version", self.match_text()))
            if self.read_done:
                read = len(self.bios.device)
                rows.append(("Settings", f"{read} variables read, {len(self.missing)} kept by the BIOS"))
                if self.bios.device:
                    rows.append(("Read", ", ".join(name for _, name in sorted(self.bios.device, key=lambda k: k[1]))))
            else:
                rows.append(("Settings", "Not read yet"))
        self.device_pane.show_rows(rows)
        self.device_pane.action = ("Read again" if self.read_done else "Read the settings") if self.bios else "Read"
        if self.bios is not None and self.match_text().startswith("No"):
            self.device_card.set_text(f"BIOS {found.version}: the file is another version.")
        self.update_legend()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        super().closeEvent(event)
