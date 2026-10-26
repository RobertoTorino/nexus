# SPDX-License-Identifier: GPL-3.0-or-later
"""Main window: title bar, category navigation on the left, pages on the right."""

from __future__ import annotations

import platform
import shutil
import subprocess
import time
from pathlib import Path

from PyQt6.QtCore import QEvent, QUrl, Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QDesktopServices, QHideEvent, QShowEvent
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QListWidget, QMainWindow, QMessageBox,
    QStackedWidget, QVBoxLayout, QWidget,
)

from . import APP_NAME, DISPLAY_NAME, LOGO_PATH, __version__, plain_tooltip
from .bench import BASELINE_NAME, BASELINE_PATH, BenchSettings, load_history, scores_for
from .disk import DiskSettings
from .catalog import (BENCH_TEST_ID, CATEGORIES, CATEGORY_OF, DISK_TEST_ID, SPEEDTEST_TEST_ID, STRESS_TEST_ID,
                      TESTS)
from .dashboard import ACCENT, ORANGE, RED, ResultsPreview, Stats, StatsBar, header_font, results_card
from .cleanup import CleanupDialog, execute as execute_cleanup
from .findings import Entry, FindingsDialog
from .integrity import check_engine
from .history import DESKTOP_DIR, History, RunInfo, db_path
from .ingame import InGamePage
from .privacy import Redactor
from .settings import AppSettings, SettingsOverlay
from .readme import ReadmeView
from .runhistory import HistoryPage
from .livestatus import LiveStatus
from .logstore import RunLog
from .notify import notify
from .pages import CategoryPage, OutputPage, OverviewPage, StressSettings
from .runner import ERROR, IDLE, RUNNING, RunRequest, TestRunner
from .sysscore import SystemScoreDialog, compute as compute_system_score
from .widgets import ClickableLogo, LogsDialog, SudoDialog

# Long-running tests whose run button shows a countdown or elapsed time while they run.
_LONG_TESTS = {STRESS_TEST_ID: "Stress test", BENCH_TEST_ID: "Benchmark",
               DISK_TEST_ID: "Disk speed test", SPEEDTEST_TEST_ID: "Internet speed test"}


