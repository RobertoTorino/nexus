# SPDX-License-Identifier: GPL-3.0-or-later
"""The window on folders made in a temp folder: the states before and after installing, the BIOS chosen and
removed, the games in the table, the game folders, the plan for Steam, installing through the worker, Steam's
shortcuts changed with a fake "close Steam", PCSX2's settings kept at what the app owns, PCSX2's titles, each
game's screen, the tabs, the log with PCSX2's last run, the action pills and the blue look."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QMessageBox

from conftest import make_bios, make_disc

from bc250_core import steam
from pcsx2_manager import LOGO_PATH, catalogue, emulator, pcsx2_settings, shortcuts, style
from pcsx2_manager.games import Game
from pcsx2_manager import main_window as window_module
from pcsx2_manager.main_window import MainWindow
from pcsx2_manager.userdata import bios_dir


@pytest.fixture
def folders(tmp_path):
    pcsx2 = tmp_path / "PCSX2"
    pcsx2.mkdir()
    make_disc(tmp_path / "games" / "Two.iso", "SLUS_000.02")
    config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    config.mkdir(parents=True)
    run = tmp_path / "bin" / "bc250-pcsx2-run"
    run.parent.mkdir()
    run.write_text("#!/bin/sh\n")
    return {"home": tmp_path / "emulator", "pcsx2_home": pcsx2, "steam_dir": tmp_path / "Steam", "run": run,
            "log_path": tmp_path / "app.log"}


@pytest.fixture(autouse=True)
def pinned_size(monkeypatch):
    """The AppImage install() writes (empty) is the pinned release's size."""
    monkeypatch.setattr(emulator, "SIZE", 0)


def _install(home: Path) -> None:
    (home / emulator.VERSION).mkdir(parents=True)
    (home / emulator.VERSION / emulator.MEMBER).write_text("")
    (home / "current").symlink_to(emulator.VERSION)


def _setting(key: str) -> pcsx2_settings.Setting:
    return next(s for s in pcsx2_settings.SETTINGS if s.key == key)


def _wait(window, qapp) -> None:
    deadline = time.monotonic() + 10
    while window.worker.running and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()


def _window(folders, **kwargs) -> MainWindow:
    closed = kwargs.pop("closed", [])
    kwargs.setdefault("newer_release", lambda: None)                         # never GitHub in a test
    kwargs.setdefault("pcsx2_running", lambda: False)
    return MainWindow(**folders, steam_closed=lambda change: (closed.append(1), change())[0] and False,
                      steam_running=lambda: False, **kwargs)


def test_before_installing(qapp, folders):
    window = _window(folders)
    assert window.pill.text() == "Not installed"
    assert "Not installed" in window.emulator_state.text() and "No BIOS" in window.bios_state.text()
    assert window.install_pill.isEnabled() and not window.remove_pill.isEnabled()
    assert window.bios_pill.isEnabled() and not window.bios_remove_pill.isEnabled()      # no dump to remove
    assert window.refresh_pill.isEnabled()
    assert window.folder_pill.isEnabled() and not window.forget_pill.isEnabled()
    assert window.table.rowCount() == 0                                          # no folders chosen yet
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == ["Your games", "Settings",
                                                                             "Memory cards", "Log"]
    assert [b.caption.text() for b in window.header_pills[1:]] == ["PCSX2 version", "Your games",
                                                                    "Available in Steam", "Play time"]
    for name in ("play_button", "pcsx2_button", "memcards_button", "nightly_check", "refresh_button",
                 "install_button", "bios_button", "folder_button"):
        assert not hasattr(window, name), name                               # gone (owner, 24-10-2026)
    # The action pills (owner, 24-10-2026): what it is for in large type, what the pill does under it, the header
    # pills' size and all one width.
    assert [(p.value.text(), p.caption.text()) for p in window.actions] == [
        ("PCSX2", "Install"), ("PCSX2", "Uninstall"), ("BIOS", "Install"), ("BIOS", "Uninstall"),
        ("Games", "Add folder"), ("Games", "Remove folder")]
    assert all(p.sizeHint().height() == window.refresh_pill.sizeHint().height() for p in window.actions)
    window.show()                                       # spread over the width: all one width, no gap at the end
    window.centralWidget().layout().activate()
    assert len({p.width() for p in window.actions}) <= 2            # equal but for a pixel of rounding
    assert abs(window.tabs.tabBar().tabRect(0).height() - window.install_pill.height()) <= 2   # tabs as big
    assert window.forget_pill.geometry().right() >= window.tabs.geometry().right() - 1
    assert len({p.width() for p in window.header_pills}) <= 2       # the header's pills spread the same way
    assert window.time_box.geometry().right() >= window.tabs.geometry().right() - 1
    window.place_states()                               # the states end at the middle of the last pill (owner)
    window.centralWidget().layout().activate()
    centre = window.time_box.mapTo(window, window.time_box.rect().center()).x()
    right = window.controller.mapTo(window, window.controller.rect().topRight()).x()
    assert abs(right - centre) <= 8 and window.pill.x() < window.controller.x()
    assert "folders deep" not in window.folders_state.text()        # owner, 24-10-2026: the line went
    assert "PCSX2's release notes" in window.intro.text() and emulator.RELEASE_PAGE in window.intro.text()
    assert ">Wiki</a>" in window.intro.text() and "Manual" not in window.intro.text()
    window.close()


