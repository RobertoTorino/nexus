# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py): the tabs and tiles, what the strip says for an app in each state, an install (the
release fetched in the background, the installer's PowerShell window, its exit status), opening an app, the details
page with Remove's second press, the Settings page with the portal's own update, and B."""

from __future__ import annotations

import hashlib
import html
import os
import re
import shutil
import time
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from bc250_core import portable, steam
from bc250_core.platform import private
from bc250_core.portable import MENU, VIEW
from bc250_core.gamepad import Gamepad
from bc250_core.updates import ReleaseInfo

from portable_portal import MANIFEST
from portable_portal import main_window as mw
from portable_portal.manifest import AppEntry, load
from portable_portal.portal_update import AppChange, PortalUpdate
from portable_portal.sources import Records, Sources
from test_operating_mode import FakeHelper

NEWER = f"{int(mw.__version__.split('.')[0]) + 1}.0.0"    # a portal release newer than this one, whatever its version


class FakePad:
    def __init__(self):
        self.queue = []

    def events(self):
        found, self.queue = self.queue, []
        return found

    def close(self):
        pass

    def names(self):
        return ["ASUSTeK Computer Inc."]


class FakeTerminal:
    """Stands in for the PowerShell window: records the line, runs the "installer" (makes or removes the app's
    program) and writes the exit status, as the window would."""

    def __init__(self, app_dir: Path, status: str = "0"):
        self.app_dir, self.status, self.lines, self.exit_files = app_dir, status, [], []

    def __call__(self, line: str, exit_file: Path | None = None, keep_open=True) -> None:
        self.lines.append(line)
        self.exit_files.append(exit_file)
        if exit_file is None:
            return
        if self.status == "0" and "--uninstall" in line:
            shutil.rmtree(self.app_dir, ignore_errors=True)
        elif self.status == "0":
            self.app_dir.mkdir(parents=True, exist_ok=True)
            (self.app_dir / "X.exe").write_bytes(b"x")
        exit_file.write_text(self.status + "\n")


def plain(label) -> str:
    """A status line as it reads, also when a part of it is colored (rich text)."""
    return html.unescape(re.sub(r"<[^>]+>", "", label.text())).replace(" ", " ")


def make_zip(path: Path, top: str) -> str:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{top}/install.ps1", b"Write-Host hi\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_for(qapp, predicate, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not predicate():
        qapp.processEvents()
        time.sleep(0.01)
    return predicate()


@pytest.fixture
def world(qapp, tmp_path, monkeypatch):
    """Two apps (test, required, and a gaming one), their releases served from a folder, the installer stood in
    for, and a window on them."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    app_dir = tmp_path / "Local" / "windows-portable-suite" / "windows-portable-test" / "app"
    other_dir = tmp_path / "Local" / "windows-portable-suite" / "windows-portable-pcsx2" / "app"
    test = AppEntry(key="test", name="Windows Portable Test", summary="Device and controller.", tag="wp-test-v0.1.0",
                    required=True, category="sustainable", install=("powershell -File install.ps1",),
                    uninstall=("powershell -File install.ps1 --uninstall",),
                    detect=(r"%LOCALAPPDATA%\windows-portable-suite\windows-portable-test\app\X.exe",),
                    launch=(("Open", r'"%LOCALAPPDATA%\windows-portable-suite\windows-portable-test\app\X.exe" --full'),))
    pcsx2 = AppEntry(key="pcsx2", name="Windows Portable PCSX2 Manager", summary="PS2 games.", tag="wp-pcsx2-v0.2.0",
                     category="gaming", install=("powershell -File install.ps1",),
                     uninstall=("powershell -File install.ps1 --uninstall",),
                     detect=(r"%LOCALAPPDATA%\windows-portable-suite\windows-portable-pcsx2\app\X.exe",),
                     launch=(("Open", r"%LOCALAPPDATA%\windows-portable-suite\windows-portable-pcsx2\app\X.exe"),))
    assets = tmp_path / "assets"
    assets.mkdir()
    sums = ""
    for tag in ("wp-test-v0.1.0", "wp-pcsx2-v0.2.0", f"wp-portal-v{NEWER}"):
        sums += f"{make_zip(assets / f'{tag}.zip', tag)}  {tag}.zip\n"
    (assets / "SHA256SUMS").write_text(sums)

    def download(url: str, dest: Path) -> None:
        src = assets / url.rsplit("/", 1)[1]
        if not src.is_file():
            raise OSError(f"404 {url}")
        shutil.copy(src, dest)

    class World:
        pass
    w = World()
    w.entries, w.app_dir, w.other_dir = [test, pcsx2], app_dir, other_dir
    w.sources = Sources(tmp_path / "state" / "releases", repo_url="https://example.invalid/r", download=download)
    w.records = Records(tmp_path / "state" / "installed.json")
    w.terminal = FakeTerminal(app_dir)
    w.launched = []
    w.checks = []
    w.update = PortalUpdate(ReleaseInfo(version=NEWER, tag=f"wp-portal-v{NEWER}", published="2030-01-01"),
                            [AppChange("Windows Portable Test", "0.1.0", "0.2.0")])
    w.windows = []
    w.played = []                                       # what the window's player was given: never a real sound
    w.displays = []                                     # what Windows' display setup was set to
    w.sound = "speakers"                                # where Windows plays the sound, as the window reads it
    w.notices = []                                      # the Windows notifications shown

    def make(portal_check=None, **kwargs):
        pad = FakePad()
        kwargs.setdefault("intro_ms", 0)                # the intro has its own tests
        kwargs.setdefault("steam_here", lambda: False)  # never this machine's own Steam
        kwargs.setdefault("startup", tmp_path / "Startup")   # never this user's own Startup folder
        kwargs.setdefault("shortcut", lambda link, target, arguments="", **_: (
            link.parent.mkdir(parents=True, exist_ok=True), link.write_text(f"{target} {arguments}")))
        kwargs.setdefault("chip_parts", lambda: ["CPU 12% 48°", "GPU 7% 47°"])   # never this machine's own chip
        kwargs.setdefault("modes", lambda: None)        # never this machine's own operating mode
        kwargs.setdefault("helper", lambda: FakeHelper(installed=False))   # nor its helper
        kwargs.setdefault("player", w.played.append)
        kwargs.setdefault("display", w.displays.append)     # never this machine's own display setup
        kwargs.setdefault("xbox_mode", lambda: w.displays.append("Win + F11"))   # nor its XBOX mode
        kwargs.setdefault("sound_kind", lambda: w.sound)    # never this machine's own sound outputs
        kwargs.setdefault("notify", w.notices.append)       # nor its notifications
        window = mw.MainWindow(w.entries, w.sources, w.records, portal_check=portal_check,
                               gamepad=Gamepad(source_factory=lambda: pad), battery=lambda: (82, False),
                               launch=w.launched.append, terminal=w.terminal, exit_dir=tmp_path / "exit", **kwargs)
        (tmp_path / "exit").mkdir(exist_ok=True)
        portable.scale((1280, 720))
        window.resize(1280, 720)
        window.show()
        window.activateWindow()
        qapp.processEvents()
        window.start()
        w.windows.append(window)
        return window
    w.make = make
    yield w
    for window in w.windows:
        window.close()


def pane_texts(window) -> tuple[str, str, str]:
    pane = window.app_pane
    return (pane.name.text(), pane.main, pane.other)


def test_the_tabs_and_tiles_and_the_strip_for_the_focused_app(world, qapp):
    window = world.make()
    assert window.tabs.keys == ["sustainable", "gaming"] and window.tabs.current == "sustainable"
    assert window.tiles["test"].isVisible() and not window.tiles["pcsx2"].isVisible()
    assert window.tiles["test"].hasFocus() and window.tiles["test"].icon is not None      # the suite's drawing
    assert window.tiles["test"].text.text() == "Not installed"
    assert pane_texts(window) == ("Windows Portable Test", "Install", "")
    assert window.app_pane.versions.text() == "Not installed; this portal has 0.1.0"
    # The date and the time; under them the CPU and the GPU live and the battery last (owner, 30-10-2026: two
    # lines, one was wider than the Ally's screen)
    assert window.header.second.text() == "CPU 12% 48°  |  GPU 7% 47°  |  82%" and "CPU" not in window.header.status.text()
    assert mw.STATUS_MS == 2_000
    # The Ally X's operating mode, its letter just before the battery (owner, 31-10-2026)
    window.mode_marker = lambda: "T"
    window.update_status()
    assert plain(window.header.second) == "CPU 12% 48°  |  GPU 7% 47°  |  T  |  82%"
    assert f'<span style="color: {mw.TURBO_COLOR}; font-weight: 800">T</span>' in window.header.second.text()  # red
    window.mode_marker = lambda: "P"
    window.update_status()
    assert window.header.second.text() == "CPU 12% 48°  |  GPU 7% 47°  |  P  |  82%"          # the others plain
    assert [text for _, text in window.legend.items][1:] == ["Details", "Settings", portable.KEYBOARD_ICON, "Exit"]
    assert isinstance(window.legend.entries["R3"].label, portable.KeyboardIcon)   # a symbol, not a word (owner)
    assert window.legend.items[0][0] == "A" and window.app_pane.findChildren(portable.Pill) == []   # no pill (owner)
    window.tabs.step(1)
    assert window.tabs.current == "gaming" and window.tiles["pcsx2"].isVisible() and not window.tiles["test"].isVisible()
    assert pane_texts(window)[0] == "Windows Portable PCSX2 Manager" and window.tiles["pcsx2"].hasFocus()
    window.tabs.step(1)
    assert window.tabs.current == "sustainable"                                          # round


