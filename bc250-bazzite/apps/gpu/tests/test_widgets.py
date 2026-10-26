# SPDX-License-Identifier: GPL-3.0-or-later
"""The rounded tooltip lets go of the app's events when the app quits, so nothing calls into Python while it tears
down (the app crashed at exit otherwise)."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from gpu_governor.widgets import RoundedToolTip


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
