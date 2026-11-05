# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller's battery as a phone shows it (the BC250 app's, owner 23-10-2026): standing upright, an outline
with its terminal on top, five modules stacked from the bottom for the level, and the percentage inside it on two
lines, the number and "%". In the portable design's colors: the dimmed text color while the controller runs on its
battery, amber at 20 % or less, the suite's red at 10 % or less; while it charges, the modules above the level fill
one after another, upwards, again and again; full, all five. The level comes from the controller's input reports, in
tens of percent."""

from __future__ import annotations

import math

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from bc250_core.portable import AMBER, DIM, DOT, FONT, TEXT, px

MODULES = 5
STEP_MS = 450                       # one more module lit while charging
WIDTH, HEIGHT = 68, 104             # at 1280 x 720


def modules(capacity: int) -> int:
    """How many of the five modules a level fills: any charge lights the first, 100 % all five."""
    return max(1, min(MODULES, math.ceil(capacity / (100 / MODULES)))) if capacity > 0 else 0


def colour(capacity: int, status: str) -> str:
    if status in ("Charging", "Full") or capacity > 20:
        return DIM
    return AMBER if capacity > 10 else DOT


class BatteryIcon(QWidget):
    """set_battery(capacity, status) with the controller's values; None: not known yet, an empty outline."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.capacity: int | None = None
        self.status = ""
        self.extra = 0                  # charging: modules lit above the level, in turn
        self.timer = QTimer(self, interval=STEP_MS)
        self.timer.timeout.connect(self._step)
        self.setFixedSize(px(WIDTH), px(HEIGHT))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

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
        line = max(2.0, px(2.2))
        top = px(6)
        body = QRectF(line, top + line, self.width() - 2 * line, self.height() - top - 2 * line)
        p.setPen(QPen(QColor(TEXT), line))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(body, px(5), px(5))
        p.setBrush(QColor(TEXT))
        p.setPen(Qt.PenStyle.NoPen)
        terminal = body.width() * 0.36
        p.drawRoundedRect(QRectF(body.center().x() - terminal / 2, body.top() - top, terminal, top - 1), 2, 2)
        lit = self.lit_modules()
        fill = QColor(colour(self.capacity or 0, self.status))
        gap, inner = px(2), body.adjusted(px(4), px(4), -px(4), -px(4))
        height = (inner.height() - gap * (MODULES - 1)) / MODULES
        for index in range(MODULES):                    # from the bottom up
            cell = QRectF(inner.left(), inner.bottom() - (index + 1) * height - index * gap, inner.width(), height)
            if index < lit:
                p.setBrush(fill)
                p.drawRoundedRect(cell, 2, 2)
        # The percentage inside, on two lines and centered both ways; with a dark shadow, so it reads on the lit
        # modules and on the empty ones alike.
        font = QFont(FONT)
        font.setPixelSize(px(17))
        font.setWeight(QFont.Weight.ExtraBold)
        p.setFont(font)
        text = "—" if self.capacity is None else f"{self.capacity}\n%"
        p.setPen(QColor(0, 0, 0, 200))
        p.drawText(body.translated(1, 1), Qt.AlignmentFlag.AlignCenter, text)
        p.setPen(QColor("white") if self.capacity is not None else QColor(DIM))
        p.drawText(body, Qt.AlignmentFlag.AlignCenter, text)
        p.end()
