# SPDX-License-Identifier: GPL-3.0-or-later
"""The portable window (portable.py): the design's sizes on any screen, a card's focus, the pill's, moving the focus
with the d-pad or the arrow keys, A and B, a page's own buttons, the legend whose entries act on a tap, the tabs, and
the controller only while the window is active."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QEnterEvent, QKeyEvent, QPixmap
from PyQt6.QtWidgets import (QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QVBoxLayout,
                             QWidget)

from bc250_core import portable
from bc250_core.portable import AMBER, Card, Legend, Pill, PortableHeader, PortableWindow, nearest


class NoPad:
    def events(self):
        return []

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def mockup_scale():
    portable.pin_scale((1280, 720))     # the mock-up's screen, not the offscreen one
    portable.glass(255)
    yield
    portable.pin_scale((1280, 720))
    portable.glass(255)


def test_the_sizes_follow_the_screen():
    """The mock-up is 1280 x 720: the Ally's screen at 150 % is that, a TV at 125 % is 1536 x 864 (1.2 times)."""
    assert portable.scale((1280, 720)) == 1 and portable.px(14) == 14
    assert portable.scale((1536, 864)) == pytest.approx(1.2) and portable.px(14) == 17
    assert portable.scale((2560, 1080)) == pytest.approx(1.5)              # the smaller ratio: it fits
    assert portable.scale((1024, 600)) == pytest.approx(0.8)               # smaller: it fits (owner, 28-10-2026)
    assert portable.scale((1097, 617)) == pytest.approx(0.857, abs=1e-3)   # a 1080p screen at 175 %
    assert portable.scale((400, 300)) == portable.MIN_SCALE                # never too small to read
    portable.scale((1280, 720))
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


def test_a_tap_on_a_legend_entry_does_what_its_button_does(qapp, monkeypatch):
    """The bottom row is for actions (owner, 29-10-2026): an entry tapped runs the window's handler for its button,
    B its back, and the same entries set again leave the row as it is (a page refreshes while it downloads)."""
    from PyQt6.QtGui import QMouseEvent
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    column = QVBoxLayout(window)
    legend = Legend([("X", "Details"), ("Y", "Update"), ("LB", "Folders"), ("B", "Back")])
    column.addWidget(legend)
    window.show()
    qapp.processEvents()
    done, backs = [], []
    window.bind("x", lambda: done.append("x"))
    window.bind("previous", lambda: done.append("previous"))
    window.back.connect(lambda: backs.append(True))
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)   # a tap counts, whatever the controller's rule
    entry = legend.entries["X"]
    press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(5, 5), QPointF(5, 5), Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    entry.mousePressEvent(press)
    legend.entries["LB"].pressed.emit()
    legend.entries["B"].pressed.emit()
    legend.entries["Y"].pressed.emit()                                     # no handler bound: nothing happens
    assert done == ["x", "previous"] and backs == [True]
    assert entry.minimumSizeHint().height() > portable.px(26)                # taller than the glyph: a finger's target
    before = list(legend.entries.values())
    legend.set_items(legend.items)
    assert list(legend.entries.values()) == before                          # the same again: untouched
    legend.set_items([("B", "Close")])
    assert list(legend.entries) == ["B"] and legend.entries["B"].label.text() == "Close"
    window.close()


