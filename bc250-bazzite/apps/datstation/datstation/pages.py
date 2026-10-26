# SPDX-License-Identifier: GPL-3.0-or-later
"""What every page of the window shares: the Back button with the page's title on the first line, the body under
it, and a status line for the window's status bar. HtmlPage is a page whose body is one QTextBrowser (the history,
the versions, the region codes, the news and the scores: text that scrolls, with links the page handles)."""

from __future__ import annotations

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QTextBrowser, QVBoxLayout, QWidget

from .style import html_page, label, quiet_button


class Page(QWidget):
    back = pyqtSignal()
    status = pyqtSignal(str)            # a line for the status bar

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.page_title = title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.header_row = QHBoxLayout()
        self.header_row.setSpacing(12)
        self.back_button = quiet_button("← Back", "Back to the front page (Escape)")
        self.back_button.clicked.connect(self.back.emit)
        self.header_row.addWidget(self.back_button)
        self.title = label(title, title=True)
        self.header_row.addWidget(self.title)
        self.header_row.addStretch(1)
        layout.addLayout(self.header_row)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        layout.addLayout(self.body, 1)

    def activate(self) -> None:
        """The page was opened: load what it shows, start what runs while it is open."""

    def deactivate(self) -> None:
        """The page was left: stop what ran while it was open."""

    def first_focus(self) -> QWidget:
        """The widget that takes the focus when the page opens (the keyboard and a controller start there)."""
        return self.back_button


class HtmlPage(Page):
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(title, parent)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.setOpenExternalLinks(False)
        self.view.anchorClicked.connect(self.on_link)
        self.body.addWidget(self.view, 1)

    def set_body(self, body: str) -> None:
        self.view.setHtml(html_page(body))

    def on_link(self, url: QUrl) -> None:
        """A link in the text was clicked; pages that have links override it."""

    def first_focus(self) -> QWidget:
        return self.view

