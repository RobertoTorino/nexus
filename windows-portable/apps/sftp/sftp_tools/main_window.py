# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the cards on the left (Connection, Server's files, This device, Transfers, SSH server, Settings), what
the focused one shows on the right, the controller's buttons at the bottom. It is the BC250 suite's SFTP Tools made
for the handheld: its SFTP Client is the first four cards, its Server Manager the SSH server card, on one connection.

The Connection card's rows are the BC250 app's form, a row a field (a field's page with the touch keyboard), the key
stepped through those in %USERPROFILE%\\.ssh, and the servers connected to before; X connects. The two sides are
lists: A opens a folder or moves a file, X moves a folder, Y deletes on a second press, B goes a folder up. Transfers
wait their turn on the Transfers card, one at a time on a channel of their own, so browsing goes on meanwhile. Nothing
runs before it is asked for (owner, 28-10-2026); every step on the network runs off the window's thread."""

from __future__ import annotations

import posixpath
import socket
import threading
from collections.abc import Callable
from pathlib import Path

import paramiko
from PyQt6.QtCore import QObject, QSettings, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, browse, power
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private
from bc250_core.portable import KEYBOARD, VIEW, Card, Legend, Pane, PortableHeader, PortableWindow, px, status_clock

from . import APP_ID, APP_NAME, __version__, connection, folders, servers, transfers
from .folders import LocalFolder, RemoteFolder
from .panes import FieldPane, InfoPane, ListPane
from .servers import Server
from .transfer_queue import DONE, FAILED, QUEUED, RUNNING, TransferJob, TransferQueue, speed_text

STATUS_MS = 30_000              # the header's time and battery
CONFIRM_MS = 5000               # Delete, Forget, Stop, Cancel, and View while transfers run, ask for a second press
CARDS_WIDTH = 400
CARD_HEIGHT = 84                # six cards and their gaps fit the column at 720 px high
LOCAL_KEY = "local"             # the This device folder kept for next time (browse.remember)
LOG_MAX = 2000                  # the lines of the log the view shows, the newest
NOT_CONNECTED = "Not connected: the X button on the Connection card connects first."

CONNECTION_INFO = (
    "Fill in the server: its host, the port (22), your user name, and a password or a key. The A button changes the "
    "row the focus is on: the host, the port, the user name and the password each open a page with a field, where "
    "R3 (the right stick pressed) opens Windows' touch keyboard and the X button pastes what you copied. The Key row "
    "steps through the private keys in %USERPROFILE%\\.ssh; with none chosen, the default keys and the SSH agent are "
    "used. With a key, the password is the key's passphrase.\n\n"
    "The X button connects, and disconnects again. The first time, the app shows the server's key: compare it with "
    "the server's own (ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub on the server), then press the X button again "
    "to trust it. It is kept in %USERPROFILE%\\.ssh\\known_hosts, which Windows' own ssh uses too.\n\n"
    "A server you connected to is remembered under the fields, without its password: the A button fills it in, the "
    "Y button forgets it on a second press. A password is kept until the app closes and never saved. Without a key it "
    "needs at least 8 characters, a capital, a number and a special character, or the app does not connect.")
REMOTE_INFO = (
    "The server's folders, from your home there (~). The A button opens a folder, or downloads a file; the X button "
    "downloads the folder the focus is on; the Y button deletes it on the server, on a second press. The B button "
    "goes a folder up, and from your home back to the card; the ‹ row goes above it.\n\n"
    "A download goes to the folder open on the This device card (Downloads while it shows the places) and waits its "
    "turn on the Transfers card. The characters Windows refuses in a name (< > : \" | ? *) become _.")
LOCAL_INFO = (
    "This device's folders: your usual folders first, then every drive (an SD card, a USB stick). The A button opens "
    "a folder, or uploads a file to the server's folder open on the Server's files card; the X button uploads the "
    "folder the focus is on; the Y button deletes it from this device, on a second press. The B button goes a folder "
    "up, and from the places back to the card. Downloads go to the folder open here.")
TRANSFERS_INFO = (
    "Every upload and download, one at a time in the order asked for: how far the running one is, its speed, and "
    "what waits. The A button tries a failed one again. The X button takes the done and the failed ones off the "
    "list. The Y button stops the running one and the waiting ones, on a second press; a file half moved stays as it "
    "is. Transfers stop when the connection ends or the app closes.")
SERVER_INFO = (
    "The SSH server (sshd) of the host you are connected to: a Linux with systemd, such as Bazzite on a BC-250. The A "
    "button reads whether it runs. The X button starts it, or stops it on a second press: the connection you are on "
    "stays, but no new one can be made until sshd is started again. The Y button reads its settings, "
    "/etc/ssh/sshd_config, to scroll through; they are changed on the host itself.\n\n"
    "Starting and stopping needs sudo without a password on the host (sudo -n): when it asks for one, the app shows "
    "the error and nothing changes.")
SETTINGS_INFO = (
    "What a transfer does. The A button steps a setting to its next value; it counts from the next transfer, "
    "compression from the next connection. The last row shows the app's log: the d-pad scrolls it, the B button goes "
    "back. The log keeps no password.")

# The field pages: (title, what it is for, hidden, placeholder, longest)
FIELDS = {
    "host": ("Host", "The server's name or IP address. On a Bazzite host, hostname -I prints its address.", False,
             "192.168.1.20", 253),
    "port": ("Port", "The SSH server's port: 22, unless the server was set up with another.", False, "22", 5),
    "user": ("User name", "Your account on the server: whoami prints it there.", False, "", 64),
    "password": ("Password", "Your password on the server, or the key's passphrase when a key is chosen. It is kept "
                 "until the app closes, never saved.", True, "", 256),
}
STATES = {"active": "Running", "inactive": "Stopped", "failed": "Failed: it stopped with an error",
          "activating": "Starting", "deactivating": "Stopping", "reloading": "Reloading"}


class _Worker(QObject):
    """Runs a slow step off the window's thread; done or failed arrive on the window's. It stays busy until the
    window has the outcome, so a step started meanwhile waits for the one before to be shown."""

    done = pyqtSignal(object)
    failed = pyqtSignal(object)
    _outcome = pyqtSignal(bool, object)                 # from the step's thread to the window's

    def __init__(self):
        super().__init__()
        self.busy = False
        self._outcome.connect(self._deliver)

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
            self._outcome.emit(False, error)
            return
        self._outcome.emit(True, result)

    def _deliver(self, ok: bool, result: object) -> None:
        self.busy = False
        (self.done if ok else self.failed).emit(result)


def error_text(error: BaseException) -> str:
    """What went wrong, for the status line: paramiko's and the network's errors in plain words."""
    if isinstance(error, paramiko.PasswordRequiredException):        # an AuthenticationException too
        return "The key has a passphrase: put it in the Password row."
    if isinstance(error, paramiko.AuthenticationException):
        return "The server refused the login: check the user name, the password or the key."
    if isinstance(error, (socket.timeout, TimeoutError)):
        return "The host did not answer in time: check its address, and that sshd runs there."
    if isinstance(error, socket.gaierror):
        return "No host by that name: check the address."
    if isinstance(error, (ConnectionRefusedError, paramiko.ssh_exception.NoValidConnectionsError)):
        return "The host refused the connection: sshd may not run there, or the port is another."
    if isinstance(error, PermissionError):
        return "Not allowed: the server or Windows refused it."
    if isinstance(error, FileNotFoundError):
        return "It is not there anymore."
    text = getattr(error, "strerror", None) or str(error) or type(error).__name__
    return text if text.endswith(".") else f"{text}."


class MainWindow(PortableWindow):
    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery,
                 connect: Callable[..., paramiko.SSHClient] = connection.connect_ssh,
                 known_hosts: Path | None = None, settings: QSettings | None = None,
                 roots: Callable[[], list[Path]] = browse.drives, user_home: Path | None = None,
                 beep: Callable[[], None] = QApplication.beep):
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.connect_ssh, self.known_hosts, self.beep = connect, known_hosts, beep
        self.settings = settings or QSettings()
        self.roots, self.user_home = roots, user_home
        self.server: Server = servers.last(self.settings)
        self.password = ""                              # kept until the app closes, never saved
        self.client: paramiko.SSHClient | None = None
        self.sftp: paramiko.SFTPClient | None = None    # the window's channel: listing, deleting
        self.transfer_sftp: paramiko.SFTPClient | None = None   # the queue's own
        self.connected_to: Server | None = None
        self.untrusted: connection.UnknownHostKeyError | None = None    # a new server's key, until X trusts it
        self.remote: RemoteFolder | None = None
        self.remote_before = ""                         # the server's folder before the one being listed
        self.remote_focus = ""                          # the row to give the focus once it is listed
        self.local = LocalFolder(browse.places(user_home, roots), browse.remembered(self.settings, LOCAL_KEY),
                                 self.hidden())
        self.sshd = ""                                  # sshd's state as read, "" before
        self.job = ""                                   # what the worker does: connect, list, delete, server, config
        self.asked = ""                                 # the action pressed once, waiting for its second press
        self.close_asked = False

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
        cards.setSpacing(px(10))
        self.connection_card = Card("Connection", "")
        self.remote_card = Card("Server's files", "")
        self.local_card = Card("This device", "")
        self.transfers_card = Card("Transfers", "")
        self.server_card = Card("SSH server", "")
        self.settings_card = Card("Settings", "What a transfer does, and the log.")
        for card in (self.connection_card, self.remote_card, self.local_card, self.transfers_card, self.server_card,
                     self.settings_card):
            card.setFixedHeight(px(CARD_HEIGHT))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()
        self.connection_pane = ListPane("Connection", CONNECTION_INFO)
        self.remote_pane = ListPane("Server's files", REMOTE_INFO)
        self.local_pane = ListPane("This device", LOCAL_INFO)
        self.transfers_pane = ListPane("Transfers", TRANSFERS_INFO)
        self.server_pane = InfoPane("SSH server", SERVER_INFO)
        self.settings_pane = ListPane("Settings", SETTINGS_INFO)
        self.field_pane = FieldPane()
        for pane in (self.connection_pane, self.remote_pane, self.local_pane, self.transfers_pane, self.server_pane,
                     self.settings_pane, self.field_pane):
            self.panes.addWidget(pane)
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend()
        page.addWidget(self.legend)
        self.cards = {self.connection_pane: self.connection_card, self.remote_pane: self.remote_card,
                      self.local_pane: self.local_card, self.transfers_pane: self.transfers_card,
                      self.server_pane: self.server_card, self.settings_pane: self.settings_card,
                      self.field_pane: self.connection_card}

        self.worker = _Worker()
        self.worker.done.connect(self._done)
        self.worker.failed.connect(self._failed)
        self.queue = TransferQueue(self)
        self.queue.changed.connect(self.show_transfers)
        self.queue.finished.connect(self.transfer_finished)
        for pane, card in self.cards.items():
            if pane is not self.field_pane:
                card.focused.connect(lambda pane=pane: self.show_pane(pane))
        self.connection_card.activated.connect(lambda: self.focus_list(self.connection_pane))
        self.remote_card.activated.connect(lambda: self.focus_list(self.remote_pane))
        self.local_card.activated.connect(lambda: self.focus_list(self.local_pane))
        self.transfers_card.activated.connect(lambda: self.focus_list(self.transfers_pane))
        self.server_card.activated.connect(lambda: self.server_step("status"))
        self.settings_card.activated.connect(lambda: self.focus_list(self.settings_pane))
        self.connection_pane.list.picked.connect(self.connection_row)
        self.remote_pane.list.picked.connect(self.remote_row)
        self.local_pane.list.picked.connect(self.local_row)
        self.transfers_pane.list.picked.connect(self.transfer_row)
        self.settings_pane.list.picked.connect(self.settings_row)
        self.field_pane.field.returnPressed.connect(self.keep_field)
        self.bind("accept", self.a_action)
        self.bind("x", self.x_action)
        self.bind("y", self.y_action)
        self.back.connect(self.on_back)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(self.update_status)
        self.confirm_timer = QTimer(self)
        self.confirm_timer.setSingleShot(True)
        self.confirm_timer.setInterval(CONFIRM_MS)
        self.confirm_timer.timeout.connect(self._confirm_over)
        self.show_connection()
        self.show_remote()
        self.show_local()
        self.show_transfers()
        self.show_server()
        self.show_settings()
        self.show_pane(self.connection_pane)

    def start(self) -> None:
        """After the window is shown: the controller and the status line; nothing connects before X asks for it."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.connection_card.setFocus()

    def update_status(self) -> None:
        self.header.set_status([*status_clock(), power.text(self.battery())])   # the battery last (owner, 30-10-2026)

    @property
    def busy(self) -> bool:
        """Transfers run or wait, or a connection is being made: PortableWindow waits with a move to another screen,
        and View asks for a second press."""
        return self.queue.busy or bool(self.queue.jobs_in(QUEUED)) or self.job == "connect"

    def hidden(self) -> bool:
        return servers.HIDDEN.value(self.settings) == "on"

    def is_connected(self) -> bool:
        transport = self.client.get_transport() if self.client is not None else None
        return transport is not None and transport.is_active() and self.sftp is not None

    def show_pane(self, pane: Pane) -> None:
        current = self.panes.currentWidget()
        if current is not pane and getattr(current, "viewing", False):
            current.show_body()
        self.panes.setCurrentWidget(pane)
        self.update_legend()

    def focus_list(self, pane: ListPane) -> None:
        """The list's first row, or the pane's card while the list is empty (its status says why)."""
        if not pane.list.focus(""):
            if pane is self.remote_pane and not self.is_connected():
                pane.status.setText(NOT_CONNECTED)
            self.cards[pane].setFocus()

    def legend_items(self) -> list[tuple[str, str]]:
        """The legend for the pane that shows and the row the focus is on: its actions on the controller's buttons,
        A too (a tap on an entry does the same), then core's Menu Info, B Back and View Exit. A press that cannot
        act now says why on the status line."""
        if self.close_asked:
            return [(VIEW, "Press again to exit")]
        pane = self.panes.currentWidget()
        items: list[tuple[str, str]] = []
        if pane is self.field_pane:
            items = [("A", "Keep"), ("X", "Paste"), KEYBOARD]
        elif getattr(pane, "viewing", False):
            items = []
        elif pane is self.connection_pane:
            row = pane.list.focused()
            connect = ("Press again" if self.asked == "disconnect" else "Disconnect") if self.is_connected() else \
                "Trust and connect" if self.untrusted is not None else "Connect"
            if row.startswith("server:"):
                items = [("A", "Fill in"), ("X", connect), ("Y", "Press again" if self.asked == row else "Forget")]
            else:
                items = [("A", "Next key" if row == "key" else "Change"), ("X", connect)]
        elif pane is self.remote_pane:
            items = self.side_items(pane.list.focused(), "Download")
        elif pane is self.local_pane:
            # The places are only opened: a place or a drive is neither uploaded whole nor deleted
            items = self.side_items(pane.list.focused(), "Upload") if self.local.path is not None else [("A", "Open")]
        elif pane is self.transfers_pane:
            row = pane.list.focused()
            job = self.job_of(row)
            items = [*([("A", "Try again")] if job is not None and job.state == FAILED else
                       [("A", "Open")] if not row else []),
                     ("X", "Clear finished"), ("Y", "Press again" if self.asked == "cancel" else "Stop all")]
        elif pane is self.server_pane:
            running = self.sshd == "active"
            items = [("A", "Read the state"),
                     ("X", ("Press again" if self.asked == "stop" else "Stop sshd") if running else "Start sshd"),
                     ("Y", "sshd_config")]
        elif pane is self.settings_pane:
            row = pane.list.focused()
            items = [("A", "View the log" if row == "log" else "Change" if row else "Open")]
        on_a_page = pane is self.field_pane or getattr(pane, "viewing", False)
        return [*items, *self.common_items(True if on_a_page else None)]

    def side_items(self, row: str, move: str) -> list[tuple[str, str]]:
        """The Server's files or This device legend: A opens a folder or moves a file, X moves a folder, Y deletes."""
        delete = ("Y", "Press again" if self.asked == f"delete:{row}" else "Delete")
        if row.startswith("dir:"):
            return [("A", "Open"), ("X", move), delete]
        if row.startswith("file:"):
            return [("A", move), delete]
        return [("A", "Open")]

    def update_legend(self) -> None:
        if hasattr(self, "legend"):
            self.legend.set_items(self.legend_items())

    # The buttons

    def a_action(self) -> None:
        """A beside a card (a tap on the legend's A) or in a text field: the pane's own A."""
        pane = self.panes.currentWidget()
        if pane is self.field_pane:
            self.keep_field()
        elif pane is self.server_pane:
            self.server_step("status")
        elif isinstance(pane, ListPane) and not pane.viewing:
            row = pane.list.focused()
            if row:
                pane.list.picked.emit(row)
            else:
                self.focus_list(pane)

    def x_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.field_pane:
            self.paste()
        elif getattr(pane, "viewing", False):
            return
        elif pane is self.connection_pane:
            self.connect_or_disconnect()
        elif pane is self.remote_pane:
            self.move_folder(pane, pane.list.focused(), "download")
        elif pane is self.local_pane:
            self.move_folder(pane, pane.list.focused(), "upload")
        elif pane is self.transfers_pane:
            cleared = self.queue.clear_finished()
            pane.status.setText(f"{cleared} taken off the list." if cleared else "Nothing finished to take off.")
        elif pane is self.server_pane:
            self.server_step("stop" if self.sshd == "active" else "start")

    def y_action(self) -> None:
        pane = self.panes.currentWidget()
        if getattr(pane, "viewing", False) or pane is self.field_pane:
            return
        if pane is self.connection_pane:
            row = pane.list.focused()
            if row.startswith("server:"):
                self.forget(row)
            else:
                pane.status.setText("The Y button forgets a server remembered under the fields: put the focus on it "
                                    "first.")
        elif pane is self.remote_pane:
            self.delete(pane, pane.list.focused(), remote=True)
        elif pane is self.local_pane:
            self.delete(pane, pane.list.focused(), remote=False)
        elif pane is self.transfers_pane:
            self.stop_all()
        elif pane is self.server_pane:
            self.server_step("config")

    def on_back(self) -> None:
        """B goes back (the suite's rule, owner 29-10-2026): a field's page to its row (nothing kept), a text read to
        its pane, in the server's or this device's folders a folder up and from the top to the card, a pane to its
        card; on a card it does nothing (View exits)."""
        pane = self.panes.currentWidget()
        if pane is self.field_pane:
            self.back_to_connection()
        elif getattr(pane, "viewing", False):
            pane.show_body()
            if isinstance(pane, ListPane):
                self.focus_list(pane)
            else:
                self.cards[pane].setFocus()
            self.update_legend()
        elif pane is self.remote_pane and self.can_go_back() and self.remote is not None:
            if self.worker.busy:
                pane.status.setText("Still busy with the step before: a moment.")
                return
            came_from = self.remote.path
            if self.remote.back():
                self.remote_before = came_from
                self.list_remote(focus=f"dir:{came_from}")
            else:
                self.go_back()
        elif pane is self.local_pane and self.can_go_back() and self.local.path is not None:
            came_from = self.local.path
            self.local.up()
            self.show_local(focus=f"dir:{came_from}")
        else:
            self.go_back()

    def ask(self, what: str, pane: Pane, text: str) -> bool:
        """A second press of *what* within five seconds: True on it; on the first, *text* on the pane's status line."""
        if self.asked == what:
            self._confirm_over(keep_status=True)
            return True
        self.asked = what
        self.confirm_timer.start()
        pane.status.setText(text)
        self.update_legend()
        return False

    def _confirm_over(self, keep_status: bool = False) -> None:
        self.confirm_timer.stop()
        if self.asked and not keep_status:
            pane = self.panes.currentWidget()
            if getattr(pane, "status", None) is not None and pane.status.text().startswith("Press "):
                pane.status.setText("")
        if self.close_asked and not keep_status and self.connection_pane.status.text().startswith("Press View"):
            self.connection_pane.status.setText("")
        self.asked, self.close_asked = "", False
        self.update_legend()

    # The worker

    def run(self, job: str, pane: Pane, work: Callable[[], object], text: str) -> bool:
        """*work* off the window's thread, *text* on the pane's status line meanwhile; while another step runs, the
        status says so."""
        if self.worker.busy:
            pane.status.setText("Still busy with the step before: a moment.")
            return False
        self.job = job
        pane.status.setText(text)
        self.worker.start(work)
        return True

    def _done(self, result) -> None:
        job, self.job = self.job, ""
        if job == "connect":
            self.connected(*result)
        elif job == "list":
            self.listed(result)
        elif job == "delete":
            pane, said = result
            pane.status.setText(said)
            self.log.info(said)
            if pane is self.remote_pane:
                self.list_remote()
            else:
                self.show_local()
        elif job == "server":
            self.sshd = result
            self.server_pane.status.setText(f"sshd: {STATES.get(result, result or 'Not known')}.")
            self.log.info(f"sshd's state read: {result or 'not known'}.")
            self.show_server()
        elif job == "config":
            self.server_pane.show_text("sshd_config", result or "The file is empty.")
            self.server_pane.status.setText(f"{connection.SSHD_CONFIG_PATH}: the d-pad scrolls it, the B button goes "
                                            "back.")
            self.update_legend()
        self.update_legend()

    def _failed(self, error: BaseException) -> None:
        job, self.job = self.job, ""
        if job == "connect":
            self.connect_failed(error)
            return
        text = error_text(error)
        pane = {"list": self.remote_pane, "server": self.server_pane, "config": self.server_pane,
                "delete": self.panes.currentWidget()}.get(job, self.connection_pane)
        if job == "list" and self.remote is not None and self.remote_before:
            self.remote.path = self.remote_before         # stay where it was
        if self.client is not None and not self.is_connected():
            self.disconnect("The connection was lost.")
            pane.status.setText(f"The connection was lost: {text}")
        else:
            pane.status.setText(text)
        self.log.error(f"{job.capitalize() or 'A step'} failed: {text}")
        self.update_legend()

    # The Connection card

    def show_connection(self) -> None:
        server, keys = self.server, self.key_name()
        rows = [("host", f"Host: {server.host or 'Not filled in'}"), ("port", f"Port: {server.port}"),
                ("user", f"User: {server.user or 'Not filled in'}"),
                ("password", "Password: " + ("Typed, kept until the app closes" if self.password else
                                             "None, the key or the SSH agent")),
                ("key", f"Key: {keys}")]
        rows += [(f"server:{n}", f"Saved: {saved.label}") for n, saved in enumerate(servers.servers(self.settings))]
        self.connection_pane.list.set_items(rows)
        if self.is_connected() and self.connected_to is not None:
            self.connection_card.set_text(f"Connected: {self.connected_to.label}")
            self.connection_pane.summary.setText(f"Connected to {self.connected_to.label}.")
        else:
            self.connection_card.set_text("Not connected: X connects.")
            self.connection_pane.summary.setText("The server to connect to. The X button connects.")
        self.update_legend()

    def key_name(self) -> str:
        return Path(self.server.key).name if self.server.key else "Default keys and the SSH agent"

    def connection_row(self, key: str) -> None:
        """A on a row of the Connection card: a field's page, the next key, or a saved server filled in."""
        pane = self.connection_pane
        if key in FIELDS:
            title, text, hidden, placeholder, length = FIELDS[key]
            if key == "password" and self.server.key:
                text = "The passphrase of the key " + self.key_name() + ", kept until the app closes, never saved."
            value = {"host": self.server.host, "port": str(self.server.port), "user": self.server.user,
                     "password": self.password}[key]
            self.field_pane.set_field(key, title, text, value, hidden, placeholder, length)
            self.show_pane(self.field_pane)
            self.field_pane.field.setFocus()
        elif key == "key":
            choices = ["", *(str(path) for path in folders.private_keys(self.user_home))]
            if len(choices) == 1:
                pane.status.setText("No key in %USERPROFILE%\\.ssh: the default keys and the SSH agent are used. "
                                    "ssh-keygen -t ed25519 in a terminal makes one.")
                return
            at = choices.index(self.server.key) if self.server.key in choices else 0
            self.set_server(Server(self.server.host, self.server.port, self.server.user,
                                   choices[(at + 1) % len(choices)]))
            pane.status.setText(f"Key: {self.key_name()}." + (" The password is its passphrase."
                                                               if self.server.key else ""))
        elif key.startswith("server:"):
            saved = self.saved(key)
            if saved is None:
                return
            if not saved.same(self.server):
                self.password = ""                      # another server's password is not carried over
            self.set_server(saved)
            pane.status.setText(f"{saved.label} filled in: the X button connects.")
            pane.list.focus("host")

    def saved(self, row: str) -> Server | None:
        try:
            return servers.servers(self.settings)[int(row.removeprefix("server:"))]
        except (ValueError, IndexError):
            return None

    def set_server(self, server: Server) -> None:
        """The fields changed: kept for next time, a key not trusted yet forgotten."""
        if not server.same(self.server):
            self.untrusted = None
        self.server = server
        servers.keep_last(self.settings, server)
        self.show_connection()

    def forget(self, row: str) -> None:
        saved = self.saved(row)
        if saved is None:
            return
        if not self.ask(row, self.connection_pane, f"Press the Y button again to forget {saved.label}."):
            return
        servers.forget(self.settings, saved)
        self.connection_pane.status.setText(f"{saved.label} is forgotten.")
        self.show_connection()
        self.connection_pane.list.focus("key")

    def back_to_connection(self, said: str = "") -> None:
        key = self.field_pane.key
        self.field_pane.field.clear()                   # a password is not left in the window
        self.show_pane(self.connection_pane)
        self.connection_pane.status.setText(said)
        self.connection_pane.list.focus(key)

    def keep_field(self) -> None:
        """A on a field's page: the value kept, back to the Connection card."""
        key, value = self.field_pane.key, self.field_pane.field.text()
        server = self.server
        if key == "host":
            server = Server(value.strip(), server.port, server.user, server.key)
        elif key == "port":
            try:
                port = int(value.strip() or "22")
            except ValueError:
                port = 0
            if not 1 <= port <= 65535:
                self.field_pane.status.setText("The port is a number from 1 to 65535.")
                return
            server = Server(server.host, port, server.user, server.key)
        elif key == "user":
            server = Server(server.host, server.port, value.strip(), server.key)
        elif key == "password":
            self.password = value                       # a password keeps its spaces
        if key != "password":
            self.set_server(server)
        else:
            self.show_connection()
        self.back_to_connection(f"{FIELDS[key][0]} kept.")

    def paste(self) -> None:
        """The clipboard's text into the page's field (copied in a browser on the device)."""
        text = QGuiApplication.clipboard().text()
        text = text if self.field_pane.key == "password" else text.strip()
        if not text:
            self.field_pane.status.setText("The clipboard is empty: copy the text on this device first.")
            return
        self.field_pane.field.setText(text)
        self.field_pane.status.setText("The text is in the field: the A button keeps it.")

    def connect_or_disconnect(self) -> None:
        pane = self.connection_pane
        if self.job == "connect":
            pane.status.setText("Still connecting: a moment.")
            return
        if self.is_connected():
            moving = self.queue.busy or bool(self.queue.jobs_in(QUEUED))
            if moving and not self.ask("disconnect", pane, "Press the X button again to disconnect: the transfers "
                                                           "stop."):
                return
            self.disconnect()
            pane.status.setText("Disconnected.")
            return
        server, password = self.server, self.password
        if not server.host or not server.user:
            pane.status.setText("Fill in the " + ("host" if not server.host else "user name") + " first: the A button "
                                "on its row.")
            return
        if password and not server.key and (missing := connection.check_password(password)):
            pane.status.setText(f"{missing} Change the password row, or choose a key.")
            return
        trusted = ""
        if self.untrusted is not None:
            try:
                connection.save_trusted_host_key(self.untrusted, self.known_hosts)
            except OSError as error:
                pane.status.setText(f"The server's key could not be kept: {error_text(error)}")
                return
            trusted = "The server's key is trusted now. "
            self.log.info("A server's key was added to known_hosts.")
            self.untrusted = None
        compression = servers.COMPRESSION.value(self.settings) == "on"
        known_hosts = self.known_hosts

        def work():
            client = self.connect_ssh(server.host, server.port, server.user, password, server.key,
                                      compression=compression, known_hosts=known_hosts)
            try:
                sftp, queue_sftp = client.open_sftp(), client.open_sftp()
                return client, sftp, queue_sftp, connection.remote_home(sftp), server
            except Exception:
                client.close()
                raise

        self.run("connect", pane, work, f"{trusted}Connecting to {server.label} …")
        self.update_legend()

    def connected(self, client, sftp, queue_sftp, home: str, server: Server) -> None:
        self.client, self.sftp, self.transfer_sftp = client, sftp, queue_sftp
        self.connected_to = server
        self.queue.set_sftp(queue_sftp)
        servers.remember(self.settings, server)
        self.remote = RemoteFolder(home)
        self.sshd = ""
        self.connection_pane.status.setText("Connected. The Server's files card shows your home there.")
        self.log.info("Connected to a server" + (" with a key." if server.key else "."))
        self.show_connection()
        self.show_server()
        self.show_targets()
        self.list_remote()

    def connect_failed(self, error: BaseException) -> None:
        pane = self.connection_pane
        if isinstance(error, connection.UnknownHostKeyError):
            self.untrusted = error
            pane.status.setText(f"This server is new to this device. Its key: {connection.fingerprint(error.key)}. "
                                "When it is the server's own, the X button trusts it and connects.")
            self.log.info("A server's key is not in known_hosts yet: asked whether to trust it.")
        else:
            text = error_text(error)
            pane.status.setText(text)
            self.log.error(f"Connecting failed: {text}")
        self.update_legend()

    def disconnect(self, reason: str = "Disconnected") -> None:
        was = self.client is not None
        self.queue.abort_all(reason)
        for channel in (self.sftp, self.transfer_sftp, self.client):
            if channel is not None:
                try:
                    channel.close()
                except Exception:  # noqa: BLE001  (closed already)
                    pass
        self.client = self.sftp = self.transfer_sftp = None
        self.connected_to, self.remote, self.sshd = None, None, ""
        if was:
            self.log.info(f"{reason}.")
        self.show_connection()
        self.show_remote()
        self.show_server()

    # The Server's files card

    def show_remote(self, rows: list[tuple[str, str]] | None = None) -> None:
        pane, remote = self.remote_pane, self.remote
        if remote is None or not self.is_connected():
            pane.list.set_items([])
            pane.summary.setText("Not connected.")
            self.remote_card.set_text("Connect first: the Connection card.")
            self.show_targets()
            return
        if rows is not None:
            pane.list.set_items(rows, focus=self.remote_focus)
        self.show_targets()

    def show_targets(self) -> None:
        """Where each side is, and where a file moved from the other one goes: the two panes' lines and cards."""
        local, remote = self.local, self.remote if self.is_connected() else None
        if remote is not None:
            where = private(local.target(folders.downloads_folder(self.user_home)))
            self.remote_pane.summary.setText(f"{remote.shown()}   ·   downloads go to {where}")
            self.remote_card.set_text(f"In {remote.shown()}")
        here = private(local.path) if local.path is not None else "The places: your folders and every drive."
        to = f"   ·   uploads go to {remote.shown()}" if remote is not None and local.path is not None else ""
        self.local_pane.summary.setText(here + to)
        self.local_card.set_text(f"In {private(local.path)}" if local.path is not None else "The places")

    def list_remote(self, focus: str = "") -> None:
        """The server's folder as it is now, read off the window's thread."""
        remote, sftp, hidden = self.remote, self.sftp, self.hidden()
        if remote is None or sftp is None:
            self.show_remote()
            return
        self.remote_focus = focus
        path = remote.path
        if not self.run("list", self.remote_pane, lambda: folders.remote_entries(sftp, path, hidden),
                        f"Reading {remote.shown()} …"):
            remote.path = self.remote_before or remote.path

    def listed(self, entries: list[folders.Entry]) -> None:
        remote = self.remote
        if remote is None:
            return
        self.remote_before = ""
        self.remote_pane.status.setText("" if entries else "The folder is empty.")
        self.show_remote(remote.rows(entries))

    def remote_row(self, key: str) -> None:
        """A on a row of the server's files: into a folder or up, or a file downloaded."""
        remote = self.remote
        if remote is None or not self.is_connected():
            self.remote_pane.status.setText(NOT_CONNECTED)
            return
        if key.startswith("file:"):
            self.download(key[5:], is_dir=False)
            return
        if self.worker.busy:
            self.remote_pane.status.setText("Still busy with the step before: a moment.")
            return
        before = remote.path
        if remote.open(key):
            self.remote_before = before
            self.list_remote(focus=f"dir:{before}" if key == folders.UP else "")

    def download(self, source: str, is_dir: bool) -> None:
        name = transfers.windows_name(posixpath.basename(source.rstrip("/")) or "server")
        target = self.local.target(folders.downloads_folder(self.user_home))
        self.queue_job(self.remote_pane, TransferJob("download", source, str(target / name), is_dir),
                       f"↓ {name} is on the Transfers card: it goes to {private(target)}.")

    def move_folder(self, pane: ListPane, row: str, direction: str) -> None:
        """X: the folder the focus is on downloaded or uploaded."""
        if not row.startswith("dir:"):
            pane.status.setText("The X button moves a folder: put the focus on one first. The A button moves a "
                                "file.")
            return
        if direction == "download":
            if not self.is_connected():
                pane.status.setText(NOT_CONNECTED)
                return
            self.download(row[4:], is_dir=True)
        else:
            self.upload(Path(row[4:]), is_dir=True)

    # The This device card

    def show_local(self, focus: str = "") -> None:
        pane, local = self.local_pane, self.local
        local.hidden = self.hidden()
        pane.list.set_items(local.rows(), focus=focus)
        browse.remember(self.settings, LOCAL_KEY, local.path)
        self.show_targets()

    def local_row(self, key: str) -> None:
        if key.startswith("file:"):
            self.upload(Path(key[5:]), is_dir=False)
            return
        came_from = self.local.path
        self.local.open(key)
        self.show_local(focus=f"dir:{came_from}" if key == folders.UP and came_from is not None else "")

    def upload(self, source: Path, is_dir: bool) -> None:
        pane = self.local_pane
        if self.remote is None or not self.is_connected():
            pane.status.setText(NOT_CONNECTED)
            return
        if is_dir and self.local.path is None:
            pane.status.setText("A place is not uploaded whole: open it, then choose a folder in it.")
            return
        target = posixpath.join(self.remote.path, source.name)
        self.queue_job(pane, TransferJob("upload", str(source), target, is_dir),
                       f"↑ {source.name} is on the Transfers card: it goes to {self.remote.shown()}.")

    def delete(self, pane: ListPane, row: str, remote: bool) -> None:
        """Y on a row: deleted on a second press within five seconds, off the window's thread."""
        if not row.startswith(("dir:", "file:")):
            pane.status.setText("The Y button deletes the folder or the file the focus is on.")
            return
        if remote and not self.is_connected():
            pane.status.setText(NOT_CONNECTED)
            return
        if not remote and self.local.path is None:
            pane.status.setText("A place or a drive is not deleted here: open it, then choose what to delete.")
            return
        path = row.split(":", 1)[1]
        name = posixpath.basename(path) if remote else Path(path).name
        kind = "folder" if row.startswith("dir:") else "file"
        where = "on the server" if remote else "from this device"
        if not self.ask(f"delete:{row}", pane, f"Press the Y button again to delete the {kind} {name} {where}"
                                               + (", with everything in it." if kind == "folder" else ".")):
            return
        sftp = self.sftp

        def work():
            if remote:
                transfers.delete_remote(sftp, path)
            else:
                transfers.delete_local(path)
            return pane, f"The {kind} is deleted {where}."

        self.run("delete", pane, work, f"Deleting {name} …")

    # The Transfers card

    def queue_job(self, pane: ListPane, job: TransferJob, said: str) -> None:
        job.skip_existing = servers.EXISTS.value(self.settings) == "skip"
        job.preserve_times = servers.TIMES.value(self.settings) == "keep"
        job.limit_kbps = int(servers.LIMIT.value(self.settings))
        self.queue.enqueue(job)
        pane.status.setText(said)
        self.log.info(f"{'Download' if job.direction == 'download' else 'Upload'} queued.")

    def job_of(self, row: str) -> TransferJob | None:
        return next((job for job in self.queue.jobs if row == f"job:{id(job)}"), None)

    def job_text(self, job: TransferJob) -> str:
        if job.state == QUEUED:
            state = "Waiting"
        elif job.state == RUNNING:
            percent = job.percent
            state = ("Counting the files" if job.total == 0 and job.done == 0 else
                     f"{percent}%  ·  {folders.size_text(job.done)} of {folders.size_text(job.total)}"
                     if percent is not None else folders.size_text(job.done))
        elif job.state == DONE:
            state = (f"Done: {job.files} file{'s' if job.files != 1 else ''}" if job.is_dir else
                     "Done" if job.files else "Skipped: it is there already")
        else:
            state = f"Failed: {job.error}"
        return f"{job.arrow} {job.name}{folders.APART}{state}"

    def show_transfers(self) -> None:
        queue, pane = self.queue, self.transfers_pane
        pane.list.set_items([(f"job:{id(job)}", self.job_text(job)) for job in queue.jobs])
        waiting, running = len(queue.jobs_in(QUEUED)), queue.running
        done, failed = len(queue.jobs_in(DONE)), len(queue.jobs_in(FAILED))
        if running is not None:
            percent = running.percent
            text = f"{running.arrow} {speed_text(queue.speed)}" + (f", {percent}%" if percent is not None else "") \
                + (f", {waiting} waiting" if waiting else "")
        elif queue.jobs:
            text = ", ".join(part for part in (f"{done} done" if done else "", f"{failed} failed" if failed else "")
                             if part) or "Nothing is moving."
        else:
            text = "Nothing yet: A on a file moves it."
        pane.summary.setText(text)
        self.transfers_card.set_text(text)
        self.update_legend()

    def transfer_row(self, row: str) -> None:
        job = self.job_of(row)
        if job is None:
            return
        if job.state == FAILED:
            if not self.is_connected():
                self.transfers_pane.status.setText(NOT_CONNECTED)
                return
            self.queue.retry(job)
            self.transfers_pane.status.setText(f"{job.name} is tried again.")
        else:
            self.transfers_pane.status.setText({QUEUED: "It waits its turn.", RUNNING: "It is moving now.",
                                                DONE: "It is done."}[job.state])

    def stop_all(self) -> None:
        pane = self.transfers_pane
        if not (self.queue.busy or self.queue.jobs_in(QUEUED)):
            pane.status.setText("Nothing is moving.")
            return
        if not self.ask("cancel", pane, "Press the Y button again to stop every transfer: a file half moved stays as "
                                        "it is."):
            return
        stopped = self.queue.cancel_all()
        pane.status.setText(f"{stopped} stopped.")
        self.log.info(f"{stopped} transfers stopped.")

    def transfer_finished(self, job: TransferJob) -> None:
        kind = "Download" if job.direction == "download" else "Upload"
        if job.state == DONE:
            self.log.info(f"{kind} done: {job.files} file{'s' if job.files != 1 else ''}.")
            if servers.SOUND.value(self.settings) == "on":
                self.beep()
            if job.direction == "upload" and self.remote is not None and \
                    posixpath.dirname(job.destination) == self.remote.path and not self.worker.busy:
                self.list_remote()
            elif job.direction == "download" and self.local.path is not None and \
                    Path(job.destination).parent == self.local.path:
                self.show_local()
        else:
            self.log.error(f"{kind} failed: {job.reason}")       # no path: it may hold a user name

    # The SSH server card

    def show_server(self) -> None:
        connected = self.is_connected() and self.connected_to is not None
        state = STATES.get(self.sshd, self.sshd) if self.sshd else "Not read yet: the A button reads it."
        self.server_pane.show_rows([("Host", self.connected_to.label if connected else "Not connected"),
                                    ("sshd", state if connected else "Connect first")])
        self.server_pane.summary.setText("The SSH server of the host you are connected to.")
        self.server_card.set_text(f"sshd: {STATES.get(self.sshd, self.sshd)}" if connected and self.sshd else
                                  "Its state; start or stop it.")
        self.update_legend()

    def server_step(self, action: str) -> None:
        """A reads sshd's state, X starts or (on a second press) stops it, Y reads sshd_config."""
        pane, client = self.server_pane, self.client
        if not self.is_connected() or client is None:
            pane.status.setText(NOT_CONNECTED)
            return
        if action == "stop" and not self.ask("stop", pane, "Press the X button again to stop sshd: no new "
                                                           "connection can be made until it is started again."):
            return
        if action == "config":
            self.run("config", pane, lambda: connection.read_sshd_config(client), "Reading sshd_config …")
            return
        said = {"status": "Reading sshd's state …", "start": "Starting sshd …", "stop": "Stopping sshd …"}[action]
        if action != "status":
            self.log.info(f"sshd: {action} asked for.")
        self.run("server", pane, lambda: connection.server_action(client, action), said)

    # The Settings card

    def show_settings(self) -> None:
        rows = [(setting.key, setting.shown(self.settings)) for setting in servers.SETTINGS]
        self.settings_pane.list.set_items([*rows, ("log", f"The app's log{folders.OPENS}")])
        self.settings_pane.summary.setText("What a transfer does. The A button changes a setting.")

    def settings_row(self, key: str) -> None:
        if key == "log":
            self.view_log()
            return
        setting = next(s for s in servers.SETTINGS if s.key == key)
        setting.step(self.settings)
        self.show_settings()
        self.settings_pane.status.setText(setting.shown(self.settings) + ".")
        if setting is servers.HIDDEN:
            self.show_local()
            if self.is_connected() and not self.worker.busy:
                self.list_remote()

    def log_lines(self) -> list[str]:
        if self.log_path is None:
            return []
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []

    def view_log(self) -> None:
        """The log's newest lines in the Settings pane: the d-pad scrolls it, B goes back (owner, 29-10-2026: not in
        Notepad, which no button closes)."""
        self.settings_pane.show_text("The log", private("\n".join(self.log_lines()[-LOG_MAX:])) or
                                     "Nothing logged yet.", end=True)
        self.settings_pane.status.setText("The d-pad scrolls it, the B button goes back.")
        self.update_legend()

    # View

    def exit_app(self) -> None:
        """View: while transfers run or wait, a second press within five seconds exits (they stop)."""
        if self.busy and not self.close_asked:
            self.close_asked = True
            self.confirm_timer.start()
            self.connection_pane.status.setText("Press View again to exit: the transfers stop.")
            self.update_legend()
            return
        self.close()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        self.confirm_timer.stop()
        self.queue.shutdown()
        self.disconnect("The app closed")
        super().closeEvent(event)

