# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings and XDG folders in a temp folder, and a home with Decky's
folders made here."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as the installer bundles it


def make_plugin(plugins: Path, folder: str, name: str, version: str | None = "1.0.0", author: str = "someone") -> Path:
    """A plugin folder as Decky's store installs it: plugin.json and, when *version* is given, package.json."""
    path = plugins / folder
    path.mkdir(parents=True)
    (path / "plugin.json").write_text(json.dumps({"name": name, "author": author, "flags": [], "api_version": 1}))
    if version is not None:
        (path / "package.json").write_text(json.dumps({"name": folder.lower(), "version": version}))
    return path


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def settings_dir(tmp_path, monkeypatch):
    """The app keeps an .ini (AppInfo.settings_ini), so this also keeps the tests out of the Windows registry."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    return tmp_path / "settings"
