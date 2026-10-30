# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py): it opens on the portable window with the header's battery, date and time, fits the
handheld's screen; every action is a button in the row at the bottom, A too, and no pill is left (owner,
29-10-2026); B goes back and View exits; PCSX2 installed on A (off the window's thread, the megabytes counted, View
asking first meanwhile, its settings prepared after), reinstalled after PCSX2 replaced itself, removed with RB
pressed twice; the BIOS chosen in the app's browser (X) and removed (LB); the Settings pane's rows, in tabs, step
through their values, never while PCSX2 runs; Your games marked for Steam with A (never played from the app), the
folder browser, the memory cards, the log read in the app, the SteamGridDB key; the version and the icons are where
the checks expect them."""

from __future__ import annotations

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
from bc250_core.portable import BACK, EXIT, VIEW
from bc250_core.portable import INFO as MENU_INFO
from conftest import make_disc
from pcsx2_manager import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, emulator, shortcuts
from pcsx2_manager.main_window import (BIOS_NEEDS_PCSX2, NO_BIOS, NO_BIOS_TO_REMOVE, NO_CARD_TO_COPY, NO_STEAM,
                                      NOT_THE_GAMES, NOTHING_TO_CHANGE, OPEN_A_FOLDER, PICK_A_GAME, MainWindow)


class FakePad:
    def events(self):
        return []

    def close(self):
        pass

    def names(self):
        return []


def fake_install(home, progress=lambda got: None, say=lambda text: None, gate=None):
    """What emulator.install() leaves behind, without a download: the program, the marker and the record."""
    progress(12_000_000)
    if gate is not None:
        gate.wait(10)
    say("Unpacking…")
    home.mkdir(parents=True, exist_ok=True)
    (home / emulator.EXE).write_bytes(b"pcsx2")
    (home / emulator.MARKER).write_text("")
    (home / emulator.RECORD).write_text(
        f'{{"version": "{emulator.VERSION}", "exe_size": 5, "files": ["{emulator.EXE}"]}}', encoding="utf-8")
    return emulator.VERSION


def with_bios(home: Path) -> None:
    (home / "bios").mkdir(parents=True, exist_ok=True)
    (home / "bios" / "SCPH-70012.bin").write_bytes(b"\0" * 64)


def wait_for(qapp, predicate, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not predicate():
        qapp.processEvents()
        time.sleep(0.01)
    return predicate()


def make(qapp, home=None, install=fake_install, running=lambda home: False, **more):
    more.setdefault("steam_dir", None)                  # never the real Steam
    more.setdefault("start", lambda command, cwd=None: None)   # never a real PCSX2
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
    assert re.fullmatch(r"\w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d  \|  82%", window.header.status.text())   # battery last
    assert window.legend.items == [("A", "Install"), ("X", "Choose BIOS"), MENU_INFO, EXIT]
    assert no_pills(window)
    window.close()


def test_the_window_fits_the_handhelds_screen(qapp):
    window = make(qapp)
    assert window.minimumSizeHint().height() <= 720 and window.height() == 720
    window.close()


def test_b_goes_back_and_view_exits(qapp, monkeypatch):
    """The suite's buttons (owner, 29-10-2026: "Close" on B was not clear): B goes back, from a pane to its card,
    and does nothing on a card; View (Exit app) closes the app; Menu shows the pane's information (the BIOS)."""
    window = make(qapp)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("back")                                    # on the PCSX2 card: nothing
    assert closed == [] and window.pcsx2_card.hasFocus()
    window.on_action("menu")
    assert window.popup is not None and "biosdrain" in window.popup.text.toPlainText()
    window.on_action("back")                                    # B closes the information first
    assert window.popup is None and closed == []
    window.settings_card.setFocus()
    window.on_action("accept")
    qapp.processEvents()
    assert BACK in window.legend.items
    window.on_action("back")
    qapp.processEvents()
    assert window.settings_card.hasFocus() and closed == []
    window.on_action("view")
    assert closed == [True]


def test_version_is_the_single_source():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__ == INFO.version


