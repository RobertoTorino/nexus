# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's portable window, the header with the date, the time and the battery, three cards
(Windows, Tools, Apps) with their panes beside them, and the controller's buttons at the bottom. The checks run in
the background when the window opens and on Y (Check again): PowerShell's list of updates takes a few seconds."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, power
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private
from bc250_core.portable import DIM, DOT, Card, Legend, Pane, PortableHeader, PortableWindow, px, status_clock

from . import APP_ID, APP_NAME, __version__, checks
from .panes import APPS_INFO, ListPane, WindowsPane, tools_info

STATUS_MS = 30_000              # the header's battery and time
CARDS_WIDTH = 460               # the cards' column; the panes take the rest
CARD_HEIGHT = 100
CHECKING = "Checking…"
ATTENTION = {"Missing", "Unsupported build", "Update in the portal", "Restart to update", "Update late"}


class _Worker(QObject):
    done = pyqtSignal(object)

    def __init__(self, job: Callable[[], checks.Report]):
        super().__init__()
        self.job = job
        self.busy = False

    def run(self) -> bool:
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self) -> None:
        try:
            result: object = self.job()
        except Exception as error:  # noqa: BLE001  (shown on the panes, not raised)
            result = error
        self.busy = False
        self.done.emit(result)


class MainWindow(PortableWindow):
    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery,
                 check: Callable[[], checks.Report] = checks.check_all):
        """*check*: every check at once (checks.check_all; tests pass a fake)."""
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.report: checks.Report | None = None

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
        self.windows_card = Card("Windows", CHECKING)
        self.tools_card = Card("Tools", CHECKING)
        self.apps_card = Card("Apps", CHECKING)
        for card in (self.windows_card, self.tools_card, self.apps_card):
            card.setFixedHeight(px(CARD_HEIGHT))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()
        self.windows_pane = WindowsPane()
        self.tools_pane = ListPane("Tools", tools_info())
        self.apps_pane = ListPane("Apps", APPS_INFO)
        for pane in (self.windows_pane, self.tools_pane, self.apps_pane):
            self.panes.addWidget(pane)
        self.cards: dict[Pane, Card] = {self.windows_pane: self.windows_card, self.tools_pane: self.tools_card,
                                        self.apps_pane: self.apps_card}
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend(self.common_items())
        page.addWidget(self.legend)

        self.worker = _Worker(check)
        self.worker.done.connect(self._checked)
        self.windows_card.focused.connect(lambda: self.show_pane(self.windows_pane))
        self.tools_card.focused.connect(lambda: self.show_pane(self.tools_pane))
        self.apps_card.focused.connect(lambda: self.show_pane(self.apps_pane))
        self.tools_card.activated.connect(lambda: self.focus_list(self.tools_pane))
        self.apps_card.activated.connect(lambda: self.focus_list(self.apps_pane))
        self.tools_pane.list.current.connect(self.tool_picked)
        self.apps_pane.list.current.connect(self.app_picked)
        self.bind("y", self.check_again)
        self.back.connect(self.on_back)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(self.update_status)

    def start(self) -> None:
        """After the window is shown: the controller, the status line, the focus on the Windows card, the checks."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.windows_card.setFocus()
        self.show_pane(self.windows_pane)
        self.check_again()

    def update_status(self) -> None:
        self.header.set_status([*status_clock(), power.text(self.battery())])   # the battery last (owner, 30-10-2026)

    # The checks

    def check_again(self) -> None:
        if not self.worker.run():
            return
        for card in self.cards.values():
            card.set_text(CHECKING)
        self.windows_pane.status.setText(CHECKING)
        self.update_legend()

    def _checked(self, result: object) -> None:
        if isinstance(result, Exception):
            self.log.error(f"The checks failed: {result}")
            for card in self.cards.values():
                card.set_text("The check failed", DOT)
            self.windows_pane.status.setText(f"The check failed: {result}")
            self.update_legend()
            return
        self.report = result
        self.fill()
        missing = [s.tool.name for s in result.tools if s.status in ("Missing", "Unsupported build")]
        self.log.info(f"Checked: {result.windows.status()}; tools missing: {', '.join(missing) or 'none'}; "
                      f"apps to update: {sum(s.status == 'Update in the portal' for s in result.apps)}.")
        self.update_legend()

    def fill(self) -> None:
        report = self.report
        if report is None:
            return
        windows = report.windows
        status = windows.status()
        self.windows_card.set_text(status, DOT if status in ATTENTION else DIM)
        rows = [("Windows", windows.name), ("Version", windows.version or "unknown"),
                ("Build", windows.build or "unknown"),
                ("Waiting for a restart", "yes: an update takes effect then" if windows.restart else "no"),
                ("Newest update installed", windows.last_update or "not known")]
        self.windows_pane.fill(rows, {
            "Restart to update": "An update waits for a restart: restart the handheld to finish it.",
            "Update late": f"The newest update Windows installed is more than {checks.UPDATE_DAYS} days old: open "
                           "Settings, Windows Update.",
            "Unknown": "Windows did not say which updates it installed.",
        }.get(status, "Windows is up to date, as far as Windows Update says."))

        missing = [s for s in report.tools if s.status in ("Missing", "Unsupported build")]
        self.tools_card.set_text(f"{len(missing)} missing: {', '.join(s.tool.name for s in missing)}" if missing
                                 else "All there", DOT if missing else DIM)
        self.tools_pane.summary.setText("What the installed apps need on this handheld besides themselves." +
                                        (f" Not there: {', '.join(s.tool.name for s in missing)}." if missing else ""))
        self.tools_pane.list.set_items([(s.tool.key, f"{s.tool.name}: {s.status}") for s in report.tools])
        self.tools_pane.status.setText("")

        updates = [s for s in report.apps if s.status == "Update in the portal"]
        installed = [s for s in report.apps if s.status != "Not installed"]
        self.apps_card.set_text(f"{len(updates)} to update in the portal" if updates else
                                f"{len(installed)} installed, up to date", DOT if updates else DIM)
        self.apps_pane.summary.setText(
            "The installed apps against the portal's versions." if report.manifest is not None else
            "The portal is not installed: there is no list of the suite's apps to compare with.")
        self.apps_pane.list.set_items([(s.app.key, f"{s.app.name}: {self.app_text(s)}") for s in report.apps])
        self.apps_pane.status.setText("")

    @staticmethod
    def app_text(state: checks.AppState) -> str:
        if state.status == "Update in the portal":
            return f"{state.installed}, the portal has {state.app.version}"
        if state.status == "Up to date":
            return f"{state.installed}, up to date"
        return state.status.lower() if state.status == "Not installed" else state.status

    def tool_picked(self, key: str) -> None:
        state = next((s for s in (self.report.tools if self.report else []) if s.tool.key == key), None)
        if state is None:
            return
        users = ", ".join(state.needed_by)
        text = (f"{'Needed' if state.required else 'Used when it is there'} by {users}." if users else
                "No installed app uses it.")
        where = state.found.unsupported or state.found.where
        text += f" {'Found' if state.found.ok else 'Not found'}: {private(where)}."
        if state.status in ("Missing", "Not installed", "Unsupported build"):
            text += f" {state.tool.advice}"
        self.tools_pane.status.setText(text)

    def app_picked(self, key: str) -> None:
        state = next((s for s in (self.report.apps if self.report else []) if s.app.key == key), None)
        if state is None:
            return
        self.apps_pane.status.setText({
            "Update in the portal": f"{state.app.name} {state.installed} is installed; the portal brings "
                                    f"{state.app.version}: its Y button updates it.",
            "Up to date": f"{state.app.name} {state.installed} is installed, the version the portal brings.",
            "Version unknown": f"{state.app.name} is there, but the portal did not install it: install it from the "
                               "portal to have its version known.",
        }.get(state.status, f"{state.app.name} is not installed: the portal installs it."))

    # The panes and the buttons

    def show_pane(self, pane: Pane) -> None:
        self.panes.setCurrentWidget(pane)
        self.update_legend()

    def focus_list(self, pane: ListPane) -> None:
        (pane.list.first() or self.cards[pane]).setFocus()

    def update_legend(self) -> None:
        """Y Check again (not while a check runs), then core's Menu Info, B Back and View Exit (the suite's rule)."""
        if hasattr(self, "legend"):
            busy = hasattr(self, "worker") and self.worker.busy
            self.legend.set_items([*([] if busy else [("Y", "Check again")]), *self.common_items()])

    def on_back(self) -> None:
        """B goes back: from a row to its card; with nowhere to go it does nothing (View exits the app)."""
        self.go_back()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        super().closeEvent(event)
