# SPDX-License-Identifier: GPL-3.0-or-later

"""Masked sudo password prompt and the About dialog. The sudo password is returned once and never
persisted."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from . import APP_NAME, LOGO_PATH, REPO_URL, __version__, window_title


class SudoDialog(QDialog):
    def __init__(self, message: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(window_title("administrator password"))
        self.setModal(True)
        layout = QVBoxLayout(self)
        text = QLabel(("Writing the SMU mailbox and installing the systemd service need root, so this runs "
                       "bc250-cores-unlock.sh through sudo.\n"
                       "Your password is passed to sudo only and is never stored."))
        text.setWordWrap(True)
        layout.addWidget(text)
        if message:
            err = QLabel(message)
            err.setStyleSheet("color:#e57373; font-weight:600;")
            err.setWordWrap(True)
            layout.addWidget(err)
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setPlaceholderText("sudo password")
        layout.addWidget(self.edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setEnabled(False)
        self.edit.textChanged.connect(lambda text: self._ok_btn.setEnabled(bool(text)))
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


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(window_title("about"))
        self.setModal(True)
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        if LOGO_PATH.is_file():
            icon = QLabel()
            icon.setPixmap(QPixmap(str(LOGO_PATH)).scaled(
                64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            top.addWidget(icon)
        names = QVBoxLayout()
        name_label = QLabel(f"<b>{APP_NAME}</b>")
        name_label.setStyleSheet("font-size:16px;")
        names.addWidget(name_label)
        names.addWidget(QLabel("Version {0}".format(__version__)))
        top.addLayout(names)
        top.addStretch(1)
        layout.addLayout(top)

        desc = QLabel(("A PyQt6 front-end for bc250-cores-unlock.sh: keeps the BC-250 8C/16T core unlock you "
                       "already validated with bc250-cores-bisect.sh across reboots."))
        desc.setWordWrap(True)
        layout.addWidget(desc)

        link = QLabel(f'<a href="{REPO_URL}">{REPO_URL}</a>')
        link.setOpenExternalLinks(True)
        link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(link)

        layout.addWidget(QLabel("License: GNU GPLv3."))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
