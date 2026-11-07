# SPDX-License-Identifier: GPL-3.0-or-later
"""The PS News page: the latest PlayStation.Blog announcements, loaded in a thread, each a link to the post; the
Upcoming Games and New Releases buttons open PlayStation's pages. Only PlayStation's own links are opened."""

from __future__ import annotations

import html
from datetime import datetime, timezone

from PyQt6.QtCore import QThread, QUrl, pyqtSignal
from PyQt6.QtWidgets import QWidget

from bc250_core.platform import xdg_open

from . import INFO
from . import news
from .pages import HtmlPage
from .style import label, quiet_button


class NewsWorker(QThread):
    loaded = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, user_agent: str, url: str = news.FEED_URL, parent=None):
        super().__init__(parent)
        self.user_agent = user_agent
        self.url = url

    def run(self) -> None:
        try:
            self.loaded.emit(news.load(self.user_agent, self.url))
        except news.NewsError as error:
            self.failed.emit(str(error))
        except Exception as error:  # noqa: BLE001  (an unexpected failure is still a message, not a crash)
            self.failed.emit(f"Failed to load PlayStation updates: {error}")


def items_html(items: list[news.NewsItem], now: datetime | None = None) -> str:
    if not items:
        return "<p class='muted'>No announcements found.</p>"
    parts = ["<h2>Latest Announcements</h2>"]
    for item in items:
        date = news.format_date(item.published, now)
        parts.append(f"<p><a href='{html.escape(item.link, quote=True)}'>{html.escape(item.title)}</a><br>"
                     f"<span class='muted'>{html.escape(date)}</span><br>"
                     f"<span class='muted' style='font-size:12px;'>{html.escape(item.link)}</span></p><hr>")
    return "".join(parts)


class NewsPage(HtmlPage):
    def __init__(self, opener=xdg_open, feed_url: str = news.FEED_URL, parent: QWidget | None = None):
        super().__init__("PS News", parent)
        self.opener = opener
        self.feed_url = feed_url
        self.worker: NewsWorker | None = None
        self.items: list[news.NewsItem] = []
        self.upcoming_button = quiet_button("Upcoming Games", news.UPCOMING_URL)
        self.upcoming_button.clicked.connect(lambda: self.open_url(news.UPCOMING_URL))
        self.releases_button = quiet_button("New Releases", news.NEW_RELEASES_URL)
        self.releases_button.clicked.connect(lambda: self.open_url(news.NEW_RELEASES_URL))
        self.refresh_button = quiet_button("Refresh", "Load the announcements again")
        self.refresh_button.clicked.connect(self.load)
        for button in (self.upcoming_button, self.releases_button, self.refresh_button):
            self.header_row.addWidget(button)
        self.subtitle = label("Announcements, release-date news, and new PlayStation releases", muted=True)
        self.body.insertWidget(0, self.subtitle)

    def activate(self) -> None:
        if not self.items and self.worker is None:
            self.load()

    def load(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        self.refresh_button.setEnabled(False)
        self.set_body("<p>Loading official PlayStation blog updates...</p>")
        self.status.emit("Loading the PlayStation Blog feed...")
        self.worker = NewsWorker(INFO.user_agent, self.feed_url, self)
        self.worker.loaded.connect(self.show_items)
        self.worker.failed.connect(self.show_error)
        self.worker.finished.connect(self._done)
        self.worker.start()

    def _done(self) -> None:
        self.refresh_button.setEnabled(True)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    def show_items(self, items: list) -> None:
        self.items = list(items)
        self.set_body(items_html(self.items, datetime.now(timezone.utc)))
        self.status.emit(f"{len(self.items)} announcements loaded.")

    def show_error(self, message: str) -> None:
        self.items = []
        self.set_body(f"<h3>Could not load announcements</h3><p>{html.escape(message)}</p>"
                      "<p class='muted'>For this feature to show results you need an active internet connection. "
                      "Use Refresh to try again.</p>")
        self.status.emit(message)

    def on_link(self, url: QUrl) -> None:
        self.open_url(url.toString())

    def open_url(self, url: str) -> None:
        if not news.allowed(url):
            self.status.emit("Blocked unexpected link.")
            return
        if self.opener(url):
            self.status.emit(f"Opened {url} in the browser.")
        else:
            self.status.emit("No browser could be started (xdg-open is missing).")
