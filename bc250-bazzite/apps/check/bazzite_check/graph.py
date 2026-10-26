# SPDX-License-Identifier: GPL-3.0-or-later
"""Graph window for the CSV files the script writes (stress telemetry, benchmark history, or any CSV)."""

from __future__ import annotations

import csv
import html
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QPointF, QProcess, Qt, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QPainter
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from . import plain_tooltip, window_title
from .widgets import hide_tooltip, show_tooltip

try:
    from PyQt6.QtCharts import (
        QAbstractBarSeries, QBarCategoryAxis, QBarSet, QBarSeries, QChart, QChartView, QLineSeries, QValueAxis,
    )
    CHARTS_AVAILABLE = True
except ImportError:          # PyQt6-Charts is a separate wheel; the rest of the app works without it
    CHARTS_AVAILABLE = False

SCRIPT_LOG_DIR = Path("/var/log/bc250-bazzite-test")
DESKTOP_DIR = Path.home() / "Desktop" / "bc250-bazzite-test"
STRESS_GLOB = "bc250-stress-*.csv"
HISTORY_NAME = "bc250-bench-history.csv"
SPEEDTEST_HISTORY_NAME = "bc250-speedtest-history.csv"
# Set by the main window: loads the benchmark baseline (bench.BenchSettings.baseline). Scores in the benchmark history graph are
# recomputed against it, so runs made before the baseline existed get a score too.
BENCH_BASELINE: Callable[[], dict | None] | None = None

COLORS = ["#1565c0", "#c62828", "#2e7d32", "#ef6c00", "#6a1b9a", "#00838f", "#5d4037"]

# Stress telemetry: (panel title, unit, [(column, label)]).
STRESS_PANELS = [
    ("Clocks", "MHz", [("sclk_mhz", "GPU core"), ("mclk_mhz", "GPU memory"), ("cpu_mhz_avg", "CPU average")]),
    ("Temperatures", "°C", [("gpu_temp_c", "GPU"), ("cpu_tctl_c", "CPU (Tctl)")]),
    ("GPU busy", "%", [("gpu_busy_pct", "GPU busy")]),
    ("GPU power", "W", [("gpu_power_w", "GPU power")]),
    ("GPU memory", "MiB", [("vram_used_mib", "VRAM used"), ("gtt_used_mib", "GTT used")]),
    ("Fan", "RPM", [("fan_rpm", "Fan")]),
    ("GPU voltage", "mV", [("vddgfx_mv", "VDDGFX")]),
    ("CPU load average", "", [("load1", "1-minute load")]),
]
DISK_PANELS = [
    ("Write speed", "MB/s", [("write_mbps", "Write speed")]),
    ("Drive temperature", "°C", [("drive_temp_c", "Drive")]),
]
# In-game monitoring CSVs written by gamemon. Panels whose columns are missing (sessions recorded by
# an older version) are dropped silently by _line_chart.
GAME_PANELS = [
    ("FPS", "", [("fps", "FPS (MangoHud)")]),
    ("Game load", "%", [("game_cpu_pct", "Game CPU"), ("game_gpu_pct", "Game GPU")]),
    ("Total load", "%", [("cpu_pct", "CPU"), ("gpu_pct", "GPU")]),
    ("Clocks", "MHz", [("sclk_mhz", "GPU core"), ("mclk_mhz", "GPU memory"),
                       ("cpu_mhz_avg", "CPU average")]),
    ("Temperatures", "°C", [("gpu_temp_c", "GPU"), ("cpu_temp_c", "CPU (Tctl)")]),
    ("GPU power", "W", [("gpu_power_w", "GPU power")]),
    ("GPU memory", "MiB", [("vram_used_mib", "VRAM used"), ("gtt_used_mib", "GTT used")]),
    ("System memory free", "MiB", [("mem_avail_mib", "MemAvailable")]),
    ("Fan", "RPM", [("fan_rpm", "Fan")]),
    ("GPU voltage", "mV", [("vddgfx_mv", "VDDGFX")]),
]
HISTORY_PANELS = [
    ("Score vs stock baseline", "%", [("cpu_score", "CPU multi"), ("cpu1_score", "CPU single"),
                                      ("gpu_score", "GPU")]),
    ("GPU FP32 compute", "GFLOPS", [("gpu_fp32", "GPU FP32")]),
    ("CPU multi-thread", "ops/s", [("cpu_multi", "Multi-thread")]),
    ("CPU single-thread", "ops/s", [("cpu_single", "Single-thread")]),
    ("VRAM copy bandwidth", "GB/s", [("gpu_copy_gbps", "VRAM copy")]),
    ("GPU clock under load", "MHz", [("gpu_mhz", "GPU clock")]),
]

