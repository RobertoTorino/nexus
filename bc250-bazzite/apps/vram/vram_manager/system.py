# SPDX-License-Identifier: GPL-3.0-or-later
"""What the running system says about its memory, read without root from /sys and /proc: the VRAM split the
kernel got, the GTT it may lend the GPU, the TTM limit behind it, the RAM and the swap layout.

The swap checks are the ones of bazzite-test's test 14 and system score (zram and disk swap from /proc/swaps,
zswap from its module parameter). read_usage() adds what changes while the system runs, for the memory map: the
VRAM and GTT in use, the RAM available, what zram and zswap hold and what that costs in RAM."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

MIB = 1024 * 1024
PAGE = 4096
TOTAL_MIB = 16384                       # the BC-250's 16 GB of GDDR6, shared by the CPU and the GPU


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _int(text: str | None) -> int | None:
    try:
        return int(text) if text is not None else None
    except ValueError:
        return None


@dataclass(frozen=True)
class Memory:
    vram_mib: int | None                # the split the kernel got at boot
    gtt_mib: int | None                 # system RAM the GPU may borrow (GTT)
    ram_mib: int | None                 # MemTotal: what is left for the system
    ttm_limit_mib: int | None           # ttm.pages_limit, in MiB
    ttm_on_cmdline: bool
    zram: bool
    zswap: bool
    disk_swap: bool
    swappiness: int | None
    boot_id: str

    @property
    def gtt_capped(self) -> bool:
        """amdgpu caps GTT at the RAM on this APU, so a TTM limit above it has no effect."""
        return (self.ttm_limit_mib is not None and self.gtt_mib is not None
                and self.ttm_limit_mib > self.gtt_mib)

    @property
    def swap_text(self) -> str:
        parts = [name for name, on in (("zram", self.zram), ("zswap", self.zswap), ("disk", self.disk_swap)) if on]
        return " + ".join(parts) if parts else "none"


def gpu_device(sys_root: Path = Path("/sys")) -> Path | None:
    """The amdgpu device with VRAM figures (the last one, as bazzite-test's test 37 does)."""
    found = [p for p in sorted((sys_root / "class/drm").glob("card*/device")) if (p / "mem_info_vram_total").is_file()]
    return found[-1] if found else None


def read_memory(sys_root: Path = Path("/sys"), proc_root: Path = Path("/proc")) -> Memory:
    dev = gpu_device(sys_root)
    vram = _int(_read(dev / "mem_info_vram_total")) if dev else None
    gtt = _int(_read(dev / "mem_info_gtt_total")) if dev else None
    ram_kib = None
    for line in (_read(proc_root / "meminfo") or "").splitlines():
        if line.startswith("MemTotal:"):
            ram_kib = _int(line.split()[1])
    ttm = _int(_read(sys_root / "module/ttm/parameters/pages_limit"))
    names = [line.split()[0] for line in (_read(proc_root / "swaps") or "").splitlines()[1:] if line.split()]
    return Memory(
        vram_mib=vram // MIB if vram else None,
        gtt_mib=gtt // MIB if gtt else None,
        ram_mib=ram_kib // 1024 if ram_kib else None,
        ttm_limit_mib=ttm * PAGE // MIB if ttm else None,
        ttm_on_cmdline="ttm.pages_limit=" in (_read(proc_root / "cmdline") or ""),
        zram=any(Path(n).name.startswith("zram") for n in names),
        zswap=_read(sys_root / "module/zswap/parameters/enabled") in ("Y", "1"),
        disk_swap=any(not Path(n).name.startswith("zram") for n in names),
        swappiness=_int(_read(proc_root / "sys/vm/swappiness")),
        boot_id=_read(proc_root / "sys/kernel/random/boot_id") or "",
    )


@dataclass(frozen=True)
class Zram:
    name: str                           # "zram0"
    size_mib: int                       # the swap size it offers
    stored_mib: int                     # swapped-out pages it holds, uncompressed (mm_stat orig_data_size)
    ram_mib: int                        # the RAM that costs, compressed plus overhead (mm_stat mem_used_total)
    algorithm: str                      # "zstd"

    @property
    def ratio(self) -> float | None:
        return self.stored_mib / self.ram_mib if self.ram_mib else None


@dataclass(frozen=True)
class Usage:
    vram_used_mib: int | None = None
    gtt_used_mib: int | None = None     # RAM the GPU borrows now
    ram_available_mib: int | None = None
    zram: tuple[Zram, ...] = field(default_factory=tuple)
    zswap_pool_mib: int | None = None   # the RAM zswap's compressed cache takes (Zswap: in /proc/meminfo)
    zswap_stored_mib: int | None = None  # the pages it holds, uncompressed (Zswapped:)
    zswap_max_pool_percent: int | None = None
    zswap_compressor: str = ""
    disk_swap_size_mib: int = 0
    disk_swap_used_mib: int = 0


def _meminfo(proc_root: Path) -> dict[str, int]:
    """The /proc/meminfo fields, in KiB."""
    out = {}
    for line in (_read(proc_root / "meminfo") or "").splitlines():
        parts = line.replace(":", " ").split()
        if len(parts) >= 2 and parts[1].isdigit():
            out[parts[0]] = int(parts[1])
    return out


def _selected(text: str | None) -> str:
    """The [chosen] entry of a sysfs list such as "lzo lz4 [zstd]", or the text itself."""
    text = text or ""
    if "[" in text and "]" in text:
        return text[text.index("[") + 1:text.index("]")]
    return text.strip()


def read_usage(sys_root: Path = Path("/sys"), proc_root: Path = Path("/proc")) -> Usage:
    dev = gpu_device(sys_root)
    vram_used = _int(_read(dev / "mem_info_vram_used")) if dev else None
    gtt_used = _int(_read(dev / "mem_info_gtt_used")) if dev else None
    info = _meminfo(proc_root)
    zrams, disk_size, disk_used = [], 0, 0
    for line in (_read(proc_root / "swaps") or "").splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4 or not (parts[2].isdigit() and parts[3].isdigit()):
            continue
        name, size_kib, used_kib = Path(parts[0]).name, int(parts[2]), int(parts[3])
        if not name.startswith("zram"):
            disk_size, disk_used = disk_size + size_kib // 1024, disk_used + used_kib // 1024
            continue
        stat = (_read(sys_root / "block" / name / "mm_stat") or "").split()
        stored = _int(stat[0]) if len(stat) > 2 else None
        ram = _int(stat[2]) if len(stat) > 2 else None
        zrams.append(Zram(name, size_kib // 1024, (stored if stored is not None else used_kib * 1024) // MIB,
                          (ram or 0) // MIB, _selected(_read(sys_root / "block" / name / "comp_algorithm"))))
    zswap = sys_root / "module/zswap/parameters"
    return Usage(
        vram_used_mib=vram_used // MIB if vram_used is not None else None,
        gtt_used_mib=gtt_used // MIB if gtt_used is not None else None,
        ram_available_mib=info["MemAvailable"] // 1024 if "MemAvailable" in info else None,
        zram=tuple(zrams),
        zswap_pool_mib=info["Zswap"] // 1024 if "Zswap" in info else None,
        zswap_stored_mib=info["Zswapped"] // 1024 if "Zswapped" in info else None,
        zswap_max_pool_percent=_int(_read(zswap / "max_pool_percent")),
        zswap_compressor=_selected(_read(zswap / "compressor")),
        disk_swap_size_mib=disk_size,
        disk_swap_used_mib=disk_used,
    )


def mib_text(mib: int | None) -> str:
    if mib is None:
        return "—"
    return f"{mib / 1024:.1f} GiB" if mib >= 1024 else f"{mib} MiB"
