# SPDX-License-Identifier: GPL-3.0-or-later
"""The Extract PKG window: PKG file and output folder, icon and param.sfo preview, the extraction worker with its
progress and log, preview-only / salvage mode, rename to CONTENT_ID, and the extraction comparison.
Port of ``tools/pkgxtractor/gui.cpp``. Once the standalone Bazzite pkgxtractor's main window; here a dialog of the
manager, whose game folders it offers as the output, so an extracted game shows up in the list."""

from __future__ import annotations

import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (QByteArray, QDir, QFileInfo, QObject, QSettings, QSize, QStandardPaths, QThread,
                          QTimer, QUrl, Qt, pyqtSignal, pyqtSlot)
from PyQt6.QtGui import (QCloseEvent, QContextMenuEvent, QDesktopServices, QDragEnterEvent, QDropEvent,
                         QGuiApplication, QImage, QKeyEvent, QMouseEvent, QPixmap, QResizeEvent)
from PyQt6.QtWidgets import (QApplication, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMenu,
                             QMessageBox, QProgressBar, QPushButton, QTextEdit, QVBoxLayout, QWidget)

from bc250_core import window_title
from bc250_core.platform import config_home, data_home

from . import APP_ID, LOGO_PATH, style
from .pkgxtractor.compare import run_compare
from .pkgxtractor.compare_delta import load_report, summarize_delta
from .pkgxtractor.pkg import PKG, PKGError, is_pkg_file, sanitize_folder_name
from .pkgxtractor.psf import PSF, PSFError


ENTRY_ICON0 = 0x1200
ENTRY_PIC0 = 0x1220
ENTRY_PIC1 = 0x1006
MAX_ICON_SIZE = 32 * 1024 * 1024
MAX_PREVIEW_SIZE = 64 * 1024 * 1024
TITLE = "Extract PKG"
FILE_STEM = "pkgxtractor"               # pkgxtractor.log, .state and .progress in the app's data folder
OLD_APP_ID = "bazzite-pkgxtractor"      # the standalone app; its last used folders are adopted once
PKG_FOLDER_KEY = "pkg/last_pkg_folder"
OUTPUT_FOLDER_KEY = "pkg/last_output_folder"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def app_data_dir() -> Path:
    """Per-user writable folder for the log, crash marker and progress checkpoint: the app's own data folder."""
    folder = data_home() / APP_ID
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        folder = Path.home()
    return folder


def old_folders() -> tuple[str, str]:
    """The last package and output folders the standalone app had saved (paths/lastPkgDir, paths/lastOutputDir);
    empty strings without them. Its settings file stays as it is."""
    path = config_home() / OLD_APP_ID / f"{OLD_APP_ID}.ini"
    if not path.is_file():
        return "", ""
    old = QSettings(str(path), QSettings.Format.IniFormat)
    return str(old.value("paths/lastPkgDir", "") or ""), str(old.value("paths/lastOutputDir", "") or "")


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def open_pkg_with_retry(pkg: PKG, path: Path, max_attempts: int = 3,
                        delay_ms: int = 120) -> tuple[bool, str]:
    reason = ""
    for attempt in range(1, max_attempts + 1):
        try:
            pkg.open(path)
            return True, ""
        except PKGError as exc:
            reason = str(exc)
        if attempt < max_attempts:
            time.sleep(delay_ms / 1000.0)
    return False, reason


def directory_has_entries(directory: Path) -> tuple[bool, list[str], str]:
    """Return ``(has_entries, sample_entries, error_message)`` for the guardrail."""
    try:
        if not directory.exists():
            return False, [], ""
        if not directory.is_dir():
            return True, [], "Target path exists but is not a directory"
        samples: list[str] = []
        with os.scandir(directory) as it:
            for entry in it:
                if len(samples) < 5:
                    samples.append(entry.name)
                return True, samples, ""
        return False, [], ""
    except OSError:
        return True, [], "Failed to inspect target directory"


def pkg_category(pkg: PKG) -> str:
    """CATEGORY from the package's param.sfo, lower case (gd a game, gp an update, ac add-on content); "" without."""
    if not pkg.sfo:
        return ""
    try:
        category = PSF.from_bytes(pkg.sfo).get_string("CATEGORY") or ""
    except PSFError:
        return ""
    return category.replace("\x00", "").strip().lower()


def extraction_target(output_root: Path, title_id: str, category: str) -> tuple[Path, bool]:
    """The folder a package goes into, and whether it is an update beside its game. A game goes into its TITLE_ID
    folder; an update (CATEGORY gp) into TITLE_ID-UPDATE beside the game's folder, which shadPS4 lays over the game
    (fs.cpp in 0.20.0), so the game stays as it was. Without the game's folder there a gp package goes into TITLE_ID:
    a game with its update in it says gp too."""
    game = output_root / sanitize_folder_name(title_id or "unknown_title")
    if category == "gp" and directory_has_entries(game)[0] and game.is_dir():
        return game.with_name(f"{game.name}-UPDATE"), True
    return game, False


def load_image(data: bytes, fmt: str = "PNG") -> QImage:
    image = QImage()
    image.loadFromData(QByteArray(bytes(data)), fmt)
    return image


def clean_text(value: Optional[str]) -> str:
    if value is None:
        return "not available"
    value = value.replace("\x00", "").strip()
    return value or "not available"


def same_path(a: Path, b: Path) -> bool:
    try:
        return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))
    except OSError:
        return os.path.normcase(str(a)) == os.path.normcase(str(b))


# ---------------------------------------------------------------------------
# Full-screen image viewer
# ---------------------------------------------------------------------------

