# SPDX-License-Identifier: GPL-3.0-or-later
"""Main window: logo and metric boxes on top, navigation on the left, pages on the right."""

from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QIcon, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QListWidget, QMainWindow, QMessageBox,
    QScrollArea, QStackedWidget,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from . import APP_ID, APP_NAME, DISPLAY_NAME, LOGO_PATH, __version__, fmt
from .backends import CyanSkillfishBackend, GovernorConfig, PerformanceState
from .backends import (
    FEATURE_DBUS, FEATURE_DOWN_EVENTS, FEATURE_FREQUENCY_RANGE, FEATURE_GPU_USAGE, FEATURE_SET_METHOD,
)
from .alerts import AlertMonitor
from .backups_page import BackupsPage
from .config_pages import GpuUsagePage, TuningPage
from .diagnostics import build_report, default_filename
from .help import HelpView
from . import instance
from .history import default_csv_name, read_csv
from .kernelwatch import KernelWatch
from .pages import LOAD_SOURCES, POLL_MS, OverviewPage, ServicePage, Snapshot, load_sensor_hint
from .performance_page import PerformancePage
from .profiles import ProfileStore, clean_name
from .safepoints_page import SafePointsPage
from .settings_page import SettingsPage
from .stress import NO_TOOL, StressRunner
from .tray import Tray, profile_command
from .update_check import UpdateChecker, UpdateResult
from .widgets import ACCENT, BLUE, GREEN, GREY, ORANGE, PURPLE, RED, ClickableLogo, MetricBox, header_font

SOURCE_NAMES = {"hwmon": "amdgpu hwmon sensor",
                "gpu_metrics": "gpu_metrics table"}


def _scrollable(page: QWidget) -> QScrollArea:
    """Host a page in a scroll area, so a window that is too short scrolls instead of squashing the controls."""
    area = QScrollArea()
    area.setWidget(page)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.viewport().setAutoFillBackground(False)
    page.setAutoFillBackground(False)
    return area


