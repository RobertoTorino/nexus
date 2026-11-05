# SPDX-License-Identifier: GPL-3.0-or-later
"""Convert a suite's category icons: a front end for tools/sync_icons.py (the Nexus tool, every suite's since
02-11-2026) on the suite chosen in the dashboard, the Windows Portable Suite's too since 05-11-2026 (its PNG icons,
the wide gaming one). A suite whose apps take no category icons (no icons/categories.toml) gets the dialog greyed
out."""

from __future__ import annotations

import subprocess
import sys
import tomllib
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

SYNC_ICONS = Path("tools") / "sync_icons.py"           # the Nexus tool, from the checkout's root
SIZES = (1024, 512, 256, 128)
IMAGE_FILTER = "Images (*.png *.webp *.jpg *.jpeg *.bmp *.tif *.tiff);;All files (*)"


def has_category_icons(suite: Path) -> bool:
    """Whether the suite's apps take category icons: icons/categories.toml assigns them."""
    return (suite / "icons" / "categories.toml").is_file()


def categories(suite: Path) -> list[str]:
    return sorted(p.name for p in (suite / "icons").iterdir() if p.is_dir())


def png_icons(suite: Path) -> bool:
    """Whether the suite's icons are PNG at every size ([icons] format = "png" in its categories.toml)."""
    try:
        table = tomllib.loads((suite / "icons" / "categories.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return table.get("icons", {}).get("format") == "png"


def icon_path(suite: Path, category: str, size: int) -> Path:
    """A category's icon at one size, as tools/sync_icons.py names it."""
    png = size == 128 or png_icons(suite)
    return suite / "icons" / category / f"{category}-{size}.{'png' if png else 'webp'}"


def convert_commands(root: Path, suite: str, category: str, whole: Path | None,
                     sizes: dict[int, Path]) -> list[list[str]]:
    """The tools/sync_icons.py runs (the checkout *root*'s, on the suite named) for one image for every size and
    images for single sizes; the whole set first, so a size picked on its own replaces that size of it. Each run
    also writes the copies to the apps."""
    base = [sys.executable, str(root / SYNC_ICONS), "--suite", suite, "--category", category]
    commands = [base + ["--from", str(whole)]] if whole is not None else []
    for size in SIZES:
        if size in sizes:
            commands.append(base + ["--from", str(sizes[size]), "--size", str(size)])
    return commands


class IconsDialog(QDialog):
    def __init__(self, root: Path, suite: str, parent: QWidget | None = None) -> None:
        """*root* is the checkout, *suite* the folder name of the suite chosen in the dashboard."""
        super().__init__(parent)
        self.setWindowTitle("Suite icons")
        self.resize(640, 560)
        self.root, self.suite = root, suite
        self.checkout: Path | None = root / suite
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Make a category's icons from your images: one image for every size, or an image for a single size. "
            "They are scaled, saved as WebP (the 128 px icon as PNG) under the category's names, and copied to "
            "every app of the category. Images must be square."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        suite_row = QHBoxLayout()
        suite_row.addWidget(QLabel("Suite:"))
        self.suite_label = QLabel(str(root / suite))
        self.suite_label.setToolTip("The suite's folder in the checkout, as chosen in the dashboard")
        suite_row.addWidget(self.suite_label, 1)
        layout.addLayout(suite_row)

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
        self._set_checkout(root / suite)

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

    def _set_checkout(self, checkout: Path) -> None:
        """The suite's folder; a suite without category icons gets the dialog greyed out."""
        self.category.clear()
        if not has_category_icons(checkout):
            self.checkout = None
            self.output.setPlainText(f"{checkout.name} has no icons/categories.toml: its apps take no category "
                                     "icons, so there is nothing to convert here.")
        else:
            self.checkout = checkout
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
        for command in convert_commands(self.root, self.suite, self.category.currentText(), whole, sizes):
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
