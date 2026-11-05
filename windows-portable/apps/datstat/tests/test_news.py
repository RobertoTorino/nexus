# SPDX-License-Identifier: GPL-3.0-or-later
"""The news: the feed parsed from a recorded copy of the PlayStation.Blog feed (made up in its shape), the allowed
links, the dates, the errors, and the rows the page makes of it."""

from __future__ import annotations

import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from conftest import FIXTURES
from dat_station import news
from dat_station.panes import NewsPane, elided

FEED = (FIXTURES / "feed.xml").read_bytes()


def test_the_feed_parses():
    items = news.parse_rss(FEED)
    assert len(items) == 10
    first = items[0]
    assert first.title.startswith("(For Southeast Asia) Example Racing’s autumn update")
    assert first.link == "https://blog.playstation.com/2026/10/14/example-racing-autumn-update/"
    assert first.published is not None and first.published.tzinfo is not None
    assert all(news.allowed(item.link) for item in items)


def test_cleaning_and_dates():
    assert news.clean("  Hello &amp; <b>world</b>\n twice ") == "Hello & world twice"
    assert news.clean(None) == ""
    published = news.parse_date("Thu, 15 Oct 2026 02:07:00 +0000")
    assert published == datetime(2026, 10, 15, 2, 7, tzinfo=timezone.utc)
    assert news.parse_date("") is None and news.parse_date("not a date") is None
    now = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    assert news.relative(now - timedelta(seconds=30), now) == "just now"
    assert news.relative(now - timedelta(minutes=1), now) == "1 minute ago"
    assert news.relative(now - timedelta(minutes=5), now) == "5 minutes ago"
    assert news.relative(now - timedelta(hours=3), now) == "3 hours ago"
    assert news.relative(now - timedelta(days=1), now) == "yesterday"
    assert news.relative(now - timedelta(days=4), now) == "4 days ago"
    assert news.relative(now + timedelta(hours=1), now) == "just now"
    assert news.format_date(None) == ""
    assert news.format_date(published, now).endswith("• 9 hours ago")


@pytest.mark.parametrize("url, ok", [
    ("https://blog.playstation.com/2026/10/14/x/", True), ("https://store.playstation.com/en-us/x", True),
    ("https://www.playstation.com/en-us/ps5/games/", True), ("https://playstation.com/", True),
    ("http://blog.playstation.com/", False), ("https://evil.example.com/blog.playstation.com", False),
    ("https://blog.playstation.com.evil.example/", False), ("not a url", False), ("", False)])
def test_only_playstation_links_are_allowed(url, ok):
    assert news.allowed(url) is ok


def test_errors_are_sentences(monkeypatch):
    with pytest.raises(news.NewsError, match="not valid XML"):
        news.parse_rss(b"<rss><channel><item>")

    def refuse(request, timeout):
        raise urllib.error.URLError("no network")
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    with pytest.raises(news.NewsError, match="Could not reach blog.playstation.com"):
        news.load("test/1.0")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return FEED

    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: Response())
    assert len(news.load("test/1.0", count=3)) == 3


def test_the_pages_rows(qapp):
    pane = NewsPane()
    items = news.parse_rss(FEED)
    pane.set_news(items)
    assert len(pane.list.pills) == 10 and pane.item("0") is items[0] and pane.item("10") is None
    assert pane.list.pills["1"].label.text() == items[1].title
    long = elided("A title " * 40)
    assert long.endswith("…") and len(long) < len("A title " * 40)
    assert elided("Short") == "Short"
