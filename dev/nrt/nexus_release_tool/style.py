# SPDX-License-Identifier: GPL-3.0-or-later
"""Nexus's design for the window (owner, 26-10-2026: a Nexus app takes Nexus's look, not a suite's): the theme and
its colors come from core's nexus.py since 02-11-2026, every Nexus app's; this module keeps the window's own style
sheets on them. The states (the working tree, a build, a release) keep the state family every app shares."""

from pathlib import Path

from bc250_core.nexus import EDGE, INK, MAIN, NEXUS, SILVER, TEAL   # noqa: F401 (the window imports them from here)

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
