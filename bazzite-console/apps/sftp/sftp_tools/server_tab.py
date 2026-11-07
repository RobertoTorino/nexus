# SPDX-License-Identifier: GPL-3.0-or-later
"""The Server Manager tab: the sshd service of a Bazzite host, and its sshd_config; and the sshd of this computer,
so it can be the host."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import paramiko
from bc250_core.widgets import InfoButton
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from .common import (
    ConnectionFields,
    PlainMessageBox,
    TaskRunner,
    connection_header,
    default_profile_store,
    SERVER_PROFILES_FILE,
    trust_unknown_host,
)
from .connection import (
    UnknownHostKeyError,
    connect_ssh,
    read_sshd_config,
    server_status_after_action,
    validate_password_requirements,
    write_sshd_config,
)
from .local_host import LocalSshd, describe, local_status, set_local_sshd, supported
from .settings import current_settings


class ServerManagerTab(QWidget):
    status_changed = pyqtSignal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.connection = ConnectionFields("Bazzite server over SSH")
        self.connection.bind_profiles(default_profile_store(SERVER_PROFILES_FILE))
        self.connect_button = QPushButton("Connect")
        self.refresh_button = QPushButton("Refresh status")
        self.toggle_service_button = QPushButton("Start sshd")
        self.status = QLabel("Not connected")
        self.status.setWordWrap(True)
        self._sshd_active: bool | None = None
        self._ssh: paramiko.SSHClient | None = None
        self._connection_values: tuple[str, int, str, str, str] | None = None
        self._pending_connection_error: Exception | None = None
        self._worker: TaskRunner | None = None
        self._workers: set[TaskRunner] = set()
        self._local_worker: TaskRunner | None = None
        self._local_active: bool | None = None
        self.local_status = QLabel("Checking…")
        self.local_status.setWordWrap(True)
        self.local_button = QPushButton("Start sshd here")
        self.local_button.setEnabled(False)

        self.load_config_button = QPushButton("Load sshd_config")
        self.save_config_button = QPushButton("Save sshd_config")
        self.config_editor = QPlainTextEdit()
        self.config_editor.setPlaceholderText(
            "Connect, then load /etc/ssh/sshd_config to edit it."
        )
        self.config_editor.setStyleSheet("font-family: monospace;")

        actions = QVBoxLayout()
        actions.addWidget(self.connect_button)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.toggle_service_button)
        config_actions = QHBoxLayout()
        config_actions.addWidget(self.load_config_button)
        config_actions.addWidget(self.save_config_button)
        config_actions.addStretch()

        controls = QVBoxLayout()
        controls.addLayout(actions)
        controls.addWidget(QLabel("OpenSSH sshd status:"))
        controls.addWidget(self.status)
        if supported():
            local_title = QHBoxLayout()
            local_title.addWidget(QLabel("This computer as host:"))
            local_title.addWidget(InfoButton(
                "Start sshd on this computer, so another computer can connect to it. Start enables sshd, so it "
                "also starts at boot, and opens the firewall for ssh when it is closed. Stop disables sshd and "
                "leaves the firewall as it is. Both ask for your password."))
            local_title.addStretch()
            controls.addLayout(local_title)
            controls.addWidget(self.local_status)
            controls.addWidget(self.local_button)
        controls.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(connection_header(self.connection, controls))
        layout.addWidget(QLabel("Server configuration (/etc/ssh/sshd_config):"))
        layout.addLayout(config_actions)
        layout.addWidget(self.config_editor, 1)

        self.load_config_button.clicked.connect(self.load_config)
        self.save_config_button.clicked.connect(self.save_config)
        self.connect_button.clicked.connect(self.toggle_connection)
        self.refresh_button.clicked.connect(lambda: self.perform_action("status"))
        self.toggle_service_button.clicked.connect(self.toggle_service)
        self.local_button.clicked.connect(self.toggle_local_service)
        self._set_controls_connected(False)
        self.status_changed.emit("Not checked", "neutral")
        if supported():
            self._run_local(local_status)

    def _set_controls_connected(self, connected: bool) -> None:
        self.refresh_button.setEnabled(connected)
        self.load_config_button.setEnabled(connected)
        self.save_config_button.setEnabled(connected)
        self.toggle_service_button.setEnabled(
            connected and self._sshd_active is not None
        )

    def _run(self, operation: Callable[[], Any], done: Callable[[Any], None]) -> None:
        if self._worker is not None:
            return
        worker = TaskRunner(operation, self)
        self._worker = worker
        self._workers.add(worker)
        worker.succeeded.connect(lambda result: self._finish_task(done, result))
        worker.failed.connect(self._show_task_error)
        worker.finished.connect(lambda worker=worker: self._release_worker(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _release_worker(self, worker: TaskRunner) -> None:
        self._workers.discard(worker)

    @property
    def has_running_tasks(self) -> bool:
        return any(worker.isRunning() for worker in self._workers)

    def _finish_task(self, done: Callable[[Any], None], result: Any) -> None:
        self._worker = None
        done(result)

    def _show_task_error(self, message: str) -> None:
        self._worker = None
        self.connect_button.setEnabled(True)
        if (
            isinstance(self._pending_connection_error, UnknownHostKeyError)
            and self._connection_values is not None
        ):
            trusted = trust_unknown_host(
                self,
                self._pending_connection_error,
            )
            self._pending_connection_error = None
            if trusted:
                self._start_connection(self._connection_values)
                return
            self._connection_values = None
            return
        if self._ssh is not None:
            self._set_controls_connected(True)
            self.status.setText("Operation failed.")
        else:
            self.status.setText("Connection failed.")
        self.status_changed.emit("Connection/operation error", "error")
        PlainMessageBox.critical(self, "Server manager error", message)

    def toggle_connection(self) -> None:
        if self._worker is not None:
            return
        if self._ssh is not None:
            self._ssh.close()
            self._ssh = None
            self._connection_values = None
            self._pending_connection_error = None
            self._sshd_active = None
            self.connect_button.setText("Connect")
            self._set_controls_connected(False)
            self.status.setText("Not connected")
            self.status_changed.emit("Not checked", "neutral")
            return
        self._connection_values = self.connection.values()

        # Validate password requirements if password is being used
        host, port, username, password, key_filename = self._connection_values
        if password and not key_filename.strip():
            is_valid, error_msg = validate_password_requirements(password)
            if not is_valid:
                PlainMessageBox.critical(
                    self,
                    "Password Security Requirements",
                    f"Connection refused: {error_msg}\n\n"
                    "Password must have:\n"
                    "• At least 8 characters\n"
                    "• At least 1 uppercase letter\n"
                    "• At least 1 number\n"
                    "• At least 1 special character (!@#$%^&*()_+-=[]{}|;:,.<>?.)"
                )
                return

        self._start_connection(self._connection_values)

    def _start_connection(
        self, values: tuple[str, int, str, str, str]
    ) -> None:
        self.status.setText("Connecting…")
        self.status_changed.emit("Connecting…", "warning")
        self.connect_button.setEnabled(False)
        self._pending_connection_error = None

        def connect() -> paramiko.SSHClient:
            try:
                return connect_ssh(
                    *values,
                    timeout=current_settings().connection_timeout,
                    compression=current_settings().sftp_compression,
                    keepalive_interval=current_settings().keepalive_interval,
                    reconnect_count=current_settings().reconnect_count,
                    reconnect_delay=current_settings().reconnect_delay,
                )
            except UnknownHostKeyError as error:
                self._pending_connection_error = error
                raise

        self._run(connect, self._connected)

    def _connected(self, client: paramiko.SSHClient) -> None:
        self._ssh = client
        self.connect_button.setText("Disconnect")
        self.connect_button.setEnabled(True)
        self._set_controls_connected(True)
        self.status_changed.emit("Connected; checking sshd", "info")
        self.perform_action("status")

    def perform_action(self, action: str) -> None:
        if self._ssh is None or self._worker is not None:
            return
        self.status.setText(f"Running {action}…")
        if action != "status":
            self.status_changed.emit(f"Running {action}…", "warning")
        self._set_controls_connected(False)
        client = self._ssh
        self._run(
            lambda: server_status_after_action(client, action),
            self._show_status,
        )

    def load_config(self) -> None:
        if self._ssh is None or self._worker is not None:
            return
        client = self._ssh
        self.status.setText("Reading sshd_config…")
        self._set_controls_connected(False)
        self._run(lambda: read_sshd_config(client), self._config_loaded)

    def _config_loaded(self, text: str) -> None:
        self.config_editor.setPlainText(text)
        self.status.setText("Loaded sshd_config.")
        self._set_controls_connected(True)

    def save_config(self) -> None:
        if self._ssh is None or self._worker is not None:
            return
        answer = PlainMessageBox.question(
            self,
            "Save sshd_config",
            "Validate and save the configuration to the server?\n"
            "The previous file is kept as sshd_config.bak.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        client = self._ssh
        content = self.config_editor.toPlainText()
        self.status.setText("Saving sshd_config…")
        self._set_controls_connected(False)
        self._run(lambda: write_sshd_config(client, content), self._config_saved)

    def _config_saved(self, _result: Any) -> None:
        self._set_controls_connected(True)
        self.status.setText("sshd_config saved.")
        answer = PlainMessageBox.question(
            self,
            "Restart sshd",
            "Saved. Restart sshd now to apply the changes?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.perform_action("restart")

    def toggle_service(self) -> None:
        if self._sshd_active is None:
            return
        action = "stop" if self._sshd_active else "start"
        message = (f"{action.capitalize()} sshd on the remote host? Stopping it can interrupt connections; "
                   "starting it allows incoming SSH connections according to the host's configuration.")
        if PlainMessageBox.question(self, "Change remote SSH server", message) == QMessageBox.StandardButton.Yes:
            self.perform_action(action)

    def _show_status(self, result: str) -> None:
        state = result.strip().lower()
        if state == "active":
            self._sshd_active = True
        elif state in {"inactive", "failed"}:
            self._sshd_active = False
        else:
            self._sshd_active = None
        self.toggle_service_button.setText(
            "Stop sshd" if self._sshd_active else "Start sshd"
        )
        self.toggle_service_button.setEnabled(
            self._ssh is not None and self._sshd_active is not None
        )
        if state == "active":
            self.status.setText("sshd is running.")
            self.status_changed.emit("sshd is running", "success")
        elif state in {"inactive", "failed"}:
            self.status.setText("sshd is stopped.")
            self.status_changed.emit("sshd is stopped", "warning")
        else:
            self.status.setText(f"sshd state: {result or 'unknown'}")
            self.status_changed.emit(
                f"sshd state: {result or 'unknown'}",
                "warning",
            )

    def _run_local(self, operation: Callable[[], LocalSshd]) -> None:
        if self._local_worker is not None:
            return
        worker = TaskRunner(operation, self)
        self._local_worker = worker
        self._workers.add(worker)
        self.local_button.setEnabled(False)
        worker.succeeded.connect(self._show_local)
        worker.failed.connect(self._local_failed)
        worker.finished.connect(lambda worker=worker: self._release_local(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _release_local(self, worker: TaskRunner) -> None:
        self._local_worker = None
        self._workers.discard(worker)

    def _show_local(self, state: LocalSshd) -> None:
        self._local_active = state.active if state.installed else None
        self.local_status.setText(describe(state))
        self.local_button.setText("Stop sshd here" if state.active else "Start sshd here")
        self.local_button.setEnabled(state.installed)

    def _local_failed(self, message: str) -> None:
        self.local_status.setText("The change failed.")
        self.local_button.setEnabled(self._local_active is not None)
        PlainMessageBox.critical(self, "sshd on this computer", message)
        self._local_worker = None
        self._run_local(local_status)

    def toggle_local_service(self) -> None:
        if self._local_active is None:
            return
        start = not self._local_active
        message = ("Enable and start sshd on this Bazzite host, including at boot? If firewalld is active, "
                   "this may permanently open SSH in its default zone and reload the firewall. Other computers may connect."
                   if start else
                   "Stop and disable sshd on this Bazzite host? Existing connections may be interrupted. "
                   "The firewall rules are left in place.")
        if PlainMessageBox.question(self, "Change local SSH server", message) != QMessageBox.StandardButton.Yes:
            return
        self.local_status.setText("Starting sshd…" if start else "Stopping sshd…")
        self._run_local(lambda: set_local_sshd(start))
