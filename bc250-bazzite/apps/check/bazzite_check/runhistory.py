# SPDX-License-Identifier: GPL-3.0-or-later
"""History page: past runs by date; one selected run shows its results and numbers, two are compared."""

from __future__ import annotations

import html
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QDate, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDateEdit, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
)

from .catalog import CATEGORIES, CATEGORY_OF, TESTS
from .dashboard import Stats, score_color
from .findings import LEVEL_COLOR
from .history import DESKTOP_DIR, History, RunSummary
from .runner import ERROR, INFO, SUCCESS, WARNING

MUTED = "#9aa0a6"
BETTER, WORSE = "#81c784", "#e57373"
STATUS_COLOR = {SUCCESS: BETTER, WARNING: LEVEL_COLOR[WARNING], ERROR: LEVEL_COLOR[ERROR], INFO: LEVEL_COLOR[INFO]}
STATUS_TEXT = {SUCCESS: "passed", WARNING: "warning", ERROR: "failure", INFO: "info"}
SEVERITY = {SUCCESS: 0, INFO: 0, WARNING: 1, ERROR: 2}
SAME_WITHIN = 0.02            # differences under 2 % count as unchanged (measurement noise)

# key: (label, unit, decimals, True = higher is better / False = lower / None = neither)
METRICS: dict[str, tuple[str, str, int, bool | None]] = {
    "bench.cpu_score": ("CPU score (stock = 100)", "", 0, True),
    "bench.cpu1_score": ("CPU single-thread score", "", 0, True),
    "bench.gpu_score": ("GPU score (stock = 100)", "", 0, True),
    "bench.cpu_multi": ("CPU multi-thread", "ops/s", 1, True),
    "bench.cpu_single": ("CPU single-thread", "ops/s", 1, True),
    "bench.gpu_fp32": ("GPU FP32 compute", "GFLOPS", 1, True),
    "bench.gpu_copy": ("GPU memory copy", "GB/s", 1, True),
    "bench.gpu_mhz": ("GPU clock in benchmark", "MHz", 0, True),
    "stress.sclk_min": ("Stress: GPU clock min", "MHz", 0, True),
    "stress.sclk_avg": ("Stress: GPU clock avg", "MHz", 0, True),
    "stress.sclk_max": ("Stress: GPU clock max", "MHz", 0, True),
    "stress.busy_avg": ("Stress: GPU busy avg", "%", 0, None),
    "stress.busy_max": ("Stress: GPU busy max", "%", 0, None),
    "stress.gpu_temp_max": ("Stress: GPU temperature max", "°C", 0, False),
    "stress.cpu_temp_max": ("Stress: CPU temperature max", "°C", 0, False),
    "stress.gpu_power_avg": ("Stress: GPU power avg", "W", 1, None),
    "stress.gpu_power_max": ("Stress: GPU power max", "W", 1, None),
    "stress.fan_max": ("Stress: fan max", "RPM", 0, False),
    "disk.read_mbps": ("NVMe sequential read", "MB/s", 0, True),
    "disk.write_start_mbps": ("NVMe write, start", "MB/s", 0, True),
    "disk.write_end_mbps": ("NVMe write, end", "MB/s", 0, True),
    "disk.write_avg_mbps": ("NVMe write, average", "MB/s", 0, True),
    "disk.iops_qd1": ("NVMe random 4K read QD1", "IOPS", 0, True),
    "disk.iops_qd32": ("NVMe random 4K read QD32", "IOPS", 0, True),
    "net.down_mbps": ("Internet download", "Mbps", 1, True),
    "net.up_mbps": ("Internet upload", "Mbps", 1, True),
    "net.ping_ms": ("Internet latency (idle)", "ms", 1, False),
}
CONFIG_ONLY = {"bench.cores", "bench.threads", "bench.cus"}     # shown with the configuration instead

COLUMNS = ["Date", "What ran", "Tests", "Passed", "Warnings", "Failures", "Info / hints", "Health", "CUs", "Cores"]


def scope_text(run: RunSummary) -> str:
    if run.source == "script":
        return "Full report (imported)"
    if run.scope == "all":
        return "All tests"
    if run.scope.startswith("test-") and (t := TESTS.get(run.scope[5:])):
        return f"Test {t.id} {t.name}"
    for cat in CATEGORIES:
        if cat.key == run.scope:
            return cat.title
    return run.scope


def health(run: RunSummary) -> int | None:
    return Stats(len(TESTS), run.passed, run.warnings, run.failures, run.info).score