def test_the_last_tab_is_remembered(world, qapp):
    first = world.make()
    first.tabs.select("gaming")
    first.close()
    assert world.make().tabs.current == "gaming"


def test_a_installs_the_app_through_its_installer_window(world, qapp):
    window = world.make()
    window.on_action("accept")
    assert window.tiles["test"].text.text() == "Downloading…" and pane_texts(window)[1] == ""
    assert wait_for(qapp, lambda: window.pending is not None)
    assert window.tiles["test"].text.text() == "Installing…"
    line = world.terminal.lines[0]
    folder = world.sources.folder(world.entries[0])
    assert line.startswith(f"Set-Location -LiteralPath '{folder}'; powershell -File install.ps1; if ($LASTEXITCODE")
    assert (folder / "install.ps1").is_file()
    assert wait_for(qapp, lambda: window.pending is None)
    assert world.records.get("test") == "wp-test-v0.1.0"
    assert window.tiles["test"].text.text() == "Installed 0.1.0" and pane_texts(window) == ("Windows Portable Test", "Open", "")
    assert window.app_pane.status.text() == "Windows Portable Test 0.1.0 is installed."
    assert not world.terminal.exit_files[0].exists()


def test_a_failed_install_says_so_and_changes_nothing(world, qapp):
    world.terminal.status = "1"
    window = world.make()
    window.main_action("test")
    assert wait_for(qapp, lambda: window.pending is None and window.job is None and world.terminal.lines)
    assert world.records.get("test") == "" and window.tiles["test"].text.text() == "Not installed"
    assert "exit status 1" in window.app_pane.status.text()
    world.terminal.status = "0"
    world.sources.download = lambda url, dest: (_ for _ in ()).throw(OSError("offline"))
    shutil.rmtree(world.sources.work)
    window.main_action("test")
    assert wait_for(qapp, lambda: window.job is None)
    assert "could not be prepared" in window.app_pane.status.text() and "offline" in window.app_pane.status.text()


def test_an_update_and_a_reinstall_are_offered_with_y(world, qapp):
    world.app_dir.mkdir(parents=True)
    (world.app_dir / "X.exe").write_bytes(b"x")
    world.records.set("test", "wp-test-v0.0.9")
    window = world.make()
    assert window.tiles["test"].text.text() == "Update 0.1.0" and pane_texts(window) == ("Windows Portable Test", "Open", "Update")
    assert window.tiles["test"].dot and not window.tiles["pcsx2"].dot     # the red dot (owner, 29-10-2026)
    assert window.app_pane.versions.text() == "Installed 0.0.9; this portal has 0.1.0"
    world.records.remove("test")
    window.refresh()
    assert window.tiles["test"].text.text() == "Installed, version unknown" and pane_texts(window)[2] == "Reinstall"
    window.on_action("y")
    assert wait_for(qapp, lambda: window.pending is None and world.records.get("test") == "wp-test-v0.1.0")
    assert pane_texts(window) == ("Windows Portable Test", "Open", "")


def test_a_opens_an_installed_app_detached(world, qapp):
    world.app_dir.mkdir(parents=True)
    (world.app_dir / "X.exe").write_bytes(b"x")
    world.records.set("test", "wp-test-v0.1.0")
    window = world.make()
    window.on_action("accept")
    assert world.launched == [[str(world.app_dir / "X.exe"), "--full"]]
    assert world.terminal.lines == []


def test_rt_opens_steam_where_it_is_installed(world, qapp):
    """RT Steam (owner, 30-10-2026: the game managers' Open Steam, now in the portal's bottom row): on every page
    while Steam is installed, by RT or a tap; without Steam no entry, and RT says why."""
    opened, here = [], [True]
    window = world.make(steam_here=lambda: here[0], open_steam=opened.append)
    assert ("RT", "Steam") in window.legend.items and window.legend.items[-1] == (VIEW, "Exit")
    window.on_action("rt")
    assert opened == [steam.OPEN_URL] and window.app_pane.status.text() == "Opening Steam…"
    window.legend._tapped("RT")
    assert opened == [steam.OPEN_URL] * 2
    window.on_action("menu")
    assert ("RT", "Steam") in window.legend.items                 # the Settings page too
    window.on_action("back")
    here[0] = False
    window.refresh()
    assert ("RT", "Steam") not in window.legend.items
    window.on_action("rt")
    assert opened == [steam.OPEN_URL] * 2 and window.app_pane.status.text() == mw.STEAM_MISSING

    def fails(url):
        raise FileNotFoundError(2, "The system cannot find the file specified")
    window = world.make(steam_here=lambda: True, open_steam=fails)
    window.on_action("rt")
    assert window.app_pane.status.text() == "Steam could not be opened: The system cannot find the file specified"


def test_the_settings_page_has_no_xbox_menu_row(world, qapp):
    """The XBOX menu row is gone (owner, 07-11-2026: it was very slow, the XBOX app has to be ended and started again
    for each change); install.ps1 still offers it on a first install."""
    window = world.make()
    window.on_action("menu")
    assert not hasattr(window.suite_pane, "xbox") and "XBOX menu" not in window.suite_pane.info.info


def test_the_operating_mode_page_on_the_ally_x(world, qapp, monkeypatch):
    """The ROG XBOX Ally X's operating mode (owner, 31-10-2026): a Settings row opens its page, a row per mode with
    its watts for the power source now; A sets the plan and the power mode; B goes back to Settings."""
    from portable_portal import operating_mode as om
    from test_operating_mode import FakeApi
    window = world.make()
    window.on_action("menu")
    assert not window.suite_pane.mode.isVisible()                   # not an Ally X
    window.close()
    turbo = om.BY_LETTER["T"]
    api = FakeApi(turbo.plan, turbo.overlay)
    window = world.make(modes=lambda: api)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert plain(window.header.second) == "CPU 12% 48°  |  GPU 7% 47°  |  T  |  82%"
    window.on_action("menu")
    row = window.suite_pane.mode
    assert row.isVisible() and row.label.text() == "Performance mode: Turbo"
    assert "Performance mode: the ROG XBOX Ally X's mode" in window.suite_pane.info.info
    row.activated.emit()
    pane = window.mode_pane
    assert window.stack.currentWidget() is pane and pane.rows["T"].hasFocus()
    assert pane.source.text() == "On battery"                       # the fixture's battery: 82 %, unplugged
    assert [r.label.text() for r in pane.rows.values()] == [
        "Silent: 13 / 16 / 20 W", "Performance: 17 / 21 / 26 W", "Turbo: 25 / 30 / 36 W  (active)",
        "Windows: 17 / 21 / 26 W"]
    assert window.legend.items[0] == ("A", "Set") and ("B", "Back") in window.legend.items
    window.on_action("up")
    window.on_action("up")
    assert pane.rows["S"].hasFocus()
    assert pane.helper.label.text() == "Watt limits: Install"
    window.on_action("accept")
    assert api.calls == [("plan", om.BY_LETTER["S"].plan), ("overlay", om.EFFICIENCY)]
    assert pane.status.text().startswith("Silent set: its power plan and power mode. The watts stay as Armoury Crate")
    assert pane.rows["S"].label.text().endswith("(active)")
    assert window.header.second.text().endswith("|  S  |  82%")
    window.battery = lambda: (82, True)                             # the charger in: its watts
    window.update_status()
    assert pane.source.text() == "On the charger" and pane.rows["T"].label.text() == "Turbo: 35 / 44 / 55 W"
    api.fails = ("plan",)
    pane.rows["T"].activated.emit()
    assert pane.status.text() == "Turbo not set: Windows did not take its power plan or power mode."
    window.on_action("menu")
    assert window.popup is not None and "Command Center keeps its own record" in pane.info.info
    window.on_action("back")
    assert window.popup is None
    window.on_action("back")
    assert window.stack.currentWidget() is window.suite_pane and row.hasFocus()
    assert row.label.text() == "Performance mode: Silent"
    api._plan = "11111111-1111-1111-1111-111111111111"              # another plan
    window.show_suite(row)
    assert row.label.text() == "Performance mode: Other"
    window.on_action("back")
    assert window.stack.currentWidget() is window.apps_page


