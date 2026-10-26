# SPDX-License-Identifier: GPL-3.0-or-later

"""Single window: shows whether bc250-cores-bisect.sh's results accept the unlock, and installs/removes
the persistence service."""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QSettings, Qt
from PyQt6.QtGui import QCursor, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from . import APP_NAME, LOGO_PATH, __version__
from .gate import GateResult, check
from .runner import UnlockRunner
from .theme import GREEN, RED, surface_style
from .widgets import AboutDialog, SudoDialog

# Stock BC-250 layout (mask 0x77): core 3 of each 4-core CCX is fused off.
DEFAULT_BASE = [0, 1, 2, 4, 5, 6]
DEFAULT_NEW = [3, 7]

_COLORS = {
    "stock": "#1565c0",
    "good": "#2e7d32",
    "bad": "#c62828",
    "random": "#ef6c00",
    "none": "#424242",
}
_MARKS = {"stock": "stock", "good": "ok", "bad": "xx", "random": "??", "none": ".."}


class CoreMapWidget(QWidget):
    """The 8 physical cores in the same order as the script's map: stock first, unlocked last."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setSpacing(6)
        self._cells: list[tuple[QLabel, QLabel]] = []
        for i in range(8):
            name = QLabel()
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell = QLabel()
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.setFixedSize(64, 32)
            self._grid.addWidget(name, 0, i)
            self._grid.addWidget(cell, 1, i)
            self._cells.append((name, cell))
        self._grid.setColumnStretch(8, 1)
        legend = QLabel(("stock = always enabled (6C/12T)   ok = passed every round   "
                         "xx = fails every time   ?? = random   .. = not tested yet"))
        legend.setStyleSheet("color:#888;")
        self._grid.addWidget(legend, 2, 0, 1, 9)
        self.set_cores(DEFAULT_BASE, DEFAULT_NEW, {})

    def set_cores(self, base: list[int], new: list[int], verdicts: dict[int, str]) -> None:
        cores = [(c, "stock") for c in base] + [(c, verdicts.get(c, "none")) for c in new]
        for i, (name, cell) in enumerate(self._cells):
            if i < len(cores):
                core, state = cores[i]
                name.setText(f"core{core}")
                cell.setText(_MARKS[state])
                cell.setStyleSheet(f"background:{_COLORS[state]}; color:white; border-radius:4px;"
                                   "font-weight:600;")
                name.show()
                cell.show()
            else:
                name.hide()
                cell.hide()


class MainWindow(QWidget):
    @staticmethod
    def _banner_style(colour: str | None = None) -> str:
        """The theme's surface, the state as its left edge; padding 8px inside the border."""
        return (surface_style(colour, "QLabel", 4)
                + "QLabel { font-weight:700; font-size:14px; padding:7px 7px 7px 4px; }")

    def __init__(self, script: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.runner = UnlockRunner(script, self)
        self.runner.line.connect(self._append_line)
        self.runner.auth_failed.connect(self._on_auth_failed)
        self.runner.finished.connect(self._on_finished)
        self._gate_result: GateResult | None = None
        self._pending_action = ""  # what the running process is, for the right message when it ends
        self._pending_args: list[str] = []  # so a wrong password can be retried without re-clicking
        self._auth_failed_this_run = False

        root = QVBoxLayout(self)

        # The logo spans the title row and the description line below it, like every app of the suite.
        header = QHBoxLayout()
        header.setSpacing(14)
        if LOGO_PATH.is_file():
            logo = QLabel()
            logo.setPixmap(QPixmap(str(LOGO_PATH)).scaled(
                96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            header.addWidget(logo)
        header_right = QVBoxLayout()
        header_right.setSpacing(6)
        header_row = QHBoxLayout()
        title = QLabel(f"{APP_NAME}  <span style='color:#9aa0a6; font-size:14px;'>v{__version__}</span>")
        title.setStyleSheet("font-size:24px; font-weight:800;")
        header_row.addWidget(title)
        header_row.addStretch(1)
        about_btn = QPushButton("About")
        about_btn.setFlat(True)
        about_btn.clicked.connect(self._on_about)
        header_row.addWidget(about_btn)
        header_right.addLayout(header_row)
        sub = QLabel("Keeps the 8C/16T core unlock you already validated with bc250-cores-bisect.sh across reboots.")
        sub.setWordWrap(True)
        header_right.addWidget(sub)
        header.addLayout(header_right, 1)
        root.addLayout(header)

        gate_frame = QFrame()
        gate_frame.setFrameShape(QFrame.Shape.StyledPanel)
        gate_layout = QVBoxLayout(gate_frame)
        self.gate_title = QLabel()
        self.gate_title.setStyleSheet(self._banner_style())
        gate_layout.addWidget(self.gate_title)
        self.gate_reasons = QLabel()
        self.gate_reasons.setWordWrap(True)
        self.gate_reasons.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        gate_layout.addWidget(self.gate_reasons)
        root.addWidget(gate_frame)

        self.core_map = CoreMapWidget()
        root.addWidget(self.core_map)

        buttons = QHBoxLayout()
        self.install_btn = QPushButton("Install (keep 8C/16T after every boot)")
        self.install_btn.setToolTip(
            "Enable the root service that re-applies the unlock after a cold boot and warm-reboots once.")
        self.install_btn.clicked.connect(self._on_install)
        self.uninstall_btn = QPushButton("Uninstall (stock after next power off)")
        self.uninstall_btn.setToolTip(
            "Remove the service. The unlock stays active until the next full power off (cold boot).")
        self.uninstall_btn.clicked.connect(self._on_uninstall)
        self.status_btn = QPushButton("Refresh status")
        self.status_btn.setToolTip("Show the core presence mask, threads, service and guard state.")
        self.status_btn.clicked.connect(self._refresh_status)
        self.sudo_status_btn = QPushButton("Status with sudo")
        self.sudo_status_btn.setToolTip(
            "Run the status as root (asks for the sudo password), so it also shows the core presence mask.")
        self.sudo_status_btn.clicked.connect(self._on_sudo_status)
        self.recheck_btn = QPushButton("Re-check bisect results")
        self.recheck_btn.setToolTip(
            "Re-read bc250-cores-bisect.sh's recorded results, e.g. after more rounds finished.")
        self.recheck_btn.clicked.connect(self._refresh_gate)
        for btn in (self.install_btn, self.uninstall_btn, self.status_btn, self.sudo_status_btn, self.recheck_btn):
            buttons.addWidget(btn)
        root.addLayout(buttons)

        self.busy_label = QLabel()
        self.busy_label.setStyleSheet("color:#888; font-style:italic;")
        root.addWidget(self.busy_label)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(2000)
        self.output.setPlaceholderText("Output of bc250-cores-unlock.sh appears here.")
        root.addWidget(self.output, stretch=1)

        self._restore_geometry()
        self._refresh_gate()
        self._refresh_status()

    # --------------------------------------------------------------- window
    def _restore_geometry(self) -> None:
        geometry = QSettings().value("main_window/geometry")
        if isinstance(geometry, QByteArray) and self.restoreGeometry(geometry):
            return
        self.resize(700, 560)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        QSettings().setValue("main_window/geometry", self.saveGeometry())
        super().closeEvent(event)

    def _on_about(self) -> None:
        AboutDialog(self).exec()

    # ------------------------------------------------------------------ gate
    def _refresh_gate(self) -> None:
        result = check()
        self._gate_result = result
        if result.accepted:
            self.gate_title.setText("\u2714 ACCEPTED")
            self.gate_title.setStyleSheet(self._banner_style(GREEN))
        else:
            self.gate_title.setText("\u2718 NOT ACCEPTED YET!")
            self.gate_title.setStyleSheet(self._banner_style(RED))
        self.gate_reasons.setText("\n".join(result.reasons))
        base = result.base_cores or DEFAULT_BASE
        new = result.new_cores or [c for c in range(8) if c not in base] or DEFAULT_NEW
        self.core_map.set_cores(base, new, result.core_verdicts)
        self.install_btn.setEnabled(result.accepted and not self.runner.busy)

    # ---------------------------------------------------------------- output
    def _append_line(self, text: str) -> None:
        self.output.appendPlainText(text)

    def _set_busy(self, busy: bool) -> None:
        for btn in (self.install_btn, self.uninstall_btn, self.status_btn, self.sudo_status_btn, self.recheck_btn):
            btn.setEnabled(not busy)
        if busy:
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
            label = {
                "install": "Working \u2014 installing\u2026",
                "uninstall": "Working \u2014 uninstalling\u2026",
            }.get(self._pending_action, "Working\u2026")
            self.busy_label.setText(label)
        else:
            QApplication.restoreOverrideCursor()
            self.busy_label.setText("")
            self.install_btn.setEnabled(self._gate_result is not None and self._gate_result.accepted)

    def _on_auth_failed(self) -> None:
        self._auth_failed_this_run = True
        self._append_line("sudo: authentication failed.")

    def _on_finished(self, code: int) -> None:
        self._set_busy(False)
        action = self._pending_action
        auth_failed = self._auth_failed_this_run
        self._auth_failed_this_run = False
        if auth_failed and code != 0 and action:
            # Wrong password: let the user retry right away instead of re-clicking Install/Uninstall.
            entered = SudoDialog.ask(self, "Incorrect password, try again.")
            if entered is None:
                self._pending_action = ""
                self._pending_args = []
                return
            self._set_busy(True)
            self.runner.run(self._pending_args, pw=entered)
            return
        self._pending_action = ""
        self._pending_args = []
        if action in ("install", "uninstall"):
            self._append_line("({0} finished, exit code {1})".format(action, code))
            self._refresh_status()
        if code != 0 and action:
            QMessageBox.warning(self, APP_NAME, "{0} failed (exit code {1}). See the output above."
                                .format(action, code))

    # --------------------------------------------------------------- actions
    def _run_privileged(self, args: list[str], action: str) -> None:
        if self.runner.busy:
            return
        self._pending_action = action
        self._pending_args = args
        self._set_busy(True)
        if self.runner.sudo_ready():
            self.runner.run(args)
            return
        entered = SudoDialog.ask(self)
        if entered is None:
            self._pending_action = ""
            self._pending_args = []
            self._set_busy(False)
            return
        self.runner.run(args, pw=entered)

    def _on_install(self) -> None:
        self._refresh_gate()  # results may have changed since the window opened
        if self._gate_result is None or not self._gate_result.accepted:
            return
        answer = QMessageBox.question(
            self, APP_NAME,
            ("Keep all 8 cores (16 threads) enabled on every boot?\n\n"
             "A root service checks the core mask at every boot. After a cold boot it re-applies "
             "the unlock and warm-reboots once. If the unlock isn't active right now, reboot (warm) "
             "after installing to bring the cores up."),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_privileged(["--install"], "install")

    def _on_uninstall(self) -> None:
        answer = QMessageBox.question(
            self, APP_NAME,
            ("Remove the unlock service? The 8 cores stay enabled until the next full power off "
             "(cold boot); after that the board is back to the stock 6C/12T."),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_privileged(["--uninstall"], "uninstall")

    def _on_sudo_status(self) -> None:
        self._run_privileged(["--status"], "status")

    def _refresh_status(self) -> None:
        if self.runner.busy:
            return
        self._pending_action = ""
        self.runner.run_unprivileged(["--status"])
