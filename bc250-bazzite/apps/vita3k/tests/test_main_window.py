# SPDX-License-Identifier: GPL-3.0-or-later
"""The window on folders made in a temp folder: the states before and after installing, the firmware's three parts,
the games in the table, the firmware and games installed through a fake Vita3K, the plan for Steam, installing
through the worker, Steam's shortcuts changed with a fake "close Steam", the Settings and Log tabs, and the blue look
of RPCS3 Manager's design."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QMessageBox

from conftest import install_firmware, make_game, write_vita3k_files

from bc250_core import steam
from vita3k_manager import library, LOGO_PATH, emulator, shortcuts, style
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
    log = tmp_path / "data" / "bc250-vita3k-manager" / "bc250-vita3k-manager.log"
    log.parent.mkdir(parents=True)
    return {"home": tmp_path / "emulator", "vita3k_config": config, "steam_dir": tmp_path / "Steam", "run": run,
            "log_path": log, "user_home": tmp_path, "drives": lambda: []}


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


def test_vita3k_is_set_up_once_installed(qapp, folders):
    """Once Vita3K is installed, and while it does not run, the app turns its welcome window and its update check
    off in config.yml (owner, 03-11-2026); the Log tab says so once, and nothing is written while Vita3K runs."""
    path = folders["vita3k_config"] / "config.yml"
    before = path.read_text()
    window = _window(folders)
    assert path.read_text() == before                                                 # not installed: left alone
    window.close()
    _install(folders["home"])
    running = [True]
    window = _window(folders, vita3k_running=lambda: running[0])
    assert path.read_text() == before                                                 # Vita3K runs: left alone
    running[0] = False
    window.refresh()
    assert "show-welcome: false\n" in path.read_text() and "check-for-updates-mode: 0\n" in path.read_text()
    assert window.output.toPlainText().splitlines()[-1].endswith(" INFO Vita3K set up: its welcome window off, its update "
                                                            "check off.")
    lines = len(window.output.toPlainText().splitlines())
    window.refresh()
    assert len(window.output.toPlainText().splitlines()) == lines                      # said once
    assert window.vita_fs == folders["vita3k_config"].parent / "storage"               # pref-path still read
    window.close()


def test_no_user_name_on_the_screen(qapp, folders, tmp_path, monkeypatch):
    """The user's folders show as ~ (owner, 03-11-2026: the privacy rule): the game folder and Vita3K's storage on
    the game folder's step, the firmware folder behind its info symbol, and a message with a path in it."""
    monkeypatch.setenv("HOME", str(tmp_path))
    window = _window(folders)
    assert window.folders_state.text() == "<b>~/Games/Vita</b>"                # what goes there: the info symbol
    assert window.folders_info.text_ == ("Drop your games in ~/Games/Vita, .vpk, .zip, .pkg, zRIF license key, or "
                                         "drop a game folder there.")
    assert window.folders_state.toolTip() == "~/Games/Vita\n1 game(s) installed in Vita3K's storage, ~/storage."
    assert window.firmware_info.text_.startswith("Drop your own firmware and font package in ~/Games/Vita/Firmware. ")
    assert str(tmp_path) not in window.firmware_info.text_ + window.firmware_state.toolTip()
    window._job_done((False, f"Vita3K could not be installed: {tmp_path}/emulator is read-only"))
    assert window.running.text() == "Vita3K could not be installed: ~/emulator is read-only"
    window.close()


def test_before_installing(qapp, folders, tmp_path):
    window = _window(folders)
    assert window.pill.text() == "Not installed" and window.vita_fs == tmp_path / "storage"   # pref-path
    # The state alone, in the words every manager uses (owner, 07-11-2026); what Install does in the tip.
    assert window.emulator_state.text() == "Not installed.<br>Install it with the Install button."
    assert f"Install downloads Vita3K build {emulator.VERSION}" in window.emulator_state.toolTip()
    # The state of the firmware and of each part; where they come from: the info symbol (owner, 12-11-2026)
    assert window.firmware_state.text() == ("Not installed<br>System software: not installed<br>Font package: not "
                                            "installed<br>Preinstalled apps: not installed")
    assert window.install_pill.isEnabled() and not window.remove_pill.isEnabled()
    assert not window.game_pill.isEnabled() and not hasattr(window, "firmware_button")
    assert not window.vita3k_button.isEnabled()
    assert [window.table.item(r, 1).text() for r in range(window.table.rowCount())] == ["Two"]
    window.close()


