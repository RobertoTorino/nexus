# SPDX-License-Identifier: GPL-3.0-or-later
"""Performance benchmark (test 42): settings, baseline, scores and run history.

The script measures CPU single/multi-thread (stress-ng matrixprod) and GPU FP32 compute (vkpeak) and
prints one machine-readable line, "BENCH: key=value ...". Scores are 100 x result / baseline, where the
baseline is a run on a stock BC-250 (6C/12T, 24 CUs) saved as bench-baseline.json next to the script.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import window_title

BASELINE_NAME = "bench-baseline.json"
# The script keeps one baseline for every copy of itself in its root-owned log folder.
BASELINE_PATH = Path("/var/log/bc250-bazzite-test") / BASELINE_NAME
HISTORY_NAME = "bc250-bench-history.csv"
# The script writes the history as root to /var/log (world-readable) and copies it to the Desktop.
HISTORY_CANDIDATES = [
    Path("/var/log/bc250-bazzite-test") / HISTORY_NAME,
    Path.home() / "Desktop" / "bc250-bazzite-test" / HISTORY_NAME,
]


def parse_bench_line(body: str) -> dict[str, str] | None:
    """The key=value pairs of a "BENCH: ..." line (empty values dropped), or None."""
    if not body.startswith("BENCH: "):
        return None
    pairs = (kv.split("=", 1) for kv in body[7:].split() if "=" in kv)
    return {k: v for k, v in pairs if v}


def _num(value: object) -> float | None:
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def score(value: object, base: object) -> int | None:
    v, b = _num(value), _num(base)
    return round(100 * v / b) if v and b else None


def load_baseline(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def describe_baseline(base: dict | None) -> str:
    if not base:
        return ("No baseline yet. Put the board in its stock configuration (24 CUs, 6C/12T, governor "
                "max 1850 MHz), tick \"Save as baseline\" and run the benchmark once.")
    return (f"Baseline (= 100): {base.get('cores', '?')}C/{base.get('threads', '?')}T, {base.get('cus', '?')} CUs, "
            f"~{base.get('gpu_mhz', '?')} MHz, measured {base.get('date', '?')}. "
            f"CPU {base.get('cpu_multi', '?')} ops/s, GPU {base.get('gpu_fp32', '?')} GFLOPS.")


def load_history() -> list[dict[str, str]]:
    for path in HISTORY_CANDIDATES:
        try:
            with path.open(newline="", encoding="utf-8") as fh:
                return list(csv.DictReader(fh))
        except OSError:
            continue
    return []


def scores_for(result: dict, base: dict | None) -> tuple[int | None, int | None, int | None]:
    """(CPU multi-thread, CPU single-thread, GPU) scores against base; falls back to the scores the
    script stored when there is no baseline file here."""
    if base:
        return (score(result.get("cpu_multi"), base.get("cpu_multi")),
                score(result.get("cpu_single"), base.get("cpu_single")),
                score(result.get("gpu_fp32"), base.get("gpu_fp32")))
    as_int = lambda k: round(_num(result.get(k))) if _num(result.get(k)) else None  # noqa: E731
    return as_int("cpu_score"), as_int("cpu1_score"), as_int("gpu_score")


class BenchSettings(QObject):
    changed = pyqtSignal()

    def __init__(self, baseline_path: Path, legacy_path: Path | None = None) -> None:
        super().__init__()
        self.baseline_path = baseline_path
        # Older script versions saved the baseline next to the script; the next benchmark run moves it.
        self.legacy_path = legacy_path
        self.seconds = 20
        self.save_baseline = False

    def baseline(self) -> dict | None:
        base = load_baseline(self.baseline_path)
        if base is None and self.legacy_path is not None:
            base = load_baseline(self.legacy_path)
        return base

    def set(self, **kw) -> None:
        for k, v in kw.items():
            setattr(self, k, v)
        self.changed.emit()


class BenchControls(QWidget):
    def __init__(self, settings: BenchSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)

        row = QHBoxLayout()
        row.addWidget(QLabel("CPU time per phase (s):"))
        self.seconds = QSpinBox()
        self.seconds.setRange(5, 300)
        self.seconds.setSingleStep(5)
        self.seconds.setValue(settings.seconds)
        self.seconds.setToolTip("stress-ng runs this long on 1 thread and again on all threads. "
                                "Keep it the same between runs you want to compare.")
        self.seconds.valueChanged.connect(lambda v: settings.set(seconds=v))
        row.addWidget(self.seconds)
        self.save = QCheckBox("Save as baseline (stock board only)")
        self.save.setToolTip(f"Writes the result to {settings.baseline_path}; later runs score against it.")
        self.save.toggled.connect(lambda v: settings.set(save_baseline=v))
        row.addWidget(self.save)
        row.addStretch(1)
        history = QPushButton("Benchmark history")
        history.clicked.connect(lambda: BenchHistoryDialog(settings.baseline(), self).exec())
        row.addWidget(history)
        graph = QPushButton("Show graph")
        graph.setToolTip("Bar charts of every benchmark run, to compare CU/core unlocks side by side.")
        graph.clicked.connect(self._show_graph)
        row.addWidget(graph)
        calc = QPushButton("Open CSV")
        calc.setToolTip("Open the benchmark history CSV in LibreOffice Calc.")
        calc.clicked.connect(self._open_csv)
        row.addWidget(calc)
        col.addLayout(row)

        self.baseline = QLabel()
        self.baseline.setWordWrap(True)
        self.baseline.setStyleSheet("color:#9aa0a6;")
        col.addWidget(self.baseline)
        self.refresh()

    def _show_graph(self) -> None:
        from .graph import history_csv, show_graph
        show_graph(self, history_csv(), None, "No benchmark history yet. Run the benchmark (42) first.")

    def _open_csv(self) -> None:
        from .graph import history_csv, open_in_calc
        open_in_calc(self, history_csv(), "No benchmark history yet. Run the benchmark (42) first.")

    def refresh(self) -> None:
        self.baseline.setText(describe_baseline(self.settings.baseline()))
        has_base = self.settings.baseline() is not None
        self.save.blockSignals(True)
        if has_base and self.settings.save_baseline:
            self.settings.save_baseline = False
        self.save.setEnabled(not has_base)
        self.save.setChecked(self.settings.save_baseline)
        self.save.setToolTip(
            f"A baseline already exists ({self.settings.baseline_path}); delete that file to save a new one."
            if has_base else
            f"Writes the result to {self.settings.baseline_path}; later runs score against it.")
        self.save.blockSignals(False)


class BenchHistoryDialog(QDialog):
    COLUMNS = [
        ("Date", "date"), ("Cores/threads", None), ("CUs", "cus"), ("GPU MHz", "gpu_mhz"),
        ("CPU 1T ops/s", "cpu_single"), ("CPU MT ops/s", "cpu_multi"), ("GPU GFLOPS", "gpu_fp32"),
        ("VRAM GB/s", "gpu_copy_gbps"), ("CPU score", None), ("CPU 1T score", None), ("GPU score", None),
        ("Mitigations", "mitigations"), ("Kernel", "kernel"),
    ]

    def __init__(self, base: dict | None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(window_title("benchmark history"))
        self.resize(1150, 480)
        layout = QVBoxLayout(self)
        info = QLabel(describe_baseline(base) + "<br>Scores are recalculated against the current baseline.")
        info.setWordWrap(True)
        layout.addWidget(info)

        rows = list(reversed(load_history()))
        table = QTableWidget(len(rows), len(self.COLUMNS))
        table.setHorizontalHeaderLabels([c[0] for c in self.COLUMNS])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        for r, row in enumerate(rows):
            cpu, cpu1, gpu = scores_for(row, base)
            computed = {"Cores/threads": f"{row.get('cores', '?')}C/{row.get('threads', '?')}T",
                        "CPU score": cpu, "CPU 1T score": cpu1, "GPU score": gpu}
            for c, (title, key) in enumerate(self.COLUMNS):
                value = row.get(key, "") if key else computed[title]
                table.setItem(r, c, QTableWidgetItem("" if value is None else str(value)))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table, 1)
        if not rows:
            layout.addWidget(QLabel("No benchmark runs found in: " + ", ".join(map(str, HISTORY_CANDIDATES))))

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
