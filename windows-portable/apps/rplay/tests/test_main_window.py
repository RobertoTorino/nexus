# SPDX-License-Identifier: AGPL-3.0-or-later
"""The window (main_window.py) on fake network steps: it opens on the portable window with the header's battery, date
and time and fits the handheld's screen; X searches, A on a console chooses it for registering, the fields are filled
on their pages, the sign-in's address is taken from the clipboard, X registers; on My consoles A plays (the stream
window full screen, closed by the quit chord) and X opens the console's page: wake, the tests, the stream settings,
the login passcode, the Steam entry, rest mode and remove (those two on a second press). History lists and clears
the games played. The personal details are masked until Settings shows them, and always in the log; B goes back and
View exits. jobs.py end to end against the fake console; the version and the icons are where the checks expect
them."""

from __future__ import annotations

import re
import threading
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
from remote_play.history import HistoryStore
from remote_play.discovery import Console
from remote_play.jobs import Outcome
from remote_play.main_window import MainWindow
from remote_play.session import SessionInfo
from remote_play.stream_options import AUTO
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

    def test_stream(self, console):
        self.calls.append(("teststream", console.nickname))
        return Outcome(True, "Stream ran 5 s.", SessionInfo(console.target, "PS5"))

    def wake_and_wait(self, console, progress):
        self.calls.append(("wake_and_wait", console.nickname))
        progress(f"Looking for {console.nickname}…")
        return Outcome(True, f"{console.nickname} is on.", console)

    def watch_stream(self, console, deliver, wanted, stop, play, **kwargs):
        """Streams until *stop*, as the real one does; holding the quit chord is kwargs["on_quit"]."""
        self.calls.append(("stream", console.nickname, console.options.fps))
        self.stream_kwargs = kwargs
        stop.wait(5)
        return Outcome(True, f"Stream with {console.nickname} ended after 1 s: fine.",
                       SessionInfo(console.target, "PS5"))

    def steam_entry(self, console, steam_dir, logo, remove=False):
        self.calls.append(("steam", console.nickname, remove))
        (steam_dir / "entries").write_text("" if remove else console.key)
        return Outcome(True, "Steam changed.")


class FakePlayWindow:
    """The stream window as the window drives it: shown full screen, told what happens, closed."""

    made = []

    def __init__(self, title, on_close, options):
        self.title, self.on_close, self.options = title, on_close, options
        self.said, self.visible, self.figures = [], False, lambda: {}
        FakePlayWindow.made.append(self)

    def showFullScreen(self):
        self.visible = True

    def bring_forward(self):
        pass

    def say(self, text):
        self.said.append(text)

    def deliver(self, picture):
        pass

    def wanted(self):
        return True

    def play(self, pcm, rate, channels):
        pass

    def end(self):
        self.close()

    def isVisible(self):
        return self.visible

    def close(self):
        if self.visible:
            self.visible = False
            self.on_close()


def wait(qapp, until, seconds: float = 10) -> None:
    end = time.monotonic() + seconds
    while not until() and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)
    assert until()


@pytest.fixture
def make(qapp, tmp_path):
    windows = []

    def make(ops=None, consoles=(), opened=None, log_path=None, steam_dir=None):
        store = ConsoleStore(tmp_path / "data")
        if consoles:
            store.save(list(consoles))
        settings = QSettings(str(tmp_path / "rplay.ini"), QSettings.Format.IniFormat)
        window = MainWindow(log_path=log_path, gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False),
                            folder=tmp_path / "data", settings=settings, ops=ops or FakeOps(),
                            open_url=lambda url: (opened.append(url) if opened is not None else None) or True,
                            steam_dir=steam_dir, play_window=FakePlayWindow, stats_dir=tmp_path / "streams")
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
    assert window.mine_card.text.text() == "1 registered: A plays one."
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


def page(window, row=""):
    """My consoles' first console's page, the focus on *row*."""
    window.mine_card.setFocus()
    press(window, "accept", "x")
    assert window.panes.currentWidget() is window.console_pane
    if row:
        window.console_pane.list.focus(row)


