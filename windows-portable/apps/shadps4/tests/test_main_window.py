# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py), as RPCS3 Manager's is tested: it opens on the portable window with the header's
battery, date and time, fits the handheld's screen; every action is a button in the row at the bottom, A too, and no
pill is left (owner, 29-10-2026); B goes back and View exits; shadPS4 installed on A (off the window's thread, the
megabytes counted, View asking first meanwhile, its quit hotkeys set after), updated from another version, and removed
with X pressed twice; the system modules put in Games\\PS4\\Modules taken in by themselves; the packages put in the
app's Games\\PS4 folder unpacked from Your games (Extract PKG, with the synthetic package), a game and its update beside
it, each package deleted after; a game removed; the Settings pane's rows, in tabs, step through their values in
config.json, never while shadPS4 runs; the shadNet pane's rows and field pages, the account kept in shadPS4's files,
created and tried on a fake server; Your games from Games\\PS4 (no folder is chosen), marked for Steam with A (never
played from the app) and put in Steam; the Log pane and the whole log read in the app; the SteamGridDB key; the
version and the icons are where the checks expect them."""

from __future__ import annotations

import json
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QSettings

from bc250_core import play, portable, steam
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private
from bc250_core.portable import BACK, EXIT, VIEW
from bc250_core.portable import INFO as MENU_INFO
from conftest import FakeShadNet, fake_install, make_game, write_shad_files
from shadps4_manager import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, emulator, shortcuts, userdata
from shadps4_manager.main_window import NO_STEAM, NOTHING_TO_CHANGE, MainWindow


class FakePad:
    def events(self):
        return []

    def close(self):
        pass

    def names(self):
        return []


def wait_for(qapp, predicate, seconds=10.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not predicate():
        qapp.processEvents()
        time.sleep(0.01)
    return predicate()


def make(qapp, home=None, install=fake_install, running=lambda home: False, **more):
    more.setdefault("steam_dir", None)                  # never the real Steam
    more.setdefault("start", lambda command, cwd=None: None)   # never a real shadPS4
    more.setdefault("user_home", Path(tempfile.mkdtemp()) / "me")   # never the real Games\\PS4
    more.setdefault("drives", lambda: [])
    more.setdefault("runtime_missing", lambda: [])
    more.setdefault("settings", QSettings(str(Path(tempfile.mkdtemp()) / "app.ini"),
                                          QSettings.Format.IniFormat))   # never Windows' registry
    window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False),
                        home=home or Path(tempfile.mkdtemp()) / "emulator", install=install, running=running, **more)
    portable.scale((1280, 720))
    window.resize(1280, 720)
    window.show()
    window.activateWindow()                     # the focus moves in the active window only
    qapp.processEvents()
    window.start()
    return window


def no_pills(window) -> bool:
    """Every action is in the row at the bottom (owner, 29-10-2026): the panes hold rows and icons, no pill."""
    return [p for p in window.panes.findChildren(portable.Pill)
            if type(p) is portable.Pill and p.isVisibleTo(window)] == []


def ready(home: Path) -> Path:
    """shadPS4 installed and run once, with every system module it cannot do without; its user folder."""
    fake_install(home)
    user = write_shad_files(emulator.user_folder(home))
    (user / "sys_modules").mkdir()
    for name in userdata.NEEDED:
        (user / "sys_modules" / name).write_bytes(b"")
    return user


def test_the_window_opens_with_the_suites_header(qapp):
    window = make(qapp)
    assert window.header.title.text() == APP_NAME and window.header.version.text() == __version__
    assert re.fullmatch(r"\w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d  \|  82%", window.header.status.text())   # battery last
    assert window.legend.items == [("A", "Install"), MENU_INFO, EXIT]   # on a card: no Back
    assert no_pills(window)
    window.close()


def test_the_window_fits_the_handhelds_screen(qapp):
    window = make(qapp)
    assert window.minimumSizeHint().height() <= 720 and window.height() == 720
    window.close()


def test_b_goes_back_and_view_exits(qapp, monkeypatch):
    """The suite's buttons (owner, 29-10-2026): B goes back, from a pane to its card, and does nothing on a card; View
    (the Exit app entry) closes the app, a tap on the entry too."""
    window = make(qapp)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("back")                                    # on the shadPS4 card: nothing
    assert closed == [] and window.shadps4_card.hasFocus()
    window.settings_card.setFocus()
    window.on_action("accept")                                  # into the pane: B Back shows, and goes to the card
    qapp.processEvents()
    assert BACK in window.legend.items
    window.on_action("back")
    qapp.processEvents()
    assert window.settings_card.hasFocus() and BACK not in window.legend.items and closed == []
    window.legend.entries[VIEW].pressed.emit()                  # a tap on Exit app
    assert closed == [True]
    window.on_action("view")
    assert closed == [True, True]


def test_version_is_the_single_source():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__ == INFO.version


def test_icons_are_beside_the_package():
    assert LOGO_PATH.is_file() and LOGO_PATH.name == f"{APP_ID}.webp"
    assert (ROOT / "images" / f"{APP_ID}-128.png").is_file()
    assert re.fullmatch(r"[A-Za-z0-9-]+", EXE_NAME)


def test_nothing_is_installed_before_a(qapp, tmp_path):
    calls = []
    window = make(qapp, tmp_path / "emulator", install=lambda *a, **k: calls.append(True))
    assert calls == [] and window.shadps4_card.hasFocus()
    assert dict(window.rows())["Installed"] == "not installed" and dict(window.rows())["System modules"] == "0 of 24"
    window.on_action("x")                                       # X Remove: says why, nothing happens
    assert "nothing to remove" in window.status.text() and calls == []
    assert ("LB", "Modules") not in window.legend.items         # no browsing (owner, 30-10-2026)
    window.close()


def test_a_installs_off_the_windows_thread_and_counts_the_megabytes(qapp, tmp_path, monkeypatch):
    gate = threading.Event()
    window = make(qapp, tmp_path / "emulator", install=lambda home, **k: fake_install(home, gate=gate, **k))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("accept")                                  # A on the shadPS4 card
    assert window.busy
    window.refresh()
    assert window.status.text() == f"Downloading shadPS4 {emulator.VERSION}… 12 of 32 MB"
    assert ("A", "Install") not in window.legend.items
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.on_action("view")                                    # Exit asks first while it downloads
    assert closed == [] and window.legend.items == [(VIEW, "Press again to exit")]
    assert window.status.text() == "Press View again to exit: the download stops."
    gate.set()
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == f"shadPS4 {emulator.VERSION} is installed."
    assert window.legend.items == [("X", "Remove shadPS4"), MENU_INFO, EXIT]
    hotkeys = (emulator.user_folder(tmp_path / "emulator") / "input_config" / "global.ini").read_text()
    assert "hotkey_quit = back, options" in hotkeys                 # View + Menu: set before its first start
    window.on_action("view")
    assert closed == [True]                                     # nothing runs: View exits at once


def test_a_failed_install_says_why(qapp, tmp_path):
    def failing(home, **kwargs):
        raise emulator.EmulatorError("the release has no shadPS4.exe")
    window = make(qapp, tmp_path / "emulator", install=failing)
    window.act("accept")
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == "shadPS4 could not be installed: the release has no shadPS4.exe"
    assert ("A", "Install") in window.legend.items
    window.close()


def test_update_and_remove_with_x_pressed_twice(qapp, tmp_path):
    home = tmp_path / "emulator"
    user = ready(home)
    fake_install(home, version="0.19.0")
    save = user / "home" / "1000" / "savedata" / "CUSA00900" / "SAVEDATA00" / "sce_sys" / "param.sfo"
    save.parent.mkdir(parents=True)
    save.write_bytes(b"x")
    window = make(qapp, home)
    assert window.legend.items == [("X", "Remove shadPS4"), ("Y", "Update"), MENU_INFO, EXIT]
    assert window.status.text() == f"This app installs shadPS4 {emulator.VERSION}: the Y button updates it."
    window.act("y")
    assert wait_for(qapp, lambda: not window.busy) and emulator.installed(home) == emulator.VERSION
    window.legend.entries["X"].pressed.emit()                   # a tap on X Remove shadPS4
    assert window.legend.items[0] == ("X", "Press again") and emulator.installed(home)
    assert window.status.text().startswith("Press the X button again")
    window._confirm_over()                                      # five seconds without a second press
    assert window.legend.items[0] == ("X", "Remove shadPS4")
    window.act("x")
    window.act("x")
    assert emulator.installed(home) == "" and save.is_file() and (user / "config.json").is_file()
    assert "stays" in window.status.text() and window.legend.items[0] == ("A", "Install")
    window.close()


def test_remove_and_update_while_shadps4_runs_say_so(qapp, tmp_path):
    home = tmp_path / "emulator"
    ready(home)
    fake_install(home, version="0.19.0")
    window = make(qapp, home, running=lambda h: True, install=lambda *a, **k: 1 / 0)
    window.act("x")
    window.act("x")
    assert emulator.installed(home) and window.status.text().startswith("shadPS4 is open")
    window.act("y")
    assert not window.busy and window.status.text() == "shadPS4 is open: close it first, then update it."
    window.close()


def test_the_runtime_and_the_modules_are_asked_for(qapp, tmp_path):
    home = tmp_path / "emulator"
    fake_install(home)                                                      # no system modules yet
    window = make(qapp, home, runtime_missing=lambda: ["msvcp140_atomic_wait.dll"])
    assert window.status.text().startswith("shadPS4 needs Microsoft's Visual C++ runtime (msvcp140_atomic_wait.dll")
    window.close()
    window = make(qapp, home, user_home=tmp_path / "me")
    assert window.status.text() == ("Some games need system modules from your own PS4: put them in "
                                    f"{private(tmp_path / 'me' / 'Games' / 'PS4' / 'Modules')}, and the app copies "
                                    "them into shadPS4.")
    window.close()


def test_the_system_modules_put_in_the_modules_folder_are_taken_in(qapp, tmp_path, monkeypatch):
    r"""The system modules are put in Games\PS4\Modules (owner, 30-10-2026: no browsing, the app takes care of them):
    copied into shadPS4 when the app opens and when the shadPS4 card gets the focus, the new or changed ones only."""
    home = tmp_path / "emulator"
    fake_install(home)
    user = tmp_path / "me"
    dump = user / "Games" / "PS4" / "Modules"
    dump.mkdir(parents=True)
    for name in (*userdata.NEEDED[:20], "libSceNgs2.sprx"):
        (dump / name).write_bytes(b"sprx")
    (dump / "notes.txt").write_text("")
    window = make(qapp, home, user_home=user)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert window.status.text() == ("21 system module(s) taken from the Modules folder: 20 of the 24 shadPS4 cannot do "
                                    "without are there now.")
    assert dict(window.rows())["System modules"] == "20 of 24"
    modules = emulator.user_folder(home) / "sys_modules"
    assert (modules / "libSceNgs2.sprx").is_file() and not (modules / "notes.txt").exists()
    for name in userdata.NEEDED[20:]:                           # the rest, put in while the app is open
        (dump / name).write_bytes(b"sprx")
    window.games_card.setFocus()
    window.shadps4_card.setFocus()                              # the card again: they are taken in
    qapp.processEvents()
    assert window.status.text().startswith("4 system module(s) taken from the Modules folder: 24 of the 24")
    assert dict(window.rows())["System modules"] == "all 24"
    assert userdata.sync_modules(dump, modules) == []           # nothing new: nothing copied
    window.close()


def test_the_cards_show_their_panes(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert window.panes.currentWidget() is window.pane
    window.on_action("down")
    assert window.games_card.hasFocus() and window.panes.currentWidget() is window.games_pane
    window.on_action("down")
    assert window.settings_card.hasFocus() and window.panes.currentWidget() is window.settings_pane
    assert window.settings_pane.status.text() == "Install shadPS4 first: the settings are in its folder."
    assert window.legend.items[:3] == [("A", "Change"), ("LB", "Previous tab"), ("RB", "Next tab")]
    window.settings_pane.status.setText("")
    window.settings_pane.pills["present"].click()                                  # never grayed out: says why
    assert window.settings_pane.status.text() == "Install shadPS4 first: the settings are in its folder."
    window.on_action("down")
    assert window.shadnet_card.hasFocus() and window.panes.currentWidget() is window.shadnet_pane
    window.on_action("down")
    assert window.log_card.hasFocus() and window.panes.currentWidget() is window.log_pane
    for card in (window.shadps4_card, window.games_card, window.settings_card, window.shadnet_card, window.log_card):
        card.setFocus()
        qapp.processEvents()
        assert no_pills(window)
    window.close()


def test_the_settings_step_and_are_written_at_once(qapp, tmp_path, monkeypatch):
    home = tmp_path / "emulator"
    user = ready(home)
    is_running = [False]
    window = make(qapp, home, running=lambda h: is_running[0])
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    pills = window.settings_pane.pills
    assert pills["present"].label.text() == "VSync: Mailbox (no tearing)"         # shadPS4's default
    window.settings_card.setFocus()
    window.on_action("accept")                                                     # A on the card: the first row
    assert pills["present"].hasFocus()
    window.on_action("accept")
    assert pills["present"].label.text() == "VSync: On"
    config = json.loads((user / "config.json").read_text())
    assert config["GPU"]["present_mode"] == "Fifo" and config["Audio"] == {"audio_backend": 0}   # the rest kept
    pills["fsr"].click()
    assert pills["fsr"].label.text() == "FidelityFX upscaling (FSR): On"
    window.settings_pane.tabs.select("game")
    assert pills["trophies"].label.text() == "Trophy messages: On"                # trophy_popup_disabled: false
    is_running[0] = True                                                           # shadPS4 is open
    pills["trophies"].click()
    assert window.settings_pane.status.text().startswith("shadPS4 is open")
    assert pills["trophies"].label.text() == "Trophy messages: On"
    is_running[0] = False
    pills["trophies"].click()
    assert pills["trophies"].label.text() == "Trophy messages: Off"
    assert json.loads((user / "config.json").read_text())["General"]["trophy_popup_disabled"] is True
    window.settings_pane.tabs.select("sound")
    pills["volume"].click()
    assert pills["volume"].label.text() == "Volume: 75%"
    assert json.loads((user / "config.json").read_text())["General"]["volume_slider"] == 75
    window.close()


def test_the_settings_are_in_tabs(qapp, tmp_path, monkeypatch):
    """LB and RB step through Picture, Sound, Controller and In a game; the focus follows to the tab's first row; the
    information tells the tab's settings; every tab's rows fit the pane."""
    from shadps4_manager.shadps4_settings import TABS
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    pane = window.settings_pane
    assert [key for key, _, _ in TABS] == ["picture", "sound", "controller", "game"] == pane.tabs.keys
    assert pane.tabs.current == "picture" and pane.pills["fps"].isVisibleTo(pane)
    assert not pane.pills["audio"].isVisibleTo(pane) and "VSync:" in pane.info.info
    assert "The A button changes" in pane.info.info
    window.settings_card.setFocus()
    window.on_action("accept")
    assert pane.pills["present"].hasFocus()
    window.on_action("next")                                                       # RB: the next tab
    assert pane.tabs.current == "sound" and pane.pills["audio"].hasFocus() and "Sound output:" in pane.info.info
    window.on_action("previous")
    window.on_action("previous")                                                   # LB twice: round to the last
    assert pane.tabs.current == "game" and pane.pills["language"].hasFocus()
    assert pane.minimumSizeHint().height() <= window.panes.height()
    window.close()


def test_shadnet_is_set_up_row_by_row_and_kept_in_shadps4s_files(qapp, tmp_path, monkeypatch):
    """The BC250 app's shadNet window as rows: A on a text row opens its page, A keeps the value in shadPS4's files at
    once (users.json made with its default users when shadPS4 never ran), B goes back without keeping; Sign in only
    with a name and a password; never while shadPS4 runs."""
    home = tmp_path / "emulator"
    fake_install(home)                                          # shadPS4 never ran: no users.json yet
    user = emulator.user_folder(home)
    is_running = [False]
    window = make(qapp, home, running=lambda h: is_running[0])
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.shadnet_card.setFocus()
    qapp.processEvents()
    pane = window.shadnet_pane
    assert window.legend.items == [("A", "Change"), ("X", "Create account"), ("Y", "Try sign-in"), MENU_INFO, EXIT]
    assert [p.label.text() for p in pane.pills.values()] == [
        "Sign in when a game starts: Off", "Player: shadPS4 (player 1 of 4)", "shadNet name: not set",
        "Password: not set", "Email: not set", "Server: srv.shadps4.net:31313",
        "Registration key: none (only when the server asks for one)"]
    assert pane.summary.text().startswith("Off: shadPS4 plays offline")
    window.on_action("accept")                                  # A on the card: the first row
    assert pane.pills["on"].hasFocus()
    window.on_action("accept")                                  # Sign in without a name: says so
    assert pane.status.text().startswith("Fill in the shadNet name first")
    pane.pills["npid"].click()                                  # a text row: its page
    assert window.panes.currentWidget() is window.field_pane and window.field_pane.field.hasFocus()
    assert window.field_pane.heading.text() == "shadNet name"
    assert window.legend.items == [("A", "Keep"), ("X", "Paste"), BACK, EXIT]
    window.field_pane.field.setText("no spaces allowed")
    window.on_action("accept")
    assert window.field_pane.status.text().startswith("A shadNet name has 3 to 16")
    window.field_pane.field.setText("Player_1")
    window.on_action("accept")                                  # A: kept, back on the row
    assert window.panes.currentWidget() is pane and pane.pills["npid"].hasFocus()
    assert pane.pills["npid"].label.text() == "shadNet name: Player_1"
    users = json.loads((user / "users.json").read_text())["Users"]["user"]
    assert len(users) == 4 and users[0]["shadnet_npid"] == "Player_1"
    pane.pills["password"].click()
    window.field_pane.field.setText("secret")
    window.on_action("back")                                    # B: nothing kept
    assert pane.pills["password"].label.text() == "Password: not set" and window.field_pane.field.text() == ""
    pane.pills["password"].click()
    window.field_pane.field.setText("secret")
    window.on_action("accept")
    assert pane.pills["password"].label.text() == "Password: ••••••••"
    pane.pills["on"].click()                                    # now it signs in
    assert pane.pills["on"].label.text() == "Sign in when a game starts: On"
    assert pane.summary.text() == "Player_1 signs in to srv.shadps4.net:31313 when a game starts."
    assert json.loads((user / "config.json").read_text())["Network"]["shad_net_enabled"] is True
    pane.pills["server"].click()
    window.field_pane.field.setText("not a server:x")
    window.on_action("accept")
    assert "is not a server address" in window.field_pane.status.text()
    window.field_pane.field.setText("192.168.1.20")
    window.on_action("accept")
    assert pane.pills["server"].label.text() == "Server: 192.168.1.20:31313"
    pane.pills["user"].click()                                  # the next player: its own account
    assert pane.pills["user"].label.text() == "Player: shadPS4-2 (player 2 of 4)"
    assert pane.pills["npid"].label.text() == "shadNet name: not set"
    is_running[0] = True
    pane.pills["user"].click()
    pane.pills["user"].click()
    pane.pills["user"].click()                                  # round to player 1
    pane.pills["on"].click()
    assert pane.status.text() == "shadPS4 is open: close it first, it would write its own settings over the change."
    assert pane.pills["on"].label.text() == "Sign in when a game starts: On"
    window.close()


def test_shadnet_creates_and_tries_the_account_on_the_server(qapp, tmp_path, monkeypatch):
    home = tmp_path / "emulator"
    user = ready(home)
    userdata.save_shadnet(user, 1000, "Player_1", "secret", "", False, "127.0.0.1:31313")
    server = FakeShadNet()
    window = make(qapp, home, connect=server.connect)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.shadnet_card.setFocus()
    qapp.processEvents()
    pane = window.shadnet_pane
    window.on_action("x")                                       # X Create account: the email first
    assert pane.status.text() == "Fill in the email address first: creating an account needs it."
    window.shadnet_row("key")
    window.field_pane.field.setText("letmein")
    window.on_action("accept")                                  # the registration key: not in shadPS4's files
    assert "letmein" not in (user / "users.json").read_text() and "letmein" not in (user / "config.json").read_text()
    window.shadnet_row("email")
    window.field_pane.field.setText("me@example.com")
    window.on_action("accept")
    window.on_action("x")
    assert wait_for(qapp, lambda: not window.busy)
    assert pane.status.text() == "The account Player_1 was created on 127.0.0.1:31313."
    assert server.requests[-1] == (2, {1: "Player_1", 2: "secret", 4: "me@example.com", 5: "letmein"})
    window.on_action("y")                                       # Y Try sign-in
    assert wait_for(qapp, lambda: not window.busy)
    assert pane.status.text() == "Player_1 signed in to 127.0.0.1:31313: the account works."
    assert server.requests[-1] == (0, {1: "Player_1", 2: "secret"})
    refused = FakeShadNet(error=8)
    window.connect = refused.connect
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy)
    assert pane.status.text() == "The sign-in failed: the password is wrong."
    window.close()


def test_a_long_folder_wraps_and_the_window_stays_on_the_screen(qapp, tmp_path):
    deep = tmp_path / ("a-rather-long-folder-name" * 3) / "windows-portable-suite" / "windows-portable-shadps4" / "emulator"
    window = make(qapp, deep)
    assert window.minimumSizeHint().width() <= 1280 and window.width() == 1280
    assert window.panes.minimumSizeHint().width() < 800
    window.close()


def test_the_window_fits_a_smaller_screen(qapp, tmp_path):
    # It adapts to the screen it is on (a 1080p screen at 175 % is 1097 x 617), as every app of the suite.
    portable.pin_scale((1097, 617))
    try:
        window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False), steam_dir=None,
                            home=tmp_path / "emulator", user_home=tmp_path / "me", runtime_missing=lambda: [],
                            settings=QSettings(str(tmp_path / "app.ini"), QSettings.Format.IniFormat))
        window.resize(1097, 617)
        window.show()
        qapp.processEvents()
        assert window.minimumSizeHint().height() <= 617
        window.close()
    finally:
        portable.pin_scale((1280, 720))


def test_your_games_are_marked_with_a_and_put_in_steam(qapp, tmp_path, monkeypatch):
    """The games are played from Steam (owner, 29-10-2026): A on a game is its Steam mark, Y Update Steam writes the
    marks, X plays a game that is in Steam through Steam (steam://rungameid); Steam's library is the portal's (owner,
    30-10-2026: no Open Steam row)."""
    home = tmp_path / "emulator"
    shad = ready(home)
    (shad / "play_time.txt").write_text("CUSA00900 1:22:47 1792613335\n")
    user = tmp_path / "me"
    bloodborne = make_game(user / "Games" / "PS4" / "CUSA00900", "Bloodborne", "CUSA00900", pictures=True)
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    closed = []

    def with_steam_closed(change):
        closed.append(True)
        change()
        return False
    played = []
    window = make(qapp, home, steam_dir=steam_dir, steam_closed=with_steam_closed, user_home=user,
                  play=played.append)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert dict(window.rows())["Play time"] == "1 h 22 min"
    window.games_card.setFocus()
    qapp.processEvents()
    assert window.legend.items == [("A", "Steam mark"), ("Y", "Update Steam"), ("LB", "Steam artwork"), MENU_INFO,
                                   EXIT]
    assert "Press the A button on a game to mark it for Steam" in window.games_pane.info.info
    assert not hasattr(window, "steam_row")
    pills = window.games_pane.list.pills                           # the game in Games\PS4: no folder chosen
    assert [pill.label.text() for pill in pills.values()] == ["Bloodborne  ·  CUSA00900  ·  1 h 22 min"]
    window.legend.entries["Y"].pressed.emit()                      # a tap on Y Update Steam: nothing to change yet
    assert window.games_pane.status.text() == NOTHING_TO_CHANGE
    pills[str(bloodborne)].setFocus()
    qapp.processEvents()
    assert ("X", "Play") in window.legend.items
    assert ("RB", "Remove game") in window.legend.items
    window.on_action("x")                                          # X: not in Steam yet
    assert window.games_pane.status.text() == ("Bloodborne is not in Steam yet: A marks it, then Y Update Steam "
                                               "puts it there.") and played == []
    window.on_action("accept")                                     # A: the Steam mark
    assert "✓ Steam (Update Steam)" in window.games_pane.list.pills[str(bloodborne)].label.text()
    window.on_action("y")                                          # Y on Your games: Update Steam
    assert wait_for(qapp, lambda: not window.busy)
    assert closed == [True] and shortcuts.in_steam(steam_dir) == {str(bloodborne): "[PS4] Bloodborne"}
    assert "1 game(s) in Steam" in window.games_pane.status.text() and "Read back" not in window.games_pane.status.text()
    assert window.games_pane.list.pills[str(bloodborne)].label.text().endswith("✓ Steam")
    window.games_pane.list.pills[str(bloodborne)].setFocus()
    window.on_action("x")                                          # X: played through Steam
    number = shortcuts.numbers(steam_dir)[str(bloodborne)]
    assert played[-1] == f"steam://rungameid/{(number << 32) | 0x02000000}"
    assert window.games_pane.status.text() == ("Starting Bloodborne in Steam… In the game, hold View, LB and RB together "
                                               "to quit.")             # how to quit, on the screen (owner, 30-10-2026)
    window.close()


def test_without_steam_x_starts_the_game_in_shadps4(qapp, tmp_path, monkeypatch):
    """A device without Steam (owner, 30-10-2026: a fallback): X starts shadPS4 with the game full screen, as its
    shortcut would, from shadPS4's folder; without shadPS4 it says to install it first."""
    home = tmp_path / "emulator"
    user = tmp_path / "me"
    game = make_game(user / "Games" / "PS4" / "CUSA00900", "Bloodborne", "CUSA00900")
    started, played = [], []
    window = make(qapp, home, user_home=user, start=lambda command, cwd=None: started.append((command, cwd)),
                  play=played.append)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    window.on_action("accept")
    window.games_pane.list.pills[str(game)].setFocus()
    qapp.processEvents()
    assert ("X", "Play") in window.legend.items
    window.on_action("x")
    assert started == [] and window.games_pane.status.text() == ("Install shadPS4 first: it starts Bloodborne on a "
                                                                 "device without Steam.")
    ready(home)
    window.on_action("x")
    program = emulator.program(home)
    launcher, before = play.launcher(ROOT)                      # the play mode, as the shortcut would start it
    assert started == [([launcher, *before, "-f", "true", "-g", str(game)], program.parent)]
    assert played == [] and window.games_pane.status.text() == ("Starting Bloodborne in shadPS4… In the game, hold "
                                                                "View, LB and RB together to quit.")

    def fails(command, cwd=None):
        raise PermissionError(13, "Access is denied")
    window.start_program = fails
    window.on_action("x")
    assert window.games_pane.status.text() == "shadPS4 could not start Bloodborne: Access is denied"
    window.close()


