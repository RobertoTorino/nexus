# SPDX-License-Identifier: GPL-3.0-or-later
"""The front page's tiles and the feature pages' panes: History, System Version History, Region Codes, PS News and
Scores & Trophies (the quiz has its own module, quiz_pane.py). A long list is a ListArea, as Xenia Manager's: rows in
a column that scrolls, the one with the focus kept in view, so the d-pad goes down a list of any length and a finger
can drag it. The row with the focus shows what it holds beside the list (a console's history, a system's versions, a
region table) or says more on the pane's status line. A long text is core's TextView, which the d-pad scrolls. Every
action is a controller button in the window's legend, never a pill (owner, 29-10-2026).

The BC250 app's pages were HTML; a handheld's pages are rows and plain text, so the text functions here (console_text,
series_text, section_text, score_text) give the same content as plain lines, the tables in columns set by tab stops.

The symbols (the controller's shapes on the tiles, the results' star) are drawn, not characters: Inter, the suite's
font, has none of them, and a Qt platform without font fallback draws a missing one as a box."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QScroller, QVBoxLayout, QWidget

from bc250_core.portable import (AMBER, BODY, DIM, PILL, ROW_HEIGHT, InfoPill, Pane, Row, TextView, font, px,
                                 text_label)

from . import history, news, regions, versions
from .scores import TOP, Score, ScoreStore, Trophy

ROW = ROW_HEIGHT
LIST_WIDTH = 380                # the list beside a text: History's consoles, the systems, the region codes
TAB_STOP = 150                  # a region table's columns
ROW_TEXT = 1040                 # a news title is cut off with … beyond this (a Row's text does not wrap)
TRIANGLE, CIRCLE, CROSS, SQUARE = "#3dbf9c", "#e8505b", "#6f9fe8", "#e48fc0"   # as the BC250 app draws them
WHITE, YELLOW, GOLD = "#f5f4f0", "#ffd166", "#ffd700"
SILVER, BRONZE = "#c0c0c0", "#cd7f32"


@dataclass(frozen=True)
class Feature:
    key: str
    shape: str                  # draw_symbol()'s shape
    color: str
    name: str
    tile: str                   # the name on the tile, short enough for one line
    text: str


def features(questions: int, categories: int) -> tuple[Feature, ...]:
    """The front page's tiles, the BC250 app's, in its order (a long name shortened on its tile; the pane under the
    tiles has it whole); the quiz's text counts the shipped questions."""
    return (
        Feature("quiz", "triangle", TRIANGLE, "PlayStation Quiz", "PlayStation Quiz",
                f"{questions:,} questions in {categories} categories, against the clock. Perfect rounds earn trophies."),
        Feature("history", "circle", CIRCLE, "PlayStation History", "PlayStation History",
                "Every console since 1994: what it sold, how many titles, and its legacy."),
        Feature("versions", "cross", CROSS, "System Version History", "System Versions",
                "Every system software release, from the PS1 to the PS5 and the Portal."),
        Feature("regions", "square", SQUARE, "Region Codes Explained", "Region Codes",
                "What the prefix of a title ID and the last digit of a model number say about the region."),
        Feature("guides", "diamond", WHITE, "PlayStation User Guides", "User Guides",
                "Sony's online manuals for every PlayStation product, in your browser."),
        Feature("news", "diamond_filled", YELLOW, "PS News", "PS News",
                "The latest announcements from the PlayStation Blog, upcoming games and new releases."),
        Feature("scores", "star", GOLD, "Scores & Trophies", "Scores & Trophies",
                "Your best quiz scores and the trophies your perfect rounds earned."),
    )


# --- The symbols ------------------------------------------------------------------------------------------------

def _star(center: QPointF, outer: float, inner: float) -> QPainterPath:
    path = QPainterPath()
    for n in range(10):
        radius = outer if n % 2 == 0 else inner
        angle = math.pi / 2 + n * math.pi / 5
        point = QPointF(center.x() + radius * math.cos(angle), center.y() - radius * math.sin(angle))
        if n == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    return path


