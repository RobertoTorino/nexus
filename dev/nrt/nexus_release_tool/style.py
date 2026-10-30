# SPDX-License-Identifier: GPL-3.0-or-later
"""Nexus's design for the window (owner, 26-10-2026: a Nexus app takes Nexus's look, not a suite's): the colors of
the Nexus page (nexus/docs/stylesheets/nexus.css), ink, silver and teal, as a theme for core's widgets, set with
create_app(theme=NEXUS). The states (the working tree, a build, a release) keep the state family every app shares."""

from pathlib import Path

from bc250_core.theme import Theme

INK = "#010101"                         # the window, the header, the dialogs; every other row
MAIN = "#0f0f0f"                        # the fields, lists and tables; the top of a sheen
SILVER = "#c0c0c0"                      # the text
TEAL = "#17b6a7"                        # the accent: selection, focus, hover, the main action
EDGE = "#66808080"                      # the page's dimmed silver at 40 %: borders and the neutral edge

NEXUS = Theme("Nexus", True, window=INK, base=MAIN, alt=INK, text=SILVER, button=MAIN, button_low=INK, edge=EDGE,
              accent=TEAL, accent_text=INK)

# The checkboxes (the table's ticks, the Portals column's): a teal box with a teal checkmark, as the selected tab's
# edge, where the platform's own box was dark on dark (owner, 28-10-2026).
CHECK_IMAGE = (Path(__file__).resolve().parent / "check.svg").as_posix()
CHECK_STYLESHEET = (
    "QCheckBox::indicator, QListView::indicator, QTableView::indicator { width:14px; height:14px; "
    f"border:1px solid {TEAL}; border-radius:3px; background:{MAIN}; }}"
    "QCheckBox::indicator:checked, QListView::indicator:checked, QTableView::indicator:checked { "
    f"image:url({CHECK_IMAGE}); }}"
    "QCheckBox::indicator:disabled, QListView::indicator:disabled, QTableView::indicator:disabled { "
    f"border-color:{EDGE}; }}"
)

# A column's title drawn as a tab over its list (the Portals column, owner, 28-10-2026): the selected tab's look.
TAB_TITLE_STYLESHEET = (
    f"background:{INK}; border:1px solid {EDGE}; border-bottom:none; border-top:2px solid {TEAL}; "
    "border-top-left-radius:5px; border-top-right-radius:5px; padding:6px 16px;"
)