def test_installed_with_firmware_and_games(qapp, folders, tmp_path):
    _install(folders["home"])
    window = _window(folders)
    assert window.pill.text() == "No firmware" and window.firmware_box.value.text() == "—"
    assert window.game_pill.isEnabled()
    text = window.firmware_info.text_
    assert "playstation.com/en-us/support/hardware/psvita/system-software" in text and "its official page" in text
    assert "sd_8b5f60b56c3da8365b973dba570c53a5/PSP2UPDAT.PUP" in text and "http" not in window.firmware_state.text()
    install_firmware(tmp_path / "storage", fonts=False)
    window.refresh()
    assert window.pill.text() == "No firmware" and window.firmware_box.value.text() == "Partly"
    install_firmware(tmp_path / "storage")
    window.refresh()
    assert window.pill.text() == "Ready" and window.firmware_box.value.text() == "Ready"
    assert window.firmware_state.text() == ("Installed<br>System software: installed<br>Font package: installed<br>"
                                            "Preinstalled apps: not installed")
    assert window.emulator_box.value.text() == "4269"
    assert window.games_box.value.text() == "1" and window.steam_box.value.text() == "0"
    assert window.emulator_state.text() == "Installed.<br>Uninstall with the Uninstall button."
    assert window.emulator_state.toolTip() == (f"Vita3K build {emulator.VERSION} ({emulator.SEMVER}), the build this "
                                               "version of the app was tried with")
    assert not window.install_pill.isEnabled() and window.remove_pill.isEnabled()
    assert not hasattr(window, "play_button")                   # a game is started from Steam (owner, 07-11-2026)
    assert not window.remove_game_button.isEnabled()                            # nothing chosen yet
    window.table.selectRow(0)
    assert window.remove_game_button.isEnabled() and window.chosen().title == "Two"
    assert not window.steam_button.isEnabled()                                  # nothing to change
    window.close()


def test_no_games_yet(qapp, folders, tmp_path):
    _install(folders["home"])
    install_firmware(tmp_path / "storage")
    window = _window({**folders, "vita3k_config": write_vita3k_files(tmp_path / "other", str(tmp_path / "empty"))})
    assert window.pill.text() == "No firmware"                                  # another storage: nothing there
    install_firmware(tmp_path / "empty")
    window.refresh()
    assert window.pill.text() == "No games" and "0 game(s) installed" in window.folders_state.toolTip()
    window.close()


def test_the_appimage_updated_itself(qapp, folders):
    _install(folders["home"])
    emulator.appimage(folders["home"]).write_bytes(b"another build")
    window = _window(folders)
    assert window.emulator_state.text() == "Installed.<br>Uninstall with the Uninstall button."
    assert "updated itself" in window.emulator_state.toolTip() and window.emulator_box.value.text() == "other"
    assert window.install_pill.isEnabled()                                      # puts the pinned build back
    window.close()


