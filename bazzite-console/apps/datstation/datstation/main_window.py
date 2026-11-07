# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window: the suite's header (the logo, the name with the version, the Steam state and the settings
menu), then the front page of tiles or the page that was opened. Escape, or a page's Back, returns to the tiles.
The settings menu adds the app to Steam (a non-Steam game, for Game Mode) and takes it out again."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QThread, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QKeyEvent
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QMessageBox, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from bc250_core import steam
from bc250_core.platform import xdg_open
from bc250_core.settings import open_settings, restore_geometry, save_geometry
from bc250_core.widgets import AppHeader, StatusText

from . import APP_NAME, INFO, LOGO_PATH, REPO_URL, __version__
from . import steam_shortcut
from .front_page import FrontPage
from .history_page import HistoryPage
from .news_page import NewsPage
from .pages import Page
from .quiz_page import QuizPage
from .regions_page import RegionsPage
from .scores import ScoreStore
from .scores_page import ScoresPage
from .style import label
from .versions_page import VersionsPage

GUIDES_URL = "https://manuals.playstation.net/document/en/products.html"
ABOUT = (f"<b>{APP_NAME} {__version__}</b><br><br>"
         "The PlayStation knowledge part of the DatStation Android app, on Bazzite: the quiz, the PlayStation "
         "history, the system version history, the region codes explained, the user guides and the PlayStation "
         "news.<br><br>"
         f"<a href='{REPO_URL}'>{REPO_URL}</a><br>"
         "<a href='https://github.com/RobertoTorino/DatStation'>github.com/RobertoTorino/DatStation</a> "
         "(the Android app)<br><br>GPL-3.0-or-later.")


class SteamWorker(QThread):
    """Steam's shortcut file is changed with Steam closed, which takes a while: off the window's thread."""

    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, action: Callable[[], bool], verb: str, parent=None):
        super().__init__(parent)
        self.action = action
        self.verb = verb

    def run(self) -> None:
        try:
            restarted = self.action()
        except (steam_shortcut.NotInstalled, steam.SteamError, steam.ShortcutError, OSError) as error:
            self.failed.emit(str(error))
            return
        self.done.emit(f"{APP_NAME} {self.verb} Steam." + (" Steam was started again." if restarted else ""))


