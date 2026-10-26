# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's header with three states and the Connect pill, the SFTP Client and the Server Manager in
tabs."""

from __future__ import annotations

from pathlib import Path

from bc250_core.theme import BLUE, GREEN, GREY, ORANGE, PURPLE, RED
from bc250_core.widgets import AppHeader, MetricBox, Pill
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QLabel, QMainWindow, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from . import APP_NAME, LOGO_PATH, __version__
from .client_tab import SftpClientTab
from .common import ErrorIndicator, PlainMessageBox
from .formatting import local_platform_name
from .server_tab import ServerManagerTab
from .settings import current_settings, log_file
from .settings_dialog import SettingsDialog

# The tabs report their state as one of these tones; the header box takes its color.
TONE_COLOURS = {"neutral": GREY, "info": BLUE, "success": GREEN, "warning": ORANGE, "error": RED}


def set_state(box: MetricBox, value: str, tone: str) -> None:
    box.set_value(value, value)
    box.set_colour(TONE_COLOURS[tone])


class MainWindow(QMainWindow):
    def __init__(self, log_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 820)
        self.sftp_tab = SftpClientTab()
        self.server_tab = ServerManagerTab()

        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.error_indicator = ErrorIndicator(log_path or log_file())
        header.add_action(self.error_indicator)
        self.local_box = MetricBox("Local", PURPLE)
        self.local_box.set_value(local_platform_name())
        self.sftp_box = MetricBox("SFTP")
        self.server_box = MetricBox("Bazzite SSH")
        for box in (self.local_box, self.sftp_box, self.server_box):
            header.add_second(box)
        # Connect is a pill beside the states (owner, 26-10-2026): it connects the SFTP Client with the fields in its
        # tab, and reads Disconnect while connected.
        self.connect_pill = Pill("Connect", "SFTP client",
                                 "Connect to the host filled in under SFTP Client; click again to disconnect.")
        self.connect_pill.setSizePolicy(self.sftp_box.sizePolicy())        # as wide as the boxes beside it
        header.add_second(self.connect_pill)
        self.connect_pill.clicked.connect(self.sftp_tab.toggle_connection)
        self.sftp_tab.connect_changed.connect(self._show_connect)
        self.sftp_tab.status_changed.connect(lambda value, tone: set_state(self.sftp_box, value, tone))
        self.server_tab.status_changed.connect(lambda value, tone: set_state(self.server_box, value, tone))
        set_state(self.sftp_box, "Disconnected", "neutral")
        set_state(self.server_box, "Not checked", "neutral")

        tabs = QTabWidget()
        tabs.addTab(self.sftp_tab, "SFTP Client")
        tabs.addTab(self.server_tab, "Server Manager")
        contents = QWidget()
        layout = QVBoxLayout(contents)
        layout.addLayout(header)
        layout.addWidget(tabs, 1)
        self.setCentralWidget(contents)
        settings_action = self.menuBar().addMenu("&Edit").addAction("&Settings…")
        settings_action.triggered.connect(self.open_settings)
        self.speed_label = QLabel("Idle")
        self.statusBar().addPermanentWidget(self.speed_label)
        self.sftp_tab.queue.speed_changed.connect(self.speed_label.setText)

    def _show_connect(self, text: str, enabled: bool) -> None:
        self.connect_pill.set_value(text, self.connect_pill.toolTip())
        self.connect_pill.setEnabled(enabled)

    def open_settings(self) -> None:
        hidden_files = current_settings().view_hidden_files
        if SettingsDialog(self).exec():
            self.sftp_tab.settings_changed(current_settings().view_hidden_files != hidden_files)

    def closeEvent(self, event: QCloseEvent) -> None:
        sftp_tab = self.sftp_tab
        busy = (
            sftp_tab.has_running_tasks
            or self.server_tab.has_running_tasks
            or bool(sftp_tab.queue.jobs_in("queued"))
        )
        if busy:
            answer = PlainMessageBox.question(
                self,
                "Close application",
                "This will disconnect you from the server and cancels all current "
                "transfers, are you sure?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        sftp_tab.queue.shutdown()
        if sftp_tab._sftp is not None:
            sftp_tab._sftp.close()
        for ssh in (sftp_tab._ssh, self.server_tab._ssh):
            if ssh is not None:
                ssh.close()
        event.accept()
