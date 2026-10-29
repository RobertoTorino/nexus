# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py): it opens on the portable window with the header's battery, date and time, fits the
handheld's screen, and B closes it; PCSX2 installed on A (off the window's thread, the megabytes counted, B asking
first meanwhile, its settings prepared after), opened, reinstalled after PCSX2 replaced itself, and removed with a
second press; the Settings pane's rows, in tabs, step through their values, never while PCSX2 runs; the actions
with a controller button in the legend (X, Y, LB, RB), a tap on an entry doing the same; the version and the icons
are where the checks expect them."""

from __future__ import annotations

import re
import tempfile
import threading
import time

from bc250_core import portable
from bc250_core.gamepad import Gamepad
from pathlib import Path

from PyQt6.QtCore import QSettings

from conftest import make_disc
from pcsx2_manager import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, emulator, shortcuts
from pcsx2_manager.main_window import (BIOS_NEEDS_PCSX2, NO_BIOS_TO_REMOVE, NO_CARD_TO_COPY, NO_STEAM, NOT_THE_GAMES,
                                      NOTHING_TO_CHANGE, MainWindow)


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


def wait_for(qapp, predicate, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not predicate():
        qapp.processEvents()
        time.sleep(0.01)
    return predicate()


def make(qapp, home=None, install=fake_install, running=lambda home: False, **more):
    more.setdefault("steam_dir", None)                  # never the real Steam
    more.setdefault("drives", lambda: [])
    more.setdefault("settings", QSettings(str(Path(tempfile.mkdtemp()) / "app.ini"),
                                          QSettings.Format.IniFormat))   # never Windows' registry
    window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False), home=home,
                        install=install, running=running, **more)
    portable.scale((1280, 720))
    window.resize(1280, 720)
    window.show()
    window.activateWindow()                     # the focus moves in the active window only
    qapp.processEvents()
    window.start()
    return window


def test_the_window_opens_with_the_suites_header(qapp):
    window = make(qapp)
    assert window.header.title.text() == APP_NAME and window.header.version.text() == __version__
    assert re.fullmatch(r"82%  \|  \w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d", window.header.status.text())
    assert window.legend.items == [("X", "Choose BIOS"), ("B", "Close")]
    window.close()


def test_the_window_fits_the_handhelds_screen(qapp):
    window = make(qapp)
    assert window.minimumSizeHint().height() <= 720 and window.height() == 720
    window.close()


def test_b_closes_the_app(qapp, monkeypatch):
    window = make(qapp)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("back")
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
    assert calls == [] and window.main.label.text() == "Install" and window.pcsx2_card.hasFocus()
    assert not window.remove_pill.isVisible() and ("Y", "Reinstall") not in window.legend.items
    assert dict(window.rows())["Installed"] == "not installed"
    window.close()


def test_a_installs_off_the_windows_thread_and_counts_the_megabytes(qapp, tmp_path, monkeypatch):
    gate = threading.Event()
    window = make(qapp, tmp_path / "emulator", install=lambda home, **k: fake_install(home, gate=gate, **k))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("accept")
    assert window.busy and not window.main.isVisible()
    window.refresh()
    assert window.status.text() == f"Downloading PCSX2 {emulator.VERSION}… 12 of 26 MB"
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.on_action("back")                                    # B asks first while it downloads
    assert closed == [] and window.legend.items == [("B", "Press again to close")]
    assert window.status.text() == "Press B again to close: the download stops."
    gate.set()
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == f"PCSX2 {emulator.VERSION} is installed."
    assert window.legend.items == [("X", "Choose BIOS"), ("B", "Close")]
    assert not window.main.isVisible() and window.remove_pill.isVisible()
    window.on_action("back")
    assert closed == [True]                                     # nothing runs: B closes at once


def test_a_failed_install_says_why(qapp, tmp_path):
    def failing(home, **kwargs):
        raise emulator.EmulatorError("the release has no pcsx2-qt.exe")
    window = make(qapp, tmp_path / "emulator", install=failing)
    window.main.click()
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == "PCSX2 could not be installed: the release has no pcsx2-qt.exe"
    assert window.main.label.text() == "Install"
    window.close()


def test_open_reinstall_and_remove(qapp, tmp_path, monkeypatch):
    home = tmp_path / "emulator"
    fake_install(home)
    (home / "memcards").mkdir()
    (home / "memcards" / "Mcd001.ps2").write_bytes(b"x")
    window = make(qapp, home)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    # Installed, no A pill (owner, 29-10-2026: Your games is the card on the left); A on the card goes to the pills
    assert not window.main.isVisible() and ("Y", "Reinstall") not in window.legend.items
    window.pcsx2_card.setFocus()
    window.on_action("accept")
    assert window.remove_bios_pill.hasFocus() and window.panes.currentWidget() is window.pane
    pills = [window.remove_bios_pill, window.remove_pill, window.main]
    assert len({pill.geometry().center().y() for pill in pills if pill.isVisible()}) == 1   # one row
    window.pcsx2_card.setFocus()
    emulator.program(home).write_bytes(b"another build")         # PCSX2's own updater
    window.refresh()
    assert window.legend.items == [("X", "Choose BIOS"), ("Y", "Reinstall"), ("B", "Close")]   # Y in the legend
    assert "replaced itself" in window.status.text()
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy) and not emulator.replaced(home)
    window.remove_pill.click()
    assert window.remove_pill.label.text() == "Press again" and emulator.installed(home)
    window._confirm_over()                                      # five seconds without a second press
    assert window.remove_pill.label.text() == "Remove PCSX2"
    window.remove_pill.click()
    window.remove_pill.click()
    assert emulator.installed(home) == "" and (home / "memcards" / "Mcd001.ps2").is_file()
    assert "stay" in window.status.text() and window.main.label.text() == "Install"
    window.close()


def test_the_cards_show_their_panes_and_a_on_pcsx2_installs(qapp, tmp_path, monkeypatch):
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
    assert window.settings_pane.pills["renderer"].isEnabled()
    window.pcsx2_card.setFocus()
    window.on_action("accept")                                                     # A on the PCSX2 card
    assert wait_for(qapp, lambda: not window.busy) and emulator.installed(tmp_path / "emulator")
    window.close()


def test_an_install_prepares_pcsx2s_settings_before_its_first_start(qapp, tmp_path):
    home = tmp_path / "emulator"
    window = make(qapp, home)
    window.main.click()
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
    window.settings_card.activated.emit()                                          # A on the card: the first pill
    assert pills["renderer"].hasFocus()
    pills["renderer"].click()
    assert pills["renderer"].label.text() == "Renderer: Direct3D 12"
    assert "Renderer = 15" in (home / "inis" / "PCSX2.ini").read_text(encoding="utf-8")
    pills["aspect"].click()                                                        # the screen's shape (owner)
    assert pills["aspect"].label.text() == "Aspect ratio: 4:3"
    assert "AspectRatio = 4:3" in (home / "inis" / "PCSX2.ini").read_text(encoding="utf-8")
    is_running[0] = True                                                           # PCSX2 is open
    window.settings_pane.tabs.select("osd")
    pills["fps"].click()
    assert window.settings_pane.status.text().startswith("PCSX2 is open") and pills["fps"].label.text() == "Show FPS: Off"
    window.panes.setCurrentWidget(window.pane)
    window.on_action("x")                                                          # X Choose BIOS, PCSX2 open: says so
    assert window.status.text().startswith("PCSX2 is open")
    window.close()


def test_the_settings_are_in_tabs(qapp, tmp_path, monkeypatch):
    """More settings than one page holds (owner, 29-10-2026: "we can use tabs in the settings page to add more"):
    LB and RB step through Picture, Game, Controller and On screen; the focus follows to the tab's first row; the
    information icon tells the tab's settings; every tab's rows fit the pane."""
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
    assert "Big Picture" not in pane.info.info
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
                            settings=QSettings(str(tmp_path / "app.ini"), QSettings.Format.IniFormat))
        window.resize(1097, 617)
        window.show()
        qapp.processEvents()
        assert window.minimumSizeHint().height() <= 617
        window.close()
    finally:
        portable.pin_scale((1280, 720))


def test_your_games_folders_play_and_steam(qapp, tmp_path, monkeypatch):
    home = tmp_path / "emulator"
    fake_install(home)
    (home / "resources").mkdir()
    (home / "resources" / "GameIndex.yaml").write_text('SLUS-21553:\n  name: "Lumines Plus"\n', encoding="utf-8")
    user = tmp_path / "me"
    games = user / "Games"
    make_disc(games / "PS2" / "SLUS_215.53.Lumines.iso", "SLUS_215.53")
    (user / "Downloads").mkdir(parents=True)
    other = tmp_path / "picked"
    make_disc(other / "Other.iso", "SLES_500.03")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    played, closed = [], []

    def with_steam_closed(change):
        closed.append(True)
        change()
        return False
    window = make(qapp, home, play=lambda h, game: played.append(game), steam_dir=steam_dir,
                  steam_closed=with_steam_closed, choose_folder=lambda: str(other), user_home=user)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    qapp.processEvents()
    assert window.panes.currentWidget() is window.games_pane
    # The actions on the buttons, in the legend alone (owner, 29-10-2026: Update Steam was a pill and a legend entry)
    assert window.legend.items == [("X", "Steam mark"), ("Y", "Update Steam"), ("LB", "Folders"),
                                   ("RB", "Steam artwork"), ("B", "Close")]
    assert [p for p in window.games_pane.findChildren(portable.Pill) if type(p) is portable.Pill] == []
    assert window.games_pane.list.pills == {} and "Folders adds" in window.games_pane.status.text()
    window.on_action("previous")                                   # LB Folders: the usual places, and Choose
    assert window.legend.items == [("LB", "Games"), ("RB", "Steam artwork"), ("B", "Close")]
    pills = window.games_pane.list.pills
    assert list(pills) == [f"add:{games}", f"add:{user / 'Downloads'}", "choose"]
    pills[f"add:{games}"].click()
    assert "1 game(s) in it" in window.games_pane.status.text()
    window.games_pane.list.pills["choose"].click()                 # Windows' folder window, stood in for
    window.legend.entries["LB"].pressed.emit()                     # a tap on the legend's entry: back to the games
    pills = window.games_pane.list.pills
    lumines = str(games / "PS2" / "SLUS_215.53.Lumines.iso")
    assert pills[lumines].label.text() == "Lumines Plus  ·  SLUS-21553" and len(pills) == 2
    pills[lumines].click()                                         # no BIOS: PCSX2 would show its error window
    assert played == [] and window.games_pane.status.text().startswith("Choose BIOS first")
    (home / "bios").mkdir()
    (home / "bios" / "SCPH-70012.bin").write_bytes(b"\0" * 64)
    pills[lumines].click()                                         # A plays it
    assert played == [Path(lumines)] and "starts in PCSX2" in window.games_pane.status.text()
    window.legend.entries["Y"].pressed.emit()                      # a tap on Y Update Steam: nothing to change yet
    assert window.games_pane.status.text() == NOTHING_TO_CHANGE
    window.games_pane.list.pills[lumines].setFocus()
    qapp.processEvents()
    window.on_action("y")                                          # Y answers even then (owner, 29-10-2026)
    assert window.games_pane.status.text() == NOTHING_TO_CHANGE and not window.busy
    window.on_action("x")                                          # X marks it for Steam
    assert "✓ Steam (Update Steam)" in window.games_pane.list.pills[lumines].label.text()
    window.on_action("y")                                          # Y on Your games: Update Steam
    assert wait_for(qapp, lambda: not window.busy)
    assert closed == [True] and shortcuts.in_steam(steam_dir) == {lumines: "[PS2] Lumines Plus"}
    assert "1 game(s) in Steam" in window.games_pane.status.text() and "Read back" not in window.games_pane.status.text()
    assert window.in_steam == {lumines: "[PS2] Lumines Plus"} and "1 in Steam" in window.games_pane.summary.text()
    assert window.games_pane.list.pills[lumines].label.text().endswith("✓ Steam")
    window.close()


def test_a_game_written_but_not_read_back_is_said_and_logged(qapp, tmp_path, monkeypatch):
    """"It still says 0 games in Steam" (owner, 29-10-2026): the games are read back from Steam's file right after the
    write, and one that is not found then is named on the status line and in the log."""
    from pcsx2_manager import library
    home = tmp_path / "emulator"
    fake_install(home)
    (home / "bios").mkdir()
    (home / "bios" / "SCPH-70012.bin").write_bytes(b"\0" * 64)
    games = tmp_path / "games"
    make_disc(games / "A.iso", "SLUS_123.45")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    monkeypatch.setattr(library, "update_steam", lambda *a, **k: (True, "1 game(s) in Steam.", {}))
    window = make(qapp, home, steam_dir=steam_dir, choose_folder=lambda: str(games), user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    logged = []
    monkeypatch.setattr(window.log, "error", lambda text: logged.append(text))
    window.games_card.setFocus()
    window.toggle_folders()
    window.games_pane.list.pills["choose"].click()
    window.toggle_folders()
    window.games_pane.list.first().setFocus()
    qapp.processEvents()
    window.on_action("x")
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy)
    assert "Read back from Steam's file, 0 of the 1 game(s) are there: not A" in window.games_pane.status.text()
    assert any("reading Steam's file back finds 0" in text for text in logged) and window.in_steam == {}
    window.close()


def test_a_folder_is_taken_off_the_list_with_a_second_press(qapp, tmp_path):
    folder = tmp_path / "games"
    make_disc(folder / "A.iso", "SLUS_123.45")
    window = make(qapp, tmp_path / "emulator", choose_folder=lambda: str(folder), user_home=tmp_path / "me")
    window.toggle_folders()
    window.games_pane.list.pills["choose"].click()
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
    assert "save(s)" in pills["mc01.ps2"].label.text()
    pills["mc01.ps2"].setFocus()                                   # the card Copy card copies
    pills["mc01.ps2"].click()                                      # A: its saves
    saves = window.cards_pane.list.pills
    assert list(saves)[0] == "‹" and len(saves) > 1 and "mc01.ps2:" in window.cards_pane.summary.text()
    saves["‹"].click()                                        # back to the cards
    assert window.legend.items == [("X", "New card"), ("Y", "Copy card"), ("B", "Close")]   # no pills (owner)
    assert [p for p in window.cards_pane.findChildren(portable.Pill) if type(p) is portable.Pill] == []
    window.y_action()                                              # Y Copy card
    assert (cards / "mc01 copy.ps2").is_file() and "is copied to mc01 copy.ps2" in window.cards_pane.status.text()
    window.legend.entries["X"].pressed.emit()                      # a tap on X New card
    assert (cards / "Mcd001.ps2").is_file() and "Mcd001.ps2" in window.cards_pane.list.pills
    window.close()


def test_the_log_shows_pcsx2s_last_run(qapp, tmp_path):
    home = tmp_path / "emulator"
    fake_install(home)
    (home / "logs").mkdir()
    (home / "logs" / "emulog.txt").write_text("[    0.07] PCSX2 v2.8.2\n[    0.50]   Serial: SLUS-21553\n"
                                             "[  346.00] Add 346 seconds play time to SLUS-21553 -> now 346\n")
    log = tmp_path / "app.log"
    log.write_text("first line\nPlayed Lumines Plus (SLUS-21553).\n", encoding="utf-8")
    window = MainWindow(log_path=log, gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False),
                        home=home, steam_dir=None,
                        settings=QSettings(str(tmp_path / "app.ini"), QSettings.Format.IniFormat))
    window.resize(1280, 720)
    window.show()
    window.log_card.setFocus()
    qapp.processEvents()
    grid = window.log_pane.grid
    cells = [grid.itemAt(i).widget().text() for i in range(grid.count())]
    rows = dict(zip(cells[0::2], cells[1::2]))
    assert rows["Played"] == "5 min 46 s" and rows["PCSX2's last run"].endswith("SLUS-21553")
    assert "Played Lumines Plus" in window.log_pane.lines.text()
    window.close()



def test_the_bios_is_chosen_and_removed_on_the_pcsx2_pane(qapp, tmp_path, monkeypatch):
    r"""The BC250 app's BIOS Install and BIOS Uninstall (owner, 29-10-2026: "where do I set the BIOS"): Windows' file
    window stood in for, the dump with its files copied into bios\ and named in PCSX2.ini, the state line, X Choose
    BIOS in the legend and the Remove BIOS pill with a second press; while PCSX2 runs or is not installed, both say
    why (owner, 29-10-2026: a pill is never grayed out)."""
    home = tmp_path / "emulator"
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    dump = downloads / "SCPH-70012.bin"
    dump.write_bytes(b"\0" * (4 << 20))
    (downloads / "SCPH-70012.nvm").write_bytes(b"\0" * 1024)
    is_running = [False]
    window = make(qapp, home, running=lambda h: is_running[0], choose_file=lambda: str(dump))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert dict(window.rows())["BIOS"] == "install PCSX2 first"
    assert window.legend.items[0] == ("X", "Choose BIOS")
    for press in (lambda: window.on_action("x"), window.remove_bios_pill.click):   # not installed
        window.message = ""
        press()
        assert window.remove_bios_pill.isEnabled() and window.status.text() == BIOS_NEEDS_PCSX2
    assert not (home / "bios").exists()
    fake_install(home)
    window.refresh()
    window.remove_bios_pill.click()                                                # no BIOS yet
    assert window.status.text() == NO_BIOS_TO_REMOVE
    assert dict(window.rows())["BIOS"].startswith("No BIOS yet") and "No BIOS yet" in window.pcsx2_card.text.text()
    window.legend.entries["X"].pressed.emit()                                      # a tap on X Choose BIOS
    assert sorted(p.name for p in (home / "bios").iterdir()) == ["SCPH-70012.bin", "SCPH-70012.nvm"]
    assert "BIOS = SCPH-70012.bin" in (home / "inis" / "PCSX2.ini").read_text(encoding="utf-8")
    assert dict(window.rows())["BIOS"] == "PCSX2 uses SCPH-70012.bin"
    assert window.status.text() == "PCSX2 uses SCPH-70012.bin now." and "No BIOS" not in window.pcsx2_card.text.text()
    is_running[0] = True                                         # PCSX2 writes its settings when it closes
    window.refresh()
    for press in (lambda: window.on_action("x"), window.remove_bios_pill.click):
        window.message = ""
        press()
        assert window.status.text().startswith("PCSX2 is open") and (home / "bios" / dump.name).is_file()
    is_running[0] = False
    window.message = ""
    window.refresh()
    window.remove_bios_pill.click()
    assert window.remove_bios_pill.label.text() == "Press again" and (home / "bios" / dump.name).is_file()
    window._confirm_over()                                       # five seconds without a second press
    assert window.remove_bios_pill.label.text() == "Remove BIOS"
    window.remove_bios_pill.click()
    window.remove_bios_pill.click()
    assert list((home / "bios").iterdir()) == [] and dump.is_file()
    assert window.status.text() == "SCPH-70012.bin, SCPH-70012.nvm removed from PCSX2's bios folder. PCSX2 has no BIOS now."
    assert "biosdrain" in window.bios_info.info and "your own PlayStation 2" in window.bios_info.info
    window.close()


def test_a_game_starts_with_pcsx2s_window_kept_away(tmp_path, monkeypatch):
    # -nogui -fullscreen -batch (owner, 29-10-2026: PCSX2 is never seen), for the app and for Steam's shortcuts
    seen = []
    monkeypatch.setattr(emulator.subprocess, "Popen", lambda argv, **kwargs: seen.append((argv, kwargs["env"])) or None)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")         # the app's own Qt never reaches PCSX2's
    emulator.start(tmp_path, tmp_path / "game.iso")
    assert not any(key.upper().startswith("QT_") for key in seen[0][1])
    seen = [argv for argv, _env in seen]
    assert seen == [[str(tmp_path / emulator.EXE), "-nogui", "-fullscreen", "-batch", "--", str(tmp_path / "game.iso")]]
    from pcsx2_manager.games import Game
    assert shortcuts.launch_options(Game(tmp_path / "g.iso", "G")) == f'-nogui -fullscreen -batch -- "{tmp_path / "g.iso"}"'



def test_the_steamgriddb_key_is_pasted_saved_and_removed(qapp, tmp_path, monkeypatch):
    r"""The BC250 app's Steam artwork… key (owner, 29-10-2026: "exactly as BC250 has it"), as a page: one key for the
    suite in %APPDATA%\windows-portable-suite\steamgriddb-key, X Paste from the clipboard, A Save, Y Remove key with a
    second press, B back without saving, the page on RB; told as the BC250 app tells it."""
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
    assert window.panes.currentWidget() is pane
    assert window.legend.items == [("X", "Paste"), ("Y", "Remove key"), ("B", "Back")]
    assert pane.field.echoMode() == pane.field.EchoMode.Password and "Generate API Key" in pane.findChildren(
        type(window.status))[1].text()
    assert pane.status.text().startswith("No key") and pane.save.hasFocus()
    window.on_action("y")                                       # no key: it says so
    assert pane.status.text().startswith("There is no key to remove")
    QGuiApplication.clipboard().setText("  0123456789abcdef0123456789abcdef \n")
    window.on_action("x")                                       # X on the key page: Paste
    assert pane.field.text() == "0123456789abcdef0123456789abcdef"
    window.on_action("back")                                    # B: back, nothing saved
    assert window.panes.currentWidget() is window.games_pane and not key_file.exists()
    assert window.legend.items[-1] == ("B", "Close") and window.games_card.hasFocus()
    window.legend.entries["RB"].pressed.emit()                  # a tap on RB Steam artwork
    window.key_pane.field.setText("0123456789abcdef0123456789abcdef")
    window.key_pane.save.click()
    assert covers.read_key(key_file) == "0123456789abcdef0123456789abcdef"
    assert window.games_pane.status.text() == "The SteamGridDB key was changed."
    assert window.panes.currentWidget() is window.games_pane and pane.field.text() == ""   # not left in the window
    window.on_action("next")
    assert pane.field.text() == "0123456789abcdef0123456789abcdef"
    window.on_action("y")
    assert window.legend.items[1] == ("Y", "Press again") and key_file.exists()
    assert pane.status.text() == "Press Y again to remove the key."
    window._confirm_over()                                      # five seconds without a second press
    assert window.legend.items[1] == ("Y", "Remove key") and pane.status.text() == ""
    window.on_action("y")
    window.legend.entries["Y"].pressed.emit()                   # the second press, as a tap
    assert not key_file.exists()
    assert window.games_pane.status.text() == "The SteamGridDB key was taken out; the pictures kept stay in use."
    window.close()


def test_y_on_your_games_always_says_what_it_did(qapp, tmp_path, monkeypatch):
    """Y in Your games did nothing when there was nothing to do (owner, 29-10-2026): now the status line says why."""
    folder = tmp_path / "games"
    make_disc(folder / "A.iso", "SLUS_123.45")
    window = make(qapp, tmp_path / "emulator", choose_folder=lambda: str(folder), user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    window.toggle_folders()
    window.games_pane.list.pills["choose"].click()
    window.games_pane.list.first().setFocus()
    qapp.processEvents()
    assert ("Y", "Update Steam") not in window.legend.items
    window.on_action("y")                                          # the folders: Update Steam is the games'
    assert window.games_pane.status.text() == NOT_THE_GAMES
    window.toggle_folders()
    window.games_pane.list.first().setFocus()
    qapp.processEvents()
    window.on_action("x")
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


def test_no_pill_of_the_app_is_ever_grayed_out(qapp, tmp_path):
    """The suite's rule (owner, 29-10-2026): every pill stays amber; one that cannot act says why."""
    window = make(qapp, tmp_path / "emulator")
    for pane in (window.pane, window.games_pane, window.settings_pane, window.cards_pane, window.log_pane,
                 window.key_pane):
        window.panes.setCurrentWidget(pane)
        window.refresh()
        assert all(pill.isEnabled() for pill in pane.findChildren(portable.Pill))
    window.close()
