# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings and data in a temp folder, and a fake /sys and /proc of a
BC-250 with a 6 GB split (as on the owner's boards), with the live figures of one of them: 924 MiB of VRAM and 280
MiB of GTT in use, 3 GiB of RAM available and zram holding 2.2 GiB in 663 MiB of RAM."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as the installer bundles it
sys.path.insert(0, str(Path(__file__).resolve().parent))

MIB = 1024 * 1024


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def settings_dir(tmp_path, monkeypatch):
    """The app keeps an .ini (AppInfo.settings_ini), so this also keeps the tests out of the Windows registry."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return tmp_path / "settings"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")


@pytest.fixture
def sys_root(tmp_path) -> Path:
    root = tmp_path / "sys"
    write(root / "class/dmi/id/board_name", "AMD BC-250")
    write(root / "class/dmi/id/bios_vendor", "American Megatrends Inc.")
    write(root / "class/dmi/id/bios_version", "P5.00")
    write(root / "class/dmi/id/bios_date", "05/03/2022")
    write(root / "kernel/security/lockdown", "[none] integrity confidentiality")
    dev = root / "class/drm/card1/device"
    write(dev / "mem_info_vram_total", str(6144 * MIB))
    write(dev / "mem_info_gtt_total", str(9650 * MIB))
    write(dev / "mem_info_vram_used", str(924 * MIB))
    write(dev / "mem_info_gtt_used", str(280 * MIB))
    write(root / "module/ttm/parameters/pages_limit", "3014656")
    write(root / "module/zswap/parameters/enabled", "N")
    write(root / "module/zswap/parameters/max_pool_percent", "20")
    write(root / "module/zswap/parameters/compressor", "zstd")
    write(root / "block/zram0/mm_stat", "2377252864 671759750 694964224        0 832544768     5198    50004    37212    61443")
    write(root / "block/zram0/comp_algorithm", "lzo-rle lzo lz4 lz4hc [zstd] deflate 842")
    return root


@pytest.fixture
def proc_root(tmp_path) -> Path:
    root = tmp_path / "proc"
    write(root / "meminfo", "MemTotal:        9882080 kB\nMemFree:  1000 kB\nMemAvailable:    3094976 kB\n"
                            "Zswap:                 0 kB\nZswapped:              0 kB")
    write(root / "swaps", "Filename\tType\tSize\tUsed\tPriority\n/dev/zram0  partition\t4940796\t2498340\t100")
    write(root / "cmdline", "BOOT_IMAGE=x rw mitigations=off ttm.pages_limit=3014656 zswap.enabled=0")
    write(root / "sys/vm/swappiness", "10")
    write(root / "sys/kernel/random/boot_id", "boot-1")
    return root
