# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window: the memory the system has now (split, GTT, RAM, swap), a live map of it, and the VRAM split
in CMOS with apply, undo and a read of the CMOS block.

A split is written to CMOS and takes effect at the next boot. The window remembers the change with the boot it was
made in, and after a reboot says whether the kernel got the new split."""

from __future__ import annotations

import json
import time
from html import escape
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (QComboBox, QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
                             QVBoxLayout, QWidget)

from bc250_core import SUITE_MANUAL_URL, window_title
from bc250_core import __version__ as CORE_VERSION
from bc250_core.platform import data_home
from bc250_core.settings import SettingsStore
from bc250_core.theme import BLUE, GREY, PURPLE
from bc250_core.widgets import AppHeader, MetricBox, StatusText, TextDialog, accent_button, hint_label

from . import APP_ID, APP_NAME, INFO, LOGO_PATH, __version__
from . import cmos, privileged, system
from .memory_map import MemoryMap

MANUAL_URL = f"{SUITE_MANUAL_URL}apps/vram/"
REFRESH_MS = 2000                       # the memory map's live figures
RECOMMENDED_MB = 6144                   # bazzite-test's recommendation (test 37): fixes framebuffer pin failures
SPLITS = (512, 1024, 2048, 4096, RECOMMENDED_MB, 8192, 10240)


class ManagerSettings(SettingsStore):
    DEFAULTS = {"pending_mb": 0, "pending_boot_id": "", "previous_mb": 0, "outcome": ""}


def backups_dir() -> Path:
    return data_home() / APP_ID / "backups"


def split_label(mb: int) -> str:
    text = f"{mb // 1024} GB" if mb >= 1024 else f"{mb} MB"
    return text + ("  (recommended for games)" if mb == RECOMMENDED_MB else "")


class MainWindow(QMainWindow):
    def __init__(self, sys_root: Path = Path("/sys"), proc_root: Path = Path("/proc"),
                 runner: Callable[[list[str]], privileged.Result] = privileged.run):
        super().__init__()
        self.resize(900, 820)
        self.sys_root = sys_root
        self.proc_root = proc_root
        self.runner = runner
        self.settings = ManagerSettings(INFO, self)
        self.memory = system.read_memory(sys_root, proc_root)

        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.badge = StatusText()
        header.add_state(self.badge)

        self.vram_box = MetricBox("VRAM split", PURPLE)
        self.gtt_box = MetricBox("GTT (RAM the GPU may borrow)", BLUE)
        self.ram_box = MetricBox("System RAM", GREY)
        self.swap_box = MetricBox("Swap", GREY)
        for box in (self.vram_box, self.gtt_box, self.ram_box, self.swap_box):
            header.add_second(box)
        self.details = hint_label("")

        mapped = QGroupBox("Memory map")
        self.map = MemoryMap(self.memory)
        lay_map = QVBoxLayout(mapped)
        lay_map.addWidget(self.map)
        lay_map.addWidget(hint_label("Hover a part for what it is. Picking a new split below shows the next boot "
                                     "under the bar."))
        self.timer = QTimer(self)
        self.timer.setInterval(REFRESH_MS)
        self.timer.timeout.connect(self.refresh_usage)
        self.timer.start()

        split = QGroupBox("VRAM split in CMOS")
        self.combo = QComboBox()
        for mb in SPLITS:
            self.combo.addItem(split_label(mb), mb)
        self.combo.currentIndexChanged.connect(lambda _i: self.map.set_preview(self.combo.currentData()))
        self.apply_button = accent_button("Apply…", "Write this split to CMOS; it takes effect after a reboot")
        self.apply_button.clicked.connect(self.apply_split)
        self.undo_button = QPushButton("Undo")
        self.undo_button.setToolTip("Write back the split from before the last change")
        self.undo_button.clicked.connect(self.undo)
        self.read_button = QPushButton("Read CMOS…")
        self.read_button.setToolTip("Show the memory block in CMOS and save a dump of it (read-only)")
        self.read_button.clicked.connect(self.read_cmos)
        row = QHBoxLayout()
        row.addWidget(QLabel("New split:"))
        row.addWidget(self.combo, 1)
        for w in (self.apply_button, self.undo_button, self.read_button):
            row.addWidget(w)
        self.split_note = hint_label("")
        self.block_reason = hint_label("")
        lay_split = QVBoxLayout(split)
        lay_split.addLayout(row)
        lay_split.addWidget(self.split_note)
        lay_split.addWidget(self.block_reason)
        lay_split.addWidget(hint_label(
            "The split is the part of the 16 GB the GPU keeps for itself; the rest is system RAM, from which the GPU "
            "can borrow more (GTT). A larger split prevents the framebuffer pin failures that end a game session "
            "(Bazzite Test, test 37). The firmware reads the new split at the next boot. Clearing CMOS (jumper or "
            f"battery) brings back the firmware's default. <a href='{MANUAL_URL}'>Manual</a>"))

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(header)
        lay.addWidget(self.details)
        lay.addWidget(mapped)
        lay.addWidget(split)
        lay.addStretch(1)
        version = QLabel(f"{APP_NAME} {__version__} · core {CORE_VERSION} · CMOS is written only when you apply a split")
        version.setStyleSheet("color:palette(placeholder-text);")
        lay.addWidget(version, 0, Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(central)

        geometry = self.settings.window_state("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.check_reboot()
        self.refresh_usage()
        self.refresh()

    # --- State ------------------------------------------------------------------------------------------------

    def check_reboot(self) -> None:
        """After a reboot, a pending split either reached the kernel or did not; remember which and clear it."""
        pending = self.settings.get("pending_mb")
        if not pending or self.settings.get("pending_boot_id") == self.memory.boot_id:
            return
        got = self.memory.vram_mib
        if got == pending:
            self.settings.set("outcome", f"The {split_label(pending)} split from the last change is active.")
        else:
            self.settings.set("outcome", f"The {pending} MB split was written, but the kernel got "
                                         f"{system.mib_text(got)}. Read CMOS to see what the firmware kept.")
        self.settings.set("pending_mb", 0)
        self.settings.set("pending_boot_id", "")

    def refresh_usage(self) -> None:
        self.map.set_usage(system.read_usage(self.sys_root, self.proc_root))

    def refresh(self) -> None:
        m = self.memory
        self.vram_box.set_value(system.mib_text(m.vram_mib))
        self.gtt_box.set_value(system.mib_text(m.gtt_mib))
        self.ram_box.set_value(system.mib_text(m.ram_mib))
        self.swap_box.set_value(m.swap_text)
        details = []
        if m.ttm_limit_mib is not None:
            ttm = f"ttm.pages_limit {system.mib_text(m.ttm_limit_mib)}"
            if not m.ttm_on_cmdline:
                ttm += " (the kernel default: half the RAM)"
            elif m.gtt_capped:
                ttm += " (above the RAM, so GTT is capped at the RAM)"
            details.append(ttm)
        if m.swappiness is not None:
            details.append(f"vm.swappiness {m.swappiness}")
        self.details.setText(" · ".join(details))

        pending = self.settings.get("pending_mb")
        outcome = self.settings.get("outcome")
        if pending:
            self.badge.set_status("Reboot to apply", "warn", f"{split_label(pending)} is in CMOS; the firmware "
                                                               "reads it at the next boot.")
            self.split_note.setText(f"<b>{escape(split_label(pending))}</b> is written to CMOS and takes effect after "
                                    "a reboot.")
        else:
            current = f"{system.mib_text(m.vram_mib)} split" if m.vram_mib else "Unknown split"
            kind = "ok" if m.vram_mib == RECOMMENDED_MB else "info" if m.vram_mib else "neutral"
            self.badge.set_status(current, kind)
            self.split_note.setText(escape(outcome))
        self.split_note.setVisible(bool(self.split_note.text()))
        target = pending or m.vram_mib
        if target in SPLITS:
            self.combo.setCurrentIndex(SPLITS.index(target))

        problem = cmos.board_problem(self.sys_root)
        self.block_reason.setText(escape(problem))
        self.block_reason.setVisible(bool(problem))
        for button in (self.apply_button, self.read_button):
            button.setEnabled(not problem)
        previous = self.settings.get("previous_mb")
        self.undo_button.setEnabled(not problem and bool(previous) and previous != (pending or m.vram_mib))
        self.undo_button.setToolTip(f"Write back {split_label(previous)}" if previous else "Nothing to undo yet")

    # --- Actions ----------------------------------------------------------------------------------------------

    def apply_split(self) -> None:
        self.write_split(self.combo.currentData(), "Apply split")

    def undo(self) -> None:
        self.write_split(self.settings.get("previous_mb"), "Undo")

    def write_split(self, mb: int, title: str) -> None:
        m = self.memory
        left = ""
        if m.vram_mib and m.ram_mib:
            left = f" The system keeps about {system.mib_text(m.vram_mib + m.ram_mib - mb)} of RAM."
        answer = QMessageBox.question(
            self, window_title(title),
            f"Write a VRAM split of {split_label(mb)} to CMOS?\n\n"
            f"This changes how the board starts: the firmware reads the split at the next boot.{left} Only the split "
            "changes; the memory timings stay as they are. You can change it back here, or clear CMOS (jumper or "
            "battery) for the firmware's default.\n\nIt needs your password.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = self.runner(["--set-uma", str(mb)])
        if not result.ok:
            QMessageBox.warning(self, window_title(title), result.error or "The write failed.")
            return
        self.save_backup(result.data)
        before = result.data["before"]["uma_mb"]
        if before != mb:
            self.settings.set("previous_mb", before)
        self.settings.set("pending_mb", mb if mb != m.vram_mib else 0)
        self.settings.set("pending_boot_id", m.boot_id if mb != m.vram_mib else "")
        self.settings.set("outcome", "" if mb != m.vram_mib else f"CMOS holds the {split_label(mb)} split again.")
        self.refresh()

    def save_backup(self, data: dict) -> Path:
        folder = backups_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"cmos-{time.strftime('%Y%m%d-%H%M%S')}.json"
        path.write_text(json.dumps({"before": data["before"], "after": data["after"]}, indent=2) + "\n")
        return path

    def read_cmos(self) -> None:
        result = self.runner(["--read"])
        if not result.ok:
            QMessageBox.warning(self, window_title("Read CMOS"), result.error or "The read failed.")
            return
        text = privileged.report(result.data, self.sys_root)
        folder = backups_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"cmos-dump-{time.strftime('%Y%m%d-%H%M%S')}.txt"
        path.write_text(text)
        dialog = TextDialog("CMOS memory block", f"{text}\nSaved: {path}\n", self)
        dialog.exec()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.timer.stop()
        self.settings.set_window_state("geometry", self.saveGeometry())
        self.settings.sync()
        super().closeEvent(event)
