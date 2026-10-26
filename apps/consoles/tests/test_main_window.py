# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QDialog, QInputDialog, QMessageBox

from consoles_link import jobs, psn, steam_settings
from consoles_link.consoles import ConsoleStore, RegisteredConsole
from consoles_link.discovery import Console
from consoles_link.jobs import Outcome
from consoles_link.main_window import AccountDialog, MainWindow
from consoles_link.psn import Account
from consoles_link.session import SessionInfo
from consoles_link.target import Target
from consoles_link.video import Picture
from fake_console import AMBASSADOR, MAC, REGIST_KEY, RP_KEY, RegistConsole, SessionConsole

PS5 = Console("192.168.1.20", True, "ready", host_name="Living room PS5", host_id="AABBCCDDEEFF", host_type="PS5",
              system_version="08050001")
PS4 = Console("192.168.1.21", False, "standby", host_name="PS4-Pro", host_id="001122334455", host_type="PS4",
              system_version="11008001")


def _registered(console: Console = PS5, **changes) -> RegisteredConsole:
    data = dict(host_id=console.host_id, nickname=console.host_name, address=console.address, target=console.target,
                regist_key=REGIST_KEY, rp_key=RP_KEY, mac=MAC)
    return RegisteredConsole(**{**data, **changes})


class FakeOps:
    """jobs.py as the window calls it; records the calls."""

    def __init__(self, found=(PS5, PS4)):
        self.found, self.calls = list(found), []

    def steam_shortcut(self, console, steam, remove=False):
        self.calls.append(("steam_shortcut", console.address) + (("remove",) if remove else ()))
        return Outcome(True, "In Steam.")

    def steam_guide_focus(self, on, steam):
        self.calls.append(("steam_guide_focus", on))
        return jobs.steam_guide_focus(on, steam, run=lambda c: None, running=lambda: False)

    def find(self, address=None):
        self.calls.append(("find", address))
        consoles = [c for c in self.found if address in (None, c.address)]
        return Outcome(True, f"{len(consoles)} found.", consoles)

    def register(self, console, account_id, pin):
        self.calls.append(("register", console.address, account_id, pin))
        return Outcome(True, "Registered.", _registered(console))

    def psn_account(self, redirect):
        self.calls.append(("psn_account", redirect))
        if "code=" not in redirect:
            return Outcome(False, "That address has no code in it.")
        return Outcome(True, "Account ID found.", Account(bytes(range(1, 9)), "player"))

    def wake(self, console):
        self.calls.append(("wake", console.address))
        return Outcome(True, "Wake-up sent.")

    def test_session(self, console):
        self.calls.append(("test_session", console.address))
        return Outcome(True, "Session started and closed.", SessionInfo(console.target, "PS5", "abc"), ["Session ID."])

    def test_stream(self, console):
        self.calls.append(("test_stream", console.address))
        return Outcome(True, "Stream ran.", SessionInfo(console.target, "PS5", "abc"), ["STREAMINFO received."])

    def watch_stream(self, console, deliver, wanted, stop, play=None, figures=None, stats_dir=None, played=None):
        """Delivers one picture, then ends as when the console stops the stream (stop not set)."""
        self.calls.append(("watch_stream", console.address, stop.is_set()))
        if wanted():
            deliver(Picture("nv12", 4, 2, bytes(12)))
        return Outcome(False, "The console ended the stream.", SessionInfo(console.target, "PS5", "abc"), [])

    def rest_mode(self, console):
        self.calls.append(("rest_mode", console.address))
        return Outcome(False, "No session.", SessionInfo(console.target), [])


def _now(job, after):
    after(job())
    return True


@pytest.fixture(autouse=True)
def no_real_steam(monkeypatch):
    """The window looks for Steam: never the real one here."""
    monkeypatch.setattr(steam_settings, "find_steam", lambda: None)
    monkeypatch.setattr(steam_settings, "steam_running", lambda: False)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")


@pytest.fixture
def window(qapp, config_dir):
    ops = FakeOps()
    w = MainWindow(config_dir=config_dir, ops=ops, run=_now)
    w.ops_fake = ops
    yield w
    w.close()


