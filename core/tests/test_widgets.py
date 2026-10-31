# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from PyQt6 import sip
from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPushButton, QTabBar, QTableWidget, QTableWidgetItem,
                             QWidget)

from bc250_core import theme
from bc250_core.widgets import (
    AppHeader, MetricBox, Pill, RoundedToolTip, StatusPill, StatusText, Terminal, TextDialog, accent_button,
    hide_tooltip, same_width, set_button_active, show_tooltip,
)


def test_status_pill_colours(qapp):
    """The theme's surface; the state a colored left edge, the edge's color for neutral."""
    pill = StatusPill()
    assert pill.text() == "Unknown"
    assert f"border-left:4px solid {theme.THEME.edge}" in pill.styleSheet()
    pill.set_status("Active", "ok", "tip")
    assert (pill.text(), pill.toolTip()) == ("Active", "tip")
    assert f"border-left:4px solid {theme.GREEN}" in pill.styleSheet()
    assert "white" not in pill.styleSheet()                                     # the theme's text color
    pill.set_status("?", "no-such-kind")
    assert f"border-left:4px solid {theme.THEME.edge}" in pill.styleSheet()


def test_status_text_colours(qapp):
    status = StatusText()
    assert status.text() == "Unknown" and "palette(window-text)" in status.label.styleSheet()
    status.set_status("Test failed", "bad", "tip")
    assert (status.text(), status.toolTip(), status.kind) == ("Test failed", "tip", "bad")
    assert theme.RED in status.label.styleSheet() and theme.RED in status.dot.styleSheet()
    assert "font-weight:700" in status.label.styleSheet()
    status.set_status("Not installed", "warn")
    assert theme.ORANGE in status.label.styleSheet()
    status.set_status("?", "no-such-kind")
    assert "palette(window-text)" in status.label.styleSheet()


def test_metric_box(qapp):
    box = MetricBox("GPU clock", theme.PURPLE)
    box.set_value("1800 MHz", "now")
    assert (box.value.text(), box.caption.text(), box.toolTip()) == ("1800 MHz", "GPU clock", "now")
    centre = Qt.AlignmentFlag.AlignHCenter
    assert box.value.alignment() & centre and box.caption.alignment() & centre        # centered by default
    left = MetricBox("GPU clock", theme.PURPLE, centred=False)
    assert not left.value.alignment() & centre
    assert f"border-left:4px solid {theme.PURPLE}" in box.styleSheet()
    box.set_colour(theme.RED)
    assert f"border-left:4px solid {theme.RED}" in box.styleSheet() and theme.PURPLE not in box.styleSheet()
    assert f"border-left:4px solid {theme.BLUE}" in MetricBox("Neutral").styleSheet()   # GRAY: the suite's blue
    assert theme.THEME.edge not in MetricBox("Neutral").styleSheet().split("border-left")[1].split(";")[0]


def test_pill_is_a_metric_box_that_clicks(qapp):
    """A click, Enter or Space emits clicked; the accent edge under the mouse or the keyboard focus."""
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent
    pill = Pill("Refresh", "Click to refresh", "tip")
    assert (pill.value.text(), pill.caption.text(), pill.toolTip()) == ("Refresh", "Click to refresh", "tip")
    assert f"#pill:hover, #pill:focus {{ border-color:{theme.ACCENT}; }}" in pill.styleSheet()
    clicks = []
    pill.clicked.connect(lambda: clicks.append(1))
    pill.click()
    for key in (Qt.Key.Key_Space, Qt.Key.Key_Return):
        pill.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))
    assert clicks == [1, 1, 1]
    pill.set_colour(theme.RED)                                  # the edge color and the hover both stay
    assert theme.RED in pill.styleSheet() and "#pill:hover" in pill.styleSheet()


def _text_lightness(pill: Pill) -> int:
    """The bright end of the pill's text on its dark surface (inside the border; the 20th brightest pixel)."""
    image = pill.grab().toImage()
    return sorted(image.pixelColor(x, y).lightness() for x in range(10, image.width() - 10)
                  for y in range(6, image.height() - 6))[-20]


