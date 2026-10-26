# SPDX-License-Identifier: GPL-3.0-or-later

"""Turns the setup GUI's choices into a bc250-cores-bisect.sh command line, and the validation that
goes with it - kept free of any Qt import so it's easy to unit-test on its own.

The cores bisect takes far fewer knobs than the CU bisect: the SMU primitive is all-or-nothing, so
there is no baseline mask to pick and no per-item selection. Only the load time, the number of
rounds, the load tool and the run-mode switches matter."""

from __future__ import annotations

import shlex
from dataclasses import dataclass

# Mirrors the script's own defaults (see bc250-cores-bisect.sh: ROUNDS 3, STRESS_SECS 600).
DEFAULT_TIME_SECS = 600
DEFAULT_ROUNDS = 3
MIN_TIME_SECS = 60
MIN_ROUNDS = 1
MAX_ROUNDS = 9

# --load values understood by the script; stress-ng is its default.
LOAD_TOOLS = ("stress-ng", "mprime", "both")
DEFAULT_LOAD_TOOL = "stress-ng"


@dataclass
class BisectOptions:
    time_secs: int = DEFAULT_TIME_SECS
    rounds: int = DEFAULT_ROUNDS
    same_boot: bool = False
    unattended: bool = False  # --auto
    load_tool: str = DEFAULT_LOAD_TOOL  # --load
    rasdaemon: bool = False  # --rasdaemon

    def validate(self) -> list[str]:
        errors = []
        if self.time_secs < MIN_TIME_SECS:
            errors.append(f"Load time must be at least {MIN_TIME_SECS} seconds.")
        if not MIN_ROUNDS <= self.rounds <= MAX_ROUNDS:
            errors.append(f"Rounds must be between {MIN_ROUNDS} and {MAX_ROUNDS}.")
        if self.load_tool not in LOAD_TOOLS:
            errors.append(f"Load tool must be one of: {', '.join(LOAD_TOOLS)}.")
        return errors

    def to_args(self) -> list[str]:
        args = ["-t", str(self.time_secs), "-r", str(self.rounds)]
        if self.load_tool != DEFAULT_LOAD_TOOL:
            args += ["--load", self.load_tool]
        if self.rasdaemon:
            args.append("--rasdaemon")
        if self.same_boot:
            args.append("--same-boot")
        if self.unattended:
            args.append("--auto")
        return args

    def to_command(self, script: str) -> str:
        """Full shell command line, quoted for safe use with ``bash -lc``."""
        return shlex.join(["bash", script, *self.to_args()])
