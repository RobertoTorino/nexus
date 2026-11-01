# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py), as RPCS3 Manager's is tested: it opens on the portable window with the header's
battery, date and time, fits the handheld's screen; every action is a button in the row at the bottom, A too, and no
pill is left (owner, 29-10-2026); B goes back and View exits; Xenia installed on A (off the window's thread, the
megabytes counted, View asking first meanwhile), updated from another build, and removed with X pressed twice; a newer
build on GitHub shown; the Settings pane's rows, in tabs, step through their values, never while Xenia runs; Your games
from the app's Games\\Xbox360 folders, marked for Steam with A and put in Steam, removed with RB on the keep page;
the Log pane and the whole log read in the app; the SteamGridDB key; the version and the icons are where the checks
expect them."""

from __future__ import annotations

import os
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
from bc250_core.portable import BACK, EXIT, KEYBOARD, VIEW
from bc250_core.portable import INFO as MENU_INFO
from bc250_core.updates import ReleaseInfo
from conftest import fake_install, make_iso, make_package, make_xex
from xenia_manager import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, emulator, shortcuts
from xenia_manager.main_window import NO_STEAM, NOTHING_TO_CHANGE, PICK_A_GAME, MainWindow


class FakePad:
    def events(self):
        return []

    def close(self):
        pass

    def names(self):
        return []


def wait_for(qapp, predicate, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not predicate():
        qapp.processEvents()
        time.sleep(0.01)
    return predicate()


def make(qapp, home=None, install=fake_install, running=lambda home: False, **more):
    more.setdefault("steam_dir", None)                  # never the real Steam
    more.setdefault("start", lambda command, cwd=None: None)   # never a real Xenia
    more.setdefault("drives", lambda: [])
    more.setdefault("user_home", Path(tempfile.mkdtemp()) / "me")   # never the real Games\\Xbox360
    more.setdefault("runtime_missing", lambda: [])
    more.setdefault("newer_release", lambda: None)      # never GitHub
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
    assert window.legend.items == [("A", "Install"), MENU_INFO, EXIT]       # on a card: nothing to go back to
    assert no_pills(window)
    window.close()


def test_the_window_fits_the_handhelds_screen(qapp):
    window = make(qapp)
    assert window.minimumSizeHint().height() <= 720 and window.height() == 720
    window.close()


def test_b_goes_back_and_view_exits(qapp, monkeypatch):
    """The suite's buttons (owner, 29-10-2026): B goes back, from a pane to its card, and does nothing on a card; View
    (the Exit entry) closes the app, a tap on the entry too."""
    window = make(qapp)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("back")                                    # on the Xenia card: nothing
    assert closed == [] and window.xenia_card.hasFocus()
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
    assert calls == [] and window.xenia_card.hasFocus()
    assert dict(window.rows())["Installed"] == "not installed" and dict(window.rows())["This app installs"] == "e6cd2e4"
    window.on_action("x")                                       # X Remove: says why, nothing happens
    assert "nothing to remove" in window.status.text() and calls == []
    window.close()


def test_a_installs_off_the_windows_thread_and_counts_the_megabytes(qapp, tmp_path, monkeypatch):
    gate = threading.Event()
    window = make(qapp, tmp_path / "emulator", install=lambda home, **k: fake_install(home, gate=gate, **k))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("accept")                                  # A on the Xenia card
    assert window.busy
    window.refresh()
    assert window.status.text() == f"Downloading Xenia {emulator.VERSION}… 1.2 of 3.7 MB"
    assert ("A", "Install") not in window.legend.items
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.on_action("view")                                    # Exit asks first while it downloads
    assert closed == [] and window.legend.items == [(VIEW, "Press again to exit")]
    assert window.status.text() == "Press View again to exit: the download stops."
    gate.set()
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == f"Xenia {emulator.VERSION} is installed."
    assert window.legend.items == [("X", "Remove Xenia"), MENU_INFO, EXIT]
    window.on_action("view")
    assert closed == [True]                                     # nothing runs: View exits at once


def test_a_failed_install_says_why(qapp, tmp_path):
    def failing(home, **kwargs):
        raise emulator.EmulatorError("the archive has no xenia_canary.exe")
    window = make(qapp, tmp_path / "emulator", install=failing)
    window.act("accept")
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == "Xenia could not be installed: the archive has no xenia_canary.exe"
    assert ("A", "Install") in window.legend.items
    window.close()


def test_update_and_remove_with_x_pressed_twice(qapp, tmp_path):
    home = tmp_path / "emulator"
    fake_install(home, version="f42147a")
    save = home / "content" / "0000000000000000" / "4D5307E6" / "00000001" / "save.bin"
    save.parent.mkdir(parents=True)
    save.write_bytes(b"x")
    window = make(qapp, home)
    assert window.legend.items == [("X", "Remove Xenia"), ("Y", "Update"), MENU_INFO, EXIT]
    assert window.status.text() == f"This app installs Xenia {emulator.VERSION}: the Y button updates it."
    window.act("y")
    assert wait_for(qapp, lambda: not window.busy) and emulator.installed(home) == emulator.VERSION
    window.legend.entries["X"].pressed.emit()                   # a tap on X Remove Xenia
    assert window.legend.items[0] == ("X", "Press again") and emulator.installed(home)
    assert window.status.text().startswith("Press the X button again")
    window._confirm_over()                                      # five seconds without a second press
    assert window.legend.items[0] == ("X", "Remove Xenia")
    window.act("x")
    window.act("x")
    assert emulator.installed(home) == "" and save.is_file()
    assert "stays" in window.status.text() and window.legend.items[0] == ("A", "Install")
    window.close()


def test_remove_while_xenia_runs_says_so(qapp, tmp_path):
    home = tmp_path / "emulator"
    fake_install(home)
    window = make(qapp, home, running=lambda h: True)
    window.act("x")
    window.act("x")
    assert emulator.installed(home) and window.status.text().startswith("Xenia is open")
    window.close()


def test_the_runtime_is_asked_for_and_a_newer_build_shown(qapp, tmp_path):
    home = tmp_path / "emulator"
    fake_install(home)
    window = make(qapp, home, runtime_missing=lambda: ["msvcp140.dll"],
                  newer_release=lambda: ReleaseInfo("48b318a", "48b318a", "https://x/48b318a", "2026-10-27"))
    assert window.status.text().startswith("Xenia needs Microsoft's Visual C++ runtime (msvcp140.dll missing")
    assert wait_for(qapp, lambda: window.newer is not None)
    assert dict(window.rows())["Newest build"].startswith("48b318a (2026-10-27): a later version of this app brings")
    assert emulator.installed(home) == emulator.VERSION
    window.close()


def test_the_cards_show_their_panes(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert window.panes.currentWidget() is window.pane
    window.on_action("down")
    assert window.games_card.hasFocus() and window.panes.currentWidget() is window.games_pane
    window.on_action("down")
    assert window.settings_card.hasFocus() and window.panes.currentWidget() is window.settings_pane
    assert window.settings_pane.status.text() == "Install Xenia first: the settings are in its folder."
    assert window.legend.items[:3] == [("A", "Change"), ("LB", "Previous tab"), ("RB", "Next tab")]
    window.settings_pane.status.setText("")
    window.settings_pane.pills["gpu"].click()                                      # never grayed out: says why
    assert window.settings_pane.status.text() == "Install Xenia first: the settings are in its folder."
    window.on_action("down")
    assert window.log_card.hasFocus() and window.panes.currentWidget() is window.log_pane
    for card in (window.xenia_card, window.games_card, window.settings_card, window.log_card):
        card.setFocus()
        qapp.processEvents()
        assert no_pills(window)
    window.close()


def test_the_settings_step_and_are_written_at_once(qapp, tmp_path, monkeypatch):
    from xenia_manager import xenia_settings
    home = tmp_path / "emulator"
    fake_install(home)
    is_running = [False]
    window = make(qapp, home, running=lambda h: is_running[0])
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    pills = window.settings_pane.pills
    assert pills["gpu"].label.text() == "Graphics: Automatic (Direct3D 12)"         # Xenia's default
    window.settings_card.setFocus()
    window.on_action("accept")                                                     # A on the card: the first row
    assert pills["gpu"].hasFocus()
    window.on_action("accept")
    assert pills["gpu"].label.text() == "Graphics: Direct3D 12"
    config = xenia_settings.settings_path(home)
    assert "gpu = 'd3d12'" in config.read_text(encoding="utf-8").splitlines()
    pills["scale"].click()
    assert pills["scale"].label.text() == "Resolution scale: 2x (1440p)"
    is_running[0] = True                                                           # Xenia is open
    window.settings_pane.tabs.select("sound")
    pills["mute"].click()
    assert window.settings_pane.status.text().startswith("Xenia is open")
    assert pills["mute"].label.text() == "Mute: Off"
    is_running[0] = False
    pills["mute"].click()
    assert pills["mute"].label.text() == "Mute: On"
    assert "mute = true" in config.read_text(encoding="utf-8").splitlines()
    window.close()


def test_the_settings_are_in_tabs(qapp, tmp_path, monkeypatch):
    """LB and RB step through Picture, Speed, Sound and Console; the focus follows to the tab's first row; the
    information tells the tab's settings; every tab's rows fit the pane."""
    from xenia_manager.xenia_settings import TABS
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    pane = window.settings_pane
    assert [key for key, _, _ in TABS] == ["picture", "speed", "sound", "console"] == pane.tabs.keys
    assert pane.tabs.current == "picture" and pane.pills["vsync"].isVisibleTo(pane)
    assert not pane.pills["framelimit"].isVisibleTo(pane) and "Graphics:" in pane.info.info
    window.settings_card.setFocus()
    window.on_action("accept")
    assert pane.pills["gpu"].hasFocus()
    window.on_action("next")                                                       # RB: the next tab
    assert pane.tabs.current == "speed" and pane.pills["framelimit"].hasFocus() and "Frame limit:" in pane.info.info
    window.on_action("previous")
    window.on_action("previous")                                                   # LB twice: round to the last
    assert pane.tabs.current == "console" and pane.pills["license"].hasFocus()
    assert pane.minimumSizeHint().height() <= window.panes.height()
    window.close()


def test_a_long_folder_wraps_and_the_window_stays_on_the_screen(qapp, tmp_path):
    deep = tmp_path / ("a-rather-long-folder-name" * 3) / "windows-portable-suite" / "windows-portable-xenia" / "emulator"
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
    """The games are played from Steam (owner, 29-10-2026; without Steam Xenia starts one): A on a game is its Steam
    mark, Y Update Steam writes the marks."""
    home = tmp_path / "emulator"
    fake_install(home)
    user = tmp_path / "me"
    games = user / "Games" / "Xbox360"
    card = tmp_path / "E"
    halo = make_iso(games / "Halo 3.iso")
    gears = make_xex(games / "Gears of War" / "default.xex", 0x4D5307D5)
    braid = make_package(card / "Games" / "Xbox360" / "Content", "Braid", 0x000D0000, 0x58410954)   # on the SD card
    make_iso(user / "Games" / "Elsewhere.iso")                     # not in Games\Xbox360: not looked in
    old = QSettings(str(tmp_path / "app.ini"), QSettings.Format.IniFormat)
    old.setValue("games/folders", [str(user / "Games")])           # a folder added before: no longer read
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    closed = []

    def with_steam_closed(change):
        closed.append(True)
        change()
        return False
    window = make(qapp, home, steam_dir=steam_dir, steam_closed=with_steam_closed, user_home=user,
                  drives=lambda: [card], settings=old)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    qapp.processEvents()
    assert window.legend.items == [("A", "Steam mark"), ("Y", "Update Steam"), ("LB", "Steam artwork"), ("LT", "Refresh"), MENU_INFO,
                                   EXIT]
    assert "Press the A button on a game to mark it for Steam" in window.games_pane.info.info
    assert window.games_pane.summary.text().startswith("3 game(s) in 2 folder(s)")    # the user's and the card's
    assert dict(window.rows())["Games"] == "3"
    pills = window.games_pane.list.pills
    assert [pill.label.text() for pill in pills.values()] == ["Braid  ·  58410954  ·  Arcade",
                                                              "Gears of War  ·  4D5307D5  ·  XEX", "Halo 3  ·  ISO"]
    window.legend.entries["Y"].pressed.emit()                      # a tap on Y Update Steam: nothing to change yet
    assert window.games_pane.status.text() == NOTHING_TO_CHANGE
    pills[str(halo)].setFocus()
    qapp.processEvents()
    window.on_action("accept")                                     # A: the Steam mark
    assert "✓ Steam (Update Steam)" in window.games_pane.list.pills[str(halo)].label.text()
    window.on_action("y")                                          # Y on Your games: Update Steam
    assert wait_for(qapp, lambda: not window.busy)
    assert closed == [True] and shortcuts.in_steam(steam_dir) == {str(halo): "[X360] Halo 3"}
    assert "1 game(s) in Steam" in window.games_pane.status.text() and "Read back" not in window.games_pane.status.text()
    assert window.games_pane.list.pills[str(halo)].label.text().endswith("✓ Steam")
    item = next(i for i in steam.shortcuts(steam_dir) if i.get("AppName"))
    launcher, before = play.launcher(ROOT)                         # the play mode (owner, 30-10-2026)
    assert item["LaunchOptions"] == play.launch_options(before, f'--fullscreen=true "{halo}"')
    assert item["Exe"] == f'"{launcher}"'
    assert str(gears) in window.games_pane.list.pills and str(braid) in window.games_pane.list.pills
    window.close()


def test_update_steam_needs_xenia(qapp, tmp_path, monkeypatch):
    make_iso(tmp_path / "me" / "Games" / "Xbox360" / "A.iso")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    window = make(qapp, tmp_path / "emulator", steam_dir=steam_dir, user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.refresh_games()
    window.games_card.setFocus()
    window.games_pane.list.first().setFocus()
    qapp.processEvents()
    window.on_action("accept")
    window.on_action("y")
    assert window.games_pane.status.text().startswith("Install Xenia first") and not window.busy
    window.close()


def test_a_game_is_removed_from_steam_and_the_disk(qapp, tmp_path, monkeypatch):
    """RB Remove game (owner, 30-10-2026: a game that no longer plays goes; owner, 01-11-2026: before deleting
    anything, let the user decide what to keep): the keep page lists the game and its Steam shortcut, both marked
    Delete; B deletes nothing; X deletes the marked ones off the window's thread, the shortcut out of Steam; Xenia's
    content stays. A game that is a game folder itself is never offered."""
    home = tmp_path / "emulator"
    fake_install(home)
    (home / "content" / "4D5307D5").mkdir(parents=True)          # the game's saves, in Xenia's folder
    games = tmp_path / "me" / "Games" / "Xbox360"
    gears = make_xex(games / "Gears of War" / "default.xex", 0x4D5307D5)
    (games / "Gears of War" / "media.xex").write_bytes(b"XEX2")
    halo = make_iso(games / "Halo 3.iso")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    closed = []

    def with_steam_closed(change):
        closed.append(True)
        change()
        return True
    card = tmp_path / "E"
    loose = make_xex(card / "Games" / "Xbox360" / "default.xex", 0x41560817)   # a game that is a game folder itself
    window = make(qapp, home, steam_dir=steam_dir, steam_closed=with_steam_closed, user_home=tmp_path / "me",
                  drives=lambda: [card])
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.mark_game(str(gears))
    window.mark_game(str(halo))
    window.update_steam()
    assert wait_for(qapp, lambda: not window.busy) and len(shortcuts.in_steam(steam_dir)) == 2
    window.games_card.setFocus()
    window.on_action("accept")
    window.games_pane.list.pills[str(gears)].setFocus()
    qapp.processEvents()
    assert window.legend.items[4] == ("RB", "Remove game")
    window.on_action("next")                                    # RB: the keep page, nothing deleted yet
    assert window.panes.currentWidget() is window.keep_pane and gears.exists()
    assert window.keep_pane.heading.text() == "Remove Gears of War"
    texts = [pill.label.text() for pill in window.keep_pane.list.pills.values()]
    assert texts[0].startswith("Delete  ·  Gears of War (the game's folder)  ·  ")
    assert texts[1] == "Delete  ·  Steam shortcut"
    assert window.keep_pane.summary.text().startswith("The X button deletes the rows marked Delete (")
    window.on_back()                                            # B: nothing deleted
    assert window.panes.currentWidget() is window.games_pane and gears.exists()
    assert window.games_pane.status.text() == "Nothing was deleted." and len(closed) == 1
    window.games_pane.list.pills[str(gears)].setFocus()
    window.on_action("next")
    keys = list(window.keep_pane.list.pills)
    window.keep_pane.list.pills[keys[0]].setFocus()
    qapp.processEvents()
    assert window.legend.items[:2] == [("A", "Keep"), ("X", "Delete marked")]
    window.on_action("accept")                                  # A: the folder is kept
    assert window.keep_pane.list.pills[keys[0]].label.text().startswith("Keep  ·  Gears of War")
    assert window.keep_pane.list.pills[keys[0]].hasFocus() and window.legend.items[0] == ("A", "Delete")
    window.keep_pane.list.pills[keys[1]].setFocus()
    window.on_action("accept")                                  # and the shortcut too: nothing marked
    window.on_action("x")
    assert window.keep_pane.status.text() == "Nothing is marked Delete: B goes back, and nothing is deleted."
    window.on_action("accept")                                  # the shortcut marked Delete again
    window.legend.entries["X"].pressed.emit()                   # X, as a tap: only the shortcut goes
    assert wait_for(qapp, lambda: not window.busy)
    assert gears.exists() and shortcuts.in_steam(steam_dir) == {str(halo): "[X360] Halo 3"} and len(closed) == 2
    assert window.games_pane.status.text() == ("Gears of War: deleted Steam shortcut; kept Gears of War (the game's "
                                               "folder). Your saves stay in Xenia's folder.")
    window.games_pane.list.pills[str(gears)].setFocus()
    window.on_action("next")
    assert list(window.keep_pane.list.pills) == [str(games / "Gears of War")]    # out of Steam: no shortcut row
    window.on_action("x")
    assert wait_for(qapp, lambda: not window.busy) and not (games / "Gears of War").exists() and len(closed) == 2
    assert (home / "content" / "4D5307D5").is_dir()
    window.games_pane.list.pills[str(halo)].setFocus()
    window.on_action("next")
    window.on_action("x")                                       # an .iso: the file alone, and its shortcut
    assert wait_for(qapp, lambda: not window.busy) and not halo.exists() and games.is_dir()
    assert shortcuts.in_steam(steam_dir) == {}
    assert list(window.games_pane.list.pills) == [str(loose)]
    window.games_pane.list.pills[str(loose)].setFocus()
    window.on_action("next")
    assert window.games_pane.status.text().startswith("Xbox360 is in Xbox360, one of the app's game folders itself")
    assert loose.exists() and not window.busy
    window.close()


def test_a_console_titles_add_ons_can_be_kept(qapp, tmp_path, monkeypatch):
    r"""A Games on Demand title in the console's folders: the game, its title updates and its add-ons each a row of
    the keep page; the add-ons kept, the rest deleted, and the title ID folder stays for them."""
    home = tmp_path / "emulator"
    fake_install(home)
    games = tmp_path / "me" / "Games" / "Xbox360"
    make_package(games, "Fable II", title_id=0x4D5307E6)
    title = games / "4D5307E6"
    (title / "000B0000").mkdir()
    (title / "000B0000" / "TU1").write_bytes(b"x" * 100)
    (title / "00000002").mkdir()
    (title / "00000002" / "DLC").write_bytes(b"x" * 100)
    window = make(qapp, home, steam_dir=None, user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    window.on_action("accept")
    qapp.processEvents()
    window.on_action("next")
    rows = {key: pill.label.text() for key, pill in window.keep_pane.list.pills.items()}
    assert [text.split("  ·  ")[1] for text in rows.values()] == [
        "the game (00007000)", "Add-ons (00000002)", "Title updates (000B0000)"]
    assert rows[str(title / "00000002")] == "Delete  ·  Add-ons (00000002)  ·  100 B"
    window.keep_pane.list.pills[str(title / "00000002")].setFocus()
    window.on_action("accept")
    window.on_action("x")
    assert wait_for(qapp, lambda: not window.busy)
    assert sorted(p.name for p in title.iterdir()) == ["00000002"] and (title / "00000002" / "DLC").exists()
    assert window.games_pane.status.text().endswith("; kept Add-ons (00000002). Your saves stay in Xenia's folder.")
    window.close()


def test_remove_game_while_xenia_runs_says_so(qapp, tmp_path, monkeypatch):
    home = tmp_path / "emulator"
    fake_install(home)
    halo = make_iso(tmp_path / "me" / "Games" / "Xbox360" / "Halo 3.iso")
    window = make(qapp, home, running=lambda home: True, user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    window.on_action("accept")
    qapp.processEvents()
    window.on_action("next")
    assert window.games_pane.status.text() == "Xenia is open: quit the game first, then remove it."
    assert halo.exists() and window.panes.currentWidget() is window.games_pane
    window.close()


def test_a_game_written_but_not_read_back_is_said_and_logged(qapp, tmp_path, monkeypatch):
    from xenia_manager import library
    home = tmp_path / "emulator"
    fake_install(home)
    make_iso(tmp_path / "me" / "Games" / "Xbox360" / "A.iso")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    monkeypatch.setattr(library, "update_steam", lambda *a, **k: (True, "1 game(s) in Steam.", {}))
    window = make(qapp, home, steam_dir=steam_dir, user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    logged = []
    monkeypatch.setattr(window.log, "error", lambda text: logged.append(text))
    window.refresh_games()
    window.games_card.setFocus()
    window.games_pane.list.first().setFocus()
    qapp.processEvents()
    window.on_action("accept")
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy)
    assert "Read back from Steam's file, 0 of the 1 game(s) are there: not A" in window.games_pane.status.text()
    assert any("reading Steam's file back finds 0" in text for text in logged) and window.in_steam == {}
    window.close()


def test_y_on_your_games_always_says_what_it_did(qapp, tmp_path, monkeypatch):
    make_iso(tmp_path / "me" / "Games" / "Xbox360" / "A.iso")
    window = make(qapp, tmp_path / "emulator", user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    window.games_pane.list.first().setFocus()
    qapp.processEvents()
    window.on_action("accept")
    window.on_action("y")                                          # a game marked, but no Steam on this device
    assert window.games_pane.status.text() == NO_STEAM and not window.busy
    window.close()


def test_the_log_is_read_in_the_app(qapp, tmp_path, monkeypatch):
    """The Log pane shows Xenia's folder and the newest lines; A (or a tap on the pane) shows the whole log in the
    app, the d-pad scrolls it and B goes back (owner, 29-10-2026: Notepad has no button to close it)."""
    home = tmp_path / "emulator"
    fake_install(home)
    log = tmp_path / "app.log"
    log.write_text("".join(f"line {n}\n" for n in range(300)), encoding="utf-8")
    window = make(qapp, home)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.log_path = log
    window.log_card.setFocus()
    qapp.processEvents()
    texts = [label.text() for label in window.log_pane.findChildren(type(window.status))]
    assert "Games" in texts and "Games found" in texts
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
    r"""The BC250 app's Covers… key, as the suite's other apps have it on a page: one key for the suite in
    %APPDATA%\windows-portable-suite\steamgriddb-key, X Paste from the clipboard, A Save, Y Remove key with a second
    press, B back without saving, the page on LB."""
    from bc250_core import covers
    from PyQt6.QtGui import QGuiApplication
    from xenia_manager import library
    key_file = library.key_file()
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


def test_menu_shows_the_panes_information_and_the_icon_is_touch_only(qapp, tmp_path, monkeypatch):
    """Menu (☰ Info in the legend) opens the information of the pane that shows, and closes it again; the icon
    itself is never on the d-pad's way, so A in a pane is always its own action (owner, 29-10-2026)."""
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.xenia_card.setFocus()
    qapp.processEvents()
    assert window.xenia_info not in window.focusables()
    window.on_action("menu")
    assert window.popup is not None and "needs no firmware" in window.popup.text.toPlainText()
    window.on_action("menu")
    assert window.popup is None
    window.games_card.setFocus()
    qapp.processEvents()
    window.on_action("menu")
    assert window.popup is not None and "to play from Steam" in window.popup.text.toPlainText()
    window.on_action("menu")
    assert window.popup is None and window.games_card.hasFocus()
    window.close()