class MainWindow(QMainWindow):
    def __init__(self, backend: CyanSkillfishBackend):
        super().__init__()
        self.backend = backend
        self.settings = QSettings(APP_ID, APP_ID)
        self.setWindowTitle(DISPLAY_NAME)     # equal to the display name, so Linux does not repeat it
        self.resize(1080, 760)
        self._quitting = False
        self._last_snapshot: Snapshot | None = None
        self.tray: Tray | None = None

        central = QWidget()
        root = QVBoxLayout(central)

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
        boxes = QHBoxLayout()
        boxes.setSpacing(8)
        self.box_load = MetricBox("GPU load", BLUE)
        self.box_clock = MetricBox("GPU clock", PURPLE)
        self.box_temp = MetricBox("GPU temperature", GREY)
        self.box_power = MetricBox("Power", GREY)
        self.box_perf = MetricBox("Performance mode", GREY)
        self.box_service = MetricBox("Governor", GREY)
        for box in (self.box_load, self.box_clock, self.box_temp, self.box_power, self.box_perf, self.box_service):
            boxes.addWidget(box, 1)
        header_right.addLayout(boxes)
        header.addLayout(header_right, 1)
        root.addLayout(header)

        main = QHBoxLayout()
        self.nav = QListWidget()
        self.nav.setFixedWidth(200)
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

        self.overview = OverviewPage()
        self.overview.export_requested.connect(self._export_history)
        self.overview.compare_requested.connect(self._compare_history)
        self.gpu_usage = GpuUsagePage(str(backend.config_path))
        self.tuning = TuningPage()
        self.config_pages = ((self.gpu_usage, self.tuning) if backend.supports(FEATURE_GPU_USAGE) else (self.tuning,))
        for page in self.config_pages:
            page.apply_requested.connect(self._apply)
            page.reload.clicked.connect(self._reload_config)
            page.dirty_changed.connect(self._on_dirty)
        self.profiles = ProfileStore()
        self.tuning.profiles.load_requested.connect(self._profile_load)
        self.tuning.profiles.apply_requested.connect(self._profile_apply)
        self.tuning.profiles.save_requested.connect(self._profile_save)
        self.tuning.profiles.copy_command_requested.connect(self._profile_copy_command)
        self.tuning.profiles.delete_requested.connect(self._profile_delete)
        self._sync_profiles()
        self.performance = PerformancePage()
        self.performance.enable_requested.connect(self._perf_enable)
        self.performance.fixed_requested.connect(self._perf_fixed)
        self.performance.range_requested.connect(self._perf_range)
        self.performance.load_requested.connect(self._perf_load)
        self.performance.temperature_requested.connect(self._perf_temperature)
        self.performance.copy_requested.connect(self._perf_copy)
        self.performance.refresh_requested.connect(self.refresh)
        self.performance.launch.generated.connect(
            lambda text: self.statusBar().showMessage(fmt("Copied: %1", text), 6000))
        self.safe_points = SafePointsPage(str(backend.config_path), backend.default_safe_points)
        self.safe_points.reload.clicked.connect(self._reload_config)
        self.safe_points.apply_requested.connect(self._apply_safe_points)
        self.safe_points.dirty_changed.connect(self._on_dirty)
        self.safe_points.test_requested.connect(self._test_point)
        self.safe_points.stop_test_requested.connect(self._stop_test)
        self._test: tuple[int, int, float] | None = None     # frequency, voltage, monotonic deadline (0 = none)
        self._test_started: datetime | None = None
        self._test_tool_exit: str = ""                       # how the load tool ended, if it did on its own
        self._test_timer = QTimer(self)
        self._test_timer.setSingleShot(True)
        self._test_timer.timeout.connect(lambda: self._stop_test(auto=True))
        self._stress = StressRunner(self)
        self._stress.finished.connect(self._stress_finished)
        self.instance_server: instance.InstanceServer | None = None
        self._kernel = KernelWatch(self)
        self._kernel.trouble.connect(self._kernel_event)
        self._kernel.unavailable.connect(lambda why: self.refresh())
        self.backups = BackupsPage(str(backend.config_path))
        self.backups.read_backup = backend.read_backup
        self.backups.restore_requested.connect(self._restore_backup)
        self.backups.refresh_requested.connect(self._reload_config)
        self.service = ServicePage(backend.service_name)
        self.service.action_requested.connect(self._service_action)
        self.service.refresh_requested.connect(self.refresh)
        self.service.export_requested.connect(self._export_diagnostics)
        self.service.update_check_requested.connect(self._check_updates)
        self.updates = UpdateChecker(self.backend.package_name, self)
        self.updates.finished.connect(self._update_checked)
        self.settings_page = SettingsPage(self.settings, QSystemTrayIcon.isSystemTrayAvailable())
        self.settings_page.tray_toggled.connect(self._set_tray)
        self.alerts = AlertMonitor()
        self._page_rows: dict[QWidget, int] = {}
        for name, page in (("Overview", self.overview), ("GPU Usage", self.gpu_usage),
                           ("Tuning", self.tuning), ("Safe points", self.safe_points),
                           ("Performance", self.performance), ("Backups", self.backups),
                           ("Service", self.service), ("Settings", self.settings_page),
                           ("Help", HelpView(str(backend.config_path)))):
            self.nav.addItem(name)
            self._page_rows[page] = self.stack.addWidget(_scrollable(page))
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.currentRowChanged.connect(self._bold_nav_item)
        self._apply_features()

        self.statusBar().showMessage("Ready")
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self.refresh)

        self._reload_config()
        self.refresh()
        self._restore_window_state()
        self._timer.start()
        if self.backend.release_check and self.settings_page.check_updates_at_start():
            QTimer.singleShot(1500, self._check_updates)

    def _apply_features(self) -> None:
        """Hide what the selected governor backend does not have (the tt governor lacks most of it)."""
        gpu_usage = self.backend.supports(FEATURE_GPU_USAGE)
        dbus = self.backend.supports(FEATURE_DBUS)
        self.tuning.set_features(frequency_range=self.backend.supports(FEATURE_FREQUENCY_RANGE), dbus=dbus,
                                 down_events=self.backend.supports(FEATURE_DOWN_EVENTS))
        self.gpu_usage.set_features(set_method=self.backend.supports(FEATURE_SET_METHOD))
        for page, shown in ((self.gpu_usage, gpu_usage), (self.performance, dbus)):
            self.nav.item(self._page_rows[page]).setHidden(not shown)
        if not gpu_usage:
            self.overview.hide_pills("mount", "fix")
            self.service.hide_fields("mount")
        if not dbus:
            self.box_perf.hide()
            self.overview.hide_pills("perf", "bus")
        self.safe_points.set_features(dbus=dbus)
        if not self.backend.release_check:
            self.service.update_button.hide()
            self.service.hide_fields("version")

    # ------------------------------------------------------------ window state
    def _restore_window_state(self) -> None:
        geometry = self.settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self._keep_on_screen()
        try:
            row = int(self.settings.value("window/page", 0))
        except (TypeError, ValueError):
            row = 0
        if not 0 <= row < self.nav.count() or self.nav.item(row).isHidden():
            row = 0
        self.nav.setCurrentRow(row)

    def _bold_nav_item(self, row: int) -> None:
        for index in range(self.nav.count()):
            item = self.nav.item(index)
            font = item.font()
            font.setBold(index == row)
            item.setFont(font)

    def _keep_on_screen(self) -> None:
        """Pull a restored window back into the visible area, so the title bar and close button stay reachable."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        frame = self.frameGeometry()
        if area.contains(frame):
            return
        width = min(frame.width(), area.width())
        height = min(frame.height(), area.height())
        x = max(area.left(), min(frame.left(), area.right() - width + 1))
        y = max(area.top(), min(frame.top(), area.bottom() - height + 1))
        if (width, height) != (frame.width(), frame.height()):
            # Shrink the client area by the same amount the frame is too large.
            self.resize(self.width() - (frame.width() - width), self.height() - (frame.height() - height))
        self.move(x, y)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Drag the window from any empty spot (header, margins), not only from the title bar."""
        handle = self.windowHandle()
        if event.button() == Qt.MouseButton.LeftButton and handle is not None and handle.startSystemMove():
            event.accept()
            return
        super().mousePressEvent(event)

    # ------------------------------------------------------------ tray
    def _set_tray(self, enabled: bool) -> None:
        if enabled and self.tray is None and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = Tray(self.windowIcon() if not self.windowIcon().isNull() else QIcon(str(LOGO_PATH)), self)
            self.tray.quit_action.triggered.connect(self.quit)
            self.tray.perf_action.toggled.connect(self._perf_enable)
            self.tray.profile_requested.connect(self._profile_apply)
            self.tray.set_profiles(self.profiles.names())
            self.tray.show()
        elif not enabled and self.tray is not None:
            self.tray.hide()
            self.tray.deleteLater()
            self.tray = None
        QApplication.instance().setQuitOnLastWindowClosed(self.tray is None)

    def _update_tray(self, snap: Snapshot) -> None:
        if self.tray is None:
            return
        t = snap.telemetry
        parts = [fmt("Load %1%", f"{t.load_percent:.0f}") if t.load_percent is not None
                else "Load N/A"]
        if t.clock_mhz is not None:
            parts.append(f"{t.clock_mhz} MHz")
        if t.temp_c is not None:
            parts.append(f"{t.temp_c:.0f} °C")
        if snap.perf.available and snap.perf.enabled:
            parts.append("performance mode")
        state = ("running" if snap.service.active
                 else ("not installed" if not snap.service.installed else "stopped"))
        self.tray.setToolTip(fmt("%1\n%2\nGovernor %3", APP_NAME, ' · '.join(parts), state))
        self.tray.set_perf(snap.perf.available, snap.perf.enabled)
        self.tray.sync_toggle()

    def _check_alerts(self, snap: Snapshot) -> None:
        self.alerts.settings = self.settings_page.alert_settings()
        for title, text in self.alerts.check(snap, time.monotonic()):
            if self.tray is not None:
                self.tray.showMessage(f"{APP_NAME}: {title}", text, QSystemTrayIcon.MessageIcon.Warning, 10000)
            self.statusBar().showMessage(f"{title}: {text}", 15000)

    def quit(self) -> None:
        """Really leave, also from the tray: run the usual close checks, then exit."""
        self._quitting = True
        if not self.isVisible():
            self.show()                 # a hidden window gets no close event
        self.close()
        if self.isVisible():            # the user canceled because of unapplied changes
            self._quitting = False
        else:
            QApplication.instance().quit()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.tray is not None and self.settings_page.minimise_on_close() and not self._quitting:
            self.hide()
            self.tray.sync_toggle()
            self.tray.showMessage(APP_NAME, "Still running in the tray; use Quit in its menu to leave.",
                                  QSystemTrayIcon.MessageIcon.Information, 3000)
            event.ignore()
            return
        if self._dirty_pages():
            answer = QMessageBox.question(self, APP_NAME,
                                          fmt("%1 unapplied changes. Close anyway?", self._dirty_pages()))
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/page", self.nav.currentRow())
        if self._test is not None:
            self._stop_test(quiet=True)     # never leave the board pinned to a test point without a watcher
        self.service.journal.stop()         # QProcess must not outlive the window
        self.updates.stop()
        if self.instance_server is not None:
            self.instance_server.close()
        super().closeEvent(event)

    # ------------------------------------------------------------ polling
    def refresh(self) -> None:
        service = self.backend.service_status()
        # busctl is only worth asking while the governor runs; otherwise the name has no owner anyway.
        perf = (self.backend.performance_state() if service.active
                else PerformanceState(error="The governor service is not running."))
        snap = Snapshot(install=self.backend.installation_status(), service=service,
                        mounted=self.backend.metrics_mount_active(), telemetry=self.backend.telemetry(),
                        saved=self.backend.read_config(), perf=perf,
                        fix_metrics_supported=self.backend.supports(FEATURE_GPU_USAGE))
        self._last_snapshot = snap
        self._check_alerts(snap)
        self.overview.update(snap)
        self.performance.update(perf, snap.saved, service.active)
        self.tuning.show_allowed_range(perf)
        self.safe_points.show_runtime(perf)
        self._update_test(perf)
        self.service.update(snap)
        self._update_boxes(snap)
        self._update_tray(snap)

    def _source_hint(self, source: str, default: str) -> str:
        name = SOURCE_NAMES.get(source)
        return name if name is not None else default

    def _update_boxes(self, snap: Snapshot) -> None:
        t = snap.telemetry
        self.box_load.set_value("N/A" if t.load_percent is None else f"{t.load_percent:.0f}%",
                                load_sensor_hint(snap) if t.load_percent is None
                                else LOAD_SOURCES.get(t.load_source, ""))
        self.box_clock.set_value("—" if t.clock_mhz is None else f"{t.clock_mhz} MHz",
                                 self._source_hint(t.clock_source, "No frequency sensor."))
        self.box_temp.set_value("—" if t.temp_c is None else f"{t.temp_c:.0f} °C",
                                self._source_hint(t.temp_source, "No temperature sensor."))
        power = t.metrics.socket_power_w if t.metrics is not None else None
        self.box_power.set_value("—" if power is None else f"{power:.1f} W",
                                 ("average_socket_power of the gpu_metrics table (whole APU); the SMU "
                                  "reports it in 24.8 fixed point, shown here in watts") if power is not None
                                 else "The gpu_metrics table reports no socket power.")
        perf = snap.perf
        if perf.available:
            no_limit = "no limit"
            low = str(perf.current_min) if perf.current_min else no_limit
            high = str(perf.current_max) if perf.current_max else no_limit
            self.box_perf.set_value("On" if perf.enabled else "Off",
                                    fmt("Current range %1–%2 MHz", low, high))
            _paint(self.box_perf, GREEN if perf.enabled else GREY)
        else:
            self.box_perf.set_value("—", perf.error or "D-Bus not reachable.")
            _paint(self.box_perf, GREY)
        if not snap.service.installed:
            state, colour = "Missing", RED
        elif snap.service.active:
            state, colour = "Running", GREEN
        elif snap.service.sub_state == "failed":
            state, colour = "Failed", RED
        else:
            state, colour = "Stopped", ORANGE
        self.box_service.set_value(state, snap.install.message)
        _paint(self.box_service, colour)

    # ------------------------------------------------------------ actions
    def _reload_config(self) -> None:
        config = self.backend.read_config()
        text = self.backend.read_config_text()
        for page in self.config_pages:
            page.load(config)
        self.gpu_usage.show_raw(text)
        self.safe_points.load(self.backend.safe_points(text))
        self.backups.load(self.backend.list_backups(), text)

    def _dirty_pages(self) -> str:
        names = self._dirty_names()
        if not names:
            return ""
        suffix = " pages have" if len(names) > 1 else " page has"
        return " and ".join(names) + suffix

    def _dirty_names(self) -> list[str]:
        pages = [*self.config_pages, self.safe_points]
        return [self.nav.item(self._page_rows[page]).text() for page in pages if page.is_dirty()]

    def _on_dirty(self, *_) -> None:
        dirty = self._dirty_pages()
        self.setWindowTitle(f"{DISPLAY_NAME}{' *' if dirty else ''}")
        self.statusBar().showMessage(
            fmt("Unapplied changes: %1", ', '.join(self._dirty_names())) if dirty else "Ready")
        # Either Apply button writes the pending edits of both pages, so both wait for valid Tuning values.
        enabled = any(page.is_dirty() for page in self.config_pages) and not self.tuning.problem.text()
        for page in self.config_pages:
            page.set_apply_enabled(enabled)

    def _collect(self) -> GovernorConfig:
        config = self.backend.read_config()
        for page in self.config_pages:
            config = page.collect(config)
        return config

    def _apply(self, restart: bool) -> None:
        config = self._collect()
        try:
            config.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid values", str(exc))
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            backup = self.backend.write_config(config, backup=True)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Could not write config.toml", str(exc))
            return
        QApplication.restoreOverrideCursor()
        self._reload_config()
        message = "Configuration applied"
        if backup:
            message += fmt(", backup: %1", backup.name)
        self._after_write(message, restart)

    def _after_write(self, message: str, restart: bool) -> None:
        if restart:
            ok, output = self.backend.service_action("restart")
            if not ok:
                QMessageBox.warning(self, "Saved, but the restart failed",
                                    "config.toml was updated, but the governor could not be restarted.\n\n"
                                    + (output or "No error text was returned."))
                message += " — restart failed"
            else:
                message += ", governor restarted"
        self.statusBar().showMessage(message, 8000)
        self.refresh()

    def _apply_safe_points(self, points: list, restart: bool) -> None:
        top = max(f for f, _ in points)
        answer = QMessageBox.warning(
            self, "Apply safe points",
            fmt(("Write %1 safe points (%2–%3 MHz) to config.toml?\n\n"
                 "The governor will scale along this curve. A point the silicon cannot hold freezes the "
                 "board under load; a backup of the current file is made first and can be restored from "
                 "the Backups page."), str(len(points)), str(points[0][0]), str(top)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            backup = self.backend.write_safe_points([tuple(p) for p in points], backup=True)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Could not write config.toml", str(exc))
            return
        QApplication.restoreOverrideCursor()
        self._reload_config()
        message = "Safe points applied"
        if backup:
            message += fmt(", backup: %1", backup.name)
        self._after_write(message, restart)

    # ------------------------------------------------------------ profiles
    def _sync_profiles(self, select: str | None = None) -> None:
        names = self.profiles.names()
        self.tuning.profiles.set_names(names, select)
        if self.tray is not None:
            self.tray.set_profiles(names)

    def handle_request(self, line: str) -> None:
        """A request from another launch (see instance.py): `show` or `profile <name>`."""
        if line == instance.SHOW:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            if self.tray is not None:
                self.tray.sync_toggle()
        elif line.startswith(instance.PROFILE):
            self.apply_profile_by_name(line[len(instance.PROFILE):].strip())

    def apply_profile_by_name(self, name: str) -> None:
        """Hotkey / command-line entry: like "Apply now", with a tray message instead of a dialog when the name
        is unknown so a mistyped shortcut does not pop a window."""
        if name not in self.profiles:
            known = ", ".join(self.profiles.names()) or "none saved"
            text = fmt("No profile named '%1' (known: %2).", name, known)
            self.statusBar().showMessage(text, 8000)
            if self.tray is not None:
                self.tray.showMessage(APP_NAME, text, QSystemTrayIcon.MessageIcon.Warning, 5000)
            return
        self._profile_apply(name)

    def _profile_config(self, name: str) -> GovernorConfig:
        return self.profiles.get(name, self.backend.read_config())

    def _profile_load(self, name: str) -> None:
        if name not in self.profiles:
            return
        config = self._profile_config(name)
        for page in self.config_pages:
            page.show_values(config)
        self.nav.setCurrentRow(self._page_rows[self.tuning])
        self.statusBar().showMessage(fmt("Profile '%1' loaded into the forms; apply to write it", name),
                                     6000)

    def _profile_apply(self, name: str) -> None:
        if name not in self.profiles:
            return
        dirty = self._dirty_pages()
        if dirty:
            answer = QMessageBox.question(
                self, "Apply profile",
                fmt("Apply '%1'? The %2 unapplied changes, they are discarded.", name, dirty),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Yes:
                return
        config = self._profile_config(name)
        try:
            config.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid profile",
                                fmt("'%1' cannot be applied: %2", name, str(exc)))
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            backup = self.backend.write_config(config, backup=True)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Could not write config.toml", str(exc))
            return
        QApplication.restoreOverrideCursor()
        self._reload_config()
        message = fmt("Profile '%1' applied", name)
        if backup:
            message += fmt(", backup: %1", backup.name)
        self._after_write(message, True)
        if self.tray is not None and not self.isVisible():
            self.tray.showMessage(APP_NAME, fmt("Profile '%1' applied, governor restarted.", name))

    def _profile_copy_command(self, name: str) -> None:
        command = profile_command(name)
        QApplication.clipboard().setText(command)
        self.tuning.profiles.hint.setText(fmt("Copied: %1", command))
        self.statusBar().showMessage(("Bind that command to a key in your desktop's shortcut settings; it "
                                      "reaches the running app and applies the profile."), 10000)

    def _profile_save(self) -> None:
        current = self.tuning.profiles.combo.currentText()
        name, ok = QInputDialog.getText(self, "Save profile", "Profile name:", text=current)
        name = clean_name(name)
        if not ok or not name:
            return
        if name in self.profiles and QMessageBox.question(
                self, "Replace profile",
                fmt("'%1' exists. Replace it with the current form values?", name)) \
                != QMessageBox.StandardButton.Yes:
            return
        self.profiles.save(name, self._collect())
        self._sync_profiles(select=name)
        self.statusBar().showMessage(fmt("Profile '%1' saved", name), 5000)

    def _profile_delete(self, name: str) -> None:
        if name not in self.profiles:
            return
        if QMessageBox.question(self, "Delete profile",
                                fmt("Delete profile '%1'?", name)) != QMessageBox.StandardButton.Yes:
            return
        self.profiles.delete(name)
        self._sync_profiles()
        self.statusBar().showMessage(fmt("Profile '%1' deleted", name), 5000)

    def _restore_backup(self, path: Path, restart: bool) -> None:
        message = fmt("Replace %1 with %2?\n\nThe current file is backed up first.",
                      self.backend.config_path.name, path.name)
        if restart:
            message += "\nThe governor is restarted afterwards."
        answer = QMessageBox.question(self, "Restore backup", message)
        if answer != QMessageBox.StandardButton.Yes:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            backup = self.backend.restore_backup(path)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Could not restore the backup", str(exc))
            return
        QApplication.restoreOverrideCursor()
        self._reload_config()
        message = fmt("Restored %1", path.name)
        if backup:
            message += fmt(", backup: %1", backup.name)
        self._after_write(message, restart)

    def _check_updates(self) -> None:
        if self.backend.release_check and self.updates.start():
            self.service.checking_update()

    def _update_checked(self, result: UpdateResult) -> None:
        self.service.show_update(result)
        if result.update_available:
            self.statusBar().showMessage(
                fmt("Governor %1 is available (installed %2); see the Service page",
                    result.latest, result.installed), 15000)
            if self.tray is not None:
                self.tray.showMessage(APP_NAME, fmt("Governor update %1 is available.", result.latest),
                                      QSystemTrayIcon.MessageIcon.Information, 5000)

    def _export_history(self) -> None:
        history = self.overview.history
        span = history.span()
        if span is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export telemetry history",
                                              str(Path.home() / default_csv_name(span[1])),
                                              "CSV files (*.csv)")
        if not path:
            return
        try:
            rows = history.write_csv(Path(path))
        except OSError as exc:
            QMessageBox.critical(self, "Could not write the CSV file", str(exc))
            return
        self.statusBar().showMessage(
            fmt("%1 samples (%2–%3) written to %4", str(rows),
                f"{span[0]:%H:%M:%S}", f"{span[1]:%H:%M:%S}", path), 8000)

    def _compare_history(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Compare with an earlier telemetry export",
                                              str(Path.home()), "CSV files (*.csv);;All files (*)")
        if not path:
            return
        try:
            samples = read_csv(Path(path))
        except (OSError, ValueError, csv.Error) as exc:
            QMessageBox.critical(self, "Could not read the CSV file", str(exc))
            return
        if not samples:
            QMessageBox.warning(self, "Nothing to compare",
                                "The file holds no samples with a readable time.")
            return
        self.overview.set_reference(samples, Path(path).name)
        self.statusBar().showMessage(
            fmt("%1 reference samples from %2 drawn dashed", str(len(samples)), Path(path).name), 8000)

    def _export_diagnostics(self) -> None:
        start = Path.home() / default_filename()
        target, _ = QFileDialog.getSaveFileName(self, "Export diagnostics", str(start),
                                                "Text files (*.txt)")
        if not target:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            report = build_report(config_path=self.backend.config_path, service_name=self.backend.service_name,
                                  gpu_devices=self.backend.gpu_devices(), package_name=self.backend.package_name,
                                  extra={"App: last telemetry": self._telemetry_summary()})
            Path(target).write_text(report)
        except OSError as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        QApplication.restoreOverrideCursor()
        QMessageBox.information(self, "Diagnostics exported",
                                fmt(("Saved to %1.\n\nRead it before attaching it to a bug report and "
                                     "remove anything you do not want to share."), target))

    def _telemetry_summary(self) -> str:
        snap = self._last_snapshot
        if snap is None:
            return "(no sample yet)"
        return f"telemetry: {snap.telemetry}\nperformance: {snap.perf}\nservice: {snap.service}"

    def _service_action(self, action: str) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        ok, output = self.backend.service_action(action)
        QApplication.restoreOverrideCursor()
        if ok:
            self.statusBar().showMessage(fmt("systemctl %1: done", action), 5000)
        else:
            QMessageBox.warning(self, fmt("systemctl %1 failed", action),
                                output or "No error text was returned.")
        self.refresh()

    # ------------------------------------------------------------ performance mode (D-Bus)
    def _bus_call(self, what: str, ok: bool, error: str, ends_test: bool = True) -> None:
        if ok and ends_test and self._test is not None:
            # Enabled, SetFixedFrequency and SetRange end test mode in the governor; drop our bookkeeping too.
            # SetLoadTarget and SetTemperatureThresholds leave it alone.
            self._end_test()
            self.safe_points.show_test(
                False, fmt("The test ended because of '%1' on the Performance page.", what))
        if ok:
            self.statusBar().showMessage(fmt("%1: done", what), 5000)
        else:
            QMessageBox.warning(self, fmt("%1 failed", what),
                                error or "The governor returned no error text.")
        self.refresh()

    def _perf_enable(self, enabled: bool) -> None:
        ok, error = self.backend.bus.set_enabled(enabled)
        what = "Performance mode on" if enabled else "Performance mode off"
        self._bus_call(what, ok, error)

    def _perf_fixed(self, mhz: int) -> None:
        ok, error = self.backend.bus.set_fixed_frequency(mhz)
        self._bus_call(fmt("Fixed frequency %1 MHz", str(mhz)), ok, error)

    def _perf_range(self, low: int, high: int) -> None:
        ok, error = self.backend.bus.set_range(low, high)
        no_limit = "no limit"
        self._bus_call(fmt("Runtime range %1–%2 MHz", str(low) if low else no_limit,
                           str(high) if high else no_limit), ok, error)

    def _perf_load(self, lower: float, upper: float) -> None:
        ok, error = self.backend.bus.set_load_target(lower, upper)
        self._bus_call(fmt("Load target %1–%2 %", f"{lower * 100:.0f}", f"{upper * 100:.0f}"),
                       ok, error, ends_test=False)

    def _perf_temperature(self, throttling: int, recovery: int) -> None:
        ok, error = self.backend.bus.set_temperature_thresholds(throttling, recovery)
        not_set = "not set"
        self._bus_call(fmt("Temperature %1 °C / %2", str(throttling), str(recovery) if recovery
                           else not_set), ok, error, ends_test=False)

    def _perf_copy(self) -> None:
        self.tuning.take_runtime(self.performance.state())
        self.nav.setCurrentRow(self._page_rows[self.tuning])
        self.statusBar().showMessage("Runtime values copied to the Tuning page; apply to save them", 6000)

    # ------------------------------------------------------------ test mode (D-Bus, root)
    def _test_point(self, frequency: int, voltage: int, seconds: int, tool: str = NO_TOOL) -> None:
        duration = fmt("for %1 s", str(seconds)) if seconds else "until you stop it"
        load = fmt(" and run %1 for load", tool) if tool != NO_TOOL else ""
        answer = QMessageBox.warning(
            self, "Test a safe point",
            fmt(("Pin the GPU to %1 MHz at %2 mV %3%4?\n\n"
                 "The governor applies this pair as given and stops its automatic scaling; thermal "
                 "throttling stays active. A point the silicon cannot hold freezes the board under load. "
                 "Nothing is written to config.toml. You will be asked for your password (the TestMode "
                 "interface is root-only)."), str(frequency), str(voltage), duration, load),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        ok, error = self.backend.bus.set_test_mode(frequency, voltage)
        QApplication.restoreOverrideCursor()
        if not ok:
            QMessageBox.warning(self, "Test mode failed",
                                error or "The governor returned no error text.")
            return
        deadline = time.monotonic() + seconds if seconds else 0.0
        self._test = (frequency, voltage, deadline)
        self._test_started = datetime.now()
        self._test_tool_exit = ""
        if seconds:
            self._test_timer.start(seconds * 1000)
        self._kernel.start()
        if tool != NO_TOOL:
            started, error = self._stress.start(tool)
            if not started:
                self._test_tool_exit = fmt("%1 could not be started (%2)", tool, error)
        self.statusBar().showMessage(fmt("Test mode: %1 MHz @ %2 mV", str(frequency), str(voltage)), 5000)
        self.refresh()

    def _end_test(self) -> None:
        """Drop the local bookkeeping of a running test: timer, load tool, kernel watch. Does not talk to the
        governor; callers do that (or the governor already ended it)."""
        self._test_timer.stop()
        self._test = None
        self._stress.stop()
        self._kernel.stop()

    def _kernel_event(self, line: str) -> None:
        if self._test is None:
            return
        # The kernel just reported amdgpu trouble: release the point now rather than wait for the freeze.
        self._stop_test(auto=True, reason="aborted after a GPU error in the kernel log")

    def _stress_finished(self, code: int, crashed: bool) -> None:
        if self._test is None:
            return
        how = "crashed" if crashed else fmt("exited with code %1", str(code))
        self._test_tool_exit = fmt("%1 %2 while the point was pinned", self._stress.tool, how)
        self.refresh()

    def _test_verdict(self, frequency: int, voltage: int, how: str) -> str:
        """One line about the test that just ended: duration, load tool, temperature and clock seen."""
        started = self._test_started
        samples = [s for s in self.overview.history if started is not None and s.time >= started]
        held = round((datetime.now() - started).total_seconds()) if started is not None else 0
        parts = [fmt("Test of %1 MHz @ %2 mV %3 after %4 s",
                     str(frequency), str(voltage), how, str(held))]
        if self._stress.tool and not self._test_tool_exit:
            parts[0] += fmt(" under %1 load", self._stress.tool)
        temps = [s.temp for s in samples if s.temp is not None]
        clocks = [s.clock for s in samples if s.clock is not None]
        seen = []
        if temps:
            seen.append(fmt("peak %1 °C", f"{max(temps):.0f}"))
        if clocks:
            seen.append(fmt("clock %1–%2 MHz", str(min(clocks)), str(max(clocks)))
                        if min(clocks) != max(clocks) else fmt("clock %1 MHz", str(clocks[0])))
        if seen:
            parts.append(", ".join(seen))
        if self._test_tool_exit:
            parts.append("⚠ " + self._test_tool_exit)
        if self._kernel.events:
            parts.append(fmt("⚠ kernel: %1", _short(self._kernel.events[0]))
                         + (fmt(" (+%1 more)", str(len(self._kernel.events) - 1))
                            if len(self._kernel.events) > 1 else ""))
        elif self._kernel.reason:
            parts.append("kernel log not watched")
        else:
            parts.append("no GPU errors in the kernel log")
        return "; ".join(parts) + ". The governor scales normally again."


    def _stop_test(self, *, auto: bool = False, quiet: bool = False, reason: str = "") -> None:
        if self._test is None:
            return
        frequency, voltage, _ = self._test
        # The kernel watch's last lines must survive into the verdict, so stop it after building the text.
        self._test_timer.stop()
        self._test = None
        self._stress.stop()
        # Any PerformanceMode call ends test mode; Enabled=false also restores the start-up range.
        ok, error = self.backend.bus.set_enabled(False)
        if quiet:
            self._kernel.stop()
            return
        how = reason or ("ended by the timer" if auto else "stopped")
        if ok:
            text = self._test_verdict(frequency, voltage, how)
            self._kernel.stop()
            self.safe_points.show_test(False, text)
            self.statusBar().showMessage(text, 8000)
            if auto and self.tray is not None:
                icon = (QSystemTrayIcon.MessageIcon.Warning if self._kernel.events
                        else QSystemTrayIcon.MessageIcon.Information)
                self.tray.showMessage(APP_NAME, text, icon, 6000)
        else:
            self._kernel.stop()
            QMessageBox.warning(self, "Could not end the test",
                                (error or "The governor returned no error text.")
                                + "\n\nRestarting the governor on the Service page also ends test mode.")
        self.refresh()

    def _update_test(self, perf: PerformanceState) -> None:
        if self._test is None:
            return
        frequency, voltage, deadline = self._test
        if not perf.available:
            # The governor went away (stopped or restarted): test mode went with it.
            self._end_test()
            self.safe_points.show_test(False, "The governor stopped; the test ended with it.")
            return
        left = (fmt(", %1 s left", str(max(0, round(deadline - time.monotonic()))))
                if deadline else "")
        if self._test_tool_exit:
            load = fmt(" ⚠ %1.", self._test_tool_exit)
        elif self._stress.running:
            load = fmt(" %1 is loading the GPU.", self._stress.tool)
        else:
            load = " Load the GPU yourself."
        watch = (" Kernel log not readable, no hang detection." if self._kernel.reason
                 else " Kernel log watched." if self._kernel.running else "")
        self.safe_points.show_test(True, fmt(("Testing %1 MHz @ %2 mV%3.%4%5 Watch "
                                              "the Overview; Stop test returns to normal scaling."),
                                              str(frequency), str(voltage), left, load, watch))


def _short(line: str, limit: int = 110) -> str:
    """A journal line without its timestamp/host prefix, cut for a status line."""
    text = line.split("kernel: ", 1)[-1].strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _paint(box: MetricBox, colour: str) -> None:
    box.set_colour(colour)
