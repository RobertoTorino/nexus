# SPDX-License-Identifier: GPL-3.0-or-later
from vram_manager import system


def test_owner_board(sys_root, proc_root):
    m = system.read_memory(sys_root, proc_root)
    assert (m.vram_mib, m.gtt_mib, m.ram_mib) == (6144, 9650, 9650)
    assert m.ttm_limit_mib == 11776 and m.ttm_on_cmdline
    assert m.gtt_capped                                 # 11.5 GiB limit, GTT stops at the RAM
    assert (m.zram, m.zswap, m.disk_swap) == (True, False, False)
    assert m.swap_text == "zram"
    assert m.swappiness == 10 and m.boot_id == "boot-1"


def test_zswap_with_disk_and_default_limit(sys_root, proc_root):
    (proc_root / "swaps").write_text("Filename\tType\tSize\tUsed\tPriority\n/var/swap/swapfile file 16777212 0 -2\n")
    (sys_root / "module/zswap/parameters/enabled").write_text("Y\n")
    (sys_root / "module/ttm/parameters/pages_limit").write_text("1235260\n")
    (proc_root / "cmdline").write_text("rw quiet\n")
    m = system.read_memory(sys_root, proc_root)
    assert m.swap_text == "zswap + disk"
    assert not m.ttm_on_cmdline and not m.gtt_capped


def test_missing_files(tmp_path):
    m = system.read_memory(tmp_path / "sys", tmp_path / "proc")
    assert m.vram_mib is None and m.ram_mib is None and m.swap_text == "none"
    assert system.mib_text(None) == "—"
    assert system.mib_text(512) == "512 MiB" and system.mib_text(6144) == "6.0 GiB"