def test_a_plays_until_the_quit_chord(qapp, make, tmp_path):
    ops = FakeOps()
    window = make(ops, consoles=[registered(options=registered().options.__class__(fps=30))])
    window.mine_card.setFocus()
    press(window, "accept")
    assert window.mine_pane.list.focused() == "mine:AABBCCDDEEFF"
    assert legend(window)[:2] == ["Play", "Its page"]
    assert window.mine_pane.list.pills["mine:AABBCCDDEEFF"].label.text() == "Living room PS5  ·  PS5  ·  Not searched"
    press(window, "accept")
    wait(qapp, lambda: ("stream", "Living room PS5", 30) in ops.calls)    # the console's own settings
    stream_window = FakePlayWindow.made[-1]
    assert stream_window.visible and stream_window.said[0] == "Looking for Living room PS5…"
    assert any("Starting the stream" in text for text in stream_window.said)
    assert ops.stream_kwargs["stats_dir"] == tmp_path / "streams"
    assert ops.stream_kwargs["played"] is window.history
    ops.stream_kwargs["on_quit"]()                      # View, LB and RB held
    idle(qapp, window)
    assert not stream_window.visible and window.stream_window is None
    assert "ended after 1 s" in window.mine_pane.status.text()
    assert window.session_info == {"AABBCCDDEEFF": "PS5"}


def test_a_console_that_does_not_wake_is_said_and_the_window_closes(qapp, make):
    ops = FakeOps()
    ops.wake_and_wait = lambda console, progress: Outcome(False, "Living room PS5 does not answer.")
    window = make(ops, consoles=[registered()])
    window.mine_card.setFocus()
    press(window, "accept", "accept")
    idle(qapp, window)
    assert not FakePlayWindow.made[-1].visible and "does not answer" in window.mine_pane.status.text()


def test_the_console_page_wakes_tests_and_rests(qapp, make):
    ops = FakeOps()
    window = make(ops, consoles=[registered()])
    page(window)
    assert window.console_pane.heading.text() == "Living room PS5"
    assert window.console_pane.list.focused() == "wake" and legend(window)[0] == "Wake"
    assert list(window.console_pane.list.pills) == ["wake", "test", "teststream", "resolution", "fps", "bitrate",
                                                    "screen", "audio_delay", "low_latency", "passcode", "steam",
                                                    "rest", "remove"]
    press(window, "accept")
    idle(qapp, window)
    assert ops.calls == [("wake", "Living room PS5")] and "Wake-up sent" in window.console_pane.status.text()
    window.console_pane.list.focus("test")
    press(window, "accept")
    idle(qapp, window)
    assert ops.calls[-1] == ("test", "Living room PS5") and window.session_info == {"AABBCCDDEEFF": "PS5"}
    window.console_pane.list.focus("teststream")
    press(window, "accept")
    idle(qapp, window)
    assert ops.calls[-1] == ("teststream", "Living room PS5")
    window.console_pane.list.focus("rest")
    press(window, "accept")
    assert ops.calls[-1][0] == "teststream" and "Press A again" in window.console_pane.status.text()
    assert legend(window)[0] == "Press again"
    press(window, "accept")
    idle(qapp, window)
    assert ops.calls[-1] == ("rest", "Living room PS5")
    press(window, "back")
    assert window.panes.currentWidget() is window.mine_pane and window.mine_pane.list.focused() == "mine:AABBCCDDEEFF"


def test_the_stream_settings_step_and_are_kept(qapp, make, tmp_path):
    window = make(consoles=[registered()])
    page(window, "resolution")
    assert window.console_pane.list.pills["resolution"].label.text() == "Resolution: Automatic (1080p)"
    press(window, "accept")
    kept = ConsoleStore(tmp_path / "data").load()[0].options
    assert kept.resolution == 360 and window.console_pane.list.pills["resolution"].label.text() == "Resolution: 360p"
    for row, text in [("fps", "Frame rate: 30 fps"), ("bitrate", "Bitrate: 5 Mbit/s"), ("screen", "Picture: Stretch"),
                      ("audio_delay", "Sound later by: 50 ms"), ("low_latency", "Low latency: On")]:
        window.console_pane.list.focus(row)
        press(window, "accept")
        assert window.console_pane.list.pills[row].label.text() == text
    kept = ConsoleStore(tmp_path / "data").load()[0].options
    assert (kept.fps, kept.bitrate, kept.screen, kept.audio_delay, kept.low_latency) == (30, 5000, "stretch", 50, True)
    window.console_pane.list.focus("bitrate")
    for _ in range(7):
        press(window, "accept")
    assert ConsoleStore(tmp_path / "data").load()[0].options.bitrate == AUTO


