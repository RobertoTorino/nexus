# SPDX-License-Identifier: GPL-3.0-or-later
"""The memory cards (memcards.py) on mymc++'s own test cards: what is found in PCSX2's folder, the saves on a card,
and every change. A change gives the card byte for byte what mymc++'s own tests expect of its command line (the
same checksums, with its clock fixed), so the backup, the copy and the replace around it change nothing in the
card; then what memcards.py adds: the backups, PCSX2 running, the space counted first, and the fixes in the kept
card code."""

from __future__ import annotations

import os
import struct
from datetime import datetime
from pathlib import Path

import pytest

from conftest import md5

from pcsx2_manager import memcards
from pcsx2_manager.memcards import CardError
from pcsx2_manager.mymc import ps2icon, ps2mc
from pcsx2_manager.mymc.ps2mc_dir import DF_PSX
from pcsx2_manager.mymc.save import format_max_drive, lzari, ps2save

REZ = "BESCES-50501REZ"
SYSTEM = "BEDATA-SYSTEM"
EMPTY_8MB = 8 * (1 << 20) // 512 * 528


# --- Where the cards are --------------------------------------------------------------------------------------

def _ini(home: Path, text: str) -> None:
    (home / "inis").mkdir(parents=True, exist_ok=True)
    (home / "inis" / "PCSX2.ini").write_text(text, encoding="utf-8")


def test_the_card_folder_and_the_slots(tmp_path):
    home = tmp_path / "PCSX2"
    assert memcards.card_folder(home) == home / "memcards"
    assert memcards.slot_cards(home) == {"Mcd001.ps2": 1, "Mcd002.ps2": 2}         # PCSX2's own names
    _ini(home, "[Folders]\nMemoryCards = cards\n[MemoryCards]\nSlot1_Filename = Rez.ps2\nSlot2_Enable = false\n")
    assert memcards.card_folder(home) == home / "cards"
    assert memcards.slot_cards(home) == {"Rez.ps2": 1}
    _ini(home, f"[Folders]\nMemoryCards = {tmp_path / 'elsewhere'}\n")
    assert memcards.card_folder(home) == tmp_path / "elsewhere"


def test_the_cards_pcsx2_lists(cards):
    (cards / "Mcd003.mcr").write_bytes(b"\0" * 131072)                  # a PS1 card
    (cards / "Folder.ps2").mkdir()                                     # a folder card: its superblock file
    (cards / "Folder.ps2" / "_pcsx2_superblock").write_bytes(b"")
    (cards / "NotACard.ps2").mkdir()                                   # a folder without one: not a card
    (cards / "Blank.ps2").write_bytes(b"\xff" * EMPTY_8MB)             # PCSX2's new card before a game formats it
    (cards / "mc01.ps2.20261016-090000.bak").write_bytes(b"")          # a backup and other files: not listed
    (cards / "notes.txt").write_text("")
    found = {c.name: c for c in memcards.find_cards(cards)}
    assert sorted(found) == ["Blank.ps2", "Folder.ps2", "Mcd003.mcr", "mc01.ps2", "mc02.ps2"]
    assert found["Folder.ps2"].error.startswith("A folder memory card")
    assert found["Mcd003.mcr"].error.startswith("A PS1 memory card")
    assert found["Blank.ps2"].error == "Blank.ps2 is not a formatted PS2 memory card."
    assert found["mc01.ps2"].readable and found["mc02.ps2"].readable
    assert memcards.find_cards(cards / "missing") == []


def test_the_saves_on_a_card(cards):
    card = memcards.read_card(cards / "mc01.ps2")
    assert card.ecc
    assert [(s.name, s.title, s.size, s.ps1) for s in card.saves] == [
        (REZ, "Ｒｅｚ", 54272, False),
        (SYSTEM, "Ｙｏｕｒ Ｓｙｓｔｅｍ Ｃｏｎｆｉｇｕｒａｔｉｏｎ", 5120, False)]
    assert card.saves[0].modified > 0
    assert (card.free, card.total) == (8268800, 8330240)
    empty = memcards.read_card(cards / "mc02.ps2")
    assert empty.saves == [] and empty.free == empty.total - 1024             # the root folder's cluster


