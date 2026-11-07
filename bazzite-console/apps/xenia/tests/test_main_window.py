# SPDX-License-Identifier: GPL-3.0-or-later
"""The window on folders made in a temp folder: the states before and after installing, the games in the table, the
game folders, the plan for Steam, installing through the worker, Steam's shortcuts changed with a fake "close
Steam", a newer Xenia build, the Settings and Log tabs, and the blue look of RPCS3 Manager's design."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QMessageBox

from conftest import make_iso, make_package

from bc250_core import steam
from xenia_manager import emulator, shortcuts, style
from xenia_manager.games import Game
from xenia_manager.main_window import MainWindow


@pytest.fixture
def folders(tmp_path):
    make_iso(tmp_path / "Games" / "XBOX360" / "One.iso")                        # the app's own folder
    make_package(tmp_path / "Games" / "XBOX360", "Two")
    config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    config.mkdir(parents=True)
    run = tmp_path / "bin" / "ps5-xenia-run"
    run.parent.mkdir()
    run.write_text("#!/bin/sh\n")
    log = tmp_path / "data" / "ps5-xenia-manager" / "ps5-xenia-manager.log"
    log.parent.mkdir(parents=True)
    return {"home": tmp_path / "emulator", "steam_dir": tmp_path / "Steam", "run": run, "user_home": tmp_path,
            "drives": lambda: [], "log_path": log}


def _install(home: Path) -> None:
    (home / emulator.VERSION).mkdir(parents=True)
    (home / emulator.VERSION / emulator.MEMBER).write_text("")
    (home / "current").symlink_to(emulator.VERSION)


def _wait(window, qapp) -> None:
    deadline = time.monotonic() + 10
    while window.worker.running and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()


def _window(folders, **kwargs) -> MainWindow:
    closed = kwargs.pop("closed", [])
    kwargs.setdefault("newer_release", lambda: None)                         # never GitHub in a test
    return MainWindow(**folders, steam_closed=lambda change: (closed.append(1), change())[0] and False,
                      steam_running=lambda: False, **kwargs)


def _titles(window) -> list[str]:
    return [window.table.item(r, 1).text() for r in range(window.table.rowCount())]


def test_before_installing(qapp, folders):
    window = _window(folders)
    assert window.pill.text() == "Not installed"
    # The state alone, in the words every manager uses (owner, 07-11-2026); what Install does in the tip.
    assert window.emulator_state.text() == "Not installed.<br>Install it with the Install button."
    assert "Install downloads Xenia 838850f" in window.emulator_state.toolTip()
    assert window.install_pill.isEnabled() and not window.remove_pill.isEnabled()
    assert not window.xenia_button.isEnabled() and not hasattr(window, "play_button")
    for name in ("folder_button", "forget_button"):
        assert not hasattr(window, name), name                               # gone (owner, 03-11-2026): fixed folders
    assert window.table.rowCount() == 2                                          # the games in Games/XBOX360
    window.close()


def test_installed_with_games(qapp, folders, tmp_path):
    _install(folders["home"])
    window = _window(folders)
    assert window.pill.text() == "Ready"                                       # the games in Games/XBOX360
    assert window.pill.text() == "Ready" and window.emulator_box.value.text() == emulator.VERSION
    assert window.emulator_state.text() == "Installed.<br>Uninstall with the Uninstall button."
    assert "experimental on Linux" in window.emulator_state.toolTip()
    assert window.games_box.value.text() == "2" and window.steam_box.value.text() == "0"
    assert not window.install_pill.isEnabled() and window.remove_pill.isEnabled()
    assert not window.remove_game_button.isEnabled()                              # nothing chosen yet
    window.table.selectRow(0)
    assert window.remove_game_button.isEnabled() and window.chosen().title == "One"
    assert not window.steam_button.isEnabled()                                    # nothing to change
    assert [window.table.item(r, 2).text() for r in range(2)] == ["", "4D5307E6"]
    assert [window.table.item(r, 3).text() for r in range(2)] == ["ISO", "Games on Demand"]
    window.close()


def test_an_older_build_is_offered_the_pinned_one(qapp, folders):
    (folders["home"] / "f42147a").mkdir(parents=True)
    (folders["home"] / "f42147a" / emulator.MEMBER).write_text("")
    (folders["home"] / "current").symlink_to("f42147a")
    window = _window(folders)
    assert window.emulator_state.text() == "Installed.<br>Uninstall with the Uninstall button."
    assert "Xenia f42147a is installed; this version of the app brings 838850f" in window.emulator_state.toolTip()
    assert window.install_pill.isEnabled()
    window.refresh()
    assert window.output.toPlainText().count("Xenia f42147a is installed") == 1           # logged once
    window.close()


def test_the_apps_own_game_folders(qapp, folders, tmp_path, monkeypatch):
    """The games are put in Games/XBOX360 in the home folder, made when the app opens, and in Games/XBOX360 on a
    removable drive that has one (owner, 03-11-2026: fixed folders, no folder choosing); no folder is chosen or
    remembered any more."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _install(folders["home"])
    (tmp_path / "sd" / "Games" / "XBOX360").mkdir(parents=True)
    (tmp_path / "stick").mkdir()                                                # a drive without the folder
    window = _window({**folders, "drives": lambda: [tmp_path / "sd", tmp_path / "stick", tmp_path / "gone"]})
    assert window.folders == [tmp_path / "Games" / "XBOX360", tmp_path / "sd" / "Games" / "XBOX360"]
    text = window.folders_state.text()
    assert "<b>~/Games/XBOX360</b>" in text and "<b>~/sd/Games/XBOX360</b>" in text
    assert str(tmp_path) not in text and "folders" not in window.settings.DEFAULTS
    window.close()


