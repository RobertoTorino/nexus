# SPDX-License-Identifier: GPL-3.0-or-later
"""The play mode's screen for a game that is no longer there (gone.py): which file, without the user's name, what to
do, A, B or a tap on A Close closing it, and closing by itself."""

from __future__ import annotations

from pathlib import Path

from bc250_core import gone, portable
from bc250_core.gamepad import Gamepad


class NoPad:
    def events(self):
        return []

    def close(self) -> None:
        pass


def test_the_gone_screen_says_which_game_and_closes_on_a_b_or_a_tap(qapp, monkeypatch):
    portable.pin_scale((1280, 720))
    monkeypatch.setenv("USERPROFILE", str(Path.home()))
    game = Path.home() / "Games" / "Xbox360" / "Halo 3 [NTSC].iso"
    for close in ("accept", "back", "tap"):
        window = gone.GoneWindow("Xenia Manager", "4.1.0", game, Gamepad(source_factory=NoPad))
        window.resize(1280, 720)
        window.show()
        qapp.processEvents()
        text = window.text.text()
        assert "Halo 3 [NTSC].iso" in text and Path.home().name not in text.replace("Halo 3", "")
        assert "Open Xenia Manager" in text and "LT Refresh" in text and "Update Steam" in text
        assert window.legend.items == [("A", "Close"), portable.EXIT]
        assert window.timer.isActive() and window.timer.interval() == gone.CLOSE_MS
        if close == "tap":
            window.legend.entries["A"].pressed.emit()
        else:
            window.act(close)
        assert not window.isVisible()
    window = gone.GoneWindow("Xenia Manager", "4.1.0", game, Gamepad(source_factory=NoPad))
    window.show()
    window.timer.timeout.emit()                                     # no button pressed: it closes by itself
    assert not window.isVisible()
