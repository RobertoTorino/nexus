# SPDX-License-Identifier: GPL-3.0-or-later
"""Escape and B close the app's window: what the window does with the key first, the windows left alone, and B only
for the app that has had the focus for a moment."""

from __future__ import annotations

import os

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit, QMainWindow, QMenu, QVBoxLayout, QWidget

from bc250_core import exit_keys
from bc250_core.exit_keys import GRACE_S, BackButton, ExitKeys


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.closed = 0
        self.field = QLineEdit()
        self.setCentralWidget(self.field)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.closed += 1
        super().closeEvent(event)


class BackWindow(Window):
    """An app's own Escape: back from a page while one is open."""

    page = True

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.key() == Qt.Key.Key_Escape and self.page:
            self.page = False
            event.accept()
            return
        super().keyPressEvent(event)


class Presses:
    def __init__(self):
        self.waiting = 0
        self.closed = False

    def pressed(self) -> int:
        count, self.waiting = self.waiting, 0
        return count

    def close(self) -> None:
        self.closed = True


def press(widget: QWidget, key=Qt.Key.Key_Escape, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, key, modifiers))


@pytest.fixture
def keys(qapp):
    made = ExitKeys(qapp, controller=False)
    yield made
    qapp.removeEventFilter(made)
    made.stop()
    made.deleteLater()


@pytest.fixture
def pad(qapp, monkeypatch):
    """ExitKeys with a controller whose B the test presses, a clock it sets, and the app's focus as it says."""
    now = [100.0]
    source = Presses()
    made = ExitKeys(qapp, source_factory=lambda: source, clock=lambda: now[0])
    made.start()
    made.timer.stop()                                   # the test polls
    made.now, made.presses = now, source
    yield made
    qapp.removeEventFilter(made)
    made.stop()
    made.deleteLater()


def test_escape_closes_the_window_from_the_widget_with_the_focus(keys):
    window = Window()
    window.show()
    press(window.field)
    assert window.closed == 1 and not window.isVisible()


def test_another_key_and_escape_with_a_modifier_do_nothing(keys):
    window = Window()
    window.show()
    press(window.field, Qt.Key.Key_A)
    press(window.field, Qt.Key.Key_Escape, Qt.KeyboardModifier.ShiftModifier)
    assert window.closed == 0 and window.isVisible()
    window.close()


def test_the_windows_own_escape_comes_first(keys):
    window = BackWindow()
    window.show()
    press(window.field)                                 # back from the page
    assert window.closed == 0 and not window.page
    press(window.field)                                 # nothing left to go back from
    assert window.closed == 1


def test_a_window_that_refuses_to_close_stays(keys):
    class Busy(Window):
        def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
            self.closed += 1
            event.ignore()

    window = Busy()
    window.show()
    press(window.field)
    assert window.closed == 1 and window.isVisible()
    window.destroy()


def test_a_dialog_a_menu_and_a_window_that_keeps_its_keys_are_left_alone(keys):
    class Stream(Window):
        exit_keys = False

    stream = Stream()
    assert not ExitKeys.closes(stream)
    assert not ExitKeys.closes(QDialog())
    assert not ExitKeys.closes(QMenu())
    assert not ExitKeys.closes(stream.field)            # not a window
    assert ExitKeys.closes(Window())
    stream.show()
    press(stream.field)
    assert stream.closed == 0
    stream.close()


def test_a_dialog_keeps_qts_escape(keys):
    window = Window()
    window.show()
    dialog = QDialog(window)
    field = QLineEdit()
    QVBoxLayout(dialog).addWidget(field)
    dialog.show()
    press(field)
    assert not dialog.isVisible() and window.closed == 0
    window.close()


def test_b_is_escape_for_the_app_with_the_focus(pad, monkeypatch):
    window = Window()
    window.show()
    monkeypatch.setattr(pad.app, "activeWindow", lambda: window)
    monkeypatch.setattr(pad.app, "focusWidget", lambda: window.field)
    pad.now[0] += GRACE_S
    pad.presses.waiting = 1
    pad.poll()
    assert window.closed == 1


def test_b_without_the_focus_is_read_and_dropped(pad, monkeypatch):
    window = Window()
    window.show()
    monkeypatch.setattr(pad.app, "activeWindow", lambda: None)
    pad.now[0] += 10
    pad.presses.waiting = 1
    pad.poll()
    assert window.closed == 0 and pad.presses.waiting == 0
    monkeypatch.setattr(pad.app, "activeWindow", lambda: window)
    pad.poll()                                          # the press does not come back with the focus
    assert window.closed == 0
    window.close()


def test_b_right_after_the_focus_came_is_the_press_that_closed_another_app(pad, monkeypatch):
    window = Window()
    window.show()
    monkeypatch.setattr(pad.app, "activeWindow", lambda: window)
    monkeypatch.setattr(pad.app, "focusWidget", lambda: window.field)
    pad.now[0] += 10
    pad._state_changed(Qt.ApplicationState.ApplicationActive)
    pad.now[0] += GRACE_S / 2
    pad.presses.waiting = 1
    pad.poll()
    assert window.closed == 0
    pad.now[0] += GRACE_S
    pad.presses.waiting = 1
    pad.poll()
    assert window.closed == 1


def test_b_closes_a_dialog_before_the_window(pad, monkeypatch):
    window = Window()
    window.show()
    dialog = QDialog(window)
    field = QLineEdit()
    QVBoxLayout(dialog).addWidget(field)
    dialog.show()
    monkeypatch.setattr(pad.app, "activeWindow", lambda: dialog)
    monkeypatch.setattr(pad.app, "focusWidget", lambda: field)
    pad.now[0] += GRACE_S
    pad.presses.waiting = 1
    pad.poll()
    assert not dialog.isVisible() and window.closed == 0
    window.close()


def test_without_a_controller_reader_there_is_escape_alone(qapp):
    def none():
        raise ImportError("no pygame")

    made = ExitKeys(qapp, source_factory=none)
    try:
        assert made.start() is False and not made.timer.isActive()
        window = Window()
        window.show()
        press(window.field)
        assert window.closed == 1
    finally:
        qapp.removeEventFilter(made)
        made.deleteLater()


def test_a_reader_that_fails_is_stopped_and_the_app_goes_on(pad, monkeypatch):
    source = pad.presses

    def gone() -> int:
        raise RuntimeError("video system not initialized")

    monkeypatch.setattr(source, "pressed", gone)
    pad.poll()
    assert pad.source is None and source.closed and not pad.timer.isActive()
    pad.poll()                                          # nothing left to read


def test_stop_closes_the_reader(pad):
    source = pad.presses
    pad.stop()
    assert source.closed and pad.source is None


def test_sdls_variables_do_not_stay_in_the_environment(monkeypatch):
    """What the app starts later (Steam, an emulator) must not inherit SDL's dummy video driver; a value that was
    there before (from the portal that started the app) stays as it was."""
    pytest.importorskip("pygame")
    monkeypatch.delenv("SDL_VIDEODRIVER", raising=False)
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    button = BackButton()
    try:
        assert "SDL_VIDEODRIVER" not in os.environ
        assert os.environ["SDL_AUDIODRIVER"] == "dummy"
        assert button.pressed() == 0
    finally:
        button.close()


def test_install_gives_the_app_its_exit_keys(qapp):
    made = exit_keys.install(qapp, controller=False)
    try:
        assert isinstance(made, ExitKeys) and made.parent() is qapp and not made.timer.isActive()
    finally:
        qapp.removeEventFilter(made)
        made.deleteLater()
