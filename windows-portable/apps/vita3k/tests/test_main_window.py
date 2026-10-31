# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py), as RPCS3 Manager's is tested: it opens on the portable window with the header's
battery, date and time, fits the handheld's screen; every action is a button in the row at the bottom, A too, and no
pill is left (owner, 29-10-2026); B goes back and View exits; Vita3K installed on A (off the window's thread, the
megabytes counted, View asking first meanwhile, its config.yml prepared after), updated from another build, and
removed with X pressed twice; a newer build on GitHub shown; the firmware, a .vpk, a dumped folder and a .pkg with its
license key given to Vita3K (stood in for) and the result read from what it wrote; the Settings pane's rows, in tabs,
step through their values, never while Vita3K runs; Your games from Vita3K's storage, marked for Steam with A (never
played from the app) and put in Steam; the Log pane and the whole log read in the app; the SteamGridDB key; the
version and the icons are where the checks expect them."""

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
from conftest import fake_install, install_firmware, make_game
from vita3k_manager import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, emulator, shortcuts, userdata
from vita3k_manager.main_window import (NEEDS_VITA3K, NO_FIRMWARE, NO_STEAM, NOTHING_TO_CHANGE, OPEN_A_FOLDER,
                                        MainWindow)


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
    more.setdefault("start", lambda command, cwd=None: None)   # never a real Vita3K
    more.setdefault("roots", lambda: [])
    more.setdefault("runtime_missing", lambda: [])
    more.setdefault("newer_release", lambda: None)      # never GitHub
    more.setdefault("run_quiet", lambda home, *args: 0)
    more.setdefault("install_content", lambda home, content: True)
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
    """Vita3K installed with its firmware and fonts, as after an install and two firmware installs."""
    fake_install(home, firmware=True)


def fs(home: Path) -> Path:
    return home / "portable" / "fs"


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
    window.on_action("back")                                    # on the Vita3K card: nothing
    assert closed == [] and window.vita3k_card.hasFocus()
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
    assert calls == [] and window.vita3k_card.hasFocus()
    rows = dict(window.rows())
    assert rows["Installed"] == "not installed" and rows["This app installs"] == "build 4186 (0.2.1)"
    assert rows["Firmware"] == "no system software and no font package" and rows["Games"] == "0"
    window.on_action("x")                                       # X Remove: says why, nothing happens
    assert "nothing to remove" in window.status.text() and calls == []
    window.on_action("previous")                                # LB Firmware: Vita3K first
    assert window.status.text() == NEEDS_VITA3K and window.panes.currentWidget() is window.pane
    window.close()


def test_a_installs_off_the_windows_thread_and_counts_the_megabytes(qapp, tmp_path, monkeypatch):
    gate = threading.Event()
    window = make(qapp, tmp_path / "emulator", install=lambda home, **k: fake_install(home, gate=gate, **k))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("accept")                                  # A on the Vita3K card
    assert window.busy
    window.refresh()
    assert window.status.text() == f"Downloading Vita3K build {emulator.VERSION}… 12 of 25 MB"
    assert ("A", "Install") not in window.legend.items
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.on_action("view")                                    # Exit asks first while it downloads
    assert closed == [] and window.legend.items == [(VIEW, "Press again to exit")]
    assert window.status.text() == "Press View again to exit: the download stops."
    gate.set()
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == f"Vita3K build {emulator.VERSION} is installed."
    assert window.legend.items == [("X", "Remove Vita3K"), ("LB", "Firmware"), ("RB", "Install a game"), MENU_INFO,
                                   EXIT]
    config = userdata.read_map(userdata.config_path(tmp_path / "emulator"))   # prepared before its first start
    assert config == {"boot-apps-full-screen": "true", "show-welcome": "false", "check-for-updates-mode": "0"}
    window.on_action("view")
    assert closed == [True]                                     # nothing runs: View exits at once


def test_a_failed_install_says_why(qapp, tmp_path):
    def failing(home, **kwargs):
        raise emulator.EmulatorError("the archive has no Vita3K.exe")
    window = make(qapp, tmp_path / "emulator", install=failing)
    window.act("accept")
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == "Vita3K could not be installed: the archive has no Vita3K.exe"
    assert ("A", "Install") in window.legend.items
    window.close()


def test_update_and_remove_with_x_pressed_twice(qapp, tmp_path):
    home = tmp_path / "emulator"
    fake_install(home, version="4100", firmware=True)
    save = fs(home) / "ux0" / "user" / "00" / "savedata" / "PCSB00245" / "sdslot.dat"
    save.parent.mkdir(parents=True)
    save.write_bytes(b"x")
    window = make(qapp, home)
    assert window.legend.items == [("X", "Remove Vita3K"), ("Y", "Update"), ("LB", "Firmware"),
                                   ("RB", "Install a game"), MENU_INFO, EXIT]
    assert window.status.text() == f"This app installs Vita3K build {emulator.VERSION}: the Y button updates it."
    window.act("y")
    assert wait_for(qapp, lambda: not window.busy) and emulator.installed(home) == emulator.VERSION
    window.legend.entries["X"].pressed.emit()                   # a tap on X Remove Vita3K
    assert window.legend.items[0] == ("X", "Press again") and emulator.installed(home)
    assert window.status.text().startswith("Press the X button again")
    window._confirm_over()                                      # five seconds without a second press
    assert window.legend.items[0] == ("X", "Remove Vita3K")
    window.act("x")
    window.act("x")
    assert emulator.installed(home) == "" and save.is_file() and userdata.firmware(fs(home)).ready
    assert "stays" in window.status.text() and window.legend.items[0] == ("A", "Install")
    window.close()


def test_remove_while_vita3k_runs_says_so(qapp, tmp_path):
    home = tmp_path / "emulator"
    ready(home)
    window = make(qapp, home, running=lambda h: True)
    window.act("x")
    window.act("x")
    assert emulator.installed(home) and window.status.text().startswith("Vita3K is open")
    assert userdata.config_path(home).exists() is False         # nothing written while it runs
    window.close()


def test_the_runtime_and_the_firmware_are_asked_for(qapp, tmp_path):
    home = tmp_path / "emulator"
    fake_install(home)                                                      # no firmware yet
    window = make(qapp, home, runtime_missing=lambda: ["msvcp140.dll"])
    assert window.status.text().startswith("Vita3K needs Microsoft's Visual C++ runtime (msvcp140.dll missing")
    window.close()
    window = make(qapp, home)
    assert window.status.text().startswith("Vita3K needs the PS Vita's firmware and its font package")
    install_firmware(fs(home), fonts=False)
    window.read_vita3k()
    assert dict(window.rows())["Firmware"] == "no font package"
    install_firmware(fs(home), preinstalled=True)
    window.read_vita3k()
    window.refresh()
    assert dict(window.rows())["Firmware"] == "installed, with the preinstalled apps" and window.status.text() == ""
    window.close()


def test_a_newer_build_is_shown(qapp, tmp_path):
    """GitHub asked off the window's thread (the BC250 app's notice): a newer build is a row of the pane, never
    installed."""
    home = tmp_path / "emulator"
    ready(home)
    window = make(qapp, home, newer_release=lambda: ReleaseInfo("4242", "4242", "https://x/4242", "2026-10-29"))
    assert wait_for(qapp, lambda: window.newer is not None)
    assert dict(window.rows())["Newest build"].startswith("4242 (2026-10-29): a later version of this app brings it")
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
    assert window.settings_pane.status.text() == "Install Vita3K first: the settings are in its folder."
    assert window.legend.items[:3] == [("A", "Change"), ("LB", "Previous tab"), ("RB", "Next tab")]
    window.settings_pane.status.setText("")
    window.settings_pane.pills["renderer"].click()                                 # never grayed out: says why
    assert window.settings_pane.status.text() == "Install Vita3K first: the settings are in its folder."
    window.on_action("down")
    assert window.log_card.hasFocus() and window.panes.currentWidget() is window.log_pane
    for card in (window.vita3k_card, window.games_card, window.settings_card, window.log_card):
        card.setFocus()
        qapp.processEvents()
        assert no_pills(window)
    window.close()


def test_the_settings_step_and_are_written_at_once(qapp, tmp_path, monkeypatch):
    home = tmp_path / "emulator"
    ready(home)
    is_running = [False]
    window = make(qapp, home, running=lambda h: is_running[0])
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    pills = window.settings_pane.pills
    assert pills["renderer"].label.text() == "Renderer: Vulkan"                    # Vita3K's default
    window.settings_card.setFocus()
    window.on_action("accept")                                                     # A on the card: the first row
    assert pills["renderer"].hasFocus()
    window.on_action("accept")
    assert pills["renderer"].label.text() == "Renderer: OpenGL"
    config = userdata.config_path(home)
    assert "backend-renderer: OpenGL" in config.read_text(encoding="utf-8").splitlines()
    pills["scale"].click()
    assert pills["scale"].label.text() == "Resolution: 1.5x (816p)"
    is_running[0] = True                                                           # Vita3K is open
    window.settings_pane.tabs.select("system")
    pills["enter"].click()
    assert window.settings_pane.status.text().startswith("Vita3K is open")
    assert pills["enter"].label.text() == "Confirm button: Cross (X)"
    is_running[0] = False
    pills["enter"].click()
    assert pills["enter"].label.text() == "Confirm button: Circle (O)"
    assert "sys-button: 0" in config.read_text(encoding="utf-8").splitlines()
    window.close()


def test_the_settings_are_in_tabs(qapp, tmp_path, monkeypatch):
    """LB and RB step through Picture, Speed, Sound and System; the focus follows to the tab's first row; the
    information tells the tab's settings; every tab's rows fit the pane."""
    from vita3k_manager.vita3k_settings import TABS
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    pane = window.settings_pane
    assert [key for key, _, _ in TABS] == ["picture", "speed", "sound", "system"] == pane.tabs.keys
    assert pane.tabs.current == "picture" and pane.pills["vsync"].isVisibleTo(pane)
    assert not pane.pills["fps"].isVisibleTo(pane) and "Renderer:" in pane.info.info
    assert "The A button changes" in pane.info.info
    window.settings_card.setFocus()
    window.on_action("accept")
    assert pane.pills["renderer"].hasFocus()
    window.on_action("next")                                                       # RB: the next tab
    assert pane.tabs.current == "speed" and pane.pills["accuracy"].hasFocus() and "FPS hack:" in pane.info.info
    window.on_action("previous")
    window.on_action("previous")                                                   # LB twice: round to the last
    assert pane.tabs.current == "system" and pane.pills["enter"].hasFocus()
    assert pane.pills["language"].isVisibleTo(pane)
    assert pane.minimumSizeHint().height() <= window.panes.height()
    window.close()


def test_a_long_folder_wraps_and_the_window_stays_on_the_screen(qapp, tmp_path):
    deep = tmp_path / ("a-rather-long-folder-name" * 3) / "windows-portable-suite" / "windows-portable-vita3k" / "emulator"
    window = make(qapp, deep)
    assert window.minimumSizeHint().width() <= 1280 and window.width() == 1280
    assert window.panes.minimumSizeHint().width() < 800
    window.close()


def test_the_window_fits_a_smaller_screen(qapp, tmp_path):
    # It adapts to the screen it is on (a 1080p screen at 175 % is 1097 x 617), as every app of the suite.
    portable.pin_scale((1097, 617))
    try:
        window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False), steam_dir=None,
                            home=tmp_path / "emulator", roots=lambda: [], runtime_missing=lambda: [])
        window.resize(1097, 617)
        window.show()
        qapp.processEvents()
        assert window.minimumSizeHint().height() <= 617
        window.close()
    finally:
        portable.pin_scale((1280, 720))


def test_the_firmware_is_installed_by_vita3k_without_its_window(qapp, tmp_path, monkeypatch):
    """LB Firmware opens the browser in Downloads with the .PUP files; A on one runs Vita3K with --firmware (stood in
    for: it writes the files Vita3K would), and the Vita3K pane names the parts it wrote."""
    home = tmp_path / "emulator"
    fake_install(home)
    user = tmp_path / "me"
    (user / "Downloads").mkdir(parents=True)
    pup = user / "Downloads" / "PSP2UPDAT.PUP"
    pup.write_bytes(b"pup")
    (user / "Downloads" / "notes.txt").write_text("")
    runs = []

    def run_quiet(home_, *args):
        runs.append(args)
        install_firmware(fs(home_))
        return 0
    window = make(qapp, home, user_home=user, run_quiet=run_quiet)
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
    assert window.status.text().startswith("Vita3K installs PSP2UPDAT.PUP, without its window")
    assert wait_for(qapp, lambda: not window.busy)
    assert runs == [("--firmware", str(pup))]
    assert window.status.text() == "PSP2UPDAT.PUP: the system software and the font package installed."
    assert dict(window.rows())["Firmware"] == "installed" and window.firmware.ready
    window.close()


def test_a_file_vita3k_cannot_use_is_said(qapp, tmp_path):
    home = tmp_path / "emulator"
    fake_install(home)
    window = make(qapp, home)
    window.install_firmware(tmp_path / "x.pup")                 # Vita3K quits and writes nothing
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == ("Vita3K did not install x.pup: nothing of the firmware was written. Is it one of "
                                    "the PS Vita's PSP2UPDAT.PUP files?")
    window.close()


def test_a_vpk_is_installed_and_vita3k_closed_before_the_game(qapp, tmp_path, monkeypatch):
    """RB Install a game opens the browser with the .vpk, .zip and .pkg files; A on a .vpk gives it to Vita3K (stood
    in for: it installs the game and the app closes it), and the game shows in Your games."""
    home = tmp_path / "emulator"
    ready(home)
    user = tmp_path / "me"
    (user / "Downloads").mkdir(parents=True)
    vpk = user / "Downloads" / "Persona.vpk"
    vpk.write_bytes(b"PK")
    (user / "Downloads" / "Game.pkg").write_bytes(b"\x7fPKG")
    (user / "Downloads" / "readme.txt").write_text("")
    installs = []

    def install_content(home_, content):
        installs.append(content)
        make_game(fs(home_), "Persona 4 Golden", "PCSB00245", pictures=True)
        return True
    window = make(qapp, home, user_home=user, install_content=install_content)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("next")                                    # RB Install a game
    assert window.panes.currentWidget() is window.browse_pane
    assert window.browse_pane.heading.text() == "Choose a game to install"
    assert window.legend.items == [("A", "Open"), ("X", "Install this folder"), MENU_INFO, BACK, EXIT]
    rows = window.browse_pane.list.pills
    assert sorted(k for k in rows if k.startswith("file:")) == sorted(f"file:{user / 'Downloads' / n}"
                                                                     for n in ("Game.pkg", "Persona.vpk"))
    rows[f"file:{vpk}"].click()
    assert window.busy and window.status.text().startswith("Vita3K installs Persona.vpk…")
    assert wait_for(qapp, lambda: not window.busy)
    assert installs == [vpk]
    assert window.status.text() == "Installed in Vita3K: Persona 4 Golden (PCSB00245)."
    assert dict(window.rows())["Games"] == "1"
    window.games_card.setFocus()
    qapp.processEvents()
    assert [p.label.text() for p in window.games_pane.list.pills.values()] == [
        "Persona 4 Golden  ·  PCSB00245  ·  1.00"]
    window.close()


def test_a_dumped_folder_is_installed_with_x(qapp, tmp_path, monkeypatch):
    home = tmp_path / "emulator"
    ready(home)
    user = tmp_path / "me"
    dump = user / "Downloads" / "PCSE00001"
    (dump / "sce_sys").mkdir(parents=True)
    (dump / "sce_sys" / "param.sfo").write_bytes(b"\0PSF")
    installs = []

    def install_content(home_, content):
        installs.append(content)
        make_game(fs(home_), "Update", "PCSE00001", kind="patch")
        return False                                            # an update starts no game: Vita3K ends by itself
    window = make(qapp, home, user_home=user, install_content=install_content)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("next")
    window.on_action("x")                                       # the Downloads folder is open, not the game's
    assert window.browse_pane.status.text().startswith("No PS Vita game in Downloads: open the game's own folder")
    assert installs == [] and not window.busy
    window.browse_pane.list.pills[f"dir:{dump}"].click()
    window.on_action("x")
    assert wait_for(qapp, lambda: not window.busy)
    assert installs == [dump]
    assert window.status.text() == "Installed in Vita3K: an update for PCSE00001."
    window.close()


def test_x_in_the_browser_needs_an_open_folder(qapp, tmp_path, monkeypatch):
    home = tmp_path / "emulator"
    ready(home)
    window = make(qapp, home, user_home=tmp_path / "nobody")    # no Downloads: the browser starts at the places
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("next")
    window.on_action("x")
    assert window.browse_pane.status.text() == OPEN_A_FOLDER and not window.busy
    window.on_action("back")                                    # B at the places: back to the Vita3K pane
    assert window.panes.currentWidget() is window.pane and window.browser is None
    window.close()


def test_nothing_installed_is_said(qapp, tmp_path):
    home = tmp_path / "emulator"
    ready(home)
    window = make(qapp, home, install_content=lambda home_, content: True)
    window.install_game(tmp_path / "Vitamin.vpk")
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text().startswith("Vita3K installed nothing from Vitamin.vpk: is it a PS Vita game")
    failing = make(qapp, home, install_content=lambda h, c: (_ for _ in ()).throw(
        emulator.EmulatorError("Vita3K did not finish installing Big.vpk in 15 minutes")))
    failing.install_game(tmp_path / "Big.vpk")
    assert wait_for(qapp, lambda: not failing.busy)
    assert failing.status.text() == ("Vita3K could not install Big.vpk: Vita3K did not finish installing Big.vpk in "
                                     "15 minutes")
    window.close()
    failing.close()


def test_a_package_is_installed_with_its_pasted_license(qapp, tmp_path, monkeypatch):
    """A on a .pkg asks for its license key on a page of its own (X pastes it, B goes back to the folder); A installs
    it through Vita3K without its window, the key on its command line and in no log line."""
    from PyQt6.QtGui import QGuiApplication
    home = tmp_path / "emulator"
    ready(home)
    user = tmp_path / "me"
    (user / "Downloads").mkdir(parents=True)
    pkg = user / "Downloads" / "Game.pkg"
    pkg.write_bytes(b"\x7fPKG")
    runs = []

    def run_quiet(home_, *args):
        runs.append(args)
        make_game(fs(home_), "Gravity Rush", "PCSA00011")
        return 0
    window = make(qapp, home, user_home=user, run_quiet=run_quiet)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    logged = []
    monkeypatch.setattr(window.log, "info", lambda text: logged.append(text))
    window.on_action("next")
    window.browse_pane.list.pills[f"file:{pkg}"].click()        # A on the .pkg: its license's page
    pane = window.zrif_pane
    assert window.panes.currentWidget() is pane and pane.field.hasFocus()
    assert pane.heading.text() == "The license of Game.pkg"
    assert window.legend.items == [("A", "Install"), ("X", "Paste"), KEYBOARD, BACK, EXIT]
    window.on_action("back")                                    # B: the folder again, nothing installed
    assert window.panes.currentWidget() is window.browse_pane and window.browser.path == user / "Downloads"
    window.browse_pane.list.pills[f"file:{pkg}"].click()
    window.on_action("accept")                                  # empty: says why
    assert "empty" in pane.status.text() and runs == []
    pane.field.setText("not a key")
    window.on_action("accept")
    assert "no zRIF" in pane.status.text()
    QGuiApplication.clipboard().setText("  KO5ifR1dQ+eHBlOi4mY2h6aW0=  \n")
    window.on_action("x")                                       # X Paste
    assert pane.field.text() == "KO5ifR1dQ+eHBlOi4mY2h6aW0="
    window.on_action("accept")                                  # A Install
    assert window.panes.currentWidget() is window.pane and pane.field.text() == ""
    assert wait_for(qapp, lambda: not window.busy)
    assert runs == [("--pkg", str(pkg), "--zrif", "KO5ifR1dQ+eHBlOi4mY2h6aW0=")]
    assert window.status.text() == "Installed in Vita3K: Gravity Rush (PCSA00011)."
    assert not any("KO5i" in text for text in logged)
    window.close()


def test_a_package_with_the_wrong_license_is_said(qapp, tmp_path):
    home = tmp_path / "emulator"
    ready(home)
    window = make(qapp, home)
    window.install_package(tmp_path / "Game.pkg", "KO5iwrong")
    assert wait_for(qapp, lambda: not window.busy)
    assert window.status.text() == "Vita3K did not install Game.pkg: is the license key the package's own?"
    window.close()


def test_view_while_vita3k_installs_asks_first(qapp, tmp_path, monkeypatch):
    home = tmp_path / "emulator"
    ready(home)
    gate = threading.Event()
    window = make(qapp, home, install_content=lambda h, c: gate.wait(10))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.install_game(tmp_path / "Game.vpk")
    window.on_action("view")
    assert closed == [] and window.status.text().startswith("Press View again to exit: Vita3K goes on installing")
    window.on_action("next")                                    # busy: RB says so
    gate.set()
    assert wait_for(qapp, lambda: not window.busy)


def test_your_games_are_marked_with_a_and_put_in_steam(qapp, tmp_path, monkeypatch):
    """The games are played from Steam (owner, 29-10-2026): A on a game is its Steam mark, Y Update Steam writes the
    marks, X plays a game that is in Steam through Steam (steam://rungameid); Steam's library is the portal's (owner,
    30-10-2026: no Open Steam row)."""
    home = tmp_path / "emulator"
    ready(home)
    persona = make_game(fs(home), "Persona 4 Golden", "PCSB00245", pictures=True)
    make_game(fs(home), "Gravity Rush", "PCSA00011")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    closed = []

    def with_steam_closed(change):
        closed.append(True)
        change()
        return False
    played = []
    window = make(qapp, home, steam_dir=steam_dir, steam_closed=with_steam_closed, play=played.append)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    qapp.processEvents()
    assert window.legend.items == [("A", "Steam mark"), ("Y", "Update Steam"), ("RB", "Steam artwork"), MENU_INFO,
                                   EXIT]
    window.on_action("accept")                                     # into the list
    assert not hasattr(window, "steam_row")
    assert "Press the A button on a game to mark it for Steam" in window.games_pane.info.info
    assert window.games_pane.summary.text() == "2 game(s) installed in Vita3K, 0 in Steam"
    pills = window.games_pane.list.pills
    assert [pill.label.text() for pill in pills.values()] == ["Gravity Rush  ·  PCSA00011  ·  1.00",
                                                              "Persona 4 Golden  ·  PCSB00245  ·  1.00"]
    window.legend.entries["Y"].pressed.emit()                      # a tap on Y Update Steam: nothing to change yet
    assert window.games_pane.status.text() == NOTHING_TO_CHANGE
    pills["PCSB00245"].setFocus()
    qapp.processEvents()
    assert ("X", "Play") in window.legend.items
    window.on_action("x")                                          # X: not in Steam yet
    assert window.games_pane.status.text() == ("Persona 4 Golden is not in Steam yet: A marks it, then Y Update "
                                               "Steam puts it there.") and played == []
    window.on_action("accept")                                     # A: the Steam mark
    assert "✓ Steam (Update Steam)" in window.games_pane.list.pills["PCSB00245"].label.text()
    assert window.games_pane.list.pills["PCSB00245"].hasFocus()
    window.on_action("y")                                          # Y on Your games: Update Steam
    assert wait_for(qapp, lambda: not window.busy)
    assert closed == [True] and shortcuts.in_steam(steam_dir) == {"PCSB00245": "[PS Vita] Persona 4 Golden"}
    assert "1 game(s) in Steam" in window.games_pane.status.text() and "Read back" not in window.games_pane.status.text()
    assert window.games_pane.list.pills["PCSB00245"].label.text().endswith("✓ Steam")
    item = next(i for i in steam.shortcuts(steam_dir) if i.get("AppName"))
    launcher, before = play.launcher(ROOT)                         # the play mode (owner, 30-10-2026)
    assert item["LaunchOptions"] == play.launch_options(before, "-r PCSB00245") and item["Exe"] == f'"{launcher}"'
    assert item["icon"] == str(persona / "sce_sys" / "icon0.png")
    window.games_pane.list.pills["PCSB00245"].setFocus()
    window.on_action("x")                                          # X: played through Steam
    number = shortcuts.numbers(steam_dir)["PCSB00245"]
    assert played[-1] == f"steam://rungameid/{(number << 32) | 0x02000000}"
    assert number == steam.appid(item["Exe"], item["AppName"]) & 0xFFFFFFFF
    assert window.games_pane.status.text() == ("Starting Persona 4 Golden in Steam… In the game, hold View, LB and "
                                               "RB together to quit.")    # how to quit, on the screen
    window.games_pane.list.pills["PCSB00245"].click()              # the mark off, and Steam again: taken out
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy) and shortcuts.in_steam(steam_dir) == {}
    window.close()


def test_without_steam_x_starts_the_game_in_vita3k(qapp, tmp_path, monkeypatch):
    """A device without Steam (owner, 30-10-2026: a fallback): X starts Vita3K with the game full screen, as its
    shortcut would, from Vita3K's folder; without Vita3K it says to install it first."""
    home = tmp_path / "emulator"
    ready(home)
    make_game(fs(home), "Persona 4 Golden", "PCSB00245")
    started, played = [], []
    window = make(qapp, home, start=lambda command, cwd=None: started.append((command, cwd)), play=played.append)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    window.on_action("accept")
    window.games_pane.list.pills["PCSB00245"].setFocus()
    qapp.processEvents()
    assert ("X", "Play") in window.legend.items
    window.on_action("x")
    program = emulator.program(home)
    launcher, before = play.launcher(ROOT)                      # the play mode, as the shortcut would start it
    assert started == [([launcher, *before, "-r", "PCSB00245"], program.parent)]
    assert played == [] and window.games_pane.status.text() == ("Starting Persona 4 Golden in Vita3K… In the game, "
                                                                "hold View, LB and RB together to quit.")

    def fails(command, cwd=None):
        raise PermissionError(13, "Access is denied")
    window.start_program = fails
    window.on_action("x")
    assert window.games_pane.status.text() == "Vita3K could not start Persona 4 Golden: Access is denied"
    program.unlink()                                              # Vita3K gone
    window.on_action("x")
    assert window.games_pane.status.text() == ("Install Vita3K first: it starts Persona 4 Golden on a device without "
                                               "Steam.")
    assert len(started) == 1
    window.close()


