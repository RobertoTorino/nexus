# SPDX-License-Identifier: GPL-3.0-or-later
"""The window on folders made in a temp folder: the states before and after installing, the games in the table, the
game folders, the plan for Game Mode, installing through the worker, Steam's shortcuts changed with a fake "close
Steam", a newer Xenia build, and the blue look."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from conftest import make_iso, make_package

from bc250_core import steam
from xenia_manager import emulator, shortcuts, style
from xenia_manager.games import Game
from xenia_manager.main_window import MainWindow


@pytest.fixture
def folders(tmp_path):
    make_iso(tmp_path / "games" / "One.iso")
    make_package(tmp_path / "games", "Two")
    config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    config.mkdir(parents=True)
    run = tmp_path / "bin" / "bc250-xenia-run"
    run.parent.mkdir()
    run.write_text("#!/bin/sh\n")
    return {"home": tmp_path / "emulator", "steam_dir": tmp_path / "Steam", "run": run}


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
    assert "Not installed. Install downloads Xenia e6cd2e4" in window.emulator_state.text()
    assert window.install_button.isEnabled() and not window.remove_button.isEnabled()
    assert not window.xenia_button.isEnabled() and not window.play_button.isEnabled()
    assert window.folder_button.isEnabled() and not window.forget_button.isEnabled()
    assert window.table.rowCount() == 0                                          # no game folder yet
    window.close()


def test_installed_with_games(qapp, folders, tmp_path):
    _install(folders["home"])
    window = _window(folders)
    assert window.pill.text() == "No games"
    window.add_folder(tmp_path / "games")
    assert window.pill.text() == "Ready" and window.emulator_box.value.text() == emulator.VERSION
    assert "experimental on Linux" in window.emulator_state.text()
    assert window.games_box.value.text() == "2" and window.steam_box.value.text() == "0"
    assert not window.install_button.isEnabled() and window.remove_button.isEnabled()
    assert not window.play_button.isEnabled()                                     # nothing chosen yet
    window.table.selectRow(0)
    assert window.play_button.isEnabled() and window.chosen().title == "One"
    assert not window.steam_button.isEnabled()                                    # nothing to change
    assert [window.table.item(r, 2).text() for r in range(2)] == ["", "4D5307E6"]
    assert [window.table.item(r, 3).text() for r in range(2)] == ["ISO", "Games on Demand"]
    window.close()


def test_an_older_build_is_offered_the_pinned_one(qapp, folders):
    (folders["home"] / "f42147a").mkdir(parents=True)
    (folders["home"] / "f42147a" / emulator.MEMBER).write_text("")
    (folders["home"] / "current").symlink_to("f42147a")
    window = _window(folders)
    assert "Xenia f42147a is installed; this version of the app brings e6cd2e4" in window.emulator_state.text()
    assert window.install_button.isEnabled()
    window.close()


def test_game_folders_added_and_removed(qapp, folders, tmp_path):
    window = _window(folders)
    window.add_folder(tmp_path / "games")
    assert window.running.text() == f"{tmp_path / 'games'} is a game folder now: 2 game(s) in it."
    assert _titles(window) == ["One", "Two"] and window.forget_button.isEnabled()
    window.add_folder(tmp_path / "games")                                         # once only
    assert window.folders == [tmp_path / "games"]
    window.close()
    window = _window(folders)                                                     # remembered
    assert window.folders == [tmp_path / "games"] and window.games_box.value.text() == "2"
    window.forget_folder(tmp_path / "games")
    assert window.folders == [] and window.table.rowCount() == 0 and not window.forget_button.isEnabled()
    window.close()


def test_install_runs_off_the_window(qapp, folders, monkeypatch):
    payload = b"#!/bin/sh\n"
    monkeypatch.setattr(emulator, "SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = _window(folders, fetch=lambda url, dest, progress=None: dest.write_bytes(payload))
    window.on_install()
    assert not window.install_button.isEnabled()                                  # busy
    _wait(window, qapp)
    assert window.running.text() == f"Xenia {emulator.VERSION} is installed."
    assert window.version == emulator.VERSION and window.pill.text() == "No games"
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


def test_play_and_xenias_window(qapp, folders, tmp_path):
    _install(folders["home"])
    log = tmp_path / "args"
    folders["run"].write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n')
    folders["run"].chmod(0o755)
    window = _window(folders)
    window.add_folder(tmp_path / "games")
    window.table.selectRow(0)
    window.on_play()
    window.on_open_xenia()
    deadline = time.monotonic() + 10
    while (not log.exists() or len(log.read_text().splitlines()) < 2) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert sorted(log.read_text().splitlines()) == sorted([str(tmp_path / "games" / "One.iso"), ""])
    assert window.running.text() == "Started One."
    window.close()


def test_game_mode_added_and_taken_out(qapp, folders, tmp_path, monkeypatch):
    _install(folders["home"])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    closed = []
    window = _window(folders, closed=closed)
    window.add_folder(tmp_path / "games")
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
    window.add_folder(tmp_path / "games")
    window.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    window.on_update_steam()
    assert "Install Xenia first" in window.running.text() and not window.worker.running
    window.close()


def test_no_steam_game_mode_or_no_wrapper(qapp, folders, tmp_path, monkeypatch):
    _install(folders["home"])
    monkeypatch.setattr(steam, "find_steam", lambda: None)                       # None: looked up, and not found
    window = _window({**folders, "steam_dir": None})
    window.add_folder(tmp_path / "games")
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
    _install(folders["home"])
    window = _window(folders)
    assert style.BLUE in window.styleSheet()
    assert window.install_button.property("primary") and window.steam_button.property("primary")
    assert style.BLUE in window.emulator_box.styleSheet()
    assert f"color:{style.BLUE}" in window.emulator_state.text()                   # the release link
    steps = (window.install_button, window.remove_button, window.folder_button, window.forget_button)
    assert len({(b.width(), b.height()) for b in steps}) == 1                       # one size, padding included
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
    text = window.emulator_state.text()
    assert "Xenia 0a1b2c3 is out (2026-11-30)" in text and "releases/tag/0a1b2c3" in text
    assert window.install_button.isEnabled() is False                              # it never installs that one
    window.close()


def test_covers_with_the_suites_key(qapp, folders, monkeypatch, tmp_path):
    """Covers… keeps the suite's key; Update Game Mode then looks up the game by its title and puts
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
    window.add_folder(tmp_path / "games")
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
