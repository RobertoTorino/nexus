# SPDX-License-Identifier: GPL-3.0-or-later
"""The Rename files window (rename_dialog.py) on images made in a temp folder: the table with the new names, the
template (remembered, and adopted from the standalone app once), the translation, the pictures, and Rename all with
a name that is already taken."""

from __future__ import annotations

import pytest

from conftest import game_pictures, make_disc

from ppsspp_manager import INFO
from ppsspp_manager.games import read_disc
from ppsspp_manager.main_window import PpssppSettings
from ppsspp_manager.rename_dialog import RenameDialog
from ppsspp_manager.renamer import NamingTemplate, renamable


@pytest.fixture
def settings(qapp):
    return PpssppSettings(INFO)


def _games(tmp_path):
    make_disc(tmp_path / "download (1).iso", "Ever17", "ULJM05437", "1.01", pictures=True)
    make_disc(tmp_path / "b.cso", "Lumines", "ULUS10002", cso=True)
    return renamable([read_disc(tmp_path / "download (1).iso"), read_disc(tmp_path / "b.cso")])


def test_the_table_and_the_template(qapp, settings, tmp_path):
    dialog = RenameDialog(_games(tmp_path), settings)
    assert dialog.table.rowCount() == 2
    assert [dialog.table.item(0, c).text() for c in range(5)] == \
        ["ULJM05437", "Ever17", "1.01", "download (1).iso", "ULJM05437 - Ever17.iso"]
    assert dialog.table.item(1, 4).text() == "ULUS10002 - Lumines.cso"          # the extension stays the file's
    dialog.template_combo.setCurrentIndex(NamingTemplate.TITLE_BRACKET_ID.index)
    assert dialog.table.item(0, 4).text() == "Ever17 [ULJM05437].iso"
    assert settings.get("rename_template") == NamingTemplate.TITLE_BRACKET_ID.index     # remembered
    dialog.close()
    dialog = RenameDialog(_games(tmp_path), settings)                           # and used the next time
    assert dialog.template() is NamingTemplate.TITLE_BRACKET_ID
    dialog.close()


def test_the_standalones_template_is_adopted_once(qapp, settings, tmp_path, monkeypatch):
    ini = tmp_path / "config" / "bazzite-umd-file-renamer" / "bazzite-umd-file-renamer.ini"
    ini.parent.mkdir(parents=True)
    ini.write_text("[ui]\nnamingTemplate=5\n", encoding="utf-8")
    dialog = RenameDialog(_games(tmp_path), settings)
    assert dialog.template() is NamingTemplate.TITLE_ONLY
    assert settings.get("rename_template") == NamingTemplate.TITLE_ONLY.index
    dialog.close()
    settings.set("rename_template", 0)                                          # a choice here wins from then on
    dialog = RenameDialog(_games(tmp_path), settings)
    assert dialog.template() is NamingTemplate.ID_TITLE
    dialog.close()


def test_translation_and_pictures(qapp, settings, tmp_path):
    dialog = RenameDialog(_games(tmp_path), settings)
    dialog.table.selectRow(0)
    assert dialog.picture.pixmap() is not None and not dialog.picture.pixmap().isNull()   # ICON0.PNG
    dialog._cycle_picture(None)
    assert dialog.picture.text() == "PIC0?"                                     # the image has no PIC0.PNG
    dialog._cycle_picture(None)
    assert not dialog.picture.pixmap().isNull()                                 # PIC1.PNG
    dialog.translation_edit.setText("Ever17: The Out of Infinity")
    dialog._translation_edited(dialog.translation_edit.text())
    assert dialog.table.item(0, 4).text() == "ULJM05437 - Ever17 The Out of Infinity.iso"
    dialog.table.selectRow(1)
    assert dialog.translation_edit.text() == ""                                 # per game
    dialog.table.selectRow(0)
    assert dialog.translation_edit.text() == "Ever17: The Out of Infinity"
    dialog.close()


def test_rename_all(qapp, settings, tmp_path):
    games = _games(tmp_path)
    dialog = RenameDialog(games, settings)
    dialog.rename_all()
    assert dialog.renamed and dialog.status.text() == "2 file(s) renamed."
    assert (tmp_path / "ULJM05437 - Ever17.iso").is_file() and (tmp_path / "ULUS10002 - Lumines.cso").is_file()
    assert dialog.table.item(0, 3).text() == "ULJM05437 - Ever17.iso"
    dialog.rename_all()                                                         # the same names again: all quiet
    assert dialog.status.text() == "0 file(s) renamed."
    dialog.close()


def test_a_name_that_is_taken(qapp, settings, tmp_path):
    games = _games(tmp_path)
    (tmp_path / "ULJM05437 - Ever17.iso").write_bytes(b"in the way")
    dialog = RenameDialog(games, settings)
    dialog.rename_all()
    assert "1 not renamed: another file already has that name." in dialog.status.text()
    assert (tmp_path / "download (1).iso").is_file()                            # left as it was
    assert "another file" in dialog.table.item(0, 3).toolTip()
    assert (tmp_path / "ULUS10002 - Lumines.cso").is_file()                     # the other one renamed
    dialog.close()


def test_without_pictures_the_label_says_which(qapp, settings, tmp_path):
    make_disc(tmp_path / "bare.iso", "Bare", "ULUS00003")
    dialog = RenameDialog(renamable([read_disc(tmp_path / "bare.iso")]), settings)
    dialog.table.selectRow(0)
    assert dialog.picture.text() == "ICON0?"
    assert game_pictures()                                                      # the fixtures do make pictures
    dialog.close()
