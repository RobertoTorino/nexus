# SPDX-License-Identifier: GPL-3.0-or-later

"""Single window: a menu-driven "initial setup" screen for bc250-cores-bisect.sh. Pick the options,
hit Start, and the GUI hands off to a terminal running the real script and gets out of the way."""

from __future__ import annotations

import shlex

from PyQt6.QtCore import QByteArray, QSettings, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from . import APP_NAME, LOGO_PATH, __version__
from .options import (
    DEFAULT_LOAD_TOOL, DEFAULT_ROUNDS, DEFAULT_TIME_SECS, LOAD_TOOLS, MAX_ROUNDS, MIN_ROUNDS,
    MIN_TIME_SECS, BisectOptions,
)
from .terminal import launch_in_terminal
from .widgets import AboutDialog, HelpDialog

# control + post-control + one item per new core + combined, on a standard 0x77 board.
_TYPICAL_ITEMS = 5
# Rough warm-reboot + desktop-settle cost of one attempt when not running --same-boot.
_REBOOT_OVERHEAD_SECS = 120


class MainWindow(QWidget):
    def __init__(self, script: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.script = script
        self.setWindowTitle(f"{APP_NAME} {__version__}")

        root = QVBoxLayout(self)
        root.addLayout(self._build_header())
        root.addWidget(self._build_options_frame())
        root.addLayout(self._build_buttons())

        self.hint_label = QLabel()
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color:#888; font-style:italic;")
        root.addWidget(self.hint_label)
        root.addStretch(1)

        self._restore_geometry()
        self._update_hint()

    # ------------------------------------------------------------------ UI
    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(14)
        if LOGO_PATH.is_file():
            logo = QLabel()
            logo.setPixmap(QPixmap(str(LOGO_PATH)).scaled(
                96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            header.addWidget(logo)
        header_right = QVBoxLayout()
        header_right.setSpacing(6)
        title_row = QHBoxLayout()
        title = QLabel(f"{APP_NAME}  <span style='color:#9aa0a6; font-size:14px;'>v{__version__}</span>")
        title.setStyleSheet("font-size:24px; font-weight:800;")
        title_row.addWidget(title)
        title_row.addStretch(1)
        help_btn = QPushButton("Help")
        help_btn.setFlat(True)
        help_btn.clicked.connect(lambda: HelpDialog(self.script, self).exec())
        title_row.addWidget(help_btn)
        about_btn = QPushButton("About")
        about_btn.setFlat(True)
        about_btn.clicked.connect(lambda: AboutDialog(self).exec())
        title_row.addWidget(about_btn)
        header_right.addLayout(title_row)
        sub = QLabel(("Choose how you want to run bc250-cores-bisect.sh, then click Start. This window closes "
                      "and the real run continues in a terminal, exactly like running the script by hand."))
        sub.setWordWrap(True)
        header_right.addWidget(sub)
        header.addLayout(header_right, 1)
        return header

    def _build_options_frame(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        grid = QGridLayout(frame)
        row = 0

        grid.addWidget(QLabel("Load per attempt (seconds):"), row, 0)
        self.time_spin = QSpinBox()
        self.time_spin.setRange(MIN_TIME_SECS, 36000)
        self.time_spin.setSingleStep(60)
        self.time_spin.setValue(DEFAULT_TIME_SECS)
        self.time_spin.setToolTip(
            "CPU load per attempt (-t). Minimum {0}s, default {1}s.".format(MIN_TIME_SECS, DEFAULT_TIME_SECS))
        self.time_spin.valueChanged.connect(self._update_hint)
        grid.addWidget(self.time_spin, row, 1)
        row += 1

        grid.addWidget(QLabel("Rounds per item:"), row, 0)
        self.rounds_spin = QSpinBox()
        self.rounds_spin.setRange(MIN_ROUNDS, MAX_ROUNDS)
        self.rounds_spin.setValue(DEFAULT_ROUNDS)
        self.rounds_spin.setToolTip(("Attempts per item (-r), interleaved so heat/time-of-day don't favor one item. "
                                     "A single round cannot tell a genuinely bad core from a random failure."))
        self.rounds_spin.valueChanged.connect(self._update_hint)
        grid.addWidget(self.rounds_spin, row, 1)
        row += 1

        grid.addWidget(QLabel("Load tool:"), row, 0)
        self.load_combo = QComboBox()
        # the data is the literal --load value, the label is what the menu shows
        for tool, label in (
            ("stress-ng", "stress-ng --verify (default)"),
            ("mprime", "mprime torture test"),
            ("both", "both (stress-ng, then mprime)"),
        ):
            self.load_combo.addItem(label, tool)
        self.load_combo.setCurrentIndex(LOAD_TOOLS.index(DEFAULT_LOAD_TOOL))
        self.load_combo.setToolTip(
            "--load: stress-ng verifies its own results and is always available. mprime's torture "
            "test is a much heavier AVX/FMA load that also checks every result, so it catches "
            "silent miscalculation stress-ng misses - but it has to be installed separately. "
            "'both' runs them one after the other, so an attempt takes twice the load time.")
        self.load_combo.currentIndexChanged.connect(self._update_hint)
        grid.addWidget(self.load_combo, row, 1)
        row += 1

        self.ras_check = QCheckBox("Also count hardware errors with rasdaemon")
        self.ras_check.setToolTip(
            "--rasdaemon: read ras-mc-ctl's error database before and after every attempt. "
            "rasdaemon stores errors persistently, so they are still counted when the journal is "
            "volatile or the attempt ends in a crash. Needs the rasdaemon service running.")
        grid.addWidget(self.ras_check, row, 0, 1, 3)
        row += 1

        self.same_boot_check = QCheckBox("Same boot (don't reboot between attempts)")
        self.same_boot_check.setToolTip(
            "--same-boot: much faster, but every attempt then inherits the previous one's state, "
            "so a failure is harder to pin on one core.")
        self.same_boot_check.toggled.connect(self._update_hint)
        grid.addWidget(self.same_boot_check, row, 0, 1, 3)
        row += 1

        self.auto_check = QCheckBox("Unattended (no prompts, auto-reboot, resumes after login)")
        self.auto_check.setToolTip(
            "--auto: don't ask anything, reboot on its own, and keep going after every login until "
            "every item is done. Needs passwordless sudo for setpci and journalctl - see the manual.")
        self.auto_check.toggled.connect(self._on_auto_toggled)
        grid.addWidget(self.auto_check, row, 0, 1, 3)
        row += 1

        self.autostart_check = QCheckBox("Also install the auto-resume login service (recommended with Unattended)")
        self.autostart_check.setToolTip(
            "Writes and enables ~/.config/systemd/user/bc250-cores-bisect-auto.service, so the run "
            "relaunches itself after every reboot/login, same as the manual's --auto checklist. "
            "The script removes it again once every item is done.")
        self.autostart_check.setEnabled(False)
        grid.addWidget(self.autostart_check, row, 0, 1, 3)
        row += 1

        grid.setColumnStretch(2, 1)
        return frame

    def _build_buttons(self) -> QHBoxLayout:
        buttons = QHBoxLayout()
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setToolTip(("--reset: permanently deletes all saved results and logs in "
                                   "~/.local/share/bc250-cores-bisect, so the next run starts from scratch."))
        self.reset_btn.setStyleSheet(
            "QPushButton { background:#c62828; color:white; font-weight:600; "
            "padding:6px 14px; border-radius:4px; }"
            "QPushButton:hover { background:#b71c1c; }"
        )
        self.reset_btn.clicked.connect(self._on_reset)
        buttons.addWidget(self.reset_btn)
        self.status_btn = QPushButton("Show status (--status)")
        self.status_btn.setToolTip("Show the results so far and write the report, then exit.")
        self.status_btn.clicked.connect(self._on_status)
        buttons.addWidget(self.status_btn)
        buttons.addStretch(1)
        self.start_btn = QPushButton("Start Cores Bisect")
        self.start_btn.setDefault(True)
        self.start_btn.setStyleSheet("font-weight:700; padding:6px 18px;")
        self.start_btn.clicked.connect(self._on_start)
        buttons.addWidget(self.start_btn)
        return buttons

    # --------------------------------------------------------------- window
    def _restore_geometry(self) -> None:
        settings = QSettings()
        geometry = settings.value("main_window/geometry")
        if isinstance(geometry, QByteArray) and self.restoreGeometry(geometry):
            return
        self.resize(560, 380)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        QSettings().setValue("main_window/geometry", self.saveGeometry())
        super().closeEvent(event)

    # ------------------------------------------------------------- behavior
    def _on_auto_toggled(self, checked: bool) -> None:
        self.autostart_check.setEnabled(checked)
        self.autostart_check.setChecked(checked)

    def _update_hint(self) -> None:
        per_attempt = self.time_spin.value()
        if self._load_tool() == "both":
            per_attempt *= 2  # stress-ng and mprime each get the full load time, back to back
        if not self.same_boot_check.isChecked():
            per_attempt += _REBOOT_OVERHEAD_SECS
        total_hours = _TYPICAL_ITEMS * self.rounds_spin.value() * per_attempt / 3600
        self.hint_label.setText(("Rough estimate: ~{0:.1f} h for a typical board ({1} items x {2} rounds){3}. "
                                 "The run is resumable - results are saved after every attempt.").format(
            total_hours, _TYPICAL_ITEMS, self.rounds_spin.value(),
            "" if self.same_boot_check.isChecked() else ", reboots included",
        ))

    def _load_tool(self) -> str:
        return self.load_combo.currentData() or DEFAULT_LOAD_TOOL

    def _collect_options(self) -> BisectOptions:
        return BisectOptions(
            time_secs=self.time_spin.value(),
            rounds=self.rounds_spin.value(),
            same_boot=self.same_boot_check.isChecked(),
            unattended=self.auto_check.isChecked(),
            load_tool=self._load_tool(),
            rasdaemon=self.ras_check.isChecked(),
        )

    def _run_script(self, *args: str) -> bool:
        try:
            launch_in_terminal(shlex.join(["bash", self.script, *args]))
        except RuntimeError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return False
        return True

    def _on_status(self) -> None:
        self._run_script("--status")

    def _on_reset(self) -> None:
        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Icon.Warning)
        confirm.setWindowTitle(APP_NAME)
        confirm.setText("Delete all bc250-cores-bisect results?")
        confirm.setInformativeText(
            "This permanently deletes every saved result and log in "
            "~/.local/share/bc250-cores-bisect (--reset). This cannot be undone and there is no "
            "backup. The script will still ask you to confirm once more in the terminal.")
        confirm.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        confirm.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if confirm.exec() != QMessageBox.StandardButton.Yes:
            return
        self._run_script("--reset")

    def _on_start(self) -> None:
        opts = self._collect_options()
        errors = opts.validate()
        if errors:
            QMessageBox.warning(self, APP_NAME, "\n".join(errors))
            return

        summary = (
            "Start bc250-cores-bisect.sh with:\n\n"
            "  load time: {t}s\n  rounds: {r}\n  load tool: {lt}\n  rasdaemon: {ras}\n"
            "  same-boot: {sb}\n  unattended: {au}\n\n"
            "This window will close and the run continues in a terminal."
        ).format(t=opts.time_secs, r=opts.rounds, lt=opts.load_tool, ras=opts.rasdaemon,
                 sb=opts.same_boot, au=opts.unattended)
        if QMessageBox.question(self, APP_NAME, summary) != QMessageBox.StandardButton.Yes:
            return

        if opts.unattended and self.autostart_check.isChecked():
            from . import service
            try:
                service.install(self.script, opts)
            except Exception as exc:  # noqa: BLE001 - surfaced to the user, not fatal to starting
                QMessageBox.warning(self, APP_NAME, (
                    "Could not install the auto-resume login service:\n{0}\n\n"
                    "The run will still start now; see the manual's --auto checklist to set it up "
                    "by hand.").format(exc))

        if not self._run_script(*opts.to_args()):
            return
        self.close()