class FullScreenImageViewer(QWidget):
    """Borderless full-screen viewer for pic0/pic1 with a "save as wallpaper" menu."""

    def __init__(self, image: QImage, content_id: str = "",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._content_id = content_id
        self._pixmap = QPixmap()
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet("background-color: black;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("QLabel { background-color: black; border: none; margin: 0px; padding: 0px; }")
        layout.addWidget(self._label)

        if image.isNull():
            self._label.setText("Preview image missing or not available")
            self._label.setStyleSheet("color: white; font-size: 16px; background-color: black;")
        else:
            self._pixmap = QPixmap.fromImage(image)
            self._update_scaled_image()

    def set_content_id(self, content_id: str) -> None:
        self._content_id = content_id

    # -- events -------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            event.ignore()
            return
        self.close()
        event.accept()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { font-size: 14pt; } QMenu::item { padding: 12px 28px; }")
        action = menu.addAction("save as wallpaper")
        action.setEnabled(not self._pixmap.isNull())
        action.triggered.connect(self._save_as_wallpaper)
        menu.exec(event.globalPos())
        event.accept()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_scaled_image()

    # -- internals ----------------------------------------------------------

    def _update_scaled_image(self) -> None:
        if self._pixmap.isNull():
            return
        target = self.size()
        if target.width() <= 0 or target.height() <= 0:
            return
        expanded = self._pixmap.scaled(target, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                       Qt.TransformationMode.SmoothTransformation)
        crop_x = max(0, (expanded.width() - target.width()) // 2)
        crop_y = max(0, (expanded.height() - target.height()) // 2)
        self._label.setPixmap(expanded.copy(crop_x, crop_y, target.width(), target.height()))

    def _save_as_wallpaper(self) -> None:
        save_as_wallpaper(self, self._pixmap, self._content_id)


def save_as_wallpaper(parent: QWidget, pixmap: QPixmap, content_id: str) -> None:
    """Saves pic0/pic1 where the user chooses: the Pictures folder, named after the content id, by default."""
    if pixmap.isNull():
        QMessageBox.information(parent, "Nothing to save", "No image is currently available.")
        return
    base_dir = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.PicturesLocation) or str(Path.home())
    default_name = f"{content_id}.png" if content_id else f"{APP_ID}-wallpaper.png"
    selected, _ = QFileDialog.getSaveFileName(
        parent, "Save as wallpaper", str(Path(base_dir) / default_name),
        "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg);;All Files (*)")
    if not selected:
        return
    if not pixmap.toImage().save(selected):
        QMessageBox.warning(parent, "Save failed", "Could not save wallpaper image.")
        return
    QMessageBox.information(parent, "Wallpaper saved", f"Saved to:\n{selected}")


# ---------------------------------------------------------------------------
# Clickable icon preview
# ---------------------------------------------------------------------------

class ClickableIconLabel(QLabel):
    """icon0 preview; clicking opens pic0/pic1 full screen."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.output_path = ""
        self.preview_image_path = ""
        self.pkg_path = ""
        self.pkg_loaded = False
        self._viewer: Optional[FullScreenImageViewer] = None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        # Only the left button opens the picture. A right click opened it too, and Qt shows the context menu on the
        # release on Windows (over the picture, by then) but on the press on Linux: there only the picture came up.
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self.show_full_screen()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        if not self.pkg_loaded and not self.output_path and not self.pkg_path:
            event.ignore()
            return
        menu = QMenu(self)
        menu.addAction("show full screen").triggered.connect(self.show_full_screen)
        menu.addAction("save as wallpaper").triggered.connect(self._save_as_wallpaper)
        menu.exec(event.globalPos())
        event.accept()

    def _save_as_wallpaper(self) -> None:
        found = self._preview_image()
        if found is not None:
            save_as_wallpaper(self, QPixmap.fromImage(found[0]), found[1])

    def show_full_screen(self) -> None:
        if not self.pkg_loaded and not self.output_path and not self.pkg_path:
            QMessageBox.information(self, "No package loaded", "Select a PKG file first.")
            return

        if self._viewer is not None:
            try:
                if self._viewer.isVisible():
                    self._viewer.raise_()
                    self._viewer.activateWindow()
                    return
            except RuntimeError:
                self._viewer = None

        found = self._preview_image()
        if found is None:
            return
        image, content_id = found
        viewer = FullScreenImageViewer(image, content_id)
        viewer.destroyed.connect(self._viewer_destroyed)
        self._viewer = viewer

        screen = None
        top = self.window()
        if top is not None and top.windowHandle() is not None:
            screen = top.windowHandle().screen()
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is not None:
            viewer.setGeometry(screen.geometry())
        viewer.showFullScreen()

    def _preview_image(self) -> Optional[tuple[QImage, str]]:
        """pic0 (or pic1) from the extracted folder or the package, with the content id; says so when none."""
        image = QImage()
        content_id = ""
        preview_path = self._resolve_preview_image_path()
        if preview_path:
            image = QImage(preview_path)

        if self.pkg_path and (image.isNull() or not content_id):
            try:
                with PKG() as pkg:
                    ok, _ = open_pkg_with_retry(pkg, Path(self.pkg_path), 2, 60)
                    if ok:
                        content_id = pkg.content_id
                        if image.isNull():
                            for entry_id in (ENTRY_PIC0, ENTRY_PIC1):
                                try:
                                    data = pkg.get_entry_data_by_id(entry_id)
                                except PKGError:
                                    continue
                                if not data or len(data) > MAX_PREVIEW_SIZE:
                                    continue
                                candidate = load_image(data)
                                if not candidate.isNull():
                                    image = candidate
                                    break
            except Exception:
                pass

        if image.isNull():
            QMessageBox.information(
                self, "Image not found", "pic0.png or pic1.png is not available in this package.")
            return None
        return image, content_id

    def _viewer_destroyed(self, *_args: object) -> None:
        self._viewer = None

    def _resolve_preview_image_path(self) -> str:
        if self.preview_image_path and Path(self.preview_image_path).exists():
            return self.preview_image_path
        if self.output_path:
            for name in ("pic0.png", "pic1.png"):
                candidate = Path(self.output_path) / "sce_sys" / name
                if candidate.exists():
                    return str(candidate)
        return ""


# ---------------------------------------------------------------------------
# SFO preview with copy context menu
# ---------------------------------------------------------------------------

class SfoPreview(QTextEdit):
    """Read-only text box; right click copies everything or the clicked line."""

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        menu = QMenu(self)
        line = self.cursorForPosition(event.pos()).block().text()
        copy_line = menu.addAction("Copy line")
        copy_line.setEnabled(bool(line.strip()))
        copy_value = menu.addAction("Copy value")
        copy_value.setEnabled(":" in line)
        copy_all = menu.addAction("Copy all")
        copy_all.setEnabled(bool(self.toPlainText().strip()))
        chosen = menu.exec(event.globalPos())
        clipboard = QApplication.clipboard()
        if chosen is copy_line:
            clipboard.setText(line)
        elif chosen is copy_value:
            clipboard.setText(line.split(":", 1)[1].strip())
        elif chosen is copy_all:
            clipboard.setText(self.toPlainText())


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

class ExtractionWorker(QObject):
    log_message = pyqtSignal(str)
    update_progress = pyqtSignal(int)
    set_max_progress = pyqtSignal(int)
    open_folder = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, pkg_path: Path, output_path: Path, progress_path: Optional[Path],
                 preview_only: bool, salvage_mode: bool, replace_update: bool = False) -> None:
        super().__init__()
        self._pkg_path = pkg_path
        self._output_path = output_path
        self._progress_path = progress_path
        self._preview_only = preview_only
        self._salvage_mode = salvage_mode
        self._replace_update = replace_update       # the user agreed to replace the update already there

    def log(self, message: str) -> None:
        self.log_message.emit(message)

    @pyqtSlot()
    def run(self) -> None:
        self.log("=== Starting extraction ===")
        pkg = PKG()
        try:
            self._run(pkg)
        except OSError as exc:
            self.log(f"Filesystem error: {exc}")
            if getattr(exc, "filename", None):
                self.log(f"Path: {exc.filename}")
        except Exception as exc:  # noqa: BLE001 - surfaced to the user in the log
            self.log(f"Fatal error: {exc}")
        finally:
            pkg.close()
            self.finished.emit()

    def _run(self, pkg: PKG) -> None:
        file = self._pkg_path
        output_folder = self._output_path

        self.log(f"Checking file: {file}")
        if not file.exists():
            self.log(f"Error: File does not exist: {file}")
            return

        self.log("Detecting file type...")
        if not is_pkg_file(file):
            self.log(f"Error: {file} is not a valid PKG file")
            return
        self.log(f"{file} is a valid PKG")

        self.log("Initializing PKG extractor...")
        self.log("Opening PKG file...")
        ok, reason = open_pkg_with_retry(pkg, file)
        if not ok:
            self.log(f"Cannot open PKG file: {reason}")
            return
        self.log("PKG file opened successfully")

        folder_name = pkg.title_id.replace("\x00", "")
        self.log(f"Using TITLE_ID from PKG header: {folder_name}")
        if not folder_name:
            self.log("Warning: TITLE_ID missing, using unknown_title")
        sanitized = sanitize_folder_name(folder_name or "unknown_title")
        if folder_name and sanitized != folder_name:
            self.log(f"Sanitized folder name: {sanitized}")

        output_folder, update = extraction_target(output_folder, folder_name, pkg_category(pkg))
        if update:
            self.log(f"An update (CATEGORY gp) for the game in {output_folder.with_name(sanitized)}: extracting into "
                     f"{output_folder.name}, which shadPS4 lays over the game.")
        else:
            self.log("Creating TITLE_ID extraction subfolder...")
        final_folder = output_folder

        has_entries, samples, guard_error = directory_has_entries(output_folder)
        if has_entries and update and self._replace_update and not self._preview_only and output_folder.is_dir():
            # The new update goes into a folder beside the old one and takes its place only when it is complete.
            output_folder = final_folder.with_name(f".{final_folder.name}.new")
            shutil.rmtree(output_folder, ignore_errors=True)
            self.log(f"Replacing the update in {final_folder}: extracting into {output_folder.name} first.")
        elif has_entries:
            self.log("Guardrail: target output folder is not empty.")
            self.log(f"Target folder: {output_folder}")
            self.log("For stability, each preview/extraction requires a new empty folder.")
            if guard_error:
                self.log(f"Guardrail detail: {guard_error}")
            if samples:
                self.log("Existing entries: " + ", ".join(samples))
            return

        if self._preview_only:
            self.log("Preview mode: reading PKG metadata...")
            try:
                output_folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self.log(f"Warning: Failed to create preview folder: {exc}")
            if not self._populate(pkg, file, output_folder):
                return
            files_count = pkg.num_files
            self.log(f"Preview: {files_count} files in PKG")
            if files_count == 0:
                self.log("Preview: no extractable outer PFS entries detected; package appears metadata-only.")
            self._export_file_list(pkg, output_folder)
            self.set_max_progress.emit(1)
            self.update_progress.emit(1)
            self.log("=== Preview complete (metadata extracted) ===")
            self._clear_progress_checkpoint()
            return

        try:
            output_folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.log(f"Warning: Failed to create extraction folder: {exc}")

        self.log("Running PKG extraction to populate file table...")
        if not self._populate(pkg, file, output_folder):
            return

        self.log("Getting file count from PKG...")
        files_count = pkg.num_files
        self.log(f"Total files to extract: {files_count}")
        if files_count == 0:
            self.log("No extractable outer PFS entries detected; extracted metadata/sce_sys only.")

        self._export_file_list(pkg, output_folder)
        self.log(f"Extraction target: {output_folder}")
        self.log("Setting up progress bar...")
        self.set_max_progress.emit(files_count)

        self.log("Starting file extraction loop...")
        failed_files = 0
        extraction_error = False
        aborted_early = False
        salvage_skipped: list[str] = []
        error_entries: list[str] = []

        for index in range(files_count):
            self._write_progress_checkpoint(index + 1, files_count)
            if index % 100 == 0 and index > 0:
                self.log(f"[BOUNDARY] Processed {index} files successfully")
            self.log(f"Extracting file {index + 1}/{files_count}")

            ok, preflight_reason = pkg.can_extract_file(index)
            if not ok:
                failed_files += 1
                extraction_error = True
                msg = f"Preflight failed for file {index + 1} ({preflight_reason})"
                error_entries.append(msg)
                self.log(msg)
                if self._salvage_mode:
                    skip = (f"Salvage: skipping file {index + 1} due to invalid metadata "
                            f"({preflight_reason})")
                    salvage_skipped.append(skip)
                    self.log(skip)
                    self.update_progress.emit(index + 1)
                    continue
                self.log("Aborting extraction in normal mode due to invalid metadata. "
                         "Enable Salvage Mode to skip bad entries.")
                self.update_progress.emit(index + 1)
                aborted_early = True
                break

            try:
                pkg.extract_files(index)
            except Exception as exc:  # noqa: BLE001 - recorded and extraction continues
                failed_files += 1
                extraction_error = True
                msg = f"Error extracting file {index + 1}: {exc}"
                error_entries.append(msg)
                self.log(msg)
                self.log("Continuing with next file...")
            self.update_progress.emit(index + 1)

        if aborted_early:
            self.log("=== Extraction aborted early due to invalid metadata ===")
        elif failed_files == 0:
            self.log("=== Extraction complete! ===")
        else:
            self.log(f"=== Extraction finished with {failed_files} file errors ===")

        if self._salvage_mode:
            self.log(f"Recovery Summary: skipped entries = {len(salvage_skipped)}")
            shown = min(20, len(salvage_skipped))
            for i in range(shown):
                self.log(f"  [{i + 1}] {salvage_skipped[i]}")
            if len(salvage_skipped) > shown:
                self.log(f"  ... {len(salvage_skipped) - shown} more (see salvage_report.txt)")

        if error_entries:
            report_path = output_folder / "extraction_errors.txt"
            try:
                report_path.write_text(
                    "pkgxtractor Extraction Error Report\n"
                    "================================\n"
                    f"PKG: {file}\n"
                    f"Mode: {'salvage' if self._salvage_mode else 'normal'}\n"
                    f"Total files: {files_count}\n"
                    f"Error entries: {len(error_entries)}\n\n"
                    + "\n".join(error_entries) + "\n", encoding="utf-8")
                self.log(f"Extraction error report written: {report_path}")
            except OSError:
                self.log("Warning: Could not write extraction_errors.txt")

        if self._salvage_mode and salvage_skipped:
            report_path = output_folder / "salvage_report.txt"
            try:
                report_path.write_text(
                    "pkgxtractor Salvage Report\n"
                    "========================\n"
                    f"PKG: {file}\n"
                    f"Skipped entries: {len(salvage_skipped)}\n\n"
                    + "\n".join(salvage_skipped) + "\n", encoding="utf-8")
                self.log(f"Salvage report written: {report_path}")
            except OSError:
                self.log("Warning: Could not write salvage_report.txt")

        if output_folder != final_folder:
            if extraction_error or aborted_early:
                shutil.rmtree(output_folder, ignore_errors=True)
                self.log(f"The update in {final_folder} stays as it was.")
                extraction_error = True
            else:
                old = final_folder.with_name(f".{final_folder.name}.old")
                shutil.rmtree(old, ignore_errors=True)
                final_folder.rename(old)
                output_folder.rename(final_folder)
                shutil.rmtree(old, ignore_errors=True)
                self.log(f"The new update replaced the old one in {final_folder}.")

        if not extraction_error:
            if final_folder.exists():
                self.open_folder.emit(str(final_folder))
            else:
                self.log("Warning: Output folder path does not exist")

        self._clear_progress_checkpoint()

    def _populate(self, pkg: PKG, file: Path, output_folder: Path) -> bool:
        try:
            pkg.extract(file, output_folder)
        except PKGError as exc:
            self.log(f"Cannot extract PKG: {exc}")
            return False
        except Exception as exc:  # noqa: BLE001
            self.log(f"CRITICAL: PKG extract() threw exception: {exc}")
            self.log("Extraction aborted due to critical error")
            return False
        for warning in pkg.warnings:
            self.log(f"Warning: {warning}")
        return True

    def _export_file_list(self, pkg: PKG, output_folder: Path) -> None:
        self.log("Exporting file list...")
        filelist_path = output_folder / "filelist.txt"
        if pkg.export_file_list(filelist_path):
            self.log(f"File list exported to: {filelist_path}")
        else:
            self.log("Warning: Failed to export file list")

    def _write_progress_checkpoint(self, current: int, total: int) -> None:
        if self._progress_path is None:
            return
        try:
            self._progress_path.write_text(
                f"current={current}\ntotal={total}\npkg={self._pkg_path}\ntimestamp={now_text()}\n",
                encoding="utf-8")
        except OSError:
            pass

    def _clear_progress_checkpoint(self) -> None:
        if self._progress_path is None:
            return
        try:
            self._progress_path.unlink()
        except OSError:
            pass


class CompareWorker(QObject):
    log_message = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, left: Path, right: Path, use_hash: bool, report_path: Path) -> None:
        super().__init__()
        self._left = left
        self._right = right
        self._use_hash = use_hash
        self._report_path = report_path

    @pyqtSlot()
    def run(self) -> None:
        left_fl = self._left / "filelist.txt"
        right_fl = self._right / "filelist.txt"
        use_filelists = left_fl.exists() and right_fl.exists()
        try:
            run_compare(self._left, self._right, use_hash=self._use_hash,
                        left_filelist=left_fl if use_filelists else None,
                        right_filelist=right_fl if use_filelists else None,
                        json_out=self._report_path, log=self.log_message.emit)
        except Exception as exc:  # noqa: BLE001
            self.log_message.emit(f"Compare Extractions: {exc}")
            self.finished.emit(False, "")
            return
        self.finished.emit(True, str(self._report_path))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class ExtractDialog(QDialog):
    """*settings*: the app's store (the last used folders); *game_folders*: shadPS4's game folders, offered as the
    output; *initial_pkg*: a package to load when it opens. extracted says whether a game was extracted, so the
    caller knows to look for games again."""

    def __init__(self, settings, game_folders: list[Path], parent: Optional[QWidget] = None,
                 initial_pkg: Optional[str] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(window_title(TITLE))
        self.resize(760, 680)
        self.setMinimumSize(700, 620)
        self.setAcceptDrops(True)

        self._thread: Optional[QThread] = None
        self._worker: Optional[QObject] = None
        self.game_folders = list(game_folders)
        self.extracted = False

        # Log file, crash marker and progress checkpoint live in the app's data folder.
        data_dir = app_data_dir()
        self._log_path = data_dir / f"{FILE_STEM}.log"
        self._crash_marker_path = data_dir / f"{FILE_STEM}.state"
        self._progress_path = data_dir / f"{FILE_STEM}.progress"
        self._log_file = None
        try:
            self._log_file = open(self._log_path, "a", encoding="utf-8")
            self._log_file.write(f"\n=== Session started at {now_text()} ===\n")
            self._log_file.flush()
        except OSError:
            self._log_file = None

        # The last used folders, in the app's settings; the standalone app's adopted the first time.
        self._settings = settings
        self._last_pkg_dir = str(settings.qsettings.value(PKG_FOLDER_KEY, "") or "")
        self._last_output_dir = str(settings.qsettings.value(OUTPUT_FOLDER_KEY, "") or "")
        if not settings.qsettings.contains(PKG_FOLDER_KEY) and not settings.qsettings.contains(OUTPUT_FOLDER_KEY):
            self._last_pkg_dir, self._last_output_dir = old_folders()
            settings.qsettings.setValue(PKG_FOLDER_KEY, self._last_pkg_dir)
            settings.qsettings.setValue(OUTPUT_FOLDER_KEY, self._last_output_dir)

        self._build_ui()
        style.apply(self)
        self._check_crash_marker()
        self._write_crash_marker()
        QApplication.instance().aboutToQuit.connect(self._on_about_to_quit)

        if initial_pkg:
            QTimer.singleShot(0, lambda: self.open_pkg(initial_pkg))

    def default_output(self) -> str:
        """The last used output folder while it is there, else the first game folder."""
        if self._last_output_dir and Path(self._last_output_dir).is_dir():
            return self._last_output_dir
        return str(self.game_folders[0]) if self.game_folders else ""

    def _show_output_note(self) -> None:
        text = self.output_input.text().strip()
        if not text:
            self.output_note.setText("")
        elif any(same_path(Path(text), folder) for folder in self.game_folders):
            self.output_note.setText("A game folder of shadPS4: an extracted game shows up in the list.")
        elif self.game_folders:
            self.output_note.setText("Not one of shadPS4's game folders: add it (Add folder…) to see the game in "
                                     "the list, or extract into " + ", ".join(str(f) for f in self.game_folders)
                                     + ".")
        else:
            self.output_note.setText("shadPS4 has no game folder yet: add this one (Add folder…) to see the game "
                                     "in the list.")

    def is_busy(self) -> bool:
        return self._thread is not None

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override)
        if self.is_busy():
            QMessageBox.information(self, window_title(TITLE), "An extraction is running: close this window when "
                                                               "it has finished.")
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self) -> None:
        """Esc and Close: not while an extraction runs (its thread would be destroyed under it)."""
        if self.is_busy():
            return
        super().reject()

    def done(self, result: int) -> None:
        self._on_about_to_quit()
        super().done(result)

    def open_pkg(self, file_path: str) -> None:
        """Load a package as Browse does: the package given at start-up or by a later launch."""
        self.pkg_input.setText(file_path)
        self.update_sfo_preview(file_path)

    # -- UI construction ------------------------------------------------------

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)

        # PKG file row
        pkg_row = QHBoxLayout()
        pkg_row.addWidget(QLabel("PKG File:"))
        self.pkg_input = QLineEdit()
        self.pkg_input.setPlaceholderText("Select or drag & drop a PKG file...")
        pkg_row.addWidget(self.pkg_input)
        browse_pkg = QPushButton("Browse")
        browse_pkg.clicked.connect(self.on_browse_pkg)
        pkg_row.addWidget(browse_pkg)
        self.rename_btn = QPushButton("Rename to CONTENT_ID")
        self.rename_btn.clicked.connect(self.on_rename_pkg_to_content_id)
        pkg_row.addWidget(self.rename_btn)
        main_layout.addLayout(pkg_row)

        # Output row: a game folder of shadPS4 by default, so the game shows up in the list
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output:"))
        self.output_input = QLineEdit()
        self.output_input.setPlaceholderText("Select destination folder (required)")
        out_row.addWidget(self.output_input)
        browse_out = QPushButton("Browse")
        browse_out.clicked.connect(self.on_browse_output)
        out_row.addWidget(browse_out)
        main_layout.addLayout(out_row)
        self.output_note = QLabel()
        self.output_note.setWordWrap(True)
        self.output_note.setStyleSheet("color:palette(placeholder-text);")
        main_layout.addWidget(self.output_note)
        self.output_input.textChanged.connect(lambda _text: self._show_output_note())
        self.output_input.setText(self.default_output())

        # SFO + icon preview
        preview_row = QHBoxLayout()
        sfo_col = QVBoxLayout()
        sfo_col.addWidget(QLabel("SFO Preview:"))
        self.sfo_preview = SfoPreview()
        self.sfo_preview.setReadOnly(True)
        self.sfo_preview.setPlaceholderText("Select a PKG file to preview param.sfo metadata...")
        self.sfo_preview.setMaximumHeight(220)
        self.sfo_preview.setStyleSheet("QTextEdit { border: none; }")
        self.sfo_preview.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sfo_col.addWidget(self.sfo_preview)
        sfo_col.addStretch()
        preview_row.addLayout(sfo_col, 3)

        icon_col = QVBoxLayout()
        icon_col.addWidget(QLabel("icon preview (click)"))
        self.icon_preview = ClickableIconLabel()
        self.icon_preview.setFixedSize(200, 200)
        self.icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_preview.setStyleSheet("QLabel { border: none; background: transparent; }")
        self.show_fallback_logo()
        icon_col.addWidget(self.icon_preview)
        icon_col.addStretch()
        preview_row.addLayout(icon_col, 1)
        main_layout.addLayout(preview_row)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setEnabled(False)
        main_layout.addWidget(self.progress_bar)

        # Action row
        action_row = QHBoxLayout()
        self.salvage_check = QCheckBox("Salvage Mode (skip bad metadata)")
        action_row.addWidget(self.salvage_check)
        self.preview_btn = QPushButton("Preview Only")
        self.preview_btn.clicked.connect(self.on_preview_only)
        action_row.addWidget(self.preview_btn)
        self.compare_btn = QPushButton("Compare Extractions")
        compare_menu = QMenu(self.compare_btn)
        compare_menu.addAction("Compare two extraction folders…", self.on_compare_extractions)
        compare_menu.addAction("Delta between two compare reports…", self.on_compare_report_delta)
        self.compare_btn.setMenu(compare_menu)
        action_row.addWidget(self.compare_btn)
        self.extract_btn = style.primary_button("Extract PKG", "Extract the package into a TITLE_ID folder in the "
                                                              "output folder")
        self.extract_btn.clicked.connect(self.on_extract)
        action_row.addWidget(self.extract_btn)
        main_layout.addLayout(action_row)

        # Log area
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet("QTextEdit { border: none; }")
        self.log_output.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        main_layout.addWidget(self.log_output)

    # -- crash marker -----------------------------------------------------------

    def _check_crash_marker(self) -> None:
        if not self._crash_marker_path.exists():
            return
        details = ""
        try:
            details = self._progress_path.read_text(encoding="utf-8")
        except OSError:
            pass
        message = (f"{TITLE} appears to have crashed during the previous run.\n"
                   f"Check {self._log_path} for the last recorded step.")
        if details:
            message += "\n\nLast progress checkpoint:\n" + details
        QMessageBox.warning(self, "Previous crash detected", message)
        self._write_log_file("WARNING: Previous unclean shutdown detected.")

    def _write_crash_marker(self) -> None:
        try:
            self._crash_marker_path.write_text(f"running\n{now_text()}\n", encoding="utf-8")
        except OSError:
            pass

    def _on_about_to_quit(self) -> None:
        try:
            self._crash_marker_path.unlink()
        except OSError:
            pass
        if self._log_file is not None:
            try:
                self._log_file.close()
            except OSError:
                pass
            self._log_file = None

    # -- drag & drop ------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if not urls:
            return
        file_path = urls[0].toLocalFile()
        if file_path.lower().endswith(".pkg"):
            self.open_pkg(file_path)
            event.acceptProposedAction()

    # -- logging ---------------------------------------------------------------

    def _write_log_file(self, message: str) -> None:
        if self._log_file is None:
            return
        try:
            self._log_file.write(message + "\n")
            self._log_file.flush()
        except OSError:
            pass

    @pyqtSlot(str)
    def on_log(self, message: str) -> None:
        self.log_output.append(message)
        self._write_log_file(message)

    # -- browse buttons -----------------------------------------------------------

    def on_browse_pkg(self) -> None:
        initial = ""
        current = self.pkg_input.text().strip()
        if current:
            info = QFileInfo(current)
            if info.exists():
                initial = info.absolutePath() if info.isFile() else info.absoluteFilePath()
        if not initial and self._last_pkg_dir and QDir(self._last_pkg_dir).exists():
            initial = self._last_pkg_dir
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select PKG File", initial, "PKG Files (*.pkg *.PKG);;All Files (*)")
        if file_name:
            self.pkg_input.setText(file_name)
            self._last_pkg_dir = QFileInfo(file_name).absolutePath()
            self._settings.qsettings.setValue(PKG_FOLDER_KEY, self._last_pkg_dir)
            self.update_sfo_preview(file_name)

    def on_browse_output(self) -> None:
        initial = ""
        current = self.output_input.text().strip()
        if current:
            info = QFileInfo(current)
            if info.exists():
                initial = info.absoluteFilePath() if info.isDir() else info.absolutePath()
        if not initial and self._last_output_dir and QDir(self._last_output_dir).exists():
            initial = self._last_output_dir
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", initial)
        if folder:
            self.output_input.setText(folder)
            self._last_output_dir = folder
            self._settings.qsettings.setValue(OUTPUT_FOLDER_KEY, folder)

    # -- worker management ------------------------------------------------------------

    def _set_busy(self, busy: bool) -> None:
        for widget in (self.extract_btn, self.preview_btn, self.compare_btn,
                       self.rename_btn, self.salvage_check):
            widget.setEnabled(not busy)
        self.progress_bar.setEnabled(busy)

    def _start_thread(self, worker: QObject) -> None:
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    @pyqtSlot()
    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._set_busy(False)

    def start_worker(self, preview_only: bool) -> None:
        if self._thread is not None:
            return
        if not self.pkg_input.text().strip():
            QMessageBox.warning(self, "Error", "Please select a PKG file first.")
            return
        if not self.output_input.text().strip():
            QMessageBox.warning(self, "Error", "Please select a destination folder.")
            return

        pkg_path, output_root = Path(self.pkg_input.text().strip()), Path(self.output_input.text().strip())
        replace_update = False
        if not preview_only:
            replace_update = self._ask_replace_update(pkg_path, output_root)
            if replace_update is None:
                return

        self._set_busy(True)
        self.progress_bar.setValue(0)
        self.log_output.clear()
        self.extracted = self.extracted or not preview_only       # the caller looks for games again

        worker = ExtractionWorker(pkg_path, output_root, self._progress_path, preview_only,
                                  self.salvage_check.isChecked(), replace_update)
        worker.log_message.connect(self.on_log)
        worker.update_progress.connect(self.progress_bar.setValue)
        worker.set_max_progress.connect(self.progress_bar.setMaximum)
        worker.open_folder.connect(self.open_folder)
        self._start_thread(worker)

    def _ask_replace_update(self, pkg_path: Path, output_root: Path) -> Optional[bool]:
        """For an update whose TITLE_ID-UPDATE folder is there already: whether to replace it (None: the user said
        no). False for everything else, which the worker checks itself."""
        with PKG() as pkg:
            try:
                ok, _ = open_pkg_with_retry(pkg, pkg_path, 2, 60)
            except OSError:
                ok = False
            if not ok:
                return False
            target, update = extraction_target(output_root, pkg.title_id.replace("\x00", ""), pkg_category(pkg))
        if not update or not directory_has_entries(target)[0]:
            return False
        answer = QMessageBox.question(
            self, "Replace the update",
            f"{target} holds an update for this game already.\n\nReplace it with this one? The new update is "
            "extracted first; the old one is removed only when that worked.")
        return True if answer == QMessageBox.StandardButton.Yes else None

    @pyqtSlot(str)
    def open_folder(self, folder: str) -> None:
        if folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def on_extract(self) -> None:
        self.start_worker(False)

    def on_preview_only(self) -> None:
        self.start_worker(True)

    # -- compare ------------------------------------------------------------------

    def on_compare_extractions(self) -> None:
        if self._thread is not None:
            return
        left = QFileDialog.getExistingDirectory(self, "Select pkgxtractor Extraction Folder")
        if not left:
            return
        right = QFileDialog.getExistingDirectory(self, "Select LibOrbisPkg Extraction Folder")
        if not right:
            return
        choice = QMessageBox.question(
            self, "Deep Comparison",
            "Enable SHA-256 hash comparison?\n\nYes = slower but more accurate\nNo = fast path/size comparison")
        use_hash = choice == QMessageBox.StandardButton.Yes

        report_path = Path(left) / f"compare_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        self.on_log("=== Starting extraction comparison ===")
        self.on_log(f"Left: {left}")
        self.on_log(f"Right: {right}")
        self.on_log("Mode: " + ("path + size + hash" if use_hash else "path + size"))

        self._set_busy(True)
        worker = CompareWorker(Path(left), Path(right), use_hash, report_path)
        worker.log_message.connect(self.on_log)
        worker.finished.connect(self._on_compare_finished)
        self._start_thread(worker)

    def on_compare_report_delta(self) -> None:
        """Before/after: what a change fixed and what it broke, from two compare_report JSON files."""
        if self._thread is not None:
            return
        filters = "Compare reports (compare_report_*.json);;JSON files (*.json);;All Files (*)"
        before, _ = QFileDialog.getOpenFileName(self, "Select the BEFORE compare report",
                                                self._last_output_dir, filters)
        if not before:
            return
        after, _ = QFileDialog.getOpenFileName(self, "Select the AFTER compare report",
                                               str(Path(before).parent), filters)
        if not after:
            return
        try:
            text = summarize_delta(load_report(Path(before)), load_report(Path(after)))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Compare Report Delta", f"Could not read the reports: {exc}")
            return

        self.on_log(f"Before: {before}")
        self.on_log(f"After: {after}")
        for line in text.splitlines():
            self.on_log(line)
        delta_path = Path(after).with_name(f"{Path(after).stem}_delta.txt")
        try:
            delta_path.write_text(text + "\n", encoding="utf-8")
            self.on_log(f"Delta written to: {delta_path}")
        except OSError:
            self.on_log("Warning: Could not write the delta file")

    @pyqtSlot(bool, str)
    def _on_compare_finished(self, ok: bool, report_path: str) -> None:
        if not ok:
            QMessageBox.warning(self, "Compare Extractions",
                                          "Comparison failed. See the log panel for details.")
            return
        self.on_log(f"Comparison JSON report: {report_path}")
        QMessageBox.information(self, "Compare Extractions",
                                          f"Comparison completed successfully.\n\nReport:\n{report_path}")

    # -- rename -------------------------------------------------------------------

    def on_rename_pkg_to_content_id(self) -> None:
        current = self.pkg_input.text().strip()
        if not current:
            QMessageBox.warning(self, "Rename PKG", "Please select a PKG file first.")
            return
        pkg_path = Path(current)
        if not pkg_path.exists():
            QMessageBox.warning(self, "Rename PKG", "Selected PKG file does not exist.")
            return
        if not is_pkg_file(pkg_path):
            QMessageBox.warning(self, "Rename PKG", "Selected file is not a valid PKG.")
            return

        target_scheme = "CONTENT_ID"
        with PKG() as pkg:
            ok, reason = open_pkg_with_retry(pkg, pkg_path, 2, 60)
            if not ok:
                QMessageBox.warning(self, "Rename PKG", f"Failed to open PKG: {reason}")
                return
            content_id = pkg.content_id.replace("\x00", "").strip()
            if not content_id:
                QMessageBox.warning(self, "Rename PKG",
                                              "CONTENT_ID is empty or not found in PKG header.")
                return
            target_base = content_id

            # Game packages get the normalized APP_VER appended (01.00 -> 0100); add-on
            # content (CATEGORY=AC) usually has no APP_VER and keeps CONTENT_ID only.
            if pkg.sfo:
                try:
                    psf = PSF.from_bytes(pkg.sfo)
                except PSFError:
                    psf = None
                if psf is not None:
                    category = (psf.get_string("CATEGORY") or "").replace("\x00", "").strip().upper()
                    is_addon = category == "AC" or category.startswith("AC ")
                    if not is_addon:
                        app_ver = (psf.get_string("APP_VER") or "").replace("\x00", "").strip().replace(".", "")
                        if app_ver:
                            target_base = f"{content_id}-{app_ver}"
                            target_scheme = "CONTENT_ID-APP_VER"

        extension = pkg_path.suffix or ".pkg"
        target_path = pkg_path.with_name(target_base + extension)

        if same_path(pkg_path, target_path):
            QMessageBox.information(self, "Rename PKG",
                                              f"PKG is already named after {target_scheme}.")
            return
        if target_path.exists():
            QMessageBox.warning(
                self, "Rename PKG", f"A file with that {target_scheme} name already exists in this folder.")
            return
        try:
            pkg_path.rename(target_path)
        except OSError as exc:
            QMessageBox.warning(
                self, "Rename PKG",
                f"Failed to rename file: {exc.strerror or exc}. "
                "Ensure it is not in use and you have write permission.")
            return

        self.pkg_input.setText(str(target_path))
        self.icon_preview.pkg_path = str(target_path)
        self.on_log(f"Renamed PKG to {target_scheme}: {target_path}")

    # -- preview --------------------------------------------------------------------

    def show_fallback_logo(self) -> None:
        if LOGO_PATH.exists():
            logo = QPixmap(str(LOGO_PATH))
            if not logo.isNull():
                dpr = self.icon_preview.devicePixelRatioF()
                size = QSize(int(200 * dpr), int(200 * dpr))
                scaled = logo.scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                scaled.setDevicePixelRatio(dpr)
                self.icon_preview.setPixmap(scaled)
                self.icon_preview.setText("")
                return
        self.icon_preview.setPixmap(QPixmap())
        self.icon_preview.setText("No icon")

    def update_sfo_preview(self, pkg_path: str) -> None:
        self.on_log(f"Preview: loading icon metadata for {pkg_path}")
        self.sfo_preview.clear()
        self.show_fallback_logo()
        self.icon_preview.pkg_path = pkg_path
        self.icon_preview.pkg_loaded = False
        self.icon_preview.output_path = ""
        self.icon_preview.preview_image_path = ""

        values = {key: "not available" for key in ("CATEGORY", "CONTENT_ID", "TITLE", "TITLE_ID", "VERSION")}

        def render() -> None:
            self.sfo_preview.setPlainText("\n".join(f"{key}: {value}" for key, value in values.items()))

        if not pkg_path:
            render()
            return

        try:
            with PKG() as pkg:
                ok, reason = open_pkg_with_retry(pkg, Path(pkg_path), 2, 60)
                if not ok:
                    self.on_log(f"Preview: failed to open PKG for icon: {reason}")
                    render()
                    return
                self.icon_preview.pkg_loaded = True

                output_root = self.output_input.text().strip()
                header_title_id = pkg.title_id.replace("\x00", "")
                if output_root and header_title_id:
                    self.icon_preview.output_path = str(Path(output_root) / sanitize_folder_name(header_title_id))

                try:
                    icon_data = pkg.get_entry_data_by_id(ENTRY_ICON0)
                except PKGError:
                    icon_data = b""
                if icon_data:
                    if len(icon_data) <= MAX_ICON_SIZE:
                        image = load_image(icon_data)
                        if not image.isNull():
                            pixmap = QPixmap.fromImage(image).scaled(
                                self.icon_preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
                            self.icon_preview.setPixmap(pixmap)
                            self.icon_preview.setText("")
                            self.on_log("Preview: icon0.png loaded")
                        else:
                            self.on_log("Preview: icon0.png invalid, using fallback logo")
                    else:
                        self.on_log("Preview: icon0.png too large, using fallback logo")
                else:
                    self.on_log("Preview: icon0.png not found, using fallback logo")

                if pkg.sfo:
                    try:
                        psf = PSF.from_bytes(pkg.sfo)
                    except PSFError:
                        self.on_log("Preview: failed to parse param.sfo, using fallback values")
                    else:
                        for key in values:
                            values[key] = clean_text(psf.get_string(key))
                        self.on_log("Preview: SFO metadata loaded (5-key view)")
                else:
                    self.on_log("Preview: param.sfo missing, using fallback values")

                if values["CONTENT_ID"] == "not available":
                    values["CONTENT_ID"] = clean_text(pkg.content_id)
                if values["TITLE_ID"] == "not available":
                    values["TITLE_ID"] = clean_text(pkg.title_id)
        except Exception as exc:  # noqa: BLE001
            self.on_log(f"Preview: icon load exception: {exc}")

        render()
