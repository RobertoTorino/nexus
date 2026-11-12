# SPDX-License-Identifier: GPL-3.0-or-later
"""A tab that acts (owner, 12-11-2026: Start game in the BC250 suite's game managers): it stands in the row of
tabs as the last one, and a click on it does something instead of opening a page. The page that was open stays
open. Reached with the keyboard (the arrow keys on the tabs, Ctrl+Tab) it does nothing: the tabs go on to the page
they came from, so a game never starts from a key that only moves."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QTabWidget, QWidget


class ActionTab(QObject):
    """The last tab of *tabs*, named *label* with *tooltip*: a click on it calls *pressed*. index is its place."""

    def __init__(self, tabs: QTabWidget, label: str, tooltip: str, pressed: Callable[[], None]):
        super().__init__(tabs)
        self.tabs = tabs
        self.pressed = pressed
        self.last = max(0, tabs.currentIndex())     # the page that stays open
        self.index = tabs.addTab(QWidget(), label)
        tabs.setTabToolTip(self.index, tooltip)
        tabs.tabBarClicked.connect(self._clicked)
        tabs.currentChanged.connect(self._changed)

    def _clicked(self, index: int) -> None:
        if index == self.index:
            self.pressed()

    def _changed(self, index: int) -> None:
        if index == self.index:
            self.tabs.setCurrentIndex(self.last)
        else:
            self.last = index
