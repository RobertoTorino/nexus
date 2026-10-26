# SPDX-License-Identifier: MIT
"""Masked sudo password prompt, the About dialog, and the header's status box and state (copies of core's
MetricBox and StatusText: this app is not on core). The sudo password is returned once and never persisted."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from . import APP_NAME, LOGO_PATH, REPO_URL, __version__, window_title
from .theme import BLUE, STATE_COLORS, header_font, surface_style


class SudoDialog(QDialog):
    def __init__(self, message: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(window_title("administrator password"))
        self.setModal(True)
        layout = QVBoxLayout(self)
        text = QLabel(
            "Changing /boot and the GRUB configuration needs root, so this runs bc250-acpi-override.sh "
            "through sudo.\nYour password is passed to sudo only and is never stored."
        )
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
        names.addWidget(QLabel(f"Version {__version__}"))
        top.addLayout(names)
        top.addStretch(1)
        layout.addLayout(top)

        desc = QLabel(
            "A PyQt6 front-end for bc250-acpi-override.sh: installs the ACPI tables from e-tho/bc250-acpi-fix "
            "as a GRUB early initrd, which gives the BC-250 CPU idle states and frequency scaling."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        link = QLabel(f'<a href="{REPO_URL}">{REPO_URL}</a>')
        link.setOpenExternalLinks(True)
        link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(link)

        layout.addWidget(QLabel("License: MIT."))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class MetricBox(QFrame):
    """One box of the header's second row: a big value with a caption, centered, on the theme's surface with
    *colour* as its left edge. A copy of core's MetricBox with the same sizes: this app is not on core."""

    MIN_WIDTH = 120

    def __init__(self, caption: str, colour: str = BLUE, parent: QWidget | None = None):
        super().__init__(parent)
        self.set_colour(colour)
        self.setMinimumWidth(self.MIN_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 7, 11, 7)         # 12, 8, 12, 8 inside the border
        layout.setSpacing(0)
        self.value = QLabel("—")
        self.value.setStyleSheet(header_font() + "font-size:22px; font-weight:800;")
        self.caption = QLabel(caption)
        self.caption.setStyleSheet("font-size:12px; font-weight:600;")
        for label in (self.value, self.caption):
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            layout.addWidget(label)

    def set_value(self, text: str, tooltip: str = "") -> None:
        self.value.setText(text)
        self.setToolTip(tooltip)

    def set_colour(self, colour: str) -> None:
        """The box's state or category color, its left edge."""
        self.setStyleSheet(surface_style(colour) + "QLabel { background:transparent; border:none; }")


class StatusText(QWidget):
    """A state next to the title: a colored dot and the state in bold, in the color of its kind (ok, warn, bad,
    info; neutral uses the text color). A copy of core's StatusText: this app is not on core."""

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)
        self.dot = QLabel("●")
        self.label = QLabel()
        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        self.kind = ""
        self.set_status(text or "Unknown", "neutral")

    def set_status(self, text: str, kind: str, tooltip: str = "") -> None:
        self.kind = kind
        self.label.setText(text)
        self.setToolTip(tooltip)
        colour = STATE_COLORS.get(kind) if kind != "neutral" else None
        style = f"color:{colour};" if colour else "color:palette(window-text);"
        self.dot.setStyleSheet(style + "font-size:14px;")
        self.label.setStyleSheet(style + "font-weight:700; font-size:14px;")

    def text(self) -> str:
        return self.label.text()
