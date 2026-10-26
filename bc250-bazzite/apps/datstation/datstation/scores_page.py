# SPDX-License-Identifier: GPL-3.0-or-later
"""The scores page: the best quiz score, the top ten rounds and the trophies, from the score store."""

from __future__ import annotations

import html

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QMessageBox, QWidget

from .pages import HtmlPage
from .scores import TOP, ScoreStore
from .style import CARD, quiet_button


def _when(value: str) -> str:
    return value.replace("T", " ") if value else ""


def page_html(store: ScoreStore) -> str:
    parts = [f"<h2>Best score: {store.best()}</h2>",
             f"<p class='muted'>{len(store.scores)} rounds played, {len(store.trophies)} trophies earned. "
             "The quick quiz is not counted.</p>"]
    parts.append(f"<h3>Top {TOP}</h3>")
    top = store.top()
    if top:
        rows = "".join(f"<tr><td>{n}</td><td><b>{s.score}</b></td><td>{html.escape(s.category)}</td>"
                       f"<td>{s.round}</td><td class='muted'>{html.escape(_when(s.when))}</td></tr>"
                       for n, s in enumerate(top, 1))
        parts.append(f"<table cellpadding='4' cellspacing='0' bgcolor='{CARD}' width='100%'>"
                     "<tr><th>#</th><th>Score</th><th>Category</th><th>Round</th><th>When</th></tr>"
                     f"{rows}</table>")
    else:
        parts.append("<p class='muted'>No scores yet. Play a round of the quiz: every finished round of a saved "
                     "game is listed here.</p>")
    parts.append("<h3>Trophies</h3>")
    if store.trophies:
        rows = "".join(f"<tr><td>★ {html.escape(t.kind)}</td><td>{html.escape(t.category)}</td>"
                       f"<td class='muted'>{html.escape(_when(t.when))}</td></tr>"
                       for t in reversed(store.trophies))
        parts.append(f"<table cellpadding='4' cellspacing='0' bgcolor='{CARD}' width='100%'>"
                     f"<tr><th>Trophy</th><th>Category</th><th>When</th></tr>{rows}</table>")
    else:
        parts.append("<p class='muted'>No trophies yet. A perfect round (every answer right, the round "
                     "complete) earns one.</p>")
    return "".join(parts)


class ScoresPage(HtmlPage):
    def __init__(self, store: ScoreStore, parent: QWidget | None = None):
        super().__init__("Scores & Trophies", parent)
        self.store = store
        self.clear_button = quiet_button("Clear scores", "Remove every score and trophy")
        self.clear_button.clicked.connect(self.clear)
        self.header_row.addWidget(self.clear_button)

    def activate(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.store.load()
        self.set_body(page_html(self.store))
        self.clear_button.setEnabled(bool(self.store.scores or self.store.trophies))

    def clear(self) -> None:
        answer = QMessageBox.question(self, "Clear scores",
                                      "Remove every quiz score and trophy? This cannot be undone.",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.store.clear()
            self.refresh()
            self.status.emit("Scores and trophies removed.")

    def on_link(self, url: QUrl) -> None:
        pass
