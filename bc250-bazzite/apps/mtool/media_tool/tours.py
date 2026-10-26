# SPDX-License-Identifier: GPL-3.0-or-later
"""Record the suite's video tours from a checkout: front ends for the checkout's tools/record-tour.sh (the portal's
tour) and tools/record-app-tour.sh (one app's), which run in the background with their output shown."""

from __future__ import annotations

import os
import signal
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .icons import find_checkout
from .theme import ACCENT, header_font, surface_style

RECORD_TOUR = Path("tools") / "record-tour.sh"
RECORD_APP_TOUR = Path("tools") / "record-app-tour.sh"
MANIFEST = Path("portal") / "apps.toml"
SECONDS = 40                                        # an app's tour, as tools/app_tour.py makes it by default


class Pill(QFrame):
    """A header pill, as the suite's apps have them: a name in large type, what it does under it; the accent edge
    under the mouse or the keyboard focus. A click, Enter or Space emits clicked."""

    clicked = pyqtSignal()

    def __init__(self, value: str, caption: str, tooltip: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pill")
        self.setStyleSheet(surface_style(None, "#pill") + f"#pill:hover, #pill:focus {{ border-color:{ACCENT}; }}"
                           + "QLabel { background:transparent; border:none; }")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(tooltip)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 7, 11, 7)
        layout.setSpacing(0)
        self.value = QLabel(value)
        self.value.setStyleSheet(header_font() + "font-size:18px; font-weight:800;")
        self.caption = QLabel(caption)
        self.caption.setStyleSheet("font-size:12px; font-weight:600;")
        for label in (self.value, self.caption):
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            layout.addWidget(label)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


@dataclass(frozen=True)
class TourApp:
    """One program a tour can be made of: an app, or one of the two programs of compute and cores."""

    key: str
    name: str
    package: str | None = None                      # only for an app with two programs
    version: str = ""

    @property
    def label(self) -> str:
        return f"{self.name} ({self.package})" if self.package else self.name

    @property
    def file_name(self) -> str:
        """The video's name, as tools/app_tour.py names it."""
        name = self.key if self.package is None else f"{self.key}-{self.package}"
        return f"bc250-{name}-tour{f'-v{self.version}' if self.version else ''}.mp4"


def videos_dir() -> Path:
    return Path.home() / "Videos"


def tour_apps(checkout: Path) -> list[TourApp]:
    """The apps of the checkout's portal manifest, each program once, in the manifest's order."""
    manifest = tomllib.loads((checkout / MANIFEST).read_text(encoding="utf-8"))
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
                apps.append(TourApp(key, name, None, version))
            else:
                apps += [TourApp(key, name, package, version) for package in packages]
    return apps


def portal_video(checkout: Path) -> Path:
    """Where tools/record-tour.sh writes the portal's tour."""
    version = (checkout / "portal" / "VERSION").read_text(encoding="utf-8").strip()
    return videos_dir() / f"bc250-portal-tour-v{version}.mp4"


def portal_command(checkout: Path, out: Path, music: bool, wiki: bool) -> list[str]:
    return ["bash", str(checkout / RECORD_TOUR), str(out), *([] if music else ["--no-music"]),
            *(["--wiki"] if wiki else [])]


def app_command(checkout: Path, app: TourApp, out: Path, seconds: int, music: bool) -> list[str]:
    return ["bash", str(checkout / RECORD_APP_TOUR), app.key, str(out),
            *(["--package", app.package] if app.package else []), "--seconds", str(seconds),
            *([] if music else ["--no-music"])]


