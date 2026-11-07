# SPDX-License-Identifier: AGPL-3.0-or-later
"""Controller test: every input of the controllers on the board, live, so a broken button or a drifting stick shows
up before the app is suspected; the motors and the light bar on request; and, for a Sony controller, whether it is
genuine or fake (genuine.py).

The controllers are read as the stream reads them (gamepad.Reader, SDL3 on a thread of its own); the window shows the
newest readings every 30 ms. Only one reader runs at a time, so the window is not opened during a stream."""

from __future__ import annotations

import threading

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QComboBox, QDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QProgressBar,
                             QPushButton, QVBoxLayout, QWidget)

from bc250_core.widgets import hint_label

from . import APP_NAME, gamepad, genuine, style
from .gamepad import PadInfo, Reading

REFRESH_MS = 30
RUMBLE_MS = 1000
DRIFT = 0.10                             # more than this at rest is drift
LIGHT_BAR = [((255, 0, 0), "red"), ((0, 255, 0), "green"), ((0, 0, 255), "blue")]
BUTTON_NAMES = [
    (gamepad.SOUTH, "Cross"), (gamepad.EAST, "Circle"), (gamepad.WEST, "Square"), (gamepad.NORTH, "Triangle"),
    (gamepad.DPAD_UP, "Up"), (gamepad.DPAD_DOWN, "Down"), (gamepad.DPAD_LEFT, "Left"), (gamepad.DPAD_RIGHT, "Right"),
    (gamepad.LEFT_SHOULDER, "L1"), (gamepad.RIGHT_SHOULDER, "R1"), (gamepad.LEFT_STICK, "L3"),
    (gamepad.RIGHT_STICK, "R3"), (gamepad.BACK, "Share"), (gamepad.START, "Options"), (gamepad.GUIDE, "PS"),
    (gamepad.TOUCHPAD, "Touchpad click"),
]
PRESSED = "background:#2e7d32;color:white;border-radius:4px;padding:4px;"
SEEN = "background:palette(midlight);border-radius:4px;padding:4px;"
UNSEEN = "border:1px solid palette(mid);border-radius:4px;padding:4px;"


def stick_text(x: int, y: int) -> str:
    return f"x {x / 32768:+.0%}  y {y / 32768:+.0%}"


class StickView(QWidget):
    """A stick: its round range, the center's dead area of 10 % and where the stick is."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(110, 110)
        self.position = (0, 0)

    def set_position(self, x: int, y: int) -> None:
        if (x, y) != self.position:
            self.position = (x, y)
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = min(self.width(), self.height()) / 2 - 4
        centre = QPointF(self.width() / 2, self.height() / 2)
        painter.setPen(QPen(self.palette().mid().color(), 1))
        painter.drawEllipse(centre, r, r)
        painter.drawEllipse(centre, r * DRIFT, r * DRIFT)
        x, y = (v / 32768 for v in self.position)
        painter.setBrush(QColor(style.MARK))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(centre.x() + x * r, centre.y() + y * r), 6, 6)


class TouchView(QWidget):
    """The touchpad and the fingers on it (0 to 1 both ways)."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(220, 100)
        self.fingers: list[tuple[float, float]] = []

    def set_fingers(self, fingers: list[tuple[float, float]]) -> None:
        if fingers != self.fingers:
            self.fingers = fingers
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(2, 2, self.width() - 4, self.height() - 4)
        painter.setPen(QPen(self.palette().mid().color(), 1))
        painter.drawRoundedRect(area, 6, 6)
        painter.setBrush(QColor(style.MARK))
        painter.setPen(Qt.PenStyle.NoPen)
        for x, y in self.fingers:
            painter.drawEllipse(QPointF(area.x() + x * area.width(), area.y() + y * area.height()), 7, 7)


