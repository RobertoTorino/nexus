# SPDX-License-Identifier: GPL-3.0-or-later
"""The system version history page: the systems on the left, the versions of the chosen one on the right, each a
card with its release date, its region and model where the data has them, the hardware facts and the notes."""

from __future__ import annotations

import html
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QTextBrowser, QWidget

from . import DATA_DIR
from .pages import Page
from .style import CARD, html_page
from .versions import PAGES, Entry, Series, load_page

LIST_WIDTH = 300


def entry_html(entry: Entry) -> str:
    lines = [f"<b style='font-size:17px;'>{html.escape(entry.version)}</b>",
             f"<span class='accent'>Release Date: {html.escape(entry.release_date)}</span>"]
    if entry.region:
        region = f"Region: {html.escape(entry.region)}"
        if entry.region_code:
            region += f" [{html.escape(entry.region_code)}]"
        if entry.model:
            region += f" ({html.escape(entry.model)})"
        lines.append(region)
    if entry.color:
        lines.append(f"<span class='muted'>Color: {html.escape(entry.color)}</span>")
    if entry.size:
        lines.append(f"<span class='muted'>Size: {html.escape(entry.size)}</span>")
    specs = entry.specs
    if specs:
        lines.append("<br>".join(f"<span class='muted'>{html.escape(name)}: {html.escape(value)}</span>"
                                 for name, value in specs))
    if entry.notes:
        lines.append("".join(f"• {html.escape(note)}<br>" for note in entry.notes))
    body = "<br>".join(lines)
    return (f"<table width='100%' cellpadding='12' cellspacing='0' bgcolor='{CARD}'><tr><td>{body}</td></tr>"
            "</table><p></p>")


def series_html(series_list: list[Series]) -> str:
    if not series_list or not any(s.entries for s in series_list):
        return "<p class='muted'>No system software data available.</p>"
    parts = []
    for series in series_list:
        if series.heading:
            parts.append(f"<h3>{html.escape(series.heading)}</h3>")
        parts.extend(entry_html(entry) for entry in series.entries)
    return "".join(parts)


class VersionsPage(Page):
    def __init__(self, folder: Path = DATA_DIR, parent: QWidget | None = None):
        super().__init__("System Version History", parent)
        self.folder = folder
        self.cache: dict[str, str] = {}
        row = QHBoxLayout()
        row.setSpacing(12)
        self.systems = QListWidget()
        self.systems.setFixedWidth(LIST_WIDTH)
        self.systems.setSpacing(4)
        self.systems.setStyleSheet("QListWidget { font-size: 14px; }")
        for page in PAGES:
            item = QListWidgetItem(page.title)
            item.setData(Qt.ItemDataRole.UserRole, page.file)
            self.systems.addItem(item)
        self.systems.currentRowChanged.connect(self.show_system)
        row.addWidget(self.systems)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        row.addWidget(self.view, 1)
        self.body.addLayout(row, 1)

    def activate(self) -> None:
        if self.systems.currentRow() < 0:
            self.systems.setCurrentRow(0)
        else:
            self.show_system(self.systems.currentRow())

    def first_focus(self) -> QWidget:
        return self.systems

    def show_system(self, row: int) -> None:
        if row < 0 or row >= len(PAGES):
            return
        page = PAGES[row]
        if page.file not in self.cache:
            series = load_page(page, self.folder)
            total = sum(len(s.entries) for s in series)
            self.cache[page.file] = html_page(f"<h2>{html.escape(page.title)}</h2>"
                                              f"<p class='muted'>{total} versions</p>{series_html(series)}")
        self.view.setHtml(self.cache[page.file])
        self.view.verticalScrollBar().setValue(0)