class TourDialog(QDialog):
    """A tour dialog: the suite checkout, the dialog's own options, the output of the runs, and Record and Stop.
    The runs go one after another, each in its own process group so Stop ends the recording and what it started."""

    SCRIPT = RECORD_TOUR

    def __init__(self, title: str, intro: str, checkout: Path | None, play: Callable[[Path], object] | None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(680, 560)
        self.checkout = checkout
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

        checkout_row = QHBoxLayout()
        checkout_row.addWidget(QLabel("Suite checkout:"))
        self.checkout_path = QLineEdit()
        self.checkout_path.setReadOnly(True)
        self.checkout_path.setPlaceholderText("Choose the folder of a suite checkout")
        checkout_row.addWidget(self.checkout_path, 1)
        choose_checkout = QPushButton("Choose folder…")
        choose_checkout.clicked.connect(self._choose_checkout)
        checkout_row.addWidget(choose_checkout)
        layout.addLayout(checkout_row)

        self.options = QVBoxLayout()
        layout.addLayout(self.options)
        self.music = QCheckBox("Music under the video, faded out over the last two seconds")
        self.music.setChecked(True)

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

    # --- the checkout ---------------------------------------------------------------------------------------
    def _choose_checkout(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose the suite checkout")
        if not selected:
            return
        checkout = find_checkout(Path(selected))
        if checkout is None:
            self.output.setPlainText(f"{selected} is not a suite checkout.")
            return
        self.set_checkout(checkout)

    def set_checkout(self, checkout: Path | None) -> None:
        self.checkout = checkout
        if checkout is None:
            self.checkout_path.clear()
            self.output.setPlainText("Choose the folder of a suite checkout: the tours are recorded from it.")
        elif not (checkout / self.SCRIPT).is_file():
            self.checkout_path.setText(str(checkout))
            self.output.setPlainText(f"This checkout has no {self.SCRIPT.as_posix()}: update it first.")
            self.checkout = None
        else:
            self.checkout_path.setText(str(checkout))
            self.output.clear()
        self.checkout_changed()
        self.update_buttons()

    def checkout_changed(self) -> None:
        """A dialog's own options that come from the checkout."""

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

    def __init__(self, checkout: Path | None, play: Callable[[Path], object] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(
            "Portal video tour",
            "Record the portal's video tour, about two minutes, from the checkout as it is now: the real portal "
            "window, offscreen, so nothing shows on the screen while it records. It takes about a minute and goes to "
            "your Videos folder.", checkout, play, parent)
        self.wiki = QCheckBox("Also write the copy on the wiki's Portal Tour page (docs/videos/portal-tour.mp4)")
        self.options.addWidget(self.music)
        self.options.addWidget(self.wiki)
        self.set_checkout(checkout)

    def runs(self) -> list[tuple[list[str], Path]]:
        if self.checkout is None:
            return []
        out = portal_video(self.checkout)
        return [(portal_command(self.checkout, out, self.music.isChecked(), self.wiki.isChecked()), out)]

    def finished_all(self) -> None:
        if self.made and self.wiki.isChecked():
            self.output.appendPlainText("The wiki's copy is changed in the checkout; review and commit it there.")


class AppsTourDialog(TourDialog):
    SCRIPT = RECORD_APP_TOUR

    def __init__(self, checkout: Path | None, play: Callable[[Path], object] | None = None,
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
            item.setToolTip(str(videos_dir() / app.file_name))
            self.apps.addItem(item)

    def _tick(self, on: bool) -> None:
        for row in range(self.apps.count()):
            self.apps.item(row).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def ticked(self) -> list[TourApp]:
        return [self.apps.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.apps.count())
                if self.apps.item(row).checkState() == Qt.CheckState.Checked]

    def runs(self) -> list[tuple[list[str], Path]]:
        if self.checkout is None:
            return []
        return [(app_command(self.checkout, app, videos_dir() / app.file_name, self.seconds.value(),
                             self.music.isChecked()), videos_dir() / app.file_name) for app in self.ticked()]

    def _play_item(self, item: QListWidgetItem) -> None:
        video = videos_dir() / item.data(Qt.ItemDataRole.UserRole).file_name
        if video.is_file() and self.play is not None and not self.running():
            self.play(video)