SPEEDTEST_PANELS = [
    ("Download and upload", "Mbps", [("down_mbps", "Download"), ("up_mbps", "Upload")]),
    ("Latency idle vs loaded", "ms", [("ping_ms", "Idle"), ("down_latency_ms", "While downloading"),
                                      ("up_latency_ms", "While uploading")]),
    ("Jitter", "ms", [("jitter_ms", "Jitter")]),
    ("Packet loss", "%", [("packet_loss_pct", "Packet loss")]),
]


def _bench_label(i: int, r: dict[str, str]) -> str:
    return html.escape(f"#{i} {r.get('cus', '?')}CU {r.get('threads', '?')}T")


def _bench_tip(r: dict[str, str]) -> str:
    return (f"{r.get('date', '')}\n{r.get('cus', '?')} CUs, {r.get('cores', '?')} cores / "
            f"{r.get('threads', '?')} threads\nmitigations {r.get('mitigations', '?')}, kernel {r.get('kernel', '?')}")


def _speedtest_label(i: int, r: dict[str, str]) -> str:
    d = r.get("date", "")
    return f"#{i} {html.escape(d[8:10])}-{html.escape(d[5:7])}<br>{html.escape(d[11:16])}"


def _speedtest_tip(r: dict[str, str]) -> str:
    link = f", link {r['link_mbps']} Mbit/s" if r.get("link_mbps") else ""
    return (f"{r.get('date', '')}\n{r.get('iface', '?')}{link}\n"
            f"{r.get('server', '?')} ({r.get('isp', '?')})")


def find_csvs(pattern: str) -> list[Path]:
    """Matching CSVs from the Desktop copy and the script's log dir, newest first, one per file name.

    The Desktop copy wins: it belongs to the user, while /var/log/bc250-bazzite-test is root's and
    invisible to sandboxed (Flatpak) applications such as LibreOffice.
    """
    found: dict[str, Path] = {}
    for d in (DESKTOP_DIR, SCRIPT_LOG_DIR):
        try:
            for p in d.glob(pattern):
                found.setdefault(p.name, p)
        except OSError:
            continue
    return sorted(found.values(), key=lambda p: p.name, reverse=True)


def latest_stress_csv() -> Path | None:
    files = find_csvs(STRESS_GLOB)
    return files[0] if files else None


def history_csv() -> Path | None:
    files = find_csvs(HISTORY_NAME)
    return files[0] if files else None