def test_update_steam_needs_vita3k_and_its_firmware(qapp, tmp_path, monkeypatch):
    home = tmp_path / "emulator"
    fake_install(home)                                             # no firmware
    make_game(fs(home), "A", "PCSB00001")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    window = make(qapp, home, steam_dir=steam_dir)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    window.games_pane.list.first().setFocus()
    qapp.processEvents()
    window.on_action("accept")
    window.on_action("y")
    assert window.games_pane.status.text() == NO_FIRMWARE and not window.busy
    window.close()


def test_a_game_written_but_not_read_back_is_said_and_logged(qapp, tmp_path, monkeypatch):
    from vita3k_manager import library
    home = tmp_path / "emulator"
    ready(home)
    make_game(fs(home), "A", "PCSB00001")
    steam_dir = tmp_path / "Steam"
    (steam_dir / "userdata" / "1" / "config").mkdir(parents=True)
    monkeypatch.setattr(library, "update_steam", lambda *a, **k: (True, "1 game(s) in Steam.", {}))
    window = make(qapp, home, steam_dir=steam_dir)
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


def test_y_on_your_games_always_says_what_it_did(qapp, tmp_path, monkeypatch):
    home = tmp_path / "emulator"
    ready(home)
    make_game(fs(home), "A", "PCSB00001")
    window = make(qapp, home)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    window.games_pane.list.first().setFocus()
    qapp.processEvents()
    window.on_action("accept")
    window.on_action("y")                                          # a game marked, but no Steam on this device
    assert window.games_pane.status.text() == NO_STEAM and not window.busy
    window.close()


