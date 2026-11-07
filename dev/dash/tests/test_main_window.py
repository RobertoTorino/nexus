# SPDX-License-Identifier: GPL-3.0-or-later
"""The dashboard: the Nexus apps of the checkout as tiles, the suite's tools after them, the suite chosen in the
header, and what a click does."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QImage

from nexus_dashboard import APP_NAME, CHECKOUT, LOGO_PATH, checkout, main_window
from nexus_dashboard.main_window import SUITE_KEY, MainWindow


def test_the_icons_are_nexus_at_512_and_128_px():
    assert LOGO_PATH.name == "nexus-dashboard.webp"
    assert QImage(str(LOGO_PATH)).size().width() == 512
    assert QImage(str(LOGO_PATH.with_name("nexus-dashboard-128.png"))).size().width() == 128


def test_the_checkout_has_the_suites_and_the_nexus_apps():
    assert checkout.suites(CHECKOUT) == ["bazzite-console", "bc250-bazzite", "windows-portable"]
    assert checkout.suite_name(CHECKOUT, "bc250-bazzite") == "BC250 Bazzite Suite"
    assert checkout.suite_name(CHECKOUT, "bazzite-console") == "Bazzite Console Suite"
    assert checkout.suite_system(CHECKOUT, "bazzite-console") == "bazzite"
    assert checkout.suite_system(CHECKOUT, "windows-portable") == "windows"
    assert checkout.here(CHECKOUT, "bc250-bazzite", "linux") and not checkout.here(CHECKOUT, "bc250-bazzite", "win32")
    assert checkout.here(CHECKOUT, "windows-portable", "win32")
    apps = checkout.dev_apps(CHECKOUT)
    assert [app.key for app in apps] == ["nrt", "demo", "itests", "sounds"]   # the release tool first, then by name
    assert [app.name for app in apps] == ["Nexus Release Tool", "Nexus Demo Recorder", "Nexus Installer Tests",
                                          "Nexus Sound Lab"]
    assert all(app.icon is not None and app.icon.is_file() for app in apps)
    assert all(app.script.is_file() for app in apps)
    assert apps[1].log.name == "demo.log"


def test_the_window_lists_the_apps_then_the_suites_tools(qapp):
    settings = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "test", "test")
    window = MainWindow(settings=settings, suite="bc250-bazzite")

    assert window.windowTitle() == APP_NAME
    names = [window.tiles.item(i).text() for i in range(window.tiles.count())]
    assert names == ["Nexus Release Tool", "Nexus Demo Recorder", "Nexus Installer Tests", "Nexus Sound Lab",
                     "Portal video tour", "Apps video tour", "Convert icons", "Close issues", "Dev app versions"]
    assert window.suite_box.currentText() == "BC250 Bazzite Suite" and settings.value(SUITE_KEY) is None
    enabled = [bool(window.tiles.item(i).flags() & Qt.ItemFlag.ItemIsEnabled) for i in range(window.tiles.count())]
    if sys.platform == "win32":
        assert enabled == [True, True, True, True, False, False, True, True, True]
    else:
        assert enabled == [True] * 9
    window.close()


def test_a_windows_suite_greys_out_the_tours_and_the_choice_is_remembered(qapp):
    settings = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "test", "test")
    window = MainWindow(settings=settings, suite="bc250-bazzite")

    window.suite_box.setCurrentIndex(window.suite_box.findText("Windows Portable Suite"))

    assert window.suite == "windows-portable" and settings.value(SUITE_KEY) == "windows-portable"
    tiles = {window.tiles.item(i).text(): window.tiles.item(i) for i in range(window.tiles.count())}
    assert tiles["Convert icons"].flags() & Qt.ItemFlag.ItemIsEnabled         # its PNG icons, since 05-11-2026
    if sys.platform != "win32":
        assert not tiles["Portal video tour"].flags() & Qt.ItemFlag.ItemIsEnabled
        assert "not recorded on Linux" in tiles["Portal video tour"].toolTip()
    window.close()

    window = MainWindow(settings=settings)               # the remembered suite
    assert window.suite == "windows-portable"
    window.close()


def test_a_click_on_an_app_starts_it_with_the_suite_and_says_so(qapp, tmp_path):
    started = []
    window = MainWindow(settings=None, suite="bc250-bazzite", starter=lambda app, args: started.append((app.key, args)))
    tiles = {window.tiles.item(i).text(): window.tiles.item(i) for i in range(window.tiles.count())}

    window.click(tiles["Nexus Release Tool"].data(Qt.ItemDataRole.UserRole))
    window.click(tiles["Nexus Installer Tests"].data(Qt.ItemDataRole.UserRole))
    window.click(tiles["Nexus Demo Recorder"].data(Qt.ItemDataRole.UserRole))

    assert started == [("nrt", ("--suite", "bc250-bazzite")), ("itests", ("--suite", "bc250-bazzite")), ("demo", ())]
    assert "Nexus Release Tool" in window.output.toPlainText() and "started from" in window.output.toPlainText()

    def refuse(app, args):
        raise OSError("no bash")
    window.starter = refuse
    window.click(tiles["Nexus Release Tool"].data(Qt.ItemDataRole.UserRole))
    assert "could not start (no bash)" in window.output.toPlainText()
    window.close()


def test_a_click_on_a_tool_opens_its_dialog_on_the_suite(qapp, monkeypatch):
    opened = []
    for name in ("PortalTourDialog", "AppsTourDialog", "IconsDialog"):
        monkeypatch.setattr(main_window, name, lambda *args, _name=name: type(
            "Fake", (), {"exec": lambda self: opened.append((_name, args[:-1]))})())
    window = MainWindow(settings=None, suite="bc250-bazzite")
    tiles = {window.tiles.item(i).text(): window.tiles.item(i) for i in range(window.tiles.count())}
    for name in ("Portal video tour", "Apps video tour", "Convert icons"):
        tile = tiles[name].data(Qt.ItemDataRole.UserRole)
        tile.off = ""                                    # whatever the system: the dialogs are what is tested
        window.click(tile)

    suite = CHECKOUT / "bc250-bazzite"
    assert opened == [("PortalTourDialog", (suite, window.open_file)), ("AppsTourDialog", (suite, window.open_file)),
                      ("IconsDialog", (CHECKOUT, "bc250-bazzite"))]
    window.close()


def test_a_checkout_without_suites_or_apps(qapp, tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "dev").mkdir()
    window = MainWindow(tmp_path, settings=None)
    assert window.suite is None and window.apps == []
    assert [window.tiles.item(i).text() for i in range(window.tiles.count())] == ["Portal video tour",
                                                                                  "Apps video tour", "Convert icons",
                                                                                  "Close issues",
                                                                                  "Dev app versions"]
    assert all(not window.tiles.item(i).flags() & Qt.ItemFlag.ItemIsEnabled for i in range(3))
    assert window.tiles.item(3).flags() & Qt.ItemFlag.ItemIsEnabled          # the repository's, every suite's
    assert window.local_apps.count() == 0
    window.close()


def test_start_runs_the_apps_script_in_its_folder_with_a_log(tmp_path, monkeypatch):
    app = checkout.DevApp(tmp_path / "x", "nexus-x", "X", "0.1.0", None)
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "run.sh").write_text("echo hello $1\n", encoding="utf-8")
    monkeypatch.setattr(checkout, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(checkout, "WINDOWS", False)

    process = checkout.start(app, ("--suite", "s"))
    process.wait(10)

    assert process.returncode == 0
    assert (tmp_path / "logs" / "x.log").read_text(encoding="utf-8") == "hello --suite\n"



@pytest.mark.skipif(sys.platform != "win32", reason="run.ps1 runs with Windows PowerShell")
def test_start_runs_the_apps_powershell_script_on_windows(tmp_path, monkeypatch):
    """The script really runs: PowerShell started without a console (DETACHED_PROCESS) quit at once with code 0."""
    app = checkout.DevApp(tmp_path / "x", "nexus-x", "X", "0.1.0", None)
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "run.ps1").write_text("Write-Output \"hello $($args[0])\"\nexit 3\n", encoding="utf-8")
    monkeypatch.setattr(checkout, "LOG_DIR", tmp_path / "logs")

    process = checkout.start(app, ("--suite", "s"))
    process.wait(30)

    assert process.returncode == 3
    assert (tmp_path / "logs" / "x.log").read_text(encoding="utf-8").strip() == "hello --suite"

def test_a_second_launch_opens_no_window(qapp, monkeypatch):
    """A double-click on the Desktop icon starts the app twice: the second launch hands over to the first."""
    import nexus_dashboard.__main__ as entry
    asked = []
    monkeypatch.setattr(entry, "create_app", lambda *a, **k: qapp)
    monkeypatch.setattr(entry.instance, "already_running", lambda app_id: asked.append(app_id) or True)
    monkeypatch.setattr("sys.argv", ["nexus_dashboard"])
    assert entry.main() == 0 and asked == [entry.APP_ID]


def test_a_click_on_the_nexus_icon_opens_the_nexus_page(qapp, monkeypatch):
    opened = []
    monkeypatch.setattr(main_window, "open_url", opened.append)
    window = MainWindow(settings=None, suite="bc250-bazzite")

    assert window.header.logo.cursor().shape() == Qt.CursorShape.PointingHandCursor
    window.header.logo.clicked.emit()

    assert opened == ["https://robertotorino.github.io/nexus/"]
    window.close()
