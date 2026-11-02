# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication with bc250_core from the checkout, and the settings and the suite's folders
in a temp folder (never Windows' registry)."""

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


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)


@pytest.fixture(autouse=True)
def settings_in_tmp(tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


class FakePort:
    """A screen on the other end of the port: records what is written, answers HELLO with *reply*, and fails with
    OSError once *fail_after* writes have been made (an unplugged screen)."""

    def __init__(self, reply: bytes = b"", fail_after: int | None = None):
        self.reply = reply
        self.writes: list[bytes] = []
        self.fail_after = fail_after
        self.closed = False

    def write(self, data: bytes) -> None:
        if self.fail_after is not None and len(self.writes) >= self.fail_after:
            raise OSError(31, "A device attached to the system is not functioning")
        self.writes.append(bytes(data))

    def read(self, size: int, timeout: float) -> bytes:
        return self.reply[:size]

    def close(self) -> None:
        self.closed = True

    @property
    def data(self) -> bytes:
        return b"".join(self.writes)


def wait_until(qapp, condition, timeout: float = 5.0) -> bool:
    """Lets Qt deliver the link thread's signals until *condition* holds."""
    import time
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False
