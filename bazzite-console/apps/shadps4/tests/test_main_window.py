# SPDX-License-Identifier: GPL-3.0-or-later
"""The window on folders made in a temp folder: the states before and after installing, the system modules, the
games in the table, the game folders, the plan for Steam, installing through the worker, Steam's shortcuts changed
with a fake "close Steam", shadNet, the controller state, the play time, the Settings and Log tabs, the Steam link
and the blue look; built as PCSX2 Manager's and RPCS3 Manager's window (owner, 24-10-2026)."""

from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QLabel, QMessageBox

from conftest import make_game

from bc250_core import steam
from bc250_core.theme import GREEN, RED
from shadps4_manager import library, LOGO_PATH, emulator, shortcuts, style, userdata
from shadps4_manager.games import Game
from shadps4_manager.main_window import RUNNING, STEAM_URL, MainWindow
from shadps4_manager.settings_page import SOUND_MUTED


@pytest.fixture
def folders(tmp_path):
    games = tmp_path / "Games" / "PS4"                                         # the app's own folder
    make_game(games / "one", "One", "CUSA00001")
    make_game(games / "two", "Two", "CUSA00002")
    shad = tmp_path / "shadPS4"
    shad.mkdir()
    (shad / "config.json").write_text(json.dumps({"General": {"install_dirs": [{"enabled": True,
                                                                                 "path": str(tmp_path / "old")}]}}))
    config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    config.mkdir(parents=True)
    run = tmp_path / "bin" / "ps5-shadps4-run"
    run.parent.mkdir()
    run.write_text("#!/bin/sh\n")
    log = tmp_path / "data" / "ps5-shadps4-manager" / "ps5-shadps4-manager.log"
    log.parent.mkdir(parents=True)
    return {"home": tmp_path / "emulator", "shad_home": shad, "steam_dir": tmp_path / "Steam", "run": run,
            "log_path": log, "user_home": tmp_path, "drives": lambda: []}


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


