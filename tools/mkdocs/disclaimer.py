# SPDX-License-Identifier: GPL-3.0-or-later
"""MkDocs hook: the disclaimer every wiki shows, one text for the Nexus page and each suite's wiki (owner,
28-10-2026: the Nexus page's footer line is the one; a new wiki lists this hook and has it too).

It sets config.extra.disclaimer, which a template shows with {{ config.extra.disclaimer }} (the footer of each
home page), and puts the text in place of a line that is only MARKER in a page's Markdown (the Nexus home page's
Disclaimer section)."""

from __future__ import annotations

DISCLAIMER = (
    "Nexus and its suites are independent community projects, not affiliated with or endorsed by AMD, ASRock, the "
    "Bazzite / Universal Blue project, Sony, Microsoft, Nintendo, Valve, or the makers of the emulators and the other "
    "programs the apps work with. BC-250 is AMD's product name and Bazzite the Universal Blue project's. "
    "PlayStation, PS4, PS5, PS3, PS2, PSP, PS Vita, DualSense and Remote Play are Sony's; Xbox, Xbox 360, Xbox Cloud "
    "Gaming and Windows are Microsoft's; Steam, Steam Deck and Big Picture are Valve's; the names of Nintendo's "
    "consoles, of the emulators (shadPS4, RPCS3, PPSSPP, PCSX2, Vita3K, Xenia) and of Decky Loader, HelixSR and "
    "DirectMesh belong to their owners. The suites use them only to say what their apps work with."
)
MARKER = "<!-- disclaimer -->"


def on_config(config):
    config.extra["disclaimer"] = DISCLAIMER
    return config


def on_page_markdown(markdown, page, config, files):
    return "\n".join(DISCLAIMER if line.strip() == MARKER else line for line in markdown.split("\n"))
