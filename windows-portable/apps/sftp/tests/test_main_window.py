# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py) on a fake server: it opens on the portable window with the header's battery, date and
time and fits the handheld's screen; the fields are filled on their pages, X connects (a new server's key shown and
trusted on X again), the server's files are listed from the home, A downloads, Y deletes on a second press, the
SSH server card reads and stops sshd, the settings step, B goes back and View exits (asking first while transfers
wait); the version and the icons are where the checks expect them."""

from __future__ import annotations

import re
import time

import paramiko
import pytest
from PyQt6.QtCore import QSettings

from bc250_core import portable
from bc250_core.gamepad import Gamepad
from bc250_core.portable import EXIT, INFO as INFO_ITEM, KEYBOARD
from fake_sftp import FakeClient
from sftp_tools import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, connection, servers
from sftp_tools.main_window import NOT_CONNECTED, MainWindow
from sftp_tools.servers import Server
from sftp_tools.transfer_queue import DONE, TransferJob


class FakePad:
    def events(self):
        return []

    def close(self):
        pass

    def names(self):
        return []


class Server_:
    """The fake server: connect() hands out a FakeClient on *root*; the first connection may raise an unknown key."""

    def __init__(self, root, answers=None, new_key=None):
        self.root, self.answers, self.new_key = root, answers or {}, new_key
        self.calls = []

    def connect(self, host, port, user, password="", key="", compression=True, known_hosts=None):
        self.calls.append((host, port, user, password, key, compression))
        if self.new_key is not None and not (known_hosts and known_hosts.is_file()):
            raise connection.UnknownHostKeyError(host, port, self.new_key)
        return FakeClient(self.root, self.answers)


def wait(qapp, until, seconds: float = 10) -> None:
    end = time.monotonic() + seconds
    while not until() and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)
    assert until()


@pytest.fixture
def home(tmp_path):
    folder = tmp_path / "home"
    (folder / "Downloads").mkdir(parents=True)
    return folder


def make(qapp, tmp_path, home, server: Server_ | None = None):
    settings = QSettings(str(tmp_path / "app.ini"), QSettings.Format.IniFormat)
    server = server or Server_(tmp_path / "server")
    window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False), connect=server.connect,
                        known_hosts=tmp_path / "known_hosts", settings=settings, roots=lambda: [], user_home=home,
                        beep=lambda: None)
    portable.scale((1280, 720))
    window.resize(1280, 720)
    window.show()
    qapp.processEvents()
    window.start()
    return window


def fill(window, key: str, value: str) -> None:
    """A on the field's row, the value typed, A keeps it."""
    window.connection_row(key)
    assert window.panes.currentWidget() is window.field_pane
    window.field_pane.field.setText(value)
    window.a_action()
    assert window.panes.currentWidget() is window.connection_pane


def connected(qapp, window, tmp_path, password="") -> None:
    fill(window, "host", "192.168.1.20")
    fill(window, "user", "me")
    if password:
        fill(window, "password", password)
    window.connection_pane.list.focus("host")
    window.x_action()
    wait(qapp, lambda: window.is_connected() and not window.worker.busy)


def test_the_window_opens_with_the_suites_header(qapp, tmp_path, home):
    window = make(qapp, tmp_path, home)
    assert window.header.title.text() == APP_NAME and window.header.version.text() == __version__
    assert re.fullmatch(r"\w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d  \|  82%", window.header.status.text())
    assert window.legend.items == [("A", "Change"), ("X", "Connect"), INFO_ITEM, EXIT]
    assert window.connection_card.text.text() == "Not connected: X connects."
    window.close()


def test_the_window_fits_the_handhelds_screen(qapp, tmp_path, home):
    window = make(qapp, tmp_path, home)
    assert window.minimumSizeHint().height() <= 720 and window.height() == 720
    window.close()


def test_b_goes_back_and_view_exits(qapp, tmp_path, home, monkeypatch):
    """The suite's buttons: B goes back (with nowhere to go, nothing happens) and View exits the app, on a second
    press while a transfer waits."""
    window = make(qapp, tmp_path, home)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.connection_card.activated.emit()                     # A on the card: into its rows
    assert window.connection_pane.list.focused() == "host"
    window.on_action("back")
    assert window.focusWidget() is window.connection_card and closed == []
    window.queue.jobs.append(TransferJob("upload", "a", "b", False))
    window.on_action("view")
    assert closed == [] and window.legend.items == [("⧉", "Press again to exit")]
    window.on_action("view")
    assert closed == [True]


