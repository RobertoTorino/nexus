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

# The Windows Portable Suite is a repository of its own (owner, 13-11-2026), cloned into the checkout as its folder
WINDOWS_HERE = (CHECKOUT / "windows-portable" / "portal" / "apps.toml").is_file()


def test_the_icons_are_nexus_at_512_and_128_px():
    assert LOGO_PATH.name == "nexus-dashboard.webp"
    assert QImage(str(LOGO_PATH)).size().width() == 512
    assert QImage(str(LOGO_PATH.with_name("nexus-dashboard-128.png"))).size().width() == 128


def test_the_checkout_has_the_suites_and_the_nexus_apps(bazzite_checkout):
    assert checkout.suites(CHECKOUT) == (["windows-portable"] if WINDOWS_HERE else [])   # Nexus holds none of its own
    assert checkout.suites(bazzite_checkout) == ["bz"]
    assert checkout.suite_name(bazzite_checkout, "bz") == "Bz Suite"
    assert checkout.suite_system(bazzite_checkout, "bz") == "bazzite"
    assert checkout.here(bazzite_checkout, "bz", "linux") and not checkout.here(bazzite_checkout, "bz", "win32")
    if WINDOWS_HERE:
        assert checkout.suite_system(CHECKOUT, "windows-portable") == "windows"
        assert checkout.here(CHECKOUT, "windows-portable", "win32")
    apps = checkout.dev_apps(CHECKOUT)
    assert [app.key for app in apps] == ["nrt", "demo", "deps", "itests", "sounds"]   # the release tool, then by name
    assert [app.name for app in apps] == ["Nexus Release Tool", "Nexus Demo Recorder", "Nexus Deps",
                                          "Nexus Installer Tests", "Nexus Sound Lab"]
    assert all(app.icon is not None and app.icon.is_file() for app in apps)
    # Nexus Deps checks a Bazzite machine: it has run.sh alone
    assert all(app.script.is_file() for app in apps if not (checkout.WINDOWS and app.key == "deps"))
    assert apps[1].log.name == "demo.log"


def test_the_window_lists_the_apps_then_the_suites_tools(qapp, bazzite_checkout):
    settings = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "test", "test")
    window = MainWindow(bazzite_checkout, settings=settings, suite="bz")

    assert window.windowTitle() == APP_NAME
    names = [window.tiles.item(i).text() for i in range(window.tiles.count())]
    assert names == ["Nexus Release Tool", "Nexus Demo Recorder", "Nexus Deps", "Nexus Installer Tests",
                     "Nexus Sound Lab", "Portal video tour", "Apps video tour", "Convert icons", "Close issues", "Dev app versions"]
    assert window.suite_box.currentText() == "Bz Suite" and settings.value(SUITE_KEY) is None
    enabled = [bool(window.tiles.item(i).flags() & Qt.ItemFlag.ItemIsEnabled) for i in range(window.tiles.count())]
    # Nexus Deps: no catalog for the suite (Nexus has none since 14-11-2026), and no run.ps1 on Windows
    if sys.platform == "win32":
        assert enabled == [True, True, False, True, True, False, False, True, True, True]
    else:
        assert enabled == [True, True, False, True, True, True, True, True, True, True]
    window.close()


def test_a_windows_suite_greys_out_the_tours_and_the_choice_is_remembered(qapp, bazzite_checkout):
    wp = bazzite_checkout / "wp"                        # a Windows suite beside bz/, as the Windows Portable Suite
    for path, text in (("SYSTEM", "windows\n"), ("TAG_PREFIX", "wp-\n"), ("portal/apps.toml", ""),
                       ("portal/wp_portal/__init__.py", 'APP_NAME = "Wp Suite"\n'),
                       ("icons/categories.toml", '[icons]\nformat = "png"\n'), ("tools/record-tour.sh", "")):
        (wp / path).parent.mkdir(parents=True, exist_ok=True)
        (wp / path).write_text(text, encoding="utf-8")
    settings = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "test", "test")
    window = MainWindow(bazzite_checkout, settings=settings, suite="bz")

    window.suite_box.setCurrentIndex(window.suite_box.findText("Wp Suite"))

    assert window.suite == "wp" and settings.value(SUITE_KEY) == "wp"
    tiles = {window.tiles.item(i).text(): window.tiles.item(i) for i in range(window.tiles.count())}
    assert tiles["Convert icons"].flags() & Qt.ItemFlag.ItemIsEnabled         # its PNG icons, since 05-11-2026
    if sys.platform != "win32":
        assert not tiles["Portal video tour"].flags() & Qt.ItemFlag.ItemIsEnabled
        assert "not recorded on Linux" in tiles["Portal video tour"].toolTip()
    window.close()

    window = MainWindow(bazzite_checkout, settings=settings)               # the remembered suite
    assert window.suite == "wp"
    window.close()


