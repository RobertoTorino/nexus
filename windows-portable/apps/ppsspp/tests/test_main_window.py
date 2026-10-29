# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py), as PCSX2 Manager's is tested: it opens on the portable window with the header's
battery, date and time, fits the handheld's screen; every action is a button in the row at the bottom, A too, and no
pill is left (owner, 29-10-2026); B goes back and View exits; PPSSPP installed on A (off the window's thread, the
megabytes counted, View asking first meanwhile, its settings prepared after), updated from an older one, and removed
with X pressed twice; the Settings pane's rows, in tabs, step through their values, never while PPSSPP runs; Your
games from the folders and the memory stick, marked for Steam with A (never played from the app) and put in Steam;
the folder browser; the Log pane and the whole log read in the app; the SteamGridDB key; the version and the icons
are where the checks expect them."""

from __future__ import annotations

import json
import re
import tempfile
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QSettings

from bc250_core import portable
from bc250_core.gamepad import Gamepad
from bc250_core.portable import BACK, EXIT, VIEW
from bc250_core.portable import INFO as MENU_INFO
from conftest import make_disc, make_pbp
from ppsspp_manager import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, emulator, shortcuts
from ppsspp_manager.main_window import NO_STEAM, NOT_THE_GAMES, NOTHING_TO_CHANGE, OPEN_A_FOLDER, MainWindow


class FakePad:
    def events(self):
        return []

    def close(self):
        pass

    def names(self):
        return []


def fake_install(home, progress=lambda got: None, say=lambda text: None, gate=None, version=emulator.VERSION):
    """What emulator.install() leaves behind, without a download: the program, the memory stick and the record."""
    progress(12_000_000)
    if gate is not None:
        gate.wait(10)
    say("Unpacking…")
    home.mkdir(parents=True, exist_ok=True)
    (home / emulator.EXE).write_bytes(b"ppsspp")
    emulator.memstick(home).mkdir(exist_ok=True)
    (home / emulator.RECORD).write_text(json.dumps({"version": version, "files": [emulator.EXE]}), encoding="utf-8")
    return version


def wait_for(qapp, predicate, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not predicate():
        qapp.processEvents()
        time.sleep(0.01)
    return predicate()


def make(qapp, home=None, install=fake_install, running=lambda home: False, **more):
    more.setdefault("steam_dir", None)                  # never the real Steam
    more.setdefault("drives", lambda: [])
    more.setdefault("roots", lambda: [])
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


def test_the_window_opens_with_the_suites_header(qapp):
    window = make(qapp)
    assert window.header.title.text() == APP_NAME and window.header.version.text() == __version__
    assert re.fullmatch(r"82%  \|  \w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d", window.header.status.text())
    assert window.legend.items == [("A", "Install"), EXIT]          # on a card: nothing to go back to
    assert no_pills(window)
    window.close()


def test_the_window_fits_the_handhelds_screen(qapp):
    window = make(qapp)
    assert window.minimumSizeHint().height() <= 720 and window.height() == 720
    window.close()


def test_b_goes_back_and_view_exits(qapp, monkeypatch):
    """The suite's buttons (owner, 29-10-2026: "Close" on B was not clear): B goes back, from a pane to its card,
    and does nothing on a card; View (the Exit app entry) closes the app, a tap on the entry too."""
    window = make(qapp)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("back")                                    # on the PPSSPP card: nothing
    assert closed == [] and window.ppsspp_card.hasFocus()
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
    assert calls == [] and window.ppsspp_card.hasFocus()
    assert dict(window.rows())["Installed"] == "not installed"
    window.on_action("x")                                       # X Remove: says why, nothing happens
    assert "nothing to remove" in window.status.text() and calls == []
    window.close()


def test_a_installs_off_the_windows_thread_and_counts_the_megabytes(qapp, tmp_path, monkeypatch):
    gate = threading.Event()
    window = make(qapp, tmp_path / "emulator", install=lambda home, **k: fake_install(home, gate=gate, **k))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("accept")                                  # A on the PPSSPP card
    assert window.busy
    window.refresh()
    assert window.status.text() == f"Downloading PPSSPP {emulator.VERSION}… 12 of 20 MB"
    assert ("A", "Install") not in window.legend.items
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.on_action("view")                                    # Exit asks first while it downloads
    assert closed == [] and window.legend.items == [(VIEW, "Press again to exit")]
    assert window.status.text() == "Press View again to exit: the download stops."
    gate.set()
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == f"PPSSPP {emulator.VERSION} is installed."
    assert window.legend.items == [("X", "Remove PPSSPP"), EXIT]
    window.on_action("view")
    assert closed == [True]                                     # nothing runs: View exits at once


def test_a_failed_install_says_why(qapp, tmp_path):
    def failing(home, **kwargs):
        raise emulator.EmulatorError("the release has no PPSSPPWindows64.exe")
    window = make(qapp, tmp_path / "emulator", install=failing)
    window.act("accept")
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == "PPSSPP could not be installed: the release has no PPSSPPWindows64.exe"
    assert ("A", "Install") in window.legend.items
    window.close()


def test_update_and_remove_with_x_pressed_twice(qapp, tmp_path):
    home = tmp_path / "emulator"
    fake_install(home, version="1.19.3")
    save = emulator.memstick(home) / "PSP" / "SAVEDATA" / "ULUS10044" / "DATA.BIN"
    save.parent.mkdir(parents=True)
    save.write_bytes(b"x")
    window = make(qapp, home)
    assert window.legend.items == [("X", "Remove PPSSPP"), ("Y", "Update"), EXIT]
    assert window.status.text() == f"This app installs PPSSPP {emulator.VERSION}: the Y button updates it."
    window.act("y")
    assert wait_for(qapp, lambda: not window.busy) and emulator.installed(home) == emulator.VERSION
    window.legend.entries["X"].pressed.emit()                   # a tap on X Remove PPSSPP
    assert window.legend.items[0] == ("X", "Press again") and emulator.installed(home)
    assert window.status.text().startswith("Press the X button again")
    window._confirm_over()                                      # five seconds without a second press
    assert window.legend.items[0] == ("X", "Remove PPSSPP")
    window.act("x")
    window.act("x")
    assert emulator.installed(home) == "" and save.is_file()
    assert "stays" in window.status.text() and window.legend.items[0] == ("A", "Install")
    window.close()


def test_remove_while_ppsspp_runs_says_so(qapp, tmp_path):
    home = tmp_path / "emulator"
    fake_install(home)
    window = make(qapp, home, running=lambda h: True)
    window.act("x")
    window.act("x")
    assert emulator.installed(home) and window.status.text().startswith("PPSSPP is open")
    window.close()


def test_the_cards_show_their_panes(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert window.panes.currentWidget() is window.pane
    window.on_action("down")
    assert window.games_card.hasFocus() and window.panes.currentWidget() is window.games_pane
    window.on_action("down")
    assert window.settings_card.hasFocus() and window.panes.currentWidget() is window.settings_pane
    assert window.settings_pane.status.text() == "Install PPSSPP first: the settings are in its folder."
    assert window.legend.items[:3] == [("A", "Change"), ("LB", "Previous tab"), ("RB", "Next tab")]
    window.settings_pane.status.setText("")
    window.settings_pane.pills["renderer"].click()                                 # never grayed out: says why
    assert window.settings_pane.status.text() == "Install PPSSPP first: the settings are in its folder."
    window.on_action("down")
    assert window.log_card.hasFocus() and window.panes.currentWidget() is window.log_pane
    for card in (window.ppsspp_card, window.games_card, window.settings_card, window.log_card):
        card.setFocus()
        qapp.processEvents()
        assert no_pills(window)
    window.close()


def test_an_install_prepares_ppsspps_settings_before_its_first_start(qapp, tmp_path):
    from ppsspp_manager import ppsspp_settings
    home = tmp_path / "emulator"
    window = make(qapp, home)
    window.act("accept")
    assert wait_for(qapp, lambda: not window.busy)
    assert "CheckForNewVersion = False" in ppsspp_settings.settings_path(home).read_text(encoding="utf-8-sig")
    window.close()


def test_the_settings_step_and_are_written_at_once(qapp, tmp_path, monkeypatch):
    from ppsspp_manager import ppsspp_settings
    home = tmp_path / "emulator"
    fake_install(home)
    is_running = [False]
    window = make(qapp, home, running=lambda h: is_running[0])
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    pills = window.settings_pane.pills
    assert pills["renderer"].label.text() == "Renderer: Vulkan"                    # PPSSPP's default
    window.settings_card.setFocus()
    window.on_action("accept")                                                     # A on the card: the first row
    assert pills["renderer"].hasFocus()
    window.on_action("accept")
    assert pills["renderer"].label.text() == "Renderer: Direct3D 11"
    ini = ppsspp_settings.settings_path(home)
    assert "GraphicsBackend = 2 (DIRECT3D11)" in ini.read_text(encoding="utf-8-sig")
    pills["resolution"].click()
    assert pills["resolution"].label.text() == "Resolution: 1x (480 × 272, the PSP's)"
    is_running[0] = True                                                           # PPSSPP is open
    window.settings_pane.tabs.select("osd")
    pills["fps"].click()
    assert window.settings_pane.status.text().startswith("PPSSPP is open") and pills["fps"].label.text() == "Show FPS: Off"
    is_running[0] = False
    pills["fps"].click()
    assert pills["fps"].label.text() == "Show FPS: On" and "iShowStatusFlags = 2" in ini.read_text(encoding="utf-8-sig")
    window.close()


def test_the_settings_are_in_tabs(qapp, tmp_path, monkeypatch):
    """LB and RB step through Picture, Game, Controller and On screen; the focus follows to the tab's first row; the
    information tells the tab's settings; every tab's rows fit the pane."""
    from ppsspp_manager.ppsspp_settings import TABS
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    pane = window.settings_pane
    assert [key for key, _, _ in TABS] == ["picture", "game", "controller", "osd"] == pane.tabs.keys
    assert pane.tabs.current == "picture" and pane.pills["stretch"].isVisibleTo(pane)
    assert not pane.pills["fps"].isVisibleTo(pane) and "Renderer:" in pane.info.info
    assert "The A button changes" in pane.info.info
    window.settings_card.setFocus()
    window.on_action("accept")
    assert pane.pills["renderer"].hasFocus()
    window.on_action("next")                                                       # RB: the next tab
    assert pane.tabs.current == "game" and pane.pills["frameskip"].hasFocus() and "Frame skipping:" in pane.info.info
    window.on_action("previous")
    window.on_action("previous")                                                   # LB twice: round to the last
    assert pane.tabs.current == "osd" and pane.pills["fps"].hasFocus() and pane.pills["fps"].isVisibleTo(pane)
    assert pane.minimumSizeHint().height() <= window.panes.height()
    window.close()


def test_a_long_folder_wraps_and_the_window_stays_on_the_screen(qapp, tmp_path):
    deep = tmp_path / ("a-rather-long-folder-name" * 3) / "windows-portable-suite" / "windows-portable-ppsspp" / "emulator"
    window = make(qapp, deep)
    assert window.minimumSizeHint().width() <= 1280 and window.width() == 1280
    assert window.panes.minimumSizeHint().width() < 800
    window.close()


def test_the_window_fits_a_smaller_screen(qapp, tmp_path):
    # It adapts to the screen it is on (a 1080p screen at 175 % is 1097 x 617), as every app of the suite.
    portable.pin_scale((1097, 617))
    try:
        window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False), steam_dir=None,
                            home=tmp_path / "emulator", roots=lambda: [],
                            settings=QSettings(str(tmp_path / "app.ini"), QSettings.Format.IniFormat))
        window.resize(1097, 617)
        window.show()
        qapp.processEvents()
        assert window.minimumSizeHint().height() <= 617
        window.close()
    finally:
        portable.pin_scale((1280, 720))


def test_your_games_are_marked_with_a_and_put_in_steam(qapp, tmp_path, monkeypatch):
    """The games are played from Steam (owner, 29-10-2026: the app never starts one): A on a game is its Steam mark,
    Y Update Steam writes the marks."""
    home = tmp_path / "emulator"
    fake_install(home)
    stick_game = make_pbp(emulator.memstick(home) / "PSP" / "GAME" / "HOMEBREW", "A Homebrew")
    user = tmp_path / "me"
    games = user / "Games"
    daxter = make_disc(games / "PSP" / "Daxter.iso", "Daxter", "ULUS10044", pictures=True)
    (user / "Downloads").mkdir(parents=True)
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    closed = []

    def with_steam_closed(change):
        closed.append(True)
        change()
        return False
    window = make(qapp, home, steam_dir=steam_dir, steam_closed=with_steam_closed, user_home=user)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    qapp.processEvents()
    assert window.legend.items == [("A", "Steam mark"), ("Y", "Update Steam"), ("LB", "Folders"),
                                   ("RB", "Steam artwork"), MENU_INFO, EXIT]
    assert "Press the A button on a game to mark it for Steam" in window.games_pane.info.info
    assert "plays it" not in window.games_pane.info.info
    assert list(window.games_pane.list.pills) == [str(stick_game)]                 # the memory stick's, no folder yet
    window.on_action("previous")                                   # LB Folders: the usual places, and Browse
    assert window.legend.items == [("A", "Choose"), ("LB", "Games"), ("RB", "Steam artwork"), MENU_INFO, BACK, EXIT]
    pills = window.games_pane.list.pills
    assert list(pills) == [f"add:{games}", f"add:{user / 'Downloads'}", "browse"]
    pills[f"add:{games}"].click()
    assert "1 game(s) in it" in window.games_pane.status.text()
    window.on_action("back")                                       # B on the folders: the games
    pills = window.games_pane.list.pills
    assert [pill.label.text() for pill in pills.values()] == ["A Homebrew", "Daxter  ·  ULUS10044"]
    window.legend.entries["Y"].pressed.emit()                      # a tap on Y Update Steam: nothing to change yet
    assert window.games_pane.status.text() == NOTHING_TO_CHANGE
    pills[str(daxter)].setFocus()
    qapp.processEvents()
    window.on_action("accept")                                     # A: the Steam mark
    assert "✓ Steam (Update Steam)" in window.games_pane.list.pills[str(daxter)].label.text()
    window.on_action("y")                                          # Y on Your games: Update Steam
    assert wait_for(qapp, lambda: not window.busy)
    assert closed == [True] and shortcuts.in_steam(steam_dir) == {str(daxter): "[PSP] Daxter"}
    assert "1 game(s) in Steam" in window.games_pane.status.text() and "Read back" not in window.games_pane.status.text()
    assert window.games_pane.list.pills[str(daxter)].label.text().endswith("✓ Steam")
    window.close()


def test_the_folder_browser_goes_by_the_controller(qapp, tmp_path, monkeypatch):
    """Windows' own folder window cannot be used with the controller (owner, 29-10-2026): the app's browser lists the
    places and the folders; A opens one, X adds the open folder, B goes up and, from the places, back."""
    user = tmp_path / "me"
    target = user / "Games" / "PSP"
    make_disc(target / "Daxter.iso", "Daxter", "ULUS10044")
    card = tmp_path / "E"
    (card / "roms").mkdir(parents=True)
    window = make(qapp, tmp_path / "emulator", user_home=user, roots=lambda: [card])
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    window.on_action("previous")                                   # LB Folders
    window.games_pane.list.pills["browse"].click()
    assert window.panes.currentWidget() is window.browse_pane
    assert window.legend.items == [("A", "Open"), ("X", "Add this folder"), MENU_INFO, BACK, EXIT]
    rows = window.browse_pane.list.pills
    assert list(rows) == [f"dir:{user / 'Games'}", f"dir:{card}"]
    window.on_action("x")                                          # nothing open yet: says how
    assert window.browse_pane.status.text() == OPEN_A_FOLDER
    rows[f"dir:{user / 'Games'}"].setFocus()
    window.on_action("accept")                                     # A opens it
    assert window.browser.path == user / "Games" and list(window.browse_pane.list.pills)[1] == f"dir:{target}"
    window.on_action("back")                                       # B: up, to the places
    assert window.browser.path is None and window.panes.currentWidget() is window.browse_pane
    window.browse_pane.list.pills[f"dir:{user / 'Games'}"].click()
    window.browse_pane.list.pills[f"dir:{target}"].click()
    window.on_action("x")                                          # X: this folder
    assert window.panes.currentWidget() is window.games_pane and window.games_view == "folders"
    assert f"folder:{target}" in window.games_pane.list.pills and "1 game(s) in it" in window.games_pane.status.text()
    window.games_pane.list.pills["browse"].click()
    window.on_action("back")                                       # B at the places: back to the folders
    assert window.panes.currentWidget() is window.games_pane and window.browser is None
    window.close()


def test_a_game_written_but_not_read_back_is_said_and_logged(qapp, tmp_path, monkeypatch):
    from ppsspp_manager import library
    home = tmp_path / "emulator"
    fake_install(home)
    make_disc(tmp_path / "me" / "Games" / "A.iso", "A")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    monkeypatch.setattr(library, "update_steam", lambda *a, **k: (True, "1 game(s) in Steam.", {}))
    window = make(qapp, home, steam_dir=steam_dir, user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    logged = []
    monkeypatch.setattr(window.log, "error", lambda text: logged.append(text))
    window.add_folder(tmp_path / "me" / "Games")
    window.games_card.setFocus()
    window.games_pane.list.first().setFocus()
    qapp.processEvents()
    window.on_action("accept")
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy)
    assert "Read back from Steam's file, 0 of the 1 game(s) are there: not A" in window.games_pane.status.text()
    assert any("reading Steam's file back finds 0" in text for text in logged) and window.in_steam == {}
    window.close()


def test_a_folder_is_taken_off_the_list_with_a_second_press(qapp, tmp_path):
    folder = tmp_path / "games"
    make_disc(folder / "A.iso", "A")
    window = make(qapp, tmp_path / "emulator", user_home=tmp_path / "me")
    window.add_folder(folder)
    window.toggle_folders()
    key = f"folder:{folder}"
    window.games_pane.list.pills[key].click()
    assert window.games_pane.list.pills[key].label.text() == "Press A again to take it off the list"
    window.games_pane.list.pills[key].click()
    assert key not in window.games_pane.list.pills and (folder / "A.iso").is_file()
    assert "no longer a game folder" in window.games_pane.status.text()
    window.close()


def test_the_log_is_read_in_the_app(qapp, tmp_path, monkeypatch):
    """The Log pane shows the memory stick and the newest lines; A (or a tap on the pane) shows the whole log in the
    app, the d-pad scrolls it and B goes back (owner, 29-10-2026: Notepad has no button to close it)."""
    home = tmp_path / "emulator"
    fake_install(home)
    stick = emulator.memstick(home)
    for save in ("ULUS10044DATA00", "ULUS10043SAVE"):
        (stick / "PSP" / "SAVEDATA" / save).mkdir(parents=True)
    log = tmp_path / "app.log"
    log.write_text("".join(f"line {n}\n" for n in range(300)), encoding="utf-8")
    window = make(qapp, home)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.log_path = log
    window.log_card.setFocus()
    qapp.processEvents()
    texts = [label.text() for label in window.log_pane.findChildren(type(window.status))]
    assert "Saves" in texts and "2" in texts and "Save states" in texts
    assert window.log_pane.lines.text().splitlines() == [f"line {n}" for n in range(288, 300)]
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
    press, B back without saving, the page on RB."""
    from bc250_core import covers
    from PyQt6.QtGui import QGuiApplication
    from ppsspp_manager import library
    key_file = library.key_file()
    assert key_file == tmp_path / "Roaming" / "windows-portable-suite" / "steamgriddb-key"
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    qapp.processEvents()
    window.on_action("next")                                    # RB Steam artwork
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
    window.legend.entries["RB"].pressed.emit()                  # a tap on RB Steam artwork
    window.key_pane.field.setText("0123456789abcdef0123456789abcdef")
    window.on_action("accept")                                  # A Save
    assert covers.read_key(key_file) == "0123456789abcdef0123456789abcdef"
    assert window.games_pane.status.text() == "The SteamGridDB key was changed." and pane.field.text() == ""
    window.on_action("next")
    window.on_action("y")
    assert window.legend.items[2] == ("Y", "Press again") and key_file.exists()
    window.legend.entries["Y"].pressed.emit()                   # the second press, as a tap
    assert not key_file.exists()
    window.close()


