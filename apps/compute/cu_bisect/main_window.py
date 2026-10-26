# SPDX-License-Identifier: GPL-3.0-or-later

"""Single window: a menu-driven "initial setup" screen for bc250-cu-bisect.sh. Pick the options,
hit Start, and the GUI hands off to a terminal running the real script and gets out of the way."""

from __future__ import annotations

import shlex

from PyQt6.QtCore import QByteArray, QSettings, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from . import APP_NAME, LOGO_PATH, __version__
from .options import BASELINE_PRESETS, MASK_RE, BisectOptions
from .terminal import launch_in_terminal
from .widgets import AboutDialog, HelpDialog

_CUSTOM_LABEL = "Custom..."


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
        self._on_baseline_changed(self.baseline_combo.currentText())

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
        sub = QLabel(("Choose how you want to run bc250-cu-bisect.sh, then click Start. This window closes "
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
        self.time_spin.setRange(60, 36000)
        self.time_spin.setSingleStep(30)
        self.time_spin.setValue(180)
        self.time_spin.setToolTip("GPU load per attempt (-t). Minimum 60s, default 180s.")
        grid.addWidget(self.time_spin, row, 1)
        row += 1

        grid.addWidget(QLabel("Rounds per item:"), row, 0)
        self.rounds_spin = QSpinBox()
        self.rounds_spin.setRange(2, 9)
        self.rounds_spin.setValue(3)
        self.rounds_spin.setToolTip(("Attempts per item (-r), interleaved so heat/time-of-day don't favor one item. "
                                     "Minimum 2 (control-only runs may use 1)."))
        grid.addWidget(self.rounds_spin, row, 1)
        row += 1

        grid.addWidget(QLabel("Baseline:"), row, 0)
        self.baseline_combo = QComboBox()
        self.baseline_combo.addItems(list(BASELINE_PRESETS.keys()))
        self.baseline_combo.setToolTip(
            "The masks every attempt starts from (--baseline). Auto-detect uses this boot's own "
            "clean masks - the safest default.")
        self.baseline_combo.currentTextChanged.connect(self._on_baseline_changed)
        grid.addWidget(self.baseline_combo, row, 1)
        self.baseline_custom = QLineEdit()
        self.baseline_custom.setPlaceholderText("0x0f,0x0f,0x0f,0x0f")
        self.baseline_custom.textChanged.connect(self._validate_custom_baseline)
        grid.addWidget(self.baseline_custom, row, 2)
        row += 1

        self.control_only_check = QCheckBox("Control only (re-validate, skip per-WGP bisect)")
        self.control_only_check.setToolTip(
            "--control-only: only run the control item. For re-validating a combined mask you "
            "already bisected, without re-testing already-known-bad WGPs. Allows a single round.")
        self.control_only_check.toggled.connect(self._on_control_only_toggled)
        grid.addWidget(self.control_only_check, row, 0, 1, 3)
        row += 1

        self.same_boot_check = QCheckBox("Same boot (don't reboot between attempts)")
        self.same_boot_check.setToolTip(
            "--same-boot: faster, but every attempt then inherits the previous one's state.")
        grid.addWidget(self.same_boot_check, row, 0, 1, 3)
        row += 1

        self.auto_check = QCheckBox("Unattended (no prompts, auto-reboot, resumes after login)")
        self.auto_check.setToolTip(
            "--auto: don't ask anything, reboot on its own, and keep going after every login until "
            "every item is done. Needs passwordless sudo for umr/journalctl - see the manual.")
        self.auto_check.toggled.connect(self._on_auto_toggled)
        grid.addWidget(self.auto_check, row, 0, 1, 3)
        row += 1

        self.autostart_check = QCheckBox("Also install the auto-resume login service (recommended with Unattended)")
        self.autostart_check.setToolTip(
            "Writes and enables ~/.config/systemd/user/bc250-cu-bisect-auto.service, so the run "
            "relaunches itself after every reboot/login, same as the manual's --auto checklist.")
        self.autostart_check.setEnabled(False)
        grid.addWidget(self.autostart_check, row, 0, 1, 3)
        row += 1

        self.no_watch_check = QCheckBox("Disable live register watch (--no-watch)")
        self.no_watch_check.setToolTip("Don't read the registers back during the load.")
        grid.addWidget(self.no_watch_check, row, 0, 1, 3)
        row += 1

        grid.setColumnStretch(2, 1)
        return frame

    def _build_buttons(self) -> QHBoxLayout:
        buttons = QHBoxLayout()
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setToolTip(("--reset: permanently deletes all saved results and logs in "
                                   "~/.local/share/bc250-cu-bisect, so the next run starts from scratch."))
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
        self.start_btn = QPushButton("Start CU Bisect")
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
        self.resize(560, 420)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        QSettings().setValue("main_window/geometry", self.saveGeometry())
        super().closeEvent(event)

    # ------------------------------------------------------------- behavior
    def _on_baseline_changed(self, label: str) -> None:
        is_custom = label == _CUSTOM_LABEL
        self.baseline_custom.setVisible(is_custom)
        if not is_custom:
            self.baseline_custom.clear()
            self.baseline_custom.setStyleSheet("")

    def _validate_custom_baseline(self, text: str) -> None:
        text = text.strip()
        ok = not text or bool(MASK_RE.match(text))
        self.baseline_custom.setStyleSheet("" if ok else "border:1px solid #c62828;")

    def _on_auto_toggled(self, checked: bool) -> None:
        self.autostart_check.setEnabled(checked)
        if checked:
            self.autostart_check.setChecked(True)

    def _on_control_only_toggled(self, checked: bool) -> None:
        # Rounds must be >=2 normally; a single confirmation round is only allowed for
        # control-only re-validation runs.
        self.rounds_spin.setMinimum(1 if checked else 2)

    def _resolved_baseline(self) -> str:
        label = self.baseline_combo.currentText()
        if label == _CUSTOM_LABEL:
            return self.baseline_custom.text().strip()
        return BASELINE_PRESETS.get(label) or ""

    def _collect_options(self) -> BisectOptions:
        return BisectOptions(
            time_secs=self.time_spin.value(),
            rounds=self.rounds_spin.value(),
            baseline=self._resolved_baseline(),
            control_only=self.control_only_check.isChecked(),
            same_boot=self.same_boot_check.isChecked(),
            unattended=self.auto_check.isChecked(),
            no_watch=self.no_watch_check.isChecked(),
        )

    def _on_status(self) -> None:
        try:
            launch_in_terminal(shlex.join(["bash", self.script, "--status"]))
        except RuntimeError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))

    def _on_reset(self) -> None:
        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Icon.Warning)
        confirm.setWindowTitle(APP_NAME)
        confirm.setText("Delete all bc250-cu-bisect results?")
        confirm.setInformativeText(("This permanently deletes every saved result and log in "
                                    "~/.local/share/bc250-cu-bisect (--reset). This cannot be undone and there is no "
                                    "backup. The script will still ask you to confirm once more in the terminal."))
        confirm.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        confirm.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if confirm.exec() != QMessageBox.StandardButton.Yes:
            return
        try:
            launch_in_terminal(shlex.join(["bash", self.script, "--reset"]))
        except RuntimeError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))

    def _on_start(self) -> None:
        opts = self._collect_options()
        errors = opts.validate()
        if errors:
            QMessageBox.warning(self, APP_NAME, "\n".join(errors))
            return

        summary = (
            "Start bc250-cu-bisect.sh with:\n\n"
            "  load time: {t}s\n  rounds: {r}\n  baseline: {b}\n"
            "  control-only: {co}\n  same-boot: {sb}\n  unattended: {au}\n  no-watch: {nw}\n\n"
            "This window will close and the run continues in a terminal."
        ).format(t=opts.time_secs, r=opts.rounds, b=opts.baseline or "auto-detect",
                  co=opts.control_only, sb=opts.same_boot, au=opts.unattended, nw=opts.no_watch)
        if QMessageBox.question(self, APP_NAME, summary) != QMessageBox.StandardButton.Yes:
            return

        if opts.unattended and self.autostart_check.isChecked():
            from . import service
            try:
                service.install(self.script, opts.time_secs, opts.rounds)
            except Exception as exc:  # noqa: BLE001 - surfaced to the user, not fatal to starting
                QMessageBox.warning(self, APP_NAME, (
                    "Could not install the auto-resume login service:\n{0}\n\n"
                    "The run will still start now; see the manual's --auto checklist to set it up "
                    "by hand.").format(exc))

        try:
            launch_in_terminal(opts.to_command(self.script))
        except RuntimeError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return

        self.close()
