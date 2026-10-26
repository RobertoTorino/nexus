# SPDX-License-Identifier: GPL-3.0-or-later
"""Convert the suite's category icons in a checkout: a front end for the checkout's tools/sync_icons.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

SYNC_ICONS = Path("tools") / "sync_icons.py"
SIZES = (1024, 512, 256, 128)
IMAGE_FILTER = "Images (*.png *.webp *.jpg *.jpeg *.bmp *.tif *.tiff);;All files (*)"


def find_checkout(*starts: Path | None) -> Path | None:
    """The first suite checkout at or above one of the folders: it has the icons and tools/sync_icons.py."""
    for start in starts:
        if start is None:
            continue
        for folder in (start.expanduser().resolve(), *start.expanduser().resolve().parents):
            if (folder / SYNC_ICONS).is_file() and (folder / "icons" / "categories.toml").is_file():
                return folder
    return None


def categories(checkout: Path) -> list[str]:
    return sorted(p.name for p in (checkout / "icons").iterdir() if p.is_dir())


def icon_path(checkout: Path, category: str, size: int) -> Path:
    """A category's icon at one size, as tools/sync_icons.py names it."""
    return checkout / "icons" / category / f"{category}-{size}.{'png' if size == 128 else 'webp'}"


def convert_commands(checkout: Path, category: str, whole: Path | None,
                     sizes: dict[int, Path]) -> list[list[str]]:
    """The tools/sync_icons.py runs for one image for every size and images for single sizes; the whole set first,
    so a size picked on its own replaces that size of it. Each run also writes the copies to the apps."""
    base = [sys.executable, str(checkout / SYNC_ICONS), "--category", category]
    commands = [base + ["--from", str(whole)]] if whole is not None else []
    for size in SIZES:
        if size in sizes:
            commands.append(base + ["--from", str(sizes[size]), "--size", str(size)])
    return commands


class IconsDialog(QDialog):
    def __init__(self, checkout: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Suite icons")
        self.resize(640, 560)
        self.checkout = checkout
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Make a category's icons from your images: one image for every size, or an image for a single size. "
            "They are scaled, saved as WebP (the 128 px icon as PNG) under the category's names, and copied to "
            "every app of the category. Images must be square."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        checkout_row = QHBoxLayout()
        checkout_row.addWidget(QLabel("Suite checkout:"))
        self.checkout_path = QLineEdit()
        self.checkout_path.setReadOnly(True)
        self.checkout_path.setPlaceholderText("Choose the folder of a suite checkout")
        checkout_row.addWidget(self.checkout_path, 1)
        choose_checkout = QPushButton("Choose folder…")
        choose_checkout.clicked.connect(self._choose_checkout)
        checkout_row.addWidget(choose_checkout)
        layout.addLayout(checkout_row)

        category_row = QHBoxLayout()
        category_row.addWidget(QLabel("Category:"))
        self.category = QComboBox()
        self.category.currentIndexChanged.connect(lambda _index: self._show_icons())
        category_row.addWidget(self.category, 1)
        layout.addLayout(category_row)

        grid = QGridLayout()
        self.whole = self._image_row(grid, 0, "Every size from one image")
        self.previews: dict[int, QLabel] = {}
        self.sizes: dict[int, QLineEdit] = {}
        for row, size in enumerate(SIZES, start=1):
            self.sizes[size] = self._image_row(grid, row, f"{size} px ({'PNG' if size == 128 else 'WebP'})")
            preview = QLabel()
            preview.setFixedSize(48, 48)
            grid.addWidget(preview, row, 0)
            self.previews[size] = preview
        layout.addLayout(grid)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.convert_button = QPushButton("Convert and copy to the apps")
        self.convert_button.clicked.connect(self.convert)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(self.convert_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        for field in (self.whole, *self.sizes.values()):
            field.textChanged.connect(lambda _text: self._update_convert_button())
        self._set_checkout(checkout)

    def _image_row(self, grid: QGridLayout, row: int, label: str) -> QLineEdit:
        grid.addWidget(QLabel(label), row, 1)
        field = QLineEdit()
        field.setPlaceholderText("unchanged")
        field.setClearButtonEnabled(True)
        grid.addWidget(field, row, 2)
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: self._choose_image(field))
        grid.addWidget(browse, row, 3)
        return field

    def _choose_image(self, field: QLineEdit) -> None:
        selected, _filter = QFileDialog.getOpenFileName(self, "Choose an image", field.text(), IMAGE_FILTER)
        if selected:
            field.setText(selected)

    def _choose_checkout(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose the suite checkout")
        if not selected:
            return
        checkout = find_checkout(Path(selected))
        if checkout is None:
            self.output.setPlainText(f"{selected} is not a suite checkout: it has no icons/ and {SYNC_ICONS}.")
            return
        self._set_checkout(checkout)

    def _set_checkout(self, checkout: Path | None) -> None:
        self.checkout = checkout
        self.category.clear()
        if checkout is None:
            self.checkout_path.clear()
            self.output.setPlainText("Choose the folder of a suite checkout: the icons are converted there.")
        else:
            self.checkout_path.setText(str(checkout))
            self.category.addItems(categories(checkout))
        self._show_icons()

    def _show_icons(self) -> None:
        category = self.category.currentText()
        for size, preview in self.previews.items():
            path = icon_path(self.checkout, category, size) if self.checkout and category else None
            pixmap = QPixmap(str(path)) if path is not None and path.is_file() else QPixmap()
            preview.setPixmap(pixmap.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation) if not pixmap.isNull()
                              else pixmap)
            preview.setToolTip(str(path) if path is not None else "")
        self._update_convert_button()

    def _picked(self) -> tuple[Path | None, dict[int, Path]]:
        whole = Path(self.whole.text().strip()) if self.whole.text().strip() else None
        return whole, {size: Path(field.text().strip()) for size, field in self.sizes.items() if field.text().strip()}

    def _update_convert_button(self) -> None:
        whole, sizes = self._picked()
        self.convert_button.setEnabled(bool(self.checkout and self.category.currentText() and (whole or sizes)))

    def convert(self) -> bool:
        """Run the conversions; False when one failed (the output says why), and the rest are not run."""
        if self.checkout is None:
            return False
        whole, sizes = self._picked()
        log = []
        ok = True
        for command in convert_commands(self.checkout, self.category.currentText(), whole, sizes):
            try:
                result = subprocess.run(command, cwd=self.checkout, capture_output=True, text=True, timeout=300)
            except (OSError, subprocess.TimeoutExpired) as exc:
                log.append(f"Could not run {SYNC_ICONS}: {exc}")
                ok = False
                break
            log += [line for line in (result.stdout + result.stderr).splitlines() if line]
            if result.returncode:
                log.append(f"{SYNC_ICONS} stopped with status {result.returncode}.")
                ok = False
                break
        if ok:
            log.append("Done. The icons and their copies in the apps are changed in the checkout; review and commit "
                       "them there.")
            for field in (self.whole, *self.sizes.values()):
                field.clear()
        self.output.setPlainText("\n".join(log))
        self._show_icons()
        return ok
