# SPDX-License-Identifier: GPL-3.0-or-later
"""Telemetry history: one row per poll (load, clock, temperature, socket power, performance mode, runtime
range), kept in memory for the chart window, exportable as CSV and readable back as a reference to compare a
live session against (`read_csv`, `summarize`)."""

from __future__ import annotations

import csv
from collections import deque
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Iterator


from . import fmt

if TYPE_CHECKING:
    from .pages import Snapshot

MAX_SECONDS = 3600          # an hour of samples is kept; the chart shows a window of it

COLUMNS = ("time", "load_percent", "clock_mhz", "temp_c", "socket_power_w", "performance_mode", "range_min_mhz",
           "range_max_mhz")


@dataclass(frozen=True, slots=True)
class Sample:
    time: datetime
    load: float | None
    clock: int | None
    temp: float | None
    power: float | None
    perf_enabled: bool | None       # None when the governor's bus is not reachable
    range_min: int | None
    range_max: int | None

    @classmethod
    def from_snapshot(cls, snap: "Snapshot", when: datetime) -> "Sample":
        t = snap.telemetry
        perf = snap.perf
        return cls(when, t.load_percent, t.clock_mhz, t.temp_c,
                   t.metrics.socket_power_w if t.metrics is not None else None,
                   perf.enabled if perf.available else None,
                   perf.current_min if perf.available else None,
                   perf.current_max if perf.available else None)

    def row(self) -> list[str]:
        def cell(value, fmt="{}"):
            return "" if value is None else fmt.format(value)
        return [self.time.isoformat(timespec="seconds"), cell(self.load, "{:.1f}"), cell(self.clock),
                cell(self.temp, "{:.1f}"), cell(self.power, "{:.2f}"),
                "" if self.perf_enabled is None else ("on" if self.perf_enabled else "off"),
                cell(self.range_min), cell(self.range_max)]


class History:
    def __init__(self, maxlen: int):
        self._samples: deque[Sample] = deque(maxlen=maxlen)

    def __len__(self) -> int:
        return len(self._samples)

    def add(self, sample: Sample) -> None:
        self._samples.append(sample)

    def last(self, count: int) -> list[Sample]:
        if count >= len(self._samples):
            return list(self._samples)
        return list(self._samples)[-count:]

    def __iter__(self) -> Iterator[Sample]:
        return iter(self._samples)

    def span(self) -> tuple[datetime, datetime] | None:
        if not self._samples:
            return None
        return self._samples[0].time, self._samples[-1].time

    def write_csv(self, path: Path) -> int:
        """Write every kept sample; returns the row count."""
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(COLUMNS)
            for sample in self._samples:
                writer.writerow(sample.row())
        return len(self._samples)


def read_csv(path: Path) -> list[Sample]:
    """Samples from a file written by `write_csv`. Tolerates missing optional columns and blank cells; rows
    without a parsable time are skipped. Raises ValueError when the header is not ours."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "time" not in reader.fieldnames:
            raise ValueError("not a telemetry export: no 'time' column")
        unknown = [c for c in ("load_percent", "clock_mhz", "temp_c") if c not in reader.fieldnames]
        if unknown:
            raise ValueError(fmt("not a telemetry export: missing column(s) %1",
                                  ", ".join(unknown)))
        samples: list[Sample] = []
        for row in reader:
            try:
                when = datetime.fromisoformat(row["time"])
            except (TypeError, ValueError):
                continue
            perf = (row.get("performance_mode") or "").strip()
            samples.append(Sample(when, _num(row.get("load_percent"), float), _num(row.get("clock_mhz"), int),
                                  _num(row.get("temp_c"), float), _num(row.get("socket_power_w"), float),
                                  None if perf not in ("on", "off") else perf == "on",
                                  _num(row.get("range_min_mhz"), int), _num(row.get("range_max_mhz"), int)))
    return samples


def _num(cell: str | None, kind):
    cell = (cell or "").strip()
    if not cell:
        return None
    try:
        return kind(float(cell)) if kind is int else kind(cell)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class Summary:
    seconds: int
    load_avg: float | None
    load_max: float | None
    clock_avg: float | None
    clock_max: int | None
    temp_avg: float | None
    temp_max: float | None
    power_avg: float | None

    def text(self) -> str:
        parts = []
        if self.load_avg is not None:
            parts.append(fmt("load %1 %", f"{self.load_avg:.0f}"))
        if self.clock_avg is not None:
            parts.append(fmt("clock %1 MHz (max %2)",
                              f"{self.clock_avg:.0f}", str(self.clock_max)))
        if self.temp_avg is not None:
            parts.append(fmt("%1 °C (max %2)",
                              f"{self.temp_avg:.0f}", f"{self.temp_max:.0f}"))
        if self.power_avg is not None:
            parts.append(fmt("%1 W", f"{self.power_avg:.0f}"))
        return ", ".join(parts) if parts else "no readings"


def summarise(samples: list[Sample]) -> Summary:
    """Averages and peaks over `samples`; seconds is wall time from first to last sample."""
    def avg(values):
        values = [v for v in values if v is not None]
        return sum(values) / len(values) if values else None

    def peak(values):
        values = [v for v in values if v is not None]
        return max(values) if values else None

    seconds = round((samples[-1].time - samples[0].time).total_seconds()) if len(samples) > 1 else 0
    return Summary(seconds, avg(s.load for s in samples), peak(s.load for s in samples),
                   avg(s.clock for s in samples), peak(s.clock for s in samples),
                   avg(s.temp for s in samples), peak(s.temp for s in samples),
                   avg(s.power for s in samples))


def default_csv_name(now: datetime) -> str:
    return f"bc250-telemetry-{now:%Y%m%d-%H%M%S}.csv"


assert len(COLUMNS) == len(fields(Sample)), "CSV header and Sample fields must line up"
