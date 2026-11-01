# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window: the memory the system has now (split, GTT, RAM, swap), a live map of it, the VRAM split in
CMOS with apply, undo and a read of the CMOS block, and the GTT limit (ttm.pages_limit) in the next boot's kernel
arguments.

A split is written to CMOS, a GTT limit to the next boot's kernel arguments with rpm-ostree; both take effect at
the next boot. The window remembers each change with the boot it was made in, and after a reboot says whether the
kernel got it."""

from __future__ import annotations

import json
import time
from html import escape
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (QApplication, QComboBox, QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                             QPushButton, QVBoxLayout, QWidget)

from bc250_core import SUITE_MANUAL_URL, window_title
from bc250_core import __version__ as CORE_VERSION
from bc250_core.platform import data_home
from bc250_core.settings import SettingsStore
from bc250_core.theme import BLUE, GREY, PURPLE
from bc250_core.widgets import AppHeader, InfoButton, MetricBox, StatusText, TextDialog, accent_button, hint_label

from . import APP_ID, APP_NAME, INFO, LOGO_PATH, __version__
from . import cmos, kargs, privileged, system
from .memory_map import MemoryMap, gtt_ceiling

MANUAL_URL = f"{SUITE_MANUAL_URL}apps/vram/"
REFRESH_MS = 2000                       # the memory map's live figures
RECOMMENDED_MB = 6144                   # bazzite-test's recommendation (test 37): fixes framebuffer pin failures
SPLITS = (512, 1024, 2048, 4096, RECOMMENDED_MB, 8192, 10240)
FIRMWARE_MB = 512                       # the split the firmware starts with after a CMOS clear
SUITE_PAGES = 3014656                   # the suite's GTT limit, 11.5 GiB (Bazzite Test, test 37)
PICK = object()                         # apply_ttm(): the limit the combo shows

# The profiles (owner, 01-11-2026): both values at once, each written only where it differs.
PROFILES = {
    "defaults": ("Default profile", FIRMWARE_MB, None),
    "games": ("Games profile", RECOMMENDED_MB, SUITE_PAGES),
}


class ManagerSettings(SettingsStore):
    DEFAULTS = {"pending_mb": 0, "pending_boot_id": "", "previous_mb": 0, "outcome": "",
                # the GTT limit written for the next boot: "" none, "default" (the argument removed) or the pages
                "pending_ttm": "", "pending_ttm_boot_id": "", "ttm_outcome": ""}


def backups_dir() -> Path:
    return data_home() / APP_ID / "backups"


def split_label(mb: int) -> str:
    text = f"{mb // 1024} GB" if mb >= 1024 else f"{mb} MB"
    return text + ("  (recommended for games)" if mb == RECOMMENDED_MB else "")


def ttm_label(pages: int | None) -> str:
    """A GTT limit in words: its size, or the kernel's default."""
    return f"{system.mib_text(kargs.mib(pages))} GTT limit" if pages else "kernel default GTT limit (half the RAM)"


def ttm_setting(pages: int | None) -> str:
    return "default" if pages is None else str(pages)


def ttm_pages(setting: str) -> int | None:
    return None if setting == "default" else int(setting)