def test_installed_with_bios_and_games(qapp, folders, tmp_path):
    _install(folders["home"])
    window = _window(folders)
    assert window.pill.text() == "No BIOS" and not hasattr(window, "bios_box")       # the BIOS line says which
    assert "pcsx2.net" in window.bios_state.text()
    make_bios(bios_dir(folders["pcsx2_home"]))
    window.add_folder(tmp_path / "games")
    assert window.pill.text() == "Ready"
    assert "SCPH-70012.bin" in window.bios_state.text()
    assert str(bios_dir(folders["pcsx2_home"])) not in window.bios_state.text()    # the name, not the path
    assert str(bios_dir(folders["pcsx2_home"])) in window.bios_state.toolTip()
    assert window.emulator_box.value.text() == emulator.VERSION
    assert window.emulator_state.text() == f"PCSX2 {emulator.VERSION} is installed."
    assert window.games_box.value.text() == "1" and window.steam_box.value.text() == "0"
    assert not window.install_pill.isEnabled() and window.remove_pill.isEnabled()
    assert window.bios_remove_pill.isEnabled()
    head = window.table.horizontalHeader().model()
    assert [head.headerData(c, Qt.Orientation.Horizontal) for c in range(6)] == [
        "In Steam", "Game title", "Id", "Type", "File name", "Screen setting"]        # owner, 24-10-2026
    assert window.table.item(0, 2).text() == "SLUS-00002"
    assert window.table.item(0, 4).text() == "Two.iso"                          # the file's name; the path as tip
    assert window.table.item(0, 4).toolTip() == str(tmp_path / "games" / "Two.iso")
    assert not window.steam_button.isEnabled()                                  # nothing to change
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
    devices.unlink()
    window.show_controller()
    assert window.controller.text() == "No controller"
    window.close()
    assert not window.controller_timer.isActive()


def test_the_play_time_in_the_header(qapp, folders, tmp_path):
    """The time spent in all games together, as PCSX2 counts it in playtime.dat, with each game in the tip; a dash
    while there is none."""
    _install(folders["home"])
    window = _window(folders)
    assert window.time_box.value.text() == "—" and "none yet" in window.time_box.toolTip()
    (folders["pcsx2_home"] / "inis").mkdir(exist_ok=True)
    (folders["pcsx2_home"] / "inis" / "playtime.dat").write_text(
        f"{'SLUS-00002':<32} {'1482':<20} {'1792814410':<20}\n{'SLUS-99999':<32} {'2400':<20} {'1792814849':<20}\n"
        f"{'SLUS-00000':<32} {'0':<20} {'0':<20}\nbroken line\n")
    window.add_folder(tmp_path / "games")
    assert window.time_box.value.text() == "1 h 4 min"
    tip = window.time_box.toolTip().splitlines()
    assert tip[1].startswith("SLUS-99999: 40 min, last played ") and tip[2].startswith("Two: 24 min 42 s, last ")
    assert len(tip) == 3                                                        # a game never played is left out
    window.close()


