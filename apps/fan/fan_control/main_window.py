# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window: the GPU and CPU temperatures and the fans as the board reports them, the thermal guard with its
limits (turned on, changed and off through the password dialog), and what the guard did lately.

The window reads the sensors itself, so it shows them also while the guard is off; the guard is a system service
(guard.py) and runs without the window."""

from __future__ import annotations

import time
from html import escape
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
                             QSpinBox, QVBoxLayout, QWidget)

from bc250_core import SUITE_MANUAL_URL, window_title
from bc250_core import __version__ as CORE_VERSION
from bc250_core.settings import SettingsStore
from bc250_core.theme import BLUE, ORANGE, RED, STATE_COLORS
from bc250_core.widgets import AppHeader, MetricBox, StatusText, accent_button, hint_label

from . import APP_NAME, INFO, LOGO_PATH, __version__
from . import guard, privileged

MANUAL_URL = f"{SUITE_MANUAL_URL}apps/fan/"
REFRESH_MS = 2000


class FanSettings(SettingsStore):
    DEFAULTS: dict = {}


def celsius_text(value: float | None) -> str:
    return "—" if value is None else f"{value:.0f} °C"


def set_box_colour(box: MetricBox, colour: str) -> None:
    box.set_colour(colour)


class MainWindow(QMainWindow):
    def __init__(self, sys_root: Path = Path("/sys"), paths: guard.Paths | None = None,
                 runner: Callable[[list[str]], str] = privileged.run, clock: Callable[[], float] = time.time):
        super().__init__()
        self.resize(900, 760)
        self.sys_root = sys_root
        self.paths = paths or guard.Paths()
        self.runner = runner
        self.clock = clock
        self.settings = FanSettings(INFO, self)

        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.badge = StatusText()
        header.add_state(self.badge)
        self.gpu_box = MetricBox("GPU (edge)", BLUE)          # the suite's blue edge while nothing is wrong, as
        self.cpu_box = MetricBox("CPU (Tctl)", BLUE)          # the portal's pills (owner, 26-10-2026)
        self.fan_box = MetricBox("Fan", BLUE)
        self.guard_box = MetricBox("Thermal guard", BLUE)
        for box in (self.gpu_box, self.cpu_box, self.fan_box, self.guard_box):
            header.add_second(box)

        guarded = QGroupBox("Thermal guard")
        self.warn_spin = self.spin(60, 104, " °C", "A desktop notification")
        self.cool_spin = self.spin(61, 104, " °C", "Every fan to full speed, and the governor's performance mode off")
        self.shutdown_spin = self.spin(62, 105, " °C", "A clean shutdown, when it stays this hot for the time on "
                                                      "the right")
        self.hold_spin = self.spin(3, 60, " s", "How long the temperature stays at the shutdown limit before the "
                                                "board shuts down")
        row = QHBoxLayout()
        for text, widget in (("Warn at", self.warn_spin), ("cool at", self.cool_spin),
                             ("shut down at", self.shutdown_spin), ("after", self.hold_spin)):
            row.addWidget(QLabel(text))
            row.addWidget(widget)
        row.addStretch(1)
        self.apply_button = accent_button("Turn on…", "Install the guard as a system service with these limits")
        self.apply_button.clicked.connect(self.apply)
        self.off_button = QPushButton("Turn off…")
        self.off_button.setToolTip("Stop and remove the guard; the fans go back as they were")
        self.off_button.clicked.connect(self.turn_off)
        self.defaults_button = QPushButton("Defaults")
        self.defaults_button.setToolTip("85, 90 and 95 °C, 10 s")
        self.defaults_button.clicked.connect(lambda: self.show_limits(guard.Limits()))
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for w in (self.defaults_button, self.off_button, self.apply_button):
            buttons.addWidget(w)
        self.guard_note = hint_label("")
        lay_guard = QVBoxLayout(guarded)
        lay_guard.addLayout(row)
        lay_guard.addLayout(buttons)
        lay_guard.addWidget(self.guard_note)
        lay_guard.addWidget(hint_label(
            "The guard watches the hotter of the GPU (edge) and the CPU (Tctl) every 2 seconds, also with this window "
            "closed and from boot. At the warning it sends a desktop notification. At the cooling limit it turns "
            "every fan to full speed and the governor's performance mode off. When the temperature stays at the "
            f"shutdown limit for the time set, it shuts the board down cleanly. {guard.REARM_C} °C below the warning "
            "the fans go back as they were; performance mode stays off until you turn it on. AMD publishes no "
            "limits for the BC-250; the defaults follow what boards are known to take: throttling from about 85 °C, "
            f"instability from 90 to 95 °C. <a href='{MANUAL_URL}'>Manual</a>"))

        fans = QGroupBox("Fans")
        self.fans_label = QLabel()
        self.fans_label.setTextFormat(Qt.TextFormat.RichText)
        self.fans_label.setWordWrap(True)
        self.fans_note = hint_label("")
        lay_fans = QVBoxLayout(fans)
        lay_fans.addWidget(self.fans_label)
        lay_fans.addWidget(self.fans_note)
        lay_fans.addWidget(hint_label(
            "A fan on CPU_FAN1 is the one the board can drive and read. J4003 carries the speed signal and the "
            "control of four more fans, without power: a fan there takes its 12 V from the power supply. A fan "
            "powered straight from the power supply reports nothing, so the guard can neither see nor drive it. "
            "With a Y splitter on one header, only one of the fans reports its speed."))

        events = QGroupBox("What the guard did")
        self.events_view = QPlainTextEdit()
        self.events_view.setReadOnly(True)
        self.events_view.setMaximumBlockCount(200)
        QVBoxLayout(events).addWidget(self.events_view)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(header)
        lay.addWidget(guarded)
        lay.addWidget(fans)
        lay.addWidget(events, 1)
        version = QLabel(f"{APP_NAME} {__version__} · core {CORE_VERSION} · the board changes only while the guard "
                         "is on")
        version.setStyleSheet("color:palette(placeholder-text);")
        lay.addWidget(version, 0, Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(central)

        geometry = self.settings.window_state("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.show_limits(guard.installed(self.paths) or guard.Limits())
        self.timer = QTimer(self)
        self.timer.setInterval(REFRESH_MS)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def spin(self, low: int, high: int, suffix: str, tooltip: str) -> QSpinBox:
        box = QSpinBox()
        box.setRange(low, high)
        box.setSuffix(suffix)
        box.setToolTip(tooltip)
        box.valueChanged.connect(lambda _v: self.refresh_buttons())
        return box

    # --- State ------------------------------------------------------------------------------------------------

    def limits(self) -> guard.Limits:
        return guard.Limits(self.warn_spin.value(), self.cool_spin.value(), self.shutdown_spin.value(),
                            self.hold_spin.value())

    def show_limits(self, limits: guard.Limits) -> None:
        self.warn_spin.setValue(limits.warn_c)
        self.cool_spin.setValue(limits.cool_c)
        self.shutdown_spin.setValue(limits.shutdown_c)
        self.hold_spin.setValue(limits.hold_s)

    def refresh(self) -> None:
        reading = guard.read_sensors(self.sys_root)
        self.installed = guard.installed(self.paths)
        self.state = guard.read_state(self.paths, self.clock()) if self.installed else None
        limits = self.installed or self.limits()
        for box, value in ((self.gpu_box, reading.gpu_c), (self.cpu_box, reading.cpu_c)):
            box.set_value(celsius_text(value))
            hot = value is not None and value >= limits.cool_c
            set_box_colour(box, RED if hot else ORANGE if value is not None and value >= limits.warn_c else BLUE)
        self.show_fans(reading)
        self.show_guard(reading)
        self.refresh_buttons()

    def show_fans(self, reading: guard.Reading) -> None:
        turning = reading.turning
        if turning:
            first = turning[0]
            self.fan_box.set_value(f"{first.rpm} RPM", f"{first.header}, {first.mode_text}")
            self.fan_box.caption.setText(first.header if len(turning) == 1 else f"{first.header} (+{len(turning) - 1})")
        else:
            self.fan_box.set_value("—", "")
            self.fan_box.caption.setText("Fan")
        if not reading.fans:
            self.fans_label.setText("No fan controller found.")
            self.fans_note.setText("The board's sensor chip (a Nuvoton NCT6686) needs the nct6687 driver, which "
                                   "Bazzite ships. Bazzite Test (test 22) checks it and says how to load it.")
            self.fans_note.setVisible(True)
            return
        rows = [f"<b>{escape(f.header)}</b>: {f.rpm} RPM, {escape(f.mode_text)}" for f in turning]
        silent = [f.header for f in reading.fans if not f.rpm]
        if silent:
            rows.append(f"No speed from {escape(', '.join(silent))}: nothing connected there, or a fan without a "
                        "speed signal.")
        self.fans_label.setText("<br>".join(rows))
        self.fans_note.setText("" if turning else "No fan reports a speed. A fan powered from the power supply runs "
                                                  "on its own: watch the temperatures above.")
        self.fans_note.setVisible(bool(self.fans_note.text()))

    def show_guard(self, reading: guard.Reading) -> None:
        notes = []
        if self.installed is None:
            self.badge.set_status("Guard off", "warn", "Nothing watches the temperatures while this window is closed.")
            self.guard_box.set_value("Off")
            set_box_colour(self.guard_box, BLUE)
        elif self.state is None:
            self.badge.set_status("Guard not running", "bad", "The guard is installed but does not run.")
            self.guard_box.set_value("Stopped")
            set_box_colour(self.guard_box, RED)
            notes.append(f"The guard is installed but has not reported in {guard.STALE_S} s. See its log: "
                         f"<code>journalctl -u {guard.UNIT}</code>")
        else:
            level = self.state.get("level", "ok")
            text, kind = {"ok": ("Guard on", "ok"), "warn": ("Hot", "warn"), "cooling": ("Cooling", "bad"),
                          "shutdown": ("Shutting down", "bad")}.get(level, ("Guard on", "ok"))
            self.badge.set_status(text, kind)
            self.guard_box.set_value("On" if level == "ok" else text)
            set_box_colour(self.guard_box, STATE_COLORS[kind])
        if self.installed is not None and guard.outdated(self.paths):
            notes.append("The guard was installed by another version of the app: press Apply to update it.")
        if reading.hottest is None:
            notes.append("No GPU or CPU temperature can be read on this system, so the guard would have nothing to "
                         "watch.")
        self.guard_note.setText("<br>".join(notes))
        self.guard_note.setVisible(bool(notes))
        events = (self.state or {}).get("events", [])
        text = "\n".join(f"{time.strftime('%d-%m %H:%M:%S', time.localtime(e.get('time', 0)))}  {e.get('text', '')}"
                         for e in reversed(events))
        text = text or ("The guard has nothing to report yet." if self.state else
                        "The guard is off." if self.installed is None else "")
        if text != self.events_view.toPlainText():
            self.events_view.setPlainText(text)

    def refresh_buttons(self) -> None:
        installed = getattr(self, "installed", None)
        problem = guard.limits_problem(self.limits())
        changed = installed != self.limits() or guard.outdated(self.paths)
        self.apply_button.setText("Apply…" if installed else "Turn on…")
        self.apply_button.setEnabled(not problem and (installed is None or changed))
        self.apply_button.setToolTip(problem or ("Update the guard with these limits" if installed else
                                                 "Install the guard as a system service with these limits"))
        self.off_button.setEnabled(installed is not None)

    # --- Actions ----------------------------------------------------------------------------------------------

    def apply(self) -> None:
        lim = self.limits()
        title = "Update the guard" if self.installed else "Turn on the guard"
        answer = QMessageBox.question(
            self, window_title(title),
            f"Run the thermal guard as a system service, from now on and at every boot?\n\n"
            f"At {lim.warn_c} °C it warns. At {lim.cool_c} °C it turns every fan to full speed and performance mode "
            f"off. At {lim.shutdown_c} °C held for {lim.hold_s} s it shuts the board down cleanly, to protect it. "
            "Below that the fans stay as they are. You can turn it off here at any time.\n\n"
            "It needs your password.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        error = self.runner(["install", "--warn", str(lim.warn_c), "--cool", str(lim.cool_c),
                             "--shutdown", str(lim.shutdown_c), "--hold", str(lim.hold_s)])
        if error:
            QMessageBox.warning(self, window_title(title), error)
        self.refresh()

    def turn_off(self) -> None:
        title = "Turn off the guard"
        answer = QMessageBox.question(
            self, window_title(title),
            "Stop and remove the thermal guard?\n\nNothing then watches the temperatures while this window is "
            "closed; the fans follow the firmware's curve.\n\nIt needs your password.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        error = self.runner(["uninstall"])
        if error:
            QMessageBox.warning(self, window_title(title), error)
        self.refresh()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.timer.stop()
        self.settings.set_window_state("geometry", self.saveGeometry())
        self.settings.sync()
        super().closeEvent(event)
