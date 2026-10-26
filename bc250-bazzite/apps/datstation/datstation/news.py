# SPDX-License-Identifier: GPL-3.0-or-later
"""The PlayStation news: the PlayStation.Blog RSS feed, read with the standard library, and the two store pages the
page links to. Only links to PlayStation's own sites are opened (ALLOWED_HOSTS), as in the Android app."""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

FEED_URL = "https://blog.playstation.com/feed/"
UPCOMING_URL = "https://www.playstation.com/en-us/ps5/games/"
NEW_RELEASES_URL = "https://store.playstation.com/en-us/category/024029c7-f61b-4bef-a4d7-06270ed12b56/1"
ALLOWED_HOSTS = frozenset({"blog.playstation.com", "www.playstation.com", "playstation.com",
                           "store.playstation.com"})
TIMEOUT = 15
ITEMS = 20
_TAGS = re.compile(r"<[^>]+>")


class NewsError(Exception):
    """Why the news could not be loaded, in a sentence for the page."""


@dataclass(frozen=True)
class NewsItem:
    title: str
    link: str
    published: datetime | None          # aware, from the feed's pubDate; None when it has none or an odd one


def allowed(url: str) -> bool:
    """Whether a link may be opened: https, on one of PlayStation's own hosts."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme.lower() == "https" and (parts.hostname or "").lower() in ALLOWED_HOSTS


def clean(text: str | None) -> str:
    """Feed text as plain text: entities decoded, tags dropped, whitespace collapsed."""
    text = html.unescape(_TAGS.sub("", text or ""))
    return " ".join(text.split())


def parse_date(text: str) -> datetime | None:
    if not text.strip():
        return None
    try:
        parsed = parsedate_to_datetime(text.strip())
    except (TypeError, ValueError, IndexError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_rss(data: bytes) -> list[NewsItem]:
    """The items of an RSS 2.0 feed, in the feed's order. Raises NewsError when it is not XML."""
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        raise NewsError(f"The feed is not valid XML ({error}).") from error
    items = []
    for item in root.iter("item"):
        title = clean(item.findtext("title"))
        link = clean(item.findtext("link"))
        if title and link:
            items.append(NewsItem(title, link, parse_date(item.findtext("pubDate") or "")))
    return items


def fetch(url: str, user_agent: str, timeout: int = TIMEOUT) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": "application/rss+xml, application/xml, text/xml",
                                                   "User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise NewsError(f"HTTP {error.code} while loading the PlayStation feed.") from error
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        reason = getattr(error, "reason", None) or error
        raise NewsError(f"Could not reach blog.playstation.com ({reason}).") from error


def load(user_agent: str, url: str = FEED_URL, timeout: int = TIMEOUT, count: int = ITEMS) -> list[NewsItem]:
    """The latest announcements; raises NewsError with the reason when they cannot be loaded."""
    return parse_rss(fetch(url, user_agent, timeout))[:count]


def relative(published: datetime, now: datetime) -> str:
    """"3 hours ago", as Android's relative time span: minutes under an hour, hours under a day, then days."""
    seconds = int((now - published).total_seconds())
    if seconds < 0:
        return "just now"
    minutes, hours, days = seconds // 60, seconds // 3600, seconds // 86400
    if minutes < 1:
        return "just now"
    if hours < 1:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    if days < 1:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


def format_date(published: datetime | None, now: datetime | None = None) -> str:
    """"15 Oct 2026 • 3 hours ago"; "" without a date."""
    if published is None:
        return ""
    now = now or datetime.now(timezone.utc)
    return f"{published.astimezone().strftime('%d %b %Y')} • {relative(published, now)}"
