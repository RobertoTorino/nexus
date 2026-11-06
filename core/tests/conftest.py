# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings in a temporary folder and a test AppInfo."""

from __future__ import annotations

import gc
import os
import sys
import uuid
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SUITE = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    # create_app() installs the tooltip filter on this app, and no aboutToQuit takes it off without an event loop:
    # left on, it saw the events of the widgets pytest's final garbage collection destroyed, and crashed it now and
    # then (CI, 06-11-2026). Off before that collection, and the leftover widgets collected while the app is whole.
    from bc250_core.widgets import RoundedToolTip
    RoundedToolTip.uninstall()
    gc.collect()


@pytest.fixture
def settings_dir(tmp_path, qapp, monkeypatch):
    """Point QSettings files at tmp_path for the duration of a test.

    On Windows the native format is the registry, which setPath() cannot redirect, so there QSettings(org, app) is
    turned into the same call with IniFormat: a file under tmp_path, as on Linux, where native is a .conf file."""
    from PyQt6.QtCore import QSettings
    for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
        QSettings.setPath(fmt, QSettings.Scope.UserScope, str(tmp_path))
    if sys.platform == "win32":
        import bc250_core.settings as core_settings

        class FileSettings(QSettings):
            def __init__(self, *args):
                if args and isinstance(args[0], str):
                    args = (QSettings.Format.IniFormat, QSettings.Scope.UserScope, *args)
                super().__init__(*args)

        monkeypatch.setattr(core_settings, "QSettings", FileSettings)
    yield tmp_path


@pytest.fixture
def board(tmp_path) -> Path:
    """A fake BC-250 /proc and /sys (board.py)."""
    from board import make_board
    return make_board(tmp_path / "root")


@pytest.fixture
def info(tmp_path):
    """A test AppInfo with a unique id, so no test sees another's settings."""
    from bc250_core.appinfo import AppInfo
    return AppInfo(app_id=f"bc250-test-app-{uuid.uuid4().hex[:8]}", name="BC-250 Test App", version="1.2.3",
                   tag_prefix="test-app-v")
