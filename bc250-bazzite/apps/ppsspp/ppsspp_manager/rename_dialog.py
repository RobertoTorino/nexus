# SPDX-License-Identifier: GPL-3.0-or-later
"""The Rename files window: the app's disc images with the name each would get, the naming template, the selected
game's pictures (a click cycles ICON0, PIC0 and PIC1) and a translation to use as the title in the new name, and
Rename all. What the standalone Bazzite UMD File Renamer's window did, on the folders this app already knows."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from urllib.parse import quote

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from bc250_core import window_title
from bc250_core.widgets import hint_label

from . import style
from .games import Game
from .renamer import NamingTemplate, formatted_name, old_template_index, rename_file

# The images a click on the picture cycles through.
PREVIEW_IMAGES = ("ICON0.PNG", "PIC0.PNG", "PIC1.PNG")
TRANSLATE_URL = "https://translate.google.com/?sl=auto&tl=en&text={text}"
TEMPLATE_KEY = "rename_template"


class RenameDialog(QDialog):
    """*games*: the renamable disc images (renamer.renamable); *settings*: the app's store, for the template.
    renamed says whether anything changed on disk, so the caller knows to look again."""

    def __init__(self, games: list[Game], settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle(window_title("Rename files"))
        self.resize(900, 560)
        self.games = list(games)
        self.settings = settings
        self.translations: dict[Path, str] = {}
        self.renamed = False
        self._preview = 0

        index = int(self.settings.get(TEMPLATE_KEY))
        if index < 0:                                   # never chosen here: the standalone app's choice, adopted
            old = old_template_index()
            index = old if old is not None else 0
            self.settings.set(TEMPLATE_KEY, index if 0 <= index < len(NamingTemplate) else 0)
        self.template_combo = QComboBox()
        for template in NamingTemplate:
            self.template_combo.addItem(template.value)
        self.template_combo.setCurrentIndex(index if 0 <= index < len(NamingTemplate) else 0)
        self.template_combo.currentIndexChanged.connect(self._template_changed)

        top = QHBoxLayout()
        label = QLabel("Naming:")
        label.setStyleSheet("font-weight:700;")
        top.addWidget(label)
        top.addWidget(self.template_combo)
        top.addStretch(1)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "Title", "Version", "File name", "New name"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        head = self.table.horizontalHeader()
        for column, mode in enumerate((QHeaderView.ResizeMode.ResizeToContents,
                                       QHeaderView.ResizeMode.ResizeToContents,
                                       QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch,
                                       QHeaderView.ResizeMode.Stretch)):
            head.setSectionResizeMode(column, mode)
        self.table.itemSelectionChanged.connect(self._selection_changed)

        self.picture = QLabel()
        self.picture.setFixedSize(180, 100)
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setToolTip("Click to cycle through ICON0, PIC0 and PIC1")
        self.picture.mousePressEvent = self._cycle_picture  # type: ignore[method-assign]
        self.translation_edit = QLineEdit()
        self.translation_edit.setPlaceholderText("Type a translation to use it as the title in the new name")
        self.translation_edit.textEdited.connect(self._translation_edited)
        self.translate_button = QPushButton("Translate")
        self.translate_button.setToolTip("Open Google Translate for the selected title")
        self.translate_button.clicked.connect(self._open_translate)
        details = QHBoxLayout()
        details.addWidget(self.picture)
        details.addWidget(self.translation_edit, 1)
        details.addWidget(self.translate_button)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.rename_button = style.primary_button("Rename all", "Rename every file to the name in New name")
        self.rename_button.clicked.connect(self.rename_all)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(self.status, 1)
        buttons.addWidget(self.rename_button)
        buttons.addWidget(close_button)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(hint_label("The new name comes from the game's own PARAM.SFO. A renamed game that is in Game "
                                 "Mode needs Update Game Mode afterwards: its shortcut names the file."))
        lay.addWidget(self.table, 1)
        lay.addLayout(details)
        lay.addLayout(buttons)
        style.apply(self)
        self._fill_table()
        if self.games:
            self.table.selectRow(0)

    # --- State ------------------------------------------------------------------------------------------------

    def template(self) -> NamingTemplate:
        return NamingTemplate.from_index(self.template_combo.currentIndex())

    def new_name(self, game: Game) -> str:
        return formatted_name(game, self.template(), self.translations.get(game.file, ""))

    def _fill_table(self) -> None:
        self.table.setRowCount(len(self.games))
        for row, game in enumerate(self.games):
            for column, text in enumerate((game.disc_id, game.title, game.version, game.file.name,
                                           self.new_name(game) + game.file.suffix)):
                self.table.setItem(row, column, QTableWidgetItem(text))
        self.rename_button.setEnabled(bool(self.games))
        self.translation_edit.setEnabled(bool(self.games))
        self.translate_button.setEnabled(bool(self.games))

    def _show_new_names(self) -> None:
        for row, game in enumerate(self.games):
            self.table.item(row, 4).setText(self.new_name(game) + game.file.suffix)

    def chosen(self) -> Game | None:
        rows = self.table.selectionModel().selectedRows()
        return self.games[rows[0].row()] if rows else None

    def _template_changed(self, index: int) -> None:
        self.settings.set(TEMPLATE_KEY, index)
        self._show_new_names()

    def _selection_changed(self) -> None:
        self._preview = 0
        game = self.chosen()
        self.translation_edit.setText(self.translations.get(game.file, "") if game else "")
        self._show_picture()

    def _translation_edited(self, text: str) -> None:
        game = self.chosen()
        if game is None:
            return
        self.translations[game.file] = text
        rows = self.table.selectionModel().selectedRows()
        self.table.item(rows[0].row(), 4).setText(self.new_name(game) + game.file.suffix)

    def _open_translate(self) -> None:
        game = self.chosen()
        if game is not None:
            QDesktopServices.openUrl(QUrl(TRANSLATE_URL.format(text=quote(game.title))))

    def _cycle_picture(self, _event) -> None:
        self._preview = (self._preview + 1) % len(PREVIEW_IMAGES)
        self._show_picture()

    def _show_picture(self) -> None:
        game = self.chosen()
        data = game.picture(PREVIEW_IMAGES[self._preview]) if game else None
        if not data:
            self.picture.setPixmap(QPixmap())
            self.picture.setText("—" if game is None else PREVIEW_IMAGES[self._preview].partition(".")[0] + "?")
            return
        self.picture.setText("")
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        self.picture.setPixmap(pixmap.scaled(self.picture.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))

    # --- The rename -------------------------------------------------------------------------------------------

    def rename_all(self) -> None:
        done = failed = 0
        for row, game in enumerate(self.games):
            new = rename_file(game.file, self.new_name(game))
            if new is None:
                failed += 1
                self.table.item(row, 3).setToolTip("Not renamed: another file already has that name.")
                continue
            if new != game.file:
                done += 1
                self.renamed = True
                self.translations.pop(game.file, None)
                self.games[row] = replace(game, file=new)
                self.table.item(row, 3).setText(new.name)
                self.table.item(row, 3).setToolTip("")
        text = f"{done} file(s) renamed."
        if failed:
            text += f" {failed} not renamed: another file already has that name."
        self.status.setStyleSheet("font-weight:600;color:#c62828;" if failed else "font-weight:600;")
        self.status.setText(text)
        self._show_new_names()
