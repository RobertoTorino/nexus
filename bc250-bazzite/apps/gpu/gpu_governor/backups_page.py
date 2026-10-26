# SPDX-License-Identifier: GPL-3.0-or-later
"""Backups page: the config.toml.bak-* copies the app makes before every write, with diff and restore."""

from __future__ import annotations

import difflib
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import fmt
from .backends.base import ConfigBackup
from .widgets import Terminal, accent_button, hint_label, page_header


class BackupsPage(QWidget):
    restore_requested = pyqtSignal(object, bool)        # Path, restart after restoring
    refresh_requested = pyqtSignal()

    def __init__(self, config_path: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.config_path = config_path
        self.backups: list[ConfigBackup] = []
        self.current_text = ""
        self.read_backup = None                          # set by the main window: Path -> str

        layout = QVBoxLayout(self)
        header, _ = page_header("Backups")
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_requested)
        header.addWidget(refresh)
        layout.addLayout(header)
        layout.addWidget(hint_label(fmt(
            "Before every write the app copies %1 to config.toml.bak-YYYYMMDD-HHMMSS next to it. "
            "Pick one to see what differs from the current file; Restore puts it back (the current file is backed "
            "up first, so nothing is lost).", config_path)))

        box = QGroupBox("Copies, newest first")
        box_layout = QVBoxLayout(box)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Created", "Size", "File"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMaximumHeight(180)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        box_layout.addWidget(self.table)
        self.empty = QLabel("No backups yet.")
        box_layout.addWidget(self.empty)
        layout.addWidget(box)

        diff_box = QGroupBox("Difference: backup → current file")
        diff_layout = QVBoxLayout(diff_box)
        self.diff = Terminal()
        diff_layout.addWidget(self.diff)
        layout.addWidget(diff_box, 1)

        row = QHBoxLayout()
        self.restart_after = QCheckBox("Restart the governor after restoring")
        self.restart_after.setChecked(True)
        row.addWidget(self.restart_after)
        row.addStretch(1)
        self.restore = accent_button("Restore selected",
                                     "Make the selected copy the config again (asks for your password).")
        self.restore.setEnabled(False)
        self.restore.clicked.connect(self._restore_clicked)
        row.addWidget(self.restore)
        layout.addLayout(row)

    # ------------------------------------------------------------------ data
    def load(self, backups: list[ConfigBackup], current_text: str) -> None:
        selected = self.selected_path()
        self.backups = backups
        self.current_text = current_text
        self.table.setRowCount(len(backups))
        for row, backup in enumerate(backups):
            cells = (backup.created.strftime("%Y-%m-%d %H:%M:%S"), _size(backup.size), backup.path.name)
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, item)
            if selected is not None and backup.path == selected:
                self.table.selectRow(row)
        self.table.setVisible(bool(backups))
        self.empty.setVisible(not backups)
        if not backups:
            self.diff.set_text("")
            self.restore.setEnabled(False)
        elif self.selected_path() is None:
            self.diff.set_text("Select a backup to compare it with the current file.")

    def selected_path(self) -> Path | None:
        rows = {index.row() for index in self.table.selectedIndexes()}
        if len(rows) != 1:
            return None
        row = rows.pop()
        return self.backups[row].path if 0 <= row < len(self.backups) else None

    # ------------------------------------------------------------------ slots
    def _selection_changed(self) -> None:
        path = self.selected_path()
        if path is None or self.read_backup is None:
            self.restore.setEnabled(False)
            return
        try:
            old = self.read_backup(path)
        except OSError as exc:
            self.diff.set_text(fmt("Cannot read %1: %2", str(path), str(exc)))
            self.restore.setEnabled(False)
            return
        if old == self.current_text:
            self.diff.set_text("Identical to the current file.")
            self.restore.setEnabled(False)
            return
        lines = difflib.unified_diff(old.splitlines(), self.current_text.splitlines(),
                                     fromfile=path.name, tofile=Path(self.config_path).name, lineterm="", n=2)
        self.diff.set_text("\n".join(lines))
        self.restore.setEnabled(True)

    def _restore_clicked(self) -> None:
        path = self.selected_path()
        if path is not None:
            self.restore_requested.emit(path, self.restart_after.isChecked())


def _size(size: int) -> str:
    return f"{size} B" if size < 10_000 else f"{size / 1024:.1f} KiB"