def test_a_second_press_runs_out(qapp, make):
    window = make(consoles=[registered()])
    page(window, "remove")
    press(window, "accept")
    assert window.asked == "remove:AABBCCDDEEFF"
    window.confirm_timer.timeout.emit()
    assert window.asked == "" and window.console_pane.status.text() == "" and legend(window)[0] == "Remove"


def test_remove_on_a_second_press(qapp, make, tmp_path):
    window = make(consoles=[registered(), registered(PS4)])
    page(window, "remove")
    press(window, "accept")
    assert "Press A again to remove Living room PS5" in window.console_pane.status.text()
    assert len(ConsoleStore(tmp_path / "data").load()) == 2
    press(window, "accept")
    assert [c.nickname for c in ConsoleStore(tmp_path / "data").load()] == ["PS4-Pro"]
    assert window.panes.currentWidget() is window.mine_pane
    assert window.mine_pane.status.text() == "Living room PS5 is removed."
    assert window.mine_pane.list.focused() == "mine:001122334455"


def test_the_login_passcode_page(qapp, make, tmp_path):
    window = make(consoles=[registered()])
    page(window, "passcode")
    press(window, "accept")
    assert window.panes.currentWidget() is window.field_pane and "Living room PS5" in window.field_pane.text.text()
    window.field_pane.field.setText("12a4")
    press(window, "accept")
    assert "4 digits" in window.field_pane.status.text()
    window.field_pane.field.setText("0420")
    press(window, "accept")
    assert ConsoleStore(tmp_path / "data").load()[0].login_pin == "0420"
    assert window.panes.currentWidget() is window.console_pane and window.console_pane.list.focused() == "passcode"
    assert window.console_pane.list.pills["passcode"].label.text() == "Login passcode: Set"


def test_the_steam_entry_is_added_and_taken_out(qapp, make, tmp_path, monkeypatch):
    steam_dir = tmp_path / "steam"
    steam_dir.mkdir()
    monkeypatch.setattr("remote_play.steam_shortcuts.in_steam",
                        lambda folder: {key for key in [(folder / "entries").read_text()] if key}
                        if (folder / "entries").is_file() else set())
    ops = FakeOps()
    window = make(ops, consoles=[registered()], steam_dir=steam_dir)
    page(window, "steam")
    assert window.console_pane.list.pills["steam"].label.text() == "In Steam: Not added"
    assert legend(window)[0] == "Add to Steam" and "Take out of Steam" not in legend(window)
    press(window, "accept")
    idle(qapp, window)
    assert ops.calls[-1] == ("steam", "Living room PS5", False)
    assert window.console_pane.list.pills["steam"].label.text() == "In Steam: Added"
    assert legend(window)[:2] == ["Update in Steam", "Take out of Steam"]
    press(window, "y")
    assert ops.calls[-1][2] is False and "Press Y again" in window.console_pane.status.text()
    press(window, "y")
    idle(qapp, window)
    assert ops.calls[-1] == ("steam", "Living room PS5", True)
    assert window.console_pane.list.pills["steam"].label.text() == "In Steam: Not added"


def test_without_steam_the_row_says_so(qapp, make):
    window = make(consoles=[registered()])
    page(window, "steam")
    assert window.console_pane.list.pills["steam"].label.text() == "In Steam: Steam is not installed"
    press(window, "accept")
    assert "Steam is not installed" in window.console_pane.status.text()


def test_history_lists_the_games_and_clears_on_a_second_press(qapp, make, tmp_path):
    import datetime
    HistoryStore(tmp_path / "data").add("AABBCCDDEEFF", "Living room PS5", "PPSA01", "Astro Bot", 3900,
                                        datetime.datetime(2026, 11, 1, 20, 15))
    window = make()
    window.history_card.setFocus()
    assert window.history_card.text.text() == "1 game, 1 h 05 min in all."
    press(window, "accept")
    assert window.history_pane.list.pills["game:0"].label.text() == \
        "Astro Bot  ·  Living room PS5  ·  1 h 05 min  ·  last 01/11/2026 20:15"
    press(window, "x")
    assert "Press X again" in window.history_pane.status.text()
    press(window, "x")
    assert HistoryStore(tmp_path / "data").load() == [] and window.history_card.text.text() == "Nothing played yet."


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