def test_install_runs_off_the_window(qapp, folders, monkeypatch):
    payload = b"#!/bin/sh\n"
    monkeypatch.setattr(emulator, "SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(emulator, "SIZE", len(payload))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = _window(folders, fetch=lambda url, dest, progress=None: dest.write_bytes(payload))
    window.on_install()
    assert not window.install_pill.isEnabled()                                  # busy
    _wait(window, qapp)
    assert window.running.text() == "Vita3K build 4269 is installed."
    assert window.version == "4269" and window.pill.text() == "No firmware"
    window.close()


def test_the_firmware_is_taken_from_the_apps_folder(qapp, folders, tmp_path, monkeypatch):
    """The PUP files put in Games/Vita/Firmware are given to Vita3K by themselves, the largest first, one after the
    other, once Vita3K is installed (owner, 03-11-2026): each file once as it is, not while Vita3K runs."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _install(folders["home"])
    log = tmp_path / "args"
    storage = tmp_path / "storage"
    _fake_vita3k(folders["run"], log, f'mkdir -p "{storage}/vs0/vsh" "{storage}/os0" && touch "{storage}/vs0/vsh/x"')
    home = library.firmware_home(tmp_path)
    (home / "fonts").mkdir(parents=True)
    (home / "PSP2UPDAT.PUP").write_bytes(b"\0" * 300)                          # the system software: largest
    (home / "fonts" / "PSP2UPDAT.PUP").write_bytes(b"\0" * 100)
    running = [True]
    window = _window(folders, vita3k_running=lambda: running[0])
    assert not log.exists() and window.settings.get("firmware_given") == []    # Vita3K runs: nothing yet
    running[0] = False
    window.refresh()
    _wait(window, qapp)                                                         # both files, one after the other
    assert log.read_text().splitlines() == [f"--firmware {home / 'PSP2UPDAT.PUP'}",
                                            f"--firmware {home / 'fonts' / 'PSP2UPDAT.PUP'}"]
    assert window.running.text() == "PSP2UPDAT.PUP: the system software installed."
    assert f"{home / 'PSP2UPDAT.PUP'}" not in window.output.toPlainText()       # the home folder as ~
    assert "~/Games/Vita/Firmware/PSP2UPDAT.PUP is given to Vita3K." in window.output.toPlainText()
    assert window.firmware.system and len(window.settings.get("firmware_given")) == 2
    log.unlink()
    window.refresh()
    _wait(window, qapp)
    assert not log.exists()                                                     # given once
    _fake_vita3k(folders["run"], log, f'mkdir -p "{storage}/sa0" && touch "{storage}/sa0/f"')
    (home / "fonts" / "PSP2UPDAT.PUP").write_bytes(b"\0" * 120)                 # replaced: given again
    window.refresh()
    _wait(window, qapp)
    assert log.read_text().strip().endswith("fonts/PSP2UPDAT.PUP") and window.firmware.fonts
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


def test_vita3ks_window(qapp, folders, tmp_path):
    """Vita3K settings opens Vita3K's own window, through the run wrapper and without a game."""
    _install(folders["home"])
    log = tmp_path / "args"
    _fake_vita3k(folders["run"], log)
    window = _window(folders)
    window.vita3k_button.click()
    deadline = time.monotonic() + 10
    while not log.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert log.read_text().splitlines() == [""]
    assert window.output.toPlainText().splitlines()[-1].endswith(" INFO Vita3K's own window was opened.")
    window.close()


def test_the_steam_link(qapp, folders):
    opened = []
    window = _window(folders, open_url=lambda url: opened.append(url) or True)
    window.steam_hint.linkActivated.emit("steam://open/games")
    assert opened == ["steam://open/games"]
    window.close()


def test_steam_added_and_taken_out(qapp, folders, monkeypatch):
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


def test_the_blue_look(qapp, folders, monkeypatch):
    """RPCS3 Manager's design (owner, 07-11-2026): the Refresh pill and the boxes in the header, the action pills
    under the introduction, the tabs; Games Install opens the menu of what to install from."""
    from PyQt6.QtWidgets import QMenu
    _install(folders["home"])
    window = _window(folders)
    from bc250_core.theme import OUTLINE
    assert style.BLUE in window.styleSheet()
    assert window.covers_button.property("primary") is None and window.steam_button.property("primary")
    assert window.vita3k_button.property("primary") is None
    assert style.BLUE in window.emulator_box.styleSheet() and style.BLUE in window.refresh_pill.styleSheet()
    assert f"color:{style.BLUE}" in window.intro.text()                             # the release link
    assert [(p.value.text(), p.caption.text()) for p in window.actions] == [
        ("Vita3K", "Install"), ("Vita3K", "Uninstall"), ("Games", "Install")]
    for pill in (window.refresh_pill, *window.actions):
        sheet = pill.styleSheet()                       # the blue left edge only, also under the mouse (owner)
        assert sheet.rfind(f"border-left-color:{style.BLUE}") > sheet.rfind(OUTLINE) >= 0, pill.caption.text()
        assert style.HOVER_SHEEN in sheet and style.BLUE_TINT not in sheet
    assert "QTabBar::tab" in window.styleSheet() and "QComboBox" in window.styleSheet()
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == ["Your games", "Settings", "Log",
                                                                            "Start game"]
    shown = []
    monkeypatch.setattr(QMenu, "popup", lambda menu, point, *a: shown.append(menu))
    window.game_pill.click()
    assert shown == [window.game_menu]
    assert [a.text() for a in window.game_menu.actions()] == ["From a file (.vpk, .zip, .pkg)…",
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
    tip = window.emulator_state.toolTip()                   # the line stays the state; the tip and the log say
    assert window.emulator_state.text() == "Installed.<br>Uninstall with the Uninstall button."
    assert "Vita3K build 4200 is out (2026-11-30)" in tip and "releases/tag/4200" in tip
    assert "Vita3K build 4200 is out (2026-11-30)" in window.output.toPlainText()
    assert window.install_pill.isEnabled() is False                                # it never installs that one
    window.close()


def test_the_log_tab(qapp, folders):
    """What the window says goes to the Log tab with the time, after what the log file held already."""
    folders["log_path"].write_text("07-11-2026 22:14:00 INFO Vita3K Manager 2.2.0 started\n")
    window = _window(folders)
    assert window.output.toPlainText().splitlines() == ["07-11-2026 22:14:00 INFO Vita3K Manager 2.2.0 started"]
    window.say("Steam was not changed: no Steam", ok=False)
    lines = window.output.toPlainText().splitlines()
    assert lines[-1][:19].count("-") == 2 and lines[-1][10] == " "               # DD-MM-YYYY HH:MM:SS
    assert lines[-1].endswith(" ERROR Steam was not changed: no Steam") and "c62828" in window.running.styleSheet()
    assert str(folders["log_path"]) in window.tabs.widget(2).findChildren(QLabel)[0].text()
    window.close()


def test_covers_with_the_suites_key(qapp, folders, monkeypatch, tmp_path):
    """Steam artwork… keeps the suite's key; Update Steam then looks up the games and puts the cover on the portrait,
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
    assert game.title == "Two" and window.remove_game_button.isEnabled()
    target = tmp_path / "storage" / "ux0" / "app" / "PCSE00002"
    assert target.exists()
    seen = []
    monkeypatch.setattr(KeepDialog, "exec", lambda self: (seen.append(self.items), QDialog.DialogCode.Rejected)[1])
    window.on_remove_game()
    assert [item.label for item in seen[0]] == ["The game, ux0/app/PCSE00002"] and target.exists()
    assert window.running.text() == "Nothing was deleted."

    def keep_it(self):
        self.items[0].delete = False
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(KeepDialog, "exec", keep_it)
    window.on_remove_game()
    _wait(window, qapp)
    assert target.exists() and window.running.text() == "Two: deleted nothing. Kept: The game, ux0/app/PCSE00002."
    window.table.selectRow(0)
    monkeypatch.setattr(KeepDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    window.on_remove_game()
    _wait(window, qapp)
    assert not target.exists() and window.running.text() == "Two: deleted The game, ux0/app/PCSE00002."
    assert "Two" not in [window.table.item(r, 1).text() for r in range(window.table.rowCount())]
    window.close()


def test_the_settings_tab(qapp, folders):
    """The Settings tab holds Vita3K's settings in the app (core's settings_page): the values as config.yml holds
    them, a change written into it at once, and nothing while Vita3K runs."""
    path = folders["vita3k_config"] / "config.yml"
    running = [False]
    window = _window(folders, vita3k_running=lambda: running[0])
    page = window.settings_page
    assert window.tabs.widget(1) is page and page.widgets["scale"].currentData() == "1"
    assert page.widgets["renderer"].currentText() == "Vulkan" and page.widgets["vsync"].isChecked()
    page.widgets["scale"].setCurrentIndex(page.widgets["scale"].findData("2"))
    assert "resolution-multiplier: 2" in path.read_text() and page.status.text() == "Resolution: 2x (1088p)."
    running[0] = True
    page.widgets["stretch"].setChecked(True)
    assert "stretch_the_display_area: false" in path.read_text() and "Vita3K is running" in page.status.text()
    window.close()


def test_start_game_starts_the_chosen_game_through_steam(qapp, folders, monkeypatch):
    """The Start game tab (owner, 12-11-2026), a tab that is a button: a click starts the game chosen under Your
    games through Steam, by its shortcut's number, and the open tab stays open. Without a chosen game, or with one
    that is not in Steam yet, it says what to do first and starts nothing."""
    _install(folders["home"])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    opened = []
    window = _window(folders, open_url=lambda url: opened.append(url) or True)
    tabs, start = window.tabs, window.start_tab.index
    assert start == tabs.count() - 1 and tabs.tabText(start) == "Start game" and "Steam" in tabs.tabToolTip(start)
    window.table.clearSelection()
    tabs.tabBarClicked.emit(start)                                           # no game chosen
    assert opened == [] and window.running.text().startswith("Choose a game under Your games first")
    window.table.selectRow(0)
    title = window.chosen().title
    tabs.tabBarClicked.emit(start)                                           # chosen, but not in Steam yet
    assert opened == [] and window.running.text() == (f"{title} is not in Steam yet: tick it and press Update Steam "
                                                      "first.")
    window.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    window.on_update_steam()
    _wait(window, qapp)
    window.table.selectRow(0)
    (name,) = shortcuts.in_steam(folders["steam_dir"]).values()
    tabs.setCurrentIndex(1)
    tabs.tabBarClicked.emit(start)                                           # a click on the tab
    tabs.setCurrentIndex(start)                                              # as the click goes on to select it
    assert opened == [steam.play_url(steam.appid(f'"{folders["run"]}"', name))]
    assert opened[0].startswith("steam://rungameid/") and window.running.text() == f"Steam starts {title}."
    assert tabs.currentIndex() == 1                                          # Settings is still open
    window.open_url = lambda url: False
    window.on_start_game()
    assert window.running.text() == f"{title} could not be started: xdg-open is missing."
    window.close()