def test_the_log_is_read_in_the_app(qapp, tmp_path, monkeypatch):
    """The Log pane shows Vita3K's folder and the newest lines; A (or a tap on the pane) shows the whole log in the
    app, the d-pad scrolls it and B goes back (owner, 29-10-2026: Notepad has no button to close it)."""
    home = tmp_path / "emulator"
    ready(home)
    make_game(fs(home), "A", "PCSB00001")
    log = tmp_path / "app.log"
    log.write_text("".join(f"line {n}\n" for n in range(300)), encoding="utf-8")
    window = make(qapp, home)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.log_path = log
    window.log_card.setFocus()
    qapp.processEvents()
    texts = [label.text() for label in window.log_pane.findChildren(type(window.status))]
    assert "Firmware" in texts and "installed" in texts and "Installed games" in texts and "1" in texts
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
    r"""The BC250 app's Covers… key, as the suite's other apps have it on a page: one key for the suite in
    %APPDATA%\windows-portable-suite\steamgriddb-key, X Paste from the clipboard, A Save, Y Remove key with a second
    press, B back without saving, the page on RB."""
    from bc250_core import covers
    from PyQt6.QtGui import QGuiApplication
    from vita3k_manager import library
    key_file = library.key_file()
    assert key_file == tmp_path / "Roaming" / "windows-portable-suite" / "steamgriddb-key"
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.games_card.setFocus()
    qapp.processEvents()
    window.on_action("next")                                    # RB Steam artwork
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


