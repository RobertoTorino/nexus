# SPDX-License-Identifier: GPL-3.0-or-later
"""The Memory cards tab (memcard_page.py) on mymc++'s test cards: the cards with their slots from PCSX2's settings,
the slot chosen in the tab, the saves and the icon's picture, every action through the page's worker, and nothing
offered that would write while PCSX2 runs."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QMessageBox

from pcsx2_manager import memcards, pcsx2_settings
from pcsx2_manager.memcard_page import MemcardPage, NewCardDialog, shown

REZ = "BESCES-50501REZ"


def _wait(page, qapp) -> None:
    deadline = time.monotonic() + 30
    while (page.worker.running or page.pictures.running) and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()


def _home(tmp_path: Path, cards: Path, slots: dict[int, str]) -> Path:
    """PCSX2's folder with its memory card folder *cards* and the slots as PCSX2.ini names them."""
    home = tmp_path / "PCSX2"
    (home / "inis").mkdir(parents=True)
    lines = ["[Folders]", f"MemoryCards = {cards}", "", "[MemoryCards]"]
    for slot in (1, 2):
        lines += [f"Slot{slot}_Enable = {'true' if slot in slots else 'false'}"]
        if slot in slots:
            lines += [f"Slot{slot}_Filename = {slots[slot]}"]
    (home / "inis" / "PCSX2.ini").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return home


@pytest.fixture
def page(qapp, cards, tmp_path):
    (cards / "Mcd002.mcr").write_bytes(b"\0" * 131072)
    window = MemcardPage(_home(tmp_path, cards, {1: "mc01.ps2", 2: "Mcd002.mcr"}), running=lambda: False)
    yield window
    _wait(window, qapp)
    window.stop()


def test_the_cards_and_the_saves(page, qapp):
    assert page.folder == page.cards[0].path.parent
    assert [page.card_combo.itemText(i) for i in range(page.card_combo.count())] == \
        ["Mcd002.mcr  (slot 2)", "mc01.ps2  (slot 1)", "mc02.ps2"]
    assert page.card().name == "mc01.ps2" and page.slot_combo.currentData() == 1        # slot 1's card first
    assert [page.table.item(r, 0).text() for r in range(page.table.rowCount())] == \
        ["Rez", "Your System Configuration"]                           # full-width letters shown as such
    assert page.table.item(0, 1).text() == REZ and page.table.item(0, 2).text() == "53 KB"
    assert page.space.text() == "8,075 KB free of 8,135 KB"
    assert "Rez" in page.details.text() and "A PS2 save" in page.details.text()
    _wait(page, qapp)
    assert not page.picture.pixmap().isNull()                         # Rez's icon
    page.table.selectRow(1)
    _wait(page, qapp)
    assert page.picture.text() == "No icon"                           # the system configuration has none
    page.card_combo.setCurrentIndex(0)
    assert page.status.text().startswith("A PS1 memory card") and page.slot_combo.currentData() == 2
    assert not page.import_button.isEnabled() and not page.format_button.isEnabled()
    page.card_combo.setCurrentIndex(2)
    assert page.status.text() == "mc02.ps2 is empty." and page.table.rowCount() == 0
    assert page.slot_combo.currentData() == 0


def test_the_slot_is_chosen_in_the_tab(page, qapp):
    """A card into a slot, which takes it from the card there; out of its slot; written in PCSX2's settings and
    shown in the list; not while PCSX2 runs."""
    page.card_combo.setCurrentIndex(2)                                # mc02, in no slot
    page.slot_combo.setCurrentIndex(page.slot_combo.findData(1))
    assert page.status.text() == "mc02.ps2 is in slot 1 now."
    assert memcards.slot_cards(page.pcsx2_home) == {"mc02.ps2": 1, "Mcd002.mcr": 2}       # mc01 left slot 1
    assert [page.card_combo.itemText(i) for i in range(3)] == ["Mcd002.mcr  (slot 2)", "mc01.ps2",
                                                               "mc02.ps2  (slot 1)"]
    assert page.card().name == "mc02.ps2"
    ini = pcsx2_settings.IniFile(pcsx2_settings.settings_path(page.pcsx2_home).read_text())
    assert ini.get("MemoryCards", "Slot1_Filename") == "mc02.ps2" and ini.get("Folders", "MemoryCards")
    page.slot_combo.setCurrentIndex(page.slot_combo.findData(0))
    assert page.status.text() == "mc02.ps2 is in no slot now."
    assert memcards.slot_cards(page.pcsx2_home) == {"Mcd002.mcr": 2}
    assert ini.get("MemoryCards", "Slot1_Enable") == "true"           # the file before: now false
    ini = pcsx2_settings.IniFile(pcsx2_settings.settings_path(page.pcsx2_home).read_text())
    assert ini.get("MemoryCards", "Slot1_Enable") == "false" and ini.get("MemoryCards", "Slot1_Filename") == "mc02.ps2"
    page.running = lambda: True
    page.slot_combo.setCurrentIndex(page.slot_combo.findData(2))
    assert page.status.text().startswith("PCSX2 is running") and page.slot_combo.currentData() == 0
    assert memcards.slot_cards(page.pcsx2_home) == {"Mcd002.mcr": 2}