def test_a_pill_that_cannot_be_clicked_looks_muted(qapp):
    """Only a disabled pill's text is muted (a rule on the pill's own state would mute every pill: Qt ignores an
    ancestor's pseudo-state); enabled again, it is bright again."""
    row = QWidget()
    layout = QHBoxLayout(row)
    enabled, disabled = Pill("Update", "Firmware"), Pill("Update", "Firmware")
    disabled.setEnabled(False)
    for pill in (enabled, disabled):
        layout.addWidget(pill)
    row.show()
    qapp.processEvents()
    assert _text_lightness(disabled) < _text_lightness(enabled)
    disabled.setEnabled(True)
    disabled.set_colour(theme.RED)                              # the rule survives a new color
    qapp.processEvents()
    assert _text_lightness(disabled) == _text_lightness(enabled)
    disabled.setEnabled(False)
    qapp.processEvents()
    assert _text_lightness(disabled) < _text_lightness(enabled)
    row.close()


def test_same_width_follows_the_widest(qapp):
    boxes = [Pill("A", "a"), MetricBox("Caption"), Pill("No", "Icons on Desktop")]
    same_width(boxes)
    widths = {b.minimumWidth() for b in boxes}
    assert len(widths) == 1 and widths.pop() >= max(b.sizeHint().width() for b in boxes)
    boxes[1].set_value("A much longer value than any other")    # a value grows: every box with it
    wide = boxes[1].sizeHint().width()
    assert {b.minimumWidth() for b in boxes} == {wide} and wide > MetricBox.MIN_WIDTH
    boxes[1].set_value("—")                                    # and shrinks back
    assert {b.minimumWidth() for b in boxes} == {max(MetricBox.MIN_WIDTH, *(b.sizeHint().width() for b in boxes))}


def test_set_button_active_keeps_height(qapp):
    button = QPushButton("Stress test")
    height = button.sizeHint().height()
    set_button_active(button, True)
    assert theme.ACTIVE_RED in button.styleSheet()
    assert button.height() == height and button.minimumHeight() == button.maximumHeight() == height
    set_button_active(button, False)
    assert button.styleSheet() == ""


def test_accent_button(qapp):
    assert theme.ACCENT in accent_button("Apply").styleSheet()


def test_terminal_follows_end_only_when_at_end(qapp):
    term = Terminal()
    term.resize(300, 100)
    term.show()
    term.set_text("\n".join(map(str, range(200))))
    bar = term.verticalScrollBar()
    bar.setValue(bar.maximum())
    term.set_text("\n".join(map(str, range(400))))
    assert bar.value() == bar.maximum()
    bar.setValue(0)
    term.set_text("\n".join(map(str, range(600))))
    assert bar.value() == 0


def test_text_dialog(qapp):
    dialog = TextDialog("journal", "line 1\nline 2")
    assert dialog.terminal.toPlainText() == "line 1\nline 2"
    assert dialog.terminal.isReadOnly()


def test_tooltip_follows_window_and_survives_its_deletion(qapp):
    tip = RoundedToolTip(qapp)
    first = QWidget()
    first.show()
    tip.show_text(QPoint(10, 10), "hello", first)
    assert tip.popup.parentWidget() is first.window()     # Wayland: parented to the hovered window
    assert tip.popup.isVisible() and tip.label.text() == "hello"
    tip.hide()
    assert not tip.popup.isVisible()
    first.deleteLater()
    qapp.processEvents()
    qapp.sendPostedEvents(None, 0)
    second = QWidget()
    second.show()
    tip.show_text(QPoint(10, 10), "again", second)        # rebuilt when it died with the first window
    assert not sip.isdeleted(tip.popup)
    assert tip.popup.parentWidget() is second
    tip.show_text(QPoint(10, 10), "", second)
    assert not tip.popup.isVisible()


def test_long_tooltip_wraps(qapp):
    tip = RoundedToolTip(qapp)
    owner = QWidget()
    owner.show()
    tip.show_text(QPoint(0, 0), "word " * 200, owner)
    assert tip.label.wordWrap() and tip.label.width() == RoundedToolTip.MAX_WIDTH


