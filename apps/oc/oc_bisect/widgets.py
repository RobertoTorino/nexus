# SPDX-License-Identifier: GPL-3.0-or-later

"""About and Help dialogs for the launcher GUI, and the header's status box (a copy of core's MetricBox: this app is
not on core)."""

from __future__ import annotations

import subprocess

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QTextEdit, QVBoxLayout, QWidget,
)

from . import APP_NAME, LOGO_PATH, REPO_URL, __version__, window_title
from .theme import BLUE, header_font, surface_style


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

        desc = QLabel(("A PyQt6 launcher for bc250-gpu-oc-bisect.sh: pick your options and start a sweep, "
                       "which then continues in a terminal exactly as if typed by hand."))
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


class HelpDialog(QDialog):
    """Shows bc250-gpu-oc-bisect.sh's own ``--help`` text (the single source of truth for what the
    options do), so the GUI's help never drifts out of sync with the script."""

    def __init__(self, script: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(window_title("help"))
        self.setModal(True)
        self.resize(720, 560)
        layout = QVBoxLayout(self)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        text.setPlainText(self._help_text(script))
        layout.addWidget(text)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    @staticmethod
    def _help_text(script: str) -> str:
        try:
            result = subprocess.run(
                ["bash", script, "--help"], capture_output=True, text=True, timeout=10, check=False)
            if result.stdout.strip():
                return result.stdout
        except (OSError, subprocess.SubprocessError):
            pass
        return (
            "Could not read bc250-gpu-oc-bisect.sh --help.\n\n"
            "Run it from a terminal instead:\n"
            f"  bash {script} --help"
        )


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