def test_the_operating_mode_helper_writes_the_watts(world, qapp, monkeypatch):
    """The helper (owner, 31-10-2026): installed from the Watt limits row with Windows' prompt, asked for the whole
    mode after the portal set its plan and power mode, its answer on the page."""
    from portable_portal import operating_mode as om
    from test_operating_mode import FakeApi
    monkeypatch.setattr(mw, "HELPER_ANSWER_S", -1)       # never waited for in the test
    helper = FakeHelper(installed=False)
    window = world.make(modes=lambda: FakeApi(), helper=lambda: helper)
    window.on_action("menu")
    window.suite_pane.mode.activated.emit()
    pane = window.mode_pane
    assert window.suite_pane.mode.label.text() == "Performance mode: Other" and pane.rows["S"].hasFocus()
    pane.helper.activated.emit()
    assert helper.installs == [False] and pane.status.text() == "Installing the helper: answer Windows' prompt…"
    helper._installed = True
    window._check_helper()
    assert pane.status.text() == "The helper is installed: a mode set here sets its watts too."
    assert pane.helper.label.text() == "Watt limits: Installed" and not window.helper_timer.isActive()
    helper.answer = "T ok battery 25 / 30 / 36 W"
    pane.rows["T"].activated.emit()
    assert helper.requests == ["T"] and pane.status.text() == "Turbo set; its watts are being written…"
    window._check_helper()
    assert pane.status.text() == "Turbo set, with its watts: 25 / 30 / 36 W."
    helper.answer = "S failed the firmware did not take 0x001200A3 (13 / 16 / 20 W)"
    pane.rows["S"].activated.emit()
    window._check_helper()
    assert pane.status.text() == "Silent set, but not its watts: the firmware did not take 0x001200A3 (13 / 16 / 20 W)."
    helper.answer = None                                            # no answer in time
    pane.rows["P"].activated.emit()
    window._check_helper()
    assert pane.status.text() == "Performance set; the helper did not answer, so its watts may not be written."
    helper.error = "the helper's task could not be started (schtasks: 1)"
    pane.rows["W"].activated.emit()
    assert pane.status.text() == "Windows set, but not its watts: the helper's task could not be started (schtasks: 1)."
    helper.install_error = "administrator rights were not given"
    pane.helper.activated.emit()
    assert helper.installs == [False, True]
    assert pane.status.text() == "The helper was not removed: administrator rights were not given."


def test_x_shows_the_details_and_remove_takes_a_second_press(world, qapp):
    world.app_dir.mkdir(parents=True)
    (world.app_dir / "X.exe").write_bytes(b"x")
    world.records.set("test", "wp-test-v0.1.0")
    window = world.make()
    window.on_action("x")
    assert window.stack.currentWidget() is window.details_pane
    assert window.legend.items == [("A", "Open"), ("Y", "Remove"), portable.KEYBOARD, ("B", "Back"), (VIEW, "Exit")]
    rows = {window.details_pane.grid.itemAt(i).widget().text(): window.details_pane.grid.itemAt(i + 1).widget().text()
            for i in range(0, window.details_pane.grid.count(), 2)}
    assert rows["Installed"] == "0.1.0 (wp-test-v0.1.0)" and rows["This portal pins"] == "wp-test-v0.1.0"
    assert rows["Program"] == private(world.app_dir / "X.exe") and rows["Category"] == "Sustainable"   # no user name
    window.on_action("y")
    assert ("Y", "Press again to remove") in window.legend.items and world.terminal.lines == []
    window._confirm_over()                                      # the few seconds passed: asked again
    assert ("Y", "Remove") in window.legend.items
    window.on_action("y")
    window.on_action("y")
    assert wait_for(qapp, lambda: window.pending is None and world.terminal.lines)
    assert "--uninstall" in world.terminal.lines[0] and world.records.get("test") == ""
    assert not world.app_dir.exists() and not world.sources.folder(world.entries[0]).exists()
    assert window.stack.currentWidget() is window.apps_page           # back: the app is gone
    assert window.tiles["test"].text.text() == "Not installed"


def test_b_goes_back_and_view_exits(world, qapp, monkeypatch):
    """The suite's buttons (owner, 29-10-2026: "Close" on B was not clear): B goes back from a page to the tiles, and
    on a tile does nothing; View (Exit) closes the portal after its question (owner, 05-11-2026), a tap on its
    entry too, and B is the question's No."""
    window = world.make()
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.on_action("menu")
    assert window.stack.currentWidget() is window.suite_pane and window.suite_pane.wallpaper.hasFocus()
    window.on_action("back")
    assert window.stack.currentWidget() is window.apps_page and window.tiles["test"].hasFocus() and closed == []
    window.on_action("back")                            # on a tile: nothing
    assert closed == [] and window.tiles["test"].hasFocus()
    window.on_action("menu")
    window.legend.entries[VIEW].pressed.emit()          # asked on the Settings page too
    assert closed == [] and window.legend.items == mw.EXIT_ANSWERS
    assert window.message == "Do you really want to exit the portal?"
    window.on_action("back")                            # No: the question gone, still on the Settings page
    assert closed == [] and not window.close_asked and window.stack.currentWidget() is window.suite_pane
    assert ("B", "Back") in window.legend.items and window.message == ""
    window.legend.entries[VIEW].pressed.emit()
    window.legend.entries[VIEW].pressed.emit()          # Yes
    assert closed == [True]


def test_the_portal_looks_for_its_update_again(world, qapp, monkeypatch):
    """Not only at the start (owner's roadmap, 04-11-2026): every hour, and when the portal is active again once the
    last check is a quarter of an hour old; a check again that fails keeps the update found before."""
    from PyQt6.QtCore import QEvent
    answers = [world.update]
    calls = []

    def check():
        calls.append(True)
        return answers[-1]
    window = world.make(portal_check=check)
    assert wait_for(qapp, lambda: window.update is not None and not window.checking)
    assert len(calls) == 1 and window.update_available()
    assert window.recheck_timer.isActive() and window.recheck_timer.interval() == mw.RECHECK_MS
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.changeEvent(QEvent(QEvent.Type.ActivationChange))    # active again at once: not looked for again
    assert len(calls) == 1 and not window.checking
    window.checked_at -= mw.RECHECK_AFTER_S                     # a quarter of an hour later
    answers.append(PortalUpdate(ReleaseInfo(error="offline"), []))
    window.changeEvent(QEvent(QEvent.Type.ActivationChange))
    assert wait_for(qapp, lambda: len(calls) == 2 and not window.checking)
    assert window.update_available() and window.update is answers[0]            # offline for a moment: it stays
    window.check_portal()                                       # Check again on the Settings page shows the error
    assert wait_for(qapp, lambda: len(calls) == 3 and not window.checking)
    assert window.update is answers[1] and not window.update_available()
    answers.append(world.update)
    window.recheck_timer.timeout.emit()                         # an hour later
    assert wait_for(qapp, lambda: len(calls) == 4 and not window.checking) and window.update_available()


def test_a_portal_newer_than_the_newest_release_says_so(world, qapp):
    """A draft on its device test (owner, 30-10-2026: "it says the latest update is 5.0.0 but the version is already
    6.0.0"): the newest release is older than this portal, which is not published yet."""
    older = PortalUpdate(ReleaseInfo(version="0.0.1", tag="wp-portal-v0.0.1", published="2026-10-30"), [])
    window = world.make(portal_check=lambda: older)
    assert wait_for(qapp, lambda: window.update is not None)
    window.show_suite()
    rows = {window.suite_pane.grid.itemAt(i).widget().text(): window.suite_pane.grid.itemAt(i + 1).widget().text()
            for i in range(0, window.suite_pane.grid.count(), 2)}
    assert rows["Newest release"] == "0.0.1, 2026-10-30: older than this portal, which is not published yet"
    assert ("Y", "Check again") in window.legend.items and "available" not in window.header.status.text()


