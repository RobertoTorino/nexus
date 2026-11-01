# SPDX-License-Identifier: AGPL-3.0-or-later
"""The window (main_window.py) on fake network steps: it opens on the portable window with the header's battery, date
and time and fits the handheld's screen; X searches, A on a console chooses it for registering, the fields are filled
on their pages, the sign-in's address is taken from the clipboard, X registers, and on My consoles A wakes, X tests a
session, RB puts the console in rest mode and Y removes it on a second press, LB sets its login passcode; the personal
details are masked until Settings shows them, and always in the log; B goes back and View exits. jobs.py end to end
against the fake console; the version and the icons are where the checks expect them."""

from __future__ import annotations

import re
import time

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QGuiApplication

from bc250_core import portable
from bc250_core.gamepad import Gamepad
from bc250_core.portable import EXIT, INFO as INFO_ITEM, KEYBOARD
from fake_console import AMBASSADOR, MAC, REGIST_KEY, RP_KEY, RegistConsole, SessionConsole
from remote_play import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, jobs, psn
from remote_play.consoles import ConsoleStore, RegisteredConsole
from remote_play.discovery import Console
from remote_play.jobs import Outcome
from remote_play.main_window import MainWindow
from remote_play.session import SessionInfo
from remote_play.target import Target

PS5 = Console("192.168.1.20", True, "ready", host_name="Living room PS5", host_id="AABBCCDDEEFF", host_type="PS5",
              system_version="08050001")
PS4 = Console("192.168.1.21", False, "standby", host_name="PS4-Pro", host_id="001122334455", host_type="PS4",
              system_version="11008001")
ACCOUNT = "AQIDBAUGBwg="                # bytes 1 to 8


def registered(console: Console = PS5, **changes) -> RegisteredConsole:
    data = dict(host_id=console.host_id, nickname=console.host_name, address=console.address, target=console.target,
                regist_key=REGIST_KEY, rp_key=RP_KEY, mac=MAC)
    return RegisteredConsole(**{**data, **changes})


class FakePad:
    def events(self):
        return []

    def close(self):
        pass

    def names(self):
        return []


class FakeOps:
    """jobs.py as the window calls it; records the calls."""

    def __init__(self, found=(PS5, PS4)):
        self.found, self.calls = list(found), []

    def find(self, address=""):
        self.calls.append(("find", address))
        found = [c for c in self.found if not address or c.address == address]
        return Outcome(True, f"{len(found)} consoles found.", found)

    def psn_account(self, redirect):
        self.calls.append(("account", redirect))
        return Outcome(True, "Account ID of your PSN account (player_one): AQIDBAUGBwg=, filled in.",
                       psn.Account(bytes(range(1, 9)), "player_one"))

    def register(self, console, account_id, pin):
        self.calls.append(("register", console.host_name, account_id, pin))
        return Outcome(True, f"Registered with {console.host_name}.", registered(console))

    def wake(self, console):
        self.calls.append(("wake", console.nickname))
        return Outcome(True, f"Wake-up sent to {console.nickname}.")

    def test_session(self, console):
        self.calls.append(("test", console.nickname))
        return Outcome(True, "Session started and closed again (PS5).", SessionInfo(console.target, "PS5"))

    def rest_mode(self, console):
        self.calls.append(("rest", console.nickname))
        return Outcome(True, f"{console.nickname} goes to rest mode.")


def wait(qapp, until, seconds: float = 10) -> None:
    end = time.monotonic() + seconds
    while not until() and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)
    assert until()


@pytest.fixture
def make(qapp, tmp_path):
    windows = []

    def make(ops=None, consoles=(), opened=None, log_path=None):
        store = ConsoleStore(tmp_path / "data")
        if consoles:
            store.save(list(consoles))
        settings = QSettings(str(tmp_path / "rplay.ini"), QSettings.Format.IniFormat)
        window = MainWindow(log_path=log_path, gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False),
                            folder=tmp_path / "data", settings=settings, ops=ops or FakeOps(),
                            open_url=lambda url: (opened.append(url) if opened is not None else None) or True)
        portable.scale((1280, 720))
        window.resize(1280, 720)
        window.show()
        qapp.processEvents()
        window.start()
        windows.append(window)
        return window

    yield make
    for window in windows:
        window.close()


def press(window, *actions):
    for action in actions:
        window.act(action)


def idle(qapp, window):
    wait(qapp, lambda: not window.worker.busy)
    qapp.processEvents()


def legend(window):
    return [label for _glyph, label in window.legend.items]