def test_icons_are_beside_the_package():
    assert LOGO_PATH.is_file() and LOGO_PATH.name == f"{APP_ID}.webp"
    assert (ROOT / "images" / f"{APP_ID}-128.png").is_file()
    assert re.fullmatch(r"[A-Za-z0-9-]+", EXE_NAME)


def test_nothing_is_installed_before_a(qapp, tmp_path):
    calls = []
    window = make(qapp, tmp_path / "emulator", install=lambda *a, **k: calls.append(True))
    assert calls == [] and window.pcsx2_card.hasFocus()
    assert dict(window.rows())["Installed"] == "not installed"
    window.act("next")                                          # RB Remove PCSX2: says why
    assert "nothing to remove" in window.status.text() and calls == []
    window.close()


def test_a_installs_off_the_windows_thread_and_counts_the_megabytes(qapp, tmp_path, monkeypatch):
    gate = threading.Event()
    window = make(qapp, tmp_path / "emulator", install=lambda home, **k: fake_install(home, gate=gate, **k))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("accept")
    assert window.busy
    window.refresh()
    assert window.status.text() == f"Downloading PCSX2 {emulator.VERSION}… 12 of 26 MB"
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.on_action("view")                                    # Exit asks first while it downloads
    assert closed == [] and window.legend.items == [(VIEW, "Press again to exit")]
    assert window.status.text() == "Press View again to exit: the download stops."
    gate.set()
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == f"PCSX2 {emulator.VERSION} is installed."
    assert window.legend.items == [("X", "Choose BIOS"), ("LB", "Remove BIOS"), ("RB", "Remove PCSX2"), MENU_INFO,
                                   EXIT]
    window.on_action("view")
    assert closed == [True]                                     # nothing runs: View exits at once


def test_a_failed_install_says_why(qapp, tmp_path):
    def failing(home, **kwargs):
        raise emulator.EmulatorError("the release has no pcsx2-qt.exe")
    window = make(qapp, tmp_path / "emulator", install=failing)
    window.act("accept")
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == "PCSX2 could not be installed: the release has no pcsx2-qt.exe"
    assert window.legend.items[0] == ("A", "Install")
    window.close()


def test_reinstall_and_remove_with_rb_pressed_twice(qapp, tmp_path):
    home = tmp_path / "emulator"
    fake_install(home)
    (home / "memcards").mkdir()
    (home / "memcards" / "Mcd001.ps2").write_bytes(b"x")
    window = make(qapp, home)
    assert ("Y", "Reinstall") not in window.legend.items
    emulator.program(home).write_bytes(b"another build")         # PCSX2's own updater
    window.refresh()
    assert window.legend.items[:3] == [("X", "Choose BIOS"), ("Y", "Reinstall"), ("LB", "Remove BIOS")]
    assert "replaced itself" in window.status.text()
    window.act("y")
    assert wait_for(qapp, lambda: not window.busy) and not emulator.replaced(home)
    window.legend.entries["RB"].pressed.emit()                  # a tap on RB Remove PCSX2
    assert ("RB", "Press again") in window.legend.items and emulator.installed(home)
    assert window.status.text().startswith("Press the RB button again")
    window._confirm_over()                                      # five seconds without a second press
    assert ("RB", "Remove PCSX2") in window.legend.items
    window.act("next")
    window.act("next")
    assert emulator.installed(home) == "" and (home / "memcards" / "Mcd001.ps2").is_file()
    assert "stay" in window.status.text() and window.legend.items[0] == ("A", "Install")
    window.close()