def test_the_suite_page_offers_the_portals_own_update_and_installs_it(world, qapp, monkeypatch):
    window = world.make(portal_check=lambda: world.update, exe=r"C:\portal\Windows-Portable-Suite.exe")
    assert wait_for(qapp, lambda: window.update is not None)
    assert f"Suite {NEWER} available" in window.header.status.text()
    window.show_suite()
    rows = {window.suite_pane.grid.itemAt(i).widget().text(): window.suite_pane.grid.itemAt(i + 1).widget().text()
            for i in range(0, window.suite_pane.grid.count(), 2)}
    assert rows == {"Newest release": f"{NEWER}, 2030-01-01", "It brings": "updates Test"}    # this portal: the line
    assert window.suite_pane.version.text() == f"{mw.__version__}, the portal of the suite"   # under the title
    # App by app in the information (owner, 01-11-2026: eight apps' lines ran over each other)
    assert window.suite_pane.info.info.startswith("The update brings:\nWindows Portable Test: 0.1.0 → 0.2.0\n\n")
    assert ("Y", f"Update to {NEWER}") in window.legend.items           # A switches the setting, Y updates
    assert window.banner.isVisible() and window.banner.text() == mw.BANNER
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.on_action("y")
    assert wait_for(qapp, lambda: closed == [True])
    line = world.terminal.lines[0]
    folder = world.sources.work.parent / "portal-update" / f"wp-portal-v{NEWER}"
    assert (folder / "install.ps1").is_file()
    assert line.startswith("Wait-Process -Id ") and f"Set-Location -LiteralPath '{folder}'" in line
    assert "-File install.ps1" in line and line.endswith("Start-Process -FilePath 'C:\\portal\\Windows-Portable-Suite.exe'")
    assert world.terminal.exit_files == [None]


def test_the_banner_offers_the_portals_update_on_the_tiles(world, qapp, monkeypatch):
    """Owner, 01-11-2026: the portal's update was hidden on the Settings page. While a newer portal is out, a banner on
    the tabs' line says so on the tiles and the Settings page (not on Details, where Y removes); Y on the tiles, or a
    tap on the banner, updates the portal before an app; once there is no update, the banner is gone."""
    world.app_dir.mkdir(parents=True)
    (world.app_dir / "X.exe").write_bytes(b"x")
    world.records.set("test", "wp-test-v0.0.9")         # an app update waits too: the portal goes first
    window = world.make(portal_check=lambda: world.update, exe=r"C:\portal\Windows-Portable-Suite.exe")
    assert wait_for(qapp, lambda: window.update is not None)
    assert window.banner.isVisible() and window.banner.text() == "UPDATE AVAILABLE, PRESS Y TO UPDATE"
    assert ("Y", "Update suite") in window.legend.items
    window.on_action("x")
    assert window.stack.currentWidget() is window.details_pane and not window.banner.isVisible()
    window.on_action("back")
    assert window.banner.isVisible()
    window.pending = mw.Pending(world.entries[1], "install", world.sources.work / "x.exit", "t")   # an app installing
    window.banner.pressed.emit()
    assert window.app_pane.status.text() == mw.WAIT_UPDATE and window.job is None
    window.pending = None
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.on_action("y")
    assert wait_for(qapp, lambda: closed == [True])
    assert world.terminal.lines[0].startswith("Wait-Process -Id ") and world.records.get("test") == "wp-test-v0.0.9"
    window.update = PortalUpdate(ReleaseInfo(version=mw.__version__, tag=f"wp-portal-v{mw.__version__}"))
    window.refresh()
    assert not window.banner.isVisible() and ("Y", "Update") in window.legend.items      # the app's own again


def test_the_screens_as_windows_names_them(world, qapp, monkeypatch, tmp_path):
    """XBOX mode runs on Windows' main screen only and leaves the TV empty (found on the Ally, 05-11-2026): the
    Settings page's rows switch Windows' display setup as Win + P does and names them (owner, 07-11-2026: PC screen
    only, Duplicate, Extend, Second screen only), always shown (with the TV alone Windows sees one screen); a switch
    that does not start says so."""
    window = world.make()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    moved = []
    monkeypatch.setattr(window, "move_to", moved.append)
    monkeypatch.setattr(mw, "SETTLE_MS", 0)
    window.on_action("menu")
    pane = window.suite_pane
    rows = [pane.handheld, pane.both, pane.extend, pane.tv]
    assert [row.label.text() for row in rows] == ["PC screen only", "Duplicate", "Extend", "Second screen only"]
    assert all(row.isVisible() for row in rows)
    assert "Second screen only: the second screen only (a TV or a monitor)" in pane.info.info
    pane.tv.setFocus()
    window.on_action("accept")
    assert world.displays == ["/external"] and pane.status.text() == mw.ON_SECOND
    # then the portal starts again on Windows' main screen, sized for it (owner, 05-11-2026: the TV cut it off)
    assert wait_for(qapp, lambda: moved == [mw.QGuiApplication.primaryScreen()])
    pane.handheld.activated.emit()                      # a tap
    assert world.displays == ["/external", "/internal"] and pane.status.text() == mw.ON_HANDHELD
    pane.both.activated.emit()
    assert world.displays[-1] == "/clone" and pane.status.text() == mw.ON_BOTH
    pane.extend.activated.emit()                        # Extend, missing before (owner, 07-11-2026)
    assert world.displays[-1] == "/extend" and pane.status.text() == mw.ON_EXTEND
    assert wait_for(qapp, lambda: len(moved) == 4)
    pane.xbox_mode.activated.emit()                     # XBOX mode or the desktop: Win + F11, either way
    assert world.displays[-1] == "Win + F11" and pane.status.text() == mw.SWITCHED_MODE
    assert "XBOX mode ↔ Desktop: Windows' switch" in pane.info.info

    def broken(mode):
        raise OSError("not found")
    window.display = broken
    pane.tv.activated.emit()
    assert pane.status.text() == "Windows' display setting did not change: not found"


def test_the_screen_goes_back_to_the_handheld_after_the_portal(world, qapp, monkeypatch, tmp_path):
    """Owner, 07-11-2026: after exiting the portal or a restart the screen should be the handheld's again, it kept the
    last one set. Any screen but PC screen only puts a shortcut in the Startup folder that sets PC screen only at the
    next sign-in; PC screen only takes it away, and so does exiting with View, which sets PC screen only first. A
    restart of the portal by itself (after a switch) leaves both alone."""
    link = tmp_path / "Startup" / mw.STARTUP_LINK
    window = world.make()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    monkeypatch.setattr(window, "move_to", lambda screen: None)
    window.suite_pane.extend.activated.emit()
    assert link.read_text() == f"{mw.DISPLAY_SWITCH} /internal"
    window.suite_pane.handheld.activated.emit()
    assert not link.exists() and world.displays == ["/extend", "/internal"]
    window.suite_pane.tv.activated.emit()
    assert link.exists()
    window.close()                                      # the portal starting again: nothing changes
    assert link.exists() and world.displays[-1] == "/external"
    window = world.make(booted=lambda: 0.0)             # a start after it, Windows not restarted: it stays
    assert link.exists()
    window.on_action("view")
    window.on_action("view")                            # exit: PC screen only, the shortcut gone
    assert world.displays[-1] == "/internal" and not link.exists()
    window.close()
    window = world.make()
    window.on_action("view")
    window.on_action("view")                            # nothing set here: the screen is left as it is
    assert world.displays[-1] == "/internal" and len([d for d in world.displays if d == "/internal"]) == 2
    link.write_text("x")                                # from before Windows' last start: done at the sign-in
    os.utime(link, (1000, 1000))
    world.make(booted=lambda: 2000.0)
    assert not link.exists()


def test_every_controller_action_has_its_sound(world, qapp, monkeypatch):
    """A short sound on every controller action (owner, 05-11-2026), as the BC250 portal: the owner's blob.wav, off
    with the suite's Sound setting, none while the intro plays (its button only skips it) or the portal is not
    the active window."""
    from portable_portal import ACTION_SOUND
    assert ACTION_SOUND.name == "blob.wav" and ACTION_SOUND.is_file()
    window = world.make(intro_ms=60_000)
    active = [True]
    monkeypatch.setattr(window, "isActiveWindow", lambda: active[0])
    window.on_action("right")                           # skips the intro: no sound of its own
    assert window.intro is None and world.played == [mw.INTRO_SOUND, None]     # the intro's, then cut short
    world.played.clear()
    window.on_action("right")
    window.on_action("x")
    assert world.played == [ACTION_SOUND, ACTION_SOUND]
    window.on_action("back")
    active[0] = False                                   # a game has the controller
    window.on_action("right")
    assert world.played == [ACTION_SOUND] * 3
    active[0] = True
    portable.set_sound_on(mw.SUITE, False)              # Sound: Off
    window.on_action("right")
    assert world.played == [ACTION_SOUND] * 3


