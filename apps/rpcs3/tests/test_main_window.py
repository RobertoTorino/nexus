# SPDX-License-Identifier: GPL-3.0-or-later
"""The window on folders made in a temp folder: the states before and after installing, the firmware, the games in
the table, the game folders, the packages, each game's screen, RPCS3's files set up (its GUI settings, player 1),
the plan for Steam, installing through the worker, Steam's shortcuts changed with a fake "close Steam", the
controller state, the play time, the Log tab, the Steam link and the blue look; built as PCSX2 Manager's window
(owner, 24-10-2026)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QLabel, QMessageBox

from conftest import make_disc_game, make_hdd_game, write_rpcs3_files

from bc250_core import steam
from rpcs3_manager import LOGO_PATH, emulator, shortcuts, style, userdata
from rpcs3_manager.games import Game
from rpcs3_manager.main_window import RUNNING, RUNNING_INSTALL, STEAM_URL, MainWindow, install_message
from rpcs3_manager.settings_page import SOUND_MUTED

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def folders(tmp_path):
    rpcs3 = write_rpcs3_files(tmp_path / "rpcs3", firmware=None)
    make_hdd_game(rpcs3 / "dev_hdd0" / "game" / "NPUB00002", "Two", "NPUB00002")
    make_disc_game(tmp_path / "games" / "one", "One", "BLUS00001")
    config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    config.mkdir(parents=True)
    run = tmp_path / "bin" / "bc250-rpcs3-run"
    run.parent.mkdir()
    run.write_text("#!/bin/sh\n")
    log = tmp_path / "data" / "bc250-rpcs3-manager" / "bc250-rpcs3-manager.log"
    log.parent.mkdir(parents=True)
    return {"home": tmp_path / "emulator", "rpcs3_home": rpcs3, "steam_dir": tmp_path / "Steam", "run": run,
            "log_path": log}


@pytest.fixture(autouse=True)
def pinned_size(monkeypatch):
    """The AppImage _install() writes (empty) is the pinned build's size."""
    monkeypatch.setattr(emulator, "SIZE", 0)


def _install(home: Path) -> None:
    (home / emulator.VERSION).mkdir(parents=True)
    (home / emulator.VERSION / emulator.MEMBER).write_text("")
    (home / "current").symlink_to(emulator.VERSION)


def _firmware(rpcs3: Path, text: str = "release:04.9200:\n") -> None:
    version = rpcs3 / "dev_flash" / "vsh" / "etc" / "version.txt"
    version.parent.mkdir(parents=True, exist_ok=True)
    version.write_text(text)


def _wait(window, qapp) -> None:
    deadline = time.monotonic() + 10
    while window.worker.running and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()


def _window(folders, **kwargs) -> MainWindow:
    closed = kwargs.pop("closed", [])
    kwargs.setdefault("newer_release", lambda: None)                         # never GitHub in a test
    kwargs.setdefault("devices", folders["home"].parent / "no-devices")       # no controller, no file
    kwargs.setdefault("rpcs3_running", lambda: False)
    kwargs.setdefault("sdl_names", lambda: [])                                # never SDL in a test
    kwargs.setdefault("open_url", lambda url: True)
    return MainWindow(**folders, steam_closed=lambda change: (closed.append(1), change())[0] and False,
                      steam_running=lambda: False, **kwargs)


def test_before_installing(qapp, folders):
    window = _window(folders)
    assert window.pill.text() == "Not installed"
    assert "Not installed" in window.emulator_state.text() and "No firmware" in window.firmware_state.text()
    assert window.install_pill.isEnabled() and not window.remove_pill.isEnabled()
    assert not window.firmware_pill.isEnabled() and not window.rpcs3_button.isEnabled()
    assert window.refresh_pill.isEnabled()
    assert window.folder_pill.isEnabled() and not window.package_pill.isEnabled()
    assert [window.table.item(r, 1).text() for r in range(window.table.rowCount())] == ["Two"]   # RPCS3's own
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == ["Your games", "Settings", "Log"]
    assert [b.caption.text() for b in window.header_pills[1:]] == ["RPCS3 version", "Your games",
                                                                    "Available in Steam", "Play time"]
    for name in ("play_button", "firmware_box", "refresh_button", "install_button", "remove_button",
                 "firmware_button", "folder_button", "forget_button", "forget_pill", "folders_state"):
        assert not hasattr(window, name), name                               # gone (the PCSX2 pattern, the owner)
    # The action pills: what it is for in large type, what the pill does under it, the header pills' size and all
    # one width (owner, 24-10-2026: Games Install in place of Remove folder, which is a link in the Disc games line).
    assert [(p.value.text(), p.caption.text()) for p in window.actions] == [
        ("RPCS3", "Install"), ("RPCS3", "Uninstall"), ("Firmware", "Install"), ("Games", "Install"),
        ("Games", "Add folder")]
    assert all(p.sizeHint().height() == window.refresh_pill.sizeHint().height() for p in window.actions)
    window.show()                                       # spread over the width: all one width, no gap at the end
    window.centralWidget().layout().activate()
    assert len({p.width() for p in window.actions}) <= 2            # equal but for a pixel of rounding
    assert abs(window.tabs.tabBar().tabRect(0).height() - window.install_pill.height()) <= 2   # tabs as big
    assert window.folder_pill.geometry().right() >= window.tabs.geometry().right() - 1
    assert len({p.width() for p in window.header_pills}) <= 2       # the header's pills spread the same way
    assert window.time_box.geometry().right() >= window.tabs.geometry().right() - 1
    window.place_states()                               # the states end at the middle of the last pill (owner)
    window.centralWidget().layout().activate()
    centre = window.time_box.mapTo(window, window.time_box.rect().center()).x()
    right = window.controller.mapTo(window, window.controller.rect().topRight()).x()
    assert abs(right - centre) <= 8 and window.pill.x() < window.controller.x()
    assert "RPCS3's release notes" in window.intro.text() and emulator.RELEASE_PAGE in window.intro.text()
    assert ">Wiki</a>" in window.intro.text() and "Manual" not in window.intro.text()
    assert "Game Mode" not in window.intro.text() and "Big Picture Mode" in window.intro.text()
    window.close()


