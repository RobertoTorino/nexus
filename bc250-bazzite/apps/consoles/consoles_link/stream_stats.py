# SPDX-License-Identifier: AGPL-3.0-or-later
"""A stream's statistics, one line per second, in a file of its own: what was received, decoded and shown, how the
sound buffer fared, how late the window and the controller reader ran, and how busy the processor was. For finding
where stutter and lag come from (owner, 13-10-2026): an average at the end hides a bad second, a line per second
does not.

The files are in ~/.local/state/bc250-console-link/streams (XDG_STATE_HOME), named by the stream's start, the
newest KEEP kept. They hold no account details and the console's address only masked (privacy.py).

The figures come from callables, each giving a dict: counters that only grow (the recorder takes the difference
from the second before) and per-second maxima that the source resets when it is read."""

from __future__ import annotations

import datetime
import os
import platform
import threading
import time
from pathlib import Path
from typing import Callable, TextIO

KEEP = 20
INTERVAL = 1.0

Figures = Callable[[], dict]


def folder() -> Path:
    state = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return Path(state) / "bc250-console-link" / "streams"


def new_path(where: Path, now: datetime.datetime | None = None) -> Path:
    """A new file in *where*, named by the time, with only the newest KEEP - 1 older files left beside it."""
    where.mkdir(parents=True, exist_ok=True)
    old = sorted(where.glob("stream-*.txt"))
    for path in old[:max(0, len(old) - (KEEP - 1))]:
        path.unlink(missing_ok=True)
    return where / f"stream-{(now or datetime.datetime.now()):%Y-%m-%d_%H-%M-%S}.txt"


# --- The processor ----------------------------------------------------------------------------------------------

def cpu_times(proc: Path = Path("/proc")) -> dict[str, tuple[int, int]]:
    """Every processor's (busy, total) clock ticks from /proc/stat, "cpu" for all together."""
    times = {}
    for line in (proc / "stat").read_text().splitlines():
        if not line.startswith("cpu"):
            continue
        name, *values = line.split()
        ticks = [int(v) for v in values]
        idle = ticks[3] + (ticks[4] if len(ticks) > 4 else 0)            # idle and iowait
        times[name] = (sum(ticks) - idle, sum(ticks))
    return times


def thread_times(proc: Path = Path("/proc"), pid: int | None = None) -> dict[int, tuple[str, int]]:
    """This process's threads: thread id -> (name, user + system ticks)."""
    threads = {}
    for task in (proc / str(pid or os.getpid()) / "task").glob("[0-9]*"):
        try:
            stat = (task / "stat").read_text()
        except OSError:
            continue
        name = stat[stat.index("(") + 1:stat.rindex(")")]
        fields = stat[stat.rindex(")") + 2:].split()
        threads[int(task.name)] = (name, int(fields[11]) + int(fields[12]))
    return threads


def cpu_mhz(proc: Path = Path("/proc")) -> list[float]:
    try:
        text = (proc / "cpuinfo").read_text()
    except OSError:
        return []
    return [float(line.split(":")[1]) for line in text.splitlines() if line.startswith("cpu MHz")]