def test_pcsx2_updated_itself(qapp, folders):
    _install(folders["home"])
    emulator.appimage(folders["home"]).write_bytes(b"another build")
    window = _window(folders)
    assert "updated itself" in window.emulator_state.text() and window.emulator_box.value.text() == "other"
    assert window.install_pill.isEnabled()                                      # puts the pinned release back
    window.close()


def test_a_bios_is_chosen_and_removed(qapp, folders, tmp_path):
    """Install under BIOS copies the dump with the files beside it into PCSX2's bios folder and PCSX2 uses it; a
    dump already there is not copied again; Remove takes a dump out with its files and PCSX2 uses another; nothing
    is written while PCSX2 runs."""
    _install(folders["home"])
    dumps = tmp_path / "my-bios"
    dump = make_bios(dumps, "SCPH10000.BIN")
    (dumps / "SCPH10000.MEC").write_bytes(b"\0" * 4)
    (dumps / "other.txt").write_text("not the dump's")
    running = [True]
    window = _window(folders, pcsx2_running=lambda: running[0])
    window.choose_bios(dump)
    assert window.running.text() == window_module.RUNNING
    assert not bios_dir(folders["pcsx2_home"]).exists()
    running[0] = False
    window.choose_bios(dump)
    folder = bios_dir(folders["pcsx2_home"])
    assert sorted(p.name for p in folder.iterdir()) == ["SCPH10000.BIN", "SCPH10000.MEC", "SCPH10000.nvm"]
    assert pcsx2_settings.chosen_bios(folders["pcsx2_home"]) == "SCPH10000.BIN"
    assert window.running.text() == "PCSX2 uses SCPH10000.BIN now."
    assert "PCSX2 uses <b>SCPH10000.BIN</b>" in window.bios_state.text() and window.pill.text() == "No games"
    second = make_bios(folder, "SCPH-70004.BIN")                                # already in the folder
    window.choose_bios(second)
    assert pcsx2_settings.chosen_bios(folders["pcsx2_home"]) == "SCPH-70004.BIN"
    assert "also there: SCPH10000.BIN" in window.bios_state.text()
    running[0] = True
    window.remove_bios(second)
    assert window.running.text() == window_module.RUNNING and second.is_file()
    running[0] = False
    window.remove_bios(second)
    assert sorted(p.name for p in folder.iterdir()) == ["SCPH10000.BIN", "SCPH10000.MEC", "SCPH10000.nvm"]
    assert window.running.text() == ("SCPH-70004.BIN, SCPH-70004.nvm removed from PCSX2's BIOS folder. "
                                     "PCSX2 uses SCPH10000.BIN now.")
    assert pcsx2_settings.chosen_bios(folders["pcsx2_home"]) == "SCPH10000.BIN"    # prepare() picked it
    window.remove_bios(folder / "SCPH10000.BIN")
    assert list(folder.iterdir()) == [] and window.running.text().endswith("PCSX2 has no BIOS now.")
    assert window.pill.text() == "No BIOS" and not window.bios_remove_pill.isEnabled()
    window.close()


def test_pcsx2_is_set_up_once_installed(qapp, folders, tmp_path):
    """Before PCSX2 is installed nothing is written; then its settings get what the app owns, and a game starts
    straight away. While PCSX2 runs they are left alone."""
    ini = pcsx2_settings.settings_path(folders["pcsx2_home"])
    window = _window(folders)
    assert not ini.exists()
    window.close()
    _install(folders["home"])
    running = [True]
    window = _window(folders, pcsx2_running=lambda: running[0])
    assert not ini.exists()
    running[0] = False
    window.refresh()
    text = ini.read_text()
    assert "SetupWizardIncomplete = false" in text and "Cross = SDL-0/FaceSouth" in text
    assert "HideMouseCursor = true" in text                                     # the mouse hidden in a game
    assert "ShutdownVM = SDL-0/Back & SDL-0/Start" in text                      # Select + Start quits, by default
    assert window.settings_page.widgets["quit"].isChecked()
    assert "PCSX2 set up: PCSX2's settings made from its own defaults" in window.output.toPlainText()
    window.close()


