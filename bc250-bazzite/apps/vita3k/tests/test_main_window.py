# SPDX-License-Identifier: GPL-3.0-or-later
"""The window on folders made in a temp folder: the states before and after installing, the firmware's three parts,
the games in the table, the firmware and games installed through a fake Vita3K, the plan for Game Mode, installing
through the worker, Steam's shortcuts changed with a fake "close Steam", and the blue look."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from conftest import install_firmware, make_game, write_vita3k_files

from bc250_core import steam
from vita3k_manager import LOGO_PATH, emulator, shortcuts, style
from vita3k_manager.games import Game
from vita3k_manager.main_window import MainWindow


@pytest.fixture
def folders(tmp_path):
    vita_fs = tmp_path / "storage"
    config = write_vita3k_files(tmp_path / "Vita3K", str(vita_fs))
    make_game(vita_fs, "Two", "PCSE00002")
    steam_config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    steam_config.mkdir(parents=True)
    run = tmp_path / "bin" / "bc250-vita3k-run"
    run.parent.mkdir()
    run.write_text("#!/bin/sh\n")
    return {"home": tmp_path / "emulator", "vita3k_config": config, "steam_dir": tmp_path / "Steam", "run": run}


@pytest.fixture(autouse=True)
def pinned_size(monkeypatch):
    """The AppImage _install() writes (empty) is the pinned build's size."""
    monkeypatch.setattr(emulator, "SIZE", 0)


def _install(home: Path) -> None:
    (home / emulator.VERSION).mkdir(parents=True)
    (home / emulator.VERSION / emulator.MEMBER).write_text("")
    (home / "current").symlink_to(emulator.VERSION)


def _fake_vita3k(run: Path, log: Path, body: str = "") -> None:
    """A run wrapper that writes its arguments to *log*, then runs *body* (shell)."""
    run.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n{body}\n')
    run.chmod(0o755)


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


def test_before_installing(qapp, folders, tmp_path):
    window = _window(folders)
    assert window.pill.text() == "Not installed" and window.vita_fs == tmp_path / "storage"   # pref-path
    assert "Not installed" in window.emulator_state.text()
    assert window.firmware_state.text().count("not installed") == 3
    assert window.install_button.isEnabled() and not window.remove_button.isEnabled()
    assert not window.firmware_button.isEnabled() and not window.game_button.isEnabled()
    assert not window.vita3k_button.isEnabled()
    assert [window.table.item(r, 1).text() for r in range(window.table.rowCount())] == ["Two"]
    window.close()


def test_installed_with_firmware_and_games(qapp, folders, tmp_path):
    _install(folders["home"])
    window = _window(folders)
    assert window.pill.text() == "No firmware" and window.firmware_box.value.text() == "—"
    assert window.firmware_button.isEnabled() and window.game_button.isEnabled()
    text = window.firmware_state.text()
    assert "playstation.com/en-us/support/hardware/psvita/system-software" in text and "(official page)" in text
    assert "sd_8b5f60b56c3da8365b973dba570c53a5/PSP2UPDAT.PUP" in text and "(Sony's file)" in text
    install_firmware(tmp_path / "storage", fonts=False)
    window.refresh()
    assert window.pill.text() == "No firmware" and window.firmware_box.value.text() == "Partly"
    install_firmware(tmp_path / "storage")
    window.refresh()
    assert window.pill.text() == "Ready" and window.firmware_box.value.text() == "Ready"
    assert "System software: installed<br>Font package: installed" in window.firmware_state.text()
    assert "Preinstalled apps (optional): not installed" in window.firmware_state.text()
    assert window.emulator_box.value.text() == "4186"
    assert window.games_box.value.text() == "1" and window.steam_box.value.text() == "0"
    assert not window.install_button.isEnabled() and window.remove_button.isEnabled()
    assert not window.play_button.isEnabled()                                   # nothing chosen yet
    window.table.selectRow(0)
    assert window.play_button.isEnabled() and window.chosen().title == "Two"
    assert not window.steam_button.isEnabled()                                  # nothing to change
    window.close()


def test_no_games_yet(qapp, folders, tmp_path):
    _install(folders["home"])
    install_firmware(tmp_path / "storage")
    window = _window({**folders, "vita3k_config": write_vita3k_files(tmp_path / "other", str(tmp_path / "empty"))})
    assert window.pill.text() == "No firmware"                                  # another storage: nothing there
    install_firmware(tmp_path / "empty")
    window.refresh()
    assert window.pill.text() == "No games" and "None installed yet" in window.games_state.text()
    assert ".pkg with its zRIF" in window.games_state.text()
    window.close()


