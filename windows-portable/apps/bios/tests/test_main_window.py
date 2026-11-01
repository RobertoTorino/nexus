# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py): it opens on the portable window with the header's battery, date and time, fits the
handheld's screen, B goes back and View exits; the BIOS file card picks a file in core's browser and reads it; the
Setup screens card opens pages and menus (A, B, LB, RB, Y); This device reads its BIOS version, then its settings.
Fakes stand in for the device and Windows' prompt."""

from __future__ import annotations

import re

from PyQt6.QtCore import QSettings

from bc250_core import portable
from bc250_core.gamepad import Gamepad
from bc250_core.portable import EXIT, INFO as INFO_ITEM
from bios_reader import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, bios
from bios_reader.bios import Identity
from bios_reader.main_window import MainWindow

DEVICE = (Identity("Vendor Inc.", "P9.99", "01/02/2023"), "Handheld X")


class FakePad:
    def events(self):
        return []

    def close(self):
        pass

    def names(self):
        return []


def make(qapp, tmp_path, identify=lambda: DEVICE, read_settings=None):
    calls = []

    def read(keys, folder):
        calls.append(list(keys))
        return {keys[0]: bytes([0, 1, 0, 0, 0, 0, 0, 0])}, []
    window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False),
                        identify=identify, read_settings=read_settings or read,
                        settings=QSettings(str(tmp_path / "bios.ini"), QSettings.Format.IniFormat),
                        folder=tmp_path / "data", roots=lambda: [tmp_path / "files"], user_home=tmp_path / "home")
    # Slow steps run here at once instead of on a thread
    window.file_worker.start = lambda work: window.file_done(work()) or True
    window.device_worker.start = lambda work: window.device_done(work()) or True
    portable.scale((1280, 720))
    window.resize(1280, 720)
    window.show()
    qapp.processEvents()
    window.start()
    window.calls = calls
    return window


def pick(window, qapp, name):
    """The file browser: A on the card, then the files folder (the only place), then the file."""
    window.file_card.setFocus()
    window.act("accept")
    rows = dict((text, key) for key, text in window.browser.rows())
    window.browse_picked(next(key for text, key in rows.items() if "files" in text))
    window.browse_picked(next(key for key, text in window.browser.rows() if text == name))
    qapp.processEvents()


def test_the_window_opens_with_the_suites_header(qapp, tmp_path):
    window = make(qapp, tmp_path)
    assert window.header.title.text() == APP_NAME and window.header.version.text() == __version__
    assert re.fullmatch(r"\w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d  \|  82%", window.header.status.text())
    assert window.legend.items == [("A", "Pick a file"), INFO_ITEM, EXIT]
    assert window.file_card.hasFocus() and window.bios is None
    window.close()


def test_the_window_fits_the_handhelds_screen(qapp, tmp_path):
    window = make(qapp, tmp_path)
    assert window.minimumSizeHint().height() <= 720 and window.height() == 720
    window.close()


def test_b_goes_back_and_view_exits(qapp, tmp_path, monkeypatch):
    """The suite's buttons: B goes back (with nowhere to go, nothing happens) and View exits the app."""
    window = make(qapp, tmp_path)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("back")
    assert closed == []
    window.on_action("view")
    assert closed == [True]


def test_nothing_is_read_before_a_asks(qapp, tmp_path):
    asked = []
    window = make(qapp, tmp_path, identify=lambda: asked.append(True) or DEVICE)
    window.device_card.setFocus()
    qapp.processEvents()
    assert asked == [] and window.device_pane.rows() == [("BIOS", "Not read yet")]
    window.close()


def test_a_file_is_picked_and_read(qapp, tmp_path, update_zip):
    window = make(qapp, tmp_path)
    pick(window, qapp, update_zip.name)
    assert window.bios is not None and window.bios.name == "RC00XAAS.123"
    rows = dict(window.file_pane.rows())
    assert rows["File"] == "RC00XAAS.123" and rows["Version"] == "RC00XA.123"
    assert rows["Setup screens"] == "1 modules, 7 settings"
    assert rows["Hidden"] == "2 menus the BIOS hides, 1 no menu links to"
    assert window.file_card.text.text() == "RC00XAAS.123, RC00XA.123"
    assert window.file_pane.status.text().startswith("Read")
    assert window.screens_card.text.text() == "1 pages"
    window.file_card.setFocus()
    window.act("accept")
    assert window.browser.path == update_zip.parent                 # the browser opens where it was left
    window.close()


def test_a_file_that_is_no_bios(qapp, tmp_path):
    window = make(qapp, tmp_path)
    (tmp_path / "files").mkdir()
    (tmp_path / "files" / "notes.bin").write_bytes(b"\xff" * 64)
    window.file_worker.start = lambda work: _fail(window, work)
    pick(window, qapp, "notes.bin")
    assert window.bios is None and "could not be read" in window.file_pane.status.text()
    window.close()


def _fail(window, work):
    try:
        work()
    except Exception as error:  # noqa: BLE001
        window.file_failed(str(error))
    return True