def test_installed_with_firmware_and_games(qapp, folders):
    _install(folders["home"])
    window = _window(folders)
    assert window.pill.text() == "No firmware"
    assert window.firmware_pill.isEnabled() and window.rpcs3_button.isEnabled()
    assert "playstation.com" in window.firmware_state.text()
    assert ">PlayStation's firmware page</a>" in window.firmware_state.text()
    assert "Firmware Install" in window.firmware_state.text()
    _firmware(folders["rpcs3_home"])
    window.refresh()
    assert window.pill.text() == "Ready"
    # The state lines are the version alone (owner, 24-10-2026), the rest in the tips.
    assert window.firmware_state.text() == "<b>4.92</b>"
    assert window.firmware_state.toolTip().startswith("PS3 firmware 4.92 in RPCS3's firmware folder: ")
    assert str(folders["rpcs3_home"] / "dev_flash") in window.firmware_state.toolTip()     # the path as the tip
    assert window.emulator_box.value.text() == emulator.LANDMARK
    assert window.emulator_state.text() == f"<b>{emulator.LANDMARK}</b>"
    assert window.emulator_state.toolTip() == f"RPCS3 {emulator.VERSION}, the build this version of the app was tried with"
    # PKG games: RPCS3's games folder within its own folder, the count in the tip (owner, 24-10-2026).
    assert window.pkg_state.text() == "<b>dev_hdd0/game/</b>"
    assert window.pkg_state.toolTip().startswith(
        f"1 game(s) installed in RPCS3's games folder: {folders['rpcs3_home'] / 'dev_hdd0' / 'game'}\n")
    assert "Install takes the folder with your .pkg files" in window.pkg_state.toolTip()
    assert window.disc_state.text().startswith("None yet: Add folder takes the folder with your disc games")
    assert window.games_box.value.text() == "1" and window.steam_box.value.text() == "0"
    assert not window.install_pill.isEnabled() and window.remove_pill.isEnabled() and window.package_pill.isEnabled()
    head = window.table.horizontalHeader().model()
    assert [head.headerData(c, Qt.Orientation.Horizontal) for c in range(6)] == [
        "In Steam", "Game title", "Id", "Version", "Folder", "Screen setting"]
    assert window.table.item(0, 2).text() == "NPUB00002" and window.table.item(0, 4).text() == "NPUB00002"
    assert window.table.item(0, 4).toolTip() == str(folders["rpcs3_home"] / "dev_hdd0" / "game" / "NPUB00002")
    assert not window.steam_button.isEnabled()                                  # nothing to change
    window.close()


