# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py), as PCSX2 Manager's is tested: it opens on the portable window with the header's
battery, date and time, fits the handheld's screen; every action is a button in the row at the bottom, A too, and no
pill is left (owner, 29-10-2026); B goes back and View exits; PPSSPP installed on A (off the window's thread, the
megabytes counted, View asking first meanwhile, its settings prepared after), updated from an older one, and removed
with X pressed twice; the Settings pane's rows, in tabs, step through their values, never while PPSSPP runs; Your
games from the app's own Games\\PSP folders and the memory stick, marked for Steam with A and put in Steam, and
removed with RB pressed twice; the Log pane and the whole log read in the app; the SteamGridDB key; the version and
the icons are where the checks expect them."""

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

from bc250_core import keep, play, portable, steam
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private
from bc250_core.portable import BACK, EXIT, KEYBOARD, VIEW
from bc250_core.portable import INFO as MENU_INFO
from conftest import make_disc, make_pbp
from ppsspp_manager import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, emulator, shortcuts
from ppsspp_manager.main_window import (CARD_INSTALLED, CARD_NOT_INSTALLED, NO_STEAM, NOTHING_TO_CHANGE,
                                       PICK_A_GAME, MainWindow)


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
    more.setdefault("start", lambda command, cwd=None: None)   # never a real PPSSPP
    more.setdefault("user_home", Path(tempfile.mkdtemp()) / "me")   # never the real Games\PSP
    more.setdefault("drives", lambda: [])
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
    assert re.fullmatch(r"\w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d  \|  82%", window.header.status.text())   # battery last
    assert window.legend.items == [("A", "Install"), EXIT]          # on a card: nothing to go back to
    assert no_pills(window)
    window.close()


def test_the_window_fits_the_handhelds_screen(qapp):
    window = make(qapp)
    assert window.minimumSizeHint().height() <= 720 and window.height() == 720
    window.close()


def test_b_goes_back_and_view_exits(qapp, monkeypatch):
    """The suite's buttons (owner, 29-10-2026: "Close" on B was not clear): B goes back, from a pane to its card,
    and does nothing on a card; View (the Exit entry) closes the app, a tap on the entry too."""
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
    window.legend.entries[VIEW].pressed.emit()                  # a tap on Exit
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


def test_the_cards_say_what_they_are_for(qapp, tmp_path):
    """The cards' texts, the same in every emulator manager (owner, 07-11-2026): the PPSSPP card says only whether
    PPSSPP is installed and which button acts, Not installed. and Install with the A button., then Installed. and
    Remove with the X button.; the Settings pane's first tab is Screen."""
    from ppsspp_manager.ppsspp_settings import TABS
    window = make(qapp, tmp_path / "emulator")
    assert window.ppsspp_card.text.text() == CARD_NOT_INSTALLED == "Not installed.\nInstall with the A button."
    assert window.games_card.text.text() == "Mark them for Steam and press X to play."
    assert window.settings_card.text.text() == "Screen, game and controller settings"
    assert window.log_card.text.text() == "This app's log file."
    assert TABS[0][:2] == ("picture", "Screen") and "Picture" not in [name for _key, name, _group in TABS]
    window.act("accept")                                        # A Install
    assert wait_for(qapp, lambda: not window.busy) and emulator.installed(window.home)
    assert window.ppsspp_card.text.text() == CARD_INSTALLED == "Installed.\nRemove with the X button."
    window.act("x")
    window.act("x")                                             # X Remove PPSSPP, pressed twice
    assert not emulator.installed(window.home)
    assert window.ppsspp_card.text.text() == CARD_NOT_INSTALLED
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
                            home=tmp_path / "emulator", user_home=tmp_path / "me",
                            drives=lambda: [],
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
    daxter = make_disc(user / "Games" / "PSP" / "Daxter.iso", "Daxter", "ULUS10044", pictures=True)
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
    assert window.legend.items == [("A", "Steam mark"), ("Y", "Update Steam"), ("LB", "Steam artwork"), ("LT", "Refresh"), MENU_INFO,
                                   EXIT]
    assert "Press the A button on a game to mark it for Steam" in window.games_pane.info.info
    assert "plays it" not in window.games_pane.info.info
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


