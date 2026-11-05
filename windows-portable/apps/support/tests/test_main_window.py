# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py): it opens on the portable window with the header's battery, date and time, fits the
handheld's screen; the checks run in the background and fill the three cards and their panes; the row with the focus
says more; Y checks again; B goes back and View exits; the version and the icons are where the checks expect them."""

from __future__ import annotations

import datetime
import re
import time

from bc250_core import portable
from bc250_core.gamepad import Gamepad
from bc250_core.portable import BACK, EXIT
from bc250_core.portable import INFO as MENU_INFO
from support_checker import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, checks
from support_checker.checks import App, AppState, Found, ToolState, WindowsState
from support_checker.main_window import MainWindow


class FakePad:
    def events(self):
        return []

    def close(self):
        pass

    def names(self):
        return []


def report(restart=False, missing=False) -> checks.Report:
    tools = [ToolState(checks.TOOLS[1], "Missing" if missing else "Available",
                       Found(not missing, "missing in System32: msvcp140.dll" if missing else r"C:\Windows\System32"),
                       ("Xenia Manager",), True),
             ToolState(checks.TOOLS[3], "Not installed", Found(False, "no Steam folder was found"),
                       ("Xenia Manager", "the portal"), False)]
    apps = [AppState(App("xenia", "Xenia Manager", "wp-xenia-v0.4.0", ()), "Update in the portal", "0.3.1"),
            AppState(App("test", "Windows Portable Test", "wp-test-v0.2.0", ()), "Up to date", "0.2.0"),
            AppState(App("bios", "BIOS Reader", "wp-bios-v0.8.0", ()), "Not installed")]
    windows = WindowsState("Windows 11 Home", "24H2", "26100.4351", restart, "2026-11-01 (KB5066835)",
                           datetime.date.today())
    return checks.Report(windows, tools, apps, None)


def wait_for(qapp, predicate, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not predicate():
        qapp.processEvents()
        time.sleep(0.01)
    return predicate()


def make(qapp, check=report):
    window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False), check=check)
    portable.scale((1280, 720))
    window.resize(1280, 720)
    window.show()
    window.activateWindow()
    qapp.processEvents()
    window.start()
    assert wait_for(qapp, lambda: not window.worker.busy and window.report is not None or isinstance(check, str))
    qapp.processEvents()
    return window


def test_the_window_opens_with_the_suites_header(qapp):
    window = make(qapp)
    assert window.header.title.text() == APP_NAME and window.header.version.text() == __version__
    assert re.fullmatch(r"\w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d  \|  82%", window.header.status.text())
    assert window.legend.items == [("Y", "Check again"), MENU_INFO, EXIT]
    window.close()


def test_the_window_fits_the_handhelds_screen(qapp):
    window = make(qapp)
    assert window.minimumSizeHint().height() <= 720 and window.height() == 720
    window.close()


def test_the_cards_and_panes_say_what_was_found(qapp, monkeypatch):
    window = make(qapp, lambda: report(missing=True))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert window.windows_card.text.text() == "Up to date"
    assert window.tools_card.text.text() == "1 missing: Microsoft Visual C++ runtime"
    assert window.apps_card.text.text() == "1 to update in the portal"
    rows = {window.windows_pane.grid.itemAt(i).widget().text(): window.windows_pane.grid.itemAt(i + 1).widget().text()
            for i in range(0, window.windows_pane.grid.count(), 2)}
    assert rows["Build"] == "26100.4351" and rows["Newest update installed"] == "2026-11-01 (KB5066835)"
    assert [p.label.text() for p in window.tools_pane.list.pills.values()] == [
        "Microsoft Visual C++ runtime: Missing", "Steam: Not installed"]
    window.on_action("down")                                    # the Tools card
    assert window.panes.currentWidget() is window.tools_pane
    window.on_action("accept")                                  # into its list: the first row
    assert window.tools_pane.list.focused() == "vcruntime"
    status = window.tools_pane.status.text()
    assert status.startswith("Needed by Xenia Manager. Not found: missing in System32: msvcp140.dll.")
    assert "vc_redist.x64.exe" in status
    window.on_action("down")
    assert window.tools_pane.status.text().startswith("Used when it is there by Xenia Manager, the portal.")
    assert window.legend.items == [("Y", "Check again"), MENU_INFO, BACK, EXIT]
    window.on_action("back")                                    # B: back to the card
    assert window.tools_card.hasFocus()
    window.on_action("down")                                    # the Apps card
    assert [p.label.text() for p in window.apps_pane.list.pills.values()] == [
        "Xenia Manager: 0.3.1, the portal has 0.4.0", "Windows Portable Test: 0.2.0, up to date",
        "BIOS Reader: not installed"]
    window.on_action("accept")
    assert window.apps_pane.status.text().startswith("Xenia Manager 0.3.1 is installed; the portal brings 0.4.0")
    window.close()


def test_a_restart_waits_and_y_checks_again(qapp, monkeypatch):
    answers = [report(restart=True), report()]
    window = make(qapp, lambda: answers.pop(0))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert window.windows_card.text.text() == "Restart to update"
    assert window.windows_pane.status.text().startswith("An update waits for a restart")
    window.on_action("y")                                       # Y Check again
    assert wait_for(qapp, lambda: window.windows_card.text.text() == "Up to date") and answers == []
    window.close()


def test_a_check_that_fails_says_so(qapp):
    def broken():
        raise OSError("no registry")
    window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False), check=broken)
    window.show()
    window.start()
    assert wait_for(qapp, lambda: window.windows_card.text.text() == "The check failed")
    assert "no registry" in window.windows_pane.status.text()
    window.close()


def test_b_goes_back_and_view_exits(qapp, monkeypatch):
    """The suite's buttons: B goes back (with nowhere to go, nothing happens) and View exits the app."""
    window = make(qapp)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("back")
    assert closed == []
    window.on_action("view")
    assert closed == [True]


def test_version_is_the_single_source():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__ == INFO.version


def test_icons_are_beside_the_package():
    assert LOGO_PATH.is_file() and LOGO_PATH.name == f"{APP_ID}.webp"
    assert (ROOT / "images" / f"{APP_ID}-128.png").is_file()
    assert re.fullmatch(r"[A-Za-z0-9-]+", EXE_NAME)
