# SPDX-License-Identifier: GPL-3.0-or-later
import json

import pytest
from PyQt6.QtWidgets import QMessageBox

from vram_manager import cmos, main_window, privileged
from vram_manager.main_window import MainWindow
from conftest import FakeOstree
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
    replies = {"value": QMessageBox.StandardButton.Yes, "questions": []}

    def question(_parent, _title, text, *a, **k):
        replies["questions"].append(text)
        return replies["value"]
    monkeypatch.setattr(QMessageBox, "question", question)
    warnings, infos = [], []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text: warnings.append(text))
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, text: infos.append(text))
    replies["warnings"], replies["infos"] = warnings, infos
    return replies


def make(qapp, sys_root, proc_root, board, ostree=None):
    return MainWindow(sys_root, proc_root, runner=board, commands=ostree or FakeOstree())


def test_shows_the_board(qapp, sys_root, proc_root):
    w = make(qapp, sys_root, proc_root, Board())
    assert w.vram_box.value.text() == "6.0 GiB" and w.gtt_box.value.text() == "9.4 GiB"
    assert w.swap_box.value.text() == "zram"
    assert w.ttm_box.value.text() == "11.5 GiB" and w.ttm_box.caption.text() == "ttm.pages_limit"
    assert w.gtt_box.caption.text() == "GTT: all the RAM"
    assert "above the RAM, so the GTT is all the RAM, 9.4 GiB" in w.ttm_box.toolTip()
    assert w.details.text() == "vm.swappiness 10"
    assert w.badge.text() == "6.0 GiB split"
    assert w.combo.currentData() == 6144
    assert not w.apply_button.isEnabled() and not w.undo_button.isEnabled()   # the split it has: nothing to apply
    assert w.ttm_combo.currentData() == 3014656 and not w.ttm_button.isEnabled()
    assert w.ttm_note.isHidden() and w.ttm_reason.isHidden()
    w.combo.setCurrentIndex(main_window.SPLITS.index(4096))
    w.ttm_combo.setCurrentIndex(w.ttm_combo.findData(None))
    assert w.apply_button.isEnabled() and w.ttm_button.isEnabled()
    assert "framebuffer pin failures" in w.split_info.text_ and "Manual" in w.ttm_info.text_
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
    assert not w.apply_button.isEnabled()                 # 4 GB is written already
    w.combo.setCurrentIndex(main_window.SPLITS.index(6144))
    assert w.apply_button.isEnabled()                     # back to the booted split: a write, as Undo is
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
    w.combo.setCurrentIndex(main_window.SPLITS.index(4096))
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


def test_ttm_apply_reboot_and_default(qapp, sys_root, proc_root, answer):
    ostree = FakeOstree()
    w = make(qapp, sys_root, proc_root, Board(), ostree)
    w.ttm_combo.setCurrentIndex(w.ttm_combo.findData(4194304))
    w.apply_ttm()
    assert ("The GTT stays at 9.4 GiB, all the RAM with this split: a limit above the RAM changes nothing until a "
            "smaller split.") in answer["questions"][0]
    assert ostree.calls[1] == ["rpm-ostree", "kargs", "--replace=ttm.pages_limit=4194304", "--unchanged-exit-77"]
    assert "ttm.pages_limit=4194304" in ostree.arguments and "3014656" not in ostree.arguments
    assert w.badge.text() == "Reboot to apply" and "16.0 GiB GTT limit is in the next boot" in w.ttm_note.text()
    assert "Reboot the board to use it" in w.ttm_note.text()
    assert not w.ttm_button.isEnabled()                   # 16 GiB is written: not again
    w.ttm_combo.setCurrentIndex(w.ttm_combo.findData(3014656))
    assert w.ttm_button.isEnabled()
    w.ttm_combo.setCurrentIndex(w.ttm_combo.findData(4194304))
    assert w.ttm_box.value.text() == "11.5 GiB" and w.ttm_box.caption.text() == "next boot 16.0 GiB"
    assert answer["infos"] == ["Done: the 16.0 GiB GTT limit is in the next boot's kernel arguments.\n\nReboot the "
                               "board to use it. The app does not reboot by itself: use the menu, or in a terminal: "
                               "systemctl reboot."]
    assert w.combo.currentData() == 6144 and not w.apply_button.isEnabled()  # the split is untouched
    w.close()

    # Same boot: still waiting, whatever the settings say.
    w = make(qapp, sys_root, proc_root, Board(), ostree)
    assert w.badge.text() == "Reboot to apply" and w.ttm_combo.currentData() == 4194304
    w.close()

    # After the reboot into the new arguments.
    (proc_root / "sys/kernel/random/boot_id").write_text("boot-2\n")
    (proc_root / "cmdline").write_text("BOOT_IMAGE=x rw ttm.pages_limit=4194304\n")
    (sys_root / "module/ttm/parameters/pages_limit").write_text("4194304\n")
    w = make(qapp, sys_root, proc_root, Board(), ostree)
    assert w.badge.text() == "6.0 GiB split"
    assert w.ttm_note.text() == ("The 16.0 GiB GTT limit from the last change is active. The GPU may borrow up to "
                                 "9.4 GiB of the RAM, all of it.")
    assert w.ttm_box.value.text() == "16.0 GiB" and w.ttm_box.caption.text() == "ttm.pages_limit"

    # Back to the kernel's default: the argument is removed.
    w.ttm_combo.setCurrentIndex(w.ttm_combo.findData(None))
    assert w.ttm_combo.currentData() is None
    w.apply_ttm()
    assert "The GTT then is about 4.7 GiB instead of 9.4 GiB now." in answer["questions"][-1]
    assert ostree.calls[-3] == ["rpm-ostree", "kargs", "--delete=ttm.pages_limit=4194304", "--unchanged-exit-77"]
    assert "ttm.pages_limit" not in ostree.arguments
    assert "kernel default GTT limit (half the RAM) is in the next boot" in w.ttm_note.text()
    assert w.ttm_box.caption.text() == "next boot: default"
    assert w.map.previewing and w.map.preview is None and w.map.preview_ttm is None
    w.close()