class MainWindow(QMainWindow):
    def __init__(self, runner: TestRunner):
        super().__init__()
        self.runner = runner
        self.stress = StressSettings()
        self.bench = BenchSettings(BASELINE_PATH, Path(runner.script).resolve().parent / BASELINE_NAME)
        from . import graph
        graph.BENCH_BASELINE = self.bench.baseline
        self.disk = DiskSettings()
        self._log: RunLog | None = None
        self._origin: OutputPage | None = None
        self._test_status: dict[str, str] = {}
        self._hint_count: dict[str, int] = {}
        self._result_log: dict[str, Path] = {}       # test id -> GUI log of its result this session
        self._retry_auth: str | None = None
        self._run_id: int | None = None
        self._run_info = RunInfo()
        self._pending: set[str] = set()     # tests of the current run that have not finished yet
        self._run_total = 0
        self._run_started_at = 0.0
        # Currently running long test: (label, started_at, estimated seconds or None for elapsed-only).
        self._long_test: tuple[str, float, int | None] | None = None
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(1000)
        self._progress_timer.timeout.connect(self._update_progress)
        self._quitting = False              # closing: waiting for the running tests to stop
        self.settings = AppSettings(self)
        self.stress.set(duration=self.settings.get("run/stress_duration"),
                        interval=self.settings.get("run/stress_interval"))
        self.stress.changed.connect(self._save_stress)
        self._sudo_allowed = runner.use_sudo        # False with --no-sudo or when running as root
        runner.use_sudo = self._sudo_allowed and self.settings.use_sudo
        self._redactor: Redactor | None = None
        self.history: History | None = None
        self._open_history()

        self.setWindowTitle(DISPLAY_NAME)     # equal to the display name, so Linux does not repeat it
        self.resize(1280, 820)

        central = QWidget()
        root = QVBoxLayout(central)
        # Shown when the test engine fails its integrity check (see integrity.py).
        self.integrity_banner = QLabel()
        self.integrity_banner.setWordWrap(True)
        self.integrity_banner.hide()
        root.addWidget(self.integrity_banner)

        # The logo spans the title and the stats row.
        header = QHBoxLayout()
        header.setSpacing(14)
        logo = ClickableLogo(str(LOGO_PATH), 96)
        logo.setCursor(Qt.CursorShape.ArrowCursor)
        header.addWidget(logo)
        header_right = QVBoxLayout()
        header_right.setSpacing(6)
        title = QLabel(f"{APP_NAME}  <span style='color:#9aa0a6; font-size:14px;'>v{__version__}</span>")
        title.setStyleSheet(header_font() + "font-size:24px; font-weight:800;")
        header_right.addWidget(title)
        self.stats = StatsBar(len(TESTS))
        self.stats.details_requested.connect(self.show_findings)
        self.stats.system_score_requested.connect(self._show_system_score)
        header_right.addWidget(self.stats)
        header.addLayout(header_right, 1)
        root.addLayout(header)

        self.results_preview = ResultsPreview()
        self.results_preview.image_requested.connect(self._open_results_image)
        self.results_preview.folder_requested.connect(self._open_results_folder)
        root.addWidget(self.results_preview)

        main = QHBoxLayout()
        self.nav = QListWidget()
        self.nav.setFixedWidth(220)
        # Selected page: an outlined box with the same corner radius as the test buttons, no fill.
        self.nav.setStyleSheet(
            "QListWidget { outline:0; }"
            "QListWidget::item { padding:6px; margin:2px 4px; border:2px solid transparent; border-radius:6px; }"
            "QListWidget::item:hover { border-color:palette(mid); }"
            "QListWidget::item:selected { background:transparent; color:palette(text);"
            f" border-color:{ACCENT}; }}")
        self.stack = QStackedWidget()
        main.addWidget(self.nav)
        main.addWidget(self.stack, 1)
        root.addLayout(main, 1)
        self.setCentralWidget(central)

        self.overview = OverviewPage(self.stress)
        self.overview.run_all_requested.connect(self.run_all)
        self.overview.stop_requested.connect(self.runner.cancel)
        self._add_page("Overview", self.overview)

        self.category_pages: dict[str, CategoryPage] = {}
        for cat in CATEGORIES:
            page = CategoryPage(cat, self.stress, self.bench, self.disk)
            page.run_tests_requested.connect(self.run_tests)
            self.category_pages[cat.key] = page
            self._add_page(cat.title, page)

        self.history_page = HistoryPage(lambda: self.history)
        self.history_page.open_test.connect(self.open_test_page)
        self.history_page.show_files.connect(self._show_run_files)
        self.nav.addItem("History")
        self.stack.addWidget(self.history_page)

        self.nav.addItem("Game details")
        self.stack.addWidget(InGamePage())

        self.nav.addItem("Help")                # the app's chapter of the suite manual
        self.stack.addWidget(ReadmeView())
        # Settings is not a page: it opens a panel over the window and the nav keeps the current page.
        self.nav.addItem("Settings")
        self._settings_row = self.nav.count() - 1
        self._nav_row = 0
        self.settings_overlay = SettingsOverlay(self.settings, str(runner.script), not self._sudo_allowed, central,
                                                lambda: self.history)
        self.settings_overlay.forget_sudo_requested.connect(self._forget_sudo)
        self.settings_overlay.cleanup_requested.connect(self.clean_up_logs)
        self.settings_overlay.print_results_requested.connect(self._print_results)
        self.settings.changed.connect(self._on_setting_changed)

        self.nav.currentRowChanged.connect(self._on_nav)
        self.nav.setCurrentRow(0)

        runner.run_started.connect(self._on_run_started)
        runner.line.connect(self._on_line)
        runner.hint.connect(self._on_hint)
        runner.test_started.connect(self._on_test_started)
        runner.test_finished.connect(self._on_test_finished)
        runner.run_finished.connect(self._on_run_finished)
        runner.auth_failed.connect(self._on_auth_failed)
        runner.bench_result.connect(self._on_bench_result)
        self._show_last_bench()
        self._update_stats()

        self.live = LiveStatus()
        self.statusBar().addPermanentWidget(self.live)
        mode = "sudo" if runner.use_sudo else "no sudo"
        self.statusBar().showMessage(f"Ready ({mode})")
        QTimer.singleShot(0, self._load_history)
        self._check_engine(report=False)    # the banner only; the message comes with a run
        self._restore_window_state()

    # ------------------------------------------------------------ window state
    def _splitters(self) -> dict:
        found = {f"split/{page.scope}": page.split for page in self._pages()}
        found["split/history"] = self.history_page.split
        return found

    def _restore_window_state(self) -> None:
        geometry = self.settings.window_state("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)      # the position is up to the compositor on Wayland
        for key, split in self._splitters().items():
            state = self.settings.window_state(key)
            if state is not None:
                split.restoreState(state)
        try:
            row = int(self.settings.window_state("page") or 0)
        except (TypeError, ValueError):
            row = 0
        if 0 < row < self._settings_row:
            self.nav.setCurrentRow(row)

    def save_window_state(self) -> None:
        self.settings.set_window_state("geometry", self.saveGeometry())
        self.settings.set_window_state("page", self._nav_row)
        for key, split in self._splitters().items():
            self.settings.set_window_state(key, split.saveState())
        self.settings.sync()

    def _save_stress(self) -> None:
        self.settings.set("run/stress_duration", self.stress.duration)
        self.settings.set("run/stress_interval", self.stress.interval)

    # --------------------------------------------------------------- quitting
    STOP_TIMEOUT_MS = 20000

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.runner.busy:
            event.ignore()
            if self._quitting:
                return
            req = self.runner.request
            answer = QMessageBox.question(
                self, "Tests are running",
                f"A test run ({req.scope if req else 'tests'}) is still in progress.\n\nStop it and quit? The tests "
                "first end their CPU/GPU load and remove their temporary files; that takes a few seconds.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
            if not self.runner.busy:            # it finished while the question was open
                QTimer.singleShot(0, self.close)
                return
            self._quitting = True
            self.statusBar().showMessage("Stopping the running tests before quitting…")
            self.runner.cancel()
            QTimer.singleShot(self.STOP_TIMEOUT_MS, self.runner.kill)
            return
        self.save_window_state()
        super().closeEvent(event)

    def shutdown(self) -> None:
        """The app is quitting without a close event (logout, SIGTERM): stop a run and keep the layout."""
        self._quitting = True
        self.runner.shutdown()
        self.save_window_state()

    # The live monitor pauses while nobody can see it.
    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.WindowStateChange:
            self.live.set_window_visible(not self.isMinimized())
        super().changeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        self.live.set_window_visible(not self.isMinimized())
        super().showEvent(event)

    def hideEvent(self, event: QHideEvent) -> None:
        self.live.set_window_visible(False)
        super().hideEvent(event)

    def show_settings(self, section: str | None = None) -> None:
        self.settings_overlay.open(section)

    def _on_nav(self, row: int) -> None:
        if row == self._settings_row:
            self.nav.blockSignals(True)
            self.nav.setCurrentRow(self._nav_row)
            self.nav.blockSignals(False)
            self.show_settings()
            return
        self._nav_row = row
        self.stack.setCurrentIndex(row)
        self._bold_nav_item(row)        # font-weight in ::item QSS is ignored

    def _open_history(self) -> None:
        self.history = None
        if not self.settings.keep_history:
            return
        try:
            self.history = History()
        except Exception as exc:             # a broken database must never stop the app
            print(f"Test history disabled: {exc}")
            return
        if self.history.recovered_from is not None:
            QTimer.singleShot(0, lambda p=self.history.recovered_from: self._plain_message(
                QMessageBox.Icon.Warning, "Test history", "The test history was damaged or changed outside this app, so a new "
                f"one was started.\n\nThe old file was kept as:\n{p}"))
        self.history.keep_system_details = self.settings.store_system_details
        if not self.history.keep_system_details:
            self.history.scrub_system_details()

    def _on_setting_changed(self, key: str) -> None:
        if key == "privacy/keep_history":
            if self.runner.busy:
                self._run_id = None         # the running run is not recorded halfway
            self._open_history()
            if self.history is not None:
                self._load_history()
            else:
                self._update_stats()
                self.history_page.reload()
        elif key == "privacy/store_system_details" and self.history is not None:
            self.history.keep_system_details = self.settings.store_system_details
            if not self.history.keep_system_details:
                self.history.scrub_system_details()
                self.history_page.reload()
        elif key == "privacy/use_sudo":
            self.runner.use_sudo = self._sudo_allowed and self.settings.use_sudo
            mode = "sudo" if self.runner.use_sudo else "no sudo"
            self.statusBar().showMessage(f"Tests run with {mode} from the next run on.", 8000)

    def _forget_sudo(self) -> None:
        if shutil.which("sudo"):
            subprocess.run(["sudo", "-k"], capture_output=True)
        self.statusBar().showMessage("sudo authentication forgotten: the next run asks for the password.", 8000)

    def _print_results(self) -> None:
        """Settings > General > Print results: save the shareable results card as a PNG."""
        pix = results_card(self.stats)
        downloads = Path.home() / "Downloads"
        default = str((downloads if downloads.is_dir() else Path.home()) / "results.png")
        path, _ = QFileDialog.getSaveFileName(self, "Save results card", default, "PNG image (*.png)")
        if not path:
            return
        if pix.save(path, "PNG"):
            if not self.results_preview.set_image(path):
                QMessageBox.warning(self, "Print results",
                                    f"The results card was saved to {path}, but its preview could not be loaded.")
            self.statusBar().showMessage(f"Results card saved to {path}", 8000)
            self._open_results_image(path)
        else:
            QMessageBox.warning(self, "Print results", f"Could not save the card to {path}.")

    def _open_results_image(self, path: str) -> None:
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            QMessageBox.warning(self, "Print results", f"Could not open the results image:\n{path}")

    def _open_results_folder(self, path: str) -> None:
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            QMessageBox.warning(self, "Print results", f"Could not open the results folder:\n{path}")

    def _update_stats(self) -> None:
        if self.history is None:
            s = Stats.from_results(len(TESTS), self._test_status, sum(self._hint_count.values()))
        else:
            # Latest result of every test over all runs; tests queued in the current run count once they finish.
            latest = {t: r for t, r in self.history.latest_results().items() if t in TESTS and t not in self._pending}
            s = Stats.from_results(len(TESTS), {t: r.status for t, r in latest.items()},
                                   sum(r.hints for r in latest.values()))
        self.stats.update_stats(s)
        self._system_score = compute_system_score(self.history, s.score)
        if len(self._system_score.missing) == len(self._system_score.factors):
            self.stats.set_system_scores(None, None)
        else:
            self.stats.set_system_scores(self._system_score.base, self._system_score.extended)

    def _show_system_score(self, extended: bool) -> None:
        self._update_stats()
        SystemScoreDialog(self._system_score, extended, self).exec()

    def _findings_entries(self) -> list[Entry]:
        """The results the counters are based on, with the files their details can be read from."""
        if self.history is None:
            return [Entry(t, st, self._hint_count.get(t, 0), None,
                          [self._result_log[t]] if t in self._result_log else [])
                    for t, st in self._test_status.items() if t in TESTS and st != RUNNING]
        entries = []
        for tid, r in self.history.latest_results().items():
            if tid not in TESTS or tid in self._pending:
                continue
            logs = [Path(r.log_path).expanduser()] if r.log_path else []
            if r.report_path:
                logs += [Path(r.report_path), DESKTOP_DIR / Path(r.report_path).name]
            entries.append(Entry(tid, r.status, r.hints, r.started, logs))
        return entries

    def show_findings(self, kind: str) -> None:
        dlg = FindingsDialog(kind, self._findings_entries(), self)
        dlg.open_test.connect(self.open_test_page)
        dlg.open_log.connect(lambda path, tid: self._show_log_at(dlg, Path(path), tid))
        dlg.exec()

    def _show_log_at(self, parent: QWidget, path: Path, test_id: str) -> None:
        logs = LogsDialog(None, parent, [path])
        logs.show_test(test_id)
        logs.exec()

    def open_test_page(self, test_id: str) -> None:
        self.nav.setCurrentRow(self.stack.indexOf(self._page_for(test_id)))

    def _load_history(self) -> None:
        """Import the script's reports not seen yet, then show the last known result of every test."""
        if self.history is None:
            return
        added = self.history.import_reports()
        latest = self.history.latest_results()
        for tid, result in latest.items():
            if tid in TESTS and not self.runner.busy:
                self._button(tid).set_last_result(result.status, result.started)
        self._update_stats()
        self.history_page.reload()
        if latest and not self.runner.busy:
            oldest = min(r.started for t, r in latest.items() if t in TESTS)
            note = f", {added} report(s) imported" if added else ""
            self.statusBar().showMessage(
                f"History: {self.history.run_count()} run(s){note}. The counters show the latest result of each "
                f"test (oldest from {oldest[:16]}).", 15000)

    def clean_up_logs(self) -> None:
        if self.runner.busy:
            return
        dlg = CleanupDialog(self)
        if dlg.exec() != CleanupDialog.DialogCode.Accepted:
            return
        plan, remove_all = dlg.plan, dlg.remove_all
        if remove_all and QMessageBox.question(
                self, "Remove all logs",
                f"Remove {len(plan.files)} log file(s) and empty the test history?\n\nThis cannot be undone.") \
                != QMessageBox.StandardButton.Yes:
            return
        password = None
        if plan.root_files and not self.runner.sudo_ready():
            password = SudoDialog.ask(self, "Removing the full reports in /var/log needs root.")
            if password is None:
                self.statusBar().showMessage("Cleanup canceled — no password entered.")
                return
        removed, errors = execute_cleanup(plan, password)
        del password
        if errors and plan.root_files and not any(str(p) in removed for p in plan.root_files):
            QMessageBox.warning(self, "Clean up logs", "Nothing was removed:\n\n" + "\n".join(errors[:10]))
            return
        if remove_all and self.history is None and db_path().exists():
            History().clear()           # history is turned off, but an older database may still be there
        if self.history is not None:
            if remove_all:
                self.history.clear()
            else:
                self.history.mark_logs_removed(removed)
        if remove_all:
            self._test_status.clear()
            self._hint_count.clear()
            for page in self._pages():
                page.hints.clear()
                page.terminal.clear()
            for tid in TESTS:
                self._button(tid).set_state(IDLE)
        self._update_stats()
        self.history_page.reload()
        text = f"Removed {len(removed)} file(s), {plan.size / 1048576:.1f} MiB."
        if remove_all:
            text += " The test history is empty."
        if errors:
            QMessageBox.warning(self, "Clean up logs", text + "\n\nSome files could not be removed:\n"
                                + "\n".join(errors[:10]))
        self.statusBar().showMessage(text)

    def _show_run_files(self, files: list[Path]) -> None:
        if not files:
            self.statusBar().showMessage("The logs of this run are no longer available (removed, or not readable).", 8000)
            return
        LogsDialog(None, self, files).exec()

    def _add_page(self, title: str, page: OutputPage) -> None:
        page.show_logs_requested.connect(lambda scope: LogsDialog(scope, self).exec())
        self.nav.addItem(title)
        self.stack.addWidget(page)

    def _page_for(self, test_id: str) -> CategoryPage:
        return self.category_pages[CATEGORY_OF[test_id].key]

    def _button(self, test_id: str):
        return self._page_for(test_id).buttons[test_id]

    # ------------------------------------------------------------------ runs
    def run_all(self) -> None:
        s = self.stress
        if s.include_in_run_all and not self._confirm_stress():
            return
        self._origin = self.overview
        # The benchmark, disk speed and internet speed tests are never part of "Run all": they need an idle
        # system (and the speed test uses ~1 GB of data), so they are run on their own.
        ids = [t for t in TESTS if t not in (BENCH_TEST_ID, DISK_TEST_ID, SPEEDTEST_TEST_ID)
               and (t != STRESS_TEST_ID or s.include_in_run_all)]
        self._launch(RunRequest("all", sorted(ids), s.include_in_run_all, s.duration, s.interval))

    def run_tests(self, test_ids: list[str], scope: str) -> None:
        s = self.stress
        if test_ids == [STRESS_TEST_ID]:
            stress = True
        else:
            stress = STRESS_TEST_ID in test_ids and s.include_in_run_all
            if not stress:
                # Without --stress the script only logs "skipped" for 41; leave it out entirely.
                test_ids = [t for t in test_ids if t != STRESS_TEST_ID]
        if not test_ids:
            return
        bench = BENCH_TEST_ID in test_ids
        disk = DISK_TEST_ID in test_ids
        if stress and not self._confirm_stress():
            return
        if bench and not self._confirm_bench():
            return
        if disk and not self._confirm_disk():
            return
        speedtest = SPEEDTEST_TEST_ID in test_ids
        if speedtest and not self._confirm_speedtest():
            return
        d = self.disk
        self._origin = self.category_pages[CATEGORY_OF[test_ids[0]].key]
        self._launch(RunRequest(scope, test_ids, stress, s.duration, s.interval,
                                bench, self.bench.seconds, bench and self.bench.save_baseline,
                                disk, d.write_gib if d.write else 0, speedtest))

    def _confirm_bench(self) -> bool:
        b = self.bench
        text = (f"The benchmark runs stress-ng for {b.seconds}s on 1 thread and {b.seconds}s on all threads, "
                "then vkpeak on the GPU (about a minute). Close games and other heavy apps first.")
        if b.save_baseline:
            text += ("\n\nThis run will be SAVED AS THE BASELINE (= 100) for all later scores. Only do this "
                     "with the board in its stock configuration: 24 CUs, 6 cores / 12 threads, governor "
                     "max 1850 MHz.")
            if b.baseline():
                text += f"\n\nThe existing baseline in {b.baseline_path} will be replaced."
        answer = QMessageBox.question(self, "Performance benchmark", text + "\n\nContinue?")
        return answer == QMessageBox.StandardButton.Yes

    def _confirm_disk(self) -> bool:
        d = self.disk
        text = ("The disk speed test reads 4 GiB from the system disk (and runs 2 × 10 s of random reads when "
                "fio is installed). Reading changes nothing. Close games and downloads first, they skew the result.")
        if d.write:
            text += (f"\n\nIt then WRITES {d.write_gib} GiB to a temporary file in /var/tmp to measure write speed "
                     f"and the SLC cache; the file is deleted afterwards. This needs {d.write_gib + 5} GiB free and "
                     f"adds {d.write_gib} GiB of wear to the drive (a tiny share of its rated endurance).")
        answer = QMessageBox.question(self, "Disk speed test", text + "\n\nContinue?")
        return answer == QMessageBox.StandardButton.Yes

    def _bold_nav_item(self, row: int) -> None:
        for i in range(self.nav.count()):
            item = self.nav.item(i)
            font = item.font()
            font.setBold(i == row)
            item.setFont(font)

    def _confirm_speedtest(self) -> bool:
        text = ("The internet speed test downloads and uploads for about 30 s. On a fast connection that is "
                "about 1 GB of data, so skip it on a metered or mobile connection. Pause Steam downloads and "
                "streams first, they skew the result.\n\nWith Ookla's speedtest, running it accepts Ookla's "
                "license and GDPR terms (https://www.speedtest.net/about/eula).")
        answer = QMessageBox.question(self, "Internet speed test", text + "\n\nContinue?")
        return answer == QMessageBox.StandardButton.Yes

    def _show_last_bench(self) -> None:
        history = load_history()
        if history:
            last = history[-1]
            cpu, cpu1, gpu = scores_for(last, self.bench.baseline())
            self.stats.set_bench(cpu, cpu1, gpu, f"Last run: {last.get('date', '?')}, {last.get('cus', '?')} CUs, "
                                               f"{last.get('cores', '?')}C/{last.get('threads', '?')}T")

    def _on_bench_result(self, result: dict) -> None:
        base = self.bench.baseline()
        if self.runner.request and self.runner.request.save_baseline:
            base = None     # the file is only written after this line; this run is the new 100
            result = {**result, "cpu_score": 100, "cpu1_score": 100, "gpu_score": 100}
        cpu, cpu1, gpu = scores_for(result, base)
        self.stats.set_bench(cpu, cpu1, gpu, f"This session: {result.get('cus', '?')} CUs, "
                                           f"{result.get('cores', '?')}C/{result.get('threads', '?')}T, "
                                           f"~{result.get('gpu_mhz', '?')} MHz")

    def _confirm_stress(self) -> bool:
        answer = QMessageBox.warning(
            self, "Stress test",
            f"The stress test loads CPU and GPU for {self.stress.duration}s to reproduce "
            "under-load lockups.\n\nThe system will be sluggish and may freeze outright. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _launch(self, req: RunRequest, message: str = "") -> None:
        if self.runner.busy:
            return
        if not self._check_engine():
            return
        req.copy_desktop = self.settings.get("run/copy_to_desktop")
        password = None
        if not self.runner.sudo_ready():
            password = SudoDialog.ask(self, message)
            if password is None:
                self.statusBar().showMessage("Canceled — no password entered.")
                return
        self.runner.start(req, password)
        del password

    def _plain_message(self, icon: QMessageBox.Icon, title: str, text: str) -> None:
        """Message box that never renders its text as HTML (it holds paths and file contents)."""
        box = QMessageBox(icon, title, text, QMessageBox.StandardButton.Ok, self)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.exec()

    def _check_engine(self, report: bool = True) -> bool:
        """Check the test engine before every run; False when a release build must not run it."""
        verdict = check_engine(self.runner.script)
        problems = "\n".join(f"• {p}" for p in verdict.problems)
        if verdict.ok:
            self.integrity_banner.hide()
            return True
        if verdict.blocked:
            text = "Tests are blocked: the test engine failed its integrity check. Reinstall the app."
            colour = RED
        else:
            text = "Development mode: the test engine is not protected; its integrity is not enforced."
            colour = ORANGE
        self.integrity_banner.setText(f"⚠  {text}  (hover for details)")
        self.integrity_banner.setToolTip(plain_tooltip(problems))
        self.integrity_banner.setStyleSheet(f"background:{colour}; color:white; font-weight:600;"
                                            " padding:6px 10px; border-radius:6px;")
        self.integrity_banner.show()
        if verdict.blocked and report:
            self._plain_message(QMessageBox.Icon.Critical, "Tests blocked",
                                "The test engine failed its integrity check, so no tests are run.\n\n"
                                f"{problems}\n\nReinstall the app to restore it.")
            self.statusBar().showMessage("Tests blocked: the test engine failed its integrity check.")
        return not verdict.blocked

    # ------------------------------------------------------------- callbacks
    def _pages(self) -> list[OutputPage]:
        return [self.overview, *self.category_pages.values()]

    def _on_run_started(self, req: RunRequest) -> None:
        for page in self._pages():
            page.set_running(True)
        self.settings_overlay.set_running(True)
        ids = req.test_ids or list(TESTS)
        for tid in ids:
            self._button(tid).set_state(IDLE)
            self._page_for(tid).hints.clear_test(tid)
            self._test_status.pop(tid, None)
            self._hint_count.pop(tid, None)
        if req.scope == "all":
            self.overview.hints.clear()
        assert self._origin is not None
        self._origin.terminal.clear()
        if self.settings.mask_logs and self._redactor is None:
            self._redactor = Redactor()
        self._log = RunLog(req.scope, self._redactor if self.settings.mask_logs else None)
        self._pending = set(ids)
        self._run_total = len(ids)
        self._run_started_at = time.monotonic()
        self._long_test = None
        self._update_progress()
        self._run_info = RunInfo()
        self._run_id = self.history.start_run(req.scope, self._log.path) if self.history else None
        self._update_stats()
        self.statusBar().showMessage(f"Running {req.scope}… logging to {self._log.path}")

    def _targets(self, test_id: str | None) -> list[OutputPage]:
        pages: list[OutputPage] = [self._origin] if self._origin else []
        if test_id is not None:
            page = self._page_for(test_id)
            if page is not self._origin:
                pages.append(page)
        return pages

    def _on_line(self, text: str, level: str, test_id: str | None) -> None:
        if self._log:
            self._log.write(text)
        self._run_info.scan(text)
        for page in self._targets(test_id):
            page.terminal.append_line(text, level)

    def _on_hint(self, test_id: str, text: str, severity: str) -> None:
        self._hint_count[test_id] = self._hint_count.get(test_id, 0) + 1
        self._update_stats()
        for page in self._targets(test_id):
            page.hints.add_hint(test_id, text, severity)

    def _on_test_started(self, test_id: str) -> None:
        self._test_status[test_id] = RUNNING
        self._button(test_id).set_state(RUNNING)
        req = self.runner.request
        if req is not None and test_id in _LONG_TESTS:
            # Estimated durations; None shows elapsed time instead (the disk test depends on the drive).
            estimate = None
            if test_id == STRESS_TEST_ID and req.stress:
                estimate = req.stress_duration
            elif test_id == BENCH_TEST_ID and req.bench:
                estimate = 2 * req.bench_seconds + 60       # 1-thread + all-threads stress-ng, then vkpeak
            elif test_id == SPEEDTEST_TEST_ID and req.speedtest:
                estimate = 40
            if test_id != STRESS_TEST_ID or req.stress:
                self._long_test = (_LONG_TESTS[test_id], time.monotonic(), estimate)
                self._progress_timer.start()
        self._update_progress()

    def _update_progress(self) -> None:
        if not self.runner.busy or self._origin is None:
            self._progress_timer.stop()
            return
        done = self._run_total - len(self._pending)
        text = f"Running…  {done} / {self._run_total} done"
        if self._long_test is not None:
            label, started, estimate = self._long_test
            if estimate is not None:
                left = round(started + estimate - time.monotonic())
                part = f"{label}: {left // 60}:{left % 60:02d} left" if left > 0 else f"{label}: finishing…"
            else:
                elapsed = round(time.monotonic() - started)
                part = f"{label}: {elapsed // 60}:{elapsed % 60:02d}"
            text = f"{part}  ·  {done} / {self._run_total} done"
        self._origin.set_progress(text)

    def _on_test_finished(self, test_id: str, status: str) -> None:
        if status == IDLE:
            self._test_status.pop(test_id, None)
            self._hint_count.pop(test_id, None)
        else:
            self._test_status[test_id] = status
            if self._log:
                self._result_log[test_id] = self._log.path
            if self.history and self._run_id is not None:
                self.history.record_result(self._run_id, test_id, status, self._hint_count.get(test_id, 0))
        self._pending.discard(test_id)
        self._button(test_id).set_state(status)
        if test_id in _LONG_TESTS:
            self._long_test = None
            self._progress_timer.stop()
        self._update_stats()
        self._update_progress()

    def _on_auth_failed(self, message: str) -> None:
        self._retry_auth = message

    def _on_run_finished(self, code: int, cancelled: bool) -> None:
        self._progress_timer.stop()
        self._long_test = None
        for page in self._pages():
            page.set_running(False)
        self.settings_overlay.set_running(False)
        req_done = self.runner.request
        if req_done and req_done.save_baseline and not cancelled:
            self.bench.set(save_baseline=False)
        for page in self.category_pages.values():
            if page.bench_controls:
                page.bench_controls.refresh()
        if self._log:
            self._log.close()
        self._pending.clear()
        if self.history and self._run_id is not None:
            if self._retry_auth is not None:
                self.history.delete_run(self._run_id)
            else:
                self._run_info.meta.setdefault("kernel", platform.release())
                self.history.finish_run(self._run_id, self._run_info, code, cancelled)
                # Tests that never finished (canceled) show their previous result again.
                latest = self.history.latest_results()
                for tid in (self.runner.request.test_ids or list(TESTS)) if self.runner.request else []:
                    if self._button(tid).state == IDLE and tid in latest:
                        self._button(tid).set_last_result(latest[tid].status, latest[tid].started)
        self._run_id = None
        self._update_stats()
        self.history_page.reload()
        req = self.runner.request
        if self._quitting:
            self._log = None
            QTimer.singleShot(0, self.close)
            return
        if self._retry_auth is not None and req is not None:
            message, self._retry_auth = self._retry_auth, None
            if self._log:
                self._log.path.unlink(missing_ok=True)
            self._log = None
            QTimer.singleShot(0, lambda: self._launch(req, message))
            return
        ran = (req.test_ids or list(TESTS)) if req else []
        errors = sum(1 for tid in ran if self._test_status.get(tid) == ERROR)
        state = "cancelled" if cancelled else f"finished (exit {code})"
        where = f" — log: {self._log.path}" if self._log else ""
        self.statusBar().showMessage(f"Run {state}, {errors} test(s) with errors{where}")
        self._log = None
        self._notify_finished(ran, cancelled)

    def _notify_finished(self, ran: list[str], cancelled: bool) -> None:
        """Tell the user a long run is done when they're working in another window."""
        if (time.monotonic() - self._run_started_at < 60 or self.isActiveWindow()
                or not self.settings.get("general/notify")):
            return
        QApplication.alert(self)        # the taskbar entry asks for attention
        stats = Stats.from_results(len(ran), {t: self._test_status[t] for t in ran if t in self._test_status},
                                   sum(self._hint_count.get(t, 0) for t in ran))
        name = "All tests" if self.runner.request and self.runner.request.scope == "all" else "Test run"
        if cancelled:
            summary = f"{name} stopped"
        else:
            summary = f"{name} finished" + (f": health {stats.score}%" if stats.score is not None else "")
        body = (f"{stats.ran} of {len(ran)} tests finished: {stats.passed} passed, {stats.warnings} warning(s), "
                f"{stats.failures} failure(s), {stats.info} info, {stats.hints} hint(s).")
        notify(summary, body)
