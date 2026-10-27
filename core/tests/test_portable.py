# SPDX-License-Identifier: GPL-3.0-or-later
"""The portable window (portable.py): the design's sizes on any screen, a card's focus, the pill's, moving the focus
with the d-pad or the arrow keys, A and B, a page's own buttons, and the controller only while the window is active."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QKeyEvent, QPixmap
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QGridLayout, QVBoxLayout

from bc250_core import portable
from bc250_core.portable import AMBER, Card, Legend, Pill, PortableHeader, PortableWindow, nearest


class NoPad:
    def events(self):
        return []

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def mockup_scale():
    portable.scale((1280, 720))
    yield
    portable.scale((1280, 720))


def test_the_sizes_follow_the_screen():
    """The mock-up is 1280 x 720: the Ally's screen at 150 % is that, a TV at 125 % is 1536 x 864 (1.2 times)."""
    assert portable.scale((1280, 720)) == 1 and portable.px(14) == 14
    assert portable.scale((1536, 864)) == pytest.approx(1.2) and portable.px(14) == 17
    assert portable.scale((2560, 1080)) == pytest.approx(1.5)              # the smaller ratio: it fits
    assert portable.scale((1024, 600)) == 1                                # never smaller than the mock-up
    assert portable.font(portable.TITLE).pointSizeF() == pytest.approx(portable.TITLE)


@pytest.fixture
def page(qapp):
    """Two rows of two cards and a pill under them, as a portal page or the test app lays them out."""
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    window.setFixedSize(800, 500)
    column = QVBoxLayout(window)
    grid = QGridLayout()
    cards = [Card(f"Card {i}", "What it does.") for i in range(4)]
    for i, card in enumerate(cards):
        grid.addWidget(card, i // 2, i % 2)
    column.addLayout(grid)
    pill = Pill("Open", "A", main=True)
    column.addWidget(pill)
    window.show()
    qapp.processEvents()
    yield window, cards, pill
    window.close()


def test_a_focused_card_is_raised_with_an_amber_edge_and_glow(page, qapp):
    window, cards, _ = page
    cards[0].setFocus()
    qapp.processEvents()
    assert AMBER in cards[0].styleSheet() and isinstance(cards[0].graphicsEffect(), QGraphicsDropShadowEffect)
    assert AMBER not in cards[1].styleSheet() and cards[1].graphicsEffect() is None
    cards[1].setFocus()
    qapp.processEvents()
    assert cards[0].graphicsEffect() is None and AMBER not in cards[0].styleSheet()


def test_a_focused_pill_is_dimmed(page, qapp):
    _, cards, pill = page
    pill.setFocus()
    qapp.processEvents()
    assert isinstance(pill.graphicsEffect(), QGraphicsOpacityEffect)
    assert pill.graphicsEffect().opacity() == portable.DIMMED
    cards[0].setFocus()
    qapp.processEvents()
    assert pill.graphicsEffect() is None
    assert pill.sizeHint().width() >= pill.layout().sizeHint().width()     # the label is never cut off


def test_the_d_pad_moves_to_the_nearest_one(page, qapp):
    window, cards, pill = page
    focused = qapp.focusWidget()
    if focused is not None:
        focused.clearFocus()
    assert window.move_focus("down") is cards[0]                          # none had it: the first
    assert window.move_focus("right") is cards[1]
    assert window.move_focus("right") is cards[1]                         # nothing further: it stays
    assert window.move_focus("down") is cards[3]
    assert window.move_focus("left") is cards[2]
    assert window.move_focus("down") is pill
    assert window.move_focus("up") in (cards[2], cards[3])


def test_nearest_goes_straight_before_sideways(page):
    _, cards, _ = page
    assert nearest(cards[0], cards, "down") is cards[2]                   # not the diagonal card 3
    assert nearest(cards[0], cards, "up") is None


def test_a_and_b_and_a_pages_own_buttons(page, qapp, monkeypatch):
    window, cards, pill = page
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    opened, details, backs = [], [], []
    cards[1].activated.connect(lambda: opened.append("card"))
    pill.activated.connect(lambda: opened.append("pill"))
    window.back.connect(lambda: backs.append(True))
    window.bind("x", lambda: details.append(True))
    cards[1].setFocus()
    window.on_action("accept")
    window.on_action("down")                                               # card 3, then the pill
    window.on_action("down")
    window.on_action("accept")
    window.on_action("x")
    window.on_action("y")                                                  # not bound on this page: nothing
    window.on_action("back")
    assert opened == ["card", "pill"] and details == [True] and backs == [True]


def test_the_controller_counts_only_while_the_window_is_active(page, monkeypatch):
    window, cards, _ = page
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    opened = []
    cards[0].activated.connect(lambda: opened.append(True))
    cards[0].setFocus()
    window.on_action("accept")
    window.on_action("right")
    assert opened == [] and cards[0].hasFocus()


def test_the_keyboard_and_touch(page, qapp):
    window, cards, _ = page
    opened, backs = [], []
    cards[0].activated.connect(lambda: opened.append(True))
    window.back.connect(lambda: backs.append(True))
    cards[0].setFocus()
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier))
    assert cards[1].hasFocus()
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert backs == [True]
    cards[0].keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
    assert opened == [True]
    from PyQt6.QtTest import QTest
    QTest.mouseClick(cards[2], Qt.MouseButton.LeftButton, pos=QPoint(10, 10))     # a first tap: the focus
    assert cards[2].hasFocus() and opened == [True]
    QTest.mouseClick(cards[2], Qt.MouseButton.LeftButton, pos=QPoint(10, 10))     # a second tap: the action
    assert opened == [True]
    cards[2].activated.connect(lambda: opened.append("tap"))
    QTest.mouseClick(cards[2], Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    assert opened == [True, "tap"]


def test_the_legend_has_no_amber_glyph(qapp):
    """A, the amber one, is on the page's main pill; the legend shows the buttons that have none."""
    legend = Legend([("X", "Details"), ("B", "Back")])
    glyphs = [w for w in legend.findChildren(portable.Glyph)]
    assert [g.text() for g in glyphs] == ["X", "B"] and not any(AMBER in g.styleSheet() for g in glyphs)
    legend.set_items([("B", "Back")])
    assert legend.items == [("B", "Back")]


def test_the_header(qapp):
    header = PortableHeader("Windows Portable Test", "0.1.0")
    header.set_status(["82 %", "", "14:32"])
    assert header.title.text() == "Windows Portable Test" and header.version.text() == "0.1.0"
    assert header.status.text() == "82 %  |  14:32"
    assert header.icon is None                                  # no icon unless one is given (owner, 27-10-2026)
    icon = QPixmap(8, 8)
    icon.fill()
    assert PortableHeader("Portal", "0.1.0", icon).icon is not None


def test_the_main_pill_has_the_button_color(qapp):
    """Only the main pill takes #cd8b22 (owner, 27-10-2026, a trial); the focus stays amber, a gray pill gray."""
    main, other = Pill("Open", "A", main=True), Pill("Update", "Y")
    assert portable.BUTTON == "#cd8b22" and f"color: {portable.BUTTON};" in main.glyph.styleSheet()
    assert portable.BUTTON not in other.glyph.styleSheet()
