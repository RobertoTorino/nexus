# SPDX-License-Identifier: MIT
"""Single window: shows whether the ACPI override is installed and in use, and installs/removes it. The header is
the suite's (owner, 26-10-2026): the icon, the title with the version and the state beside it, About at the right
end, and under it the status boxes (the override, the frequency steps, the idle states), read from the script's
status lines."""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QSettings, Qt
from PyQt6.QtGui import QCursor, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from . import APP_NAME, LOGO_PATH, __version__
from .runner import ScriptRunner
from .theme import BLUE, STATE_COLORS, header_font, muted
from .widgets import AboutDialog, MetricBox, StatusText, SudoDialog

NEEDS_CONFIRMATION = 3      # bc250-acpi-override.sh: a warning needs "Continue anyway?" (--yes)

_STATES = {                     # the state beside the title and in the Override box: text and kind
    "installed": ("Installed", "ok"),
    "not installed": ("Not installed", "neutral"),
    "incomplete": ("Incomplete", "warn"),
}
_STATUS_FIELDS = {"Frequency steps: ": "steps", "Idle states: ": "idle"}


def override_state(line: str) -> str | None:
    """'installed', 'not installed' or 'incomplete' from the script's "Override: ..." status line."""
    if not line.startswith("Override: "):
        return None
    value = line[len("Override: "):]
    for state in ("not installed", "incomplete", "installed"):
        if value.startswith(state):
            return state
    return None


def status_value(line: str) -> tuple[str, str, str] | None:
    """("steps" or "idle", the value, the note in parentheses) from the script's "Frequency steps: 8 (800-3200 MHz;
    ...)" and "Idle states: POLL,C1,C2 (...)" lines; None for any other line."""
    for prefix, field in _STATUS_FIELDS.items():
        if line.startswith(prefix):
            value, _, note = line[len(prefix):].partition(" (")
            return field, value.strip(), note.rstrip(")").strip()
    return None


