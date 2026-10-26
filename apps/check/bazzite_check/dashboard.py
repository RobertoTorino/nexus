# SPDX-License-Identifier: GPL-3.0-or-later
"""Stats toolbar: one colored box per counter plus the system health score."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

# The suite palette and the bundled Inter font (header_font) come from bc250_core; ACCENT is the brighter purple
# of the logo's circuit lines, PURPLE the logo's own.
from bc250_core.theme import ACCENT, BLUE, GREEN, GREY, ORANGE, PURPLE, RED, THEME, header_font, surface_style

from . import plain_tooltip
from .runner import ERROR, INFO, SUCCESS, WARNING

# Performance scores are relative to a stock board, not good/bad: CPU keeps the logo's purple,
# the GPU box gets the suite's info blue so the two are easy to tell apart at a glance.
GPU_BLUE = "#1565c0"
# System scores: bright, but calm enough to look at, and unlike any other box.
BASE_SYSTEM = EXTENDED_SYSTEM = "#f8fafc"
SYSTEM_TEXT = "#222222"

# Share of a full pass each result earns towards the health score.
SCORE_WEIGHT = {SUCCESS: 1.0, INFO: 1.0, WARNING: 0.5, ERROR: 0.0}


@dataclass
class Stats:
    total: int
    passed: int = 0
    warnings: int = 0
    failures: int = 0
    info: int = 0
    hints: int = 0

    @property
    def ran(self) -> int:
        return self.passed + self.warnings + self.failures + self.info

    @property
    def score(self) -> int | None:
        if not self.ran:
            return None
        earned = (self.passed * SCORE_WEIGHT[SUCCESS] + self.info * SCORE_WEIGHT[INFO]
                  + self.warnings * SCORE_WEIGHT[WARNING] + self.failures * SCORE_WEIGHT[ERROR])
        return round(100 * earned / self.ran)

    @classmethod
    def from_results(cls, total: int, results: dict[str, str], hints: int) -> Stats:
        values = list(results.values())
        return cls(total, values.count(SUCCESS), values.count(WARNING), values.count(ERROR),
                   values.count(INFO), hints)


def score_color(score: int | None) -> str:
    if score is None:
        return GREY
    return GREEN if score >= 90 else ORANGE if score >= 70 else RED


class StatBox(QFrame):
    clicked = pyqtSignal()

    def __init__(self, title: str, color: str, tooltip: str, parent: QWidget | None = None,
                 clickable: bool = False, text_color: str = "white"):
        super().__init__(parent)
        self.clickable = clickable
        self.text_color = text_color
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setAttribute(Qt.WidgetAttribute.WA_Hover)
            tooltip += "\nClick to see the details."
        self.setToolTip(tooltip)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 7, 11, 7)         # 12, 8, 12, 8 inside the border, as before
        layout.setSpacing(0)
        # On screen in the theme's text color; text_color is the results card's (results_card()).
        self.value = QLabel("0")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value.setStyleSheet(header_font() + f"font-size:24px; font-weight:800; color:{THEME.text}; "
                                 "background:transparent; border:none;")
        self.title = QLabel(title)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet(header_font() + f"font-size:11px; font-weight:600; color:{THEME.text}; "
                                 "background:transparent; border:none;")
        layout.addWidget(self.value)
        layout.addWidget(self.title)
        # Narrow boxes, but never narrower than their title.
        self.setMinimumWidth(max(80, self.title.sizeHint().width() + 24))
        self.set_color(color)

    def set_color(self, color: str) -> None:
        """The theme's surface, *color* its left edge (GRAY: the suite's blue, as every neutral header box; owner,
        26-10-2026); outlined in the accent on hover."""
        self.color = color
        hover = f"StatBox:hover {{ border-color:{ACCENT}; }}" if self.clickable else ""
        self.setStyleSheet(surface_style(BLUE if color == GREY else color, "StatBox") + hover)

    def mouseReleaseEvent(self, event) -> None:
        if (self.clickable and event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def set_value(self, text: str) -> None:
        self.value.setText(text)


class StatsBar(QWidget):
    details_requested = pyqtSignal(str)      # "warnings", "failures" or "info"
    system_score_requested = pyqtSignal(bool)    # True for the Extended System score

    def __init__(self, total: int, parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.tests = StatBox("Tests", GREY, "Number of tests available")
        self.ran = StatBox("Finished", GREY, "Tests with a result in this session")
        self.passed = StatBox("Passed", GREEN, "Tests that passed without warnings")
        self.warnings = StatBox("Warnings", ORANGE, "Tests that raised at least one warning",
                                clickable=True)
        self.failures = StatBox("Failures", RED, "Tests that found at least one error",
                                clickable=True)
        self.info = StatBox("Info / hints", BLUE, "Informational-only tests / hints collected",
                            clickable=True)
        self.score = StatBox("Health score", GREY,
                             "Passed and info count fully, warnings half, failures zero, "
                             "as a percentage of the tests that ran")
        for kind in ("warnings", "failures", "info"):
            getattr(self, kind).clicked.connect(lambda k=kind: self.details_requested.emit(k))
        self.score.setMinimumWidth(100)
        self.cpu_score = StatBox("CPU score", GREY, "")
        self.gpu_score = StatBox("GPU score", GREY, "")
        self.base_system = StatBox("Base System", GREY,
                                   "Base System score: your board against a stock BC-250 on BIOS 5.00, "
                                   "which scores 100. Never more than 100.", clickable=True,
                                   text_color=SYSTEM_TEXT)
        self.ext_system = StatBox("Extended System", GREY,
                                  "Extended System score: the Base score plus what upgrades add "
                                  "(more CUs or cores, a bigger or faster drive, a faster link).", clickable=True,
                                  text_color=SYSTEM_TEXT)
        self.base_system.clicked.connect(lambda: self.system_score_requested.emit(False))
        self.ext_system.clicked.connect(lambda: self.system_score_requested.emit(True))
        for box in (self.tests, self.ran, self.passed, self.warnings, self.failures, self.info):
            row.addWidget(box, 1)
        row.addSpacing(12)
        row.addWidget(self.score, 1)
        row.addSpacing(12)
        row.addWidget(self.cpu_score, 1)
        row.addWidget(self.gpu_score, 1)
        row.addSpacing(12)
        row.addWidget(self.base_system, 1)
        row.addWidget(self.ext_system, 1)
        self.set_system_scores(None, None)
        self.set_bench(None, None, None, "")

        self.update_stats(Stats(total))

    def update_stats(self, s: Stats) -> None:
        self.tests.set_value(str(s.total))
        self.ran.set_value(f"{s.ran}")
        self.passed.set_value(str(s.passed))
        self.warnings.set_value(str(s.warnings))
        self.failures.set_value(str(s.failures))
        self.info.set_value(f"{s.info} / {s.hints}")
        score = s.score
        self.score.set_value("—" if score is None else f"{score}%")
        self.score.set_color(score_color(score))

    def set_system_scores(self, base: int | None, extended: int | None) -> None:
        for box, value, colour in ((self.base_system, base, BASE_SYSTEM), (self.ext_system, extended, EXTENDED_SYSTEM)):
            box.set_value("—" if value is None else str(value))
            box.set_color(GREY if value is None else colour)

    def set_bench(self, cpu: int | None, cpu1: int | None, gpu: int | None, detail: str) -> None:
        """Performance scores from the benchmark (test 42), 100 = stock BC-250 baseline."""
        base_tip = ("Performance benchmark (test 42, Performance page), 100 = the stock BC-250 baseline.\n"
                    "Run it before and after a CU or core unlock to see the gain.")
        for box, value, colour, what in ((self.cpu_score, cpu, PURPLE, "CPU multi-thread (stress-ng matrixprod)"
                                          + (f", single-thread score {cpu1}" if cpu1 is not None else "")),
                                         (self.gpu_score, gpu, GPU_BLUE, "GPU FP32 compute (vkpeak)")):
            box.set_value("—" if value is None else str(value))
            box.set_color(GREY if value is None else colour)
            box.setToolTip(plain_tooltip(f"{what}\n{base_tip}" + (f"\n\n{detail}" if detail else "")))


class ResultsPreview(QFrame):
    image_requested = pyqtSignal(str)
    folder_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("resultsPreview")
        self.setStyleSheet("#resultsPreview { border:1px solid #3a3f4a; border-radius:8px;"
                           " background:rgba(255,255,255,0.03); }")
        self._image_path: str | None = None

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(12)
        self.image = QPushButton()
        self.image.setObjectName("resultsPreviewImage")
        self.image.setFixedSize(192, 108)
        self.image.setIconSize(QSize(184, 100))
        self.image.setFlat(True)
        self.image.setCursor(Qt.CursorShape.PointingHandCursor)
        self.image.setToolTip("Click to open the results image.")
        self.image.clicked.connect(self._open_image)
        row.addWidget(self.image)

        details = QVBoxLayout()
        details.setSpacing(4)
        title = QLabel("Latest results image")
        title.setStyleSheet("font-weight:700;")
        details.addWidget(title)
        self.folder = QLabel()
        self.folder.setWordWrap(True)
        self.folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details.addWidget(self.folder)
        details.addStretch(1)
        self.open_folder = QPushButton("Open folder")
        self.open_folder.clicked.connect(self._open_folder)
        details.addWidget(self.open_folder, 0, Qt.AlignmentFlag.AlignLeft)
        row.addLayout(details, 1)
        self.hide()

    def set_image(self, image_path: str) -> bool:
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return False
        self._image_path = image_path
        self.image.setIcon(QIcon(pixmap.scaled(
            self.image.iconSize(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)))
        self.folder.setText(f"Folder: {Path(image_path).parent}")
        self.show()
        return True

    def _open_image(self) -> None:
        if self._image_path is not None:
            self.image_requested.emit(self._image_path)

    def _open_folder(self) -> None:
        if self._image_path is not None:
            self.folder_requested.emit(str(Path(self._image_path).parent))


def results_card(bar: StatsBar) -> "QPixmap":
    """A compact, shareable "BC-250 Bazzite Test Results" card (Settings > General > Print results):
    the logo and title on top, the Base and Extended System scores as two large tiles, the nine stat
    boxes as a readable 3x3 grid below, rendered offscreen."""
    from datetime import datetime

    from PyQt6.QtWidgets import QGridLayout

    from . import APP_NAME, LOGO_PATH, __version__

    card = QWidget()
    card.setObjectName("resultsCard")
    card.setStyleSheet("#resultsCard { background:#14161c; }")
    col = QVBoxLayout(card)
    col.setContentsMargins(16, 14, 16, 10)
    col.setSpacing(10)

    head = QHBoxLayout()
    head.setSpacing(10)
    logo = QLabel()
    pix = QPixmap(str(LOGO_PATH))
    if not pix.isNull():
        logo.setPixmap(pix.scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation))
    head.addWidget(logo)
    title = QLabel("BC-250 Bazzite Test Results")
    title.setStyleSheet(header_font() + "font-size:17px; font-weight:800; color:white; background:transparent;")
    head.addWidget(title, 1)
    col.addLayout(head)

    def tile(box: StatBox, value_px: int, label_px: int, pad: int) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ background:{box.color}; border-radius:6px; }}")
        frame.setMinimumWidth(120)
        tcol = QVBoxLayout(frame)
        tcol.setContentsMargins(10, pad, 10, pad)
        tcol.setSpacing(0)
        for text, px, weight in ((box.value.text(), value_px, 800), (box.title.text(), label_px, 600)):
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(header_font() + f"font-size:{px}px; font-weight:{weight}; color:{box.text_color}; "
                              "background:transparent;")
            tcol.addWidget(lbl)
        return frame

    # The two system scores as large tiles on top, the nine stat boxes as a 3x3 grid below.
    grid = QGridLayout()
    grid.setSpacing(6)
    grid.addWidget(tile(bar.base_system, 26, 11, 8), 0, 0, 1, 3)
    grid.addWidget(tile(bar.ext_system, 26, 11, 8), 0, 3, 1, 3)
    boxes = (bar.tests, bar.ran, bar.passed, bar.warnings, bar.failures, bar.info,
             bar.score, bar.cpu_score, bar.gpu_score)
    for i, box in enumerate(boxes):
        grid.addWidget(tile(box, 16, 9, 5), 1 + i // 3, (i % 3) * 2, 1, 2)
    col.addLayout(grid)

    foot = QLabel(f"{APP_NAME} v{__version__} — {datetime.now().strftime('%d-%m-%Y %H:%M')}")
    foot.setStyleSheet("font-size:9px; color:#9aa0a6; background:transparent;")
    foot.setAlignment(Qt.AlignmentFlag.AlignRight)
    col.addWidget(foot)

    card.adjustSize()
    return card.grab()
