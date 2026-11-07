# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: bc250_core from the checkout and an offscreen QApplication."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PORTAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORTAL.parent.parent / "core"))
sys.path.insert(0, str(PORTAL))


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    return home


@pytest.fixture
def settings_dir(tmp_path, qapp):
    from PyQt6.QtCore import QSettings

    for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
        QSettings.setPath(fmt, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    return tmp_path / "settings"


@pytest.fixture(autouse=True)
def desktop(tmp_path, monkeypatch):
    from bazzite_console_portal import desktop_icons

    folder = tmp_path / "Desktop"
    folder.mkdir()
    monkeypatch.setattr(desktop_icons, "desktop_dir", lambda: folder)
    return folder
