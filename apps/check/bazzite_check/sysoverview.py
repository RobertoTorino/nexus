# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings > System overview: the board's configuration and latest measurements as colored boxes.

Everything is read when the page is opened, never in the background: a few sysfs files, one statvfs
call and two small history queries, well under a millisecond in total.
"""

from __future__ import annotations

import csv
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from . import plain_tooltip
from .dashboard import BLUE, GREEN, GREY, PURPLE, RED, StatBox
from .graph import SPEEDTEST_HISTORY_NAME, find_csvs

if TYPE_CHECKING:
    from .history import History

# The BC-250's Cyan Skillfish die: 40 CUs (24 enabled from the factory), 8 Zen 2 cores with SMT (6 enabled).
MAX_CUS, MAX_CORES, MAX_THREADS = 40, 8, 16


@dataclass
class Item:
    value: str
    color: str
    tip: str


def _read(path: Path) -> str | None:
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return None


def _cpu_list(text: str | None) -> list[int]:
    """'0-5,8,10-11' -> [0, 1, 2, 3, 4, 5, 8, 10, 11]."""
    out: list[int] = []
    for part in (text or "").split(","):
        lo, _, hi = part.partition("-")
        if lo.isdigit() and (not hi or hi.isdigit()):
            out.extend(range(int(lo), int(hi or lo) + 1))
    return out


def cpu_topology(sys_root: Path = Path("/sys")) -> tuple[int, int] | None:
    """(cores, threads) online right now, from sysfs (Linux); None elsewhere."""
    cpu = sys_root / "devices" / "system" / "cpu"
    online = _cpu_list(_read(cpu / "online"))
    if not online:
        return None
    cores = {(_read(cpu / f"cpu{n}" / "topology" / "physical_package_id"),
              _read(cpu / f"cpu{n}" / "topology" / "core_id")) for n in online}
    return len(cores), len(online)


def _gb(n_bytes: float) -> str:
    return f"{n_bytes / 1e12:.2f} TB" if n_bytes >= 1e12 else f"{n_bytes / 1e9:.0f} GB"


def system_disk(sys_root: Path = Path("/sys")) -> tuple[str, int] | None:
    """(name, size in bytes) of the first NVMe drive."""
    for dev in sorted((sys_root / "block").glob("nvme*n1")):
        sectors = _read(dev / "size")
        if sectors and sectors.isdigit() and int(sectors) > 0:
            return dev.name, int(sectors) * 512
    return None


@dataclass
class Bios:
    version: str
    vendor: str
    date: str


def bios_info(sys_root: Path = Path("/sys")) -> Bios | None:
    """The firmware version from DMI (Linux); None when it is not exposed."""
    dmi = sys_root / "class" / "dmi" / "id"
    version = _read(dmi / "bios_version")
    if not version:
        return None
    return Bios(version, _read(dmi / "bios_vendor") or "unknown", _read(dmi / "bios_date") or "unknown")


LATEST_STOCK_BIOS = 5
_STOCK_BIOS = re.compile(r"^[LP]?([1-5])\.00$")
_MODDED_BIOS = re.compile(r"meimei|mod|unlock", re.IGNORECASE)


def bios_rating(version: str) -> tuple[float, str]:
    """(share of the stock 5.00 BIOS, description), with the same rules as test 00 of the script.
    A modded BIOS counts as current: its unlocks show up in the CU and core counts."""
    if _MODDED_BIOS.search(version):
        return 1.0, "modded BIOS"
    if m := _STOCK_BIOS.match(version.strip()):
        n = int(m.group(1))
        return n / LATEST_STOCK_BIOS, ("latest stock BIOS" if n == LATEST_STOCK_BIOS
                                       else f"older stock BIOS, the latest is {LATEST_STOCK_BIOS}.00")
    return 0.5, "unrecognized version; stock releases are 1.00/2.00/3.00/5.00"


def _latest_speedtest_csv() -> dict[str, str] | None:
    for path in find_csvs(SPEEDTEST_HISTORY_NAME):
        try:
            with path.open(newline="", encoding="utf-8", errors="replace") as fh:
                rows = list(csv.DictReader(fh))
        except OSError:
            continue
        if rows:
            return rows[-1]
    return None


# Every box has its own color; gray means "no data yet". Only the free space turns red (below 10% free).
BOX_COLOR = {"cus": PURPLE, "cores": "#ad1457", "threads": "#00796b", "down": BLUE, "up": "#3949ab",
             "nvme": "#6d4c41", "free": GREEN, "pkgs": "#5e35b1", "bios": "#00838f"}
BIOS_BOX_CHARS = 10


def _vs_stock(value: int, stock: int) -> str:
    return "unlocked" if value > stock else "stock" if value == stock else "below stock"


def collect(history: History | None, home: Path = Path.home(), sys_root: Path = Path("/sys")) -> dict[str, Item]:
    """Everything shown on the page, as (value, color, tooltip) per box."""
    items: dict[str, Item] = {}

    bios = bios_info(sys_root)
    if bios:
        shown = bios.version if len(bios.version) <= BIOS_BOX_CHARS else bios.version[:BIOS_BOX_CHARS - 1] + "…"
        items["bios"] = Item(shown, BOX_COLOR["bios"],
                             f"BIOS {bios.version} ({bios_rating(bios.version)[1]}).\n"
                             f"Vendor: {bios.vendor}, date: {bios.date}. Read from DMI (sysfs).")
    else:
        items["bios"] = Item("—", GREY, "The BIOS version is not exposed via DMI on this system.")

    cus = history.latest_config("cus") if history else None
    items["cus"] = (Item(f"{cus[0]}/{MAX_CUS}", BOX_COLOR["cus"],
                         f"Compute units routed, out of the {MAX_CUS} on the die (stock: 24, "
                         f"{_vs_stock(cus[0], 24)}).\n"
                         f"From test 21 or 42, run {cus[1]}.")
                    if cus else Item("—", GREY, "Run test 21 (GPU page) or 42 (benchmark) to see the CU count."))

    live = cpu_topology(sys_root)
    if live:
        cores, threads = live
        source = "Online now (sysfs)."
    else:
        c = history.latest_config("cores") if history else None
        t = history.latest_config("threads") if history else None
        cores, threads = (c[0] if c else None), (t[0] if t else None)
        source = f"From the test history, run {c[1]}." if c else ""
    for key, value, top, stock, what in (("cores", cores, MAX_CORES, 6, "Physical CPU cores"),
                                         ("threads", threads, MAX_THREADS, 12, "CPU threads")):
        if value is None:
            items[key] = Item("—", GREY, "Run test 25 (CPU page) to see this.")
        else:
            items[key] = Item(f"{value}/{top}", BOX_COLOR[key],
                              f"{what} active, out of the {top} on the die (stock: {stock}, "
                              f"{_vs_stock(value, stock)}). {source}".strip())

    csv_row = _latest_speedtest_csv()
    for key, metric, column, label in (("down", "net.down_mbps", "down_mbps", "Download"),
                                       ("up", "net.up_mbps", "up_mbps", "Upload")):
        found = history.latest_metric(metric) if history else None
        if found is None and csv_row and csv_row.get(column):
            try:
                found = (float(csv_row[column]), csv_row.get("date", "?"))
            except ValueError:
                found = None
        items[key] = (Item(f"{found[0]:.0f} Mbps", BOX_COLOR[key], f"{label} speed of the latest internet speed test "
                           f"(test 44), {found[1]}.") if found
                      else Item("—", GREY, "Run the internet speed test (test 44, Network page)."))

    disk = system_disk(sys_root)
    items["nvme"] = (Item(_gb(disk[1]), BOX_COLOR["nvme"], f"Capacity of {disk[0]}.") if disk
                     else Item("—", GREY, "No NVMe drive found."))
    try:
        usage = shutil.disk_usage(home)
    except OSError:
        usage = None
    if usage and usage.total:
        free = usage.free / usage.total
        items["free"] = Item(f"{_gb(usage.free)}/{_gb(usage.total)}",
                             BOX_COLOR["free"] if free >= 0.1 else RED,
                             f"Free space on the file system of your home folder ({free:.0%} free). "
                             "The box turns red below 10% free.")
    else:
        items["free"] = Item("—", GREY, "Could not read the free space.")

    total = history.latest_metric("pkg.total") if history else None
    if total:
        tip = f"Installed packages and apps, from test 45 run {total[1]}."
        if history:
            parts = history.latest_run_metrics("pkg.total")
            details = [f"{label}: {parts[key]:.0f}" for key, label in (
                ("pkg.sources", "Sources"), ("pkg.layered", "Layered on the image"),
                ("pkg.flatpak_system", "Flatpak apps (system)"), ("pkg.flatpak_user", "Flatpak apps (user)"))
                if key in parts]
            if details:
                tip += "\n" + "\n".join(details)
        items["pkgs"] = Item(f"{total[0]:.0f}", BOX_COLOR["pkgs"], tip)
    else:
        items["pkgs"] = Item("—", GREY, "Run test 45 (Updates page) to count the installed packages.")
    return items


BOXES = [("bios", "BIOS version"), ("cus", "Unlocked CUs"), ("cores", "CPU cores"), ("threads", "CPU threads"),
         ("down", "Speedtest DL"), ("up", "Speedtest UL"), ("nvme", "NVMe size"), ("free", "NVMe free space"),
         ("pkgs", "Package count")]


class SystemOverviewPage(QWidget):
    def __init__(self, history_provider, parent: QWidget | None = None):
        super().__init__(parent)
        self._history = history_provider
        layout = QVBoxLayout(self)
        title = QLabel("System overview")
        title.setStyleSheet("font-size:16px; font-weight:700;")
        layout.addWidget(title)
        intro = QLabel("The board's configuration and the latest measurements. Hover a box for details.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        grid = QGridLayout()
        grid.setSpacing(10)
        self.boxes: dict[str, StatBox] = {}
        for i, (key, label) in enumerate(BOXES):
            box = StatBox(label, GREY, "")
            box.setMinimumSize(150, 70)
            self.boxes[key] = box
            grid.addWidget(box, i // 3, i % 3)
        layout.addLayout(grid)
        layout.addStretch(1)

    def refresh(self) -> None:
        for key, item in collect(self._history()).items():
            box = self.boxes[key]
            box.set_value(item.value)
            box.set_color(item.color)
            box.setToolTip(plain_tooltip(item.tip))