def draw_symbol(painter: QPainter, shape: str, color: str, side: float) -> None:
    """*shape* in a square of *side*: the controller's triangle, circle, cross and square as outlines, the diamond
    as an outline or filled, the star filled."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    line = side * 0.11
    pen = QPen(QColor(color), line)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    inset = line / 2 + side * 0.06
    box = QRectF(inset, inset, side - 2 * inset, side - 2 * inset)
    middle = box.center()
    if shape == "triangle":
        path = QPainterPath(QPointF(middle.x(), box.top() + side * 0.04))
        path.lineTo(box.right(), box.bottom() - side * 0.08)
        path.lineTo(box.left(), box.bottom() - side * 0.08)
        path.closeSubpath()
        painter.drawPath(path)
    elif shape == "circle":
        painter.drawEllipse(box)
    elif shape == "cross":
        painter.drawLine(box.topLeft(), box.bottomRight())
        painter.drawLine(box.topRight(), box.bottomLeft())
    elif shape == "square":
        painter.drawRect(box.adjusted(side * 0.05, side * 0.05, -side * 0.05, -side * 0.05))
    elif shape in ("diamond", "diamond_filled"):
        if shape == "diamond_filled":
            painter.setBrush(QColor(color))
        path = QPainterPath(QPointF(middle.x(), box.top()))
        path.lineTo(box.right(), middle.y())
        path.lineTo(middle.x(), box.bottom())
        path.lineTo(box.left(), middle.y())
        path.closeSubpath()
        painter.drawPath(path)
    elif shape == "star":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPath(_star(QPointF(side / 2, side / 2 + side * 0.03), side * 0.48, side * 0.2))


def symbol_pixmap(shape: str, color: str, side: int = 128) -> QPixmap:
    """A tile's icon: the symbol on a transparent square (Card trims and scales it)."""
    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    draw_symbol(painter, shape, color, side)
    painter.end()
    return pixmap


class Symbol(QWidget):
    """A symbol in a square of *side* on the page (the results' star)."""

    def __init__(self, shape: str, color: str, side: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.shape, self.color = shape, color
        self.setFixedSize(px(side), px(side))

    def set_color(self, color: str) -> None:
        self.color = color
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        draw_symbol(painter, self.shape, self.color, self.width())


# --- The lists --------------------------------------------------------------------------------------------------

class ListArea(QScrollArea):
    """Rows in a column that scrolls; current(key) when one gets the focus or A on it (activated(key))."""

    current = pyqtSignal(str)
    activated = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # A thin bar of where in the list it is, no arrows (TextView's): the d-pad and a finger scroll
        self.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget "
                           "{ background: transparent; }"
                           f" QScrollBar:vertical {{ background: transparent; width: {px(6)}px; margin: 0; }}"
                           f" QScrollBar::handle:vertical {{ background: {DIM}; border-radius: {px(3)}px;"
                           f" min-height: {px(24)}px; }}"
                           " QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
                           " QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }")
        self.setMinimumHeight(px(ROW * 2 + 8))
        self.inner = QWidget()
        self.column = QVBoxLayout(self.inner)
        self.column.setContentsMargins(0, 0, px(4), 0)
        self.column.setSpacing(px(6))
        self.column.addStretch()
        self.setWidget(self.inner)
        QScroller.grabGesture(self.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)  # a finger drags
        self.pills: dict[str, Row] = {}
        self._keys: dict[QObject, str] = {}

    def set_items(self, items: Sequence[tuple[str, str]]) -> None:
        """The list's (key, text) rows, in order; the focus, when a row had it, stays on the row with its key."""
        old = self.pills
        had = next((key for key, pill in old.items() if pill.hasFocus()), None)
        self.pills, self._keys = {}, {}
        for n, (key, text) in enumerate(items):
            pill = Row(text)
            pill.activated.connect(lambda key=key: self.activated.emit(key))
            pill.installEventFilter(self)
            self.column.insertWidget(n, pill)
            if self.isVisible():
                pill.show()
            self.pills[key] = pill
            self._keys[pill] = key
        if had is not None:
            keep = self.pills.get(had) or self.first()
            if keep is not None:
                keep.setFocus()
        for pill in old.values():
            pill.removeEventFilter(self)
            pill.hide()
            pill.deleteLater()

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.FocusIn and obj in self._keys:
            self.ensureWidgetVisible(obj, 0, px(8))
            self.current.emit(self._keys[obj])
        return super().eventFilter(obj, event)

    def first(self) -> Row | None:
        return next(iter(self.pills.values()), None)

    def focused(self) -> str:
        return next((key for key, pill in self.pills.items() if pill.hasFocus()), "")

    def focus(self, key: str) -> bool:
        """The focus on the row with *key* (else the first); whether there was a row."""
        pill = self.pills.get(key) or self.first()
        if pill is None:
            return False
        pill.setFocus(Qt.FocusReason.OtherFocusReason)
        return True