def test_y_on_your_games_always_says_what_it_did(qapp, tmp_path, monkeypatch):
    folder = tmp_path / "games"
    make_disc(folder / "A.iso", "A")
    window = make(qapp, tmp_path / "emulator", user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.add_folder(folder)
    window.games_card.setFocus()
    window.toggle_folders()
    window.on_action("y")                                          # the folders: Update Steam is the games'
    assert window.games_pane.status.text() == NOT_THE_GAMES
    window.toggle_folders()
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
    window.ppsspp_card.setFocus()
    qapp.processEvents()
    window.on_action("menu")                                    # the PPSSPP pane has no information icon
    assert window.popup is None
    window.games_card.setFocus()
    qapp.processEvents()
    assert window.games_pane.info not in window.focusables()
    window.on_action("menu")
    assert window.popup is not None and "to play from Steam" in window.popup.text.text()
    window.on_action("menu")                                    # Menu again (or B) closes it
    assert window.popup is None and window.games_card.hasFocus()
    window.close()


def test_no_path_on_the_screen_shows_the_users_name(qapp, tmp_path):
    """The privacy rule (owner, 29-10-2026: the Folder row showed the user's name): the folder, the game folders and
    the places to add show the user's folders by their variable (%LOCALAPPDATA%, %USERPROFILE%)."""
    import os
    user = Path(os.environ.get("USERPROFILE") or Path.home())
    games = user / "AppData" / "Local" / "Temp" / f"wps-private-test-{os.getpid()}"
    (games / "Games").mkdir(parents=True, exist_ok=True)
    try:
        window = make(qapp, tmp_path / "emulator", user_home=games)
        window.add_folder(games / "Games")
        window.toggle_folders()
        shown = [value for _label, value in window.rows()] + [pill.label.text() for pill in
                                                              window.games_pane.list.pills.values()]
        assert shown and not any(str(user).lower() in text.replace("​", "").lower() for text in shown)
        assert any("%LOCALAPPDATA%" in text or "%USERPROFILE%" in text for text in shown)
        window.close()
    finally:
        import shutil
        shutil.rmtree(games, ignore_errors=True)
