# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py): the tabs and tiles, what the strip says for an app in each state, an install (the
release fetched in the background, the installer's PowerShell window, its exit status), opening an app, the details
page with Remove's second press, the Suite page with the portal's own update, and B."""

from __future__ import annotations

import hashlib
import os
import shutil
import time
import zipfile
from pathlib import Path

import pytest
from bc250_core import portable
from bc250_core.platform import private
from bc250_core.portable import VIEW
from bc250_core.gamepad import Gamepad
from bc250_core.updates import ReleaseInfo

from portable_portal import main_window as mw
from portable_portal.manifest import AppEntry
from portable_portal.portal_update import AppChange, PortalUpdate
from portable_portal.sources import Records, Sources


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
    for tag in ("wp-test-v0.1.0", "wp-pcsx2-v0.2.0", "wp-portal-v9.9.9"):
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
    w.update = PortalUpdate(ReleaseInfo(version="9.9.9", tag="wp-portal-v9.9.9", published="2030-01-01"),
                            [AppChange("Windows Portable Test", "0.1.0", "0.2.0")])
    w.windows = []

    def make(portal_check=None, **kwargs):
        pad = FakePad()
        kwargs.setdefault("intro_ms", 0)                # the intro has its own tests
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
    assert window.header.status.text().startswith("82%  |  ")
    assert [text for _, text in window.legend.items][1:] == ["Details", "Suite", "Exit app"]
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


def test_x_shows_the_details_and_remove_takes_a_second_press(world, qapp):
    world.app_dir.mkdir(parents=True)
    (world.app_dir / "X.exe").write_bytes(b"x")
    world.records.set("test", "wp-test-v0.1.0")
    window = world.make()
    window.on_action("x")
    assert window.stack.currentWidget() is window.details_pane
    assert window.legend.items == [("A", "Open"), ("Y", "Remove"), ("B", "Back"), (VIEW, "Exit app")]
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
    on a tile does nothing; View (Exit app) closes the portal, a tap on its entry too."""
    window = world.make()
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.on_action("menu")
    assert window.stack.currentWidget() is window.suite_pane and window.suite_pane.wallpaper.hasFocus()
    window.on_action("back")
    assert window.stack.currentWidget() is window.apps_page and window.tiles["test"].hasFocus() and closed == []
    window.on_action("back")                            # on a tile: nothing
    assert closed == [] and window.tiles["test"].hasFocus()
    window.legend.entries[VIEW].pressed.emit()
    assert closed == [True]


def test_the_suite_page_offers_the_portals_own_update_and_installs_it(world, qapp, monkeypatch):
    window = world.make(portal_check=lambda: world.update, exe=r"C:\portal\Windows-Portable-Suite.exe")
    assert wait_for(qapp, lambda: window.update is not None)
    assert "Suite 9.9.9 available" in window.header.status.text()
    window.show_suite()
    rows = {window.suite_pane.grid.itemAt(i).widget().text(): window.suite_pane.grid.itemAt(i + 1).widget().text()
            for i in range(0, window.suite_pane.grid.count(), 2)}
    assert rows["This portal"] == mw.__version__ and rows["Newest release"] == "9.9.9, 2030-01-01"
    assert rows["It brings"] == "updates Test" and rows[""] == "Windows Portable Test: 0.1.0 → 0.2.0"
    assert ("Y", "Update to 9.9.9") in window.legend.items           # A switches the setting, Y updates
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.on_action("y")
    assert wait_for(qapp, lambda: closed == [True])
    line = world.terminal.lines[0]
    folder = world.sources.work.parent / "portal-update" / "wp-portal-v9.9.9"
    assert (folder / "install.ps1").is_file()
    assert line.startswith("Wait-Process -Id ") and f"Set-Location -LiteralPath '{folder}'" in line
    assert "-File install.ps1" in line and line.endswith("Start-Process -FilePath 'C:\\portal\\Windows-Portable-Suite.exe'")
    assert world.terminal.exit_files == [None]


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
    assert window.suite_pane.grid.itemAt(3).widget().text() == "not known: no connection (offline)"


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
    played = []
    monkeypatch.setattr("portable_portal.intro.play", played.append)
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
    assert closed == [] and window.legend.items == [(VIEW, "Press again to exit")]
    assert window.app_pane.status.text() == "Press View again to exit the portal: the download stops."
    window._confirm_over()                              # five seconds without a second press
    assert ("X", "Details") in window.legend.items and not window.close_asked
    window.on_action("view")
    window.on_action("view")
    assert closed == [True]
    release.set()
    assert wait_for(qapp, lambda: window.job is None)
    window.on_action("view")                            # nothing runs: View exits at once
    assert closed == [True, True]


def test_the_suite_page_switches_the_wallpaper(world, qapp, monkeypatch):
    # The wallpaper is a setting (owner, 28-10-2026: "a feature you can toggle, so a settings menu"), on the Suite
    # page since View became Exit app (owner, 29-10-2026).
    from bc250_core import portable
    window = world.make()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    assert window.wallpaper_on and portable.glass() == portable.GLASS
    window.on_action("menu")
    assert window.stack.currentWidget() is window.suite_pane
    window.suite_pane.wallpaper.setFocus()
    assert window.suite_pane.wallpaper.label.text() == "Wallpaper: On"
    assert window.legend.items == [("A", "Change"), ("Y", "Check again"), ("B", "Back"), (VIEW, "Exit app")]
    window.on_action("accept")
    assert not window.wallpaper_on and portable.glass() == 255 and window.suite_pane.wallpaper.label.text() == "Wallpaper: Off"
    assert "rgba" not in window.app_pane.styleSheet()                 # the strip solid again, at once
    assert not portable.wallpaper_on(mw.SUITE)                         # the suite's: every app (owner, 29-10-2026)
    window.on_action("back")
    assert window.stack.currentWidget() is window.apps_page
    again = world.make()                                              # kept for the next start
    assert not again.wallpaper_on and portable.glass() == 255
    again.toggle_wallpaper()
    assert again.wallpaper_on and portable.glass() == portable.GLASS and "rgba" in again.app_pane.styleSheet()


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


def test_the_suite_page_switches_the_sound(world, qapp, monkeypatch):
    """Suite settings: sound off (owner, 29-10-2026): the intro plays no sound at the next start."""
    from bc250_core import portable
    played = []
    monkeypatch.setattr("portable_portal.intro.play", played.append)
    window = world.make()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("menu")
    assert window.suite_pane.wallpaper.hasFocus() and window.suite_pane.sound.label.text() == "Sound: On"
    window.on_action("down")
    assert window.suite_pane.sound.hasFocus() and ("A", "Change") in window.legend.items
    window.on_action("accept")
    assert window.suite_pane.sound.label.text() == "Sound: Off" and not portable.sound_on(mw.SUITE)
    assert window.wallpaper_on                                        # the other row unchanged
    silent = world.make(intro_ms=60_000)
    assert played == [] and silent.intro is not None                  # the intro plays, silent
    silent.toggle_sound()
    assert portable.sound_on(mw.SUITE)
    world.make(intro_ms=60_000)
    assert len(played) == 1 and played[0].name == "intro.wav"
