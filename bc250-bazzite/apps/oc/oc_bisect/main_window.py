# SPDX-License-Identifier: GPL-3.0-or-later

"""Single window: a menu-driven "initial setup" screen for bc250-gpu-oc-bisect.sh. Pick the
options, hit Start, and the GUI hands off to a terminal running the real script and gets out of
the way. The header is the suite's (owner, 26-10-2026): the icon, the title with the version, and under it four
status boxes that sum up the sweep as the options stand (the load per attempt, the rounds per step, the overclock
and the undervolt sweep) with Help and About as pills beside them, as the core apps' header has its actions; what
the window does is a muted note below."""

from __future__ import annotations

import shlex

from PyQt6.QtCore import QByteArray, QSettings, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from . import APP_NAME, LOGO_PATH, __version__
from .options import (
    DEFAULT_FREQ_STEP, DEFAULT_MAX_FREQ, DEFAULT_MIN_VOLT, DEFAULT_VOLT_STEP,
    HARD_MAX_FREQ, HARD_MAX_VOLT, HARD_MIN_VOLT, SweepOptions,
)
from .terminal import launch_in_terminal
from .theme import BLUE, header_font, muted
from .widgets import AboutDialog, HelpDialog, MetricBox, Pill, same_width


class MainWindow(QWidget):
    def __init__(self, script: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.script = script
        self.setWindowTitle(f"{APP_NAME} {__version__}")

        root = QVBoxLayout(self)
        root.addLayout(self._build_header())
        note = QLabel("Choose how you want to run bc250-gpu-oc-bisect.sh, then click Start. This window closes and "
                      "the real sweep continues in a terminal, exactly like running the script by hand. An unstable "
                      "step can freeze the system - save your work first.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{muted()};")
        root.addWidget(note)
        root.addWidget(self._build_options_frame())
        root.addLayout(self._build_buttons())
        root.addStretch(1)

        self._restore_geometry()
        self._on_sweep_toggled()

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
        title = QLabel(f"{APP_NAME}  <span style='color:{muted()}; font-size:14px;'>v{__version__}</span>")
        title.setStyleSheet(header_font() + "font-size:24px; font-weight:800;")
        title_row.addWidget(title)
        title_row.addStretch(1)
        header_right.addLayout(title_row)
        boxes = QHBoxLayout()                          # the sweep as the options stand, kept up to date
        boxes.setSpacing(8)
        self.load_box = MetricBox("Load per attempt", BLUE)
        self.rounds_box = MetricBox("Rounds per step", BLUE)
        self.oc_box = MetricBox("Overclock sweep", BLUE)
        self.uv_box = MetricBox("Undervolt sweep", BLUE)
        # Help and About are pills beside the boxes (owner, 26-10-2026), as the core apps' header has its actions.
        self.help_pill = Pill("Help", "The script's options", "Shows the help of bc250-gpu-oc-bisect.sh.")
        self.help_pill.clicked.connect(lambda: HelpDialog(self.script, self).exec())
        self.about_pill = Pill("About", "Version and license", "The version, the license and the repository.")
        self.about_pill.clicked.connect(lambda: AboutDialog(self).exec())
        row = [self.load_box, self.rounds_box, self.oc_box, self.uv_box, self.help_pill, self.about_pill]
        for box in row:
            boxes.addWidget(box)
        same_width(row)                                # as wide as the widest, never narrower than their text
        boxes.addStretch(1)
        header_right.addLayout(boxes)
        header.addLayout(header_right, 1)
        return header

    def _show_summary(self) -> None:
        """The status boxes: the sweep the Start button would run."""
        self.load_box.set_value(f"{self.time_spin.value()} s", "GPU load per attempt (-t).")
        self.rounds_box.set_value(str(self.rounds_spin.value()), "Attempts per step (-r).")
        if self.oc_check.isChecked():
            volt = self.oc_volt_spin.value()
            self.oc_box.set_value(f"to {self.max_freq_spin.value()} MHz",
                                  f"--oc: up in steps of {self.freq_step_spin.value()} MHz, at "
                                  f"{f'{volt} mV' if volt else 'the config\'s top voltage'}.")
        else:
            self.oc_box.set_value("Off", "No overclock sweep.")
        if self.uv_check.isChecked():
            self.uv_box.set_value(f"to {self.min_volt_spin.value()} mV",
                                  f"--uv: down in steps of {self.volt_step_spin.value()} mV.")
        else:
            self.uv_box.set_value("Off", "No undervolt sweep.")

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

        grid.addWidget(QLabel("Rounds per step:"), row, 0)
        self.rounds_spin = QSpinBox()
        self.rounds_spin.setRange(2, 9)
        self.rounds_spin.setValue(3)
        self.rounds_spin.setToolTip(
            "Attempts per step (-r). All rounds of a step finish before the next step is tried, "
            "so the sweep never drives past a step that is still failing. Minimum 2.")
        grid.addWidget(self.rounds_spin, row, 1)
        row += 1

        self.oc_check = QCheckBox("Overclock sweep (raise frequency, more performance)")
        self.oc_check.setChecked(True)
        self.oc_check.setToolTip("--oc: raise the top frequency one step at a time at a fixed voltage.")
        self.oc_check.toggled.connect(self._on_sweep_toggled)
        grid.addWidget(self.oc_check, row, 0, 1, 2)
        row += 1

        grid.addWidget(QLabel("    Max frequency (MHz):"), row, 0)
        self.max_freq_spin = QSpinBox()
        self.max_freq_spin.setRange(100, HARD_MAX_FREQ)
        self.max_freq_spin.setSingleStep(50)
        self.max_freq_spin.setValue(DEFAULT_MAX_FREQ)
        self.max_freq_spin.setToolTip(
            "--max-freq: highest frequency to try. Hard ceiling {0} MHz; the community record of "
            "hard-locks above ~1850-2000 MHz is the reason.".format(HARD_MAX_FREQ))
        grid.addWidget(self.max_freq_spin, row, 1)
        row += 1

        grid.addWidget(QLabel("    Frequency step (MHz):"), row, 0)
        self.freq_step_spin = QSpinBox()
        self.freq_step_spin.setRange(25, 500)
        self.freq_step_spin.setSingleStep(25)
        self.freq_step_spin.setValue(DEFAULT_FREQ_STEP)
        self.freq_step_spin.setToolTip("--freq-step: OC ladder step. Minimum 25 MHz.")
        grid.addWidget(self.freq_step_spin, row, 1)
        row += 1

        grid.addWidget(QLabel("    OC voltage (mV, 0 = config's top voltage):"), row, 0)
        self.oc_volt_spin = QSpinBox()
        self.oc_volt_spin.setRange(0, HARD_MAX_VOLT)
        self.oc_volt_spin.setSingleStep(25)
        self.oc_volt_spin.setValue(0)
        self.oc_volt_spin.setSpecialValueText("config default")
        self.oc_volt_spin.setToolTip(
            "--oc-volt: voltage used for the OC ladder. Hard ceiling {0} mV - one board was "
            "bricked by overvolting; leave at the default unless you know why not.".format(HARD_MAX_VOLT))
        grid.addWidget(self.oc_volt_spin, row, 1)
        row += 1

        self.uv_check = QCheckBox("Undervolt sweep (lower voltage, less heat and power)")
        self.uv_check.setChecked(True)
        self.uv_check.setToolTip("--uv: lower the top voltage one step at a time at the stock top frequency.")
        self.uv_check.toggled.connect(self._on_sweep_toggled)
        grid.addWidget(self.uv_check, row, 0, 1, 2)
        row += 1

        grid.addWidget(QLabel("    Min voltage (mV):"), row, 0)
        self.min_volt_spin = QSpinBox()
        self.min_volt_spin.setRange(HARD_MIN_VOLT, 1100)
        self.min_volt_spin.setSingleStep(25)
        self.min_volt_spin.setValue(DEFAULT_MIN_VOLT)
        self.min_volt_spin.setToolTip("--min-volt: lowest voltage to try. Hard floor {0} mV.".format(HARD_MIN_VOLT))
        grid.addWidget(self.min_volt_spin, row, 1)
        row += 1

        grid.addWidget(QLabel("    Voltage step (mV):"), row, 0)
        self.volt_step_spin = QSpinBox()
        self.volt_step_spin.setRange(5, 100)
        self.volt_step_spin.setSingleStep(5)
        self.volt_step_spin.setValue(DEFAULT_VOLT_STEP)
        self.volt_step_spin.setToolTip("--volt-step: UV ladder step. Minimum 5 mV.")
        grid.addWidget(self.volt_step_spin, row, 1)
        row += 1

        self.per_boot_check = QCheckBox("One attempt per boot (strict isolation, slower)")
        self.per_boot_check.setToolTip(
            "--per-boot: reboot between attempts. Default is same boot with a cooldown; the "
            "governor restart resets its state.")
        grid.addWidget(self.per_boot_check, row, 0, 1, 2)
        row += 1

        grid.setColumnStretch(1, 1)
        for spin in (self.time_spin, self.rounds_spin, self.max_freq_spin, self.freq_step_spin, self.oc_volt_spin,
                     self.min_volt_spin, self.volt_step_spin):
            spin.valueChanged.connect(lambda _value: self._show_summary())
        return frame

    def _build_buttons(self) -> QHBoxLayout:
        buttons = QHBoxLayout()
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setToolTip(("--reset: permanently deletes all saved results and logs in "
                                   "~/.local/share/bc250-gpu-oc-bisect, so the next run starts from scratch."))
        self.reset_btn.setStyleSheet(
            "QPushButton { background:#c62828; color:white; font-weight:600; "
            "padding:6px 14px; border-radius:4px; }"
            "QPushButton:hover { background:#b71c1c; }"
        )
        self.reset_btn.clicked.connect(self._on_reset)
        buttons.addWidget(self.reset_btn)
        self.status_btn = QPushButton("Show status (--status)")
        self.status_btn.setToolTip("Show the results so far and write the report, then exit.")
        self.status_btn.clicked.connect(lambda: self._run_simple("--status"))
        buttons.addWidget(self.status_btn)
        self.install_btn = QPushButton("Install result")
        self.install_btn.setToolTip(
            "--install: write the best validated step into the governor config (backup kept at "
            "config.toml.pre-oc-bisect). The script checks the sweep is complete and asks for "
            "confirmation in the terminal.")
        self.install_btn.clicked.connect(self._on_install)
        buttons.addWidget(self.install_btn)
        self.uninstall_btn = QPushButton("Uninstall")
        self.uninstall_btn.setToolTip("--uninstall: restore the governor config from the backup made by Install.")
        self.uninstall_btn.clicked.connect(lambda: self._run_simple("--uninstall"))
        buttons.addWidget(self.uninstall_btn)
        buttons.addStretch(1)
        self.start_btn = QPushButton("Start GPU OC Bisect")
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
        self.resize(600, 480)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        QSettings().setValue("main_window/geometry", self.saveGeometry())
        super().closeEvent(event)

    # ------------------------------------------------------------- behavior
    def _on_sweep_toggled(self) -> None:
        oc = self.oc_check.isChecked()
        uv = self.uv_check.isChecked()
        self.max_freq_spin.setEnabled(oc)
        self.freq_step_spin.setEnabled(oc)
        self.oc_volt_spin.setEnabled(oc)
        self.min_volt_spin.setEnabled(uv)
        self.volt_step_spin.setEnabled(uv)
        self.start_btn.setEnabled(oc or uv)
        self._show_summary()

    def _collect_options(self) -> SweepOptions:
        return SweepOptions(
            time_secs=self.time_spin.value(),
            rounds=self.rounds_spin.value(),
            sweep_oc=self.oc_check.isChecked(),
            sweep_uv=self.uv_check.isChecked(),
            max_freq=self.max_freq_spin.value(),
            min_volt=self.min_volt_spin.value(),
            oc_volt=self.oc_volt_spin.value(),
            freq_step=self.freq_step_spin.value(),
            volt_step=self.volt_step_spin.value(),
            per_boot=self.per_boot_check.isChecked(),
        )

    def _run_simple(self, flag: str) -> None:
        try:
            launch_in_terminal(shlex.join(["bash", self.script, flag]))
        except RuntimeError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))

    def _on_install(self) -> None:
        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Icon.Warning)
        confirm.setWindowTitle(APP_NAME)
        confirm.setText("Write the best validated step into the governor config?")
        confirm.setInformativeText(
            "This changes /etc/cyan-skillfish-governor-smu/config.toml (--install). A backup is "
            "kept at config.toml.pre-oc-bisect and Uninstall restores it. The script will show "
            "the chosen point and ask you to confirm once more in the terminal.")
        confirm.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        confirm.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if confirm.exec() == QMessageBox.StandardButton.Yes:
            self._run_simple("--install")

    def _on_reset(self) -> None:
        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Icon.Warning)
        confirm.setWindowTitle(APP_NAME)
        confirm.setText("Delete all bc250-gpu-oc-bisect results?")
        confirm.setInformativeText(
            "This permanently deletes every saved result and log in "
            "~/.local/share/bc250-gpu-oc-bisect (--reset). This cannot be undone and there is no "
            "backup. The script will still ask you to confirm once more in the terminal.")
        confirm.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        confirm.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if confirm.exec() == QMessageBox.StandardButton.Yes:
            self._run_simple("--reset")

    def _on_start(self) -> None:
        opts = self._collect_options()
        errors = opts.validate()
        if errors:
            QMessageBox.warning(self, APP_NAME, "\n".join(errors))
            return

        sweep = ("overclock + undervolt" if opts.sweep_oc and opts.sweep_uv
                 else "overclock only" if opts.sweep_oc else "undervolt only")
        summary = (
            "Start bc250-gpu-oc-bisect.sh with:\n\n"
            "  load time: {t}s\n  rounds: {r}\n  sweep: {s}\n"
            "  max frequency: {mf} MHz (step {fs})\n  min voltage: {mv} mV (step {vs})\n"
            "  OC voltage: {ov}\n  per boot: {pb}\n\n"
            "This window will close and the sweep continues in a terminal."
        ).format(t=opts.time_secs, r=opts.rounds, s=sweep,
                  mf=opts.max_freq, fs=opts.freq_step, mv=opts.min_volt, vs=opts.volt_step,
                  ov=(f"{opts.oc_volt} mV" if opts.oc_volt else "config default"),
                  pb=opts.per_boot)
        if QMessageBox.question(self, APP_NAME, summary) != QMessageBox.StandardButton.Yes:
            return

        try:
            launch_in_terminal(opts.to_command(self.script))
        except RuntimeError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return

        self.close()