def test_rpcs3_is_set_up_once_installed(qapp, folders, tmp_path):
    """Before RPCS3 is installed nothing is written; then its GUI settings get what the app owns (its welcome dialog
    and its update check off) and, with a controller connected, player 1 goes on it as SDL names it. While RPCS3
    runs its files are left alone, and a pad file RPCS3 wrote itself too."""
    from test_run_wrapper import DS4_AND_STEAM
    gui = folders["rpcs3_home"] / userdata.GUI_SETTINGS
    pads = folders["rpcs3_home"] / userdata.INPUT_CONFIG
    devices = tmp_path / "devices"
    devices.write_text(DS4_AND_STEAM)
    asked = []

    def sdl_names():
        asked.append(1)
        return ["DualShock 4 Wireless Controller"]
    window = _window(folders, devices=devices, sdl_names=sdl_names)
    assert not gui.exists() and not pads.exists() and asked == []
    window.close()
    _install(folders["home"])
    running = [True]
    window = _window(folders, devices=devices, sdl_names=sdl_names, rpcs3_running=lambda: running[0])
    assert not gui.exists() and not pads.exists() and asked == []
    running[0] = False
    window.refresh()
    assert gui.read_text() == ("[main_window]\ninfoBoxEnabledWelcome=false\n\n[Meta]\ncheckUpdateStart=false\n"
                               "currentStylesheet=Darker Style by TheMitoSan\n")      # the suite's theme is dark
    assert asked == [1] and pads.read_text().startswith(userdata.PAD_MARK)
    assert '  Device: "DualShock 4 Wireless Controller 1"' in pads.read_text()
    assert "    Cross: South" in pads.read_text() and "Player 2 Input" not in pads.read_text()
    lines = window.output.toPlainText().splitlines()
    assert lines[-2].endswith("RPCS3 set up: its welcome dialog off, its own update check off, its dark style.")
    assert lines[-1].endswith("RPCS3 set up: player 1 on DualShock 4 Wireless Controller 1.")
    window.refresh()                                                            # nothing more to do or ask
    assert asked == [1] and len(window.output.toPlainText().splitlines()) == len(lines)
    window.show_controller()
    assert asked == [1]
    # The controllers change: asked again, the file rewritten.
    devices.write_text(DS4_AND_STEAM.replace("Wireless Controller", "Other Pad"))
    window.show_controller()
    assert asked == [1, 1] and '  Device: "DualShock 4 Wireless Controller 1"' in pads.read_text()   # SDL's name
    # A file RPCS3 wrote itself (no mark of the app's) is never touched; RPCS3's GUI settings keep the rest.
    pads.write_text("Player 1 Input:\n  Handler: DualSense\n  Device: DualSense Pad #1\n")
    gui.write_text("[main_window]\ngeometry=@ByteArray(x)\ninfoBoxEnabledWelcome=true\n")
    devices.write_text(DS4_AND_STEAM)
    window.refresh()
    assert pads.read_text().startswith("Player 1 Input:\n  Handler: DualSense") and asked == [1, 1]
    assert gui.read_text() == ("[main_window]\ngeometry=@ByteArray(x)\ninfoBoxEnabledWelcome=false\n\n"
                               "[Meta]\ncheckUpdateStart=false\ncurrentStylesheet=Darker Style by TheMitoSan\n")
    window.close()


def test_without_sdl3_the_kernels_names_are_used(qapp, folders, tmp_path):
    from test_run_wrapper import DS4_AND_STEAM
    _install(folders["home"])
    devices = tmp_path / "devices"
    devices.write_text(DS4_AND_STEAM)
    window = _window(folders, devices=devices, sdl_names=lambda: None)
    text = (folders["rpcs3_home"] / userdata.INPUT_CONFIG).read_text()
    assert '  Device: "Sony Interactive Entertainment Wireless Controller 1"' in text
    assert "SDL3 was not found to ask" in window.running.text()
    window.close()


def test_packages_installed_through_rpcs3_without_its_window(qapp, folders, tmp_path):
    """Games Install runs RPCS3 headless once per file (--headless --installpkg; owner, 24-10-2026): the licenses
    first, then the packages, the updates last (a fake RPCS3 that writes RPCS3's log lines and the files RPCS3
    would); the result comes from RPCS3's log and the state follows. A folder without a package or license is
    refused here, a subfolder's files are not RPCS3's to take, and nothing runs while RPCS3 does."""
    _install(folders["home"])
    args = tmp_path / "args"
    rpcs3_log = tmp_path / "cache" / "rpcs3" / "RPCS3.log"
    rpcs3_log.parent.mkdir(parents=True)
    hdd0 = folders["rpcs3_home"] / "dev_hdd0"
    ready = make_hdd_game(tmp_path / "ready" / "NPUB00003", "Three", "NPUB00003").parent.parent
    folders["run"].write_text(f"""#!/bin/sh
echo "$@" >> "{args}"
case "$3" in
  *.rap) mkdir -p "{hdd0}/home/00000001/exdata" && cp "$3" "{hdd0}/home/00000001/exdata/"
         printf '·S 0:00:00.1 GUI: Successfully copied rap file: %s\\n' "$(basename "$3")" > "{rpcs3_log}" ;;
  *Game.PKG) cp -r "{ready}" "{hdd0}/game/"
         printf '·S 0:01:00.1 GUI: Successfully installed %s (title_id=NPUB00003, title=Three, version=01.00).\\n' \\
             "$3" > "{rpcs3_log}" ;;
  *) printf '·E 0:00:00.3 GUI: Cannot install invalid package: %s\\n' "''" > "{rpcs3_log}" ;;
esac
""")
    folders["run"].chmod(0o755)
    running = [False]
    window = _window(folders, rpcs3_log=rpcs3_log, rpcs3_running=lambda: running[0])
    window.install_packages(tmp_path / "games")                                 # disc games only
    assert window.running.text() == "No .pkg, .rap or .edat file in games." and not args.exists()
    packages = tmp_path / "pkgs"
    (packages / "sub").mkdir(parents=True)
    (packages / "Game.PKG").write_bytes((FIXTURES / "game.pkg.head").read_bytes())
    (packages / "A-Update.pkg").write_bytes((FIXTURES / "update.pkg.head").read_bytes())  # by name, first
    (packages / "sub" / "Other.pkg").write_bytes((FIXTURES / "dlc.pkg.head").read_bytes())  # not RPCS3's
    (packages / "Game.rap").write_bytes(b"\0" * 16)
    running[0] = True
    window.install_packages(packages)
    assert window.running.text() == RUNNING_INSTALL and not args.exists()
    running[0] = False
    window.install_packages(packages)
    assert window.running.text().startswith("RPCS3 installs 2 package(s) and 1 license(s) from pkgs, without its "
                                            "window…")
    assert not window.package_pill.isEnabled() and not window.install_pill.isEnabled()
    _wait(window, qapp)
    assert args.read_text().splitlines() == [f"--headless --installpkg {packages / 'Game.rap'}",
                                             f"--headless --installpkg {packages / 'Game.PKG'}",
                                             f"--headless --installpkg {packages / 'A-Update.pkg'}"]
    assert window.running.text() == ("1 game(s) installed in RPCS3: Three (NPUB00003); 1 license(s) copied into "
                                     f"RPCS3; 1 file(s) that are no PS3 package. RPCS3's log: {rpcs3_log}")
    assert window.pkg_state.text() == "<b>dev_hdd0/game/</b>" and window.games_box.value.text() == "2"
    assert window.package_pill.isEnabled()
    window.close()


