# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py), as PPSSPP Manager's is tested: it opens on the portable window with the header's
battery, date and time, fits the handheld's screen; every action is a button in the row at the bottom, A too, and no
pill is left (owner, 29-10-2026); B goes back and View exits; RPCS3 installed on A (off the window's thread, the
megabytes counted, View asking first meanwhile, its files prepared after), updated from an older build, and removed
with X pressed twice; the firmware and the packages given to RPCS3 without its window (stood in for) and the result
read from its log; the Settings pane's rows, in tabs, step through their values, never while RPCS3 runs; Your games
from the folders and RPCS3, marked for Steam with A, put in Steam and played through it with X, without Steam in
RPCS3 itself; the
folder browser, which opens where it was left; the Log pane and the whole log read in the app; the SteamGridDB key; the version and the
icons are where the checks expect them."""

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
from conftest import fake_install, make_disc_game, make_hdd_game, write_rpcs3_files
from rpcs3_manager import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, emulator, shortcuts, userdata
from rpcs3_manager.main_window import (NEEDS_RPCS3, NO_FIRMWARE, NO_STEAM, NOT_THE_GAMES, NOTHING_TO_CHANGE,
                                       OPEN_A_FOLDER, MainWindow)

FIRMWARE = "release:04.9200:\nbuild:...\n"


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
    more.setdefault("start", lambda command, cwd=None: None)   # never a real RPCS3
    more.setdefault("drives", lambda: [])
    more.setdefault("roots", lambda: [])
    more.setdefault("runtime_missing", lambda: [])
    more.setdefault("run_headless", lambda home, *args: 0)
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


def ready(home: Path) -> None:
    """RPCS3 installed with its firmware, as after an install and a firmware install."""
    fake_install(home, firmware=FIRMWARE)


def test_the_window_opens_with_the_suites_header(qapp):
    window = make(qapp)
    assert window.header.title.text() == APP_NAME and window.header.version.text() == __version__
    assert re.fullmatch(r"82%  \|  \w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d", window.header.status.text())
    assert window.legend.items == [("A", "Install"), MENU_INFO, EXIT]       # on a card: nothing to go back to
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
    window.on_action("back")                                    # on the RPCS3 card: nothing
    assert closed == [] and window.rpcs3_card.hasFocus()
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
    assert calls == [] and window.rpcs3_card.hasFocus()
    assert dict(window.rows())["Installed"] == "not installed" and dict(window.rows())["Firmware"] == "none yet"
    window.on_action("x")                                       # X Remove: says why, nothing happens
    assert "nothing to remove" in window.status.text() and calls == []
    window.on_action("previous")                                # LB Firmware: RPCS3 first
    assert window.status.text() == NEEDS_RPCS3 and window.panes.currentWidget() is window.pane
    window.close()


def test_a_installs_off_the_windows_thread_and_counts_the_megabytes(qapp, tmp_path, monkeypatch):
    gate = threading.Event()
    window = make(qapp, tmp_path / "emulator", install=lambda home, **k: fake_install(home, gate=gate, **k))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("accept")                                  # A on the RPCS3 card
    assert window.busy
    window.refresh()
    assert window.status.text() == f"Downloading RPCS3 {emulator.VERSION}… 12 of 37 MB"
    assert ("A", "Install") not in window.legend.items
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.on_action("view")                                    # Exit asks first while it downloads
    assert closed == [] and window.legend.items == [(VIEW, "Press again to exit")]
    assert window.status.text() == "Press View again to exit: the download stops."
    gate.set()
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == f"RPCS3 {emulator.VERSION} is installed."
    assert window.legend.items == [("X", "Remove RPCS3"), ("LB", "Firmware"), ("RB", "Packages"), MENU_INFO, EXIT]
    assert userdata.pad_device(tmp_path / "emulator") == "XInput Pad #1"          # prepared before its first start
    assert "checkUpdateStart=false" in (tmp_path / "emulator" / userdata.GUI_SETTINGS).read_text()
    window.on_action("view")
    assert closed == [True]                                     # nothing runs: View exits at once


def test_a_failed_install_says_why(qapp, tmp_path):
    def failing(home, **kwargs):
        raise emulator.EmulatorError("the archive has no rpcs3.exe")
    window = make(qapp, tmp_path / "emulator", install=failing)
    window.act("accept")
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == "RPCS3 could not be installed: the archive has no rpcs3.exe"
    assert ("A", "Install") in window.legend.items
    window.close()


def test_update_and_remove_with_x_pressed_twice(qapp, tmp_path):
    home = tmp_path / "emulator"
    fake_install(home, version="0.0.42-20000", firmware=FIRMWARE)
    save = home / "dev_hdd0" / "home" / "00000001" / "savedata" / "BLUS30443-S01" / "PARAM.SFO"
    save.parent.mkdir(parents=True)
    save.write_bytes(b"x")
    window = make(qapp, home)
    assert window.legend.items == [("X", "Remove RPCS3"), ("Y", "Update"), ("LB", "Firmware"), ("RB", "Packages"),
                                   MENU_INFO, EXIT]
    assert window.status.text() == f"This app installs RPCS3 {emulator.VERSION}: the Y button updates it."
    window.act("y")
    assert wait_for(qapp, lambda: not window.busy) and emulator.installed(home) == emulator.VERSION
    window.legend.entries["X"].pressed.emit()                   # a tap on X Remove RPCS3
    assert window.legend.items[0] == ("X", "Press again") and emulator.installed(home)
    assert window.status.text().startswith("Press the X button again")
    window._confirm_over()                                      # five seconds without a second press
    assert window.legend.items[0] == ("X", "Remove RPCS3")
    window.act("x")
    window.act("x")
    assert emulator.installed(home) == "" and save.is_file() and userdata.firmware_version(home / "dev_flash") == "4.92"
    assert "stays" in window.status.text() and window.legend.items[0] == ("A", "Install")
    window.close()


def test_remove_while_rpcs3_runs_says_so(qapp, tmp_path):
    home = tmp_path / "emulator"
    ready(home)
    window = make(qapp, home, running=lambda h: True)
    window.act("x")
    window.act("x")
    assert emulator.installed(home) and window.status.text().startswith("RPCS3 is open")
    window.close()


def test_the_runtime_and_the_firmware_are_asked_for(qapp, tmp_path):
    home = tmp_path / "emulator"
    fake_install(home)                                                      # no firmware yet
    window = make(qapp, home, runtime_missing=lambda: ["msvcp140.dll"])
    assert window.status.text().startswith("RPCS3 needs Microsoft's Visual C++ runtime (msvcp140.dll missing")
    window.close()
    window = make(qapp, home)
    assert window.status.text() == "No firmware yet: the LB button takes the PS3UPDAT.PUP you downloaded."
    window.close()


def test_the_cards_show_their_panes(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert window.panes.currentWidget() is window.pane
    window.on_action("down")
    assert window.games_card.hasFocus() and window.panes.currentWidget() is window.games_pane
    window.on_action("down")
    assert window.settings_card.hasFocus() and window.panes.currentWidget() is window.settings_pane
    assert window.settings_pane.status.text() == "Install RPCS3 first: the settings are in its folder."
    assert window.legend.items[:3] == [("A", "Change"), ("LB", "Previous tab"), ("RB", "Next tab")]
    window.settings_pane.status.setText("")
    window.settings_pane.pills["renderer"].click()                                 # never grayed out: says why
    assert window.settings_pane.status.text() == "Install RPCS3 first: the settings are in its folder."
    window.on_action("down")
    assert window.log_card.hasFocus() and window.panes.currentWidget() is window.log_pane
    for card in (window.rpcs3_card, window.games_card, window.settings_card, window.log_card):
        card.setFocus()
        qapp.processEvents()
        assert no_pills(window)
    window.close()


def test_the_settings_step_and_are_written_at_once(qapp, tmp_path, monkeypatch):
    from rpcs3_manager import rpcs3_settings
    home = tmp_path / "emulator"
    ready(home)
    is_running = [False]
    window = make(qapp, home, running=lambda h: is_running[0])
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    pills = window.settings_pane.pills
    assert pills["renderer"].label.text() == "Renderer: Vulkan"                    # RPCS3's default
    window.settings_card.setFocus()
    window.on_action("accept")                                                     # A on the card: the first row
    assert pills["renderer"].hasFocus()
    window.on_action("accept")
    assert pills["renderer"].label.text() == "Renderer: OpenGL"
    config = rpcs3_settings.settings_path(home)
    assert "  Renderer: OpenGL" in config.read_text(encoding="utf-8")
    pills["scale"].click()
    assert pills["scale"].label.text() == "Resolution scale: 150% (1080p)"
    is_running[0] = True                                                           # RPCS3 is open
    window.settings_pane.tabs.select("messages")
    pills["trophies"].click()
    assert window.settings_pane.status.text().startswith("RPCS3 is open")
    assert pills["trophies"].label.text() == "Trophy messages: On"
    is_running[0] = False
    pills["trophies"].click()
    assert pills["trophies"].label.text() == "Trophy messages: Off"
    assert "  Show trophy popups: false" in config.read_text(encoding="utf-8")
    window.close()


def test_the_settings_are_in_tabs(qapp, tmp_path, monkeypatch):
    """LB and RB step through Picture, Speed, Sound and Messages; the focus follows to the tab's first row; the
    information tells the tab's settings; every tab's rows fit the pane."""
    from rpcs3_manager.rpcs3_settings import TABS
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    pane = window.settings_pane
    assert [key for key, _, _ in TABS] == ["picture", "speed", "sound", "messages"] == pane.tabs.keys
    assert pane.tabs.current == "picture" and pane.pills["screen"].isVisibleTo(pane)
    assert not pane.pills["vsync"].isVisibleTo(pane) and "Renderer:" in pane.info.info
    assert "The A button changes" in pane.info.info
    window.settings_card.setFocus()
    window.on_action("accept")
    assert pane.pills["renderer"].hasFocus()
    window.on_action("next")                                                       # RB: the next tab
    assert pane.tabs.current == "speed" and pane.pills["vsync"].hasFocus() and "VSync:" in pane.info.info
    window.on_action("previous")
    window.on_action("previous")                                                   # LB twice: round to the last
    assert pane.tabs.current == "messages" and pane.pills["trophies"].hasFocus()
    assert pane.pills["trophies"].isVisibleTo(pane)
    assert pane.minimumSizeHint().height() <= window.panes.height()
    window.close()


def test_a_long_folder_wraps_and_the_window_stays_on_the_screen(qapp, tmp_path):
    deep = tmp_path / ("a-rather-long-folder-name" * 3) / "windows-portable-suite" / "windows-portable-rpcs3" / "emulator"
    window = make(qapp, deep)
    assert window.minimumSizeHint().width() <= 1280 and window.width() == 1280
    assert window.panes.minimumSizeHint().width() < 800
    window.close()


def test_the_window_fits_a_smaller_screen(qapp, tmp_path):
    # It adapts to the screen it is on (a 1080p screen at 175 % is 1097 x 617), as every app of the suite.
    portable.pin_scale((1097, 617))
    try:
        window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False), steam_dir=None,
                            home=tmp_path / "emulator", roots=lambda: [], runtime_missing=lambda: [],
                            settings=QSettings(str(tmp_path / "app.ini"), QSettings.Format.IniFormat))
        window.resize(1097, 617)
        window.show()
        qapp.processEvents()
        assert window.minimumSizeHint().height() <= 617
        window.close()
    finally:
        portable.pin_scale((1280, 720))


def test_the_firmware_is_installed_by_rpcs3_without_its_window(qapp, tmp_path, monkeypatch):
    """LB Firmware opens the browser in Downloads with the .PUP files; A on one runs RPCS3 headless (stood in for:
    it writes the log and the version file RPCS3 would), and the RPCS3 pane shows the version."""
    home = tmp_path / "emulator"
    fake_install(home)
    user = tmp_path / "me"
    (user / "Downloads").mkdir(parents=True)
    pup = user / "Downloads" / "PS3UPDAT.PUP"
    pup.write_bytes(b"pup")
    (user / "Downloads" / "notes.txt").write_text("")
    runs = []

    def run_headless(home_, *args):
        runs.append(args)
        write_rpcs3_files(home_, FIRMWARE)
        log = userdata.rpcs3_log(home_)
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("·S 0:01:40.9 GUI: Successfully installed PS3 firmware version 4.92.\n", encoding="utf-8")
        return -1073740791                                      # RPCS3's own fault at teardown
    window = make(qapp, home, user_home=user, run_headless=run_headless)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("previous")                                # LB Firmware
    assert window.panes.currentWidget() is window.browse_pane and window.browser.path == user / "Downloads"
    assert window.browse_pane.heading.text() == "Choose the firmware file"
    assert window.legend.items == [("A", "Open"), MENU_INFO, BACK, EXIT]
    rows = window.browse_pane.list.pills
    assert list(rows)[1:] == [f"file:{pup}"]                    # the .PUP, not the text file
    window.on_action("x")                                       # X does nothing here
    rows[f"file:{pup}"].click()                                 # A on it
    assert window.busy and window.panes.currentWidget() is window.pane
    assert window.status.text().startswith("RPCS3 installs PS3UPDAT.PUP, without its window")
    assert wait_for(qapp, lambda: not window.busy)
    assert runs == [("--installfw", str(pup))]
    assert window.status.text() == "PS3 firmware 4.92 is installed." and window.firmware == "4.92"
    assert dict(window.rows())["Firmware"] == "4.92"
    window.close()


def test_a_firmware_rpcs3_refuses_is_said(qapp, tmp_path, monkeypatch):
    home = tmp_path / "emulator"
    fake_install(home)

    def run_headless(home_, *args):
        log = userdata.rpcs3_log(home_)
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("·E 0:00:00.1 GUI: Error while installing firmware: provided file is not a PUP file.\n",
                       encoding="utf-8")
        return -1073740791
    window = make(qapp, home, run_headless=run_headless)
    window.install_firmware(tmp_path / "x.pup")
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == ("RPCS3 did not install the firmware: Error while installing firmware: provided "
                                    "file is not a PUP file.")
    window.close()


def test_packages_are_installed_one_run_each_the_updates_last(qapp, tmp_path, monkeypatch):
    """RB Packages opens the browser; X installs the open folder's licenses and packages, each in a run of RPCS3
    without its window (stood in for), the game before its update; the result from RPCS3's log."""
    home = tmp_path / "emulator"
    ready(home)
    user = tmp_path / "me"
    pkgs = user / "Downloads" / "lumines"
    pkgs.mkdir(parents=True)
    fixtures = Path(__file__).resolve().parents[4] / "bc250-bazzite" / "apps" / "rpcs3" / "tests" / "fixtures"
    (pkgs / "A-Update.pkg").write_bytes((fixtures / "update.pkg.head").read_bytes())
    (pkgs / "Game.pkg").write_bytes((fixtures / "game.pkg.head").read_bytes())
    (pkgs / "Game.rap").write_bytes(b"")
    runs = []

    def run_headless(home_, *args):
        runs.append(Path(args[1]).name)
        log = userdata.rpcs3_log(home_)
        log.parent.mkdir(parents=True, exist_ok=True)
        if args[1].endswith(".rap"):
            log.write_text("·S 0:00:00.1 GUI: Successfully copied rap file: Game.rap\n", encoding="utf-8")
        elif args[1].endswith("Game.pkg"):
            make_hdd_game(home_ / "dev_hdd0" / "game" / "NPUB30048", "LUMINES Supernova", "NPUB30048")
            log.write_text("·S 0:01:03.1 GUI: Successfully installed x (title_id=NPUB30048, title=LUMINES Supernova, "
                           "version=01.00).\n", encoding="utf-8")
        else:
            log.write_text("·S 0:01:03.1 GUI: Successfully installed y (title_id=NPUB30048, title=LUMINES Supernova, "
                           "version=01.02).\n", encoding="utf-8")
        return 0
    window = make(qapp, home, user_home=user, run_headless=run_headless)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("next")                                    # RB Packages
    assert window.panes.currentWidget() is window.browse_pane
    assert window.legend.items == [("A", "Open"), ("X", "Install from this folder"), MENU_INFO, BACK, EXIT]
    assert window.browser.path == user / "Downloads"
    window.browse_pane.list.pills[f"dir:{pkgs}"].click()       # into the folder: its files show
    assert sorted(k for k in window.browse_pane.list.pills if k.startswith("file:")) == sorted(
        f"file:{pkgs / n}" for n in ("A-Update.pkg", "Game.pkg", "Game.rap"))
    window.on_action("x")                                       # X: install the folder's
    assert window.busy and window.panes.currentWidget() is window.pane
    assert "RPCS3 installs 2 package(s) and 1 license(s) from lumines" in window.status.text()
    assert wait_for(qapp, lambda: not window.busy)
    assert runs == ["Game.rap", "Game.pkg", "A-Update.pkg"]
    assert window.status.text() == ("2 game(s) installed in RPCS3: LUMINES Supernova (NPUB30048), LUMINES Supernova "
                                    "(NPUB30048); 1 license(s) copied into RPCS3.")
    window.games_card.setFocus()
    qapp.processEvents()
    assert [p.label.text() for p in window.games_pane.list.pills.values()] == ["LUMINES Supernova  ·  NPUB30048"]
    window.rpcs3_card.setFocus()
    window.on_action("next")                                    # RB again: the folder of before (owner, 29-10-2026)
    assert window.browser.path == pkgs
    window.close()


