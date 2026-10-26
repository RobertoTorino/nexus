# SPDX-License-Identifier: GPL-3.0-or-later
"""Base and Extended System Score: a stock BC-250 on BIOS 5.00, set up as recommended, scores 100.

Hardware items lose points below their default and only add to the Extended score above it, so the
Base score never exceeds 100. Configuration items (IOMMU, mitigations, VRAM split, ACPI fix) are
either right or not; swap scores zswap with a disk swapfile full and zram less. Everything is read on demand: a few sysfs/proc files and small history queries.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import plain_tooltip, window_title
from .dashboard import ACCENT, header_font, score_color
from .sysoverview import _gb, _read, bios_info, bios_rating, cpu_topology, system_disk

if TYPE_CHECKING:
    from .history import History

DEFAULT_CUS, DEFAULT_CORES, DEFAULT_THREADS = 24, 6, 12
SHADER_ARRAYS = 4                 # 2 shader engines x 2 arrays; CUs come in WGPs of 2
CU_STEP = SHADER_ARRAYS * 2       # an evenly distributed CU count is a multiple of 8: 24, 32, 40
DEFAULT_NVME_READ_MBPS = 850      # PCIe 2.0 slot, ~1000 MB/s raw ceiling; a good drive reads ~85% of it
DEFAULT_NVME_BYTES = 500e9        # the "512 GB class": 480/500/512 GB drives all count as the default
MIN_FULL_NVME_BYTES = 480e9
DEFAULT_LINK_MBPS = 1000
RECOMMENDED_VRAM_MIB = 6144       # manual: the split with a documented fix for framebuffer pin failures
VRAM_TOLERANCE_MIB = 64
OTHER_VRAM_SHARE = 0.5            # another split works, but is not the recommended one
LOG_BONUS = 0.25                  # Extended: +25% of the weight per doubling above the default
TEXT_GREEN, TEXT_ORANGE, TEXT_RED, TEXT_GREY = "#81c784", "#ffb74d", "#e57373", "#9aa0a6"
TEXT_YELLOW = "#fdd835"
HARDWARE, CONFIGURATION = "Hardware", "Configuration"


@dataclass
class Factor:
    label: str
    weight: int
    value: str          # "—" when not measured yet
    default: str
    base: float         # points towards the Base score, at most the weight
    extended: float     # points towards the Extended score, may exceed the weight
    note: str
    group: str = HARDWARE
    warning: str = ""

    @property
    def measured(self) -> bool:
        return self.value != "—"


@dataclass
class SystemScore:
    factors: list[Factor]

    # Rounded down: 99.6 is not a fully set up stock board.
    @property
    def base(self) -> int:
        return min(100, math.floor(sum(f.base for f in self.factors) + 1e-6))

    @property
    def extended(self) -> int:
        return max(self.base, math.floor(sum(f.extended for f in self.factors) + 1e-6))

    @property
    def missing(self) -> list[Factor]:
        return [f for f in self.factors if not f.measured]

    @property
    def warnings(self) -> list[str]:
        return [f.warning for f in self.factors if f.warning]


def _factor(label: str, weight: int, value: str, default: str, ratio: float | None, above: str,
            note: str, group: str = HARDWARE, warning: str = "") -> Factor:
    """above: 'linear' (compute), 'log' (diminishing returns) or 'none' (no bonus above the default)."""
    if ratio is None:
        return Factor(label, weight, "—", default, 0.0, 0.0, note, group)
    ratio = max(0.0, ratio)
    if ratio <= 1 or above == "none":
        pts = weight * min(ratio, 1.0)
        return Factor(label, weight, value, default, pts, pts, note, group, warning)
    ext = weight * (ratio if above == "linear" else 1 + LOG_BONUS * math.log2(ratio))
    return Factor(label, weight, value, default, float(weight), ext, note, group, warning)


def _capacity_ratio(n_bytes: float) -> float:
    """Below the 512 GB class in proportion; from there on whole size classes only (512 GB, 1 TB, 2 TB, ...),
    so a 512 GB or a 1.024 TB drive scores exactly like a 500 GB or a 1 TB one."""
    if n_bytes < MIN_FULL_NVME_BYTES:
        return n_bytes / MIN_FULL_NVME_BYTES
    return 2.0 ** max(0, round(math.log2(n_bytes / DEFAULT_NVME_BYTES)))


def balanced_cus(total: int, per_array: list[int] | None) -> int:
    """The CU count the score uses. Work is spread over all four shader arrays, so the array with the fewest
    CUs sets the pace: an uneven unlock counts as the evenly distributed configuration below it."""
    if per_array and len(per_array) == SHADER_ARRAYS and sum(per_array) == total:
        return SHADER_ARRAYS * min(per_array)
    return total - total % CU_STEP


def link_speed(sys_root: Path = Path("/sys")) -> tuple[str, int] | None:
    """(interface, Mbit/s) of the fastest wired link that is up."""
    best: tuple[str, int] | None = None
    for dev in sorted((sys_root / "class" / "net").glob("*")):
        if not (dev / "device").exists() or (dev / "wireless").exists() or _read(dev / "operstate") != "up":
            continue
        speed = _read(dev / "speed")
        if speed and speed.isdigit() and int(speed) > 0 and (best is None or int(speed) > best[1]):
            best = (dev.name, int(speed))
    return best


def iommu_groups(sys_root: Path = Path("/sys")) -> int | None:
    """Number of IOMMU groups: 0 when the IOMMU is off (BIOS or amd_iommu=off); None when not on Linux."""
    if not (sys_root / "kernel").is_dir():
        return None
    groups = sys_root / "kernel" / "iommu_groups"
    try:
        return sum(1 for _ in groups.iterdir()) if groups.is_dir() else 0
    except OSError:
        return None


def mitigations_off(proc_root: Path = Path("/proc")) -> bool | None:
    cmdline = _read(proc_root / "cmdline")
    return None if cmdline is None else "mitigations=off" in cmdline.split()


def acpi_fix(sys_root: Path = Path("/sys")) -> bool | None:
    """True when cpufreq scaling and CPU idle states exist, which the BC-250 only has with the ACPI fix
    (initrd override or a modded BIOS); the same check as test 26."""
    cpu0 = sys_root / "devices" / "system" / "cpu" / "cpu0"
    if not cpu0.is_dir():
        return None
    return (cpu0 / "cpufreq").is_dir() and (cpu0 / "cpuidle").is_dir()


@dataclass
class SwapLayout:
    zram: bool
    zswap: bool
    disk: bool


def swap_layout(sys_root: Path = Path("/sys"), proc_root: Path = Path("/proc")) -> SwapLayout | None:
    """Active swap backends, the same checks as test 14: zram devices and disk swap from /proc/swaps,
    zswap from its module parameter."""
    swaps = _read(proc_root / "swaps")
    if swaps is None:
        return None
    names = [line.split()[0] for line in swaps.splitlines()[1:] if line.split()]
    zram = any(Path(n).name.startswith("zram") for n in names)
    disk = any(not Path(n).name.startswith("zram") for n in names)
    zswap = _read(sys_root / "module" / "zswap" / "parameters" / "enabled") in ("Y", "1")
    return SwapLayout(zram, zswap, disk)


def swap_rating(layout: SwapLayout) -> tuple[float, str, str]:
    """(share of the points, short value, note). zswap in front of a disk swapfile is the default:
    it keeps a game alive under memory pressure, where zram alone fills up and ends in the OOM killer."""
    if layout.zram and layout.zswap:
        return 0.4, "zram + zswap", "zram and zswap both compress the same pages: disable zram (test 14)."
    if layout.zswap and layout.disk:
        return 1.0, "zswap + disk", "zswap backed by a disk swapfile, the recommended layout."
    if layout.zram and layout.disk:
        return 0.6, "zram + disk", ("zram with a disk backstop works, but zswap in front of the swapfile is "
                                    "more stable for gaming: disable zram and enable zswap (test 14).")
    if layout.disk:
        return 0.6, "disk only", "Disk swap without zswap: enable zswap (zswap.enabled=1) in front of it (test 14)."
    if layout.zram:
        return 0.4, "zram only", ("zram alone has no overflow, so a full zram ends in the OOM killer: "
                                  "switch to zswap with a disk swapfile (test 14).")
    if layout.zswap:
        return 0.0, "zswap, no disk", "zswap is a cache in front of disk swap and does nothing without it: add a swapfile (test 14)."
    return 0.0, "none", "No swap at all: add a disk swapfile with zswap in front of it (test 14)."


def vram_split_mib(sys_root: Path = Path("/sys")) -> int | None:
    sizes = [_read(dev / "mem_info_vram_total") for dev in sorted((sys_root / "class" / "drm").glob("card*/device"))]
    sizes = [int(s) for s in sizes if s and s.isdigit() and int(s) > 0]
    return max(sizes) // 1048576 if sizes else None


def _cu_factor(history: History | None) -> Factor:
    cus = history.latest_config("cus") if history else None
    if not cus:
        return _factor("GPU compute units", 20, "", f"{DEFAULT_CUS} CUs", None, "linear",
                       "Run test 21 (GPU) or 42 (benchmark).")
    total = cus[0]
    metrics = history.latest_run_metrics("cu.sa0") if history else {}
    per_array = [int(metrics[f"cu.sa{i}"]) for i in range(SHADER_ARRAYS) if f"cu.sa{i}" in metrics]
    if len(per_array) != SHADER_ARRAYS or sum(per_array) != total:
        per_array = []
    counted = balanced_cus(total, per_array)
    note = f"From the run of {cus[1][:16]}."
    warning = ""
    if counted != total:
        spread = (" (per shader array: " + ", ".join(map(str, per_array)) + ")") if per_array else ""
        warning = (f"CUs are not evenly assigned: {total} CUs{spread}. Every shader array should have the same "
                   f"number (24, 32 or 40 in total). Scored as {counted} CUs; redo the CU unlock.")
        note += f" Counted as {counted}: the evenly distributed configuration below {total}."
    value = f"{total} CUs" + (f" → {counted}" if counted != total else "")
    return _factor("GPU compute units", 20, value, f"{DEFAULT_CUS} CUs", counted / DEFAULT_CUS, "linear",
                   note, warning=warning)


def compute(history: History | None, health: int | None, sys_root: Path = Path("/sys"),
            proc_root: Path = Path("/proc")) -> SystemScore:
    topo = cpu_topology(sys_root)
    if topo is None and history:
        c, t = history.latest_config("cores"), history.latest_config("threads")
        topo = (c[0], t[0]) if c and t else None
    read = history.latest_metric("disk.read_mbps") if history else None
    bios = bios_info(sys_root)
    rating = bios_rating(bios.version) if bios else None
    disk = system_disk(sys_root)
    link = link_speed(sys_root)
    groups = iommu_groups(sys_root)
    mitig = mitigations_off(proc_root)
    acpi = acpi_fix(sys_root)
    vram = vram_split_mib(sys_root)
    layout = swap_layout(sys_root, proc_root)
    swap = swap_rating(layout) if layout else None
    vram_ok = vram is not None and abs(vram - RECOMMENDED_VRAM_MIB) <= VRAM_TOLERANCE_MIB
    return SystemScore([
        _cu_factor(history),
        _factor("CPU cores / threads", 15, f"{topo[0]}C/{topo[1]}T" if topo else "",
                f"{DEFAULT_CORES}C/{DEFAULT_THREADS}T",
                0.75 * topo[0] / DEFAULT_CORES + 0.25 * topo[1] / DEFAULT_THREADS if topo else None, "linear",
                "Cores count 75%, SMT threads 25%." if topo else "Run test 25 (CPU)."),
        _factor("NVMe read speed", 10, f"{read[0]:.0f} MB/s" if read else "", f"{DEFAULT_NVME_READ_MBPS} MB/s",
                read[0] / DEFAULT_NVME_READ_MBPS if read else None, "log",
                f"Sequential read of test 43, {read[1][:16]}." if read else "Run the disk speed test (test 43)."),
        _factor("NVMe capacity", 5, _gb(disk[1]) if disk else "", "512 GB",
                _capacity_ratio(disk[1]) if disk else None, "log",
                f"Size of {disk[0]}." if disk else "No NVMe drive found."),
        _factor("Network link", 5, f"{link[1]} Mbit/s" if link else "", "1000 Mbit/s",
                link[1] / DEFAULT_LINK_MBPS if link else None, "log",
                f"Wired link of {link[0]}." if link else "No wired Ethernet link is up."),
        _factor("BIOS", 5, bios.version if bios else "", "5.00", rating[0] if rating else None, "none",
                rating[1][0].upper() + rating[1][1:] + "." if rating else "Not exposed via DMI.",
                CONFIGURATION),
        _factor("ACPI fix", 10, ("applied" if acpi else "missing") if acpi is not None else "", "applied",
                None if acpi is None else float(acpi), "none",
                "cpufreq scaling and CPU idle states are available (test 26)." if acpi else
                "Without it the BC-250 has no frequency scaling or C-states: apply bc250-acpi-fix (test 26).",
                CONFIGURATION),
        _factor("VRAM split", 10, f"{vram / 1024:.1f} GB" if vram else "", f"{RECOMMENDED_VRAM_MIB // 1024} GB",
                None if vram is None else 1.0 if vram_ok else OTHER_VRAM_SHARE, "none",
                "The recommended split." if vram_ok else
                "6 GB is the split with a documented fix for framebuffer pin failures: "
                "sudo ./bc250memcfg UMA_SIZE 6144 (see test 37 and the manual).", CONFIGURATION),
        _factor("CPU mitigations", 5, ("off" if mitig else "on") if mitig is not None else "", "off",
                None if mitig is None else float(mitig), "none",
                "mitigations=off is on the kernel command line (test 24)." if mitig else
                "rpm-ostree kargs --append-if-missing=mitigations=off, then reboot (test 24).", CONFIGURATION),
        _factor("IOMMU", 5, ("disabled" if groups == 0 else f"enabled ({groups} groups)") if groups is not None
                else "", "disabled", None if groups is None else float(groups == 0), "none",
                "No IOMMU groups (test 23)." if groups == 0 else
                "The IOMMU is broken on the BC-250: disable it in the BIOS or with amd_iommu=off (test 23).",
                CONFIGURATION),
        _factor("Swap", 5, swap[1] if swap else "", "zswap + disk", swap[0] if swap else None, "none",
                swap[2] if swap else "Not on Linux.", CONFIGURATION),
        _factor("Health score", 5, f"{health}%" if health is not None else "", "100%",
                health / 100 if health is not None else None, "none",
                "The health score of the latest test results." if health is not None else "Run all tests.",
                CONFIGURATION),
    ])


def _tone(f: Factor) -> str:
    if not f.measured:
        return TEXT_GREY
    share = f.base / f.weight
    return TEXT_GREEN if share >= 0.999 else TEXT_ORANGE if share >= 0.5 else TEXT_RED


class ScoreRing(QWidget):
    """The score as a ring: the first lap up to 100, a second purple lap for what goes beyond."""

    def __init__(self, score: int, color: str, caption: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.score, self.color, self.caption = score, color, caption
        self.setFixedSize(190, 190)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(12, 12, self.width() - 24, self.height() - 24)
        for color, share in (("#2a2d36", 1.0), (self.color, min(self.score, 100) / 100),
                             (ACCENT, max(0, self.score - 100) / 100)):
            if share > 0:
                pen = QPen(QColor(color))
                pen.setWidth(14)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawArc(rect, 90 * 16, -round(360 * 16 * min(share, 1.0)))
        font = QFont(self.font())
        font.setPointSize(40)
        font.setWeight(QFont.Weight.ExtraBold)
        p.setFont(font)
        p.setPen(QColor("white"))
        p.drawText(rect.adjusted(0, -14, 0, -14), Qt.AlignmentFlag.AlignCenter, str(self.score))
        font.setPointSize(10)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(QColor(TEXT_GREY))
        p.drawText(rect.adjusted(0, 56, 0, 0), Qt.AlignmentFlag.AlignCenter, self.caption)
        p.end()


class _Bar(QWidget):
    def __init__(self, share: float, extra: float, color: str, scale: float):
        super().__init__()
        self.share, self.extra, self.color, self.scale = share, extra, color, scale
        self.setFixedSize(140, 8)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        w, h = self.width(), self.height()
        p.setBrush(QColor("#2a2d36"))
        p.drawRoundedRect(QRectF(0, 0, w, h), 4, 4)
        base_w = w * min(self.share, 1.0) / self.scale
        if base_w > 0:
            p.setBrush(QColor(self.color))
            p.drawRoundedRect(QRectF(0, 0, base_w, h), 4, 4)
        if self.extra > 0:
            p.setBrush(QColor(ACCENT))
            p.drawRoundedRect(QRectF(base_w, 0, min(w - base_w, w * self.extra / self.scale), h), 4, 4)
        p.end()


class SystemScoreDialog(QDialog):
    def __init__(self, result: SystemScore, extended: bool, parent: QWidget | None = None):
        super().__init__(parent)
        name = "Extended System Score" if extended else "Base System Score"
        self.setWindowTitle(window_title(name))
        self.setObjectName("scoreDialog")
        self.setStyleSheet("#scoreDialog { background:#14161c; } QLabel { color:#e6e6e6; background:transparent; }")
        base = result.base
        score = result.extended if extended else base
        col = QVBoxLayout(self)
        col.setContentsMargins(24, 20, 24, 16)
        col.setSpacing(16)

        head = QHBoxLayout()
        head.setSpacing(22)
        caption = f"base {base} + {score - base}" if extended else "out of 100"
        head.addWidget(ScoreRing(score, score_color(min(score, 100)), caption))
        text = QVBoxLayout()
        title = QLabel(name)
        title.setStyleSheet(header_font() + "font-size:22px; font-weight:800;")
        sub = QLabel("Your hardware on top of the stock board: more CUs, cores, a faster or bigger drive and a "
                     "faster network link add points. Equal to the Base score on a stock board." if extended else
                     "Your board against a stock BC-250 on BIOS 5.00, set up as recommended: meeting every default "
                     "gives 100. Below a default costs points; anything above it counts in the Extended score.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{TEXT_GREY};")
        text.addStretch(1)
        text.addWidget(title)
        text.addWidget(sub)
        text.addStretch(1)
        head.addLayout(text, 1)
        col.addLayout(head)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        for c, h in enumerate(("Item", "Your board", "Default", "Points", "")):
            lbl = QLabel(h)
            lbl.setStyleSheet(f"color:{TEXT_GREY}; font-size:11px; font-weight:600;")
            grid.addWidget(lbl, 0, c)
        r = 0
        for group in (HARDWARE, CONFIGURATION):
            factors = [f for f in result.factors if f.group == group]
            r += 1
            got = sum(f.extended if extended else f.base for f in factors)
            section = QLabel(f"{group}  ·  {got:.1f} / {sum(f.weight for f in factors)}")
            section.setStyleSheet(f"color:{ACCENT}; font-size:12px; font-weight:800; padding-top:6px;")
            grid.addWidget(section, r, 0, 1, 5)
            for f in factors:
                r += 1
                self._add_row(grid, r, f, extended)
        col.addLayout(grid)

        if result.warnings:
            warn = QLabel("⚠ " + "\n⚠ ".join(result.warnings))
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color:{TEXT_ORANGE}; font-weight:700;")
            col.addWidget(warn)

        if result.missing:
            miss = QLabel("Not measured yet (0 points): "
                          + "; ".join(f"{f.label} — {f.note}" for f in result.missing))
            miss.setWordWrap(True)
            miss.setStyleSheet(f"color:{TEXT_GREY}; font-size:11px;")
            col.addWidget(miss)

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        col.addLayout(row)

    @staticmethod
    def _add_row(grid: QGridLayout, r: int, f: Factor, extended: bool) -> None:
        tone = _tone(f)
        bonus = f.extended - f.weight if extended else 0.0
        if extended:
            pts = f"{f.extended:.1f}" + (f"  (+{bonus:.1f})" if bonus > 0.05 else "")
        else:
            pts = f"{f.base:.1f} / {f.weight}"
        # U+FE0E keeps the sign a text glyph, so it takes the color instead of rendering as an emoji.
        name_lbl = QLabel(f.label + (f" <span style='color:{TEXT_YELLOW};'>⚠\ufe0e</span>" if f.warning else ""))
        name_lbl.setStyleSheet("font-weight:700;")
        name_lbl.setToolTip(plain_tooltip("\n".join(filter(None, (f.note, f.warning)))))
        value_lbl = QLabel(f.value)
        value_lbl.setStyleSheet(f"color:{TEXT_ORANGE if f.warning else tone};")
        value_lbl.setToolTip(plain_tooltip(f.note))
        pts_lbl = QLabel(pts)
        pts_lbl.setStyleSheet(f"color:{ACCENT if bonus > 0.05 else tone}; font-weight:700;")
        bar = _Bar(f.base / f.weight, max(0.0, bonus) / f.weight, tone, 2.0 if extended else 1.0)
        for c, w in enumerate((name_lbl, value_lbl, QLabel(f.default), pts_lbl, bar)):
            grid.addWidget(w, r, c, Qt.AlignmentFlag.AlignVCenter)
