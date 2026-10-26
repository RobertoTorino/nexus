# SPDX-License-Identifier: GPL-3.0-or-later
"""Named profiles: snapshots of the Tuning and GPU Usage values (every GovernorConfig field, not the safe
points), kept per user in ~/.config/bc250-governor-manager/profiles.json. Loading one fills the forms; applying
one writes it over config.toml like the Apply button does."""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QGroupBox, QHBoxLayout, QPushButton, QWidget

from . import APP_ID
from .backends.base import GovernorConfig
from .widgets import accent_button, hint_label

PROFILES_FILE = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_ID / "profiles.json"
NAME_MAX = 40


class ProfileStore:
    """JSON file {"name": {field: value, ...}}; unknown fields are ignored, missing ones take the base values."""

    def __init__(self, path: Path = PROFILES_FILE):
        self.path = path
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        self._data = {str(k): v for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def names(self) -> list[str]:
        return sorted(self._data, key=str.casefold)

    def __contains__(self, name: str) -> bool:
        return name in self._data

    def get(self, name: str, base: GovernorConfig) -> GovernorConfig:
        """`base` with the profile's fields on top, so a profile from an older version still loads."""
        values = self._data[name]
        known = {f.name for f in dataclasses.fields(GovernorConfig)}
        fixed = {}
        for key, value in values.items():
            if key not in known:
                continue
            current = getattr(base, key)
            try:
                fixed[key] = type(current)(value) if not isinstance(current, bool) else bool(value)
            except (TypeError, ValueError):
                continue
        return dataclasses.replace(base, **fixed)

    def save(self, name: str, config: GovernorConfig) -> None:
        self._data[name] = dataclasses.asdict(config)
        self._write()

    def delete(self, name: str) -> None:
        self._data.pop(name, None)
        self._write()


def clean_name(text: str) -> str:
    return " ".join(text.split())[:NAME_MAX]


class ProfilesBox(QGroupBox):
    """Combo of saved profiles with Load / Apply / Save / Delete; the main window does the work."""

    load_requested = pyqtSignal(str)
    apply_requested = pyqtSignal(str)
    save_requested = pyqtSignal()
    delete_requested = pyqtSignal(str)
    copy_command_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Profiles", parent)
        row = QHBoxLayout(self)
        self.combo = QComboBox()
        self.combo.setToolTip(("Named snapshots of this page and the GPU Usage page, stored for your "
                               "user only. Safe points are not part of a profile."))
        self.combo.currentIndexChanged.connect(self._sync)
        row.addWidget(self.combo, 1)
        self.load_button = QPushButton("Load into forms")
        self.load_button.setToolTip(("Fills the Tuning and GPU Usage forms; nothing is written until "
                                     "you apply."))
        self.load_button.clicked.connect(lambda: self.load_requested.emit(self.combo.currentText()))
        row.addWidget(self.load_button)
        self.apply_button = accent_button("Apply now",
                                          ("Writes the profile to config.toml (backup first, one "
                                           "password prompt) and restarts the governor. Pending edits "
                                           "on the config pages are discarded."))
        self.apply_button.clicked.connect(lambda: self.apply_requested.emit(self.combo.currentText()))
        row.addWidget(self.apply_button)
        self.save_button = QPushButton("Save current as…")
        self.save_button.setToolTip(("Stores the values in the forms right now (applied or not) under "
                                     "a name."))
        self.save_button.clicked.connect(self.save_requested)
        row.addWidget(self.save_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self.combo.currentText()))
        row.addWidget(self.delete_button)
        self.copy_button = QPushButton("Copy hotkey command")
        self.copy_button.setToolTip(("Puts a command line on the clipboard that applies this profile "
                                     "in the running app. Bind it to a key in System Settings → "
                                     "Shortcuts (KDE) or Keyboard → Custom Shortcuts (GNOME) to switch "
                                     "profiles without opening the window."))
        self.copy_button.clicked.connect(lambda: self.copy_command_requested.emit(self.combo.currentText()))
        row.addWidget(self.copy_button)
        self.hint = hint_label("")
        row.addWidget(self.hint, 1)
        self.set_names([])

    def set_names(self, names: list[str], select: str | None = None) -> None:
        current = select or self.combo.currentText()
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems(names)
        if current in names:
            self.combo.setCurrentText(current)
        self.combo.blockSignals(False)
        self._sync()

    def _sync(self, *_args) -> None:
        has = bool(self.combo.count())
        for button in (self.load_button, self.apply_button, self.delete_button, self.copy_button):
            button.setEnabled(has)
        self.hint.setText("" if has else "No profiles yet: set the forms up and use Save current as…")
