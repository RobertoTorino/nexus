# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's header (the icon at 96 px, the name with the version, the drive's state beside it) with
the health, the serial (a popup shows it), the speed test and Refresh on the second row (owner, 05-11-2026); below
it the drive chosen by its number, its model and where its values come from, and its specs as pills: the power
cycles, the power-on hours and days, the device, the data the host read and wrote, the firmware and whether a newer
one exists, then a row on speed: the interface, the link now, the most the board's port carries and the maker's
rated read and write (rated.py), beside the speeds measured in this board at the top (speedtest.py), so it shows
whether the board holds the drive back. The reading and the measuring run off the GUI thread: udisks may wake a sleeping drive first.
Screenshot, beside the drive's list (owner, 05-11-2026), saves the window with the values it shows as a PNG in the
Pictures folder; the serial stays hidden in it, as on the screen."""

from __future__ import annotations

import datetime
import threading
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QObject, QPoint, QStandardPaths, Qt, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout,
                             QWidget)

from bc250_core.platform import private, show_in_folder
from bc250_core.theme import GREEN, GREY, ORANGE, RED
from bc250_core.widgets import (AppHeader, InfoButton, MetricBox, Pill, RoundedToolTip, StatusText, accent,
                                hint_label, same_width)

from . import APP_NAME, LOGO_PATH, __version__, smart, speedtest

ABOUT = ("<b>Health</b>: how much of its rated life the drive has left, by the drive's own count. An NVMe drive "
         "reports how much it has used (health is 100 minus that); a SATA SSD reports it in an attribute of its "
         "maker's, so a drive without a known one shows “not reported”.<br><b>Power cycles</b>: how often "
         "the drive was switched on. <b>Power-on hours</b>: how long it has run in all.<br>udisks reads the "
         "values from the drive now and then; Refresh shows what it read last. A drive on USB often hides them "
         "behind its adapter: then only its specs show.<br><b>Update</b>: whether fwupd knows a newer firmware "
         "for the drive. <b>Serial</b>: hidden; click it to show it.<br><b>Board link</b>: the most the board's "
         "port carries, orange when that is less than the drive can do. <b>Rated</b>: the maker's read and write "
         "speeds. <b>Measured</b>: click it to measure what the drive does in this board.")
WARNINGS = {"spare": "little spare space left", "temperature": "too hot or too cold", "degraded": "less reliable",
            "readonly": "read-only", "volatile_mem": "its backup power failed", "pmr_readonly": "read-only",
            "failing": "SMART says the drive is failing"}
NONE = "—"
HIDDEN = "••••••••"
SECTORS_TIP = "Attribute {}, counted as 512-byte sectors, as most makers do"


class _Speed(QObject):
    """speedtest.measure() in a thread of its own; done carries the drive's path and (read, write) or the error's
    text."""

    done = pyqtSignal(str, object)

    def __init__(self, path: str, folder: Path):
        super().__init__()
        self.path, self.folder = path, folder

    def start(self) -> None:
        threading.Thread(target=self._measure, daemon=True).start()

    def _measure(self) -> None:
        try:
            self.done.emit(self.path, speedtest.measure(self.folder))
        except speedtest.SpeedError as exc:
            self.done.emit(self.path, str(exc))


def rw(read: float | None, write: float | None) -> str:
    return f"{read:,.0f} / {write:,.0f}" if read is not None and write is not None else NONE


class _Reader(QObject):
    """smart.read_drives() in a thread of its own; done carries the drives or the error's text."""

    done = pyqtSignal(object)

    def __init__(self, run_: smart.Run, sysfs: Path):
        super().__init__()
        self.run, self.sysfs = run_, sysfs

    def start(self) -> None:
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        try:
            self.done.emit(smart.read_drives(self.run, self.sysfs))
        except smart.SmartError as exc:
            self.done.emit(str(exc))


def thousands(number: int) -> str:
    return f"{number:,}"


def pictures() -> Path:
    """The user's Pictures folder (xdg-user-dirs, ~/Pictures by default), the app's folder in it."""
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)) / APP_NAME


