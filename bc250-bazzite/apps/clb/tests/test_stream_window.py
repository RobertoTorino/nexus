# SPDX-License-Identifier: GPL-3.0-or-later
"""The stream's window: the controller and the keyboard as the pad, leaving, the picture, dialogs and rumble."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QImage, QKeyEvent

from console_linkb import pads
from console_linkb.channels import Dialog
from console_linkb.inputs import PadState, Vibration
from console_linkb.stream import Stream
from console_linkb.stream_window import StreamWindow, merge


class FakeStream(Stream):
    def __init__(self):
        super().__init__(account=None, kind="cloud", target="X")
        self.pads: list = []
        self.shown: list = []
        self.answers: list = []
        self.stopped = 0

    def set_pads(self, pads):
        self.pads.append(pads)

    def frame_shown(self, rtp_timestamp, arrived_ms):
        self.shown.append((rtp_timestamp, arrived_ms))

    def answer_dialog(self, dialog, accepted):
        self.answers.append((dialog, accepted))

    def stop(self):
        self.stopped += 1


class FakeSource:
    def __init__(self):
        self.state: PadState | None = None
        self.rumbles: list = []
        self.closed = False

    def read(self):
        return self.state

    def rumble(self, vibration):
        self.rumbles.append(vibration)

    def close(self):
        self.closed = True


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def window(qapp):
    source, clock = FakeSource(), Clock()
    stream = FakeStream()
    view = StreamWindow(stream, "Fortnite", source_factory=lambda: source, sound=False, clock=clock)
    view.timer.stop()
    yield view, stream, source, clock
    view.close()


def key(view, which, press=True):
    kind = QEvent.Type.KeyPress if press else QEvent.Type.KeyRelease
    event = QKeyEvent(kind, which, Qt.KeyboardModifier.NoModifier)
    (view.keyPressEvent if press else view.keyReleaseEvent)(event)


def test_merge_controller_and_keyboard():
    assert merge(None, frozenset()) is None
    assert merge(None, frozenset({"a"})) == PadState(buttons=frozenset({"a"}))
    pad = PadState(0, frozenset({"b"}), left_x=0.5, right_trigger=1.0)
    merged = merge(pad, frozenset({"a"}))
    assert merged.buttons == {"a", "b"} and merged.left_x == 0.5 and merged.right_trigger == 1.0


def test_the_pad_goes_to_the_stream(window):
    view, stream, source, _clock = window
    view.poll()
    assert stream.pads[-1] == []
    source.state = PadState(0, frozenset({"x"}), left_y=-1.0)
    view.poll()
    assert stream.pads[-1] == [PadState(0, frozenset({"x"}), left_y=-1.0)]


def test_the_keyboard_as_a_pad(window):
    view, stream, _source, _clock = window
    key(view, Qt.Key.Key_Return)
    key(view, Qt.Key.Key_Up)
    view.poll()
    assert stream.pads[-1][0].buttons == {"a", "dpad_up"}
    key(view, Qt.Key.Key_Return, press=False)
    view.poll()
    assert stream.pads[-1][0].buttons == {"dpad_up"}


def test_holding_view_and_menu_leaves(window):
    view, stream, source, clock = window
    view.show()
    source.state = PadState(0, frozenset({"view", "menu"}))
    view.poll()
    clock.now = 1.5
    view.poll()
    assert view.isVisible()
    source.state = PadState(0, frozenset({"view"}))
    view.poll()                                         # let go: the hold starts again
    source.state = PadState(0, frozenset({"view", "menu"}))
    clock.now = 2.0
    view.poll()
    clock.now = 3.9
    view.poll()
    assert view.isVisible()
    clock.now = 4.1
    view.poll()
    assert not view.isVisible() and stream.stopped == 1 and source.closed


def test_ctrl_q_leaves(window):
    view, stream, _source, _clock = window
    view.show()
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Q, Qt.KeyboardModifier.ControlModifier))
    assert not view.isVisible() and stream.stopped == 1


def test_a_frame_drawn_is_reported(window):
    view, stream, _source, _clock = window
    view.resize(320, 180)
    image = QImage(64, 36, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.green)
    stream.image.emit(image, 900, 12.5)
    view.grab()
    assert stream.shown == [(900, 12.5)]
    view.grab()
    assert stream.shown == [(900, 12.5)]                # once per frame


def test_status_and_end(window):
    view, stream, _source, _clock = window
    view.show()
    stream.status.emit("Getting the Xbox ready…")
    assert view.message == "Getting the Xbox ready…"
    stream.ready.emit()
    assert view.message == ""
    stream.ended.emit("the connection to the stream was lost")
    assert view.isVisible() and "connection to the stream was lost" in view.message
    stream.ended.emit("")
    assert not view.isVisible()


def test_dialogs_and_rumble(window, monkeypatch):
    view, stream, source, _clock = window
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    dialog = Dialog("D1", "Quit?", "Sure?")
    stream.dialog.emit(dialog)
    assert stream.answers == [(dialog, True)]
    vibration = Vibration(0, 0.5, 0.2, 0, 0, 100, 0, 0)
    stream.vibration.emit(vibration)
    assert source.rumbles == [vibration]


def test_no_controller_source_leaves_the_keyboard(qapp):
    def broken():
        raise RuntimeError("no SDL")
    assert pads.open_source(broken) is None
    stream = FakeStream()
    view = StreamWindow(stream, "X", source_factory=broken, sound=False)
    view.timer.stop()
    view.poll()
    assert stream.pads[-1] == []
    view.close()
