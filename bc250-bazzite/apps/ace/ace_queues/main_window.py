# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window: the four steps (build, install, test, use) with their state and buttons, and the output of the
step that runs. Every step runs bc250-ace-queues.sh; the ones that change the system go through polkit (pkexec)."""

from __future__ import annotations

import subprocess
from html import escape
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (QApplication, QGridLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
                             QVBoxLayout, QWidget)

from bc250_core import SUITE_MANUAL_URL, window_title
from bc250_core import __version__ as CORE_VERSION
from bc250_core.settings import SettingsStore
from bc250_core.widgets import AppHeader, StatusText, Terminal, accent_button, hint_label, set_button_active

from . import APP_NAME, INFO, LOGO_PATH, SCRIPT, __version__
from .status import Status, parse, verdict

MANUAL_URL = f"{SUITE_MANUAL_URL}apps/ace/"
NOT_AUTHORISED = (126, 127)             # pkexec: the password dialog was canceled or refused

# What runs, by action: (arguments, needs root, text while it runs)
ACTIONS = {
    "build": (["--build"], False, "Building the driver (20 to 40 minutes)…"),
    "install": (["--install-driver"], True, "Installing the driver…"),
    "remove": (["--remove-driver"], True, "Removing the driver…"),
    "test": (["--test"], False, "Testing the ACE queues…"),
    "all-on": (["--all-apps", "on"], True, "Switching on for all apps…"),
    "all-off": (["--all-apps", "off"], True, "Switching off for all apps…"),
}


class AceSettings(SettingsStore):
    DEFAULTS: dict = {}


class MainWindow(QMainWindow):
    def __init__(self, script: Path = SCRIPT):
        super().__init__()
        self.resize(900, 700)
        self.script = script
        self.settings = AceSettings(INFO, self)
        self.status = Status()
        self.action = ""
        self._output = ""
        self.process: QProcess | None = None

        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.pill = StatusText()
        header.add_state(self.pill)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Read the state again")
        self.refresh_button.clicked.connect(self.refresh)
        header.add_action(self.refresh_button)

        self.system = QLabel()
        self.system.setWordWrap(True)
        header.add_second(self.system, 1)            # board, kernel and Mesa
        intro = hint_label(
            "Games use the BC-250's dedicated compute queues (async compute) through a patched RADV driver. It is "
            "built on this board and installed beside the system Mesa, which stays as it is. Games use it only "
            "with their launch options, or every app after you switch that on, and only after the test passed on "
            f"the running kernel. <a href='{MANUAL_URL}'>Manual</a>")

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        self.build_state, self.install_state, self.test_state, self.use_state = (self._state_label() for _ in range(4))
        self.build_button = accent_button("Build", "Build the patched RADV in a podman container")
        self.build_button.clicked.connect(self.on_build)
        self.install_button = QPushButton("Install")
        self.install_button.setToolTip("Install the build in /usr/local/lib/bc250-ace-queues (asks for your password)")
        self.install_button.clicked.connect(self.on_install)
        self.remove_button = QPushButton("Remove")
        self.remove_button.setToolTip("Remove the driver; every app uses the system Mesa again")
        self.remove_button.clicked.connect(self.on_remove)
        self.test_button = QPushButton("Run test")
        self.test_button.setToolTip("Run the ACE queue test with the installed driver (about a minute)")
        self.test_button.clicked.connect(self.on_test)
        self.copy_button = QPushButton("Copy launch options")
        self.copy_button.setToolTip("Copy the Steam launch options for a game to the clipboard")
        self.copy_button.clicked.connect(self.copy_launch_options)
        self.all_button = QPushButton("All apps: on")
        self.all_button.setToolTip("Every app uses the patched driver, without launch options (asks for your "
                                   "password; applies after you log out and back in)")
        self.all_button.clicked.connect(self.on_all_apps)
        rows = [("1. Build", self.build_state, [self.build_button]),
                ("2. Install", self.install_state, [self.install_button, self.remove_button]),
                ("3. Test", self.test_state, [self.test_button]),
                ("4. Use", self.use_state, [self.copy_button, self.all_button])]
        # One line per step: name, state and its buttons centered on the row. Every button has the size of the
        # widest plain one (Build too), in two columns on the right (a single button in the right one), so they
        # line up.
        everything = [b for _, _, buttons in rows for b in buttons]
        width = max(b.sizeHint().width() for b in everything)
        height = max(b.sizeHint().height() for b in everything if b is not self.build_button)
        centre = Qt.AlignmentFlag.AlignVCenter
        for row, (name, state, buttons) in enumerate(rows):
            label = QLabel(name)
            label.setStyleSheet("font-weight:700;")
            # The labels fill their cell and center their own text: a word-wrapped label added with an alignment
            # gets no height for its second line.
            for text in (label, state):
                text.setAlignment(Qt.AlignmentFlag.AlignLeft | centre)
            grid.addWidget(label, row, 0)
            grid.addWidget(state, row, 1)
            for column, button in zip((3, 2), reversed(buttons)):
                button.setFixedSize(width, height)
                grid.addWidget(button, row, column, centre)
            grid.setRowMinimumHeight(row, height)

        self.running = QLabel()
        self.running.setStyleSheet("font-weight:600;")
        self.output = Terminal()
        self.output.setPlaceholderText("The output of each step appears here.")

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(header)
        lay.addWidget(intro)
        lay.addSpacing(6)
        lay.addLayout(grid)
        lay.addSpacing(6)
        lay.addWidget(self.running)
        lay.addWidget(self.output, 1)
        version = QLabel(f"{APP_NAME} {__version__} · core {CORE_VERSION} · the system Mesa is never changed")
        version.setStyleSheet("color:palette(placeholder-text);")
        lay.addWidget(version, 0, Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(central)

        geometry = self.settings.window_state("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.refresh()

    @staticmethod
    def _state_label() -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    # --- State ------------------------------------------------------------------------------------------------

    def refresh(self) -> None:
        try:
            done = subprocess.run(["bash", str(self.script), "--status"], capture_output=True, text=True, timeout=30)
            text = done.stdout
        except (OSError, subprocess.SubprocessError) as exc:
            text = ""
            self.output.setPlainText(f"Could not read the state: {exc}")
        self.set_status(parse(text))

    def set_status(self, status: Status) -> None:
        self.status = status
        s = status
        pill, kind, tip = verdict(s)
        self.pill.set_status(pill, kind, tip)
        self.system.setText(f"<b>{escape(s.get('Board') or '?')}</b> · kernel {escape(s.get('Kernel') or '?')} · "
                            f"system Mesa {escape(s.system_mesa or '?')}")

        if not s.built:
            build = "Not built. Downloads the Mesa source (checked against its signature) and the build tools, " \
                    "then builds in a Fedora container: 20 to 40 minutes."
        else:
            build = f"Built: {escape(s.get('Build'))}."
            if s.build_outdated:
                build += f" <b>The system has Mesa {escape(s.system_mesa)} now:</b> build again to keep up with it."
        self.build_state.setText(build)

        if not s.installed:
            install = "Not installed." if s.built else "Not installed: build it first."
        else:
            install = f"Installed: {escape(s.get('Driver')[len('installed, '):])}, in /usr/local/lib/bc250-ace-queues."
            if s.install_outdated:
                install += " <b>A newer build is waiting:</b> install it."
        self.install_state.setText(install)

        if not s.installed:
            test = "Needs the installed driver."
        elif s.tested:
            test = f"<span style='color:#2e7d32'><b>Passed</b></span> {escape(s.get('Test')[len('passed '):])}."
        elif s.test_failed:
            test = f"<span style='color:#c62828'><b>Failed</b></span> {escape(s.get('Test')[len('failed '):])}."
        else:
            test = f"{escape(s.get('Test')).capitalize()}. Games only use the driver once it passed on this kernel."
        self.test_state.setText(test)

        use = (f"Per game, Steam launch options: <code>{escape(s.launch_options)}</code><br>"
               "Started without a passed test on this kernel, the game uses the system Mesa.")
        off_note = s.get("All apps").removeprefix("off").strip(" ()")
        if s.all_apps:
            use += "<br><b>On for all apps</b> (after a log-out and back in). Flatpak apps keep their own driver."
        elif off_note:
            use += f"<br>All apps: off ({escape(off_note)})."
        self.use_state.setText(use)
        self._fit_states()
        self._update_buttons()

    def _fit_states(self) -> None:
        """Each state text keeps the height its lines need at its width. Qt leaves wrapped text out of a window's
        minimum height, so a short window would otherwise squeeze a second line out of sight."""
        for label in (self.build_state, self.install_state, self.test_state, self.use_state):
            label.setMinimumHeight(label.heightForWidth(max(label.width(), 300)))

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._fit_states()                  # a narrower window wraps into more lines

    def _update_buttons(self) -> None:
        s, idle = self.status, self.process is None
        self.refresh_button.setEnabled(idle)
        self.build_button.setEnabled(idle and s.is_bc250)
        self.install_button.setEnabled(idle and s.built and (not s.installed or s.install_outdated))
        self.remove_button.setEnabled(idle and s.installed)
        self.test_button.setEnabled(idle and s.installed)
        self.copy_button.setEnabled(s.installed)
        self.all_button.setText("All apps: off" if s.all_apps else "All apps: on")
        self.all_button.setEnabled(idle and (s.all_apps or (s.installed and s.tested)))
        set_button_active(self.all_button, s.all_apps)

    # --- Actions ----------------------------------------------------------------------------------------------

    def _ask(self, title: str, text: str) -> bool:
        answer = QMessageBox.question(self, window_title(title), text)
        return answer == QMessageBox.StandardButton.Yes

    def on_build(self) -> None:
        if self._ask("Build", "Build the patched RADV for Mesa "
                     f"{self.status.system_mesa or '(the system version)'}?\n\n"
                     "It runs as your user in a Fedora container (podman) and downloads several hundred MB: the "
                     "Mesa source and the build tools. It takes 20 to 40 minutes; nothing on the system changes."):
            self.run("build")

    def on_install(self) -> None:
        if self._ask("Install", "Install the patched RADV?\n\n"
                     "It goes to /usr/local/lib/bc250-ace-queues, beside the system Mesa, which stays as it is. "
                     "Nothing uses it until the test has passed and you give a game the launch options. "
                     "Remove takes it out again."):
            self.run("install")

    def on_remove(self) -> None:
        if self._ask("Remove", "Remove the patched RADV? Every app uses the system Mesa again.\n\n"
                     f"Also remove \"{self.status.launch_options}\" from the launch options of your games: without "
                     "the driver they do not start."):
            self.run("remove")

    def on_test(self) -> None:
        self.run("test")

    def on_all_apps(self) -> None:
        if self.status.all_apps:
            self.run("all-off")
            return
        if self._ask("All apps", "Let every app use the patched RADV, the desktop included?\n\n"
                     "It applies after you log out and back in. When the kernel or the driver changes, it switches "
                     "itself off at the next boot, until the test passes again.\n\n"
                     "If the desktop does not come back: press Ctrl+Alt+F3, log in and run\n"
                     "sudo rm /etc/environment.d/90-bc250-ace-queues.conf\nthen reboot."):
            self.run("all-on")

    def copy_launch_options(self) -> None:
        QApplication.clipboard().setText(self.status.launch_options)
        self.running.setText("Launch options copied: paste them into a game's Properties → Launch options in Steam.")

    def command(self, action: str) -> list[str]:
        args, root, _ = ACTIONS[action]
        cmd = ["bash", str(self.script), *args]
        return ["pkexec", "/usr/bin/bash", *cmd[1:]] if root else cmd

    def run(self, action: str) -> None:
        if self.process is not None:
            return
        self.action = action
        self._output = ""
        self.output.set_text("")
        self.running.setText(ACTIONS[action][2])
        cmd = self.command(action)
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._error)
        self.process = process
        self._update_buttons()
        process.start(cmd[0], cmd[1:])

    def _read(self) -> None:
        if self.process is None:
            return
        self._output += bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace")
        self.output.set_text(self._output)

    def _finished(self, code: int, _status=None) -> None:
        root = ACTIONS[self.action][1]
        if code == 0:
            self.running.setText("Done.")
        elif root and code in NOT_AUTHORISED:
            self.running.setText("Not authorized: the password dialog was canceled or refused.")
        else:
            self.running.setText(f"Stopped with exit code {code}; see the output.")
        self.process = None
        self.refresh()

    def _error(self, _error) -> None:
        if self.process is not None and self.process.error() == QProcess.ProcessError.FailedToStart:
            self.running.setText(f"Could not start: {self.process.errorString()}")
            self.process = None
            self._update_buttons()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override)
        if self.process is not None:
            if not self._ask("Close", "A step is still running. Stop it and close?"):
                event.ignore()
                return
            self.process.terminate()            # the build script then also stops its container
            if not self.process.waitForFinished(15000):
                self.process.kill()
        self.settings.set_window_state("geometry", self.saveGeometry())
        self.settings.sync()
        super().closeEvent(event)
