# SPDX-License-Identifier: GPL-3.0-or-later
"""Nexus's design for the window (owner, 26-10-2026: a Nexus app takes Nexus's look, not a suite's): the colors of
the Nexus page (nexus/docs/stylesheets/nexus.css), ink, silver and teal, as a theme for core's widgets, set with
create_app(theme=NEXUS). The states (the working tree, a build, a release) keep the state family every app shares."""

from bc250_core.theme import Theme

INK = "#010101"                         # the window, the header, the dialogs; every other row
MAIN = "#0f0f0f"                        # the fields, lists and tables; the top of a sheen
SILVER = "#c0c0c0"                      # the text
TEAL = "#17b6a7"                        # the accent: selection, focus, hover, the main action
EDGE = "#66808080"                      # the page's dimmed silver at 40 %: borders and the neutral edge

NEXUS = Theme("Nexus", True, window=INK, base=MAIN, alt=INK, text=SILVER, button=MAIN, button_low=INK, edge=EDGE,
              accent=TEAL, accent_text=INK)
