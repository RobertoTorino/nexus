# SPDX-License-Identifier: GPL-3.0-or-later

"""Single window: shows whether bc250-cu-bisect.sh's results accept a mask, and installs/removes it."""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QSettings, Qt
from PyQt6.QtGui import QCursor, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from . import APP_NAME, LOGO_PATH, __version__
from .gate import GateResult, MASK_RE, check, cu_count, even_level
from .runner import UnlockRunner
from .theme import GREEN, RED, surface_style
from .widgets import AboutDialog, SudoDialog

ROWS = ("SE0.SH0", "SE0.SH1", "SE1.SH0", "SE1.SH1")


class CuMapWidget(QWidget):
    """Static 4x5 grid of the shader-array rows and WGPs for the currently accepted mask."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setSpacing(6)
        self._cells: list[list[QLabel]] = []
        for r, row in enumerate(ROWS):
            self._grid.addWidget(QLabel(row), r, 0)
            cells = []
            for b in range(5):
                cell = QLabel("WGP%d" % b)
                cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell.setFixedSize(64, 28)
                cell.setStyleSheet(self._style(False))
                self._grid.addWidget(cell, r, b + 1)
                cells.append(cell)
            self._cells.append(cells)
        # Without this, QGridLayout hands any leftover horizontal space to column 0 (the row labels),
        # opening a big gap before the boxes. Give it to a trailing spacer column instead.
        self._grid.setColumnStretch(6, 1)
        self.clear()

    @staticmethod
    def _style(unlocked: bool) -> str:
        bg = "#2e7d32" if unlocked else "#424242"
        return f"background:{bg}; color:white; border-radius:4px; font-weight:600;"

    def clear(self) -> None:
        for cells in self._cells:
            for cell in cells:
                cell.setStyleSheet(self._style(False))

    def set_masks(self, masks: str) -> None:
        values = [int(m, 16) for m in masks.split(",")]
        for r, v in enumerate(values):
            for b in range(5):
                self._cells[r][b].setStyleSheet(self._style(bool(v >> b & 1)))


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
        self._pending_action = ""  # what the running process is, for the right message when it ends
        self._pending_args: list[str] = []  # so a wrong password can be retried without re-clicking
        self._auth_failed_this_run = False

        root = QVBoxLayout(self)

        # The logo spans the title row and the description line below it (same layout as
        # bc250-bazzite-test, for a consistent look across the BC-250 tools).
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
        about_btn = QPushButton("About")
        about_btn.setFlat(True)
        about_btn.clicked.connect(self._on_about)
        title_row.addWidget(about_btn)
        header_right.addLayout(title_row)
        sub = QLabel("Keeps a CU unlock you already validated with bc250-cu-bisect.sh across reboots.")
        sub.setWordWrap(True)
        header_right.addWidget(sub)
        header.addLayout(header_right, 1)
        root.addLayout(header)

        gate_frame = QFrame()
        gate_frame.setFrameShape(QFrame.Shape.StyledPanel)
        gate_layout = QVBoxLayout(gate_frame)
        self.gate_title = QLabel()
        self.gate_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.gate_title.setStyleSheet(self._banner_style())
        gate_layout.addWidget(self.gate_title)
        self.gate_reasons = QLabel()
        self.gate_reasons.setWordWrap(True)
        self.gate_reasons.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        gate_layout.addWidget(self.gate_reasons)
        root.addWidget(gate_frame)

        self.cu_map = CuMapWidget()
        root.addWidget(self.cu_map)

        preview_row = QHBoxLayout()
        preview_row.addWidget(QLabel("Preview a mask:"))
        self.mask_preview_input = QLineEdit()
        self.mask_preview_input.setPlaceholderText("0x0f,0x0f,0x0f,0x0f")
        self.mask_preview_input.setToolTip(
            "Paste any 4-row WGP mask (SE0.SH0,SE0.SH1,SE1.SH0,SE1.SH1, e.g. from --baseline or the "
            "README) to see it on the map above, without needing it to be an accepted result. Only "
            "even masks can be installed: 3 WGPs per row = 24 CUs (stock), 4 = 32 CUs, 5 = 40 CUs.")
        self.mask_preview_input.textChanged.connect(self._on_mask_preview_changed)
        preview_row.addWidget(self.mask_preview_input, stretch=1)
        self.mask_preview_label = QLabel()
        preview_row.addWidget(self.mask_preview_label)
        root.addLayout(preview_row)

        buttons = QHBoxLayout()
        self.install_btn = QPushButton("Install (apply now + keep after reboot)")
        self.install_btn.setToolTip("Apply the accepted mask now and reapply it automatically on every future boot.")
        self.install_btn.clicked.connect(self._on_install)
        self.uninstall_btn = QPushButton("Uninstall (back to stock next boot)")
        self.uninstall_btn.setToolTip(
            "Disable the unlock service; the board returns to the stock 24 CUs from the next reboot.")
        self.uninstall_btn.clicked.connect(self._on_uninstall)
        self.status_btn = QPushButton("Refresh status")
        self.status_btn.setToolTip("Show the installed masks, service state and live masks (no root needed).")
        self.status_btn.clicked.connect(self._refresh_status)
        self.recheck_btn = QPushButton("Re-check bisect results")
        self.recheck_btn.setToolTip("Re-read bc250-cu-bisect.sh's recorded results, e.g. after running another retest.")
        self.recheck_btn.clicked.connect(self._refresh_gate)
        buttons.addWidget(self.install_btn)
        buttons.addWidget(self.uninstall_btn)
        buttons.addWidget(self.status_btn)
        buttons.addWidget(self.recheck_btn)
        root.addLayout(buttons)

        self.busy_label = QLabel()
        self.busy_label.setStyleSheet("color:#888; font-style:italic;")
        root.addWidget(self.busy_label)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(2000)
        self.output.setPlaceholderText("Output of bc250-cu-unlock.sh appears here.")
        root.addWidget(self.output, stretch=1)

        self._restore_geometry()
        self._refresh_gate()
        self._refresh_status()

    # --------------------------------------------------------------- window
    def _restore_geometry(self) -> None:
        settings = QSettings()
        geometry = settings.value("main_window/geometry")
        if isinstance(geometry, QByteArray) and self.restoreGeometry(geometry):
            return
        self.resize(640, 520)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        QSettings().setValue("main_window/geometry", self.saveGeometry())
        super().closeEvent(event)

    def _on_about(self) -> None:
        AboutDialog(self).exec()

    # ------------------------------------------------------------------ gate
    def _refresh_gate(self) -> None:
        result: GateResult = check()
        self._gate_result = result
        if result.accepted:
            self.gate_title.setText("\u2714 ACCEPTED")
            self.gate_title.setStyleSheet(self._banner_style(GREEN))
        else:
            self.gate_title.setText("\u2718 NOT ACCEPTED YET!")
            self.gate_title.setStyleSheet(self._banner_style(RED))
        self.gate_reasons.setText("\n".join(result.reasons))
        self.install_btn.setEnabled(result.accepted and not self.runner.busy)
        # Don't stomp on a mask the user is currently previewing (see _on_mask_preview_changed).
        if not self.mask_preview_input.text().strip():
            self._apply_gate_map()

    def _apply_gate_map(self) -> None:
        result = getattr(self, "_gate_result", None)
        if result is not None and result.accepted:
            self.cu_map.set_masks(result.masks or "")
        else:
            self.cu_map.clear()

    # --------------------------------------------------------------- preview
    def _on_mask_preview_changed(self, text: str) -> None:
        text = text.strip()
        if not text:
            self.mask_preview_input.setStyleSheet("")
            self.mask_preview_label.setText("")
            self._apply_gate_map()
            return
        if not MASK_RE.match(text):
            self.mask_preview_input.setStyleSheet("border:1px solid #c62828;")
            self.mask_preview_label.setText("invalid mask")
            return
        self.cu_map.set_masks(text)
        if even_level(text) is None:
            self.mask_preview_input.setStyleSheet("border:1px solid #ef6c00;")
            self.mask_preview_label.setText(
                "{0} CUs \u2014 not installable (needs 3, 4 or 5 WGPs on every row = 24/32/40 CUs)"
                .format(cu_count(text)))
            return
        self.mask_preview_input.setStyleSheet("border:1px solid #2e7d32;")
        self.mask_preview_label.setText("{0} CUs (preview)".format(cu_count(text)))

    # ---------------------------------------------------------------- output
    def _append_line(self, text: str) -> None:
        self.output.appendPlainText(text)

    def _set_busy(self, busy: bool) -> None:
        for btn in (self.install_btn, self.uninstall_btn, self.status_btn, self.recheck_btn):
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
            self.install_btn.setEnabled(getattr(self, "_gate_result", None) is not None
                                         and self._gate_result.accepted)

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
            self._pending_action = action
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
        result = getattr(self, "_gate_result", None)
        if result is None or not result.accepted or not result.masks:
            return
        answer = QMessageBox.question(
            self, APP_NAME,
            "Apply {0} ({1} CUs) now and keep it enabled on every boot?"
            .format(result.masks, result.cu_total),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_privileged(["--install", result.masks], "install")

    def _on_uninstall(self) -> None:
        answer = QMessageBox.question(
            self, APP_NAME,
            ("Disable the unlock service? The board goes back to the stock 24 CUs from the "
             "next reboot."),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_privileged(["--uninstall"], "uninstall")

    def _refresh_status(self) -> None:
        if self.runner.busy:
            return
        self._pending_action = ""
        self.runner.run_unprivileged(["--status"])
