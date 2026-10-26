# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the main window: Overview and Service (the editors live in config_pages, performance_page)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PyQt6.QtCore import QMargins, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import fmt
from .backends.base import GovernorConfig, GovernorInstallStatus, GpuTelemetry, PerformanceState, ServiceStatus
from .backends.gpu_metrics import GpuMetrics
from .history import MAX_SECONDS, History, Sample, summarise
from .journal import JournalView
from .widgets import ACCENT, BLUE, ORANGE, StatusPill, Terminal, hint_label, page_header


POLL_MS = 2000
CHART_WINDOWS = ((120, "2 min"), (600, "10 min"),
                 (1800, "30 min"), (3600, "60 min"))
HISTORY_POINTS = MAX_SECONDS * 1000 // POLL_MS
CLOCK_AXIS_MHZ = 2500               # the governor's hard ceiling; the right-hand axis of the chart

LOAD_SOURCES = {
    "gpu_metrics": "average_gfx_activity of the governor's patched gpu_metrics table.",
    "gpu_busy_percent": "amdgpu gpu_busy_percent sysfs sensor.",
    "radeontop": "Fallback: radeontop.",
}


METRIC_ROWS = (
    ("version", "Table"), ("gfx_activity", "GFX activity"),
    ("mm_activity", "MM activity"), ("temp_gfx", "GFX temp"),
    ("temp_soc", "SoC temp"), ("socket_power", "Socket power"),
    ("gfx_power", "GFX power"), ("cpu_power", "CPU power"),
    ("gfxclk", "GFX clock"), ("avg_gfxclk", "Avg GFX clock"),
    ("socclk", "SoC clock"), ("uclk", "Memory clock"),
    ("fclk", "Fabric clock"),
    ("throttle", "Throttle status"), ("cores", "CPU cores"),
)


def load_sensor_hint(snap: "Snapshot") -> str:
    """What the user can do about a missing GPU load sensor, from the most likely cause down."""
    if not snap.fix_metrics_supported:
        return ("Only cyan-skillfish-governor-smu publishes a load figure (fix-metrics); the tt governor "
                "does not, so this stays unavailable.")
    if not snap.service.installed:
        return "Install cyan-skillfish-governor-smu; it measures the load and publishes it via gpu_metrics."
    if not snap.saved.fix_metrics:
        return ("Enable fix-metrics on the GPU Usage page and apply with a "
                "restart.")
    if not snap.service.active:
        return ("Start the governor service on the Service page; fix-metrics is on but nothing publishes "
                "the load.")
    if not snap.mounted:
        return ("fix-metrics is on and the service runs, but no patched gpu_metrics is mounted: check the "
                "journal.")
    return "The patched gpu_metrics table holds no valid load value; check the Service page journal."


@dataclass
class Snapshot:
    """Everything the pages show, polled by the main window every POLL_MS."""

    install: GovernorInstallStatus
    service: ServiceStatus
    mounted: bool
    telemetry: GpuTelemetry
    saved: GovernorConfig
    perf: PerformanceState
    fix_metrics_supported: bool = True