def test_the_intro_says_a_portal_update_is_out(world, qapp):
    """The banner on the intro when the update check answers while it plays (owner, 01-11-2026)."""
    window = world.make(portal_check=lambda: world.update, intro_ms=60_000)
    window.intro.player = lambda wav: None             # no sound in the tests
    window.start()
    assert wait_for(qapp, lambda: window.update is not None)
    assert window.intro.banner == "PORTAL UPDATE AVAILABLE"
    window.intro.progress = window.intro.banner_at + 0.2   # drawn, faded in
    assert not window.intro.grab().isNull()
    window.intro.skip()
    assert window.intro is None


def test_the_suite_page_without_an_update(world, qapp):
    same = PortalUpdate(ReleaseInfo(version=mw.__version__, tag=f"wp-portal-v{mw.__version__}"))
    window = world.make(portal_check=lambda: same)
    assert wait_for(qapp, lambda: window.update is not None)
    assert "available" not in window.header.status.text()
    window.show_suite()
    assert ("Y", "Check again") in window.legend.items
    offline = PortalUpdate(ReleaseInfo(error="no connection (offline)"))
    window.portal_check = lambda: offline
    window.legend.entries["Y"].pressed.emit()
    assert wait_for(qapp, lambda: window.update is offline)
    assert window.suite_pane.grid.itemAt(1).widget().text() == "not known: no connection (offline)"
    assert not window.banner.isVisible() and not window.suite_pane.info.info.startswith("The update brings")


def test_a_new_build_of_this_version_is_offered(world, qapp):
    """A release built again under the same version (owner, 31-10-2026: the Ally kept the 6.4.0 draft the device test
    turned down, and the version alone never offered the 6.4.0 that replaced it): offered when its zip's sha256 is
    not the one this portal came from, or that one is not known; never from a checkout."""
    rebuilt = PortalUpdate(ReleaseInfo(version=mw.__version__, tag=f"wp-portal-v{mw.__version__}",
                                       published="2026-10-31"), [AppChange("Windows Portable Test", "0.1.0", "0.2.0")],
                           sha256="a" * 64)
    window = world.make(portal_check=lambda: rebuilt, build="b" * 64)
    assert wait_for(qapp, lambda: window.update is not None)
    assert window.update_available() and f"Suite {mw.__version__} available" in window.header.status.text()
    window.show_suite()
    rows = {window.suite_pane.grid.itemAt(i).widget().text(): window.suite_pane.grid.itemAt(i + 1).widget().text()
            for i in range(0, window.suite_pane.grid.count(), 2)}
    assert rows["Newest release"] == f"{mw.__version__}, 2026-10-31: a new build of this version"
    assert rows["It brings"] == "updates Test" and ("Y", f"Update to {mw.__version__}") in window.legend.items
    window.build = ""                                   # installed before build.sha256: offered once
    assert window.update_available()
    window.build = "a" * 64                             # this build
    assert not window.update_available()
    window.build = None                                 # from a checkout
    assert not window.update_available()
    window.build = "b" * 64
    window.update = replace(rebuilt, sha256="")         # SHA256SUMS not read: the version alone decides
    assert not window.update_available()
    window.update = replace(rebuilt, release=replace(rebuilt.release, version="0.0.1"))   # an older release
    assert not window.update_available()


def test_every_summary_fits_one_line_of_the_app_pane(world, qapp):
    """The pane under the tiles is the title and two lines, the versions and the summary (owner, 31-10-2026:
    shadPS4's wrapped to a third): every summary of apps.toml fits one line at 1280 x 720."""
    window = world.make()
    label = window.app_pane.summary
    width = label.contentsRect().width()
    for entry in load(MANIFEST):
        assert label.fontMetrics().horizontalAdvance(entry.summary) <= width, f"{entry.key}: summary longer than a line"


def test_ps_line_and_launch_argv(monkeypatch):
    line = mw.ps_line(Path(r"C:\it's\wp-test-v0.1.0"), ("powershell -File install.ps1", "second"))
    assert line == ("Set-Location -LiteralPath 'C:\\it''s\\wp-test-v0.1.0'; powershell -File install.ps1; "
                    'if ($LASTEXITCODE -ne 0) { throw "ended with exit status $LASTEXITCODE" }; second; '
                    'if ($LASTEXITCODE -ne 0) { throw "ended with exit status $LASTEXITCODE" }')
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\me\AppData\Local")
    assert mw.launch_argv(r'"%LOCALAPPDATA%\suite\app\X.exe" --full') == [r"C:\Users\me\AppData\Local\suite\app\X.exe", "--full"]
    assert mw.launch_argv(r"%LOCALAPPDATA%\suite\app\X.exe") == [r"C:\Users\me\AppData\Local\suite\app\X.exe"]
    assert mw.restart_line(Path(r"C:\u"), "").endswith('{ throw "install.ps1 ended with exit status $LASTEXITCODE" }')


def test_the_update_window_leaves_the_program_folder_before_the_installer_runs():
    # The window starts in the portal's working directory, its program folder: while a process has it as its working
    # directory install.ps1 cannot replace it (owner, 28-10-2026: the update deleted the program and stopped).
    steps = mw.restart_line(Path(r"C:\rel"), r"C:\app\X.exe").split("; ")
    moved = steps.index(r"[Environment]::CurrentDirectory = 'C:\rel'")
    assert steps.index(r"Set-Location -LiteralPath 'C:\rel'") < moved
    assert moved < steps.index("powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1")
    assert steps[-1] == r"Start-Process -FilePath 'C:\app\X.exe'"


def test_the_intro_plays_at_the_start_and_any_button_skips_it(world, qapp, monkeypatch):
    played = world.played                               # the window's player, the intro's too
    window = world.make(intro_ms=60_000)
    assert len(played) == 1 and played[0].name == "intro.wav"
    intro = window.intro
    assert intro is not None and intro.isVisible() and intro.name == "Windows Portable Suite"
    assert intro.geometry() == window.rect()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("accept")                          # skips the intro, installs nothing
    assert window.intro is None and world.terminal.lines == [] and intro.done
    assert window.tiles["test"].hasFocus() and played[-1] is None


def test_the_intro_ends_by_itself(world, qapp, monkeypatch):
    monkeypatch.setattr("portable_portal.intro.play", lambda wav: None)
    window = world.make(intro_ms=50)
    assert window.intro is not None
    end = time.monotonic() + 5
    while window.intro is not None and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)
    assert window.intro is None


def test_the_intro_paints_every_phase_and_plays_its_sound(qapp):
    from PyQt6.QtWidgets import QWidget
    from portable_portal import INTRO_SOUND
    from portable_portal.intro import Intro
    assert INTRO_SOUND.is_file() and INTRO_SOUND.read_bytes()[:4] == b"RIFF"
    host = QWidget()
    host.resize(1280, 720)
    played = []
    intro = Intro(host, player=played.append)
    intro.begin()
    assert played == [INTRO_SOUND]
    for step in range(11):
        intro.progress = step / 10
        assert not intro.grab().isNull()
    intro.skip()
    assert played == [INTRO_SOUND, None]                # skipped: the sound stops too
    intro.skip()
    assert played == [INTRO_SOUND, None]


def test_the_intro_ends_with_its_sound(qapp):
    from PyQt6.QtWidgets import QWidget
    from portable_portal.intro import Intro
    host = QWidget()
    played = []
    intro = Intro(host, duration=10, player=played.append)
    intro.begin()
    end = time.monotonic() + 5
    while not intro.done and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)
    assert intro.done and played == [played[0]]         # ended by itself: the sound plays on to its end


def test_a_download_shows_how_far_it_is(world, qapp, monkeypatch):
    # 94 MB of a portal release took two minutes on the Ally with nothing moving on screen (owner, 28-10-2026).
    import threading
    release = threading.Event()
    first = world.sources.download

    def slow(url: str, dest: Path) -> None:
        if url.endswith(".zip"):
            dest.write_bytes(b"\0" * 3_000_000)         # the first 3 MB are in
            release.wait(10)
        first(url, dest)
    monkeypatch.setattr(world.sources, "download", slow)
    window = world.make()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("accept")                          # A: install the focused app (the test app)
    assert wait_for(qapp, lambda: window.tiles["test"].text.text() == "Downloading… 3 MB")
    release.set()
    assert wait_for(qapp, lambda: window.job is None) and not window.progress_timer.isActive()