def test_no_path_on_the_screen_shows_the_users_name(qapp):
    """The privacy rule (owner, 29-10-2026): the folder, the game folders and the places to add show the user's
    folders by their variable (%LOCALAPPDATA%, %USERPROFILE%)."""
    user = Path(os.environ.get("USERPROFILE") or Path.home())
    games = user / "AppData" / "Local" / "Temp" / f"wps-private-test-{os.getpid()}"
    (games / "Games").mkdir(parents=True, exist_ok=True)
    try:
        window = make(qapp, Path(os.environ["LOCALAPPDATA"]) / "windows-portable-suite" / "emulator", user_home=games)
        window.refresh_games()
        window.refresh_log()
        shown = [value for _label, value in window.rows()] + [window.games_pane.status.text()] + [
            label.text() for label in window.log_pane.findChildren(type(window.status))]
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
    game = make_iso(tmp_path / "me" / "Games" / "Xbox360" / "Halo 3.iso")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    opened = []

    def with_steam_closed(change):
        change()
        return False
    window = make(qapp, home, steam_dir=steam_dir, steam_closed=with_steam_closed, user_home=tmp_path / "me",
                  open_url=opened.append)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.refresh_games()
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
    assert window.games_pane.status.text() == (f"Starting {title} in Steam… In the game, hold View, LB and RB together "
                                               "to quit.")             # how to quit, on the screen (owner, 30-10-2026)
    assert not hasattr(window, "open_steam") and not hasattr(window, "show_steam")
    window.games_card.setFocus()                                   # X without a game plays nothing
    window.show_pane(window.games_pane)
    window.on_action("x")
    assert len(opened) == 1 and window.games_pane.status.text() == PICK_A_GAME
    window.close()