def test_the_setup_screens(qapp, tmp_path, bios_file):
    window = make(qapp, tmp_path)
    window.screens_card.setFocus()
    window.act("accept")
    assert "Pick a BIOS file" in window.pages_pane.status.text()
    pick(window, qapp, bios_file.name)
    window.screens_card.setFocus()
    window.act("accept")                                        # the pages
    assert window.panes.currentWidget() is window.pages_pane
    assert list(window.pages_pane.list.pills) == ["0"] and window.pages_pane.list.pills["0"].hasFocus()
    window.act("accept")                                        # Main
    assert window.panes.currentWidget() is window.screen_pane
    assert window.screen_pane.title.text() == "Main"
    assert [(e.prompt, e.value) for e in window.entries][:3] == [("BIOS Info", ""), ("BIOS Vendor", "Vendor Inc."),
                                                                 ("Mode", "On")]
    assert window.focused_entry().prompt == "BIOS Vendor"       # the first row; the subtitle is text
    window.act("down")
    assert window.focused_entry().prompt == "Mode"
    assert window.screen_pane.line.text() == "On, from the file  ·  default Off"
    assert window.screen_pane.info.title == "Mode" and "Options:" in window.screen_pane.info.info
    assert ("A", "Open") not in window.legend.items and ("LB", "Page before") in window.legend.items
    window.act("accept")                                        # a setting: read only
    assert "Read only" in window.screen_pane.status.text()
    for _ in range(4):
        window.act("down")
    assert window.focused_entry().prompt == "Sub" and ("A", "Open") in window.legend.items
    window.act("accept")                                        # into Sub
    assert window.screen_pane.title.text() == "Sub" and window.screen_pane.path.text() == "Main  \u203a  Sub"
    window.act("back")                                          # back to Main, on the link
    assert window.screen_pane.title.text() == "Main" and window.focused_entry().prompt == "Sub"
    window.act("back")                                          # back to the pages
    assert window.panes.currentWidget() is window.pages_pane and window.pages_pane.list.pills["0"].hasFocus()
    window.act("back")                                          # back to the card
    assert window.screens_card.hasFocus()
    window.close()


def test_y_shows_what_the_bios_hides(qapp, tmp_path, bios_file):
    window = make(qapp, tmp_path)
    pick(window, qapp, bios_file.name)
    window.screens_card.setFocus()
    window.act("accept")
    assert ("Y", "Show hidden") in window.legend.items
    window.act("y")
    assert [p.title for p in window.pages] == ["Main", "Hidden tab", "Not linked"]
    assert window.pages_pane.list.pills["1"].label.text() == "Hidden tab  (hidden)"
    assert ("Y", "Hide hidden") in window.legend.items and window.screens_card.text.text().endswith("hidden ones too")
    window.act("down")
    window.act("down")
    window.act("accept")                                        # Not linked
    assert window.screen_pane.title.text() == "Not linked"
    assert [e.prompt for e in window.entries] == ["Setup", "Orphan"]
    window.act("next")                                          # RB: round to the first page
    assert window.screen_pane.title.text() == "Main"
    window.act("previous")                                      # LB: back to the last
    assert window.screen_pane.title.text() == "Not linked"
    window.act("y")                                             # hidden ones off: the menu stays open
    assert window.screen_pane.title.text() == "Not linked" and [p.title for p in window.pages] == ["Main"]
    window.close()


def test_this_device(qapp, tmp_path, bios_file):
    """A reads the BIOS version; without a file that is all. With a file, A reads the settings (the fake prompt)."""
    window = make(qapp, tmp_path)
    window.device_card.setFocus()
    window.act("accept")
    assert dict(window.device_pane.rows())["BIOS version"] == "P9.99"
    assert window.device_card.text.text() == "BIOS P9.99"
    assert "Pick a BIOS file" in window.device_pane.status.text() and window.calls == []
    pick(window, qapp, bios_file.name)
    window.device_card.setFocus()
    assert window.legend.items[0] == ("A", "Read the settings")
    assert dict(window.device_pane.rows())["The file's version"] == "Yes: both are P9.99"
    window.act("accept")
    assert window.calls == [[window.bios.stores()[0]]]
    rows = dict(window.device_pane.rows())
    assert rows["Settings"] == "1 variables read, 0 kept by the BIOS" and rows["Read"] == "Setup"
    assert window.legend.items[0] == ("A", "Read again")
    window.screens_card.setFocus()
    window.act("accept")
    window.act("accept")
    window.act("down")
    assert window.focused_entry().prompt == "Mode"
    assert window.screen_pane.line.text() == "Off, from this device  ·  default Off"
    window.close()


def test_another_version_is_said(qapp, tmp_path, update_zip):
    window = make(qapp, tmp_path)
    pick(window, qapp, update_zip.name)
    window.device_card.setFocus()
    window.act("accept")
    assert dict(window.device_pane.rows())["The file's version"] == "No: the file is RC00XA.123, this device runs P9.99"
    assert window.device_card.text.text() == "BIOS P9.99: the file is another version."
    window.close()


def test_a_declined_prompt_is_said(qapp, tmp_path, bios_file):
    def declined(keys, folder):
        raise RuntimeError("Windows' prompt was declined: the settings were not read.")
    window = make(qapp, tmp_path, read_settings=declined)
    window.device_worker.start = lambda work: _device_fail(window, work)
    pick(window, qapp, bios_file.name)
    window.device_card.setFocus()
    window.act("accept")
    window.act("accept")
    assert window.device_pane.status.text() == "Windows' prompt was declined: the settings were not read."
    assert window.bios.device == {}
    window.close()


def _device_fail(window, work):
    try:
        work()
    except Exception as error:  # noqa: BLE001
        window.device_failed(str(error))
    return True


def test_version_is_the_single_source():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__ == INFO.version


def test_icons_are_beside_the_package():
    assert LOGO_PATH.is_file() and LOGO_PATH.name == f"{APP_ID}.webp"
    assert (ROOT / "images" / f"{APP_ID}-128.png").is_file()
    assert re.fullmatch(r"[A-Za-z0-9-]+", EXE_NAME)


def test_the_suffixes_are_the_files():
    assert bios.SUFFIXES[:5] == (".cap", ".bin", ".rom", ".fd", ".zip")
