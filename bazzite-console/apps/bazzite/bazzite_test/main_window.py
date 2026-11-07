# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's header (the icon at 96 px, the name with the version, the state beside it, Refresh at the
right end, a status box on the second row) and the page below it."""

from __future__ import annotations

import platform

from PyQt6.QtWidgets import QMainWindow, QPushButton, QVBoxLayout, QWidget

from bc250_core.widgets import AppHeader, MetricBox, StatusText

from . import APP_NAME, LOGO_PATH, __version__


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(900, 600)
        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.state = StatusText()
        header.add_state(self.state)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Read again")
        self.refresh_button.clicked.connect(self.refresh)
        header.add_action(self.refresh_button)
        self.os_box = MetricBox("Operating system")
        self.kernel_box = MetricBox("Kernel")
        header.add_second(self.os_box)
        header.add_second(self.kernel_box)
        contents = QWidget()
        layout = QVBoxLayout(contents)
        layout.addLayout(header)
        layout.addStretch(1)
        self.setCentralWidget(contents)
        self.refresh()

    def refresh(self) -> None:
        """Reads the operating system and kernel without changing the device."""
        release = platform.freedesktop_os_release()
        self.state.set_status("Ready", "ok")
        self.os_box.set_value(release.get("PRETTY_NAME", release.get("NAME", "Unknown")))
        self.kernel_box.set_value(platform.release(), platform.machine())
