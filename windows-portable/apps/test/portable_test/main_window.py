# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the tests as cards on the left (Device, Hardware, Connected, Network, Controller), what the focused one
shows on the right, the controller's buttons at the bottom (X Save report; on the Controller card Y Stick lights; a
tap on an entry does the same). Direction D's test screen (the owner's, 26-10-2026)."""

from __future__ import annotations

import datetime
import threading
import time
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, power
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private, suite_data
from bc250_core.portable import (BODY, DIM, Card, Legend, Pane, PortableHeader, PortableWindow,
                                 px, status_clock, text_label)

from . import APP_ID, APP_NAME, SUITE, __version__, back_buttons, controller, device, lights, network, temps
from .controller import LIGHTS_TEXT, LIGHTS_TITLE, ControllerPane, LightsPanel

STATUS_MS = 5_000               # the header's battery, temperatures and time: the temperatures live
CARDS_WIDTH = 663               # the cards' column, as wide as its 5 of 9 parts of the page were: a long value wraps
CONTROLLER_LEGEND = [("A", "Start the test"), ("Y", "Stick lights")]   # then core's Info, Back and Exit app


class _Reader(QObject):
    """Reads the device (or measures the network) off the window's thread; done, failed and what it is doing
    (progress) arrive on the window's."""

    done = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, read: Callable[[], object]):
        super().__init__()
        self.read = read
        self.busy = False

    def start(self) -> bool:
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self) -> None:
        try:
            found = self.read()
        except Exception as error:  # noqa: BLE001  (shown in the pane, not raised)
            self.busy = False
            self.failed.emit(str(error) or type(error).__name__)
            return
        self.busy = False
        self.done.emit(found)


class InfoPane(Pane):
    """What Windows reports, as labels and values: the Device, Hardware and Connected cards' pane (one read fills all
    three) and the Network card's. Its action, A Read or A Test (then Read again, Test again), is in the window's
    legend, never a pill (owner, 29-10-2026: one way everywhere); nothing runs before A asks for it (owner,
    28-10-2026). *action* is the legend's text for A."""

    def __init__(self, title: str, about: str, empty: str = "", action: str = "Read",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.empty = empty                              # said when a read found nothing for this card
        self.column.addWidget(text_label(title, 24, QFont.Weight.ExtraBold))
        self.column.addWidget(text_label(about, BODY + 1, color=DIM, wrap=True))
        self.column.addSpacing(px(12))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(4))
        self.column.addLayout(self.grid)
        self.column.addStretch()
        self.status = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.status)
        self.action = action

    def show_rows(self, rows: list[tuple[str, str]]) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()                           # gone now, not when Qt deletes it later
                widget.deleteLater()
        for r, (label, value) in enumerate(rows):
            self.grid.addWidget(text_label(label, BODY + 1, color=DIM), r, 0, Qt.AlignmentFlag.AlignTop)
            shown = text_label(value, BODY + 1, QFont.Weight.DemiBold, wrap=True)    # a long value wraps
            shown.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(shown, r, 1)
        self.grid.setColumnStretch(1, 1)
        self.status.setText("" if rows else self.empty)