def test_without_steam_x_starts_the_game_in_xenia(qapp, tmp_path, monkeypatch):
    """A device without Steam (owner, 30-10-2026: a fallback): X starts Xenia with the game full screen, as its
    shortcut would, from Xenia's folder; without Xenia it says to install it first."""
    home = tmp_path / "emulator"
    game = make_iso(tmp_path / "me" / "Games" / "Xbox360" / "Halo 3.iso")
    started, opened = [], []
    window = make(qapp, home, user_home=tmp_path / "me", start=lambda command, cwd=None: started.append((command, cwd)),
                  open_url=opened.append)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.refresh_games()
    window.games_card.setFocus()
    window.games_pane.list.pills[str(game)].setFocus()
    qapp.processEvents()
    title = window.focused_game().title
    assert ("X", "Play") in window.legend.items
    window.on_action("x")
    assert started == [] and window.games_pane.status.text() == (f"Install Xenia first: it starts {title} on a "
                                                                 "device without Steam.")
    fake_install(home)
    window.on_action("x")
    program = emulator.program(home)
    launcher, before = play.launcher(ROOT)                      # the play mode, as the shortcut would start it
    assert started == [([launcher, *before, "--fullscreen=true", str(game)], program.parent)]
    assert opened == [] and window.games_pane.status.text() == (f"Starting {title} in Xenia… In the game, hold View"
                                                                ", LB and RB together to quit.")

    def fails(command, cwd=None):
        raise PermissionError(13, "Access is denied")
    window.start_program = fails
    window.on_action("x")
    assert window.games_pane.status.text() == f"Xenia could not start {title}: Access is denied"
    window.close()