def test_a_folder_without_packages_says_so(qapp, tmp_path):
    home = tmp_path / "emulator"
    ready(home)
    (tmp_path / "empty").mkdir()
    window = make(qapp, home)
    window.install_packages(tmp_path / "empty")
    assert window.status.text() == "No .pkg, .rap or .edat file in empty." and not window.busy
    window.close()


def test_your_games_are_marked_with_a_and_put_in_steam(qapp, tmp_path, monkeypatch):
    """The games are played from Steam (owner, 29-10-2026): A on a game is its Steam mark, Y Update Steam writes the
    marks, X plays a game that is in Steam through Steam (steam://rungameid); Steam's library is the portal's (owner,
    30-10-2026: no Open Steam row)."""
    home = tmp_path / "emulator"
    ready(home)
    hdd_game = make_hdd_game(home / "dev_hdd0" / "game" / "NPUB30001", "Flower", "NPUB30001")
    user = tmp_path / "me"
    games = user / "Games"
    demon = make_disc_game(games / "PS3" / "Demon's Souls", "Demon's Souls", "BLUS30443", pictures=True)
    (user / "Downloads").mkdir(parents=True)
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
    window.games_card.setFocus()
    qapp.processEvents()
    assert window.legend.items == [("A", "Steam mark"), ("Y", "Update Steam"), ("LB", "Folders"),
                                   ("RB", "Steam artwork"), MENU_INFO, EXIT]
    assert not hasattr(window, "steam_row")
    assert "Press the A button on a game to mark it for Steam" in window.games_pane.info.info
    assert list(window.games_pane.list.pills) == [str(hdd_game)]                   # RPCS3's, no folder yet
    window.on_action("previous")                                   # LB Folders: the usual places, and Browse
    assert window.legend.items == [("A", "Choose"), ("LB", "Games"), ("RB", "Steam artwork"), MENU_INFO, BACK, EXIT]
    pills = window.games_pane.list.pills
    assert list(pills) == [f"add:{games}", f"add:{user / 'Downloads'}", "browse"]
    pills[f"add:{games}"].click()
    assert "1 game(s) in it" in window.games_pane.status.text()
    window.on_action("back")                                       # B on the folders: the games
    pills = window.games_pane.list.pills
    assert [pill.label.text() for pill in pills.values()] == ["Demon's Souls  ·  BLUS30443", "Flower  ·  NPUB30001"]
    window.legend.entries["Y"].pressed.emit()                      # a tap on Y Update Steam: nothing to change yet
    assert window.games_pane.status.text() == NOTHING_TO_CHANGE
    pills[str(demon)].setFocus()
    qapp.processEvents()
    assert ("X", "Play") in window.legend.items
    window.on_action("x")                                          # X: not in Steam yet
    assert window.games_pane.status.text() == ("Demon's Souls is not in Steam yet: A marks it, then Y Update Steam "
                                               "puts it there.") and played == []
    window.on_action("accept")                                     # A: the Steam mark
    assert "✓ Steam (Update Steam)" in window.games_pane.list.pills[str(demon)].label.text()
    window.on_action("y")                                          # Y on Your games: Update Steam
    assert wait_for(qapp, lambda: not window.busy)
    assert closed == [True] and shortcuts.in_steam(steam_dir) == {str(demon): "[PS3] Demon's Souls"}
    assert "1 game(s) in Steam" in window.games_pane.status.text() and "Read back" not in window.games_pane.status.text()
    assert window.games_pane.list.pills[str(demon)].label.text().endswith("✓ Steam")
    window.games_pane.list.pills[str(demon)].setFocus()
    window.on_action("x")                                          # X: played through Steam
    number = shortcuts.numbers(steam_dir)[str(demon)]
    assert played[-1] == f"steam://rungameid/{(number << 32) | 0x02000000}"
    assert window.games_pane.status.text() == ("Starting Demon's Souls in Steam… In the game, hold View and Menu "
                                               "together to quit.")      # how to quit, on the screen (30-10-2026)
    window.close()