def test_what_an_install_says(tmp_path):
    """The message after an install: RPCS3's log first, the files that came when the log says nothing."""
    log = tmp_path / "RPCS3.log"
    report = userdata.InstallReport()
    assert install_message(report, 0, 0, "pkgs", log) == (False, f"RPCS3 installed nothing from pkgs. RPCS3's log: {log}")
    assert install_message(report, 1, 2, "pkgs", log) == (True, "1 game(s) installed in RPCS3; 2 license(s) copied "
                                                                "into RPCS3.")
    report = userdata.InstallReport(installed=[("Three", "NPUB00003"), ("Four", "")], copied=["a.rap"],
                                    failed=[("Five", "NPUB00005")], not_copied=["b.edat"])
    ok, text = install_message(report, 2, 1, "pkgs", log)
    assert not ok and text == ("2 game(s) installed in RPCS3: Three (NPUB00003), Four; 1 license(s) copied into "
                               "RPCS3; 1 package(s) RPCS3 could not install: Five (NPUB00005); 1 license(s) RPCS3 "
                               f"could not copy: b.edat. RPCS3's log: {log}")


def test_bazzites_volume_for_rpcs3(qapp, folders, tmp_path):
    """The volume Bazzite remembers for RPCS3 (WirePlumber's stream-properties): in the Settings tab's Sound box,
    and said once while RPCS3 is muted there (found on the board, 24-10-2026)."""
    state = tmp_path / "state" / "wireplumber" / "stream-properties"
    state.parent.mkdir(parents=True)
    window = _window(folders, sound_state=state)
    assert window.settings_page.system_sound.text() == "— (RPCS3 has not played yet)"
    state.write_text('[stream-properties]\nOutput/Audio:application.name:RPCS3={"volume":1.000000, "mute":true, '
                     '"channelVolumes":[1.000000, 1.000000], "channelMap":["FL", "FR"]}\n')
    window.refresh()
    assert window.settings_page.system_sound.text() == "Muted" and window.running.text() == SOUND_MUTED
    assert "color:#c62828" in window.settings_page.system_sound.styleSheet()
    window.say("something else")
    window.refresh()
    assert window.running.text() == "something else"                            # said once
    state.write_text('[stream-properties]\nOutput/Audio:application.name:RPCS3={"volume":0.700000, "mute":false}\n')
    window.refresh()
    assert window.settings_page.system_sound.text() == "70 %" and window.settings_page.system_sound.styleSheet() == ""
    assert window.output.toPlainText().count("muted in Bazzite") == 1
    window.close()


