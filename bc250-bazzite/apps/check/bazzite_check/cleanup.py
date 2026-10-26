# SPDX-License-Identifier: GPL-3.0-or-later
"""Log cleanup: remove run logs older than N days, or everything for a fresh start.

Only timestamped per-run files are removed. The benchmark baseline and the benchmark and speed test
history CSVs have no timestamp in their name, so they are never touched.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QLabel, QRadioButton, QSpinBox, QHBoxLayout, QVBoxLayout, QWidget,
)

from . import window_title
from .history import DESKTOP_DIR, SCRIPT_LOG_DIR
from .logstore import log_dir

LEGACY_DIR = Path("/var/log")       # reports of script versions before the bc250-bazzite-test folder
_SCRIPT_FILE = re.compile(r"^bc250-[a-z0-9-]+-(\d{8}-\d{6})\.(?:log|csv|json)$")
_GUI_FILE = re.compile(r"^(\d{8}-\d{6})_.+\.log$")
DEFAULT_DAYS = 30


@dataclass
class Plan:
    user_files: list[Path] = field(default_factory=list)    # removable as the current user
    root_files: list[Path] = field(default_factory=list)    # need sudo (/var/log is root's)
    size: int = 0

    @property
    def files(self) -> list[Path]:
        return self.user_files + self.root_files

    def summary(self) -> str:
        if not self.files:
            return "Nothing to remove."
        where: dict[str, int] = {}
        for p in self.files:
            where[str(p.parent)] = where.get(str(p.parent), 0) + 1
        lines = [f"{n} file(s) in {d}" for d, n in sorted(where.items())]
        return f"{len(self.files)} file(s), {self.size / 1048576:.1f} MiB:\n" + "\n".join(lines)


def _stamp(name: str, rx: re.Pattern) -> datetime | None:
    if m := rx.match(name):
        try:
            return datetime.strptime(m.group(1), "%Y%m%d-%H%M%S")
        except ValueError:
            return None
    return None


def collect(older_than_days: int | None) -> Plan:
    """Files to remove; None = all of them."""
    cutoff = datetime.now() - timedelta(days=older_than_days) if older_than_days is not None else None
    plan = Plan()
    sources = [(log_dir(), _GUI_FILE), (SCRIPT_LOG_DIR, _SCRIPT_FILE), (LEGACY_DIR, _SCRIPT_FILE),
               (DESKTOP_DIR, _SCRIPT_FILE)]
    for directory, rx in sources:
        try:
            entries = list(directory.iterdir())
        except OSError:
            continue
        writable = os.access(directory, os.W_OK)
        for path in entries:
            stamp = _stamp(path.name, rx)
            if stamp is None or not path.is_file() or (cutoff and stamp >= cutoff):
                continue
            try:
                plan.size += path.stat().st_size
            except OSError:
                pass
            (plan.user_files if writable else plan.root_files).append(path)
    return plan


def execute(plan: Plan, password: str | None) -> tuple[set[str], list[str]]:
    """Remove the files; returns (removed paths, error messages). Root files go through one sudo rm."""
    removed: set[str] = set()
    errors: list[str] = []
    if plan.root_files:
        cmd = ["sudo", "-S", "-p", "", "rm", "-f", "--"] if password is not None else ["sudo", "-n", "rm", "-f", "--"]
        proc = subprocess.run(cmd + [str(p) for p in plan.root_files], capture_output=True, text=True,
                              input=(password + "\n") if password is not None else None)
        if proc.returncode == 0:
            removed.update(str(p) for p in plan.root_files)
        else:
            errors.append("sudo rm failed: " + (proc.stderr.strip() or f"exit {proc.returncode}"))
            removed.update(str(p) for p in plan.root_files if not p.exists())
    for p in plan.user_files:
        try:
            p.unlink()
            removed.add(str(p))
        except FileNotFoundError:
            removed.add(str(p))
        except OSError as exc:
            errors.append(f"{p}: {exc}")
    return removed, errors


class CleanupDialog(QDialog):
    """Choose what to remove; shows what each choice would delete before anything happens."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(window_title("clean up logs"))
        self.resize(560, 360)
        layout = QVBoxLayout(self)

        self.old = QRadioButton("Remove logs older than")
        self.days = QSpinBox()
        self.days.setRange(1, 3650)
        self.days.setValue(DEFAULT_DAYS)
        self.days.setSuffix(" days")
        row = QHBoxLayout()
        row.addWidget(self.old)
        row.addWidget(self.days)
        row.addStretch(1)
        layout.addLayout(row)
        self.all = QRadioButton("Remove ALL logs and the test history (start fresh)")
        layout.addWidget(self.all)
        group = QButtonGroup(self)
        group.addButton(self.old)
        group.addButton(self.all)
        self.old.setChecked(True)

        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.details.setStyleSheet("padding:8px; border:1px solid palette(mid); border-radius:6px;")
        layout.addWidget(self.details, 1)
        keep = QLabel("Always kept: bench-baseline.json, bc250-bench-history.csv and bc250-speedtest-history.csv, "
                      "so performance and speed comparisons survive a cleanup. Removing old logs keeps their "
                      "results in the history; only “Remove ALL” also empties it.")
        keep.setWordWrap(True)
        keep.setStyleSheet("color:#9aa0a6;")
        layout.addWidget(keep)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.remove = self.buttons.addButton("Remove", QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        for w in (self.old, self.all):
            w.toggled.connect(self._refresh)
        self.days.valueChanged.connect(self._refresh)
        self.plan = Plan()
        self._refresh()

    @property
    def remove_all(self) -> bool:
        return self.all.isChecked()

    def _refresh(self) -> None:
        self.days.setEnabled(self.old.isChecked())
        self.plan = collect(None if self.remove_all else self.days.value())
        text = self.plan.summary()
        if self.plan.root_files:
            text += "\n\nFiles in /var/log belong to root: you will be asked for your password."
        if self.remove_all:
            text += "\n\nThe test history (counters, per-test results, stored numbers) is emptied as well."
        self.details.setText(text)
        self.remove.setEnabled(bool(self.plan.files) or self.remove_all)
