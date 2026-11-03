# SPDX-License-Identifier: GPL-3.0-or-later
"""The keep page as a window (keep_dialog.py; owner, 03-11-2026): every row ticked at first, unticking keeps it, the
total follows, Delete marked needs a row still marked."""

from __future__ import annotations

from PyQt6.QtWidgets import QDialog

from bc250_core import keep
from bc250_core.keep_dialog import KeepDialog


def test_the_rows_and_their_marks(qapp, tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "data.bin").write_bytes(b"\0" * 2048)
    items = [keep.Item("game", "The game's folder", (game,)), keep.Item("steam", "Its shortcut in Steam")]
    dialog = KeepDialog("Remove One", items)
    assert [b.text() for b in dialog.boxes] == ["The game's folder", "Its shortcut in Steam"]
    assert all(b.isChecked() for b in dialog.boxes) and items[0].size == 2048
    assert dialog.total.text() == "2 of 2 marked Delete, 2.0 KB" and dialog.delete_button.isEnabled()
    dialog.boxes[0].setChecked(False)
    assert not items[0].delete and items[1].delete and keep.chosen(items) == [items[1]]
    assert dialog.total.text() == "1 of 2 marked Delete"
    dialog.boxes[1].setChecked(False)
    assert not dialog.delete_button.isEnabled() and dialog.total.text() == "0 of 2 marked Delete"
    dialog.boxes[0].setChecked(True)
    assert dialog.delete_button.isEnabled()
    dialog.buttons.accepted.emit()
    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog.close()
