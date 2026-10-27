# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py): the device read in the background and shown, read again, the report saved, a failed
read, the controller test that has every button until B is held, and B closing the app."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent

from bc250_core import portable
from bc250_core.gamepad import Gamepad
from portable_test import device
from portable_test.main_window import MainWindow


class FakePad:
    def __init__(self):
        self.queue = []

    def events(self):
        found, self.queue = self.queue, []
        return found

    def close(self):
        pass

    def names(self):
        return ["ASUSTeK Computer Inc."]


def wait_for(qapp, predicate, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not predicate():
        qapp.processEvents()
        time.sleep(0.01)
    return predicate()


@pytest.fixture
def make(qapp, tmp_path, ally_json):
    windows = []

    def make(read=None, pad=None):
        pad = pad or FakePad()
        window = MainWindow(gamepad=Gamepad(source_factory=lambda: pad), read=read or (lambda: device.parse(ally_json)),
                            battery=lambda: (82, False), reports=tmp_path / "reports")
        portable.scale((1280, 720))
        window.resize(1280, 720)
        window.show()
        window.activateWindow()                     # a card gets its focus events in the active window only
        qapp.processEvents()
        window.start()
        windows.append(window)
        return window, pad
    yield make
    for window in windows:
        window.close()


def values(window) -> dict[str, str]:
    grid = window.device_pane.grid
    cells = [grid.itemAt(i).widget().text() for i in range(grid.count())]
    return dict(zip(cells[0::2], cells[1::2]))


def test_the_device_is_read_and_shown(make, qapp):
    window, _ = make()
    assert wait_for(qapp, lambda: window.device is not None)
    shown = values(window)
    assert shown["Device"] == "ROG Xbox Ally X" and shown["Memory"] == "24 GB, 15.6 GB usable"
    assert "Screen" in shown and " % scaling, " in shown["Screen"]
    assert list(shown).index("Screen") == list(shown).index("Memory") - 1
    assert window.header.status.text().startswith("82 %  |  ")
    assert window.header.icon is None                       # the screen is too small for it (owner, 27-10-2026)
    assert [text for _, text in window.legend.items] == ["Save report", "Close"]


def test_read_again_and_a_failed_read(make, qapp, ally_json):
    answers = [lambda: device.parse(ally_json), lambda: (_ for _ in ()).throw(RuntimeError("CIM is not running"))]
    window, _ = make(read=lambda: answers.pop(0)())
    assert wait_for(qapp, lambda: window.device is not None and window.device_pane.read_pill.isEnabled())
    window.device_pane.read_pill.click()
    assert wait_for(qapp, lambda: "did not answer" in window.device_pane.status.text())
    assert "CIM is not running" in window.device_pane.status.text() and window.device is not None


def test_x_saves_the_report(make, qapp, tmp_path, monkeypatch):
    window, _ = make()
    assert wait_for(qapp, lambda: window.device is not None)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("x")
    saved = list((tmp_path / "reports").glob("device-*.txt"))
    assert len(saved) == 1 and "Device: ROG Xbox Ally X" in saved[0].read_text(encoding="utf-8")
    assert str(saved[0]) in window.device_pane.status.text()


def test_the_controller_test_has_every_button_until_b_is_held(make, qapp, monkeypatch):
    window, pad = make()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.controller_card.setFocus()
    qapp.processEvents()
    assert window.panes.currentWidget() is window.controller_pane
    window.on_action("accept")
    assert window.testing and window.legend.items == [("B", "Hold to finish")]
    pad.queue += [("button", "b", True), ("button", "b", False), ("button", "dpad_down", True),
                  ("button", "dpad_down", False), ("button", "x", True)]
    window.gamepad.poll()
    assert closed == [] and window.controller_card.hasFocus()                # B and the d-pad were the test's
    assert set(window.controller_pane.seen()) == {"b", "dpad_down", "x"}
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert not window.testing and closed == []                                # Escape ended the test only
    window.on_action("back")
    assert closed == [True]                                                   # now B closes the app


def test_the_cards_show_their_panes(make, qapp):
    window, _ = make()
    window.controller_card.setFocus()
    qapp.processEvents()
    assert window.panes.currentWidget() is window.controller_pane
    assert window.legend.items == [("A", "Start the test"), ("B", "Close")]
    window.device_card.setFocus()
    qapp.processEvents()
    assert window.panes.currentWidget() is window.device_pane


def test_the_version_is_the_apps():
    from portable_test import __version__
    assert __version__ == (Path(__file__).resolve().parents[1] / "VERSION").read_text().strip()
