# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, HOME, the XDG folders and QSettings in a temp folder (the tests never
touch your settings, results or systemd units), a fake unlock script, and the bisect state the unlock gate reads."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

# The owner's boards: cores 0-2 and 4-6 are on at stock, the unlock adds 3 and 7.
BASE_CORES, NEW_CORES = "0 1 2 4 5 6", "3 7"


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("bc250-cores-bisect")
    yield app


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
        QSettings.setPath(fmt, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    return home


@pytest.fixture
def unlock_script(tmp_path) -> Path:
    """Stands in for bc250-cores-unlock.sh: --status prints one line, nothing else runs."""
    script = tmp_path / "bc250-cores-unlock.sh"
    script.write_text('#!/usr/bin/env bash\necho "fake unlock: $*"\n', encoding="utf-8")
    script.chmod(0o755)
    return script


@pytest.fixture
def state(tmp_path):
    """Writes bc250-cores-bisect.sh's state (config, runs.tsv, pending) into a folder for gate.check()."""
    folder = tmp_path / "state"
    folder.mkdir()

    def write(phase: str | None = "bisect", rounds: int = 2, runs: list[tuple] = (), pending: bool = False,
              time: int = 600) -> Path:
        if phase is not None:
            (folder / "config").write_text(f"PHASE={phase}\nBASE_CORES={BASE_CORES}\nNEW_CORES={NEW_CORES}\n"
                                           f"ROUNDS={rounds}\nTIME={time}\n")
        if runs:
            # The columns of the script's record(): date, boot, round, item, cpus, outcome, mces, verify_errs,
            # maxtemp, maxfreq, note, load_secs, tool, ras_errs.
            lines = []
            for r, item, outcome, *load in runs:          # an optional 4th value: the attempt's load seconds
                lines.append(f"2026-10-11 10:00:00\tabcd1234\t{r}\t{item}\t0-15\t{outcome}\t0\t0\t70\t3500\t-\t"
                             f"{load[0] if load else time}\tstress-ng\t-")
            (folder / "runs.tsv").write_text("\n".join(lines) + "\n")
        if pending:
            (folder / "pending").write_text("1 core3\n")
        return folder
    return write


def all_passed(rounds: int = 2) -> list[tuple]:
    """Every item of a finished bisect, PASS in every round."""
    items = ["control", "post-control", "core3", "core7", "combined"]
    return [(r, item, "PASS") for r in range(1, rounds + 1) for item in items]
