# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's portable window, the header with the date, the time and the battery, a card for each drive
(Drive 1, Drive 2, as Disk Management numbers them, with its health or what kind it is) and the drive's pane beside
them, and the controller's buttons at the bottom: X measures the drive's speed, Y reads the drives again, RB saves a
screenshot. The reading (about a second) and the measuring (a few seconds) run off the window's thread.

The BC250 Bazzite Suite's SSD Check on the handheld (owner, 06-11-2026): no serial number (the suite never reads
one), no firmware update check (Windows has no fwupd), and a SATA drive's specs only (its SMART values need an
administrator on Windows)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QStandardPaths, QTimer, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from bc250_core import applog, power
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private, show_in_folder, suite_data
from bc250_core.portable import (AMBER, DIM, DOT, TEXT, Card, Legend, PortableHeader, PortableWindow, px,
                                 status_clock)

from . import APP_ID, APP_NAME, SUITE, __version__, drives, speedtest
from .panes import DrivePane

STATUS_MS = 30_000              # the header's battery and time
CARDS_WIDTH = 400               # the cards' column; the pane takes the rest
CARD_HEIGHT = 100
NONE = "—"
READING = "Reading the drives…"
WARNINGS = {"spare": "little spare space left", "temperature": "too hot or too cold", "degraded": "less reliable",
            "readonly": "read-only", "volatile_mem": "its backup power failed", "pmr_readonly": "read-only"}


class _Worker(QObject):
    """A job in a thread of its own; done carries its result or the exception it raised."""

    done = pyqtSignal(object)

    def __init__(self, job: Callable[[], object]):
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
        except Exception as error:  # noqa: BLE001  (shown on the pane, not raised)
            result = error
        self.busy = False
        self.done.emit(result)


def thousands(number: int) -> str:
    return f"{number:,}"


def rw(read: float | None, write: float | None) -> str:
    return f"{read:,.0f} / {write:,.0f}" if read is not None and write is not None else NONE


def new_path(folder: Path, suffix: str, now: float | None = None) -> Path:
    """A file in *folder* named after the app and the time ("SSD Check 2026-11-06 21-04-09.png"), not one there
    already: two in one second get (2), (3) and so on."""
    stem = f"{APP_NAME} {time.strftime('%Y-%m-%d %H-%M-%S', time.localtime(now))}"
    path, n = folder / f"{stem}{suffix}", 1
    while path.exists():
        n += 1
        path = folder / f"{stem} ({n}){suffix}"
    return path


def own_folder() -> Path:
    """The app's folder (%LOCALAPPDATA%\\windows-portable-suite\\windows-portable-ssd): the speed test's file goes
    there when it is on the drive measured."""
    return suite_data(SUITE) / APP_ID


def card_text(drive: drives.Drive) -> tuple[str, str]:
    """The card's line under "Drive N" and its color: the health, or what kind of drive it is."""
    size = drives.size_text(drive.size) if drive.size else ""
    if drive.warnings:
        return "The drive reports a problem", DOT
    if drive.health is not None:
        return " · ".join(p for p in (f"Health {drive.health} %", size) if p), AMBER if drive.health == 0 else DIM
    return " · ".join(p for p in (drive.kind, size) if p), DIM


