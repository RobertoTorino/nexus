# SPDX-License-Identifier: GPL-3.0-or-later

"""Decides whether bc250-cu-bisect.sh's own recorded results accept a combined mask for install.

Nothing here runs the bisect script or any register write; it only reads the state the script already
keeps in ~/.local/share/bc250-cu-bisect/. A mask is only accepted once that state proves:

  - it was retested as its own baseline (umr-config BASE), with every WGP in it unlocked, so the
    recorded run has no individual "SEx.SHy.WGPn" items left, only "control";
  - every round of that retest is recorded with outcome PASS (no crash, no drift, no mismatch);
  - no attempt is still marked as in progress (umr-pending would mean an interrupted run); and
  - the 4 shader-array rows are unlocked evenly, at one of the three real levels: 3 WGPs per row
    (24 CUs, stock), 4 per row (32 CUs) or 5 per row (40 CUs, max). The GPU feeds all 4 arrays in
    lockstep, so anything in between performs like its smallest row while drawing the extra power
    (see the CU Bisect manual).

This mirrors the "retest the combination" step bc250-cu-bisect.sh's own summary suggests
(--reset && --baseline <masks> --control-only --rounds N) - the GUI just checks that step was actually
done and passed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

STATE_DIR = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local/share")) / "bc250-cu-bisect"
CONFIG = STATE_DIR / "umr-config"
RUNS = STATE_DIR / "umr-runs.tsv"
PENDING = STATE_DIR / "umr-pending"

MASK_RE = re.compile(r"^0x[0-9a-fA-F]{1,2}(,0x[0-9a-fA-F]{1,2}){3}$")
# Outcomes that count as a failed attempt in bc250-cu-bisect.sh (same FAIL_RE as the script).
FAIL_RE = re.compile(r"^(CRASH-APPLY|CRASH-LOAD|FAULT|ERRORS|LOAD-FAIL|DRIFT|MISMATCH)$")
INCOMPLETE = {"ABORTED", "SKIPPED", ""}
# WGPs per shader-array row -> total CUs. Only these three are installable; see check().
LEVELS = {3: 24, 4: 32, 5: 40}


def popcount(n: int) -> int:
    return bin(n & 0x1F).count("1")


def cu_count(masks: str) -> int:
    return sum(popcount(int(m, 16)) for m in masks.split(",")) * 2


def even_level(masks: str) -> int | None:
    """WGPs-per-row if `masks` is one of the three allowed even levels, else None."""
    counts = {popcount(int(m, 16)) for m in masks.split(",")}
    if len(counts) != 1:
        return None
    level = counts.pop()
    return level if level in LEVELS else None


@dataclass
class GateResult:
    accepted: bool
    masks: str | None = None
    cu_total: int | None = None
    # Human-readable lines: the reason(s) it was rejected, or a confirmation of what passed.
    reasons: list[str] = field(default_factory=list)


def _read_config() -> dict[str, str]:
    cfg: dict[str, str] = {}
    if CONFIG.is_file():
        for line in CONFIG.read_text(errors="replace").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                cfg[k] = v
    return cfg


def check() -> GateResult:
    if not CONFIG.is_file():
        return GateResult(False, reasons=[
            f"No bc250-cu-bisect.sh results found in {STATE_DIR}. Run that script first."])

    cfg = _read_config()
    base = cfg.get("BASE", "")
    if not MASK_RE.match(base):
        return GateResult(False, reasons=[f"No usable baseline recorded ({base or 'none'!r})."])

    if PENDING.is_file():
        return GateResult(False, masks=base, reasons=[
            "An attempt is still marked as in progress (umr-pending exists). Finish that bisect run, "
            "or reboot and let it resume, before this mask can be accepted."])

    rows = [int(m, 16) for m in base.split(",")]
    counts = [popcount(m) for m in rows]
    if len(set(counts)) != 1:
        target = min(counts) if min(counts) in LEVELS else 3
        suggestion = ",".join(f"0x{(1 << target) - 1:02x}" for _ in range(4))
        return GateResult(False, masks=base, reasons=[
            f"The recorded baseline ({base}) is uneven across the 4 rows ({'/'.join(map(str, counts))} "
            "WGPs). The GPU feeds all 4 shader arrays in lockstep, so it would run no faster than its "
            f"smallest row ({min(counts)} WGPs = {LEVELS.get(min(counts), min(counts) * 8)} CUs) while "
            "drawing the extra power. Retest a mask that unlocks the same number of WGPs on every row:",
            f"./bc250-cu-bisect.sh --reset && ./bc250-cu-bisect.sh --baseline {suggestion} --control-only --rounds 1"])

    if counts[0] not in LEVELS:
        return GateResult(False, masks=base, reasons=[
            f"The recorded baseline ({base}) unlocks {counts[0]} WGPs per row. Only 3 per row "
            "(24 CUs, stock), 4 per row (32 CUs) and 5 per row (40 CUs, max) are supported."])

    try:
        rounds = int(cfg.get("ROUNDS", "0") or 0)
    except ValueError:
        rounds = 0

    if not RUNS.is_file():
        return GateResult(False, masks=base, reasons=["No attempts recorded yet for this baseline."])

    items: set[str] = set()
    control: dict[int, str] = {}
    for line in RUNS.read_text(errors="replace").splitlines():
        cols = line.split("\t")
        if len(cols) < 6:
            continue
        round_s, item, outcome = cols[2], cols[3], cols[5]
        items.add(item)
        if item == "control":
            try:
                control[int(round_s)] = outcome
            except ValueError:
                pass

    extra = sorted(items - {"control"})
    if extra:
        return GateResult(False, masks=base, reasons=[
            f"This baseline still has {len(extra)} WGP(s) under individual test ({', '.join(extra[:4])}"
            f"{', ...' if len(extra) > 4 else ''}) - that's a bisect run, not yet the retest of a final, "
            "fully-combined mask. Retest it with:",
            f"./bc250-cu-bisect.sh --reset && ./bc250-cu-bisect.sh --baseline {base} --control-only --rounds 1"])

    if rounds < 1 or len(control) < rounds:
        return GateResult(False, masks=base, reasons=[
            f"Only {len(control)} of {rounds or '?'} retest round(s) are recorded so far."])

    failed = {r: o for r, o in control.items() if FAIL_RE.match(o) or o in INCOMPLETE}
    if failed:
        bad = ", ".join(f"round {r}: {o or 'incomplete'}" for r, o in sorted(failed.items()))
        return GateResult(False, masks=base, reasons=[f"The retest did not pass every round ({bad})."])

    total = cu_count(base)
    return GateResult(True, masks=base, cu_total=total, reasons=[
        f"{base} ({total} CUs, {counts[0]} WGPs on each of the 4 shader-array rows) passed "
        f"{rounds} retest round(s) as its own baseline."])
