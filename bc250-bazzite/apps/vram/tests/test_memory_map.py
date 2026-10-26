# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import replace

from PyQt6.QtCore import QPointF

from vram_manager import system
from vram_manager.main_window import MainWindow
from vram_manager.memory_map import MemoryMap, gtt_ceiling, gtt_text, ram_layout, swap_rows
from vram_manager.system import TOTAL_MIB, Usage


def test_usage_of_the_owner_board(sys_root, proc_root):
    u = system.read_usage(sys_root, proc_root)
    assert (u.vram_used_mib, u.gtt_used_mib, u.ram_available_mib) == (924, 280, 3022)
    (z,) = u.zram
    assert (z.name, z.size_mib, z.stored_mib, z.ram_mib, z.algorithm) == ("zram0", 4824, 2267, 662, "zstd")
    assert round(z.ratio, 1) == 3.4
    assert (u.zswap_pool_mib, u.zswap_stored_mib, u.zswap_max_pool_percent, u.zswap_compressor) == (0, 0, 20, "zstd")
    assert u.disk_swap_size_mib == 0


def test_usage_with_zswap_and_disk_swap(sys_root, proc_root):
    (proc_root / "swaps").write_text("Filename\tType\tSize\tUsed\tPriority\n/var/swap/swapfile file 8388604 1048576 -2\n")
    (proc_root / "meminfo").write_text("MemTotal: 9882080 kB\nMemAvailable: 3094976 kB\nZswap: 409600 kB\n"
                                       "Zswapped: 1228800 kB\n")
    u = system.read_usage(sys_root, proc_root)
    assert u.zram == () and (u.disk_swap_size_mib, u.disk_swap_used_mib) == (8191, 1024)
    assert (u.zswap_pool_mib, u.zswap_stored_mib) == (400, 1200)


def test_usage_without_files(tmp_path):
    u = system.read_usage(tmp_path / "sys", tmp_path / "proc")
    assert u == Usage()


def test_layout_adds_up_to_the_16_gb(sys_root, proc_root):
    memory, usage = system.read_memory(sys_root, proc_root), system.read_usage(sys_root, proc_root)
    parts = ram_layout(memory, usage)
    assert [p.key for p in parts] == ["vram_used", "vram_free", "gtt", "zram", "used", "available", "firmware"]
    assert sum(p.mib for p in parts) == TOTAL_MIB
    by_key = {p.key: p.mib for p in parts}
    assert (by_key["vram_used"], by_key["vram_free"], by_key["gtt"], by_key["zram"]) == (924, 5220, 280, 662)
    assert by_key["available"] == 3022 and by_key["firmware"] == TOTAL_MIB - 6144 - 9650
    assert "framebuffers" in parts[0].tip and "2.2 GiB" in {p.key: p for p in parts}["zram"].tip


def test_layout_without_usage_and_without_figures(sys_root, proc_root, tmp_path):
    memory = system.read_memory(sys_root, proc_root)
    assert [p.key for p in ram_layout(memory)] == ["vram", "ram", "firmware"]
    assert ram_layout(system.read_memory(tmp_path / "none", tmp_path / "none")) == []


def test_used_parts_never_exceed_what_is_used(sys_root, proc_root):
    memory = system.read_memory(sys_root, proc_root)
    usage = replace(system.read_usage(sys_root, proc_root), ram_available_mib=9500, gtt_used_mib=5000)
    parts = {p.key: p.mib for p in ram_layout(memory, usage)}
    assert parts["gtt"] == 150 and "zram" not in parts and parts["used"] == 0
    assert sum(parts.values()) == TOTAL_MIB


def test_preview_of_the_next_boot(sys_root, proc_root):
    memory = system.read_memory(sys_root, proc_root)
    parts = ram_layout(memory, split_mib=4096)
    assert [(p.key, p.mib) for p in parts][:2] == [("preview_vram", 4096), ("preview_ram", 9650 + 2048)]
    assert sum(p.mib for p in parts) == TOTAL_MIB
    assert gtt_ceiling(memory, 4096) == 11698                 # ttm.pages_limit 11.5 GiB stays; the RAM is lower
    assert gtt_ceiling(memory, 8192) == 7602
    default = replace(memory, ttm_on_cmdline=False)
    assert gtt_ceiling(default, 4096) == 11698 // 2           # the kernel's default: half the RAM
    assert gtt_ceiling(memory) == 9650


def test_gtt_and_swap_texts(sys_root, proc_root):
    memory, usage = system.read_memory(sys_root, proc_root), system.read_usage(sys_root, proc_root)
    first, second = gtt_text(memory, usage)
    assert first == "GTT: the GPU may borrow up to 9.4 GiB of the RAM (it borrows 280 MiB now)"
    assert "above the RAM" in second
    (zram, zswap) = swap_rows(memory, usage)
    assert zram[0] == "zram0: 2.2 GiB of pages in 662 MiB of RAM (zstd, 3.4×), swap size 4.7 GiB"
    assert zswap[0].startswith("zswap: off. That is usual with zram") and zswap[2:4] == (0, 0)


def test_swap_rows_for_zswap_and_disk(sys_root, proc_root):
    memory = replace(system.read_memory(sys_root, proc_root), zram=False, zswap=True, disk_swap=True)
    usage = Usage(zswap_pool_mib=400, zswap_stored_mib=1200, zswap_max_pool_percent=20, zswap_compressor="zstd",
                  disk_swap_size_mib=8191, disk_swap_used_mib=1024)
    rows = swap_rows(memory, usage)
    assert rows[0][0] == "zswap: 1.2 GiB of pages in 400 MiB of RAM (zstd), pool up to 1.9 GiB (20% of the RAM)"
    assert rows[1][0] == "disk swap: 1.0 GiB used of 8.0 GiB"
    assert swap_rows(replace(memory, zswap=False, disk_swap=False), Usage())[0][0] == "No swap."


def test_widget_draws_and_explains(qapp, sys_root, proc_root):
    m = MemoryMap(system.read_memory(sys_root, proc_root))
    m.resize(860, m.height())
    m.set_usage(system.read_usage(sys_root, proc_root))
    plain = m.height()
    m.grab()                                                  # paints, and records where each tooltip is
    assert "VRAM in use: 924 MiB of the 6.0 GiB split" in m.tip_at(QPointF(10, 30))
    assert "GTT limit" in m.tip_at(QPointF(500, 60))
    m.set_preview(4096)
    assert m.preview == 4096 and m.height() > plain
    m.grab()
    m.set_preview(6144)                                       # the split it has now: no preview
    assert m.preview is None and m.height() == plain


def test_window_previews_the_picked_split(qapp, sys_root, proc_root):
    w = MainWindow(sys_root, proc_root, runner=lambda args: None)
    assert w.map.usage.vram_used_mib == 924 and w.map.preview is None and w.timer.isActive()
    w.combo.setCurrentIndex(w.combo.findData(4096))
    assert w.map.preview == 4096
    w.combo.setCurrentIndex(w.combo.findData(6144))
    assert w.map.preview is None
    dev = sys_root / "class/drm/card1/device"
    (dev / "mem_info_vram_used").write_text(str(3000 * system.MIB))
    w.refresh_usage()                                         # what the timer does every 2 s
    assert w.map.usage.vram_used_mib == 3000
    w.close()
    assert not w.timer.isActive()