def test_pcsx2s_titles_name_the_games(qapp, folders, tmp_path):
    """With PCSX2's catalog beside the AppImage, a game is named as PCSX2 names it, in the table and in Steam; a
    game PCSX2 does not know keeps its file's name, without the serial in it."""
    _install(folders["home"])
    current = emulator.appimage(folders["home"]).parent
    (current / catalogue.GAME_INDEX).write_text('SLUS-00002:\n  name: "Two Of Them"\n  region: "NTSC-U"\n')
    (current / catalogue.PATCHES).write_bytes(_patches({}))
    make_disc(tmp_path / "games" / "SLUS_000.07.Seven.iso", "SLUS_000.07")
    window = _window(folders)
    window.add_folder(tmp_path / "games")
    titles = [window.table.item(r, 1).text() for r in range(window.table.rowCount())]
    assert titles == ["Seven", "Two Of Them"]
    assert sorted(shortcuts.names(window.games).values()) == ["[PS2] Seven", "[PS2] Two Of Them"]
    window.close()


def _patches(files: dict[str, str]) -> bytes:
    import io
    import zipfile
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return out.getvalue()


def test_each_games_screen(qapp, folders, tmp_path):
    """The Screen column: Widescreen only for a game PCSX2 has a widescreen patch for, the choice kept in the game's
    own settings in PCSX2; a compressed image has no choice; nothing is written while PCSX2 runs."""
    from pcsx2_manager.games import elf_crc
    _install(folders["home"])
    program = b"\x7fELF" + bytes(range(60))
    crc = elf_crc(program)
    make_disc(tmp_path / "games" / "Wide.iso", "SLUS_000.08", program=program)
    make_disc(tmp_path / "games" / "Two.iso", "SLUS_000.02", program=b"\x7fELF two")    # no patch for this one
    (tmp_path / "games" / "Packed.chd").write_bytes(b"MComprHD")
    current = emulator.appimage(folders["home"]).parent
    (current / catalogue.GAME_INDEX).write_text("")
    (current / catalogue.PATCHES).write_bytes(_patches({f"SLUS-00008_{crc:08X}.pnach": "[Widescreen 16:9]\n"}))
    running = [False]
    window = _window(folders, pcsx2_running=lambda: running[0])
    window.add_folder(tmp_path / "games")
    rows = {window.table.item(r, 1).text(): r for r in range(window.table.rowCount())}
    wide, two, packed = (window.table.cellWidget(rows[t], 5) for t in ("Wide", "Two", "Packed"))
    assert [wide.itemText(i) for i in range(wide.count())] == ["Original", "Widescreen", "Fill screen"]
    assert [two.itemText(i) for i in range(two.count())] == ["Original", "Fill screen"]   # PCSX2 has no patch
    assert not packed.isEnabled()
    wide.setCurrentIndex(wide.findData(pcsx2_settings.WIDESCREEN))
    path = pcsx2_settings.game_settings(folders["pcsx2_home"], "SLUS-00008", crc)
    assert path.name == f"SLUS-00008_{crc:08X}.ini" and "EnableWideScreenPatches = true" in path.read_text()
    assert window.running.text() == "Wide: widescreen."
    running[0] = True
    wide = window.table.cellWidget(rows["Wide"], 5)
    wide.setCurrentIndex(wide.findData(pcsx2_settings.FILL))
    assert window.running.text() == window_module.RUNNING
    assert pcsx2_settings.read_screen(path) == pcsx2_settings.WIDESCREEN                     # unchanged
    assert window.table.cellWidget(rows["Wide"], 5).currentData() == pcsx2_settings.WIDESCREEN
    window.close()


def test_game_folders_added_and_removed(qapp, folders, tmp_path):
    _install(folders["home"])
    make_disc(tmp_path / "more" / "One.iso", "SLUS_000.01")
    window = _window(folders)
    window.add_folder(tmp_path / "more")
    assert window.running.text() == "more is a game folder now: 1 game(s) in it."
    assert "<b>more</b>" in window.folders_state.text() and str(tmp_path) not in window.folders_state.text()
    assert window.folders_state.toolTip() == str(tmp_path / "more")             # the whole path as the tip
    assert [window.table.item(r, 1).text() for r in range(1)] == ["One"]
    assert window.table.item(0, 2).text() == "SLUS-00001" and window.forget_pill.isEnabled()
    window.add_folder(tmp_path / "more")                                        # once only
    assert window.folders == [tmp_path / "more"]
    window.close()
    window = _window(folders)                                                   # remembered
    assert window.folders == [tmp_path / "more"] and window.games_box.value.text() == "1"
    window.forget_folder(tmp_path / "more")
    assert window.folders == [] and window.table.rowCount() == 0 and not window.forget_pill.isEnabled()
    assert window.running.text() == "more is no longer a game folder; its games stay where they are."
    window.close()


