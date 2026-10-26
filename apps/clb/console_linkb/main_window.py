# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window: the Microsoft account as the first step (sign in with a code, sign out), then the account's
Xbox consoles and the games of Xbox Cloud Gaming, each list with its buttons. Every call to Microsoft runs off the
GUI thread; the stream opens in a window of its own. The look is the app's own blue (style.py)."""

from __future__ import annotations

from collections.abc import Callable
from html import escape

from PyQt6.QtCore import QLocale, Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (QAbstractItemView, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QMainWindow, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
                             QVBoxLayout, QWidget)

from bc250_core import SUITE_MANUAL_URL, window_title
from bc250_core import __version__ as CORE_VERSION
from bc250_core.settings import SettingsStore
from bc250_core.updates import UpdateChecker
from bc250_core.widgets import AppHeader, MetricBox, StatusText, Terminal, hint_label

from . import APP_NAME, INFO, LOGO_PATH, __version__, auth, privacy, style, xbox
from .auth import Account, AuthError, DeviceCode, SignedOut
from .net import HttpError
from .stream import Stream
from .stream_window import StreamWindow

MANUAL_URL = f"{SUITE_MANUAL_URL}apps/clb/"
OFFERINGS = {auth.CLOUD: "Game Pass", auth.CLOUD_FREE: "Free to play"}


class LinkSettings(SettingsStore):
    DEFAULTS: dict = {}


def locale_name() -> str:
    """The system's language for the games, as the service wants it (en-US)."""
    name = QLocale.system().name().replace("_", "-")
    return name if "-" in name else "en-US"


