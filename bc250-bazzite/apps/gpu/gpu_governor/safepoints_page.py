# SPDX-License-Identifier: GPL-3.0-or-later
"""Safe points page: the [[safe-points]] frequency/voltage curve of config.toml, with an editor that checks the
points against the governor's rules and the community hard rails before anything is written."""

from __future__ import annotations

from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QScatterSeries, QValueAxis
from PyQt6.QtCore import QMargins, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSpinBox,
    QTableWidget, QVBoxLayout, QWidget,
)

from . import fmt
from .backends.base import PerformanceState, SafePoint
from .stress import NO_TOOL, available_tools
from .widgets import ACCENT, BLUE, ORANGE, RED, accent_button, hint_label, page_header

BISECT_URL = "https://github.com/RobertoTorino/nexus/tree/main/bc250-bazzite/apps/oc"


# Hard rails, the same as bc250-gpu-oc-bisect: community reports of hard-locks above ~2000 MHz and one bricked
# board from overvolting. The governor itself only insists on unique frequencies and non-decreasing voltage.
HARD_MAX_FREQ = 2500
HARD_MIN_VOLT = 700
HARD_MAX_VOLT = 1100
WARN_FREQ = 2000
WARN_VOLT = 1000
FREQ_STEP = 25
VOLT_STEP = 5
MIN_POINTS = 2


def validate(points: list[tuple[int, int]]) -> tuple[list[str], list[str]]:
    """(errors, warnings) for a list of (frequency, voltage). Errors block Apply; warnings only tell."""
    errors: list[str] = []
    warnings: list[str] = []
    if len(points) < MIN_POINTS:
        errors.append(fmt("At least %1 points are needed.",
                           str(MIN_POINTS)))
    seen: dict[int, int] = {}
    for frequency, voltage in points:
        if frequency in seen:
            errors.append(fmt("%1 MHz appears twice.", str(frequency)))
        seen[frequency] = voltage
        if not 0 < frequency <= HARD_MAX_FREQ:
            errors.append(fmt("%1 MHz is outside 1–%2 MHz.",
                               str(frequency), str(HARD_MAX_FREQ)))
        if not HARD_MIN_VOLT <= voltage <= HARD_MAX_VOLT:
            errors.append(fmt("%1 mV at %2 MHz is outside %3–%4 mV.",
                               str(voltage), str(frequency), str(HARD_MIN_VOLT), str(HARD_MAX_VOLT)))
    ordered = sorted(points)
    for (f0, v0), (f1, v1) in zip(ordered, ordered[1:]):
        if v1 < v0:
            errors.append(fmt(("%1 mV at %2 MHz is lower than %3 mV at %4 MHz; voltage must not drop "
                               "as the frequency rises (governor rule)."), str(v1), str(f1), str(v0), str(f0)))
    top = [f for f, _ in points if f > WARN_FREQ]
    if top:
        warnings.append(fmt("%1 MHz is above %2 MHz, where many boards start to hard-lock.",
                             str(max(top)), str(WARN_FREQ)))
    hot = [v for _, v in points if v > WARN_VOLT]
    if hot:
        warnings.append(fmt("%1 mV is above %2 mV; keep an eye on temperature and the PSU.",
                             str(max(hot)), str(WARN_VOLT)))
    return errors, warnings


