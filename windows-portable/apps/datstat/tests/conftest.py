# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication with bc250_core from the checkout, the settings and the suite's folders
in a temp folder (never Windows' registry), no Steam of the machine's, a dozen questions, the recorded feed, and the
window with fakes for the controller, the music, the feed and the browser."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as a release bundles it
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from bc250_core import portable
    portable.pin_scale((1280, 720))     # the Ally's screen, not the offscreen one (800 x 800): the windows fit-tested
    yield app
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)


@pytest.fixture(autouse=True)
def settings_in_tmp(tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


@pytest.fixture(autouse=True)
def no_real_steam(monkeypatch):
    """Keeps every test away from the machine's Steam: with_steam_closed() sees no Steam running and starts no Steam
    command. Its defaults were bound when core was imported, so patching steam.steam_running alone does not reach
    them."""
    import time

    from bc250_core import steam

    def no_command(command):
        pytest.fail(f"a test started a Steam command: {command}")

    monkeypatch.setattr(steam.with_steam_closed, "__defaults__",
                        (no_command, lambda: False, steam.SHUTDOWN_TIMEOUT, time.sleep))


@pytest.fixture
def questions():
    """Twelve questions: ten multiple choice over four categories and two true/false, one with an explanation."""
    from dat_station.quiz import Question
    items = []
    for n in range(10):
        category = ("PlayStation1", "PlayStation2", "General", "App")[n % 4]
        items.append(Question(f"q{n}", f"Question {n}?", "MC", category, ("Right", "Wrong A", "Wrong B", "Wrong C"),
                              "Right", 10))
    items.append(Question("tf1", "The PS2 used Blu-ray discs.", "TF", "PlayStation2", ("True", "False"), "False", 10,
                          "PlayStation 2 used CDs and DVDs for games, not Blu-ray discs."))
    items.append(Question("tf2", "The PS1 launched in 1994.", "TF", "PlayStation1", ("True", "False"), "True", 10))
    return items


def make_steam(folder: Path, users: int = 1) -> Path:
    """A Steam folder with *users* users, each with a shortcuts.vdf holding one other non-Steam game."""
    from bc250_core import steam
    other = {"appid": -1234, "AppName": "RetroArch", "Exe": '"C:\\RetroArch\\retroarch.exe"',
             "StartDir": '"C:\\RetroArch\\"', "LaunchOptions": "", "LastPlayTime": 1700000000,
             "tags": {"0": "Emulators"}}
    for n in range(users):
        config = folder / "Steam" / "userdata" / str(1000 + n) / "config"
        config.mkdir(parents=True)
        (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": other}}))
    return folder / "Steam"