def test_the_fields_are_kept_and_the_password_never_saved(qapp, tmp_path, home):
    window = make(qapp, tmp_path, home)
    window.connection_row("password")
    assert window.legend.items == [("A", "Keep"), ("X", "Paste"), KEYBOARD, ("B", "Back"), EXIT]
    window.on_back()                                            # B: nothing kept
    fill(window, "host", " board ")
    fill(window, "password", "Secret#42 x")
    window.connection_row("port")
    window.field_pane.field.setText("99999")
    window.a_action()
    assert window.field_pane.status.text() == "The port is a number from 1 to 65535."
    window.field_pane.field.setText("2222")
    window.a_action()
    assert window.server == Server("board", 2222, "", "") and window.password == "Secret#42 x"
    assert servers.last(window.settings) == Server("board", 2222)
    window.settings.sync()
    assert "board" in (tmp_path / "app.ini").read_text() and "Secret" not in (tmp_path / "app.ini").read_text()
    assert window.connection_pane.list.pills["port"].label.text() == "Port: 2222"
    window.close()


def test_x_says_what_is_missing_before_connecting(qapp, tmp_path, home):
    window = make(qapp, tmp_path, home)
    window.x_action()
    assert window.connection_pane.status.text().startswith("Fill in the host first")
    fill(window, "host", "board")
    fill(window, "user", "me")
    fill(window, "password", "simple")
    window.x_action()
    assert window.connection_pane.status.text().startswith("The password needs 8 characters, a capital")
    assert not window.worker.busy
    window.close()


def test_x_connects_and_the_servers_files_are_listed_from_the_home(qapp, tmp_path, home):
    server = Server_(tmp_path / "server")
    (tmp_path / "server" / "var" / "home" / "me" / "Games").mkdir(parents=True)
    (tmp_path / "server" / "var" / "home" / "me" / "save.dat").write_bytes(b"s" * 40)
    window = make(qapp, tmp_path, home, server)
    connected(qapp, window, tmp_path, password="Secret#42")
    assert server.calls == [("192.168.1.20", 22, "me", "Secret#42", "", True)]
    assert window.connection_card.text.text() == "Connected: me@192.168.1.20"
    assert servers.servers(window.settings) == [Server("192.168.1.20", 22, "me")]
    assert "Saved: me@192.168.1.20" in [p.label.text() for p in window.connection_pane.list.pills.values()]
    assert list(window.remote_pane.list.pills) == ["up", "dir:/var/home/me/Games", "file:/var/home/me/save.dat"]
    assert window.remote_card.text.text() == "In ~"
    summary = window.remote_pane.summary.text()
    assert summary.startswith("~   ") and "downloads go to %USERPROFILE%" in summary and "/var/home/me" not in summary
    window.remote_card.setFocus()
    window.remote_pane.list.focus("dir:/var/home/me/Games")
    assert window.legend.items[:3] == [("A", "Open"), ("X", "Download"), ("Y", "Delete")]
    window.remote_row("dir:/var/home/me/Games")
    wait(qapp, lambda: not window.worker.busy and window.remote.path == "/var/home/me/Games")
    assert window.remote_card.text.text() == "In ~/Games"
    window.on_back()                                            # B: a folder up, the focus on the one it came from
    wait(qapp, lambda: not window.worker.busy and window.remote.path == "/var/home/me")
    assert window.remote_pane.list.focused() == "dir:/var/home/me/Games"
    window.on_back()                                            # at the home: back to the card
    assert window.focusWidget() is window.remote_card
    window.close()


def test_a_new_servers_key_is_shown_then_trusted_on_x_again(qapp, tmp_path, home):
    key = paramiko.ECDSAKey.generate()
    server = Server_(tmp_path / "server", new_key=key)
    window = make(qapp, tmp_path, home, server)
    fill(window, "host", "board")
    fill(window, "user", "me")
    window.x_action()
    wait(qapp, lambda: not window.worker.busy and window.untrusted is not None)
    assert connection.fingerprint(key) in window.connection_pane.status.text()
    assert not window.is_connected() and ("X", "Trust and connect") in window.legend.items
    window.x_action()
    wait(qapp, lambda: window.is_connected() and not window.worker.busy)
    assert paramiko.HostKeys(str(tmp_path / "known_hosts")).lookup("board")
    window.close()


def test_a_download_goes_to_this_devices_folder(qapp, tmp_path, home):
    (tmp_path / "server" / "var" / "home" / "me").mkdir(parents=True)
    (tmp_path / "server" / "var" / "home" / "me" / "save.dat").write_bytes(b"s" * 40)
    window = make(qapp, tmp_path, home)
    connected(qapp, window, tmp_path)
    window.remote_row("file:/var/home/me/save.dat")             # A on a file
    job = window.queue.jobs[0]
    wait(qapp, lambda: job.state == DONE)
    assert (home / "Downloads" / "save.dat").read_bytes() == b"s" * 40       # the places: Downloads
    assert window.transfers_pane.list.pills[f"job:{id(job)}"].label.text() == "↓ save.dat  ·  Done"
    assert window.transfers_card.text.text() == "1 done"
    window.close()


