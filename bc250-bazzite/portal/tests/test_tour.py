# SPDX-License-Identifier: GPL-3.0-or-later
"""The Portal Tour's player: a video that cannot be played says so once and closes, and its keys."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QDialog

from bc250_portal import tour


def test_a_tour_that_cannot_be_played_says_so_once_and_closes(qapp):
    player = tour.TourPlayer("file:///nowhere/portal-tour.mp4", sound=False)
    reasons = []
    player.failed.connect(reasons.append)
    player._fail("The video did not start.")
    player._fail("a late error")
    assert reasons == ["The video did not start."]
    assert player.result() == QDialog.DialogCode.Rejected and not player.isVisible()
    player.deleteLater()


def test_space_pauses_and_plays_on_and_does_not_close(qapp, monkeypatch):
    player = tour.TourPlayer("file:///nowhere/portal-tour.mp4", sound=False)
    toggled = []
    monkeypatch.setattr(player, "toggle", lambda: toggled.append(True))
    for key in (Qt.Key.Key_Space, Qt.Key.Key_Return):
        player.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))
    assert toggled == [True, True]
    player.toggle = tour.TourPlayer.toggle.__get__(player)
    player.toggle()                                         # before start(): nothing to pause, no error
    player.deleteLater()
