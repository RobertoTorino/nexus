# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window: a header with the stock/modded verdict, where the values come from, the setup screen and the
actions (read the BIOS chip, open a dump, back to this board, show hidden items)."""

from __future__ import annotations

import os
from html import escape
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
                             QMessageBox, QPushButton, QVBoxLayout, QWidget)

from bc250_core import SUITE_MANUAL_URL, window_title
from bc250_core import __version__ as CORE_VERSION
from bc250_core.platform import data_home
from bc250_core.settings import SettingsStore
from bc250_core.widgets import AppHeader, StatusText, Terminal, accent_button, hint_label

from . import APP_ID, APP_NAME, INFO, LOGO_PATH, __version__
from . import bios as biosmod
from . import dump, table
from .screen import BiosScreen

MANUAL_URL = f"{SUITE_MANUAL_URL}apps/bios/#reading-the-bios-flash-chip-optional"
VERDICT_COLOURS = {"stock": "ok", "modded": "warn", "unknown": "neutral"}


class ReaderSettings(SettingsStore):
    DEFAULTS = {"show_hidden": False, "last_dir": ""}


def dumps_dir() -> Path:
    return data_home() / APP_ID / "dumps"


class MainWindow(QMainWindow):
    def __init__(self, sys_root: Path = Path("/sys"), tables_dir: Path = table.TABLES_DIR):
        super().__init__()
        self.resize(1100, 720)
        self.sys_root = sys_root
        self.tables_dir = tables_dir
        self.settings = ReaderSettings(INFO, self)
        self.bios: biosmod.Bios | None = None

        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.badge = StatusText()
        header.add_state(self.badge)
        self.read_button = accent_button("Read BIOS chip…", "Read the BIOS flash chip with flashrom (read-only)")
        self.read_button.clicked.connect(self.read_chip)
        self.open_button = QPushButton("Open dump…")
        self.open_button.setToolTip("Open a BIOS image file made earlier")
        self.open_button.clicked.connect(self.open_dump)
        self.board_button = QPushButton("This board")
        self.board_button.setToolTip("Show the settings of the running board")
        self.board_button.clicked.connect(self.load_board)
        self.hidden_box = QCheckBox("Show hidden items")
        self.hidden_box.setToolTip("Also list the menus and settings the BIOS does not show (H)")
        self.hidden_box.toggled.connect(self._toggle_hidden)
        self.source = QLabel()                     # what is shown: the board, a dump or the chip
        self.source.setWordWrap(True)
        header.add_second(self.source, 1)
        for w in (self.hidden_box, self.board_button, self.open_button, self.read_button):
            header.add_second(w)
        self.note = hint_label("")
        self.screen = BiosScreen()

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(header)
        lay.addWidget(self.note)
        lay.addWidget(self.screen, 1)
        version = QLabel(f"{APP_NAME} {__version__} · core {CORE_VERSION} · reads only, changes nothing")
        version.setStyleSheet("color:palette(placeholder-text);")
        lay.addWidget(version, 0, Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(central)
        QShortcut(QKeySequence("H"), self, activated=lambda: self.hidden_box.toggle())

        geometry = self.settings.window_state("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.hidden_box.setChecked(self.settings.get("show_hidden"))
        self.screen.set_show_hidden(self.hidden_box.isChecked())
        self._process: QProcess | None = None

    # --- Loading ----------------------------------------------------------------------------------------------

    def load_board(self) -> None:
        self.set_bios(biosmod.load_running(self.sys_root, self.tables_dir))

    def load_dump_file(self, path: Path) -> bool:
        try:
            loaded = biosmod.load_dump(path, self.sys_root)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, window_title("Open dump"), f"Could not read {path.name}:\n{exc}")
            return False
        self.set_bios(loaded)
        return True

    def set_bios(self, loaded: biosmod.Bios) -> None:
        self.bios = loaded
        self.screen.set_bios(loaded)
        verdict = biosmod.verdict(loaded, self._stock_screens(loaded))
        tip = "\n".join(verdict.reasons)
        if not verdict.certain and loaded.source == "running":
            tip += "\n\nFrom the version string only. Read the BIOS chip for proof."
        self.badge.set_status(verdict.title, VERDICT_COLOURS[verdict.kind], tip)
        self.source.setText(self._source_text(loaded))
        self.note.setText(loaded.note)
        self.note.setVisible(bool(loaded.note))
        self.board_button.setEnabled(loaded.source == "dump")

    def _stock_screens(self, loaded: biosmod.Bios) -> biosmod.Screens | None:
        """The stock release's screens with this BIOS's values, to name the menus a modded BIOS opens."""
        if loaded.source != "dump" or not loaded.version:
            return None
        path = table.table_path(loaded.version, self.tables_dir)
        if not path.is_file():
            return None
        version, date, formsets, defaults = table.load_table(path)
        return biosmod.Screens(biosmod.Bios(formsets, loaded.values, defaults, "table", version, date))

    def _source_text(self, loaded: biosmod.Bios) -> str:
        hidden = len(list(self.screen.screens.hidden_forms())) if self.screen.screens else 0
        if loaded.source == "dump":
            what = (f"<b>Dump</b> {escape(Path(loaded.dump_path).name)} · BIOS {escape(loaded.version or '?')} "
                    f"{escape(loaded.date)} · SHA-256 {loaded.dump_sha256[:12]}…")
        else:
            what = (f"<b>This board</b> · BIOS {escape(loaded.dmi.version or '?')} {escape(loaded.dmi.date)} · "
                    "values from the UEFI variables Linux can read")
        return f"{what} · {hidden} menus hidden in the BIOS"

    # --- Actions ----------------------------------------------------------------------------------------------

    def _toggle_hidden(self, on: bool) -> None:
        self.settings.set("show_hidden", on)
        self.screen.set_show_hidden(on)

    def open_dump(self) -> None:
        start = self.settings.get("last_dir") or str(dumps_dir() if dumps_dir().is_dir() else Path.home())
        path, _ = QFileDialog.getOpenFileName(self, window_title("Open dump"), start,
                                              "BIOS images (*.bin *.rom *.img *.cap);;All files (*)")
        if path:
            self.settings.set("last_dir", str(Path(path).parent))
            self.load_dump_file(Path(path))

    def read_chip(self) -> None:
        flashrom = dump.find_flashrom()
        if flashrom is None:
            box = QMessageBox(QMessageBox.Icon.Information, window_title("Read BIOS chip"),
                              "flashrom is not installed in a form that can read the board's own chip.", parent=self)
            box.setTextFormat(Qt.TextFormat.RichText)
            box.setInformativeText(
                "Homebrew's flashrom cannot (it has no <i>internal</i> programmer). Unpack Fedora's flashrom into "
                f"~/flashrom as the <a href='{MANUAL_URL}'>manual</a> describes, then try again.")
            box.exec()
            return
        folder = dumps_dir()
        first, second = dump.dump_paths(folder)
        answer = QMessageBox.question(
            self, window_title("Read BIOS chip"),
            "Read the BIOS flash chip?\n\n"
            "flashrom reads the chip twice (read-only, nothing is written) and the two reads are compared. "
            "It needs your password and takes about a minute.\n\n"
            f"flashrom: {flashrom.binary}\nThe dump goes to: {first}\n\n"
            "A dump is this board's own firmware with its settings. Keep it to yourself.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        folder.mkdir(parents=True, exist_ok=True)
        dialog = ReadDialog(dump.read_command(flashrom, first, second, f"{os.getuid()}:{os.getgid()}"), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        problem = dump.check_reads(first, second)
        if problem:
            QMessageBox.warning(self, window_title("Read BIOS chip"), problem)
            return
        self.load_dump_file(first)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.settings.set_window_state("geometry", self.saveGeometry())
        self.settings.sync()
        super().closeEvent(event)


class ReadDialog(QDialog):
    """Runs the read command and shows flashrom's output; accepted when it exits with 0."""

    def __init__(self, command: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(window_title("Read BIOS chip"))
        self.resize(760, 420)
        self.output = Terminal()
        self.status = QLabel("Reading… (flashrom runs twice)")
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        self.buttons.setEnabled(False)
        lay = QVBoxLayout(self)
        lay.addWidget(self.status)
        lay.addWidget(self.output, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.buttons)
        lay.addLayout(row)
        self._text = ""
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.process.start(command[0], command[1:])

    def _read(self) -> None:
        self._text += bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace")
        self.output.set_text(self._text)

    def _finished(self, code: int, _status) -> None:
        self.buttons.setEnabled(True)
        if code == 0:
            self.status.setText("Done: both reads finished.")
            self.accept()
        elif code in (126, 127):
            self.status.setText("Not authorized: the password dialog was canceled or refused.")
        else:
            self.status.setText(f"flashrom stopped with exit code {code}; see its output above.")

    def _error(self, _error) -> None:
        self.buttons.setEnabled(True)
        self.status.setText(f"Could not start pkexec: {self.process.errorString()}")

    def reject(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return                              # never leave flashrom running without its window
        super().reject()
