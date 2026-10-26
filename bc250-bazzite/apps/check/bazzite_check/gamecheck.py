# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-session verdicts for the Game details page.

The wrapper (gamemon) records a CSV of samples and, when the game ends, a small JSON sidecar next to
it with what only makes sense once per session: the memory budget, the GPU power cap, the frametime
statistics from MangoHud's per-frame log and the amdgpu errors the kernel logged while the game ran.
This module turns both into short pass/warn/fail checks. Plain Python (no Qt), so the wrapper can
use it as well.
"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# amdgpu trouble worth reporting against a play session (the same families as tests 35 and 37).
KERNEL_RE = re.compile(
    r"ring .*timeout|GPU reset|gpu recover|Failed to pin|fatal flip error|VM_L2|page fault|"
    r"amdgpu.*(hang|reset|fail)", re.I)
MIN_FRAMES = 100          # below this a frametime log says nothing
STUTTER_FACTOR = 2.0      # a frame over twice the median is a visible hitch
SHORT_SESSION_S = 120.0   # below this the averages are mostly loading screens


@dataclass
class Check:
    level: str            # "ok" | "info" | "warn" | "error"
    title: str
    text: str


@dataclass
class Frametime:
    frames: int
    seconds: float
    avg_fps: float
    low1_fps: float
    low01_fps: float
    stutter_pct: float


# ----------------------------------------------------------------- reading
def read_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def column(rows: list[dict[str, str]], name: str) -> list[float]:
    """Every value of one CSV column that is a number; empty cells are skipped."""
    out: list[float] = []
    for r in rows:
        try:
            out.append(float(r.get(name) or ""))
        except ValueError:
            pass
    return out


def summary_path(csv_path: Path) -> Path:
    return csv_path.with_suffix(".json")


def write_summary(csv_path: Path, data: dict) -> None:
    try:
        summary_path(csv_path).write_text(json.dumps(data, indent=1), encoding="utf-8")
    except OSError:
        pass


