# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py), as Xenia Manager's is tested: it opens on the portable window with the header's
battery, date and time, fits the handheld's screen; every action is a button in the row at the bottom, A too, and no
pill is left (owner, 29-10-2026); B goes back and View exits; Get HelixSR runs off the window's thread (a fake job)
and its result becomes the payload, View asking first meanwhile; the games from a fake Steam are looked through, A runs
one with HelixSR (a second press the first time, Steam asked to start it), Y goes back on a second press, nothing
while the game runs; a folder added in the browser; the OptiScaler page; the Deployments' Update older games and
Forget; the settings saved as the payload's helixsr.ini and applied to a game; NVIDIA's DLL found in Steam; the log
read in the app; the version and the icons are where the checks expect them. Temp folders only: no real game, no
Steam, no GitHub."""

from __future__ import annotations

import re
import tempfile
import time
from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QGuiApplication

from bc250_core import portable
from bc250_core.gamepad import Gamepad
from bc250_core.portable import BACK, EXIT, VIEW
from conftest import FAKE_GAME_DLL, make_game, make_payload, make_steam
from upscale_boost import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, backend
from upscale_boost.acquire import ReleaseInfo, SetupOutcome, UpdateStatus
from upscale_boost.main_window import CHECK_KEY, DLSS_KEY, FALLBACK_KEY, FOLDERS_KEY, MainWindow
from upscale_boost.panes import CHECK_AT_START

GAMES = {"Alpha": True, "Beta": False, "Gamma": True}   # Alpha 1000, Beta 1001, Gamma 1002


class FakePad:
    def events(self):
        return []

    def close(self):
        pass

    def names(self):
        return []


class FakeSetup:
    """Get HelixSR without the network: says a line and a stage, then hands back a built release."""

    made: list[FakeSetup] = []

    def __init__(self, request, say, stage, progress, version: str = "2.0.0", ok: bool = True):
        self.request, self.say, self.stage, self.progress = request, say, stage, progress
        self.version, self.ok = version, ok
        self.cancelled = False
        FakeSetup.made.append(self)

    def run(self) -> SetupOutcome:
        self.stage("Building the network (a few minutes)")
        self.say("[helixsr-setup] compiling 1 of 2")
        self.progress("HelixSR-2.0.0.zip", 1 << 20, 2 << 20)
        if not self.ok:
            return SetupOutcome(False, None, "", "HelixSR's builder exited with code 2; the log has its output.", 1)
        release = self.request.work_dir / f"HelixSR-{self.version}" / f"HelixSR-{self.version}"
        make_payload(release / backend.FSRFG, self.version)
        (release / "README.md").write_text(f"# HelixSR {self.version}\n", encoding="utf-8")
        return SetupOutcome(True, release, self.version, f"HelixSR {self.version} is built.", 3)

    def cancel(self) -> None:
        self.cancelled = True


def wait_for(qapp, predicate, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not predicate():
        qapp.processEvents()
        time.sleep(0.01)
    return predicate()


def make(qapp, built: bool = True, games: dict[str, bool] | None = None, **more):
    root = Path(tempfile.mkdtemp())
    home = root / "home"
    if built:
        make_payload(home / "payload")
    more.setdefault("steam_dir", make_steam(root, GAMES if games is None else games))
    more.setdefault("settings", QSettings(str(root / "app.ini"), QSettings.Format.IniFormat))  # never the registry
    more.setdefault("check_updates", lambda version: UpdateStatus("HelixSR", version, ReleaseInfo(
        "2.0.0", "v2.0.0", "", "2026-10-19", "HelixSR-2.0.0.zip", "file:///nowhere")))
    more.setdefault("setup", FakeSetup)
    more.setdefault("running", lambda: "")
    more.setdefault("open_url", lambda url: opened.append(url))
    more.setdefault("roots", lambda: [root / "drive"])
    more.setdefault("user_home", root / "me")
    (root / "drive").mkdir()
    opened: list[str] = []
    window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False), home=home, **more)
    window.opened, window.root = opened, root
    portable.scale((1280, 720))
    window.resize(1280, 720)
    window.show()
    window.activateWindow()
    qapp.processEvents()
    window.start()
    settled(qapp, window)
    return window


def settled(qapp, window) -> None:
    """Every game looked through, the list drawn again, the update check answered."""
    wait_for(qapp, lambda: all(s is not None for s in window.games.values()) and not window.scanner.busy
             and not window.checking)
    wait_for(qapp, lambda: not window.render_timer.isActive())
    qapp.processEvents()


def legend(window) -> list[tuple[str, str]]:
    return list(window.legend.items)


def no_pills(window) -> bool:
    """Every action is in the row at the bottom (owner, 29-10-2026): the panes hold rows and icons, no pill."""
    return [p for p in window.panes.findChildren(portable.Pill)
            if type(p) is portable.Pill and p.isVisibleTo(window)] == []


def focus_game(qapp, window, name: str) -> Path:
    window.games_card.setFocus()
    qapp.processEvents()
    game = next(g for g in window.games if g.name == name)
    window.games_pane.list.pills[str(game)].setFocus()
    qapp.processEvents()
    return game


def upscaler(game: Path) -> Path:
    return game / "Engine" / "Plugins" / "FSR3" / "ThirdParty" / "Win64" / backend.UPSCALER_DLL


# The window

def test_the_window_opens_with_the_suites_header(qapp):
    window = make(qapp)
    assert window.header.title.text() == APP_NAME and window.header.version.text() == __version__
    assert re.fullmatch(r"\w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d  \|  82%", window.header.status.text())
    assert window.panes.currentWidget() is window.helix_pane
    assert [b for b, _t in legend(window)] == ["A", "Y", "LB", "RB", "LT", portable.MENU, VIEW]
    assert window.helix_card.text.text() == "HelixSR 2.0.0, ready"
    assert no_pills(window)
    window.close()


def test_the_window_fits_the_handhelds_screen(qapp):
    window = make(qapp)
    for card in (window.helix_card, window.games_card, window.deploy_card, window.settings_card, window.log_card):
        card.setFocus()
        qapp.processEvents()
        assert window.minimumSizeHint().height() <= 720 and window.height() == 720
        assert no_pills(window)
    window.close()


def test_b_goes_back_and_view_exits(qapp, monkeypatch):
    window = make(qapp)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    game = focus_game(qapp, window, "Alpha")
    assert BACK in legend(window)
    window.act("back")
    assert window.focusWidget() is window.games_card
    window.act("view")
    assert closed == [True] and game


# HelixSR

def test_get_helixsr_builds_and_imports_the_payload(qapp):
    window = make(qapp, built=False)
    assert window.helix_card.text.text() == "Not built yet: the A button gets it."
    window.helix_card.setFocus()
    window.act("accept")
    assert window.busy and legend(window)[0] == ("X", "Cancel")
    assert wait_for(qapp, lambda: not window.busy)
    status = backend.payload_status(window.payload_dir)
    assert status.ready and status.version == "2.0.0"
    assert window.helix_pane.status.text().startswith("HelixSR 2.0.0 is built. (3 s)")
    assert window.output == ["[helixsr-setup] compiling 1 of 2"]
    request = FakeSetup.made[-1].request
    assert request.release.version == "2.0.0" and not request.fallback and request.dlss_file is None
    assert request.work_dir == window.home / "work" and request.helix_data == window.home / "HelixSR"
    window.close()


def test_a_current_payload_is_built_again_on_a_second_press(qapp):
    window = make(qapp)
    count = len(FakeSetup.made)
    window.helix_card.setFocus()
    window.act("accept")
    assert not window.busy and ("A", "Press again") in legend(window)
    assert "Press the A button again" in window.helix_pane.status.text()
    window.act("accept")
    assert window.busy and len(FakeSetup.made) == count + 1
    wait_for(qapp, lambda: not window.busy)
    window.close()


def test_a_failed_build_says_why_and_view_asks_first_meanwhile(qapp, monkeypatch):
    window = make(qapp, built=False, setup=lambda *a: FakeSetup(*a, ok=False))
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.helix_card.setFocus()
    window.busy = True                                  # as while it runs
    window.act("view")
    assert closed == [] and legend(window) == [(VIEW, "Press again to exit")]
    window.busy = False
    window._confirm_over()
    window.act("accept")
    wait_for(qapp, lambda: not window.busy)
    assert window.helix_pane.status.text() == ("Get HelixSR failed: HelixSR's builder exited with code 2; the log "
                                               "has its output.")
    window.close()


def test_the_version_to_get_and_a_newer_release(qapp):
    newer = UpdateStatus("HelixSR", "2.0.0", ReleaseInfo("2.1.0", "v2.1.0", "", "2026-11-01"), "3.1.0")
    window = make(qapp, check_updates=lambda version: newer)
    assert window.helix_card.dot and "2.1.0 is out" in window.helix_card.text.text()
    assert window.helix_pane.status.text() == "HelixSR 2.1.0 is out: the A button gets it."
    window.helix_card.setFocus()
    window.act("previous")
    assert window.settings.value(FALLBACK_KEY, type=bool) and ("LB", "Use the latest") in legend(window)
    window.act("previous")
    assert not window.settings.value(FALLBACK_KEY, type=bool)
    window.close()


def test_nvidias_dll_found_in_steam_and_chosen(qapp):
    found = []
    window = make(qapp, find_dlss=lambda libraries, sha: found.append((libraries, sha)) or [Path("C:/x/nvngx_dlss.dll")])
    window.helix_card.setFocus()
    window.act("next")
    assert window.panes.currentWidget() is window.dlss_pane
    window.act("y")
    assert wait_for(qapp, lambda: len(window.dlss_pane.list.pills) == 3)
    assert found[0][1] == "be6e434a94ca32499515eb62ca0e6c274526055d568d0426e4c652dcdfb6ee6e"
    window.dlss_pane.list.pills["file:" + str(Path("C:/x/nvngx_dlss.dll"))].activated.emit()
    assert window.settings.value(DLSS_KEY) == str(Path("C:/x/nvngx_dlss.dll"))
    assert window.panes.currentWidget() is window.helix_pane
    window.close()


def test_import_takes_a_release_folder_in_the_browser(qapp):
    window = make(qapp, built=False)
    release = window.root / "drive" / "HelixSR-1.8.1"
    make_payload(release, "1.8.1", optiscaler=True)
    window.helix_card.setFocus()
    window.act("lt")
    assert window.panes.currentWidget() is window.browse_pane
    window.browse_pane.list.pills["dir:" + str(window.root / "drive")].activated.emit()
    window.browse_pane.list.pills["dir:" + str(release)].activated.emit()
    assert ("X", "Use this folder") in legend(window)
    window.act("x")
    assert window.panes.currentWidget() is window.helix_pane
    status = backend.payload_status(window.payload_dir)
    assert status.version == "1.8.1" and status.optiscaler
    window.close()


# Games

def test_the_games_with_fsr_come_first(qapp):
    window = make(qapp)
    texts = [pill.label.text() for pill in window.games_pane.list.pills.values()]
    assert [t.split("  ·  ")[0] for t in texts] == ["Alpha", "Gamma", "Beta"]
    assert texts[0] == "Alpha  ·  Not installed" and texts[2] == "Beta  ·  no FSR 3.1 DLL"
    assert window.games_card.text.text() == "2 of 3 games can use HelixSR."
    window.close()


def test_run_with_helixsr_asks_once_then_puts_it_in_and_starts_steam(qapp):
    window = make(qapp)
    game = focus_game(qapp, window, "Alpha")
    assert ("A", "Run with HelixSR") in legend(window)
    window.act("accept")
    assert "Press the A button again" in window.games_pane.status.text() and window.opened == []
    window.act("accept")
    assert window.opened == ["steam://rungameid/1000"]
    assert backend.original_path(upscaler(game)).read_bytes() == FAKE_GAME_DLL
    assert window.store.find(upscaler(game)).helixsr_version == "2.0.0"
    assert wait_for(qapp, lambda: window.games[game] is not None and window.games[game].state()[0] == "ok")
    window.act("accept")                                # in already: no second press, Steam starts it
    assert window.opened[-1] == "steam://rungameid/1000"
    window.close()


def test_go_back_on_a_second_press(qapp):
    window = make(qapp)
    game = focus_game(qapp, window, "Alpha")
    window.run_game(str(game))
    window.run_game(str(game))
    settled(qapp, window)
    qapp.processEvents()
    window.games_pane.list.pills[str(game)].setFocus()
    assert ("Y", "Go back") in legend(window)
    window.act("y")
    assert ("Y", "Press again") in legend(window) and backend.original_path(upscaler(game)).exists()
    window.act("y")
    assert upscaler(game).read_bytes() == FAKE_GAME_DLL and not backend.original_path(upscaler(game)).exists()
    assert window.store.items == []
    window.close()


def test_nothing_changes_while_the_game_runs_or_before_helixsr_is_built(qapp):
    window = make(qapp, running=lambda: "1000")
    game = focus_game(qapp, window, "Alpha")
    window.run_game(str(game))
    assert window.games_pane.status.text().startswith("Alpha is running. Close it first")
    window.close()
    window = make(qapp, built=False)
    game = focus_game(qapp, window, "Alpha")
    window.run_game(str(game))
    assert window.games_pane.status.text().startswith("Get HelixSR first")
    assert not backend.original_path(upscaler(game)).exists()
    window.close()


def test_a_folder_added_in_the_browser_and_taken_off(qapp):
    window = make(qapp)
    other = make_game(window.root / "drive", "Delta")
    focus_game(qapp, window, "Alpha")
    window.act("previous")
    assert window.panes.currentWidget() is window.browse_pane and window.focusWidget() is not window.helix_card
    window.browse_pane.list.pills["dir:" + str(window.root / "drive")].activated.emit()
    window.browse_pane.list.pills["dir:" + str(other)].activated.emit()
    window.act("x")
    assert window.settings.value(FOLDERS_KEY) == [str(other)] or window.settings.value(FOLDERS_KEY) == str(other)
    assert wait_for(qapp, lambda: window.games.get(other) is not None)
    window.render_timer.stop()
    window.show_games()
    window.games_pane.list.pills[str(other)].setFocus()
    assert ("A", "Put HelixSR in") in legend(window) and ("RB", "Take off the list") in legend(window)
    window.act("accept")
    window.act("accept")
    assert backend.original_path(upscaler(other)).is_file() and window.opened == []
    assert "Start the game as you always do" in window.games_pane.status.text()
    window.act("next")
    assert other not in window.games and window.added() == []
    window.close()


def test_the_optiscaler_page_puts_helixsr_and_optiscaler_in(qapp):
    window = make(qapp)
    make_payload(window.payload_dir, "1.8.1", optiscaler=True)
    game = focus_game(qapp, window, "Beta")
    window.act("x")
    assert window.panes.currentWidget() is window.opti_pane and window.pane_card is window.games_card
    rows = [pill.label.text() for pill in window.opti_pane.list.pills.values()]
    assert rows == ["OptiScaler beside the game's .exe: yes", "Second upscaler: none", "Write helixsr.ini: yes"]
    window.act("x")
    assert ("X", "Press again") in legend(window)
    window.act("x")
    folder = game / backend.HELIXSR_FOLDER
    exe_dir = game / "Beta" / "Binaries" / "Win64"
    assert (folder / backend.UPSCALER_DLL).is_file() and (exe_dir / "dxgi.dll").read_bytes() == b"MZ OptiScaler dll"
    assert window.store.find(folder).mode == backend.MODE_FOLDER
    assert "select DLSS" in window.opti_pane.status.text()
    window.opti_pane.list.pills["optiscaler"].activated.emit()
    assert ("LB", "Copy lines") in legend(window)
    window.act("previous")
    assert "FfxDx12Path=" in QGuiApplication.clipboard().text()
    window.act("y")
    window.act("y")
    assert not folder.exists() and not (exe_dir / "dxgi.dll").exists()
    window.act("back")
    assert window.panes.currentWidget() is window.games_pane
    window.close()


# Deployments

def test_update_older_games_and_forget(qapp):
    window = make(qapp)
    game = focus_game(qapp, window, "Alpha")
    window.run_game(str(game))
    window.run_game(str(game))
    make_payload(window.payload_dir, "2.1.0")           # a newer build is the payload now
    window.deploy_card.setFocus()
    qapp.processEvents()
    assert window.deploy_pane.list.first().label.text().endswith("Older build")
    assert ("RB", "Update older games") in legend(window)
    window.act("next")
    assert window.deploy_pane.status.text() == "HelixSR 2.1.0 put into 1 game(s)."
    assert window.deploy_pane.list.first().label.text().endswith("In place")
    window.focus_list(window.deploy_pane)
    window.act("x")
    assert window.store.items
    window.act("x")
    assert window.store.items == [] and backend.original_path(upscaler(game)).exists()
    window.close()


# Settings

def test_a_setting_is_saved_as_the_payloads_helixsr_ini_and_applied_to_a_game(qapp):
    window = make(qapp)
    game = focus_game(qapp, window, "Alpha")
    window.run_game(str(game))
    window.run_game(str(game))
    window.settings_card.setFocus()
    window.act("accept")
    assert window.focusWidget() is window.settings_pane.pills["sharpener"]          # 2.0 has no Mode row
    assert window.settings_pane.pills["sharpening_mode"].isHidden()
    window.act("accept")
    assert backend.parse_ini((window.payload_dir / backend.INI).read_text()).sharpener == "nvidia"
    assert window.settings_pane.pills["sharpener"].label.text() == "Sharpener: nvidia"
    window.act("y")
    assert window.panes.currentWidget() is window.apply_pane
    window.act("accept")
    assert backend.parse_ini((upscaler(game).parent / backend.INI).read_text()).sharpener == "nvidia"
    window.act("back")
    window.act("x")
    window.act("x")
    assert backend.parse_ini((window.payload_dir / backend.INI).read_text()).sharpener == "off"
    window.settings_pane.pills[CHECK_AT_START].activated.emit()
    assert window.settings.value(CHECK_KEY, type=bool) is False
    window.close()


def test_a_step_skips_a_value_that_would_make_the_file_invalid(qapp):
    window = make(qapp)
    window.ini.motion_threshold, window.ini.motion_limit = 6.0, 8.0
    window.step_setting("motion_threshold")             # 8 would not be below the limit: round to 0
    assert window.ini.motion_threshold == 0.0
    window.close()


# Log

def test_the_whole_log_is_read_in_the_pane(qapp, tmp_path):
    log = tmp_path / "app.log"
    log.write_text("one\ntwo\n", encoding="utf-8")
    window = make(qapp, log_path=log)
    window.log_card.setFocus()
    qapp.processEvents()
    assert legend(window)[0] == ("A", "View log")
    window.act("accept")
    assert window.log_pane.viewing and window.log_pane.view.toPlainText() == "one\ntwo"
    window.act("back")
    assert not window.log_pane.viewing
    window.close()


def test_without_steam_the_list_says_how_to_add_a_game(qapp):
    window = make(qapp, steam_dir=None)
    assert window.games == {} and "Steam was never started" in window.games_pane.summary.text()
    assert window.legend.items[-1] == EXIT
    window.close()


def test_version_is_the_single_source():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__ == INFO.version


def test_icons_are_beside_the_package():
    assert LOGO_PATH.is_file() and LOGO_PATH.name == f"{APP_ID}.webp"
    assert (ROOT / "images" / f"{APP_ID}-128.png").is_file()
    assert re.fullmatch(r"[A-Za-z0-9-]+", EXE_NAME)