def test_a_shortcut_made_before_the_play_mode_asks_for_update_steam(qapp, tmp_path, monkeypatch):
    """A game whose shortcut still starts Xenia itself (1.0.1's) says (Update Steam), and Y brings it to the play
    mode (owner, 30-10-2026: View, LB and RB held quit every game)."""
    home = tmp_path / "emulator"
    fake_install(home)
    user = tmp_path / "me"
    game = make_iso(user / "Games" / "Xbox360" / "Halo 3.iso")
    steam_dir = tmp_path / "Steam"
    config = steam_dir / "userdata" / "1" / "config"
    config.mkdir(parents=True)
    program = emulator.program(home)
    old = steam.shortcut_entry(f'"{program}"', "[X360] Halo 3", f'"{program.parent}\\"', "",
                               f'--fullscreen=true "{game}"', shortcuts.TAGS)
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": old}}))

    def with_steam_closed(change):
        change()
        return False
    window = make(qapp, home, steam_dir=steam_dir, steam_closed=with_steam_closed, user_home=user)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.refresh_games()
    assert window.games_pane.list.pills[str(game)].label.text().endswith("✓ Steam (Update Steam)")
    window.games_card.setFocus()
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy)
    assert shortcuts.outdated(steam_dir) == set() and len(steam.shortcuts(steam_dir)) == 1
    assert window.games_pane.list.pills[str(game)].label.text().endswith("✓ Steam")
    window.close()