def test_without_steam_x_starts_the_game_in_rpcs3(qapp, tmp_path, monkeypatch):
    """A device without Steam (owner, 30-10-2026: a fallback): X starts RPCS3 with the game full screen, as its
    shortcut would, from RPCS3's folder; without RPCS3 it says to install it first."""
    home = tmp_path / "emulator"
    ready(home)
    game = make_hdd_game(home / "dev_hdd0" / "game" / "NPUB30001", "Flower", "NPUB30001")
    started, played = [], []
    window = make(qapp, home, user_home=tmp_path / "me",
                  start=lambda command, cwd=None: started.append((command, cwd)), play=played.append)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    window.on_action("accept")
    window.games_pane.list.pills[str(game)].setFocus()
    qapp.processEvents()
    assert ("X", "Play") in window.legend.items
    window.on_action("x")
    program = emulator.program(home)
    launcher, before = play.launcher(ROOT)                      # the play mode, as the shortcut would start it
    assert started == [([launcher, *before, "--no-gui", "--fullscreen", str(game)], program.parent)]
    assert played == [] and window.games_pane.status.text() == ("Starting Flower in RPCS3… In the game, hold View "
                                                                "and Menu together to quit.")

    def fails(command, cwd=None):
        raise PermissionError(13, "Access is denied")
    window.start_program = fails
    window.on_action("x")
    assert window.games_pane.status.text() == "RPCS3 could not start Flower: Access is denied"
    program.unlink()                                    # RPCS3 gone
    window.on_action("x")
    assert len(started) == 1 and window.games_pane.status.text() == ("Install RPCS3 first: it starts Flower on a "
                                                                     "device without Steam.")
    window.close()


