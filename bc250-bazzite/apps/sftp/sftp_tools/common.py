# SPDX-License-Identifier: GPL-3.0-or-later
"""Parts the tabs and dialogs share: message boxes, the background task thread, the connection form, the file
tables and the profile stores."""

from __future__ import annotations

import textwrap
from collections.abc import Callable
from pathlib import Path
from typing import Any

import paramiko
from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bc250_core.theme import muted

from .app_logging import ErrorCallbackHandler, get_logger
from .connection import UnknownHostKeyError, save_trusted_host_key, validate_password_requirements
from .profiles import ConnectionProfile, ConnectionProfileStore
from .settings import config_dir


class PlainMessageBox(QMessageBox):
    """Message boxes that never interpret server-supplied text as HTML."""

    @staticmethod
    def _show(icon, parent, title, text, buttons, default) -> QMessageBox.StandardButton:
        box = QMessageBox(icon, title, text, buttons, parent)
        box.setTextFormat(Qt.TextFormat.PlainText)
        if default != QMessageBox.StandardButton.NoButton:
            box.setDefaultButton(default)
        return QMessageBox.StandardButton(box.exec())

    @staticmethod
    def critical(parent, title, text, buttons=QMessageBox.StandardButton.Ok,
                 default=QMessageBox.StandardButton.NoButton):
        return PlainMessageBox._show(QMessageBox.Icon.Critical, parent, title, text, buttons, default)

    @staticmethod
    def information(parent, title, text, buttons=QMessageBox.StandardButton.Ok,
                    default=QMessageBox.StandardButton.NoButton):
        return PlainMessageBox._show(QMessageBox.Icon.Information, parent, title, text, buttons, default)

    @staticmethod
    def question(parent, title, text,
                 buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                 default=QMessageBox.StandardButton.NoButton):
        return PlainMessageBox._show(QMessageBox.Icon.Question, parent, title, text, buttons, default)


# Each tab keeps its own profile file.
SFTP_PROFILES_FILE = "profiles.json"
SERVER_PROFILES_FILE = "server-profiles.json"


def default_profile_store(file_name: str = SFTP_PROFILES_FILE) -> ConnectionProfileStore:
    return ConnectionProfileStore(config_dir() / file_name)


def trust_unknown_host(parent: QWidget, error: UnknownHostKeyError) -> bool:
    answer = PlainMessageBox.question(
        parent,
        "Trust SSH server?",
        "Do you trust this server and do you want to add this server to known_hosts?\n\n"
        f"Server: {error.known_hosts_name}\n"
        f"Host key fingerprint: {error.key.get_fingerprint().hex(':')}",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        PlainMessageBox.information(
            parent,
            "Server not trusted",
            "The server was not added to known_hosts. No connection was made.",
        )
        return False
    try:
        known_hosts = save_trusted_host_key(error)
    except (OSError, paramiko.SSHException, ValueError) as save_error:
        get_logger().error("Could not save host key", exc_info=True)
        PlainMessageBox.critical(parent, "Could not save host key", str(save_error))
        return False
    PlainMessageBox.information(
        parent,
        "Server trusted",
        f"Host key added to {known_hosts}. Retrying connection.",
    )
    return True


class ErrorIndicator(QPushButton):
    """Red dot shown after an error has been logged; click to open the log."""

    _error_logged = pyqtSignal()

    def __init__(self, log_file: Path | None) -> None:
        super().__init__()
        self.log_file = log_file
        self.setFixedSize(16, 16)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Errors found check the logs")
        self.setStyleSheet(
            "QPushButton { background-color: #c62828; border: none;"
            " border-radius: 8px; }"
        )
        self.hide()
        self._error_logged.connect(self.show)
        self.clicked.connect(self._open_log)
        handler = ErrorCallbackHandler(self._error_logged.emit)
        get_logger().addHandler(handler)
        # The logger outlives the window: a handler left behind would signal a deleted button.
        self.destroyed.connect(lambda _obj=None: get_logger().removeHandler(handler))

    def _open_log(self) -> None:
        if self.log_file is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_file)))
        self.hide()


