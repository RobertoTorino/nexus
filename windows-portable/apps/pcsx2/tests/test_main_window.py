# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py): it opens on the portable window with the header's battery, date and time, fits the
handheld's screen, and B closes it; PCSX2 installed on A (off the window's thread, the megabytes counted, B asking
first meanwhile, its settings prepared after), opened, reinstalled after PCSX2 replaced itself, and removed with a
second press; the Settings pane's pills step through their values, never while PCSX2 runs; the version and the
icons are where the checks expect them."""

from __future__ import annotations

import re
import threading
import time

from bc250_core import portable
from bc250_core.gamepad import Gamepad
from pcsx2_manager import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, emulator
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


def make(qapp, home=None, install=fake_install, start=lambda home: None, running=lambda home: False):
    window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False), home=home,
                        install=install, start=start, running=running)
    portable.scale((1280, 720))
    window.resize(1280, 720)
    window.show()
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
    assert window.settings_card.hasFocus() and window.panes.currentWidget() is window.settings_pane
    assert not window.settings_pane.pills["renderer"].isEnabled()                  # nothing installed yet
    assert window.settings_pane.status.text() == "Install PCSX2 first: the settings are in its folder."
    window.on_action("up")
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
