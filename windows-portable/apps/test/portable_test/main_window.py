# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the tests as cards on the left (Device, Controller), what the focused one shows on the right, the
controller's buttons at the bottom. Direction D's test screen (the owner's, 26-10-2026)."""

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
from bc250_core.platform import suite_data
from bc250_core.portable import (BODY, DIM, Card, Legend, Pane, Pill, PortableHeader, PortableWindow, px,
                                 text_label)

from . import APP_ID, APP_NAME, SUITE, __version__, device
from .controller import ControllerPane

STATUS_MS = 30_000              # the header's battery and time
WAITING = "Press A to read what Windows reports."     # nothing runs before (owner, 28-10-2026)
CARDS_WIDTH = 663               # the cards' column, as wide as its 5 of 9 parts of the page were: a long value wraps


class _Reader(QObject):
    """Reads the device off the window's thread; done or failed arrive on the window's."""

    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, read: Callable[[], device.Device]):
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


class DevicePane(Pane):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.column.addWidget(text_label("Device", 24, QFont.Weight.ExtraBold))
        self.column.addWidget(text_label("What Windows reports about this handheld. It changes nothing.", BODY + 1,
                                         color=DIM, wrap=True))
        self.column.addSpacing(px(12))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(4))
        self.column.addLayout(self.grid)
        self.column.addStretch()
        self.status = text_label(WAITING, BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.status)
        self.read_pill = Pill("Read", "A", main=True)
        self.column.addWidget(self.read_pill)

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


class MainWindow(PortableWindow):
    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 read: Callable[[], device.Device] = device.read,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery,
                 reports: Path | None = None, clock: Callable[[], float] = time.monotonic):
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.reports = reports or suite_data(SUITE) / APP_ID / "reports"
        self.device: device.Device | None = None
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
        self.controller_card = Card("Controller", "Every button, stick and trigger, shown as you press them.")
        for card in (self.device_card, self.controller_card):
            card.setFixedHeight(px(104))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()
        self.device_pane = DevicePane()
        self.controller_pane = ControllerPane(clock=clock)
        self.panes.addWidget(self.device_pane)
        self.panes.addWidget(self.controller_pane)
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend()
        page.addWidget(self.legend)

        self.reader = _Reader(read)
        self.reader.done.connect(self.device_read)
        self.reader.failed.connect(self.device_failed)
        self.device_card.focused.connect(lambda: self.show_pane(self.device_pane))
        self.controller_card.focused.connect(lambda: self.show_pane(self.controller_pane))
        self.device_card.activated.connect(self.read_device)
        self.device_pane.read_pill.activated.connect(self.read_device)
        self.controller_card.activated.connect(self.start_test)
        self.controller_pane.finished.connect(self.test_finished)
        self.gamepad.raw.connect(self.controller_pane.feed)
        self.bind("x", self.save_report)
        self.back.connect(self.on_back)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(self.update_status)
        self.show_pane(self.device_pane)

    def start(self) -> None:
        """After the window is shown: the controller and the status line; the device is read on A."""
        self.start_gamepad()
        self.controller_pane.set_pads(self.gamepad.names())
        self.update_status()
        self.status_timer.start()
        self.device_card.setFocus()

    def update_status(self) -> None:
        self.header.set_status([power.text(self.battery()), datetime.datetime.now().strftime("%H:%M")])

    def show_pane(self, pane: Pane) -> None:
        if self.testing:
            return
        self.panes.setCurrentWidget(pane)
        if pane is self.device_pane:
            self.legend.set_items([("X", "Save report"), ("B", "Close")])
        else:
            self.legend.set_items([("A", "Start the test"), ("B", "Close")])

    # The Device card

    def read_device(self) -> None:
        if self.reader.start():
            self.device_pane.status.setText("Reading what Windows reports ...")
            self.device_pane.read_pill.setEnabled(False)

    def screen_row(self) -> tuple[str, str]:
        """The screen the window is on, as Qt sees it: its pixels, Windows' scaling and the refresh rate."""
        screen = self.screen()
        if screen is None:
            return ("Screen", "")
        ratio = screen.devicePixelRatio()
        size = screen.size()
        name = f" ({screen.name()})" if screen.name() else ""
        return ("Screen", f"{round(size.width() * ratio)} x {round(size.height() * ratio)}, "
                          f"{round(ratio * 100)} % scaling, {round(screen.refreshRate())} Hz{name}")

    def rows(self) -> list[tuple[str, str]]:
        rows = self.device.rows() if self.device is not None else []
        at = next((i for i, (label, _) in enumerate(rows) if label == "Memory"), len(rows))
        rows.insert(at, self.screen_row())
        return [(label, value) for label, value in rows if value]

    def device_read(self, found: device.Device) -> None:
        self.device = found
        self.device_pane.show_rows(self.rows())
        self.device_pane.status.setText("")
        self.device_pane.read_pill.set_text("Read again")
        self.device_pane.read_pill.setEnabled(True)
        self.log.info(f"Read the device: {found.name}.")

    def device_failed(self, error: str) -> None:
        self.device_pane.status.setText(f"Windows did not answer: {error}")
        self.device_pane.read_pill.setEnabled(True)
        self.log.error(f"Reading the device failed: {error}")

    def save_report(self) -> Path | None:
        """The device report as a text file in the suite's folder; the pane says where."""
        if self.device is None or self.testing:
            return None
        stamp = datetime.datetime.now()
        path = self.reports / f"device-{stamp:%Y-%m-%d-%H%M%S}.txt"
        text = f"{APP_NAME} {__version__}, {stamp:%d-%m-%Y %H:%M:%S}\n\n" + \
            "\n".join(f"{label}: {value}" for label, value in self.rows()) + "\n"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError as error:
            self.device_pane.status.setText(f"The report was not saved: {error.strerror or error}")
            self.log.error(f"Saving the report failed: {error}")
            return None
        self.device_pane.status.setText(f"Saved: {path}")
        self.log.info(f"Saved the device report: {path}")
        return path

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
        if not self.testing:
            self.close()
