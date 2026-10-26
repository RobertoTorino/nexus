# SPDX-License-Identifier: GPL-3.0-or-later
"""The window on a home made in a temp folder, with a fake service, a fake root part and a fake download: the states
before and after installing, a Decky that updated itself, a newer release, the plugins in the table, installing
through the worker, removing, Steam's switch, the /home/deck link and Game Mode."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest

from conftest import make_plugin

from bc250_core.updates import ReleaseInfo
from decky_manager import loader, privileged, state, style
from decky_manager.main_window import MainWindow

BINARY = b"\x7fELF decky"


class FakeSystem:
    """systemctl and the root part, on the temp folder: installing writes what loader.install writes."""

    def __init__(self, paths: loader.Paths, running: bool = True):
        self.paths = paths
        self.running = running
        self.calls: list[list[str]] = []
        self.seen_download = False

    def run(self, argv: list[str]) -> tuple[int, str]:
        if argv[0] == "journalctl":
            return 0, "Decky's log\n"
        unit = self.paths.unit.is_file()
        if argv[1] == "is-enabled":
            return (0, "enabled\n") if unit else (1, "not-found\n")
        return (0, "active\n") if unit and self.running else (3, "inactive\n")

    def root(self, args: list[str]) -> privileged.Result:
        self.calls.append(args)
        if args[0] == "install":
            self.seen_download = Path(args[1]).read_bytes() == BINARY
            install(self.paths)
            return privileged.Result(True, "Decky Loader 3.3.0 is installed and running.")
        if args[0] == "remove":
            self.paths.unit.unlink()
            self.paths.binary.unlink()
            return privileged.Result(True, "Decky Loader is removed.")
        if args[0] == "link":
            self.paths.deck.symlink_to(self.paths.home)
        return privileged.Result(True, f"{args[0]} done.")


def install(paths: loader.Paths, version: str = loader.TAG) -> None:
    paths.services.mkdir(parents=True, exist_ok=True)
    paths.binary.write_bytes(BINARY)
    paths.version_file.write_text(version + "\n")
    paths.unit.parent.mkdir(parents=True, exist_ok=True)
    paths.unit.write_text(loader.unit_text(paths.homebrew))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "SHA256", hashlib.sha256(BINARY).hexdigest())
    home = tmp_path / "home"
    home.mkdir()
    paths = loader.Paths(home, etc=tmp_path / "etc", deck=tmp_path / "deck")
    steam_dir = home / ".local/share/Steam"
    steam_dir.mkdir(parents=True)
    return paths, FakeSystem(paths), [steam_dir], tmp_path / "download"


def _window(setup, latest=ReleaseInfo, fetch=None) -> MainWindow:
    paths, system, steam_dirs, download_dir = setup

    def fake_fetch(url: str, dest: Path, progress=None) -> None:
        dest.write_bytes(BINARY)
    window = MainWindow(paths, steam_dirs, run=system.run, root=system.root, fetch=fetch or fake_fetch,
                        latest=latest, download_dir=download_dir)
    _wait(window)
    return window


def _wait(window) -> None:
    from PyQt6.QtWidgets import QApplication
    deadline = time.monotonic() + 10
    while (window.worker.running or window.checker.running) and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    QApplication.processEvents()


def test_before_installing(qapp, setup):
    window = _window(setup)
    assert window.pill.text() == "Not installed"
    assert window.install_button.isEnabled() and window.install_button.text() == "Install"
    assert not window.remove_button.isEnabled() and not window.restart_button.isEnabled()
    assert "Not installed" in window.decky_state.text() and window.decky_box.value.text() == "—"
    assert window.steam_box.value.text() == "Off" and window.steam_button.text() == "Switch on"
    assert window.deck_button.text() == "Link" and window.deck_button.isEnabled()
    assert window.table.rowCount() == 0 and not window.folder_button.isEnabled()


def test_installed_and_running_with_plugins(qapp, setup):
    paths, _system, steam_dirs, _download = setup
    install(paths)
    state.enable_cef(steam_dirs)
    make_plugin(paths.plugins, "SDH-CssLoader", "CSS Loader", "2.1.2", "DeckThemes")
    window = _window(setup)
    assert window.pill.text() == "Ready" and window.decky_box.value.text() == "3.3.0"
    assert "Running as root; starts at boot." == window.service_state.text()
    assert not window.install_button.isEnabled() and window.remove_button.isEnabled()
    assert window.restart_button.isEnabled() and window.steam_box.value.text() == "On"
    assert window.table.rowCount() == 1 and window.table.item(0, 0).text() == "CSS Loader"
    assert window.table.item(0, 3).text() == "On" and window.plugins_box.value.text() == "1"


def test_not_running_without_the_switch_or_without_steam(qapp, setup):
    paths, system, _steam_dirs, download = setup
    install(paths)
    system.running = False
    window = _window(setup)
    assert window.pill.text() == "Not running" and "Not running" in window.service_state.text()
    system.running = True
    window.refresh()
    assert window.pill.text() == "Steam switch off"
    window = _window((paths, system, [], download))
    assert window.pill.text() == "Ready" and "never started" in window.steam_state.text()
    assert not window.steam_button.isEnabled()


def test_older_newer_and_unknown_versions(qapp, setup):
    paths = setup[0]
    install(paths, "v3.2.8")
    window = _window(setup)
    assert window.install_button.text() == "Update" and window.install_button.isEnabled()
    assert "brings 3.3.0" in window.decky_state.text()
    install(paths, "v3.4.0")                                 # Decky updated itself
    window.refresh()
    assert "updated itself" in window.decky_state.text() and window.install_button.text() == "Install"
    paths.version_file.unlink()
    window.refresh()
    assert window.decky_box.value.text() == "unknown" and window.install_button.isEnabled()


def test_a_newer_release_is_named(qapp, setup):
    window = _window(setup, latest=lambda: ReleaseInfo(version="3.4.0", tag="v3.4.0", published="2026-12-01"))
    assert "Decky Loader 3.4.0 is out (2026-12-01)" in window.decky_state.text()
    window = _window(setup, latest=lambda: ReleaseInfo(version="3.3.0"))
    assert "is out" not in window.decky_state.text()
    window = _window(setup, latest=lambda: ReleaseInfo(error="no connection"))
    assert "is out" not in window.decky_state.text()


def test_install_downloads_checks_and_runs_the_root_part(qapp, setup, monkeypatch):
    paths, system, steam_dirs, download = setup
    window = _window(setup)
    monkeypatch.setattr(window, "_ask", lambda title, text: True)
    window.on_install()
    _wait(window)
    assert system.calls == [["install", str(download / "PluginLoader")]] and system.seen_download
    assert not (download / "PluginLoader").exists()            # the download goes once it is installed
    assert state.cef_enabled(steam_dirs)
    assert window.pill.text() == "Ready" and "Ctrl + 2" in window.running.text()


def test_a_different_download_never_reaches_the_root_part(qapp, setup, monkeypatch):
    paths, system, steam_dirs, download = setup
    window = _window(setup, fetch=lambda url, dest, progress=None: dest.write_bytes(b"other"))
    monkeypatch.setattr(window, "_ask", lambda title, text: True)
    window.on_install()
    _wait(window)
    assert system.calls == [] and "SHA-256 differs" in window.running.text()
    assert not (download / "PluginLoader").exists() and not state.cef_enabled(steam_dirs)

    def offline(url, dest, progress=None):
        import urllib.error
        raise urllib.error.URLError("Name or service not known")
    window.fetch = offline
    window.on_install()
    _wait(window)
    assert system.calls == [] and "download failed: Name or service not known" in window.running.text()


def test_remove_with_and_without_the_plugins(qapp, setup, monkeypatch):
    paths, system, steam_dirs, _download = setup
    install(paths)
    state.enable_cef(steam_dirs)
    paths.deck.symlink_to(paths.home)
    window = _window(setup)
    assert window.deck_button.text() == "Unlink"
    monkeypatch.setattr(window, "_confirm_remove", lambda: (True, True))
    window.on_remove()
    assert system.calls == [["remove", "--wipe", "--unlink"]]
    assert not state.cef_enabled(steam_dirs) and window.pill.text() == "Not installed"
    install(paths)
    window.refresh()
    monkeypatch.setattr(window, "_confirm_remove", lambda: (False, True))
    window.on_remove()
    assert len(system.calls) == 1


def test_restart_log_switch_and_link(qapp, setup, monkeypatch):
    paths, system, steam_dirs, _download = setup
    install(paths)
    window = _window(setup)
    window.on_restart()
    assert system.calls[-1] == ["restart"] and window.running.text() == "restart done."
    assert "Decky's log" in state.journal(system.run)
    window.on_steam_switch()
    assert state.cef_enabled(steam_dirs) and window.steam_button.text() == "Switch off"
    window.on_steam_switch()
    assert not state.cef_enabled(steam_dirs)
    monkeypatch.setattr(window, "_ask", lambda title, text: True)
    window.on_deck_link()
    assert system.calls[-1] == ["link"] and window.deck_button.text() == "Unlink"


def test_a_failed_root_step_is_shown(qapp, setup):
    paths, system, steam_dirs, download = setup
    install(paths)
    window = _window((paths, system, steam_dirs, download))
    window.root = lambda args: privileged.Result(False, "Not authorized: the password dialog was canceled or refused.")
    window.on_restart()
    assert "Not authorized" in window.running.text() and "c62828" in window.running.styleSheet()


def test_game_mode_greys_the_root_steps(qapp, setup, monkeypatch):
    paths = setup[0]
    install(paths)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "gamescope")
    window = _window(setup)
    for button in (window.remove_button, window.restart_button, window.deck_button):
        assert not button.isEnabled() and "Desktop Mode" in button.toolTip()
    assert window.log_button.isEnabled() and window.steam_button.isEnabled()


def test_the_blue_look(qapp, setup):
    """The gaming apps' look (owner, 20-10-2026): the shadPS4 Manager's blue on the buttons, the header's boxes all
    with a blue left edge, the main action filled blue."""
    window = _window(setup)
    assert style.BLUE in window.styleSheet() and f"border-color:{style.BLUE}; background:{style.BLUE_TINT}" \
        in window.styleSheet()                                                      # the hover
    for box in (window.decky_box, window.service_box, window.steam_box, window.plugins_box):
        assert f"border-left:4px solid {style.BLUE}" in box.styleSheet()
    assert window.install_button.property("primary")
    window.close()
