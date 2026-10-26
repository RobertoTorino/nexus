# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window: the stick as the board sees it, the chip's answer and the driver branch it takes, the build
(as your own user, with its output shown), and the driver installed as a system service (through the password
dialog), with what that service did last. Below it every Wi-Fi adapter on the board and whether the kernel has a
driver for it (bc250_core.wifi, the same reader as BC-250 Bazzite Test's Wi-Fi Adapter test), so a stick of
another chip can be checked here too.

The window reads the board itself; the driver is a system service (driver.py) and runs without the window."""

from __future__ import annotations

import html
import time
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                             QPushButton, QVBoxLayout, QWidget)

from bc250_core import SUITE_MANUAL_URL, wifi, window_title
from bc250_core import __version__ as CORE_VERSION
from bc250_core.platform import data_home
from bc250_core.settings import SettingsStore
from bc250_core.theme import GREEN, GREY, ORANGE, RED
from bc250_core.widgets import AppHeader, MetricBox, Pill, StatusText, Terminal, accent_button, hint_label

from . import APP_ID, APP_NAME, INFO, LOGO_PATH, __version__
from . import builder, driver, privileged, stick

MANUAL_URL = f"{SUITE_MANUAL_URL}apps/wdriver/"
REFRESH_MS = 2000
LOG_EVERY = 5                                   # refreshes between two reads of the kernel log and the adapters
LEVEL_COLOURS = {"SUCCESS": GREEN, "WARNING": ORANGE}


class WifiSettings(SettingsStore):
    DEFAULTS: dict = {"branch": ""}             # "" follows the chip


def set_box_colour(box: MetricBox, colour: str) -> None:
    box.set_colour(colour)


class StepRunner:
    """Runs the build's steps one after the other as a QProcess, feeding their output to a callback. A step with
    a fallback gets its fallback run when it fails (the mirror, then upstream)."""

    def __init__(self, on_output: Callable[[str], None], on_done: Callable[[bool], None]):
        self.on_output, self.on_done = on_output, on_done
        self.steps: list[builder.Step] = []
        self.process: QProcess | None = None
        self.current: builder.Step | None = None

    def start(self, steps: list[builder.Step]) -> None:
        self.steps = list(steps)
        self.next()

    def next(self) -> None:
        if not self.steps:
            self.on_done(True)
            return
        self.run(self.steps.pop(0))

    def run(self, step: builder.Step) -> None:
        self.current = step
        self.on_output("$ " + " ".join(step.argv) + "\n")
        self.process = QProcess()
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(
            lambda: self.on_output(bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace")))
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(lambda _e: self.finished(127))
        self.process.start(step.argv[0], step.argv[1:])

    def finished(self, code: int, *_rest) -> None:
        if self.process is None:
            return
        self.process = None
        step = self.current
        if code != 0 and step is not None and step.fallback:
            self.on_output(f"\n{step.note or 'Trying the fallback.'}\n")
            self.run(builder.Step(step.fallback))
            return
        if code != 0:
            self.on_output(f"\nStopped: exit code {code}.\n")
            self.on_done(False)
            return
        self.next()


class MainWindow(QMainWindow):
    def __init__(self, sys_root: Path = Path("/sys"), proc_root: Path = Path("/proc"), usr_root: Path = Path("/usr"),
                 paths: driver.Paths | None = None, data_dir: Path | None = None,
                 runner: Callable[[list[str]], str] = privileged.run,
                 log_reader: Callable[[], str] = stick.read_kernel_log,
                 kernel: str | None = None, which: Callable[[str], str | None] | None = None,
                 clock: Callable[[], float] = time.time, lib_root: Path = Path("/lib/modules"),
                 boot_log_reader: Callable[[], str] = wifi.read_boot_log,
                 link_runner: Callable[[list[str]], str] = wifi.run_text):
        super().__init__()
        self.resize(940, 800)
        self.sys_root, self.proc_root, self.usr_root = sys_root, proc_root, usr_root
        self.paths = paths or driver.Paths()
        self.data_dir = data_dir or data_home() / APP_ID
        self.runner = runner
        self.log_reader = log_reader
        self.kernel = kernel or stick.kernel_release()
        self.which = which
        self.clock = clock
        self.boot_log_reader = boot_log_reader
        self.link_runner = link_runner
        self.kernel_modules = wifi.read_modules(self.kernel, lib_root)
        self.settings = WifiSettings(INFO, self)
        self.busy = False
        self.refreshes = 0
        self.chip: stick.Chip | None = None

        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.badge = StatusText()
        header.add_state(self.badge)
        self.stick_box = MetricBox("Stick", GREY)
        self.chip_box = MetricBox("Chip", GREY)
        self.driver_box = MetricBox("Driver", GREY)
        self.wifi_box = MetricBox("Wi-Fi", GREY)
        # Refresh is a pill beside the boxes (owner, 26-10-2026), as the portal's.
        self.refresh_pill = Pill("Refresh", "Click to refresh", "Read the stick, the kernel log and the service again")
        self.refresh_pill.clicked.connect(lambda: self.refresh(read_log=True))
        for box in (self.stick_box, self.chip_box, self.driver_box, self.wifi_box, self.refresh_pill):
            header.add_second(box)

        group = QGroupBox("Driver")
        self.branch_combo = QComboBox()
        for branch in builder.BRANCHES:
            self.branch_combo.addItem(f"{branch}: {builder.PINS[branch].chips}", branch)
        self.branch_combo.setToolTip("The driver branch to build; chosen from the chip's answer, change it only "
                                     "when you know better")
        self.branch_combo.currentIndexChanged.connect(self.branch_chosen)
        self.newest_check = QCheckBox("Newest sources (untested)")
        self.newest_check.setToolTip("Fetch the branch's current head instead of the tested, pinned commit: a way "
                                     "out when a new kernel breaks the pinned build, until a release moves the pin")
        self.newest_check.toggled.connect(lambda _c: self.refresh_buttons())
        row = QHBoxLayout()
        row.addWidget(QLabel("Driver branch"))
        row.addWidget(self.branch_combo, 1)
        row.addWidget(self.newest_check)
        self.build_button = QPushButton("Build")
        self.build_button.setToolTip("Fetch the pinned sources and build the driver for the running kernel, as your "
                                     "own user (needs the network the first time)")
        self.build_button.clicked.connect(self.build)
        self.install_button = accent_button("Install…", "Install the built driver with its service and the "
                                                        "stick's rule, and load it now")
        self.install_button.clicked.connect(self.install)
        self.remove_button = QPushButton("Remove…")
        self.remove_button.setToolTip("Unload the driver and remove it, its service and its rule")
        self.remove_button.clicked.connect(self.remove)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for w in (self.build_button, self.remove_button, self.install_button):
            buttons.addWidget(w)
        self.driver_note = hint_label("")
        self.driver_note.setOpenExternalLinks(True)
        lay = QVBoxLayout(group)
        lay.addLayout(row)
        lay.addLayout(buttons)
        lay.addWidget(self.driver_note)
        lay.addWidget(hint_label(
            "The driver comes from pinned sources, built here against the running kernel. Installed, a system "
            "service loads it at every boot, switches a stick out of its storage mode, and after a kernel update "
            "builds it again at the next boot (no network needed). The stick's firmware does WPA2, not WPA3: set "
            f"the Wi-Fi connection to WPA2 when the router offers both. <a href='{MANUAL_URL}'>Manual</a>"))

        output = QGroupBox("Build output")
        self.terminal = Terminal()
        self.terminal.setMinimumHeight(160)
        QVBoxLayout(output).addWidget(self.terminal)

        adapters = QGroupBox("Wi-Fi adapters")
        self.adapters_label = QLabel()
        self.adapters_label.setTextFormat(Qt.TextFormat.RichText)
        self.adapters_label.setWordWrap(True)
        self.adapters_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay = QVBoxLayout(adapters)
        lay.addWidget(self.adapters_label)
        lay.addWidget(hint_label("Every Wi-Fi adapter on the board, of any chip, and whether the running kernel has "
                                 "a driver and firmware for it: plug a stick in and press Refresh to see whether it "
                                 "works on Bazzite. Only read: nothing is loaded or switched."))

        events = QGroupBox("What the service did")
        self.events_label = QLabel()
        self.events_label.setTextFormat(Qt.TextFormat.RichText)
        self.events_label.setWordWrap(True)
        self.events_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        QVBoxLayout(events).addWidget(self.events_label)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(header)
        lay.addWidget(group)
        lay.addWidget(output, 1)
        lay.addWidget(events)
        lay.addWidget(adapters)
        version = QLabel(f"{APP_NAME} {__version__} · core {CORE_VERSION} · the board changes only while the driver "
                         "is installed")
        version.setStyleSheet("color:palette(placeholder-text);")
        lay.addWidget(version, 0, Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(central)

        geometry = self.settings.window_state("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.steps = StepRunner(self.show_output, self.build_done)
        self.output_text = ""
        self.timer = QTimer(self)
        self.timer.setInterval(REFRESH_MS)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh(read_log=True)

    # --- State ------------------------------------------------------------------------------------------------

    @property
    def branch(self) -> str:
        return self.branch_combo.currentData()

    def layout_for(self, branch: str | None = None) -> builder.Layout:
        return builder.Layout(self.data_dir, branch or self.branch, self.kernel, self.newest_check.isChecked())

    def branch_chosen(self, _index: int) -> None:
        chosen = self.branch
        wanted = self.chip.branch if self.chip else ""
        self.settings.set("branch", "" if chosen == wanted else chosen)     # "" keeps following the chip
        self.refresh_buttons()

    def choose_branch(self) -> None:
        """The chip's branch, unless the user chose another one."""
        chosen = str(self.settings.get("branch") or "")
        branch = chosen if chosen in builder.BRANCHES else (self.chip.branch if self.chip else "main")
        index = self.branch_combo.findData(branch)
        if index >= 0 and index != self.branch_combo.currentIndex():
            self.branch_combo.blockSignals(True)
            self.branch_combo.setCurrentIndex(index)
            self.branch_combo.blockSignals(False)

    def refresh(self, read_log: bool = False) -> None:
        if read_log or self.refreshes % LOG_EVERY == 0:
            self.chip = stick.chip_from_log(self.log_reader())
            self.choose_branch()
            self.adapters = wifi.find_adapters(self.sys_root, self.kernel_modules, self.boot_log_reader(),
                                               wifi.loaded_modules(self.proc_root), self.link_runner)
            self.show_adapters()
        self.refreshes += 1
        self.sticks = stick.find_sticks(self.sys_root)
        self.interfaces = stick.wifi_interfaces(self.sys_root)
        self.modules = stick.loaded_modules(self.proc_root)
        self.installed = driver.installed(self.paths)
        self.state = driver.read_state(self.paths)
        self.show_stick()
        self.show_chip()
        self.show_driver()
        self.show_wifi()
        self.show_events()
        self.refresh_buttons()

    def show_stick(self) -> None:
        if not self.sticks:
            self.stick_box.set_value("None", "No AIC8800 stick on the USB bus")
            set_box_colour(self.stick_box, GREY)
            return
        first = self.sticks[0]
        self.stick_box.set_value(first.mode_text, f"{first.name} ({first.usb_id})"
                                 + (f", drivers: {', '.join(first.drivers)}" if first.drivers else ""))
        set_box_colour(self.stick_box, {"wifi": GREEN, "loader": ORANGE, "storage": ORANGE}.get(first.mode, GREY))

    def show_chip(self) -> None:
        if self.chip is None:
            self.chip_box.set_value("Unknown", "The kernel log has no answer from the chip yet: it comes when the "
                                               "loader first takes the stick")
            set_box_colour(self.chip_box, GREY)
        else:
            self.chip_box.set_value(f"MCU {self.chip.mcu_id}", f"AIC8800D80 {self.chip.text}: the {self.chip.branch} "
                                                               "branch")
            set_box_colour(self.chip_box, RED if self.chip.upload_failed else GREEN)

    def show_driver(self) -> None:
        if self.installed is None:
            built = builder.complete(self.layout_for().output)
            self.driver_box.set_value("Built" if built else "Not installed",
                                      f"Built for {self.kernel}, not installed" if built else "")
            set_box_colour(self.driver_box, GREY)
            return
        kernels = driver.built_kernels(self.paths)
        for_kernel = self.kernel in kernels
        pinned = self.installed.commit == builder.PINS[self.installed.branch].commit
        self.driver_box.set_value(self.installed.branch if pinned else f"{self.installed.branch} (newest)",
                                  f"Installed from commit {self.installed.commit[:12] or '?'}"
                                  + ("" if pinned else ", the newest sources, not the tested pin")
                                  + f"; built for {', '.join(kernels) or 'no kernel'}")
        set_box_colour(self.driver_box, GREEN if for_kernel and len(self.modules) == 2 else ORANGE)

    def show_wifi(self) -> None:
        if not self.interfaces:
            self.wifi_box.set_value("—", "No interface from the driver")
            set_box_colour(self.wifi_box, GREY)
            return
        first = self.interfaces[0]
        self.wifi_box.set_value(first.name, f"{first.operstate}, {'carrier' if first.carrier else 'no carrier'}")
        set_box_colour(self.wifi_box, GREEN if first.carrier else ORANGE)

    def show_adapters(self) -> None:
        rows = []
        for level, text in wifi.report(self.adapters, self.kernel_modules, in_wifi_app=True):
            text = html.escape(text)
            if level == "INFO" and rows:
                rows.append("")
            if level == "HINT":
                rows.append(f"<span style='color:{GREY}'>{text}</span>")
            elif level in LEVEL_COLOURS:
                rows.append(f"<span style='color:{LEVEL_COLOURS[level]}'>{text}</span>")
            else:
                rows.append(f"<b>{text}</b>" if level == "INFO" else text)
        self.adapters_label.setText("<br>".join(rows))

    def show_events(self) -> None:
        if self.installed is None:
            text = "The driver is not installed."
        elif self.state is None:
            text = "The service has not run this boot."
        else:
            when = time.strftime("%d-%m %H:%M:%S", time.localtime(self.state.get("time", 0)))
            parts = [f"<b>{when}</b>, kernel {self.state.get('kernel', '?')}, branch {self.state.get('branch', '?')}"]
            if self.state.get("built"):
                parts.append("Built the driver for this kernel.")
            if self.state.get("loaded"):
                parts.append(f"Loaded {', '.join(self.state['loaded'])}.")
            if self.state.get("ejected"):
                parts.append(f"Ejected the virtual disk of {', '.join(self.state['ejected'])} (storage mode).")
            if self.state.get("error"):
                parts.append(f"<span style='color:{RED}'>{self.state['error']}</span>")
            text = "<br>".join(parts) + f"<br>The service's log: <code>journalctl -u {driver.UNIT}</code>"
        if text != self.events_label.text():
            self.events_label.setText(text)

    def badge_and_notes(self) -> tuple[tuple[str, str, str], list[str]]:
        notes = []
        tree = stick.build_tree(self.kernel, self.usr_root)
        missing = stick.missing_tools(self.which) if self.which else stick.missing_tools()
        if tree is None:
            notes.append(f"No kernel build tree for {self.kernel} (kernel-devel): the driver cannot be built. "
                         "Bazzite ships it with its kernel; check the Dependency Checker.")
        if missing:
            notes.append(f"Not installed: {', '.join(missing)}. The build needs them.")
        if self.chip is None:
            notes.append("The chip has not answered yet. Build and install the main branch: the loader reports the "
                         "chip when it takes the stick. If the upload then breaks off at 0x170400, the chip is the "
                         "older MCU revision: switch to legacy-mcu1, build and install again, and plug the stick in "
                         "again.")
        elif self.chip.upload_failed and self.chip.branch != (self.installed.branch if self.installed else ""):
            notes.append(f"The firmware upload broke off at 0x170400: this chip ({self.chip.text}) needs the "
                         f"{self.chip.branch} branch. Build and install it, then plug the stick in again.")
        elif self.chip.upload_failed:
            notes.append("The firmware upload broke off once; plug the stick in again so it starts afresh.")
        if self.installed and driver.outdated(self.paths):
            notes.append("The driver's service was installed by another version of the app: press Update to "
                         "update it.")
        if self.installed and self.installed.branch != self.branch:
            notes.append(f"The installed driver is {self.installed.branch}; Install replaces it with {self.branch}.")
        if self.newest_check.isChecked():
            notes.append("Newest sources: the branch's current head, which nobody has tested on this kernel. Use it "
                         "when the pinned build fails on a new kernel; go back to the pin with the next release.")
        if self.sticks and self.sticks[0].mode == "storage" and self.installed is None:
            notes.append("The stick sits in storage mode. Installing the driver switches it; by hand: eject its "
                         "virtual disk (<code>sudo eject /dev/sdX</code>).")

        if self.busy:
            badge = ("Building", "info", "")
        elif self.interfaces and self.interfaces[0].carrier:
            badge = ("Connected", "ok", f"{self.interfaces[0].name} has a link")
        elif self.interfaces:
            badge = ("Wi-Fi up", "ok", f"{self.interfaces[0].name} is there; connect in the network settings")
        elif self.installed and self.kernel not in driver.built_kernels(self.paths):
            badge = ("No driver for this kernel", "warn", "The service builds it at the next boot, or press Install")
        elif self.installed and len(self.modules) < 2:
            badge = ("Driver not loaded", "warn", f"See journalctl -u {driver.UNIT}")
        elif self.installed and not self.sticks:
            badge = ("No stick", "neutral", "Plug the stick in")
        elif self.installed:
            badge = ("Driver loaded", "ok", "")
        else:
            badge = ("Not installed", "neutral", "")
        return badge, notes

    def refresh_buttons(self) -> None:
        badge, notes = self.badge_and_notes()
        self.badge.set_status(*badge)
        self.driver_note.setText("<br>".join(notes))
        self.driver_note.setVisible(bool(notes))
        idle = not self.busy
        can_build = stick.build_tree(self.kernel, self.usr_root) is not None and not (
            stick.missing_tools(self.which) if self.which else stick.missing_tools())
        built = builder.complete(self.layout_for().output)
        self.build_button.setEnabled(idle and can_build)
        self.build_button.setText("Build again" if built else "Build")
        self.install_button.setEnabled(idle and built)
        self.install_button.setText("Update…" if self.installed else "Install…")
        self.install_button.setToolTip("Replace the installed driver with this build and (re)load it" if self.installed
                                       else "Install the built driver with its service and the stick's rule, and load "
                                            "it now" if built else "Build the driver first")
        self.remove_button.setEnabled(idle and self.installed is not None)
        self.branch_combo.setEnabled(idle)
        self.newest_check.setEnabled(idle)
        self.refresh_pill.setEnabled(idle)

    # --- Actions ----------------------------------------------------------------------------------------------

    def show_output(self, text: str) -> None:
        self.output_text += text
        self.terminal.set_text(self.output_text)

    def build(self) -> None:
        tree = stick.build_tree(self.kernel, self.usr_root)
        if tree is None:
            return
        layout = self.layout_for()
        layout.source.mkdir(parents=True, exist_ok=True)
        self.building = layout
        self.output_text = ""
        what = ("the newest sources, untested" if layout.newest else
                f"{builder.PINS[layout.branch].commit[:12]}, {builder.PINS[layout.branch].date}")
        self.show_output(f"Building {layout.branch} ({what}) for kernel {self.kernel}\n")
        self.busy = True
        self.refresh_buttons()
        self.steps.start(builder.fetch_steps(layout) + [builder.make_step(layout, tree)])

    def build_done(self, ok: bool) -> None:
        layout = self.building
        if ok:
            builder.mark_checked_out(layout)
            error = builder.collect(layout)
            if error:
                self.show_output(f"\n{error}\n")
            else:
                self.show_output(f"\nBuilt: {layout.output}\n")
                try:
                    (layout.output / "build.log").write_text(self.output_text, encoding="utf-8")
                except OSError:
                    pass
        self.busy = False
        self.refresh()

    def install(self) -> None:
        layout = self.layout_for()
        title = "Update the driver" if self.installed else "Install the driver"
        commit = builder.output_commit(layout.output) or builder.source_commit(layout)
        source = f"the newest sources (commit {commit[:12]}, untested)" if layout.newest else "the tested sources"
        answer = QMessageBox.question(
            self, window_title(title),
            f"Install the {layout.branch} driver from {source} for kernel {self.kernel} as a system service, from "
            "now on and at every boot?\n\nThe service loads it now and at every boot, switches the stick out of "
            "storage mode, and builds it again after a kernel update. You can remove it here at any time.\n\nIt "
            "needs your password.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        error = self.runner(["install", "--branch", layout.branch, "--build", str(layout.output),
                             "--source", str(layout.source), "--commit", commit,
                             "--app-version", __version__, "--kernel", self.kernel])
        if error:
            QMessageBox.warning(self, window_title(title), error)
        self.refresh(read_log=True)

    def remove(self) -> None:
        title = "Remove the driver"
        answer = QMessageBox.question(
            self, window_title(title),
            "Unload the driver and remove it, its service and the stick's rule?\n\nThe stick then has no driver "
            "until you install it again. The build in your home folder stays.\n\nIt needs your password.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        error = self.runner(["uninstall"])
        if error:
            QMessageBox.warning(self, window_title(title), error)
        self.refresh(read_log=True)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.timer.stop()
        self.settings.set_window_state("geometry", self.saveGeometry())
        self.settings.sync()
        super().closeEvent(event)
