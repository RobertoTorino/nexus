# SPDX-License-Identifier: GPL-3.0-or-later
"""Performance page: runtime control of the governor over D-Bus (performance mode, fixed clock, range, load
target, temperature thresholds)."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout,
    QWidget,
)

from . import fmt
from .backends.base import GovernorConfig, PerformanceState
from .launch_options import LaunchOptionsBox
from .widgets import StatusPill, hint_label, page_header, set_button_active

FREQ_STEP = 25
FREQ_LIMIT = 3000


class PerformancePage(QWidget):
    """Everything here takes effect at once and is forgotten when the governor restarts."""

    enable_requested = pyqtSignal(bool)
    fixed_requested = pyqtSignal(int)
    range_requested = pyqtSignal(int, int)
    load_requested = pyqtSignal(float, float)      # lower, upper (0..1)
    temperature_requested = pyqtSignal(int, int)   # throttling, recovery (0 = not set)
    copy_requested = pyqtSignal()           # copy the runtime values to the Tuning page
    refresh_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._state = PerformanceState()
        self._seen = (None, None, None, None)   # runtime load/temp values the forms were last filled from
        layout = QVBoxLayout(self)
        header, _ = page_header("Performance")
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_requested)
        header.addWidget(refresh)
        layout.addLayout(header)

        layout.addWidget(hint_label(
            "Runtime controls over D-Bus (com.cyanskillfish.Governor): they apply immediately, need no password "
            "and are lost at the next governor restart. config.toml is unchanged; use the Tuning page to persist "
            "values. Performance mode opens the full safe-points range; a fixed frequency pins the clock; the "
            "load target and temperature thresholds change how the governor scales without touching the mode."))

        status = QGroupBox("Runtime state")
        grid = QGridLayout(status)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        self.pills: dict[str, StatusPill] = {}
        for col, (key, caption) in enumerate((("bus", "D-Bus"), ("mode", "Performance mode"))):
            grid.addWidget(QLabel(caption + ":"), 0, col * 2)
            pill = StatusPill()
            self.pills[key] = pill
            grid.addWidget(pill, 0, col * 2 + 1)
        self.fields: dict[str, QLabel] = {}
        rows = (("current", "Current range"),
                ("initial", "Range at start ([frequency-range])"),
                ("allowed", "Allowed range (safe points)"),
                ("load", "Load target (lower / upper)"),
                ("temp", "Temperature (throttle / recover)"))
        for index, (key, caption) in enumerate(rows, start=1):
            grid.addWidget(QLabel(caption + ":"), index, 0)
            value = QLabel("—")
            self.fields[key] = value
            grid.addWidget(value, index, 1, 1, 3)
        grid.setColumnStretch(4, 1)
        layout.addWidget(status)

        self.controls = QGroupBox("Controls")
        form = QFormLayout(self.controls)
        form.setVerticalSpacing(10)

        mode_row = QHBoxLayout()
        self.mode_button = QPushButton()
        # Wide enough for both labels in this font and language, so the button keeps its size when it toggles.
        widths = []
        for text in ("Performance mode: on", "Performance mode: off"):
            self.mode_button.setText(text)
            widths.append(self.mode_button.sizeHint().width())
        self.mode_button.setFixedWidth(max(widths))
        self.mode_button.setToolTip(("SetEnabled: on lets the governor use the whole allowed range and "
                                     "react faster to load; off returns to the range the governor started "
                                     "with."))
        self.mode_button.clicked.connect(lambda: self.enable_requested.emit(not self._state.enabled))
        set_button_active(self.mode_button, False)
        mode_row.addWidget(self.mode_button)
        mode_row.addStretch(1)
        form.addRow("Mode:", mode_row)

        fixed_row = QHBoxLayout()
        self.fixed = QSpinBox()
        self.fixed.setRange(0, FREQ_LIMIT)
        self.fixed.setSingleStep(FREQ_STEP)
        self.fixed.setSuffix(" MHz")
        self.fixed.setToolTip(("SetFixedFrequency: performance mode with the clock pinned here. Must lie "
                               "inside the allowed range."))
        self.fixed_button = QPushButton("Pin clock")
        self.fixed_button.clicked.connect(lambda: self.fixed_requested.emit(self.fixed.value()))
        fixed_row.addWidget(self.fixed)
        fixed_row.addWidget(self.fixed_button)
        fixed_row.addStretch(1)
        form.addRow("Fixed frequency:", fixed_row)

        range_row = QHBoxLayout()
        self.range_min = QSpinBox()
        self.range_max = QSpinBox()
        for spin in (self.range_min, self.range_max):
            spin.setRange(0, FREQ_LIMIT)
            spin.setSingleStep(FREQ_STEP)
            spin.setSuffix(" MHz")
            spin.setSpecialValueText("No limit")
        self.range_min.setToolTip("Lower clock limit for now; No limit = the lowest safe point.")
        self.range_max.setToolTip("Upper clock limit for now; No limit = the highest safe point.")
        self.range_button = QPushButton("Set range")
        self.range_button.setToolTip("SetRange(min, max): a temporary range, leaves performance mode.")
        self.range_button.clicked.connect(lambda: self.range_requested.emit(self.range_min.value(),
                                                                            self.range_max.value()))
        range_row.addWidget(self.range_min)
        range_row.addWidget(QLabel("to"))
        range_row.addWidget(self.range_max)
        range_row.addWidget(self.range_button)
        range_row.addStretch(1)
        form.addRow("Runtime range:", range_row)

        load_row = QHBoxLayout()
        self.load_lower = QDoubleSpinBox()
        self.load_upper = QDoubleSpinBox()
        for spin in (self.load_lower, self.load_upper):
            spin.setRange(1.0, 100.0)
            spin.setDecimals(0)
            spin.setSingleStep(1.0)
            spin.setSuffix(" %")
            spin.valueChanged.connect(self._check_targets)
        self.load_lower.setToolTip("Below this GPU load the governor steps the clock down.")
        self.load_upper.setToolTip("Above this GPU load the governor steps the clock up.")
        self.load_button = QPushButton("Set load target")
        self.load_button.setToolTip(("SetLoadTarget(lower, upper): the load band the governor keeps the "
                                     "GPU in, until the next restart. Does not touch performance mode."))
        self.load_button.clicked.connect(lambda: self.load_requested.emit(self.load_lower.value() / 100,
                                                                          self.load_upper.value() / 100))
        load_row.addWidget(self.load_lower)
        load_row.addWidget(QLabel("to"))
        load_row.addWidget(self.load_upper)
        load_row.addWidget(self.load_button)
        load_row.addStretch(1)
        form.addRow("Load target:", load_row)

        temp_row = QHBoxLayout()
        self.temp_throttle = QSpinBox()
        self.temp_throttle.setRange(1, 100)
        self.temp_throttle.setSuffix(" °C")
        self.temp_throttle.setToolTip("Above this temperature the governor lowers the maximum clock.")
        self.temp_recover = QSpinBox()
        self.temp_recover.setRange(0, 100)
        self.temp_recover.setSuffix(" °C")
        self.temp_recover.setSpecialValueText("Not set")
        self.temp_recover.setToolTip(("Below this temperature the full range is allowed again; Not set = "
                                      "the governor's own hysteresis."))
        for spin in (self.temp_throttle, self.temp_recover):
            spin.valueChanged.connect(self._check_targets)
        self.temp_button = QPushButton("Set temperatures")
        self.temp_button.setToolTip(("SetTemperatureThresholds(throttling, recovery): until the next "
                                     "restart. Does not touch performance mode."))
        self.temp_button.clicked.connect(lambda: self.temperature_requested.emit(self.temp_throttle.value(),
                                                                                 self.temp_recover.value()))
        temp_row.addWidget(self.temp_throttle)
        temp_row.addWidget(QLabel("/"))
        temp_row.addWidget(self.temp_recover)
        temp_row.addWidget(self.temp_button)
        temp_row.addStretch(1)
        form.addRow("Temperature:", temp_row)
        self.target_warning = hint_label("")
        form.addRow(self.target_warning)

        self.copy_button = QPushButton("Copy runtime values to the Tuning page")
        self.copy_button.setToolTip(("Puts the current range, load target and temperatures into the "
                                     "Tuning form so you can save them to config.toml."))
        self.copy_button.clicked.connect(self.copy_requested)
        form.addRow(self.copy_button)
        layout.addWidget(self.controls)

        self.reason = hint_label("")
        layout.addWidget(self.reason)

        self.launch = LaunchOptionsBox()
        layout.addWidget(self.launch)
        layout.addStretch(1)

    def update(self, state: PerformanceState, saved: GovernorConfig, service_active: bool) -> None:
        self._state = state
        bus = self.pills["bus"]
        mode = self.pills["mode"]
        if state.available:
            bus.set_status("Reachable", "ok",
                           "com.cyanskillfish.Governor answers on the system bus.")
            mode.set_status("On" if state.enabled else "Off", "ok" if state.enabled else "neutral",
                            "Enabled property of the PerformanceMode interface.")
            set_button_active(self.mode_button, state.enabled)
            self.mode_button.setText("Performance mode: on" if state.enabled
                                     else "Performance mode: off")
            self.fields["current"].setText(_range(state.current_min, state.current_max))
            self.fields["initial"].setText(_range(state.initial_min, state.initial_max))
            self.fields["allowed"].setText(_range(state.allowed_min, state.allowed_max))
            self.fields["load"].setText(fmt("%1 % / %2 %", f"{state.load_min * 100:.0f}",
                                             f"{state.load_max * 100:.0f}"))
            recovery = fmt("%1 °C", str(state.temp_recovery)) if state.temp_recovery else "not set"
            self.fields["temp"].setText(fmt("%1 °C / %2", str(state.temp_throttling), recovery))
            if state.allowed_max:
                self.fixed.setRange(state.allowed_min, state.allowed_max)
                if not self.fixed.value():
                    self.fixed.setValue(state.allowed_max)
            # Refill the load/temperature forms only when the governor's values change, so a poll does not
            # overwrite what the user is typing.
            seen = (state.load_min, state.load_max, state.temp_throttling, state.temp_recovery)
            if seen != self._seen:
                self._seen = seen
                if state.load_max:
                    self.load_lower.setValue(round(state.load_min * 100))
                    self.load_upper.setValue(round(state.load_max * 100))
                if state.temp_throttling:
                    self.temp_throttle.setValue(state.temp_throttling)
                    self.temp_recover.setValue(state.temp_recovery)
            self.reason.setText("")
            self.launch.prefill(state)
        else:
            bus.set_status("Unreachable", "warn", state.error)
            mode.set_status("Unknown", "neutral", "")
            set_button_active(self.mode_button, False)
            self.mode_button.setText("Performance mode: off")
            for field in self.fields.values():
                field.setText("—")
            if not service_active:
                reason = "The governor service is not running (Service page)."
            elif not saved.dbus_enabled:
                reason = ("D-Bus is off in config.toml: enable it on the Tuning page and apply with a "
                          "restart.")
            else:
                reason = state.error or "The governor did not answer on the system bus."
            self.reason.setText(fmt("Controls are disabled: %1", reason))
        self.controls.setEnabled(state.available)
        self._check_targets()

    def _check_targets(self, *_args) -> None:
        """Keep the buttons off while the load band or the temperature pair cannot be sent."""
        problems = []
        load_ok = self.load_lower.value() < self.load_upper.value()
        if not load_ok:
            problems.append("the lower load target must be below the upper one")
        recovery = self.temp_recover.value()
        temp_ok = not recovery or recovery < self.temp_throttle.value()
        if not temp_ok:
            problems.append("recovery must be below the throttling temperature (or Not set)")
        self.load_button.setEnabled(load_ok)
        self.temp_button.setEnabled(temp_ok)
        text = "; ".join(problems)
        self.target_warning.setText(text[0].upper() + text[1:] + "." if text else "")

    def state(self) -> PerformanceState:
        return self._state


def _range(low: int, high: int) -> str:
    if not low and not high:
        return "—"
    no_limit = "no limit"
    return fmt("%1 – %2 MHz",
               str(low) if low else no_limit, str(high) if high else no_limit)
