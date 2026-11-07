# SPDX-License-Identifier: GPL-3.0-or-later
"""The line on the right of the portal's header: the CPU's and GPU's load and temperature,
then the date and the time, as in "CPU 12% 54°C | GPU 3% 61°C | Thursday 11/5/26 | 07:44 PM CEST". The clock is set
on the Settings page (ClockStyle, owner 05-11-2026): a 12- or 24-hour clock, with or without the seconds, in the
system's own time zone, Central European Time (CET, CEST in summer) or UTC.

Read as Bazzite Test's status bar reads them, so it costs next to nothing: plain file reads from /proc and sysfs, no
helper programs, a sample every 2 s (the window skips them while it is minimized). The load is the change since the
sample before, so the first sample has none.

CPU load: /proc/stat. GPU load, in order of preference: gpu_busy_percent, the kernel load sensor (a stock Cyan
Skillfish kernel answers EOPNOTSUPP); gpu_metrics, when GPU Governor's fix-metrics has mounted its patched copy; the
gfx and compute engine time of this user's processes in /proc/<pid>/fdinfo (the games and the compositor among
them), the processes found again every 10 s. Temperatures: the CPU's from k10temp (or zenpower), the GPU's from the
card's own amdgpu sensor. What the system does not report is left out of the line."""

from __future__ import annotations

import datetime
import os
import re
import struct
import time
import zoneinfo
from dataclasses import dataclass
from pathlib import Path

SCAN_S = 10                     # the processes that hold the GPU are found again this often
CPU_CHIPS = ("k10temp", "zenpower", "coretemp")
CPU_LABELS = ("Tctl", "Tdie", "Package id 0")      # the sensor of the whole CPU, before the first one listed
AMDGPU = re.compile(r"^drm-driver:\s*amdgpu", re.M)
CLIENT = re.compile(r"^drm-client-id:\s*(\d+)", re.M)
ENGINES = (re.compile(r"^drm-engine-gfx:\s*(\d+)", re.M), re.compile(r"^drm-engine-compute:\s*(\d+)", re.M))


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return ""


# The clock's time zones: the system's own, Central European Time (summer time included) or UTC.
ZONES = {"local": "The system's", "cet": "CET", "utc": "UTC"}
CET = "Europe/Amsterdam"        # CET in winter, CEST in summer, as every Central European zone


@dataclass(frozen=True)
class ClockStyle:
    """How the clock reads: 12 or 24 hours, the seconds or not, and the zone (a key of ZONES). The default is the
    clock as it always was."""
    hours: int = 12
    seconds: bool = False
    zone: str = "local"


def zone_of(style: ClockStyle) -> datetime.tzinfo | None:
    """The style's time zone; None for the system's own (and when the system lacks the zone's data)."""
    try:
        return datetime.timezone.utc if style.zone == "utc" else zoneinfo.ZoneInfo(CET) if style.zone == "cet" \
            else None
    except zoneinfo.ZoneInfoNotFoundError:
        return None


def clock_text(now: datetime.datetime | None = None, style: ClockStyle = ClockStyle()) -> str:
    """'Thursday 11/5/26 | 07:44 PM CEST': the weekday, month/day/year, the time and its zone, in the style's time
    zone (the system's own by default); '19:44:05 CEST' with 24 hours and the seconds."""
    zone = zone_of(style)
    now = now or datetime.datetime.now().astimezone()       # the system's own time zone
    if zone is not None:
        now = now.astimezone(zone)
    name = now.tzname() or ""
    form = ("%H:%M" if style.hours == 24 else "%I:%M") + (":%S" if style.seconds else "") \
        + (" %p" if style.hours != 24 else "")
    return f"{now:%A} {now.month}/{now.day}/{now:%y} | {now:{form}}{' ' + name if name else ''}"


def _temperature(chip: Path, labels: tuple[str, ...] = ()) -> float | None:
    """A chip's temperature in °C: the first sensor whose label is one of *labels*, else its first sensor."""
    inputs = sorted(chip.glob("temp*_input"), key=lambda p: int(p.name[4:-6]) if p.name[4:-6].isdigit() else 0)
    named = {_read(p.with_name(p.name[:-6] + "_label")): p for p in inputs}
    for sensor in [named[label] for label in labels if label in named] + inputs:
        value = _read(sensor)
        if value.lstrip("-").isdigit() and int(value) != 0:
            return int(value) / 1000
    return None


def _part(name: str, load: float | None, temperature: float | None) -> str:
    values = [f"{load:.0f}%" if load is not None else "", f"{temperature:.0f}°C" if temperature is not None else ""]
    values = [v for v in values if v]
    return f"{name} {' '.join(values)}" if values else ""


