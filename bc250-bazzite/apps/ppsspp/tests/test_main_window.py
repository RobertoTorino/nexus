# SPDX-License-Identifier: GPL-3.0-or-later
"""The window on folders made in a temp folder: the states before and after installing, the games in the table, the
game folders, the plan for Game Mode, installing through the worker, Steam's shortcuts changed with a fake "close
Steam", and the blue look."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from conftest import make_disc, make_memstick, make_pbp

from bc250_core import steam
from ppsspp_manager import LOGO_PATH, emulator, shortcuts, style
from ppsspp_manager.games import Game, memstick_game
from ppsspp_manager.main_window import MainWindow


@pytest.fixture
def folders(tmp_path):
    memstick = make_memstick(tmp_path / "ppsspp")
    make_pbp(memstick_game(memstick) / "HOMEBREW", "Two")
    make_disc(tmp_path / "games" / "one.iso", "One", "ULUS00001")
    config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    config.mkdir(parents=True)
    run = tmp_path / "bin" / "bc250-ppsspp-run"
    run.parent.mkdir()
    run.write_text("#!/bin/sh\n")
    return {"home": tmp_path / "emulator", "memstick": memstick, "steam_dir": tmp_path / "Steam", "run": run}


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


def test_before_installing(qapp, folders):
    window = _window(folders)
    assert window.pill.text() == "Not installed"
    assert "Not installed" in window.emulator_state.text()
    assert window.install_button.isEnabled() and not window.remove_button.isEnabled()
    assert not window.ppsspp_button.isEnabled()
    assert window.folder_button.isEnabled() and not window.forget_button.isEnabled()
    assert [window.table.item(r, 1).text() for r in range(window.table.rowCount())] == ["Two"]   # the memory stick
    window.close()


def test_installed_with_games(qapp, folders):
    _install(folders["home"])
    window = _window(folders)
    assert window.pill.text() == "Ready" and window.emulator_box.value.text() == emulator.VERSION
    assert window.games_box.value.text() == "1" and window.steam_box.value.text() == "0"
    assert not window.install_button.isEnabled() and window.remove_button.isEnabled()
    assert not window.play_button.isEnabled()                                   # nothing chosen yet
    window.table.selectRow(0)
    assert window.play_button.isEnabled() and window.chosen().title == "Two"
    assert not window.steam_button.isEnabled()                                  # nothing to change
    assert window.table.item(0, 3).text() == "Memory Stick"
    window.close()


def test_game_folders_added_and_removed(qapp, folders, tmp_path):
    _install(folders["home"])
    window = _window(folders)
    window.add_folder(tmp_path / "games")
    assert window.running.text() == f"{tmp_path / 'games'} is a game folder now: 1 game(s) in it."
    assert [window.table.item(r, 1).text() for r in range(2)] == ["One", "Two"]
    assert window.table.item(0, 2).text() == "ULUS00001" and window.forget_button.isEnabled()
    assert window.table.item(0, 3).text() == "ISO"
    window.add_folder(tmp_path / "games")                                       # once only
    assert window.folders == [tmp_path / "games"]
    window.close()
    window = _window(folders)                                                   # remembered
    assert window.folders == [tmp_path / "games"] and window.games_box.value.text() == "2"
    window.forget_folder(tmp_path / "games")
    assert window.folders == [] and window.table.rowCount() == 1 and not window.forget_button.isEnabled()
    window.close()


def test_rename_files_needs_a_disc_image(qapp, folders, tmp_path):
    _install(folders["home"])
    window = _window(folders)
    assert not window.rename_button.isEnabled()                                 # only the memory stick game (a PBP)
    window.add_folder(tmp_path / "games")
    assert window.rename_button.isEnabled()
    window.close()


def test_a_chd_is_marked(qapp, folders, tmp_path):
    _install(folders["home"])
    (tmp_path / "games" / "Lumines.chd").write_bytes(b"MComprHD")
    window = _window(folders)
    window.add_folder(tmp_path / "games")
    row = [window.table.item(r, 1).text() for r in range(window.table.rowCount())].index("Lumines")
    assert window.table.item(row, 3).text() == "CHD" and "not looked into" in window.table.item(row, 3).toolTip()
    window.close()


def test_install_runs_off_the_window(qapp, folders, monkeypatch):
    payload = b"#!/bin/sh\n"
    monkeypatch.setattr(emulator, "SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = _window(folders, fetch=lambda url, dest, progress=None: dest.write_bytes(payload))
    window.on_install()
    assert not window.install_button.isEnabled()                                # busy
    _wait(window, qapp)
    assert window.running.text() == f"PPSSPP {emulator.VERSION} is installed."
    assert window.version == emulator.VERSION and window.pill.text() == "Ready"
    window.close()


def test_play_and_ppsspps_window(qapp, folders, tmp_path):
    _install(folders["home"])
    log = tmp_path / "args"
    folders["run"].write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n')
    folders["run"].chmod(0o755)
    window = _window(folders)
    window.table.selectRow(0)
    window.on_play()
    window.on_open_ppsspp()
    deadline = time.monotonic() + 10
    while (not log.exists() or len(log.read_text().splitlines()) < 2) and time.monotonic() < deadline:
        time.sleep(0.01)
    pbp = memstick_game(folders["memstick"]) / "HOMEBREW" / "EBOOT.PBP"
    assert sorted(log.read_text().splitlines()) == sorted([f"{pbp}", ""])
    assert window.running.text() == "Started Two."
    window.close()


def test_game_mode_added_and_taken_out(qapp, folders, monkeypatch):
    _install(folders["home"])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    closed = []
    window = _window(folders, closed=closed)
    window.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    assert window.steam_button.isEnabled()
    add, remove = window.steam_plan()
    assert [g.title for g in add] == ["Two"] and remove == []
    window.on_update_steam()
    _wait(window, qapp)
    assert closed == [1] and window.running.text().startswith("1 game(s) in Steam")
    assert list(shortcuts.in_steam(folders["steam_dir"]).values()) == ["[PSP] Two"]
    assert window.steam_box.value.text() == "1" and window.table.item(0, 0).checkState() == Qt.CheckState.Checked
    window.table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    add, remove = window.steam_plan()
    assert add == [] and [g.title for g in remove] == ["Two"]
    window.on_update_steam()
    _wait(window, qapp)
    assert shortcuts.in_steam(folders["steam_dir"]) == {} and "1 taken out" in window.running.text()
    window.close()


def test_a_shortcut_named_before_the_system_prefix_is_renamed(qapp, folders, monkeypatch):
    """A shortcut named by the title alone, as before "[PSP] ": Update Game Mode is on for it and renames it, with
    its play time; the artwork under its old number goes."""
    _install(folders["home"])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = _window(folders)
    game = window.games[0]
    old = steam.Change(shortcuts.entry(game, game.title, folders["run"], Path("/i.png")), shortcuts.for_game(game),
                       {"p": b"P"})
    steam.write_shortcuts(folders["steam_dir"], [old])
    config = steam.user_folders(folders["steam_dir"])[0]
    values = steam.read_vdf((config / "shortcuts.vdf").read_bytes())
    values["shortcuts"]["0"]["LastPlayTime"] = 1750000000
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf(values))
    window.refresh()
    assert window.table.item(0, 0).checkState() == Qt.CheckState.Checked and window.steam_button.isEnabled()
    window.on_update_steam()
    _wait(window, qapp)
    [item] = steam.shortcuts(folders["steam_dir"])
    assert item["AppName"] == f"[PSP] {game.title}" and item["LastPlayTime"] == 1750000000
    assert not list((config / "grid").glob(f"{old.number}*")) and not window.steam_button.isEnabled()
    window.close()


def test_a_shortcut_of_a_game_no_longer_found_is_taken_out(qapp, folders):
    _install(folders["home"])
    gone = Game(Path("/old/games/gone.iso"), "Gone")
    steam.write_shortcuts(folders["steam_dir"], shortcuts.changes([gone], [], folders["run"], Path("/i.png"), {},
                                                                  art=False))
    window = _window(folders)
    add, remove = window.steam_plan()
    assert add == [] and [(str(g.file), g.title) for g in remove] == [(str(gone.file), "[PSP] Gone")]
    assert window.steam_button.isEnabled()
    window.close()


def test_no_steam_game_mode_or_no_wrapper(qapp, folders, monkeypatch):
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
    assert "install PPSSPP Manager through the portal first" in window.running.text()
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
    assert window.folder_button.width() >= window.folder_button.sizeHint().width()
    window.close()


def test_a_newer_ppsspp_is_mentioned(qapp, folders):
    from bc250_core.updates import ReleaseInfo
    _install(folders["home"])
    release = ReleaseInfo("1.21.0", "v1.21", "https://github.com/hrydgard/ppsspp/releases/tag/v1.21", "2026-11-30")
    window = _window(folders, newer_release=lambda: release)
    deadline = time.monotonic() + 10
    while window.newer is None and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    text = window.emulator_state.text()
    assert "PPSSPP 1.21.0 is out (2026-11-30)" in text and "releases/tag/v1.21" in text
    assert window.install_button.isEnabled() is False                              # it never installs that one
    window.close()


def test_covers_with_the_suites_key(qapp, folders, monkeypatch, tmp_path):
    """Covers… keeps the suite's key; Update Game Mode then looks up the games and puts the cover on the portrait, and a
    game in Steam not looked up yet makes the button do something again."""
    from PyQt6.QtGui import QColor, QImage
    from PyQt6.QtWidgets import QInputDialog

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
                                                          "url": "https://cdn2.steamgriddb.com/p.png"}]}).encode()
        return (tmp_path / "blue.png").read_bytes()
    _install(folders["home"])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    key = tmp_path / "key"
    window = _window(folders, covers_home=tmp_path / "covers", covers_get=get, covers_key=key)
    window.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    window.on_update_steam()
    _wait(window, qapp)
    assert asked == [] and not window.steam_button.isEnabled()                  # no key: nothing asked
    monkeypatch.setattr(QInputDialog, "exec", lambda self: (self.setTextValue("0123456789abcdef"), 1)[1])
    window.on_covers()
    assert key.read_text() == "0123456789abcdef\n"
    game = window.ticked()[0]
    assert window.no_cover == {str(game.file)} and window.steam_button.isEnabled()
    window.on_update_steam()
    _wait(window, qapp)
    assert window.running.text().startswith("Covers: SteamGridDB had pictures for 1 of 1 game(s).\n1 game(s) in")
    assert not any("heroes/" in url or "logos/" in url for url in asked)        # the portrait alone
    assert "0123456789abcdef" not in window.output.toPlainText()
    number = shortcuts.entry(game, "[PSP] Two", folders["run"], LOGO_PATH)["appid"] & 0xFFFFFFFF
    grid = steam.user_folders(folders["steam_dir"])[0] / "grid"
    assert QImage(str(grid / f"{number}p.png")).pixelColor(300, 450).name() == "#0000ff"
    assert window.no_cover == set() and not window.steam_button.isEnabled()
    window.close()