def elided(text: str, width: int = ROW_TEXT) -> str:
    """*text* as a Row shows it on one line: cut off with … where it would be wider than *width*."""
    metrics = QFontMetrics(font(PILL - 1, QFont.Weight.DemiBold))
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, px(width))


# --- The panes --------------------------------------------------------------------------------------------------

class FeaturePane(Pane):
    """A feature's page: its title with the information icon at the top right, a line under it, what the feature
    shows (body, filled by the subclass) and the status line."""

    def __init__(self, title: str, info: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # holds the focus itself while it has no row (no scores yet)
        heading = QHBoxLayout()
        self.title = text_label(title, 24, QFont.Weight.ExtraBold)
        heading.addWidget(self.title)
        heading.addStretch()
        self.info = InfoPill(title, info)
        heading.addWidget(self.info, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(heading)
        self.summary = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.summary)
        self.column.addSpacing(px(8))
        self.body = QVBoxLayout()
        self.body.setSpacing(px(8))
        self.column.addLayout(self.body, 1)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)

    def first_focus(self) -> QWidget | None:
        """Where the focus goes when the page opens."""
        return None


class SplitPane(FeaturePane):
    """A list on the left and what its focused row holds on the right: a TextView (*text_view*) or a column of
    labels the subclass fills (*detail*)."""

    def __init__(self, title: str, info: str, text_view: bool, parent: QWidget | None = None):
        super().__init__(title, info, parent)
        row = QHBoxLayout()
        row.setSpacing(px(16))
        self.list = ListArea()
        self.list.setFixedWidth(px(LIST_WIDTH))
        self.shown = ""                                 # the row whose text shows: B from the text goes back to it
        self.list.current.connect(self._shown)
        row.addWidget(self.list)
        self.view: TextView | None = None
        self.detail = QVBoxLayout()
        if text_view:
            self.view = TextView()
            row.addWidget(self.view, 1)
        else:
            self.detail.setSpacing(px(6))
            row.addLayout(self.detail, 1)
        self.body.addLayout(row, 1)

    def first_focus(self) -> QWidget | None:
        return self.list.first()

    def _shown(self, key: str) -> None:
        self.shown = key

    def show_text(self, text: str) -> None:
        if self.view is not None:
            self.view.setPlainText(text)
            self.view.verticalScrollBar().setValue(0)


# --- PlayStation History ----------------------------------------------------------------------------------------

HISTORY_INFO = (
    "Every PlayStation since 1994 with its launch year, what it sold and how many titles it had, and a brief "
    "overview of its legacy. The A button on a console opens pictures of it on the web, in your browser.\n\n"
    f"Update info. Source: Internet. Updated {history.UPDATED}.")


def console_totals(console: history.Console) -> str:
    """What a console sold and its titles, as the BC250 app's totals list it."""
    return f"{console.sold} • {console.titles}"


class HistoryPane(SplitPane):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("PlayStation History", HISTORY_INFO, text_view=False, parent=parent)
        self.summary.setText("Lifetime totals and a brief overview of PlayStation's legacy.")
        self.name = text_label("", 20, QFont.Weight.Bold, wrap=True)
        self.totals = text_label("", BODY + 1, color=DIM, wrap=True)
        self.legacy = text_label("", BODY + 1, wrap=True)
        self.legacy.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.detail.addWidget(self.name)
        self.detail.addWidget(self.totals)
        self.detail.addSpacing(px(6))
        self.detail.addWidget(self.legacy)
        self.detail.addStretch()
        self.list.set_items([(str(n), console.name) for n, console in enumerate(history.CONSOLES)])
        self.list.current.connect(self.show_console)
        self.show_console("0")

    def console(self, key: str) -> history.Console | None:
        return history.CONSOLES[int(key)] if key.isdigit() and int(key) < len(history.CONSOLES) else None

    def show_console(self, key: str) -> None:
        console = self.console(key)
        if console is None:
            return
        self.name.setText(console.name)
        self.totals.setText(console_totals(console))
        self.legacy.setText(console.legacy)


# --- System Version History -------------------------------------------------------------------------------------

VERSIONS_INFO = (
    "Every system software release of every PlayStation, from the Android app's data: its release date, its notes "
    "and, where the data has them, its region, model, color, size and hardware facts.\n\n"
    "The d-pad goes down the systems; the versions of the one with the focus show beside the list. The A button (or "
    "right) goes into the versions, where up and down scroll them; B goes back to the list. The PlayStation 6 entry "
    "is a placeholder until there is one.")


