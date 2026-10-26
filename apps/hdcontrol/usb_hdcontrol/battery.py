# SPDX-License-Identifier: GPL-3.0-or-later
"""The battery as a phone shows it (owner, 23-10-2026): standing upright, an outline with its terminal on top, five
modules stacked from the bottom for the level, and the percentage inside it on two lines, the number and "%". Green, orange at 20 % or less, red at 10 % or less, while the controller runs on its battery;
while it charges, the modules above the level fill one after another, upwards, in green, again and again; full, all five
green. The level comes from hid-playstation, in steps of 10 %."""

from __future__ import annotations

import math

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from bc250_core.theme import GREEN, ORANGE, RED, THEME, header_font, muted

MODULES = 5
STEP_MS = 450                       # one more module lit while charging
TOP = 6                             # the terminal's top: the top of the title's capitals


def modules(capacity: int) -> int:
    """How many of the five modules a level fills: any charge lights the first, 100 % all five."""
    return max(1, min(MODULES, math.ceil(capacity / (100 / MODULES)))) if capacity > 0 else 0


def colour(capacity: int, status: str) -> str:
    if status in ("Charging", "Full") or capacity > 20:
        return GREEN
    return ORANGE if capacity > 10 else RED


class BatteryIcon(QWidget):
    """set_battery(capacity, status) with the power_supply's values; None: no controller, an empty outline."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.capacity: int | None = None
        self.status = ""
        self.extra = 0                  # charging: modules lit above the level, in turn
        self.timer = QTimer(self, interval=STEP_MS)
        self.timer.timeout.connect(self._step)
        self.setFixedSize(68, 96)              # the header's height: its top level with the title
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setToolTip("Battery: No controller.")

    @property
    def charging(self) -> bool:
        return self.status == "Charging" and self.capacity is not None and modules(self.capacity) < MODULES

    def set_battery(self, capacity: int | None, status: str) -> None:
        if (capacity, status) == (self.capacity, self.status):
            return
        self.capacity, self.status, self.extra = capacity, status, 0
        if self.charging and not self.timer.isActive():
            self.timer.start()
        elif not self.charging:
            self.timer.stop()
        self.setToolTip("Battery: No controller." if capacity is None else
                        f"Battery: {capacity} %, {status.lower()}. The controller reports its level in steps of 10 %.")
        self.update()

    def lit_modules(self) -> int:
        if self.capacity is None:
            return 0
        if self.status == "Full":
            return MODULES
        return min(MODULES, modules(self.capacity) + self.extra)

    def _step(self) -> None:
        """One module more, until all five are lit; then back to the level."""
        if self.capacity is None or modules(self.capacity) + self.extra >= MODULES:
            self.extra = 0
        else:
            self.extra += 1
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt override)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Twice as wide as first drawn, and as tall as the header, the terminal level with the title's top
        # (owner, 23-10-2026).
        body = QRectF(6, TOP + 6, 56, self.height() - TOP - 8)
        p.setPen(QPen(QColor(THEME.text), 2.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(body, 5, 5)
        p.setBrush(QColor(THEME.text))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(body.center().x() - 10, body.top() - 6, 20, 5), 2, 2)      # the terminal
        lit = self.lit_modules()
        fill = QColor(colour(self.capacity or 0, self.status))
        gap, inner = 2.0, body.adjusted(4, 4, -4, -4)
        height = (inner.height() - gap * (MODULES - 1)) / MODULES
        for index in range(MODULES):                    # from the bottom up
            cell = QRectF(inner.left(), inner.bottom() - (index + 1) * height - index * gap, inner.width(), height)
            if index < lit:
                p.setBrush(fill)
                p.drawRoundedRect(cell, 2, 2)
        # The percentage inside, on two lines and centered both ways (owner, 23-10-2026); white with a dark shadow,
        # so it reads on the green modules and on the empty ones alike.
        font = p.font()
        font.setPixelSize(20)
        font.setWeight(font.Weight.ExtraBold)
        if "Inter" in header_font():             # the metric boxes' font, where it is bundled
            font.setFamily("Inter")
        p.setFont(font)
        text = "—" if self.capacity is None else f"{self.capacity}\n%"
        p.setPen(QColor(0, 0, 0, 170))
        p.drawText(body.translated(1, 1), Qt.AlignmentFlag.AlignCenter, text)
        p.setPen(QColor("white") if self.capacity is not None else QColor(muted()))
        p.drawText(body, Qt.AlignmentFlag.AlignCenter, text)
        p.end()