def test_update_steam_needs_rpcs3_and_its_firmware(qapp, tmp_path, monkeypatch):
    home = tmp_path / "emulator"
    fake_install(home)                                             # no firmware
    folder = tmp_path / "games"
    make_disc_game(folder / "A", "A", "BLUS00001")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    window = make(qapp, home, steam_dir=steam_dir, user_home=tmp_path / "me")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.add_folder(folder)
    window.games_card.setFocus()
    window.games_pane.list.first().setFocus()
    qapp.processEvents()
    window.on_action("accept")
    window.on_action("y")
    assert window.games_pane.status.text() == NO_FIRMWARE and not window.busy
    window.close()


def test_a_disc_game_without_its_sfb_is_marked_so(qapp, tmp_path):
    folder = tmp_path / "games"
    make_disc_game(folder / "A", "A", "BLUS00001", sfb=None)
    window = make(qapp, tmp_path / "emulator", user_home=tmp_path / "me")
    window.add_folder(folder)
    assert [p.label.text() for p in window.games_pane.list.pills.values()] == ["A  ·  BLUS00001  ·  no PS3_DISC.SFB"]
    window.close()


def test_the_folder_browser_goes_by_the_controller(qapp, tmp_path, monkeypatch):
    """Windows' own folder window cannot be used with the controller (owner, 29-10-2026): the app's browser lists the
    places and the folders; A opens one, X adds the open folder, B goes up and, from the places, back."""
    user = tmp_path / "me"
    target = user / "Games" / "PS3"
    make_disc_game(target / "DeS", "Demon's Souls", "BLUS30443")
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
    window.games_pane.list.pills["browse"].click()                 # again: where it was left
    assert window.browser.path == target
    window.on_action("back")                                       # B: up, Games, a place
    window.on_action("back")                                       # the places
    window.on_action("back")                                       # B at the places: back to the folders
    assert window.panes.currentWidget() is window.games_pane and window.browser is None
    window.close()