# --- Changes, as mymc++'s own tests expect them ----------------------------------------------------------------

@pytest.mark.parametrize("file, expected", [
    ("BESCES-50501REZ.psu", "4085992c23fc38d6c4ece5303dc77e74"),
    ("BESCES-50501REZ.max", "0e2dd8d53f05f6debe7d93aa726fc6e6"),
    ("BESCES-50501REZ.sps", "9726ad34016df2586eb9663a12f9ba02"),
    ("BESCES-50501REZ.xps", "9726ad34016df2586eb9663a12f9ba02"),
    ("BESCES-50501REZ.cbs", "897b0fbd1965dc02a442e1723bd3df27"),
    ("BESCES-5050152455A.PSV", "2872c456bcb647e78aeb3ce29e718309"),
    ("BASLUS-006623030303030303041.PSV", "c9f26130a5de7548248a5fec80593a4d")])     # a PS1 save
def test_import_gives_mymcs_card(cards, mymc_data, fixed_time, file, expected):
    card = cards / "mc02.ps2"
    assert memcards.import_saves(card, [mymc_data / file]) == "1 save(s) written to mc02.ps2."
    assert md5(card) == expected
    backup, = memcards.backups(card)
    assert md5(backup) == md5(mymc_data / "mc02.ps2")                # the card as it was before


def test_a_ps1_save_is_listed_with_its_title(cards, mymc_data):
    memcards.import_saves(cards / "mc02.ps2", [mymc_data / "BASLUS-006623030303030303041.PSV"])
    save, = memcards.read_card(cards / "mc02.ps2").saves
    assert save.ps1
    assert save.title                                                 # from the PS1 header, Shift-JIS


def test_delete_gives_mymcs_card(cards):
    assert memcards.delete_saves(cards / "mc01.ps2", [REZ]) == "1 save(s) deleted from mc01.ps2."
    assert md5(cards / "mc01.ps2") == "143e640ccf3f22e48e1d1d4b10300d57"
    backup, = memcards.backups(cards / "mc01.ps2")
    assert [s.name for s in memcards.read_card(backup).saves] == [REZ, SYSTEM]        # the backup keeps it


def test_a_new_card_is_mymcs_format(cards, fixed_time):
    path = memcards.new_card(cards, "mc")
    assert path == cards / "mc.ps2"
    assert md5(path) == "18ab430278362e6e70ce7cda9081888f"


@pytest.mark.parametrize("suffix, expected", [(".psu", "d86c82e559c8250c894fbbc4405d8789"),
                                              (".max", "3f63d38668a0a5a5fa508ab8c3bb469a")])
def test_export_gives_mymcs_file(cards, tmp_path, suffix, expected):
    name = memcards.export_name(cards / "mc01.ps2", REZ, suffix)
    assert name == f"SCES-50501 Rez (DD5DAEA3){suffix}"
    target = memcards.export_save(cards / "mc01.ps2", REZ, tmp_path / name)
    assert md5(target) == expected
    assert memcards.backups(cards / "mc01.ps2") == []                 # reading needs no backup
    with pytest.raises(CardError, match="export as .psu or .max"):
        memcards.export_save(cards / "mc01.ps2", REZ, tmp_path / "rez.zip")


# --- What memcards.py adds ------------------------------------------------------------------------------------

def test_a_save_already_on_the_card_is_left_alone(cards, mymc_data):
    card = cards / "mc01.ps2"
    before = md5(card)
    text = memcards.import_saves(card, [mymc_data / "BESCES-50501REZ.psu"])
    assert text == ("0 save(s) written to mc01.ps2. Already on the card, left as they are: BESCES-50501REZ "
                    "(delete one first to replace it).")
    assert md5(card) == before and memcards.backups(card) == []     # not touched: no backup either


def test_copy_between_cards(cards):
    text = memcards.copy_saves(cards / "mc01.ps2", [REZ, SYSTEM], cards / "mc02.ps2")
    assert text == "2 save(s) written to mc02.ps2."
    assert [s.name for s in memcards.read_card(cards / "mc02.ps2").saves] == [REZ, SYSTEM]
    assert memcards.backups(cards / "mc01.ps2") == []                 # the source is only read
    with pytest.raises(CardError, match="another card"):
        memcards.copy_saves(cards / "mc01.ps2", [REZ], cards / "mc01.ps2")


