# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller test: every button, stick and trigger of the pad shown as it is pressed (bc250_core.gamepad's raw
events). A button lights amber while it is held and keeps an amber letter once it was pressed, so a button that
never answers stands out; the count says how many of them answered. The sticks are a dot in a circle, the triggers a
bar. The test has every button, B too, so it ends by holding B (HOLD seconds), the Finish pill or Escape."""

from __future__ import annotations

import time
from collections.abc import Callable

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QWidget

from bc250_core.portable import (AMBER, BODY, DIM, ON_AMBER, RAISED, TEXT, Pane, Pill, font, px,
                                 text_label)

HOLD = 1.5                      # s that B is held to end the test
# The buttons as the chips show them, in rows: SDL's name and the label (the Ally's face: A B X Y, View, the Menu
# button's ☰)
ROWS = [[("leftshoulder", "LB"), ("back", "View"), ("guide", "Xbox"), ("start", "☰"), ("rightshoulder", "RB")],
        [("dpad_up", "Up"), ("dpad_down", "Down"), ("dpad_left", "Left"), ("dpad_right", "Right")],
        [("a", "A"), ("b", "B"), ("x", "X"), ("y", "Y"), ("leftstick", "LS"), ("rightstick", "RS")]]
BUTTONS = [name for row in ROWS for name, _ in row]
# The Ally's back buttons are Armoury Crate's modifiers: Windows never sees them as buttons (owner, 28-10-2026)
BACK_BUTTONS = ("The back buttons M1 and M2 answer here only once Armoury Crate maps them to a button "
                "(Settings, Configure).")


class Chip(QLabel):
    """One button: raised gray; amber while held; an amber letter once it was pressed."""

    def __init__(self, label: str):
        super().__init__(label)
        self.setFont(font(BODY, QFont.Weight.Bold))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(px(64), px(40))
        self.held = self.seen = False
        self.paint()

    def set_held(self, held: bool) -> None:
        self.held = held
        self.seen = self.seen or held
        self.paint()

    def paint(self) -> None:
        fill = AMBER if self.held else RAISED
        color = ON_AMBER if self.held else AMBER if self.seen else TEXT
        self.setStyleSheet(f"color: {color}; background: {fill}; border-radius: {px(10)}px;")


class Stick(QWidget):
    """A stick: its travel as a circle, where it is as an amber dot; the dot fills when the stick is pressed."""

    def __init__(self, label: str):
        super().__init__()
        self.label, self.x, self.y, self.pressed = label, 0.0, 0.0, False
        self.setMinimumSize(px(110), px(116))          # the circle and the line under it
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def set_axis(self, axis: str, value: float) -> None:
        if axis == "x":
            self.x = value
        else:
            self.y = value
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = px(40)
        center = QPointF(self.width() / 2, px(8) + radius)
        painter.setPen(QPen(QColor(DIM), px(2)))
        painter.setBrush(QColor(RAISED))
        painter.drawEllipse(center, radius, radius)
        dot = QPointF(center.x() + self.x * (radius - px(9)), center.y() + self.y * (radius - px(9)))
        painter.setPen(QPen(QColor(AMBER), px(3)))
        painter.setBrush(QColor(AMBER) if self.pressed else Qt.BrushStyle.NoBrush)
        painter.drawEllipse(dot, px(9), px(9))
        painter.setPen(QColor(DIM))
        painter.setFont(font(BODY))
        painter.drawText(QRectF(0, center.y() + radius + px(4), self.width(), px(24)),
                         Qt.AlignmentFlag.AlignCenter, f"{self.label}  {self.x:+.2f}  {self.y:+.2f}")


class Trigger(QWidget):
    """A trigger: how far it is pulled, as an amber bar from 0 to 1."""

    def __init__(self, label: str):
        super().__init__()
        self.label, self.value = label, 0.0
        self.setMinimumSize(px(160), px(48))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, value: float) -> None:
        self.value = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar = QRectF(0, px(24), self.width(), px(18))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(RAISED))
        painter.drawRoundedRect(bar, px(9), px(9))
        if self.value > 0:
            painter.setBrush(QColor(AMBER))
            painter.drawRoundedRect(QRectF(bar.x(), bar.y(), max(bar.height(), bar.width() * self.value),
                                           bar.height()), px(9), px(9))
        painter.setPen(QColor(DIM))
        painter.setFont(font(BODY))
        painter.drawText(QRectF(0, 0, self.width(), px(22)), Qt.AlignmentFlag.AlignLeft,
                         f"{self.label}  {round(self.value * 100)}%")


class ControllerPane(Pane):
    """The test itself: feed() it the pad's raw events while it runs (start() to finish())."""

    finished = pyqtSignal()

    def __init__(self, clock: Callable[[], float] = time.monotonic, parent: QWidget | None = None):
        super().__init__(parent)
        self.clock = clock
        self.running = False
        self.b_since: float | None = None
        self.column.addWidget(text_label("Controller", 24, QFont.Weight.ExtraBold))
        self.name = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.name)
        self.column.addSpacing(px(12))
        grid = QGridLayout()
        grid.setSpacing(px(6))
        self.chips: dict[str, Chip] = {}
        for r, row in enumerate(ROWS):
            for c, (name, label) in enumerate(row):
                self.chips[name] = Chip(label)
                grid.addWidget(self.chips[name], r, c)
        self.column.addLayout(grid)
        self.column.addSpacing(px(12))
        sticks = QHBoxLayout()
        self.sticks = {"left": Stick("Left stick"), "right": Stick("Right stick")}
        sticks.addWidget(self.sticks["left"])
        sticks.addWidget(self.sticks["right"])
        self.column.addLayout(sticks)
        self.triggers = {"lefttrigger": Trigger("LT"), "righttrigger": Trigger("RT")}
        triggers = QHBoxLayout()
        triggers.setSpacing(px(24))
        triggers.addWidget(self.triggers["lefttrigger"])
        triggers.addWidget(self.triggers["righttrigger"])
        self.column.addLayout(triggers)
        self.count = text_label("", BODY + 1, QFont.Weight.DemiBold)
        self.column.addWidget(self.count)
        self.back_buttons = text_label(BACK_BUTTONS, BODY, color=DIM, wrap=True)
        self.column.addWidget(self.back_buttons)
        self.column.addStretch()
        self.finish_pill = Pill("Finish", main=True)
        self.finish_pill.activated.connect(self.finish)
        self.column.addWidget(self.finish_pill)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.check_hold)
        self.reset()

    def set_pads(self, names: list[str]) -> None:
        self.name.setText(", ".join(names) if names else "No controller found. Connect one, or use the Ally's own.")

    def reset(self) -> None:
        for chip in self.chips.values():
            chip.held = chip.seen = False
            chip.paint()
        for stick in self.sticks.values():
            stick.x = stick.y = 0.0
            stick.pressed = False
            stick.update()
        for trigger in self.triggers.values():
            trigger.set_value(0.0)
        self.update_count()

    def start(self) -> None:
        self.reset()
        self.running = True
        self.b_since = None
        self.timer.start()

    def finish(self) -> None:
        if not self.running:
            return
        self.running = False
        self.timer.stop()
        self.b_since = None
        self.finished.emit()

    def seen(self) -> list[str]:
        return [name for name in BUTTONS if self.chips[name].seen]

    def update_count(self) -> None:
        self.count.setText(f"{len(self.seen())} of {len(BUTTONS)} buttons answered")

    def feed(self, kind: str, name: str, value) -> None:
        """A raw event of the pad: ("button", name, pressed) or ("axis", name, value)."""
        if not self.running:
            return
        if kind == "button" and name in self.chips:
            self.chips[name].set_held(bool(value))
            if name in ("leftstick", "rightstick"):
                stick = self.sticks["left" if name == "leftstick" else "right"]
                stick.pressed = bool(value)
                stick.update()
            if name == "b":
                self.b_since = self.clock() if value else None
            self.update_count()
        elif kind == "axis":
            if name in self.triggers:
                self.triggers[name].set_value(float(value))
            elif name in ("leftx", "lefty", "rightx", "righty"):
                self.sticks[name[:-1]].set_axis(name[-1], float(value))

    def check_hold(self) -> None:
        if self.b_since is not None and self.clock() - self.b_since >= HOLD:
            self.finish()
