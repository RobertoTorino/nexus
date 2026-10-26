# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings and the XDG folders in a temp folder (so no test touches the
user's scores, settings or the Windows registry), and a small set of questions."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_ROOT = Path(__file__).resolve().parents[1]
CORE = Path(__file__).resolve().parents[4] / "core"
for folder in (CORE, APP_ROOT):                 # bc250_core from the checkout, as the installer bundles it
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(["bazzite-datstation-test"])
    yield app


@pytest.fixture(autouse=True)
def settings_dir(tmp_path, monkeypatch):
    """The app keeps an .ini, so this keeps the tests out of the user's settings (and the Windows registry)."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_BIN_HOME", str(tmp_path / "bin"))
    return tmp_path / "settings"


@pytest.fixture(autouse=True)
def no_real_steam(tmp_path, monkeypatch):
    """Keeps every test away from a Steam on the machine: HOME is a temp folder, so find_steam() finds none, and
    with_steam_closed() sees no Steam running and starts no Steam command. Its defaults were bound when core was
    imported, so patching steam.steam_running alone does not reach them."""
    import time

    from bc250_core import steam

    def no_command(command):
        pytest.fail(f"a test started a Steam command: {command}")

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(steam.with_steam_closed, "__defaults__",
                        (no_command, lambda: False, steam.SHUTDOWN_TIMEOUT, time.sleep))


@pytest.fixture
def questions():
    """Twelve questions: ten multiple choice over four categories and two true/false, one with an explanation."""
    from datstation.quiz import Question
    items = []
    for n in range(10):
        category = ("PlayStation1", "PlayStation2", "General", "App")[n % 4]
        items.append(Question(f"q{n}", f"Question {n}?", "MC", category, ("Right", "Wrong A", "Wrong B", "Wrong C"),
                              "Right", 10))
    items.append(Question("tf1", "The PS2 used Blu-ray discs.", "TF", "PlayStation2", ("True", "False"), "False", 10,
                          "PlayStation 2 used CDs and DVDs for games, not Blu-ray discs."))
    items.append(Question("tf2", "The PS1 launched in 1994.", "TF", "PlayStation1", ("True", "False"), "True", 10))
    return items
