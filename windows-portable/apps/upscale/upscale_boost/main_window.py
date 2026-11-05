# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's portable window, as Xenia Manager lays it out: the cards on the left (HelixSR, Games,
Deployments, Settings, Log: the BC250 suite's BC-250 Upscaler Manager's Setup, Games, Overview, helixsr.ini and Help
pages, its Deploy page in the Games card's OptiScaler page), what the focused one shows on the right, the
controller's buttons at the bottom.

Every action is a controller button in the legend at the bottom, A too, and a tap on the entry does the same; there
are no pills and no dialogs (owner, 29-10-2026: one way everywhere). What the BC250 app asked in a dialog asks for a
second press within five seconds here (the first install into a game, Go back, Forget, building a current payload
again), the legend's entry and the status line saying so. A press that cannot act now says why on the status line.
Core's rule ends the legend: B goes back (a pane to its card, a page to where it came from), View exits the app and
Menu shows the information of the pane that shows. Windows' own windows are not used: a folder or a file is chosen in
core's browser, the log is read in the pane.

The HelixSR pane: the payload, the newest release and the version to get; A Get HelixSR (download and build, off the
window's thread, its output in the pane and the log), X Cancel while it runs, Y Check now, LB the version (latest or
the fallback), RB NVIDIA's DLL (download it, or a game's copy), LT Import (a release built by hand). The Games pane:
every Steam game and the folders added, looked through off the window's thread; A Run with HelixSR, Y Go back, X
OptiScaler, LB Add a folder, RB Take off the list, LT Rescan. The Deployments pane: every place HelixSR was put; Y Go
back, X Forget, RB Update older games. The Settings pane: helixsr.ini in tabs, A steps a value and saves it as the
payload's helixsr.ini at once, X Defaults, Y Apply to a game. The Log pane: where HelixSR is kept, the newest lines of
the log, A shows the whole log."""

from __future__ import annotations

import dataclasses
import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, browse, power, steam
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private
from bc250_core.portable import DIM, EXIT, VIEW, Card, Legend, Pane, PortableHeader, PortableWindow, px, \
    status_clock

from . import APP_ID, APP_NAME, __version__, acquire, app_home, backend, ini_settings
from .acquire import FALLBACK_VERSION, Setup, SetupOutcome, SetupRequest, UpdateStatus
from .backend import MODE_FOLDER, MODE_REPLACE, Deployment, GameScan, HelixError, HelixIni
from .panes import (APPLY_INFO, BROWSE_INFO, CHECK_AT_START, DEPLOY_INFO, DLSS_INFO, GAMES_INFO, OPTI_INFO, HelixPane,
                    ListPane, LogPane, SettingsPane)

STATUS_MS = 30_000              # the header's battery and time
PROGRESS_MS = 500               # the megabytes of a download, the builder's newest lines
CONFIRM_MS = 5000               # an action that needs care asks for a second press within this
RENDER_MS = 200                 # the games list drawn again this long after a game was looked through
CARDS_WIDTH = 460               # the cards' column; the panes take the rest
CARD_HEIGHT = 100               # five cards and their gaps fit the column at 720 px high
OUTPUT_LINES = 6                # the builder's newest lines on the HelixSR pane
OUTPUT_MAX = 2000               # the builder's lines kept
LOG_LINES = 12                  # the newest lines of the app's log in the Log pane
LOG_MAX = 2000                  # the lines of the log the whole view shows, the newest
MB = 1 << 20
BUSY = "Wait a moment: Get HelixSR is still running (the X button on the HelixSR card cancels it)."
NOT_BUILT = "Get HelixSR first (the HelixSR card): there is nothing to put in yet."
FALLBACK_KEY = "setup/fallback"
DLSS_KEY = "setup/dlss"
CHECK_KEY = "updates/check_on_start"
FOLDERS_KEY = "games/folders"
TAB_INTRO = ("Every change is saved at once as the payload's helixsr.ini: what HelixSR gets in each game you put it "
             "in from now on. The A button changes the setting the focus is on, the LB and RB buttons change the tab. "
             "The Y button writes them into a game that has HelixSR already; the X button sets HelixSR's defaults. "
             "HelixSR reads them when a game starts. Rows the payload's HelixSR does not read are not shown.\n\n")
TAB_INFO = {key: TAB_INTRO + "\n".join(f"{setting.label}: {setting.tip}" for setting in group)
            + ("\nLook for a new HelixSR at start: whether the app asks GitHub at every start (the HelixSR card's Y "
               "button asks any time)." if key == ini_settings.TABS[-1][0] else "")
            for key, _name, group in ini_settings.TABS}
BROWSE_TITLES = {"folder": "Add a game folder", "import": "Import HelixSR", "dlss": "NVIDIA's DLL",
                 "second": "Second upscaler"}
BROWSE_SUMMARIES = {"folder": "Where is the game? Open a place, then its folder; the X button adds it.",
                    "import": "Where is the HelixSR release? The X button takes its folder, the A button its zip.",
                    "dlss": f"Where is {acquire.DLSS_DLL}? Open a place, then the folder it is in.",
                    "second": "Where is the second FidelityFX upscaler DLL? Open a place, then the folder it is in."}
BROWSE_SUFFIXES = {"folder": (), "import": (".zip",), "dlss": (".dll",), "second": (".dll",)}


def wrappable(path: Path) -> str:
    """A path as the screen shows it: the user's folders by their variable (%LOCALAPPDATA%: never the user's name,
    owner 29-10-2026), wrapping after each backslash, as a long one would make the pane wider than the screen."""
    return private(path).replace("\\", "\\​")


class _Worker(QObject):
    """Runs a job off the window's thread; done (the result, or the exception), what it says (said: a line of the
    builder's output) and what it does (staged) arrive on the window's."""

    done = pyqtSignal(object)
    said = pyqtSignal(str)
    staged = pyqtSignal(str)

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
        except Exception as error:  # noqa: BLE001  (shown in the pane, not raised)
            result = error
        self.busy = False
        self.done.emit(result)


class _Scanner(QObject):
    """Looks through game folders off the window's thread (backend.scan_game): scanned(GameScan) for each, finished
    after the last. A new list while one runs waits for it."""

    scanned = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self, scan: Callable[..., GameScan]):
        super().__init__()
        self.scan = scan
        self.busy = False
        self.pending: list[tuple[Path, str]] = []
        self._cancel = False
        self.finished.connect(self._next)

    def start(self, items: list[tuple[Path, str]], payload_dir: Path) -> None:
        self.payload_dir = payload_dir
        self.pending += [item for item in items if item not in self.pending]
        if not self.busy:
            self._next()

    def _next(self) -> None:
        items, self.pending = self.pending, []
        if not items or self._cancel:
            self.busy = False
            return
        self.busy = True
        threading.Thread(target=self._run, args=(items, self.payload_dir), daemon=True).start()

    def _run(self, items: list[tuple[Path, str]], payload_dir: Path) -> None:
        for folder, app_id in items:
            if self._cancel:
                break
            try:
                result = self.scan(folder, payload_dir, app_id, cancelled=lambda: self._cancel)
            except OSError:
                result = GameScan(folder, [], app_id)
            self.scanned.emit(result)
        self.finished.emit()

    def cancel(self) -> None:
        self._cancel = True


class MainWindow(PortableWindow):
    release_found = pyqtSignal(object)                  # the update check's UpdateStatus, from its thread

    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery, home: Path | None = None,
                 steam_dir: Path | None | bool = False, settings: QSettings | None = None,
                 check_updates: Callable[[str], UpdateStatus] = acquire.check_updates,
                 setup: Callable[..., Setup] = Setup, scan: Callable[..., GameScan] = backend.scan_game,
                 running: Callable[[], str] = backend.running_app_id,
                 open_url: Callable[[str], None] = steam.open_url,
                 find_dlss: Callable[..., list[Path]] = acquire.find_dlss_dlls,
                 roots: Callable[[], list[Path]] = browse.drives, user_home: Path | None = None):
        """*home*: the app's folder (the payload, the downloads, the builder's Python and compiler, the list of
        deployments); *steam_dir*: Steam's folder (False: found on this system, None: no Steam); *settings*: the
        app's (its .ini, create_app's); *check_updates*: asks GitHub for the newest HelixSR; *setup*: makes the Get
        HelixSR job; *scan*: looks through a game folder; *running*: the AppID of the game Steam runs; *open_url*:
        hands a steam:// address to Steam; *find_dlss*: looks for NVIDIA's DLL in the Steam libraries; *roots* and
        *user_home*: where the browser starts."""
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.home = home or app_home()
        self.payload_dir = self.home / "payload"
        self.work_dir = self.home / "work"
        self.helix_data = self.home / "HelixSR"
        self.store = backend.DeploymentStore(self.home / "deployments.json")
        self.steam_dir = steam.find_steam() if steam_dir is False else steam_dir
        self.settings = settings if settings is not None else QSettings()
        self.check_job, self.setup_job, self.running = check_updates, setup, running
        self.open_url, self.find_dlss = open_url, find_dlss
        self.roots, self.user_home = roots, user_home
        self.libraries: list[Path] = []
        self.app_ids: dict[Path, str] = {}
        self.games: dict[Path, GameScan | None] = {}    # None: not looked through yet
        self.checking_games: set[Path] = set()          # being looked through (again)
        self.update: UpdateStatus | None = None
        self.checking = False                           # the update check runs
        self.busy = False                               # Get HelixSR runs
        self.job: Setup | None = None
        self.got = self.total = 0                       # a download's bytes (the worker's thread writes them)
        self.got_name = ""
        self.stage = ""                                 # what Get HelixSR does now
        self.output: list[str] = []                     # the builder's lines
        self.message = ""                               # the HelixSR pane's last outcome
        self.confirm = ""                               # the action waiting for its second press
        self.close_asked = False
        self.browser: browse.Browser | None = None
        self.browse_for = ""                            # "folder", "import", "dlss" or "second"
        self.browse_from: Pane | None = None
        self.opti_game: Path | None = None              # the game the OptiScaler page is for
        self.opti_exe: Path | None = None
        self.opti_install = False
        self.opti_second: Path | None = None
        self.opti_ini = True
        self.dlss_found: list[Path] = []
        self.ini, self.template = HelixIni(), backend.DEFAULT_INI_TEXT

        page = QVBoxLayout(self)
        page.setContentsMargins(*self.margins())
        self.header = PortableHeader(APP_NAME, __version__)
        page.addWidget(self.header)
        page.addSpacing(px(14))
        body = QHBoxLayout()
        column = QWidget()
        column.setFixedWidth(px(CARDS_WIDTH))
        cards = QVBoxLayout(column)
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(px(12))
        self.helix_card = Card("HelixSR", "Get it.")
        self.games_card = Card("Games", "Put HelixSR in, or take it out.")
        self.deploy_card = Card("Deployments", "Where HelixSR is.")
        self.settings_card = Card("Settings", "helixsr.ini: sharpening, the network, the log.")
        self.log_card = Card("Log", "Where HelixSR is kept, and this app's log.")
        for card in (self.helix_card, self.games_card, self.deploy_card, self.settings_card, self.log_card):
            card.setFixedHeight(px(CARD_HEIGHT))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()
        self.helix_pane = HelixPane()
        self.games_pane = ListPane("Games", "Games", GAMES_INFO)
        self.deploy_pane = ListPane("Deployments", "Deployments", DEPLOY_INFO)
        self.settings_pane = SettingsPane(TAB_INFO)
        self.log_pane = LogPane()
        self.opti_pane = ListPane("OptiScaler", "OptiScaler", OPTI_INFO)
        self.dlss_pane = ListPane("NVIDIA's DLL", "NVIDIA's DLL", DLSS_INFO)
        self.apply_pane = ListPane("Apply to a game", "Apply to a game", APPLY_INFO)
        self.browse_pane = ListPane("Browse", "Browse", BROWSE_INFO)
        for pane in (self.helix_pane, self.games_pane, self.deploy_pane, self.settings_pane, self.log_pane,
                     self.opti_pane, self.dlss_pane, self.apply_pane, self.browse_pane):
            self.panes.addWidget(pane)
        self.cards: dict[Pane, Card] = {self.helix_pane: self.helix_card, self.games_pane: self.games_card,
                                        self.deploy_pane: self.deploy_card, self.settings_pane: self.settings_card,
                                        self.log_pane: self.log_card, self.opti_pane: self.games_card,
                                        self.dlss_pane: self.helix_card, self.apply_pane: self.settings_card,
                                        self.browse_pane: self.games_card}
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend([EXIT])
        page.addWidget(self.legend)

        self.worker = _Worker()
        self.worker.done.connect(self._built)
        self.worker.said.connect(self._said)
        self.worker.staged.connect(self._staged)
        self.find_worker = _Worker()
        self.find_worker.done.connect(self._dlss_found)
        self.scanner = _Scanner(scan)
        self.scanner.scanned.connect(self._scanned)
        self.release_found.connect(self._release_found)
        self.helix_card.focused.connect(lambda: self.show_pane(self.helix_pane))
        self.helix_card.activated.connect(self.get_helixsr)
        self.games_card.focused.connect(lambda: self.show_pane(self.games_pane))
        self.games_card.activated.connect(lambda: self.focus_list(self.games_pane))
        self.deploy_card.focused.connect(lambda: self.show_pane(self.deploy_pane))
        self.deploy_card.activated.connect(lambda: self.focus_list(self.deploy_pane))
        self.settings_card.focused.connect(lambda: self.show_pane(self.settings_pane))
        self.settings_card.activated.connect(self.settings_pane.focus_first)
        self.log_card.focused.connect(lambda: self.show_pane(self.log_pane))
        self.log_card.activated.connect(self.view_log)
        self.log_pane.tapped.connect(self.view_log)
        self.games_pane.list.picked.connect(self.run_game)
        self.games_pane.list.current.connect(self.game_focused)
        self.deploy_pane.list.current.connect(self.deployment_focused)
        self.opti_pane.list.picked.connect(self.opti_picked)
        self.dlss_pane.list.picked.connect(self.dlss_picked)
        self.apply_pane.list.picked.connect(self.apply_to)
        self.browse_pane.list.picked.connect(self.browse_picked)
        for key, pill in self.settings_pane.pills.items():
            pill.activated.connect(lambda key=key: self.step_setting(key))
        self.bind("accept", self.a_action)
        self.bind("x", self.x_action)
        self.bind("y", self.y_action)
        self.bind("previous", self.lb_action)
        self.bind("next", self.rb_action)
        self.bind("lt", self.lt_action)
        self.back.connect(self.on_back)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(self.update_status)
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(PROGRESS_MS)
        self.progress_timer.timeout.connect(self.refresh_helix)
        self.confirm_timer = QTimer(self)
        self.confirm_timer.setSingleShot(True)
        self.confirm_timer.setInterval(CONFIRM_MS)
        self.confirm_timer.timeout.connect(self._confirm_over)
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(RENDER_MS)
        self.render_timer.timeout.connect(self.show_games)
        self.load_ini()
        self.refresh()

    def start(self) -> None:
        """After the window is shown: the controller, the status line, the games looked through, the focus on the
        HelixSR card, and GitHub asked for the newest HelixSR (off the window's thread) unless that is turned off."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.refresh_games()
        self.helix_card.setFocus()
        self.show_pane(self.helix_pane)
        if self.settings.value(CHECK_KEY, True, type=bool):
            self.check_now()

    def update_status(self) -> None:
        self.header.set_status([*status_clock(), power.text(self.battery())])   # the battery last (owner, 30-10-2026)

    # The legend

    def show_pane(self, pane: Pane) -> None:
        if pane is not self.log_pane and self.log_pane.viewing:
            self.log_pane.show_summary()
        old, focus = self.panes.currentWidget(), self.focusWidget()
        if pane is not old and focus is not None and old.isAncestorOf(focus):
            self.setFocus()                             # off the old pane first: a row hidden with the focus would
        self.panes.setCurrentWidget(pane)               # hand it to the first card, and its pane would show
        if pane is self.log_pane:
            self.refresh_log()
        elif pane is self.deploy_pane:
            self.show_deployments()
        self.update_legend()

    def legend_items(self) -> list[tuple[str, str]]:
        """The legend for the pane that shows: its actions on the controller's buttons, A too (a tap on an entry does
        the same), then core's Menu Info, B Back (in a pane, and on a page) and View Exit."""
        if self.close_asked:
            return [(VIEW, "Press again to exit")]
        pane = self.panes.currentWidget()
        again = "Press again"
        items: list[tuple[str, str]] = []
        if pane is self.helix_pane:
            if self.busy:
                items = [("X", "Cancel")]
            else:
                items = [("A", again if self.confirm == "build" else "Get HelixSR"),
                         ("Y", "Check now"), ("LB", "Use the latest" if self.fallback() else f"Use {FALLBACK_VERSION}"),
                         ("RB", "NVIDIA's DLL"), ("LT", "Import")]
        elif pane is self.games_pane:
            game = self.focused_game()
            scan = self.games.get(game) if game is not None else None
            if scan is not None and scan.usable:
                items.append(("A", again if self.confirm == f"run:{game}" else
                              "Run with HelixSR" if scan.app_id else "Put HelixSR in"))
            if scan is not None and any(d.deployed for d in scan.dlls):
                items.append(("Y", again if self.confirm == f"goback:{game}" else "Go back"))
            if game is not None:
                items.append(("X", "OptiScaler"))
            items.append(("LB", "Add a folder"))
            if game is not None and game in self.added():
                items.append(("RB", "Take off the list"))
            items.append(("LT", "Rescan"))
        elif pane is self.deploy_pane:
            dep = self.focused_deployment()
            if dep is not None:
                items += [("Y", again if self.confirm == f"remove:{dep.path}" else "Go back"),
                          ("X", again if self.confirm == f"forget:{dep.path}" else "Forget")]
            if any(backend.needs_update(d, self.payload_dir) for d in self.store.items):
                items.append(("RB", "Update older games"))
        elif pane is self.settings_pane:
            items = [("A", "Change"), ("X", again if self.confirm == "defaults" else "Defaults"),
                     ("Y", "Apply to a game"), ("LB", "Previous tab"), ("RB", "Next tab")]
        elif pane is self.log_pane:
            items = [] if self.log_pane.viewing else [("A", "View log")]
        elif pane is self.opti_pane:
            items = [("A", "Change"), ("X", again if self.confirm == "opti" else "Put HelixSR in")]
            if self.opti_folder() is not None and (self.opti_folder() / backend.HELIXSR_DLL).is_file():
                items.append(("Y", again if self.confirm == "optiremove" else "Go back"))
            if not self.opti_install:
                items.append(("LB", "Copy lines"))
        elif pane is self.dlss_pane:
            items = [("A", "Use"), ("Y", "Find in Steam")]
        elif pane is self.apply_pane:
            items = [("A", "Write")] if self.store.items else []
        elif pane is self.browse_pane:
            items = [("A", "Open")]
            if self.browser is not None and self.browser.path is not None and self.browse_for in ("folder", "import"):
                items.append(("X", "Use this folder"))
        on_a_page = pane in (self.opti_pane, self.dlss_pane, self.apply_pane, self.browse_pane) or \
            self.log_pane.viewing
        return [*items, *self.common_items(True if on_a_page else None)]

    def update_legend(self) -> None:
        if hasattr(self, "legend"):
            self.legend.set_items(self.legend_items())

    def focus_list(self, pane: ListPane) -> None:
        """The list's first row, or the pane's card while the list is empty."""
        (pane.list.first() or self.cards[pane]).setFocus()

    def ask_again(self, action: str, status, text: str) -> bool:
        """An action that needs care (owner, 29-10-2026: no dialogs): True when *action* was pressed a moment ago,
        else it waits five seconds for the second press, *text* on the pane's status line meanwhile."""
        if self.confirm == action:
            self._confirm_over()
            return True
        self.confirm = action
        self.confirm_timer.start()
        status.setText(text)
        self.update_legend()
        return False

    def _confirm_over(self) -> None:
        self.confirm_timer.stop()
        self.confirm = ""
        if self.close_asked:
            self.close_asked = False
            self.refresh_helix()
        self.update_legend()

    # Everything the cards say

    def refresh(self) -> None:
        self.refresh_helix()
        self.refresh_settings()
        self.show_deployments()
        self.update_legend()

    def payload(self) -> backend.PayloadStatus:
        return backend.payload_status(self.payload_dir)

    def fallback(self) -> bool:
        return self.settings.value(FALLBACK_KEY, False, type=bool)

    def dlss_file(self) -> Path | None:
        value = str(self.settings.value(DLSS_KEY, "") or "")
        return Path(value) if value else None

    def on_fallback(self, status: backend.PayloadStatus) -> bool:
        return self.fallback() and acquire.version_tuple(status.version) == acquire.version_tuple(FALLBACK_VERSION)

    def helix_rows(self, status: backend.PayloadStatus) -> list[tuple[str, str]]:
        network = ("built into the DLL" if status.embedded else "ready" if status.network_ready else
                   "not built" if status.dll else "—")
        rows = [("Payload", status.version or ("HelixSR" if status.dll else "not built yet")), ("Network", network)]
        if status.dll:
            rows.append(("OptiScaler", "in the payload" if status.optiscaler else "not in the payload"))
        update = self.update
        if self.checking:
            latest = "asking GitHub…"
        elif update is None:
            latest = "not checked yet: the Y button asks"
        elif update.latest.error:
            latest = f"unknown ({update.latest.error})"
        else:
            latest = f"{update.latest.version} ({update.latest.published})"
            if update.unsupported:
                latest += f"; HelixSR {update.unsupported} is out, this app does not support it yet"
        rows.append(("Latest release", latest))
        rows.append(("Version to get", f"{FALLBACK_VERSION}, the fallback" if self.fallback() else "the latest"))
        dlss = self.dlss_file()
        rows.append(("NVIDIA's DLL", wrappable(dlss) if dlss is not None else "downloaded from NVIDIA"))
        return rows

    def helix_state(self, status: backend.PayloadStatus) -> str:
        """The HelixSR pane's status line while nothing else is said."""
        if self.busy:
            if self.got_name and self.total:
                return f"{self.stage}… {self.got_name}: {self.got / MB:.1f} of {self.total / MB:.1f} MB"
            return f"{self.stage}…" if self.stage else "Starting…"
        update = self.update
        if not status.ready:
            return ("HelixSR's network is not built: the A button gets HelixSR and builds it." if status.dll else
                    "The A button gets HelixSR and builds it on this handheld (a few minutes).")
        if update is not None and update.update_available and not self.on_fallback(status):
            return f"HelixSR {update.latest.version} is out: the A button gets it."
        return ""

    def refresh_helix(self) -> None:
        status = self.payload()
        self.helix_pane.fill(self.helix_rows(status), self.output[-OUTPUT_LINES:])
        text = self.helix_state(status) if self.busy else self.message or self.helix_state(status)
        if self.close_asked:
            text = "Press View again to exit: Get HelixSR stops."
        elif self.confirm == "build":
            text = (f"The payload already has HelixSR {status.version or ''} with its network. Press the A button "
                    "again to build it again.")
        self.helix_pane.status.setText(text)
        update = self.update
        newer = update is not None and update.update_available and not self.on_fallback(status)
        if self.busy:
            self.helix_card.set_text(self.stage or "Getting HelixSR…", DIM)
        elif not status.ready:
            self.helix_card.set_text("Not built yet: the A button gets it." if not status.dll else
                                     "The network is not built yet.", DIM)
        else:
            self.helix_card.set_text(f"HelixSR {status.version or ''}, ready" +
                                     (f"; {update.latest.version} is out" if newer else ""), DIM)
        self.helix_card.set_dot(newer)
        if self.panes.currentWidget() is self.helix_pane:
            self.update_legend()

    # The HelixSR pane: Get HelixSR, the version, NVIDIA's DLL, Import, the update check

    def check_now(self) -> None:
        """Y Check now (and at start): GitHub asked for the newest HelixSR off the window's thread."""
        if self.checking:
            return
        self.checking = True
        self.refresh_helix()
        version, ask = self.payload().version, self.check_job
        threading.Thread(target=lambda: self.release_found.emit(ask(version)), daemon=True).start()

    def _release_found(self, status: object) -> None:
        self.checking = False
        self.update = status if isinstance(status, UpdateStatus) else None
        if self.update is not None:
            self.log.info(f"Update check: {self.update.summary}.")
        self.refresh_helix()

    def get_helixsr(self) -> None:
        """A Get HelixSR: the release downloaded and built off the window's thread. A payload that has that version
        already asks for a second press."""
        if self.busy:
            self.helix_pane.status.setText("Get HelixSR is running: the X button cancels it.")
            return
        dlss = self.dlss_file()
        if dlss is not None and not dlss.is_file():
            self.message = (f"{private(dlss)} is not there any more: the RB button picks another, or the download "
                            "from NVIDIA.")
            self.refresh_helix()
            return
        fallback = self.fallback()
        update = self.update
        release = update.latest if update is not None and update.latest.asset_url and not fallback else None
        wanted = FALLBACK_VERSION if fallback else release.version if release is not None else ""
        status = self.payload()
        if status.ready and wanted and acquire.version_tuple(status.version) == acquire.version_tuple(wanted) \
                and not self.ask_again("build", self.helix_pane.status, ""):
            self.refresh_helix()
            return
        request = SetupRequest(self.work_dir, self.helix_data, release, dlss, fallback)
        self.job = self.setup_job(request, self.worker.said.emit, self.worker.staged.emit, self._progress)
        self.busy, self.message, self.stage, self.output = True, "", "", []
        self.got = self.total = 0
        self.got_name = ""
        self.progress_timer.start()
        self.log.info(f"Get HelixSR: {'the fallback ' + FALLBACK_VERSION if fallback else 'the latest release'}"
                      + (", with a local NVIDIA DLL." if dlss is not None else "."))
        self.worker.run(self.job.run)
        self.refresh_helix()

    def _progress(self, name: str, done: int, total: int) -> None:
        self.got_name, self.got, self.total = name, done, total     # read by refresh_helix() on the window's thread

    def _said(self, line: str) -> None:
        self.output.append(private(line))
        del self.output[:-OUTPUT_MAX]
        self.log.info(f"Get HelixSR: {line}")

    def _staged(self, text: str) -> None:
        self.stage, self.got_name, self.got, self.total = text, "", 0, 0
        self.refresh_helix()

    def cancel_build(self) -> None:
        """X while Get HelixSR runs: the download or the build stops."""
        if self.busy and self.job is not None:
            self.job.cancel()
            self.stage = "Canceling"
            self.refresh_helix()

    def _built(self, outcome: object) -> None:
        self.busy, self.job = False, None
        self.progress_timer.stop()
        if self.close_asked:
            self._confirm_over()
        if not isinstance(outcome, SetupOutcome):
            outcome = SetupOutcome(False, None, "", f"Get HelixSR failed: {outcome}", 0)
        if not outcome.ok:
            self.message = private(outcome.message if outcome.message == "Canceled." else
                                   f"Get HelixSR failed: {outcome.message}")
            if outcome.message == "Canceled.":
                self.log.info("Get HelixSR was canceled.")
            else:
                self.log.error(f"Get HelixSR: {outcome.message}")
            self.refresh_helix()
            return
        self.log.info(f"{outcome.message} ({outcome.seconds:.0f} s)")
        if not self.import_from(outcome.release_dir, f"{outcome.message} ({outcome.seconds:.0f} s)"):
            return
        older = [d for d in self.store.items if backend.needs_update(d, self.payload_dir)]
        if older:
            self.message += (f" {len(older)} game(s) still have an older HelixSR or their own DLL: the Deployments "
                             "card's RB button puts the new build in.")
            self.refresh_helix()
        self.check_now()

    def import_from(self, source: Path, said: str = "") -> bool:
        """The payload from *source* (a release folder or zip); the settings, the games and the panes follow."""
        try:
            result = backend.import_payload(source, self.payload_dir)
        except (HelixError, OSError) as error:
            self.message = private(f"The import failed: {error}")
            self.log.error(f"Import from {source}: {error}")
            self.refresh_helix()
            return False
        text = said or f"Imported {len(result.copied)} file(s)."
        if result.missing:
            text += (f" Still missing: {', '.join(result.missing)}. Build them with Get HelixSR, or with the "
                     "release's own setup, then import that folder.")
        self.message = text
        self.log.info(f"Imported {', '.join(result.copied)} from {source}.")
        self.load_ini()
        self.refresh()
        self.rescan_all()
        return True

    def switch_version(self) -> None:
        """LB: the latest release or the fallback, for the next Get HelixSR."""
        if self.busy:
            self.helix_pane.status.setText(BUSY)
            return
        fallback = not self.fallback()
        self.settings.setValue(FALLBACK_KEY, fallback)
        self.message = (f"Get HelixSR now builds HelixSR {FALLBACK_VERSION}, the version HelixSR's developer "
                        "recommends when the latest one does not work for you." if fallback else
                        "Get HelixSR now builds the latest HelixSR release.")
        self.refresh_helix()

    # NVIDIA's DLL (the BC250 app's local nvngx_dlss.dll and Find in Steam)

    def show_dlss(self) -> None:
        if self.busy:
            self.helix_pane.status.setText(BUSY)
            return
        self.dlss_pane.status.setText("")
        self.show_pane(self.dlss_pane)
        self.show_dlss_rows()
        self.focus_list(self.dlss_pane)

    def show_dlss_rows(self) -> None:
        chosen = self.dlss_file()
        mark = lambda on: "  ✓" if on else ""          # noqa: E731
        rows = [("download", "Download it from NVIDIA (used once, then deleted)" + mark(chosen is None))]
        files = list(self.dlss_found)
        if chosen is not None and chosen not in files:
            files.insert(0, chosen)
        rows += [(f"file:{f}", private(f) + mark(f == chosen)) for f in files]
        rows.append(("pick", "Pick a file…"))
        self.dlss_pane.summary.setText(f"Where HelixSR's builder takes NVIDIA's {acquire.DLSS_DLL} 310.7.0 from.")
        self.dlss_pane.list.set_items(rows)
        self.update_legend()

    def dlss_picked(self, key: str) -> None:
        if key == "download":
            self.settings.setValue(DLSS_KEY, "")
            self.leave_dlss("Get HelixSR downloads NVIDIA's DLL, uses it once and deletes it.")
        elif key.startswith("file:"):
            self.use_dlss(Path(key[5:]))
        elif key == "pick":
            self.show_browser("dlss", self.dlss_pane)

    def use_dlss(self, path: Path) -> None:
        if path.name.lower() != acquire.DLSS_DLL:
            self.browse_pane.status.setText(f"Pick {acquire.DLSS_DLL}: HelixSR builds its network from that file.")
            return
        self.settings.setValue(DLSS_KEY, str(path))
        self.log.info(f"NVIDIA's DLL for the build: {path}.")
        self.leave_dlss(f"Get HelixSR takes {private(path)}; HelixSR's builder checks it.")

    def leave_dlss(self, said: str = "") -> None:
        self.browser = None
        self.message = said
        self.show_pane(self.helix_pane)
        self.refresh_helix()
        self.helix_card.setFocus()

    def find_in_steam(self) -> None:
        """Y on NVIDIA's DLL: the Steam libraries looked through for the exact DLL HelixSR pins, off the window's
        thread."""
        if not self.libraries:
            self.dlss_pane.status.setText("No Steam library found on this handheld.")
            return
        sha = acquire.pinned_dlss_sha(acquire.latest_work_release(self.work_dir))
        libraries, find = list(self.libraries), self.find_dlss
        if self.find_worker.run(lambda: find(libraries, sha)):
            self.dlss_pane.status.setText(f"Looking through your Steam games for {acquire.DLSS_DLL}…")

    def _dlss_found(self, result: object) -> None:
        self.dlss_found = list(result) if isinstance(result, list) else []
        self.dlss_pane.status.setText(
            f"Found {len(self.dlss_found)} copy(ies) of the build HelixSR pins: the A button uses one."
            if self.dlss_found else
            f"No game here ships the {acquire.DLSS_DLL} HelixSR pins: Get HelixSR downloads it from NVIDIA.")
        if self.panes.currentWidget() is self.dlss_pane:
            self.show_dlss_rows()

    # The browser (core's browse): a game folder, a release to import, NVIDIA's DLL, a second upscaler

    def show_browser(self, kind: str, origin: Pane) -> None:
        start = browse.places(self.user_home, self.roots)
        built = acquire.latest_work_release(self.work_dir) if kind == "import" else None
        if built is not None:
            start.insert(0, built)
        self.browser = browse.Browser(start, BROWSE_SUFFIXES[kind], path=browse.remembered(self.settings, kind))
        self.browse_for, self.browse_from = kind, origin
        self.cards[self.browse_pane] = self.cards[origin]
        self.browse_pane.heading.setText(BROWSE_TITLES[kind])
        self.browse_pane.status.setText("")
        self.show_pane(self.browse_pane)
        self.show_browse()

    def show_browse(self) -> None:
        path = self.browser.path if self.browser is not None else None
        self.browse_pane.summary.setText(wrappable(path) if path is not None else BROWSE_SUMMARIES[self.browse_for])
        self.browse_pane.list.set_items(self.browser.rows() if self.browser is not None else [])
        self.focus_list(self.browse_pane)
        self.update_legend()

    def browse_picked(self, key: str) -> None:
        if self.browser is None:
            return
        picked = self.browser.open(key)
        if picked is None:
            self.show_browse()
            return
        browse.remember(self.settings, self.browse_for, picked.parent)
        if self.browse_for == "import":
            self.leave_browser()
            self.import_from(picked)
        elif self.browse_for == "dlss":
            self.use_dlss(picked)
        elif self.browse_for == "second":
            self.opti_second = picked
            self.leave_browser()
            self.opti_pane.status.setText(f"The second upscaler: {picked.name}.")

    def use_folder(self) -> None:
        """X in the browser: the folder it is in, as a game folder or a release to import."""
        if self.browser is None or self.browser.path is None or self.browse_for not in ("folder", "import"):
            return
        folder, kind = self.browser.path, self.browse_for
        browse.remember(self.settings, kind, folder)
        self.leave_browser()
        if kind == "import":
            self.import_from(folder)
        else:
            self.add_folder(folder)

    def leave_browser(self) -> None:
        origin = self.browse_from or self.helix_pane
        self.browser, self.browse_from = None, None
        self.show_pane(origin)
        if origin is self.helix_pane:
            self.refresh_helix()
            self.helix_card.setFocus()
        elif origin is self.opti_pane:
            self.show_opti_rows()
            self.focus_list(self.opti_pane)
        elif origin is self.dlss_pane:
            self.show_dlss_rows()
            self.focus_list(self.dlss_pane)
        else:
            self.focus_list(self.games_pane)

    # Games

    def added(self) -> list[Path]:
        """The game folders added by hand (LB), kept in the app's settings."""
        value = self.settings.value(FOLDERS_KEY, [])
        values = [value] if isinstance(value, str) else list(value or [])
        return [Path(v) for v in values if v]

    def refresh_games(self) -> None:
        """Steam's libraries and the added folders read again; every game looked through again, off the window's
        thread (the list keeps a game's last result until then)."""
        self.libraries = backend.steam_libraries(self.steam_dir) if self.steam_dir is not None else []
        self.app_ids = backend.steam_app_ids(self.libraries)
        folders = [g for g in backend.steam_games(self.libraries) if not backend.is_steam_tool(g)]
        folders += [f for f in self.added() if f.is_dir() and f not in folders]
        self.games = {folder: self.games.get(folder) for folder in folders}
        self.checking_games = set(folders)
        self.scanner.start([(f, self.app_ids.get(f, "")) for f in folders], self.payload_dir)
        self.show_games()

    def rescan(self, folders: list[Path]) -> None:
        folders = [f for f in folders if f in self.games]
        self.checking_games |= set(folders)
        self.scanner.start([(f, self.app_ids.get(f, "")) for f in folders], self.payload_dir)

    def rescan_all(self) -> None:
        self.rescan(list(self.games))

    def _scanned(self, scan: object) -> None:
        if isinstance(scan, GameScan) and scan.folder in self.games:
            self.games[scan.folder] = scan
            self.checking_games.discard(scan.folder)
            if not self.render_timer.isActive():
                self.render_timer.start()
            if scan.folder == self.focused_game():
                self.update_legend()                    # its A and Y follow what was found

    def game_of(self, location: Path) -> Path | None:
        """The listed game folder *location* is in, if any."""
        return next((g for g in self.games if location == g or g in location.parents), None)

    def show_games(self) -> None:
        def order(game: Path) -> tuple:
            scan = self.games[game]
            return (0 if scan is not None and scan.usable else 1 if scan is None else 2, game.name.lower())
        rows = []
        for game in sorted(self.games, key=order):
            scan = self.games[game]
            state = "looking…" if scan is None else scan.state()[1] if scan.usable else "no FSR 3.1 DLL"
            rows.append((str(game), f"{game.name}  ·  {state}"))
        usable = sum(1 for s in self.games.values() if s is not None and s.usable)
        waiting = sum(1 for s in self.games.values() if s is None)
        if not self.games:
            summary = ("Steam was never started on this handheld: the LB button adds a game folder." if self.steam_dir
                       is None else "No games found: the LB button adds a game folder.")
        elif waiting:
            summary = f"Looking through {len(self.games) - waiting} of {len(self.games)} games…"
        else:
            summary = f"{usable} of {len(self.games)} games ship AMD FSR 3.1: those can use HelixSR."
        self.games_pane.summary.setText(summary)
        self.games_card.set_text(summary if waiting or not self.games else
                                 f"{usable} of {len(self.games)} games can use HelixSR.")
        self.games_pane.list.set_items(rows)
        self.update_legend()

    def focused_game(self) -> Path | None:
        key = self.games_pane.list.focused()
        return Path(key) if key else None

    def game_focused(self, key: str) -> None:
        """The row with the focus: where its FSR 3.1 DLL is, and what the buttons do for it."""
        game = Path(key)
        scan = self.games.get(game)
        if self.confirm.startswith(("run:", "goback:")) and not self.confirm.endswith(key):
            self._confirm_over()
        if scan is None:
            text = f"Still looking through {game.name}…"
        elif not scan.usable:
            text = "No AMD FSR 3.1 DLL: HelixSR cannot replace one. The X button (OptiScaler) can still put it in."
        else:
            dlls = ", ".join(str(d.path.relative_to(game)) for d in scan.targets())
            text = f"{scan.state()[1]}: {dlls}"
        self.games_pane.status.setText(text)
        self.update_legend()

    def run_game(self, key: str) -> None:
        """A Run with HelixSR: HelixSR goes in where it is missing, older or replaced by the game's own DLL, then Steam
        starts the game (a folder added by hand: HelixSR goes in, the user starts the game). The first install into a
        game asks for a second press; nothing changes while the game runs."""
        game = Path(key)
        scan = self.games.get(game)
        status = self.games_pane.status
        if scan is None:
            status.setText(f"Still looking through {game.name}: a moment.")
            return
        if not scan.usable:
            status.setText(f"No AMD FSR 3.1 DLL in {game.name}: HelixSR cannot replace one. The X button "
                           "(OptiScaler) can still put it in.")
            return
        if self.busy:
            status.setText(BUSY)
            return
        if not self.payload().ready:
            status.setText(NOT_BUILT)
            return
        if backend.game_running(scan.app_id, self.running):
            status.setText(f"{game.name} is running. Close it first: HelixSR goes in before the game starts.")
            return
        targets = [d for d in scan.targets() if not d.matches_payload]
        fresh = [d for d in targets if not d.deployed]
        if fresh and not self.ask_again(f"run:{game}", status, (
                "Press the A button again to put HelixSR in place of {0}. The game's file is kept as .original.dll; "
                "Go back puts it back.").format(", ".join(str(d.path.relative_to(game)) for d in fresh))):
            return
        version = self.payload().version
        try:
            for dll in targets:
                backend.update_deployment(Deployment(str(dll.path), MODE_REPLACE, game.name), self.payload_dir)
                self.store.record(dll.path, MODE_REPLACE, game.name, version)
        except (HelixError, OSError) as error:
            status.setText(private(f"HelixSR could not be put into {game.name}: {error}"))
            self.log.error(f"Run with HelixSR, {game.name}: {error}")
            self.rescan([game])
            return
        if targets:
            self.log.info(f"HelixSR {version} put into {game.name}: {', '.join(str(d.path) for d in targets)}.")
        self.rescan([game])
        self.show_deployments()
        if not scan.app_id:
            status.setText(f"HelixSR is in {game.name}. Start the game as you always do, and choose AMD FSR in it.")
            return
        try:
            self.open_url(backend.play_url(scan.app_id))
        except OSError as error:
            status.setText(f"Steam could not be asked to start {game.name}: {error.strerror or error}")
            self.log.error(f"Starting {game.name} in Steam failed: {error}")
            return
        status.setText(f"HelixSR put into {len(targets)} DLL(s); starting {game.name} through Steam. Choose AMD FSR "
                       "in the game." if targets else f"Starting {game.name} through Steam with HelixSR. Choose AMD "
                       "FSR in the game.")

    def go_back_game(self) -> None:
        """Y Go back on a game: HelixSR's files deleted and the game's own DLL given its name back, on a second
        press."""
        game = self.focused_game()
        scan = self.games.get(game) if game is not None else None
        status = self.games_pane.status
        if game is None or scan is None:
            return
        deployed = [d for d in scan.dlls if d.deployed]
        if not deployed:
            status.setText(f"HelixSR is not in {game.name}: there is nothing to put back.")
            return
        if self.busy:
            status.setText(BUSY)
            return
        if backend.game_running(scan.app_id, self.running):
            status.setText(f"{game.name} is running. Close it first, then go back.")
            return
        if not self.ask_again(f"goback:{game}", status, "Press the Y button again: HelixSR's files go, and the "
                                                        "game's own DLL gets its name back."):
            return
        removed = 0
        try:
            for dll in deployed:
                removed += len(backend.remove(dll.path, self.payload_dir))
                self.store.forget(dll.path)
        except (HelixError, OSError) as error:
            status.setText(private(f"HelixSR could not be taken out of {game.name}: {error}"))
            self.log.error(f"Go back, {game.name}: {error}")
        else:
            status.setText(f"HelixSR is gone from {game.name}: {removed} file(s) deleted, the game's own DLL is back.")
            self.log.info(f"Go back: HelixSR taken out of {game.name}.")
        self.rescan([game])
        self.show_deployments()

    def add_folder(self, folder: Path) -> None:
        folders = self.added()
        if folder in self.games or folder in folders:
            self.games_pane.status.setText(f"{folder.name} is on the list already.")
        else:
            self.settings.setValue(FOLDERS_KEY, [str(f) for f in [*folders, folder]])
            self.log.info(f"Game folder added: {folder}.")
            self.games[folder] = None
            self.rescan([folder])
            self.show_games()
            self.games_pane.status.setText(f"{folder.name} is added: the app looks through it now.")
        pill = self.games_pane.list.pills.get(str(folder))
        (pill or self.games_pane.list.first() or self.games_card).setFocus()

    def take_off_list(self) -> None:
        """RB on an added folder: off the list, the game itself stays."""
        game = self.focused_game()
        if game is None or game not in self.added():
            return
        self.settings.setValue(FOLDERS_KEY, [str(f) for f in self.added() if f != game])
        self.games.pop(game, None)
        self.show_games()
        self.games_pane.status.setText(f"{game.name} is off the list; the game and HelixSR in it stay as they are.")
        self.focus_list(self.games_pane)

    # OptiScaler (the BC250 app's stand-alone folder mode on its Deploy page)

    def opti_folder(self) -> Path | None:
        return self.opti_game / backend.HELIXSR_FOLDER if self.opti_game is not None else None

    def show_opti(self) -> None:
        """X on a game: the OptiScaler page for it."""
        game = self.focused_game()
        if game is None:
            return
        self.opti_game = game
        self.opti_exe = backend.find_exe_folder(game)
        folder = self.opti_folder()
        record = backend.optiscaler_record(folder)
        self.opti_install = (self.payload().optiscaler or record is not None) and self.opti_exe is not None
        second = folder / backend.SECOND_UPSCALER_DLL
        self.opti_second = second if second.is_file() else None
        self.opti_ini = True
        self.opti_pane.heading.setText(f"OptiScaler: {game.name}")
        self.opti_pane.status.setText("")
        self.show_pane(self.opti_pane)
        self.show_opti_rows()
        self.focus_list(self.opti_pane)

    def show_opti_rows(self) -> None:
        folder = self.opti_folder()
        if folder is None:
            return
        exe = private(self.opti_exe) if self.opti_exe is not None else "no game .exe found"
        state = ("HelixSR is in it: " + backend.deployment_state(Deployment(str(folder), MODE_FOLDER, ""),
                                                                 self.payload_dir)[1]
                 if (folder / backend.HELIXSR_DLL).is_file() else "not made yet")
        self.opti_pane.summary.setText(f"HelixSR's folder: {wrappable(folder)} ({state}). The game's .exe: {exe}.")
        yes = lambda on: "yes" if on else "no"          # noqa: E731
        self.opti_pane.list.set_items([
            ("optiscaler", f"OptiScaler beside the game's .exe: {yes(self.opti_install)}"),
            ("second", f"Second upscaler: {self.opti_second.name if self.opti_second else 'none'}"),
            ("ini", f"Write helixsr.ini: {yes(self.opti_ini)}"),
        ])
        if not self.opti_install and not self.opti_pane.status.text():
            self.opti_pane.status.setText("Install OptiScaler yourself, then paste the lines the LB button copies "
                                          "into its OptiScaler.ini.")
        self.update_legend()

    def opti_picked(self, key: str) -> None:
        status = self.opti_pane.status
        if key == "optiscaler":
            if self.opti_install:
                self.opti_install = False
                status.setText("")
            elif not self.payload().optiscaler:
                status.setText(f"The payload has no OptiScaler: get HelixSR {FALLBACK_VERSION} once (the LB button on "
                               "the HelixSR card), and the payload keeps it.")
            elif self.opti_exe is None:
                status.setText(f"No game .exe found in {self.opti_game.name}.")
            else:
                self.opti_install = True
                status.setText("")
        elif key == "second":
            if self.opti_second is not None:
                self.opti_second = None
                status.setText("No second upscaler.")
            else:
                self.show_browser("second", self.opti_pane)
                return
        elif key == "ini":
            self.opti_ini = not self.opti_ini
            status.setText("")
        self.show_opti_rows()

    def opti_deploy(self) -> None:
        """X Put HelixSR in: the stand-alone folder, and OptiScaler beside the game's .exe when chosen (that one on a
        second press, as the BC250 app asked)."""
        folder, game, status = self.opti_folder(), self.opti_game, self.opti_pane.status
        if folder is None or game is None:
            return
        if self.busy:
            status.setText(BUSY)
            return
        if not self.payload().ready:
            status.setText(NOT_BUILT)
            return
        exe_dir = self.opti_exe if self.opti_install else None
        if exe_dir is not None and backend.optiscaler_record(folder) is None and not self.ask_again(
                "opti", status, (f"Press the X button again to put OptiScaler into {private(exe_dir)}, beside the "
                                 "game's .exe, pointed at HelixSR. A file of the game it replaces is kept in "
                                 f"{backend.HELIXSR_FOLDER}\\{backend.OPTISCALER_BACKUP}; Go back puts it back.")):
            return
        ini_text = backend.render_ini(self.ini, self.template) if self.opti_ini else None
        try:
            written = backend.deploy_folder(folder, self.payload_dir, ini_text, self.opti_second)
            if exe_dir is not None:
                written += backend.install_optiscaler(exe_dir, folder, self.payload_dir)
        except (HelixError, OSError) as error:
            status.setText(private(f"HelixSR could not be put in: {error}"))
            self.log.error(f"OptiScaler folder for {game.name}: {error}")
            return
        self.store.record(folder, MODE_FOLDER, game.name, self.payload().version)
        self.log.info(f"HelixSR's folder for OptiScaler written for {game.name}: {len(written)} file(s).")
        record = backend.optiscaler_record(folder)
        if exe_dir is not None and record:
            text = (f"HelixSR is in its folder, and OptiScaler, as {record['optiscaler']}, beside the game's .exe. "
                    "Start the game and select DLSS; OptiScaler's menu (Insert) shows FSR HelixSR.")
        else:
            text = "HelixSR is in its folder. Point OptiScaler at it: the LB button copies the OptiScaler.ini lines."
        if self.opti_second is not None:
            text += (f" The second upscaler is in the folder as {backend.SECOND_UPSCALER_DLL}; OptiScaler's FFX "
                     "Upscaler menu lists its upscalers after HelixSR.")
        status.setText(text)
        self.show_opti_rows()
        self.show_deployments()

    def opti_remove(self) -> None:
        folder, status = self.opti_folder(), self.opti_pane.status
        if folder is None or not (folder / backend.HELIXSR_DLL).is_file():
            return
        if not self.ask_again("optiremove", status, "Press the Y button again: HelixSR's folder goes, and OptiScaler "
                                                    "with it; what OptiScaler replaced comes back."):
            return
        self.remove_location(folder, MODE_FOLDER, status)
        self.show_opti_rows()

    def copy_lines(self) -> None:
        folder = self.opti_folder()
        if folder is None:
            return
        QGuiApplication.clipboard().setText(backend.optiscaler_snippet(folder))
        self.opti_pane.status.setText("The OptiScaler.ini lines are copied: paste them into the game's OptiScaler.ini.")

    def leave_opti(self) -> None:
        game, self.opti_game = self.opti_game, None
        self.show_pane(self.games_pane)
        if game is not None:
            self.rescan([game])
        pill = self.games_pane.list.pills.get(str(game)) if game is not None else None
        (pill or self.games_pane.list.first() or self.games_card).setFocus()

    # Deployments (the BC250 app's Overview)

    def show_deployments(self) -> None:
        states = {d.path: backend.deployment_state(d, self.payload_dir) for d in self.store.items}
        rows = [(d.path, "  ·  ".join((d.game, "OptiScaler folder" if d.mode == MODE_FOLDER else d.location.name,
                                        states[d.path][1]))) for d in self.store.items]
        in_place = sum(1 for kind, _text in states.values() if kind == "ok")
        summary = (f"{in_place} of {len(rows)} in place." if rows else
                   "Nothing deployed yet: the Games card puts HelixSR in.")
        self.deploy_pane.summary.setText(summary)
        self.deploy_card.set_text(summary if rows else "Nothing yet.")
        self.deploy_pane.list.set_items(rows)
        if self.panes.currentWidget() is self.deploy_pane:
            self.update_legend()

    def focused_deployment(self) -> Deployment | None:
        key = self.deploy_pane.list.focused()
        return self.store.find(Path(key)) if key else None

    def deployment_focused(self, key: str) -> None:
        dep = self.store.find(Path(key))
        if dep is None:
            return
        if self.confirm.startswith(("remove:", "forget:")) and not self.confirm.endswith(key):
            self._confirm_over()
        self.deploy_pane.status.setText(f"{wrappable(dep.location)}: HelixSR {dep.helixsr_version or '?'}, "
                                        f"{dep.deployed_at.replace('T', ' ')}.")
        self.update_legend()

    def remove_deployment(self) -> None:
        dep = self.focused_deployment()
        if dep is None:
            return
        what = ("Press the Y button again: HelixSR's files there go, and the game's own DLL gets its name back."
                if dep.mode == MODE_REPLACE else
                "Press the Y button again: HelixSR's folder goes, and OptiScaler with it.")
        if not self.ask_again(f"remove:{dep.path}", self.deploy_pane.status, what):
            return
        self.remove_location(dep.location, dep.mode, self.deploy_pane.status)
        self.focus_list(self.deploy_pane)

    def remove_location(self, location: Path, mode: str, status) -> None:
        """Go back where HelixSR is: the game's DLL back, or the stand-alone folder (and OptiScaler) gone."""
        if self.busy:
            status.setText(BUSY)
            return
        try:
            removed = (backend.remove(location, self.payload_dir) if mode == MODE_REPLACE
                       else backend.remove_folder(location, self.payload_dir))
        except (HelixError, OSError) as error:
            status.setText(private(f"Go back failed: {error}"))
            self.log.error(f"Go back, {location}: {error}")
            return
        self.store.forget(location)
        self.log.info(f"Go back: {len(removed)} file(s) deleted at {location}.")
        status.setText(f"HelixSR is gone: {len(removed)} file(s) deleted" +
                       (", the game's own DLL is back." if mode == MODE_REPLACE else "."))
        game = self.game_of(location)
        if game is not None:
            self.rescan([game])
        self.show_deployments()

    def forget(self) -> None:
        dep = self.focused_deployment()
        if dep is None or not self.ask_again(f"forget:{dep.path}", self.deploy_pane.status,
                                             "Press the X button again to drop the line; the game is not touched."):
            return
        self.store.forget(dep.location)
        self.deploy_pane.status.setText(f"{dep.game} is off the list; HelixSR there stays as it is.")
        self.show_deployments()
        self.focus_list(self.deploy_pane)

    def update_older(self) -> None:
        """RB Update older games: the payload's HelixSR into every deployment with an older build or with the game's
        own DLL back, their helixsr.ini kept; a running game is left alone."""
        status = self.deploy_pane.status
        deps = [d for d in self.store.items if backend.needs_update(d, self.payload_dir)]
        if not deps:
            status.setText("Every game has the payload's HelixSR.")
            return
        if self.busy:
            status.setText(BUSY)
            return
        if not self.payload().ready:
            status.setText(NOT_BUILT)
            return
        version = self.payload().version
        done, skipped = [], []
        for dep in deps:
            game = self.game_of(dep.location)
            if game is not None and backend.game_running(self.app_ids.get(game, ""), self.running):
                skipped.append(f"{dep.game}: running, close it first")
                continue
            try:
                backend.update_deployment(dep, self.payload_dir)
            except (HelixError, OSError) as error:
                skipped.append(f"{dep.game}: {error}")
                continue
            self.store.record(dep.location, dep.mode, dep.game, version)
            done.append(dep)
        self.log.info(f"Update older games: {len(done)} of {len(deps)} updated."
                      + (f" Not: {'; '.join(skipped)}." if skipped else ""))
        status.setText(private(f"Updated {len(done)} of {len(deps)}. Not updated: {'; '.join(skipped)}." if skipped
                               else f"HelixSR {version} put into {len(done)} game(s)."))
        self.rescan([g for g in (self.game_of(d.location) for d in done) if g is not None])
        self.show_deployments()

    # Settings: helixsr.ini (the BC250 app's helixsr.ini page)

    def load_ini(self) -> None:
        self.template = backend.ini_template(self.payload_dir)
        self.ini = backend.parse_ini(self.template)

    def refresh_settings(self) -> None:
        version = self.payload().version
        shown = ini_settings.shown_settings(version)
        self.settings_pane.show_only({s.key for s in shown})
        for setting in ini_settings.SETTINGS:
            pill = self.settings_pane.pills[setting.key]
            pill.set_text(f"{setting.label}: {setting.shown(getattr(self.ini, setting.key))}")
        check = self.settings.value(CHECK_KEY, True, type=bool)
        self.settings_pane.pills[CHECK_AT_START].set_text(f"Look for a new HelixSR at start: {'on' if check else 'off'}")

    def step_setting(self, key: str) -> None:
        """A on a setting's row: its next value that makes a valid file, saved as the payload's helixsr.ini now."""
        status = self.settings_pane.status
        if key == CHECK_AT_START:
            self.settings.setValue(CHECK_KEY, not self.settings.value(CHECK_KEY, True, type=bool))
            status.setText("")
            self.refresh_settings()
            return
        setting = next(s for s in ini_settings.SETTINGS if s.key == key)
        value = getattr(self.ini, key)
        for _ in setting.values:
            value = setting.next_value(value)
            trial = dataclasses.replace(self.ini, **{key: value})
            if not backend.validate_ini(trial):
                break
        else:
            status.setText(" ".join(backend.validate_ini(trial)))
            return
        if self.save_ini(trial):
            status.setText("")
            self.log.info(f"helixsr.ini: {setting.label} {setting.shown(value)}.")

    def save_ini(self, settings: HelixIni) -> bool:
        text = backend.render_ini(settings, self.template)
        try:
            self.payload_dir.mkdir(parents=True, exist_ok=True)
            (self.payload_dir / backend.INI).write_text(text, encoding="utf-8")
        except OSError as error:
            self.settings_pane.status.setText(f"helixsr.ini was not saved: {error.strerror or error}")
            self.log.error(f"Saving helixsr.ini failed: {error}")
            return False
        self.ini, self.template = settings, text
        self.refresh_settings()
        return True

    def defaults(self) -> None:
        """X Defaults: HelixSR's own value for every setting, on a second press."""
        if not self.ask_again("defaults", self.settings_pane.status,
                              "Press the X button again to set every setting to HelixSR's default."):
            return
        if self.save_ini(HelixIni()):
            self.settings_pane.status.setText("Every setting is HelixSR's default again.")
            self.log.info("helixsr.ini: HelixSR's defaults.")

    def show_apply(self) -> None:
        """Y Apply to a game: the games that have HelixSR, A writes the settings into one."""
        rows = [(d.path, f"{d.game}  ·  {'OptiScaler folder' if d.mode == MODE_FOLDER else d.location.name}")
                for d in self.store.items]
        self.apply_pane.summary.setText("The A button writes the settings as the game's helixsr.ini." if rows else
                                        "No game has HelixSR yet: the Games card puts it in.")
        self.apply_pane.status.setText("")
        self.show_pane(self.apply_pane)
        self.apply_pane.list.set_items(rows)
        self.focus_list(self.apply_pane)

    def apply_to(self, key: str) -> None:
        dep = self.store.find(Path(key))
        if dep is None:
            return
        if not dep.folder.is_dir():
            self.apply_pane.status.setText(f"{private(dep.folder)} is not there any more.")
            return
        try:
            (dep.folder / backend.INI).write_text(backend.render_ini(self.ini, self.template), encoding="utf-8")
        except OSError as error:
            self.apply_pane.status.setText(f"helixsr.ini was not written: {error.strerror or error}")
            self.log.error(f"Writing helixsr.ini to {dep.folder} failed: {error}")
            return
        self.log.info(f"helixsr.ini written to {dep.game} ({dep.folder}).")
        self.apply_pane.status.setText(f"helixsr.ini written to {dep.game}: HelixSR reads it at the game's next start.")

    def leave_apply(self) -> None:
        self.show_pane(self.settings_pane)
        self.settings_pane.focus_first()

    # Log

    def refresh_log(self) -> None:
        rows = [("HelixSR", wrappable(self.payload_dir)), ("Downloads", wrappable(self.work_dir)),
                ("Python and compiler", wrappable(self.helix_data)), ("Games list", wrappable(self.store.path))]
        self.log_pane.fill(rows, [private(line) for line in self.log_lines()[-LOG_LINES:]])

    def log_lines(self) -> list[str]:
        if self.log_path is None:
            return []
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []

    def view_log(self) -> None:
        """The whole log (its newest lines) in the Log pane: the d-pad scrolls it, B goes back (owner, 29-10-2026:
        Notepad has no button to close it)."""
        self.show_pane(self.log_pane)
        self.log_pane.show_whole(private("\n".join(self.log_lines()[-LOG_MAX:])))
        self.update_legend()

    # The legend's buttons: what A (beside a card or a row), X, Y, LB, RB and LT do on the pane that shows (a tap on
    # the legend's entry does the same)

    def a_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.helix_pane:
            self.get_helixsr()
        elif pane is self.log_pane:
            self.view_log()
        elif pane is self.games_pane and self.focused_game() is not None:
            self.run_game(str(self.focused_game()))

    def x_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.helix_pane:
            self.cancel_build()
        elif pane is self.games_pane:
            self.show_opti()
        elif pane is self.deploy_pane:
            self.forget()
        elif pane is self.settings_pane:
            self.defaults()
        elif pane is self.opti_pane:
            self.opti_deploy()
        elif pane is self.browse_pane:
            self.use_folder()

    def y_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.helix_pane:
            if self.busy:
                self.helix_pane.status.setText(BUSY)
            else:
                self.check_now()
        elif pane is self.games_pane:
            self.go_back_game()
        elif pane is self.deploy_pane:
            self.remove_deployment()
        elif pane is self.settings_pane:
            self.show_apply()
        elif pane is self.opti_pane:
            self.opti_remove()
        elif pane is self.dlss_pane:
            self.find_in_steam()

    def lb_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.helix_pane:
            self.switch_version()
        elif pane is self.games_pane:
            self.show_browser("folder", self.games_pane)
        elif pane is self.settings_pane:
            self.settings_pane.tabs.step(-1)
        elif pane is self.opti_pane:
            self.copy_lines()

    def rb_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.helix_pane:
            self.show_dlss()
        elif pane is self.games_pane:
            self.take_off_list()
        elif pane is self.deploy_pane:
            self.update_older()
        elif pane is self.settings_pane:
            self.settings_pane.tabs.step(1)

    def lt_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.helix_pane:
            if self.busy:
                self.helix_pane.status.setText(BUSY)
            else:
                self.show_browser("import", self.helix_pane)
        elif pane is self.games_pane:
            self.refresh_games()
            self.games_pane.status.setText("The games are looked through again.")

    # B

    def on_back(self) -> None:
        """B goes back (the suite's rule, owner 29-10-2026): the whole log to its summary, the browser a level up (at
        the places, to where it was opened), a page to its pane, a pane to its card; on a card it does nothing (View
        exits)."""
        pane = self.panes.currentWidget()
        if pane is self.log_pane and self.log_pane.viewing:
            self.log_pane.show_summary()
            self.log_card.setFocus()
            self.update_legend()
        elif pane is self.browse_pane:
            if self.browser is not None and self.browser.up():
                self.show_browse()
            else:
                self.leave_browser()
        elif pane is self.opti_pane:
            self.leave_opti()
        elif pane is self.dlss_pane:
            self.leave_dlss()
        elif pane is self.apply_pane:
            self.leave_apply()
        else:
            self.go_back()

    # View

    def exit_app(self) -> None:
        if self.busy and not self.close_asked:          # exiting drops the job (the portal's rule: ask first)
            self.close_asked = True
            self.confirm_timer.start()
            self.refresh_helix()
            self.update_legend()
            return
        self.close()

    def closeEvent(self, event) -> None:
        if self.job is not None:
            self.job.cancel()
        self.scanner.cancel()
        self.status_timer.stop()
        self.progress_timer.stop()
        self.confirm_timer.stop()
        self.render_timer.stop()
        super().closeEvent(event)
