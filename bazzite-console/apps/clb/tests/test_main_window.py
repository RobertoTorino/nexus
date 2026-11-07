# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window: signing in with a code, the consoles and cloud games, the buttons, waking and streaming."""

from __future__ import annotations

import time

import pytest
from conftest import USER_TOKEN, FakeTransport, signed_in_routes
from PyQt6.QtCore import QCoreApplication, QEvent, Qt
from PyQt6.QtWidgets import QWidget
from test_xbox import CONSOLES, DEVICES

from console_linkb import auth, xbox
from console_linkb.auth import Account
from console_linkb.main_window import MainWindow, locale_name
from console_linkb.net import Client

TITLES = "https://weu.core.gssv-play-prod.xboxlive.com/v2/titles"
LOGIN = "https://login.microsoftonline.com/consumers/oauth2/v2.0"


def routes() -> dict:
    found = signed_in_routes()
    found[("GET", DEVICES)] = (200, CONSOLES)
    found[("GET", TITLES)] = (200, {"results": [
        {"titleId": "FORTNITE", "details": {"productId": "9P1", "hasEntitlement": True}},
        {"titleId": "HALO", "details": {"productId": "9P2", "hasEntitlement": True}},
        {"titleId": "LOCKED", "details": {"productId": "9P3", "hasEntitlement": False}}]})
    found[("POST", xbox.CATALOG)] = (200, {"Products": {"9P1": {"StoreId": "9P1", "ProductTitle": "Fortnite"},
                                                        "9P2": {"StoreId": "9P2", "ProductTitle": "Halo Infinite"}}})
    found[("POST", "https://xccs.xboxlive.com/commands")] = (200, {})
    return found


class FakeView(QWidget):
    made: list = []

    def __init__(self, stream, title):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)        # as the stream's window
        self.stream, self.title = stream, title
        FakeView.made.append(self)

    def showFullScreen(self):  # noqa: N802 (Qt override)
        self.show()


def wait(qapp, window, condition=None, timeout=5.0) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        if (condition() if condition else not window.worker.running):
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


@pytest.fixture
def signed_in(qapp, tmp_path):
    transport = FakeTransport(routes())
    auth.save_refresh_token("RT-1", tmp_path / "a.json")
    window = MainWindow(Account(Client(transport), tmp_path / "a.json"), stream_window=FakeView)
    wait(qapp, window)
    yield window, transport
    window.close()


def test_locale_name():
    assert "-" in locale_name()


def test_signed_out_window(qapp, tmp_path):
    window = MainWindow(Account(Client(FakeTransport()), tmp_path / "none.json"), stream_window=FakeView)
    assert window.pill.text() == "Signed out"
    assert "Not signed in" in window.account_state.text()
    assert window.sign_in_button.isEnabled() and not window.sign_out_button.isEnabled()
    assert not window.refresh_button.isEnabled() and not window.stream_console_button.isEnabled()
    assert window.account_box.value.text() == "—"
    window.close()


def test_signed_in_window_lists_consoles_and_games(qapp, signed_in):
    window, _transport = signed_in
    assert window.pill.text() == "Ready"
    assert window.account_box.value.text() == "Player One"
    assert "Player One" in window.account_state.text()
    assert window.console_table.rowCount() == 2
    assert window.console_table.item(0, 0).text() == "Living room"
    assert window.console_table.item(0, 2).text() == "Sleep"
    assert window.console_table.item(1, 3).text().startswith("Off")
    assert [window.title_table.item(r, 0).text() for r in range(window.title_table.rowCount())] == \
        ["Fortnite", "Halo Infinite"]                   # sorted; the one without entitlement left out
    assert window.cloud_box.value.text() == "Game Pass"
    assert window.consoles_box.value.text() == "2"
    assert "Player One" not in window.output.toPlainText()          # the gamertag stays out of the log


def test_search_filters_the_games(qapp, signed_in):
    window, _transport = signed_in
    window.search.setText("halo")
    assert window.title_table.rowCount() == 1 and window.title_table.item(0, 0).text() == "Halo Infinite"
    window.search.setText("")
    assert window.title_table.rowCount() == 2


def test_buttons_follow_the_chosen_console(qapp, signed_in):
    window, _transport = signed_in
    assert not window.wake_button.isEnabled() and not window.stream_console_button.isEnabled()
    window.console_table.selectRow(0)
    assert window.wake_button.isEnabled() and window.stream_console_button.isEnabled()
    window.console_table.selectRow(1)                   # off, no remote features
    assert not window.wake_button.isEnabled()


def test_wake(qapp, signed_in):
    window, transport = signed_in
    window.console_table.selectRow(0)
    window.on_wake()
    wait(qapp, window)
    assert transport.sent("POST", "https://xccs.xboxlive.com/commands")[0]["command"] == "WakeUp"
    assert "Living room is waking up" in window.running.text()


