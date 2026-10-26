# SPDX-License-Identifier: GPL-3.0-or-later

"""Turns the launcher GUI's choices into a bc250-gpu-oc-bisect.sh command line, and the validation
that goes with it - kept free of any Qt import so it's easy to unit-test on its own.

The hard rails mirror the script's own (which re-checks them anyway): the community record of
hard-locks above ~1850-2000 MHz and one bricked-board report from overvolting are the reason."""

from __future__ import annotations

import shlex
from dataclasses import dataclass

HARD_MAX_FREQ = 2500
HARD_MAX_VOLT = 1100
HARD_MIN_VOLT = 700

DEFAULT_MAX_FREQ = 2200
DEFAULT_MIN_VOLT = 850
DEFAULT_FREQ_STEP = 50
DEFAULT_VOLT_STEP = 25


@dataclass
class SweepOptions:
    time_secs: int = 180
    rounds: int = 3
    sweep_oc: bool = True
    sweep_uv: bool = True
    max_freq: int = DEFAULT_MAX_FREQ
    min_volt: int = DEFAULT_MIN_VOLT
    oc_volt: int = 0             # 0 = use the config's top voltage (script default)
    freq_step: int = DEFAULT_FREQ_STEP
    volt_step: int = DEFAULT_VOLT_STEP
    per_boot: bool = False

    def validate(self) -> list[str]:
        errors = []
        if self.time_secs < 60:
            errors.append("Load time must be at least 60 seconds.")
        if not 2 <= self.rounds <= 9:
            errors.append("Rounds must be between 2 and 9.")
        if not (self.sweep_oc or self.sweep_uv):
            errors.append("Pick at least one sweep: overclock, undervolt or both.")
        if not 0 < self.max_freq <= HARD_MAX_FREQ:
            errors.append(f"Max frequency must be between 1 and {HARD_MAX_FREQ} MHz (hard ceiling).")
        if self.min_volt < HARD_MIN_VOLT:
            errors.append(f"Min voltage must be {HARD_MIN_VOLT} mV or more (hard floor).")
        if self.oc_volt and self.oc_volt > HARD_MAX_VOLT:
            errors.append(f"OC voltage must be at most {HARD_MAX_VOLT} mV (hard ceiling).")
        if self.freq_step < 25:
            errors.append("Frequency step must be 25 MHz or more.")
        if self.volt_step < 5:
            errors.append("Voltage step must be 5 mV or more.")
        return errors

    def to_args(self) -> list[str]:
        args = ["-t", str(self.time_secs), "-r", str(self.rounds)]
        # Both ladders is the script default, so only pass a flag for a single-ladder sweep.
        if self.sweep_oc and not self.sweep_uv:
            args.append("--oc")
        elif self.sweep_uv and not self.sweep_oc:
            args.append("--uv")
        if self.sweep_oc:
            if self.max_freq != DEFAULT_MAX_FREQ:
                args += ["--max-freq", str(self.max_freq)]
            if self.freq_step != DEFAULT_FREQ_STEP:
                args += ["--freq-step", str(self.freq_step)]
            if self.oc_volt:
                args += ["--oc-volt", str(self.oc_volt)]
        if self.sweep_uv:
            if self.min_volt != DEFAULT_MIN_VOLT:
                args += ["--min-volt", str(self.min_volt)]
            if self.volt_step != DEFAULT_VOLT_STEP:
                args += ["--volt-step", str(self.volt_step)]
        if self.per_boot:
            args.append("--per-boot")
        return args

    def to_command(self, script: str) -> str:
        """Full shell command line, quoted for safe use with ``bash -lc``."""
        return shlex.join(["bash", script, *self.to_args()])