def _float(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        rows = [r for r in reader]
        return list(reader.fieldnames or []), rows


class GraphDialog(QDialog):
    def __init__(self, path: Path, siblings: list[Path] | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.resize(1150, 780)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.picker = QComboBox()
        self.picker.setMinimumWidth(420)
        file_label = QLabel("File:")
        top.addWidget(file_label)
        top.addWidget(self.picker)
        top.addStretch(1)
        save = QPushButton("Save as PNG…")
        save.clicked.connect(self._save_png)
        top.addWidget(save)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        top.addWidget(close)
        layout.addLayout(top)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary)
        hint = QLabel("Drag to zoom in, right-click to zoom out, hover a line for its values.")
        hint.setStyleSheet("color:#9aa0a6;")
        layout.addWidget(hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll, 1)

        files = siblings or [path]
        if path not in files:
            files = [path, *files]
        for f in files:
            self.picker.addItem(f.name, str(f))
        self.picker.setCurrentIndex(files.index(path))
        self.picker.currentIndexChanged.connect(lambda _i: self.load(Path(self.picker.currentData())))
        self.picker.setVisible(len(files) > 1)
        file_label.setVisible(len(files) > 1)
        self.load(path)

    # ---------------------------------------------------------------- build
    def load(self, path: Path) -> None:
        self.setWindowTitle(window_title(path.name))
        try:
            cols, rows = read_csv(path)
        except OSError as exc:
            self.summary.setText(html.escape(f"Could not read {path}: {exc}"))
            self.scroll.setWidget(QWidget())
            return
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        self._charts: list[QChartView] = []
        if "write_mbps" in cols and "written_gib" in cols:
            self.summary.setText(self._disk_summary(path, rows))
            views = [self._line_chart(t, u, s, rows, "written_gib", "Written (GiB)") for t, u, s in DISK_PANELS]
        elif "fps" in cols and "game_cpu_pct" in cols:
            self.summary.setText(self._game_summary(path, rows))
            views = [self._line_chart(t, u, s, rows, "elapsed_s", "Time (s)") for t, u, s in GAME_PANELS]
        elif "elapsed_s" in cols:
            self.summary.setText(self._stress_summary(path, rows))
            views = [self._line_chart(t, u, s, rows, "elapsed_s", "Time (s)") for t, u, s in STRESS_PANELS]
        elif "gpu_fp32" in cols and "date" in cols:
            note = self._rescore(rows)
            self.summary.setText(f"<b>{html.escape(path.name)}</b>: {len(rows)} benchmark run(s), oldest first. {note}")
            views = [self._bar_chart(t, u, s, rows) for t, u, s in HISTORY_PANELS]
        elif "down_mbps" in cols and "date" in cols:
            self.summary.setText(f"<b>{html.escape(path.name)}</b>: {len(rows)} speed test run(s), oldest first. "
                                 "Loaded latency far above idle latency means bufferbloat.")
            views = [self._bar_chart(t, u, s, rows, _speedtest_label, _speedtest_tip, "%.1f")
                     for t, u, s in SPEEDTEST_PANELS]
        else:
            numeric = [c for c in cols if any(_float(r.get(c)) is not None for r in rows)]
            x = numeric[0] if numeric else None
            self.summary.setText(f"<b>{html.escape(path.name)}</b>: {len(rows)} rows, x axis: {html.escape(x or 'row number')}.")
            # Column names come from the file and chart titles render HTML, so escape them for display.
            views = [self._line_chart(html.escape(c), "", [(c, html.escape(c))], rows, x, html.escape(x or "Row"))
                     for c in numeric[1:] or numeric]
        views = [v for v in views if v is not None]
        for i, view in enumerate(views):
            grid.addWidget(view, i // 2, i % 2)
        if not views:
            grid.addWidget(QLabel("No numeric data to plot in this file."), 0, 0)
        self._charts = views
        self.scroll.setWidget(grid_host)

    @staticmethod
    def _rescore(rows: list[dict[str, str]]) -> str:
        from .bench import scores_for
        base = BENCH_BASELINE() if BENCH_BASELINE else None
        if not base:
            return "Scores as stored by the script (no bench-baseline.json found)."
        for r in rows:
            cpu, cpu1, gpu = scores_for(r, base)
            r["cpu_score"], r["cpu1_score"], r["gpu_score"] = (str(v) if v else "" for v in (cpu, cpu1, gpu))
        return html.escape(f"Scores against the baseline of {base.get('date', '?')} ({base.get('cus', '?')} CUs, "
                           f"{base.get('cores', '?')}C/{base.get('threads', '?')}T) = 100.")

    @staticmethod
    def _game_summary(path: Path, rows: list[dict[str, str]]) -> str:
        from .gamecheck import load_summary
        def stats(col: str) -> tuple[float, float] | None:
            vals = [v for r in rows if (v := _float(r.get(col))) is not None]
            return (sum(vals) / len(vals), max(vals)) if vals else None
        dur = _float(rows[-1].get("elapsed_s")) if rows else None
        parts = []
        ft = load_summary(path).get("frametime")
        if isinstance(ft, dict) and ft.get("avg_fps"):
            # Per-frame data beats the sampled averages: these are the lows players actually feel.
            parts.append(f"FPS avg {ft['avg_fps']:.0f}, 1% low {ft['low1_fps']:.0f}, "
                         f"0.1% low {ft['low01_fps']:.0f}, stutter {ft['stutter_pct']:.1f}%")
        elif f := stats("fps"):
            parts.append(f"FPS avg {f[0]:.0f}")
        for col, label in (("game_gpu_pct", "game GPU"), ("game_cpu_pct", "game CPU")):
            if v := stats(col):
                parts.append(f"{label} avg {v[0]:.0f}%")
        for col, label, unit in (("gpu_temp_c", "GPU", " °C"), ("cpu_temp_c", "CPU", " °C"),
                                 ("gpu_power_w", "GPU power", " W"), ("sclk_mhz", "GPU clock", " MHz"),
                                 ("vram_used_mib", "VRAM", " MiB"), ("gtt_used_mib", "GTT", " MiB")):
            if v := stats(col):
                parts.append(f"{label} peak {v[1]:.0f}{unit}")
        detail = ". " + ", ".join(parts) + "." if parts else ""
        return (f"<b>{html.escape(path.name)}</b>: {len(rows)} samples over {dur or 0:.0f} s of gameplay"
                + html.escape(detail))

    @staticmethod
    def _stress_summary(path: Path, rows: list[dict[str, str]]) -> str:
        def peak(col: str) -> str:
            vals = [v for r in rows if (v := _float(r.get(col))) is not None]
            return f"{max(vals):.0f}" if vals else "—"
        dur = _float(rows[-1].get("elapsed_s")) if rows else None
        return (f"<b>{html.escape(path.name)}</b>: {len(rows)} samples over {dur or 0:.0f} s. Peaks: GPU clock {peak('sclk_mhz')} MHz, "
                f"GPU {peak('gpu_temp_c')} °C, CPU {peak('cpu_tctl_c')} °C, GPU power {peak('gpu_power_w')} W, "
                f"GPU busy {peak('gpu_busy_pct')}%, fan {peak('fan_rpm')} RPM.")

    @staticmethod
    def _disk_summary(path: Path, rows: list[dict[str, str]]) -> str:
        speeds = [v for r in rows if (v := _float(r.get("write_mbps"))) is not None]
        if not speeds:
            return f"<b>{html.escape(path.name)}</b>: no samples."
        q = max(1, len(speeds) // 4)
        burst = sum(speeds[1:1 + q] or speeds[:1]) / len(speeds[1:1 + q] or speeds[:1])
        end = sum(speeds[-q:]) / q
        temps = [v for r in rows if (v := _float(r.get("drive_temp_c"))) is not None]
        written = _float(rows[-1].get("written_gib")) or 0
        text = (f"<b>{html.escape(path.name)}</b>: {written:.0f} GiB written. Start {burst:.0f} MB/s, end {end:.0f} MB/s"
                f"{f', peak drive temperature {max(temps):.0f} °C' if temps else ''}.")
        if end < 0.6 * burst:
            text += " The drop is where the SLC cache ran out (or the drive throttled, if the temperature peaks there)."
        return text

    def _view(self, chart: "QChart") -> "QChartView":
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        chart.layout().setContentsMargins(0, 0, 0, 0)
        view = QChartView(chart)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setRubberBand(QChartView.RubberBand.RectangleRubberBand)
        view.setMinimumHeight(280)
        return view

    def _line_chart(self, title, unit, series_def, rows, xcol, xlabel):
        chart = QChart()
        chart.setTitle(f"{title} ({unit})" if unit else title)
        lo, hi, xmax = None, None, 0.0
        for i, (col, label) in enumerate(series_def):
            s = QLineSeries()
            s.setName(label)
            pen = s.pen()
            pen.setColor(QColor(COLORS[i % len(COLORS)]))
            pen.setWidthF(2.0)
            s.setPen(pen)
            for n, r in enumerate(rows):
                y = _float(r.get(col))
                x = _float(r.get(xcol)) if xcol else float(n)
                if y is None or x is None:
                    continue
                s.append(QPointF(x, y))
                lo = y if lo is None else min(lo, y)
                hi = y if hi is None else max(hi, y)
                xmax = max(xmax, x)
            if s.count():
                s.hovered.connect(lambda p, on, name=label, u=unit:
                                  show_tooltip(self.cursor().pos(),
                                               plain_tooltip(f"{name}: {p.y():.1f} {u}\nx = {p.x():.0f}"), self)
                                  if on else hide_tooltip())
                chart.addSeries(s)
        if not chart.series():
            return None
        ax, ay = QValueAxis(), QValueAxis()
        ax.setTitleText(xlabel)
        ax.setLabelFormat("%.0f")
        ax.setRange(0, xmax or 1)
        pad = max(1.0, (hi - lo) * 0.1)
        ay.setRange(max(0.0, lo - pad) if lo >= 0 else lo - pad, hi + pad)
        ay.setLabelFormat("%.0f")
        ax.applyNiceNumbers()
        ay.applyNiceNumbers()
        chart.addAxis(ax, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(ay, Qt.AlignmentFlag.AlignLeft)
        for s in chart.series():
            s.attachAxis(ax)
            s.attachAxis(ay)
        if len(series_def) == 1:
            chart.legend().hide()
        return self._view(chart)

    def _bar_chart(self, title, unit, series_def, rows, cat_label=_bench_label, tip_text=_bench_tip, fmt="%.0f"):
        chart = QChart()
        chart.setTitle(f"{title} ({unit})")
        series = QBarSeries()
        hi = 0.0
        for i, (col, label) in enumerate(series_def):
            bars = QBarSet(label)
            bars.setColor(QColor(COLORS[i % len(COLORS)]))
            vals = [_float(r.get(col)) or 0.0 for r in rows]
            if not any(vals) and col != "packet_loss_pct":
                continue
            bars.append(vals)
            hi = max(hi, *vals)
            series.append(bars)
        if not series.count():
            return None
        def tip(on: bool, idx: int, bars: "QBarSet", u=unit) -> None:
            if on and 0 <= idx < len(rows):
                r = rows[idx]
                show_tooltip(self.cursor().pos(), plain_tooltip(
                    f"{bars.label()}: {bars.at(idx):.{2 if fmt != '%.0f' else 0}f} {u}\n{tip_text(r)}"), self)
            else:
                hide_tooltip()
        series.hovered.connect(tip)
        series.setLabelsVisible(True)
        series.setLabelsFormat("@value")
        if fmt != "%.0f":
            # Many small bars side by side: 3 significant digits above the bar instead of inside it.
            series.setLabelsPrecision(3)
            series.setLabelsPosition(QAbstractBarSeries.LabelsPosition.LabelsOutsideEnd)
            for b in series.barSets():
                b.setLabelColor(QColor("#333333"))
        chart.addSeries(series)
        cats = QBarCategoryAxis()
        cats.append([cat_label(i, r) for i, r in enumerate(rows, 1)])
        cats.setTruncateLabels(False)
        ay = QValueAxis()
        ay.setRange(0, hi * 1.15 or 1)
        ay.setLabelFormat(fmt)
        ay.applyNiceNumbers()
        chart.addAxis(cats, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(ay, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(cats)
        series.attachAxis(ay)
        if series.count() == 1:
            chart.legend().hide()
        return self._view(chart)

    def _save_png(self) -> None:
        name = Path(self.picker.currentData() or "graph").stem + ".png"
        target, _ = QFileDialog.getSaveFileName(self, "Save graph", str(Path.home() / name), "PNG image (*.png)")
        if target:
            self.scroll.widget().grab().save(target)


def show_graph(parent: QWidget, path: Path | None, siblings: list[Path] | None = None,
               missing: str = "No CSV file found yet.") -> None:
    if not CHARTS_AVAILABLE:
        QMessageBox.information(parent, "Show graph",
                                "Graphs are not available: this installation lacks the Qt Charts module.\n\n"
                                "Reinstall or update the app to get them back.")
        return
    if path is None:
        QMessageBox.information(parent, "Show graph", missing)
        return
    GraphDialog(path, siblings, parent).exec()


def _user_readable(parent: QWidget, path: Path) -> Path | None:
    """A copy of path that user applications (including Flatpaks) can open.

    Files in /var/log/bc250-bazzite-test belong to root and are not visible inside a Flatpak sandbox
    (LibreOffice would report that the file does not exist), so the user's Desktop copy is preferred;
    without one the file is copied to ~/.local/share/bc250-bazzite-test/export/ first.
    """
    if not path.is_relative_to(SCRIPT_LOG_DIR):
        return path
    desktop = DESKTOP_DIR / path.name
    if desktop.is_file():
        return desktop
    from .logstore import log_dir
    export = log_dir().parent / "export"
    try:
        export.mkdir(parents=True, exist_ok=True)
        copy = export / path.name
        shutil.copyfile(path, copy)
        return copy
    except OSError:
        QMessageBox.information(
            parent, "Open in Calc",
            f"No permission to read {path} (it belongs to root).\n\n"
            "Turn on Settings > General > \"Copy the full reports to Desktop\" so the next run leaves "
            f"a readable copy, or copy it yourself:\nsudo cp {path} ~/ && sudo chown $USER ~/{path.name}")
        return None


def open_in_calc(parent: QWidget, path: Path | None, missing: str = "No CSV file found yet.") -> None:
    """Open a CSV in LibreOffice Calc; falls back to the system's default application for the file."""
    if path is None:
        QMessageBox.information(parent, "Open in Calc", missing)
        return
    path = _user_readable(parent, path)
    if path is None:
        return
    for cmd in (["localc"], ["libreoffice", "--calc"], ["soffice", "--calc"], ["flatpak", "run",
                "org.libreoffice.LibreOffice", "--calc"]):
        if not shutil.which(cmd[0]):
            continue
        if cmd[0] == "flatpak":
            # flatpak run starts fine even when LibreOffice is not installed; check first.
            try:
                installed = subprocess.run(["flatpak", "info", "org.libreoffice.LibreOffice"],
                                           capture_output=True, timeout=10).returncode == 0
            except OSError:
                installed = False
            if not installed:
                continue
        if QProcess.startDetached(cmd[0], cmd[1:] + [str(path)]):
            return
    if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
        QMessageBox.information(parent, "Open in Calc",
                                "LibreOffice Calc was not found and no other application is set up "
                                f"for CSV files.\n\nOpen the file yourself: {path}")