def screenshot_path(folder: Path, now: datetime.datetime | None = None) -> Path:
    """A PNG in *folder* named after the app and the time ("SSD Check 2026-11-05 18-04-09.png"), not one there
    already: two in one second get (2), (3) and so on."""
    stem = f"{APP_NAME} {(now or datetime.datetime.now()):%Y-%m-%d %H-%M-%S}"
    path, n = folder / f"{stem}.png", 1
    while path.exists():
        n += 1
        path = folder / f"{stem} ({n}).png"
    return path


class MainWindow(QMainWindow):
    def __init__(self, run_: smart.Run = smart.run, threaded: bool = True, sysfs: Path = smart.SYSFS,
                 home: Path | None = None, pictures_: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(820, 420)
        self.run, self.threaded, self.sysfs = run_, threaded, sysfs
        self.home = home                                        # where the speed test prefers to write; tests set it
        self.pictures = pictures_                               # where Screenshot saves (default pictures()); tests set it
        self.measured: dict[str, tuple[float, float]] = {}     # drive path: its measured (read, write)
        self.speed_test: _Speed | None = None                   # kept alive until its thread reports
        self.drives: list[smart.Drive] = []
        self.readers: list[_Reader] = []        # kept alive until their thread reports
        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.state = StatusText()
        header.add_state(self.state)
        # The top row (owner, 05-11-2026): the health, the serial, the speed test and Refresh, as Wi-Fi Driver's and
        # the portal's. The serial shows in a popup, so the pill keeps its width.
        self.health_box = MetricBox("Health")
        self.serial_pill = Pill(HIDDEN, "Serial", "Click to show the serial number")
        self.serial_pill.clicked.connect(self.show_serial_popup)
        self.serial_popup: QWidget | None = None
        self.measure_pill = Pill("Test", "Measured R / W MB/s")
        self.measure_pill.clicked.connect(self.measure)
        self.refresh_pill = Pill("Refresh", "Click to refresh", "Read the drives again")
        self.refresh_pill.clicked.connect(self.refresh)
        same_width([self.health_box, self.serial_pill, self.measure_pill])
        for box in (self.health_box, self.serial_pill, self.measure_pill, self.refresh_pill):
            header.add_second(box)
        self.about = InfoButton(ABOUT, "About these values")
        header.add_second(self.about)
        header.second_row.addStretch(1)
        contents = QWidget()
        layout = QVBoxLayout(contents)
        layout.addLayout(header)

        # The drive by its number (owner, 05-11-2026); its model and where its values come from below it.
        self.drive_box = QComboBox()
        self.drive_box.setToolTip("The drive to show")
        self.drive_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.drive_box.currentIndexChanged.connect(self.drive_chosen)
        # Screenshot on the same line (owner, 05-11-2026): the window with its values, as a PNG.
        self.shot_button = QPushButton("Screenshot")
        self.shot_button.setToolTip("Save the window with the values it shows as a PNG in your Pictures folder "
                                    "(the serial stays hidden)")
        self.shot_button.clicked.connect(self.screenshot)
        self.shot_note = hint_label("")
        drive_row = QHBoxLayout()
        drive_row.addWidget(QLabel("Drive"))
        drive_row.addWidget(self.drive_box)
        drive_row.addWidget(self.shot_button)
        drive_row.addWidget(self.shot_note)
        drive_row.addStretch(1)
        self.model = QLabel("")
        self.model.setStyleSheet("font-size:16px; font-weight:700;")
        self.detail = hint_label("")
        layout.addSpacing(6)
        layout.addLayout(drive_row)
        layout.addWidget(self.model)
        layout.addWidget(self.detail)

        # The specs, every one a pill (owner, 05-11-2026).
        self.cycles_box = MetricBox("Power cycles")
        self.hours_box = MetricBox("Power-on hours")
        self.days_box = MetricBox("Power-on days")
        self.firmware_box = MetricBox("Firmware")
        self.update_box = MetricBox("Update")
        self.interface_box = MetricBox("Interface")
        self.speed_box = MetricBox("Speed")
        self.device_box = MetricBox("Drive")
        self.read_box = MetricBox("Host reads")
        self.written_box = MetricBox("Host writes")
        # Speed (owner, 05-11-2026): the link now, the most the board's port carries and the maker's rated speeds,
        # against the speeds measured here (the Test pill at the top): whether the board holds the drive back.
        self.board_box = MetricBox("Board link")
        self.rated_box = MetricBox("Rated R / W MB/s")
        rows = [[self.cycles_box, self.hours_box, self.days_box, self.device_box],
                [self.read_box, self.written_box, self.firmware_box, self.update_box],
                [self.interface_box, self.speed_box, self.board_box, self.rated_box]]
        self.specs = [box for row in rows for box in row]
        same_width(self.specs)
        grid = QGridLayout()
        grid.setSpacing(8)
        for row, boxes in enumerate(rows):
            for column, box in enumerate(boxes):
                grid.addWidget(box, row, column)
        grid.setColumnStretch(4, 1)
        layout.addSpacing(6)
        layout.addLayout(grid)
        layout.addStretch(1)
        self.setCentralWidget(contents)
        self.refresh()

    def refresh(self) -> None:
        """Reads the drives again; the window follows when udisks has answered."""
        self.refresh_pill.setEnabled(False)
        self.state.set_status("Reading…", "info")
        reader = _Reader(self.run, self.sysfs)
        reader.done.connect(self._read)
        if self.threaded:
            self.readers.append(reader)
            reader.start()
        else:
            reader._read()

    def _read(self, result) -> None:
        self.readers = [r for r in self.readers if r is not self.sender()]
        self.refresh_pill.setEnabled(True)
        chosen = self.current().path if self.current() else ""
        self.drives = result if isinstance(result, list) else []
        self.close_serial_popup()
        self.drive_box.blockSignals(True)
        self.drive_box.clear()
        for number, drive in enumerate(self.drives, 1):
            self.drive_box.addItem(f"Drive {number}")
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
            self.state.set_status("No drive found", "neutral",
                                  "udisks knows no NVMe or SATA drive that reports SMART values, and no drive on USB")
            self.detail.setText("")
        else:
            self.show_drive()

    def current(self) -> smart.Drive | None:
        index = self.drive_box.currentIndex()
        return self.drives[index] if 0 <= index < len(self.drives) else None

    def clear_boxes(self) -> None:
        self.model.setText("")
        for box in (self.health_box, self.serial_pill, self.measure_pill, *self.specs):
            box.set_value(NONE)
            box.set_colour(GREY)
        self.serial_pill.setEnabled(False)
        self.measure_pill.setEnabled(False)

    def drive_chosen(self) -> None:
        self.close_serial_popup()               # another drive: the serial of the last one goes
        self.show_drive()

    def show_drive(self) -> None:
        drive = self.current()
        if drive is None:
            return
        if not drive.smart:
            self.health_box.set_value(NONE, "The drive's adapter hides its SMART values")
            self.health_box.set_colour(GREY)
        elif drive.health is None:
            self.health_box.set_value("Not reported", "The drive reports no health value that SSD Check knows")
            self.health_box.set_colour(GREY)
        else:
            self.health_box.set_value(f"{drive.health} %", f"From {drive.health_source}")
            # 0: the rated endurance is used up; the drive may still work, but keep a backup
            self.health_box.set_colour(RED if drive.warnings else ORANGE if drive.health == 0 else GREEN)
        self.cycles_box.set_value(NONE if drive.power_cycles is None else thousands(drive.power_cycles))
        if drive.hours is None:
            self.hours_box.set_value(NONE)
            self.days_box.set_value(NONE)
        else:
            self.hours_box.set_value(thousands(drive.hours), f"About {drive.hours / 8766:.1f} years")
            # full days only (owner, 05-11-2026): a day the drive has not finished yet does not count
            self.days_box.set_value(thousands(drive.hours // 24), f"About {drive.hours / 8766:.1f} years")
        if drive.warnings:
            said = ", ".join(WARNINGS.get(w, w) for w in drive.warnings)
            self.state.set_status("The drive reports a problem", "bad", f"The drive says: {said}")
        elif drive.error:
            self.state.set_status("Partly read", "warn", drive.error)
        elif not drive.smart:
            self.state.set_status("No SMART over USB", "neutral",
                                  "udisks cannot read the SMART values through the drive's USB adapter (some "
                                  "adapters pass them only to smartctl, which needs root): health, power cycles, "
                                  "hours and the data read and written stay empty")
        elif drive.health is None:
            self.state.set_status("Health not reported", "neutral")
        else:
            self.state.set_status("No problems reported", "ok")
        self.model.setText(" · ".join(p for p in (drive.model or "Unknown drive",
                                                  smart.size_text(drive.size) if drive.size else "") if p))
        read = (f", read by udisks at {datetime.datetime.fromtimestamp(drive.updated):%d-%m-%Y %H:%M}"
                if drive.updated else "")
        kind = "NVMe drive on USB" if drive.interface == "NVMe over USB" else f"{drive.bus} drive"
        self.detail.setText(f"{kind}{read}." if drive.bus else "")
        self.show_specs(drive)

    def show_specs(self, drive: smart.Drive) -> None:
        self.firmware_box.set_value(drive.firmware or NONE)
        self.update_box.set_value(drive.update, drive.update_tip)
        self.update_box.set_colour(ORANGE if drive.update == smart.AVAILABLE else
                                   GREEN if drive.update == smart.UP_TO_DATE else GREY)
        self.show_serial(drive)
        self.interface_box.set_value(drive.interface or NONE)
        self.speed_box.set_value(drive.speed or NONE, " ".join(t for t in (
            f"{drive.speed_tip}." if drive.speed_tip else "", drive.slow_link) if t))
        self.device_box.set_value(drive.device or NONE, f"/dev/{drive.device}" if drive.device else "")
        for box, amount, number in ((self.read_box, drive.data_read, smart.READ_ID),
                                    (self.written_box, drive.data_written, smart.WRITTEN_ID)):
            tip = SECTORS_TIP.format(number) if drive.bus != "NVMe" and amount is not None else ""
            box.set_value(NONE if amount is None else smart.size_text(amount), tip)
        for box in self.specs:
            if box is not self.update_box:
                box.set_colour(GREY)
        if drive.slow_link:
            self.speed_box.set_colour(ORANGE)          # slower than the port allows: the tooltip says what to try
        self.show_speeds(drive)

    def show_speeds(self, drive: smart.Drive) -> None:
        board = f"{drive.board_link}, at most about {drive.board_mbps:,} MB/s" if drive.board_mbps else ""
        held = smart.held_back(drive)
        if held is None:
            verdict = ""
        elif drive.rated_read:
            verdict = (f"The drive is rated {drive.rated_read:,} MB/s read: "
                       + ("the board holds it back." if held else "the board's port is fast enough for it."))
        else:
            verdict = (f"The drive's fastest link carries about {drive.drive_mbps:,} MB/s: "
                       + ("the board holds it back." if held else "the board's port is fast enough for it."))
        self.board_box.set_value(drive.board_link or NONE, f"The board's port: {board}. {verdict}" if board else "")
        self.board_box.set_colour(ORANGE if held else GREEN if held is False else GREY)
        if drive.rated_read is not None:
            self.rated_box.set_value(rw(drive.rated_read, drive.rated_write),
                                     "The maker's rated sequential read and write")
        else:
            most = f" Its fastest link carries about {drive.drive_mbps:,} MB/s." if drive.drive_mbps else ""
            self.rated_box.set_value("Unknown", f"Not in SSD Check's list of rated speeds.{most}")
        self.show_measured(drive)

    def test_folder(self, drive: smart.Drive) -> Path | None:
        return speedtest.folder_for(drive.mounts, self.home)

    def show_measured(self, drive: smart.Drive) -> None:
        folder = self.test_folder(drive)
        busy = self.speed_test is not None
        self.measure_pill.setEnabled(folder is not None and not busy)
        if busy:
            self.measure_pill.set_value("Testing…", "Writing a test file and reading it back")
        elif folder is None and drive.mounts:
            self.measure_pill.set_value(NONE, "The test needs a folder on the drive that you may write to; its file "
                                              "systems belong to root (another system's, for example)")
        elif folder is None:
            self.measure_pill.set_value(NONE, "Mount the drive to measure it: the test needs a folder on it")
        elif drive.path in self.measured:
            self.measure_pill.set_value(rw(*self.measured[drive.path]),
                                        "Measured in this board. Click to measure again.")
        else:
            self.measure_pill.set_value("Test", "Click to measure: writes a test file of 1 GB to the drive, reads it "
                                                "back and deletes it. A few seconds.")

    def measure(self) -> None:
        """The chosen drive's read and write speed in this board, off the GUI thread."""
        drive = self.current()
        folder = self.test_folder(drive) if drive else None
        if drive is None or folder is None or self.speed_test is not None:
            return
        self.speed_test = _Speed(drive.path, folder)
        self.speed_test.done.connect(self._measured)        # a bound method: queued to the GUI thread
        self.show_measured(drive)
        if self.threaded:
            self.speed_test.start()
        else:
            self.speed_test._measure()

    def _measured(self, path: str, result) -> None:
        self.speed_test = None
        if isinstance(result, tuple):
            self.measured[path] = result
        drive = self.current()
        if drive is not None:
            self.show_measured(drive)
        if isinstance(result, str) and drive is not None and drive.path == path:
            self.measure_pill.set_value("Failed", result)

    def screenshot(self) -> None:
        """The window as it shows now, saved as a PNG in the Pictures folder. The serial's popup is a window of its
        own, so the picture has the hidden pill only; the line beside the button says where the file went, and the
        file manager shows it (owner, 06-11-2026)."""
        self.shot_note.setText("")                      # the last one's line stays out of the picture
        self.shot_note.setToolTip("")
        path = screenshot_path(self.pictures or pictures())
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            saved = self.grab().save(str(path), "PNG")
        except OSError:
            saved = False
        if saved:
            self.shot_note.setText(f"Saved: {path.name}")
            self.shot_note.setToolTip(private(path))
            show_in_folder(path)
        else:
            self.shot_note.setText("The screenshot could not be saved")
            self.shot_note.setToolTip(f"Could not write to {private(path.parent)}")

    def show_serial(self, drive: smart.Drive) -> None:
        """The pill only says there is a serial; the popup shows it (show_serial_popup)."""
        self.serial_pill.setEnabled(bool(drive.serial))
        if drive.serial:
            self.serial_pill.set_value(HIDDEN, "Click to show the serial number")
        else:
            self.serial_pill.set_value(NONE, "The drive reports no serial number")

    def show_serial_popup(self) -> None:
        """The serial in a popup below its pill, in the style of the info symbol's, selectable to copy; the pill keeps
        its width. The serial is personal data: shown only on a click, gone with a click elsewhere, another drive or
        Refresh, and never logged."""
        drive = self.current()
        if drive is None or not drive.serial:
            return
        self.close_serial_popup()
        # Wayland maps a popup relative to a parent surface, so it is a child of the window.
        popup = QWidget(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box = QVBoxLayout(popup)
        box.setContentsMargins(0, 0, 0, 0)
        label = QLabel(drive.serial)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setStyleSheet(f"QLabel {{ background:palette(window); color:palette(window-text); border:1px solid "
                            f"{accent()}; border-radius:6px; padding:8px 10px; font-size:16px; font-weight:700; }}")
        box.addWidget(label)
        popup.adjustSize()
        pill = self.serial_pill
        popup.move(RoundedToolTip._place(pill.mapToGlobal(QPoint(0, pill.height() + 4)), popup.size()))
        self.serial_popup = popup
        popup.show()

    def close_serial_popup(self) -> None:
        if self.serial_popup is not None and not sip.isdeleted(self.serial_popup):
            self.serial_popup.close()               # a click elsewhere may have closed (and deleted) it already
        self.serial_popup = None