def test_y_deletes_on_a_second_press(qapp, tmp_path, home):
    (tmp_path / "server" / "var" / "home" / "me").mkdir(parents=True)
    old = tmp_path / "server" / "var" / "home" / "me" / "old.txt"
    old.write_text("old")
    window = make(qapp, tmp_path, home)
    connected(qapp, window, tmp_path)
    window.remote_card.setFocus()
    window.remote_pane.list.focus("file:/var/home/me/old.txt")
    window.y_action()
    assert old.exists() and window.remote_pane.status.text().startswith("Press the Y button again to delete")
    assert ("Y", "Press again") in window.legend.items
    window.y_action()
    wait(qapp, lambda: not window.worker.busy and "file:/var/home/me/old.txt" not in window.remote_pane.list.pills)
    assert not old.exists()
    window.close()


def test_the_ssh_server_card_reads_and_stops_sshd(qapp, tmp_path, home):
    answers = {connection.SERVICE_COMMANDS["status"]: ("active\n", "", 0)}
    window = make(qapp, tmp_path, home, Server_(tmp_path / "server", answers))
    window.server_step("status")
    assert window.server_pane.status.text() == NOT_CONNECTED
    connected(qapp, window, tmp_path)
    window.server_card.setFocus()
    window.server_card.activated.emit()                         # A reads the state
    wait(qapp, lambda: not window.worker.busy and window.sshd == "active")
    assert window.server_card.text.text() == "sshd: Running"
    assert window.legend.items[:3] == [("A", "Read the state"), ("X", "Stop sshd"), ("Y", "sshd_config")]
    window.x_action()
    assert window.server_pane.status.text().startswith("Press the X button again to stop sshd")
    window.x_action()
    wait(qapp, lambda: not window.worker.busy)
    assert connection.SERVICE_COMMANDS["stop"] in window.client.commands
    window.close()


def test_the_settings_step_and_the_log_is_read_in_the_app(qapp, tmp_path, home):
    window = make(qapp, tmp_path, home)
    window.log_path = tmp_path / "app.log"
    window.log_path.write_text("one\ntwo\n", encoding="utf-8")
    window.settings_card.setFocus()
    window.settings_row("exists")
    assert window.settings_pane.list.pills["exists"].label.text() == "If a file is there already: Overwrite it"
    window.settings_row("log")
    assert window.settings_pane.viewing and window.settings_pane.view.toPlainText() == "one\ntwo"
    window.on_back()
    assert not window.settings_pane.viewing
    window.close()


def test_nothing_moves_before_connecting(qapp, tmp_path, home):
    window = make(qapp, tmp_path, home)
    (home / "Downloads" / "mine.txt").write_text("x")
    window.local_row(f"dir:{home / 'Downloads'}")
    window.local_row(f"file:{home / 'Downloads' / 'mine.txt'}")
    assert window.local_pane.status.text() == NOT_CONNECTED and window.queue.jobs == []
    window.remote_card.activated.emit()
    assert window.remote_pane.status.text() == NOT_CONNECTED
    window.close()


def test_version_is_the_single_source():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__ == INFO.version


def test_icons_are_beside_the_package():
    assert LOGO_PATH.is_file() and LOGO_PATH.name == f"{APP_ID}.webp"
    assert (ROOT / "images" / f"{APP_ID}-128.png").is_file()
    assert re.fullmatch(r"[A-Za-z0-9-]+", EXE_NAME)


def test_the_log_holds_no_host_user_name_or_path(qapp, tmp_path, home, caplog):
    """The privacy rule (owner, 29-10-2026): a connection and a failed download log what happened, never where."""
    (tmp_path / "server" / "var" / "home" / "me").mkdir(parents=True)
    window = make(qapp, tmp_path, home)
    with caplog.at_level("INFO", logger=APP_ID):
        fill(window, "host", "nas.example")
        fill(window, "user", "someone")
        window.x_action()
        wait(qapp, lambda: window.is_connected() and not window.worker.busy)
        window.download("/var/home/someone/gone.txt", is_dir=False)
        job = window.queue.jobs[0]
        wait(qapp, lambda: job.state == "failed")
        window.close()
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "Connected to a server." in logged and "Download failed:" in logged
    assert "nas.example" not in logged and "someone" not in logged and "gone.txt" not in logged
    assert "gone.txt" in job.error                              # the row says which, on the screen
