# SPDX-License-Identifier: GPL-3.0-or-later
import json

import pytest
from PyQt6.QtWidgets import QMessageBox

from vram_manager import cmos, main_window, privileged
from vram_manager.main_window import MainWindow
from dumps import BOARD_1, FakePort, bank


class Board:
    """Runs the helper's own code on a fake bank, as pkexec would run cmos.py."""

    def __init__(self):
        self.data = bank(BOARD_1)
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        bank2 = cmos.Bank(FakePort(self.data))
        try:
            data = cmos.do_read(bank2) if args == ["--read"] else cmos.do_set_uma(bank2, int(args[1]))
        except cmos.CmosError as exc:
            return privileged.Result(False, {}, str(exc))
        return privileged.Result(True, json.loads(json.dumps(data)), "")

    @property
    def uma(self):
        return cmos.Block(bytes(self.data[0x90:0xAC])).uma_mb


@pytest.fixture
def answer(monkeypatch):
    replies = {"value": QMessageBox.StandardButton.Yes}
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: replies["value"])
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text: warnings.append(text))
    replies["warnings"] = warnings
    return replies


def make(qapp, sys_root, proc_root, board):
    return MainWindow(sys_root, proc_root, runner=board)


def test_shows_the_board(qapp, sys_root, proc_root):
    w = make(qapp, sys_root, proc_root, Board())
    assert w.vram_box.value.text() == "6.0 GiB" and w.gtt_box.value.text() == "9.4 GiB"
    assert w.swap_box.value.text() == "zram"
    assert "GTT is capped at the RAM" in w.details.text() and "swappiness 10" in w.details.text()
    assert w.badge.text() == "6.0 GiB split"
    assert w.combo.currentData() == 6144
    assert w.apply_button.isEnabled() and not w.undo_button.isEnabled()
    w.close()


def test_apply_reboot_and_undo(qapp, sys_root, proc_root, answer, tmp_path):
    board = Board()
    w = make(qapp, sys_root, proc_root, board)
    w.combo.setCurrentIndex(main_window.SPLITS.index(4096))
    w.apply_split()
    assert board.calls == [["--set-uma", "4096"]] and board.uma == 4096
    assert w.badge.text() == "Reboot to apply"
    assert w.undo_button.isEnabled()
    backups = list((tmp_path / "data/bc250-memory-manager/backups").glob("cmos-*.json"))
    assert len(backups) == 1 and json.loads(backups[0].read_text())["before"]["uma_mb"] == 6144
    w.close()

    # Same boot: still pending.
    w = make(qapp, sys_root, proc_root, board)
    assert w.badge.text() == "Reboot to apply" and w.combo.currentData() == 4096
    w.close()

    # After a reboot into the new split.
    (proc_root / "sys/kernel/random/boot_id").write_text("boot-2\n")
    (sys_root / "class/drm/card1/device/mem_info_vram_total").write_text(str(4096 * 1024 * 1024))
    w = make(qapp, sys_root, proc_root, board)
    assert w.badge.text() == "4.0 GiB split"
    assert "4 GB split from the last change is active" in w.split_note.text()
    w.undo()
    assert board.uma == 6144 and w.badge.text() == "Reboot to apply"
    w.close()


def test_reboot_without_the_split(qapp, sys_root, proc_root, answer):
    board = Board()
    w = make(qapp, sys_root, proc_root, board)
    w.combo.setCurrentIndex(main_window.SPLITS.index(8192))
    w.apply_split()
    w.close()
    (proc_root / "sys/kernel/random/boot_id").write_text("boot-2\n")
    w = make(qapp, sys_root, proc_root, board)
    assert "kernel got 6.0 GiB" in w.split_note.text()
    w.close()


def test_cancel_writes_nothing(qapp, sys_root, proc_root, answer):
    answer["value"] = QMessageBox.StandardButton.No
    board = Board()
    w = make(qapp, sys_root, proc_root, board)
    w.combo.setCurrentIndex(0)
    w.apply_split()
    assert board.calls == [] and board.uma == 6144
    w.close()


def test_helper_error_is_shown(qapp, sys_root, proc_root, answer):
    board = Board()
    board.data[0x94] ^= 0xFF                            # a bad checksum: the helper refuses
    w = make(qapp, sys_root, proc_root, board)
    w.apply_split()
    assert "cannot be trusted" in answer["warnings"][0]
    assert w.badge.text() == "6.0 GiB split"
    w.close()


def test_read_cmos_saves_a_dump(qapp, sys_root, proc_root, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(main_window.TextDialog, "exec", lambda self: shown.append(self.terminal.toPlainText()))
    w = make(qapp, sys_root, proc_root, Board())
    w.read_cmos()
    assert "UMA_SIZE   6144 MB" in shown[0]
    dumps = list((tmp_path / "data/bc250-memory-manager/backups").glob("cmos-dump-*.txt"))
    assert len(dumps) == 1 and "bank 2:" in dumps[0].read_text()
    w.close()


def test_other_board_disables_the_actions(qapp, sys_root, proc_root):
    (sys_root / "class/dmi/id/board_name").write_text("Other Board\n")
    w = make(qapp, sys_root, proc_root, Board())
    assert not w.apply_button.isEnabled() and not w.read_button.isEnabled()
    assert "not a BC-250" in w.block_reason.text()
    w.close()
