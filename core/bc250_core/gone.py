# SPDX-License-Identifier: GPL-3.0-or-later
"""The play mode's screen for a game that is no longer there (the Windows Portable Suite's game managers; owner,
01-11-2026: a game renamed after it was put in Steam started Xenia without it, Xenia's own error under Steam's
keyboard, neither closable with the controller): the emulator is not started, and a screen in the suite's design says
which file is missing and what to do. A, B or View closes it (a tap on its entry too), and it closes by itself after
CLOSE_MS, so Steam sees the game end either way.

play.missing() tells whether the game is gone; show() is what the app's play mode runs then, instead of play.run()."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QVBoxLayout

from .app import create_app, exec_app
from .appinfo import AppInfo
from .gamepad import Gamepad
from .platform import private
from .portable import BODY, DIM, PORTABLE, Legend, Pane, PortableHeader, PortableWindow, px, text_label

CLOSE_MS = 60_000               # the screen closes by itself after this
TITLE = "This game is no longer there"


def message(app_name: str, game: Path) -> str:
    """What the screen says: the file (the user's folders by their variable, never the user's name) and what to
    do."""
    return (f"{private(game)}\n\nIt was renamed, moved or deleted after it was put in Steam, or it is on an SD card "
            f"that is not in, so the emulator was not started. Open {app_name}: on Your games, LT Refresh finds the "
            "game again under its new name, and Y Update Steam brings its shortcut in Steam up to date.")


class GoneWindow(PortableWindow):
    """The header, the message in a pane and the legend: A Close (B and View close it too)."""

    def __init__(self, app_name: str, version: str, game: Path, gamepad: Gamepad | None = None):
        super().__init__(gamepad)
        self.setWindowTitle(app_name)
        page = QVBoxLayout(self)
        page.setContentsMargins(*self.margins())
        page.addWidget(PortableHeader(app_name, version))
        page.addSpacing(px(14))
        pane = Pane()
        pane.column.addWidget(text_label(TITLE, 24, QFont.Weight.ExtraBold))
        pane.column.addSpacing(px(8))
        self.text = text_label(message(app_name, game), BODY + 1, color=DIM, wrap=True)
        pane.column.addWidget(self.text)
        pane.column.addStretch()
        page.addWidget(pane, 1)
        page.addSpacing(px(8))
        self.legend = Legend([("A", "Close"), *self.common_items(False)])
        page.addWidget(self.legend)
        self.bind("accept", self.close)
        self.back.connect(self.close)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(CLOSE_MS)
        self.timer.timeout.connect(self.close)
        self.timer.start()


def show(info: AppInfo, app_name: str, version: str, game: Path) -> int:
    """The screen full screen until it is closed; the play mode's exit code (1: the game did not run)."""
    app = create_app(info, theme=PORTABLE)
    window = GoneWindow(app_name, version, game)
    window.showFullScreen()
    window.activateWindow()                     # the controller counts in the active window only
    window.start_gamepad()
    exec_app(app)
    return 1
