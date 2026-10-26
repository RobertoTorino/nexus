# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent, QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import APP_ICON_PATH, APP_NAME, SUITE_ROOT, TESTS_DIR, __version__
from .runner import InstallerTestRunner, discover_tests


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1050, 700)

        self.runner = InstallerTestRunner(TESTS_DIR, SUITE_ROOT, self)
        self.runner.output.connect(self._append_output)
        self.runner.test_started.connect(self._test_started)
        self.runner.test_finished.connect(self._test_finished)
        self.runner.run_finished.connect(self._run_finished)
        self._items: dict[str, tuple[QListWidgetItem, str, QCheckBox, QLabel]] = {}

        central = QWidget()
        layout = QVBoxLayout(central)
        # The icon spans the title and the line below it, like every app of the suite.
        header = QHBoxLayout()
        header.setSpacing(14)
        self.header_icon = QLabel()
        pixmap = QPixmap(str(APP_ICON_PATH))
        if not pixmap.isNull():
            self.header_icon.setPixmap(
                pixmap.scaled(
                    96,
                    96,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self.header_icon.setFixedSize(96, 96)
        self.header_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_icon.setAccessibleName(f"{APP_NAME} icon")
        header.addWidget(self.header_icon)
        header_right = QVBoxLayout()
        header_right.setSpacing(6)
        title = QLabel(f"{APP_NAME}  <span style='color:#9aa0a6; font-size:14px;'>v{__version__}</span>")
        title.setStyleSheet("font-size:24px; font-weight:800;")
        header_right.addWidget(title)
        header_right.addWidget(QLabel("Choose installer checks to run. Output and exit status appear here."))
        header.addLayout(header_right, 1)
        layout.addLayout(header)

        warning = QLabel(
            "Tests use fakeroot and fixed temporary directories under /tmp. "
            "Do not run the same installer test concurrently."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("padding: 8px; border: 1px solid palette(mid); border-radius: 4px;")
        layout.addWidget(warning)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.test_list = QListWidget()
        self._populate_tests()
        left_layout.addWidget(self.test_list, 1)

        selection_buttons = QHBoxLayout()
        select_all = QPushButton("Select all")
        select_all.clicked.connect(self._select_all)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear_selection)
        selection_buttons.addWidget(select_all)
        selection_buttons.addWidget(clear)
        left_layout.addLayout(selection_buttons)

        run_buttons = QHBoxLayout()
        self.run_selected_button = QPushButton("Run selected")
        self.run_selected_button.clicked.connect(self._run_selected)
        self.run_all_button = QPushButton("Run all")
        self.run_all_button.clicked.connect(self._run_all)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.runner.cancel)
        run_buttons.addWidget(self.run_selected_button)
        run_buttons.addWidget(self.run_all_button)
        run_buttons.addWidget(self.stop_button)
        left_layout.addLayout(run_buttons)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Live output"))
        self.output_view = QPlainTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.document().setMaximumBlockCount(20000)
        right_layout.addWidget(self.output_view, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Select tests or choose Run all.")

    def _populate_tests(self) -> None:
        for script in discover_tests(TESTS_DIR):
            title = script.stem.replace("-", " ").title()
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, script)
            item.setToolTip(script.name)
            self.test_list.addItem(item)
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 0, 8, 0)
            checkbox = QCheckBox(title)
            checkbox.setToolTip(script.name)
            status = QLabel()
            status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            status.setFixedWidth(28)
            status.setAccessibleName(f"{title} result")
            row_layout.addWidget(checkbox, 1)
            row_layout.addWidget(status)
            item.setSizeHint(row.sizeHint())
            self.test_list.setItemWidget(item, row)
            self._items[script.name] = item, title, checkbox, status

    def _select_all(self) -> None:
        for _item, _title, checkbox, _status in self._items.values():
            checkbox.setChecked(True)

    def _clear_selection(self) -> None:
        for _item, _title, checkbox, _status in self._items.values():
            checkbox.setChecked(False)

    def _run_selected(self) -> None:
        scripts = [
            item.data(Qt.ItemDataRole.UserRole)
            for item, _title, checkbox, _status in self._items.values()
            if checkbox.isChecked()
        ]
        if not scripts:
            QMessageBox.information(self, APP_NAME, "Select one or more installer tests first.")
            return
        self._run(scripts)

    def _run_all(self) -> None:
        self._run(discover_tests(TESTS_DIR))

    def _run(self, scripts: list[Path]) -> None:
        self.output_view.clear()
        try:
            self.runner.start(scripts)
        except (OSError, RuntimeError, ValueError) as error:
            QMessageBox.critical(self, APP_NAME, str(error))
            return
        self.run_selected_button.setEnabled(False)
        self.run_all_button.setEnabled(False)
        self.statusBar().showMessage(f"Running {len(scripts)} installer test(s)…")

    def _append_output(self, text: str) -> None:
        self.output_view.moveCursor(QTextCursor.MoveOperation.End)
        self.output_view.insertPlainText(text)
        self.output_view.ensureCursorVisible()

    def _test_started(self, name: str) -> None:
        _item, title, _checkbox, _status = self._items[name]
        self.stop_button.setEnabled(True)
        self.statusBar().showMessage(f"Running {title}…")

    def _test_finished(self, name: str, exit_code: int, cancelled: bool) -> None:
        _item, title, _checkbox, status = self._items[name]
        result = "CANCELED" if cancelled else "PASS" if exit_code == 0 else f"FAIL ({exit_code})"
        if not cancelled:
            if exit_code == 0:
                status.setText("✓")
                status.setStyleSheet("color: #2e7d32; font-weight: bold;")
                status.setToolTip(f"{title}: passed")
            else:
                status.setText("✗")
                status.setStyleSheet("color: #c62828; font-weight: bold;")
                status.setToolTip(f"{title}: failed (exit code {exit_code})")
        self._append_output(f"\n== {title}: {result} ==\n")

    def _run_finished(self, cancelled: bool) -> None:
        self.run_selected_button.setEnabled(True)
        self.run_all_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.statusBar().showMessage("Run canceled." if cancelled else "Run complete.")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.runner.busy:
            answer = QMessageBox.question(
                self,
                APP_NAME,
                "An installer test is running. Stop it and close?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.runner.shutdown()
        event.accept()
