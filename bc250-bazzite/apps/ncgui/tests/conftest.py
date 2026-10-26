# SPDX-License-Identifier: GPL-2.0-only
"""Shared fixtures: an offscreen QApplication, settings in a temp folder, an event-loop pump, a free port, and the
message boxes replaced by collectors so a dialog never blocks a test."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_ROOT = Path(__file__).resolve().parents[1]
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as the installer bundles it
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(["bazzite-netcatgui-test"])
    yield app


@pytest.fixture(autouse=True)
def settings_dir(tmp_path, monkeypatch):
    """The app keeps an .ini, so this keeps the tests out of the user's settings (and the Windows registry)."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return tmp_path / "settings"


class Dialogs:
    """What QMessageBox would have shown: (kind, title, text) per call."""

    def __init__(self) -> None:
        self.shown: list[tuple[str, str, str]] = []

    def titles(self, kind: str | None = None) -> list[str]:
        return [title for k, title, _ in self.shown if kind is None or k == kind]


@pytest.fixture
def dialogs(monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    collector = Dialogs()
    for kind in ("warning", "critical", "information", "about"):
        monkeypatch.setattr(QMessageBox, kind,
                            lambda parent, title, text, *a, _k=kind, **kw: collector.shown.append((_k, title, text)))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda parent, title, text, *a, **kw: (collector.shown.append(("question", title, text)),
                                                               QMessageBox.StandardButton.No)[1])
    return collector


@pytest.fixture
def pump(qapp):
    """pump(condition, deadline_ms): runs the event loop until the condition holds or the deadline passes."""
    from PyQt6.QtCore import QElapsedTimer, QEventLoop, QThread

    def _pump(done=lambda: False, deadline_ms: int = 5000) -> bool:
        timer = QElapsedTimer()
        timer.start()
        while timer.elapsed() < deadline_ms:
            qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
            if done():
                return True
            QThread.msleep(5)
        return done()
    return _pump


@pytest.fixture
def free_port():
    def _free_port(kind=socket.SOCK_STREAM) -> int:
        with socket.socket(socket.AF_INET, kind) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
    return _free_port
