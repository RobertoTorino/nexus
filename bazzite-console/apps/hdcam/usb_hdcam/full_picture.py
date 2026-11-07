# SPDX-License-Identifier: GPL-3.0-or-later
"""The picture full screen (owner, 03-11-2026, from the Windows Portable Suite's USB HD Cam, 01-11-2026): a window
over the whole screen with the camera's picture (preview.PictureView) and a row at the bottom: Screenshot, Record
and Stop, Gray and Color, Zoom − and Zoom +, Mode − and Mode +, and Close. The line above the row shows the mode,
the zoom and, while it records, the recording's time. The keyboard does the same: Esc closes, the arrow keys move
the zoomed picture, + and − zoom, G is gray or color, S a screenshot, R starts and stops a recording, PageUp and
PageDown change the mode; the mouse wheel zooms and a drag moves the picture. The window holds nothing itself: the
main window owns the look, the recording and the preview, and the buttons call it (the signals below)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .preview import PAN_STEP, PictureView

RECORD, STOP = "Record", "Stop"
GRAY, COLOR = "Gray", "Color"


class FullPicture(QWidget):
    """A window of its own over the whole screen; *parent* is the main window, whose style it takes."""

    screenshot = pyqtSignal()
    record = pyqtSignal()
    gray = pyqtSignal()
    zoomed = pyqtSignal(int)            # +1 in, -1 out
    panned = pyqtSignal(float, float)   # how far, as a part of what shows
    mode_step = pyqtSignal(int)         # +1 the next mode, -1 the one before
    closed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("USB HD Cam")
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        self.view = PictureView()
        self.view.dragged.connect(self.panned)
        self.view.wheeled.connect(self.zoomed)
        column.addWidget(self.view, 1)
        line = QHBoxLayout()
        line.setContentsMargins(16, 0, 16, 0)
        line.setSpacing(16)
        self.recording = QLabel()
        self.recording.setStyleSheet("font-weight:700;color:#c62828;")
        self.recording.hide()
        line.addWidget(self.recording)
        self.summary = QLabel()
        self.summary.setStyleSheet("color:palette(placeholder-text);")
        line.addWidget(self.summary)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet("font-weight:600;")
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        line.addWidget(self.status, 1)
        column.addLayout(line)
        row = QHBoxLayout()
        row.setContentsMargins(16, 0, 16, 10)
        row.setSpacing(8)
        self.screenshot_button = self._button(row, "Screenshot", "Save what shows as a PNG in your Pictures folder (S)",
                                              self.screenshot)
        self.record_button = self._button(row, RECORD, "Record what shows as an MP4 in your Videos folder, and stop "
                                                       "it (R)", self.record)
        self.gray_button = self._button(row, GRAY, "Black and white, or color again; remembered (G)", self.gray)
        self.zoom_out_button = self._button(row, "Zoom −", "Zoom out (−, or the mouse wheel)",
                                            lambda: self.zoomed.emit(-1))
        self.zoom_in_button = self._button(row, "Zoom +", "Zoom in: 1x, 1.5x, 2x, 3x and 4x (+, or the mouse wheel); "
                                                          "the arrow keys or a drag move the zoomed picture",
                                           lambda: self.zoomed.emit(1))
        self.mode_down_button = self._button(row, "Mode −", "The mode before (PageUp); not while it records",
                                             lambda: self.mode_step.emit(-1))
        self.mode_up_button = self._button(row, "Mode +", "The next mode (PageDown); not while it records",
                                           lambda: self.mode_step.emit(1))
        row.addStretch(1)
        self.close_button = self._button(row, "Close", "Back to the window (Esc); a recording stops and is kept",
                                         self.close)
        column.addLayout(row)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    @staticmethod
    def _button(row: QHBoxLayout, text: str, tip: str, target) -> QPushButton:
        button = QPushButton(text)
        button.setToolTip(tip)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)       # the keys stay the window's
        button.clicked.connect(target)
        row.addWidget(button)
        return button

    def show_recording(self, running: bool, seconds: int) -> None:
        self.record_button.setText(STOP if running else RECORD)
        self.recording.setText(f"● {seconds // 60}:{seconds % 60:02d}")
        self.recording.setVisible(running)
        for button in (self.mode_down_button, self.mode_up_button):
            button.setEnabled(not running)

    def show_gray(self, gray: bool) -> None:
        self.gray_button.setText(COLOR if gray else GRAY)

    def say(self, text: str, ok: bool = True) -> None:
        self.status.setStyleSheet("font-weight:600;" + ("" if ok else "color:#c62828;"))
        self.status.setText(text)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoomed.emit(1)
        elif key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self.zoomed.emit(-1)
        elif key == Qt.Key.Key_G:
            self.gray.emit()
        elif key == Qt.Key.Key_S:
            self.screenshot.emit()
        elif key == Qt.Key.Key_R:
            self.record.emit()
        elif key == Qt.Key.Key_PageUp:
            self.mode_step.emit(-1)
        elif key == Qt.Key.Key_PageDown:
            self.mode_step.emit(1)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            dx, dy = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (0, -1),
                      Qt.Key.Key_Down: (0, 1)}[key]
            self.panned.emit(dx * PAN_STEP, dy * PAN_STEP)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.closed.emit()
        super().closeEvent(event)