def test_a_compressed_image_is_marked(qapp, folders, tmp_path):
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
    monkeypatch.setattr(emulator, "SIZE", len(payload))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = _window(folders, fetch=lambda url, dest, progress=None: dest.write_bytes(payload))
    window.on_install()
    assert not window.install_pill.isEnabled() and not window.refresh_pill.isEnabled()        # busy
    _wait(window, qapp)
    assert window.running.text() == f"PCSX2 {emulator.VERSION} is installed."
    assert window.version == emulator.VERSION and window.pill.text() == "No BIOS"
    assert window.refresh_pill.isEnabled()
    window.close()


def test_steam_added_and_taken_out(qapp, folders, monkeypatch, tmp_path):
    _install(folders["home"])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    closed = []
    window = _window(folders, closed=closed)
    window.add_folder(tmp_path / "games")
    window.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    assert window.steam_button.isEnabled()
    add, remove = window.steam_plan()
    assert [g.title for g in add] == ["Two"] and remove == []
    window.on_update_steam()
    _wait(window, qapp)
    assert closed == [1] and window.running.text().startswith("1 game(s) in Steam")
    assert list(shortcuts.in_steam(folders["steam_dir"]).values()) == ["[PS2] Two"]
    assert window.steam_box.value.text() == "1" and window.table.item(0, 0).checkState() == Qt.CheckState.Checked
    assert window.table.item(0, 0).toolTip() == "In Steam"
    window.table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    add, remove = window.steam_plan()
    assert add == [] and [g.title for g in remove] == ["Two"]
    window.on_update_steam()
    _wait(window, qapp)
    assert shortcuts.in_steam(folders["steam_dir"]) == {} and "1 taken out" in window.running.text()
    window.close()


def test_a_shortcut_named_before_the_system_prefix_is_renamed(qapp, folders, monkeypatch, tmp_path):
    """A shortcut named by the title alone, as before "[PS2] ": Update Steam is on for it and renames it, with
    its play time; the artwork under its old number goes."""
    _install(folders["home"])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window = _window(folders)
    window.add_folder(tmp_path / "games")
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
    assert item["AppName"] == f"[PS2] {game.title}" and item["LastPlayTime"] == 1750000000
    assert not list((config / "grid").glob(f"{old.number}*")) and not window.steam_button.isEnabled()
    window.close()


def test_a_shortcut_of_a_game_no_longer_found_is_taken_out(qapp, folders):
    _install(folders["home"])
    gone = Game(Path("/old/games/gone.iso"), "Gone")
    steam.write_shortcuts(folders["steam_dir"], shortcuts.changes([gone], [], folders["run"], Path("/i.png"), {},
                                                                  art=False))
    window = _window(folders)
    add, remove = window.steam_plan()
    assert add == [] and [(str(g.file), g.title) for g in remove] == [(str(gone.file), "[PS2] Gone")]
    assert window.steam_button.isEnabled()
    window.close()


def test_no_steam_game_mode_or_no_wrapper(qapp, folders, monkeypatch, tmp_path):
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
    assert "install PCSX2 Manager through the portal first" in window.running.text()
    assert not window.worker.running
    window.close()


def test_the_blue_look(qapp, folders):
    _install(folders["home"])
    window = _window(folders)
    from bc250_core.theme import ACCENT
    assert style.BLUE in window.styleSheet()
    assert window.covers_button.property("primary") is None and window.steam_button.property("primary")
    assert style.BLUE in window.emulator_box.styleSheet() and style.BLUE in window.refresh_pill.styleSheet()
    assert f"color:{style.BLUE}" in window.intro.text()                             # the release link
    for pill in (window.refresh_pill, *window.actions):
        sheet = pill.styleSheet()                       # the blue left edge only, also under the mouse (owner)
        assert sheet.rfind(f"border-left-color:{style.BLUE}") > sheet.rfind(ACCENT), pill.caption.text()
        assert style.HOVER_SHEEN in sheet and style.BLUE_TINT not in sheet
    assert all(p.value.styleSheet() == window.refresh_pill.value.styleSheet() for p in window.actions)  # same type
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