def test_an_icon_pill_shows_its_focus_in_amber(qapp):
    """Dimmed as a pill is, it was hard to see which icon was active (owner, 29-10-2026): with the focus, the ring and
    the sign are amber."""
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    line = QHBoxLayout(window)
    card, info = Card("Card", "What it does."), portable.InfoPill("Title", "Text.")
    line.addWidget(card)
    line.addWidget(info)
    window.resize(600, 300)
    window.show()
    window.activateWindow()
    qapp.processEvents()
    plain = info.grab().toImage()
    info.setFocus()
    qapp.processEvents()
    focused = info.grab().toImage()
    side = info.width()
    ring = [focused.pixelColor(side // 2, y) for y in range(1, 5)]           # the ring, drawn with antialiasing
    assert any(abs(c.red() - 0xF5) <= 2 and abs(c.green() - 0xA5) <= 2 and abs(c.blue() - 0x24) <= 2 for c in ring)
    before = [plain.pixelColor(side // 2, y) for y in range(1, 5)]
    assert any(c.red() > 0xE0 and c.green() > 0xE0 and c.blue() > 0xE0 for c in before)      # TEXT, no amber
    assert info.graphicsEffect() is None                                     # drawn, not dimmed
    window.close()


def test_tabs_step_round_and_tell_their_change(qapp):
    """The portal's tabs are core's (29-10-2026, for a page's parts too): LB and RB step round, a tap selects, the
    selected one is amber."""
    tabs = portable.Tabs([("a", "First"), ("b", "Second"), ("c", "Third")])
    seen = []
    tabs.changed.connect(seen.append)
    assert tabs.current == "a" and tabs.keys == ["a", "b", "c"]
    tabs.step(1)
    tabs.step(-1)
    tabs.step(-1)
    assert seen == ["b", "a", "c"] and tabs.current == "c"
    tabs.select("c")                                                         # the same again: no change told
    tabs.labels["b"].pressed.emit("b")                                       # a tap
    assert seen == ["b", "a", "c", "b"]
    assert AMBER in tabs.labels["b"].styleSheet() and AMBER not in tabs.labels["a"].styleSheet()


def test_the_header(qapp):
    header = PortableHeader("Windows Portable Test", "0.1.0")
    header.set_status(["82 %", "", "14:32"])
    assert header.title.text() == "Windows Portable Test" and header.version.text() == "0.1.0"
    assert header.status.text() == "82 %  |  14:32"
    assert header.icon is None                                  # no icon unless one is given (owner, 27-10-2026)
    icon = QPixmap(8, 8)
    icon.fill()
    assert PortableHeader("Portal", "0.1.0", icon).icon is not None


def test_every_pill_is_the_same(qapp):
    """One kind of pill everywhere (owner, 29-10-2026): amber with dark text, the glyph's letter amber on dark, the
    same height and minimum width with a button or without one (touch only); disabled it is gray."""
    main, other, touch = Pill("Open", "A", main=True), Pill("Update", "Y"), Pill("Folders")
    for pill in (main, other, touch):
        assert pill.minimumHeight() == portable.px(portable.PILL_HEIGHT)
        assert pill.minimumWidth() == portable.px(portable.PILL_WIDTH)
        assert f"color: {portable.ON_AMBER};" in pill.label.styleSheet()
    assert main.glyph.colors == other.glyph.colors == (portable.BUTTON, portable.ON_AMBER)
    assert touch.glyph is None
    other.setEnabled(False)
    assert f"color: {portable.DIM};" in other.label.styleSheet() and other.glyph.colors[0] == portable.DIM
    other.setEnabled(True)
    assert f"color: {portable.ON_AMBER};" in other.label.styleSheet()


def test_hover_dims_a_pill_as_the_focus_does(qapp, monkeypatch):
    pill = Pill("Open", "A", main=True)
    assert pill.graphicsEffect() is None
    monkeypatch.setattr(pill, "underMouse", lambda: True)
    pill.enterEvent(QEnterEvent(QPointF(), QPointF(), QPointF()))
    assert isinstance(pill.graphicsEffect(), QGraphicsOpacityEffect)
    assert pill.graphicsEffect().opacity() == pytest.approx(portable.DIMMED)
    monkeypatch.setattr(pill, "underMouse", lambda: False)
    pill.leaveEvent(QEvent(QEvent.Type.Leave))
    assert pill.graphicsEffect() is None
    pill.setEnabled(False)
    monkeypatch.setattr(pill, "underMouse", lambda: True)
    pill.enterEvent(QEnterEvent(QPointF(), QPointF(), QPointF()))
    assert pill.graphicsEffect() is None                                    # a disabled pill does not answer


def test_a_row_is_a_row_and_pills_sit_at_the_bottom_right(qapp):
    row = portable.Row("Renderer: Automatic")
    assert row.height() == portable.px(portable.ROW_HEIGHT) or row.maximumHeight() == portable.px(portable.ROW_HEIGHT)
    assert f"color: {portable.TEXT};" in row.label.styleSheet() and row.glyph is None
    assert bool(row.label.alignment() & Qt.AlignmentFlag.AlignLeft)
    a, y = Pill("Save", "A", main=True), Pill("Remove", "Y")
    line = portable.pill_row(y, a)
    assert line.itemAt(0).spacerItem() is not None                          # right-aligned
    assert [line.itemAt(i).widget() for i in (1, 2)] == [y, a]              # the A pill rightmost


def test_the_pane_with_the_focus_reads_as_one_with_its_card(qapp, monkeypatch):
    """Where you are (owner, 29-10-2026): the focus in a pane gives it the amber edge and glow, and its card keeps the
    edge without the glow; back on the cards, the pane is plain again."""
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    window.setFixedSize(900, 500)
    line = QHBoxLayout(window)
    card, other = Card("Card", "What it does."), Card("Other", "Too.")
    cards = QVBoxLayout()
    cards.addWidget(card)
    cards.addWidget(other)
    line.addLayout(cards)
    pane = portable.Pane()
    row = portable.Row("A row")
    pill = Pill("Open", "A", main=True)
    pane.column.addWidget(row)
    pane.column.addWidget(pill)
    line.addWidget(pane)
    window.show()
    window.activateWindow()
    qapp.processEvents()
    card.setFocus()
    qapp.processEvents()
    assert not pane.active and f"solid {portable.AMBER}" not in pane.styleSheet() and not card.selected
    row.setFocus()
    qapp.processEvents()
    assert pane.active and f"solid {portable.AMBER}" in pane.styleSheet()
    assert isinstance(pane.graphicsEffect(), QGraphicsDropShadowEffect)    # the glow
    assert card.selected and card.graphicsEffect() is None and f"solid {portable.AMBER}" in card.styleSheet()
    pill.setFocus()
    qapp.processEvents()
    assert pane.active and card.selected
    other.setFocus()
    qapp.processEvents()
    assert not pane.active and pane.graphicsEffect() is None and not card.selected
    assert f"solid {portable.AMBER}" not in card.styleSheet()
    window.close()


def test_a_switch_inside_a_switch_leaves_one_page_visible(qapp):
    """The text of one pane on another (owner, 29-10-2026, seen in PCSX2 Manager and PPSSPP Manager): a switch away
    from the page with the focus hands the focus to a card, whose own pane is switched to in that moment, inside the
    first switch; QStackedLayout then left both pages visible, the see-through one over the other. One stays."""
    from PyQt6.QtCore import QObject
    from PyQt6.QtWidgets import QStackedWidget

    class SwitchWhenHidden(QObject):                # the card that takes the focus shows its own pane, then and there
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.Hide and stack.currentWidget() is not own:
                stack.setCurrentWidget(own)
            return False
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    window.setFixedSize(900, 500)
    line = QHBoxLayout(window)
    stack = QStackedWidget()
    own, focused, other = portable.Pane(), portable.Pane(), portable.Pane()
    for page in (own, focused, other):
        stack.addWidget(page)
    line.addWidget(stack)
    window.show()
    qapp.processEvents()
    stack.setCurrentWidget(focused)
    qapp.processEvents()
    hidden = SwitchWhenHidden()
    focused.installEventFilter(hidden)
    stack.setCurrentWidget(other)                                     # a switch, with one inside it
    qapp.processEvents()
    assert [page for page in (own, focused, other) if page.isVisible()] == [stack.currentWidget()]
    window.close()


def test_the_info_pill_shows_its_text_over_the_window(qapp, monkeypatch):
    """More text than fits goes behind an "i" (owner, 28-10-2026): Menu or a tap opens it, A, B, Menu or Escape
    closes it, and the focus goes back where it was. The icon is touch only (owner, 29-10-2026): the d-pad skips it."""
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    window.setFixedSize(800, 500)
    column = QVBoxLayout(window)
    card = Card("Card", "What it does.")
    info = portable.InfoPill("The back buttons", "A long explanation.")
    column.addWidget(card)
    column.addWidget(info)
    window.show()
    qapp.processEvents()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    backs = []
    window.back.connect(lambda: backs.append(True))
    assert info.width() == info.height() == portable.px(32)
    assert info not in window.focusables()
    card.setFocus()
    window.on_action("menu")
    popup = window.popup
    assert popup is not None and popup.geometry() == window.rect()
    assert popup.text.toPlainText() == "A long explanation."
    assert popup.legend.items == [("B", "Close")] and not popup.findChildren(Pill)   # no big amber pill
    assert not popup.pills() and card.hasFocus()                           # a short text: nothing to scroll
    window.on_action("up")                                                 # the popup has the buttons
    window.on_action("back")
    assert window.popup is None and backs == [] and card.hasFocus()
    info.click()                                                           # a tap
    assert window.popup is not None
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert window.popup is None and backs == []
    window.on_action("back")
    assert backs == [True]                                                 # no popup: B is the page's again
    window.close()


def test_glass_lets_a_wallpaper_shine_through(qapp):
    """A window with a wallpaper makes its cards and panes see-through (owner, 28-10-2026); a focused card stays
    solid, so its amber glow does not tint it, and an InfoPopup's panel stays solid to read."""
    assert portable.glass() == 255 and portable.surface(portable.SURFACE) == portable.SURFACE
    try:
        portable.glass(200)
        assert portable.surface(portable.SURFACE) == "rgba(29, 30, 34, 200)"
        card, pane = Card("Card", "What it does."), portable.Pane()
        assert "rgba(29, 30, 34, 200)" in card.styleSheet() and "rgba(29, 30, 34, 200)" in pane.styleSheet()
        card._paint(True)
        assert portable.RAISED in card.styleSheet()
        window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
        popup = window.show_popup("Title", "Text.")
        assert "rgba" not in popup.panel.styleSheet()
        window.close()
    finally:
        portable.glass(255)


def test_a_pinned_scale_is_kept_by_a_window(qapp):
    portable.pin_scale((1536, 864))
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    assert portable.scale() == pytest.approx(1.2)                          # not the offscreen screen's
    window.close()
    portable.pin_scale(None)
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    screen = qapp.primaryScreen().geometry()
    assert portable.scale() == pytest.approx(max(portable.MIN_SCALE, min(screen.width() / 1280, screen.height() / 720)))
    window.close()


def test_the_wallpaper_is_the_suites(qapp, tmp_path):
    """Every window of a suite shows the wallpaper unless the suite switched it off (owner, 29-10-2026: "available
    throughout the suite"); a window of no suite shows none."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    plain = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    assert not plain.shows_wallpaper() and portable.glass() == 255
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad), suite="x-suite")
    assert window.shows_wallpaper() and portable.glass() == portable.GLASS
    assert portable.WALLPAPER.is_file()
    card = Card("Card", "What it does.")
    window.set_wallpaper(False)
    assert not portable.wallpaper_on("x-suite") and portable.glass() == 255
    assert (tmp_path / "x-suite" / "suite.ini").is_file()
    other = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad), suite="x-suite")
    assert not other.shows_wallpaper()                                     # another app of the suite: off too
    for w in (plain, window, other):
        w.close()
    card.close()


def test_the_focused_row_is_raised_with_an_amber_edge(qapp):
    """In a list the row with the focus stands out (owner, 29-10-2026): lighter, with the amber edge."""
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    column = QVBoxLayout(window)
    row, other = portable.Row("Renderer: Automatic"), portable.Row("Aspect: 16:9")
    column.addWidget(row)
    column.addWidget(other)
    window.resize(400, 200)
    window.show()
    window.activateWindow()
    row.setFocus()
    qapp.processEvents()
    focused, plain = row.grab().toImage(), other.grab().toImage()
    beside = row.width() - portable.px(8)                                  # right of the text, which is left-aligned
    assert focused.pixelColor(beside, row.height() // 2).name() == portable.ROW_FOCUS
    assert plain.pixelColor(beside, other.height() // 2).name() == portable.RAISED
    assert focused.pixelColor(row.width() // 2, 0).name() == AMBER         # the edge
    window.close()


def test_a_pane_in_a_stack_glows_on_the_stack(qapp):
    """The stack is as big as its pane: on the pane, the glow would be cut off at the stack's edges."""
    from PyQt6.QtWidgets import QStackedWidget
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    line = QHBoxLayout(window)
    card = Card("Card", "What it does.")
    line.addWidget(card)
    stack = QStackedWidget()
    first, second = portable.Pane(), portable.Pane()
    row = portable.Row("A row")
    first.column.addWidget(row)
    stack.addWidget(first)
    stack.addWidget(second)
    line.addWidget(stack)
    window.resize(900, 500)
    window.show()
    window.activateWindow()
    row.setFocus()
    qapp.processEvents()
    assert first.active and isinstance(stack.graphicsEffect(), QGraphicsDropShadowEffect)
    assert first.graphicsEffect() is None
    card.setFocus()
    qapp.processEvents()
    assert stack.graphicsEffect() is None and not first.active
    window.close()


def test_a_glyph_paints_a_circle_not_a_square(qapp):
    """On the Ally a QLabel's stylesheet border-radius showed a black square (owner, 29-10-2026): Glyph paints its
    circle itself, so its corners stay clear."""
    pill = Pill("Open", "A", main=True)
    for glyph in (portable.Glyph("A"), pill.glyph, portable.Glyph("LB", filled=True)):
        image = glyph.grab().toImage()
        assert image.pixelColor(0, 0).alpha() == 0 and image.pixelColor(image.width() - 1, image.height() - 1).alpha() == 0
        middle = image.pixelColor(image.width() // 2, 1)
        assert middle.alpha() == 255 and middle.name() == glyph.colors[1]


def test_a_popup_holds_pills_and_keeps_the_focus(qapp, monkeypatch):
    """A popup with controls (owner, 29-10-2026): the d-pad moves between its pills and Close only, A presses the
    focused one, B closes it and the focus goes back."""
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    line = QHBoxLayout(window)
    outside = Pill("Outside", "A", main=True)
    line.addWidget(outside)
    window.resize(1280, 720)
    window.show()
    window.activateWindow()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    pressed = []
    content = QWidget()
    row = QHBoxLayout(content)
    one, two = Pill("One", "A"), Pill("Two", "A")
    one.activated.connect(lambda: pressed.append("one"))
    two.activated.connect(lambda: pressed.append("two"))
    row.addWidget(one)
    row.addWidget(two)
    popup = window.show_popup("Title", "Text.", outside, content)
    qapp.processEvents()
    assert one.hasFocus() and outside not in window.focusables()
    window.on_action("right")
    assert two.hasFocus()
    window.on_action("accept")
    assert pressed == ["two"] and window.popup is popup             # A presses, the popup stays
    window.on_action("down")
    assert two.hasFocus()                                           # nothing below the rows: the legend's B Close
    popup.legend.entries["B"].pressed.emit()                        # a tap on B Close
    assert window.popup is None and outside.hasFocus()
    window.close()


def test_a_long_popup_text_scrolls(qapp, monkeypatch):
    """A long information text was cut off (owner, 29-10-2026): the popup's text is at most half the window high and
    the d-pad's up and down scroll it."""
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    window.resize(1280, 720)
    window.show()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    text = "\n\n".join(f"Paragraph {n}: a line of what the page does, long enough to wrap once or twice in the "
                        "popup's panel at the handheld's size." for n in range(40))
    popup = window.show_popup("Title", text)
    qapp.processEvents()
    assert popup.text.height() <= 720 * portable.POPUP_TEXT and popup.text.scrolls()
    assert popup.text.hasFocus() and popup.pills() == [popup.text]
    bar = popup.text.verticalScrollBar()
    assert bar.value() == 0
    window.on_action("down")
    assert bar.value() > 0 and window.popup is popup
    window.on_action("up")
    assert bar.value() == 0
    window.on_action("accept")                                      # A still closes it
    assert window.popup is None
    window.close()


def test_a_popup_legend_names_its_actions(qapp):
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    content = QWidget()
    QHBoxLayout(content).addWidget(portable.Row("Red"))
    popup = window.show_popup("Title", "Text.", None, content, [("A", "Show")])
    assert popup.legend.items == [("A", "Show"), ("B", "Close")]
    window.close()


def test_a_card_shows_a_red_dot_for_an_update(qapp):
    """The portal's tile of an app with an update shows a red dot (owner, 29-10-2026)."""
    card = Card("Card", "Installed 1.0.0")
    card.resize(293, 176)
    plain = card.grab().toImage()
    card.set_dot(True)
    dotted = card.grab().toImage()
    x = card.width() - portable.px(portable.DOT_INSET) - portable.px(portable.DOT_SIZE) // 2
    y = portable.px(portable.DOT_INSET) + portable.px(portable.DOT_SIZE) // 2
    assert dotted.pixelColor(x, y).name() == portable.DOT and plain.pixelColor(x, y).name() != portable.DOT
    card.set_dot(False)
    assert card.grab().toImage().pixelColor(x, y).name() != portable.DOT


def test_the_suite_sound_switch(qapp):
    suite = "test-suite-sound"
    portable.look_settings(suite).remove(portable.SOUND_KEY)
    assert portable.sound_on(suite)
    portable.set_sound_on(suite, False)
    assert not portable.sound_on(suite)
    portable.set_sound_on(suite, True)
    assert portable.sound_on(suite)


def test_the_light_icon_is_drawn_as_the_info_icon(qapp):
    light, info = portable.LightPill(), portable.InfoPill("Title", "Text.")
    assert light.size() == info.size() and not light.label.isVisible()
    assert light.grab().toImage() != info.grab().toImage()


def test_closing_a_popup_gives_the_focus_back_before_it_hides(qapp, monkeypatch):
    """Hidden while a pill in it had the focus, Qt handed the focus to the first card, which showed its own pane."""
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    line = QHBoxLayout(window)
    card, icon = Card("Card", "What it does."), Pill("Icon", "A")
    line.addWidget(card)
    line.addWidget(icon)
    window.resize(1280, 720)
    window.show()
    window.activateWindow()
    qapp.processEvents()
    seen = []
    card.focused.connect(lambda: seen.append("card"))
    icon.setFocus()
    qapp.processEvents()
    window.show_popup("Title", "Text.", icon).dismiss()
    qapp.processEvents()
    assert icon.hasFocus() and seen == []
    window.close()


def test_b_goes_back_view_exits_and_menu_shows_the_information(qapp, monkeypatch):
    """Every window's buttons (owner, 29-10-2026: "Close" on B was not clear): B in a pane goes back to its card and
    does nothing on a card; View is Exit app; Menu opens the information icon of the pane that shows (and closes it
    again). The legend's last entries follow the focus: Menu Info, B Back while B can act, View Exit app."""
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    window.setFixedSize(900, 500)
    line = QHBoxLayout(window)
    card = Card("Card", "Its pane.")
    line.addWidget(card)
    pane = portable.Pane()
    info = portable.InfoPill("About it", "What the pane does.")
    pill = Pill("Open", "A", main=True)
    pane.column.addWidget(info)
    pane.column.addWidget(pill)
    line.addWidget(pane)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.back.connect(window.go_back)
    window.show()
    window.activateWindow()
    qapp.processEvents()
    card.setFocus()
    qapp.processEvents()
    assert window.common_items() == [portable.INFO, portable.EXIT] and not window.go_back()
    pill.setFocus()
    qapp.processEvents()
    assert window.common_items() == [portable.INFO, portable.BACK, portable.EXIT]
    window.act("menu")
    assert window.popup is not None and window.popup.text.toPlainText() == "What the pane does."
    window.act("menu")
    assert window.popup is None
    window.act("back")
    qapp.processEvents()
    assert card.hasFocus() and closed == []
    window.act("back")                                                # on the card: nothing
    assert card.hasFocus() and closed == []
    window.act("view")
    assert closed == [True]
    window.close()


def test_the_focus_stays_in_the_pane_until_b(qapp):
    """Working in a pane, the d-pad stays in it (owner, 29-10-2026: at the top or bottom of a list the focus jumped
    back to the cards); only B goes back to the card. From a card the d-pad still reaches the other cards."""
    window = PortableWindow(gamepad=portable.Gamepad(source_factory=NoPad))
    window.setFixedSize(900, 500)
    line = QHBoxLayout(window)
    cards = QVBoxLayout()
    card, other = Card("Card", "Its pane."), Card("Other", "Another.")
    cards.addWidget(card)
    cards.addWidget(other)
    line.addLayout(cards)
    pane = portable.Pane()
    first, second = portable.Row("First"), portable.Row("Second")
    pane.column.addWidget(first)
    pane.column.addWidget(second)
    line.addWidget(pane)
    window.back.connect(window.go_back)
    window.show()
    window.activateWindow()
    qapp.processEvents()
    card.setFocus()
    qapp.processEvents()
    window.act("down")
    assert other.hasFocus()                                           # from a card: the next card
    card.setFocus()
    first.setFocus()
    qapp.processEvents()
    for direction in ("up", "left", "up"):                            # the top, and the cards to the left: stays
        window.act(direction)
        assert first.hasFocus(), direction
    window.act("down")
    window.act("down")                                                # the bottom: stays
    assert second.hasFocus()
    window.act("back")
    qapp.processEvents()
    assert card.hasFocus()                                            # only B goes back
    window.close()
