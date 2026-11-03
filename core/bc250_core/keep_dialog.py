# SPDX-License-Identifier: GPL-3.0-or-later
"""The keep page as a window of its own, for the BC250 suite's desktop apps (owner, 03-11-2026, from the Windows
Portable Suite's managers, 01-11-2026: before deleting anything, let the user decide what to keep): what would go,
a row each with its size, every row ticked (Delete) at first; unticking a row keeps it; Delete marked deletes the
rows still ticked, Cancel deletes nothing. The rows are core's keep.Item; the caller deletes what is chosen
(keep.chosen) off the window's thread."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QLabel, QVBoxLayout, QWidget

from . import keep


class KeepDialog(QDialog):
    """*items* are shown as they are and changed in place: a row's tick is its Delete mark. exec() answers Accepted
    for Delete marked (only with a row still marked), Rejected for Cancel."""

    def __init__(self, title: str, items: Sequence[keep.Item], parent: QWidget | None = None,
                 lead: str = "Untick what you want to keep. Nothing is deleted before you press Delete marked."):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self.items = list(items)
        keep.measure(self.items)
        self.boxes: list[QCheckBox] = []
        lay = QVBoxLayout(self)
        intro = QLabel(lead)
        intro.setWordWrap(True)
        lay.addWidget(intro)
        grid = QGridLayout()
        grid.setColumnStretch(0, 1)
        for row, item in enumerate(self.items):
            box = QCheckBox(item.label)
            box.setChecked(item.delete)
            box.toggled.connect(lambda on, it=item: self._mark(it, on))
            size = QLabel(keep.human(item.size) if item.paths and item.size >= 0 else "")
            size.setStyleSheet("color:palette(placeholder-text);")
            grid.addWidget(box, row, 0)
            grid.addWidget(size, row, 1)
            self.boxes.append(box)
        lay.addLayout(grid)
        self.total = QLabel()
        self.total.setStyleSheet("color:palette(placeholder-text);")
        lay.addWidget(self.total)
        self.buttons = QDialogButtonBox()
        self.delete_button = self.buttons.addButton("Delete marked", QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self._show_total()

    def _mark(self, item: keep.Item, on: bool) -> None:
        item.delete = on
        self._show_total()

    def _show_total(self) -> None:
        chosen = keep.chosen(self.items)
        freed = keep.total(self.items)
        self.total.setText(f"{len(chosen)} of {len(self.items)} marked Delete" + (f", {keep.human(freed)}" if freed
                                                                                   else ""))
        self.delete_button.setEnabled(bool(chosen))
