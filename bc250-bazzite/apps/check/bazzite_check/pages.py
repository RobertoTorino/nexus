# SPDX-License-Identifier: GPL-3.0-or-later
"""Overview and per-category pages."""

from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, QSplitter,
    QVBoxLayout, QWidget,
)

from .bench import BenchControls, BenchSettings
from .disk import DiskControls, DiskSettings
from .speedtest import SpeedtestControls
from .graph import STRESS_GLOB, find_csvs, show_graph
from .catalog import BENCH_TEST_ID, DISK_TEST_ID, SPEEDTEST_TEST_ID, STRESS_TEST_ID, Category
from .widgets import HintsPanel, Terminal, TestButton


class StressSettings(QObject):
    """Shared stress options, so every page that shows them stays in sync."""

    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.include_in_run_all = False
        self.duration = 120
        self.interval = 2

    def set(self, **kw) -> None:
        for k, v in kw.items():
            setattr(self, k, v)
        self.changed.emit()


class StressControls(QWidget):
    def __init__(self, settings: StressSettings, show_include: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)

        self.include = QCheckBox("Include stress test (41) in run")
        self.include.setVisible(show_include)
        self.include.toggled.connect(lambda v: settings.set(include_in_run_all=v))
        row.addWidget(self.include)

        row.addWidget(QLabel("Stress duration (s):"))
        self.duration = QSpinBox()
        self.duration.setRange(10, 3600)
        self.duration.setSingleStep(30)
        self.duration.valueChanged.connect(lambda v: settings.set(duration=v))
        row.addWidget(self.duration)

        row.addWidget(QLabel("Sample interval (s):"))
        self.interval = QSpinBox()
        self.interval.setRange(1, 60)
        self.interval.valueChanged.connect(lambda v: settings.set(interval=v))
        row.addWidget(self.interval)
        row.addStretch(1)

        graph = QPushButton("Show graph")
        graph.setToolTip("Plot the telemetry CSV of the latest stress run (older runs can be picked in the window).")
        graph.clicked.connect(self._show_graph)
        row.addWidget(graph)
        calc = QPushButton("Open CSV")
        calc.setToolTip("Open the telemetry CSV of the latest stress run in LibreOffice Calc.")
        calc.clicked.connect(self._open_csv)
        row.addWidget(calc)

        settings.changed.connect(self._sync)
        self._sync()

    def _show_graph(self) -> None:
        files = find_csvs(STRESS_GLOB)
        show_graph(self, files[0] if files else None, files,
                   "No stress telemetry CSV found yet. Run the stress test (41) first.")

    def _open_csv(self) -> None:
        from .graph import open_in_calc
        files = find_csvs(STRESS_GLOB)
        open_in_calc(self, files[0] if files else None,
                     "No stress telemetry CSV found yet. Run the stress test (41) first.")

    def _sync(self) -> None:
        for widget, value in ((self.include, self.settings.include_in_run_all),
                              (self.duration, self.settings.duration),
                              (self.interval, self.settings.interval)):
            widget.blockSignals(True)
            if isinstance(widget, QCheckBox):
                widget.setChecked(value)
            else:
                widget.setValue(value)
            widget.blockSignals(False)


class OutputPage(QWidget):
    """Common layout: header row, page-specific controls, then terminal + hints."""

    show_logs_requested = pyqtSignal(object)    # list of log scopes or None

    def __init__(self, title: str, scope: str | None, parent: QWidget | None = None):
        super().__init__(parent)
        self.scope = scope
        # Log files are named after the run's scope ("all", a category key or "test-NN"); pages
        # override this with every scope whose runs belong on them (see CategoryPage).
        self.log_scopes: list[str] | None = [scope] if scope else None
        self.layout_ = QVBoxLayout(self)

        header = QHBoxLayout()
        label = QLabel(title)
        label.setStyleSheet("font-size:20px; font-weight:700;")
        header.addWidget(label)
        header.addStretch(1)
        self.header = header
        logs = QPushButton("Show Logs")
        logs.clicked.connect(lambda: self.show_logs_requested.emit(self.log_scopes))
        header.addWidget(logs)
        self.layout_.addLayout(header)

        self.body = QVBoxLayout()
        self.layout_.addLayout(self.body)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.split = split
        self.terminal = Terminal()
        self.hints = HintsPanel()
        hints_box = QWidget()
        hv = QVBoxLayout(hints_box)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.addWidget(QLabel("Hints"))
        hv.addWidget(self.hints)
        split.addWidget(self.terminal)
        split.addWidget(hints_box)
        split.setSizes([700, 300])
        self.layout_.addWidget(split, 1)

    def set_progress(self, text: str) -> None:
        """Progress of a run started from this page, shown on its run button."""