def _small_card(path: Path, pages: int) -> Path:
    with open(path, "w+b") as f:
        ps2mc.ps2mc(f, True, (True, 512, 16, pages)).close()
    return path


def test_a_card_too_full_gets_nothing(cards):
    small = _small_card(cards / "small.ps2", 160)                      # 53 KB free; Rez takes 54
    before = md5(small)
    with pytest.raises(CardError, match="Not enough space on the card: 59 KB needed, 53 KB free."):
        memcards.copy_saves(cards / "mc01.ps2", [REZ, SYSTEM], small)   # SYSTEM alone would fit: neither
    assert md5(small) == before and memcards.backups(small) == []      # unchanged, and no backup of it left
    assert not list(cards.glob(".*.new"))                                # nor the copy it was made on
    memcards.copy_saves(cards / "mc01.ps2", [SYSTEM], small)
    assert [s.name for s in memcards.read_card(small).saves] == [SYSTEM]


def test_the_space_is_counted_as_the_card_uses_it(cards):
    """A save's folder and files in whole clusters, and the card's root folder growing a cluster for every two
    saves (a deleted save's slot used again first): exactly what the card then has less."""
    small = _small_card(cards / "small.ps2", 176)                      # 61 KB free
    memcards.copy_saves(cards / "mc01.ps2", [REZ], small)              # 53 KB and the root's second cluster
    assert memcards.read_card(small).free == 62464 - 55296
    memcards.copy_saves(cards / "mc01.ps2", [SYSTEM], small)            # 5 KB, in the root's free slot
    assert memcards.read_card(small).free == 62464 - 55296 - 5120
    memcards.delete_saves(small, [REZ])
    with open(small, "rb") as f:
        mc = ps2mc.ps2mc(f)
        assert memcards._root_growth(mc, 1) == 0 and memcards._root_growth(mc, 2) == 1024
        mc.close()


def test_format_keeps_the_size_and_kind(cards):
    text = memcards.format_card(cards / "mc01.ps2")
    backup, = memcards.backups(cards / "mc01.ps2")
    assert text == f"mc01.ps2 was formatted (8 MB); the saves it had are in {backup.name}."
    assert memcards.read_card(cards / "mc01.ps2").saves == []
    assert len(memcards.read_card(backup).saves) == 2
    pro = memcards.new_card(cards, "Pro.mc2")
    assert pro.stat().st_size == 8 * (1 << 20) and not memcards.read_card(pro).ecc       # no ECC
    memcards.format_card(pro)
    assert memcards.card_size(pro) == (8, False)


@pytest.mark.parametrize("size_mb", memcards.SIZES_MB)
def test_new_cards_of_every_size(cards, size_mb):
    path = memcards.new_card(cards, f"Card{size_mb}", size_mb)
    assert path.stat().st_size == size_mb * (1 << 20) // 512 * 528          # PCSX2's sizes, with ECC
    assert memcards.card_size(path) == (size_mb, True)
    card = memcards.read_card(path)
    assert card.readable and card.saves == [] and card.total > (size_mb - 1) * (1 << 20)
    if size_mb == 8:                                                    # every page's ECC: 6 s at 64 MB
        assert memcards.check_card(path)[0]


def test_new_card_names(cards):
    with pytest.raises(CardError, match="already exists"):
        memcards.new_card(cards, "mc01.ps2")
    for bad in ("", "  ", "a/b", ".hidden"):
        with pytest.raises(CardError, match="Give the card a name"):
            memcards.new_card(cards, bad)
    with pytest.raises(CardError, match="8, 16, 32, 64 MB"):
        memcards.new_card(cards, "Odd", 4)
    assert memcards.new_card(cards / "made", "First").parent == cards / "made"     # the folder is made too


