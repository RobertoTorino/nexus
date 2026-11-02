# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's installer tests on the left, each with a tick box and its result, the live output on
the right. The suite is chosen in the header (remembered in the settings) among the suites of the checkout whose
installer tests run on this system: a Bazzite suite's .sh tests on Linux, a Windows suite's .ps1 tests on Windows."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QCloseEvent, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
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

from bc250_core.theme import GREEN, RED
from bc250_core.widgets import AppHeader, InfoButton, hint_label

from . import APP_NAME, CHECKOUT, LOGO_PATH, __version__
from .runner import InstallerTestRunner, discover_tests, suffix_here, tests_dir

SUITE_KEY = "suite"                     # the chosen suite, in the settings
ABOUT = ("Each installer test installs an app of the suite from the checkout, as its installer does on a device, "
         "and removes it again, in a temporary home: nothing of yours is touched. On Linux the tests run with "
         "fakeroot (Homebrew's on Bazzite) and fixed temporary folders under /tmp, so the same test is never run "
         "twice at once. CI runs every one of them on each push; here they run one at a time with their output.")


def suites_here(root: Path = CHECKOUT, suffix: str | None = None) -> list[str]:
    """The suites of the checkout with installer tests this system runs (their folder names, sorted)."""
    suffix = suffix or suffix_here()
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and (p / "portal" / "apps.toml").is_file() and discover_tests(tests_dir(p), suffix))


class MainWindow(QMainWindow):
    def __init__(self, root: Path = CHECKOUT, settings: QSettings | None = None, suite: str | None = None):
        """*settings* keeps the chosen suite (None: this session only); *suite* opens that suite (a folder name)."""
        super().__init__()
        self.root = root
        self.settings = settings
        self.setWindowTitle(APP_NAME)
        self.resize(1050, 700)
        self.suites = suites_here(root)
        remembered = str(settings.value(SUITE_KEY, "")) if settings is not None else ""
        self.suite = suite if suite in self.suites else remembered if remembered in self.suites else \
            self.suites[0] if self.suites else None
        self.runner: InstallerTestRunner | None = None
        self._items: dict[str, tuple[QListWidgetItem, str, QCheckBox, QLabel]] = {}

        central = QWidget()
        layout = QVBoxLayout(central)
        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        header.add_action(InfoButton(ABOUT, "What this app does"))
        self.suite_box = QComboBox()
        self.suite_box.addItems(self.suites)
        self.suite_box.setToolTip("The suite whose installer tests are listed: the suites of the checkout with "
                                  "tests that run on this system")
        if self.suite is not None:
            self.suite_box.setCurrentText(self.suite)
        self.suite_box.currentTextChanged.connect(self.choose_suite)
        header.add_second(QLabel("Suite:"))
        header.add_second(self.suite_box)
        header.add_second(hint_label("Tick the tests to run, or Run all; the output and each result show here."), 1)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.test_list = QListWidget()
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
        self.stop_button.clicked.connect(self._stop)
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
        self.choose_suite(self.suite)

    # --- the suite -------------------------------------------------------------------------------------------
    @property
    def suite_dir(self) -> Path | None:
        return self.root / self.suite if self.suite else None

    @property
    def tests_dir(self) -> Path | None:
        return tests_dir(self.suite_dir) if self.suite_dir else None

    def choose_suite(self, name: str | None) -> None:
        """The suite's tests listed, a runner for its folder; the choice remembered."""
        if self.runner is not None and self.runner.busy:
            return
        self.suite = name if name in self.suites else None
        if self.settings is not None and self.suite:
            self.settings.setValue(SUITE_KEY, self.suite)
        if self.runner is not None:
            self.runner.deleteLater()
            self.runner = None
        self.test_list.clear()
        self._items.clear()
        if self.suite is None:
            self.statusBar().showMessage(f"No suite in {self.root} has installer tests that run on this system "
                                         f"({suffix_here()} scripts in <suite>/tools/installer-tests).")
            for button in (self.run_selected_button, self.run_all_button):
                button.setEnabled(False)
            return
        self.runner = InstallerTestRunner(self.tests_dir, self.suite_dir, self)
        self.runner.output.connect(self._append_output)
        self.runner.test_started.connect(self._test_started)
        self.runner.test_finished.connect(self._test_finished)
        self.runner.run_finished.connect(self._run_finished)
        self._populate_tests()
        for button in (self.run_selected_button, self.run_all_button):
            button.setEnabled(True)
        self.statusBar().showMessage(f"{self.suite}: select tests or choose Run all.")

    def _populate_tests(self) -> None:
        for script in discover_tests(self.tests_dir):
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

    # --- the runs --------------------------------------------------------------------------------------------
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
        self._run(discover_tests(self.tests_dir))

    def _run(self, scripts: list[Path]) -> None:
        if self.runner is None:
            return
        self.output_view.clear()
        try:
            self.runner.start(scripts)
        except (OSError, RuntimeError, ValueError) as error:
            QMessageBox.critical(self, APP_NAME, str(error))
            return
        self.run_selected_button.setEnabled(False)
        self.run_all_button.setEnabled(False)
        self.suite_box.setEnabled(False)
        self.statusBar().showMessage(f"Running {len(scripts)} installer test(s)…")

    def _stop(self) -> None:
        if self.runner is not None:
            self.runner.cancel()

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
                status.setStyleSheet(f"color: {GREEN}; font-weight: bold;")
                status.setToolTip(f"{title}: passed")
            else:
                status.setText("✗")
                status.setStyleSheet(f"color: {RED}; font-weight: bold;")
                status.setToolTip(f"{title}: failed (exit code {exit_code})")
        self._append_output(f"\n== {title}: {result} ==\n")

    def _run_finished(self, cancelled: bool) -> None:
        self.run_selected_button.setEnabled(True)
        self.run_all_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.suite_box.setEnabled(True)
        self.statusBar().showMessage("Run canceled." if cancelled else "Run complete.")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override)
        if self.runner is not None and self.runner.busy:
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