def test_the_cards_show_their_panes_and_none_holds_a_pill(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert window.panes.currentWidget() is window.pane
    window.on_action("down")
    assert window.games_card.hasFocus() and window.panes.currentWidget() is window.games_pane
    window.on_action("down")
    assert window.settings_card.hasFocus() and window.panes.currentWidget() is window.settings_pane
    assert window.settings_pane.status.text() == "Install PCSX2 first: the settings are in its folder."
    window.settings_pane.status.setText("")
    window.settings_pane.pills["renderer"].click()                                 # never grayed out: says why
    assert window.settings_pane.status.text() == "Install PCSX2 first: the settings are in its folder."
    for card in (window.pcsx2_card, window.games_card, window.settings_card, window.cards_card, window.log_card):
        card.setFocus()
        qapp.processEvents()
        assert no_pills(window)
    window.close()


def test_an_install_prepares_pcsx2s_settings_before_its_first_start(qapp, tmp_path):
    home = tmp_path / "emulator"
    window = make(qapp, home)
    window.act("accept")
    assert wait_for(qapp, lambda: not window.busy)
    ini = (home / "inis" / "PCSX2.ini").read_text(encoding="utf-8")
    assert "SetupWizardIncomplete = false" in ini and "CheckAtStartup = false" in ini
    assert "Cross = SDL-0/FaceSouth" in ini and "StartBigPictureMode = false" in ini
    window.close()


def test_the_settings_step_and_are_written_at_once(qapp, tmp_path, monkeypatch):
    home = tmp_path / "emulator"
    fake_install(home)
    is_running = [False]
    window = make(qapp, home, running=lambda h: is_running[0])
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    pills = window.settings_pane.pills
    assert pills["renderer"].label.text() == "Renderer: Automatic"
    assert "bigpicture" not in pills and pills["quit"].label.text().endswith(": On")
    window.settings_card.setFocus()
    window.on_action("accept")                                                     # A on the card: the first row
    assert pills["renderer"].hasFocus()
    window.on_action("accept")
    assert pills["renderer"].label.text() == "Renderer: Direct3D 12"
    assert "Renderer = 15" in (home / "inis" / "PCSX2.ini").read_text(encoding="utf-8")
    pills["aspect"].click()                                                        # the screen's shape (owner)
    assert pills["aspect"].label.text() == "Aspect ratio: 4:3"
    is_running[0] = True                                                           # PCSX2 is open
    window.settings_pane.tabs.select("osd")
    pills["fps"].click()
    assert window.settings_pane.status.text().startswith("PCSX2 is open") and pills["fps"].label.text() == "Show FPS: Off"
    window.close()


def test_the_settings_are_in_tabs(qapp, tmp_path, monkeypatch):
    """More settings than one page holds (owner, 29-10-2026: "we can use tabs in the settings page to add more"):
    LB and RB step through Picture, Game, Controller and On screen; the focus follows to the tab's first row; the
    information tells the tab's settings; every tab's rows fit the pane."""
    from pcsx2_manager.pcsx2_settings import TABS
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    pane = window.settings_pane
    assert [key for key, _, _ in TABS] == ["picture", "game", "controller", "osd"] == pane.tabs.keys
    assert pane.tabs.current == "picture" and pane.pills["aspect"].isVisibleTo(pane)
    assert not pane.pills["fps"].isVisibleTo(pane) and "Renderer:" in pane.info.info
    assert all(len(group) <= 7 for _, _, group in TABS) and len(pane.pills) >= 20
    window.settings_card.setFocus()
    window.on_action("accept")
    assert pane.pills["renderer"].hasFocus()
    window.on_action("next")                                                       # RB: the next tab
    assert pane.tabs.current == "game" and pane.pills["fastboot"].hasFocus() and "Fast boot:" in pane.info.info
    window.on_action("previous")
    window.on_action("previous")                                                   # LB twice: round to the last
    assert pane.tabs.current == "osd" and pane.pills["fps"].hasFocus() and pane.pills["fps"].isVisibleTo(pane)
    assert pane.minimumSizeHint().height() <= window.panes.height()
    window.close()


def test_a_long_folder_wraps_and_the_window_stays_on_the_screen(qapp, tmp_path):
    deep = tmp_path / ("a-rather-long-folder-name" * 3) / "windows-portable-suite" / "windows-portable-pcsx2" / "emulator"
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
    Y Update Steam writes the marks; without a BIOS Update Steam says why."""
    home = tmp_path / "emulator"
    fake_install(home)
    (home / "resources").mkdir()
    (home / "resources" / "GameIndex.yaml").write_text('SLUS-21553:\n  name: "Lumines Plus"\n', encoding="utf-8")
    user = tmp_path / "me"
    games = user / "Games"
    make_disc(games / "PS2" / "SLUS_215.53.Lumines.iso", "SLUS_215.53")
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
    assert window.games_pane.list.pills == {} and "the LB button" in window.games_pane.status.text()
    window.on_action("previous")                                   # LB Folders: the usual places, and Browse
    pills = window.games_pane.list.pills
    assert list(pills) == [f"add:{games}", f"add:{user / 'Downloads'}", "browse"]
    pills[f"add:{games}"].click()
    assert "1 game(s) in it" in window.games_pane.status.text()
    window.on_action("back")                                       # B on the folders: the games
    lumines = str(games / "PS2" / "SLUS_215.53.Lumines.iso")
    pills = window.games_pane.list.pills
    assert pills[lumines].label.text() == "Lumines Plus  ·  SLUS-21553"
    pills[lumines].setFocus()
    qapp.processEvents()
    window.on_action("accept")                                     # A: the Steam mark
    assert "✓ Steam (Update Steam)" in window.games_pane.list.pills[lumines].label.text()
    window.on_action("y")                                          # no BIOS: PCSX2 would stop at its error window
    assert window.games_pane.status.text() == NO_BIOS and closed == []
    with_bios(home)
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy)
    assert closed == [True] and shortcuts.in_steam(steam_dir) == {lumines: "[PS2] Lumines Plus"}
    assert "1 game(s) in Steam" in window.games_pane.status.text()
    assert window.games_pane.list.pills[lumines].label.text().endswith("✓ Steam")
    window.close()


def test_the_folder_browser_goes_by_the_controller(qapp, tmp_path, monkeypatch):
    """Windows' own folder window cannot be used with the controller (owner, 29-10-2026): the app's browser lists the
    places and the folders; A opens one, X adds the open folder, B goes up and, from the places, back."""
    user = tmp_path / "me"
    target = user / "Games" / "PS2"
    make_disc(target / "A.iso", "SLUS_123.45")
    window = make(qapp, tmp_path / "emulator", user_home=user)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    window.on_action("previous")                                   # LB Folders
    window.games_pane.list.pills["browse"].click()
    assert window.panes.currentWidget() is window.browse_pane and window.browse_pane.heading.text() == "Choose a folder"
    assert window.legend.items == [("A", "Open"), ("X", "Add this folder"), MENU_INFO, BACK, EXIT]
    window.on_action("x")                                          # nothing open yet: says how
    assert window.browse_pane.status.text() == OPEN_A_FOLDER
    window.browse_pane.list.pills[f"dir:{user / 'Games'}"].click()
    window.browse_pane.list.pills[f"dir:{target}"].click()
    window.on_action("x")                                          # X: this folder
    assert window.panes.currentWidget() is window.games_pane and f"folder:{target}" in window.games_pane.list.pills
    window.games_pane.list.pills["browse"].click()                 # opens where the folder was added (owner)
    assert window.browser.path == target
    window.on_action("back")                                       # B: up a level, to the place
    assert window.browser.path == user / "Games"
    window.on_action("back")                                       # the places
    window.on_action("back")                                       # B at the places: back to the folders
    assert window.panes.currentWidget() is window.games_pane and window.browser is None
    window.close()


def test_a_game_written_but_not_read_back_is_said_and_logged(qapp, tmp_path, monkeypatch):
    """"It still says 0 games in Steam" (owner, 29-10-2026): the games are read back from Steam's file right after the
    write, and one that is not found then is named on the status line and in the log."""
    from pcsx2_manager import library
    home = tmp_path / "emulator"
    fake_install(home)
    with_bios(home)
    games = tmp_path / "games"
    make_disc(games / "A.iso", "SLUS_123.45")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    monkeypatch.setattr(library, "update_steam", lambda *a, **k: (True, "1 game(s) in Steam.", {}))
    window = make(qapp, home, steam_dir=steam_dir, user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    logged = []
    monkeypatch.setattr(window.log, "error", lambda text: logged.append(text))
    window.add_folder(games)
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
    make_disc(folder / "A.iso", "SLUS_123.45")
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


def test_memory_cards_new_copy_and_saves(qapp, tmp_path, cards):
    home = tmp_path / "emulator"
    fake_install(home)
    (home / "inis").mkdir()
    (home / "inis" / "PCSX2.ini").write_text(f"[Folders]\nMemoryCards = {cards}\n", encoding="utf-8")
    window = make(qapp, home, any_running=lambda: False)
    window.cards_card.setFocus()
    qapp.processEvents()
    pills = window.cards_pane.list.pills
    assert list(pills) == ["mc01.ps2", "mc02.ps2"] and "2 card(s)" in window.cards_pane.summary.text()
    assert all(pill.isVisible() for pill in pills.values())      # made before the pane showed, shown with it
    assert window.legend.items[:3] == [("A", "Saves"), ("X", "New card"), ("Y", "Copy card")]
    pills["mc01.ps2"].setFocus()                                   # the card Copy card copies
    pills["mc01.ps2"].click()                                      # A: its saves
    saves = window.cards_pane.list.pills
    assert list(saves)[0] == "‹" and len(saves) > 1 and "mc01.ps2:" in window.cards_pane.summary.text()
    assert BACK in window.legend.items
    window.act("back")                                             # B: back to the cards, as ‹ The cards does
    assert window.card_view == "" and list(window.cards_pane.list.pills) == ["mc01.ps2", "mc02.ps2"]
    window.cards_pane.list.pills["mc01.ps2"].click()
    window.cards_pane.list.pills["‹"].click()
    window.y_action()                                              # Y Copy card
    assert (cards / "mc01 copy.ps2").is_file() and "is copied to mc01 copy.ps2" in window.cards_pane.status.text()
    window.legend.entries["X"].pressed.emit()                      # a tap on X New card
    assert (cards / "Mcd001.ps2").is_file() and "Mcd001.ps2" in window.cards_pane.list.pills
    window.close()


def test_the_log_is_read_in_the_app(qapp, tmp_path, monkeypatch):
    """The Log pane shows PCSX2's last run and the newest lines; A (or a tap on the pane) shows the whole log in the
    app, the d-pad scrolls it and B goes back (owner, 29-10-2026: Notepad has no button to close it)."""
    home = tmp_path / "emulator"
    fake_install(home)
    (home / "logs").mkdir()
    (home / "logs" / "emulog.txt").write_text("[    0.07] PCSX2 v2.8.2\n[    0.50]   Serial: SLUS-21553\n"
                                             "[  346.00] Add 346 seconds play time to SLUS-21553 -> now 346\n")
    log = tmp_path / "app.log"
    log.write_text("first line\n" + "".join(f"line {n}\n" for n in range(300)) + "Played Lumines Plus (SLUS-21553).\n",
                   encoding="utf-8")
    window = make(qapp, home)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.log_path = log
    window.log_card.setFocus()
    qapp.processEvents()
    grid = window.log_pane.grid
    cells = [grid.itemAt(i).widget().text() for i in range(grid.count())]
    rows = dict(zip(cells[0::2], cells[1::2]))
    assert rows["Played"] == "5 min 46 s" and rows["PCSX2's last run"].endswith("SLUS-21553")
    assert "Played Lumines Plus" in window.log_pane.lines.toPlainText()
    summary = window.log_pane.lines.verticalScrollBar()                 # the newest lines in sight, never cut off
    assert summary.value() == summary.maximum() and window.log_pane.lines not in window.focusables()
    assert window.legend.items[0] == ("A", "View log")
    window.on_action("accept")                                     # A: the whole log, here
    view = window.log_pane.view
    assert window.log_pane.viewing and view.hasFocus() and "Played Lumines Plus" in view.toPlainText()
    bottom = view.verticalScrollBar().value()
    window.on_action("up")                                         # the d-pad scrolls it
    assert view.verticalScrollBar().value() < bottom
    window.on_action("back")
    assert not window.log_pane.viewing and window.log_card.hasFocus()
    window.log_pane.tapped.emit()                                  # a tap on the pane: the whole log too
    assert window.log_pane.viewing
    window.close()


def test_the_bios_is_chosen_in_the_browser_and_removed(qapp, tmp_path, monkeypatch):
    r"""The BC250 app's BIOS Install and BIOS Uninstall (owner, 29-10-2026: "where do I set the BIOS"; Windows' file
    window cannot be used with the controller): X Choose BIOS opens the browser in Downloads showing the dumps, A on
    one copies it with its files into bios\ and names it in PCSX2.ini; LB Remove BIOS with a second press; while
    PCSX2 runs or is not installed, both say why."""
    home = tmp_path / "emulator"
    user = tmp_path / "me"
    downloads = user / "Downloads"
    downloads.mkdir(parents=True)
    dump = downloads / "SCPH-70012.bin"
    dump.write_bytes(b"\0" * (4 << 20))
    (downloads / "SCPH-70012.nvm").write_bytes(b"\0" * 1024)
    (downloads / "notes.txt").write_text("x")
    is_running = [False]
    window = make(qapp, home, running=lambda h: is_running[0], user_home=user)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert dict(window.rows())["BIOS"] == "install PCSX2 first"
    for button in ("x", "previous"):                                             # not installed
        window.message = ""
        window.act(button)
        assert window.status.text() == BIOS_NEEDS_PCSX2
    assert not (home / "bios").exists()
    fake_install(home)
    window.refresh()
    window.act("previous")                                                       # LB, no BIOS yet
    assert window.status.text() == NO_BIOS_TO_REMOVE
    assert dict(window.rows())["BIOS"].startswith("No BIOS yet") and "No BIOS yet" in window.pcsx2_card.text.text()
    window.legend.entries["X"].pressed.emit()                                    # a tap on X Choose BIOS
    assert window.panes.currentWidget() is window.browse_pane
    assert window.browse_pane.heading.text() == "Choose your BIOS dump" and window.browser.path == downloads
    assert [text for _, text in window.browser.rows()] == ["\u2039 The places", "SCPH-70012.bin"]
    assert ("X", "Add this folder") not in window.legend.items
    window.browse_pane.list.pills[f"file:{dump}"].setFocus()
    qapp.processEvents()
    window.on_action("accept")                                                   # A on the dump: taken
    assert window.panes.currentWidget() is window.pane
    assert sorted(p.name for p in (home / "bios").iterdir()) == ["SCPH-70012.bin", "SCPH-70012.nvm"]
    assert "BIOS = SCPH-70012.bin" in (home / "inis" / "PCSX2.ini").read_text(encoding="utf-8")
    assert window.settings.value("browse/bios") == str(downloads)               # the next browser opens there
    assert window.status.text() == "PCSX2 uses SCPH-70012.bin now." and "No BIOS" not in window.pcsx2_card.text.text()
    is_running[0] = True                                         # PCSX2 writes its settings when it closes
    for button in ("x", "previous"):
        window.message = ""
        window.act(button)
        assert window.status.text().startswith("PCSX2 is open") and (home / "bios" / dump.name).is_file()
    is_running[0] = False
    window.message = ""
    window.act("previous")
    assert ("LB", "Press again") in window.legend.items and (home / "bios" / dump.name).is_file()
    window._confirm_over()                                       # five seconds without a second press
    assert ("LB", "Remove BIOS") in window.legend.items
    window.act("previous")
    window.act("previous")
    assert list((home / "bios").iterdir()) == [] and dump.is_file()
    assert window.status.text() == "SCPH-70012.bin, SCPH-70012.nvm removed from PCSX2's bios folder. PCSX2 has no BIOS now."
    assert "biosdrain" in window.bios_info.info and "the A button on the .bin chooses it" in window.bios_info.info
    window.close()


def test_the_launch_line_keeps_pcsx2s_window_away(tmp_path):
    # -nogui -fullscreen -batch (owner, 29-10-2026: PCSX2 is never seen), as Steam's shortcuts start a game
    from pcsx2_manager.games import Game
    assert shortcuts.launch_options(Game(tmp_path / "g.iso", "G")) == f'-nogui -fullscreen -batch -- "{tmp_path / "g.iso"}"'


def test_the_steamgriddb_key_is_pasted_saved_and_removed(qapp, tmp_path, monkeypatch):
    r"""The BC250 app's Steam artwork… key (owner, 29-10-2026: "exactly as BC250 has it"), as a page: one key for the
    suite in %APPDATA%\windows-portable-suite\steamgriddb-key, X Paste from the clipboard, A Save, Y Remove key with a
    second press, B back without saving, the page on RB."""
    from bc250_core import covers
    from PyQt6.QtGui import QGuiApplication
    from pcsx2_manager import library
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
    assert pane.field.echoMode() == pane.field.EchoMode.Password
    window.on_action("y")                                       # no key: it says so
    assert pane.status.text().startswith("There is no key to remove")
    QGuiApplication.clipboard().setText("  0123456789abcdef0123456789abcdef \n")
    window.on_action("x")                                       # X on the key page: Paste
    assert pane.field.text() == "0123456789abcdef0123456789abcdef"
    window.on_action("back")                                    # B: back, nothing saved
    assert window.panes.currentWidget() is window.games_pane and not key_file.exists()
    window.legend.entries["RB"].pressed.emit()                  # a tap on RB Steam artwork
    window.key_pane.field.setText("0123456789abcdef0123456789abcdef")
    window.legend.entries["A"].pressed.emit()                   # a tap on A Save
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
    make_disc(folder / "A.iso", "SLUS_123.45")
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


def test_copy_card_without_a_card_says_why(qapp, tmp_path, cards):
    """Copy card is never grayed out (owner, 29-10-2026): before the focus was on a card, it says what it needs."""
    home = tmp_path / "emulator"
    fake_install(home)
    (home / "inis").mkdir()
    (home / "inis" / "PCSX2.ini").write_text(f"[Folders]\nMemoryCards = {cards}\n", encoding="utf-8")
    window = make(qapp, home, any_running=lambda: False)
    window.cards_card.setFocus()
    qapp.processEvents()
    window.y_action()                                              # Y Copy card
    assert window.cards_pane.status.text() == NO_CARD_TO_COPY and sorted(p.name for p in cards.iterdir()) == [
        "mc01.ps2", "mc02.ps2"]
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


def test_a_game_is_played_through_steam(qapp, tmp_path, monkeypatch):
    """X on a game in Steam starts it through Steam, by its shortcut's appid; a game not in Steam yet says how (owner,
    29-10-2026). Steam's library is the portal's (owner, 30-10-2026: no Open Steam row)."""
    home = tmp_path / "emulator"
    fake_install(home)
    with_bios(home)
    game = make_disc(tmp_path / "me" / "Games" / "A.iso", "SLUS_123.45")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    opened = []

    def with_steam_closed(change):
        change()
        return False
    window = make(qapp, home, steam_dir=steam_dir, steam_closed=with_steam_closed, user_home=tmp_path / "me",
                  open_url=opened.append)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.add_folder(tmp_path / "me" / "Games")
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
    assert window.games_pane.status.text() == f"Starting {title} in Steam… {play.QUIT_HINT}"   # how to quit, shown
    assert not hasattr(window, "open_steam")
    for dump in (home / "bios").iterdir():                         # the BIOS gone: the manager says so first
        dump.unlink()
    window.on_action("x")
    assert len(opened) == 1 and window.games_pane.status.text() == NO_BIOS
    window.toggle_folders()                                        # X on the folders plays nothing
    window.on_action("x")
    assert len(opened) == 1 and window.games_pane.status.text() == PICK_A_GAME
    window.close()


def test_without_steam_x_starts_the_game_in_pcsx2(qapp, tmp_path, monkeypatch):
    """A device without Steam (owner, 30-10-2026: a fallback): X starts PCSX2 with the game full screen, as its
    shortcut would, from PCSX2's folder; without PCSX2 it says to install it first, without a BIOS to choose one
    (owner, 30-10-2026: the manager checks)."""
    home = tmp_path / "emulator"
    game = make_disc(tmp_path / "me" / "Games" / "A.iso", "SLUS_123.45")
    started, opened = [], []
    window = make(qapp, home, user_home=tmp_path / "me", start=lambda command, cwd=None: started.append((command, cwd)),
                  open_url=opened.append)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.add_folder(tmp_path / "me" / "Games")
    window.games_card.setFocus()
    window.games_pane.list.pills[str(game)].setFocus()
    qapp.processEvents()
    title = window.focused_game().title
    assert ("X", "Play") in window.legend.items
    window.on_action("x")
    assert started == [] and window.games_pane.status.text() == (f"Install PCSX2 first: it starts {title} on a "
                                                                 "device without Steam.")
    fake_install(home)
    window.on_action("x")
    assert started == [] and window.games_pane.status.text() == NO_BIOS
    with_bios(home)
    window.on_action("x")
    program = emulator.program(home)
    launcher, before = play.launcher(ROOT)                      # the play mode, as the shortcut would start it
    assert started == [([launcher, *before, *emulator.GAME_ARGS, "--", str(game)], program.parent)]
    assert opened == [] and window.games_pane.status.text() == (f"Starting {title} in PCSX2… In the game, hold View"
                                                                ", LB and RB together to quit.")

    def fails(command, cwd=None):
        raise PermissionError(13, "Access is denied")
    window.start_program = fails
    window.on_action("x")
    assert window.games_pane.status.text() == f"PCSX2 could not start {title}: Access is denied"
    window.close()


def test_a_shortcut_made_before_the_play_mode_asks_for_update_steam(qapp, tmp_path, monkeypatch):
    """A game whose shortcut still starts PCSX2 itself (3.0.1's) says (Update Steam), and Y brings it to the play
    mode (owner, 30-10-2026: View, LB and RB held quit every game)."""
    home = tmp_path / "emulator"
    fake_install(home)
    with_bios(home)
    game = make_disc(tmp_path / "me" / "Games" / "A.iso", "SLUS_123.45")
    steam_dir = tmp_path / "Steam"
    config = steam_dir / "userdata" / "1" / "config"
    config.mkdir(parents=True)

    def with_steam_closed(change):
        change()
        return False
    window = make(qapp, home, steam_dir=steam_dir, steam_closed=with_steam_closed, user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.add_folder(tmp_path / "me" / "Games")
    program = emulator.program(home)
    name = shortcuts.names([g for g in window.games if str(g.file) == str(game)])
    old = steam.shortcut_entry(f'"{program}"', next(iter(name.values())), f'"{program.parent}\\"', "",
                               f'{" ".join(emulator.GAME_ARGS)} -- "{game}"', shortcuts.TAGS)
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": old}}))
    window.refresh_games()
    assert window.games_pane.list.pills[str(game)].label.text().endswith("✓ Steam (Update Steam)")
    window.games_card.setFocus()
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy)
    assert shortcuts.outdated(steam_dir) == set() and len(steam.shortcuts(steam_dir)) == 1
    assert window.games_pane.list.pills[str(game)].label.text().endswith("✓ Steam")
    window.close()


def test_play_runs_the_game_without_a_window(monkeypatch, tmp_path):
    """--play, as a shortcut starts the app: PCSX2 with the shortcut's arguments from its folder, through core's play
    mode, before any window or the one-window check (the app's window may be open beside it)."""
    from pcsx2_manager import __main__ as entry
    ran = []
    monkeypatch.setattr(emulator, "emulator_home", lambda: tmp_path / "emulator")
    monkeypatch.setattr(entry.applog, "setup", lambda *a, **k: tmp_path / "log")
    monkeypatch.setattr(entry.play, "run", lambda command, cwd, log: ran.append((command, cwd)) or 3)
    monkeypatch.setattr(entry, "create_app", lambda *a, **k: pytest.fail("no window in the play mode"))
    monkeypatch.setattr(sys, "argv", ["PCSX2-Manager.exe", "--play", "-nogui", "-fullscreen", "--", r"D:\A.iso"])
    assert entry.main() == 3
    program = emulator.program(tmp_path / "emulator")
    assert ran == [([str(program), "-nogui", "-fullscreen", "--", r"D:\A.iso"], program.parent)]

    def fails(command, cwd, log):
        raise FileNotFoundError(2, "The system cannot find the file specified")
    monkeypatch.setattr(entry.play, "run", fails)
    assert entry.main() == 1
