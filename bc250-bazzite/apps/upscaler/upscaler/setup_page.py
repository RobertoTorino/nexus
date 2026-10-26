# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup page: get the latest HelixSR release, its prerequisites and build the network files in one go, and
see whether the payload has a newer release. The page shows and asks; the main window runs."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QElapsedTimer, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
)

from . import plain_tooltip
from .acquire import DLSS_DLL, FALLBACK_VERSION, ReleaseInfo, UpdateStatus
from .style import accent_button
from .widgets import StatusPill, Terminal, hint_label, page_header


def _size(n: int) -> str:
    return "{0:.1f} MB".format(n / 1e6) if n else "?"


class SetupPage(QWidget):
    check_requested = pyqtSignal()
    start_requested = pyqtSignal(object)            # Path | None: local nvngx_dlss.dll
    cancel_requested = pyqtSignal()
    browse_dlss_requested = pyqtSignal()
    find_dlss_requested = pyqtSignal()
    open_work_requested = pyqtSignal()
    import_requested = pyqtSignal(Path)             # import an already built release folder
    auto_check_changed = pyqtSignal(bool)
    fallback_changed = pyqtSignal(bool)             # the version choice: True = the fallback release

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.release: ReleaseInfo | None = None
        self.built: Path | None = None
        self._running = False
        self._checking = False
        layout = QVBoxLayout(self)
        header, _ = page_header("Setup")
        layout.addLayout(header)
        layout.addWidget(hint_label(
            "One click does what the HelixSR README asks you to do by hand: download the release, fetch NVIDIA's "
            "DLSS DLL, Microsoft's shader compiler and (on Bazzite) a portable Python in parallel, build the "
            "network with HelixSR's own setup and import the result as the payload. The DLSS DLL is used once and "
            "deleted; the network files it produces are NVIDIA's property and stay on this PC."))

        updates = QGroupBox("Releases")
        form = QFormLayout(updates)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.helix_pill = StatusPill("Not checked")
        self.helix_text = QLabel()
        self.helix_text.setWordWrap(True)
        self.helix_text.setOpenExternalLinks(True)
        row = QHBoxLayout()
        row.addWidget(self.helix_pill)
        row.addWidget(self.helix_text, 1)
        form.addRow("HelixSR", row)
        buttons = QHBoxLayout()
        self.check = QPushButton("Check now")
        self.check.setToolTip("Ask GitHub for the latest HelixSR release")
        self.check.clicked.connect(self.check_requested)
        buttons.addWidget(self.check)
        self.auto_check = QCheckBox("Check at start")
        self.auto_check.setToolTip("Look up the latest HelixSR release every time the app starts (one small request)")
        self.auto_check.toggled.connect(self.auto_check_changed)
        buttons.addWidget(self.auto_check)
        buttons.addStretch(1)
        form.addRow("", buttons)
        layout.addWidget(updates)

        box = QGroupBox("Get HelixSR and build the network files")
        vbox = QVBoxLayout(box)
        choice = QHBoxLayout()
        choice.addWidget(QLabel("Version:"))
        self.version = QComboBox()
        self.version.addItem("Latest release", False)
        self.version.addItem("{0} (fallback)".format(FALLBACK_VERSION), True)
        self.version.setToolTip(("HelixSR's developer recommends {0} when the latest release does not work for you. "
                                 "Switching builds the network files again; deploy again per game afterwards.")
                                .format(FALLBACK_VERSION))
        self.version.currentIndexChanged.connect(lambda _: self.fallback_changed.emit(self.fallback()))
        choice.addWidget(self.version)
        choice.addStretch(1)
        vbox.addLayout(choice)
        dlss = QHBoxLayout()
        self.use_local = QCheckBox("Use a {0} already on this PC:".format(DLSS_DLL))
        self.use_local.setToolTip(("Skips the 59 MB download from NVIDIA's GitHub. Only DLSS 310.7.0 (the exact "
                                   "build HelixSR pins) is accepted; Find looks through the Steam libraries for one."))
        self.use_local.toggled.connect(self._update_buttons)
        dlss.addWidget(self.use_local)
        self.dlss_path = QLineEdit()
        self.dlss_path.setPlaceholderText("…/steamapps/common/<game>/nvngx_dlss.dll")
        self.dlss_path.textChanged.connect(self._update_buttons)
        dlss.addWidget(self.dlss_path, 1)
        self.browse_dlss = QPushButton("Browse…")
        self.browse_dlss.clicked.connect(self.browse_dlss_requested)
        dlss.addWidget(self.browse_dlss)
        self.find_dlss = QPushButton("Find in Steam")
        self.find_dlss.setToolTip("Scan the Steam libraries for a DLSS 310.7.0 DLL (checks each file's checksum)")
        self.find_dlss.clicked.connect(self.find_dlss_requested)
        dlss.addWidget(self.find_dlss)
        vbox.addLayout(dlss)

        actions = QHBoxLayout()
        self.start = accent_button("Download and build", ("Download the latest release and everything the setup "
                                                          "needs, build the network and import the result"))
        self.start.clicked.connect(self._start_clicked)
        actions.addWidget(self.start)
        self.cancel = QPushButton("Cancel")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.cancel_requested)
        actions.addWidget(self.cancel)
        self.import_built = QPushButton("Import built release")
        self.import_built.setToolTip("Import the network files built in the work folder into the payload")
        self.import_built.setEnabled(False)
        self.import_built.clicked.connect(lambda: self.built and self.import_requested.emit(self.built))
        actions.addWidget(self.import_built)
        self.open_work = QPushButton("Open work folder")
        self.open_work.clicked.connect(self.open_work_requested)
        actions.addWidget(self.open_work)
        actions.addStretch(1)
        vbox.addLayout(actions)

        self.stage = QLabel("Idle")
        self.stage.setStyleSheet("font-weight:600;")
        vbox.addWidget(self.stage)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("")
        vbox.addWidget(self.progress)
        self.terminal = Terminal()
        self.terminal.setMinimumHeight(220)
        self.terminal.setToolTip("Output of the downloads and of HelixSR's setup")
        vbox.addWidget(self.terminal, 1)
        layout.addWidget(box, 1)
        self._lines: list[str] = []
        self._progress: dict[str, tuple[int, int]] = {}
        # While a job runs, the stage line also shows the time since it started: the build alone takes minutes.
        self._stage_text = self.stage.text()
        self._elapsed = QElapsedTimer()
        self._clock = QTimer(self, interval=1000)
        self._clock.timeout.connect(self._show_stage)
        self._update_buttons()

    # ------------------------------------------------------------ releases
    def show_updates(self, statuses: dict[str, UpdateStatus]) -> None:
        helix = statuses.get("helixsr")
        if helix:
            self.release = helix.latest if helix.latest.version else None
            self.helix_pill.set_status(self._pill_text(helix), helix.kind)
            text = helix.summary
            if helix.latest.asset_url:
                text += ' — <a href="{url}">{name}</a> ({size})'.format(
                    url=helix.latest.url, name=helix.latest.asset_name, size=_size(helix.latest.asset_size))
            self.helix_text.setText(text)
        self._update_buttons()

    @staticmethod
    def _pill_text(status: UpdateStatus) -> str:
        if status.latest.error or not status.latest.version:
            return "Unknown"
        if not status.installed:
            return f"v{status.latest.version}"
        return ("Update" if status.update_available
                else "Up to date")

    def set_checking(self, on: bool) -> None:
        self._checking = on
        self._update_buttons()
        if on:
            self.helix_pill.set_status("Checking…", "neutral")

    def set_auto_check(self, on: bool) -> None:
        self.auto_check.blockSignals(True)
        self.auto_check.setChecked(on)
        self.auto_check.blockSignals(False)

    # ------------------------------------------------------------ run
    def fallback(self) -> bool:
        return bool(self.version.currentData())

    def set_fallback(self, on: bool) -> None:
        self.version.blockSignals(True)
        self.version.setCurrentIndex(1 if on else 0)
        self.version.blockSignals(False)

    def dlss_file(self) -> Path | None:
        text = self.dlss_path.text().strip()
        return Path(text).expanduser() if self.use_local.isChecked() and text else None

    def set_dlss_candidates(self, paths: list[Path]) -> None:
        self.find_dlss.setEnabled(True)
        if paths:
            self.dlss_path.setText(str(paths[0]))
            self.use_local.setChecked(True)
            self.dlss_path.setToolTip(plain_tooltip("\n".join(str(p) for p in paths)))
            self.append("Found {0} matching {1}: {2}".format(len(paths), DLSS_DLL, ", ".join(str(p) for p in paths)))
        else:
            self.append("No DLSS 310.7.0 {0} found in the Steam libraries; it will be downloaded.".format(DLSS_DLL))

    def set_running(self, on: bool) -> None:
        self._running = on
        self.cancel.setEnabled(on)
        if on:
            self._lines.clear()
            self._progress.clear()
            self.terminal.clear()
            self.progress.setRange(0, 0)
            self.progress.setFormat("")
            self.built = None
            self._elapsed.start()
            self._clock.start()
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(1 if self.built else 0)
            self._clock.stop()
            if self._elapsed.isValid():         # keep how long the job took on the stage line
                seconds = self._elapsed.elapsed() // 1000
                self.stage.setText("{0} \u2014 took {1}:{2:02d}".format(self._stage_text, seconds // 60, seconds % 60))
        self._update_buttons()

    def set_stage(self, text: str) -> None:
        self._stage_text = text
        self._show_stage()
        self.append(f"== {text}")

    def _show_stage(self) -> None:
        if self._clock.isActive() and self._elapsed.isValid():
            seconds = self._elapsed.elapsed() // 1000
            self.stage.setText("{0} \u2014 {1}:{2:02d} elapsed".format(self._stage_text, seconds // 60, seconds % 60))
        else:
            self.stage.setText(self._stage_text)

    def set_progress(self, name: str, done: int, total: int) -> None:
        self._progress[name] = (done, total)
        done_all = sum(d for d, _ in self._progress.values())
        total_all = sum(t for _, t in self._progress.values())
        unknown = any(t == 0 for _, t in self._progress.values())
        if unknown or not total_all:
            self.progress.setRange(0, 0)
            self.progress.setFormat(f"{_size(done_all)}")
        else:
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(1000 * done_all / total_all))
            self.progress.setFormat("{done} / {total}  (%p%)".format(done=_size(done_all), total=_size(total_all)))
        active = [f"{n} {_size(d)}" + (f"/{_size(t)}" if t else "") for n, (d, t) in self._progress.items() if d < t or not t]
        if active:
            self._stage_text = "Downloading: {0}".format(", ".join(active))
            self._show_stage()

    def append(self, line: str) -> None:
        self._lines.append(line)
        if len(self._lines) > 4000:
            del self._lines[:1000]
        self.terminal.set_text("\n".join(self._lines))

    def set_built(self, release_dir: Path | None) -> None:
        self.built = release_dir
        self._update_buttons()

    def _start_clicked(self) -> None:
        self.start_requested.emit(self.dlss_file())

    def _update_buttons(self) -> None:
        local = self.use_local.isChecked()
        self.version.setEnabled(not self._running)
        self.dlss_path.setEnabled(local and not self._running)
        self.browse_dlss.setEnabled(local and not self._running)
        self.find_dlss.setEnabled(local and not self._running)
        path_ok = not local or bool(self.dlss_path.text().strip())
        self.start.setEnabled(not self._running and path_ok)
        self.import_built.setEnabled(not self._running and self.built is not None)
        self.check.setEnabled(not self._running and not self._checking)