def short_title(page: versions.Page) -> str:
    """"PlayStation 5" of "PlayStation 5 System Software": the list's row."""
    return page.title.removesuffix(" System Software")


def entry_text(entry: versions.Entry) -> str:
    """A version as plain lines: the version, the release date, the region with its code and model, the color, the
    size, the hardware facts and the notes (the BC250 app's card, in its order)."""
    lines = [entry.version, f"Release Date: {entry.release_date}"]
    if entry.region:
        region = f"Region: {entry.region}"
        if entry.region_code:
            region += f" [{entry.region_code}]"
        if entry.model:
            region += f" ({entry.model})"
        lines.append(region)
    if entry.color:
        lines.append(f"Color: {entry.color}")
    if entry.size:
        lines.append(f"Size: {entry.size}")
    lines += [f"{name}: {value}" for name, value in entry.specs]
    lines += [f"• {note}" for note in entry.notes]
    return "\n".join(lines)


def series_text(page: versions.Page, series_list: list[versions.Series]) -> str:
    """A system's page: its title, how many versions, then every series (its heading, when it has one) with its
    versions, a blank line apart."""
    head = f"{page.title}\n{versions.count(series_list)} versions"
    if not series_list or not any(s.entries for s in series_list):
        return f"{head}\n\nNo system software data available."
    parts = [head]
    for series in series_list:
        if series.heading:
            parts.append(series.heading.upper())
        parts += [entry_text(entry) for entry in series.entries]
    return "\n\n".join(parts)


class VersionsPane(SplitPane):
    def __init__(self, folder=None, parent: QWidget | None = None):
        super().__init__("System Version History", VERSIONS_INFO, text_view=True, parent=parent)
        self.folder = folder
        self.cache: dict[str, str] = {}
        self.summary.setText("Every system software release, from the PS1 to the PS5 and the Portal.")
        self.list.set_items([(page.file, short_title(page)) for page in versions.PAGES])
        self.list.current.connect(self.show_system)

    def show_system(self, file: str) -> None:
        page = next((p for p in versions.PAGES if p.file == file), None)
        if page is None:
            return
        if file not in self.cache:
            series = versions.load_page(page, self.folder) if self.folder is not None else versions.load_page(page)
            self.cache[file] = series_text(page, series)
        self.show_text(self.cache[file])
        self.status.setText("")


# --- Region Codes Explained -------------------------------------------------------------------------------------

REGIONS_INFO = (
    "Per PlayStation, what the prefix of a title ID says about the market and the publisher (PPSA, ELJM, BCES, SLUS, "
    "…), in a table, and for the PS1 and PS2 what the last digit of the model number says about the region.\n\n"
    "The d-pad goes down the consoles; the codes of the one with the focus show beside the list. The A button (or "
    "right) goes into the text, where up and down scroll it; B goes back to the list.")


def table_text(table: regions.Table) -> str:
    """A table as lines of tab-separated cells, the headers first: the view's tab stops make the columns."""
    return "\n".join("\t".join(row) for row in (table.headers, *table.rows))


def section_text(section: regions.Section) -> str:
    """A console's codes as plain text: its intro, its table and its footer, a blank line apart."""
    parts = [section.console]
    if section.coming_soon:
        parts.append("Coming soon …")
    if section.intro:
        parts.append(section.intro)
    if section.table is not None:
        parts.append(table_text(section.table))
    if section.footer:
        parts.append(section.footer)
    return "\n\n".join(parts)


class RegionsPane(SplitPane):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(regions.TITLE, REGIONS_INFO, text_view=True, parent=parent)
        self.view.setTabStopDistance(px(TAB_STOP))
        self.summary.setText("What a title ID's prefix and a model number say about the region.")
        self.list.set_items([(str(n), section.console) for n, section in enumerate(regions.SECTIONS)])
        self.list.current.connect(self.show_section)

    def show_section(self, key: str) -> None:
        if key.isdigit() and int(key) < len(regions.SECTIONS):
            self.show_text(section_text(regions.SECTIONS[int(key)]))


# --- PS News ----------------------------------------------------------------------------------------------------

