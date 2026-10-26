# SPDX-License-Identifier: GPL-3.0-or-later
"""Reusable widgets: test buttons, terminal, hints panel, sudo and log dialogs."""

from __future__ import annotations

import html
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QIcon, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QSplitter, QStyle, QVBoxLayout,
    QWidget,
)

# The logo and the rounded tooltip (Wayland-safe) are shared with the other suite apps.
from bc250_core.widgets import ClickableLogo, RoundedToolTip, hide_tooltip, show_tooltip  # noqa: F401

from . import plain_tooltip, window_title
from .catalog import TestDef
from .logstore import list_logs, log_dir, read_for_view, referenced_files
from .runner import ERROR, IDLE, INFO, RUNNING, SUCCESS, WARNING, line_level

# Button background per state. Running is yellow so it is never confused with a failed (red) test.
STATE_COLORS = {
    IDLE: ("#3a3f4b", "#e6e6e6"),
    RUNNING: ("#fdd835", "#1a1a1a"),
    SUCCESS: ("#2e7d32", "#ffffff"),
    WARNING: ("#ef6c00", "#ffffff"),
    ERROR: ("#c62828", "#ffffff"),
    INFO: ("#1565c0", "#ffffff"),
}
LINE_COLORS = {
    SUCCESS: "#81c784", INFO: "#64b5f6", WARNING: "#ffb74d", ERROR: "#e57373",
    "hint": "#ce93d8", "note": "#90a4ae", "header": "#ffffff",
}
STATE_LABEL = {IDLE: "", RUNNING: "running…", SUCCESS: "OK", WARNING: "warning", ERROR: "error", INFO: "info"}


class TestButton(QPushButton):
    run_requested = pyqtSignal(str)

    def __init__(self, test: TestDef, parent: QWidget | None = None):
        super().__init__(parent)
        self.test = test
        self.state = IDLE
        self.setToolTip(test.checks)
        self.setMinimumHeight(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(lambda: self.run_requested.emit(self.test.id))
        self.set_state(IDLE)

    def set_last_result(self, state: str, when: str | None) -> None:
        """Show a result from the history (a previous session) with its date in the tooltip."""
        self.set_state(state)
        last = f"\n\nLast result: {STATE_LABEL[state] or 'not run'} ({when})" if when and state != IDLE else ""
        self.setToolTip(self.test.checks + last)

    def set_state(self, state: str) -> None:
        if state in (RUNNING, IDLE):
            self.setToolTip(self.test.checks)
        self.state = state
        bg, fg = STATE_COLORS[state]
        suffix = f"   [{STATE_LABEL[state]}]" if STATE_LABEL[state] else ""
        self.setText(f"{self.test.id}  {self.test.name}{suffix}")
        self.setStyleSheet(
            f"QPushButton {{ background:{bg}; color:{fg}; border-radius:6px; padding:6px 12px;"
            f" text-align:left; font-weight:600; }}"
            f"QPushButton:hover {{ border:2px solid #9aa0a6; }}"
            f"QPushButton:disabled {{ color:{fg}; }}"
        )


class Terminal(QPlainTextEdit):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(20000)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.setStyleSheet("QPlainTextEdit { background:#111418; color:#d0d0d0; border:1px solid #2a2f37; }")
        self.setPlaceholderText("Test output appears here.")

    def append_line(self, text: str, level: str = "") -> None:
        color = LINE_COLORS.get(level)
        safe = html.escape(text).replace(" ", "&nbsp;") or "&nbsp;"
        if color:
            weight = "font-weight:600;" if level == "header" else ""
            safe = f'<span style="color:{color};{weight}">{safe}</span>'
        self.appendHtml(safe)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class LogHighlighter(QSyntaxHighlighter):
    """Colors a stored log like the live terminal: headers, SUCCESS/INFO/WARNING/ERROR, HINT and NOTE lines."""

    def __init__(self, document) -> None:
        super().__init__(document)
        self._formats: dict[str, QTextCharFormat] = {}
        for level, color in LINE_COLORS.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            if level == "header":
                fmt.setFontWeight(QFont.Weight.DemiBold)
            self._formats[level] = fmt

    def highlightBlock(self, text: str) -> None:
        if fmt := self._formats.get(line_level(text)):
            self.setFormat(0, len(text), fmt)


class HintsPanel(QListWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setAlternatingRowColors(True)
        # Separate the hints clearly: padding, a gap and a divider, else wrapped hints read as one text.
        self.setSpacing(3)
        self.setStyleSheet("QListWidget::item { padding:6px 4px; border-bottom:1px solid palette(midlight); }")
        style = self.style()
        self._icons = {
            "warn": style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning),
            "info": style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation),
        }

    def add_hint(self, test_id: str, text: str, severity: str) -> None:
        icon: QIcon = self._icons["warn" if severity in (WARNING, ERROR) else "info"]
        self.addItem(QListWidgetItem(icon, f"[{test_id}] {text}"))
        self.scrollToBottom()

    def clear_test(self, test_id: str) -> None:
        for row in reversed(range(self.count())):
            if self.item(row).text().startswith(f"[{test_id}] "):
                self.takeItem(row)