class MainWindow(PortableWindow):
    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 read: Callable[[], device.Device] = device.read,
                 measure: Callable[..., network.Network] = network.measure,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery,
                 reports: Path | None = None, clock: Callable[[], float] = time.monotonic,
                 temperatures: Callable[[], tuple[int | None, int | None]] | None = None,
                 watts: Callable[[], int | None] | None = None, hertz: Callable[[], int | None] | None = None,
                 back_reader: back_buttons.Reader | None = None, lamps: lights.Lights | None = None):
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.sensors: temps.Temperatures | None = None
        if temperatures is None:                    # ADL opened once, read every STATUS_MS
            self.sensors = temps.Temperatures()
            temperatures = self.sensors.read
            watts = watts or self.sensors.watts
        self.temperatures = temperatures
        self.watts = watts or (lambda: None)
        self.hertz = hertz or self.screen_hertz
        self.back_reader = back_reader if back_reader is not None else back_buttons.Reader()
        self.lights = lamps if lamps is not None else lights.Lights()
        self.reports = reports or suite_data(SUITE) / APP_ID / "reports"
        self.device: device.Device | None = None
        self.network: network.Network | None = None
        self.testing = False

        page = QVBoxLayout(self)
        page.setContentsMargins(*self.margins())
        self.header = PortableHeader(APP_NAME, __version__)          # no icon: the screen is too small (owner)
        page.addWidget(self.header)
        page.addSpacing(px(14))
        body = QHBoxLayout()
        column = QWidget()
        column.setFixedWidth(px(CARDS_WIDTH))
        cards = QVBoxLayout(column)
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(px(12))
        self.device_card = Card("Device", "Processor, graphics, memory, storage, screen and battery.")
        self.hardware_card = Card("Hardware", "Panel, touch, Wi-Fi, Bluetooth, audio, fingerprint, sensors and USB.")
        self.connected_card = Card("Connected", "A dock or hub, screens, network and drives plugged in.")
        self.network_card = Card("Network", "The Wi-Fi link, its power setting and a timed download.")
        self.controller_card = Card("Controller", "Every button, stick and trigger, shown as you press them.")
        self.info_cards = (self.device_card, self.hardware_card, self.connected_card)
        for card in (*self.info_cards, self.network_card, self.controller_card):
            card.setFixedHeight(px(100))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()
        self.device_pane = InfoPane("Device", "What Windows reports about this handheld. It changes nothing.")
        self.hardware_pane = InfoPane("Hardware", "What is built in, as Windows reports it.")
        self.connected_pane = InfoPane("Connected", "What is plugged in: a dock or a hub, screens, network adapters "
                                       "and drives. Windows does not tell a dock from a hub: the hub's maker and "
                                       "what is behind it show.", empty="Nothing is plugged in.")
        self.info_panes = (self.device_pane, self.hardware_pane, self.connected_pane)
        self.network_pane = InfoPane("Network", "The Wi-Fi link, what else is downloading, and a timed download "
                                     f"from GitHub ({network.DOWNLOAD_SECONDS} seconds at most, nothing is kept). "
                                     "Compare a slow moment with a fast one.", action="Test")
        self.report_panes = (*self.info_panes, self.network_pane)      # what X saves
        self.controller_pane = ControllerPane(clock=clock)
        for pane in (*self.report_panes, self.controller_pane):
            self.panes.addWidget(pane)
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend()
        page.addWidget(self.legend)

        self.reader = _Reader(read)
        self.reader.done.connect(self.device_read)
        self.reader.failed.connect(self.device_failed)
        for card, pane in zip(self.info_cards, self.info_panes):
            card.focused.connect(lambda pane=pane: self.show_pane(pane))
            card.activated.connect(self.read_device)
        self.tester = _Reader(lambda: measure(network.power_text(self.battery()), say=self.tester.progress.emit))
        self.tester.done.connect(self.network_measured)
        self.tester.failed.connect(self.network_failed)
        self.tester.progress.connect(self.network_pane.status.setText)
        self.network_card.focused.connect(lambda: self.show_pane(self.network_pane))
        self.network_card.activated.connect(self.measure_network)
        self.controller_card.focused.connect(lambda: self.show_pane(self.controller_pane))
        self.controller_card.activated.connect(self.start_test)
        self.controller_pane.finished.connect(self.test_finished)
        self.gamepad.raw.connect(self.controller_pane.feed)
        self.bind("accept", self.a_action)
        self.bind("x", self.save_report)
        self.bind("y", self.y_action)
        self.back.connect(self.on_back)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(self.update_status)
        self.show_pane(self.device_pane)

    def start(self) -> None:
        """After the window is shown: the controller and the status line; the device is read on A."""
        self.start_gamepad()
        self.controller_pane.set_pads(self.gamepad.names())
        self.controller_pane.set_back_buttons(self.back_reader.start())
        self.back_reader.changed.connect(lambda held: self.controller_pane.feed("button", controller.BACK, held))
        self.update_status()
        self.status_timer.start()
        self.device_card.setFocus()

    def update_status(self) -> None:
        # The date and the time, and under them the temperatures, the power draw, the screen's refresh rate and the
        # battery (owner, 28-10-2026 and 29-10-2026)
        self.header.set_status(status_clock(), temps.status(*self.temperatures(), self.watts(), self.hertz(),
                                                            power.text(self.battery())))

    def screen_hertz(self) -> int | None:
        """The refresh rate of the screen the window is on, as Qt reads it: it changes when docked to a TV."""
        screen = self.screen()
        return round(screen.refreshRate()) if screen is not None and screen.refreshRate() > 0 else None

    def show_pane(self, pane: Pane) -> None:
        if self.testing:
            return
        self.panes.setCurrentWidget(pane)
        self.update_legend()

    def update_legend(self) -> None:
        """The pane's buttons, then core's Menu Info, B Back (while the focus is in a pane) and View Exit app (the
        suite's rule, owner 29-10-2026); during the button test only B held, which ends it."""
        if self.testing or not hasattr(self, "legend"):
            return
        pane = self.panes.currentWidget()
        items = [("A", pane.action), ("X", "Save report")] if pane in self.report_panes else CONTROLLER_LEGEND
        self.legend.set_items([*items, *self.common_items()])

    def a_action(self) -> None:
        """A beside a card (a tap on the legend's A, A in a pane): the pane's action, as A on its card."""
        pane = self.panes.currentWidget()
        if pane in self.info_panes:
            self.read_device()
        elif pane is self.network_pane:
            self.measure_network()
        elif pane is self.controller_pane:
            self.start_test()

    def act(self, action: str) -> None:
        """During the button test every button is the test's (on_action drops them); a tap on the legend's "B Hold
        to finish" ends it, for a finger."""
        if self.testing:
            if action == "back":
                self.controller_pane.finish()
            return
        super().act(action)

    def y_action(self) -> None:
        """Y on the Controller card: the stick lights' test (owner, 29-10-2026: the icon for it was hard to reach)."""
        if self.panes.currentWidget() is self.controller_pane:
            self.show_lights()

    # The Device, Hardware and Connected cards: one read fills all three

    def read_device(self) -> None:
        """A on Read: a read starts, or, while one runs, the pane says so (owner, 29-10-2026: a pill is never grayed
        out)."""
        started = self.reader.start()
        for pane in self.info_panes:
            pane.status.setText("Reading what Windows reports ..." if started else
                                "Reading ... Windows is still answering the read before.")

    def say(self, text: str, panes: tuple[InfoPane, ...] | None = None) -> None:
        """A line on the status of every pane X saves (the report saved), or of *panes* (a read that failed)."""
        for pane in panes or self.report_panes:
            pane.status.setText(text)

    def screen_row(self) -> tuple[str, str]:
        """The screen the window is on, as Qt sees it: its pixels, Windows' scaling and the refresh rate."""
        screen = self.screen()
        if screen is None:
            return ("Screen", "")
        ratio = screen.devicePixelRatio()
        size = screen.size()
        name = f" ({screen.name()})" if screen.name() else ""
        return ("Screen", f"{round(size.width() * ratio)} x {round(size.height() * ratio)}, "
                          f"{round(ratio * 100)}% scaling, {round(screen.refreshRate())} Hz{name}")

    def rows(self) -> list[tuple[str, str]]:
        rows = self.device.rows() if self.device is not None else []
        at = next((i for i, (label, _) in enumerate(rows) if label == "Memory"), len(rows))
        rows.insert(at, self.screen_row())
        return [(label, value) for label, value in rows if value]

    def sections(self) -> list[tuple[str, list[tuple[str, str]]]]:
        """The title and rows of each card read or measured, as the cards show them and the report lists them."""
        sections = []
        if self.device is not None:
            sections += [("Device", self.rows()), ("Hardware", self.device.hardware_rows()),
                         ("Connected", self.device.connected_rows())]
        if self.network is not None:
            sections.append(("Network", self.network.rows()))
        return sections

    def device_read(self, found: device.Device) -> None:
        self.device = found
        for pane, (_, rows) in zip(self.info_panes, self.sections()):     # the Network section, when measured, is last
            pane.show_rows(rows)
            pane.action = "Read again"
        self.update_legend()
        self.log.info(f"Read the device: {found.name}.")

    def device_failed(self, error: str) -> None:
        self.say(f"Windows did not answer: {error}", self.info_panes)
        self.log.error(f"Reading the device failed: {error}")

    def save_report(self) -> Path | None:
        """The report of what was read and measured as a text file in the suite's folder; the pane says where."""
        if (self.device is None and self.network is None) or self.testing:
            return None
        stamp = datetime.datetime.now()
        path = self.reports / f"device-{stamp:%Y-%m-%d-%H%M%S}.txt"
        text = f"{APP_NAME} {__version__}, {stamp:%d-%m-%Y %H:%M:%S}\n" + "".join(
            f"\n{title}\n" + "".join(f"{label}: {value}\n" for label, value in rows)
            for title, rows in self.sections() if rows)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError as error:
            self.say(f"The report was not saved: {error.strerror or error}")
            self.log.error(f"Saving the report failed: {error}")
            return None
        self.say(f"Saved: {private(path)}")     # the user's folder by its variable (owner, 29-10-2026)
        self.log.info(f"Saved the report: {path}")
        return path

    # The Network card

    def measure_network(self) -> None:
        started = self.tester.start()
        self.network_pane.status.setText("Measuring the network ..." if started else
                                         "Measuring ... the test before is still running.")

    def network_measured(self, found: network.Network) -> None:
        self.network = found
        self.network_pane.show_rows(found.rows())
        self.network_pane.action = "Test again"
        self.update_legend()
        if found.error:
            self.network_pane.status.setText(f"The download failed: {found.error}")
        self.log.info("Measured the network: " + "; ".join(f"{label} {value}" for label, value in found.rows()))

    def network_failed(self, error: str) -> None:
        self.network_pane.status.setText(f"The network was not measured: {error}")
        self.log.error(f"Measuring the network failed: {error}")

    # The Controller card

    def start_test(self) -> None:
        self.show_pane(self.controller_pane)
        self.controller_pane.set_pads(self.gamepad.names())
        self.testing = True
        self.controller_pane.start()
        self.legend.set_items([("B", "Hold to finish")])
        self.log.info("Controller test started.")

    def test_finished(self) -> None:
        self.testing = False
        seen = self.controller_pane.seen()
        self.log.info(f"Controller test finished: {len(seen)} buttons answered ({', '.join(seen) or 'none'}).")
        self.show_pane(self.controller_pane)
        self.controller_card.setFocus()

    def show_lights(self) -> None:
        """The stick lights' test in a popup over the window (owner, 29-10-2026: short of space, a popup), on Y in
        the Controller pane's legend; Close gives the lights back and the focus to where it was."""
        if self.testing:
            return
        found = self.lights.open()
        self.log.info(f"Stick lights: {found.text() if found is not None else 'no LampArray'}")
        popup = self.show_popup(LIGHTS_TITLE, LIGHTS_TEXT, self.focusWidget() or self.controller_card,
                                LightsPanel(found, self.lights.show))
        popup.closed.connect(self.lights.close)

    def on_action(self, action: str) -> None:
        if self.testing:                    # every button is the test's; holding B ends it (ControllerPane)
            return
        super().on_action(action)

    def keyPressEvent(self, event) -> None:
        if self.testing and event.key() == Qt.Key.Key_Escape:
            self.controller_pane.finish()
            return
        super().keyPressEvent(event)

    def on_back(self) -> None:
        """B goes back: from a pane to its card; on a card it does nothing (View exits the app)."""
        if not self.testing:
            self.go_back()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        self.back_reader.stop()
        if self.sensors is not None:
            self.sensors.close()
        self.lights.close()
        super().closeEvent(event)