class MainWindow(QMainWindow):
    def __init__(self, account: Account | None = None,
                 stream_window: Callable[[Stream, str], QWidget] = StreamWindow):
        """*account*: the Microsoft account (tests give one with recorded answers); *stream_window*: makes the
        stream's window."""
        super().__init__()
        self.resize(980, 700)
        self.account = account or Account()
        self.make_stream_window = stream_window
        self.settings = LinkSettings(INFO, self)
        self.worker = UpdateChecker(self)               # one call to Microsoft at a time, off the GUI thread
        self.worker.finished.connect(self._job_done)
        self.sign_in_worker = UpdateChecker(self)       # waiting for the code to be entered: up to 15 minutes
        self.sign_in_worker.finished.connect(self._signed_in)
        self.code: DeviceCode | None = None
        self.cancel_sign_in = False
        self.gamertag = ""
        self.consoles: list[xbox.Console] = []
        self.titles: list[xbox.CloudTitle] = []
        self.cloud_note = ""                            # why there are no cloud games, when there are none
        self.stream_view: QWidget | None = None

        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.pill = StatusText()
        header.add_state(self.pill)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Ask Xbox Live again for the consoles and the cloud games")
        self.refresh_button.clicked.connect(self.refresh)
        header.add_action(self.refresh_button)
        self.account_box = MetricBox("Account", style.BLUE)
        self.consoles_box = MetricBox("Consoles", style.BLUE)
        self.cloud_box = MetricBox("Cloud", style.BLUE)
        for box in (self.account_box, self.consoles_box, self.cloud_box):
            header.add_second(box)
        intro = hint_label(
            "Xbox games on the BC-250: stream your own Xbox (Remote Play) or a game from Xbox Cloud Gaming. Sign "
            "in with your Microsoft account; the app never sees your password. " + style.link(self, MANUAL_URL,
                                                                                            "Manual"))

        grid = QGridLayout()
        grid.setColumnStretch(2, 1)
        grid.setHorizontalSpacing(14)
        self.account_state = QLabel()
        self.account_state.setWordWrap(True)
        self.account_state.setOpenExternalLinks(True)
        self.account_state.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.sign_in_button = style.primary_button("Sign in", "Sign in with your Microsoft account: you get a "
                                                              "code to enter on microsoft.com/link")
        self.sign_in_button.clicked.connect(self.on_sign_in)
        self.sign_out_button = QPushButton("Sign out")
        self.sign_out_button.setToolTip("Forget the account on this board")
        self.sign_out_button.clicked.connect(self.on_sign_out)
        label = QLabel("Microsoft account")
        label.setStyleSheet("font-weight:700;")
        grid.addWidget(style.step_badge(1), 0, 0, Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(label, 0, 1)
        grid.addWidget(self.account_state, 0, 2)
        grid.addWidget(self.sign_in_button, 0, 3, Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.sign_out_button, 0, 4, Qt.AlignmentFlag.AlignVCenter)

        self.console_table = self._table(["Console", "Model", "Power", "Remote play"])
        self.console_table.doubleClicked.connect(lambda _index: self.on_stream_console())
        self.console_table.itemSelectionChanged.connect(self._update_buttons)
        self.wake_button = QPushButton("Wake")
        self.wake_button.setToolTip("Wake the console from sleep (it needs the Sleep power mode and remote "
                                    "features on)")
        self.wake_button.clicked.connect(self.on_wake)
        self.stream_console_button = style.primary_button("Stream", "Stream the console on the board")
        self.stream_console_button.clicked.connect(self.on_stream_console)
        consoles_tab = QWidget()
        lay = QVBoxLayout(consoles_tab)
        lay.addWidget(self.console_table, 1)
        row = QHBoxLayout()
        row.addWidget(self.wake_button)
        row.addStretch(1)
        row.addWidget(self.stream_console_button)
        lay.addLayout(row)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a game")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _text: self._fill_titles())
        self.title_table = self._table(["Game"])
        self.title_table.doubleClicked.connect(lambda _index: self.on_stream_title())
        self.title_table.itemSelectionChanged.connect(self._update_buttons)
        self.stream_title_button = style.primary_button("Stream", "Play the game from Xbox Cloud Gaming")
        self.stream_title_button.clicked.connect(self.on_stream_title)
        cloud_tab = QWidget()
        lay = QVBoxLayout(cloud_tab)
        lay.addWidget(self.search)
        lay.addWidget(self.title_table, 1)
        row = QHBoxLayout()
        self.cloud_state = QLabel()
        self.cloud_state.setWordWrap(True)
        row.addWidget(self.cloud_state, 1)
        row.addWidget(self.stream_title_button)
        lay.addLayout(row)

        self.tabs = QTabWidget()
        self.tabs.addTab(consoles_tab, "Consoles")
        self.tabs.addTab(cloud_tab, "Cloud games")

        self.running = QLabel()
        self.running.setStyleSheet("font-weight:600;")
        self.running.setWordWrap(True)
        self.output = Terminal()
        self.output.setPlaceholderText("Messages appear here.")
        self.output.setMaximumHeight(110)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(header)
        lay.addWidget(intro)
        lay.addSpacing(6)
        lay.addLayout(grid)
        lay.addSpacing(6)
        lay.addWidget(self.tabs, 1)
        lay.addWidget(self.running)
        lay.addWidget(self.output)
        version = QLabel(f"{APP_NAME} {__version__} · core {CORE_VERSION}")
        version.setStyleSheet("color:palette(placeholder-text);")
        lay.addWidget(version, 0, Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(central)
        style.apply(self)
        for button in (self.sign_in_button, self.sign_out_button):
            button.ensurePolished()
        width = max(b.sizeHint().width() for b in (self.sign_in_button, self.sign_out_button))
        for button in (self.sign_in_button, self.sign_out_button):
            button.setFixedWidth(width)

        geometry = self.settings.window_state("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self._show_state()
        if self.account.signed_in:
            self.refresh()

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        head = table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(headers)):
            head.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        return table

    def log(self, text: str) -> None:
        self.output.appendPlainText(privacy.mask(text, [self.gamertag], [c.id for c in self.consoles]))

    def say(self, text: str, error: bool = False) -> None:
        self.running.setStyleSheet("font-weight:600;" + ("color:#c62828;" if error else ""))
        self.running.setText(text)
        if text:
            self.log(text)

    # --- State ------------------------------------------------------------------------------------------------

    def _show_state(self) -> None:
        if self.code is not None:
            link = style.link(self, self.code.verification_uri, escape(self.code.verification_uri))
            self.account_state.setText(f"Open {link} on a phone or a computer and enter the code "
                                       f"<b style='font-size:18px;'>{escape(self.code.user_code)}</b>. "
                                       "This window goes on by itself once you signed in.")
        elif self.account.signed_in:
            who = f"<b>{escape(self.gamertag)}</b>" if self.gamertag else "your Microsoft account"
            self.account_state.setText(f"Signed in as {who}.")
        else:
            self.account_state.setText("Not signed in. Sign in gives you a code to enter on Microsoft's page, "
                                       "on a phone or any computer.")
        self.account_box.set_value(self.gamertag or ("signed in" if self.account.signed_in else "—"))
        self.consoles_box.set_value(str(len(self.consoles)) if self.account.signed_in else "—")
        self.cloud_box.set_value(OFFERINGS.get(self.account.cloud_offering, "—"))
        if self.code is not None:
            self.pill.set_status("Signing in", "info", "Enter the code on Microsoft's page.")
        elif not self.account.signed_in:
            self.pill.set_status("Signed out", "warn", "Sign in with your Microsoft account first.")
        elif self.stream_view is not None:
            self.pill.set_status("Streaming", "ok", "A stream is open.")
        else:
            self.pill.set_status("Ready", "ok", "Signed in.")
        self._fill_consoles()
        self._fill_titles()
        self._update_buttons()

    def _fill_consoles(self) -> None:
        self.console_table.setRowCount(len(self.consoles))
        for row, console in enumerate(self.consoles):
            remote = "On" if console.streaming_enabled else "Off: switch it on on the Xbox"
            for column, text in enumerate((console.name, console.type_name, console.power_name, remote)):
                self.console_table.setItem(row, column, QTableWidgetItem(text))

    def shown_titles(self) -> list[xbox.CloudTitle]:
        words = self.search.text().lower().split()
        return [t for t in self.titles if all(w in t.name.lower() for w in words)]

    def _fill_titles(self) -> None:
        titles = self.shown_titles()
        self.title_table.setRowCount(len(titles))
        for row, title in enumerate(titles):
            self.title_table.setItem(row, 0, QTableWidgetItem(title.name))
        offering = OFFERINGS.get(self.account.cloud_offering, "")
        if self.titles:
            note = f"{len(self.titles)} games" + (f" ({offering})" if offering else "")
            if self.account.cloud_offering == auth.CLOUD_FREE:
                note += ": without Game Pass Ultimate, only the free-to-play games"
            self.cloud_state.setText(note + ".")
        else:
            self.cloud_state.setText(self.cloud_note)

    def chosen_console(self) -> xbox.Console | None:
        rows = self.console_table.selectionModel().selectedRows()
        return self.consoles[rows[0].row()] if rows else None

    def chosen_title(self) -> xbox.CloudTitle | None:
        rows = self.title_table.selectionModel().selectedRows()
        titles = self.shown_titles()
        return titles[rows[0].row()] if rows and rows[0].row() < len(titles) else None

    def _update_buttons(self) -> None:
        idle = not self.worker.running and self.code is None
        signed = self.account.signed_in
        free = self.stream_view is None
        console = self.chosen_console() if self.consoles else None
        self.refresh_button.setEnabled(idle and signed)
        self.sign_in_button.setEnabled(not self.worker.running)
        self.sign_in_button.setText("Cancel" if self.code is not None else "Sign in")
        self.sign_out_button.setEnabled(idle and signed and free)
        self.wake_button.setEnabled(idle and signed and console is not None and console.can_wake)
        self.stream_console_button.setEnabled(idle and signed and free and console is not None)
        self.stream_title_button.setEnabled(idle and signed and free and bool(self.titles))

    # --- Jobs -------------------------------------------------------------------------------------------------

    def _start(self, text: str, job: Callable[[], object]) -> None:
        if self.worker.start(job):
            self.say(text)
            self._update_buttons()

    def _job_done(self, result) -> None:
        kind, ok, payload = result
        if kind == "code" and ok:
            self._wait_for_code(payload)
            return
        if kind == "refresh" and ok:
            self.gamertag, self.consoles, self.titles, self.cloud_note, notes = payload
            self.say(f"{len(self.consoles)} console(s) and {len(self.titles)} cloud game(s) on the account.")
            for note in notes:
                self.log(note)
        elif kind == "wake" and ok:
            self.say(payload)
        elif not ok:
            self.say(payload, error=True)
        if not self.account.signed_in:
            self.gamertag, self.consoles, self.titles = "", [], []
        self._show_state()

    def refresh(self) -> None:
        if not self.account.signed_in:
            return
        account = self.account

        def job():
            notes = []
            try:
                web = account.web_token()
                consoles = xbox.consoles(account.client, web)
            except SignedOut as error:
                return "refresh", False, f"{error}"
            except (AuthError, HttpError) as error:
                return "refresh", False, f"The account could not be read: {error}"
            titles, cloud_note = [], ""
            try:
                cloud = account.cloud_token()
                titles = xbox.cloud_titles(account.client, cloud)
                try:
                    xbox.name_titles(account.client, cloud, titles, locale_name())
                except HttpError as error:
                    notes.append(f"The games' names could not be read ({error}): their IDs are shown.")
                titles.sort(key=lambda t: t.name.lower())
            except (AuthError, HttpError) as error:
                cloud_note = f"No cloud games: {error}"
            return "refresh", True, (web.gamertag, consoles, [t for t in titles if t.entitled], cloud_note, notes)
        self._start("Asking Xbox Live for the consoles and the cloud games…", job)

    def on_sign_in(self) -> None:
        if self.code is not None:
            self.cancel_sign_in = True
            self.say("Canceling the sign-in…")
            return
        account = self.account

        def job():
            try:
                return "code", True, auth.start_sign_in(account.client)
            except (AuthError, HttpError) as error:
                return "code", False, f"Signing in could not start: {error}"
        self._start("Asking Microsoft for a sign-in code…", job)

    def _wait_for_code(self, code: DeviceCode) -> None:
        self.code = code
        self.cancel_sign_in = False
        account = self.account

        def wait():
            try:
                return True, auth.wait_for_sign_in(account.client, code, lambda: self.cancel_sign_in)
            except (AuthError, HttpError) as error:
                return False, f"{error}"
        self.sign_in_worker.start(wait)
        self.say("Waiting for the code to be entered on Microsoft's page…")
        self._show_state()

    def _signed_in(self, result) -> None:
        ok, payload = result
        self.code = None
        if ok:
            self.account.signed_in_with(payload)
            self.say("Signed in.")
            self._show_state()
            self.refresh()
        else:
            self.say(f"Not signed in: {payload}", error=not self.cancel_sign_in)
            self._show_state()

    def on_sign_out(self) -> None:
        answer = QMessageBox.question(self, window_title("Sign out"),
                                      "Sign out and forget the account on this board?\n\nSign in again with a new "
                                      "code to use it.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.account.sign_out()
        self.gamertag, self.consoles, self.titles, self.cloud_note = "", [], [], ""
        self.say("Signed out; the account is forgotten on this board.")
        self._show_state()

    def on_wake(self) -> None:
        console = self.chosen_console()
        if console is None:
            return
        account = self.account

        def job():
            try:
                xbox.wake(account.client, account.web_token(), console.id)
            except (AuthError, HttpError) as error:
                return "wake", False, f"{console.name} was not woken: {error}"
            return "wake", True, (f"{console.name} is waking up: give it a few seconds, then Refresh or Stream.")
        self._start(f"Waking {console.name}…", job)

    # --- Streams ----------------------------------------------------------------------------------------------

    def on_stream_console(self) -> None:
        console = self.chosen_console()
        if console is None or self.stream_view is not None:
            return
        if not console.streaming_enabled:
            self.say(f"Remote play is off on {console.name}: switch it on in the Xbox's Settings, Devices & "
                     "connections, Remote features.", error=True)
            return
        self.open_stream("home", console.id, console.name)

    def on_stream_title(self) -> None:
        title = self.chosen_title()
        if title is None or self.stream_view is not None:
            return
        self.open_stream("cloud", title.title_id, title.name)

    def open_stream(self, kind: str, target: str, name: str) -> None:
        stream = Stream(self.account, kind, target, locale_name(), parent=self)
        stream.log.connect(self.log)
        stream.ended.connect(lambda reason: self._stream_ended(name, reason))
        view = self.make_stream_window(stream, name)
        view.destroyed.connect(lambda _obj=None: self._stream_closed())
        self.stream_view = view
        view.showFullScreen()
        stream.start()
        self.say(f"Streaming {name}.")
        self._show_state()

    def _stream_ended(self, name: str, reason: str) -> None:
        if reason:
            self.say(f"The stream of {name} ended: {reason}", error=True)
        else:
            self.say(f"The stream of {name} ended.")

    def _stream_closed(self) -> None:
        self.stream_view = None
        self._show_state()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override)
        if self.stream_view is not None:
            self.stream_view.close()
        self.cancel_sign_in = True
        self.worker.stop()
        self.sign_in_worker.stop(10000)
        self.settings.set_window_state("geometry", self.saveGeometry())
        self.settings.sync()
        super().closeEvent(event)