def test_a_newer_pcsx2_is_mentioned(qapp, folders):
    from bc250_core.updates import ReleaseInfo
    _install(folders["home"])
    release = ReleaseInfo("2.9.0", "v2.9.0", "https://github.com/PCSX2/pcsx2/releases/tag/v2.9.0", "2026-11-30")
    window = _window(folders, newer_release=lambda: release)
    deadline = time.monotonic() + 10
    while window.newer is None and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    text = window.emulator_state.text()
    assert "PCSX2 2.9.0 is out (2026-11-30)" in text and "releases/tag/v2.9.0" in text
    assert window.install_pill.isEnabled() is False                                # it never installs that one
    from bc250_core import upstream
    assert upstream.read_all() == {}                    # the release is pinned: the portal has nothing to announce
    window.close()


def test_the_log_tab(qapp, folders, tmp_path):
    """What the window says goes to the Log tab with the time, after what the log file held already; the Settings
    and Memory cards tabs write there too."""
    folders["log_path"].write_text("23-10-2026 22:14:00 INFO PCSX2 Manager 0.9.1 started\n")
    _install(folders["home"])
    window = _window(folders)
    lines = window.output.toPlainText().splitlines()
    assert lines[0] == "23-10-2026 22:14:00 INFO PCSX2 Manager 0.9.1 started"
    assert lines[1].endswith(" INFO PCSX2 set up: PCSX2's settings made from its own defaults, its own updates off, "
                             "the mouse pointer hidden in a game, player 1 on the first controller, Select + Start "
                             "quits a game.")
    assert lines[1][:19].count("-") == 2 and lines[1][10] == " "                 # DD-MM-YYYY HH:MM:SS
    window.add_folder(tmp_path / "games")
    window.say("Steam was not changed: no Steam", ok=False)
    lines = window.output.toPlainText().splitlines()
    assert lines[-2].endswith(" INFO games is a game folder now: 1 game(s) in it.")
    assert lines[-1].endswith(" ERROR Steam was not changed: no Steam") and "c62828" in window.running.styleSheet()
    assert str(folders["log_path"]) in window.tabs.widget(3).findChildren(QLabel)[0].text()
    window.settings_page.widgets["fps"].setChecked(True)
    assert window.settings_page.status.text() == "Show FPS: on."
    assert pcsx2_settings.read_setting(folders["pcsx2_home"], _setting("fps")) == "true"
    window.close()


EMULOG = """\
[    0.0733] PCSX2 v2.8.2
[    0.0799] SDLInputSource: Using Controller DB from resources.
[    0.5080]   Serial: SLUS-00002
[    0.5080]   CRC: 833FE0A4
[    1.0259] SDLInputSource: Opened gamepad 1 (instance id 1, player id 0): DualSense Edge Wireless Controller
[    1.8640] Enabled patch: Widescreen 16:9
[  352.6112] Add 346 seconds play time to SLUS-00002 -> now 346
[  352.7374] Releasing host memory for virtual systems...
"""