def test_each_games_screen(qapp, folders, tmp_path):
    """The Screen setting column: 16:9 (RPCS3's default), 4:3 or Fill screen, kept in the game's own settings in
    RPCS3 (custom_configs); a file RPCS3 wrote keeps its other lines; nothing is written while RPCS3 runs."""
    _install(folders["home"])
    running = [False]
    window = _window(folders, rpcs3_running=lambda: running[0])
    window.add_folder(tmp_path / "games")
    rows = {window.table.item(r, 1).text(): r for r in range(window.table.rowCount())}
    one = window.table.cellWidget(rows["One"], 5)
    assert [one.itemText(i) for i in range(one.count())] == ["16:9", "4:3", "Fill screen"]
    assert one.currentData() == userdata.WIDE
    path = userdata.game_config(folders["rpcs3_home"], "BLUS00001")
    assert path == folders["rpcs3_home"] / "custom_configs" / "config_BLUS00001.yml"
    one.setCurrentIndex(one.findData(userdata.FILL))
    assert path.read_text() == "Video:\n  Stretch To Display Area: true\n  Aspect ratio: 16:9\n"
    assert window.running.text() == "One: Fill screen."
    path.write_text("Core:\n  PPU Decoder: Recompiler (LLVM)\nVideo:\n  Aspect ratio: 16:9\n  Renderer: Vulkan\n"
                    "  Stretch To Display Area: false\n")                     # as RPCS3's own window writes it
    window.refresh()
    one = window.table.cellWidget(rows["One"], 5)
    assert one.currentData() == userdata.WIDE
    one.setCurrentIndex(one.findData(userdata.NARROW))
    assert path.read_text() == ("Core:\n  PPU Decoder: Recompiler (LLVM)\nVideo:\n  Aspect ratio: 4:3\n"
                                "  Renderer: Vulkan\n  Stretch To Display Area: false\n")
    running[0] = True
    one = window.table.cellWidget(rows["One"], 5)
    one.setCurrentIndex(one.findData(userdata.FILL))
    assert window.running.text() == RUNNING
    assert userdata.read_screen(path) == userdata.NARROW                        # unchanged
    assert window.table.cellWidget(rows["One"], 5).currentData() == userdata.NARROW
    window.close()


def test_the_settings_tab_follows_rpcs3s_file(qapp, folders):
    _install(folders["home"])
    window = _window(folders)
    assert window.settings_page.widgets["scale"].currentData() == "100"
    (folders["rpcs3_home"] / "config.yml").write_text("Video:\n  Resolution Scale: 200\n")
    window.refresh()
    assert window.settings_page.widgets["scale"].currentData() == "200"
    window.settings_page.widgets["vsync"].setCurrentIndex(1)
    assert window.settings_page.status.text() == "VSync: On."
    assert "VSync Mode: Full" in (folders["rpcs3_home"] / "config.yml").read_text()
    window.close()


def test_the_steam_link(qapp, folders):
    """The hint under the games links to Steam: the app opens Steam's library (Steam starts when it does not run)."""
    opened = []
    window = _window(folders, open_url=lambda url: (opened.append(url), True)[1])
    assert f"href='{STEAM_URL}'" in window.steam_hint.text()
    window.steam_hint.linkActivated.emit(STEAM_URL)
    assert opened == [STEAM_URL] and "Steam was opened." in window.output.toPlainText()
    window.close()
    window = _window(folders, open_url=lambda url: False)
    window.open_steam()
    assert window.running.text() == "Steam could not be opened: xdg-open is missing."
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
    assert window.controller_timer.interval() == window.CONTROLLER_POLL
    devices.write_text(DS4_AND_STEAM)
    window.show_controller()                                                    # as the timer does
    assert window.controller.text() == "Controller connected" and window.controller.kind == "ok"
    assert "Sony Interactive Entertainment Wireless Controller" in window.controller.toolTip()
    assert "Share + Options together open RPCS3's menu" in window.controller.toolTip()   # the way out of a game
    devices.unlink()
    window.show_controller()
    assert window.controller.text() == "No controller"
    window.close()
    assert not window.controller_timer.isActive()


def test_the_play_time_in_the_header(qapp, folders):
    """The time spent in all games together, as RPCS3 counts it in persistent_settings.dat (milliseconds per
    serial), with each game in the tip; a dash while there is none."""
    _install(folders["home"])
    window = _window(folders)
    assert window.time_box.value.text() == "—" and "none yet" in window.time_box.toolTip()
    (folders["rpcs3_home"] / "GuiConfigs").mkdir(exist_ok=True)              # the app's set-up made it already
    (folders["rpcs3_home"] / "GuiConfigs" / "persistent_settings.dat").write_text(
        "[Playtime]\nNPUB00002=1482000\nBLUS99999=2400000\nBLUS00000=0\n\n"
        "[LastPlayed]\nNPUB00002=2026-10-24T20:15:30\nBLUS99999=October 23, 2026\n")
    window.refresh()
    assert window.time_box.value.text() == "1 h 4 min"
    tip = window.time_box.toolTip().splitlines()
    assert tip[1] == "BLUS99999: 40 min, last played 23-10-2026 00:00"
    assert tip[2] == "Two: 24 min 42 s, last played 24-10-2026 20:15"           # named from the table
    assert len(tip) == 3                                                        # a game never played is left out
    window.close()


def test_rpcs3_updated_itself(qapp, folders):
    _install(folders["home"])
    emulator.appimage(folders["home"]).write_bytes(b"another build")
    window = _window(folders)
    assert "updated itself" in window.emulator_state.text() and window.emulator_box.value.text() == "other"
    assert window.install_pill.isEnabled()                                    # puts the pinned build back
    window.close()