def test_menu_shows_the_panes_information_and_the_icon_is_touch_only(qapp, tmp_path, monkeypatch):
    """Menu (☰ Info in the legend) opens the information of the pane that shows, and closes it again; the icon
    itself is never on the d-pad's way, so A in a pane is always its own action (owner, 29-10-2026)."""
    window = make(qapp, tmp_path / "emulator")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.vita3k_card.setFocus()
    qapp.processEvents()
    assert window.vita3k_info not in window.focusables()
    window.on_action("menu")                                    # the Vita3K pane's information: the firmware, games
    assert window.popup is not None and "PSP2UPDAT.PUP" in window.popup.text.toPlainText()
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


def test_no_path_on_the_screen_shows_the_users_name(qapp):
    """The privacy rule (owner, 29-10-2026): Vita3K's folder shows the user's folders by their variable
    (%LOCALAPPDATA%), never the user's name."""
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    home = local / "windows-portable-suite" / "windows-portable-vita3k" / "emulator"
    user = Path(os.environ.get("USERPROFILE") or Path.home())
    window = make(qapp, home)
    window.log_card.setFocus()
    qapp.processEvents()
    shown = [value for _label, value in window.rows()] + [label.text() for label in
                                                          window.log_pane.findChildren(type(window.status))]
    assert not any(str(user).lower() in text.replace("​", "").lower() for text in shown if text)
    window.close()