def test_nexus_deps_is_off_for_a_suite_without_a_catalog(qapp, bazzite_checkout):
    """Nexus Deps checks a suite with a catalog of its own (owner, 07-11-2026): none here since the BC250 Bazzite
    Suite took its catalog to a repository of its own (14-11-2026). A catalog of the suite turns the tile on."""
    window = MainWindow(bazzite_checkout, settings=None, suite="bz")
    tiles = {window.tiles.item(i).text(): window.tiles.item(i) for i in range(window.tiles.count())}
    assert not tiles["Nexus Deps"].flags() & Qt.ItemFlag.ItemIsEnabled
    if sys.platform != "win32":
        assert "no catalog for bz" in tiles["Nexus Deps"].toolTip()
    window.close()
    (bazzite_checkout / "dev" / "deps" / "nexus_deps" / "catalogs" / "bz.toml").write_text("", encoding="utf-8")
    window = MainWindow(bazzite_checkout, settings=None, suite="bz")
    tiles = {window.tiles.item(i).text(): window.tiles.item(i) for i in range(window.tiles.count())}
    if sys.platform != "win32":
        assert tiles["Nexus Deps"].flags() & Qt.ItemFlag.ItemIsEnabled
    window.close()


def test_a_click_on_an_app_starts_it_with_the_suite_and_says_so(qapp, bazzite_checkout):
    (bazzite_checkout / "dev" / "deps" / "nexus_deps" / "catalogs" / "bz.toml").write_text("", encoding="utf-8")
    started = []
    window = MainWindow(bazzite_checkout, settings=None, suite="bz",
                        starter=lambda app, args: started.append((app.key, args)))
    tiles = {window.tiles.item(i).text(): window.tiles.item(i) for i in range(window.tiles.count())}

    window.click(tiles["Nexus Release Tool"].data(Qt.ItemDataRole.UserRole))
    window.click(tiles["Nexus Installer Tests"].data(Qt.ItemDataRole.UserRole))
    window.click(tiles["Nexus Demo Recorder"].data(Qt.ItemDataRole.UserRole))
    window.click(tiles["Nexus Deps"].data(Qt.ItemDataRole.UserRole))

    assert started == [("nrt", ("--suite", "bz")), ("itests", ("--suite", "bz")), ("demo", ()),
                       ("deps", ("--suite", "bz"))]
    assert "Nexus Release Tool" in window.output.toPlainText() and "started from" in window.output.toPlainText()

    def refuse(app, args):
        raise OSError("no bash")
    window.starter = refuse
    window.click(tiles["Nexus Release Tool"].data(Qt.ItemDataRole.UserRole))
    assert "could not start (no bash)" in window.output.toPlainText()
    window.close()


def test_a_click_on_a_tool_opens_its_dialog_on_the_suite(qapp, monkeypatch, bazzite_checkout):
    opened = []
    for name in ("PortalTourDialog", "AppsTourDialog", "IconsDialog"):
        monkeypatch.setattr(main_window, name, lambda *args, _name=name: type(
            "Fake", (), {"exec": lambda self: opened.append((_name, args[:-1]))})())
    window = MainWindow(bazzite_checkout, settings=None, suite="bz")
    tiles = {window.tiles.item(i).text(): window.tiles.item(i) for i in range(window.tiles.count())}
    for name in ("Portal video tour", "Apps video tour", "Convert icons"):
        tile = tiles[name].data(Qt.ItemDataRole.UserRole)
        tile.off = ""                                    # whatever the system: the dialogs are what is tested
        window.click(tile)

    suite = bazzite_checkout / "bz"
    assert opened == [("PortalTourDialog", (suite, window.open_file)), ("AppsTourDialog", (suite, window.open_file)),
                      ("IconsDialog", (bazzite_checkout, "bz"))]
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
    window = MainWindow(settings=None)

    assert window.header.logo.cursor().shape() == Qt.CursorShape.PointingHandCursor
    window.header.logo.clicked.emit()

    assert opened == ["https://robertotorino.github.io/nexus/"]
    window.close()