class ControllerTest(QDialog):
    """backend: the reader's SDL (gamepad.Sdl, or a stand-in in the tests); check: the genuine check for a hidraw path
    (genuine.check_device, or a stand-in)."""

    def __init__(self, parent: QWidget | None = None, backend=gamepad.Sdl, check=genuine.check_device):
        super().__init__(parent)
        self.setWindowTitle(f"Controller test · {APP_NAME}")
        self.check = check
        self.lock = threading.Lock()
        self.latest: dict[int, tuple[PadInfo, Reading, tuple[str, int]]] = {}
        self.notes: list[str] = []
        self.results: dict[int, genuine.Result | None] = {}
        self.seen: dict[int, set[int]] = {}
        self.colour = 0

        self.pad_box = QComboBox()
        self.pad_box.currentIndexChanged.connect(lambda _: self.refresh())
        self.info_label = QLabel("Looking for controllers…")
        self.info_label.setWordWrap(True)
        self.genuine_label = QLabel("")
        self.genuine_label.setWordWrap(True)
        self.genuine_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)

        buttons = QGroupBox("Buttons: press each one once")
        grid = QGridLayout(buttons)
        self.button_labels: dict[int, QLabel] = {}
        for n, (button, name) in enumerate(BUTTON_NAMES):
            label = QLabel(name)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(UNSEEN)
            grid.addWidget(label, n // 4, n % 4)
            self.button_labels[button] = label
        self.seen_label = QLabel("")
        grid.addWidget(self.seen_label, 4, 0, 1, 4)

        sticks = QGroupBox("Sticks and triggers")
        lay_sticks = QGridLayout(sticks)
        self.left_view, self.right_view = StickView(), StickView()
        self.left_label, self.right_label = QLabel(), QLabel()
        self.l2_bar, self.r2_bar = QProgressBar(), QProgressBar()
        for bar, name in ((self.l2_bar, "L2"), (self.r2_bar, "R2")):
            bar.setRange(0, 255)
            bar.setFormat(f"{name} %v")
        lay_sticks.addWidget(self.left_view, 0, 0, Qt.AlignmentFlag.AlignCenter)
        lay_sticks.addWidget(self.right_view, 0, 1, Qt.AlignmentFlag.AlignCenter)
        lay_sticks.addWidget(self.left_label, 1, 0, Qt.AlignmentFlag.AlignCenter)
        lay_sticks.addWidget(self.right_label, 1, 1, Qt.AlignmentFlag.AlignCenter)
        lay_sticks.addWidget(self.l2_bar, 2, 0)
        lay_sticks.addWidget(self.r2_bar, 2, 1)
        lay_sticks.addWidget(hint_label(
            f"Let go of the sticks: each should come back inside the small circle ({DRIFT:.0%}). One that stays "
            "outside it drifts."), 3, 0, 1, 2)

        touch = QGroupBox("Touchpad and motion")
        lay_touch = QVBoxLayout(touch)
        self.touch_view = TouchView()
        self.motion_label = QLabel("")
        lay_touch.addWidget(self.touch_view, 0, Qt.AlignmentFlag.AlignCenter)
        lay_touch.addWidget(self.motion_label)

        self.left_motor = QPushButton("Rumble left")
        self.left_motor.setToolTip("The strong motor, for a second")
        self.left_motor.clicked.connect(lambda: self._rumble(0xFF, 0))
        self.right_motor = QPushButton("Rumble right")
        self.right_motor.setToolTip("The weak motor, for a second")
        self.right_motor.clicked.connect(lambda: self._rumble(0, 0xFF))
        self.light_button = QPushButton("Light bar")
        self.light_button.setToolTip("Red, green and blue in turn")
        self.light_button.clicked.connect(self._light_bar)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        outputs = QHBoxLayout()
        for button in (self.left_motor, self.right_motor, self.light_button):
            outputs.addWidget(button)
        outputs.addStretch(1)
        outputs.addWidget(close)

        middle = QHBoxLayout()
        middle.addWidget(sticks)
        middle.addWidget(touch)
        lay = QVBoxLayout(self)
        lay.addWidget(self.pad_box)
        lay.addWidget(self.info_label)
        lay.addWidget(self.genuine_label)
        lay.addWidget(buttons)
        lay.addLayout(middle)
        lay.addWidget(self.status_label)
        lay.addLayout(outputs)

        self.reader = gamepad.Reader(lambda **state: None, False, self._note, backend, watch=self._watch).start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)
        self.refresh()

    # --- From the reader's thread --------------------------------------------------------------------------------

    def _watch(self, pads: dict) -> None:
        with self.lock:
            self.latest = dict(pads)

    def _note(self, text: str) -> None:
        with self.lock:
            self.notes.append(text)

    # --- On screen -----------------------------------------------------------------------------------------------

    def selected(self) -> int | None:
        return self.pad_box.currentData()

    def refresh(self) -> None:
        with self.lock:
            pads = dict(self.latest)
            notes, self.notes = self.notes, []
        for note in notes:
            if note.startswith("Rumble sent"):
                note += (" Felt nothing? Try another controller: when that one rumbles, this one's motor is faulty "
                         "(on the owner's board, rumble worked by USB and Bluetooth, with Steam running or not).")
            self.status_label.setText(note)
        ids = list(pads)
        if ids != [self.pad_box.itemData(i) for i in range(self.pad_box.count())]:
            current = self.selected()
            self.pad_box.blockSignals(True)
            self.pad_box.clear()
            for pad_id in ids:
                self.pad_box.addItem(pads[pad_id][0].describe(), pad_id)
            if current in ids:
                self.pad_box.setCurrentIndex(ids.index(current))
            self.pad_box.blockSignals(False)
        pad_id = self.selected()
        has_pad = pad_id in pads
        for button in (self.left_motor, self.right_motor, self.light_button):
            button.setEnabled(has_pad)
        if not has_pad:
            self.info_label.setText("No controller found. Connect one to the board by USB cable or Bluetooth.")
            self.genuine_label.setText("")
            return
        info, reading, battery = pads[pad_id]
        self._show_info(pad_id, info, battery)
        self._show_inputs(pad_id, reading)
        self.left_motor.setEnabled(info.rumble)
        self.right_motor.setEnabled(info.rumble)
        self.light_button.setEnabled(info.light_bar)

    def _show_info(self, pad_id: int, info: PadInfo, battery: tuple[str, int]) -> None:
        state, percent = battery
        power = f"{state}, {percent} %" if percent >= 0 else state
        sensors = "gyro and accelerometer" if len(info.sensors) == 2 else ("none" if not info.sensors else "partly")
        firmware = f", firmware {info.firmware:#06x}" if info.firmware else ""      # SDL knows it only over USB
        self.info_label.setText(
            f"{info.model}: USB ID {info.vendor:04x}:{info.product:04x}{firmware}, "
            f"connected by {info.connection}, battery {power}. Motion sensors: {sensors}; touchpad: "
            f"{'yes' if info.touchpads else 'no'}; rumble: {'yes' if info.rumble else 'no'}; light bar: "
            f"{'yes' if info.light_bar else 'no'}.")
        if pad_id not in self.results:
            self.results[pad_id] = self.check(info.path) if info.path else None
        result = self.results[pad_id]
        if result is None:
            self.genuine_label.setText("Genuine or fake: only checked for a Sony DualShock 4 or DualSense.")
        else:
            details = " ".join(f"{'✓' if c.ok else '✗'} {c.name}: {c.detail}" for c in result.checks)
            self.genuine_label.setText(f"{result.verdict()}\n{details}")

    def _show_inputs(self, pad_id: int, reading: Reading) -> None:
        seen = self.seen.setdefault(pad_id, set())
        seen.update(b for b in reading.buttons if b in self.button_labels)
        for button, label in self.button_labels.items():
            sheet = PRESSED if button in reading.buttons else (SEEN if button in seen else UNSEEN)
            if label.styleSheet() != sheet:
                label.setStyleSheet(sheet)
        self.seen_label.setText(f"{len(seen)} of {len(self.button_labels)} buttons pressed at least once.")
        lx, ly, rx, ry, l2, r2 = reading.axes
        self.left_view.set_position(lx, ly)
        self.right_view.set_position(rx, ry)
        self.left_label.setText("Left  " + stick_text(lx, ly))
        self.right_label.setText("Right  " + stick_text(rx, ry))
        self.l2_bar.setValue(max(0, l2) >> 7)
        self.r2_bar.setValue(max(0, r2) >> 7)
        self.touch_view.set_fingers(list(reading.fingers.values()))
        if reading.motion is None:
            self.motion_label.setText("Motion: nothing from the sensors yet (move the controller).")
        else:
            gyro, accel, _orient = reading.motion
            self.motion_label.setText("Gyro " + " ".join(f"{v:+.2f}" for v in gyro) + " rad/s\nAccelerometer "
                                      + " ".join(f"{v:+.2f}" for v in accel) + " g")

    # --- Outputs ---------------------------------------------------------------------------------------------------

    def _rumble(self, left: int, right: int) -> None:
        pad_id = self.selected()
        if pad_id is not None:
            self.reader.output("rumble_pad", pad_id, left, right, RUMBLE_MS)

    def _light_bar(self) -> None:
        pad_id = self.selected()
        if pad_id is not None:
            rgb, _name = LIGHT_BAR[self.colour % len(LIGHT_BAR)]
            self.colour += 1
            self.reader.output("led_pad", pad_id, rgb)

    def closeEvent(self, event) -> None:
        self.timer.stop()
        self.reader.stop()
        super().closeEvent(event)
