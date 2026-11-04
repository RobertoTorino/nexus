# SPDX-License-Identifier: GPL-3.0-or-later
"""Dev app versions: the Nexus apps of dev/ with their versions, what changed since each one's last version and the
version that asks for, set with one click (owner, 04-11-2026: by hand they go wrong). The work is the checkout's
tools/dev_versions.py: VERSION, the copies tools/check_versions.py checks and a "Version x.y.z." CHANGELOG entry.
Nothing is committed, tagged or released."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from bc250_core.widgets import InfoButton, accent_button, hint_label

from . import CHECKOUT

ABOUT = ("A Nexus app is never released or tagged. Its version is its <code>VERSION</code>, the "
         "<code>__version__</code> copy beside it and a <b>Version x.y.z.</b> entry on top of its CHANGELOG, as "
         "core's. The version offered follows the entries since the last one: <b>Breaking.</b> major, <b>Added.</b> "
         "minor, <b>Fixed.</b> patch. A version set and not pushed yet can be set again: the new one takes its "
         "place. Commit and push it as any change; <code>tools/dev_versions.py</code> does the same in a terminal.")


def tool(root: Path = CHECKOUT):
    """The checkout's tools/dev_versions.py, as a module."""
    spec = importlib.util.spec_from_file_location("nexus_dev_versions", root / "tools" / "dev_versions.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module             # its dataclass looks its module up there
    spec.loader.exec_module(module)
    return module


class VersionsDialog(QDialog):
    """The dev apps, one selected: its offered version (or another) and a note; Set version writes it."""

    def __init__(self, root: Path = CHECKOUT, parent: QWidget | None = None, report=None):
        super().__init__(parent)
        self.root = root
        self.tool = tool(root)
        self.report = report or (lambda _text: None)     # a line for the dashboard's output
        self.setWindowTitle("Dev app versions")
        self.resize(640, 420)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._show)
        self.version = QComboBox()
        self.version.setEditable(True)
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("A note after Version x.y.z. in the CHANGELOG (optional)")
        self.state = QLabel()
        self.state.setWordWrap(True)
        self.set_button = accent_button("Set version", "Write VERSION, its copies and the CHANGELOG entry")
        self.set_button.clicked.connect(self.set_version)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)

        top = QHBoxLayout()
        top.addWidget(hint_label("Pick an app, check the version and press <b>Set version</b>."), 1)
        top.addWidget(InfoButton(ABOUT, "How a dev app's version works"))
        form = QFormLayout()
        form.addRow("Version", self.version)
        form.addRow("Note", self.notes)
        buttons = QHBoxLayout()
        buttons.addWidget(self.state, 1)
        buttons.addWidget(close)
        buttons.addWidget(self.set_button)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.list, 1)
        lay.addLayout(form)
        lay.addLayout(buttons)
        self.fill()

    def fill(self, key: str = "") -> None:
        self.apps = self.tool.dev_apps(self.root)
        self.list.clear()
        for app in self.apps:
            change = f"offers {app.offered} ({app.level}: {app.why})" if app.offered else app.why
            item = QListWidgetItem(f"{app.name}  {app.version}  ·  {change}" +
                                   ("  ·  set, not pushed yet" if app.redo else ""))
            item.setData(Qt.ItemDataRole.UserRole, app.key)
            self.list.addItem(item)
        keys = [app.key for app in self.apps]
        self.list.setCurrentRow(keys.index(key) if key in keys else 0 if keys else -1)

    def current(self):
        row = self.list.currentRow()
        return self.apps[row] if 0 <= row < len(self.apps) else None

    def _show(self, _row: int = -1) -> None:
        app = self.current()
        self.version.clear()
        if app is None or not app.entries:
            self.set_button.setEnabled(False)
            self.state.setText(f"{app.name}: nothing changed since {app.base}." if app else "")
            return
        base = app.base
        choices = [app.offered] + [self.tool.next_version(base, level) for level in ("patch", "minor", "major")]
        self.version.addItems([v for i, v in enumerate(choices) if v not in choices[:i]])
        self.set_button.setEnabled(True)
        self.state.setText(f"From {base}: {app.why}." + (f" Replaces {app.version}, not pushed yet." if app.redo
                                                         else ""))

    def set_version(self) -> None:
        app = self.current()
        if app is None:
            return
        try:
            changed = self.tool.set_version(self.root, app.key, self.version.currentText(), self.notes.text())
        except self.tool.VersionError as exc:
            self.state.setText(str(exc))
            return
        version = (app.folder / "VERSION").read_text(encoding="utf-8").strip()
        files = ", ".join(path.relative_to(self.root).as_posix() for path in changed)
        self.report(f"{app.name} is now {version}: {files}. Commit and push it as any change.")
        self.notes.clear()
        self.fill(app.key)
        self.state.setText(f"{app.name} is now {version}.")
