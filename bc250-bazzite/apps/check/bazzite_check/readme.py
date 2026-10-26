# SPDX-License-Identifier: GPL-3.0-or-later
"""Manual viewer: renders the app's chapter of the suite manual (and the other .md files it links to) inside the app.

A release ships the chapter as MANUAL.md (tools/stage_app.py copies docs/apps/check.md); in the checkout
the chapter itself is read. Links to other chapters of the manual open the published manual in the browser."""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices, QTextCursor, QTextDocument
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from bc250_core import SUITE_MANUAL_URL

DOCS_DIR = Path(__file__).resolve().parent.parent
MANUAL_PAGE = "apps/check.md"                # the chapter, under the suite's docs/
_ATTR_LIST = re.compile(r"\{\s*[.#][^}]*\}")         # MkDocs' { .class } after an image


def manual_path(app_dir: Path = DOCS_DIR) -> Path:
    """MANUAL.md of a release or an installed copy, the chapter in the checkout, else the README."""
    for path in (app_dir / "MANUAL.md", app_dir.parent.parent / "docs" / MANUAL_PAGE):
        if path.is_file():
            return path
    return app_dir / "README.md"


def manual_markdown(text: str, app_dir: Path = DOCS_DIR) -> str:
    """The chapter as Qt can show it: no MkDocs attribute lists, and its pictures from the app's images/."""
    text = _ATTR_LIST.sub("", text)
    return text.replace("](../assets/check/", f"]({(app_dir / 'images').as_posix()}/")


def online_url(link: str) -> str:
    """A relative link of the chapter as the address of that page in the published manual."""
    path, _, fragment = link.partition("#")
    page = posixpath.normpath(posixpath.join(posixpath.dirname(MANUAL_PAGE), path))
    if page == "index.md" or page.endswith("/index.md"):
        page = page.removesuffix("index.md")
    else:
        page = page.removesuffix(".md") + "/"
    return SUITE_MANUAL_URL + page + (f"#{fragment}" if fragment else "")


# Qt's Markdown import gives tables no borders and code no background; this restyles the HTML it produces.
_CSS = """
body { font-size: 14px; }
h1 { font-size: 26px; } h2 { font-size: 21px; margin-top: 22px; } h3 { font-size: 17px; margin-top: 16px; }
table { border-collapse: collapse; margin: 6px 0 12px 0; }
th { background: #3a3f4b; color: white; padding: 5px 8px; text-align: left; }
td { border: 1px solid #888; padding: 4px 8px; }
pre { background: #1e1f24; color: #e8e8e8; padding: 8px; font-family: monospace; }
code { background: rgba(127,127,127,0.18); font-family: monospace; }
"""


class ReadmeView(QWidget):
    def __init__(self, path: Path | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        self.back = QPushButton("◀  Back")
        self.back.setToolTip("Back to the previous document (after following a link to another .md file).")
        self.back.clicked.connect(self._go_back)
        bar.addWidget(self.back)
        bar.addStretch(1)
        external = QPushButton("Open in editor")
        external.setToolTip("Open the Markdown file in the default application.")
        external.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._current))))
        bar.addWidget(external)
        layout.addLayout(bar)

        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._follow)
        self.back.setEnabled(False)
        layout.addWidget(self.browser, 1)
        self._history: list[Path] = []
        path = path or manual_path()
        self._manual = path
        self._current = path
        self.load(path)

    def load(self, path: Path, push: bool = False) -> None:
        if push:
            self._history.append(self._current)
        self._current = path
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            self.browser.setPlainText(f"Could not read {path}: {exc}")
            return
        doc = QTextDocument(self.browser)
        doc.setMetaInformation(QTextDocument.MetaInformation.DocumentUrl, QUrl.fromLocalFile(str(path)).toString())
        doc.setBaseUrl(QUrl.fromLocalFile(str(path.parent) + "/"))
        if path == self._manual:
            text = manual_markdown(text)
        doc.setMarkdown(text, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
        html = doc.toHtml()
        doc.setDefaultStyleSheet(_CSS)
        doc.setHtml(html)
        self.browser.setDocument(doc)
        self.back.setEnabled(bool(self._history))

    def _follow(self, url: QUrl) -> None:
        if url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)
            return
        if not url.path() and url.fragment():
            self._scroll_to_heading(url.fragment())
            return
        target = (self._current.parent / url.path()).resolve() if not url.isLocalFile() else Path(url.toLocalFile())
        if target.suffix.lower() == ".md" and target.is_file():
            self.load(target, push=True)
        elif target.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        elif self._current == self._manual and not url.isLocalFile():
            # Another chapter of the manual, which the app does not ship.
            link = url.path() + (f"#{url.fragment()}" if url.fragment() else "")
            QDesktopServices.openUrl(QUrl(online_url(link)))

    def _scroll_to_heading(self, fragment: str) -> None:
        """GitHub-style #anchor -> the heading with that slug (Qt's Markdown import adds no anchors)."""
        slug = lambda t: re.sub(r"[^\w\- ]", "", t.lower()).strip().replace(" ", "-")  # noqa: E731
        block = self.browser.document().begin()
        while block.isValid():
            if block.blockFormat().headingLevel() and slug(block.text()) == fragment.lower():
                cursor = QTextCursor(block)
                self.browser.setTextCursor(cursor)
                bar = self.browser.verticalScrollBar()
                bar.setValue(bar.maximum())
                self.browser.ensureCursorVisible()     # from the bottom, so the heading lands at the top
                return
            block = block.next()

    def _go_back(self) -> None:
        if self._history:
            self.load(self._history.pop())