def test_install_runs_off_the_window(qapp, folders, monkeypatch):
    payload = b"#!/bin/sh\n"
    monkeypatch.setattr(emulator, "SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = _window(folders, fetch=lambda url, dest, progress=None: dest.write_bytes(payload))
    window.on_install()
    assert not window.install_pill.isEnabled()                                    # busy
    _wait(window, qapp)
    assert window.running.text() == f"Xenia {emulator.VERSION} is installed."
    assert window.version == emulator.VERSION and window.pill.text() == "Ready"
    window.close()


def test_a_failed_install_says_so(qapp, folders, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = _window(folders, fetch=lambda url, dest, progress=None: dest.write_bytes(b"other"))
    window.on_install()
    _wait(window, qapp)
    assert "Xenia was not installed:" in window.running.text() and "SHA-256 differs" in window.running.text()
    assert not window.version
    window.close()


def test_remove(qapp, folders, monkeypatch):
    _install(folders["home"])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = _window(folders)
    window.on_remove()
    assert not window.version and not window.home.exists() and window.pill.text() == "Not installed"
    window.close()


def test_xenias_window(qapp, folders, tmp_path):
    """Xenia settings opens Xenia's own window, through the run wrapper and without a game."""
    _install(folders["home"])
    log = tmp_path / "args"
    folders["run"].write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n')
    folders["run"].chmod(0o755)
    window = _window(folders)
    window.xenia_button.click()
    deadline = time.monotonic() + 10
    while not log.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert log.read_text().splitlines() == [""]
    assert window.output.toPlainText().splitlines()[-1].endswith(" INFO Xenia's own window was opened.")
    window.close()


def test_the_steam_link(qapp, folders):
    opened = []
    window = _window(folders, open_url=lambda url: opened.append(url) or True)
    window.steam_hint.linkActivated.emit("steam://open/games")
    assert opened == ["steam://open/games"]
    window.close()


def test_steam_added_and_taken_out(qapp, folders, tmp_path, monkeypatch):
    _install(folders["home"])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    closed = []
    window = _window(folders, closed=closed)
    window.table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    assert window.steam_button.isEnabled()
    add, remove = window.steam_plan()
    assert [g.title for g in add] == ["Two"] and remove == []
    window.on_update_steam()
    _wait(window, qapp)
    assert closed == [1] and window.running.text().startswith("1 game(s) in Steam")
    assert list(shortcuts.in_steam(folders["steam_dir"]).values()) == ["[X360] Two"]
    assert window.steam_box.value.text() == "1" and window.table.item(1, 0).checkState() == Qt.CheckState.Checked
    window.table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
    add, remove = window.steam_plan()
    assert add == [] and [g.title for g in remove] == ["Two"]
    window.on_update_steam()
    _wait(window, qapp)
    assert shortcuts.in_steam(folders["steam_dir"]) == {} and "1 taken out" in window.running.text()
    window.close()


def test_a_shortcut_of_a_game_no_longer_found_is_taken_out(qapp, folders):
    _install(folders["home"])
    gone = Game(Path("/old/games/gone.iso"), "Gone")
    steam.write_shortcuts(folders["steam_dir"], shortcuts.changes([gone], [], folders["run"], Path("/i.png"), {},
                                                                  art=False))
    window = _window(folders)
    add, remove = window.steam_plan()
    assert add == [] and [(str(g.file), g.title) for g in remove] == [(str(gone.file), "[X360] Gone")]
    assert window.steam_button.isEnabled()
    window.close()


def test_games_need_xenia_for_game_mode(qapp, folders, tmp_path):
    window = _window(folders)
    window.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    window.on_update_steam()
    assert "Install Xenia first" in window.running.text() and not window.worker.running
    window.close()


def test_no_steam_game_mode_or_no_wrapper(qapp, folders, tmp_path, monkeypatch):
    _install(folders["home"])
    monkeypatch.setattr(steam, "find_steam", lambda: None)                       # None: looked up, and not found
    window = _window({**folders, "steam_dir": None})
    window.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    assert not window.steam_button.isEnabled() and "never started" in window.steam_button.toolTip()
    window.close()
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "gamescope")
    window = _window(folders)
    window.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    assert not window.steam_button.isEnabled() and "Desktop Mode" in window.steam_button.toolTip()
    window.close()
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    folders["run"].unlink()
    window = _window(folders)
    window.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    window.on_update_steam()
    assert "install Xenia Manager through the portal first" in window.running.text()
    assert not window.worker.running
    window.close()


def test_the_blue_look(qapp, folders):
    """RPCS3 Manager's design (owner, 07-11-2026): the Refresh pill and the boxes in the header, the action pills
    under the introduction, a third of the width each, the tabs."""
    _install(folders["home"])
    window = _window(folders)
    from bc250_core.theme import OUTLINE
    assert style.BLUE in window.styleSheet()
    assert window.covers_button.property("primary") is None and window.steam_button.property("primary")
    assert window.xenia_button.property("primary") is None
    assert style.BLUE in window.emulator_box.styleSheet() and style.BLUE in window.refresh_pill.styleSheet()
    assert f"color:{style.BLUE}" in window.intro.text()                             # the release link
    assert [(p.value.text(), p.caption.text()) for p in window.actions] == [("Xenia", "Install"),
                                                                           ("Xenia", "Uninstall")]
    for pill in (window.refresh_pill, *window.actions):
        sheet = pill.styleSheet()                       # the blue left edge only, also under the mouse (owner)
        assert sheet.rfind(f"border-left-color:{style.BLUE}") > sheet.rfind(OUTLINE) >= 0, pill.caption.text()
        assert style.HOVER_SHEEN in sheet and style.BLUE_TINT not in sheet
    assert "QTabBar::tab" in window.styleSheet() and "QComboBox" in window.styleSheet()
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == ["Your games", "Settings", "Log"]
    window.show()
    qapp.processEvents()
    third = window.centralWidget().width() // 3
    assert all(abs(p.width() - third) < 12 for p in window.actions)               # the last third empty
    window.close()


def test_a_newer_build_is_mentioned(qapp, folders):
    from bc250_core.updates import ReleaseInfo
    _install(folders["home"])
    release = ReleaseInfo("0a1b2c3", "0a1b2c3", "https://github.com/xenia-canary/xenia-canary/releases/tag/0a1b2c3",
                          "2026-11-30")
    window = _window(folders, newer_release=lambda: release)
    deadline = time.monotonic() + 10
    while window.newer is None and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    tip = window.emulator_state.toolTip()                   # the line stays the state; the tip and the log say
    assert window.emulator_state.text() == "Installed.<br>Uninstall with the Uninstall button."
    assert "Xenia 0a1b2c3 is out (2026-11-30)" in tip and "releases/tag/0a1b2c3" in tip
    assert "Xenia 0a1b2c3 is out (2026-11-30)" in window.output.toPlainText()
    assert window.install_pill.isEnabled() is False                                # it never installs that one
    window.close()


def test_the_log_tab(qapp, folders):
    """What the window says goes to the Log tab with the time, after what the log file held already."""
    folders["log_path"].write_text("07-11-2026 22:14:00 INFO Xenia Manager 2.2.0 started\n")
    window = _window(folders)
    assert window.output.toPlainText().splitlines() == ["07-11-2026 22:14:00 INFO Xenia Manager 2.2.0 started"]
    window.say("Steam was not changed: no Steam", ok=False)
    lines = window.output.toPlainText().splitlines()
    assert lines[-1][:19].count("-") == 2 and lines[-1][10] == " "               # DD-MM-YYYY HH:MM:SS
    assert lines[-1].endswith(" ERROR Steam was not changed: no Steam") and "c62828" in window.running.styleSheet()
    assert str(folders["log_path"]) in window.tabs.widget(2).findChildren(QLabel)[0].text()
    window.close()


def test_covers_with_the_suites_key(qapp, folders, monkeypatch, tmp_path):
    """Steam artwork… keeps the suite's key; Update Steam then looks up the game by its title and puts
    SteamGridDB's pictures in place of all four drawn ones, and a game in Steam not looked up yet makes the button do
    something again."""
    import json

    from PyQt6.QtGui import QColor, QImage
    from PyQt6.QtWidgets import QInputDialog

    from xenia_manager import LOGO_PATH

    picture = QImage(600, 900, QImage.Format.Format_ARGB32)
    picture.fill(QColor("#0000ff"))
    picture.save(str(tmp_path / "blue.png"))
    asked = []

    def get(url: str, headers: dict[str, str]) -> bytes:
        asked.append(url)
        if "search/" in url:
            return json.dumps({"success": True, "data": [{"id": 1, "name": "Two"}]}).encode()
        if "/game/1?" in url:
            return json.dumps({"success": True, "data": [{"score": 1, "mime": "image/png",
                                                          "url": "https://cdn2.steamgriddb.com/x.png"}]}).encode()
        return (tmp_path / "blue.png").read_bytes()
    _install(folders["home"])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    key = tmp_path / "key"
    window = _window(folders, covers_home=tmp_path / "covers", covers_get=get, covers_key=key)
    row = _titles(window).index("Two")
    window.table.item(row, 0).setCheckState(Qt.CheckState.Checked)
    window.on_update_steam()
    _wait(window, qapp)
    assert asked == [] and not window.steam_button.isEnabled()                  # no key: nothing asked
    monkeypatch.setattr(QInputDialog, "exec", lambda self: (self.setTextValue("0123456789abcdef"), 1)[1])
    window.on_covers()
    assert key.read_text() == "0123456789abcdef\n"
    game = window.games[row]
    assert window.no_cover == {str(game.file)} and window.steam_button.isEnabled()
    window.on_update_steam()
    _wait(window, qapp)
    assert window.running.text().startswith("Covers: SteamGridDB had pictures for 1 of 1 game(s).\n1 game(s) in")
    assert asked[0].endswith("search/autocomplete/Two")
    assert any("heroes/" in url for url in asked) and any("logos/" in url for url in asked)
    assert "0123456789abcdef" not in window.output.toPlainText()
    name = shortcuts.names([game])[game.file]
    number = shortcuts.entry(game, name, folders["run"], LOGO_PATH)["appid"] & 0xFFFFFFFF
    grid = steam.user_folders(folders["steam_dir"])[0] / "grid"
    for suffix in ("p", "", "_hero"):
        image = QImage(str(grid / f"{number}{suffix}.png"))
        assert image.pixelColor(image.width() // 2, image.height() // 2).name() == "#0000ff", suffix
    assert QImage(str(grid / f"{number}_logo.png")).size() == picture.size()
    assert window.no_cover == set() and not window.steam_button.isEnabled()
    window.close()


def test_remove_game_asks_what_to_keep(qapp, folders, monkeypatch, tmp_path):
    """Remove game… (owner, 03-11-2026): the keep window lists what would go; Cancel deletes nothing, Delete marked
    deletes the rows still ticked off the window's thread and says what went and what stayed."""
    from PyQt6.QtWidgets import QDialog
    from bc250_core.keep_dialog import KeepDialog
    _install(folders["home"])
    window = _window(folders)
    assert not window.remove_game_button.isEnabled()                            # nothing chosen yet
    window.table.selectRow(0)
    game = window.chosen()
    assert game.title == "One" and window.remove_game_button.isEnabled()
    target = tmp_path / "Games" / "XBOX360" / "One.iso"
    assert target.exists()
    seen = []
    monkeypatch.setattr(KeepDialog, "exec", lambda self: (seen.append(self.items), QDialog.DialogCode.Rejected)[1])
    window.on_remove_game()
    assert [item.label for item in seen[0]] == ["One.iso (the game)"] and target.exists()
    assert window.running.text() == "Nothing was deleted."

    def keep_it(self):
        self.items[0].delete = False
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(KeepDialog, "exec", keep_it)
    window.on_remove_game()
    _wait(window, qapp)
    assert target.exists() and window.running.text() == "One: deleted nothing. Kept: One.iso (the game)."
    window.table.selectRow(0)
    monkeypatch.setattr(KeepDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    window.on_remove_game()
    _wait(window, qapp)
    assert not target.exists() and window.running.text() == "One: deleted One.iso (the game)."
    assert "One" not in [window.table.item(r, 1).text() for r in range(window.table.rowCount())]
    window.close()


def test_the_settings_tab(qapp, folders, tmp_path):
    """The Settings tab holds Xenia's settings in the app (core's settings_page): Xenia's defaults while there is no
    file, a change written into Xenia's own folder at once, and nothing while Xenia runs."""
    xenia_home = tmp_path / "Xenia"
    running = [False]
    window = _window(folders, xenia_home=xenia_home, xenia_running=lambda: running[0])
    page = window.settings_page
    assert window.tabs.widget(1) is page and page.widgets["gpu"].currentText() == "Automatic (Vulkan)"
    assert page.widgets["letterbox"].isChecked() and page.widgets["license"].currentData() == "0"
    page.widgets["scale"].setCurrentIndex(page.widgets["scale"].findData("2"))
    text = (xenia_home / emulator.CONFIG).read_text()
    assert "draw_resolution_scale_x = 2" in text and "draw_resolution_scale_y = 2" in text
    assert page.status.text() == "Resolution scale: 2x (1440p)."
    running[0] = True
    page.widgets["mute"].setChecked(True)
    assert "mute" not in (xenia_home / emulator.CONFIG).read_text() and "Xenia is running" in page.status.text()
    window.close()
