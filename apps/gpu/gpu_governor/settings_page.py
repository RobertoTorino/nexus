# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings page: tray and login-autostart behavior of the app itself (not of the governor)."""

from __future__ import annotations

from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QGroupBox, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget

from . import fmt
from .alerts import AlertSettings
from .tray import AUTOSTART_FILE, autostart_enabled, launcher_command, set_autostart
from .widgets import hint_label, page_header


KEY_TRAY = "tray/enabled"
KEY_MINIMISE = "tray/minimise_on_close"
KEY_START_HIDDEN = "tray/autostart_hidden"
KEY_UPDATE_CHECK = "updates/check_at_start"
KEY_ALERT_TEMP = "alerts/temperature_enabled"
KEY_ALERT_TEMP_C = "alerts/temperature_c"
KEY_ALERT_THROTTLE = "alerts/throttling_enabled"
KEY_ALERT_SERVICE = "alerts/service_enabled"


class SettingsPage(QWidget):
    tray_toggled = pyqtSignal(bool)

    def __init__(self, settings: QSettings, tray_supported: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        layout = QVBoxLayout(self)
        header, _ = page_header("Settings")
        layout.addLayout(header)
        layout.addWidget(hint_label(
            "These settings concern the app, not the governor. They are stored per user."))

        tray_box = QGroupBox("System tray")
        tray_layout = QVBoxLayout(tray_box)
        self.tray = QCheckBox("Show a tray icon with the GPU load, clock and temperature in its tooltip")
        self.tray.setChecked(settings.value(KEY_TRAY, True, bool) and tray_supported)
        tray_layout.addWidget(self.tray)
        self.minimise = QCheckBox("Closing the window keeps the app running in the tray")
        self.minimise.setChecked(settings.value(KEY_MINIMISE, True, bool))
        self.minimise.toggled.connect(lambda v: settings.setValue(KEY_MINIMISE, v))
        tray_layout.addWidget(self.minimise)
        tray_layout.addWidget(hint_label(("Left-click the tray icon to show or hide the window; the menu "
                                          "also toggles performance mode (when D-Bus is reachable) and quits "
                                          "the app.")))
        if not tray_supported:
            self.tray.setEnabled(False)
            self.minimise.setEnabled(False)
            tray_layout.addWidget(hint_label(("This desktop offers no system tray (on GNOME, install the "
                                              "AppIndicator extension).")))
        layout.addWidget(tray_box)

        auto_box = QGroupBox("Start at login")
        auto_layout = QVBoxLayout(auto_box)
        self.autostart = QCheckBox("Start the app when I log in")
        self.autostart.setChecked(autostart_enabled())
        self.autostart.toggled.connect(self._autostart_changed)
        auto_layout.addWidget(self.autostart)
        self.start_hidden = QCheckBox("…hidden in the tray, without opening the window")
        self.start_hidden.setChecked(settings.value(KEY_START_HIDDEN, True, bool))
        self.start_hidden.setEnabled(tray_supported)
        self.start_hidden.toggled.connect(self._autostart_changed)
        auto_layout.addWidget(self.start_hidden)
        self.autostart_info = QLabel()
        self.autostart_info.setWordWrap(True)
        self.autostart_info.setStyleSheet("color:palette(placeholder-text);")
        auto_layout.addWidget(self.autostart_info)
        layout.addWidget(auto_box)

        update_box = QGroupBox("Governor updates")
        update_layout = QVBoxLayout(update_box)
        self.update_check = QCheckBox("Check for a newer governor release when the app starts")
        self.update_check.setChecked(settings.value(KEY_UPDATE_CHECK, True, bool))
        self.update_check.toggled.connect(lambda v: settings.setValue(KEY_UPDATE_CHECK, v))
        update_layout.addWidget(self.update_check)
        update_layout.addWidget(hint_label(
            "One request to api.github.com for the latest release of filippor/cyan-skillfish-governor, compared "
            "with the installed RPM. Nothing else is sent. The Service page has the same check as a button."))
        layout.addWidget(update_box)

        alert_box = QGroupBox("Alerts")
        alert_layout = QVBoxLayout(alert_box)
        temp_row = QHBoxLayout()
        self.alert_temp = QCheckBox("Notify when the GPU temperature reaches")
        self.alert_temp.setChecked(settings.value(KEY_ALERT_TEMP, True, bool))
        self.alert_temp.toggled.connect(lambda v: settings.setValue(KEY_ALERT_TEMP, v))
        temp_row.addWidget(self.alert_temp)
        self.alert_temp_c = QSpinBox()
        self.alert_temp_c.setRange(40, 110)
        self.alert_temp_c.setSuffix(" °C")
        self.alert_temp_c.setValue(settings.value(KEY_ALERT_TEMP_C, 80, int))
        self.alert_temp_c.valueChanged.connect(lambda v: settings.setValue(KEY_ALERT_TEMP_C, v))
        temp_row.addWidget(self.alert_temp_c)
        temp_row.addStretch(1)
        alert_layout.addLayout(temp_row)
        self.alert_throttle = QCheckBox("Notify when the governor starts throttling for temperature")
        self.alert_throttle.setChecked(settings.value(KEY_ALERT_THROTTLE, True, bool))
        self.alert_throttle.toggled.connect(lambda v: settings.setValue(KEY_ALERT_THROTTLE, v))
        alert_layout.addWidget(self.alert_throttle)
        self.alert_service = QCheckBox("Notify when the governor service stops or fails on its own")
        self.alert_service.setChecked(settings.value(KEY_ALERT_SERVICE, True, bool))
        self.alert_service.toggled.connect(lambda v: settings.setValue(KEY_ALERT_SERVICE, v))
        alert_layout.addWidget(self.alert_service)
        alert_layout.addWidget(hint_label(
            "Shown as desktop notifications through the tray icon (in the status bar when the tray is off). One "
            "message per event: a temperature alert re-arms once the GPU has cooled 5 °C below its threshold, "
            "and the same alert repeats at most every 5 minutes."))
        layout.addWidget(alert_box)
        layout.addStretch(1)
        self._minimise_enabled()
        self._describe_autostart()
        self.tray.toggled.connect(self._tray_changed)

    def tray_enabled(self) -> bool:
        return self.tray.isChecked()

    def check_updates_at_start(self) -> bool:
        return self.update_check.isChecked()

    def alert_settings(self) -> AlertSettings:
        return AlertSettings(temp_enabled=self.alert_temp.isChecked(), temp_c=self.alert_temp_c.value(),
                             throttle_enabled=self.alert_throttle.isChecked(),
                             service_enabled=self.alert_service.isChecked())

    def minimise_on_close(self) -> bool:
        return self.tray.isChecked() and self.minimise.isChecked()

    def _tray_changed(self, enabled: bool) -> None:
        self.settings.setValue(KEY_TRAY, enabled)
        self._minimise_enabled()
        self.tray_toggled.emit(enabled)

    def _minimise_enabled(self) -> None:
        self.minimise.setEnabled(self.tray.isEnabled() and self.tray.isChecked())
        self.start_hidden.setEnabled(self.tray.isEnabled() and self.tray.isChecked())

    def _autostart_changed(self, *_) -> None:
        self.settings.setValue(KEY_START_HIDDEN, self.start_hidden.isChecked())
        try:
            set_autostart(self.autostart.isChecked(),
                          start_in_tray=self.start_hidden.isChecked() and self.start_hidden.isEnabled())
        except OSError as exc:
            self.autostart_info.setText(fmt("Could not write %1: %2", str(AUTOSTART_FILE), str(exc)))
            return
        self._describe_autostart()

    def _describe_autostart(self) -> None:
        if autostart_enabled():
            self.autostart_info.setText(fmt("Entry: %1\nCommand: %2", str(AUTOSTART_FILE),
                                             launcher_command()))
        else:
            self.autostart_info.setText(fmt(
                "Writes a desktop entry to %1; nothing is installed system-wide.", str(AUTOSTART_FILE.parent)))