def test_play_runs_the_game_without_a_window(monkeypatch, tmp_path):
    """--play, as a shortcut starts the app: Xenia with the shortcut's arguments from its folder, through core's play
    mode, before any window or the one-window check (the app's window may be open beside it)."""
    from xenia_manager import __main__ as entry
    ran = []
    monkeypatch.setattr(emulator, "emulator_home", lambda: tmp_path / "emulator")
    monkeypatch.setattr(entry.applog, "setup", lambda *a, **k: tmp_path / "log")
    monkeypatch.setattr(entry.play, "run", lambda command, cwd, log: ran.append((command, cwd)) or 3)
    monkeypatch.setattr(entry, "create_app", lambda *a, **k: pytest.fail("no window in the play mode"))
    monkeypatch.setattr(entry.play, "missing", lambda game: False)    # the game is there (test_play_mode.py: not)
    monkeypatch.setattr(sys, "argv", ["Xenia-Manager.exe", "--play", "--fullscreen=true", r"D:\G\Halo 3.iso"])
    assert entry.main() == 3
    program = emulator.program(tmp_path / "emulator")
    assert ran == [([str(program), "--fullscreen=true", r"D:\G\Halo 3.iso"], program.parent)]

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


def test_a_game_renamed_while_the_app_is_open(qapp, tmp_path, monkeypatch):
    """A game in Steam renamed in its folder (owner, 01-11-2026: its Steam shortcut then started Xenia with a file no
    longer there): LT Refresh finds it again under its new name with its mark (an .iso: by its size), and Update Steam
    puts it in under that name, the old shortcut out. Taken off, the mark stays off."""
    home = tmp_path / "emulator"
    fake_install(home)
    user = tmp_path / "me"
    old = make_iso(user / "Games" / "Xbox360" / "Halo 3 [NTSC].iso")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    window = make(qapp, home, steam_dir=steam_dir, steam_closed=lambda change: change() or False, user_home=user)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    qapp.processEvents()
    window.mark_game(str(old))
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy)
    assert shortcuts.in_steam(steam_dir) == {str(old): "[X360] Halo 3 [NTSC]"}
    new = old.rename(old.with_name("Halo 3.iso"))
    window.on_action("lt")
    assert list(window.games_pane.list.pills) == [str(new)] and str(new) in window.marked
    assert window.moved == {str(new): str(old)}
    assert window.games_pane.status.text() == ("The game folders were read again: 1 game(s). Found again under a new "
                                               "name or in another folder, with its Steam mark: Halo 3. The Y button "
                                               "updates Steam.")
    assert window.games_pane.list.pills[str(new)].label.text().endswith("✓ Steam (Update Steam)")
    window.mark_game(str(new))                                     # taken off: it stays off on the next refresh
    window.on_action("lt")
    assert str(new) not in window.marked
    window.mark_game(str(new))
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy)
    assert shortcuts.in_steam(steam_dir) == {str(new): "[X360] Halo 3"}
    window.on_action("lt")
    assert window.moved == {} and str(new) in window.marked
    window.close()