def test_import_export_copy_delete(page, qapp, mymc_data, tmp_path):
    page.card_combo.setCurrentIndex(2)                                # mc02, empty
    page.import_files([mymc_data / "BESCES-50501REZ.max"])
    _wait(page, qapp)
    assert page.status.text() == "1 save(s) written to mc02.ps2."
    assert page.card().name == "mc02.ps2" and page.table.rowCount() == 1
    page.table.selectAll()
    page.export_to(page.chosen(), tmp_path / "one.max")
    _wait(page, qapp)
    assert (tmp_path / "one.max").is_file() and page.status.text().startswith("Exported to")
    page.export_to(page.chosen(), tmp_path, ".psu")
    _wait(page, qapp)
    assert (tmp_path / "SCES-50501 Rez (DD5DAEA3).psu").is_file()
    page.export_to(page.chosen(), tmp_path, ".psu")                   # again: kept, not written over
    _wait(page, qapp)
    assert "Already there, left as they are: SCES-50501 Rez (DD5DAEA3).psu." in page.status.text()

    page.card_combo.setCurrentIndex(1)                                # mc01
    page.table.selectRow(1)
    page.copy_to(page.chosen(), page.cards[2])
    _wait(page, qapp)
    assert page.status.text() == "1 save(s) written to mc02.ps2."
    assert page.card().name == "mc01.ps2"                             # the source stays chosen
    page.table.selectRow(0)
    page.delete(page.chosen())
    _wait(page, qapp)
    assert page.status.text() == "1 save(s) deleted from mc01.ps2."
    assert [s.name for s in page.card().saves] == ["BEDATA-SYSTEM"]
    assert len(memcards.backups(page.card().path)) == 1


def test_new_card_format_and_check(page, qapp):
    page.new_card("Spare", 16)
    _wait(page, qapp)
    assert page.status.text().startswith("Spare.ps2 was made (16 MB). Slot puts it")
    assert page.card().name == "Spare.ps2" and page.space.text().startswith("16,")
    assert page._free_name() == "Mcd001.ps2"
    page.card_combo.setCurrentIndex([c.name for c in page.cards].index("mc01.ps2"))
    page.on_check()
    _wait(page, qapp)
    assert page.status.text() == "mc01.ps2: no problems found."
    page.format_card()
    _wait(page, qapp)
    assert page.status.text().startswith("mc01.ps2 was formatted (8 MB)")
    assert page.table.rowCount() == 0
    page.new_card("Spare", 8)
    _wait(page, qapp)
    assert page.status.text() == "Spare.ps2 already exists."
    assert "color:#c62828" in page.status.styleSheet()


def test_new_card_dialog(qapp):
    window = NewCardDialog("Mcd003.ps2")
    assert window.values() == ("Mcd003.ps2", 8)
    window.size_combo.setCurrentIndex(3)
    window.name_edit.setText("  Big.ps2 ")
    assert window.values() == ("Big.ps2", 64)
    window.close()


def test_nothing_written_while_pcsx2_runs(qapp, cards, tmp_path):
    running = [True]
    page = MemcardPage(_home(tmp_path, cards, {}), running=lambda: running[0])
    assert page.warning.text().startswith("PCSX2 is running")
    assert not page.import_button.isEnabled() and not page.delete_button.isEnabled()
    assert not page.copy_button.isEnabled() and not page.format_button.isEnabled()
    assert not page.slot_combo.isEnabled()
    assert page.export_button.isEnabled() and page.check_button.isEnabled()      # reading is fine
    before = memcards.read_card(cards / "mc01.ps2").saves
    page.delete(page.chosen())
    assert page.status.text().startswith("PCSX2 is running") and not page.worker.running
    assert memcards.read_card(cards / "mc01.ps2").saves == before
    running[0] = False
    page._update_buttons()
    assert page.import_button.isEnabled() and page.slot_combo.isEnabled() and page.warning.isHidden()
    page.stop()


def test_no_cards_yet(qapp, tmp_path):
    page = MemcardPage(tmp_path / "PCSX2", running=lambda: False)     # no settings file: PCSX2's own folder
    assert page.folder == tmp_path / "PCSX2" / "memcards" and page.card() is None
    assert page.status.text().startswith("No memory cards in")
    assert page.new_button.isEnabled() and not page.import_button.isEnabled() and not page.slot_combo.isEnabled()
    page.new_card("Mcd001", 8)
    _wait(page, qapp)
    assert page.card().name == "Mcd001.ps2" and (tmp_path / "PCSX2" / "memcards" / "Mcd001.ps2").is_file()
    assert page.slot_combo.currentData() == 1                         # PCSX2's own name for slot 1's card
    page.stop()


def test_titles_as_shown():
    assert shown("Ｙｏｕｒ Ｓｙｓｔｅｍ") == "Your System"
    assert shown("ファイナルファンタジー") == "ファイナルファンタジー"


def test_a_delete_asks_first(page, qapp, monkeypatch):
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or QMessageBox.StandardButton.No)
    page.on_delete()
    assert asked and asked[0].startswith("Delete 1 save(s) from mc01.ps2?") and page.table.rowCount() == 2