def test_the_intro_covers_the_window_before_it_shows(world, qapp):
    # The page showed first, then the intro faded in over it (owner, 28-10-2026): now its first frame is the intro's.
    window = mw.MainWindow(world.entries, world.sources, world.records, intro_ms=60_000,
                           gamepad=Gamepad(source_factory=FakePad), battery=lambda: None)
    world.windows.append(window)
    assert window.intro is not None and window.intro.isVisibleTo(window)
    portable.scale((1280, 720))
    window.resize(1280, 720)
    window.show()
    qapp.processEvents()
    assert window.intro.geometry() == window.rect()
    frame = window.grab().toImage()
    assert frame.pixelColor(640, 600).name() == portable.BACKGROUND        # dark where the tiles are, before start()


def test_a_tab_with_more_apps_than_a_page_has_pages(world, qapp, monkeypatch):
    """A ninth app in a tab (owner's roadmap, 04-11-2026: it was cut off): a second page, the marker under the tiles,
    the d-pad past the tiles' right or left edge turns the page, a tap on the marker turns it too."""
    gaming = world.entries[1]
    world.entries = [replace(gaming, key=f"g{i}", name=f"Game {i}", short=f"G{i}") for i in range(9)]
    window = world.make()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    shown = lambda: [key for key, tile in window.page_tiles() if tile.isVisible()]     # noqa: E731
    assert shown() == [f"g{i}" for i in range(8)] and not window.tiles["g8"].isVisible()
    assert window.page_marker.isVisible() and window.page_marker.text() == "Page 1 of 2"
    window.tiles["g3"].setFocus()                       # the first row's last tile
    window.on_action("right")                           # past the edge: the next page, its only tile
    assert shown() == ["g8"] and window.tiles["g8"].hasFocus() and window.current_key == "g8"
    assert window.page_marker.text() == "Page 2 of 2"
    window.on_action("right")                           # the last page: nothing further
    assert window.page == 1 and window.tiles["g8"].hasFocus()
    window.on_action("left")                            # back: the first row's last tile
    assert window.page == 0 and window.tiles["g3"].hasFocus()
    window.tiles["g4"].setFocus()
    window.on_action("left")                            # the first page: nothing before it
    assert window.page == 0 and window.tiles["g4"].hasFocus()
    window.on_action("right")                           # inside the page the d-pad moves as before
    assert window.page == 0 and window.tiles["g5"].hasFocus()
    window.page_marker.pressed.emit()                   # a tap: the next page
    window.page_marker.pressed.emit()                   # and from the last back to the first
    assert window.page == 0 and window.tiles["g0"].hasFocus()


def test_a_tab_that_fits_one_page_has_no_marker(world, qapp):
    window = world.make()
    assert not window.page_marker.isVisible() and window.pages() == 1
    assert not window.turn_page(1) and window.page == 0


def test_exit_during_a_download_asks_first(world, qapp, monkeypatch):
    # B closed the portal and dropped the download at once (owner, 28-10-2026: ask first); View exits now (29-10-2026).
    import threading
    release = threading.Event()
    first = world.sources.download

    def slow(url: str, dest: Path) -> None:
        if url.endswith(".zip"):
            release.wait(10)
        first(url, dest)
    monkeypatch.setattr(world.sources, "download", slow)
    window = world.make()
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("accept")
    assert wait_for(qapp, lambda: window.job is not None)
    window.on_action("view")
    assert closed == [] and window.legend.items == mw.EXIT_ANSWERS
    assert window.app_pane.status.text() == "Do you really want to exit the portal? The download stops."
    window._confirm_over()                              # five seconds without a second press
    assert ("X", "Details") in window.legend.items and not window.close_asked
    window.on_action("view")
    window.on_action("view")
    assert closed == [True]
    release.set()
    assert wait_for(qapp, lambda: window.job is None)
    window._confirm_over()                              # the window stays (close is a stand-in): a new question
    window.on_action("view")                            # the installer runs in its window: the question says so
    assert closed == [True] and window.app_pane.status.text() == ("Do you really want to exit the portal? The "
                                                                  "installer finishes in its window, unrecorded.")
    window.on_action("view")
    assert closed == [True, True]


def test_the_suite_page_switches_the_wallpaper(world, qapp, monkeypatch):
    # The wallpaper is a setting (owner, 28-10-2026: "a feature you can toggle, so a settings menu"), on the Suite
    # page since View became Exit (owner, 29-10-2026).
    from bc250_core import portable
    window = world.make()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert window.wallpaper_on and portable.glass() == portable.GLASS
    window.on_action("menu")
    assert window.stack.currentWidget() is window.suite_pane
    window.suite_pane.wallpaper.setFocus()
    assert window.suite_pane.wallpaper.label.text() == "Wallpaper: Built-in"
    assert window.legend.items == [("A", "Change"), ("Y", "Check again"), portable.KEYBOARD, (MENU, "Info"), ("B", "Back"),
                                   (VIEW, "Exit")]
    window.on_action("menu")                                          # on the page: what the settings do
    assert window.popup is not None and "Transparency: how much" in window.suite_pane.info.info
    window.on_action("back")
    assert window.popup is None and window.stack.currentWidget() is window.suite_pane
    window.on_action("accept")                                        # Built-in, without a picture of the user's
    assert not window.wallpaper_on and portable.glass() == 255 and window.suite_pane.wallpaper.label.text() == "Wallpaper: Off"
    assert "rgba" not in window.app_pane.styleSheet()                 # the strip solid again, at once
    assert not portable.wallpaper_on(mw.SUITE)                         # the suite's: every app (owner, 29-10-2026)
    window.on_action("back")
    assert window.stack.currentWidget() is window.apps_page
    again = world.make()                                              # kept for the next start
    assert not again.wallpaper_on and portable.glass() == 255
    again.next_wallpaper()
    assert again.wallpaper_on and portable.glass() == portable.GLASS and "rgba" in again.app_pane.styleSheet()


def test_a_wallpaper_dropped_in_the_folder_and_its_transparency(world, qapp):
    """Which wallpaper (owner, 30-10-2026): only pictures dropped in the suite's wallpaper folder, by the rules; A
    steps Off, Built-in, then each one; the Transparency row steps the veil over it by 10 %, from 90 % to 0."""
    from PyQt6.QtGui import QColor, QImage

    from bc250_core import portable
    folder = portable.wallpaper_folder(mw.SUITE)
    folder.mkdir(parents=True)
    for name, width, height in (("galaga.png", 2560, 1440), ("small.png", 800, 450), ("tall.png", 1440, 2560)):
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(QColor("#123456"))
        image.save(str(folder / name))
    (folder / "notes.txt").write_text("x", encoding="utf-8")
    window = world.make()
    window.on_action("menu")
    pane = window.suite_pane
    assert pane.wallpaper.label.text() == "Wallpaper: Built-in" and pane.transparency.label.text() == "Transparency: 59 %"
    text = pane.info.info                                            # behind the information icon (owner, 30-10-2026)
    assert r"%LOCALAPPDATA%\windows-portable-suite\wallpapers" in text
    assert "small.png (800 x 450, smaller than 1280 x 720)" in text and "tall.png (1440 x 2560, not wider than high)" in text
    assert "notes.txt (not a PNG, JPEG or WebP picture)" in text
    window.next_wallpaper()
    assert pane.wallpaper.label.text() == "Wallpaper: galaga" and window.wallpaper.width() == 2560
    assert portable.wallpaper_picture(mw.SUITE) == folder / "galaga.png"   # the suite's: every app's next start
    window.next_wallpaper()
    assert pane.wallpaper.label.text() == "Wallpaper: Off" and not window.wallpaper_on
    window.next_wallpaper()
    assert pane.wallpaper.label.text() == "Wallpaper: Built-in" and window.wallpaper_on
    assert portable.wallpaper_picture(mw.SUITE, None) is None
    window.next_wallpaper()
    assert world.make().wallpaper.width() == 2560                        # kept for the next start
    (folder / "galaga.png").unlink()                                   # taken away: the suite's own again
    assert world.make().wallpaper.width() != 2560 and portable.wallpaper_picture(mw.SUITE) == portable.WALLPAPER
    assert window.shade == portable.SHADE
    steps = []
    for _ in range(5):
        window.next_transparency()
        steps.append(pane.transparency.label.text().removeprefix("Transparency: "))
    assert steps == ["60 %", "70 %", "80 %", "90 %", "0 %"] and window.shade == 0
    window.next_transparency()
    assert window.shade == portable.shade(10) == 26 and world.make().shade == 26