def test_update_steam_needs_shadps4(qapp, tmp_path, monkeypatch):
    make_game(tmp_path / "me" / "Games" / "PS4" / "A", "A", "CUSA00001")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    window = make(qapp, tmp_path / "emulator", steam_dir=steam_dir, user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    window.games_pane.list.first().setFocus()
    qapp.processEvents()
    window.on_action("accept")
    window.on_action("y")
    assert window.games_pane.status.text().startswith("Install shadPS4 first") and not window.busy
    window.close()


def test_a_game_written_but_not_read_back_is_said_and_logged(qapp, tmp_path, monkeypatch):
    from shadps4_manager import library
    home = tmp_path / "emulator"
    ready(home)
    make_game(tmp_path / "me" / "Games" / "PS4" / "A", "A")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    monkeypatch.setattr(library, "update_steam", lambda *a, **k: (True, "1 game(s) in Steam.", {}))
    window = make(qapp, home, steam_dir=steam_dir, user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    logged = []
    monkeypatch.setattr(window.log, "error", lambda text: logged.append(text))
    window.games_card.setFocus()
    window.games_pane.list.first().setFocus()
    qapp.processEvents()
    window.on_action("accept")
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy)
    assert "Read back from Steam's file, 0 of the 1 game(s) are there: not A" in window.games_pane.status.text()
    assert any("reading Steam's file back finds 0" in text for text in logged) and window.in_steam == {}
    window.close()


def test_the_log_is_read_in_the_app(qapp, tmp_path, monkeypatch):
    """The Log pane shows shadPS4's folder and the newest lines; A (or a tap on the pane) shows the whole log in the
    app, the d-pad scrolls it and B goes back (owner, 29-10-2026: Notepad has no button to close it)."""
    home = tmp_path / "emulator"
    ready(home)
    log = tmp_path / "app.log"
    log.write_text("".join(f"line {n}\n" for n in range(300)), encoding="utf-8")
    window = make(qapp, home)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.log_path = log
    window.log_card.setFocus()
    qapp.processEvents()
    texts = [label.text() for label in window.log_pane.findChildren(type(window.status))]
    assert "System modules" in texts and "all 24" in texts and "Games" in texts
    lines = window.log_pane.lines
    assert lines.toPlainText().splitlines() == [f"line {n}" for n in range(288, 300)]
    assert lines.focusPolicy() == portable.Qt.FocusPolicy.NoFocus                 # the d-pad never lands on it
    assert lines.verticalScrollBar().value() == lines.verticalScrollBar().maximum()   # the newest line in view
    assert window.legend.items[0] == ("A", "View log")
    window.on_action("accept")                                     # A: the whole log, here
    view = window.log_pane.view
    assert window.log_pane.viewing and view.hasFocus() and view.toPlainText().splitlines()[-1] == "line 299"
    assert BACK in window.legend.items and ("A", "View log") not in window.legend.items
    bottom = view.verticalScrollBar().value()
    window.on_action("up")                                         # the d-pad scrolls it
    assert view.verticalScrollBar().value() < bottom and view.hasFocus()
    window.on_action("back")                                       # B: the summary again, the focus on the card
    assert not window.log_pane.viewing and window.log_card.hasFocus()
    window.log_pane.tapped.emit()                                  # a tap on the pane: the whole log too
    assert window.log_pane.viewing
    window.close()


def test_the_steamgriddb_key_is_pasted_saved_and_removed(qapp, tmp_path, monkeypatch):
    r"""The BC250 app's Covers… key, as PCSX2 Manager has it on a page: one key for the suite in
    %APPDATA%\windows-portable-suite\steamgriddb-key, X Paste from the clipboard, A Save, Y Remove key with a second
    press, B back without saving, the page on LB on Your games (owner, 30-10-2026: RB on a game removes it, and
    there are no folders to show)."""
    from bc250_core import covers
    from PyQt6.QtGui import QGuiApplication
    from shadps4_manager import library
    key_file = library.key_file()
    assert key_file == tmp_path / "Roaming" / "windows-portable-suite" / "steamgriddb-key"
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    qapp.processEvents()
    window.on_action("next")                                    # RB on the games: no game, nothing
    assert window.panes.currentWidget() is window.games_pane
    window.on_action("previous")                                # LB Steam artwork
    pane = window.key_pane
    assert window.panes.currentWidget() is pane and pane.field.hasFocus()
    assert window.legend.items == [("A", "Save"), ("X", "Paste"), ("Y", "Remove key"), BACK, EXIT]
    assert pane.status.text().startswith("No key")
    window.on_action("y")                                       # no key: it says so
    assert pane.status.text().startswith("There is no key to remove")
    QGuiApplication.clipboard().setText("  0123456789abcdef0123456789abcdef \n")
    window.on_action("x")                                       # X on the key page: Paste
    assert pane.field.text() == "0123456789abcdef0123456789abcdef"
    window.on_action("back")                                    # B: back, nothing saved
    assert window.panes.currentWidget() is window.games_pane and not key_file.exists()
    window.legend.entries["LB"].pressed.emit()                  # a tap on LB Steam artwork
    window.key_pane.field.setText("0123456789abcdef0123456789abcdef")
    window.on_action("accept")                                  # A Save
    assert covers.read_key(key_file) == "0123456789abcdef0123456789abcdef"
    assert window.games_pane.status.text() == "The SteamGridDB key was changed." and pane.field.text() == ""
    window.on_action("previous")
    window.on_action("y")
    assert window.legend.items[2] == ("Y", "Press again") and key_file.exists()
    window.legend.entries["Y"].pressed.emit()                   # the second press, as a tap
    assert not key_file.exists()
    window.close()


def test_y_on_your_games_always_says_what_it_did(qapp, tmp_path, monkeypatch):
    make_game(tmp_path / "me" / "Games" / "PS4" / "A", "A")
    window = make(qapp, tmp_path / "emulator", user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    window.games_pane.list.first().setFocus()
    qapp.processEvents()
    window.on_action("accept")
    window.on_action("y")                                          # a game marked, but no Steam on this device
    assert window.games_pane.status.text() == NO_STEAM and not window.busy
    window.close()


def test_menu_shows_the_panes_information_and_the_icon_is_touch_only(qapp, tmp_path, monkeypatch):
    """Menu (☰ Info in the legend) opens the information of the pane that shows, and closes it again; the icon
    itself is never on the d-pad's way, so A in a pane is always its own action (owner, 29-10-2026)."""
    window = make(qapp, tmp_path / "emulator", user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.shadps4_card.setFocus()
    qapp.processEvents()
    assert window.shadps4_info not in window.focusables()
    window.on_action("menu")                                    # the shadPS4 pane's information: modules, packages
    assert window.popup is not None and "System modules" in window.popup.text.toPlainText()
    window.on_action("menu")
    assert window.popup is None
    window.shadnet_card.setFocus()
    qapp.processEvents()
    window.on_action("menu")
    assert window.popup is not None and "shadPS4's online service" in window.popup.text.toPlainText()
    window.on_action("menu")                                    # Menu again (or B) closes it
    assert window.popup is None and window.shadnet_card.hasFocus()
    window.close()


def test_no_path_on_the_screen_shows_the_users_name(qapp, tmp_path):
    """The privacy rule (owner, 29-10-2026): the folder, Games\\PS4 and its Modules folder show the user's folders by
    their variable (%LOCALAPPDATA%, %USERPROFILE%)."""
    import os
    user = Path(os.environ.get("USERPROFILE") or Path.home())
    games = user / "AppData" / "Local" / "Temp" / f"wps-private-test-{os.getpid()}"
    (games / "Games").mkdir(parents=True, exist_ok=True)
    try:
        window = make(qapp, tmp_path / "emulator", user_home=games)
        window.refresh_log()
        shown = [value for _label, value in window.rows()] + [label.text() for label in
                                                              window.log_pane.findChildren(type(window.status))]
        assert shown and not any(str(user).lower() in text.replace("​", "").lower() for text in shown)
        assert any("%LOCALAPPDATA%" in text or "%USERPROFILE%" in text for text in shown)
        window.close()
    finally:
        import shutil
        shutil.rmtree(games, ignore_errors=True)


def test_a_game_is_removed_from_steam_and_the_disk(qapp, tmp_path, monkeypatch):
    """RB Remove game (owner, 30-10-2026: Lumines no longer plays on 0.20.0): the first press asks, naming the
    folders, and lapses; the second takes the game out of Steam and deletes its folder with its update beside it, off
    the window's thread; the saves stay. A game that is a game folder itself is never deleted."""
    home = tmp_path / "emulator"
    shad = ready(home)
    games = tmp_path / "me" / "Games" / "PS4"
    lumines = make_game(games / "CUSA11624", "LUMINES REMASTERED", "CUSA11624")
    make_game(games / "CUSA11624-UPDATE", "LUMINES REMASTERED", "CUSA11624", "01.05", category="gp")
    (lumines.parent / "sce_sys" / "param.sfo").chmod(0o444)                         # read-only goes too
    other = make_game(games / "CUSA03865", "Galaga", "CUSA03865")
    (shad / "savedata" / "1" / "CUSA11624").mkdir(parents=True)
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    closed = []

    def with_steam_closed(change):
        closed.append(True)
        change()
        return True
    card = tmp_path / "E"
    loose = make_game(card / "Games" / "PS4", "Alone", "CUSA00002")    # a game that is a game folder itself
    window = make(qapp, home, steam_dir=steam_dir, steam_closed=with_steam_closed, user_home=tmp_path / "me",
                  drives=lambda: [card])
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.mark_game(str(lumines))
    window.mark_game(str(other))
    window.update_steam()
    assert wait_for(qapp, lambda: not window.busy) and len(shortcuts.in_steam(steam_dir)) == 2
    window.games_card.setFocus()
    window.on_action("accept")
    window.games_pane.list.pills[str(lumines)].setFocus()
    qapp.processEvents()
    window.on_action("next")                                    # RB: it asks first
    assert window.legend.items[-4] == ("RB", "Press again") and lumines.exists()
    assert window.games_pane.status.text() == ("Press the RB button again to delete CUSA11624, CUSA11624-UPDATE from "
                                               "the disk and take the game out of Steam. Its saves stay in shadPS4's "
                                               "folder.")
    assert window.games_pane.list.pills[str(lumines)].label.text().startswith("Press RB again")
    window._confirm_over()                                      # five seconds later: asked no more
    assert window.games_pane.status.text() == "" and window.legend.items[-4] == ("RB", "Remove game")
    window.games_pane.list.pills[str(lumines)].setFocus()
    window.on_action("next")
    window.legend.entries["RB"].pressed.emit()                  # the second press, as a tap
    assert wait_for(qapp, lambda: not window.busy)
    assert not (games / "CUSA11624").exists() and not (games / "CUSA11624-UPDATE").exists() and other.exists()
    assert shortcuts.in_steam(steam_dir) == {str(other): "[PS4] Galaga"} and len(closed) == 2
    assert window.games_pane.status.text() == ("LUMINES REMASTERED is removed: CUSA11624, CUSA11624-UPDATE deleted, "
                                               "its shortcut taken out of Steam. Its saves stay in shadPS4's folder.")
    assert (shad / "savedata" / "1" / "CUSA11624").is_dir()
    assert list(window.games_pane.list.pills) == [str(loose), str(other)]
    window.games_pane.list.pills[str(loose)].setFocus()
    window.on_action("next")
    assert window.games_pane.status.text().startswith("Alone is in PS4, one of the app's game folders itself")
    assert loose.exists() and not window.busy
    window.close()


def test_the_packages_in_games_ps4_are_unpacked_from_your_games(qapp, tmp_path, monkeypatch, built_pkg):
    r"""The packages are dropped in the app's own Games\PS4 folder (owner, 30-10-2026: no browsing, the manager takes
    care of them): each a short row, PKG or PKG update; an update alone waits for its game; X Unpack all unpacks the
    game into its ID's folder, then its update beside it, the files counted on the pane's line, and deletes each
    package."""
    from pkg_builder import build_pkg, default_tree
    home = tmp_path / "emulator"
    ready(home)
    user = tmp_path / "me"
    own = user / "Games" / "PS4"
    gate = threading.Event()
    from shadps4_manager import extract

    def unpack(*args, **kwargs):
        gate.wait(10)
        return extract.unpack(*args, **kwargs)
    window = make(qapp, home, user_home=user, unpack=unpack)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert own.is_dir()                                         # made by the app
    window.games_card.setFocus()
    window.on_action("accept")
    assert ("X", "Unpack all") not in window.legend.items     # nothing waits
    game = own / "galaga.pkg"
    game.write_bytes(built_pkg.path.read_bytes())
    update = build_pkg(own / "update.pkg", default_tree(), category="gp", app_ver="01.01")
    window.refresh_games()
    assert window.games_pane.summary.text().startswith("0 game(s) in 1 folder(s), 2 to unpack")
    rows = window.games_pane.list.pills
    title_id = built_pkg.title_id
    assert [p.label.text() for p in rows.values()] == [f"Synthetic Test Title  ·  {title_id}  ·  PKG",
                                                       f"Synthetic Test Title  ·  {title_id}  ·  PKG"]
    rows[f"pkg:{update.path}"].setFocus()
    qapp.processEvents()
    assert window.legend.items[:4] == [("A", "Unpack"), ("X", "Unpack all"), ("Y", "Update Steam"),
                                       ("LB", "Steam artwork")]
    window.on_action("accept")                                  # A on the update alone: its game first
    assert window.games_pane.status.text().startswith("Synthetic Test Title is an update: unpack its game first")
    window.on_action("x")                                       # X Unpack all
    assert window.busy and window.panes.currentWidget() is window.games_pane
    gate.set()
    assert wait_for(qapp, lambda: not window.busy)
    assert window.games_pane.status.text() == "2 of 2 package(s) unpacked, each package deleted after."
    assert (own / title_id / "eboot.bin").read_bytes() == built_pkg.expected_files["eboot.bin"]
    assert (own / f"{title_id}-UPDATE" / "eboot.bin").read_bytes() == update.expected_files["eboot.bin"]
    assert not game.exists() and not update.path.exists()
    assert [p.label.text() for p in window.games_pane.list.pills.values()] == [f"Synthetic Test Title  ·  {title_id}"]
    newer = build_pkg(own / "newer.pkg", default_tree(), category="gp", app_ver="01.02")
    window.refresh_games()
    assert window.games_pane.list.pills[f"pkg:{newer.path}"].label.text().endswith("·  PKG update")
    window.games_pane.list.pills[f"pkg:{newer.path}"].setFocus()
    window.on_action("accept")                                  # A: the newer update replaces the one there
    assert wait_for(qapp, lambda: not window.busy)
    assert window.games_pane.status.text() == "Synthetic Test Title is unpacked, and its package is deleted."
    assert (own / f"{title_id}-UPDATE" / "eboot.bin").read_bytes() == newer.expected_files["eboot.bin"]
    window.close()


def test_a_shortcut_made_before_the_play_mode_asks_for_update_steam(qapp, tmp_path, monkeypatch):
    """A game whose shortcut still starts shadPS4 itself (1.1.0's) says (Update Steam), and Y brings it to the play
    mode (owner, 30-10-2026: View, LB and RB held quit every game)."""
    home = tmp_path / "emulator"
    ready(home)
    user = tmp_path / "me"
    game = make_game(user / "Games" / "PS4" / "CUSA00900", "Bloodborne", "CUSA00900")
    steam_dir = tmp_path / "Steam"
    config = steam_dir / "userdata" / "1" / "config"
    config.mkdir(parents=True)
    program = emulator.program(home)
    old = steam.shortcut_entry(f'"{program}"', "[PS4] Bloodborne", f'"{program.parent}\\"', "",
                               f'-f true -g "{game}"', shortcuts.TAGS)
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": old}}))

    def with_steam_closed(change):
        change()
        return False
    window = make(qapp, home, steam_dir=steam_dir, steam_closed=with_steam_closed, user_home=user)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert window.games_pane.list.pills[str(game)].label.text().endswith("✓ Steam (Update Steam)")
    window.games_card.setFocus()
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy)
    assert shortcuts.outdated(steam_dir) == set() and len(steam.shortcuts(steam_dir)) == 1
    assert window.games_pane.list.pills[str(game)].label.text().endswith("✓ Steam")
    window.close()


def test_play_runs_the_game_without_a_window(monkeypatch, tmp_path):
    """--play, as a shortcut starts the app: shadPS4 with the shortcut's arguments from its folder, through core's
    play mode, before any window or the one-window check (the app's window may be open beside it)."""
    from shadps4_manager import __main__ as entry
    ran = []
    monkeypatch.setattr(emulator, "emulator_home", lambda: tmp_path / "emulator")
    monkeypatch.setattr(entry.applog, "setup", lambda *a, **k: tmp_path / "log")
    monkeypatch.setattr(entry.play, "run", lambda command, cwd, log, confirm: ran.append((command, cwd, confirm)) or 3)
    monkeypatch.setattr(entry, "create_app", lambda *a, **k: pytest.fail("no window in the play mode"))
    monkeypatch.setattr(sys, "argv", ["shadPS4-Manager.exe", "--play", "-f", "true", "-g", r"D:\G\eboot.bin"])
    assert entry.main() == 3
    program = emulator.program(tmp_path / "emulator")
    assert ran == [([str(program), "-f", "true", "-g", r"D:\G\eboot.bin"], program.parent, entry.play.press_enter)]

    def fails(command, cwd, log, confirm):
        raise FileNotFoundError(2, "The system cannot find the file specified")
    monkeypatch.setattr(entry.play, "run", fails)
    assert entry.main() == 1