def test_the_games_are_in_the_apps_own_folders(qapp, tmp_path, monkeypatch):
    r"""Fixed folders, no folder selecting (owner, 30-10-2026): Games\PSP in the user's folder, made when the app
    opens, and Games\PSP on an SD card that has one; a card without it, or an empty slot, adds nothing. No folder is
    chosen or browsed to, and the folders chosen before are no longer read."""
    user = tmp_path / "me"
    card, bare = tmp_path / "E", tmp_path / "F"
    on_card = make_disc(card / "Games" / "PSP" / "Daxter.iso", "Daxter", "ULUS10044")
    make_disc(bare / "roms" / "Other.iso", "Other", "ULUS10045")    # no Games\PSP on this one
    elsewhere = make_disc(tmp_path / "old" / "Old.iso", "Old", "ULUS10046")
    settings = QSettings(str(tmp_path / "app.ini"), QSettings.Format.IniFormat)
    settings.setValue("games/folders", [str(elsewhere.parent)])    # what LB Folders kept before
    window = make(qapp, tmp_path / "emulator", user_home=user, drives=lambda: [card, bare], settings=settings)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert (user / "Games" / "PSP").is_dir()
    assert list(window.games_pane.list.pills) == [str(on_card)]
    assert window.games_pane.summary.text().startswith("1 game(s) in 2 folder(s)")
    assert not hasattr(window, "browse_pane") and not hasattr(window, "toggle_folders")
    window.games_card.setFocus()
    window.on_action("previous")                                   # LB: Steam artwork
    assert window.panes.currentWidget() is window.key_pane
    window.on_action("back")
    window.log_card.setFocus()
    qapp.processEvents()
    texts = [label.text().replace("​", "") for label in window.log_pane.findChildren(type(window.status))]
    assert "Games" in texts and any(text.endswith("\\me\\Games\\PSP") for text in texts)
    window.close()
    empty = make(qapp, tmp_path / "emulator2", user_home=tmp_path / "you")
    assert empty.games_pane.status.text() == ("No games yet: put your disc images (ISO, CSO, CHD) or memory stick "
                                              f"games in {private(tmp_path / 'you' / 'Games' / 'PSP')}, and they show "
                                              "here.")
    empty.close()