NEWS_INFO = (
    "The latest announcements from the PlayStation.Blog feed, newest first; the line under the list says when the "
    "one with the focus was posted. The A button opens the post in your browser. X opens PlayStation's Upcoming "
    "Games page, RB its New Releases in the PlayStation Store, Y loads the feed again.\n\n"
    "Only links to PlayStation's own sites (playstation.com, blog.playstation.com, store.playstation.com) are "
    "opened; anything else in the feed is blocked, and the status line says so. The feed needs a network "
    "connection: the page loads it when you open it, never before.")
NEWS_SUMMARY = "Announcements, release-date news, and new PlayStation releases."


class NewsPane(FeaturePane):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("PS News", NEWS_INFO, parent)
        self.summary.setText(NEWS_SUMMARY)
        self.list = ListArea()
        self.body.addWidget(self.list, 1)
        self.items: list[news.NewsItem] = []

    def first_focus(self) -> QWidget | None:
        return self.list.first()

    def set_news(self, items: Sequence[news.NewsItem]) -> None:
        self.items = list(items)
        self.list.set_items([(str(n), elided(item.title)) for n, item in enumerate(self.items)])

    def item(self, key: str) -> news.NewsItem | None:
        return self.items[int(key)] if key.isdigit() and int(key) < len(self.items) else None


# --- Scores & Trophies ------------------------------------------------------------------------------------------

SCORES_INFO = (
    "Your best quiz score, the top ten rounds with their category, round and time, and the trophies. Every finished "
    "round of a saved game adds a score; a perfect round (every answer right, the round complete) adds a Perfect "
    "trophy. The quick quiz adds nothing.\n\n"
    "The X button clears every score and trophy: press it twice within five seconds. It cannot be undone.")


def when(value: str) -> str:
    """An ISO time as the page shows it: "2026-10-15 10:05:00"."""
    return value.replace("T", " ") if value else ""


def score_text(n: int, score: Score) -> str:
    return f"{n}.  {score.score}  ·  {score.category}  ·  round {score.round}  ·  {when(score.when)}"


def trophy_text(trophy: Trophy) -> str:
    return f"{trophy.kind}  ·  {trophy.category}  ·  {when(trophy.when)}"


def scores_summary(store: ScoreStore) -> str:
    return (f"Best score: {store.best()}. {len(store.scores)} rounds played, {len(store.trophies)} trophies earned. "
            "The quick quiz is not counted.")


class ScoresPane(FeaturePane):
    """The top ten on the left, the trophies (newest first) on the right; a list with nothing in it says why."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Scores & Trophies", SCORES_INFO, parent)
        row = QHBoxLayout()
        row.setSpacing(px(16))
        self.top = ListArea()
        self.trophies = ListArea()
        self.top_empty = text_label("No scores yet. Play a round of the quiz: every finished round of a saved game "
                                    "is listed here.", BODY + 1, color=DIM, wrap=True)
        self.trophies_empty = text_label("No trophies yet. A perfect round (every answer right, the round complete) "
                                         "earns one.", BODY + 1, color=DIM, wrap=True)
        for title, area, empty in ((f"Top {TOP}", self.top, self.top_empty),
                                   ("Trophies", self.trophies, self.trophies_empty)):
            column = QVBoxLayout()
            column.setSpacing(px(6))
            column.addWidget(text_label(title, 18, QFont.Weight.Bold))
            column.addWidget(empty)
            column.addWidget(area, 1)
            row.addLayout(column, 1)
        self.body.addLayout(row, 1)

    def first_focus(self) -> QWidget | None:
        return self.top.first() or self.trophies.first()

    def fill(self, store: ScoreStore) -> None:
        self.summary.setText(scores_summary(store))
        top = store.top()
        self.top.set_items([(str(n), score_text(n, s)) for n, s in enumerate(top, 1)])
        self.trophies.set_items([(str(n), trophy_text(t)) for n, t in enumerate(reversed(store.trophies))])
        self.top_empty.setVisible(not top)
        self.trophies_empty.setVisible(not store.trophies)


# --- The front page's pane --------------------------------------------------------------------------------------

class FrontPane(Pane):
    """Under the tiles: the focused feature's name and what it opens, and the status line (Steam, the browser)."""

    def __init__(self, info: str, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        self.title = text_label("", 22, QFont.Weight.ExtraBold)
        heading.addWidget(self.title)
        heading.addStretch()
        self.info = InfoPill("DatStation", info)
        heading.addWidget(self.info, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(heading)
        self.text = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.text)
        self.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)

    def show_feature(self, feature: Feature) -> None:
        self.title.setText(feature.name)
        self.text.setText(feature.text)