def test_the_browser_opens_where_it_was_left(qapp, tmp_path, monkeypatch):
    """Owner, 29-10-2026: a file picked in a folder, the next browser of its kind opens in that folder."""
    home = tmp_path / "emulator"
    ready(home)
    user = tmp_path / "me"
    folder = user / "Downloads" / "vita"
    folder.mkdir(parents=True)
    (folder / "Persona.vpk").write_bytes(b"PK")
    window = make(qapp, home, user_home=user)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("next")                                    # RB Install a game: Downloads
    assert window.browser.path == user / "Downloads"
    window.browse_pane.list.pills[f"dir:{folder}"].click()
    window.browse_pane.list.pills[f"file:{folder / 'Persona.vpk'}"].click()
    assert wait_for(qapp, lambda: not window.busy)
    window.vita3k_card.setFocus()
    window.on_action("next")
    assert window.browser.path == folder
    window.close()


def test_a_shortcut_made_before_the_play_mode_asks_for_update_steam(qapp, tmp_path, monkeypatch):
    """A game whose shortcut still starts Vita3K itself (1.0.1's) says (Update Steam), and Y brings it to the play
    mode (owner, 30-10-2026: View, LB and RB held quit every game)."""
    home = tmp_path / "emulator"
    ready(home)
    make_game(fs(home), "Persona 4 Golden", "PCSB00245")
    steam_dir = tmp_path / "Steam"
    config = steam_dir / "userdata" / "1" / "config"
    config.mkdir(parents=True)
    program = emulator.program(home)
    old = steam.shortcut_entry(f'"{program}"', "[PS Vita] Persona 4 Golden", f'"{program.parent}"', "",
                               "-r PCSB00245", shortcuts.TAGS)
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": old}}))

    def with_steam_closed(change):
        change()
        return False
    window = make(qapp, home, steam_dir=steam_dir, steam_closed=with_steam_closed)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert window.games_pane.list.pills["PCSB00245"].label.text().endswith("✓ Steam (Update Steam)")
    window.games_card.setFocus()
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy)
    assert shortcuts.outdated(steam_dir) == set() and len(steam.shortcuts(steam_dir)) == 1
    assert window.games_pane.list.pills["PCSB00245"].label.text().endswith("✓ Steam")
    window.close()


def test_play_runs_the_game_without_a_window(monkeypatch, tmp_path):
    """--play, as a shortcut starts the app: Vita3K with the shortcut's arguments from its folder, through core's
    play mode, before any window or the one-window check (the app's window may be open beside it)."""
    from vita3k_manager import __main__ as entry
    ran = []
    monkeypatch.setattr(emulator, "emulator_home", lambda: tmp_path / "emulator")
    monkeypatch.setattr(entry.applog, "setup", lambda *a, **k: tmp_path / "log")
    monkeypatch.setattr(entry.play, "run", lambda command, cwd, log: ran.append((command, cwd)) or 3)
    monkeypatch.setattr(entry, "create_app", lambda *a, **k: pytest.fail("no window in the play mode"))
    monkeypatch.setattr(sys, "argv", ["Vita3K-Manager.exe", "--play", "-r", "PCSB00245"])
    assert entry.main() == 3
    program = emulator.program(tmp_path / "emulator")
    assert ran == [([str(program), "-r", "PCSB00245"], program.parent)]

    def fails(command, cwd, log):
        raise FileNotFoundError(2, "The system cannot find the file specified")
    monkeypatch.setattr(entry.play, "run", fails)
    assert entry.main() == 1