def test_the_window_opens_with_the_suites_header(make):
    window = make()
    assert window.header.title.text() == APP_NAME and window.header.version.text() == __version__
    assert re.fullmatch(r"\w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d  \|  82%", window.header.status.text())
    assert window.consoles_card.hasFocus() and window.panes.currentWidget() is window.consoles_pane
    assert window.consoles_card.text.text() == "Not searched yet: X searches the network."
    assert window.legend.items[-1] == EXIT and INFO_ITEM in window.legend.items


def test_the_window_fits_the_handhelds_screen(make):
    window = make()
    assert window.minimumSizeHint().height() <= 720 and window.height() == 720


def test_nothing_runs_before_it_is_asked_for(make):
    ops = FakeOps()
    make(ops)
    assert ops.calls == []


def test_x_searches_and_a_chooses_a_console_for_registering(qapp, make):
    ops = FakeOps()
    window = make(ops)
    press(window, "x")
    idle(qapp, window)
    assert ops.calls == [("find", "")]
    rows = window.consoles_pane.list.pills
    assert list(rows) == ["found:AABBCCDDEEFF", "found:001122334455", "address"]
    assert rows["found:AABBCCDDEEFF"].label.text() == \
        "Living room PS5  ·  PS5  ·  •••.•••.•••.20  ·  On  ·  not registered"      # masked
    assert "Rest mode" in rows["found:001122334455"].label.text()
    assert window.consoles_card.text.text() == "2 found: Living room PS5, PS4-Pro"
    window.consoles_pane.list.focus("found:001122334455")
    assert legend(window)[:3] == ["Register", "Search the network", "Search the address"]
    press(window, "accept")
    assert window.panes.currentWidget() is window.register_pane and window.chosen == "001122334455"
    assert window.pane_card is window.register_card                    # the card of the pane that shows
    assert window.register_pane.list.focused() == "account"        # no account ID yet
    assert "your account ID next, then the PIN" in window.register_pane.status.text()
    assert "PS4-Pro" in window.register_pane.list.pills["console"].label.text()


def test_a_on_a_registered_console_goes_to_it_on_my_consoles(qapp, make):
    window = make(consoles=[registered()])
    press(window, "x")
    idle(qapp, window)
    window.consoles_pane.list.focus("found:AABBCCDDEEFF")
    assert legend(window)[0] == "My consoles"
    press(window, "accept")
    assert window.panes.currentWidget() is window.mine_pane and window.pane_card is window.mine_card
    assert window.mine_pane.list.focused() == "mine:AABBCCDDEEFF"
    press(window, "back")
    assert window.mine_card.hasFocus()


def test_a_search_at_one_address_keeps_the_others(qapp, make):
    ops = FakeOps()
    window = make(ops)
    press(window, "y")
    assert "Fill in the address first" in window.consoles_pane.status.text() and ops.calls == []
    window.settings.setValue("address", "192.168.1.21")
    press(window, "x")
    idle(qapp, window)
    ops.found = [PS4]
    press(window, "y")
    idle(qapp, window)
    assert ops.calls[-1] == ("find", "192.168.1.21")
    assert [c.host_name for c in window.found] == ["Living room PS5", "PS4-Pro"]


def test_the_address_page_keeps_the_address(qapp, make):
    window = make()
    window.consoles_card.setFocus()
    press(window, "accept")                             # the list: its only row is the address
    assert window.consoles_pane.list.focused() == "address"
    press(window, "accept")
    assert window.panes.currentWidget() is window.field_pane
    assert legend(window)[:2] == ["Keep", "Paste"] and KEYBOARD in window.legend.items
    window.field_pane.field.setText(" 192.168.1.30 ")
    press(window, "accept")
    assert window.address() == "192.168.1.30" and window.panes.currentWidget() is window.consoles_pane
    shown = window.consoles_pane.list.pills["address"].label.text()
    assert shown == "Search an address: •••.•••.•••.30"
    assert window.consoles_pane.list.focused() == "address"
    press(window, "accept")
    window.field_pane.field.setText("192.168.1.40")
    press(window, "back")                               # nothing kept
    assert window.address() == "192.168.1.30" and window.field_pane.field.text() == ""


