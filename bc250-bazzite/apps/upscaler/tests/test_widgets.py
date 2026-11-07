# SPDX-License-Identifier: GPL-3.0-or-later
"""The rounded tooltip lets go of the app's events when the app quits, so nothing calls into Python while it tears
down (the app crashed at exit otherwise)."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from upscaler.theme import ACCENT, OUTLINE
from upscaler.widgets import RoundedToolTip


def test_tooltip_filter_is_removed_when_the_app_quits(qapp, monkeypatch):
    class App(QObject):                     # stands in for the QApplication, so the real one keeps running
        aboutToQuit = pyqtSignal()

        def __init__(self):
            super().__init__()
            self.filters: list[QObject] = []

        def installEventFilter(self, obj):  # noqa: N802
            self.filters.append(obj)

        def removeEventFilter(self, obj):   # noqa: N802
            self.filters.remove(obj)

    monkeypatch.setattr(RoundedToolTip, "_instance", None)
    app = App()
    tip = RoundedToolTip.install(app)
    assert app.filters == [tip] and RoundedToolTip._instance is tip
    app.aboutToQuit.emit()
    assert app.filters == []


def test_tooltip_border_is_the_outline(qapp):
    """Framed in the theme's outline, silver, not the accent (owner, 07-11-2026)."""
    sheet = RoundedToolTip(qapp).label.styleSheet()
    assert f"border:1px solid {OUTLINE};" in sheet and (ACCENT == OUTLINE or ACCENT not in sheet)
