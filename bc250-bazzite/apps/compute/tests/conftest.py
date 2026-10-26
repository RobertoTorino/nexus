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


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("bc250-cu-bisect")
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
    """Stands in for bc250-cu-unlock.sh: --status prints one line, nothing else runs."""
    script = tmp_path / "bc250-cu-unlock.sh"
    script.write_text('#!/usr/bin/env bash\necho "fake unlock: $*"\n', encoding="utf-8")
    script.chmod(0o755)
    return script


@pytest.fixture
def state(tmp_path, monkeypatch):
    """Writes the bisect script's state (umr-config, umr-runs.tsv, umr-pending) where the gate reads it."""
    from cu_unlock import gate
    folder = tmp_path / "state"
    folder.mkdir()
    for name, value in (("STATE_DIR", folder), ("CONFIG", folder / "umr-config"), ("RUNS", folder / "umr-runs.tsv"),
                        ("PENDING", folder / "umr-pending")):
        monkeypatch.setattr(gate, name, value)

    def write(base: str | None = None, rounds: int = 3, runs: list[tuple[int, str, str]] = (),
              pending: bool = False) -> Path:
        if base is not None:
            (folder / "umr-config").write_text(f"BASE={base}\nROUNDS={rounds}\nTIME=180\n")
        if runs:
            # The columns bc250-cu-bisect.sh's record() writes: date, boot, round, item, masks, outcome, ...
            lines = [f"2026-10-11 10:00:00\tabcd1234\t{r}\t{item}\t{base}\t{outcome}\t0\t0\t-\t70\t2000\t99\t-"
                     for r, item, outcome in runs]
            (folder / "umr-runs.tsv").write_text("\n".join(lines) + "\n")
        if pending:
            (folder / "umr-pending").write_text("1 control\n")
        return folder
    return write