def test_opens_empty(window):
    assert window.found_table.rowCount() == 0 and window.registered_table.rowCount() == 0
    assert window.found_box.value.text() == "0" and window.registered_box.value.text() == "0"
    assert not window.register_button.isEnabled() and not window.test_button.isEnabled()
    assert window.search_button.isEnabled()


def test_search_lists_both_consoles(window):
    window.search_button.click()
    assert window.found_table.rowCount() == 2
    assert window.found_table.item(0, 0).text() == "Living room PS5"
    assert window.found_table.item(1, 3).text() == "Rest mode"
    assert window.found_table.item(0, 5).text() == "no"
    assert window.found_box.value.text() == "2"
    assert "2 found." in window.log.toPlainText()


def test_search_at_an_address_is_remembered(window, config_dir):
    window.address_edit.setText("192.168.1.21")
    window.address_button.click()
    assert window.ops_fake.calls[-1] == ("find", "192.168.1.21")
    assert window.found_table.rowCount() == 1
    assert window.settings.get("address") == "192.168.1.21"


def test_register_needs_a_selection_and_valid_input(window, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    window.search_button.click()
    window.found_table.selectRow(0)
    assert window.register_button.isEnabled()
    window.account_edit.setText("my_online_name")
    window.pin_edit.setText("12345678")
    window.register_button.click()
    assert warnings and "account ID" in warnings[0]
    assert not any(call[0] == "register" for call in window.ops_fake.calls)


def test_register_stores_the_console(window, config_dir):
    window.search_button.click()
    window.found_table.selectRow(0)
    window.account_edit.setText("AAECAwQFBgc=")
    window.pin_edit.setText("1234 5678")
    window.register_button.click()
    assert window.ops_fake.calls[-1] == ("register", PS5.address, bytes(range(8)), 12345678)
    assert window.registered_table.rowCount() == 1
    assert window.registered_table.item(0, 3).text() == "1.0"
    assert window.found_table.item(0, 5).text() == "yes"
    assert window.pin_edit.text() == ""
    assert window.settings.get("account_id") == "AAECAwQFBgc="
    assert ConsoleStore(config_dir / "bc250-console-link").load() == [_registered(PS5)]


def test_registered_consoles_are_loaded(qapp, config_dir):
    ConsoleStore(config_dir / "bc250-console-link").put(_registered(PS4, login_pin="1234"))
    w = MainWindow(config_dir=config_dir, ops=FakeOps(), run=_now)
    try:
        assert w.registered_table.rowCount() == 1
        assert w.registered_table.item(0, 1).text() == "PS4"
        assert w.registered_table.item(0, 4).text() == "set"
    finally:
        w.close()


def test_a_console_with_a_new_address_is_updated(qapp, config_dir):
    store = ConsoleStore(config_dir / "bc250-console-link")
    store.put(_registered(PS5, address="192.168.1.99"))
    w = MainWindow(config_dir=config_dir, ops=FakeOps(), run=_now)
    try:
        w.search_button.click()
        assert store.load()[0].address == PS5.address
        assert w.registered_table.item(0, 2).text() == "•••.•••.•••.20"            # masked, the new address
    finally:
        w.close()


def test_personal_details_are_masked_until_shown(window, monkeypatch):
    monkeypatch.setattr(window, "ask_redirect", lambda: "https://x/redirect?code=abc")
    window.account_button.click()                                           # account ID and online ID "player"
    window.address_edit.setText("192.168.1.21")
    window.address_button.click()
    log = window.log.toPlainText()
    assert "192.168.1.21" not in log and "•••.•••.•••.21" in log
    assert "AQIDBAUGBwg=" not in log and "player" not in log
    assert window.found_table.item(0, 2).text() == "•••.•••.•••.21"
    assert window.address_edit.text() == "192.168.1.21"                     # still being edited: not masked yet
    window.address_edit.editingFinished.emit()
    assert window.address_edit.text() == "•••.•••.•••.21" and window.address_edit.isReadOnly()

    window.reveal_box.click()                                            # Show personal details
    log = window.log.toPlainText()
    assert "192.168.1.21" in log
    assert window.found_table.item(0, 2).text() == "192.168.1.21"
    assert window.account_edit.text() == "AQIDBAUGBwg=" and not window.account_edit.isReadOnly()
    # Copied from the log, the details are masked all the same.
    window.log.selectAll()
    copied = window.log.createMimeDataFromSelection().text()
    assert "192.168.1.21" not in copied and "•••.•••.•••.21" in copied and "Asking" in copied

    window.reveal_box.click()                                            # hidden again
    assert window.account_edit.text() == "••••••••Bwg=" and "192.168.1.21" not in window.log.toPlainText()


def test_wake_test_and_rest(qapp, config_dir):
    ConsoleStore(config_dir / "bc250-console-link").put(_registered(PS5))
    ops = FakeOps()
    w = MainWindow(config_dir=config_dir, ops=ops, run=_now)
    try:
        w.registered_table.selectRow(0)
        w.wake_button.click()
        w.test_button.click()
        assert w.session_box.value.text() == "OK" and w.console_box.value.text() == "PS5"
        assert "  Session ID." in w.log.toPlainText()
        w.stream_button.click()
        assert "  STREAMINFO received." in w.log.toPlainText()
        w.rest_button.click()
        assert w.session_box.value.text() == "Failed"
        assert w.badge.text() == "Failed"
        assert [call[0] for call in ops.calls] == ["wake", "test_session", "test_stream", "rest_mode"]
    finally:
        w.close()


def test_stream_window(qapp, config_dir):
    ConsoleStore(config_dir / "bc250-console-link").put(_registered(PS5))
    ops = FakeOps()
    w = MainWindow(config_dir=config_dir, ops=ops, run=_now)
    try:
        w.registered_table.selectRow(0)
        w.watch_button.click()
        window = w.stream_window
        assert window is not None and window.isVisible() and "Living room PS5" in window.windowTitle()
        assert ops.calls == [("watch_stream", PS5.address, False)]
        assert window.slot.take().format == "nv12"                       # the picture reached the window
        # The stream ended on its own: the window stays and says so; the buttons are back.
        assert window.status.text() == "The console ended the stream." and w.watch_button.isEnabled()
        stop = []
        window.on_close = lambda: stop.append(True)
        window.close()
        qapp.processEvents()
        assert stop == [True]
    finally:
        w.close()


def test_closing_the_main_window_stops_the_stream(qapp, config_dir):
    ConsoleStore(config_dir / "bc250-console-link").put(_registered(PS5))
    w = MainWindow(config_dir=config_dir, ops=FakeOps(), run=lambda job, after: True)       # the stream runs on
    w.registered_table.selectRow(0)
    w.watch_button.click()
    stop, window = w._stream_stop, w.stream_window
    assert stop is not None and not stop.is_set() and not w.watch_button.isEnabled()
    w.close()
    assert stop.is_set() and not window.isVisible()


def test_passcode_and_remove(qapp, config_dir, monkeypatch):
    store = ConsoleStore(config_dir / "bc250-console-link")
    store.put(_registered(PS5))
    w = MainWindow(config_dir=config_dir, ops=FakeOps(), run=_now)
    try:
        w.registered_table.selectRow(0)
        monkeypatch.setattr(QInputDialog, "getText", lambda *args: ("4321", True))
        w.passcode_button.click()
        assert store.load()[0].login_pin == "4321"
        assert w.registered_table.item(0, 4).text() == "set"
        w.registered_table.selectRow(0)
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
        w.remove_button.click()
        assert store.load() == [] and w.registered_table.rowCount() == 0
    finally:
        w.close()


def test_stream_settings_are_kept_with_the_console(qapp, config_dir, monkeypatch):
    from consoles_link.options_dialog import StreamOptionsDialog
    from consoles_link.stream_options import StreamOptions
    store = ConsoleStore(config_dir / "bc250-console-link")
    store.put(_registered(PS5))
    w = MainWindow(config_dir=config_dir, ops=FakeOps(), run=_now)
    try:
        assert not w.options_button.isEnabled()
        w.registered_table.selectRow(0)
        assert w.options_button.isEnabled()
        chosen = StreamOptions(resolution=720, fps=30, screen="fill")
        monkeypatch.setattr(StreamOptionsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
        monkeypatch.setattr(StreamOptionsDialog, "options", lambda self: chosen)
        w.options_button.click()
        assert store.load()[0].options == chosen
        assert "Stream settings for Living room PS5: 720p, 30 fps, 10 Mbit/s (automatic), fill." in w.log.toPlainText()
        w.registered_table.selectRow(0)
        monkeypatch.setattr(StreamOptionsDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
        monkeypatch.setattr(StreamOptionsDialog, "options", lambda self: StreamOptions())
        w.options_button.click()                                            # Cancel: nothing changes
        assert store.load()[0].options == chosen
    finally:
        w.close()


def test_buttons_are_off_while_a_job_runs(window):
    seen = []

    def later(job, after):
        seen.append((window.search_button.isEnabled(), window.badge.text()))
        return True                                     # never finishes in this test

    window.run = later
    window.search_button.click()
    assert seen == [(False, "Searching…")]
    assert not window.search_button.isEnabled()


def test_jobs_against_the_fake_console():
    """jobs.py end to end: registration and a test session against the fake console on localhost."""
    reg = RegistConsole(target=Target.PS5_1)
    try:
        outcome = jobs.register(PS5.__class__("127.0.0.1", True, "ready", host_id="X", system_version="08050001"),
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


def test_find_account_id_fills_the_field(window, monkeypatch):
    monkeypatch.setattr(window, "ask_redirect", lambda: "https://x/redirect?code=abc")
    window.account_button.click()
    assert window.account_edit.value() == "AQIDBAUGBwg=" and window.settings.get("account_id") == "AQIDBAUGBwg="
    assert window.account_edit.text() == "••••••••Bwg=" and window.account_edit.isReadOnly()     # masked
    assert window.ops_fake.calls[-1] == ("psn_account", "https://x/redirect?code=abc")
    monkeypatch.setattr(window, "ask_redirect", lambda: "nonsense")
    window.account_button.click()
    assert window.account_edit.value() == "AQIDBAUGBwg=" and "no code" in window.log.toPlainText()
    monkeypatch.setattr(window, "ask_redirect", lambda: None)                 # canceled: nothing happens
    calls = len(window.ops_fake.calls)
    window.account_button.click()
    assert len(window.ops_fake.calls) == calls


def test_account_dialog(qapp):
    dialog = AccountDialog()
    assert dialog.url == psn.login_url() and "redirect" in dialog.redirect_edit.placeholderText()
    dialog.close()


def test_account_dialog_takes_the_redirect_from_the_clipboard(qapp):
    from PyQt6.QtGui import QGuiApplication
    clipboard = QGuiApplication.clipboard()
    old = f"{psn.REDIRECT_URI}?code=old"
    clipboard.setText(old)                                  # there before the dialog: left alone
    dialog = AccountDialog()
    accepted = []
    dialog.accepted.connect(lambda: accepted.append(dialog.redirect_edit.text()))
    dialog._clipboard()
    clipboard.setText("https://example.org/?code=elsewhere")    # another page: left alone
    dialog._clipboard()
    assert accepted == [] and dialog.redirect_edit.text() == ""
    clipboard.setText(f"{psn.REDIRECT_URI}?code=v3.abc&cid=1")
    dialog._clipboard()
    assert accepted == [f"{psn.REDIRECT_URI}?code=v3.abc&cid=1"]
    clipboard.setText(f"{psn.REDIRECT_URI}?code=later")      # closed: no longer watched
    assert accepted == [f"{psn.REDIRECT_URI}?code=v3.abc&cid=1"]


def test_steam_ps_button_setting(qapp, config_dir, tmp_path, monkeypatch):
    from test_steam_settings import _steam
    steam = _steam(tmp_path, "1")
    monkeypatch.setattr(steam_settings, "find_steam", lambda: steam)
    ops = FakeOps()
    w = MainWindow(config_dir=config_dir, ops=ops, run=_now)
    try:
        assert not w.steam_box.isHidden() and w.steam_box.isChecked() and w.steam_box.isEnabled()
        w.search_button.click()
        w.found_table.selectRow(0)
        w.steam_box.setChecked(False)                               # Steam not running: no question
        assert ops.calls[-1] == ("steam_guide_focus", False)
        assert steam_settings.guide_focus(steam_settings.user_configs(steam)) is False
        assert not w.steam_box.isChecked() and "no longer comes to the front" in w.log.toPlainText()
        # Steam running and the question answered No: nothing changes.
        monkeypatch.setattr(steam_settings, "steam_running", lambda: True)
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
        w.steam_box.setChecked(True)
        assert ops.calls[-1] == ("steam_guide_focus", False) and not w.steam_box.isChecked()
    finally:
        w.close()


def test_steam_setting_hidden_without_steam_and_off_in_game_mode(qapp, config_dir, tmp_path, monkeypatch):
    w = MainWindow(config_dir=config_dir, ops=FakeOps(), run=_now)
    assert w.steam_box.isHidden() and not w.steam_note.isHidden()          # Settings says why
    w.close()
    from test_steam_settings import _steam
    steam = _steam(tmp_path, "1")
    monkeypatch.setattr(steam_settings, "find_steam", lambda: steam)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "gamescope")
    w = MainWindow(config_dir=config_dir, ops=FakeOps(), run=_now)
    assert not w.steam_box.isHidden() and not w.steam_box.isEnabled() and "Game Mode" in w.steam_box.toolTip()
    w.close()


def test_controller_test_opens_from_the_window(window, monkeypatch):
    from fake_gamepad import FakeSdl
    from consoles_link.controller_test import ControllerTest
    opened = []
    monkeypatch.setattr(ControllerTest, "exec", lambda self: opened.append(self) or 0)
    monkeypatch.setattr(type(window), "controller_test_options", {"backend": FakeSdl(), "check": lambda p: None})
    assert window.controller_button.isEnabled()
    window.controller_button.click()
    assert len(opened) == 1
    opened[0].close()
    window.busy = True
    window._update_buttons()
    assert not window.controller_button.isEnabled()                # not during a stream or another job



def test_history_opens_from_the_window(window, config_dir, monkeypatch):
    from consoles_link.history_dialog import HistoryDialog
    opened = []
    monkeypatch.setattr(HistoryDialog, "exec", lambda self: opened.append(self) or 0)
    assert window.history.path == config_dir / "bc250-console-link" / "history.json"
    window.history_button.click()
    assert len(opened) == 1 and opened[0].store is window.history
    opened[0].close()

def test_add_to_game_mode(qapp, config_dir, tmp_path, monkeypatch):
    from test_steam_settings import _steam
    steam = _steam(tmp_path, "0")
    monkeypatch.setattr(steam_settings, "find_steam", lambda: steam)
    store = ConsoleStore(config_dir / "bc250-console-link")
    store.put(_registered(PS4))
    ops = FakeOps()
    w = MainWindow(config_dir=config_dir, ops=ops, run=_now)
    try:
        assert not w.game_mode_button.isEnabled()                   # no console selected
        w.registered_table.selectRow(0)
        assert w.game_mode_button.isEnabled() and w.game_mode_button.text() == "Add to Game Mode"
        monkeypatch.setattr(steam_settings, "steam_running", lambda: True)
        monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No)
        w.game_mode_button.click()                                  # Steam would have to close: declined
        assert ("steam_shortcut", PS4.address) not in ops.calls
        monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
        w.game_mode_button.click()
        assert ops.calls[-1] == ("steam_shortcut", PS4.address) and "In Steam." in w.log.toPlainText()
    finally:
        w.close()
    monkeypatch.setattr(steam_settings, "find_steam", lambda: None)
    w = MainWindow(config_dir=config_dir, ops=FakeOps(), run=_now)
    w.registered_table.selectRow(0)
    assert not w.game_mode_button.isEnabled()                       # no Steam
    w.close()


def test_remove_offers_to_remove_the_game_mode_shortcut(qapp, config_dir, tmp_path, monkeypatch):
    from consoles_link import steam_shortcuts
    from test_steam_settings import _steam
    steam = _steam(tmp_path, "0")
    monkeypatch.setattr(steam_settings, "find_steam", lambda: steam)
    monkeypatch.setattr(steam_settings, "steam_running", lambda: False)
    store = ConsoleStore(config_dir / "bc250-console-link")
    ops = FakeOps()
    asked = []

    def answer(yes):                                        # Remove's own question: yes; the shortcut's: *yes*
        def question(parent, title, text, *rest):
            asked.append(text)
            return QMessageBox.StandardButton.Yes if yes or len(asked) == 1 else QMessageBox.StandardButton.No
        return question

    for has_shortcut, yes, removed in ((False, True, False), (True, False, False), (True, True, True)):
        store.put(_registered(PS4))
        monkeypatch.setattr(steam_shortcuts, "has_shortcut", lambda s, c, has=has_shortcut: has)
        monkeypatch.setattr(QMessageBox, "question", answer(yes))
        asked.clear()
        ops.calls.clear()
        w = MainWindow(config_dir=config_dir, ops=ops, run=_now)
        try:
            w.registered_table.selectRow(0)
            w.remove_button.click()
            assert store.load() == []
            # The first question is Remove's own; the second one, only with a shortcut, asks about Steam.
            assert len(asked) == 1 + has_shortcut
            assert not has_shortcut or "is still in Steam for Game Mode. Remove it too?" in asked[1]
            assert (("steam_shortcut", PS4.address, "remove") in ops.calls) is removed
        finally:
            w.close()


def test_console_box_shows_model_software_and_what_runs(qapp, config_dir):
    store = ConsoleStore(config_dir / "bc250-console-link")
    store.put(_registered(PS4))
    running = Console(PS4.address, False, "ready", host_name="PS4-Pro", host_id=PS4.host_id, host_type="PS4",
                      system_version="14008001", running_app="Lumines Remastered", running_title_id="CUSA12345")
    ops = FakeOps(found=(running,))
    w = MainWindow(config_dir=config_dir, ops=ops, run=_now)
    try:
        assert w.console_box.caption.text() == "Console type" and w.console_box.value.text() == "—"
        w.registered_table.selectRow(0)
        assert w.console_box.value.text() == "PS4"                     # not searched yet: no software version
        assert "Search to see them" in w.console_box.toolTip()
        w.search_button.click()
        assert w.found_table.item(0, 4).text() == "14.00"               # the System column, decoded
        assert w.console_box.value.text() == "PS4 · 14.00"
        tooltip = w.console_box.toolTip()
        assert "System software: 14.00" in tooltip and "Running: Lumines Remastered (CUSA12345)" in tooltip
        w.registered_table.selectRow(0)
        w.test_button.click()                                           # the session names the exact model
        assert w.console_box.value.text() == "PS5 · 14.00"              # (the fake session says PS5)
    finally:
        w.close()


def test_settings_box_opens_the_app_settings(window, monkeypatch):
    shown = []
    monkeypatch.setattr(window.settings_dialog, "exec", lambda: shown.append(True))
    window.settings_button.click()
    assert shown == [True]
    dialog_boxes = window.settings_dialog.findChildren(type(window.reveal_box))
    assert window.reveal_box in dialog_boxes and window.steam_box in dialog_boxes


def test_address_field_searches_on_enter(window, config_dir):
    window.address_edit.setText("192.168.1.21")
    window.address_edit.returnPressed.emit()
    assert window.ops_fake.calls[-1] == ("find", "192.168.1.21")


def test_the_window_looks_like_the_other_gaming_apps(qapp, config_dir):
    """As the shadPS4 Manager (owner, 20-10-2026): the gaming blue, numbered steps with their buttons the same size,
    Settings… in the header, both lists as tables with a blue header, Stream the filled main button; a double click
    on a registered console streams it."""
    from consoles_link import style
    store = ConsoleStore(config_dir / "bc250-console-link")
    store.put(_registered(PS5))
    w = MainWindow(config_dir=config_dir, ops=FakeOps(), run=_now)
    try:
        assert w.styleSheet() == style.STYLESHEET and "#0A55B0" in style.STYLESHEET
        assert [b.text() for b in w.findChildren(type(w.found_box.value)) if b.property("step")] == ["1", "2", "3", "4"]
        steps = (w.address_button, w.search_button, w.account_button, w.register_button, w.passcode_button,
                 w.remove_button, w.game_mode_button)
        assert len({(b.width(), b.height()) for b in steps}) == 1
        assert w.settings_button.text() == "Settings…" and w.watch_button.property("primary")
        assert not w.found_table.horizontalHeader().isHidden() and not w.registered_table.horizontalHeader().isHidden()
        assert "Select a registered console" in w.console_state.text()
        w.registered_table.selectRow(0)
        assert w.console_state.text().startswith("Selected: ")
        watched = []
        w.watch = lambda: watched.append(True)
        w.watch_button.clicked.disconnect()
        w.watch_button.clicked.connect(w.watch)
        w.registered_table.doubleClicked.emit(w.registered_table.model().index(0, 0))
        assert watched == [True]
    finally:
        w.close()