class MainWindow(QMainWindow):
    def __init__(self, store: ScoreStore | None = None, steam_dir: Path | None = None, opener=xdg_open,
                 launcher: Path | None = None):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1120, 760)
        self.setMinimumSize(1040, 620)                  # four tiles on a row, each name on one line
        self.opener = opener
        self.steam_dir = steam_dir
        self.launcher = launcher
        self.worker: SteamWorker | None = None
        self.settings = open_settings(INFO)
        self.store = store or ScoreStore()
        self.last_key = "quiz"

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # The first line, as in every suite app: the logo, the title with the version, the Steam state and the
        # settings menu; the second row says what the app is.
        self.header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.steam_state = StatusText("Steam")
        self.header.add_state(self.steam_state)
        self._align_state_with_title()
        self.settings_button = QToolButton()
        self.settings_button.setText("Menu")
        self.settings_button.setProperty("quiet", True)         # the look of the pages' Back button
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setToolTip("Add to Steam, the scores, about the app")
        self.settings_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.settings_menu = QMenu(self.settings_button)
        self.add_steam_action = self.settings_menu.addAction("Add to Steam (Game Mode)", self.add_to_steam)
        self.remove_steam_action = self.settings_menu.addAction("Remove from Steam", self.remove_from_steam)
        self.settings_menu.addSeparator()
        self.settings_menu.addAction("Scores & Trophies", lambda: self.open("scores"))
        self.settings_menu.addSeparator()
        self.settings_menu.addAction("Project page", lambda: self.open_url(REPO_URL))
        self.settings_menu.addAction("About", self.about)
        self.settings_button.setMenu(self.settings_menu)
        self.header.add_action(self.settings_button)
        self.header.add_second(label("PlayStation knowledge from DatStation: the quiz, the history, the system "
                                     "versions, the region codes, the user guides and the news.", muted=True,
                                     wrap=True), 1)
        root.addLayout(self.header)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.front = FrontPage()
        self.front.opened.connect(self.open)
        self.stack.addWidget(self.front)
        self.pages: dict[str, Page] = {
            "quiz": QuizPage(self.store, self.settings),
            "history": HistoryPage(opener=opener),
            "versions": VersionsPage(),
            "regions": RegionsPage(),
            "news": NewsPage(opener=opener),
            "scores": ScoresPage(self.store),
        }
        for page in self.pages.values():
            page.back.connect(self.back)
            page.status.connect(self.show_status)
            self.stack.addWidget(page)
        self.statusBar().showMessage("Ready.")

        if not restore_geometry(self, self.settings):
            self.resize(1120, 760)
        QApplication.instance().aboutToQuit.connect(self._save_settings)
        self.refresh_steam_state()
        QTimer.singleShot(0, self.front.focus_tile)

    def _align_state_with_title(self) -> None:
        """The Steam state stands on the title's baseline: both sit at the bottom of the title row, the state raised
        by the difference between the two fonts' descents."""
        row = self.header.title_row
        self.header.title.ensurePolished()                  # the fonts come from style sheets
        self.steam_state.label.ensurePolished()
        row.setAlignment(self.header.title, Qt.AlignmentFlag.AlignBottom)
        row.setAlignment(self.steam_state, Qt.AlignmentFlag.AlignBottom)
        title_descent = QFontMetrics(self.header.title.font()).descent()
        state_descent = QFontMetrics(self.steam_state.label.font()).descent()
        margins = self.steam_state.layout().contentsMargins()
        margins.setBottom(max(0, title_descent - state_descent))
        self.steam_state.layout().setContentsMargins(margins)

    # -- navigation ---------------------------------------------------------------------------------------------

    @property
    def current_page(self) -> Page | None:
        widget = self.stack.currentWidget()
        return widget if isinstance(widget, Page) else None

    def open(self, key: str) -> None:
        """Open a feature from its tile (or the menu). The user guides open in the browser."""
        if key == "guides":
            self.open_url(GUIDES_URL)
            return
        page = self.pages[key]
        self.last_key = key
        current = self.current_page
        if current is not None and current is not page:
            current.deactivate()
        self.stack.setCurrentWidget(page)
        page.activate()
        page.first_focus().setFocus(Qt.FocusReason.OtherFocusReason)

    def back(self) -> None:
        current = self.current_page
        if current is not None:
            current.deactivate()
        self.stack.setCurrentWidget(self.front)
        self.front.focus_tile(self.last_key)
        self.statusBar().showMessage("Ready.")

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802  (Qt's name)
        if event.key() == Qt.Key.Key_Escape and self.current_page is not None:
            self.back()
            event.accept()
            return
        super().keyPressEvent(event)

    def show_status(self, text: str) -> None:
        self.statusBar().showMessage(text, 8000)

    def open_url(self, url: str) -> None:
        if self.opener(url):
            self.show_status(f"Opened {url} in the browser.")
        else:
            self.show_status("No browser could be started (xdg-open is missing).")

    def about(self) -> None:
        QMessageBox.about(self, f"About {APP_NAME}", ABOUT)

    # -- Steam --------------------------------------------------------------------------------------------------

    def _steam_folder(self) -> Path | None:
        return self.steam_dir or steam.find_steam()

    def refresh_steam_state(self) -> None:
        folder = self._steam_folder()
        if folder is None:
            self.steam_state.set_status("No Steam", "neutral", "Steam was not found on this system.")
            self.add_steam_action.setEnabled(False)
            self.remove_steam_action.setEnabled(False)
            return
        present = steam_shortcut.in_steam(folder)
        if present:
            self.steam_state.set_status("In Steam", "ok", "The app is a non-Steam game: start it from Game Mode.")
        else:
            self.steam_state.set_status("Not in Steam", "neutral",
                                        "Add it to Steam from the settings menu to start it from Game Mode.")
        self.add_steam_action.setEnabled(self.worker is None)
        self.remove_steam_action.setEnabled(present and self.worker is None)

    def _confirm_steam(self, what: str, outcome: str) -> bool:
        if steam.game_mode():
            QMessageBox.information(self, APP_NAME, f"Switch to Desktop Mode to {what}: Steam has to close while "
                                                    "its files change, and closing it from Game Mode ends the session.")
            return False
        text = f"{APP_NAME} will be {outcome} for every Steam user."
        if steam.steam_running():
            text += " Steam closes while its shortcut file changes and starts again afterwards."
        answer = QMessageBox.question(self, APP_NAME, text + " Continue?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.Yes)
        return answer == QMessageBox.StandardButton.Yes

    def add_to_steam(self) -> None:
        if self.worker is not None or not self._confirm_steam("add it to Steam", "added as a non-Steam game"):
            return
        self._run_steam(lambda: steam_shortcut.add(LOGO_PATH, self.launcher, self._steam_folder()), "was added to")

    def remove_from_steam(self) -> None:
        if self.worker is not None or not self._confirm_steam("remove it from Steam",
                                                              "removed from the non-Steam games"):
            return
        self._run_steam(lambda: steam_shortcut.remove(LOGO_PATH, self.launcher, self._steam_folder()),
                        "was removed from")

    def _run_steam(self, action: Callable[[], bool], verb: str) -> None:
        self.add_steam_action.setEnabled(False)
        self.remove_steam_action.setEnabled(False)
        self.steam_state.set_status("Working", "info", "Steam's shortcut file is being changed.")
        self.show_status("Changing Steam's shortcuts...")
        self.worker = SteamWorker(action, verb, self)
        self.worker.done.connect(self._steam_done)
        self.worker.failed.connect(self._steam_failed)
        self.worker.finished.connect(self._steam_finished)
        self.worker.start()

    def _steam_done(self, message: str) -> None:
        self.show_status(message)

    def _steam_failed(self, message: str) -> None:
        self.show_status(message)
        QMessageBox.warning(self, APP_NAME, message)

    def _steam_finished(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None
        self.refresh_steam_state()

    # -- settings -----------------------------------------------------------------------------------------------

    def _save_settings(self) -> None:
        save_geometry(self, self.settings)
        self.settings.sync()

    def closeEvent(self, event) -> None:  # noqa: N802  (Qt's name)
        current = self.current_page
        if current is not None:
            current.deactivate()
        self._save_settings()
        super().closeEvent(event)