def test_portal_1_6_0s_wallpaper_switch_becomes_the_suites(world, qapp):
    from PyQt6.QtCore import QSettings

    from bc250_core import portable
    QSettings().setValue(mw.WALLPAPER_KEY, "false")                   # switched off in portal 1.6.0
    window = world.make()
    assert not window.wallpaper_on and not portable.wallpaper_on(mw.SUITE)
    assert not QSettings().contains(mw.WALLPAPER_KEY)


def test_a_tile_has_a_red_dot_only_while_an_update_is_out(world, qapp):
    window = world.make()
    assert not any(tile.dot for tile in window.tiles.values())       # nothing installed
    world.records.set("test", "wp-test-v0.0.9")
    window.refresh()
    assert not window.tiles["test"].dot                               # recorded, but its program is not there
    app = Path(os.environ["LOCALAPPDATA"]) / "windows-portable-suite" / "windows-portable-test" / "app"
    app.mkdir(parents=True, exist_ok=True)
    (app / "X.exe").write_bytes(b"")
    window.refresh()
    assert window.tiles["test"].dot
    world.records.set("test", "wp-test-v0.1.0")                       # updated
    window.refresh()
    assert not window.tiles["test"].dot


def test_the_sound_is_on_again_after_windows_restarts(world, qapp):
    """Sound: Off holds until Windows starts again (owner, 07-11-2026: "on reboot it should return to default"): kept
    for every start of the portal till then, On at the first start after it, also one switched off by a portal that
    did not keep the time."""
    window = world.make(booted=lambda: 1000.0)
    window.toggle_sound()                                             # Off, now
    assert not portable.sound_on(mw.SUITE)
    world.make(booted=lambda: 1000.0)                                 # started again, Windows not restarted
    assert not portable.sound_on(mw.SUITE)
    again = world.make(booted=lambda: time.time() + 60)               # Windows started after it
    assert portable.sound_on(mw.SUITE) and again.suite_pane.sound.label.text() == "Sound: On"
    assert portable.look_settings(mw.SUITE).value(mw.SOUND_OFF_KEY) is None
    portable.set_sound_on(mw.SUITE, False)                            # Off from portal 9.0.0: no time kept
    world.make(booted=lambda: 1000.0)
    assert portable.sound_on(mw.SUITE)
    window.toggle_sound()
    window.toggle_sound()                                             # Off and On again: no time left behind
    assert portable.look_settings(mw.SUITE).value(mw.SOUND_OFF_KEY) is None


def test_a_change_of_where_windows_plays_the_sound_is_said(world, qapp):
    """Every change of Windows' default sound output is said in a Windows notification (owner, 07-11-2026: a TV
    switched to another input kept the sound; it moved to the handheld only when its screen turned off), by kind,
    never a device's name; the first read only notes it, and Core Audio without an answer changes nothing."""
    world.sound = "screen"
    window = world.make()
    window.watch_sound()                                              # the portal starts: nothing to say
    window.watch_sound()
    assert world.notices == []
    world.sound = "speakers"                                          # the handheld's screen turned off
    window.watch_sound()
    window.watch_sound()
    assert world.notices == ["Sound plays on: PC speakers"]
    world.sound = "screen"                                            # woken: the TV has the sound again
    window.watch_sound()
    world.sound = None
    window.watch_sound()
    assert world.notices[1:] == ["Sound plays on: Other screen", "Windows has no sound output now."]

    def no_answer():
        raise OSError("Core Audio does not answer")
    window.sound_kind = no_answer
    window.watch_sound()
    window.watch_sound()
    assert len(world.notices) == 3 and window.sound_where is None
    window.close()
    assert not window.sound_timer.isActive() and not window.tray_timer.isActive()


def test_the_suite_page_switches_the_sound(world, qapp, monkeypatch):
    """Suite settings: sound off (owner, 29-10-2026): the intro plays no sound at the next start."""
    from bc250_core import portable
    window = world.make()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("menu")
    assert window.suite_pane.wallpaper.hasFocus() and window.suite_pane.sound.label.text() == "Sound: On"
    window.on_action("down")
    assert window.suite_pane.transparency.hasFocus()                  # the wallpaper's (30-10-2026), then the sound
    window.on_action("down")
    assert window.suite_pane.sound.hasFocus() and ("A", "Change") in window.legend.items
    window.on_action("accept")
    assert window.suite_pane.sound.label.text() == "Sound: Off" and not portable.sound_on(mw.SUITE)
    assert window.wallpaper_on                                        # the other row unchanged
    intro = lambda: [wav for wav in world.played if wav == mw.INTRO_SOUND]   # noqa: E731 (not the buttons' sound)
    silent = world.make(intro_ms=60_000)
    assert intro() == [] and silent.intro is not None                 # the intro plays, silent
    silent.toggle_sound()
    assert portable.sound_on(mw.SUITE)
    world.make(intro_ms=60_000)
    assert len(intro()) == 1


def test_the_chip_is_read_through_cores_chip_and_closed_with_the_window(world, qapp, monkeypatch):
    """The CPU's and the GPU's load and temperature (owner, 30-10-2026): AMD's driver opened once, read each STATUS_MS,
    closed with the window."""
    from bc250_core import chip
    opened = []

    class Sensors:
        def __init__(self):
            opened.append(self)
            self.closed = False

        def read(self):
            return 51, 49

        def gpu_load(self):
            return 33

        def close(self):
            self.closed = True
    monkeypatch.setattr(chip, "Temperatures", Sensors)
    monkeypatch.setattr(chip, "CpuLoad", lambda: type("Load", (), {"read": lambda self: 9})())
    window = world.make(chip_parts=None)
    window.update_status()
    assert "CPU 9% 51°  |  GPU 33% 49°" in window.header.second.text() and len(opened) == 1
    window.close()
    assert opened[0].closed


def test_the_screen_row_moves_the_portal_to_the_next_screen(world, qapp, monkeypatch):
    """With a second screen (owner, 31-10-2026: a TV over the Ally), the Screen row moves the portal there; core's
    window starts it again, sized for it, once no download or install runs."""
    window = world.make()
    window.on_action("menu")
    assert not window.suite_pane.screen_row.isVisible()             # one screen
    here = window.screen()
    other = OtherScreen()
    monkeypatch.setattr(portable.platform, "built_in_screens", lambda: [(here.geometry().x(), here.geometry().y())])
    monkeypatch.setattr(mw.QGuiApplication, "screens", staticmethod(lambda: [here, other]))
    moves = []
    monkeypatch.setattr(window, "move_to", moves.append)
    window.show_suite(window.suite_pane.wallpaper)
    row = window.suite_pane.screen_row
    assert row.isVisible() and row.label.text() == f"Screen: {portable.screen_label(here)}"
    assert "Screen: the screen the portal is on" in window.suite_pane.info.info
    row.activated.emit()
    assert moves == [other]
    assert window.can_restart()
    window.job = (world.entries[1], "install")                       # a download: it waits, and says so
    assert not window.can_restart()
    window.waiting_to_move()
    assert window.message.startswith("The portal moves to the other screen once")
    window.job = None


class OtherScreen:
    """A second screen, a TV or a monitor, beside the device's own."""
    def name(self):
        return "any name"

    def geometry(self):
        from PyQt6.QtCore import QRect
        return QRect(5000, 0, 1920, 1080)


def test_the_screen_row_follows_a_move_by_the_keyboard(world, qapp, monkeypatch):
    """Moved by Win + Shift + an arrow to a screen of the same size, the portal does not start again: the Screen row
    says the screen it is on now (owner, 01-11-2026: moved back, it still named the other one), PC screen or Other
    screen, never a screen's name (owner, 07-11-2026)."""
    window = world.make()
    here = window.screen()
    other = OtherScreen()
    monkeypatch.setattr(portable.platform, "built_in_screens", lambda: [(here.geometry().x(), here.geometry().y())])
    monkeypatch.setattr(mw.QGuiApplication, "screens", staticmethod(lambda: [here, other]))
    monkeypatch.setattr(window, "move_to", lambda screen: None)
    monkeypatch.setattr(window, "screen", lambda: other)
    window.show_suite(window.suite_pane.wallpaper)
    row = window.suite_pane.screen_row
    assert row.label.text() == "Screen: Other screen"
    monkeypatch.setattr(window, "screen", lambda: here)            # Win + Shift + an arrow
    window.screen_moved(here)
    assert row.label.text() == "Screen: PC screen"
    window.close()


