# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's header (the icon at 96 px, the name with the version, the drive's state beside it, the
Refresh at the right end) with three boxes on the second row and the drive chosen below, the health, the power cycles and the
power-on hours of the chosen drive, as udisks last read them (smart.py). The reading runs off the GUI thread: udisks
may wake a sleeping drive first."""

from __future__ import annotations

import datetime
import threading

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from bc250_core.theme import GREEN, GREY, ORANGE, RED
from bc250_core.widgets import AppHeader, InfoButton, MetricBox, StatusText, hint_label, same_width

from . import APP_NAME, LOGO_PATH, __version__, smart

ABOUT = ("<b>Health</b>: how much of its rated life the drive has left, by the drive's own count. An NVMe drive "
         "reports how much it has used (health is 100 minus that); a SATA SSD reports it in an attribute of its "
         "maker's, so a drive without a known one shows “not reported”.<br><b>Power cycles</b>: how often "
         "the drive was switched on. <b>Power-on hours</b>: how long it has run in all.<br>udisks reads the "
         "values from the drive now and then; Refresh shows what it read last.")
WARNINGS = {"spare": "little spare space left", "temperature": "too hot or too cold", "degraded": "less reliable",
            "readonly": "read-only", "volatile_mem": "its backup power failed", "pmr_readonly": "read-only",
            "failing": "SMART says the drive is failing"}
NONE = "—"


class _Reader(QObject):
    """smart.read_drives() in a thread of its own; done carries the drives or the error's text."""

    done = pyqtSignal(object)

    def __init__(self, run_: smart.Run):
        super().__init__()
        self.run = run_

    def start(self) -> None:
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        try:
            self.done.emit(smart.read_drives(self.run))
        except smart.SmartError as exc:
            self.done.emit(str(exc))


def thousands(number: int) -> str:
    return f"{number:,}"


class MainWindow(QMainWindow):
    def __init__(self, run_: smart.Run = smart.run, threaded: bool = True) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(820, 220)
        self.run, self.threaded = run_, threaded
        self.drives: list[smart.Drive] = []
        self.readers: list[_Reader] = []        # kept alive until their thread reports
        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.state = StatusText()
        header.add_state(self.state)
        self.drive_box = QComboBox()
        self.drive_box.setToolTip("The drive to show")
        self.drive_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.drive_box.currentIndexChanged.connect(self.show_drive)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Read the drives again")
        self.refresh_button.clicked.connect(self.refresh)
        header.add_action(self.refresh_button)
        self.health_box = MetricBox("Health")
        self.cycles_box = MetricBox("Power cycles")
        self.hours_box = MetricBox("Power-on hours")
        same_width([self.health_box, self.cycles_box, self.hours_box])
        for box in (self.health_box, self.cycles_box, self.hours_box):
            header.add_second(box)
        self.about = InfoButton(ABOUT, "About these values")
        header.add_second(self.about)
        header.second_row.addStretch(1)
        contents = QWidget()
        layout = QVBoxLayout(contents)
        layout.addLayout(header)
        drive_row = QHBoxLayout()
        drive_row.addWidget(QLabel("Drive"))
        drive_row.addWidget(self.drive_box)
        self.detail = hint_label("")
        drive_row.addWidget(self.detail, 1)
        layout.addSpacing(6)
        layout.addLayout(drive_row)
        layout.addStretch(1)
        self.setCentralWidget(contents)
        self.refresh()

    def refresh(self) -> None:
        """Reads the drives again; the window follows when udisks has answered."""
        self.refresh_button.setEnabled(False)
        self.state.set_status("Reading…", "info")
        reader = _Reader(self.run)
        reader.done.connect(self._read)
        if self.threaded:
            self.readers.append(reader)
            reader.start()
        else:
            reader._read()

    def _read(self, result) -> None:
        self.readers = [r for r in self.readers if r is not self.sender()]
        self.refresh_button.setEnabled(True)
        chosen = self.current().path if self.current() else ""
        self.drives = result if isinstance(result, list) else []
        self.drive_box.blockSignals(True)
        self.drive_box.clear()
        for drive in self.drives:
            self.drive_box.addItem(drive.label)
        index = next((i for i, d in enumerate(self.drives) if d.path == chosen), 0)
        self.drive_box.setCurrentIndex(index if self.drives else -1)
        self.drive_box.setEnabled(len(self.drives) > 1)
        self.drive_box.blockSignals(False)
        if isinstance(result, str):
            self.clear_boxes()
            self.state.set_status("udisks does not answer", "bad", result)
            self.detail.setText(result)
        elif not self.drives:
            self.clear_boxes()
            self.state.set_status("No drive reports SMART", "neutral",
                                  "udisks knows no NVMe or SATA drive that reports SMART values")
            self.detail.setText("A drive on USB often hides its SMART values behind the adapter.")
        else:
            self.show_drive()

    def current(self) -> smart.Drive | None:
        index = self.drive_box.currentIndex()
        return self.drives[index] if 0 <= index < len(self.drives) else None

    def clear_boxes(self) -> None:
        for box in (self.health_box, self.cycles_box, self.hours_box):
            box.set_value(NONE)
            box.set_colour(GREY)

    def show_drive(self) -> None:
        drive = self.current()
        if drive is None:
            return
        if drive.health is None:
            self.health_box.set_value("Not reported", "The drive reports no health value that SSD Check knows")
            self.health_box.set_colour(GREY)
        else:
            self.health_box.set_value(f"{drive.health} %", f"From {drive.health_source}")
            # 0: the rated endurance is used up; the drive may still work, but keep a backup
            self.health_box.set_colour(RED if drive.warnings else ORANGE if drive.health == 0 else GREEN)
        self.cycles_box.set_value(NONE if drive.power_cycles is None else thousands(drive.power_cycles))
        if drive.hours is None:
            self.hours_box.set_value(NONE)
        else:
            self.hours_box.set_value(thousands(drive.hours), f"About {drive.hours / 24:,.0f} days, "
                                                             f"{drive.hours / 8766:.1f} years")
        for box in (self.cycles_box, self.hours_box):
            box.set_colour(GREY)
        if drive.warnings:
            said = ", ".join(WARNINGS.get(w, w) for w in drive.warnings)
            self.state.set_status("The drive reports a problem", "bad", f"The drive says: {said}")
        elif drive.error:
            self.state.set_status("Partly read", "warn", drive.error)
        elif drive.health is None:
            self.state.set_status("Health not reported", "neutral")
        else:
            self.state.set_status("No problems reported", "ok")
        read = (f", read by udisks at {datetime.datetime.fromtimestamp(drive.updated):%d-%m-%Y %H:%M}"
                if drive.updated else "")
        self.detail.setText(f"{drive.bus} drive{read}." if drive.bus else "")