def test_pcsx2s_last_run_is_logged_once(qapp, folders, tmp_path):
    """PCSX2's own log of its last run (the game, the play time, the controller) goes into the app's log the next
    time the window looks, once per run; a run without a game is nothing to say."""
    import os
    _install(folders["home"])
    current = emulator.appimage(folders["home"]).parent
    (current / catalogue.GAME_INDEX).write_text('SLUS-00002:\n  name: "Two Of Them"\n')
    emulog = folders["pcsx2_home"] / "logs" / "emulog.txt"
    emulog.parent.mkdir()
    emulog.write_text(EMULOG)
    os.utime(emulog, (1792814849, 1792814849))
    window = _window(folders)
    until = time.strftime("%d-%m-%Y %H:%M:%S", time.localtime(1792814849))
    line = (f"Two Of Them (SLUS-00002) was played for 5 min 46 s in PCSX2 2.8.2, until {until}, with the "
            "controller DualSense Edge Wireless Controller.")
    assert window.output.toPlainText().count(line) == 1
    assert "was played" not in window.running.text()                            # not the status line: it is past
    window.refresh()
    assert window.output.toPlainText().count(line) == 1                         # once
    emulog.write_text(EMULOG.replace("[  352.6112] Add 346 seconds play time to SLUS-00002 -> now 346\n", "")
                      .replace("Opened gamepad 1 (instance id 1, player id 0): DualSense Edge Wireless Controller",
                               "Using Controller DB from resources."))
    os.utime(emulog, (1792814900, 1792814900))                                  # another run, ended by Steam
    window.refresh()
    assert "was played for about 5 min 52 s in PCSX2 2.8.2, until" in window.output.toPlainText()
    assert window.output.toPlainText().endswith("without a controller.")
    emulog.write_text("[    0.0733] PCSX2 v2.8.2\n[    0.5000] Releasing host memory for virtual systems...\n")
    os.utime(emulog, (1792814950, 1792814950))
    window.refresh()
    assert window.output.toPlainText().count("was played") == 2                 # no game: nothing said
    window.close()


def test_the_tabs_follow_pcsx2s_folder(qapp, folders):
    """The Settings and Memory cards tabs read PCSX2's folder when the window refreshes, and nothing of theirs is
    written while PCSX2 runs."""
    _install(folders["home"])
    running = [False]
    window = _window(folders, pcsx2_running=lambda: running[0])
    (window.memcard_page.folder).mkdir(parents=True)
    from pcsx2_manager import memcards
    memcards.new_card(window.memcard_page.folder, "Mcd001.ps2", 8)
    window.refresh()
    assert window.memcard_page.card().name == "Mcd001.ps2"
    assert window.settings_page.widgets["volume"].value() == 100
    pcsx2_settings.write_setting(folders["pcsx2_home"], _setting("volume"), "40")     # as PCSX2 might
    window.refresh()
    assert window.settings_page.widgets["volume"].value() == 40
    running[0] = True
    window.settings_page.widgets["volume"].setValue(55)
    assert window.settings_page.status.text().startswith("PCSX2 is running")
    assert window.settings_page.widgets["volume"].value() == 40                 # put back
    window.refresh()
    assert not window.memcard_page.slot_combo.isEnabled() and not window.memcard_page.warning.isHidden()
    window.close()


def test_covers_with_the_suites_key(qapp, folders, monkeypatch, tmp_path):
    """Steam artwork… keeps the suite's key; Update Steam then looks up the games and puts all four pictures in
    place of the drawn ones, and a game in Steam not looked up yet makes the button do something again."""
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
    window.add_folder(tmp_path / "games")
    window.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    window.on_update_steam()
    _wait(window, qapp)
    assert asked == [] and not window.steam_button.isEnabled()                  # no key: nothing asked
    monkeypatch.setattr(QInputDialog, "exec", lambda self: (self.setTextValue("0123456789abcdef"), 1)[1])
    window.on_covers()
    assert key.read_text() == "0123456789abcdef\n"
    assert window.running.text() == "The SteamGridDB key was changed."
    game = window.ticked()[0]
    assert window.no_cover == {str(game.file)} and window.steam_button.isEnabled()
    window.on_update_steam()
    _wait(window, qapp)
    assert window.running.text().startswith("Covers: SteamGridDB had pictures for 1 of 1 game(s).\n1 game(s) in")
    for endpoint in ("grids", "heroes", "logos"):                               # all four kinds
        assert any(f"{endpoint}/game/1?" in url for url in asked), endpoint
    assert "0123456789abcdef" not in window.output.toPlainText()
    number = shortcuts.entry(game, "[PS2] Two", folders["run"], LOGO_PATH)["appid"] & 0xFFFFFFFF
    grid = steam.user_folders(folders["steam_dir"])[0] / "grid"
    for suffix in ("p", "", "_hero", "_logo"):
        assert QImage(str(grid / f"{number}{suffix}.png")).pixelColor(10, 10).name() == "#0000ff", suffix
    assert window.no_cover == set() and not window.steam_button.isEnabled()
    window.close()


