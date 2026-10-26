# SPDX-License-Identifier: GPL-3.0-or-later
"""The region codes page: per PlayStation the prefixes of the title IDs in a table, with the notes around it."""

from __future__ import annotations

import html

from PyQt6.QtWidgets import QWidget

from .pages import HtmlPage
from .regions import SECTIONS, TITLE, Section, Table
from .style import CARD


def _lines(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")


def table_html(table: Table) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in table.headers)
    rows = "".join("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
                   for row in table.rows)
    return (f"<table cellpadding='4' cellspacing='0' bgcolor='{CARD}' width='100%'>"
            f"<tr>{head}</tr>{rows}</table>")


def section_html(section: Section) -> str:
    parts = [f"<h3>{html.escape(section.console)}</h3>"]
    if section.coming_soon:
        parts.append("<p class='muted'>Coming soon …</p>")
    if section.intro:
        parts.append(f"<p>{_lines(section.intro)}</p>")
    if section.table is not None:
        parts.append(table_html(section.table))
    if section.footer:
        parts.append(f"<p class='muted'>{_lines(section.footer)}</p>")
    return "".join(parts)


def page_html() -> str:
    return f"<h2>{html.escape(TITLE)}</h2>" + "".join(section_html(section) for section in SECTIONS)


class RegionsPage(HtmlPage):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(TITLE, parent)
        self.set_body(page_html())