class Status:
    """Reads the CPU's and the GPU's load and temperature; line() is the header's line at this moment."""

    def __init__(self, sys_root: Path = Path("/sys"), proc_root: Path = Path("/proc"), clock=time.monotonic):
        self.sys, self.proc, self.clock = sys_root, proc_root, clock
        self.gpu = next((dev for dev in sorted((sys_root / "class" / "drm").glob("card*/device"))
                         if (dev / "pp_dpm_sclk").exists()), None)
        hwmon = sorted((sys_root / "class" / "hwmon").glob("hwmon*"))
        self.cpu_chip = next((chip for name in CPU_CHIPS for chip in hwmon if _read(chip / "name") == name), None)
        self.gpu_chip = next(iter(sorted(self.gpu.glob("hwmon/hwmon*"))), None) if self.gpu else None
        self._cpu_prev: tuple[int, int] | None = None
        self._fds: list[tuple[str, str]] = []           # (pid, fd) of this user's amdgpu clients
        self._scanned = -SCAN_S
        self._clients: dict[str, tuple[int, int]] = {}
        self._at = 0.0

    def cpu_load(self) -> float | None:
        line = _read(self.proc / "stat").partition("\n")[0].split()
        if len(line) < 9 or line[0] != "cpu":
            return None
        values = [int(v) for v in line[1:9]]
        idle, total = values[3] + values[4], sum(values)
        prev, self._cpu_prev = self._cpu_prev, (total - idle, total)
        if not prev or total <= prev[1]:
            return None
        return max(0.0, min(100.0, 100 * (total - idle - prev[0]) / (total - prev[1])))

    def _sensor(self) -> float | None:
        """The GPU's load from the kernel: its load sensor, or the patched gpu_metrics; None without either."""
        value = _read(self.gpu / "gpu_busy_percent")
        if value.isdigit():
            return float(value)
        # A stock kernel's gpu_metrics holds 0 or 0xFFFF for the activity: only GPU Governor's patched copy counts.
        if "gpu_metrics" in _read(self.proc / "self" / "mountinfo"):
            try:
                raw = (self.gpu / "gpu_metrics").read_bytes()[:32]
            except OSError:
                raw = b""
            # APU layout v2.x: header(4) temp_gfx temp_soc temp_core[8] temp_l3[2] average_gfx_activity
            if len(raw) >= 30 and raw[2] == 2:
                (activity,) = struct.unpack_from("<H", raw, 28)
                if activity <= 100:
                    return float(activity)
        return None

    def _scan(self) -> None:
        """This user's processes that hold the GPU open: their DRM file descriptors."""
        found: list[tuple[str, str]] = []
        for pid in (p for p in os.listdir(self.proc) if p.isdigit()) if self.proc.is_dir() else ():
            try:
                fds = os.listdir(self.proc / pid / "fdinfo")
            except OSError:
                continue
            for fd in fds:
                if AMDGPU.search(_read(self.proc / pid / "fdinfo" / fd)):
                    found.append((pid, fd))
        self._fds = found

    def _engines(self) -> float | None:
        """The busier of gfx and compute, summed over the clients, since the sample before."""
        now = self.clock()
        if now - self._scanned >= SCAN_S:
            self._scan()
            self._scanned = now
        clients: dict[str, tuple[int, int]] = {}
        for pid, fd in self._fds:
            text = _read(self.proc / pid / "fdinfo" / fd)
            client = CLIENT.search(text)
            if not client or client.group(1) in clients:
                continue
            gfx, compute = (int(m.group(1)) if (m := pattern.search(text)) else 0 for pattern in ENGINES)
            clients[client.group(1)] = (gfx, compute)
        prev, self._clients = self._clients, clients
        elapsed, self._at = (now - self._at) * 1e9, now
        if not prev or elapsed <= 0:
            return None
        busy = [0, 0]
        for client, times in clients.items():
            if client in prev and all(t >= p for t, p in zip(times, prev[client])):
                busy = [b + t - p for b, t, p in zip(busy, times, prev[client])]
        return min(100.0, 100 * max(busy) / elapsed)

    def gpu_load(self) -> float | None:
        if self.gpu is None:
            return None
        load = self._sensor()
        return load if load is not None else self._engines()

    def loads(self) -> str:
        """The CPU's and the GPU's part of the line, sampled now: 'CPU 12% 54°C | GPU 3% 61°C'."""
        cpu = _part("CPU", self.cpu_load(), _temperature(self.cpu_chip, CPU_LABELS) if self.cpu_chip else None)
        gpu = _part("GPU", self.gpu_load(), _temperature(self.gpu_chip, ("edge",)) if self.gpu_chip else None)
        return " | ".join(part for part in (cpu, gpu) if part)

    def line(self, now: datetime.datetime | None = None, style: ClockStyle = ClockStyle()) -> str:
        return " | ".join(part for part in (self.loads(), clock_text(now, style)) if part)