class MainWindow(PortableWindow):
    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery,
                 read: Callable[[], list[drives.Drive]] = drives.read_drives,
                 measure: Callable[[Path], tuple[float, float]] = speedtest.measure,
                 own: Path | None = None, pictures: Path | None = None):
        """*read*: every drive (drives.read_drives); *measure*: the speed test in a folder (speedtest.measure);
        *own*: the app's folder, *pictures*: where screenshots go. Tests pass fakes."""
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.measure_job = measure
        self.own = own or own_folder()
        self.pictures = pictures or Path(QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.PicturesLocation)) / APP_NAME
        self.drives: list[drives.Drive] = []
        self.measured: dict[int, tuple[float, float]] = {}     # a drive's number: its measured (read, write)
        self.measuring: int | None = None                      # the drive the speed test runs on
        self.test_in: Path | None = None                        # and the folder it writes in
        self.cards: list[Card] = []
        self.current = 0                                        # the index of the drive the pane shows

        page = QVBoxLayout(self)
        page.setContentsMargins(*self.margins())
        self.header = PortableHeader(APP_NAME, __version__)
        page.addWidget(self.header)
        page.addSpacing(px(14))
        body = QHBoxLayout()
        self.card_area = QScrollArea()
        self.card_area.setFixedWidth(px(CARDS_WIDTH))
        self.card_area.setWidgetResizable(True)
        self.card_area.setFrameShape(QFrame.Shape.NoFrame)
        self.card_area.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget "
                                     "{ background: transparent; }")
        column = QWidget()
        self.card_column = QVBoxLayout(column)
        self.card_column.setContentsMargins(0, 0, px(4), 0)
        self.card_column.setSpacing(px(12))
        self.card_column.addStretch()
        self.card_area.setWidget(column)
        body.addWidget(self.card_area)
        body.addSpacing(px(16))
        self.pane = DrivePane()
        body.addWidget(self.pane, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend(self.common_items())
        page.addWidget(self.legend)

        self.reader = _Worker(read)
        self.reader.done.connect(self._read)
        self.tester = _Worker(self._measure)
        self.tester.done.connect(self._measured)
        self.bind("x", self.measure)
        self.bind("y", self.read_again)
        self.bind("next", self.screenshot)
        self.back.connect(self.on_back)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(self.update_status)

    def start(self) -> None:
        """After the window is shown: the controller, the status line, the drives read."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.read_again()

    def update_status(self) -> None:
        self.header.set_status([*status_clock(), power.text(self.battery())])   # the battery last (owner, 30-10-2026)

    # Reading the drives

    def read_again(self) -> None:
        if not self.reader.run():
            return
        if not self.drives:
            self.pane.title.setText(APP_NAME)
            self.pane.set_state(READING, DIM)
        self.pane.status.setText(READING)
        self.update_legend()

    def _read(self, result: object) -> None:
        self.pane.status.setText("")
        if isinstance(result, Exception):
            self.log.error(f"The drives could not be read: {result}")
            self.drives = []
            self.set_cards()
            self.pane.title.setText("The drives could not be read")
            self.pane.kind.setText("")
            self.pane.set_state(str(result), DOT)
            self.pane.set_values([])
            self.pane.note.setText("")
            self.update_legend()
            return
        number = self.drive().number if self.drive() else None
        self.drives = list(result)
        self.current = next((i for i, d in enumerate(self.drives) if d.number == number), 0)
        self.log.info("Drives: " + ("; ".join(f"{d.model} ({d.interface}, health "
                                                f"{'not read' if d.health is None else f'{d.health} %'})"
                                                for d in self.drives) or "none") + ".")
        self.set_cards()
        if not self.drives:
            self.pane.title.setText("No drive found")
            self.pane.kind.setText("")
            self.pane.set_state("Windows lists no drive.", DIM)
            self.pane.set_values([])
            self.pane.note.setText("")
        else:
            self.show_drive()
        self.update_legend()

    def set_cards(self) -> None:
        """A card for each drive, the focus kept on the drive it was on."""
        focused = next((i for i, card in enumerate(self.cards) if card.hasFocus()), None)
        for card in self.cards:
            card.hide()
            card.deleteLater()
        self.cards = []
        for n, drive in enumerate(self.drives):
            card = Card(f"Drive {n + 1}")
            card.setFixedHeight(px(CARD_HEIGHT))
            card.set_text(*card_text(drive))
            card.focused.connect(lambda n=n: self.drive_chosen(n))
            self.card_column.insertWidget(n, card)
            self.cards.append(card)
        in_pane = self.focusWidget() is not None and self.pane.isAncestorOf(self.focusWidget())
        if self.cards and (focused is not None or not in_pane):
            self.cards[min(self.current, len(self.cards) - 1)].setFocus()

    def drive(self) -> drives.Drive | None:
        return self.drives[self.current] if 0 <= self.current < len(self.drives) else None

    def drive_chosen(self, n: int) -> None:
        self.current = n
        if 0 <= n < len(self.cards):
            self.card_area.ensureWidgetVisible(self.cards[n], 0, px(8))
        self.show_drive()
        self.update_legend()

    def show_drive(self) -> None:
        drive = self.drive()
        if drive is None:
            return
        pane = self.pane
        pane.title.setText(drive.model or "Unknown drive")
        letters = ", ".join(f"{letter}:" for letter in drive.letters)
        size = drives.size_text(drive.size) if drive.size else ""
        pane.kind.setText(" · ".join(p for p in (drive.kind, size, letters) if p))
        pane.set_state(*self.state(drive))
        values = []
        if drive.health is not None:
            values.append(("Health", f"{drive.health} %", DOT if drive.warnings else AMBER if drive.health == 0
                           else TEXT))
        elif drive.smart:
            values.append(("Health", "Not reported", DIM))
        if drive.power_cycles is not None:
            values.append(("Power cycles", thousands(drive.power_cycles), TEXT))
        if drive.hours is not None:
            values.append(("Power-on hours", thousands(drive.hours), TEXT))
            # full days only (owner, 05-11-2026): a day the drive has not finished yet does not count
            values.append(("Power-on days", thousands(drive.hours // 24), TEXT))
        for name, amount in (("Host reads", drive.data_read), ("Host writes", drive.data_written)):
            if amount is not None:
                values.append((name, drives.size_text(amount), TEXT))
        held = drives.held_back(drive)
        values += [("Firmware", drive.firmware or NONE, TEXT), ("Interface", drive.interface or NONE, TEXT),
                   ("Speed", drive.speed or NONE, TEXT),
                   ("Board link", drive.board_link or "Not reported", AMBER if held else TEXT if drive.board_link
                    else DIM),
                   ("Rated R / W MB/s", rw(drive.rated_read, drive.rated_write) if drive.rated_read is not None
                    else "Unknown", TEXT if drive.rated_read is not None else DIM),
                   self.measured_value(drive)]
        pane.set_values(values)
        pane.note.setText(self.note(drive, held))

    @staticmethod
    def state(drive: drives.Drive) -> tuple[str, str]:
        if drive.warnings:
            said = ", ".join(WARNINGS.get(w, w) for w in drive.warnings)
            return f"The drive reports a problem: {said}. Back up what you want to keep.", DOT
        if not drive.smart:
            return {"SATA": "Health needs an administrator", "USB": "No SMART over USB",
                    "SD card": "No SMART on a memory card"}.get(drive.bus, "No SMART values"), DIM
        if drive.health == 0:
            return "Its rated endurance is used up: keep your backup current", AMBER
        return "No problems reported", TEXT

    @staticmethod
    def note(drive: drives.Drive, held: bool | None) -> str:
        """What the values mean for this drive: why some are missing, and whether the port holds it back."""
        lines = [drive.smart_note] if not drive.smart and drive.smart_note else []
        if drive.speed and drive.speed_tip:
            lines.append(f"{drive.speed_tip}.")
        if held is not None:
            can = (f"rated {drive.rated_read:,} MB/s read" if drive.rated_read else
                   f"its fastest link carries about {drive.drive_mbps:,} MB/s")
            lines.append(f"The port carries about {drive.board_mbps:,} MB/s and the drive is {can}: "
                         + ("the port holds it back." if held else "the port is fast enough for it."))
        if drive.rated_read is None and drive.drive_mbps and drive.bus in ("NVMe", "SATA"):
            lines.append(f"Not in SSD Check's list of rated speeds: its fastest link carries about "
                         f"{drive.drive_mbps:,} MB/s.")
        return " ".join(line for line in lines if line)

    # The speed test

    def test_folder(self, drive: drives.Drive | None) -> Path | None:
        return speedtest.folder_for(drive.letters, self.own) if drive else None

    def measured_value(self, drive: drives.Drive) -> tuple[str, str, str]:
        name = "Measured R / W MB/s"
        if self.measuring == drive.number:
            return name, "Testing…", AMBER
        if drive.number in self.measured:
            return name, rw(*self.measured[drive.number]), TEXT
        if self.test_folder(drive) is None:
            return name, "No drive letter", DIM
        return name, "X to test", DIM

    def measure(self) -> None:
        """The drive's read and write speed in this handheld, off the window's thread."""
        drive = self.drive()
        folder = self.test_folder(drive)
        if drive is None or folder is None or self.measuring is not None:
            return
        self.measuring, self.test_in = drive.number, folder
        if not self.tester.run():
            self.measuring = None
            return
        self.pane.status.setText("Writing a test file of 1 GB and reading it back: a few seconds.")
        self.show_drive()
        self.update_legend()

    def _measure(self) -> tuple[float, float]:
        return self.measure_job(self.test_in)

    def _measured(self, result: object) -> None:
        number, self.measuring = self.measuring, None
        if isinstance(result, tuple) and number is not None:
            self.measured[number] = result
            self.pane.status.setText("")
            self.log.info(f"Measured drive {number}: read {result[0]:,.0f}, write {result[1]:,.0f} MB/s.")
        else:
            self.pane.status.setText(str(result))
            self.log.error(f"The speed test failed: {result}")
        self.show_drive()
        self.update_legend()

    # The screenshot

    def screenshot(self) -> None:
        """RB: the window as it shows now, as a PNG in Pictures\\SSD Check; Explorer then shows it (owner,
        06-11-2026). The line at the bottom is left out of the picture."""
        self.pane.status.setText("")
        path = new_path(self.pictures, ".png")
        try:
            self.pictures.mkdir(parents=True, exist_ok=True)
            saved = self.grab().save(str(path), "PNG")
        except OSError:
            saved = False
        if not saved:
            self.pane.status.setText(f"The screenshot could not be saved in {private(self.pictures)}.")
            return
        self.pane.status.setText(f"Saved: {private(path)}")
        self.log.info(f"Screenshot saved: {private(path)}.")
        show_in_folder(path)

    # The buttons

    def update_legend(self) -> None:
        """X Test speed (a drive with a drive letter, no test running), Y Read again (not while reading), RB
        Screenshot, then core's Menu Info, B Back and View Exit (the suite's rule)."""
        if not hasattr(self, "legend"):
            return
        drive = self.drive() if hasattr(self, "drives") else None
        can_test = drive is not None and self.measuring is None and self.test_folder(drive) is not None
        reading = hasattr(self, "reader") and self.reader.busy
        self.legend.set_items([*([("X", "Test speed")] if can_test else []),
                               *([] if reading else [("Y", "Read again")]), ("RB", "Screenshot"),
                               *self.common_items()])

    def on_back(self) -> None:
        """B goes back from the pane to its card; with nowhere to go it does nothing (View exits the app)."""
        self.go_back()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        super().closeEvent(event)