def test_bazzites_volume_for_pcsx2(qapp, folders, tmp_path):
    """The volume Bazzite remembers for PCSX2 (WirePlumber's stream-properties, core's sound): in the Settings tab's
    Sound box, and said once while PCSX2 is muted there (owner, 24-10-2026, as RPCS3 Manager's)."""
    from pcsx2_manager.settings_page import SOUND_MUTED
    state = tmp_path / "state" / "wireplumber" / "stream-properties"
    state.parent.mkdir(parents=True)
    window = _window(folders, sound_state=state)
    assert window.settings_page.system_sound.text() == "— (PCSX2 has not played yet)"
    state.write_text('[stream-properties]\nOutput/Audio:application.name:PCSX2={"volume":1.000000, "mute":true, '
                     '"channelVolumes":[1.000000, 1.000000], "channelMap":["FL", "FR"]}\n')
    window.refresh()
    assert window.settings_page.system_sound.text() == "Muted" and window.running.text() == SOUND_MUTED
    window.say("something else")
    window.refresh()
    assert window.running.text() == "something else"                            # said once
    state.write_text('[stream-properties]\nOutput/Audio:application.name:PCSX2={"volume":0.700000, "mute":false}\n')
    window.refresh()
    assert window.settings_page.system_sound.text() == "70 %" and window.settings_page.system_sound.styleSheet() == ""
    assert window.output.toPlainText().count("muted in Bazzite") == 1
    window.close()


def test_the_tabs_are_not_squeezed_under_the_introduction(qapp, folders):
    """The introduction's lines count in the window's minimum height (core's WrappedLabel; owner, 24-10-2026,
    from RPCS3 Manager), so the tabs below get their minimum."""
    window = _window(folders)
    window.tabs.setCurrentIndex(1)
    window.show()
    qapp.processEvents()
    assert window.intro.minimumHeight() == window.intro.heightForWidth(window.intro.width()) > 0
    assert window.tabs.height() >= window.tabs.minimumSizeHint().height()
    window.close()


def test_the_state_lines_links_take_a_click(qapp, folders):
    """The PCSX2 and BIOS lines hold links (the release notes, PCSX2's BIOS page): a state line takes a click on a
    link, not only a selection of its text (owner, 24-10-2026: found in shadPS4 Manager's window, built the same
    way, where a click on a link did nothing)."""
    window = _window(folders)
    for label in (window.emulator_state, window.bios_state, window.folders_state):
        assert label.textInteractionFlags() & Qt.TextInteractionFlag.LinksAccessibleByMouse
        assert label.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    window.close()


def test_unmute_bazzites_volume(qapp, folders, tmp_path):
    """Unmute beside Bazzite's volume (owner, 24-10-2026): shown while PCSX2 is muted there only; a click runs
    core's unmute off the window and the row follows what WirePlumber stored; a failure is said in red."""
    state = tmp_path / "state" / "wireplumber" / "stream-properties"
    state.parent.mkdir(parents=True)
    state.write_text('[stream-properties]\nOutput/Audio:application.name:PCSX2={"volume":1.000000, "mute":true}\n')
    window = _window(folders, sound_state=state)
    page = window.settings_page
    window.tabs.setCurrentIndex(1)
    window.show()
    qapp.processEvents()
    assert page.sound_path == state and page.unmute_button.isVisible()
    asked = []

    def unmute(name, path):
        asked.append((name, path))
        path.write_text('[stream-properties]\nOutput/Audio:application.name:PCSX2={"volume":1.000000, "mute":false}\n')
        return 1.0, False
    page.unmute = unmute
    page.unmute_button.click()
    deadline = time.monotonic() + 10
    while page.unmuting.running and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    assert asked == [("PCSX2", state)]
    assert page.status.text() == "PCSX2's sound is on again in Bazzite's sound settings."
    assert page.system_sound.text() == "100 %" and not page.unmute_button.isVisible()

    def refused(name, path):
        from bc250_core import sound
        raise sound.SoundError("pactl is not installed: Unmute needs PipeWire's PulseAudio tools (pactl and paplay).")
    state.write_text('[stream-properties]\nOutput/Audio:application.name:PCSX2={"volume":1.000000, "mute":true}\n')
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
