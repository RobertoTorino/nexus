# SPDX-License-Identifier: GPL-3.0-or-later
"""Record a suite's video tours: front ends for the suite's tools/record-tour.sh (the portal's tour) and
tools/record-app-tour.sh (one app's), which run in the background with their output shown. The dialogs take the
suite's folder in the checkout (the dashboard's chosen suite); they were the Media Tool's until 02-11-2026."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

RECORD_TOUR = Path("tools") / "record-tour.sh"
RECORD_APP_TOUR = Path("tools") / "record-app-tour.sh"
MANIFEST = Path("portal") / "apps.toml"
SECONDS = 40                                        # an app's tour, as tools/app_tour.py makes it by default
SIZES = ("1080p", "1440p", "2160p")                 # the video's size (tools/tour_frames.py); the first is the default
SIZE_HINT = "1080p for the wiki, 2160p (4K) for YouTube: about four times the time"
WINDOWS = sys.platform == "win32"                   # the scripts run with Git Bash there, without setsid


def size_suffix(size: str) -> str:
    """What the scripts put before .mp4 for a size other than the default."""
    return "" if size == SIZES[0] else f"-{size}"


def video_prefix(suite: Path) -> str:
    """What the suite's tour videos start with: its tag prefix (wp-), or bc250- for the suite without one, as the
    tour scripts name them."""
    try:
        return (suite / "TAG_PREFIX").read_text(encoding="utf-8").strip() or "bc250-"
    except OSError:
        return "bc250-"


def size_options(size: str) -> list[str]:
    """The --size the scripts take, left out for the default so an older checkout's scripts still run."""
    return [] if size == SIZES[0] else ["--size", size]


@dataclass(frozen=True)
class TourApp:
    """One program a tour can be made of: an app, or one of the two programs of compute and cores."""

    key: str
    name: str
    package: str | None = None                      # only for an app with two programs
    version: str = ""
    prefix: str = "bc250-"                          # the suite's: what its videos' names start with

    @property
    def label(self) -> str:
        return f"{self.name} ({self.package})" if self.package else self.name

    @property
    def file_name(self) -> str:
        """The video's name, as tools/app_tour.py names it."""
        return self.video()

    def video(self, size: str = SIZES[0]) -> str:
        """The video's name at *size*: -2160p before .mp4 for 4K, as tools/app_tour.py names it."""
        name = self.key if self.package is None else f"{self.key}-{self.package}"
        return f"{self.prefix}{name}-tour{f'-v{self.version}' if self.version else ''}{size_suffix(size)}.mp4"


def videos_dir() -> Path:
    return Path.home() / "Videos"


def tour_apps(checkout: Path) -> list[TourApp]:
    """The apps of the checkout's portal manifest, each program once, in the manifest's order."""
    manifest = tomllib.loads((checkout / MANIFEST).read_text(encoding="utf-8"))
    prefix = video_prefix(checkout)
    apps = []
    for table in ("apps", "checkout"):
        for key, entry in manifest.get(table, {}).items():
            folder = checkout / entry.get("folder", f"apps/{key}")
            version = (folder / "VERSION").read_text(encoding="utf-8").strip() if (folder / "VERSION").is_file() else ""
            packages = sorted(path.parent.name for path in folder.glob("*/__main__.py"))
            if not packages:
                continue
            name = entry.get("name", key)
            if len(packages) == 1:
                apps.append(TourApp(key, name, None, version, prefix))
            else:
                apps += [TourApp(key, name, package, version, prefix) for package in packages]
    return apps


def portal_video(checkout: Path, size: str = SIZES[0]) -> Path:
    """Where tools/record-tour.sh writes the portal's tour (-2160p before .mp4 for 4K)."""
    version = (checkout / "portal" / "VERSION").read_text(encoding="utf-8").strip()
    return videos_dir() / f"{video_prefix(checkout)}portal-tour-v{version}{size_suffix(size)}.mp4"


def portal_command(checkout: Path, out: Path, music: bool, wiki: bool, size: str = SIZES[0]) -> list[str]:
    return ["bash", str(checkout / RECORD_TOUR), str(out), *([] if music else ["--no-music"]),
            *(["--wiki"] if wiki else []), *size_options(size)]


def app_command(checkout: Path, app: TourApp, out: Path, seconds: int, music: bool,
                size: str = SIZES[0]) -> list[str]:
    return ["bash", str(checkout / RECORD_APP_TOUR), app.key, str(out),
            *(["--package", app.package] if app.package else []), "--seconds", str(seconds),
            *([] if music else ["--no-music"]), *size_options(size)]


