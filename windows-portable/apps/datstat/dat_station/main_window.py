# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's portable window, the header with the date, the time and the battery, the front page of
tiles (the BC250 app's front page: one tile per feature, its controller shape drawn on it) with the focused tile's
pane under them, the feature's page once a tile is opened, and the controller's buttons at the bottom.

Every action is a controller button in the legend at the bottom, A too, and a tap on the entry does the same; there
are no pills (owner, 29-10-2026: one way everywhere). Core's rule ends the legend: B goes back (a page to the tiles,
the quiz's round to its categories, a text to its list), View exits the app and Menu shows the information of the
page that shows. A tile's A opens its page; the user guides open in the browser. Nothing runs before it is asked for:
PS News loads its feed when its tile is opened.

The front page's Y puts the app in Steam's library as a non-Steam game (the BC250 app's Add to Steam, from its menu),
or brings its entry up to date; X takes it out, on a second press within five seconds (the suite's rule for an action
that needs care: no dialogs). Steam closes while its file changes and starts again after; the change runs off the
window's thread. So does the feed. View while Steam's file changes asks for a second press first.

The pages: the quiz (quiz_pane.py), History, System Version History, Region Codes, PS News and Scores & Trophies
(panes.py). The quiz's buttons depend on its screen (QuizPane.legend()); a round in play leaves on a second B."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, QTimer, pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, platform, power, steam
from bc250_core.gamepad import Gamepad
from bc250_core.portable import (BACK, EXIT, VIEW, Card, Legend, PortableHeader, PortableWindow, TextView, px,
                                 status_clock)
from bc250_core.settings import open_settings

from . import ANDROID_URL, APP_ID, APP_NAME, INFO, LOGO_PATH, REPO_URL, __version__, history, news, steam_shortcut
from .panes import (NEWS_SUMMARY, Feature, FrontPane, HistoryPane, NewsPane, RegionsPane, ScoresPane, SplitPane,
                    VersionsPane, features, symbol_pixmap)
from .quiz import DATA_CATEGORIES, Question, Result, load_questions
from .quiz_pane import Music, QuizPane
from .scores import ScoreStore, Trophy

STATUS_MS = 30_000              # the header's battery and time
CONFIRM_MS = 5000               # Take out of Steam, Clear scores, B in a round and View while busy ask again within this
COLUMNS = 4
TILE_W, TILE_H, GAP = 293, 176, 14      # the portal's tiles: two rows of four
GUIDES_URL = "https://manuals.playstation.net/document/en/products.html"
ABOUT = (f"{APP_NAME} {__version__}: the PlayStation knowledge part of the DatStation Android app, on your handheld: "
         "the quiz, the PlayStation history, the system version history, the region codes explained, the user "
         "guides and the PlayStation news. The quiz scores and trophies stay on this handheld.\n\n"
         "The d-pad moves between the tiles, A opens one, B goes back to the tiles and View exits the app. Y adds the "
         "app to Steam's library as a non-Steam game, to start it from there (Steam closes for it and starts again); "
         "X takes it out again, on a second press.\n\n"
         f"{REPO_URL}\n{ANDROID_URL} (the Android app)\n\nGPL-3.0-or-later.")
NO_BROWSER = "No browser could be opened."
BUSY = "Wait a moment: Steam's library is still being changed."


class _Worker(QObject):
    """Runs a job off the window's thread; done (the result, or the exception) arrives on the window's."""

    done = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.busy = False

    def run(self, job: Callable[[], object]) -> bool:
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return True

    def _run(self, job: Callable[[], object]) -> None:
        try:
            result = job()
        except Exception as error:  # noqa: BLE001  (shown on the page, not raised)
            result = error
        self.busy = False
        self.done.emit(result)


class MainWindow(PortableWindow):
    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery, store: ScoreStore | None = None,
                 settings: QSettings | None = None, questions: list[Question] | None = None,
                 music: Music | None = None, load_news: Callable[[], list[news.NewsItem]] | None = None,
                 open_url: Callable[[str], bool] = platform.open_path, steam_dir: Path | None | bool = False,
                 steam_closed: Callable[[Callable[[], None]], bool] = steam.with_steam_closed):
        """*store*: the quiz scores (scores.json in the suite's folder); *settings*: the app's .ini (the music);
        *load_news*: reads the PlayStation.Blog feed; *open_url*: opens a page in the browser; *steam_dir*: Steam's
        folder (False: found on this system, None: no Steam); *steam_closed*: runs a change with Steam closed."""
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.store = store or ScoreStore()
        self.settings = settings if settings is not None else open_settings(INFO, self)
        self.load_news = load_news or (lambda: news.load(INFO.user_agent))
        self.open_url = open_url
        self.steam_dir = steam.find_steam() if steam_dir is False else steam_dir
        self.steam_closed = steam_closed
        self.in_steam = self.steam_state()
        self.page = "front"                             # the page that shows: "front" or a feature's key
        self.last = "quiz"                              # the tile the focus goes back to
        self.asked = ""                                 # the action that waits for its second press
        self.job = ""                                   # "news" or "steam" while one runs

        questions = questions if questions is not None else load_questions()
        page = QVBoxLayout(self)
        page.setContentsMargins(*self.margins())
        self.header = PortableHeader(APP_NAME, __version__)
        page.addWidget(self.header)
        page.addSpacing(px(14))
        self.pages = QStackedWidget()
        page.addWidget(self.pages, 1)
        page.addSpacing(px(8))
        self.legend = Legend(self.common_items(back=False))
        page.addWidget(self.legend)

        # The front page: the tiles, two rows of four, and the focused one's pane under them
        self.front = QWidget()
        front = QVBoxLayout(self.front)
        front.setContentsMargins(0, 0, 0, 0)
        front.setSpacing(px(GAP))
        grid = QGridLayout()
        grid.setHorizontalSpacing(px(GAP))
        grid.setVerticalSpacing(px(GAP))
        self.features = features(len(questions), len(DATA_CATEGORIES))
        self.tiles: dict[str, Card] = {}
        for n, feature in enumerate(self.features):
            tile = Card(feature.tile, "", symbol_pixmap(feature.shape, feature.color))
            tile.setFixedSize(px(TILE_W), px(TILE_H))
            tile.focused.connect(lambda feature=feature: self.tile_focused(feature))
            tile.activated.connect(lambda key=feature.key: self.open(key))
            grid.addWidget(tile, n // COLUMNS, n % COLUMNS)
            self.tiles[feature.key] = tile
        for column in range(COLUMNS):
            grid.setColumnStretch(column, 1)
        front.addLayout(grid)
        self.front_pane = FrontPane(ABOUT)
        front.addWidget(self.front_pane, 1)
        self.pages.addWidget(self.front)

        self.quiz_pane = QuizPane(self.store, self.settings, questions, music)
        self.history_pane = HistoryPane()
        self.versions_pane = VersionsPane()
        self.regions_pane = RegionsPane()
        self.news_pane = NewsPane()
        self.scores_pane = ScoresPane()
        self.panes = {"quiz": self.quiz_pane, "history": self.history_pane, "versions": self.versions_pane,
                      "regions": self.regions_pane, "news": self.news_pane, "scores": self.scores_pane}
        for pane in self.panes.values():
            self.pages.addWidget(pane)

        self.worker = _Worker()
        self.worker.done.connect(self._done)
        self.quiz_pane.changed.connect(self.update_legend)
        self.quiz_pane.round_saved.connect(self.round_saved)
        self.history_pane.list.activated.connect(self.console_pictures)
        self.versions_pane.list.activated.connect(lambda _key: self.read_text(self.versions_pane.view))
        self.regions_pane.list.activated.connect(lambda _key: self.read_text(self.regions_pane.view))
        self.news_pane.list.current.connect(self.news_focused)
        self.news_pane.list.activated.connect(self.open_news)
        self.bind("accept", self.on_accept)
        self.bind("x", self.on_x)
        self.bind("y", self.on_y)
        self.bind("previous", self.on_lb)
        self.bind("next", self.on_rb)
        self.back.connect(self.on_back)
        self.confirm_timer = QTimer(self)
        self.confirm_timer.setSingleShot(True)
        self.confirm_timer.setInterval(CONFIRM_MS)
        self.confirm_timer.timeout.connect(self._confirm_over)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(self.update_status)
        self.front_pane.status.setText(self.steam_text())

    def start(self) -> None:
        """After the window is shown: the controller, the status line, the focus on the quiz's tile."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.tiles[self.last].setFocus()
        self.tile_focused(self.features[0])

    def update_status(self) -> None:
        self.header.set_status([*status_clock(), power.text(self.battery())])   # the battery last (owner, 30-10-2026)

    # The pages

    def tile_focused(self, feature: Feature) -> None:
        self.last = feature.key
        self.front_pane.show_feature(feature)
        self.update_legend()

    def open(self, key: str) -> None:
        """A tile's A: its page (the scores read again, the feed loaded the first time); the user guides open in the
        browser."""
        self._confirm_over()
        if key == "guides":
            self.open_link(GUIDES_URL, self.front_pane.status)
            return
        pane = self.panes[key]
        self.last = key                                 # B comes back to its tile
        self.pages.setCurrentWidget(pane)
        self.page = key
        if key == "quiz":
            self.quiz_pane.activate()
        elif key == "scores":
            self.store.load()
            self.scores_pane.fill(self.store)
            self.scores_pane.status.setText("")
        elif key == "news" and not self.news_pane.items:
            self.refresh_news()
        (pane.first_focus() or pane).setFocus()
        self.update_legend()

    def show_front(self) -> None:
        if self.page == "quiz":
            self.quiz_pane.deactivate()
        self._confirm_over()
        self.page = "front"
        last = self.last                                # the switch hands the focus to some tile on the way
        self.pages.setCurrentWidget(self.front)
        self.tiles[last].setFocus()
        self.update_legend()

    def on_back(self) -> None:
        """B: a page back to the tiles; the quiz's results and categories one step back, a round in play on a second
        press; a text back to its list; on the tiles nothing (View exits the app)."""
        if self.page == "front":
            return
        if self.page == "quiz":
            screen = self.quiz_pane.screen()
            if screen == "categories":
                self.show_front()
            elif screen == "results" or self.ask("leave", self.quiz_pane.status,
                                                  "Press B again to leave the round: it is lost."):
                self.quiz_pane.show_categories()
            return
        pane = self.panes[self.page]
        if isinstance(self.focusWidget(), TextView) and isinstance(pane, SplitPane):
            pane.list.focus(pane.shown)                 # back on the row whose text shows
            return
        self.show_front()

    def read_text(self, view: TextView) -> None:
        """A on a system or a console's codes: the focus into its text, where the d-pad scrolls it."""
        view.setFocus()
        self.update_legend()

    def on_accept(self) -> None:
        """A where the focus is on no card or row: the quiz's results start the next game."""
        if self.page == "quiz" and self.quiz_pane.screen() == "results":
            self.quiz_pane.again()

    def on_x(self) -> None:
        if self.page == "front":
            self.take_out_of_steam()
        elif self.page == "quiz":
            self.quiz_pane.skip()
        elif self.page == "news":
            self.open_link(news.UPCOMING_URL, self.news_pane.status)
        elif self.page == "scores":
            self.clear_scores()

    def on_y(self) -> None:
        if self.page == "front":
            self.add_to_steam()
        elif self.page == "quiz":
            self.quiz_pane.toggle_pause()
        elif self.page == "news":
            self.refresh_news()

    def on_lb(self) -> None:
        if self.page == "quiz":
            self.quiz_pane.toggle_mute()

    def on_rb(self) -> None:
        if self.page == "news":
            self.open_link(news.NEW_RELEASES_URL, self.news_pane.status)

    def update_legend(self) -> None:
        """The page's buttons, then core's Menu Info, B Back (Press again while B waits for its second press) and
        View Exit (the suite's rule)."""
        if not hasattr(self, "legend"):
            return
        items: list[tuple[str, str]] = []
        focus = self.focusWidget()
        if self.page == "front":
            items.append(("A", "Open in browser" if self.last == "guides" else "Open"))
            if self.steam_dir is not None:
                items.append(("Y", "Update in Steam" if self.in_steam else "Add to Steam"))
                if self.in_steam:
                    items.append(("X", "Press again" if self.asked == "unsteam" else "Take out of Steam"))
        elif self.page == "quiz":
            items += self.quiz_pane.legend()
        elif self.page == "history" and self.history_pane.list.focused():
            items.append(("A", "Pictures"))
        elif self.page in ("versions", "regions") and not isinstance(focus, TextView):
            items.append(("A", "Read"))
        elif self.page == "news":
            if self.news_pane.list.focused():
                items.append(("A", "Open"))
            items += [("X", "Upcoming games"), ("RB", "New releases"), ("Y", "Refresh")]
        elif self.page == "scores" and (self.store.scores or self.store.trophies):
            items.append(("X", "Press again" if self.asked == "clear" else "Clear scores"))
        common = self.common_items(back=self.page != "front")
        if self.asked == "leave":
            common = [("B", "Press again") if item == BACK else item for item in common]
        if self.asked == "exit":
            common = [(VIEW, "Press again") if item == EXIT else item for item in common]
        self.legend.set_items([*items, *common])

    # A second press

    def ask(self, what: str, status, text: str) -> bool:
        """A second press of *what* within five seconds: True on it; on the first, *text* on the *status* line."""
        if self.asked == what:
            self._confirm_over(keep_status=True)
            return True
        self.asked = what
        self.confirm_timer.start()
        status.setText(text)
        self.update_legend()
        return False

    def _confirm_over(self, keep_status: bool = False) -> None:
        self.confirm_timer.stop()
        if self.asked and not keep_status:
            for status in (self.front_pane.status, self.quiz_pane.status, self.scores_pane.status):
                if status.text().startswith("Press "):
                    status.setText(self.steam_text() if status is self.front_pane.status else "")
        self.asked = ""
        self.update_legend()

    def exit_app(self) -> None:
        if self.worker.busy and self.job == "steam" and not self.ask(
                "exit", self.front_pane.status if self.page == "front" else self.panes[self.page].status,
                "Press View again to exit: Steam's library may be left half changed."):
            return
        self.close()

    # The browser

    def open_link(self, url: str, status) -> bool:
        """A page in the browser, said on the *status* line."""
        if not self.open_url(url):
            status.setText(NO_BROWSER)
            return False
        status.setText(f"Opened {url} in your browser.")
        return True

    def console_pictures(self, key: str) -> None:
        """A on a console: pictures of it on the web, as the BC250 app's history opens them."""
        console = self.history_pane.console(key)
        if console is None:
            return
        if self.open_url(history.search_url(console.name)):
            self.history_pane.status.setText(f"Searching the web for pictures of {console.name}.")
        else:
            self.history_pane.status.setText(NO_BROWSER)

    # PS News

    def refresh_news(self) -> None:
        if not self.worker.run(self.load_news):
            self.news_pane.status.setText(BUSY if self.job == "steam" else "Loading the PlayStation Blog feed…")
            return
        self.job = "news"
        self.news_pane.summary.setText("Loading official PlayStation blog updates…")
        self.news_pane.status.setText("")

    def news_focused(self, key: str) -> None:
        item = self.news_pane.item(key)
        if item is not None:
            self.news_pane.status.setText(news.format_date(item.published) or item.link)
        self.update_legend()

    def open_news(self, key: str) -> None:
        """A on an announcement: the post in the browser; only PlayStation's own sites (news.allowed), as the BC250
        app opens them."""
        item = self.news_pane.item(key)
        if item is None:
            return
        if not news.allowed(item.link):
            self.news_pane.status.setText("Blocked unexpected link.")
            return
        self.open_link(item.link, self.news_pane.status)

    def _news_done(self, result: object) -> None:
        pane = self.news_pane
        if isinstance(result, Exception):
            message = str(result) if isinstance(result, news.NewsError) else \
                f"Failed to load PlayStation updates: {result}"
            self.log.error(message)
            pane.set_news([])
            pane.summary.setText("Could not load announcements. For this page you need an active internet "
                                 "connection: Y tries again.")
            pane.status.setText(message)
        else:
            pane.set_news(result)
            pane.summary.setText(NEWS_SUMMARY)
            pane.status.setText(f"{len(pane.items)} announcements loaded." if pane.items else
                                "No announcements found.")
            if self.page == "news" and pane.items and not pane.list.focused():
                pane.list.first().setFocus()

    # Steam

    def steam_state(self) -> bool:
        try:
            return steam_shortcut.in_steam(self.steam_dir) if self.steam_dir is not None else False
        except OSError as error:
            self.log.error(f"Steam's shortcuts could not be read: {error}")
            return False

    def steam_text(self) -> str:
        if self.steam_dir is None:
            return "Steam is not installed, or was never signed in on this handheld."
        if self.in_steam:
            return f"{APP_NAME} is in Steam's library: start it from there too."
        return f"Y adds {APP_NAME} to Steam's library, to start it from there."

    def add_to_steam(self) -> None:
        self.change_steam(remove=False)

    def take_out_of_steam(self) -> None:
        if not self.in_steam or self.steam_dir is None:
            return
        if self.ask("unsteam", self.front_pane.status, "Press X again to take the app out of Steam: Steam closes "
                                                       "for it and starts again."):
            self.change_steam(remove=True)

    def change_steam(self, remove: bool) -> None:
        status = self.front_pane.status
        if self.steam_dir is None:
            status.setText(self.steam_text())
            return
        steam_dir, closed = self.steam_dir, self.steam_closed
        if not self.worker.run(lambda: (remove, steam_shortcut.apply(LOGO_PATH, steam_dir, remove, closed))):
            status.setText("Wait a moment: the news is still loading." if self.job == "news" else BUSY)
            return
        self.job = "steam"
        status.setText("Taking the app out of Steam's library…" if remove else "Adding the app to Steam's library…")
        self.update_legend()

    def _steam_done(self, result: object) -> None:
        status = self.front_pane.status
        self.in_steam = self.steam_state()
        if isinstance(result, Exception):
            message = f"Steam was not changed: {result}"
            self.log.error(message)
            status.setText(message)
        else:
            remove, restarted = result
            again = " Steam was closed for it and starts again." if restarted else ""
            message = (f"{APP_NAME} is no longer in Steam.{again}" if remove else
                       f"{APP_NAME} is in Steam's library.{again}")
            self.log.info(message)
            status.setText(message)

    def _done(self, result: object) -> None:
        job, self.job = self.job, ""
        if job == "news":
            self._news_done(result)
        elif job == "steam":
            self._steam_done(result)
            if self.asked == "exit":
                self._confirm_over(keep_status=True)
        self.update_legend()

    # The quiz and the scores

    def round_saved(self, result: Result, earned: list[Trophy]) -> None:
        if result.saves:
            self.log.info(f"Quiz round saved: {result.category}, round {result.round}, score {result.score}"
                          + (", a Perfect trophy." if earned else "."))

    def clear_scores(self) -> None:
        status = self.scores_pane.status
        if not (self.store.scores or self.store.trophies):
            status.setText("There are no scores to clear.")
            return
        if self.ask("clear", status, "Press X again to remove every quiz score and trophy: it cannot be undone."):
            self.store.clear()
            self.scores_pane.fill(self.store)
            status.setText("Scores and trophies removed.")
            self.log.info("Scores and trophies removed.")
            self.scores_pane.setFocus()
            self.update_legend()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        self.confirm_timer.stop()
        self.quiz_pane.deactivate()
        super().closeEvent(event)