class TaskRunner(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self, operation: Callable[[], Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.operation = operation

    def run(self) -> None:
        try:
            self.succeeded.emit(self.operation())
        except Exception as error:
            get_logger().error("Background task failed", exc_info=True)
            self.failed.emit(str(error))


PASSWORD_RULES = ("Password rules: 8 characters, 1 uppercase letter, 1 number, 1 special character "
                  "(!@#$%^&*()_+-=[]{}|;:,.<>?.)")
RULES_WIDTH = 58                # the rules, and what is missing, on two lines


class ConnectionFields(QGroupBox):
    def __init__(self, title: str = "SSH connection", rules_beside: bool = False) -> None:
        """rules_beside: the password rules always show, in a column at the right of the form (the tab places them
        with rules_beside()); else they are a row under the password, shown while one is typed."""
        super().__init__(title)
        self._rules_beside = rules_beside
        self.profile = QComboBox()
        self.profile.setEditable(True)
        self.profile.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.save_profile_button = QPushButton("Save profile")
        self.delete_profile_button = QPushButton("Delete profile")
        self.host = QLineEdit()
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(22)
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_warning = QLabel(
            "⚠ Password login is less secure. An SSH key is preferred."
        )
        self.password_warning.setStyleSheet("color: #ffb74d;")
        self.password_warning.setTextFormat(Qt.TextFormat.PlainText)
        self.password_warning.hide()
        self.password_requirements = QLabel()
        self.password_requirements.setTextFormat(Qt.TextFormat.PlainText)
        self.password_requirements.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.password_requirements.setWordWrap(True)        # may shrink: it takes no width from the form
        self._update_password_requirements()
        self.password.setToolTip(
            "Password login is less secure. Use an SSH key where possible; "
            "with a key, this field is only its passphrase."
        )
        self.password.textChanged.connect(self._update_password_warning)
        self.password.textChanged.connect(self._update_password_requirements)
        self.key_filename = QLineEdit()
        self.key_filename.textChanged.connect(self._update_password_warning)
        self.key_filename.textChanged.connect(self._update_password_requirements)   # a passphrase has no rules
        self.key_filename.setPlaceholderText("Optional; uses SSH agent/default keys if blank")
        browse_key = QPushButton("Browse…")
        browse_key.clicked.connect(self.select_key)

        key_row = QHBoxLayout()
        key_row.addWidget(self.key_filename)
        key_row.addWidget(browse_key)

        profile_row = QHBoxLayout()
        profile_row.addWidget(self.profile, 1)
        profile_row.addWidget(self.save_profile_button)
        profile_row.addWidget(self.delete_profile_button)

        form = QFormLayout(self)
        form.addRow("Saved profile", profile_row)
        form.addRow("Host", self.host)
        form.addRow("Port", self.port)
        form.addRow("User", self.username)
        form.addRow("Password / key passphrase", self.password)
        form.addRow("", self.password_warning)
        if not rules_beside:
            form.addRow("", self.password_requirements)
        form.addRow("Private key", key_row)
        self.profile.currentIndexChanged.connect(self._load_selected_profile)

    def _update_password_warning(self) -> None:
        # Only warn when a password is used without an explicit key.
        self.password_warning.setVisible(
            bool(self.password.text()) and not self.key_filename.text().strip()
        )

    def rules_beside(self, column: QVBoxLayout) -> None:
        """The password rules into the tab's column at the right of the form (rules_beside=True)."""
        assert self._rules_beside
        column.addWidget(self.password_requirements)

    def _show_rules(self, text: str, colour: str) -> None:
        self.password_requirements.setText(textwrap.fill(text, RULES_WIDTH))     # two lines, the column widens to them
        self.password_requirements.setStyleSheet(f"color: {colour};")

    def _update_password_requirements(self) -> None:
        # Beside the form: the rules in the theme's muted text until a password is typed without a key, then what
        # is missing in red or a check in green. Under the password: the same, but nothing until one is typed.
        password = self.password.text()
        if password and not self.key_filename.text().strip():
            _is_valid, error_msg = validate_password_requirements(password)
            if error_msg:       # "Password must have: at least 8 characters, at least 1 number": the list alone
                missing = error_msg.removeprefix("Password must have: ").replace("at least ", "")
                self._show_rules(f"✗ Missing: {missing}", "#e57373")
            else:
                self._show_rules("✓ The password meets the rules", "#81c784")
            self.password_requirements.show()
        else:
            self._show_rules(PASSWORD_RULES, muted())
            self.password_requirements.setVisible(self._rules_beside)

    def bind_profiles(self, store: ConnectionProfileStore) -> None:
        self.profile_store = store
        self.save_profile_button.clicked.connect(self.save_profile)
        self.delete_profile_button.clicked.connect(self.delete_profile)
        self._reload_profiles()

    def _reload_profiles(self, selected_name: str = "") -> None:
        if not hasattr(self, "profile_store"):
            return
        try:
            profiles = self.profile_store.list_profiles()
        except (OSError, ValueError) as error:
            self.delete_profile_button.setEnabled(False)
            get_logger().error("Could not read profiles: %s", error)
            PlainMessageBox.critical(self, "Could not read profiles", str(error))
            return
        self.profile.blockSignals(True)
        self.profile.clear()
        for profile in profiles:
            self.profile.addItem(profile.name, profile)
        self.profile.setCurrentIndex(-1)
        if selected_name:
            index = self.profile.findText(selected_name)
            if index >= 0:
                self.profile.setCurrentIndex(index)
        self.profile.blockSignals(False)
        if selected_name and self.profile.currentIndex() < 0:
            self.profile.setEditText(selected_name)
        self.delete_profile_button.setEnabled(bool(profiles))

    def _load_selected_profile(self, index: int) -> None:
        profile = self.profile.itemData(index)
        if not isinstance(profile, ConnectionProfile):
            return
        self.host.setText(profile.host)
        self.port.setValue(profile.port)
        self.username.setText(profile.username)
        self.key_filename.setText(profile.key_filename)
        self.password.clear()

    def save_profile(self) -> None:
        name = self.profile.currentText().strip()
        if not name:
            QMessageBox.warning(self, "Save profile", "Enter a profile name.")
            return
        host, port, username, _password, key_filename = self.values()
        if not host.strip() or not username.strip():
            QMessageBox.warning(
                self,
                "Save profile",
                "Enter a host and user name before saving the profile.",
            )
            return
        try:
            self.profile_store.save(
                ConnectionProfile(
                    name=name,
                    host=host.strip(),
                    port=port,
                    username=username.strip(),
                    key_filename=key_filename.strip(),
                )
            )
            self._reload_profiles(name)
        except (OSError, ValueError) as error:
            get_logger().error("Could not save profile: %s", error)
            PlainMessageBox.critical(self, "Could not save profile", str(error))

    def delete_profile(self) -> None:
        name = self.profile.currentText().strip()
        if not name:
            return
        try:
            self.profile_store.delete(name)
            self._reload_profiles()
        except (OSError, ValueError) as error:
            get_logger().error("Could not delete profile: %s", error)
            PlainMessageBox.critical(self, "Could not delete profile", str(error))

    def select_key(self) -> None:
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self, "Select SSH private key"
        )
        if filename:
            self.key_filename.setText(filename)

    def values(self) -> tuple[str, int, str, str, str]:
        return (
            self.host.text(),
            self.port.value(),
            self.username.text(),
            self.password.text(),
            self.key_filename.text(),
        )


def make_file_table(table_class: type[QTableWidget] = QTableWidget) -> QTableWidget:
    table = table_class(0, 4)
    table.setHorizontalHeaderLabels(["Name", "Type", "Size", "Modified"])
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
    table.setSortingEnabled(True)
    return table


def add_file_row(table: QTableWidget, name: str, kind: str, size: str, path: str, modified: str = "") -> None:
    row = table.rowCount()
    table.insertRow(row)
    item = QTableWidgetItem(name)
    item.setData(Qt.ItemDataRole.UserRole, path)
    table.setItem(row, 0, item)
    table.setItem(row, 1, QTableWidgetItem(kind))
    table.setItem(row, 2, QTableWidgetItem(size))
    table.setItem(row, 3, QTableWidgetItem(modified))


def connection_header(connection: QWidget, controls: QVBoxLayout, wide: bool = False) -> QHBoxLayout:
    """Connection form at half width, controls beside it, spare room on the right (wide: the controls take the
    spare room too, for the password rules on two lines)."""
    row = QHBoxLayout()
    row.addWidget(connection, 2)
    row.addLayout(controls, 2 if wide else 1)
    if not wide:
        row.addStretch(1)
    return row