def load_summary(csv_path: Path) -> dict:
    try:
        data = json.loads(summary_path(csv_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


# -------------------------------------------------------------- frametimes
def find_mangohud_log(dirs: list[Path], start: float, end: float) -> Path | None:
    """The MangoHud per-frame CSV that was last written during this session."""
    best, best_t = None, 0.0
    for d in dirs:
        try:
            with os.scandir(d) as it:
                for e in it:
                    if not e.name.endswith(".csv") or e.name.endswith("_summary.csv"):
                        continue
                    try:
                        mt = e.stat().st_mtime
                    except OSError:
                        continue
                    if start - 5 <= mt <= end + 30 and mt > best_t:
                        best, best_t = Path(e.path), mt
        except OSError:
            continue
    return best


def frametime_stats(path: Path) -> Frametime | None:
    """1% / 0.1% lows and the stutter share from MangoHud's frametime column (test 48's maths).

    Current MangoHud builds write frametimes in microseconds and older ones in milliseconds, so the
    unit is taken from the magnitude of the median instead of being assumed. Returns None when the
    file has no frametime column or too few frames to judge."""
    col: int | None = None
    values: list[float] = []
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as fh:
            for n, row in enumerate(csv.reader(fh)):
                if col is None:
                    for i, name in enumerate(row):
                        if name.strip().lower() == "frametime":
                            col = i
                            break
                    if col is None and n > 10:      # the header is in the first few lines or nowhere
                        return None
                    continue
                if len(row) > col:
                    try:
                        v = float(row[col])
                    except ValueError:
                        continue
                    if v > 0:
                        values.append(v)
    except OSError:
        return None
    if len(values) < MIN_FRAMES:
        return None
    values.sort()
    median = values[len(values) // 2]
    to_ms = 0.001 if median > 1000 else 1.0         # over 1000 it can only be microseconds
    ft = [v * to_ms for v in values]
    total = sum(ft)
    if total <= 0:
        return None
    median_ms = median * to_ms
    stutter = sum(1 for v in ft if v > STUTTER_FACTOR * median_ms)
    worst1 = ft[-max(1, len(ft) // 100):]
    worst01 = ft[-max(1, len(ft) // 1000):]
    return Frametime(frames=len(ft), seconds=total / 1000,
                     avg_fps=1000 * len(ft) / total,
                     low1_fps=1000 * len(worst1) / sum(worst1),
                     low01_fps=1000 * len(worst01) / sum(worst01),
                     stutter_pct=100 * stutter / len(ft))


# ----------------------------------------------------------- kernel errors
def kernel_errors(start: float, end: float, limit: int = 8) -> list[str]:
    """amdgpu errors the kernel logged during the session. Silent when the journal is not readable."""
    try:
        res = subprocess.run(
            ["journalctl", "-k", "-q", "--no-pager", "-o", "short-iso",
             "--since", f"@{int(start)}", "--until", f"@{int(end) + 5}"],
            capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return []
    if res.returncode != 0:
        return []
    return [ln.strip() for ln in res.stdout.splitlines() if KERNEL_RE.search(ln)][:limit]


# ---------------------------------------------------------------- verdicts
def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _frametime_check(rows: list[dict[str, str]], summary: dict) -> Check:
    ft = summary.get("frametime")
    if isinstance(ft, dict) and ft.get("frames", 0) >= MIN_FRAMES and ft.get("avg_fps"):
        ratio = 100 * ft["low1_fps"] / ft["avg_fps"]
        text = (f"{ft['avg_fps']:.0f} FPS average, 1% low {ft['low1_fps']:.0f}, "
                f"0.1% low {ft['low01_fps']:.0f}, {ft['stutter_pct']:.1f}% of frames over twice the "
                f"median ({ft['frames']} frames).")
        if ratio < 50:
            return Check("warn", f"Stutter: the 1% low is {ratio:.0f}% of the average",
                         text + " Usual causes here: first-run shader compilation, the VRAM carve-out "
                                "filling up (tests 37 and 47) or hhd running (test 27). A second "
                                "session of the same game that keeps this ratio points at memory "
                                "pressure rather than shader compilation.")
        return Check("ok", f"Frametimes are consistent (1% low is {ratio:.0f}% of the average)", text)
    if column(rows, "fps"):
        return Check("info", "Smoothness not judged",
                     "Only sampled FPS is in this log (one average per sample interval), which hides "
                     "single hitches. MangoHud's per-frame log was not found for this session; test 48 "
                     "does the same maths over all logs it can find.")
    return Check("info", "No FPS recorded",
                 "Use the launch line with MangoHud and click \"Enable FPS logging\" once; without it "
                 "FPS, the 1% low and the stutter share stay empty.")


def _limit_check(rows: list[dict[str, str]]) -> Check | None:
    gpu = _avg(column(rows, "game_gpu_pct")) or _avg(column(rows, "gpu_pct"))
    if gpu is None:
        return None
    cpu = _avg(column(rows, "game_cpu_pct"))
    detail = f"GPU {gpu:.0f}% average"
    if cpu is not None:
        detail += f", the game's CPU share {cpu:.0f}% of all cores together"
    if gpu >= 85:
        return Check("ok", "GPU-bound",
                     detail + ". The GPU is the limit: lower the resolution or the settings to gain FPS.")
    if gpu >= 60:
        return Check("info", "Mixed limit",
                     detail + ". Neither side is saturated — often a loading-heavy session or a partial cap.")
    return Check("info", "Not GPU-bound",
                 detail + ". A CPU limit, an FPS cap or vsync holds the frame rate back; lighter "
                          "graphics settings would not help here.")


def _memory_checks(rows: list[dict[str, str]], budget: dict) -> list[Check]:
    out: list[Check] = []
    for col, total_key, label, hint in (
            ("vram_used_mib", "vram_total_mib", "VRAM",
             " The carve-out is this game's ceiling; a full one causes the framebuffer pin failures of "
             "test 37 and can be raised with bc250_memcfg (test 47)."),
            ("gtt_used_mib", "gtt_total_mib", "GTT",
             " GTT is system RAM lent to the GPU; running it dry makes the game page over PCIe.")):
        used = column(rows, col)
        total = budget.get(total_key)
        if not used or not total:
            continue
        pct = 100 * max(used) / total
        text = f"Peak {max(used):.0f} MiB of {total:.0f} MiB ({pct:.0f}%)."
        if pct >= 95:
            out.append(Check("error", f"{label} ran out", text + hint))
        elif pct >= 85:
            out.append(Check("warn", f"{label} nearly full", text + hint))
        else:
            out.append(Check("ok", f"{label} headroom is fine", text))
    free = column(rows, "mem_avail_mib")
    if free:
        if min(free) < 512:
            out.append(Check("warn", "System memory ran low",
                             f"Only {min(free):.0f} MiB of RAM was left at the tightest point; the OOM "
                             f"killer or swapping can hit the game here."))
        else:
            out.append(Check("ok", "System memory headroom is fine",
                             f"At least {min(free):.0f} MiB of RAM stayed free."))
    return out


def _throttle_checks(rows: list[dict[str, str]], budget: dict, duration: float) -> list[Check]:
    out: list[Check] = []
    power = column(rows, "gpu_power_w")
    cap = budget.get("power_cap_w")
    if power and cap and 100 * max(power) / cap >= 95:
        out.append(Check("info", "Power-capped",
                         f"GPU power peaked at {max(power):.0f} W against the {cap:.0f} W cap: the board "
                         f"is at its power limit. That is normal under full load, but clocks cannot rise "
                         f"any further (test 40)."))
    temp = column(rows, "gpu_temp_c")
    if temp:
        peak = max(temp)
        if peak >= 95:
            out.append(Check("error", "GPU too hot",
                             f"Peak {peak:.0f} °C. Above 95 °C the GPU clamps hard and hangs become likely."))
        elif peak >= 90:
            out.append(Check("warn", "GPU running hot",
                             f"Peak {peak:.0f} °C — close to the throttle point."))
        else:
            out.append(Check("ok", "GPU temperature is fine",
                             f"Peak {peak:.0f} °C, {_avg(temp) or 0:.0f} °C average."))
    ctemp = column(rows, "cpu_temp_c")
    if ctemp and max(ctemp) >= 90:
        out.append(Check("warn", "CPU running hot", f"Peak Tctl {max(ctemp):.0f} °C."))
    clk = column(rows, "sclk_mhz")
    if len(clk) >= 10 and duration >= 300:
        q = max(1, len(clk) // 5)
        first, last = _avg(clk[:q]) or 0.0, _avg(clk[-q:]) or 0.0
        if first and last < 0.85 * first:
            out.append(Check("warn", "Clocks dropped over the session",
                             f"The GPU core averaged {first:.0f} MHz in the first fifth and {last:.0f} MHz "
                             f"in the last ({100 * last / first:.0f}%): sustained performance is limited "
                             f"by heat or the power cap."))
        elif first:
            out.append(Check("ok", "Clocks held up",
                             f"{first:.0f} MHz at the start against {last:.0f} MHz at the end."))
    fan = column(rows, "fan_rpm")
    if fan and temp and max(fan) == 0 and max(temp) >= 70:
        out.append(Check("warn", "No fan RPM reported",
                         "The fan never reported a speed while the GPU passed 70 °C — either the SuperIO "
                         "sensor is missing (test 22) or the fan is not spinning."))
    return out


def session_checks(rows: list[dict[str, str]], summary: dict) -> list[Check]:
    """The verdicts shown on the Game details page, in reading order."""
    if not rows:
        return [Check("info", "No samples", "This session has no samples in it.")]
    budget = summary.get("budget") or {}
    elapsed = column(rows, "elapsed_s")
    duration = elapsed[-1] if elapsed else 0.0

    checks = [_frametime_check(rows, summary)]
    if (limit := _limit_check(rows)) is not None:
        checks.append(limit)
    checks += _memory_checks(rows, budget)
    checks += _throttle_checks(rows, budget, duration)

    errors = summary.get("kernel_errors")
    if isinstance(errors, list):
        if errors:
            checks.append(Check("error", f"{len(errors)} amdgpu error(s) during this session",
                                errors[0] + ("" if len(errors) == 1 else f" (+{len(errors) - 1} more)")))
        else:
            checks.append(Check("ok", "No GPU errors in the kernel log",
                                "No ring timeout, GPU reset, VM fault or framebuffer pin failure while "
                                "this game ran."))
    if 0 < duration < SHORT_SESSION_S:
        checks.append(Check("info", "Short session",
                            f"Only {duration:.0f} s of gameplay; play longer for a verdict that means "
                            f"something."))
    return checks
