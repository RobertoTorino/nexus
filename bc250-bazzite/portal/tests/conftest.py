# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: bc250_core from the checkout, an offscreen QApplication, and a sandboxed home folder."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SUITE = Path(__file__).resolve().parents[2]      # the suite: bc250-bazzite/
sys.path.insert(0, str(SUITE.parent / "core"))  # the release bundles core; in the checkout it is at the root


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def home(tmp_path, monkeypatch):
    """HOME and XDG folders inside tmp_path, so detect paths like ~/.local/bin/x resolve there."""
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    return home


@pytest.fixture
def settings_dir(tmp_path, qapp, monkeypatch):
    """QSettings files in tmp_path; on Windows the native format (the registry) is turned into an .ini there."""
    from PyQt6.QtCore import QSettings
    for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
        QSettings.setPath(fmt, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    if sys.platform == "win32":
        import bc250_core.settings as core_settings

        class FileSettings(QSettings):
            def __init__(self, *args):
                if args and isinstance(args[0], str):
                    args = (QSettings.Format.IniFormat, QSettings.Scope.UserScope, *args)
                super().__init__(*args)

        monkeypatch.setattr(core_settings, "QSettings", FileSettings)
    return tmp_path / "settings"


@pytest.fixture(autouse=True)
def desktop(tmp_path, monkeypatch):
    """The Desktop folder inside tmp_path for every test: the portal removes app icons from the Desktop."""
    import bc250_portal.desktop_icons as desktop_icons
    folder = tmp_path / "Desktop"
    folder.mkdir()
    monkeypatch.setattr(desktop_icons, "desktop_dir", lambda: folder)
    return folder


@pytest.fixture(autouse=True)
def no_session_bus(monkeypatch):
    """R3's keyboard never reaches the desktop's real KWin: it would change the keyboard mode of the machine the tests
    run on. A test that wants KWin gives the keyboard a fake bus."""
    from bc250_portal import keyboard

    def refuse(*_args):
        raise keyboard.KeyboardError("the tests have no session bus")
    monkeypatch.setattr(keyboard, "dbus_call", refuse)


@pytest.fixture(autouse=True)
def no_kwin_no_uinput(monkeypatch, tmp_path):
    """No test brings a real window to the front through KWin, or adds a mouse to the machine through uinput: KWin's
    calls fail, and the virtual mouse finds no device. A test that wants them gives the window fakes."""
    from bc250_portal import kwin, pointer

    def refuse(*_args):
        raise kwin.KWinError("the tests have no session bus")
    monkeypatch.setattr(kwin, "dbus_call", refuse)
    monkeypatch.setattr(pointer, "DEVICE", str(tmp_path / "no-uinput"))


class SilentPlayer:
    """Stands in for the music's player: it records what the portal asked and plays nothing."""

    def __init__(self):
        self.path = None
        self.playing = False
        self.calls: list[str] = []

    def set_track(self, path) -> None:
        self.path = path
        self.calls.append("track")

    def play(self) -> None:
        self.playing = True
        self.calls.append("play")

    def pause(self) -> None:
        self.playing = False
        self.calls.append("pause")

    def stop(self) -> None:
        self.playing = False
        self.calls.append("stop")


@pytest.fixture(autouse=True)
def silent_music(monkeypatch):
    """No test plays the portal's music on the machine the tests run on: a window's player is a SilentPlayer. A test
    of the player itself makes one from the class this returns."""
    from bc250_portal import music
    real = music.Player
    monkeypatch.setattr(music, "Player", SilentPlayer)
    return real