class MainWindow(QMainWindow):
    def __init__(self, sys_root: Path = Path("/sys"), proc_root: Path = Path("/proc"),
                 runner: Callable[[list[str]], privileged.Result] = privileged.run,
                 commands: kargs.Run = privileged.run_command):
        super().__init__()
        self.resize(900, 940)
        self.sys_root = sys_root
        self.proc_root = proc_root
        self.runner = runner
        self.commands = commands                # runs rpm-ostree for the kernel arguments
        self.settings = ManagerSettings(INFO, self)
        self.memory = system.read_memory(sys_root, proc_root)
        self.next_boot = kargs.read_next_boot(commands)
        self.block_problem = ""                 # why CMOS must not be touched on this machine (cmos.board_problem)

        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.badge = StatusText()
        header.add_state(self.badge)

        self.vram_box = MetricBox("VRAM split", PURPLE)
        self.gtt_box = MetricBox("GTT (RAM the GPU borrows)", BLUE)
        self.ttm_box = MetricBox("ttm.pages_limit", BLUE)
        self.ram_box = MetricBox("System RAM", GREY)
        self.swap_box = MetricBox("Swap", GREY)
        for box in (self.vram_box, self.gtt_box, self.ttm_box, self.ram_box, self.swap_box):
            header.add_second(box)
        self.details = hint_label("")

        mapped = QGroupBox("Memory map")
        self.map = MemoryMap(self.memory)
        lay_map = QVBoxLayout(mapped)
        lay_map.addWidget(self.map)
        lay_map.addWidget(hint_label("Hover a part for what it is. Picking a new split or GTT limit below shows the "
                                     "next boot under the bar."))
        self.timer = QTimer(self)
        self.timer.setInterval(REFRESH_MS)
        self.timer.timeout.connect(self.refresh_usage)
        self.timer.start()

        split = QGroupBox("VRAM split in CMOS")
        self.combo = QComboBox()
        for mb in SPLITS:
            self.combo.addItem(split_label(mb), mb)
        self.combo.currentIndexChanged.connect(self.on_pick)
        self.apply_button = accent_button("Apply…", "Write this split to CMOS; it takes effect after a reboot")
        self.apply_button.clicked.connect(self.apply_split)
        self.undo_button = QPushButton("Undo")
        self.undo_button.setToolTip("Write back the split from before the last change")
        self.undo_button.clicked.connect(self.undo)
        self.read_button = QPushButton("Read CMOS…")
        self.read_button.setToolTip("Show the memory block in CMOS and save a dump of it (read-only)")
        self.read_button.clicked.connect(self.read_cmos)
        self.split_info = InfoButton(
            "The split is the part of the 16 GB the GPU keeps for itself; the rest is system RAM, from which the GPU "
            "can borrow more (GTT). A larger split prevents the framebuffer pin failures that end a game session "
            "(Bazzite Test, test 37). The firmware reads the new split at the next boot. Clearing CMOS (jumper or "
            f"battery) brings back the firmware's default. <a href='{MANUAL_URL}'>Manual</a>", "About the split")
        row = QHBoxLayout()
        row.addWidget(QLabel("New split:"))
        row.addWidget(self.combo, 1)
        for w in (self.apply_button, self.undo_button, self.read_button, self.split_info):
            row.addWidget(w)
        self.split_note = hint_label("")
        self.block_reason = hint_label("")
        lay_split = QVBoxLayout(split)
        lay_split.addLayout(row)
        lay_split.addWidget(self.split_note)
        lay_split.addWidget(self.block_reason)

        limit = QGroupBox("GTT limit on the kernel command line")
        self.ttm_combo = QComboBox()
        for label, pages in kargs.PRESETS:
            self.ttm_combo.addItem(label, pages)
        self.ttm_combo.currentIndexChanged.connect(self.on_pick)
        self.ttm_button = accent_button("Apply…", "Put this limit in the next boot's kernel arguments (rpm-ostree)")
        self.ttm_button.clicked.connect(self.apply_ttm)
        self.ttm_info = InfoButton(
            "The GTT limit is how much RAM the GPU may borrow on top of the split: amdgpu takes it from "
            "ttm.pages_limit on the kernel command line, half the RAM when it is not there, and never more than the "
            "RAM. A small split needs the argument to reach the whole RAM; with a 6 GB split, 11.5 GiB is already all "
            "of it. It does not fix the framebuffer pin failures; only a larger split does. rpm-ostree puts it in the "
            "next boot's kernel arguments as a new deployment, and takes it out again for the kernel default. "
            f"<a href='{MANUAL_URL}#the-gtt-limit'>Manual</a>", "About the GTT limit")
        row_ttm = QHBoxLayout()
        row_ttm.addWidget(QLabel("Next boot:"))
        row_ttm.addWidget(self.ttm_combo, 1)
        row_ttm.addWidget(self.ttm_button)
        row_ttm.addWidget(self.ttm_info)
        self.ttm_note = hint_label("")
        self.ttm_reason = hint_label("")
        lay_limit = QVBoxLayout(limit)
        lay_limit.addLayout(row_ttm)
        lay_limit.addWidget(self.ttm_note)
        lay_limit.addWidget(self.ttm_reason)

        profiles = QGroupBox("Profiles: the split and the GTT limit at once")
        self.profile_buttons: dict[str, QPushButton] = {}
        row_profiles = QHBoxLayout()
        for key, (name, mb, pages) in PROFILES.items():
            button = QPushButton(f"{name}…")
            button.setToolTip(f"{split_label(mb)} split, {ttm_label(pages)}")
            button.clicked.connect(lambda _c, k=key: self.apply_profile(k))
            self.profile_buttons[key] = button
            row_profiles.addWidget(button)
        row_profiles.addStretch(1)
        row_profiles.addWidget(InfoButton(
            f"<b>Default profile:</b> the firmware's {split_label(FIRMWARE_MB)} split and the kernel's GTT limit, "
            f"half the RAM, as a board without changes runs. <b>Games profile:</b> the {split_label(RECOMMENDED_MB)} "
            "split that "
            "prevents the framebuffer pin failures (Bazzite Test, test 37) and the 11.5 GiB limit, all the RAM with "
            "that split: what the suite's boards run. A profile writes what differs from the board: the split to CMOS "
            "and the limit to the next boot's kernel arguments, each with its password prompt; both take effect after "
            f"you reboot the board. <a href='{MANUAL_URL}#profiles'>Manual</a>", "About the profiles"))
        lay_profiles = QVBoxLayout(profiles)
        lay_profiles.addLayout(row_profiles)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(header)
        lay.addWidget(self.details)
        lay.addWidget(mapped)
        lay.addWidget(split)
        lay.addWidget(limit)
        lay.addWidget(profiles)
        lay.addStretch(1)
        version = QLabel(f"{APP_NAME} {__version__} · core {CORE_VERSION} · CMOS and the kernel arguments are written "
                         "only when you apply")
        version.setStyleSheet("color:palette(placeholder-text);")
        lay.addWidget(version, 0, Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(central)

        geometry = self.settings.window_state("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.check_reboot()
        self.check_ttm_reboot()
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

    def check_ttm_reboot(self) -> None:
        """The same for a GTT limit written for the next boot: did this boot's command line get it?"""
        pending = self.settings.get("pending_ttm")
        if not pending or self.settings.get("pending_ttm_boot_id") == self.memory.boot_id:
            return
        wanted, got = ttm_pages(pending), self.memory.ttm_cmdline_pages
        if got == wanted:
            borrow = (f" The GPU may borrow up to {system.mib_text(self.memory.gtt_mib)} of the RAM"
                      + (", all of it." if self.memory.gtt_capped else ".")) if self.memory.gtt_mib else ""
            self.settings.set("ttm_outcome", f"The {ttm_label(wanted)} from the last change is active.{borrow}")
        else:
            self.settings.set("ttm_outcome", f"The {ttm_label(wanted)} was written for the next boot, but this boot "
                                             f"has the {ttm_label(got)}: the board may have started another "
                                             "deployment.")
        self.settings.set("pending_ttm", "")
        self.settings.set("pending_ttm_boot_id", "")

    def on_pick(self) -> None:
        """A split or a GTT limit picked: the memory map's next boot with them, where they differ from this boot's,
        and Apply only for what is not written yet (owner, 01-11-2026: what is applied cannot be applied again)."""
        self.map.set_preview(self.combo.currentData(), kargs.mib(self.ttm_combo.currentData()))
        self.apply_button.setEnabled(not self.block_problem and self.combo.currentData() != self.written_split())
        self.ttm_button.setEnabled(not self.next_boot.error and self.ttm_combo.currentData() != self.next_boot.pages)
        for key, button in self.profile_buttons.items():
            button.setEnabled(bool(self.profile_steps(key)))

    def written_split(self) -> int | None:
        """The split in CMOS: the one waiting for a reboot, else the one this boot got."""
        return self.settings.get("pending_mb") or self.memory.vram_mib

    def profile_steps(self, key: str) -> list[str]:
        """What a profile would write, in words: the split (when CMOS can be written and it differs), the limit
        (when rpm-ostree works and it differs). Empty when the board has the profile, or nothing can be written."""
        _name, mb, pages = PROFILES[key]
        steps = []
        if not self.block_problem and mb != self.written_split():
            steps.append(f"the {split_label(mb)} split to CMOS")
        if not self.next_boot.error and pages != self.next_boot.pages:
            steps.append(f"the {ttm_label(pages)} to the next boot's kernel arguments")
        return steps

    def refresh_usage(self) -> None:
        self.map.set_usage(system.read_usage(self.sys_root, self.proc_root))

    def refresh(self) -> None:
        m = self.memory
        self.vram_box.set_value(system.mib_text(m.vram_mib))
        self.gtt_box.set_value(system.mib_text(m.gtt_mib))
        self.ram_box.set_value(system.mib_text(m.ram_mib))
        self.swap_box.set_value(m.swap_text)
        self.ttm_box.set_value(system.mib_text(m.ttm_limit_mib), self.ttm_tip())
        self.ttm_box.caption.setText("ttm.pages_limit" if m.ttm_on_cmdline else "ttm.pages_limit (default)")
        self.gtt_box.caption.setText("GTT: all the RAM" if m.gtt_capped else "GTT (RAM the GPU borrows)")
        self.details.setText(f"vm.swappiness {m.swappiness}" if m.swappiness is not None else "")
        self.details.setToolTip("How readily Linux moves pages out of the RAM into swap, 0 to 200: 0 only when the RAM "
                                "is full, 60 the kernel's default, 100 and more preferring swap to the file cache "
                                "(usual with zram, where swap is RAM). The board's own setting; the app only shows "
                                "it.")
        self.details.setVisible(bool(self.details.text()))

        pending = self.settings.get("pending_mb")
        outcome = self.settings.get("outcome")
        ttm_pending = self.refresh_ttm()
        if pending:
            self.badge.set_status("Reboot to apply", "warn", f"{split_label(pending)} is in CMOS; the firmware "
                                                               "reads it at the next boot.")
            self.split_note.setText(f"<b>{escape(split_label(pending))}</b> is written to CMOS and takes effect after "
                                    "a reboot.")
        else:
            if ttm_pending:
                self.badge.set_status("Reboot to apply", "warn", ttm_pending)
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
        self.block_problem = problem
        self.block_reason.setText(escape(problem))
        self.block_reason.setVisible(bool(problem))
        self.read_button.setEnabled(not problem)
        previous = self.settings.get("previous_mb")
        self.undo_button.setEnabled(not problem and bool(previous) and previous != (pending or m.vram_mib))
        self.undo_button.setToolTip(f"Write back {split_label(previous)}" if previous else "Nothing to undo yet")
        self.on_pick()

    def ttm_tip(self) -> str:
        m = self.memory
        if m.ttm_limit_mib is None:
            return "The kernel's ttm module is not loaded, so there is no limit to read."
        if not m.ttm_on_cmdline:
            return ("The kernel's default, half the RAM: ttm.pages_limit is not on the kernel command line. The GPU "
                    f"may borrow up to {system.mib_text(m.gtt_mib)} of the RAM.")
        text = f"ttm.pages_limit={m.ttm_cmdline_pages} on the kernel command line, {system.mib_text(m.ttm_limit_mib)}."
        if m.gtt_capped:
            return text + (f" That is above the RAM, so the GTT is all the RAM, {system.mib_text(m.gtt_mib)}: a "
                           "higher limit cannot give the GPU more.")
        return text + f" The GPU may borrow up to {system.mib_text(m.gtt_mib)} of the RAM."

    def refresh_ttm(self) -> str:
        """The GTT limit box: the next boot's limit in the combo (added when it is none of the presets), the note
        under it, and the reason when rpm-ostree cannot be used. Returns the note when a change waits for a reboot,
        else ""."""
        m, nxt = self.memory, self.next_boot
        waiting = ""
        if nxt.error:
            self.ttm_note.setText(escape(self.settings.get("ttm_outcome")))
            self.ttm_reason.setText(escape(nxt.error))
        else:
            if self.ttm_combo.findData(nxt.pages) < 0:
                self.ttm_combo.addItem(f"{system.mib_text(kargs.mib(nxt.pages))}, as set now", nxt.pages)
            self.ttm_combo.setCurrentIndex(self.ttm_combo.findData(nxt.pages))
            if nxt.pages != m.ttm_cmdline_pages:
                waiting = (f"The {ttm_label(nxt.pages)} is in the next boot's kernel arguments. Reboot the board to "
                           "use it; the app does not reboot by itself.")
                self.ttm_note.setText(f"<b>{escape(waiting)}</b>")
                self.ttm_box.caption.setText(f"next boot {system.mib_text(kargs.mib(nxt.pages))}" if nxt.pages
                                             else "next boot: default")
            else:
                self.ttm_note.setText(escape(self.settings.get("ttm_outcome")))
            self.ttm_reason.setText("")
        self.ttm_note.setVisible(bool(self.ttm_note.text()))
        self.ttm_reason.setVisible(bool(self.ttm_reason.text()))
        return waiting

    # --- Actions ----------------------------------------------------------------------------------------------

    def apply_split(self) -> None:
        self.write_split(self.combo.currentData(), "Apply split")

    def undo(self) -> None:
        self.write_split(self.settings.get("previous_mb"), "Undo")

    def write_split(self, mb: int, title: str, ask: bool = True) -> bool:
        """Writes the split to CMOS, after the question unless *ask* is off (a profile asked already). True when
        it is written."""
        m = self.memory
        left = ""
        if m.vram_mib and m.ram_mib:
            left = f" The system keeps about {system.mib_text(m.vram_mib + m.ram_mib - mb)} of RAM."
        if ask:
            answer = QMessageBox.question(
                self, window_title(title),
                f"Write a VRAM split of {split_label(mb)} to CMOS?\n\n"
                f"This changes how the board starts: the firmware reads the split at the next boot.{left} Only the "
                "split changes; the memory timings stay as they are. You can change it back here, or clear CMOS "
                "(jumper or battery) for the firmware's default.\n\nIt needs your password.")
            if answer != QMessageBox.StandardButton.Yes:
                return False
        result = self.runner(["--set-uma", str(mb)])
        if not result.ok:
            QMessageBox.warning(self, window_title(title), result.error or "The write failed.")
            return False
        self.save_backup(result.data)
        before = result.data["before"]["uma_mb"]
        if before != mb:
            self.settings.set("previous_mb", before)
        self.settings.set("pending_mb", mb if mb != m.vram_mib else 0)
        self.settings.set("pending_boot_id", m.boot_id if mb != m.vram_mib else "")
        self.settings.set("outcome", "" if mb != m.vram_mib else f"CMOS holds the {split_label(mb)} split again.")
        self.refresh()
        return True

    def gtt_effect(self, pages: int | None) -> str:
        """What the GTT would be after a reboot with this limit and the split of this boot, against what it is now:
        the kernel caps it at the RAM, so a limit above the RAM changes nothing visible."""
        m = self.memory
        then = gtt_ceiling(m, None, kargs.mib(pages))
        if then is None or m.gtt_mib is None:
            return ""
        ram = m.ram_mib or 0
        if then == m.gtt_mib:
            if then >= ram * 95 // 100:
                return (f" The GTT stays at {system.mib_text(m.gtt_mib)}, all the RAM with this split: a limit above "
                        "the RAM changes nothing until a smaller split.")
            return f" The GTT stays at {system.mib_text(m.gtt_mib)}."
        return f" The GTT then is about {system.mib_text(then)} instead of {system.mib_text(m.gtt_mib)} now."

    def apply_ttm(self, pages=PICK, ask: bool = True) -> bool:
        """Puts the limit (the combo's, or *pages*) in the next boot's kernel arguments, after the question and
        with the Done message unless *ask* is off (a profile does both). True when it is written."""
        if pages is PICK:
            pages = self.ttm_combo.currentData()
        if ask:
            if pages is None:
                what = "Remove ttm.pages_limit from the kernel arguments of the next boot?\n\nThe kernel then takes "
                what += "its default, half the RAM, as the GTT limit."
            else:
                what = (f"Set ttm.pages_limit to {pages} ({system.mib_text(kargs.mib(pages))}) in the kernel arguments "
                        "of the next boot?\n\nThe GPU may then borrow up to that much of the RAM, but never more "
                        "than the RAM.")
            answer = QMessageBox.question(
                self, window_title("GTT limit"),
                f"{what}{self.gtt_effect(pages)}\n\nrpm-ostree writes a new deployment with the change, which takes "
                "a minute or two (it puts the layered packages on it again). It takes effect after you reboot the "
                "board, which the app leaves to you. The split in CMOS stays as it is.\n\nIt needs your password.")
            if answer != QMessageBox.StandardButton.Yes:
                return False
        # rpm-ostree works for a minute or two after the password dialog closes: say so where it is seen, with the
        # seconds counting, so the wait does not look like a hang (owner, 01-11-2026).
        self.badge.set_status("Writing…", "info", "rpm-ostree is writing the next boot's kernel arguments")
        self.ttm_note.setVisible(True)
        for widget in (self.ttm_combo, self.ttm_button, self.apply_button, self.undo_button, self.read_button):
            widget.setEnabled(False)
        self.writing_since = time.monotonic()
        self.writing_timer = QTimer(self)
        self.writing_timer.timeout.connect(self.tick_writing)
        self.writing_timer.start(1000)
        self.tick_writing()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            error = kargs.apply(self.commands, pages, self.next_boot.pages)
        finally:
            self.writing_timer.stop()
            QApplication.restoreOverrideCursor()
            self.ttm_combo.setEnabled(True)
        if error:
            QMessageBox.warning(self, window_title("GTT limit"), error)
            pick = self.ttm_combo.currentIndex()
            self.refresh()
            self.ttm_combo.setCurrentIndex(pick)      # the pick stays, so it can be tried again
            return False
        self.next_boot = kargs.read_next_boot(self.commands)
        changed = pages != self.memory.ttm_cmdline_pages
        self.settings.set("pending_ttm", ttm_setting(pages) if changed else "")
        self.settings.set("pending_ttm_boot_id", self.memory.boot_id if changed else "")
        self.settings.set("ttm_outcome", "" if changed else f"The next boot has the {ttm_label(pages)} again.")
        if changed and ask:
            QMessageBox.information(
                self, window_title("GTT limit"),
                f"Done: the {ttm_label(pages)} is in the next boot's kernel arguments.\n\nReboot the board to use "
                "it. The app does not reboot by itself: use the menu, or in a terminal: systemctl reboot.")
        self.refresh()
        return True

    def tick_writing(self) -> None:
        """The note while rpm-ostree works: the seconds so far, so the window is seen to be alive."""
        seconds = int(time.monotonic() - self.writing_since)
        self.ttm_note.setText(f"<b>rpm-ostree is writing the next boot's kernel arguments, {seconds} s so far. This "
                              "takes a minute or two; the window answers again when it is done.</b>")

    def apply_profile(self, key: str) -> None:
        """Writes a profile's split and limit where they differ from the board, after one question; one password
        prompt for each (CMOS through pkexec, the kernel arguments through rpm-ostree)."""
        name, mb, pages = PROFILES[key]
        steps = self.profile_steps(key)
        if not steps:
            return
        prompts = "One password prompt for each." if len(steps) > 1 else "It needs your password."
        answer = QMessageBox.question(
            self, window_title(name),
            f"Write {' and '.join(steps)}?\n\n{prompts} Both take effect after you reboot the board, which the app "
            "leaves to you.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not self.block_problem and mb != self.written_split() and not self.write_split(mb, name, ask=False):
            return
        if not self.next_boot.error and pages != self.next_boot.pages and not self.apply_ttm(pages, ask=False):
            return
        QMessageBox.information(
            self, window_title(name),
            f"Done: {' and '.join(steps)}.\n\nReboot the board to use it. The app does not reboot by itself: use the "
            "menu, or in a terminal: systemctl reboot.")

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