def test_remove_game_lets_the_user_decide_what_to_keep(qapp, tmp_path, monkeypatch):
    """RB Remove game (owner, 01-11-2026: before deleting anything, let the user decide what to keep): a page of what
    would go, the game's file and its shortcut in Steam, each with its size and marked Delete; A turns a row to Keep
    and back, X deletes only the rows still marked Delete, off the window's thread, B goes back and deletes nothing.
    A memory stick game is its own folder; the saves stay; a game that is a game folder itself is never offered."""
    home = tmp_path / "emulator"
    fake_install(home)
    stick = emulator.memstick(home)
    homebrew = make_pbp(stick / "PSP" / "GAME" / "HOMEBREW", "A Homebrew")
    (stick / "PSP" / "SAVEDATA" / "HOMEBREW00").mkdir(parents=True)
    games = tmp_path / "me" / "Games" / "PSP"
    daxter = make_disc(games / "Daxter" / "Daxter.iso", "Daxter", "ULUS10044")
    (games / "Daxter" / "notes.txt").write_text("mine", encoding="utf-8")
    daxter.chmod(0o444)                                            # read-only goes too
    loose = make_pbp(games, "Alone")                               # a game that is a game folder itself
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    closed = []

    def with_steam_closed(change):
        closed.append(True)
        change()
        return True
    window = make(qapp, home, steam_dir=steam_dir, steam_closed=with_steam_closed, user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.mark_game(str(daxter))
    window.update_steam()
    assert wait_for(qapp, lambda: not window.busy) and len(shortcuts.in_steam(steam_dir)) == 1
    window.games_card.setFocus()
    window.on_action("accept")
    window.games_pane.list.pills[str(daxter)].setFocus()
    qapp.processEvents()
    assert window.legend.items[3] == ("LB", "Steam artwork") and window.legend.items[4] == ("RB", "Remove game")
    window.on_action("next")                                       # RB: the page, nothing deleted yet
    assert window.panes.currentWidget() is window.keep_pane and daxter.exists()
    assert window.keep_pane.heading.text() == "Remove Daxter"
    size = keep.human(daxter.stat().st_size)
    texts = [pill.label.text() for pill in window.keep_pane.list.pills.values()]
    assert texts == [f"Delete  ·  Daxter.iso (the game)  ·  {size}", "Delete  ·  Its shortcut in Steam"]
    assert f"frees {size}" in window.keep_pane.summary.text()
    assert window.legend.items[:2] == [("A", "Keep"), ("X", "Delete marked")]
    window.on_action("back")                                       # B: back, nothing deleted
    assert window.panes.currentWidget() is window.games_pane and daxter.exists()
    assert window.games_pane.status.text() == "Nothing was deleted."
    assert len(shortcuts.in_steam(steam_dir)) == 1
    window.games_pane.list.pills[str(daxter)].setFocus()
    window.on_action("next")
    game_row = f"path:{daxter}"
    window.on_action("accept")                                     # A on the first row: Keep
    assert window.keep_pane.list.pills[game_row].label.text().startswith("Keep  ·  Daxter.iso")
    assert window.keep_pane.list.pills[game_row].hasFocus() and window.legend.items[0] == ("A", "Delete")
    window.keep_pane.list.pills["steam"].setFocus()
    window.on_action("accept")                                     # the shortcut kept too: nothing marked
    window.on_action("x")
    assert window.keep_pane.status.text() == "Nothing is marked Delete: B goes back, and nothing is deleted."
    window.on_action("accept")                                     # the shortcut marked Delete again
    window.legend.entries["X"].pressed.emit()                      # X, as a tap: only the shortcut goes
    assert wait_for(qapp, lambda: not window.busy)
    assert daxter.exists() and shortcuts.in_steam(steam_dir) == {} and len(closed) == 2
    assert window.panes.currentWidget() is window.games_pane
    assert window.games_pane.status.text() == ("Daxter: deleted Its shortcut in Steam; kept Daxter.iso (the game). "
                                               "Your saves stay on PPSSPP's memory stick.")
    window.games_pane.list.pills[str(daxter)].setFocus()           # now the file, out of Steam already
    window.on_action("next")
    assert list(window.keep_pane.list.pills) == [game_row]
    window.on_action("x")
    assert wait_for(qapp, lambda: not window.busy)
    assert not daxter.exists() and (games / "Daxter" / "notes.txt").is_file() and len(closed) == 2
    assert window.games_pane.status.text() == ("Daxter: deleted Daxter.iso (the game). Your saves stay on PPSSPP's "
                                               "memory stick.")
    assert list(window.games_pane.list.pills) == [str(homebrew), str(loose)]
    window.games_pane.list.pills[str(homebrew)].setFocus()         # a memory stick game: its own folder
    window.on_action("next")
    assert [pill.label.text().split("  ·  ")[1] for pill in window.keep_pane.list.pills.values()] == [
        "HOMEBREW (its folder)"]
    window.on_action("x")
    assert wait_for(qapp, lambda: not window.busy)
    assert not homebrew.parent.exists() and (stick / "PSP" / "SAVEDATA" / "HOMEBREW00").is_dir()
    window.games_pane.list.pills[str(loose)].setFocus()
    window.on_action("next")
    assert window.panes.currentWidget() is window.games_pane
    assert window.games_pane.status.text().startswith("Alone is in PSP, one of the app's game folders itself")
    assert loose.exists() and not window.busy
    window.running = lambda home: True                             # never while PPSSPP runs
    window.on_action("next")
    assert window.games_pane.status.text() == "PPSSPP is open: quit the game first, then remove it."
    window.close()


def test_a_game_written_but_not_read_back_is_said_and_logged(qapp, tmp_path, monkeypatch):
    from ppsspp_manager import library
    home = tmp_path / "emulator"
    fake_install(home)
    make_disc(tmp_path / "me" / "Games" / "PSP" / "A.iso", "A")
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
    assert window.log_pane.lines.toPlainText().splitlines() == [f"line {n}" for n in range(288, 300)]
    summary = window.log_pane.lines.verticalScrollBar()                 # the newest lines in sight, never cut off
    assert summary.value() == summary.maximum() and window.log_pane.lines not in window.focusables()
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
    press, B back without saving, the page on LB."""
    from bc250_core import covers
    from PyQt6.QtGui import QGuiApplication
    from ppsspp_manager import library
    key_file = library.key_file()
    assert key_file == tmp_path / "Roaming" / "windows-portable-suite" / "steamgriddb-key"
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    qapp.processEvents()
    window.on_action("previous")                                # LB Steam artwork
    pane = window.key_pane
    assert window.panes.currentWidget() is pane and pane.field.hasFocus()
    assert window.legend.items == [("A", "Save"), ("X", "Paste"), ("Y", "Remove key"), KEYBOARD, BACK, EXIT]
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
    make_disc(tmp_path / "me" / "Games" / "PSP" / "A.iso", "A")
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
    window.ppsspp_card.setFocus()
    qapp.processEvents()
    window.on_action("menu")                                    # the PPSSPP pane has no information icon
    assert window.popup is None
    window.games_card.setFocus()
    qapp.processEvents()
    assert window.games_pane.info not in window.focusables()
    window.on_action("menu")
    assert window.popup is not None and "to play from Steam" in window.popup.text.toPlainText()
    window.on_action("menu")                                    # Menu again (or B) closes it
    assert window.popup is None and window.games_card.hasFocus()
    window.close()


def test_no_path_on_the_screen_shows_the_users_name(qapp, tmp_path):
    """The privacy rule (owner, 29-10-2026: the Folder row showed the user's name): the folder and the game folder
    show the user's folders by their variable (%LOCALAPPDATA%, %USERPROFILE%)."""
    import os
    user = Path(os.environ.get("USERPROFILE") or Path.home())
    games = user / "AppData" / "Local" / "Temp" / f"wps-private-test-{os.getpid()}"
    games.mkdir(parents=True, exist_ok=True)
    try:
        window = make(qapp, tmp_path / "emulator", user_home=games)
        window.log_card.setFocus()
        qapp.processEvents()
        shown = ([value for _label, value in window.rows()] + [window.games_pane.status.text()]
                 + [label.text() for label in window.log_pane.findChildren(type(window.status))])
        assert shown and not any(str(user).lower() in text.replace("​", "").lower() for text in shown)
        assert any("%LOCALAPPDATA%" in text or "%USERPROFILE%" in text for text in shown)
        window.close()
    finally:
        import shutil
        shutil.rmtree(games, ignore_errors=True)


def test_a_game_is_played_through_steam(qapp, tmp_path, monkeypatch):
    """X on a game in Steam starts it through Steam, by its shortcut's appid; a game not in Steam yet says how;
    Steam's library is the portal's (owner, 30-10-2026: no Open Steam row)."""
    home = tmp_path / "emulator"
    fake_install(home)
    game = make_disc(tmp_path / "me" / "Games" / "PSP" / "Daxter.iso", "Daxter", "ULUS10044")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    opened = []

    def with_steam_closed(change):
        change()
        return False
    window = make(qapp, home, steam_dir=steam_dir, steam_closed=with_steam_closed, user_home=tmp_path / "me",
                  open_url=opened.append)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    window.games_pane.list.pills[str(game)].setFocus()
    qapp.processEvents()
    title = window.focused_game().title
    assert window.legend.items[:3] == [("A", "Steam mark"), ("X", "Play"), ("Y", "Update Steam")]
    window.on_action("x")                                          # not in Steam yet: says how
    assert opened == [] and window.games_pane.status.text() == (f"{title} is not in Steam yet: A marks it, then Y "
                                                                "Update Steam puts it there.")
    window.on_action("accept")                                     # A: the Steam mark, Y: into Steam
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy)
    window.games_pane.list.pills[str(game)].setFocus()
    qapp.processEvents()
    window.on_action("x")                                          # X: started through Steam
    item = next(item for item in steam.shortcuts(steam_dir) if shortcuts.ours(item))
    number = shortcuts.numbers(steam_dir)[str(game)]
    assert number == steam.appid(str(steam.field(item, "Exe")), str(steam.field(item, "AppName")))
    assert opened == [steam.play_url(number)]
    assert window.games_pane.status.text() == f"Starting {title} in Steam… {play.QUIT_HINT}"   # how to quit
    assert not hasattr(window, "open_steam")
    window.games_card.setFocus()                                   # X on no game plays nothing
    qapp.processEvents()
    window.on_action("x")
    assert opened == [steam.play_url(number)] and window.games_pane.status.text() == PICK_A_GAME
    window.close()


def test_without_steam_x_starts_the_game_in_ppsspp(qapp, tmp_path, monkeypatch):
    """A device without Steam (owner, 30-10-2026: a fallback): X starts PPSSPP with the game full screen, as its
    shortcut would, from PPSSPP's folder; without PPSSPP it says to install it first."""
    home = tmp_path / "emulator"
    game = make_disc(tmp_path / "me" / "Games" / "PSP" / "Daxter.iso", "Daxter", "ULUS10044")
    started, opened = [], []
    window = make(qapp, home, user_home=tmp_path / "me", start=lambda command, cwd=None: started.append((command, cwd)),
                  open_url=opened.append)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    window.games_pane.list.pills[str(game)].setFocus()
    qapp.processEvents()
    title = window.focused_game().title
    assert ("X", "Play") in window.legend.items
    window.on_action("x")
    assert started == [] and window.games_pane.status.text() == (f"Install PPSSPP first: it starts {title} on a "
                                                                 "device without Steam.")
    fake_install(home)
    window.on_action("x")
    program = emulator.program(home)
    launcher, before = play.launcher(ROOT)                      # the play mode, as the shortcut would start it
    assert started == [([launcher, *before, *emulator.GAME_ARGS, str(game)], program.parent)]
    assert opened == [] and window.games_pane.status.text() == f"Starting {title} in PPSSPP… {play.QUIT_HINT}"

    def fails(command, cwd=None):
        raise PermissionError(13, "Access is denied")
    window.start_program = fails
    window.on_action("x")
    assert window.games_pane.status.text() == f"PPSSPP could not start {title}: Access is denied"
    window.close()


def test_a_shortcut_made_before_the_play_mode_asks_for_update_steam(qapp, tmp_path, monkeypatch):
    """A game whose shortcut still starts PPSSPP itself (1.0.1's) says (Update Steam), and Y brings it to the play
    mode (owner, 30-10-2026: View, LB and RB held quit every game)."""
    home = tmp_path / "emulator"
    fake_install(home)
    game = make_disc(tmp_path / "me" / "Games" / "PSP" / "Daxter.iso", "Daxter", "ULUS10044")
    steam_dir = tmp_path / "Steam"
    config = steam_dir / "userdata" / "1" / "config"
    config.mkdir(parents=True)
    program = emulator.program(home)
    old = steam.shortcut_entry(f'"{program}"', "[PSP] Daxter", f'"{program.parent}"', "",
                               f'--fullscreen --pause-menu-exit "{game}"', shortcuts.TAGS)
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": old}}))

    def with_steam_closed(change):
        change()
        return False
    window = make(qapp, home, steam_dir=steam_dir, steam_closed=with_steam_closed, user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert window.games_pane.list.pills[str(game)].label.text().endswith("✓ Steam (Update Steam)")
    window.games_card.setFocus()
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy)
    assert shortcuts.outdated(steam_dir) == set() and len(steam.shortcuts(steam_dir)) == 1
    assert window.games_pane.list.pills[str(game)].label.text().endswith("✓ Steam")
    window.close()


def test_play_runs_the_game_without_a_window(monkeypatch, tmp_path):
    """--play, as a shortcut starts the app: PPSSPP with the shortcut's arguments from its folder, through core's
    play mode, before any window or the one-window check (the app's window may be open beside it)."""
    from ppsspp_manager import __main__ as entry
    ran = []
    monkeypatch.setattr(emulator, "emulator_home", lambda: tmp_path / "emulator")
    monkeypatch.setattr(entry.applog, "setup", lambda *a, **k: tmp_path / "log")
    monkeypatch.setattr(entry.play, "run", lambda command, cwd, log: ran.append((command, cwd)) or 3)
    monkeypatch.setattr(entry, "create_app", lambda *a, **k: pytest.fail("no window in the play mode"))
    monkeypatch.setattr(entry.play, "missing", lambda game: False)    # the game is there (test_play_mode.py: not)
    monkeypatch.setattr(sys, "argv", ["PPSSPP-Manager.exe", "--play", "--fullscreen", "--pause-menu-exit", "D:/G.iso"])
    assert entry.main() == 3
    program = emulator.program(tmp_path / "emulator")
    assert ran == [([str(program), "--fullscreen", "--pause-menu-exit", "D:/G.iso"], program.parent)]

    def fails(command, cwd, log):
        raise FileNotFoundError(2, "The system cannot find the file specified")
    monkeypatch.setattr(entry.play, "run", fails)
    assert entry.main() == 1


def test_lt_refresh_reads_the_game_folders_again(qapp, monkeypatch):
    """LT Refresh on Your games reads the game folders again (owner, 01-11-2026: a game put there showed only after
    the app started again); not while a job runs. The widest legend of the pane still fits 1280 x 720."""
    window = make(qapp)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    qapp.processEvents()
    assert ("LT", "Refresh") in window.legend.items
    read = []
    refresh = window.refresh_games
    monkeypatch.setattr(window, "refresh_games", lambda *args: (read.append(True), refresh(*args)))
    window.on_action("lt")
    assert read == [True] and window.games_pane.status.text().startswith("The game folders were read again: ")
    window.busy, window._job = True, "install"
    window.legend.entries["LT"].pressed.emit()                     # a tap on the entry: busy, says why
    assert read == [True] and window.games_pane.status.text() == sys.modules[type(window).__module__].BUSY
    window.busy = False
    left, _, right, _ = window.margins()
    window.legend.set_items([("A", "Steam mark"), ("X", "Play"), ("Y", "Update Steam"), ("LB", "Steam artwork"),
                             ("RB", "Remove game"), ("LT", "Refresh"), MENU_INFO, BACK, EXIT])
    qapp.processEvents()
    assert window.legend.sizeHint().width() <= 1280 - left - right
    window.close()
