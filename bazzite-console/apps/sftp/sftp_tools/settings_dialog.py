# SPDX-License-Identifier: GPL-3.0-or-later
"""The settings dialog (Edit, Settings)."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .app_logging import get_logger, set_log_level
from .common import PlainMessageBox
from .settings import LOG_LEVELS, OVERWRITE_MODES, AppSettings, SizeFormat, apply_settings, current_settings


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        settings = current_settings()
        self.local_folder = QLineEdit(settings.default_local_folder)
        self.local_folder.setPlaceholderText("Home folder")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 300)
        self.timeout.setSuffix(" s")
        self.timeout.setValue(settings.connection_timeout)
        self.log_level = QComboBox()
        self.log_level.addItems(LOG_LEVELS)
        self.log_level.setCurrentText(settings.log_level)

        self.logging_max_mb = QSpinBox()
        self.logging_max_mb.setRange(1, 100)
        self.logging_max_mb.setSuffix(" MB")
        self.logging_max_mb.setValue(settings.logging_max_mb)
        self.logging_max_mb.setToolTip(
            "Maximum log file size before rotation. Log is kept in 3 rolling backup files."
        )

        self.overwrite = QComboBox()
        for mode, label in zip(
            OVERWRITE_MODES, ("Ask", "Overwrite", "Skip"), strict=True
        ):
            self.overwrite.addItem(label, mode)
        self.overwrite.setCurrentIndex(OVERWRITE_MODES.index(settings.overwrite_mode))
        self.speed_limit = QSpinBox()
        self.speed_limit.setRange(0, 10_000_000)
        self.speed_limit.setSuffix(" KB/s")
        self.speed_limit.setSpecialValueText("Unlimited")
        self.speed_limit.setValue(settings.speed_limit_kbps)
        self.keepalive = QSpinBox()
        self.keepalive.setRange(1, 300)
        self.keepalive.setSuffix(" s")
        self.keepalive.setValue(settings.keepalive_interval)

        self.reconnect_count = QSpinBox()
        self.reconnect_count.setRange(0, 10)
        self.reconnect_count.setValue(settings.reconnect_count)
        self.reconnect_count.setToolTip("Number of times to retry a failed connection (0 = no retries)")

        self.reconnect_delay = QSpinBox()
        self.reconnect_delay.setRange(1, 60)
        self.reconnect_delay.setSuffix(" s")
        self.reconnect_delay.setValue(settings.reconnect_delay)
        self.reconnect_delay.setToolTip("Delay between reconnection attempts")

        self.hidden_files = QCheckBox("Show hidden files")
        self.hidden_files.setChecked(settings.view_hidden_files)

        self.size_format = QComboBox()
        self.size_format.addItems(("Auto (1024-based)", "Binary (1024-based)", "Decimal (1000-based)"))
        size_format_map = {"auto": 0, "binary": 1, "decimal": 2}
        self.size_format.setCurrentIndex(size_format_map.get(settings.size_format.format, 0))

        self.size_decimal = QSpinBox()
        self.size_decimal.setRange(0, 3)
        self.size_decimal.setSuffix(" decimals")
        self.size_decimal.setValue(settings.size_format.decimal_places)

        self.size_separator = QCheckBox("Use thousands separator")
        self.size_separator.setChecked(settings.size_format.thousands_separator)

        self.sound_on_complete = QCheckBox("Beep when transfer completes")
        self.sound_on_complete.setChecked(settings.sound_on_transfer_complete)

        self.filter_invalid_chars = QCheckBox("Filter invalid Windows filename characters")
        self.filter_invalid_chars.setChecked(settings.filter_invalid_chars)
        self.filter_invalid_chars.setToolTip(
            "Replaces invalid characters (: ? < > | * \") with a safe character when downloading files"
        )
        self.char_replacement = QLineEdit(settings.invalid_char_replacement)
        self.char_replacement.setMaxLength(1)
        self.char_replacement.setMaximumWidth(50)
        self.char_replacement.setToolTip("Single character to replace invalid characters with")

        self.sftp_compression = QCheckBox("Enable SFTP compression")
        self.sftp_compression.setChecked(settings.sftp_compression)
        self.sftp_compression.setToolTip(
            "Enables zlib compression on SFTP connections to improve throughput, especially on slow networks"
        )

        self.queue_autoclear = QCheckBox("Auto-clear successful transfers")
        self.queue_autoclear.setChecked(settings.queue_autoclear)
        self.queue_autoclear.setToolTip(
            "Automatically removes completed transfers from the queue list"
        )

        self.preserve_timestamps = QCheckBox("Preserve file modification times")
        self.preserve_timestamps.setChecked(settings.preserve_timestamps)
        self.preserve_timestamps.setToolTip(
            "Sets downloaded files' modification time to match remote files"
        )

        self.date_format = QComboBox()
        self.date_format.addItems(("YYYY-MM-DD", "MM/DD/YYYY", "DD/MM/YYYY"))
        self.date_format.setCurrentText(settings.date_format)
        self.date_format.setToolTip("Date format for file modification times")

        self.time_format = QComboBox()
        self.time_format.addItems(("HH:MM:SS", "HH:MM"))
        self.time_format.setCurrentText(settings.time_format)
        self.time_format.setToolTip("Time format for file modification times")

        folder_row = QHBoxLayout()
        folder_row.addWidget(self.local_folder, 1)
        folder_row.addWidget(browse)
        form = QFormLayout()
        form.addRow("Default local folder", folder_row)
        form.addRow("Connection timeout", self.timeout)
        form.addRow("TCP keep-alive", self.keepalive)
        form.addRow("Reconnect attempts", self.reconnect_count)
        form.addRow("Reconnect delay", self.reconnect_delay)
        form.addRow(self.hidden_files)
        form.addRow("Log level", self.log_level)
        form.addRow("Max log file size", self.logging_max_mb)
        form.addRow("If file exists", self.overwrite)
        form.addRow("Speed limit", self.speed_limit)
        form.addRow("File size format", self.size_format)
        form.addRow("Size decimals", self.size_decimal)
        form.addRow(self.size_separator)
        form.addRow(self.sound_on_complete)
        form.addRow(self.filter_invalid_chars)
        replacement_row = QHBoxLayout()
        replacement_row.addWidget(QLabel("Replacement character:"))
        replacement_row.addWidget(self.char_replacement)
        replacement_row.addStretch()
        form.addRow("", replacement_row)
        form.addRow(self.sftp_compression)
        form.addRow(self.queue_autoclear)
        form.addRow(self.preserve_timestamps)
        form.addRow("Date format", self.date_format)
        form.addRow("Time format", self.time_format)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Default local folder", self.local_folder.text()
        )
        if folder:
            self.local_folder.setText(folder)

    def _save(self) -> None:
        size_format_map = {0: "auto", 1: "binary", 2: "decimal"}

        # Validate replacement character
        replacement = self.char_replacement.text().strip()
        if not replacement:
            replacement = "_"

        new = AppSettings(
            self.local_folder.text().strip(),
            self.timeout.value(),
            self.log_level.currentText(),
            self.overwrite.currentData(),
            self.speed_limit.value(),
            self.keepalive.value(),
            self.reconnect_count.value(),
            self.reconnect_delay.value(),
            self.hidden_files.isChecked(),
            SizeFormat(
                format=size_format_map.get(self.size_format.currentIndex(), "auto"),
                thousands_separator=self.size_separator.isChecked(),
                decimal_places=self.size_decimal.value(),
            ),
            self.sound_on_complete.isChecked(),
            self.filter_invalid_chars.isChecked(),
            replacement,
            self.sftp_compression.isChecked(),
            self.queue_autoclear.isChecked(),
            self.preserve_timestamps.isChecked(),
            self.date_format.currentText(),
            self.time_format.currentText(),
            self.logging_max_mb.value(),
        )
        try:
            apply_settings(new)
        except (OSError, ValueError) as error:
            get_logger().error("Could not save settings: %s", error)
            PlainMessageBox.critical(self, "Could not save settings", str(error))
            return
        set_log_level(new.log_level)
        self.accept()