def _e(value: object) -> str:
    return html.escape("—" if value is None or value == "" else str(value))


def _fmt(key: str, value: float | None) -> str:
    if value is None:
        return "—"
    _label, unit, decimals, _better = METRICS.get(key, (key, "", 2, None))
    return f"{value:,.{decimals}f}" + (f" {unit}" if unit else "")


def _metric_keys(*metric_sets: dict[str, float]) -> list[str]:
    keys = {k for m in metric_sets for k in m} - CONFIG_ONLY
    order = list(METRICS)
    return sorted(keys, key=lambda k: (order.index(k) if k in order else len(order), k))


def _status_cell(status: str | None, hints: int = 0) -> str:
    if status is None:
        return f"<td style='color:{MUTED};'>not run</td>"
    extra = f" <span style='color:{MUTED};'>· {hints} hint{'s' if hints != 1 else ''}</span>" if hints else ""
    return (f"<td><span style='color:{STATUS_COLOR.get(status, MUTED)}; font-weight:600;'>"
            f"{STATUS_TEXT.get(status, _e(status))}</span>{extra}</td>")


def _test_link(tid: str) -> str:
    t = TESTS.get(tid)
    return f"<a href='test:{tid}' style='color:#e6e6e6; text-decoration:none;'>[{_e(tid)}] {_e(t.name if t else '?')}</a>"


def _config_rows(run: RunSummary) -> list[tuple[str, str]]:
    return [("CUs", _e(run.cus)), ("Cores / threads", f"{_e(run.cores)} / {_e(run.threads)}"),
            ("Kernel", _e(run.kernel)), ("Mitigations", _e(run.mitigations))]


TABLE = "<table cellspacing='0' cellpadding='4' style='margin-bottom:10px;'>"
TH = f"<th align='left' style='color:{MUTED}; font-weight:600; padding-right:18px;'>"


def render_run(run: RunSummary, results: dict[str, tuple[str, int]], metrics: dict[str, float]) -> str:
    score = health(run)
    state = "cancelled" if run.cancelled else (
        "imported from a full report" if run.source == "script" else
        f"finished {run.finished[11:16] if run.finished[:10] == run.started[:10] else run.finished[:16]}"
        if run.finished else "did not finish")
    parts = [f"<h2 style='margin-bottom:0;'>{_e(run.started[:16])} — {_e(scope_text(run))}</h2>",
             f"<p style='color:{MUTED}; margin-top:2px;'>{_e(state)}</p>"]
    parts.append(TABLE + "<tr>" + "".join(f"<td style='padding-right:22px;'>{x}</td>" for x in (
        f"<b>{run.tests}</b> tests", f"<span style='color:{BETTER};'><b>{run.passed}</b> passed</span>",
        f"<span style='color:{STATUS_COLOR[WARNING]};'><b>{run.warnings}</b> warnings</span>",
        f"<span style='color:{STATUS_COLOR[ERROR]};'><b>{run.failures}</b> failures</span>",
        f"<span style='color:{STATUS_COLOR[INFO]};'><b>{run.info}</b> info · {run.hints} hints</span>",
        f"Health <b style='color:white; background:{score_color(score)};'>&nbsp;{_e(score)}%&nbsp;</b>")) + "</tr></table>")
    parts.append("<h3>Configuration</h3>" + TABLE + "".join(
        f"<tr>{TH}{label}</th><td>{value}</td></tr>" for label, value in _config_rows(run)) + "</table>")
    parts.append("<h3>Results</h3>" + TABLE)
    for cat in CATEGORIES:
        ids = [t for t in cat.test_ids if t in results]
        if not ids:
            continue
        parts.append(f"<tr><td colspan='2' style='color:{MUTED}; padding-top:8px;'><i>{_e(cat.title)}</i></td></tr>")
        parts += [f"<tr><td style='padding-right:24px;'>{_test_link(t)}</td>{_status_cell(*results[t])}</tr>" for t in ids]
    parts.append("</table>")
    keys = _metric_keys(metrics)
    if keys:
        parts.append("<h3>Measurements</h3>" + TABLE + "".join(
            f"<tr>{TH}{_e(METRICS.get(k, (k,))[0])}</th><td align='right'>{_e(_fmt(k, metrics[k]))}</td></tr>"
            for k in keys) + "</table>")
    files = [p for p in (run.log_path, run.report_path) if p]
    if files:
        note = " (removed by Clean up logs)" if run.logs_removed else ""
        parts.append(f"<p style='color:{MUTED}; font-size:small;'>Files{note}: "
                     + " · ".join(_e(p) for p in files) + "</p>")
    return "".join(parts)