def test_a_game_written_but_not_read_back_is_said_and_logged(qapp, tmp_path, monkeypatch):
    from rpcs3_manager import library
    home = tmp_path / "emulator"
    ready(home)
    make_disc_game(tmp_path / "me" / "Games" / "A", "A")
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
    make_disc_game(folder / "A", "A")
    window = make(qapp, tmp_path / "emulator", user_home=tmp_path / "me")
    window.add_folder(folder)
    window.toggle_folders()
    key = f"folder:{folder}"
    window.games_pane.list.pills[key].click()
    assert window.games_pane.list.pills[key].label.text() == "Press A again to take it off the list"
    window.games_pane.list.pills[key].click()
    assert key not in window.games_pane.list.pills and (folder / "A" / "PS3_DISC.SFB").is_file()
    assert "no longer a game folder" in window.games_pane.status.text()
    window.close()


def test_the_log_is_read_in_the_app(qapp, tmp_path, monkeypatch):
    """The Log pane shows RPCS3's folder and the newest lines; A (or a tap on the pane) shows the whole log in the
    app, the d-pad scrolls it and B goes back (owner, 29-10-2026: Notepad has no button to close it)."""
    home = tmp_path / "emulator"
    ready(home)
    for save in ("BLUS30443-S01", "NPUB30001-AUTO"):
        (home / "dev_hdd0" / "home" / "00000001" / "savedata" / save).mkdir(parents=True)
    log = tmp_path / "app.log"
    log.write_text("".join(f"line {n}\n" for n in range(300)), encoding="utf-8")
    window = make(qapp, home)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.log_path = log
    window.log_card.setFocus()
    qapp.processEvents()
    texts = [label.text() for label in window.log_pane.findChildren(type(window.status))]
    assert "Firmware" in texts and "4.92" in texts and "Saves" in texts and "2" in texts
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
    press, B back without saving, the page on RB."""
    from bc250_core import covers
    from PyQt6.QtGui import QGuiApplication
    from rpcs3_manager import library
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
    make_disc_game(folder / "A", "A")
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
    window.rpcs3_card.setFocus()
    qapp.processEvents()
    assert window.rpcs3_info not in window.focusables()
    window.on_action("menu")                                    # the RPCS3 pane's information: the firmware, packages
    assert window.popup is not None and "PS3UPDAT.PUP" in window.popup.text.toPlainText()
    window.on_action("menu")
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
    """The privacy rule (owner, 29-10-2026): the folder, the game folders and the places to add show the user's
    folders by their variable (%LOCALAPPDATA%, %USERPROFILE%)."""
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


def test_marked_packages_are_installed_together(qapp, tmp_path, monkeypatch):
    """Owner, 29-10-2026: not one package at a time. Y marks a file in the packages browser (a ✓ before it), X then
    installs the marked ones only, licenses first; the marks go when another folder opens."""
    home = tmp_path / "emulator"
    ready(home)
    user = tmp_path / "me"
    pkgs = user / "Downloads" / "psn"
    pkgs.mkdir(parents=True)
    for name in ("A.pkg", "B.pkg", "C.pkg", "B.rap"):
        (pkgs / name).write_bytes(b"")
    runs = []

    def run_headless(home_, *args):
        runs.append(Path(args[1]).name)
        return 0
    window = make(qapp, home, user_home=user, run_headless=run_headless)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("next")                                    # RB Packages
    window.browse_pane.list.pills[f"dir:{pkgs}"].click()
    rows = window.browse_pane.list.pills
    rows[f"file:{pkgs / 'B.pkg'}"].setFocus()
    qapp.processEvents()
    assert window.legend.items[:3] == [("A", "Install"), ("X", "Install from this folder"), ("Y", "Mark")]
    window.on_action("y")
    assert window.browse_pane.list.pills[f"file:{pkgs / 'B.pkg'}"].label.text() == "✓ B.pkg"
    assert window.browse_pane.list.pills[f"file:{pkgs / 'B.pkg'}"].hasFocus()
    assert window.legend.items[:3] == [("A", "Install"), ("X", "Install marked (1)"), ("Y", "Unmark")]
    window.on_action("down")
    window.on_action("y")                                       # B.rap too
    window.on_action("up")
    window.on_action("up")
    assert window.browse_pane.list.focused() == f"file:{pkgs / 'A.pkg'}"
    window.on_action("y")
    window.on_action("y")                                       # marked and unmarked again
    assert window.legend.items[1] == ("X", "Install marked (2)")
    window.on_action("x")
    assert wait_for(qapp, lambda: not window.busy)
    assert runs == ["B.rap", "B.pkg"]
    window.rpcs3_card.setFocus()
    window.on_action("next")                                    # the same folder again: no marks left
    assert window.browser.path == pkgs and not window.picked_files
    window.browse_pane.list.pills["up"].setFocus()
    window.on_action("y")                                       # Y on the way up: says how
    assert window.browse_pane.status.text().startswith("Put the focus on a file first")
    window.close()


def test_x_plays_only_a_game_in_steam(qapp, tmp_path, monkeypatch):
    """X with no game row in focus says how; Steam's shortcuts read for the game's number."""
    from rpcs3_manager.main_window import NO_GAME
    window = make(qapp, tmp_path / "emulator", play=lambda url: None)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    window.on_action("x")
    assert window.games_pane.status.text() == NO_GAME
    window.close()


def test_a_shortcut_made_before_the_play_mode_asks_for_update_steam(qapp, tmp_path, monkeypatch):
    """A game whose shortcut still starts RPCS3 itself (1.0.1's) says (Update Steam), and Y brings it to the play
    mode (owner, 30-10-2026: View and Menu held quit every game)."""
    home = tmp_path / "emulator"
    ready(home)
    game = make_hdd_game(home / "dev_hdd0" / "game" / "NPUB30001", "Flower", "NPUB30001")
    steam_dir = tmp_path / "Steam"
    config = steam_dir / "userdata" / "1" / "config"
    config.mkdir(parents=True)
    program = emulator.program(home)
    old = steam.shortcut_entry(f'"{program}"', "[PS3] Flower", f'"{program.parent}\\"', "",
                               f'--no-gui --fullscreen "{game}"', shortcuts.TAGS)
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
    """--play, as a shortcut starts the app: RPCS3 with the shortcut's arguments from its folder, through core's play
    mode, before any window or the one-window check (the app's window may be open beside it)."""
    from rpcs3_manager import __main__ as entry
    ran = []
    monkeypatch.setattr(emulator, "emulator_home", lambda: tmp_path / "emulator")
    monkeypatch.setattr(entry.applog, "setup", lambda *a, **k: tmp_path / "log")
    monkeypatch.setattr(entry.play, "run", lambda command, cwd, log: ran.append((command, cwd)) or 3)
    monkeypatch.setattr(entry, "create_app", lambda *a, **k: pytest.fail("no window in the play mode"))
    monkeypatch.setattr(sys, "argv", ["RPCS3-Manager.exe", "--play", "--no-gui", "--fullscreen", r"D:\G\EBOOT.BIN"])
    assert entry.main() == 3
    program = emulator.program(tmp_path / "emulator")
    assert ran == [([str(program), "--no-gui", "--fullscreen", r"D:\G\EBOOT.BIN"], program.parent)]

    def fails(command, cwd, log):
        raise FileNotFoundError(2, "The system cannot find the file specified")
    monkeypatch.setattr(entry.play, "run", fails)
    assert entry.main() == 1