def test_ttm_reboot_without_the_limit(qapp, sys_root, proc_root, answer):
    ostree = FakeOstree()
    w = make(qapp, sys_root, proc_root, Board(), ostree)
    w.ttm_combo.setCurrentIndex(w.ttm_combo.findData(None))
    w.apply_ttm()
    w.close()
    (proc_root / "sys/kernel/random/boot_id").write_text("boot-2\n")
    ostree.arguments = "BOOT_IMAGE=x rw ttm.pages_limit=3014656"         # the board started the old deployment
    w = make(qapp, sys_root, proc_root, Board(), ostree)
    assert "but this boot has the 11.5 GiB GTT limit" in w.ttm_note.text()
    assert not w.badge.text() == "Reboot to apply"
    w.close()


def test_ttm_cancel_and_failure(qapp, sys_root, proc_root, answer):
    ostree = FakeOstree()
    w = make(qapp, sys_root, proc_root, Board(), ostree)
    answer["value"] = QMessageBox.StandardButton.No
    w.ttm_combo.setCurrentIndex(w.ttm_combo.findData(None))
    w.apply_ttm()
    assert len(ostree.calls) == 1 and "3014656" in ostree.arguments
    answer["value"] = QMessageBox.StandardButton.Yes
    ostree.error = "error: Transaction in progress: upgrade"
    w.apply_ttm()
    assert answer["warnings"] == ["rpm-ostree kargs failed: error: Transaction in progress: upgrade"]
    assert "3014656" in ostree.arguments and w.ttm_button.isEnabled()
    w.close()


def test_ttm_without_rpm_ostree(qapp, sys_root, proc_root):
    ostree = FakeOstree()
    ostree.error, ostree.code = "rpm-ostree is not installed.", privileged.NOT_INSTALLED
    w = make(qapp, sys_root, proc_root, Board(), ostree)
    assert not w.ttm_button.isEnabled() and "no rpm-ostree" in w.ttm_reason.text()
    w.ttm_combo.setCurrentIndex(w.ttm_combo.findData(None))
    assert not w.ttm_button.isEnabled()
    w.combo.setCurrentIndex(main_window.SPLITS.index(4096))
    assert w.apply_button.isEnabled()                                     # the split does not depend on it
    w.close()


def test_ttm_set_outside_the_app(qapp, sys_root, proc_root):
    ostree = FakeOstree("rw ttm.pages_limit=2000000")
    (proc_root / "cmdline").write_text("rw ttm.pages_limit=2000000\n")
    (sys_root / "module/ttm/parameters/pages_limit").write_text("2000000\n")
    w = make(qapp, sys_root, proc_root, Board(), ostree)
    assert w.ttm_combo.currentText() == "7.6 GiB, as set now" and w.ttm_combo.currentData() == 2000000
    assert w.ttm_combo.count() == len(main_window.kargs.PRESETS) + 1 and not w.map.previewing
    w.close()


