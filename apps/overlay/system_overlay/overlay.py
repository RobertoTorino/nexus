# SPDX-License-Identifier: GPL-3.0-or-later
"""The overlay: a frameless, see-through window with rounded corners and a thin border that stays on top. Drag it
with the left mouse button; the right button opens a menu (rows, background, always on top, quit). Its position and
choices are remembered."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QColor, QContextMenuEvent, QMouseEvent, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QGridLayout, QLabel, QMenu, QWidget

from bc250_core.sensors import Reading, Sensors
from bc250_core.settings import SettingsStore, restore_geometry, save_geometry
from bc250_core.theme import ACCENT, ORANGE, RED, header_font

from . import APP_NAME, INFO

INTERVAL_MS = 1000
RADIUS = 10
DASH = "—"
DOT = " · "
WARM, HOT = 80, 90                       # °C: a temperature turns orange, then red
BACKGROUNDS = {"Solid": 95, "Light see-through": 75, "See-through": 55, "Very see-through": 35}   # % opacity
ROWS = (("cpu", "CPU"), ("gpu", "GPU"), ("governor", "Governor"), ("gpu_volt", "GPU volt"), ("vram", "VRAM"),
        ("ram", "RAM"), ("refresh", "Refresh"), ("fan", "Fan"), ("cpu_temp", "CPU temp"), ("gpu_temp", "GPU temp"),
        ("vrm_temp", "VRM temp"), ("nvme_temp", "NVMe temp"), ("net", "Network"), ("disk", "Disk"))
WIDEST = "↓ 100.0 MB/s · ↑ 100.0 MB/s"     # the longest value a row shows, for a steady width


class OverlaySettings(SettingsStore):
    DEFAULTS = {"background": 75, "on_top": True, "hidden_rows": ""}       # hidden_rows: comma-separated keys


def _temp(value: float | None) -> tuple[str, str]:
    if value is None:
        return DASH, ""
    colour = RED if value >= HOT else ORANGE if value >= WARM else ""
    return f"{value:.0f} °C", colour


def _gb(pair: tuple[int, int] | None) -> str:
    return f"{pair[0] / 1e9:.1f} / {pair[1] / 1e9:.1f} GB" if pair else DASH


def _rate(value: float) -> str:
    for unit, size in (("MB/s", 1e6), ("KB/s", 1e3)):
        if value >= size:
            return f"{value / size:.1f} {unit}"
    return f"{value:.0f} B/s"


def _join(*parts: str | None) -> str:
    return DOT.join(p for p in parts if p) or DASH


def format_reading(reading: Reading, refresh_hz: float | None) -> dict[str, tuple[str, str]]:
    """Row key -> (text, color; "" = the normal text color)."""
    r = reading
    return {
        "cpu": (_join(f"{r.cpu_load:.0f} %" if r.cpu_load is not None else None,
                      f"{r.cpu_mhz} MHz" if r.cpu_mhz else None), ""),
        "gpu": (_join(f"{r.gpu_load:.0f} %" if r.gpu_load is not None else None,
                      f"{r.gpu_mhz} MHz" if r.gpu_mhz else None,
                      f"{r.gpu_watts:.0f} W" if r.gpu_watts is not None else None), ""),
        "governor": (f"{r.governor[0]}–{r.governor[1]} MHz" if r.governor else DASH, ""),
        "gpu_volt": (f"{r.gpu_mv} mV" if r.gpu_mv else DASH, ""),
        "vram": (_gb(r.vram), ""),
        "ram": (_gb(r.ram), ""),
        "refresh": (f"{refresh_hz:.0f} Hz" if refresh_hz else DASH, ""),
        "fan": (f"{r.fan.rpm} RPM" if r.fan else DASH, ""),
        "cpu_temp": _temp(r.cpu_temp),
        "gpu_temp": _temp(r.gpu_temp),
        "vrm_temp": _temp(r.vrm_temp),
        "nvme_temp": _temp(r.nvme_temp),
        "net": (f"↓ {_rate(r.net[0])}{DOT}↑ {_rate(r.net[1])}" if r.net else DASH, ""),
        "disk": (f"R {_rate(r.disk[0])}{DOT}W {_rate(r.disk[1])}" if r.disk else DASH, ""),
    }


class OverlayWindow(QWidget):
    def __init__(self, sensors: Sensors | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.sensors = sensors or Sensors()
        self.settings = OverlaySettings(INFO, self)
        self._drag_offset = None                # manual drag when the platform cannot move the window itself
        self._apply_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        grid = QGridLayout(self)
        grid.setContentsMargins(14, 10, 14, 10)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(3)
        self._font = header_font()
        self.captions: dict[str, QLabel] = {}
        self.values: dict[str, QLabel] = {}
        for row, (key, caption) in enumerate(ROWS):
            name = QLabel(caption)
            name.setStyleSheet(f"{self._font} color:#b8b8c8; font-size:12px; font-weight:600;")
            value = QLabel(DASH)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            # Wide enough for the longest value, so the window does not change size every second.
            value.setMinimumWidth(value.fontMetrics().horizontalAdvance(WIDEST) + 12)
            grid.addWidget(name, row, 0)
            grid.addWidget(value, row, 1)
            self.captions[key], self.values[key] = name, value
        self._apply_rows()

        self._save_timer = QTimer(self, singleShot=True, interval=500)
        self._save_timer.timeout.connect(lambda: save_geometry(self, self.settings.qsettings))
        self.timer = QTimer(self, interval=INTERVAL_MS)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

        restore_geometry(self, self.settings.qsettings)
        self.refresh()

    # ----------------------------------------------------------------- values
    def refresh_rate(self) -> float | None:
        screen = self.screen()
        return screen.refreshRate() if screen is not None and screen.refreshRate() > 0 else None

    def refresh(self) -> None:
        reading = self.sensors.read()
        for key, (text, colour) in format_reading(reading, self.refresh_rate()).items():
            label = self.values[key]
            label.setText(text)
            label.setStyleSheet(f"{self._font} color:{colour or 'white'}; font-size:12px; font-weight:700;")
        self.values["fan"].setToolTip("\n".join(f"{f.label}: {f.rpm} RPM" for f in reading.fans) or "No fan reports a speed.")
        if reading.gpu_load is None:
            self.values["gpu"].setToolTip("No GPU load: the BC-250 reports one only when the GPU governor's fix-metrics "
                                          "is on (governor app, GPU Usage).")
        else:
            self.values["gpu"].setToolTip("")

    # ------------------------------------------------------------------- rows
    def hidden_rows(self) -> set[str]:
        return {k for k in self.settings.get("hidden_rows").split(",") if k}

    def set_row_visible(self, key: str, visible: bool) -> None:
        hidden = self.hidden_rows()
        hidden.discard(key) if visible else hidden.add(key)
        if len(hidden) >= len(ROWS):
            return                              # keep at least one row, or there is nothing left to right-click
        self.settings.set("hidden_rows", ",".join(k for k, _ in ROWS if k in hidden))
        self._apply_rows()

    def _apply_rows(self) -> None:
        hidden = self.hidden_rows()
        for key, _ in ROWS:
            self.captions[key].setVisible(key not in hidden)
            self.values[key].setVisible(key not in hidden)
        self.adjustSize()                       # shrink or grow with the rows that are shown

    # ------------------------------------------------------------- look, feel
    def _apply_flags(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.settings.get("on_top"):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        background = QColor(18, 18, 26)
        background.setAlphaF(self.settings.get("background") / 100)
        painter.setBrush(background)
        painter.setPen(QPen(QColor(ACCENT), 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.windowHandle()
            if handle is None or not handle.startSystemMove():
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def moveEvent(self, event) -> None:  # noqa: N802
        self._save_timer.start()
        super().moveEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        save_geometry(self, self.settings.qsettings)
        super().closeEvent(event)

    # ------------------------------------------------------------------- menu
    def build_menu(self) -> QMenu:
        menu = QMenu(self)
        rows = menu.addMenu("Rows")
        hidden = self.hidden_rows()
        for key, caption in ROWS:
            action = QAction(caption, rows, checkable=True)
            action.setChecked(key not in hidden)
            action.toggled.connect(lambda on, k=key: self.set_row_visible(k, on))
            rows.addAction(action)
        background = menu.addMenu("Background")
        group = QActionGroup(background)
        for name, opacity in BACKGROUNDS.items():
            action = QAction(name, background, checkable=True)
            action.setChecked(self.settings.get("background") == opacity)
            action.triggered.connect(lambda _=False, o=opacity: self.set_background(o))
            group.addAction(action)
            background.addAction(action)
        on_top = QAction("Always on top", menu, checkable=True)
        on_top.setChecked(self.settings.get("on_top"))
        on_top.toggled.connect(self.set_on_top)
        menu.addAction(on_top)
        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)
        return menu

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        self.build_menu().exec(event.globalPos())

    def set_background(self, opacity: int) -> None:
        self.settings.set("background", opacity)
        self.update()

    def set_on_top(self, on: bool) -> None:
        self.settings.set("on_top", on)
        visible = self.isVisible()
        self._apply_flags()             # changing the flags hides the window; show it again where it was
        if visible:
            self.show()