def test_registering_with_the_sign_in_and_the_pin(qapp, make, tmp_path):
    ops, opened = FakeOps(), []
    window = make(ops, opened=opened)
    press(window, "x")
    idle(qapp, window)
    window.register_card.setFocus()
    press(window, "accept")
    window.register_pane.list.focus("signin")
    assert legend(window)[:2] == ["Sign in", "Register"]
    clipboard = QGuiApplication.clipboard()
    clipboard.setText("something copied before")
    press(window, "accept")
    assert opened == [psn.login_url()] and window.signing_in
    clipboard.setText("https://example.com/not-the-sign-in")
    qapp.processEvents()
    assert window.signing_in and not window.worker.busy                  # anything else is left alone
    clipboard.setText(f"{psn.REDIRECT_URI}?code=v3abc")
    window.check_clipboard()                            # dataChanged, or the window active again
    idle(qapp, window)
    assert ops.calls[-1] == ("account", f"{psn.REDIRECT_URI}?code=v3abc") and not window.signing_in
    assert window.account() == ACCOUNT
    assert window.register_pane.list.pills["account"].label.text() == "Account ID: ••••••••Bwg="
    assert "player_one" not in window.register_pane.status.text()       # the online ID masked too
    assert window.register_pane.list.focused() == "pin"
    press(window, "x")
    assert "8 digits" in window.register_pane.status.text()
    press(window, "accept")
    window.field_pane.field.setText("1234567")
    press(window, "accept")
    assert window.panes.currentWidget() is window.field_pane and "8 digits" in window.field_pane.status.text()
    window.field_pane.field.setText("1234 5678")
    press(window, "accept")
    assert window.register_pane.list.pills["pin"].label.text() == "PIN: Typed"
    assert window.register_card.text.text() == "Ready: X registers."
    press(window, "x")
    idle(qapp, window)
    assert ops.calls[-1] == ("register", "Living room PS5", bytes(range(1, 9)), 12345678)
    assert window.pin == "" and [c.nickname for c in ConsoleStore(tmp_path / "data").load()] == ["Living room PS5"]
    assert window.mine_card.text.text() == "1 registered."
    assert "registered" in window.consoles_pane.list.pills["found:AABBCCDDEEFF"].label.text()
    assert window.chosen == "001122334455"               # the next console not registered with


def test_register_says_what_is_missing(qapp, make):
    window = make()
    window.register_card.setFocus()
    press(window, "accept")
    press(window, "x")
    assert "Choose the console first: Search first" in window.register_pane.status.text()
    window.register_pane.list.focus("console")
    press(window, "accept")
    assert "No console to register" in window.register_pane.status.text()


def test_my_consoles_wake_test_and_rest_mode(qapp, make):
    ops = FakeOps()
    window = make(ops, consoles=[registered()])
    window.mine_card.setFocus()
    press(window, "accept")
    assert window.mine_pane.list.focused() == "mine:AABBCCDDEEFF"
    assert legend(window)[:5] == ["Wake", "Test session", "Remove", "Login passcode", "Rest mode"]
    assert window.mine_pane.list.pills["mine:AABBCCDDEEFF"].label.text() == "Living room PS5  ·  PS5  ·  Not searched"
    press(window, "accept")
    idle(qapp, window)
    assert ops.calls == [("wake", "Living room PS5")] and "Wake-up sent" in window.mine_pane.status.text()
    press(window, "x")
    idle(qapp, window)
    assert ops.calls[-1] == ("test", "Living room PS5") and window.session_info == {"AABBCCDDEEFF": "PS5"}
    press(window, "next")
    assert ops.calls[-1][0] == "test" and "Press RB again" in window.mine_pane.status.text()
    assert "Press again" in legend(window)
    press(window, "next")
    idle(qapp, window)
    assert ops.calls[-1] == ("rest", "Living room PS5")


def test_a_second_press_runs_out(qapp, make):
    window = make(consoles=[registered()])
    window.mine_card.setFocus()
    press(window, "accept", "y")
    assert window.asked == "remove:AABBCCDDEEFF"
    window.confirm_timer.timeout.emit()
    assert window.asked == "" and window.mine_pane.status.text() == "" and "Remove" in legend(window)


def test_y_removes_on_a_second_press(qapp, make, tmp_path):
    window = make(consoles=[registered(), registered(PS4)])
    window.mine_card.setFocus()
    press(window, "accept", "y")
    assert "Press the Y button again to remove Living room PS5" in window.mine_pane.status.text()
    assert len(ConsoleStore(tmp_path / "data").load()) == 2
    press(window, "y")
    assert [c.nickname for c in ConsoleStore(tmp_path / "data").load()] == ["PS4-Pro"]
    assert window.mine_pane.status.text() == "Living room PS5 is removed."
    assert window.mine_pane.list.focused() == "mine:001122334455"