def test_check_finds_a_damaged_page(cards):
    card = cards / "mc01.ps2"
    assert memcards.check_card(card) == (True, "mc01.ps2: no problems found.")
    with open(card, "r+b") as f:                                        # two bits in page 0x40: beyond ECC
        f.seek(0x40 * 528)
        byte = f.read(1)[0]
        f.seek(0x40 * 528)
        f.write(bytes([byte ^ 0x03]))
    ok, report = memcards.check_card(card)
    assert not ok and "1 page(s) do not match their ECC: 00040" in report


def test_backups_are_named_by_date_and_the_newest_kept(cards):
    card = cards / "mc02.ps2"
    times = iter(datetime(2026, 10, 16, 9, 0, s) for s in range(30))
    made = [memcards.backup(card, lambda: next(times)) for _ in range(memcards.BACKUPS_KEPT + 2)]
    assert made[0].name == "mc02.ps2.20261016-090000.bak"
    assert memcards.backups(card) == made[2:]
    same = datetime(2026, 10, 16, 10, 0, 0)
    first, second = memcards.backup(card, lambda: same), memcards.backup(card, lambda: same)
    assert (first.name, second.name) == ("mc02.ps2.20261016-100000.bak", "mc02.ps2.20261016-100000-2.bak")
    assert memcards.backups(card)[-2:] == [first, second]               # -2 after the first, not before
    third = memcards.backup(card, lambda: same)
    assert memcards.backups(card)[-3:] == [first, second, third]
    assert len(memcards.backups(card)) == memcards.BACKUPS_KEPT


def _process(proc: Path, pid: int, comm: str, state: str) -> None:
    folder = proc / str(pid)
    folder.mkdir(parents=True)
    (folder / "comm").write_text(comm + "\n")
    (folder / "stat").write_text(f"{pid} ({comm}) {state} 1 2 3\n")


def test_pcsx2_running(tmp_path):
    proc = tmp_path / "proc"
    _process(proc, 10, "bash", "S")
    assert not memcards.pcsx2_running(proc)
    _process(proc, 11, "pcsx2-qt", "Z")                                 # finished, not collected yet
    assert not memcards.pcsx2_running(proc)
    _process(proc, 12, "pcsx2-qt", "S")
    assert memcards.pcsx2_running(proc)


def test_nothing_is_written_while_pcsx2_runs(cards, mymc_data, monkeypatch):
    monkeypatch.setattr(memcards, "pcsx2_running", lambda: True)
    card = cards / "mc01.ps2"
    before = md5(card)
    for change in (lambda: memcards.delete_saves(card, [REZ]), lambda: memcards.format_card(card),
                   lambda: memcards.import_saves(cards / "mc02.ps2", [mymc_data / "BESCES-50501REZ.psu"])):
        with pytest.raises(CardError, match="PCSX2 is running"):
            change()
    assert md5(card) == before and memcards.backups(card) == []


def test_files_that_are_not_saves(cards, tmp_path):
    junk = tmp_path / "junk.psu"
    junk.write_bytes(b"not a save at all" * 100)
    with pytest.raises(CardError, match="is not a save file this window knows"):
        memcards.import_saves(cards / "mc02.ps2", [junk])
    with pytest.raises(CardError, match="could not be read"):
        memcards.import_saves(cards / "mc02.ps2", [tmp_path / "missing.max"])
    assert memcards.backups(cards / "mc02.ps2") == []


# --- The fixes in the kept card code (mymc/__init__.py lists them) --------------------------------------------

def test_a_name_with_a_byte_over_127(cards):
    """mymc++ issue #11: such a name stopped the card being read."""
    card = cards / "mc02.ps2"
    with open(card, "r+b") as f:
        mc = ps2mc.ps2mc(f)
        mc.mkdir("/BESLES-12345\xffSAVE")
        mc.close()
    save, = memcards.read_card(card).saves
    assert save.name == "BESLES-12345\xffSAVE"
    memcards.delete_saves(card, [save.name])
    assert memcards.read_card(card).saves == []