class SafePointsPage(QWidget):
    apply_requested = pyqtSignal(list, bool)      # [(frequency, voltage)], restart
    dirty_changed = pyqtSignal(bool)
    test_requested = pyqtSignal(int, int, int, str)   # frequency, voltage, seconds (0 = until stopped), load tool
    stop_test_requested = pyqtSignal()

    def __init__(self, config_path: str, defaults: tuple[tuple[int, int], ...], parent: QWidget | None = None):
        super().__init__(parent)
        self.config_path = config_path
        self.defaults = [tuple(p) for p in defaults]
        self._saved: list[tuple[int, int]] = []
        self._loading = False
        self._bus_ok = False
        self._testing = False
        self._notice = ""
        layout = QVBoxLayout(self)
        header, _ = page_header("Safe points")
        self.reload = QPushButton("Reload from disk")
        header.addWidget(self.reload)
        layout.addLayout(header)
        layout.addWidget(hint_label(fmt(
            "The [[safe-points]] of %1 define the frequency/voltage curve the governor scales along. "
            "It never leaves the range between the lowest and the highest point; [frequency-range] and the runtime "
            "controls are clamped to it. Edit with care: wrong voltages can freeze or damage the board. Apply checks "
            "the governor's rules and the hard rails (%2–%3 mV, up to %4 "
            "MHz) first and makes a backup.", config_path, str(HARD_MIN_VOLT), str(HARD_MAX_VOLT),
            str(HARD_MAX_FREQ))))

        body = QHBoxLayout()
        body.setSpacing(12)
        table_box = QGroupBox("Points")
        table_layout = QVBoxLayout(table_box)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Frequency", "Voltage"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table_layout.addWidget(self.table)
        row_buttons = QHBoxLayout()
        self.add_button = QPushButton("Add point")
        self.add_button.setToolTip("Adds a point after the selected one, halfway to the next.")
        self.add_button.clicked.connect(self._add_point)
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self._remove_point)
        self.sort_button = QPushButton("Sort")
        self.sort_button.setToolTip("Order the rows by frequency (Apply does this anyway).")
        self.sort_button.clicked.connect(lambda: self._set_points(sorted(self.points())))
        row_buttons.addWidget(self.add_button)
        row_buttons.addWidget(self.remove_button)
        row_buttons.addWidget(self.sort_button)
        row_buttons.addStretch(1)
        table_layout.addLayout(row_buttons)
        self.summary = QLabel("—")
        self.summary.setWordWrap(True)
        table_layout.addWidget(self.summary)
        body.addWidget(table_box, 2)

        chart_box = QGroupBox("Curve")
        chart_layout = QVBoxLayout(chart_box)
        self.chart = QChart()
        self.chart.setBackgroundVisible(False)
        self.chart.setMargins(QMargins(4, 4, 4, 4))
        self.chart.legend().hide()
        text_colour = self.palette().windowText().color()
        self.line = QLineSeries()
        self.line.setPen(QPen(QColor(ACCENT), 2))
        self.dots = QScatterSeries()
        self.dots.setMarkerSize(9)
        self.dots.setColor(QColor(BLUE))
        self.dots.setBorderColor(QColor(BLUE))
        self.chart.addSeries(self.line)
        self.chart.addSeries(self.dots)
        self.axis_x = QValueAxis()
        self.axis_x.setTitleText("MHz")
        self.axis_x.setLabelFormat("%d")
        self.axis_y = QValueAxis()
        self.axis_y.setTitleText("mV")
        self.axis_y.setLabelFormat("%d")
        for axis, where in ((self.axis_x, Qt.AlignmentFlag.AlignBottom), (self.axis_y, Qt.AlignmentFlag.AlignLeft)):
            axis.setLabelsColor(text_colour)
            axis.setTitleBrush(text_colour)
            self.chart.addAxis(axis, where)
            self.line.attachAxis(axis)
            self.dots.attachAxis(axis)
        view = QChartView(self.chart)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setMinimumHeight(240)
        chart_layout.addWidget(view)
        body.addWidget(chart_box, 3)
        layout.addLayout(body, 1)

        self.problems = QLabel("")
        self.problems.setWordWrap(True)
        self.problems.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.problems)

        apply_row = QHBoxLayout()
        self.apply_button = accent_button("Apply safe points",
                                          ("Writes the [[safe-points]] blocks to config.toml (asks for your "
                                           "password, makes a backup first)."))
        self.apply_button.clicked.connect(lambda: self.apply_requested.emit(sorted(self.points()),
                                                                             self.restart.isChecked()))
        self.restart = QCheckBox("Restart the governor afterwards")
        self.restart.setChecked(True)
        self.restart.setToolTip("The governor reads config.toml only at start.")
        self.revert_button = QPushButton("Revert")
        self.revert_button.setToolTip("Back to the points in the file.")
        self.revert_button.clicked.connect(lambda: self._set_points(self._saved))
        self.defaults_button = QPushButton("Shipped defaults")
        self.defaults_button.setToolTip(fmt(
            "The active points of the governor's default-config.toml: %1",
            ", ".join(f"{f}@{v}" for f, v in self.defaults)))
        self.defaults_button.clicked.connect(lambda: self._set_points(self.defaults))
        apply_row.addWidget(self.apply_button)
        apply_row.addWidget(self.restart)
        apply_row.addStretch(1)
        apply_row.addWidget(self.revert_button)
        apply_row.addWidget(self.defaults_button)
        layout.addLayout(apply_row)

        self.test_box = test_box = QGroupBox("Test a point before saving it (runtime, root)")
        test_layout = QVBoxLayout(test_box)
        test_layout.addWidget(hint_label(
            "SetTestMode over D-Bus pins this frequency and voltage right now and stops the automatic scaling; "
            "the governor's thermal throttling stays active. Nothing is written to config.toml and the governor "
            "applies the pair as given, so stay inside the hard rails. Put the GPU under load while it runs. "
            "Stop test (or the timer) switches performance mode off, which returns to normal scaling with the "
            "start-up range. A point the silicon cannot hold freezes the board; have your work saved."))
        tool_row = QHBoxLayout()
        tool_row.addWidget(QLabel("Load:"))
        self.test_tool = QComboBox()
        # The real tool names are data as well as text; NO_TOOL stays the English sentinel main_window compares with.
        self.test_tool.addItem(NO_TOOL, NO_TOOL)
        for name in available_tools():
            self.test_tool.addItem(name, name)
        if self.test_tool.count() > 1:
            self.test_tool.setCurrentIndex(1)
        self.test_tool.setToolTip(("A GPU load generator found on PATH, started with the test and killed "
                                   "when it ends. If it dies while the point is pinned, that is reported."))
        tool_row.addWidget(self.test_tool, 1)
        tool_row.addWidget(hint_label("" if self.test_tool.count() > 1 else
                                      ("No load tool found (vkmark, glmark2, vkcube or glxgears): run a game "
                                       "or benchmark yourself during the test.")), 2)
        test_layout.addLayout(tool_row)
        test_row = QHBoxLayout()
        self.test_freq = QSpinBox()
        self.test_freq.setRange(1, HARD_MAX_FREQ)
        self.test_freq.setSingleStep(FREQ_STEP)
        self.test_freq.setSuffix(" MHz")
        self.test_freq.setToolTip("Prefilled from the selected row; edit freely.")
        self.test_volt = QSpinBox()
        self.test_volt.setRange(HARD_MIN_VOLT, HARD_MAX_VOLT)
        self.test_volt.setSingleStep(VOLT_STEP)
        self.test_volt.setSuffix(" mV")
        self.test_seconds = QSpinBox()
        self.test_seconds.setRange(0, 3600)
        self.test_seconds.setValue(60)
        self.test_seconds.setSuffix(" s")
        self.test_seconds.setSpecialValueText("Until stopped")
        self.test_seconds.setToolTip(("The app ends the test by itself after this time (0 = only by Stop "
                                      "test)."))
        test_row.addWidget(QLabel("Frequency:"))
        test_row.addWidget(self.test_freq)
        test_row.addWidget(QLabel("Voltage:"))
        test_row.addWidget(self.test_volt)
        test_row.addWidget(QLabel("For:"))
        test_row.addWidget(self.test_seconds)
        test_row.addStretch(1)
        self.test_button = QPushButton("Start test")
        self.test_button.setToolTip("Asks for your password (pkexec): the TestMode interface is root-only.")
        self.test_button.clicked.connect(
            lambda: self.test_requested.emit(self.test_freq.value(), self.test_volt.value(), self.test_seconds.value(),
                                             self.test_tool.currentData()))
        self.stop_test_button = QPushButton("Stop test")
        self.stop_test_button.setEnabled(False)
        self.stop_test_button.clicked.connect(self.stop_test_requested)
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.stop_test_button)
        self.add_test_button = QPushButton("Add to table")
        self.add_test_button.setToolTip(("Puts this frequency/voltage pair into the safe-points table above "
                                         "(sorted by frequency, replacing a point at the same frequency). "
                                         "Apply to save."))
        self.add_test_button.clicked.connect(self._add_test_point)
        test_row.addWidget(self.add_test_button)
        test_layout.addLayout(test_row)
        self.test_status = hint_label("")
        test_layout.addWidget(self.test_status)
        layout.addWidget(test_box)
        self.table.currentCellChanged.connect(self._row_selected)
        for spin in (self.test_freq, self.test_volt):
            spin.valueChanged.connect(self._test_point_changed)
        self._test_point_changed()

        self.runtime = hint_label("")
        layout.addWidget(self.runtime)
        layout.addWidget(hint_label(fmt(
            "Finding how far your own board can go (higher top frequency, lower voltages) is a job for "
            "%1: it tests one step at a time under a verified load and "
            "can install the result. Edit the points by hand only if you know what the silicon tolerates.",
            f'<a href="{BISECT_URL}">bc250-gpu-oc-bisect</a>')))

    # ------------------------------------------------------------------ model
    def load(self, points: list[SafePoint]) -> None:
        """Points as read from the file: becomes the saved state Revert goes back to."""
        self._saved = [(p.frequency, p.voltage) for p in points]
        self._set_points(self._saved)
        if not self._testing and self.table.currentRow() < 0 and self.table.rowCount():
            self._row_selected(self.table.rowCount() - 1)      # the top point is the one usually under test

    def points(self) -> list[tuple[int, int]]:
        out = []
        for row in range(self.table.rowCount()):
            freq = self.table.cellWidget(row, 0)
            volt = self.table.cellWidget(row, 1)
            if freq is not None and volt is not None:
                out.append((freq.value(), volt.value()))
        return out

    def is_dirty(self) -> bool:
        return sorted(self.points()) != sorted(self._saved)

    def _set_points(self, points: list[tuple[int, int]]) -> None:
        self._loading = True
        self.table.setRowCount(0)
        for frequency, voltage in points:
            self._insert_row(self.table.rowCount(), frequency, voltage)
        self._loading = False
        self._changed()

    def _insert_row(self, row: int, frequency: int, voltage: int) -> None:
        self.table.insertRow(row)
        freq = QSpinBox()
        freq.setRange(1, HARD_MAX_FREQ)
        freq.setSingleStep(FREQ_STEP)
        freq.setSuffix(" MHz")
        freq.setValue(frequency)
        volt = QSpinBox()
        volt.setRange(HARD_MIN_VOLT, HARD_MAX_VOLT)
        volt.setSingleStep(VOLT_STEP)
        volt.setSuffix(" mV")
        volt.setValue(voltage)
        for col, spin in enumerate((freq, volt)):
            spin.setFrame(False)
            spin.setAlignment(Qt.AlignmentFlag.AlignRight)
            spin.valueChanged.connect(self._changed)
            self.table.setCellWidget(row, col, spin)

    def _add_point(self) -> None:
        points = self.points()
        row = self.table.currentRow()
        if row < 0:
            row = len(points) - 1
        if not points:
            frequency, voltage = self.defaults[0] if self.defaults else (500, HARD_MIN_VOLT)
        elif row + 1 < len(points):
            (f0, v0), (f1, v1) = points[row], points[row + 1]
            frequency, voltage = (f0 + f1) // 2 // FREQ_STEP * FREQ_STEP, (v0 + v1) // 2 // VOLT_STEP * VOLT_STEP
        else:
            f0, v0 = points[row]
            frequency, voltage = min(f0 + 100, HARD_MAX_FREQ), min(v0 + 20, HARD_MAX_VOLT)
        self._insert_row(row + 1, frequency, voltage)
        self.table.selectRow(row + 1)
        self._changed()

    def _remove_point(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self._changed()

    # ------------------------------------------------------------------ view
    def _changed(self, *_) -> None:
        if self._loading:
            return
        points = self.points()
        ordered = sorted(points)
        errors, warnings = validate(points)
        self.line.clear()
        self.dots.clear()
        for frequency, voltage in ordered:
            self.line.append(frequency, voltage)
            self.dots.append(frequency, voltage)
        self.dots.setColor(QColor(RED if errors else BLUE))
        self.dots.setBorderColor(QColor(RED if errors else BLUE))
        if ordered:
            (lf, lv), (hf, hv) = ordered[0], ordered[-1]
            self.summary.setText(fmt("%1 points: %2 MHz @ %3 mV up to %4 MHz @ %5 mV.",
                                      str(len(ordered)), str(lf), str(lv), str(hf), str(hv)))
            x0, x1 = _floor(lf - 100, 250), _ceil(hf + 100, 250)
            volts = [v for _, v in ordered]
            y0, y1 = _floor(min(volts) - 50, 50), _ceil(max(volts) + 50, 50)
        else:
            self.summary.setText(("No [[safe-points]]; the governor would fall back to 350 MHz @ 700 mV and "
                                  "2000 MHz @ 1000 mV."))
            x0, x1, y0, y1 = 0, 2500, 600, 1100
        self.axis_x.setRange(x0, x1)
        self.axis_x.setTickCount((x1 - x0) // 250 + 1)
        self.axis_y.setRange(y0, y1)
        self.axis_y.setTickCount((y1 - y0) // 50 + 1)

        dirty = self.is_dirty()
        html = "".join(f'<div style="color:{RED};">✖ {e}</div>' for e in errors)
        html += "".join(f'<div style="color:{ORANGE};">⚠ {w}</div>' for w in warnings)
        if dirty and not errors and self._saved:
            html += self._diff_note(ordered)
        self.problems.setText(html)
        self.apply_button.setEnabled(dirty and not errors)
        self.revert_button.setEnabled(dirty)
        self.remove_button.setEnabled(self.table.rowCount() > 0)
        self.dirty_changed.emit(dirty)
        self._test_point_changed()

    def _diff_note(self, ordered: list[tuple[int, int]]) -> str:
        saved = sorted(self._saved)
        notes = []
        if ordered[-1][0] > saved[-1][0]:
            notes.append(fmt("raises the top frequency from %1 to %2 MHz",
                              str(saved[-1][0]), str(ordered[-1][0])))
        lowered = [(f, v) for f, v in ordered if f in dict(saved) and v < dict(saved)[f]]
        if lowered:
            notes.append(fmt("lowers the voltage at %1 existing point(s)", str(len(lowered))))
        if not notes:
            return ""
        return f'<div style="color:{ORANGE};">⚠ ' + fmt(
            "This change %1: an unstable point can freeze the board under load. Verify it with "
            "bc250-gpu-oc-bisect first.", " and ".join(notes)) + '</div>'

    def show_runtime(self, state: PerformanceState) -> None:
        self._bus_ok = state.available
        if state.available and state.allowed_max:
            no_limit = "no limit"
            self.runtime.setText(fmt("Governor (D-Bus): allowed range %1–%2 MHz, current range %3–%4 MHz.",
                str(state.allowed_min), str(state.allowed_max),
                str(state.current_min) if state.current_min else no_limit,
                str(state.current_max) if state.current_max else no_limit))
        else:
            self.runtime.setText("")
        self._test_point_changed()

    # ------------------------------------------------------------------ test mode
    def set_features(self, *, dbus: bool) -> None:
        self.test_box.setVisible(dbus)

    def _row_selected(self, row: int, *_) -> None:
        freq = self.table.cellWidget(row, 0)
        volt = self.table.cellWidget(row, 1)
        if freq is not None and volt is not None:
            self.test_freq.setValue(freq.value())
            self.test_volt.setValue(volt.value())

    def _add_test_point(self) -> None:
        frequency, voltage = self.test_freq.value(), self.test_volt.value()
        points = self.points()
        for row, (f, _) in enumerate(points):
            if f == frequency:
                self.table.cellWidget(row, 1).setValue(voltage)
                self.table.selectRow(row)
                self._changed()
                return
        row = sum(1 for f, _ in points if f < frequency)
        self._insert_row(row, frequency, voltage)
        self.table.selectRow(row)
        self._changed()

    def _test_point_changed(self, *args) -> None:
        if self._testing:
            return
        if args:                            # a spin box changed: an old end-of-test notice is stale now
            self._notice = ""
        frequency, voltage = self.test_freq.value(), self.test_volt.value()
        warnings = []
        if frequency > WARN_FREQ:
            warnings.append(fmt("%1 MHz is above %2 MHz, where many boards hard-lock",
                                 str(frequency), str(WARN_FREQ)))
        if voltage > WARN_VOLT:
            warnings.append(fmt("%1 mV is above %2 mV", str(voltage), str(WARN_VOLT)))
        curve = sorted(self.points())
        expected = _interpolate(curve, frequency)
        if expected is not None and voltage < expected:
            warnings.append(fmt("the curve above would give %1 mV at %2 MHz; this is lower",
                                 str(expected), str(frequency)))
        if not self._bus_ok:
            self.test_status.setText(("The governor's D-Bus interface is not reachable (service stopped or "
                                      "[dbus] enabled = false)."))
        elif self._notice:
            self.test_status.setText(self._notice)
        elif warnings:
            self.test_status.setText(f'<span style="color:{ORANGE};">⚠ ' + "; ".join(warnings) + ".</span>")
        else:
            self.test_status.setText("")
        self.test_button.setEnabled(self._bus_ok)

    def show_test(self, active: bool, text: str = "") -> None:
        """Reflect the test the main window is running: lock the inputs, show the countdown; when it ends,
        keep `text` as a notice until the inputs change."""
        self._testing = active
        for widget in (self.test_freq, self.test_volt, self.test_seconds, self.test_tool, self.test_button,
                       self.add_test_button):
            widget.setEnabled(not active and (self._bus_ok or widget is not self.test_button))
        self.stop_test_button.setEnabled(active)
        if active:
            self.test_status.setText(f'<span style="color:{ORANGE};">● {text}</span>')
        else:
            self._notice = text
            self._test_point_changed()


def _interpolate(curve: list[tuple[int, int]], frequency: int) -> int | None:
    """The voltage the governor would pick for `frequency` from a sorted curve (linear between points)."""
    if not curve:
        return None
    if frequency <= curve[0][0]:
        return curve[0][1]
    if frequency >= curve[-1][0]:
        return curve[-1][1]
    for (f0, v0), (f1, v1) in zip(curve, curve[1:]):
        if f0 <= frequency <= f1:
            return round(v0 + (v1 - v0) * (frequency - f0) / (f1 - f0))
    return None


def _floor(value: int, step: int) -> int:
    return max(0, value // step * step)


def _ceil(value: int, step: int) -> int:
    return -(-value // step) * step