def test_lb_sets_the_login_passcode(qapp, make, tmp_path):
    window = make(consoles=[registered()])
    window.mine_card.setFocus()
    press(window, "accept", "previous")
    assert window.panes.currentWidget() is window.field_pane and "Living room PS5" in window.field_pane.text.text()
    window.field_pane.field.setText("12a4")
    press(window, "accept")
    assert "4 digits" in window.field_pane.status.text()
    window.field_pane.field.setText("0420")
    press(window, "accept")
    assert ConsoleStore(tmp_path / "data").load()[0].login_pin == "0420"
    assert window.panes.currentWidget() is window.mine_pane and window.mine_pane.list.focused() == "mine:AABBCCDDEEFF"
    assert window.mine_pane.list.pills["mine:AABBCCDDEEFF"].label.text().endswith("passcode set")


def test_a_search_moves_a_registered_console_to_its_new_address(qapp, make, tmp_path):
    moved = Console("192.168.1.99", True, "ready", host_name="Living room PS5", host_id=PS5.host_id, host_type="PS5",
                    system_version="08050001", running_app="Astro Bot")
    window = make(FakeOps(found=[moved]), consoles=[registered()])
    press(window, "x")
    idle(qapp, window)
    assert ConsoleStore(tmp_path / "data").load()[0].address == "192.168.1.99"
    window.mine_card.setFocus()
    press(window, "accept")
    assert window.mine_pane.summary.text() == "Living room PS5: PS5  ·  running Astro Bot  ·  Remote Play 1.0"


def test_personal_details_shown_from_settings_and_never_in_the_log(qapp, make, tmp_path):
    log = tmp_path / "rplay.log"
    log.write_text("Asking 192.168.1.20 …\n", encoding="utf-8")
    window = make(log_path=log)
    press(window, "x")
    idle(qapp, window)
    row = window.consoles_pane.list.pills["found:AABBCCDDEEFF"]
    assert "•••.•••.•••.20" in row.label.text()
    window.settings_card.setFocus()
    press(window, "accept", "accept")
    assert window.revealed and "192.168.1.20" in window.consoles_pane.list.pills["found:AABBCCDDEEFF"].label.text()
    window.settings_pane.list.focus("log")
    press(window, "accept")
    assert window.settings_pane.viewing and "192.168.1.20" not in window.settings_pane.view.toPlainText()
    assert "•••.•••.•••.20" in window.settings_pane.view.toPlainText()
    press(window, "back")
    assert not window.settings_pane.viewing and window.settings_pane.list.focused() == "log"
    assert window.panes.currentWidget() is window.settings_pane


def test_b_goes_back_and_view_exits(make, monkeypatch):
    """The suite's buttons: B goes back (with nowhere to go, nothing happens) and View exits the app."""
    window = make(consoles=[registered()])
    window.mine_card.setFocus()
    window.act("accept")
    assert not window.mine_card.hasFocus()
    window.act("back")
    assert window.mine_card.hasFocus()
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("back")
    assert closed == []
    window.on_action("view")
    assert closed == [True]


def test_jobs_against_the_fake_console():
    """jobs.py end to end: registration, a test session and rest mode against the fake console on localhost."""
    reg = RegistConsole(target=Target.PS5_1)
    try:
        outcome = jobs.register(Console("127.0.0.1", True, "ready", host_id="X", system_version="08050001"),
                                bytes(range(8)), 12345678, port=reg.port, timeout=2.0, pause=0,
                                random=lambda n: AMBASSADOR[:n])
    finally:
        reg.close()
    assert outcome.ok and outcome.value.regist_key == REGIST_KEY and outcome.value.address == "127.0.0.1"
    console = SessionConsole()
    try:
        tested = jobs.test_session(outcome.value, seconds=0.1, port=console.port, timeout=2.0)
    finally:
        console.close()
    assert tested.ok and tested.value.server_type == "PS5", tested.message
    closed = SessionConsole()
    closed.close()
    failed = jobs.test_session(outcome.value, seconds=0.1, port=closed.port, timeout=1.0)
    assert not failed.ok and "rest mode" in failed.message


def test_version_is_the_single_source():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__ == INFO.version


def test_icons_are_beside_the_package():
    assert LOGO_PATH.is_file() and LOGO_PATH.name == f"{APP_ID}.webp"
    assert (ROOT / "images" / f"{APP_ID}-128.png").is_file()
    assert re.fullmatch(r"[A-Za-z0-9-]+", EXE_NAME)