def test_lt_moves_the_portal_with_a_second_screen(world, qapp, monkeypatch):
    """LT is the Screen row's A on every page (owner, 31-10-2026), in the legend with a second screen only, which
    then also shows the keyboard's Win + Shift + an arrow at its left, as key caps."""
    window = world.make()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    moves = []
    monkeypatch.setattr(window, "move_to", moves.append)
    assert ("LT", "Screen") not in window.legend.items and window.legend.hint is None
    window.on_action("lt")                                          # one screen: nothing moves, the line says why
    assert moves == [] and window.message == mw.ONE_SCREEN
    here = window.screen()
    other = OtherScreen()
    monkeypatch.setattr(portable.platform, "built_in_screens", lambda: [(here.geometry().x(), here.geometry().y())])
    monkeypatch.setattr(mw.QGuiApplication, "screens", staticmethod(lambda: [here, other]))
    window.screens_changed()                                        # a TV attached
    items = window.legend.items
    assert ("LT", "Screen") in items and items.index(("LT", "Screen")) < items.index((VIEW, "Exit"))
    assert window.legend.keys == (mw.SCREEN_KEYS[0], tuple(mw.SCREEN_KEYS[1]))
    assert [cap.text() for cap in window.legend.hint.caps] == [portable.WINDOWS_KEY, "Shift", "←", "→"]
    window.on_action("lt")
    assert moves == [other]
    window.legend._tapped("LT")                                     # a tap on the entry does the same
    assert len(moves) == 2
    window.on_action("menu")                                        # on the Settings page too
    assert ("LT", "Screen") in window.legend.items and window.legend.hint is not None
    window.on_action("lt")
    assert len(moves) == 3
    left, _, right, _ = window.margins()
    window.on_back()                                                # the widest row: a tile's, with Y and RT
    window.steam_here = lambda: True
    window.app_pane.other = "Update"
    window.update_legend()
    assert ("Y", "Update") in window.legend.items and ("RT", "Steam") in window.legend.items
    window.show()                                                   # laid out as on the screen
    qapp.processEvents()
    assert 1000 < window.legend.sizeHint().width() <= 1280 - left - right  # it fits the Ally's 1280 x 720
    window.show_suite()                                             # the Settings page: R3 Keyboard too
    window.suite_pane.action = "Check again"
    window.update_legend()
    assert portable.KEYBOARD in window.legend.items and ("Y", "Check again") in window.legend.items
    qapp.processEvents()
    assert 1000 < window.legend.sizeHint().width() <= 1280 - left - right
    window.close()


def test_the_settings_lie_in_three_columns(world, qapp, monkeypatch):
    """Owner, 06-11-2026 and 07-11-2026: the rows lay too close, the focused one's edge was cut off (also by the line
    under them). Three columns of at most five rows, Look and device, Clock and weather, Screens, with the Ally X's
    Performance mode, a second screen and a two-line message all shown: every row whole, apart, above the message;
    the d-pad goes down a column and across between them."""
    from portable_portal import operating_mode as om
    from test_operating_mode import FakeApi
    turbo = om.BY_LETTER["T"]
    window = world.make(modes=lambda: FakeApi(turbo.plan, turbo.overlay))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.resize(1280, 720)
    window.show()
    qapp.processEvents()
    window.on_action("menu")
    pane = window.suite_pane
    pane.set_screen("Other screen")
    window.say("", mw.SWITCHED_MODE)                    # two lines under the rows
    qapp.processEvents()
    columns = [[pane.wallpaper, pane.transparency, pane.sound, pane.mode, pane.xbox_mode],
               [pane.hours, pane.seconds, pane.zone, pane.place],
               [pane.handheld, pane.both, pane.extend, pane.tv, pane.screen_row]]
    lefts = []
    for rows in columns:
        assert all(row.isVisible() for row in rows)
        assert len({row.mapTo(window, row.rect().topLeft()).x() for row in rows}) == 1
        lefts.append(rows[0].mapTo(window, rows[0].rect().topLeft()).x())
        tops = [row.mapTo(window, row.rect().topLeft()).y() for row in rows]
        assert all(b - a > row.height() for a, b, row in zip(tops, tops[1:], rows))   # apart: no edge cut off
        assert all(row.height() == portable.px(portable.ROW_HEIGHT) for row in rows)
        last = rows[-1]
        assert last.mapTo(window, last.rect().bottomLeft()).y() < pane.status.mapTo(window, pane.status.rect().topLeft()).y()
    assert lefts == sorted(lefts) and len(set(lefts)) == 3
    status = pane.status.mapTo(window, pane.status.rect().bottomLeft()).y()
    assert status <= pane.mapTo(window, pane.rect().bottomLeft()).y()
    pane.wallpaper.setFocus()
    for _ in range(4):
        window.on_action("down")
    assert pane.xbox_mode.hasFocus()
    window.on_action("right")
    assert window.focusWidget() in columns[1]                        # across to the next column
    window.on_action("right")
    assert window.focusWidget() in columns[2]
    window.close()


def test_the_clock_rows_change_the_clock_at_the_top(world, qapp, monkeypatch):
    """Clock 24 or 12 hours, Seconds, Time zone CET (Amsterdam time) or UTC (owner, 06-11-2026): the time at the top
    follows at once, and the choice is kept for the next start."""
    window = world.make()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("menu")
    pane = window.suite_pane
    assert pane.hours.label.text() == "Clock: 24 hours" and pane.zone.label.text() == "Time zone: CET"
    window.update_status()
    assert window.header.status.text().split("  |  ")[1].endswith((" CET", " CEST"))
    pane.hours.activated.emit()
    pane.seconds.activated.emit()
    pane.zone.activated.emit()
    assert (pane.hours.label.text(), pane.seconds.label.text(), pane.zone.label.text()) == \
        ("Clock: 12 hours", "Seconds: On", "Time zone: UTC")
    time_part = window.header.status.text().split("  |  ")[1]
    assert time_part.endswith((" AM UTC", " PM UTC")) and time_part.count(":") == 2
    again = world.make()
    assert again.clock == window.clock and 0 < again.status_ms() <= 1020   # kept; with seconds, on each second


def test_the_location_page_finds_a_place_and_its_weather_shows_at_the_top(world, qapp, monkeypatch):
    """Location (owner, 06-11-2026): part of the name, A searches Open-Meteo's places, A takes one; its weather symbol
    and temperature show before the date. Y goes to the list, where Off takes the place away again."""
    asked = []

    def fetch(url):
        asked.append(url)
        if "geocoding" in url:
            return {"results": [{"name": "Amsterdam", "latitude": 52.37, "longitude": 4.89, "country": "Netherlands",
                                 "admin1": "North Holland"},
                                {"name": "Amstelveen", "latitude": 52.30, "longitude": 4.86,
                                 "country": "Netherlands", "admin1": "North Holland"}]}
        return {"current": {"temperature_2m": 8.6, "weather_code": 3, "is_day": 1}}
    window = world.make(weather_fetch=fetch)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("menu")
    window.suite_pane.place.activated.emit()
    pane = window.place_pane
    assert window.stack.currentWidget() is pane and pane.field.hasFocus() and ("A", "Search") in window.legend.items
    pane.field.setText("Amst")
    window.on_action("accept")
    assert wait_for(qapp, lambda: pane.rows[0].isVisible())
    assert pane.rows[0].label.text() == "Amsterdam, North Holland, Netherlands" and pane.rows[0].hasFocus()
    assert pane.rows[1].isVisible() and not pane.rows[2].isVisible() and ("A", "Take") in window.legend.items
    window.on_action("accept")
    assert window.stack.currentWidget() is window.suite_pane and window.suite_pane.place.hasFocus()
    assert window.suite_pane.place.label.text() == "Location: Amsterdam"
    assert wait_for(qapp, lambda: window.header.status.text().startswith("Amsterdam ☁ 9°  |  "))
    from portable_portal import weather
    assert weather.place(mw.SUITE) == window.place                   # kept for the next start
    window.suite_pane.place.activated.emit()
    window.on_action("y")                                            # from the field to the list: Off
    assert pane.off.hasFocus() and ("Y", "Search") in window.legend.items
    window.on_action("accept")
    assert window.place is None and window.suite_pane.place.label.text() == "Location: Off"
    assert not window.header.status.text().startswith("Amsterdam")
    window.on_action("b")
    assert len([url for url in asked if "geocoding" in url]) == 1


def test_a_search_without_a_connection_says_so(world, qapp, monkeypatch):
    def fetch(url):
        raise OSError("no route to host")
    window = world.make(weather_fetch=fetch)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.show_place()
    window.place_pane.field.setText("A")
    window.on_action("accept")
    assert window.place_pane.status.text().startswith("Type at least two letters")
    window.place_pane.field.setText("Amsterdam")
    window.on_action("accept")
    assert wait_for(qapp, lambda: "could not be reached" in window.place_pane.status.text())
    assert window.place_pane.field.text() == "Amsterdam" and window.place is None
