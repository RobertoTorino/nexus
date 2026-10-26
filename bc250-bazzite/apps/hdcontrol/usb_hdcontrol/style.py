# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's colors: the gaming apps' blue, #0A55B0 (owner, 23-10-2026: the game colors, the blue highlights), for
the drawing's lit parts, the section bars and the chosen profile; and a soft white edge for the boxes, pills and cards
on the dark themes (owner, the same day: white, at half strength so the 1 px line reads thin), over core's look."""

from __future__ import annotations

from bc250_core.theme import THEME

BLUE = "#0A55B0"
BLUE_LIGHT = "#5B93DA"                  # #0A55B0 is too dark to read on a dark window: lit parts, the chosen card
EDGE = "rgba(255, 255, 255, 0.45)" if THEME.dark else THEME.edge     # on Silver white would not show


def soften(sheet: str) -> str:
    """Core's surface style (surface_style) with the app's edge where core draws the theme's near-black one: one
    even 1 px line around a neutral box (owner, 23-10-2026: uniform); a state's color keeps its 4 px left edge."""
    return (sheet.replace(f"border:1px solid {THEME.edge}", f"border:1px solid {EDGE}")
            .replace(f"border-left:4px solid {THEME.edge}", f"border-left:1px solid {EDGE}"))
