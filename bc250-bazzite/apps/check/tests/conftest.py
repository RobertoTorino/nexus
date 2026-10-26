# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke-test fixtures: bc250_core from the suite checkout (a release bundles it), an offscreen QApplication and a
home folder in tmp_path, so nothing touches the real ~/.config, ~/.local/share or the Desktop."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[2] / "core"))


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def sandbox(tmp_path, monkeypatch, qapp):
    from PyQt6.QtCore import QSettings
    home = tmp_path / "home"
    (home / "Desktop").mkdir(parents=True)
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
        QSettings.setPath(fmt, QSettings.Scope.UserScope, str(home / ".config"))
    return home
