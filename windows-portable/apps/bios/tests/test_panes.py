# SPDX-License-Identifier: GPL-3.0-or-later
"""The panes (panes.py): a menu's list reaches its top and its end from its first and last rows, a long subtitle
wraps to the pane's width, and the line under the list keeps its height (owner, 01-11-2026)."""

from __future__ import annotations

from bc250_core import portable
from bios_reader.hii import Statement
from bios_reader.panes import ScreenPane
from bios_reader.screens import Entry

WARNING = "WARNING - DAMAGE CAUSED BY USE OF YOUR AMD PROCESSOR OUTSIDE OF SPECIFICATION " * 6


def menu(qapp, heading: str = WARNING) -> ScreenPane:
    portable.scale((1280, 720))
    pane = ScreenPane("About")
    pane.resize(800, 420)
    lines = [Entry(heading + "\r\nOperating your AMD processor ...")]
    lines += [Entry(f"Row {n}", statement=Statement("ref", f"Row {n}")) for n in range(12)]
    lines += [Entry(f"After {n}") for n in range(4)]                 # text after the last row
    pane.list.set_entries(lines)
    pane.show()
    qapp.processEvents()
    return pane


def in_view(pane: ScreenPane, widget) -> bool:
    shown = widget.geometry().translated(0, -pane.list.verticalScrollBar().value())
    return pane.list.viewport().rect().contains(shown)


def test_the_first_and_last_rows_show_the_lists_ends(qapp):
    pane = menu(qapp, "Short")
    bar = pane.list.verticalScrollBar()
    rows = list(pane.list.pills.values())
    assert bar.maximum() > 0
    rows[-1].setFocus()
    qapp.processEvents()
    assert bar.value() == bar.maximum() and in_view(pane, pane.list.widgets[-1])   # the lines after it show
    rows[0].setFocus()
    qapp.processEvents()
    assert bar.value() == 0 and in_view(pane, pane.list.widgets[0])                # the subtitle above it
    pane.close()


def test_the_first_row_stays_in_view_under_a_tall_subtitle(qapp):
    pane = menu(qapp)
    rows = list(pane.list.pills.values())
    rows[-1].setFocus()
    qapp.processEvents()
    rows[0].setFocus()
    qapp.processEvents()
    assert in_view(pane, rows[0])                   # as much of the warning above it as the view leaves room for
    assert pane.list.verticalScrollBar().value() < pane.list.widgets[0].height()
    pane.close()


def test_a_long_subtitle_wraps_and_the_line_keeps_its_height(qapp):
    pane = menu(qapp)
    heading = pane.list.widgets[0]
    assert heading.wordWrap() and "\r" not in heading.text()
    assert heading.width() <= pane.list.viewport().width()
    height = pane.line.height()
    pane.line.setText("A help text long enough to wrap over more lines than the two the line has room for. " * 5)
    qapp.processEvents()
    assert pane.line.height() == height == pane.line.fontMetrics().lineSpacing() * 2
    pane.close()
