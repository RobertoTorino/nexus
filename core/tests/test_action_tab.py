# SPDX-License-Identifier: GPL-3.0-or-later
"""A tab that acts: a click does its action and the open page stays; the keyboard passes it by."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QTabWidget, QWidget

from bc250_core.action_tab import ActionTab


def tabs_with_action(pressed: list) -> tuple[QTabWidget, ActionTab]:
    tabs = QTabWidget()
    for name in ("Your games", "Settings", "Log"):
        tabs.addTab(QWidget(), name)
    action = ActionTab(tabs, "Start game", "Start the chosen game in Steam", lambda: pressed.append(1))
    tabs.resize(600, 300)
    tabs.show()
    return tabs, action


def click(tabs: QTabWidget, index: int) -> None:
    QTest.mouseClick(tabs.tabBar(), Qt.MouseButton.LeftButton, pos=tabs.tabBar().tabRect(index).center())


def test_it_is_the_last_tab_with_its_name_and_tooltip(qapp):
    tabs, action = tabs_with_action([])
    assert action.index == 3 == tabs.count() - 1 and tabs.tabText(3) == "Start game"
    assert tabs.tabToolTip(3) == "Start the chosen game in Steam" and tabs.currentIndex() == 0
    tabs.close()


def test_a_click_acts_and_the_open_page_stays(qapp):
    pressed: list = []
    tabs, action = tabs_with_action(pressed)
    click(tabs, 1)
    assert tabs.currentIndex() == 1 and pressed == []
    click(tabs, action.index)
    assert pressed == [1] and tabs.currentIndex() == 1          # Settings is still open
    click(tabs, action.index)
    assert pressed == [1, 1]                                    # and it acts each time
    click(tabs, 2)
    click(tabs, action.index)
    assert tabs.currentIndex() == 2
    tabs.close()


def test_the_keyboard_passes_it_by(qapp):
    pressed: list = []
    tabs, action = tabs_with_action(pressed)
    tabs.setCurrentIndex(2)
    tabs.setCurrentIndex(action.index)                          # as Ctrl+Tab or the arrow keys on the tabs do
    assert tabs.currentIndex() == 2 and pressed == []
    tabs.close()


def test_a_press_beside_the_tabs_does_nothing(qapp):
    pressed: list = []
    tabs, _ = tabs_with_action(pressed)
    QTest.mouseClick(tabs.tabBar(), Qt.MouseButton.LeftButton, pos=QPoint(tabs.tabBar().width() + 5, 5))
    assert pressed == [] and tabs.currentIndex() == 0
    tabs.close()