def _delta(key: str, a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return f"<td style='color:{MUTED};'>—</td>"
    diff = b - a
    rel = diff / abs(a) if a else (0.0 if diff == 0 else 1.0)
    better = METRICS.get(key, ("", "", 2, None))[3]
    if abs(rel) < SAME_WITHIN:
        return f"<td style='color:{MUTED};'>same</td>"
    color = MUTED if better is None else BETTER if (diff > 0) == better else WORSE
    sign = "+" if diff > 0 else "−"
    pct = f" ({sign}{abs(rel):.0%})" if a else ""
    return f"<td style='color:{color};'>{sign}{_e(_fmt(key, abs(diff)))}{pct}</td>"


def render_compare(a: RunSummary, ra: dict[str, tuple[str, int]], ma: dict[str, float],
                   b: RunSummary, rb: dict[str, tuple[str, int]], mb: dict[str, float],
                   only_differences: bool) -> str:
    """a is the older run, b the newer one; differences read from a to b."""
    head = (f"<tr>{TH}</th>{TH}{_e(a.started[:16])}<br><span style='font-weight:normal;'>{_e(scope_text(a))}</span></th>"
            f"{TH}{_e(b.started[:16])}<br><span style='font-weight:normal;'>{_e(scope_text(b))}</span></th>{TH}Change</th></tr>")
    parts = ["<h2 style='margin-bottom:0;'>Comparison</h2>",
             f"<p style='color:{MUTED}; margin-top:2px;'>Older run on the left, newer on the right. Green is better, "
             f"red is worse; differences under {SAME_WITHIN:.0%} count as the same.</p>", "<h3>Summary</h3>", TABLE, head]
    sa, sb = health(a), health(b)
    rows = [("Health score", f"{_e(sa)}%", f"{_e(sb)}%", sa, sb, True),
            ("Passed", a.passed, b.passed, a.passed, b.passed, True),
            ("Warnings", a.warnings, b.warnings, a.warnings, b.warnings, False),
            ("Failures", a.failures, b.failures, a.failures, b.failures, False),
            ("Hints", a.hints, b.hints, a.hints, b.hints, False)]
    for label, ta, tb, va, vb, higher in rows:
        if va is None or vb is None or va == vb:
            change = f"<td style='color:{MUTED};'>same</td>" if va == vb else "<td></td>"
        else:
            change = f"<td style='color:{BETTER if (vb > va) == higher else WORSE};'>{vb - va:+d}</td>"
        parts.append(f"<tr>{TH}{label}</th><td>{_e(ta)}</td><td>{_e(tb)}</td>{change}</tr>")
    for (label, va), (_l, vb) in zip(_config_rows(a), _config_rows(b)):
        changed = f"<td style='color:{STATUS_COLOR[WARNING]};'>changed</td>" if va != vb else "<td></td>"
        parts.append(f"<tr>{TH}{label}</th><td>{va}</td><td>{vb}</td>{changed}</tr>")
    parts.append("</table>")

    ids = [t for c in CATEGORIES for t in c.test_ids if t in ra or t in rb]
    shown = 0
    test_rows = []
    for tid in ids:
        st_a, h_a = ra.get(tid, (None, 0))
        st_b, h_b = rb.get(tid, (None, 0))
        if st_a is None or st_b is None:
            change = f"<td style='color:{MUTED};'>only in one run</td>"
            differs = True
        elif SEVERITY.get(st_a, 0) != SEVERITY.get(st_b, 0):
            worse = SEVERITY.get(st_b, 0) > SEVERITY.get(st_a, 0)
            change = f"<td style='color:{WORSE if worse else BETTER};'>{'worse' if worse else 'better'}</td>"
            differs = True
        else:
            differs = st_a != st_b          # passed <-> info; a different number of hints alone is no difference
            change = f"<td style='color:{MUTED};'>{'changed' if differs else 'same'}</td>"
        if only_differences and not differs:
            continue
        shown += 1
        test_rows.append(f"<tr><td style='padding-right:24px;'>{_test_link(tid)}</td>"
                         f"{_status_cell(st_a, h_a)}{_status_cell(st_b, h_b)}{change}</tr>")
    title = "Tests with a different result" if only_differences else "Results"
    parts.append(f"<h3>{title}</h3>")
    if test_rows:
        parts.append(TABLE + head.replace(f"{TH}</th>", f"{TH}Test</th>", 1) + "".join(test_rows) + "</table>")
    else:
        parts.append(f"<p style='color:{MUTED};'>Every test that ran in both has the same result.</p>")

    keys = _metric_keys(ma, mb)
    if only_differences:
        keys = [k for k in keys if k in ma and k in mb]
    if keys:
        parts.append("<h3>Measurements</h3>" + TABLE + head.replace(f"{TH}</th>", f"{TH}Measurement</th>", 1))
        for k in keys:
            va, vb = ma.get(k), mb.get(k)
            parts.append(f"<tr>{TH}{_e(METRICS.get(k, (k,))[0])}</th><td align='right'>{_e(_fmt(k, va))}</td>"
                         f"<td align='right'>{_e(_fmt(k, vb))}</td>{_delta(k, va, vb)}</tr>")
        parts.append("</table>")
    return "".join(parts)


class HistoryPage(QWidget):
    """Runs between two dates; select one to see it, two to compare them."""

    open_test = pyqtSignal(str)
    show_files = pyqtSignal(list)          # list[Path] of the selected run's log and report

    PLACEHOLDER = ("<p style='color:#9aa0a6;'>Select a run to see its results and measurements.<br>"
                   "Ctrl-click (or Shift-click) a second run to compare the two side by side.</p>")

    def __init__(self, history: Callable[[], History | None], parent: QWidget | None = None):
        super().__init__(parent)
        self._history = history
        self._runs: list[RunSummary] = []
        layout = QVBoxLayout(self)
        title = QLabel("History")
        title.setStyleSheet("font-size:20px; font-weight:700;")
        layout.addWidget(title)
        layout.addWidget(QLabel("Every run with its results. Pick the dates to show, select a run to see what it "
                                "found, or select two runs to compare them."))

        row = QHBoxLayout()
        row.addWidget(QLabel("From"))
        self.since = self._date_edit()
        row.addWidget(self.since)
        row.addWidget(QLabel("to"))
        self.until = self._date_edit()
        row.addWidget(self.until)
        self.all_dates = QPushButton("All dates")
        self.all_dates.setToolTip("Show every run in the history")
        self.all_dates.clicked.connect(self._reset_dates)
        row.addWidget(self.all_dates)
        self.count = QLabel()
        self.count.setStyleSheet(f"color:{MUTED};")
        row.addSpacing(10)
        row.addWidget(self.count)
        row.addStretch(1)
        self.only_diff = QCheckBox("Only differences")
        self.only_diff.setToolTip("When comparing two runs: show only the tests whose result changed, "
                                  "and the measurements both runs have")
        self.only_diff.setChecked(True)
        self.only_diff.toggled.connect(self._show_selection)
        row.addWidget(self.only_diff)
        self.logs_btn = QPushButton("Show logs")
        self.logs_btn.setToolTip("Open the log and the full report of the selected run")
        self.logs_btn.clicked.connect(self._show_logs)
        row.addWidget(self.logs_btn)
        layout.addLayout(row)

        split = QSplitter(Qt.Orientation.Vertical)
        self.split = split
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        # A see-through purple selection keeps the colored counts and health readable.
        self.table.setStyleSheet("QTableWidget { outline:0; }"
                                 "QTableWidget::item:selected { background:rgba(139, 79, 216, 90); color:palette(text); }")
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._show_selection)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.setStyleSheet("QTextBrowser { background:#1e1f24; color:#e6e6e6; border-radius:6px; padding:6px; }")
        self.view.anchorClicked.connect(self._link)
        split.addWidget(self.table)
        split.addWidget(self.view)
        split.setSizes([260, 420])
        layout.addWidget(split, 1)

        self.since.dateChanged.connect(self._filter_changed)
        self.until.dateChanged.connect(self._filter_changed)
        self._range: tuple[str, str] | None = None
        self.reload()

    @staticmethod
    def _date_edit() -> QDateEdit:
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("yyyy-MM-dd")
        return edit

    # ------------------------------------------------------------------ data
    def reload(self) -> None:
        """Re-read the history (after a run, a cleanup or a privacy change); keeps the chosen dates."""
        history = self._history()
        enabled = history is not None
        for w in (self.since, self.until, self.all_dates, self.table, self.only_diff):
            w.setEnabled(enabled)
        if history is None:
            self._runs = []
            self.table.setRowCount(0)
            self.count.clear()
            self.logs_btn.setEnabled(False)
            self.view.setHtml(f"<p style='color:{MUTED};'>The test history is turned off "
                              "(Settings › Privacy › Keep a test history).</p>")
            return
        dates = history.run_dates()
        old_range, self._range = self._range, dates
        if dates:
            first, last = (QDate.fromString(d, "yyyy-MM-dd") for d in dates)
            today = QDate.currentDate()
            for edit in (self.since, self.until):
                edit.blockSignals(True)
                edit.setDateRange(first, max(last, today))
            # Follow new runs while the end date was at the newest run; otherwise keep the user's choice.
            if old_range is None or self.until.date().toString("yyyy-MM-dd") >= old_range[1]:
                self.until.setDate(max(last, today))
            if old_range is None or self.since.date() < first:
                self.since.setDate(first)
            for edit in (self.since, self.until):
                edit.blockSignals(False)
        self._fill()

    def _reset_dates(self) -> None:
        if self._range:
            for edit, date in ((self.since, QDate.fromString(self._range[0], "yyyy-MM-dd")),
                               (self.until, self.until.maximumDate())):
                edit.blockSignals(True)
                edit.setDate(date)
                edit.blockSignals(False)
            self._fill()

    def _filter_changed(self) -> None:
        if self.since.date() > self.until.date():
            sender = self.sender()
            other = self.until if sender is self.since else self.since
            other.blockSignals(True)
            other.setDate(sender.date())
            other.blockSignals(False)
        self._fill()

    def _fill(self) -> None:
        history = self._history()
        selected = {self._runs[i].id for i in self._selected_rows()} if self._runs else set()
        self._runs = history.runs(self.since.date().toString("yyyy-MM-dd"),
                                  self.until.date().toString("yyyy-MM-dd")) if history and self._range else []
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setRowCount(len(self._runs))
        for i, run in enumerate(self._runs):
            score = health(run)
            cells = [run.started[:16], scope_text(run), str(run.tests), str(run.passed), str(run.warnings),
                     str(run.failures), f"{run.info} / {run.hints}", "—" if score is None else f"{score}%",
                     "—" if run.cus is None else str(run.cus),
                     "—" if run.cores is None else f"{run.cores}C/{run.threads or '?'}T"]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col >= 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, col, item)
            for col, value, color in ((4, run.warnings, "#ef6c00"), (5, run.failures, "#c62828")):
                if value:
                    self.table.item(i, col).setForeground(QColor(color))
            badge = self.table.item(i, 7)
            badge.setForeground(QColor(score_color(score)))
            font = badge.font()
            font.setBold(True)
            badge.setFont(font)
            if run.cancelled:
                self.table.item(i, 1).setText(scope_text(run) + " (canceled)")
            if run.id in selected:
                self.table.selectRow(i)
        self.table.blockSignals(False)
        total = len(self._runs)
        self.count.setText(f"{total} run{'s' if total != 1 else ''}" if self._range else "No runs yet")
        self._show_selection()

    # ------------------------------------------------------------------ view
    def _selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.table.selectionModel().selectedRows()})

    def _show_selection(self) -> None:
        history = self._history()
        rows = self._selected_rows()
        self.logs_btn.setEnabled(len(rows) == 1)
        self.only_diff.setVisible(len(rows) == 2)
        if history is None:
            return
        if not rows:
            self.view.setHtml(self.PLACEHOLDER if self._runs else
                              f"<p style='color:{MUTED};'>No runs in these dates.</p>")
        elif len(rows) == 1:
            run = self._runs[rows[0]]
            self.view.setHtml(render_run(run, history.run_results(run.id), history.run_metrics(run.id)))
        elif len(rows) == 2:
            newer, older = (self._runs[r] for r in rows)        # the table is newest first
            self.view.setHtml(render_compare(older, history.run_results(older.id), history.run_metrics(older.id),
                                             newer, history.run_results(newer.id), history.run_metrics(newer.id),
                                             self.only_diff.isChecked()))
        else:
            self.view.setHtml(f"<p style='color:{MUTED};'>{len(rows)} runs selected. Select one run to see it, "
                              "or two to compare them.</p>")

    def _link(self, url: QUrl) -> None:
        text = url.toString()
        if text.startswith("test:") and text[5:] in CATEGORY_OF:
            self.open_test.emit(text[5:])

    def _show_logs(self) -> None:
        rows = self._selected_rows()
        if len(rows) != 1:
            return
        run = self._runs[rows[0]]
        files: list[Path] = []
        if run.log_path:
            files.append(Path(run.log_path).expanduser())
        files = [p for p in files if p.is_file()]
        if run.report_path:
            report = Path(run.report_path).expanduser()
            files += [p for p in (report, DESKTOP_DIR / report.name) if p.is_file()][:1]   # or its Desktop copy
        self.show_files.emit(files)