def test_game_folders_added_and_removed(qapp, folders, tmp_path):
    _install(folders["home"])
    window = _window(folders)
    window.add_folder(tmp_path / "games")
    assert window.running.text() == "games is a game folder now: 1 game(s) in it."
    # The folder's name alone, a link that takes it out (owner, 24-10-2026); the path and the count in the tip.
    assert window.disc_state.text() == f"<b>{style.link(window, 'forget:0', 'games')}</b>"
    assert str(tmp_path) not in window.disc_state.text()
    assert window.disc_state.toolTip() == (f"{tmp_path / 'games'}\n1 disc game(s) found. Click a folder to stop "
                                           "looking for games in it; its games stay where they are.")
    assert [window.table.item(r, 1).text() for r in range(2)] == ["One", "Two"]
    assert window.table.item(0, 2).text() == "BLUS00001"
    assert window.table.item(0, 4).text() == "one" and window.table.item(0, 4).toolTip() == str(tmp_path / "games"
                                                                                                 / "one")
    window.add_folder(tmp_path / "games")                                       # once only
    assert window.folders == [tmp_path / "games"]
    window.close()
    window = _window(folders)                                                   # remembered
    assert window.folders == [tmp_path / "games"] and window.games_box.value.text() == "2"
    asked = []
    original = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: (asked.append(a[2]), QMessageBox.StandardButton.No)[1])
    try:
        window.show()                                   # a real click: a state line's link once took none (owner,
        QTest.mouseClick(window.disc_state, Qt.MouseButton.LeftButton,           # 24-10-2026)
                         pos=QPoint(4, window.disc_state.height() // 2))
        qapp.processEvents()
        assert window.folders == [tmp_path / "games"]                           # No: kept
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
        window.disc_state.linkActivated.emit("forget:7")                        # no such folder: nothing
        window.disc_state.linkActivated.emit("forget:0")
    finally:
        QMessageBox.question = original
    assert asked == [f"Stop looking for games in {tmp_path / 'games'}?\n\nIts games stay where they are."]
    assert window.folders == [] and window.table.rowCount() == 1
    assert window.running.text() == "games is no longer a game folder; its games stay where they are."
    assert "forget:" not in window.disc_state.text()
    window.close()


def test_a_disc_game_rpcs3_cannot_start(qapp, folders, tmp_path):
    _install(folders["home"])
    (tmp_path / "games" / "one" / "PS3_DISC.SFB").unlink()
    window = _window(folders)
    window.add_folder(tmp_path / "games")
    folder = window.table.item(0, 4)
    assert "PS3_DISC.SFB" in folder.toolTip() and folder.foreground().color().name() == "#c62828"
    assert str(tmp_path / "games" / "one") in folder.toolTip()
    window.close()


def test_install_runs_off_the_window(qapp, folders, monkeypatch):
    payload = b"#!/bin/sh\n"
    monkeypatch.setattr(emulator, "SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(emulator, "SIZE", len(payload))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = _window(folders, fetch=lambda url, dest, progress=None: dest.write_bytes(payload))
    window.on_install()
    assert not window.install_pill.isEnabled() and not window.refresh_pill.isEnabled()        # busy
    _wait(window, qapp)
    assert window.running.text() == f"RPCS3 {emulator.VERSION} is installed."
    assert window.version == emulator.VERSION and window.pill.text() == "No firmware"
    assert window.refresh_pill.isEnabled()
    window.close()


def test_the_firmware_installed_through_rpcs3(qapp, folders, tmp_path):
    _install(folders["home"])
    log = tmp_path / "args"
    folders["run"].write_text(f'#!/bin/sh\necho "$@" > "{log}"\n')
    folders["run"].chmod(0o755)
    window = _window(folders)
    pup = tmp_path / "PS3UPDAT.PUP"
    window.install_firmware(pup)
    deadline = time.monotonic() + 10
    while not log.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert log.read_text().strip() == f"--installfw {pup}"
    assert window.firmware_watch.isActive() and "in its own window" in window.running.text()
    assert "in its own window" in window.output.toPlainText()                   # logged too
    window._watch_firmware()
    assert window.firmware_watch.isActive() and window.firmware == ""         # not there yet
    _firmware(folders["rpcs3_home"])
    window._watch_firmware()
    assert not window.firmware_watch.isActive() and window.firmware == "4.92"
    assert window.running.text() == "PS3 firmware 4.92 is installed."
    window.close()


def test_rpcs3s_window(qapp, folders, tmp_path):
    """RPCS3 settings opens RPCS3's own window through the run wrapper, for what the app does not set yet."""
    _install(folders["home"])
    log = tmp_path / "args"
    folders["run"].write_text(f'#!/bin/sh\necho "x$@" >> "{log}"\n')
    folders["run"].chmod(0o755)
    window = _window(folders)
    window.on_open_rpcs3()
    deadline = time.monotonic() + 10
    while not log.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert log.read_text().splitlines() == ["x"]
    assert "RPCS3's own window was opened." in window.output.toPlainText()
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
    assert list(shortcuts.in_steam(folders["steam_dir"]).values()) == ["[PS3] Two"]
    assert window.steam_box.value.text() == "1" and window.table.item(0, 0).checkState() == Qt.CheckState.Checked
    assert window.table.item(0, 0).toolTip() == "In Steam"
    window.table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    add, remove = window.steam_plan()
    assert add == [] and [g.title for g in remove] == ["Two"]
    window.on_update_steam()
    _wait(window, qapp)
    assert shortcuts.in_steam(folders["steam_dir"]) == {} and "1 taken out" in window.running.text()
    window.close()


def test_a_shortcut_named_before_the_system_prefix_is_renamed(qapp, folders, monkeypatch):
    """A shortcut named by the title alone, as before "[PS3] ": Update Steam is on for it and renames it, with
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
    assert item["AppName"] == f"[PS3] {game.title}" and item["LastPlayTime"] == 1750000000
    assert not list((config / "grid").glob(f"{old.number}*")) and not window.steam_button.isEnabled()
    window.close()


def test_a_shortcut_of_a_game_no_longer_found_is_taken_out(qapp, folders):
    _install(folders["home"])
    gone = Game(Path("/old/games/gone/PS3_GAME/USRDIR/EBOOT.BIN"), "Gone", disc=True)
    steam.write_shortcuts(folders["steam_dir"], shortcuts.changes([gone], [], folders["run"], Path("/i.png"), {},
                                                                  art=False))
    window = _window(folders)
    add, remove = window.steam_plan()
    assert add == [] and [(str(g.eboot), g.title) for g in remove] == [(str(gone.eboot), "[PS3] Gone")]
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
    assert "install RPCS3 Manager through the portal first" in window.running.text()
    assert not window.worker.running
    window.close()


def test_the_blue_look(qapp, folders):
    _install(folders["home"])
    window = _window(folders)
    from bc250_core.theme import ACCENT
    assert style.BLUE in window.styleSheet()
    assert window.covers_button.property("primary") is None and window.steam_button.property("primary")
    assert window.rpcs3_button.property("primary") is None
    assert style.BLUE in window.emulator_box.styleSheet() and style.BLUE in window.refresh_pill.styleSheet()
    assert f"color:{style.BLUE}" in window.intro.text()                             # the release link
    for pill in (window.refresh_pill, *window.actions):
        sheet = pill.styleSheet()                       # the blue left edge only, also under the mouse (owner)
        assert sheet.rfind(f"border-left-color:{style.BLUE}") > sheet.rfind(ACCENT), pill.caption.text()
        assert style.HOVER_SHEEN in sheet and style.BLUE_TINT not in sheet
    assert all(p.value.styleSheet() == window.refresh_pill.value.styleSheet() for p in window.actions)  # same type
    assert "QTabBar::tab" in window.styleSheet() and "QComboBox" in window.styleSheet()
    # The Refresh pill has the keyboard focus when the window opens; it looks as the boxes beside it all the same
    # (owner, 24-10-2026: it showed another background color).
    window.show()
    qapp.processEvents()
    assert window.focusWidget() is window.refresh_pill
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


def test_a_newer_rpcs3_is_mentioned(qapp, folders):
    from bc250_core.updates import ReleaseInfo
    _install(folders["home"])
    release = ReleaseInfo("0.0.44", "v0.0.44", "https://github.com/RPCS3/rpcs3/releases/tag/v0.0.44", "2026-11-30")
    window = _window(folders, newer_release=lambda: release)
    deadline = time.monotonic() + 10
    while window.newer is None and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    tip = window.emulator_state.toolTip()                   # the line stays the version; the tip and the log say
    assert window.emulator_state.text() == f"<b>{emulator.LANDMARK}</b>"
    assert "RPCS3 0.0.44 is out (2026-11-30)" in tip and "releases/tag/v0.0.44" in tip
    assert "RPCS3 0.0.44 is out (2026-11-30)" in window.output.toPlainText()
    assert window.install_pill.isEnabled() is False                                # it never installs that one
    window.close()


def test_the_log_tab(qapp, folders, tmp_path):
    """What the window says goes to the Log tab with the time, after what the log file held already."""
    folders["log_path"].write_text("24-10-2026 22:14:00 INFO RPCS3 Manager 0.9.0 started\n")
    _install(folders["home"])
    window = _window(folders)
    lines = window.output.toPlainText().splitlines()
    assert lines[0] == "24-10-2026 22:14:00 INFO RPCS3 Manager 0.9.0 started"
    assert len(lines) == 2 and lines[1].endswith(" INFO RPCS3 set up: its welcome dialog off, its own update check "
                                                 "off, its dark style.")
    window.add_folder(tmp_path / "games")
    window.say("Steam was not changed: no Steam", ok=False)
    lines = window.output.toPlainText().splitlines()
    assert lines[-2].endswith(" INFO games is a game folder now: 1 game(s) in it.")
    assert lines[-2][:19].count("-") == 2 and lines[-2][10] == " "               # DD-MM-YYYY HH:MM:SS
    assert lines[-1].endswith(" ERROR Steam was not changed: no Steam") and "c62828" in window.running.styleSheet()
    assert str(folders["log_path"]) in window.tabs.widget(2).findChildren(QLabel)[0].text()
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
    assert window.running.text() == "The SteamGridDB key was changed."
    assert window.no_cover == {str(window.games[0].eboot)} and window.steam_button.isEnabled()
    window.on_update_steam()
    _wait(window, qapp)
    assert window.running.text().startswith("Covers: SteamGridDB had pictures for 1 of 1 game(s).\n1 game(s) in")
    assert not any("heroes/" in url or "logos/" in url for url in asked)        # the portrait alone
    assert "0123456789abcdef" not in window.output.toPlainText()
    number = shortcuts.entry(window.games[0], "[PS3] Two", folders["run"], LOGO_PATH)["appid"] & 0xFFFFFFFF
    grid = steam.user_folders(folders["steam_dir"])[0] / "grid"
    assert QImage(str(grid / f"{number}p.png")).pixelColor(300, 450).name() == "#0000ff"
    assert window.no_cover == set() and not window.steam_button.isEnabled()
    window.close()


def test_another_build_installed_than_the_app_brings(qapp, folders):
    """The RPCS3 line and box show the version alone (owner, 24-10-2026: the box is not wide enough for the
    build): the installed version in the line, its landmark in the box, the advice in the tooltip and the log."""
    (folders["home"] / "0.0.43-20133").mkdir(parents=True)
    (folders["home"] / "0.0.43-20133" / emulator.MEMBER).write_text("")
    (folders["home"] / "current").symlink_to("0.0.43-20133")
    window = _window(folders)
    assert window.emulator_state.text() == "<b>0.0.43-20133</b>" and window.emulator_box.value.text() == "0.0.43"
    assert window.emulator_state.toolTip() == (f"RPCS3 0.0.43-20133 is installed; this version of the app brings "
                                               f"{emulator.VERSION}: Install puts it in.")
    assert window.install_pill.isEnabled()
    window.refresh()
    assert window.output.toPlainText().count("Install puts it in") == 1                # once
    window.close()


def test_the_settings_tab_is_not_squeezed_under_the_introduction(qapp, folders):
    """The introduction wraps to several lines and the state lines may too; their minimum heights count, so the
    tabs below get their minimum and the Sound box's rows keep their height (owner, 24-10-2026: squeezed
    unreadable on the board)."""
    _install(folders["home"])
    window = _window(folders)
    window.tabs.setCurrentIndex(1)
    window.show()
    qapp.processEvents()
    assert window.intro.minimumHeight() == window.intro.heightForWidth(window.intro.width()) > 0
    assert window.tabs.height() >= window.tabs.minimumSizeHint().height()
    page = window.settings_page
    assert page.widgets["volume"].height() >= page.widgets["volume"].sizeHint().height()
    assert page.widgets["audio"].height() >= page.widgets["audio"].sizeHint().height()
    window.close()


def test_unmute_bazzites_volume(qapp, folders, tmp_path):
    """Unmute beside Bazzite's volume (owner, 24-10-2026): shown while RPCS3 is muted there only; a click runs
    core's unmute off the window and the row follows what WirePlumber stored; a failure is said in red."""
    state = tmp_path / "state" / "wireplumber" / "stream-properties"
    state.parent.mkdir(parents=True)
    state.write_text('[stream-properties]\nOutput/Audio:application.name:RPCS3={"volume":1.000000, "mute":true}\n')
    window = _window(folders, sound_state=state)
    page = window.settings_page
    window.tabs.setCurrentIndex(1)
    window.show()
    qapp.processEvents()
    assert page.sound_path == state and page.unmute_button.isVisible()
    asked = []

    def unmute(name, path):
        asked.append((name, path))
        path.write_text('[stream-properties]\nOutput/Audio:application.name:RPCS3={"volume":1.000000, "mute":false}\n')
        return 1.0, False
    page.unmute = unmute
    page.unmute_button.click()
    deadline = time.monotonic() + 10
    while page.unmuting.running and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    assert asked == [("RPCS3", state)]
    assert page.status.text() == "RPCS3's sound is on again in Bazzite's sound settings."
    assert page.system_sound.text() == "100 %" and not page.unmute_button.isVisible()

    def refused(name, path):
        from bc250_core import sound
        raise sound.SoundError("pactl is not installed: Unmute needs PipeWire's PulseAudio tools (pactl and paplay).")
    state.write_text('[stream-properties]\nOutput/Audio:application.name:RPCS3={"volume":1.000000, "mute":true}\n')
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