def cpu_model(proc: Path = Path("/proc")) -> str:
    try:
        for line in (proc / "cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def disk_figures(proc: Path = Path("/proc"), pid: int | None = None) -> dict[str, int]:
    """Waiting on the disk: the processors' ticks spent waiting for it (iowait) and in all, the pages swapped in and
    out (/proc/vmstat), and the app's page faults that read from the disk. A board short of memory swaps, and a slow
    drive (one without its own DRAM cache) then makes the stream stutter."""
    figures = {}
    for line in (proc / "stat").read_text().splitlines():
        if line.startswith("cpu "):
            ticks = [int(v) for v in line.split()[1:]]
            figures.update(iowait=ticks[4] if len(ticks) > 4 else 0, ticks=sum(ticks))
            break
    try:
        for line in (proc / "vmstat").read_text().splitlines():
            name, _, value = line.partition(" ")
            if name in ("pswpin", "pswpout"):
                figures[name] = int(value)
    except OSError:
        pass
    try:
        stat = (proc / str(pid or os.getpid()) / "stat").read_text()
        figures["majflt"] = int(stat[stat.rindex(")") + 2:].split()[9])
    except (OSError, IndexError, ValueError):
        pass
    return figures


def disk_line(before: dict[str, int], after: dict[str, int]) -> str:
    def delta(key: str) -> int:
        return after.get(key, 0) - before.get(key, 0)
    return (f"disk wait {_percent(delta('iowait'), delta('ticks')):.0f}%, swapped {delta('pswpin')} in "
            f"{delta('pswpout')} out, app read from disk {delta('majflt')} times")


def _percent(busy: int, total: int) -> float:
    return 100.0 * busy / total if total > 0 else 0.0


def cpu_line(before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]],
             threads_before: dict[int, tuple[str, int]], threads_after: dict[int, tuple[str, int]],
             names: dict[int, str], seconds: float, mhz: list[float], ticks: int) -> str:
    """The processor's second: all cores, the busiest one, the app, its busy threads, the clock."""
    def load(name: str) -> float:
        (b0, t0), (b1, t1) = before.get(name, (0, 0)), after.get(name, (0, 0))
        return _percent(b1 - b0, t1 - t0)
    cores = [load(name) for name in after if name != "cpu"]
    used = {tid: (ticks1 - threads_before[tid][1]) / ticks / max(seconds, 1e-6) * 100
            for tid, (_name, ticks1) in threads_after.items() if tid in threads_before}
    busy = sorted(((percent, names.get(tid) or threads_after[tid][0]) for tid, percent in used.items()
                   if percent >= 5), reverse=True)
    text = (f"cpu {load('cpu'):.0f}% busiest core {max(cores, default=0):.0f}% app {sum(used.values()):.0f}%")
    if busy:
        text += " (" + ", ".join(f"{name} {percent:.0f}%" for percent, name in busy) + ")"
    if mhz:
        text += f" clock {min(mhz):.0f}-{max(mhz):.0f} MHz"
    return text


# --- The line per second ----------------------------------------------------------------------------------------

def _delta(now: dict, before: dict, key: str) -> float:
    return now.get(key, 0) - before.get(key, 0)


def line(stream_now: dict, stream_before: dict, window: dict, window_before: dict, reader: dict,
         reader_before: dict, seconds: float) -> str:
    """The stream's second, from the figures of the stream (StreamConnection.figures), the window
    (StreamWindow.figures) and the controller reader (gamepad.Reader.figures); any of them may be empty."""
    parts = []
    if stream_now:
        frames = _delta(stream_now, stream_before, "frames")
        mbit = _delta(stream_now, stream_before, "frame_bytes") * 8 / max(seconds, 1e-6) / 1e6
        decoded = _delta(stream_now, stream_before, "decoded")
        decode_ms = _delta(stream_now, stream_before, "decode_seconds") * 1000 / max(frames, 1)
        gap_ms = stream_now.get("frame_gap_max", 0) * 1000
        parts.append(f"in {frames:.0f} frames {mbit:.1f} Mbit/s, longest gap {gap_ms:.0f} ms, "
                     f"lost {_delta(stream_now, stream_before, 'frames_lost'):.0f}, "
                     f"FEC {_delta(stream_now, stream_before, 'fec_frames'):.0f}")
        parts.append(f"decode {decoded:.0f} avg {decode_ms:.1f} max {stream_now.get('decode_max', 0) * 1000:.1f} ms")
        if "idr_requests" in stream_now:
            failed = _delta(stream_now, stream_before, "fec_failed")
            parts.append(f"recovery: FEC failed {failed:.0f}, key frames asked "
                         f"{_delta(stream_now, stream_before, 'idr_requests'):.0f}, skipped "
                         f"{_delta(stream_now, stream_before, 'frames_skipped'):.0f}, no reference "
                         f"{_delta(stream_now, stream_before, 'missing_reference'):.0f}")
        parts.append(f"sound in {_delta(stream_now, stream_before, 'audio_frames'):.0f} frames, "
                     f"lost {_delta(stream_now, stream_before, 'audio_lost'):.0f}")
    if window:
        shown = _delta(window, window_before, "shown")
        parts.append(f"shown {shown:.0f}, skipped {_delta(window, window_before, 'replaced'):.0f}, age avg "
                     f"{window.get('age_sum', 0) * 1000 / max(window.get('age_count', 0), 1):.0f} max "
                     f"{window.get('age_max', 0) * 1000:.0f} ms")
        parts.append(f"window late max {window.get('late_max', 0) * 1000:.0f} ms")
        if "sound_buffered_ms" in window:
            parts.append(f"sound buffer {window['sound_buffered_ms']:.0f} ms, gaps "
                         f"{_delta(window, window_before, 'sound_silence_ms'):.0f} ms, dropped "
                         f"{_delta(window, window_before, 'sound_dropped_ms'):.0f} ms"
                         + (" (muted)" if window.get("muted") else ""))
    if reader:
        parts.append(f"controller {_delta(reader, reader_before, 'polls'):.0f} reads, longest gap "
                     f"{reader.get('gap_max', 0) * 1000:.0f} ms")
    return " | ".join(parts)