class TourDialog(QDialog):
    """A tour dialog: the suite's folder, the dialog's own options, the output of the runs, and Record and Stop.
    The runs go one after another, each in its own process group so Stop ends the recording and what it started."""

    SCRIPT = RECORD_TOUR

    def __init__(self, title: str, intro: str, checkout: Path, play: Callable[[Path], object] | None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(680, 560)
        self.checkout: Path | None = checkout
        self.play = play
        self.queue: list[tuple[list[str], Path]] = []
        self.process: QProcess | None = None
        self.current: Path | None = None
        self.made: list[Path] = []
        self.failed: list[Path] = []
        layout = QVBoxLayout(self)
        text = QLabel(intro)
        text.setWordWrap(True)
        layout.addWidget(text)
        suite_row = QHBoxLayout()
        suite_row.addWidget(QLabel("Suite:"))
        self.suite_label = QLabel(str(checkout))
        self.suite_label.setToolTip("The suite's folder in the checkout, as chosen in the dashboard")
        suite_row.addWidget(self.suite_label, 1)
        layout.addLayout(suite_row)

        self.options = QVBoxLayout()
        layout.addLayout(self.options)
        self.music = QCheckBox("Music under the video, faded out over the last two seconds")
        self.music.setChecked(True)
        self.size = QComboBox()                     # the video's size; the dialogs put it in their options
        self.size.addItems(SIZES)                   # before the signal is connected: the dialog is not built yet
        self.size.setToolTip(SIZE_HINT)
        self.size.currentTextChanged.connect(lambda _size: self.size_changed())

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(5000)
        layout.addWidget(self.output, 1)
        buttons = QHBoxLayout()
        self.folder_button = QPushButton("Open folder")
        self.folder_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(videos_dir()))))
        buttons.addWidget(self.folder_button)
        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self._play_last)
        self.play_button.setEnabled(False)
        buttons.addWidget(self.play_button)
        buttons.addStretch(1)
        self.record_button = QPushButton("Record")
        self.record_button.clicked.connect(self.record)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setEnabled(False)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        for button in (self.record_button, self.stop_button, close_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def size_row(self) -> QHBoxLayout:
        """Size: with the box and its hint, for the dialog's options."""
        row = QHBoxLayout()
        row.addWidget(QLabel("Size:"))
        row.addWidget(self.size)
        hint = QLabel(SIZE_HINT)
        hint.setStyleSheet("font-size:12px;")
        row.addWidget(hint)
        row.addStretch(1)
        return row

    # --- the suite ------------------------------------------------------------------------------------------
    def set_checkout(self, checkout: Path) -> None:
        """The suite's folder; a suite without the script (a Windows suite) gets the dialog greyed out."""
        self.checkout = checkout
        if not (checkout / self.SCRIPT).is_file():
            self.output.setPlainText(f"This suite has no {self.SCRIPT.as_posix()}: its tours are not recorded here.")
            self.checkout = None
        else:
            self.output.clear()
        self.checkout_changed()
        self.update_buttons()

    def checkout_changed(self) -> None:
        """A dialog's own options that come from the checkout."""

    def size_changed(self) -> None:
        """What a dialog shows for the size: the names of the videos."""

    # --- the runs -------------------------------------------------------------------------------------------
    def runs(self) -> list[tuple[list[str], Path]]:
        """The commands to run, each with the video it makes."""
        return []

    def running(self) -> bool:
        return self.process is not None

    def update_buttons(self) -> None:
        self.record_button.setEnabled(self.checkout is not None and not self.running() and bool(self.runs()))
        self.stop_button.setEnabled(self.running())
        self.play_button.setEnabled(bool(self.made) and self.play is not None and not self.running())

    def record(self) -> None:
        if self.checkout is None or self.running():
            return
        self.queue = self.runs()
        self.made, self.failed = [], []
        self.output.clear()
        self._next()

    def _next(self) -> None:
        if not self.queue:
            self.process = None
            self.current = None
            done = f"Done: {len(self.made)} video(s) in {videos_dir()}." if self.made else "No video was made."
            if self.failed:
                done += " Failed: " + ", ".join(path.name for path in self.failed) + "."
            self.output.appendPlainText(done)
            self.finished_all()
            self.update_buttons()
            return
        command, self.current = self.queue.pop(0)
        self.current.parent.mkdir(parents=True, exist_ok=True)
        process = self.process = QProcess(self)
        process.setWorkingDirectory(str(self.checkout))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read)
        process.finished.connect(self._ended)
        process.errorOccurred.connect(self._error)
        if WINDOWS:                 # no setsid on Windows: Stop ends the script's process tree instead
            process.start(command[0], command[1:])
        else:
            # its own process group (setsid), so Stop ends the script and the Python and ffmpeg it started
            process.start("setsid", command)
        self.update_buttons()

    def _read(self) -> None:
        if self.process is not None:
            text = bytes(self.process.readAllStandardOutput()).decode(errors="replace")
            for line in text.splitlines():
                if line.strip() and "does not support" not in line and "multimedia" not in line:
                    self.output.appendPlainText(line)

    def _ended(self, code: int, status: QProcess.ExitStatus) -> None:
        self._read()
        if self.current is not None:
            if code == 0 and status == QProcess.ExitStatus.NormalExit and self.current.is_file():
                self.made.append(self.current)
            else:
                self.failed.append(self.current)
                self.output.appendPlainText(f"{self.current.name}: stopped with status {code}.")
        self._next()

    def _error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.output.appendPlainText(f"Could not start {self.SCRIPT.as_posix()}.")
            self.queue = []
            if self.current is not None:
                self.failed.append(self.current)
            self.current = None
            self._next()

    def stop(self) -> None:
        """End the recording that runs, and leave the rest out."""
        self.queue = []
        process = self.process
        if process is None:
            return
        try:
            if WINDOWS:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(int(process.processId()))],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                os.killpg(int(process.processId()), signal.SIGTERM)
        except (OSError, ValueError):
            process.terminate()
        process.waitForFinished(5000)

    def finished_all(self) -> None:
        """After the last run."""

    def _play_last(self) -> None:
        if self.made and self.play is not None:
            self.play(self.made[-1])

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self.running():
            answer = QMessageBox.question(self, self.windowTitle(), "A recording is running. Stop it and close?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.stop()
        event.accept()


class PortalTourDialog(TourDialog):
    SCRIPT = RECORD_TOUR

    def __init__(self, checkout: Path, play: Callable[[Path], object] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(
            "Portal video tour",
            "Record the portal's video tour, about two minutes, from the checkout as it is now: the real portal "
            "window, offscreen, so nothing shows on the screen while it records. It takes about a minute and goes to "
            "your Videos folder.", checkout, play, parent)
        self.wiki = QCheckBox("Also write the copy on the wiki's Portal Tour page (docs/videos/portal-tour.mp4)")
        self.options.addWidget(self.music)
        self.options.addWidget(self.wiki)
        self.options.addLayout(self.size_row())
        self.set_checkout(checkout)

    def runs(self) -> list[tuple[list[str], Path]]:
        if self.checkout is None:
            return []
        size = self.size.currentText()
        out = portal_video(self.checkout, size)
        return [(portal_command(self.checkout, out, self.music.isChecked(), self.wiki.isChecked(), size), out)]

    def finished_all(self) -> None:
        if self.made and self.wiki.isChecked():
            self.output.appendPlainText("The wiki's copy is changed in the checkout; review and commit it there.")


class AppsTourDialog(TourDialog):
    SCRIPT = RECORD_APP_TOUR

    def __init__(self, checkout: Path, play: Callable[[Path], object] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(
            "Apps video tour",
            "Record a short video tour of each app you tick, from the checkout as it is now: the app's real window, "
            "offscreen, with its own tooltips as the captions. Each takes a few seconds and goes to your Videos "
            "folder. What an app reads from the board is real: watch a video before you publish it.",
            checkout, play, parent)
        self.apps = QListWidget()
        self.apps.itemChanged.connect(lambda _item: self.update_buttons())
        self.apps.itemDoubleClicked.connect(self._play_item)
        self.options.addWidget(self.apps, 2)
        row = QHBoxLayout()
        all_button = QPushButton("All")
        all_button.clicked.connect(lambda: self._tick(True))
        none_button = QPushButton("None")
        none_button.clicked.connect(lambda: self._tick(False))
        row.addWidget(all_button)
        row.addWidget(none_button)
        row.addStretch(1)
        row.addWidget(QLabel("Length:"))
        self.seconds = QSpinBox()
        self.seconds.setRange(20, 120)
        self.seconds.setValue(SECONDS)
        self.seconds.setSuffix(" s")
        row.addWidget(self.seconds)
        row.addSpacing(12)
        row.addWidget(QLabel("Size:"))
        row.addWidget(self.size)
        self.options.addLayout(row)
        self.options.addWidget(self.music)
        self.set_checkout(checkout)

    def checkout_changed(self) -> None:
        self.apps.clear()
        if self.checkout is None:
            return
        for app in tour_apps(self.checkout):
            item = QListWidgetItem(app.label)
            item.setData(Qt.ItemDataRole.UserRole, app)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.apps.addItem(item)
        self.size_changed()

    def size_changed(self) -> None:
        for row in range(self.apps.count()):
            item = self.apps.item(row)
            item.setToolTip(str(videos_dir() / item.data(Qt.ItemDataRole.UserRole).video(self.size.currentText())))

    def _tick(self, on: bool) -> None:
        for row in range(self.apps.count()):
            self.apps.item(row).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def ticked(self) -> list[TourApp]:
        return [self.apps.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.apps.count())
                if self.apps.item(row).checkState() == Qt.CheckState.Checked]

    def runs(self) -> list[tuple[list[str], Path]]:
        if self.checkout is None:
            return []
        size = self.size.currentText()
        return [(app_command(self.checkout, app, videos_dir() / app.video(size), self.seconds.value(),
                             self.music.isChecked(), size), videos_dir() / app.video(size)) for app in self.ticked()]

    def _play_item(self, item: QListWidgetItem) -> None:
        video = videos_dir() / item.data(Qt.ItemDataRole.UserRole).video(self.size.currentText())
        if video.is_file() and self.play is not None and not self.running():
            self.play(video)
