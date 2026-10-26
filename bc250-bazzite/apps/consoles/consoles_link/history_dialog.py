# SPDX-License-Identifier: AGPL-3.0-or-later
"""History…: the games played through the app and the time played (history.py), the newest first, with the total
and a button that clears it all."""

from __future__ import annotations

import datetime

from PyQt6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel, QMessageBox,
                             QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .history import HistoryStore, duration, newest_first

COLUMNS = ["Game", "Console", "Time played", "Last played"]


class HistoryDialog(QDialog):
    def __init__(self, store: HistoryStore, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("History")
        self.resize(720, 420)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(COLUMNS)):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.total = QLabel()
        note = QLabel("Counted while a console streams to this board, the Game Mode shortcut included; play on the "
                      "console itself is not seen. Kept only on this board, in "
                      "~/.config/bc250-console-link/history.json.")
        note.setWordWrap(True)
        note.setStyleSheet("color:palette(placeholder-text);")
        self.clear_button = QPushButton("Clear history")
        self.clear_button.setToolTip("Forget every game and its time")
        self.clear_button.clicked.connect(self.clear)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.addButton(self.clear_button, QDialogButtonBox.ButtonRole.ResetRole)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.total)
        lay.addWidget(note)
        lay.addWidget(buttons)
        self.refresh()

    def refresh(self) -> None:
        games = newest_first(self.store.load())
        self.table.setRowCount(len(games))
        for row, game in enumerate(games):
            title = QTableWidgetItem(game.title)
            if game.name and game.title_id:
                title.setToolTip(f"Title ID {game.title_id}")
            cells = [title, QTableWidgetItem(game.console_name), QTableWidgetItem(duration(game.seconds)),
                     QTableWidgetItem(_when(game.last_played))]
            for column, cell in enumerate(cells):
                self.table.setItem(row, column, cell)
        total = sum(game.seconds for game in games)
        self.total.setText(f"{len(games)} game{'s' if len(games) != 1 else ''}, {duration(total)} in all."
                           if games else "No games played through the app yet.")
        self.clear_button.setEnabled(bool(games))

    def clear(self) -> None:
        if QMessageBox.question(self, "History", "Forget every game and its time?") != \
                QMessageBox.StandardButton.Yes:
            return
        self.store.clear()
        self.refresh()


def _when(text: str) -> str:
    try:
        return f"{datetime.datetime.fromisoformat(text):%d-%m-%Y %H:%M}"
    except ValueError:
        return text