def test_ttm_says_writing_while_rpm_ostree_runs(qapp, sys_root, proc_root, answer):
    """rpm-ostree takes a minute or two after the password dialog: the window must show it is busy meanwhile."""
    seen = []
    ostree = FakeOstree()
    inner = ostree.__call__

    def slow(cmd):
        if cmd[2].startswith("--replace"):
            w.writing_since -= 83                                       # as if 83 s had passed
            w.tick_writing()                                            # what the timer does every second
            seen.append((w.badge.text(), w.ttm_note.text(), w.ttm_button.isEnabled(), w.apply_button.isEnabled(),
                         w.writing_timer.isActive()))
        return inner(cmd)

    w = make(qapp, sys_root, proc_root, Board(), slow)
    w.ttm_combo.setCurrentIndex(w.ttm_combo.findData(4194304))
    w.apply_ttm()
    assert seen == [("Writing…", "<b>rpm-ostree is writing the next boot's kernel arguments, 83 s so far. This takes "
                     "a minute or two; the window answers again when it is done.</b>", False, False, True)]
    assert not w.writing_timer.isActive()
    assert w.badge.text() == "Reboot to apply" and not w.ttm_button.isEnabled() and not w.apply_button.isEnabled()
    w.ttm_combo.setCurrentIndex(w.ttm_combo.findData(None))
    assert w.ttm_button.isEnabled()
    w.close()


def test_profiles_write_what_differs(qapp, sys_root, proc_root, answer):
    """The board runs the Games profile (6 GB, 11.5 GiB): Games is off, Defaults writes both; then Games again."""
    board, ostree = Board(), FakeOstree()
    w = make(qapp, sys_root, proc_root, board, ostree)
    assert not w.profile_buttons["games"].isEnabled() and w.profile_buttons["defaults"].isEnabled()
    assert w.profile_buttons["games"].toolTip() == "6 GB  (recommended for games) split, 11.5 GiB GTT limit"
    w.apply_profile("defaults")
    assert answer["questions"][-1].startswith("Write the 512 MB split to CMOS and the kernel default GTT limit "
                                              "(half the RAM) to the next boot's kernel arguments?\n\nOne password "
                                              "prompt for each.")
    assert board.calls == [["--set-uma", "512"]] and board.uma == 512
    assert ostree.calls[-3][2] == "--delete=ttm.pages_limit=3014656" and "ttm" not in ostree.arguments
    assert answer["infos"] == ["Done: the 512 MB split to CMOS and the kernel default GTT limit (half the RAM) to "
                               "the next boot's kernel arguments.\n\nReboot the board to use it. The app does not "
                               "reboot by itself: use the menu, or in a terminal: systemctl reboot."]
    assert w.badge.text() == "Reboot to apply" and w.combo.currentData() == 512
    assert w.ttm_combo.currentData() is None
    assert not w.profile_buttons["defaults"].isEnabled() and w.profile_buttons["games"].isEnabled()
    w.apply_profile("games")
    assert board.uma == 6144 and "ttm.pages_limit=3014656" in ostree.arguments
    assert not w.profile_buttons["games"].isEnabled() and w.profile_buttons["defaults"].isEnabled()
    w.close()


def test_profile_asks_once_and_stops_on_no(qapp, sys_root, proc_root, answer):
    board, ostree = Board(), FakeOstree()
    w = make(qapp, sys_root, proc_root, board, ostree)
    answer["value"] = QMessageBox.StandardButton.No
    w.apply_profile("defaults")
    assert len(answer["questions"]) == 1 and board.calls == [] and len(ostree.calls) == 1
    # Without rpm-ostree the profile still writes the split, and says only that.
    missing = FakeOstree()
    missing.error, missing.code = "rpm-ostree is not installed.", privileged.NOT_INSTALLED
    w = make(qapp, sys_root, proc_root, board, missing)
    answer["value"] = QMessageBox.StandardButton.Yes
    assert w.profile_steps("defaults") == ["the 512 MB split to CMOS"]
    w.apply_profile("defaults")
    assert board.uma == 512 and "It needs your password." in answer["questions"][-1]
    w.close()