def test_streaming_a_console_with_remote_play_off_is_refused(qapp, signed_in):
    window, _transport = signed_in
    window.console_table.selectRow(1)
    FakeView.made.clear()
    window.on_stream_console()
    assert not FakeView.made and "Remote play is off" in window.running.text()


def test_streaming_opens_the_window_and_closing_it_frees_the_buttons(qapp, signed_in, monkeypatch):
    window, _transport = signed_in
    started = []
    monkeypatch.setattr("console_linkb.stream.Stream.start", lambda self: started.append((self.kind, self.target)))
    FakeView.made.clear()
    window.console_table.selectRow(0)
    window.on_stream_console()
    assert started == [("home", "F4001234ABCD5678")]
    view = FakeView.made[0]
    assert view.title == "Living room" and window.pill.text() == "Streaming"
    assert not window.stream_title_button.isEnabled() and not window.sign_out_button.isEnabled()
    window.on_stream_title()                            # one stream at a time
    assert len(FakeView.made) == 1
    view.stream.ended.emit("the connection to the stream was lost")
    assert "connection to the stream was lost" in window.running.text()
    view.close()
    wait(qapp, window, lambda: window.stream_view is None)
    assert window.pill.text() == "Ready"
    window.title_table.selectRow(0)
    window.on_stream_title()
    assert started[-1] == ("cloud", "FORTNITE")
    FakeView.made[-1].close()


def test_signing_in_with_a_code(qapp, tmp_path):
    transport = FakeTransport(routes())
    transport.add("POST", f"{LOGIN}/devicecode", (200, {"user_code": "ABCD-EFGH", "device_code": "DC",
                                                        "verification_uri": "https://www.microsoft.com/link",
                                                        "expires_in": 900, "interval": 1}))
    transport.add("POST", f"{LOGIN}/token", (200, USER_TOKEN))
    window = MainWindow(Account(Client(transport), tmp_path / "a.json"), stream_window=FakeView)
    window.on_sign_in()
    wait(qapp, window, lambda: window.code is not None)
    assert "ABCD-EFGH" in window.account_state.text() and "microsoft.com/link" in window.account_state.text()
    assert window.sign_in_button.text() == "Cancel" and window.pill.text() == "Signing in"
    wait(qapp, window, lambda: window.account.signed_in and not window.worker.running and window.consoles, 10)
    assert window.code is None and window.account_box.value.text() == "Player One"
    assert auth.load_refresh_token(tmp_path / "a.json") == "RT-1"
    window.close()


def test_cancelling_the_sign_in(qapp, tmp_path):
    transport = FakeTransport(routes())
    transport.add("POST", f"{LOGIN}/devicecode", (200, {"user_code": "ABCD-EFGH", "device_code": "DC",
                                                        "verification_uri": "https://www.microsoft.com/link",
                                                        "expires_in": 900, "interval": 1}))
    transport.add("POST", f"{LOGIN}/token", (400, {"error": "authorization_pending"}))
    window = MainWindow(Account(Client(transport), tmp_path / "a.json"), stream_window=FakeView)
    window.on_sign_in()
    wait(qapp, window, lambda: window.code is not None)
    window.on_sign_in()                                 # Cancel
    wait(qapp, window, lambda: window.code is None, 5)
    assert not window.account.signed_in and "canceled" in window.running.text()
    assert window.sign_in_button.text() == "Sign in"
    window.close()


def test_sign_out(qapp, signed_in, monkeypatch, tmp_path):
    window, _transport = signed_in
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.on_sign_out()
    assert not window.account.signed_in and window.console_table.rowCount() == 0
    assert window.pill.text() == "Signed out" and not (tmp_path / "a.json").exists()


def test_without_cloud_gaming_the_consoles_still_show(qapp, tmp_path):
    found = routes()
    for offering in ("xgpuweb", "xgpuwebf2p"):
        found[("POST", f"https://{offering}.gssv-play-prod.xboxlive.com/v2/login/user")] = (403, b"")
    auth.save_refresh_token("RT-1", tmp_path / "a.json")
    window = MainWindow(Account(Client(FakeTransport(found)), tmp_path / "a.json"), stream_window=FakeView)
    wait(qapp, window)
    assert window.console_table.rowCount() == 2 and window.title_table.rowCount() == 0
    assert window.cloud_state.text().startswith("No cloud games")
    assert window.cloud_box.value.text() == "—"
    window.close()


def test_a_refused_sign_in_signs_out(qapp, tmp_path):
    found = routes()
    found[("POST", f"{LOGIN}/token")] = (400, {"error": "invalid_grant"})
    auth.save_refresh_token("RT-1", tmp_path / "a.json")
    window = MainWindow(Account(Client(FakeTransport(found)), tmp_path / "a.json"), stream_window=FakeView)
    wait(qapp, window)
    assert not window.account.signed_in and window.pill.text() == "Signed out"
    assert "sign in again" in window.running.text()
    window.close()