def test_tooltip_never_covers_the_cursor(qapp):
    geo = QApplication.primaryScreen().availableGeometry()
    size = QSize(300, 200)
    below = RoundedToolTip._place(geo.topLeft() + QPoint(50, 50), size)
    assert below == geo.topLeft() + QPoint(62, 66)                # room below: below and right, as before
    corner = geo.bottomRight() - QPoint(10, 10)                   # a button low in the window, by the screen's edge
    above = RoundedToolTip._place(corner, size)
    assert not QRect(above, size).contains(corner)
    assert above.y() + size.height() < corner.y() and above.x() + size.width() < corner.x()


def test_tooltip_lets_clicks_through(qapp):
    tip = RoundedToolTip(qapp)
    assert tip.popup.windowFlags() & Qt.WindowType.WindowTransparentForInput
    owner = QWidget()
    owner.show()
    tip.show_text(QPoint(10, 10), "hello", owner)                 # also after it moved to another window
    assert tip.popup.windowFlags() & Qt.WindowType.WindowTransparentForInput


def test_item_view_tooltip_text(qapp):
    table = QTableWidget(1, 1)
    item = QTableWidgetItem("x")
    item.setToolTip("cell tip")
    table.setItem(0, 0, item)
    table.resize(200, 100)
    table.show()
    rect = table.visualItemRect(item)
    text, area = RoundedToolTip._text_at(table.viewport(), rect.center())
    assert text == "cell tip" and area == rect


def test_tab_tooltip_text(qapp):
    """A tab's tooltip (setTabToolTip) in the rounded style too (owner, 26-10-2026: the portal's tabs showed Qt's
    plain one); between the tabs the bar's own, or nothing."""
    bar = QTabBar()
    bar.addTab("One")
    bar.addTab("Two")
    bar.setTabToolTip(1, "second tip")
    bar.setExpanding(False)                                  # room beside the tabs
    bar.resize(400, 40)
    bar.show()
    rect = bar.tabRect(1)
    assert RoundedToolTip._text_at(bar, rect.center()) == ("second tip", rect)
    assert RoundedToolTip._text_at(bar, bar.tabRect(0).center()) == ("", bar.tabRect(0))
    assert RoundedToolTip._text_at(bar, QPoint(390, 20)) == (None, bar.rect())
    bar.setToolTip("the bar")
    assert RoundedToolTip._text_at(bar, QPoint(390, 20)) == ("the bar", bar.rect())


def test_tooltip_filter_is_removed_when_the_app_quits(qapp, monkeypatch):
    from PyQt6.QtCore import QObject, pyqtSignal

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


def test_manual_tooltip_uses_installed_instance(qapp, monkeypatch):
    tip = RoundedToolTip(qapp)
    monkeypatch.setattr(RoundedToolTip, "_instance", tip)
    owner = QWidget()
    owner.show()
    show_tooltip(QPoint(5, 5), "chart value", owner)
    assert tip.popup.isVisible() and tip.label.text() == "chart value"
    hide_tooltip()
    assert not tip.popup.isVisible()


def test_app_header_layout(qapp, tmp_path):
    """Icon at 96 px spanning the title row (name, version, states, actions) and the second row."""
    header = AppHeader(tmp_path / "missing.png", "BC-250 Test", "1.2.3")
    state, action, box = StatusText("Ready"), QPushButton("Refresh"), MetricBox("Load", theme.BLUE)
    header.add_state(state)
    header.add_action(action)
    second = QHBoxLayout()
    header.add_second(box, 1)
    header.add_second(second)
    window = QWidget()
    window.setLayout(header)
    assert header.logo.width() == header.logo.height() == AppHeader.LOGO_PX == 96
    assert header.logo.cursor().shape() == Qt.CursorShape.ArrowCursor
    assert "BC-250 Test" in header.title.text() and "v1.2.3" in header.title.text()
    row = [header.title_row.itemAt(i).widget() for i in range(header.title_row.count())]
    assert row[0] is header.title and row[1] is state and row[2] is None and row[3] is action   # None: stretch
    second_state = StatusText("Two")
    header.add_state(second_state)
    assert header.title_row.itemAt(2).widget() is second_state
    assert header.second_row.itemAt(0).widget() is box and header.second_row.itemAt(1).layout() is second
    assert "v" not in AppHeader(tmp_path / "x.png", "Name").title.text().replace("Name", "")
    assert isinstance(header.title, QLabel)


