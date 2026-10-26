# SPDX-License-Identifier: GPL-3.0-or-later
"""On-screen overlay for the in-game wrapper (gamemon), like MangoHud but in the app's style.

Run as a child process by gamemon when "Show overlay" is on for the game:

    <python> -m bazzite_check.overlay            # reads samples as JSON lines from stdin
    <python> -m bazzite_check.overlay --demo     # sample numbers for ~45 s (the GUI's "Test overlay")

It reads one JSON object per line from stdin (the same fields as the session CSV) and shows them in a
small translucent rounded box with a thin purple border. The window is
frameless, always on top, never takes focus and lets all mouse input through, so the game is not
disturbed. It appears top-left by default; "Test overlay" (--demo) accepts the mouse so it can be
dragged anywhere, and that position is saved and reused for the games. It closes itself when gamemon
closes the pipe (game over).

Note: this is a normal window, not a Vulkan layer like MangoHud, so it shows over windowed and
borderless-fullscreen games on the desktop; gamescope's game mode and exclusive fullscreen can
cover it.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontDatabase, QPainter, QPainterPath
from PyQt6.QtWidgets import QApplication, QGridLayout, QLabel, QWidget

ACCENT = "#ce93d8"       # thin purple border: the suite's purple text tint, as the hints in the GUI
BACKGROUND = QColor(17, 20, 24, 208)   # the terminal's #111418, mostly opaque
MUTED = "#9aa0a6"
VALUE = "#e6e6e6"
RADIUS = 10.0
MARGIN = 24              # distance from the screen's top-left corner
DEMO_S = 45              # how long --demo stays on screen (long enough to drag it into place)

# Where the overlay sits on screen. In-game the window is click-through, so it can never steal
# a click from the game; it is dragged into place in the GUI's "Test overlay" (--demo) instead,
# and the position is saved here for the real sessions.
POS_FILE = Path.home() / ".config" / "bc250-bazzite-test" / "overlay-position.json"

ROWS = [  # label, CSV field, unit
    ("GPU", "gpu_pct", "%"),
    ("CPU", "cpu_pct", "%"),
    ("Clock", "sclk_mhz", " MHz"),
    ("Temp", "gpu_temp_c", " C"),
    ("Power", "gpu_power_w", " W"),
    ("VRAM", "vram_used_mib", " MiB"),
]


class StdinReader(QObject):
    """Reads JSON lines from stdin on a thread; EOF means the game (gamemon) is gone."""

    sample = pyqtSignal(dict)
    finished = pyqtSignal()

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        for line in sys.stdin:
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if isinstance(data, dict):
                self.sample.emit(data)
        self.finished.emit()


def load_position() -> QPoint | None:
    try:
        data = json.loads(POS_FILE.read_text(encoding="utf-8"))
        return QPoint(int(data["x"]), int(data["y"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_position(pos: QPoint) -> None:
    try:
        POS_FILE.parent.mkdir(parents=True, exist_ok=True)
        POS_FILE.write_text(json.dumps({"x": pos.x(), "y": pos.y()}), encoding="utf-8")
    except OSError:
        pass


class OverlayWindow(QWidget):
    def __init__(self, flags: Qt.WindowType, draggable: bool = False):
        super().__init__(None, flags)
        self.draggable = draggable
        self._drag_from: QPoint | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        if draggable:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.setToolTip("Drag to where the overlay should sit; the position is saved for the games.")

        grid = QGridLayout(self)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(2)

        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.fps = QLabel("—")
        self.fps.setStyleSheet(f"color:{ACCENT}; font-size:24px; font-weight:700;")
        fps_unit = QLabel("FPS")
        fps_unit.setStyleSheet(f"color:{MUTED}; font-size:11px; font-weight:600;")
        grid.addWidget(self.fps, 0, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        grid.addWidget(fps_unit, 0, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

        self.values: dict[str, QLabel] = {}
        for i, (label, field, _unit) in enumerate(ROWS, start=1):
            name = QLabel(label)
            name.setStyleSheet(f"color:{MUTED}; font-size:12px; font-weight:600;")
            value = QLabel("—")
            value.setFont(mono)
            value.setStyleSheet(f"color:{VALUE}; font-size:12px;")
            grid.addWidget(value, i, 0, Qt.AlignmentFlag.AlignRight)
            grid.addWidget(name, i, 1, Qt.AlignmentFlag.AlignLeft)
            self.values[field] = value
        if draggable:
            hint = QLabel("drag to move")
            hint.setStyleSheet(f"color:{MUTED}; font-size:10px; font-style:italic;")
            grid.addWidget(hint, len(ROWS) + 1, 0, 1, 2, Qt.AlignmentFlag.AlignHCenter)

    def mousePressEvent(self, event) -> None:
        if self.draggable and event.button() == Qt.MouseButton.LeftButton:
            self._drag_from = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_from is not None:
            self.move(event.globalPosition().toPoint() - self._drag_from)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_from is not None:
            self._drag_from = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            save_position(self.pos())

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        # Half a pixel in, so the 1 px border is not clipped by the window edge.
        path.addRoundedRect(0.5, 0.5, self.width() - 1.0, self.height() - 1.0, RADIUS, RADIUS)
        painter.fillPath(path, BACKGROUND)
        pen = painter.pen()
        pen.setColor(QColor(ACCENT))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawPath(path)

    def update_sample(self, data: dict) -> None:
        fps = str(data.get("fps") or "").strip()
        try:
            self.fps.setText(f"{float(fps):.0f}" if fps else "—")
        except ValueError:
            self.fps.setText("—")
        for label, field, unit in ROWS:
            raw = str(data.get(field) or "").strip()
            try:
                self.values[field].setText(f"{float(raw):.0f}{unit}" if raw else "—")
            except ValueError:
                self.values[field].setText("—")
        self.adjustSize()


def window_flags(platform: str, click_through: bool) -> Qt.WindowType:
    flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
             | Qt.WindowType.WindowDoesNotAcceptFocus)
    if click_through:
        # In-game: all mouse input goes through to the game. The demo window accepts the mouse
        # instead, so it can be dragged into place.
        flags |= Qt.WindowType.WindowTransparentForInput
    if platform == "xcb":
        # Unmanaged, like a tooltip: the window manager cannot hide, move or stack it below the game.
        flags |= Qt.WindowType.Tool | Qt.WindowType.X11BypassWindowManagerHint
    return flags


def main() -> int:
    demo = "--demo" in sys.argv
    app = QApplication([a for a in sys.argv if a != "--demo"])
    print(f"overlay: Qt platform {app.platformName()}", file=sys.stderr)
    window = OverlayWindow(window_flags(app.platformName(), click_through=not demo), draggable=demo)
    window.show()
    screen = window.screen() or app.primaryScreen()
    saved = load_position()
    if screen is not None:
        area = screen.availableGeometry()
        if saved is not None:
            # Clamp a stale position (resolution change, other screen) back onto the screen.
            saved.setX(max(area.left(), min(saved.x(), area.right() - 100)))
            saved.setY(max(area.top(), min(saved.y(), area.bottom() - 100)))
            window.move(saved)
        else:
            corner = area.topLeft()
            window.move(corner.x() + MARGIN, corner.y() + MARGIN)
    elif saved is not None:
        window.move(saved)
    window.raise_()
    # A game that goes fullscreen after the overlay appeared can stack above it; re-assert regularly
    # (cheap, and a no-op while the overlay is already on top).
    keep_on_top = QTimer(window)
    keep_on_top.timeout.connect(window.raise_)
    keep_on_top.start(3000)
    if demo:
        # Sample numbers, no stdin: for the "Test overlay" button and for testing from a terminal.
        import random
        def tick() -> None:
            window.update_sample({"fps": f"{random.uniform(55, 61):.1f}",
                                  "gpu_pct": f"{random.uniform(80, 97):.1f}",
                                  "cpu_pct": f"{random.uniform(30, 55):.1f}",
                                  "sclk_mhz": "1995", "gpu_temp_c": f"{random.uniform(68, 74):.1f}",
                                  "gpu_power_w": f"{random.uniform(80, 90):.1f}",
                                  "vram_used_mib": "7342"})
        feeder = QTimer(window)
        feeder.timeout.connect(tick)
        feeder.start(1000)
        tick()
        QTimer.singleShot(DEMO_S * 1000, app.quit)
    else:
        reader = StdinReader()
        reader.sample.connect(window.update_sample)
        reader.finished.connect(app.quit)
        reader.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