class OverviewPage(QWidget):
    export_requested = pyqtSignal()
    compare_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        header, _ = page_header("Overview")
        layout.addLayout(header)

        status = QGroupBox("Runtime status")
        grid = QGridLayout(status)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        self.pills: dict[str, StatusPill] = {}
        self.pill_labels: dict[str, QLabel] = {}
        for row, col, key, caption in ((0, 0, "service", "Governor service"),
                                       (0, 2, "mount", "gpu_metrics override"),
                                       (1, 0, "sensor", "GPU load sensor"),
                                       (1, 2, "fix", "fix-metrics (saved)"),
                                       (2, 0, "perf", "Performance mode"), (2, 2, "bus", "D-Bus")):
            self.pill_labels[key] = QLabel(caption + ":")
            grid.addWidget(self.pill_labels[key], row, col)
            pill = StatusPill()
            self.pills[key] = pill
            grid.addWidget(pill, row, col + 1)
        grid.setColumnStretch(4, 1)
        layout.addWidget(status)

        self.chart_box = QGroupBox("GPU load, clock and temperature")
        chart_layout = QVBoxLayout(self.chart_box)
        self.history = History(HISTORY_POINTS)
        tools = QHBoxLayout()
        tools.addWidget(QLabel("Window:"))
        self.window = QComboBox()
        for seconds, label in CHART_WINDOWS:
            self.window.addItem(label, seconds)
        self.window.setToolTip(fmt(("How much of the last %1 minutes the chart shows; the export "
                                    "always contains everything kept."), str(MAX_SECONDS // 60)))
        self.window.currentIndexChanged.connect(self._redraw)
        tools.addWidget(self.window)
        tools.addStretch(1)
        self.export_button = QPushButton("Export CSV…")
        self.export_button.setToolTip(("Saves every kept sample (time, load, clock, temperature, socket "
                                       "power, performance mode, runtime range) as a CSV file."))
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_requested)
        tools.addWidget(self.export_button)
        self.compare_button = QPushButton("Compare…")
        self.compare_button.setToolTip(("Load an earlier CSV export and draw it dashed behind the live "
                                        "lines, newest sample at the right edge, with both sessions' "
                                        "averages below the chart."))
        self.compare_button.clicked.connect(self.compare_requested)
        tools.addWidget(self.compare_button)
        self.clear_compare_button = QPushButton("Clear")
        self.clear_compare_button.setToolTip("Remove the reference session from the chart.")
        self.clear_compare_button.setEnabled(False)
        self.clear_compare_button.clicked.connect(lambda: self.set_reference([], ""))
        tools.addWidget(self.clear_compare_button)
        chart_layout.addLayout(tools)
        self.reference: list[Sample] = []
        self.reference_name = ""
        self._current_note = ""
        self.chart = QChart()
        self.chart.setBackgroundVisible(False)
        self.chart.setMargins(QMargins(4, 4, 4, 4))
        text_colour = self.palette().windowText().color()
        self.chart.legend().setLabelColor(text_colour)
        self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        self.axis_x = QValueAxis()
        self.axis_x.setLabelsVisible(False)
        self.axis_y = QValueAxis()                  # load % and temperature °C share 0..100
        self.axis_y.setRange(0, 100)
        self.axis_y.setLabelFormat("%d")
        self.axis_y.setTitleText("% / °C")
        self.axis_y.setLabelsColor(text_colour)
        self.axis_y.setTitleBrush(text_colour)
        self.axis_clock = QValueAxis()
        self.axis_clock.setRange(0, CLOCK_AXIS_MHZ)
        self.axis_clock.setLabelFormat("%d")
        self.axis_clock.setTitleText("MHz")
        self.axis_clock.setLabelsColor(text_colour)
        self.axis_clock.setTitleBrush(text_colour)
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)
        self.chart.addAxis(self.axis_clock, Qt.AlignmentFlag.AlignRight)
        self.series: dict[str, QLineSeries] = {}
        for key, name, colour, axis in (("load", "Load %", ACCENT, self.axis_y),
                                        ("temp", "Temperature °C", ORANGE, self.axis_y),
                                        ("clock", "Clock MHz", BLUE, self.axis_clock)):
            series = QLineSeries()
            series.setName(name)
            series.setPen(QPen(QColor(colour), 2))
            self.chart.addSeries(series)
            series.attachAxis(self.axis_x)
            series.attachAxis(axis)
            self.series[key] = series
        # Reference lines: same colors, dashed and thinner, under the live ones, hidden until a file is loaded.
        self.ref_series: dict[str, QLineSeries] = {}
        for key, name, colour, axis in (("load", "Load % (ref)", ACCENT, self.axis_y),
                                        ("temp", "Temperature °C (ref)", ORANGE, self.axis_y),
                                        ("clock", "Clock MHz (ref)", BLUE, self.axis_clock)):
            series = QLineSeries()
            series.setName(name)
            pen = QPen(QColor(colour), 1)
            pen.setStyle(Qt.PenStyle.DashLine)
            series.setPen(pen)
            series.setVisible(False)
            self.chart.addSeries(series)
            series.attachAxis(self.axis_x)
            series.attachAxis(axis)
            self.ref_series[key] = series
        view = QChartView(self.chart)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setStyleSheet("background:transparent;")
        view.setMinimumHeight(200)
        chart_layout.addWidget(view)
        self.chart_note = hint_label("")
        chart_layout.addWidget(self.chart_note)
        layout.addWidget(self.chart_box, 1)
        self._redraw()

        self.metrics_box = QGroupBox("gpu_metrics table")
        metrics_grid = QGridLayout(self.metrics_box)
        metrics_grid.setHorizontalSpacing(16)
        metrics_grid.setVerticalSpacing(4)
        self.metric_fields: dict[str, QLabel] = {}
        for index, (key, caption) in enumerate(METRIC_ROWS):
            row, col = divmod(index, 3)
            metrics_grid.addWidget(QLabel(caption + ":"), row, col * 2)
            value = QLabel("—")
            value.setMinimumWidth(90)
            self.metric_fields[key] = value
            metrics_grid.addWidget(value, row, col * 2 + 1)
        metrics_grid.setColumnStretch(6, 1)
        self.metrics_note = hint_label("")
        metrics_grid.addWidget(self.metrics_note, (len(METRIC_ROWS) + 2) // 3, 0, 1, 7)
        layout.addWidget(self.metrics_box)

        layout.addWidget(hint_label(
            "BC-250 usually exposes no gpu_busy_percent sensor, but the governor measures the load itself and "
            "publishes it in its patched gpu_metrics table while fix-metrics is on and the service runs. The app "
            "reads it from there; a missing sensor is shown as N/A, never as 0%."))

    def hide_pills(self, *keys: str) -> None:
        for key in keys:
            self.pills[key].hide()
            self.pill_labels[key].hide()

    def update(self, snap: Snapshot) -> None:
        service = self.pills["service"]
        if not snap.service.installed:
            service.set_status("Not installed", "bad", snap.install.message)
        elif snap.service.active:
            service.set_status("Active", "ok", fmt("SubState: %1", snap.service.sub_state))
        elif snap.service.sub_state == "failed":
            service.set_status("Failed", "bad",
                               "The unit failed; see the Service page for the journal.")
        else:
            service.set_status("Inactive", "warn",
                               fmt("SubState: %1", snap.service.sub_state or "unknown"))
        self.pills["mount"].set_status(
            "Mounted" if snap.mounted else "Not mounted", "ok" if snap.mounted else "warn",
            ("The governor bind-mounts its patched gpu_metrics table over the sysfs file "
             "while fix-metrics is on and the service runs."))
        self.pills["fix"].set_status("Enabled" if snap.saved.fix_metrics else "Disabled",
                                     "ok" if snap.saved.fix_metrics else "warn",
                                     "Value saved in config.toml.")
        t = snap.telemetry
        load = t.load_percent
        if load is None:
            hint = load_sensor_hint(snap)
            self.pills["sensor"].set_status("Unavailable", "warn", hint)
        else:
            self.pills["sensor"].set_status("Available", "ok",
                                            LOAD_SOURCES.get(t.load_source, ""))
        self.history.add(Sample.from_snapshot(snap, datetime.now()))
        self._redraw()
        current = [fmt("load %1%", f"{load:.0f}") if load is not None else "load N/A"]
        if t.clock_mhz is not None:
            current.append(fmt("clock %1 MHz", str(t.clock_mhz)))
        if t.temp_c is not None:
            current.append(fmt("temperature %1 °C", f"{t.temp_c:.0f}"))
        note = fmt("Current: %1", ", ".join(current))
        if load is None:
            note += fmt(". No usable GPU load sensor: %1", load_sensor_hint(snap))
        self._current_note = note
        self._set_note(self.history.last(self.window_seconds() * 1000 // POLL_MS))
        perf = snap.perf
        if perf.available:
            self.pills["bus"].set_status("Reachable", "ok",
                                         "com.cyanskillfish.Governor answers on the system bus.")
            self.pills["perf"].set_status(
                "On" if perf.enabled else "Off", "ok" if perf.enabled else "neutral",
                fmt("Current range %1–%2 MHz", str(perf.current_min or "no limit"),
                    str(perf.current_max or "no limit")))
        else:
            self.pills["bus"].set_status("Unreachable", "warn", perf.error)
            self.pills["perf"].set_status("Unknown", "neutral",
                                          "Needs the governor running with [dbus] enabled.")
        self._update_metrics(snap.telemetry.metrics, snap.telemetry.metrics_patched)

    def window_seconds(self) -> int:
        return int(self.window.currentData())

    def set_reference(self, samples: list[Sample], name: str) -> None:
        """Overlay an earlier session (from `history.read_csv`); an empty list removes it."""
        self.reference = list(samples)
        self.reference_name = name if samples else ""
        self.clear_compare_button.setEnabled(bool(samples))
        for series in self.ref_series.values():
            series.setVisible(bool(samples))
        self._redraw()

    def _redraw(self, *_args) -> None:
        """Show the last window of samples; a missing reading leaves a gap in the line instead of a fake zero."""
        seconds = self.window_seconds()
        points = seconds * 1000 // POLL_MS
        samples = self.history.last(points)
        offset = points - len(samples)            # right-align so the newest sample sits at the right edge
        for key, pick in (("load", lambda s: s.load), ("temp", lambda s: s.temp),
                          ("clock", lambda s: None if s.clock is None else float(s.clock))):
            self.series[key].replace([QPointF(offset + i, v) for i, s in enumerate(samples)
                                      if (v := pick(s)) is not None])
        self.axis_x.setRange(0, points - 1)
        label = next(label for secs, label in CHART_WINDOWS if secs == seconds)
        kept = len(self.history) * POLL_MS // 1000
        self.chart_box.setTitle(fmt("GPU load, clock and temperature, last %1", label)
                                + (fmt(" (%1 min %2 s recorded)", str(kept // 60), str(kept % 60))
                                   if kept else ""))
        self.export_button.setEnabled(len(self.history) > 0)
        if self.reference:
            ref = self.reference[-points:]
            ref_offset = points - len(ref)
            for key, pick in (("load", lambda s: s.load), ("temp", lambda s: s.temp),
                              ("clock", lambda s: None if s.clock is None else float(s.clock))):
                self.ref_series[key].replace([QPointF(ref_offset + i, v) for i, s in enumerate(ref)
                                              if (v := pick(s)) is not None])
        self._set_note(samples)

    def _set_note(self, live: list[Sample]) -> None:
        lines = [self._current_note] if self._current_note else []
        if self.reference:
            whole = summarise(self.reference)
            text = fmt("Reference %1 (%2): %3.", self.reference_name, _minutes(whole.seconds),
                       whole.text())
            if live:
                now = summarise(live)
                text += fmt(" Live window (%1): %2.", _minutes(now.seconds), now.text())
            lines.append(text)
        self.chart_note.setText("\n".join(lines))

    def _update_metrics(self, m: GpuMetrics | None, patched: bool) -> None:
        if m is None:
            for field in self.metric_fields.values():
                field.setText("—")
            self.metrics_note.setText("No readable gpu_metrics v2.x table under /sys/class/drm/card*/device.")
            return
        values = {
            "version": f"v{m.version}" + (" (patched)" if patched else " (raw)"),
            "gfx_activity": (f"{m.gfx_activity_percent:.0f} %" if m.gfx_activity_valid()
                             else _pct(m.gfx_activity, valid=False)),
            "mm_activity": _pct(m.mm_activity, valid=m.mm_activity is not None and m.mm_activity <= 100),
            "temp_gfx": _unit(m.temperature_gfx, "°C"),
            "temp_soc": _unit(m.temperature_soc, "°C"),
            "socket_power": _watts(m.socket_power_w, m.socket_power),
            "gfx_power": _watts(m.gfx_power_w, m.gfx_power),
            "cpu_power": _watts(m.cpu_power_w, m.cpu_power),
            "gfxclk": _unit(m.current_gfxclk, "MHz"),
            "avg_gfxclk": _unit(m.average_gfxclk, "MHz"),
            "socclk": _unit(m.current_socclk, "MHz"),
            "uclk": _unit(m.current_uclk, "MHz"),
            "fclk": _unit(m.current_fclk, "MHz"),
            "throttle": f"0x{m.throttle_status:08x}" if m.throttle_status else "none",
            "cores": _cores(m),
        }
        for key, text in values.items():
            self.metric_fields[key].setText(text)
        if patched:
            self.metrics_note.setText(("Table as published by the governor (fix-metrics): the GFX activity "
                                       "is its own measurement."))
        elif not m.gfx_activity_valid():
            self.metrics_note.setText(("Raw kernel table: the GFX activity is the broken firmware value "
                                       "(the 655% bug); enable fix-metrics to get a real one."))
        else:
            self.metrics_note.setText("Raw kernel table.")


def _minutes(seconds: int) -> str:
    if seconds >= 60:
        return fmt("%1 min %2 s", str(seconds // 60), str(seconds % 60))
    return fmt("%1 s", str(seconds))


def _unit(value: int | None, unit: str) -> str:
    return "—" if value is None else f"{value} {unit}"


def _watts(value: float | None, raw: int | None) -> str:
    if value is None:
        return "—"
    return fmt("%1 W (raw %2)", f"{value:.1f}", str(raw))


def _pct(value: int | None, *, valid: bool) -> str:
    if value is None:
        return "—"
    if valid:
        return f"{value} %"
    return fmt("%1 % (invalid)", str(value))


def _cores(m: GpuMetrics) -> str:
    clocks = [c for c in m.current_coreclk if c]
    temps = [t for t in m.temperature_core if t is not None]
    if not clocks and not temps:
        return "—"
    parts = []
    if clocks:
        parts.append(fmt("%1× %2–%3 MHz", str(len(clocks)),
                          str(min(clocks)), str(max(clocks))))
    if temps:
        parts.append(fmt("%1 °C max", str(max(temps))))
    return ", ".join(parts)


class ServicePage(QWidget):
    action_requested = pyqtSignal(str)      # start, stop, restart, enable, disable
    refresh_requested = pyqtSignal()
    export_requested = pyqtSignal()
    update_check_requested = pyqtSignal()

    def __init__(self, service_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        header, _ = page_header("Service")
        self.update_button = QPushButton("Check for updates")
        self.update_button.setToolTip("Compare the installed RPM with the latest release on GitHub.")
        self.update_button.clicked.connect(self.update_check_requested)
        header.addWidget(self.update_button)
        export = QPushButton("Export diagnostics…")
        export.setToolTip(("Save versions, config.toml, service status, journal and the raw gpu_metrics "
                           "table to a text file for a bug report."))
        export.clicked.connect(self.export_requested)
        header.addWidget(export)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_requested)
        header.addWidget(refresh)
        layout.addLayout(header)

        box = QGroupBox(service_name)
        grid = QGridLayout(box)
        grid.setHorizontalSpacing(16)
        self.fields: dict[str, QLabel] = {}
        self.field_labels: dict[str, QLabel] = {}
        for row, (key, caption) in enumerate((("installed", "Unit found"), ("active", "Active"),
                                              ("enabled", "Enabled at boot"),
                                              ("mount", "gpu_metrics override"),
                                              ("version", "Version"))):
            self.field_labels[key] = QLabel(caption + ":")
            grid.addWidget(self.field_labels[key], row, 0)
            value = QLabel("—")
            value.setOpenExternalLinks(True)
            self.fields[key] = value
            grid.addWidget(value, row, 1)
        grid.setColumnStretch(2, 1)

        buttons = QVBoxLayout()
        self.buttons: dict[str, QPushButton] = {}
        for action, caption, tip in (("start", "Start", "systemctl start"),
                                     ("stop", "Stop", "systemctl stop"),
                                     ("restart", "Restart",
                                      "systemctl restart: needed after editing config.toml"),
                                     ("enable", "Enable at boot", "systemctl enable"),
                                     ("disable", "Disable at boot", "systemctl disable")):
            button = QPushButton(caption)
            button.setToolTip(fmt("%1 %2 (asks for your password).", tip, service_name))
            button.clicked.connect(lambda _=False, a=action: self.action_requested.emit(a))
            self.buttons[action] = button
            buttons.addWidget(button)
        grid.addLayout(buttons, 0, 3, 5, 1)
        layout.addWidget(box)

        status_box = QGroupBox("systemctl status")
        status_layout = QVBoxLayout(status_box)
        self.status = Terminal()
        status_layout.addWidget(self.status)
        layout.addWidget(status_box, 1)

        journal_box = QGroupBox("Journal (live)")
        journal_layout = QVBoxLayout(journal_box)
        self.journal = JournalView(service_name)
        journal_layout.addWidget(self.journal)
        layout.addWidget(journal_box, 2)

    def hide_fields(self, *keys: str) -> None:
        for key in keys:
            self.fields[key].hide()
            self.field_labels[key].hide()

    def update(self, snap: Snapshot) -> None:
        s = snap.service
        self.fields["installed"].setText("Yes" if s.installed
                                         else fmt("No — %1", snap.install.message))
        self.fields["active"].setText(fmt("Yes (%1)", s.sub_state) if s.active
                                      else fmt("No (%1)", s.sub_state or "not loaded"))
        self.fields["enabled"].setText(fmt("Yes (%1)", s.unit_file_state) if s.enabled
                                       else fmt("No (%1)", s.unit_file_state or "—"))
        self.fields["mount"].setText("Yes" if snap.mounted else "No")
        for action, button in self.buttons.items():
            button.setEnabled(s.installed)
        if s.installed:
            self.buttons["start"].setEnabled(not s.active)
            self.buttons["stop"].setEnabled(s.active)
            self.buttons["enable"].setEnabled(not s.enabled)
            self.buttons["disable"].setEnabled(s.enabled)
        self.status.set_text(s.raw or snap.install.message)

    def show_update(self, result) -> None:
        """Result of the update check (update_check.UpdateResult)."""
        self.update_button.setEnabled(True)
        self.update_button.setText("Check for updates")
        text = result.summary
        if result.update_available:
            text = (f'<b style="color:{ORANGE};">{text}</b> — '
                    f'<a href="{result.latest_url}">{"release notes"}</a>')
        elif result.latest:
            text += f' — <a href="{result.latest_url}">{"releases"}</a>'
        self.fields["version"].setText(text)
        self.fields["version"].setToolTip(result.installed_full or "Package not installed")

    def checking_update(self) -> None:
        self.update_button.setEnabled(False)
        self.update_button.setText("Checking…")