def test_app_header_title_lines_up_with_the_second_row(qapp, tmp_path):
    """The title's text starts where the second row's does: no padding pushes it to the right."""
    from PyQt6.QtGui import QColor
    header = AppHeader(tmp_path / "missing.png", "BC250 Suite Releases", "0.1.0")
    second = QLabel("working tree clean")
    header.add_second(second)
    window = QWidget()
    window.setStyleSheet("background:black; color:white;")
    window.setLayout(header)
    window.resize(800, 130)
    window.show()
    qapp.processEvents()
    image = window.grab().toImage()

    def first_ink(label: QLabel) -> int:
        box = label.geometry()
        return next(x for x in range(box.left(), box.right())
                    if any(QColor(image.pixel(x, y)).lightness() > 128 for y in range(box.top(), box.bottom())))

    assert header.title.x() == second.x()
    assert abs(first_ink(header.title) - first_ink(second)) <= 3     # the glyphs' own side bearing only
    window.close()


def test_a_wrapped_labels_minimum_height_follows_its_width(qapp):
    """A plain wrapped QLabel reports one line as its minimum, whatever it wraps to; a WrappedLabel reports the
    lines it needs at its width (owner, 24-10-2026: the Settings tab squeezed under a three-line introduction)."""
    from bc250_core.widgets import WrappedLabel, hint_label
    text = "A long explanation " * 30
    plain, wrapped = hint_label(text), hint_label(text, follow_height=True)
    assert isinstance(wrapped, WrappedLabel) and not isinstance(plain, WrappedLabel)
    for label in (plain, wrapped):
        label.resize(300, 10)
        label.show()
    qapp.processEvents()
    one_line = plain.fontMetrics().height()
    assert plain.minimumSizeHint().height() <= one_line + 4
    assert wrapped.minimumHeight() == wrapped.heightForWidth(300) > 3 * one_line
    wrapped.setText("Short.")
    assert wrapped.minimumHeight() <= one_line + 4
    plain.close()
    wrapped.close()


def test_an_apps_own_theme(qapp):
    """An app that is not a suite's (Nexus Releases) draws the widgets with its own theme: the surfaces, the muted
    text and the accent follow set_theme(), and create_app(theme=) sets it (owner, 26-10-2026: a Nexus app takes
    Nexus's design)."""
    from PyQt6.QtGui import QPalette
    from bc250_core import widgets
    from bc250_core.app import create_app
    from bc250_core.appinfo import AppInfo
    own = theme.Theme("Own", True, "#010101", "#0f0f0f", "#010101", "#c0c0c0", "#0f0f0f", "#010101", "#66808080",
                      "#17b6a7", "#010101")
    assert widgets.current_theme() is theme.THEME and widgets.accent() == theme.ACCENT
    try:
        app = create_app(AppInfo("x-own", "Own", "0.1.0"), theme=own)
        assert widgets.current_theme() is own and widgets.accent() == "#17b6a7"
        assert app.palette().color(QPalette.ColorRole.Window).name() == "#010101"
        box = MetricBox("Box", theme.GREEN)
        assert "stop:0 #0f0f0f, stop:1 #010101" in box.styleSheet() and "color:#c0c0c0" in box.styleSheet()
        assert f"border-left:4px solid {theme.GREEN}" in box.styleSheet()
        assert "border-color:#17b6a7" in Pill("1", "c").styleSheet()
        assert "border:2px solid #17b6a7" in accent_button("Go").styleSheet()
        assert "border-left:4px solid #66808080" in StatusPill().styleSheet()      # the own theme's edge
    finally:
        widgets.set_theme(theme.THEME)
        theme.apply_theme(qapp)
    assert f"border-left:4px solid {theme.THEME.edge}" in StatusPill().styleSheet()