def test_the_appimage_updated_itself(qapp, folders):
    _install(folders["home"])
    emulator.appimage(folders["home"]).write_bytes(b"another build")
    window = _window(folders)
    assert "updated itself" in window.emulator_state.text() and window.emulator_box.value.text() == "other"
    assert window.install_button.isEnabled()                                    # puts the pinned build back
    window.close()


def test_install_runs_off_the_window(qapp, folders, monkeypatch):
    payload = b"#!/bin/sh\n"
    monkeypatch.setattr(emulator, "SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(emulator, "SIZE", len(payload))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = _window(folders, fetch=lambda url, dest, progress=None: dest.write_bytes(payload))
    window.on_install()
    assert not window.install_button.isEnabled()                                # busy
    _wait(window, qapp)
    assert window.running.text() == "Vita3K build 4186 is installed."
    assert window.version == "4186" and window.pill.text() == "No firmware"
    window.close()


def test_the_firmware_installed_through_vita3k(qapp, folders, tmp_path):
    _install(folders["home"])
    log = tmp_path / "args"
    storage = tmp_path / "storage"
    _fake_vita3k(folders["run"], log, f'mkdir -p "{storage}/vs0/vsh" "{storage}/os0" && touch "{storage}/vs0/vsh/x"')
    window = _window(folders)
    pup = tmp_path / "PSP2UPDAT.PUP"
    window.install_firmware(pup)
    _wait(window, qapp)
    assert log.read_text().strip() == f"--firmware {pup}"
    assert window.running.text() == "PSP2UPDAT.PUP: the system software installed."
    assert window.firmware.system and not window.firmware.fonts
    _fake_vita3k(folders["run"], log, f'touch "{storage}/vs0/vsh/x"')                    # the same file again
    window.install_firmware(pup)
    _wait(window, qapp)
    assert window.running.text() == "PSP2UPDAT.PUP: the system software installed."
    os.utime(storage / "vs0" / "vsh" / "x", (1000, 1000))                                 # installed long ago
    _fake_vita3k(folders["run"], log, f'mkdir -p "{storage}/sa0" "{storage}/pd0" && touch "{storage}/sa0/f" '
                                      f'"{storage}/pd0/p"')                              # Sony's two other files
    window.install_firmware(pup)
    _wait(window, qapp)
    assert window.running.text() == "PSP2UPDAT.PUP: the font package and the preinstalled apps installed."
    assert window.firmware.ready and window.firmware.preinstalled
    for part in ("sa0/f", "pd0/p"):
        os.utime(storage / part, (1000, 1000))
    _fake_vita3k(folders["run"], log, 'echo "Firmware Version file not found!"')         # a file Vita3K cannot use
    window.install_firmware(pup)
    _wait(window, qapp)
    assert window.running.text().startswith("Vita3K did not install PSP2UPDAT.PUP: nothing of the firmware was ")
    _fake_vita3k(folders["run"], log, 'echo "Firmware file not found" >&2; exit 1')
    window.install_firmware(pup)
    _wait(window, qapp)
    assert window.running.text() == "Vita3K did not install PSP2UPDAT.PUP: Firmware file not found"
    assert "color:#c62828" in window.running.styleSheet()
    window.close()


def test_a_package_installed_through_vita3k(qapp, folders, tmp_path):
    _install(folders["home"])
    log = tmp_path / "args"
    game = tmp_path / "storage" / "ux0" / "app" / "PCSB00245"
    _fake_vita3k(folders["run"], log, f'mkdir -p "{game}"')
    window = _window(folders)
    pkg = tmp_path / "Persona 4 Golden.pkg"
    window.install_package(pkg, "KO5ifR1dQ+eHBlOi")
    _wait(window, qapp)
    assert log.read_text().strip() == f"--pkg {pkg} --zrif KO5ifR1dQ+eHBlOi"
    assert window.running.text() == "Persona 4 Golden.pkg is installed: PCSB00245."
    _fake_vita3k(folders["run"], log)
    window.install_package(tmp_path / "update.pkg", "KO5i")
    _wait(window, qapp)
    assert "no new game came with it (an update goes to ux0/patch" in window.running.text()
    window.close()


def test_a_vpk_installed_in_vita3ks_window(qapp, folders, tmp_path):
    _install(folders["home"])
    log = tmp_path / "args"
    _fake_vita3k(folders["run"], log)
    window = _window(folders)
    vpk = tmp_path / "game.vpk"
    window.install_game(vpk)
    deadline = time.monotonic() + 10
    while not log.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert log.read_text().strip() == str(vpk)
    assert window.install_watch.isActive() and "starts it in its own window" in window.running.text()
    window._watch_install()
    assert window.install_watch.isActive()                                      # not there yet
    make_game(tmp_path / "storage", "Three", "PCSB00003")
    window._watch_install()
    assert not window.install_watch.isActive() and window.running.text() == "Installed in Vita3K: PCSB00003."
    assert window.games_box.value.text() == "2"
    window.close()


def test_play_and_vita3ks_window(qapp, folders, tmp_path):
    _install(folders["home"])
    log = tmp_path / "args"
    _fake_vita3k(folders["run"], log)
    window = _window(folders)
    window.table.selectRow(0)
    window.on_play()
    window.on_open_vita3k()
    deadline = time.monotonic() + 10
    while (not log.exists() or len(log.read_text().splitlines()) < 2) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert sorted(log.read_text().splitlines()) == sorted(["--frontend sdl -r PCSE00002", ""])
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
    assert shortcuts.in_steam(folders["steam_dir"]) == {"PCSE00002": "[PS Vita] Two"}
    assert window.steam_box.value.text() == "1" and window.table.item(0, 0).checkState() == Qt.CheckState.Checked
    window.table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    add, remove = window.steam_plan()
    assert add == [] and [g.title for g in remove] == ["Two"]
    window.on_update_steam()
    _wait(window, qapp)
    assert shortcuts.in_steam(folders["steam_dir"]) == {} and "1 taken out" in window.running.text()
    window.close()


def test_a_shortcut_of_a_game_no_longer_installed_is_taken_out(qapp, folders):
    _install(folders["home"])
    gone = Game(Path("/old/ux0/app/PCSB00099"), "Gone", "PCSB00099")
    steam.write_shortcuts(folders["steam_dir"], shortcuts.changes([gone], [], folders["run"], Path("/i.png"), {},
                                                                  art=False))
    window = _window(folders)
    add, remove = window.steam_plan()
    assert add == [] and [(g.name, g.title) for g in remove] == [("PCSB00099", "[PS Vita] Gone")]
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
    assert "install Vita3K Manager through the portal first" in window.running.text()
    assert not window.worker.running
    window.close()


def test_the_blue_look(qapp, folders):
    _install(folders["home"])
    window = _window(folders)
    assert style.BLUE in window.styleSheet()
    assert window.install_button.property("primary") and window.steam_button.property("primary")
    assert style.BLUE in window.emulator_box.styleSheet()
    assert f"color:{style.BLUE}" in window.emulator_state.text()                # the release link
    steps = (window.install_button, window.remove_button, window.firmware_button, window.game_button)
    assert len({(b.width(), b.height()) for b in steps}) == 1                       # one size, padding included
    assert window.firmware_button.width() >= window.firmware_button.sizeHint().width()
    assert [a.text() for a in window.game_button.menu().actions()] == ["From a file (.vpk, .zip, .pkg)…",
                                                                         "From a dumped folder…"]
    window.close()


def test_a_newer_vita3k_is_mentioned(qapp, folders):
    from bc250_core.updates import ReleaseInfo
    _install(folders["home"])
    release = ReleaseInfo("4200", "4200", "https://github.com/Vita3K/Vita3K-builds/releases/tag/4200", "2026-11-30")
    window = _window(folders, newer_release=lambda: release)
    deadline = time.monotonic() + 10
    while window.newer is None and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    text = window.emulator_state.text()
    assert "Vita3K build 4200 is out (2026-11-30)" in text and "releases/tag/4200" in text
    assert window.install_button.isEnabled() is False                              # it never installs that one
    window.close()


def test_covers_with_the_suites_key(qapp, folders, monkeypatch, tmp_path):
    """Covers… keeps the suite's key; Update Game Mode then looks up the games and puts the cover on the portrait,
    and a game in Steam not looked up yet makes the button do something again."""
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
        if "grids/" in url:
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
    assert window.no_cover == {"PCSE00002"} and window.steam_button.isEnabled()
    window.on_update_steam()
    _wait(window, qapp)
    assert window.running.text().startswith("Covers: SteamGridDB had pictures for 1 of 1 game(s).\n1 game(s) in")
    assert not any("heroes/" in url or "logos/" in url for url in asked)        # the portrait alone
    assert "0123456789abcdef" not in window.output.toPlainText()
    number = shortcuts.entry(window.games[0], "[PS Vita] Two", folders["run"], LOGO_PATH)["appid"] & 0xFFFFFFFF
    grid = steam.user_folders(folders["steam_dir"])[0] / "grid"
    assert QImage(str(grid / f"{number}p.png")).pixelColor(300, 450).name() == "#0000ff"
    assert window.no_cover == set() and not window.steam_button.isEnabled()
    window.close()