class Recorder:
    """Writes the header, then a line every INTERVAL from its own thread until stop(), and one for the rest."""

    def __init__(self, out: TextIO, header: list[str], stream: Figures | None = None, window: Figures | None = None,
                 reader: Figures | None = None, interval: float = INTERVAL, proc: Path = Path("/proc")):
        self.out, self.interval, self.proc = out, interval, proc
        self.sources = {"stream": stream, "window": window, "reader": reader}
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._run, name="stream-stats", daemon=True)
        self.lines = 0
        for text in header:
            out.write(f"# {text}\n")
        out.flush()

    def start(self) -> Recorder:
        self.thread.start()
        return self

    def stop(self) -> None:
        self.stopping.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)

    def _take(self) -> dict[str, dict]:
        taken = {}
        for name, source in self.sources.items():
            try:
                taken[name] = source() if source is not None else {}
            except Exception:                               # a source going away at the end: nothing to report
                taken[name] = {}
        return taken

    def _cpu(self) -> tuple:
        try:
            return cpu_times(self.proc), thread_times(self.proc), disk_figures(self.proc)
        except (OSError, ValueError, IndexError):
            return {}, {}, {}

    def _run(self) -> None:
        ticks = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
        start = before_time = time.monotonic()
        before, (cpu_before, threads_before, disk_before) = self._take(), self._cpu()
        stopped = False
        while not stopped:
            stopped = self.stopping.wait(self.interval)          # the last, shorter second is written too
            now_time = time.monotonic()
            now, (cpu_now, threads_now, disk_now) = self._take(), self._cpu()
            seconds = now_time - before_time
            names = {t.native_id: t.name for t in threading.enumerate() if t.native_id is not None}
            text = line(now["stream"], before["stream"], now["window"], before["window"], now["reader"],
                        before["reader"], seconds)
            if cpu_now and cpu_before:
                text += " | " + cpu_line(cpu_before, cpu_now, threads_before, threads_now, names, seconds,
                                         cpu_mhz(self.proc), ticks)
            if disk_now and disk_before:
                text += " | " + disk_line(disk_before, disk_now)
            try:
                self.out.write(f"{now_time - start:7.1f} s | {text}\n")
                self.out.flush()
            except (OSError, ValueError):
                return
            self.lines += 1
            before, cpu_before, threads_before, disk_before, before_time = now, cpu_now, threads_now, disk_now, now_time
