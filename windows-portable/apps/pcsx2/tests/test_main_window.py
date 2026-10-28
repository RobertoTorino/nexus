# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py): it opens on the portable window with the header's battery, date and time, fits the
handheld's screen, and B closes it; PCSX2 installed on A (off the window's thread, the megabytes counted, B asking
first meanwhile, its settings prepared after), opened, reinstalled after PCSX2 replaced itself, and removed with a
second press; the Settings pane's pills step through their values, never while PCSX2 runs; the version and the
icons are where the checks expect them."""

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
from pcsx2_manager.main_window import MainWindow


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


def make(qapp, home=None, install=fake_install, start=lambda home: None, running=lambda home: False, **more):
    more.setdefault("steam_dir", None)                  # never the real Steam
    more.setdefault("drives", lambda: [])
    more.setdefault("settings", QSettings(str(Path(tempfile.mkdtemp()) / "app.ini"),
                                          QSettings.Format.IniFormat))   # never Windows' registry
    window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False), home=home,
                        install=install, start=start, running=running, **more)
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
    assert window.legend.items == [("B", "Close")]
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
    assert not window.other.isVisible() and not window.remove_pill.isVisible()
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
    assert window.status.text() == f"PCSX2 {emulator.VERSION} is installed." and window.legend.items == [("B", "Close")]
    assert window.main.label.text() == "Open PCSX2" and window.remove_pill.isVisible()
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
    started = []
    window = make(qapp, home, start=started.append)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert window.main.label.text() == "Open PCSX2" and not window.other.isVisible()
    window.main.click()
    assert started == [home]
    emulator.program(home).write_bytes(b"another build")         # PCSX2's own updater
    window.refresh()
    assert window.other.isVisible() and window.other.label.text() == "Reinstall"
    assert "replaced itself" in window.status.text()
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.busy) and not emulator.replaced(home)
    window.remove_pill.click()
    assert window.remove_pill.label.text() == "Press again to remove" and emulator.installed(home)
    window._confirm_over()                                      # five seconds without a second press
    assert window.remove_pill.label.text() == "Remove"
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
    assert not window.settings_pane.pills["renderer"].isEnabled()                  # nothing installed yet
    assert window.settings_pane.status.text() == "Install PCSX2 first: the settings are in its folder."
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
    assert "Cross = SDL-0/FaceSouth" in ini and "StartBigPictureMode = true" in ini
    window.close()


def test_the_settings_step_and_are_written_at_once(qapp, tmp_path, monkeypatch):
    home = tmp_path / "emulator"
    fake_install(home)
    is_running = [False]
    window = make(qapp, home, running=lambda h: is_running[0])
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    pills = window.settings_pane.pills
    assert pills["renderer"].label.text() == "Renderer: Automatic"
    assert pills["bigpicture"].label.text() == "Big Picture: On" and pills["quit"].label.text().endswith(": On")
    window.settings_card.activated.emit()                                          # A on the card: the first pill
    assert pills["renderer"].hasFocus()
    pills["renderer"].click()
    assert pills["renderer"].label.text() == "Renderer: Direct3D 12"
    assert "Renderer = 15" in (home / "inis" / "PCSX2.ini").read_text(encoding="utf-8")
    pills["bigpicture"].click()
    assert pills["bigpicture"].label.text() == "Big Picture: Off"
    is_running[0] = True                                                           # PCSX2 is open
    pills["fps"].click()
    assert window.settings_pane.status.text().startswith("PCSX2 is open") and pills["fps"].label.text() == "Show FPS: Off"
    window.main.click()
    assert window.status.text() == "PCSX2 is open already."
    window.close()


def test_the_settings_info_is_behind_the_icon(qapp):
    window = make(qapp)
    info = window.settings_pane.info
    assert info.title == "PCSX2's settings" and "Big Picture:" in info.info and "Renderer:" in info.info
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
    assert window.legend.items == [("X", "Steam mark"), ("Y", "Update Steam"), ("B", "Close")]
    assert window.games_pane.list.pills == {} and "Folders adds" in window.games_pane.status.text()
    window.folders_pill.click()                                    # the folders: the usual places, and Choose
    assert window.legend.items == [("B", "Close")] and not window.steam_pill.isVisible()
    pills = window.games_pane.list.pills
    assert list(pills) == [f"add:{games}", f"add:{user / 'Downloads'}", "choose"]
    pills[f"add:{games}"].click()
    assert "1 game(s) in it" in window.games_pane.status.text()
    window.games_pane.list.pills["choose"].click()                 # Windows' folder window, stood in for
    window.folders_pill.click()                                    # back to the games
    pills = window.games_pane.list.pills
    lumines = str(games / "PS2" / "SLUS_215.53.Lumines.iso")
    assert pills[lumines].label.text() == "Lumines Plus  ·  SLUS-21553" and len(pills) == 2
    pills[lumines].click()                                         # A plays it
    assert played == [Path(lumines)] and "starts in PCSX2" in window.games_pane.status.text()
    assert not window.steam_pill.isEnabled()                       # nothing to change in Steam yet
    window.games_pane.list.pills[lumines].setFocus()
    qapp.processEvents()
    window.on_action("x")                                          # X marks it for Steam
    assert "✓ Steam (Update Steam)" in window.games_pane.list.pills[lumines].label.text()
    assert window.steam_pill.isEnabled()
    window.on_action("y")                                          # Y on Your games: Update Steam
    assert wait_for(qapp, lambda: not window.busy)
    assert closed == [True] and shortcuts.in_steam(steam_dir) == {lumines: "[PS2] Lumines Plus"}
    assert "1 game(s) in Steam" in window.games_pane.status.text()
    assert window.games_pane.list.pills[lumines].label.text().endswith("✓ Steam")
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
    window.copy_card_pill.click()
    assert (cards / "mc01 copy.ps2").is_file() and "is copied to mc01 copy.ps2" in window.cards_pane.status.text()
    window.new_card_pill.click()
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
