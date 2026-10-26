# SPDX-License-Identifier: GPL-3.0-or-later
"""The PlayStation history page: every console with its lifetime totals, then a brief overview of its legacy. A
click on a console's name opens pictures of it on the web."""

from __future__ import annotations

import html

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QWidget

from bc250_core.platform import xdg_open

from .history import CONSOLES, UPDATED, Console, search_url
from .pages import HtmlPage


def _name(console: Console) -> str:
    """The console's name, a link to pictures of it on the web."""
    return f"<a href='search:{html.escape(console.name, quote=True)}'>{html.escape(console.name)}</a>"


def console_html(console: Console) -> str:
    titles = html.escape(console.titles).replace("\n", "<br>")
    return f"<h3>{_name(console)}</h3><p class='muted'>{html.escape(console.sold)} • {titles}</p>"


def page_html() -> str:
    totals = "".join(console_html(console) for console in CONSOLES)
    legacy = "".join(f"<h3>{_name(console)}</h3><p>{html.escape(console.legacy)}</p>" for console in CONSOLES)
    return (f"<h2>Lifetime totals</h2><p class='muted'>Click a name for pictures of it on the web.</p>{totals}"
            f"<p class='muted'><b>Update Info</b><br>Source: Internet. Updated {UPDATED}.</p><hr>"
            f"<h2>A brief overview of PlayStation's legacy</h2>{legacy}")


class HistoryPage(HtmlPage):
    def __init__(self, opener=xdg_open, parent: QWidget | None = None):
        super().__init__("PlayStation History", parent)
        self.opener = opener
        self.loaded = False

    def activate(self) -> None:
        if not self.loaded:
            self.set_body(page_html())
            self.loaded = True

    def on_link(self, url: QUrl) -> None:
        if url.toString().startswith("search:"):
            query = url.toString(QUrl.ComponentFormattingOption.FullyDecoded)[len("search:"):]
            if self.opener(search_url(query)):
                self.status.emit(f"Searching the web for pictures of {query}.")
            else:
                self.status.emit("No browser could be started (xdg-open is missing).")