class SudoDialog(QDialog):
    """Masked password prompt. The value is returned once and never persisted."""

    def __init__(self, message: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(window_title("administrator password"))
        self.setModal(True)
        layout = QVBoxLayout(self)
        text = QLabel(
            "Most diagnostics read root-only logs and sysfs, so the tests run with sudo.\n"
            "Your password is passed to sudo only and is never stored."
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        if message:
            err = QLabel(message)
            err.setStyleSheet("color:#e57373; font-weight:600;")
            layout.addWidget(err)
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setPlaceholderText("sudo password")
        layout.addWidget(self.edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.edit.setFocus()

    @classmethod
    def ask(cls, parent: QWidget | None, message: str = "") -> str | None:
        dlg = cls(message, parent)
        ok = dlg.exec() == QDialog.DialogCode.Accepted
        password = dlg.edit.text()
        dlg.edit.clear()
        dlg.deleteLater()
        return password if ok else None


class LogsDialog(QDialog):
    """Stored GUI logs on the left; below them, the files each log refers to (the script's own
    report, the stress CSV, the GPU load tool log, configs). Selecting either shows it on the right."""

    def __init__(self, scope: str | list[str] | None = None, parent: QWidget | None = None,
                 files: list[Path] | None = None):
        super().__init__(parent)
        self.setWindowTitle(window_title("logs"))
        self.resize(1100, 680)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Stored in {log_dir()}"))
        split = QSplitter()

        left = QWidget()
        left_col = QVBoxLayout(left)
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.addWidget(QLabel("<b>Runs</b>"))
        self.files = QListWidget()
        left_col.addWidget(self.files, 3)
        left_col.addWidget(QLabel("<b>Files mentioned in this run</b>"))
        self.refs = QListWidget()
        self.refs.setToolTip("Log, CSV and config files named in the selected run. Click one to open it.")
        left_col.addWidget(self.refs, 2)

        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.viewer = Terminal()
        self._highlighter = LogHighlighter(self.viewer.document())
        right = QWidget()
        right_col = QVBoxLayout(right)
        right_col.setContentsMargins(0, 0, 0, 0)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_label, 1)
        self.graph_btn = QPushButton("Show graph")
        self.graph_btn.setToolTip("Plot this CSV file")
        self.graph_btn.setVisible(False)
        self.graph_btn.clicked.connect(self._show_graph)
        path_row.addWidget(self.graph_btn)
        self.calc_btn = QPushButton("Open CSV")
        self.calc_btn.setToolTip("Open this CSV file in LibreOffice Calc")
        self.calc_btn.setVisible(False)
        self.calc_btn.clicked.connect(self._open_csv)
        path_row.addWidget(self.calc_btn)
        right_col.addLayout(path_row)
        right_col.addWidget(self.viewer, 1)
        self._csv: Path | None = None

        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([340, 760])
        layout.addWidget(split, 1)

        row = QHBoxLayout()
        self.all_btn = QPushButton("Show all logs")
        self.all_btn.setVisible(scope is not None or files is not None)
        self.all_btn.clicked.connect(lambda: self._populate(None))
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(self.all_btn)
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)

        self.files.currentItemChanged.connect(self._show_run)
        self.refs.itemClicked.connect(self._show_ref)
        self.refs.currentItemChanged.connect(lambda item, _prev: item and self._show_ref(item))
        self._populate(scope, files)

    def _populate(self, scope: str | list[str] | None, files: list[Path] | None = None) -> None:
        """The logs of scope(s) (None = all), or only the given files (one run, from the History page)."""
        self.files.clear()
        self.refs.clear()
        self.viewer.clear()
        for path in (files if files is not None else list_logs(scope)):
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.files.addItem(item)
        if self.files.count():
            self.files.setCurrentRow(0)
        else:
            self.viewer.setPlaceholderText("No logs stored yet.")

    def show_test(self, test_id: str) -> bool:
        """Scroll the shown log so the header of test_id is at the top; False when it is not in the log."""
        doc = self.viewer.document()
        found = doc.find(f"[TEST {test_id}]")
        if found.isNull():
            return False
        cursor = QTextCursor(found.block())
        bar = self.viewer.verticalScrollBar()
        bar.setValue(bar.maximum())             # so the header can end up at the top, not at the bottom
        self.viewer.setTextCursor(cursor)
        self.viewer.ensureCursorVisible()
        return True

    def _show_file(self, path: Path) -> None:
        self.path_label.setText(str(path))
        # CSVs and configs are shown as they are; only logs are colored.
        self._highlighter.setDocument(self.viewer.document() if path.suffix.lower() == ".log" else None)
        self.viewer.setPlainText(read_for_view(path))
        self._csv = None
        if path.suffix.lower() == ".csv":
            from .graph import find_csvs
            # A CSV named in an older run may only survive as the Desktop copy.
            self._csv = path if path.is_file() else next(iter(find_csvs(path.name)), None)
        self.graph_btn.setVisible(self._csv is not None)
        self.calc_btn.setVisible(self._csv is not None)

    def _show_graph(self) -> None:
        from .graph import show_graph
        show_graph(self, self._csv)

    def _open_csv(self) -> None:
        from .graph import open_in_calc
        open_in_calc(self, self._csv)

    def _show_run(self, item: QListWidgetItem | None) -> None:
        self.viewer.clear()
        self.refs.blockSignals(True)
        self.refs.clear()
        self.refs.blockSignals(False)
        if item is None:
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        self._show_file(path)
        warn_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
        self.refs.blockSignals(True)
        for ref in referenced_files(self.viewer.toPlainText()):
            ref_item = QListWidgetItem(ref)
            ref_item.setData(Qt.ItemDataRole.UserRole, ref)
            ref_item.setToolTip(plain_tooltip(ref))
            if not Path(ref).is_file():
                ref_item.setIcon(warn_icon)
                ref_item.setToolTip(plain_tooltip(f"{ref}\nNot found on this machine"))
            self.refs.addItem(ref_item)
        self.refs.blockSignals(False)

    def _show_ref(self, item: QListWidgetItem) -> None:
        self._show_file(Path(item.data(Qt.ItemDataRole.UserRole)))