def test_a_save_with_a_folder_in_it_is_deleted(cards):
    """_remove_dir added str and bytes for a folder inside a save."""
    card = cards / "mc01.ps2"
    with open(card, "r+b") as f:
        mc = ps2mc.ps2mc(f)
        mc.mkdir(f"/{REZ}/EXTRA")
        mc.close()
    memcards.delete_saves(card, [REZ])
    assert [s.name for s in memcards.read_card(card).saves] == [SYSTEM]


def test_a_failed_import_takes_out_what_it_wrote(cards, mymc_data):
    """The card code's own cleanup (without memcards.py counting the space first): the error is the card's, and no
    half save stays."""
    small = cards / "small.ps2"
    with open(small, "w+b") as f:                                       # 53 KB: Rez needs 54
        ps2mc.ps2mc(f, True, (True, 512, 16, 160)).close()
    before = md5(small)
    save = memcards._load(mymc_data / "BESCES-50501REZ.psu")
    with open(small, "r+b") as f:
        mc = ps2mc.ps2mc(f)
        with pytest.raises(ps2mc.io_error) as error:
            mc.import_save_file(save, False)
        assert error.value.errno == 28                                  # ENOSPC, not a TypeError
        assert mc.get_mode("/" + REZ) is None                           # what it wrote is gone
        mc.close()
    assert memcards.read_card(small).saves == [] and md5(small) != before


def _icon(frame_keys: list[int]) -> bytes:
    """A small PS2 icon: one shape of three vertices, frames with *frame_keys* keys, an uncompressed texture."""
    data = struct.pack("<IIIII", 0x010000, 1, 0x07, 0, 3)
    for _ in range(3):
        data += struct.pack("<hhhH", 0, 0, 0, 0) + struct.pack("<hhhHhhBBBB", 0, 0, 4096, 0, 0, 0, 255, 255, 255, 255)
    data += struct.pack("<IIfII", 1, 10, 1.0, 0, len(frame_keys))
    for keys in frame_keys:
        data += struct.pack("<II", 0, keys) + struct.pack("<ff", 0.0, 1.0) * keys
    return data + bytes(range(256)) * 128


def test_an_icon_frame_without_keys(capsys):
    """mymc++ issue #26: such a frame was read as 16 bytes, and the texture after it was lost."""
    icon = ps2icon.Icon(_icon([1, 1, 0, 0, 0, 0, 0, 1]))
    assert len(icon.texture) == 32768 and icon.texture[:4] == bytes([0, 1, 2, 3])
    assert [len(frame.keys) for frame in icon.frames] == [1, 1, 0, 0, 0, 0, 0, 1]
    assert capsys.readouterr().out == ""                                # no "too small" warning


def test_lzari_never_loads_a_module_from_the_path():
    assert lzari.mymcsup is None


def test_a_max_export_of_a_title_without_ascii(cards, tmp_path):
    """A title the substitution tables do not cover: ? in the .max header, where the export failed."""
    with open(cards / "mc01.ps2", "rb") as f:
        mc = ps2mc.ps2mc(f)
        save = mc.export_save_file("/" + REZ)
        mc.close()
    for i in range(len(save)):
        ent, data = save.get_file(i)
        if ent[8] == b"icon.sys":
            title = "漢字".encode("shift_jis")
            data = data[:0xC0] + title + b"\0" * (68 - len(title)) + data[0xC0 + 68:]
            save.set_file(i, ent, data)
    with open(tmp_path / "rez.max", "wb") as f:
        format_max_drive.save(save, f)
    with open(tmp_path / "rez.max", "rb") as f:
        assert f.read(0x58)[0x30:0x32] == b"??"                       # the header's title
    assert memcards._load(tmp_path / "rez.max").get_directory()[8] == REZ.encode()


def test_the_ecc_code_prints_nothing(cards, capsys):
    memcards.check_card(memcards.new_card(cards, "Fresh"))              # fresh pages: their ECC is corrected
    assert capsys.readouterr().out == ""


def test_card_sizes_no_card_has(tmp_path):
    odd = tmp_path / "odd.ps2"
    odd.write_bytes(b"\0" * 1000)
    with pytest.raises(CardError, match="a size no PS2 card has"):
        memcards.card_size(odd)
    assert os.path.getsize(odd) == 1000
    assert ps2save.PS2SaveFile                                          # (the module imports)