class OverviewPage(OutputPage):
    run_all_requested = pyqtSignal()
    stop_requested = pyqtSignal()

    def __init__(self, stress: StressSettings, parent: QWidget | None = None):
        super().__init__("Overview", "all", parent)
        intro = QLabel(
            "Read-only diagnostics for an AMD BC-250 running Bazzite. Run everything at once here, "
            "or pick a category on the left to run tests individually."
        )
        intro.setWordWrap(True)
        self.body.addWidget(intro)

        row = QHBoxLayout()
        self.run_all = QPushButton(self.RUN_ALL_TEXT)
        self.run_all.setMinimumHeight(44)
        self.run_all.setStyleSheet("font-size:15px; font-weight:700;")
        self.run_all.clicked.connect(self.run_all_requested)
        self.stop = QPushButton("■  Stop")
        self.stop.setMinimumHeight(44)
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.stop_requested)
        row.addWidget(self.run_all, 2)
        row.addWidget(self.stop, 1)
        self.body.addLayout(row)
        self.body.addWidget(StressControls(stress, show_include=True))

    RUN_ALL_TEXT = "▶  Run all tests"

    def set_running(self, running: bool) -> None:
        self.run_all.setEnabled(not running)
        self.stop.setEnabled(running)
        if not running:
            self.run_all.setText(self.RUN_ALL_TEXT)

    def set_progress(self, text: str) -> None:
        self.run_all.setText(text)


class CategoryPage(OutputPage):
    run_tests_requested = pyqtSignal(list, str)     # test ids, scope

    def __init__(self, category: Category, stress: StressSettings, bench: BenchSettings, disk: DiskSettings,
                 parent: QWidget | None = None):
        super().__init__(category.title, category.key, parent)
        self.category = category
        # Runs that belong on this page: the category run, its single tests, and full runs.
        self.log_scopes = [category.key, *(f"test-{t.id}" for t in category.tests), "all"]
        self.bench_controls: BenchControls | None = None

        self._run_cat_text = f"▶  Run all {category.title.lower()} tests"
        self.run_cat = QPushButton(self._run_cat_text)
        self.run_cat.clicked.connect(lambda: self.run_tests_requested.emit(category.test_ids, category.key))
        self.header.insertWidget(1, self.run_cat)

        grid = QGridLayout()
        self.buttons: dict[str, TestButton] = {}
        for i, test in enumerate(category.tests):
            btn = TestButton(test)
            btn.run_requested.connect(lambda tid: self.run_tests_requested.emit([tid], f"test-{tid}"))
            grid.addWidget(btn, i // 2, i % 2)
            self.buttons[test.id] = btn
        self.body.addLayout(grid)

        if STRESS_TEST_ID in self.buttons:
            self.body.addWidget(StressControls(stress, show_include=True))
        if BENCH_TEST_ID in self.buttons:
            self.bench_controls = BenchControls(bench)
            self.body.addWidget(self.bench_controls)
        if DISK_TEST_ID in self.buttons:
            self.body.addWidget(DiskControls(disk))
        if SPEEDTEST_TEST_ID in self.buttons:
            self.body.addWidget(SpeedtestControls())

    def set_running(self, running: bool) -> None:
        self.run_cat.setEnabled(not running)
        for btn in self.buttons.values():
            btn.setEnabled(not running)
        if not running:
            self.run_cat.setText(self._run_cat_text)

    def set_progress(self, text: str) -> None:
        self.run_cat.setText(text)