def _click_link(qapp, label: QLabel) -> None:
    """A real mouse click on the first link of *label* (at its left edge): the signal alone proves nothing, a
    state line's link once took no click at all (owner, 24-10-2026)."""
    QTest.mouseClick(label, Qt.MouseButton.LeftButton, pos=QPoint(4, label.height() // 2))
    qapp.processEvents()


def _window(folders, **kwargs) -> MainWindow:
    closed = kwargs.pop("closed", [])
    kwargs.setdefault("newer_release", lambda: None)                         # never GitHub in a test
    kwargs.setdefault("shad_running", lambda: False)
    kwargs.setdefault("devices", folders["home"].parent / "no-devices")       # no controller, no file
    kwargs.setdefault("open_url", lambda url: True)
    kwargs.setdefault("sound_state", folders["home"].parent / "no-sound")
    return MainWindow(**folders, steam_closed=lambda change: (closed.append(1), change())[0] and False,
                      steam_running=lambda: False, **kwargs)


def test_before_installing(qapp, folders):
    window = _window(folders)
    assert window.pill.text() == "Not installed"
    assert "Not installed" in window.emulator_state.text()
    assert window.install_pill.isEnabled() and not window.remove_pill.isEnabled()
    assert not window.shad_button.isEnabled()
    assert window.refresh_pill.isEnabled() and window.package_pill.isEnabled()
    assert window.table.rowCount() == 2                                         # the folders are read all the same
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == ["Your games", "Settings", "Log"]
    assert [b.caption.text() for b in window.header_pills[1:]] == ["shadPS4 version", "Your games",
                                                                    "Available in Steam", "Play time"]
    for name in ("play_button", "nightly_check", "refresh_button", "install_button", "remove_button",
                 "modules_button", "folder_button", "extract_button", "shadnet_button", "modules_box", "latest",
                 "extract_pill", "modules_pill", "folder_pill"):                     # the last two: fixed folders
        assert not hasattr(window, name), name                               # gone (the PCSX2 pattern, the owner)
    # The action pills: what it is for in large type, what the pill does under it, the header pills' size and all
    # one width, in the owner's order (24-10-2026).
    assert [(p.value.text(), p.caption.text()) for p in window.actions] == [
        ("shadPS4", "Install"), ("shadPS4", "Uninstall"), ("Games", "Install"), ("shadNet", "Account")]
    assert all(p.sizeHint().height() == window.refresh_pill.sizeHint().height() for p in window.actions)
    window.show()                                       # spread over the width: all one width, no gap at the end
    window.centralWidget().layout().activate()
    assert len({p.width() for p in window.actions}) <= 2            # equal but for a pixel of rounding
    assert abs(window.tabs.tabBar().tabRect(0).height() - window.install_pill.height()) <= 2   # tabs as big
    assert window.account_pill.geometry().right() >= window.tabs.geometry().right() - 1
    assert len({p.width() for p in window.header_pills}) <= 2       # the header's pills spread the same way
    assert window.time_box.geometry().right() >= window.tabs.geometry().right() - 1
    window.place_states()                               # the states end at the middle of the last pill (owner)
    window.centralWidget().layout().activate()
    centre = window.time_box.mapTo(window, window.time_box.rect().center()).x()
    right = window.controller.mapTo(window, window.controller.rect().topRight()).x()
    assert abs(right - centre) <= 8 and window.pill.x() < window.shadnet_pill.x() < window.controller.x()
    assert "shadPS4's release notes" in window.intro.text() and emulator.RELEASE_PAGE in window.intro.text()
    assert ">Wiki</a>" in window.intro.text() and "Manual" not in window.intro.text()
    assert "Game Mode" not in window.intro.text() and "Big Picture Mode" in window.intro.text()
    window.close()


def test_installed_with_games(qapp, folders):
    _install(folders["home"])
    window = _window(folders)
    assert window.pill.text() == "Modules missing"
    assert window.emulator_box.value.text() == emulator.VERSION
    assert window.emulator_state.text() == f"<b>{emulator.VERSION}</b>"           # the version alone (owner)
    assert window.emulator_state.toolTip() == f"shadPS4 {emulator.VERSION}, pinned for this version of the app"
    # Ok in green or Missing sys modules in red (owner, 24-10-2026), the count and the folder in the tooltip.
    assert window.modules_state.text() == f"<b style='color:{RED};'>Missing sys modules</b>"
    assert str(folders["shad_home"] / "sys_modules") in window.modules_state.toolTip()
    assert window.games_box.value.text() == "2" and window.steam_box.value.text() == "0"
    head = window.table.horizontalHeader().model()
    assert [head.headerData(c, Qt.Orientation.Horizontal) for c in range(5)] == [
        "In Steam", "Game title", "Id", "Version", "Folder"]
    assert [window.table.item(r, 1).text() for r in range(2)] == ["One", "Two"]
    assert window.table.item(0, 2).text() == "CUSA00001" and window.table.item(0, 4).text() == "one"
    assert window.table.item(0, 4).toolTip() == str(folders["shad_home"].parent / "Games" / "PS4" / "one")
    assert not window.install_pill.isEnabled() and window.remove_pill.isEnabled()
    assert not window.steam_button.isEnabled()                                  # nothing to change
    modules = folders["shad_home"] / "sys_modules"
    modules.mkdir()
    for name in userdata.NEEDED[:3]:
        (modules / name).touch()
    window.refresh()
    assert window.modules_state.text() == f"<b style='color:{RED};'>Missing sys modules</b>"
    assert window.modules_state.toolTip().startswith(f"3 of the {len(userdata.NEEDED)} modules")
    assert "Missing: " + userdata.NEEDED[3] in window.modules_state.toolTip()
    for name in userdata.NEEDED:
        (modules / name).touch()
    window.refresh()
    assert window.pill.text() == "Ready" and window.modules_state.text() == f"<b style='color:{GREEN};'>Ok</b>"
    window.close()


def test_system_modules_are_taken_from_the_apps_folder(qapp, folders, tmp_path, monkeypatch):
    """The .sprx files put in Games/PS4/Modules are copied into shadPS4's module folder when the window opens and on
    Refresh, only what is new or changed (owner, 03-11-2026); the state follows at once."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _install(folders["home"])
    dump = library.modules_home(tmp_path)
    dump.mkdir(parents=True)
    for name in (*userdata.NEEDED[:2], "libSceNgs2.sprx"):
        (dump / name).write_bytes(b"module")
    (dump / "notes.txt").write_text("")
    window = _window(folders)
    assert window.running.text() == ("3 system module(s) taken from ~/Games/PS4/Modules into shadPS4's module "
                                     "folder.")
    target = folders["shad_home"] / "sys_modules"
    assert sorted(p.name for p in target.iterdir()) == sorted((*userdata.NEEDED[:2], "libSceNgs2.sprx"))
    assert window.modules_state.toolTip().startswith("2 of the 25 modules")
    assert "~/Games/PS4/Modules" in window.modules_state.toolTip()
    window.running.setText("")
    window.refresh()
    assert window.running.text() == ""                                          # unchanged: nothing copied again
    (dump / userdata.NEEDED[2]).write_bytes(b"module")
    window.refresh()
    assert window.running.text().startswith("1 system module(s) taken from")
    assert window.modules_state.toolTip().startswith("3 of the 25 modules")
    window.close()


def test_install_runs_off_the_window(qapp, folders, monkeypatch):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as packed:
        packed.writestr(emulator.MEMBER, "#!/bin/sh\n")
    monkeypatch.setattr(emulator, "SHA256", hashlib.sha256(payload.getvalue()).hexdigest())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = _window(folders, fetch=lambda url, dest, progress=None: dest.write_bytes(payload.getvalue()))
    window.on_install()
    assert not window.install_pill.isEnabled() and not window.refresh_pill.isEnabled()        # busy
    _wait(window, qapp)
    assert window.running.text() == f"shadPS4 {emulator.VERSION} is installed."
    assert window.version == emulator.VERSION and window.pill.text() == "Modules missing"
    assert window.refresh_pill.isEnabled()
    window.close()


def test_another_version_installed_than_the_app_brings(qapp, folders):
    """The line and box show the version alone, the advice in the tooltip and the log once (as RPCS3 Manager's); a
    nightly build from before the channel went is too long for the box."""
    (folders["home"] / "2026-10-15-b2d7ec7").mkdir(parents=True)
    (folders["home"] / "2026-10-15-b2d7ec7" / emulator.MEMBER).write_text("")
    (folders["home"] / "current").symlink_to("2026-10-15-b2d7ec7")
    window = _window(folders)
    assert window.emulator_state.text() == "<b>2026-10-15-b2d7ec7</b>" and window.emulator_box.value.text() == "other"
    assert window.emulator_state.toolTip() == (f"shadPS4 2026-10-15-b2d7ec7 is installed; this version of the app "
                                               f"brings {emulator.VERSION}: Install puts it in.")
    assert window.install_pill.isEnabled()
    window.refresh()
    assert window.output.toPlainText().count("Install puts it in") == 1                # once
    window.close()


def test_steam_added_and_taken_out(qapp, folders, monkeypatch):
    _install(folders["home"])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    closed = []
    window = _window(folders, closed=closed)
    window.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    assert window.steam_button.isEnabled()
    add, remove = window.steam_plan()
    assert [g.title for g in add] == ["One"] and remove == []
    window.on_update_steam()
    _wait(window, qapp)
    assert closed == [1] and window.running.text().startswith("1 game(s) in Steam")
    assert list(shortcuts.in_steam(folders["steam_dir"]).values()) == ["[PS4] One"]
    assert window.steam_box.value.text() == "1" and window.table.item(0, 0).checkState() == Qt.CheckState.Checked
    assert window.table.item(0, 0).toolTip() == "In Steam"
    window.table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    add, remove = window.steam_plan()
    assert add == [] and [g.title for g in remove] == ["One"]
    window.on_update_steam()
    _wait(window, qapp)
    assert shortcuts.in_steam(folders["steam_dir"]) == {} and "1 taken out" in window.running.text()
    window.close()


def test_a_shortcut_without_its_logo_is_brought_up_to_date(qapp, folders, monkeypatch):
    """A shortcut made before the app set a logo: Update Steam is on for it until the logo is there."""
    _install(folders["home"])
    game = Game(make_game(folders["shad_home"].parent / "Games" / "PS4" / "three", "Three", "CUSA00003", pictures=True),
                "Three", "CUSA00003", "01.00")
    steam.write_shortcuts(folders["steam_dir"], shortcuts.changes([game], [], folders["run"], LOGO_PATH, {}, art=False))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = _window(folders)
    assert window.no_logo == {str(game.eboot)} and window.steam_button.isEnabled()
    window.on_update_steam()
    _wait(window, qapp)
    assert window.no_logo == set() and not window.steam_button.isEnabled()
    window.close()


def test_a_shortcut_with_the_tags_of_the_old_name_is_brought_up_to_date(qapp, folders, monkeypatch):
    """A shortcut with older tags: Update Steam is on until it has the current tags."""
    _install(folders["home"])
    game = Game(make_game(folders["shad_home"].parent / "Games" / "PS4" / "four", "Four", "CUSA00004"), "Four", "CUSA00004",
                "01.00")
    old = shortcuts.entry(game, "Four", folders["run"], LOGO_PATH)
    old["tags"] = {"0": "PS4", "1": "Legacy shadPS4 Manager"}
    steam.write_shortcuts(folders["steam_dir"], [steam.Change(old, shortcuts.for_game(game))])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = _window(folders)
    assert window.old_tags == {str(game.eboot)} and window.steam_button.isEnabled()
    window.on_update_steam()
    _wait(window, qapp)
    assert window.old_tags == set() and not window.steam_button.isEnabled()
    assert list(steam.shortcuts(folders["steam_dir"])[0]["tags"].values()) == list(shortcuts.TAGS)
    window.close()


def test_a_shortcut_named_before_the_system_prefix_is_renamed(qapp, folders, monkeypatch):
    """A shortcut named by the title alone, as before "[PS4] ": Update Steam is on for it and renames it, with
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
    assert item["AppName"] == f"[PS4] {game.title}" and item["LastPlayTime"] == 1750000000
    assert not list((config / "grid").glob(f"{old.number}*")) and not window.steam_button.isEnabled()
    window.close()


def test_a_shortcut_of_a_game_no_longer_found_is_taken_out(qapp, folders):
    _install(folders["home"])
    gone = shortcuts.Game(Path("/old/games/gone/eboot.bin"), "Gone")
    steam.write_shortcuts(folders["steam_dir"], shortcuts.changes([gone], [], folders["run"], Path("/i.png"), {},
                                                                  art=False))
    window = _window(folders)
    add, remove = window.steam_plan()
    assert add == [] and [(str(g.eboot), g.title) for g in remove] == [("/old/games/gone/eboot.bin", "[PS4] Gone")]
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
    assert "install shadPS4 Manager through the portal first" in window.running.text()
    assert not window.worker.running
    window.close()


def test_the_apps_own_game_folders(qapp, folders, tmp_path, monkeypatch):
    """The games are put in Games/PS4 in the home folder, made with its Modules folder when the app opens, and in
    Games/PS4 on a removable drive that has one (owner, 03-11-2026: fixed folders, no folder choosing); shadPS4's
    own game folders (config.json) are made the same, so its own window lists the games too, not while it runs."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _install(folders["home"])
    make_game(tmp_path / "sd" / "Games" / "PS4" / "three", "Three", "CUSA00003")
    (tmp_path / "stick").mkdir()                                                # a drive without the folder
    config_path = folders["shad_home"] / "config.json"
    config = json.loads(config_path.read_text())
    config["GPU"] = {"present_mode": "Fifo"}
    config_path.write_text(json.dumps(config, indent=2))
    running = [True]
    window = _window({**folders, "drives": lambda: [tmp_path / "sd", tmp_path / "stick", tmp_path / "gone"]},
                     shad_running=lambda: running[0])
    assert window.folders == [tmp_path / "Games" / "PS4", tmp_path / "sd" / "Games" / "PS4"]
    assert (tmp_path / "Games" / "PS4" / "Modules").is_dir()                   # made for the modules
    assert [window.table.item(r, 1).text() for r in range(3)] == ["One", "Three", "Two"]
    assert userdata.game_folders(json.loads(config_path.read_text())) == [tmp_path / "old"]   # shadPS4 runs: kept
    running[0] = False
    window.refresh()
    saved = json.loads(config_path.read_text())
    assert userdata.game_folders(saved) == window.folders and saved["GPU"] == {"present_mode": "Fifo"}
    text = window.folders_state.text()
    assert "<b>~/Games/PS4</b>" in text and "<b>~/sd/Games/PS4</b>" in text and "forget:" not in text
    assert str(tmp_path) not in text and window.folders_state.toolTip().startswith("~/Games/PS4\n~/sd/Games/PS4\n3 game(s)")
    for name in ("add_folder", "forget_folder", "install_modules"):
        assert not hasattr(window, name), name
    window.close()


def test_the_settings_tab_follows_shadps4s_file(qapp, folders):
    """The Settings tab reads config.json (shadPS4's defaults where a key is missing) and writes one key the moment
    it is changed, the rest of the file kept; not while shadPS4 runs."""
    _install(folders["home"])
    running = [False]
    window = _window(folders, shad_running=lambda: running[0])
    page = window.settings_page
    assert page.widgets["present"].currentData() == "Mailbox" and page.widgets["volume"].value() == 100
    assert page.widgets["trophies"].isChecked() and page.widgets["language"].currentText() == "English (United States)"
    config_path = folders["shad_home"] / "config.json"
    config = json.loads(config_path.read_text())
    config["General"].update(volume_slider=250, trophy_popup_disabled=True, console_language=6)
    config["GPU"] = {"present_mode": "Fifo", "fsr_enabled": True}
    config_path.write_text(json.dumps(config, indent=2))
    window.refresh()
    assert page.widgets["present"].currentText() == "On" and page.widgets["fsr"].isChecked()
    assert page.widgets["volume"].value() == 250 and not page.widgets["trophies"].isChecked()
    assert page.widgets["language"].currentText() == "Dutch"
    page.widgets["trophies"].setChecked(True)                    # the key turns them off: written the other way
    page.widgets["present"].setCurrentIndex(page.widgets["present"].findData("Immediate"))
    page.widgets["cursor"].setCurrentIndex(page.widgets["cursor"].findData(2))
    saved = json.loads(config_path.read_text())
    assert saved["General"]["trophy_popup_disabled"] is False and saved["General"]["volume_slider"] == 250
    assert saved["GPU"] == {"present_mode": "Immediate", "fsr_enabled": True} and saved["Input"] == {"cursor_state": 2}
    assert saved["General"]["install_dirs"] == config["General"]["install_dirs"]
    assert page.status.text() == "Hide the mouse pointer: Always."
    running[0] = True
    page.widgets["fsr"].setChecked(False)
    assert page.status.text() == RUNNING and json.loads(config_path.read_text())["GPU"]["fsr_enabled"] is True
    assert page.widgets["fsr"].isChecked()                                      # back to what the file says
    window.close()


def test_bazzites_volume_for_shadps4(qapp, folders, tmp_path):
    """The volume Bazzite remembers for shadPS4 (WirePlumber's stream-properties): in the Settings tab's Sound box,
    and said once while shadPS4 is muted there (as on the board, 24-10-2026)."""
    state = tmp_path / "state" / "wireplumber" / "stream-properties"
    state.parent.mkdir(parents=True)
    window = _window(folders, sound_state=state)
    assert window.settings_page.system_sound.text() == "— (shadPS4 has not played yet)"
    state.write_text('[stream-properties]\nOutput/Audio:application.name:shadPS4={"volume":1.000000, '
                     '"channelMap":["FL", "FR"], "channelVolumes":[1.000000, 1.000000], "mute":true}\n')
    window.refresh()
    assert window.settings_page.system_sound.text() == "Muted" and window.running.text() == SOUND_MUTED
    window.say("something else")
    window.refresh()
    assert window.running.text() == "something else"                            # said once
    state.write_text('[stream-properties]\nOutput/Audio:application.name:shadPS4={"volume":0.700000, "mute":false}\n')
    window.refresh()
    assert window.settings_page.system_sound.text() == "70 %"
    window.close()


def test_the_play_time_in_the_header(qapp, folders):
    """The time spent in all games together, as shadPS4 counts it in play_time.txt (H:MM:SS and the last start per
    Id), with each game in the tip; a dash while there is none."""
    window = _window(folders)
    assert window.time_box.value.text() == "—" and "none yet" in window.time_box.toolTip()
    last = time.mktime((2026, 10, 24, 20, 15, 0, 0, 0, -1))
    (folders["shad_home"] / userdata.PLAY_TIME).write_text(
        f"CUSA00002 0:24:42 {last:.0f}\nCUSA99999 0:40:00\nCUSA00000 0:00:00 1\nbad line\n")
    window.refresh()
    assert window.time_box.value.text() == "1 h 4 min"
    tip = window.time_box.toolTip().splitlines()
    assert tip[1] == "CUSA99999: 40 min"
    assert tip[2] == "Two: 24 min 42 s, last played 24-10-2026 20:15"           # named from the table
    assert len(tip) == 3                                                        # a game never played is left out
    window.close()


def test_the_controller_state(qapp, folders, tmp_path):
    """Beside the title: whether a controller is connected, from the kernel's list, looked at again every few
    seconds (owner, 24-10-2026: a controller switched off by its idle timer left a game without one)."""
    from test_run_wrapper import DS4_AND_STEAM, STEAM_ONLY
    devices = tmp_path / "devices"
    devices.write_text(STEAM_ONLY)
    window = _window(folders, devices=devices)
    assert window.controller.text() == "No controller" and window.controller.kind == "warn"
    assert "PS button" in window.controller.toolTip() and window.controller_timer.isActive()
    devices.write_text(DS4_AND_STEAM)
    window.show_controller()                                                    # as the timer does
    assert window.controller.text() == "Controller connected" and window.controller.kind == "ok"
    assert "Share + Options together open shadPS4's quit window" in window.controller.toolTip()
    window.close()
    assert not window.controller_timer.isActive()


def test_the_quit_hotkeys_are_set_up_and_logged(qapp, folders):
    window = _window(folders)
    text = (folders["shad_home"] / "input_config" / "global.ini").read_text()
    assert all(line in text for line in userdata.QUIT_BINDINGS)
    assert window.output.toPlainText().count("open its quit window") == 1
    window.refresh()
    assert window.output.toPlainText().count("open its quit window") == 1        # nothing more to add
    window.close()


def test_the_steam_link(qapp, folders):
    opened = []
    window = _window(folders, open_url=lambda url: (opened.append(url), True)[1])
    assert f"href='{STEAM_URL}'" in window.steam_hint.text()
    window.steam_hint.linkActivated.emit(STEAM_URL)
    assert opened == [STEAM_URL] and "Steam was opened." in window.output.toPlainText()
    window.close()


def test_shadps4s_window(qapp, folders, tmp_path):
    """shadPS4 settings opens shadPS4's own window (Big Picture) through the run wrapper."""
    _install(folders["home"])
    log = tmp_path / "args"
    folders["run"].write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n')
    folders["run"].chmod(0o755)
    window = _window(folders)
    window.on_open_shadps4()
    deadline = time.monotonic() + 10
    while not log.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert log.read_text().splitlines() == ["-b"]
    assert "shadPS4's own window was opened." in window.output.toPlainText()
    window.close()


def test_the_log_tab(qapp, folders, tmp_path):
    """What the window says goes to the Log tab with the time, after what the log file held already."""
    folders["log_path"].write_text("24-10-2026 22:14:00 INFO shadPS4 Manager 0.11.1 started\n")
    window = _window(folders)
    lines = window.output.toPlainText().splitlines()
    assert lines[0] == "24-10-2026 22:14:00 INFO shadPS4 Manager 0.11.1 started"
    window.say("Steam was not changed: no Steam", ok=False)
    lines = window.output.toPlainText().splitlines()
    assert lines[-1].endswith(" ERROR Steam was not changed: no Steam") and "c62828" in window.running.styleSheet()
    assert lines[-1][:19].count("-") == 2 and lines[-1][10] == " "               # DD-MM-YYYY HH:MM:SS
    assert str(folders["log_path"]) in window.tabs.widget(2).findChildren(QLabel)[0].text()
    window.close()


def test_the_blue_look(qapp, folders):
    _install(folders["home"])
    window = _window(folders)
    from bc250_core.theme import OUTLINE
    assert style.BLUE in window.styleSheet()
    assert window.covers_button.property("primary") is None and window.steam_button.property("primary")
    assert style.BLUE in window.emulator_box.styleSheet() and style.BLUE in window.refresh_pill.styleSheet()
    assert f"color:{style.BLUE}" in window.intro.text()                             # the release link
    for pill in (window.refresh_pill, *window.actions):
        sheet = pill.styleSheet()                       # the blue left edge only, also under the mouse (owner)
        assert sheet.rfind(f"border-left-color:{style.BLUE}") > sheet.rfind(OUTLINE) >= 0, pill.caption.text()
        assert style.HOVER_SHEEN in sheet and style.BLUE_TINT not in sheet
    assert "QTabBar::tab" in window.styleSheet() and "QComboBox" in window.styleSheet()
    window.show()                                       # the focused Refresh pill looks as the boxes beside it
    qapp.processEvents()
    image = window.grab().toImage()
    for widget in (window.refresh_pill, window.emulator_box):
        corner = widget.mapTo(window, widget.rect().topLeft())
        samples = [image.pixelColor(corner.x() + widget.width() - 6, corner.y() + dy).name()
                   for dy in (6, widget.height() // 2, widget.height() - 6)]
        if widget is window.refresh_pill:
            refresh = samples
        else:
            assert samples == refresh
    window.close()


def test_the_settings_tab_is_not_squeezed(qapp, folders):
    """The introduction and the state lines may wrap; their minimum heights count, so the tabs below get their
    minimum and the Settings tab's rows keep their height (as RPCS3 Manager's)."""
    _install(folders["home"])
    window = _window(folders)
    window.tabs.setCurrentIndex(1)
    window.show()
    qapp.processEvents()
    assert window.tabs.height() >= window.tabs.minimumSizeHint().height()
    page = window.settings_page
    for key in ("language", "volume", "cursor", "present"):
        assert page.widgets[key].height() >= page.widgets[key].sizeHint().height(), key
    window.close()


def test_a_newer_shadps4_is_mentioned(qapp, folders):
    from bc250_core.updates import ReleaseInfo
    _install(folders["home"])
    release = ReleaseInfo("0.21.0", "v.0.21.0", "https://github.com/shadps4-emu/shadPS4/releases/tag/v.0.21.0",
                          "2026-11-20")
    window = _window(folders, newer_release=lambda: release)
    deadline = time.monotonic() + 10
    while window.newer is None and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    tip = window.emulator_state.toolTip()                   # the line stays the version; the tip and the log say
    assert window.emulator_state.text() == f"<b>{emulator.VERSION}</b>"
    assert "shadPS4 0.21.0 is out (2026-11-20)" in tip and "releases/tag/v.0.21.0" in tip
    assert "shadPS4 0.21.0 is out (2026-11-20)" in window.output.toPlainText()
    assert window.install_pill.isEnabled() is False                                # it never installs that one
    window.close()


def test_shadnet_set_up_from_the_window(qapp, folders, monkeypatch):
    from conftest import FakeShadNet, write_shad_files
    from shadps4_manager import shadnet_dialog
    shad_files = write_shad_files(folders["shad_home"])
    fake = FakeShadNet()
    window = _window(folders, shadnet_connect=fake.connect)
    assert window.shadnet_state.text() == "Off" and window.account_pill.isEnabled()

    def fill_in(dialog):
        dialog.running = lambda: False
        dialog.use.setChecked(True)
        dialog.npid.setText("Player_1")
        dialog.password.setText("secret")
        dialog.email.setText("me@example.com")
        dialog.on_create()
        deadline = time.monotonic() + 10
        while dialog.worker.running and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.01)
        qapp.processEvents()
        assert dialog.result_label.text().startswith("The account Player_1 was created on srv.shadps4.net:31313")
        dialog.on_save()
        return dialog.result()
    monkeypatch.setattr(shadnet_dialog.ShadNetDialog, "exec", fill_in)
    window.on_shadnet()
    assert fake.requests[0][1] == {1: "Player_1", 2: "secret", 4: "me@example.com"}
    assert window.shadnet_state.text() == "<b>Player_1</b>"                    # the nickname alone (owner)
    assert window.shadnet_state.toolTip() == "Player_1 (shadPS4) signs in to srv.shadps4.net:31313 when a game starts."
    assert userdata.shadnet_on(userdata.read_config(shad_files))
    assert window.running.text() == "shadNet settings saved in shadPS4's own files."
    assert "secret" not in window.output.toPlainText()
    window.close()


def test_shadnet_not_saved_while_shadps4_runs(qapp, shad_files):
    from shadps4_manager.shadnet_dialog import ShadNetDialog
    dialog = ShadNetDialog(shad_files, userdata.read_config(shad_files), userdata.read_users(shad_files),
                           running=lambda: True)
    assert not dialog.create_button.isEnabled() and dialog.save_button.isEnabled()   # off, no account: can save
    dialog.use.setChecked(True)
    assert not dialog.save_button.isEnabled()                                       # on needs an account
    dialog.npid.setText("Player_1")
    dialog.password.setText("secret")
    dialog.on_save()
    assert "close it first" in dialog.result_label.text() and not userdata.read_users(shad_files)[0].npid
    dialog.npid.setText("x")
    dialog.on_try()
    assert dialog.result_label.text().startswith("A shadNet name has 3 to 16")
    dialog.close()


def _shadnet_on(folders) -> Path:
    from conftest import write_shad_files
    home = write_shad_files(folders["shad_home"])
    userdata.save_shadnet(home, 1000, "Player_1", "secret", "", True, "srv.example:31313")
    return home


def _pill(window, qapp, text: str) -> bool:
    deadline = time.monotonic() + 10
    while window.shadnet_pill.text() != text and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    return window.shadnet_pill.text() == text


def test_shadnet_pill_off_online_offline(qapp, folders):
    from conftest import FakeShadNet
    window = _window(folders)
    assert window.shadnet_pill.text() == "shadNet Off" and window.shadnet_pill.kind == "neutral"
    window.close()
    _shadnet_on(folders)
    fake = FakeShadNet()
    window = _window(folders, shadnet_connect=fake.connect)
    assert _pill(window, qapp, "shadNet Online") and window.shadnet_pill.kind == "ok"
    assert "signs in as Player_1" in window.shadnet_pill.toolTip() and fake.requests == []   # no sign-in
    window.close()

    def refused(address, timeout):
        raise ConnectionRefusedError(111, "Connection refused")
    window = _window(folders, shadnet_connect=refused)
    assert _pill(window, qapp, "shadNet Offline") and window.shadnet_pill.kind == "bad"
    assert "could not be reached: Connection refused" in window.shadnet_pill.toolTip()
    window.close()


def test_shadnet_pill_from_shadps4_while_it_runs(qapp, folders):
    home = _shadnet_on(folders)
    (home / "log").mkdir()
    log = home / "log" / "CUSA11624.log"
    log.write_text("[ShadNet] <Info> (shadPS4:ShadNet) client.cpp:703 HandleLoginReply: Logged in npid='Player_1'\n")
    running = [True]

    def nowhere(address, timeout):
        raise AssertionError("no server check while shadPS4 runs")
    window = _window(folders, shad_running=lambda: running[0], shadnet_connect=nowhere)
    assert window.shadnet_pill.text() == "shadNet Online" and "signed in to srv.example:31313 as Player_1" in \
        window.shadnet_pill.toolTip()
    assert window.shadnet_watch.isActive()
    log.write_text("[ShadNet] <Error> (shadPS4:ShadNet) client.cpp:740 HandleLoginReply: Login rejected error code 8\n")
    window._watch_shadnet()
    assert window.shadnet_pill.text() == "shadNet Offline"
    assert window.shadnet_pill.toolTip() == "shadPS4's sign-in was refused: the password is wrong."
    window.close()


def test_covers_with_the_suites_key(qapp, folders, monkeypatch, tmp_path):
    """Steam artwork… keeps the suite's key; Update Steam then looks up the games and puts the cover on the
    portrait, and a game in Steam not looked up yet makes the button do something again."""
    from PyQt6.QtGui import QColor, QImage
    from PyQt6.QtWidgets import QInputDialog

    picture = QImage(600, 900, QImage.Format.Format_ARGB32)
    picture.fill(QColor("#0000ff"))
    picture.save(str(tmp_path / "blue.png"))
    asked = []

    def get(url: str, headers: dict[str, str]) -> bytes:
        asked.append(url)
        if "search/" in url:
            return json.dumps({"success": True, "data": [{"id": 1, "name": "One"}]}).encode()
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
    assert window.running.text() == "The SteamGridDB key was changed."
    assert window.no_cover == {str(window.games[0].eboot)} and window.steam_button.isEnabled()
    window.on_update_steam()
    _wait(window, qapp)
    assert window.running.text().startswith("Covers: SteamGridDB had pictures for 1 of 1 game(s).\n1 game(s) in")
    assert not any("heroes/" in url or "logos/" in url for url in asked)        # the portrait alone
    assert "0123456789abcdef" not in window.output.toPlainText()
    number = shortcuts.entry(window.games[0], "[PS4] One", folders["run"], LOGO_PATH)["appid"] & 0xFFFFFFFF
    grid = steam.user_folders(folders["steam_dir"])[0] / "grid"
    assert QImage(str(grid / f"{number}p.png")).pixelColor(300, 450).name() == "#0000ff"
    assert window.no_cover == set() and not window.steam_button.isEnabled()
    window.close()


def test_unmute_bazzites_volume(qapp, folders, tmp_path):
    """Unmute beside Bazzite's volume (owner, 24-10-2026): shown while shadPS4 is muted there only; a click runs
    core's unmute off the window and the row follows what WirePlumber stored; a failure is said in red."""
    state = tmp_path / "state" / "wireplumber" / "stream-properties"
    state.parent.mkdir(parents=True)
    state.write_text('[stream-properties]\nOutput/Audio:application.name:shadPS4={"volume":1.000000, "mute":true}\n')
    window = _window(folders, sound_state=state)
    page = window.settings_page
    window.tabs.setCurrentIndex(1)
    window.show()
    qapp.processEvents()
    assert page.sound_path == state and page.unmute_button.isVisible()
    asked = []

    def unmute(name, path):
        asked.append((name, path))
        path.write_text('[stream-properties]\nOutput/Audio:application.name:shadPS4={"volume":1.000000, "mute":false}\n')
        return 1.0, False
    page.unmute = unmute
    page.unmute_button.click()
    deadline = time.monotonic() + 10
    while page.unmuting.running and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    assert asked == [("shadPS4", state)]
    assert page.status.text() == "shadPS4's sound is on again in Bazzite's sound settings."
    assert page.system_sound.text() == "100 %" and not page.unmute_button.isVisible()

    def refused(name, path):
        from bc250_core import sound
        raise sound.SoundError("pactl is not installed: Unmute needs PipeWire's PulseAudio tools (pactl and paplay).")
    state.write_text('[stream-properties]\nOutput/Audio:application.name:shadPS4={"volume":1.000000, "mute":true}\n')
    window.refresh()
    page.unmute = refused
    page.unmute_button.click()
    deadline = time.monotonic() + 10
    while page.unmuting.running and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    assert page.status.text().startswith("pactl is not installed") and "c62828" in page.status.styleSheet()
    assert page.unmute_button.isVisible() and page.unmute_button.isEnabled()
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
    target = tmp_path / "Games" / "PS4" / "one"
    assert target.exists()
    seen = []
    monkeypatch.setattr(KeepDialog, "exec", lambda self: (seen.append(self.items), QDialog.DialogCode.Rejected)[1])
    window.on_remove_game()
    assert [item.label for item in seen[0]] == ["one (the game's folder)"] and target.exists()
    assert window.running.text() == "Nothing was deleted."

    def keep_it(self):
        self.items[0].delete = False
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(KeepDialog, "exec", keep_it)
    window.on_remove_game()
    _wait(window, qapp)
    assert target.exists() and window.running.text() == "One: deleted nothing. Kept: one (the game's folder)."
    window.table.selectRow(0)
    monkeypatch.setattr(KeepDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    window.on_remove_game()
    _wait(window, qapp)
    assert not target.exists() and window.running.text() == "One: deleted one (the game's folder)."
    assert "One" not in [window.table.item(r, 1).text() for r in range(window.table.rowCount())]
    window.close()


def test_packages_in_a_game_folder_wait_as_rows_and_unpack_all_takes_the_game_first(qapp, folders, built_pkg,
                                                                                    monkeypatch, tmp_path):
    """A .pkg put in a game folder (owner, 05-11-2026, as the Windows Portable Suite's): a row of its own, PKG or PKG
    update, after the games; an update whose game still waits says so; Unpack all unpacks the game first and its
    update beside it, then the keep window offers the packages: kept ones are no longer rows, deleted ones are gone."""
    import shutil
    from PyQt6.QtWidgets import QDialog
    from bc250_core.keep_dialog import KeepDialog
    from pkg_builder import build_pkg, default_tree
    games = tmp_path / "Games" / "PS4"
    shutil.copy(built_pkg.path, games / "game.pkg")
    build_pkg(games / "update.pkg", default_tree(), category="gp", app_ver="01.01")
    window = _window(folders)
    assert [p.path.name for p in window.waiting] == ["game.pkg", "update.pkg"]
    rows = window.table.rowCount()
    assert rows == len(window.games) + 2
    assert [window.table.item(r, 0).text() for r in (rows - 2, rows - 1)] == ["PKG", "PKG"]   # its game waits too
    assert not window.table.item(rows - 1, 0).flags() & Qt.ItemFlag.ItemIsUserCheckable        # not for Steam
    assert window.unpack_all_button.isVisible() or not window.isVisible()
    assert window.unpack_all_button.isEnabled() and not window.unpack_button.isEnabled()
    window.table.selectRow(rows - 1)
    assert window.chosen_package().path.name == "update.pkg" and window.chosen() is None
    window.on_unpack()                                              # the update alone: its game first
    assert "is an update: unpack its game first" in window.running.text() and not window.worker.running
    offered = []
    monkeypatch.setattr(KeepDialog, "exec", lambda self: (offered.append([i.label for i in self.items]),
                                                          QDialog.DialogCode.Rejected)[1])
    window.on_unpack_all()
    _wait(window, qapp)
    qapp.processEvents()
    game_id = built_pkg.title_id
    assert (games / game_id / "eboot.bin").is_file() and (games / f"{game_id}-UPDATE" / "eboot.bin").is_file()
    assert offered and len(offered[0]) == 2 and "game.pkg" in offered[0][0]
    assert window.waiting == [] and (games / "game.pkg").is_file()               # kept, and no longer waiting
    assert window.unpacked_packages()
    # Another one, deleted after: Delete marked.
    build_pkg(games / "other.pkg", default_tree(), content_id="UP9000-CUSA77777_00-SYNTHETICPKG0002")
    window.refresh()
    assert [p.path.name for p in window.waiting] == ["other.pkg"]
    monkeypatch.setattr(KeepDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    window.unpack_packages(window.waiting)
    _wait(window, qapp)
    qapp.processEvents()
    assert not (games / "other.pkg").exists() and (games / "CUSA77777" / "eboot.bin").is_file()
    assert window.running.text() == "Packages deleted." and not window.unpack_all_button.isVisible()
    window.close()
