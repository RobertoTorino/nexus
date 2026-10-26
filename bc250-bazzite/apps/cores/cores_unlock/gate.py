# SPDX-License-Identifier: GPL-3.0-or-later

"""Decides whether bc250-cores-bisect.sh's own recorded results accept the core unlock for install.

Nothing here runs the bisect script or touches the SMU; it only reads the state the script already
keeps in ~/.local/share/bc250-cores-bisect/. The verdict mirrors the script's own summary - the unlock
is accepted only when that state proves:

  - the run reached the bisect phase (the unlock was applied and the new cores came up);
  - no attempt is still marked as in progress (pending = an interrupted run);
  - the control (stock 6C/12T, before the unlock) never failed;
  - post-control, every new core alone and the combined item each have a result for every round,
    and every one of those results is PASS (no MCE, verify failure, crash, ...).

Because the SMU primitive enables all cores or none, a single failed item rejects the unlock as a whole.
Fewer control rounds than --rounds, or attempts that ran a shorter load than the current --time, are
reported as notes but don't block - the script's own verdict treats them the same way.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

STATE_DIR = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local/share")) / "bc250-cores-bisect"
CONFIG = STATE_DIR / "config"
RUNS = STATE_DIR / "runs.tsv"
PENDING = STATE_DIR / "pending"

PASS = "PASS"
ABORTED = "ABORTED"


@dataclass
class Attempt:
    round: int
    item: str
    outcome: str
    load: str  # seconds as text, "" for results written by older script versions


@dataclass
class GateResult:
    accepted: bool
    # Human-readable lines: why it was rejected, or what passed (plus notes).
    reasons: list[str] = field(default_factory=list)
    base_cores: list[int] = field(default_factory=list)
    new_cores: list[int] = field(default_factory=list)
    # Per new core: "good", "bad" (failed every try), "random", or "none" (not tested yet).
    core_verdicts: dict[int, str] = field(default_factory=dict)


def read_config(path: Path = CONFIG) -> dict[str, str]:
    cfg: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(errors="replace").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                cfg[k] = v
    return cfg


def read_runs(path: Path = RUNS) -> list[Attempt]:
    attempts: list[Attempt] = []
    if not path.is_file():
        return attempts
    for line in path.read_text(errors="replace").splitlines():
        cols = line.split("\t")
        if len(cols) < 6:
            continue
        try:
            rnd = int(cols[2])
        except ValueError:
            continue
        load = cols[11] if len(cols) > 11 and cols[11].isdigit() else ""
        attempts.append(Attempt(rnd, cols[3], cols[5], load))
    return attempts


def _ids(text: str) -> list[int]:
    return [int(t) for t in text.split() if t.isdigit()]


def verdict(outcomes: list[str]) -> str:
    """Same classification as the script's item_verdict()."""
    if not outcomes:
        return "none"
    fails = sum(o != PASS for o in outcomes)
    if fails == 0:
        return "good"
    return "bad" if fails == len(outcomes) else "random"


def check(state_dir: Path = STATE_DIR) -> GateResult:
    config, runs, pending = state_dir / "config", state_dir / "runs.tsv", state_dir / "pending"
    if not config.is_file():
        return GateResult(False, reasons=[
            f"No bc250-cores-bisect.sh results found in {state_dir}. Run that script first."])

    cfg = read_config(config)
    base, new = _ids(cfg.get("BASE_CORES", "")), _ids(cfg.get("NEW_CORES", ""))
    result = GateResult(False, base_cores=base, new_cores=new)
    attempts = [a for a in read_runs(runs) if a.outcome != ABORTED]

    def outcomes(item: str) -> list[str]:
        return [a.outcome for a in attempts if a.item == item]

    result.core_verdicts = {c: verdict(outcomes(f"core{c}")) for c in new}

    phase = cfg.get("PHASE", "control")
    if phase != "bisect" or not new:
        result.reasons = [
            "The bisect hasn't started yet (phase: %s). bc250-cores-bisect.sh first runs the control "
            "on the stock cores, applies the unlock, and only then tests the new cores." % phase]
        return result

    if pending.is_file() and pending.stat().st_size:
        result.reasons = [
            "An attempt is still marked as in progress. Finish that bisect run (reboot and let it "
            "resume) before the unlock can be accepted."]
        return result

    try:
        rounds = int(cfg.get("ROUNDS", "0") or 0)
    except ValueError:
        rounds = 0
    if rounds < 1:
        result.reasons = ["No valid round count recorded in the bisect config."]
        return result

    control = outcomes("control")
    if any(o != PASS for o in control):
        result.reasons = [
            "The control (stock 6C/12T, before the unlock) failed. The board, power, heat or the load "
            "tool is at fault, so nothing can be concluded about the new cores. Fix that first."]
        return result
    if not control:
        result.reasons = ["No control result is recorded."]
        return result

    items = ["post-control", *(f"core{c}" for c in new)]
    if len(new) > 1:
        items.append("combined")

    failed = {it: outcomes(it) for it in items if any(o != PASS for o in outcomes(it))}
    if "post-control" in failed:
        result.reasons = [
            "POST-CONTROL failed: a stock core fails after the unlock. The unlock destabilises the whole "
            "SoC on this board. Cold boot (full power off) to revert; don't persist it."]
        return result
    if failed:
        lines = [f"{it}: {' '.join(o)} ({verdict(o).upper()})" for it, o in failed.items()]
        result.reasons = [
            "Not every new-core item passed. The SMU primitive can only enable ALL cores, so one failing "
            "item means: don't persist the unlock. Cold boot (full power off) to revert.", *lines]
        if any(verdict(o) == "random" for o in failed.values()):
            result.reasons.append(
                "Random failures point to power or heat rather than bad silicon: improve cooling and "
                "retest with --reset.")
        return result

    missing = [f"{it} round {r}" for r in range(1, rounds + 1) for it in items
               if not any(a.item == it and a.round == r for a in attempts)]
    if missing:
        result.reasons = [
            f"The bisect isn't finished: {len(missing)} of {rounds * len(items)} attempt(s) still to do "
            f"(next: {missing[0]}). Run bc250-cores-bisect.sh again, or let --auto continue."]
        return result

    tested = ["Control", "post-control", *(f"core{c}" for c in new)]
    if len(new) > 1:
        tested.append("combined")
    result.accepted = True
    result.reasons = [
        f"{', '.join(tested[:-1])} and {tested[-1]} passed every one of {rounds} round(s). "
        "The 8C/16T unlock looks safe on this board."]

    notes = []
    if len(control) < rounds:
        notes.append(f"The control ran {len(control)} round(s), fewer than the {rounds} of the other "
                     "items (the rounds were raised after it finished).")
    time = cfg.get("TIME", "")
    shorter = sorted({it for it in ["control", *items] for a in attempts
                      if a.item == it and a.load and a.load != time})
    if shorter:
        notes.append(f"Some attempts ran a different load than the current {time}s ({', '.join(shorter)}); "
                     "the settings changed during the run.")
    result.reasons += [f"Note: {n}" for n in notes]
    return result
