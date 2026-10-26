# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, and HOME, the XDG folders and QSettings in a temp folder, so the tests
never touch your settings or results."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("bc250-gpu-oc-bisect")
    yield app


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
        QSettings.setPath(fmt, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    return home