class MainWindow(QWidget):
    def __init__(self, script: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.runner = ScriptRunner(script, self)
        self.runner.line.connect(self._append_line)
        self.runner.auth_failed.connect(self._on_auth_failed)
        self.runner.finished.connect(self._on_finished)
        self._pending_action = ""  # what the running process is, for the right message when it ends
        self._pending_args: list[str] = []  # so a wrong password can be retried without re-clicking
        self._auth_failed_this_run = False
        self._run_lines: list[str] = []  # output of the running process, for the warnings it stopped on

        root = QVBoxLayout(self)

        # The suite's header: the icon, the title with the version and the state, About; the status boxes below.
        header = QHBoxLayout()
        header.setSpacing(14)
        if LOGO_PATH.is_file():
            logo = QLabel()
            logo.setPixmap(QPixmap(str(LOGO_PATH)).scaled(
                96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            header.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)
        right = QVBoxLayout()
        right.setSpacing(6)
        title_row = QHBoxLayout()
        title = QLabel(f"{APP_NAME}  <span style='color:{muted()}; font-size:14px;'>v{__version__}</span>")
        title.setStyleSheet(header_font() + "font-size:24px; font-weight:800;")
        title_row.addWidget(title)
        self.banner = StatusText()                      # the override's state, beside the title
        title_row.addWidget(self.banner)
        title_row.addStretch(1)
        about_btn = QPushButton("About")
        about_btn.setFlat(True)
        about_btn.clicked.connect(self._on_about)
        title_row.addWidget(about_btn)
        right.addLayout(title_row)
        boxes = QHBoxLayout()
        boxes.setSpacing(8)
        self.override_box = MetricBox("Override", BLUE)
        self.steps_box = MetricBox("Frequency steps", BLUE)
        self.idle_box = MetricBox("Idle states", BLUE)
        for box in (self.override_box, self.steps_box, self.idle_box):
            boxes.addWidget(box)
        boxes.addStretch(1)
        right.addLayout(boxes)
        header.addLayout(right, 1)
        root.addLayout(header)
        sub = QLabel(
            "Gives the BC-250 CPU idle states (C-states) and frequency scaling (800 MHz - 3.2 GHz, 8 steps) "
            "through an ACPI override that GRUB loads at every boot. It survives kernel and image updates, "
            "and Uninstall reverses it completely.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{muted()};")
        root.addWidget(sub)
        self._set_banner(None)

        buttons = QHBoxLayout()
        self.install_btn = QPushButton("Install")
        self.install_btn.setToolTip("Copy the ACPI override to /boot, add the GRUB line and regenerate GRUB.")
        self.install_btn.clicked.connect(self._on_install)
        self.uninstall_btn = QPushButton("Uninstall")
        self.uninstall_btn.setToolTip("Remove the override and the GRUB line, and regenerate GRUB.")
        self.uninstall_btn.clicked.connect(self._on_uninstall)
        self.status_btn = QPushButton("Refresh status")
        self.status_btn.setToolTip("Show whether the override is installed, and the CPU's frequency steps and "
                                   "idle states.")
        self.status_btn.clicked.connect(self._refresh_status)
        self.sudo_status_btn = QPushButton("Status with sudo")
        self.sudo_status_btn.setToolTip("Run the status as root (asks for the sudo password), so it also checks "
                                        "the kernel log for the override tables.")
        self.sudo_status_btn.clicked.connect(self._on_sudo_status)
        self._buttons = (self.install_btn, self.uninstall_btn, self.status_btn, self.sudo_status_btn)
        for btn in self._buttons:
            buttons.addWidget(btn)
        root.addLayout(buttons)

        self.busy_label = QLabel()
        self.busy_label.setStyleSheet("color:#888; font-style:italic;")
        root.addWidget(self.busy_label)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(2000)
        self.output.setPlaceholderText("Output of bc250-acpi-override.sh appears here.")
        root.addWidget(self.output, stretch=1)

        self._restore_geometry()
        self._refresh_status()

    # --------------------------------------------------------------- window
    def _restore_geometry(self) -> None:
        geometry = QSettings().value("main_window/geometry")
        if isinstance(geometry, QByteArray) and self.restoreGeometry(geometry):
            return
        self.resize(700, 520)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        QSettings().setValue("main_window/geometry", self.saveGeometry())
        super().closeEvent(event)

    def _on_about(self) -> None:
        AboutDialog(self).exec()

    def _set_banner(self, state: str | None) -> None:
        """The override's state beside the title and in the Override box: green installed, orange incomplete."""
        text, kind = _STATES.get(state or "", ("Checking…", "neutral"))
        self.banner.set_status(text, kind)
        self.override_box.set_value(text)
        self.override_box.set_colour(STATE_COLORS[kind] if kind != "neutral" else BLUE)

    # ---------------------------------------------------------------- output
    def _append_line(self, text: str) -> None:
        self._run_lines.append(text)
        self.output.appendPlainText(text)
        state = override_state(text)
        if state:
            self._set_banner(state)
        found = status_value(text)
        if found:
            field, value, note = found
            (self.steps_box if field == "steps" else self.idle_box).set_value(value, note)

    def _set_busy(self, busy: bool) -> None:
        for btn in self._buttons:
            btn.setEnabled(not busy)
        if busy:
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
            label = {
                "install": "Working — installing (regenerating GRUB takes a moment)…",
                "uninstall": "Working — uninstalling (regenerating GRUB takes a moment)…",
            }.get(self._pending_action, "Working…")
            self.busy_label.setText(label)
        else:
            QApplication.restoreOverrideCursor()
            self.busy_label.setText("")

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
                self._clear_pending()
                return
            self._start(self._pending_args, entered)
            return
        if action == "install" and code == NEEDS_CONFIRMATION and "--yes" not in self._pending_args:
            self._confirm_warnings()
            return
        self._clear_pending()
        if action in ("install", "uninstall"):
            self._append_line(f"({action} finished, exit code {code})")
            self._refresh_status()
            if code == 0:
                QMessageBox.information(self, APP_NAME, {
                    "install": "The override is installed. Reboot to load it.",
                    "uninstall": "The override is removed. Reboot to return to the BIOS-provided ACPI tables.",
                }[action])
        if code != 0 and action:
            QMessageBox.warning(self, APP_NAME, f"{action} failed (exit code {code}). See the output above.")

    def _confirm_warnings(self) -> None:
        """The script stopped on a warning that asks "Continue anyway?": ask here, then run it with --yes."""
        warnings = [line[len("[WARN] "):] for line in self._run_lines
                    if line.startswith("[WARN] ") and "--yes" not in line]
        answer = QMessageBox.warning(
            self, APP_NAME,
            "\n\n".join(warnings or ["The installer stopped on a warning; see the output."])
            + "\n\nContinue anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self._append_line("Not installed.")
            self._clear_pending()
            return
        self._run_privileged([*self._pending_args, "--yes"], "install")

    def _clear_pending(self) -> None:
        self._pending_action = ""
        self._pending_args = []

    # --------------------------------------------------------------- actions
    def _start(self, args: list[str], pw: str | None) -> None:
        self._run_lines = []
        self._set_busy(True)
        self.runner.run(args, pw=pw)

    def _run_privileged(self, args: list[str], action: str) -> None:
        if self.runner.busy:
            return
        self._pending_action = action
        self._pending_args = args
        if self.runner.sudo_ready():
            self._start(args, None)
            return
        entered = SudoDialog.ask(self)
        if entered is None:
            self._clear_pending()
            return
        self._start(args, entered)

    def _on_install(self) -> None:
        answer = QMessageBox.question(
            self, APP_NAME,
            "Install the ACPI override?\n\n"
            "This copies acpi_override.cpio to /boot, adds one line to /etc/default/grub and regenerates the "
            "GRUB configuration. The new tables load after a reboot. Uninstall reverses all three.\n\n"
            "Don't combine it with a modded BIOS that already brings its own ACPI fixes.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_privileged(["--install"], "install")

    def _on_uninstall(self) -> None:
        answer = QMessageBox.question(
            self, APP_NAME,
            "Remove the ACPI override? After the next reboot the board uses the BIOS-provided ACPI tables "
            "again: no C-states and no frequency scaling.",
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
        self._run_lines = []
        self.runner.run_unprivileged(["--status"])
