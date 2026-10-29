# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller test: every button, stick and trigger of the pad shown as it is pressed (bc250_core.gamepad's raw
events). A button lights amber while it is held and keeps an amber letter once it was pressed, so a button that
never answers stands out; the count says how many of them answered. The sticks are a dot in a circle, the triggers a
bar, and the stick lights follow the buttons and the sticks (FACE_COLORS). The test has every button, B too, so it
ends by holding B (HOLD seconds), a tap on the legend's B Hold to finish, or Escape."""

from __future__ import annotations

import time
from collections.abc import Callable

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QWidget

from bc250_core.portable import AMBER, BODY, DIM, ON_AMBER, RAISED, TEXT, InfoPill, Pane, font, px, text_label

from . import lights

HOLD = 1.5                      # s that B is held to end the test
# The buttons as the chips show them, in rows: SDL's name and the label (the Ally's face: A B X Y, View, the Menu
# button's ☰)
ROWS = [[("leftshoulder", "LB"), ("back", "View"), ("guide", "Xbox"), ("start", "☰"), ("rightshoulder", "RB")],
        [("dpad_up", "Up"), ("dpad_down", "Down"), ("dpad_left", "Left"), ("dpad_right", "Right"),
         ("m1m2", "M1/M2")],
        [("a", "A"), ("b", "B"), ("x", "X"), ("y", "Y"), ("leftstick", "LS"), ("rightstick", "RS")]]
BUTTONS = [name for row in ROWS for name, _ in row]
BACK = "m1m2"                   # the back buttons' chip: only where the handheld's ASUS channel reports them
# The Ally's back buttons are Armoury Crate's modifiers, never gamepad buttons; its ASUS channel reports either of them
# as one code (back_buttons.py, owner's Ally X 28-10-2026). The text is behind the information icon at the pane's top
# right: two lines of it did not fit the 720 px high screen
BACK_TITLE = "The back buttons M1 and M2"
BACK_BUTTONS = ("M1 and M2 light the M1/M2 chip: Armoury Crate reports either of them the same way, so Windows "
                "cannot tell them apart. By default they are Armoury Crate's own modifiers: held with A a screenshot, "
                "with Y a recording, with Up the on-screen keyboard. To use them as two buttons, map them in Armoury "
                "Crate (Settings, Configure, M1 or M2: untick Secondary Function and choose a button); they then "
                "light that button here.")
NO_BACK_BUTTONS = ("The back buttons of an ASUS handheld show here as M1/M2. This handheld reports none: map its back "
                   "buttons to a controller button in its maker's app, and they light that button.")


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

    def __init__(self, clock: Callable[[], float] = time.monotonic, lamps: lights.Lights | None = None,
                 parent: QWidget | None = None):
        """*lamps*: the stick lights, opened while the test runs (None: a test without them)."""
        super().__init__(parent)
        self.clock = clock
        self.lamps = lamps
        self.lit: tuple | None = None               # what the lights show now: (rgb, lamps), set only on a change
        self.running = False
        self.b_since: float | None = None
        heading = QHBoxLayout()
        heading.addWidget(text_label("Controller", 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.back_buttons = InfoPill(BACK_TITLE, BACK_BUTTONS)        # top right: the most room (owner, 28-10-2026)
        heading.addWidget(self.back_buttons, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(heading)
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
        self.column.addSpacing(px(6))
        self.lights_line = text_label("", BODY + 1, color=DIM, wrap=True)     # what Windows reports, what is lit
        self.lights_line.setVisible(lamps is not None)
        self.column.addWidget(self.lights_line)
        self.column.addStretch()
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.check_hold)
        self.has_back = True
        self.set_back_buttons(False)                    # until the window found the ASUS channel
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
        self.back_buttons.hide()                        # every button is the test's: no popup meanwhile (a pill is
        self.b_since = None                             # never disabled: hidden when it does not belong to the state)
        self.timer.start()
        self.open_lights()

    def finish(self) -> None:
        if not self.running:
            return
        self.running = False
        self.timer.stop()
        self.b_since = None
        self.back_buttons.show()
        self.close_lights()
        self.finished.emit()

    # The stick lights, while the test runs

    def open_lights(self) -> None:
        """The stick lights taken from Windows for the test, and what it reports about them on the pane's last line."""
        self.lit = None
        if self.lamps is None:
            return
        try:
            self.found = self.lamps.open()
        except Exception as error:  # noqa: BLE001  (pywinrt's errors are not OSError: shown, never raised)
            self.found = None
            self.lights_line.setText(f"Stick lights: Windows did not answer ({error}). {NO_LIGHTS}")
            return
        if self.found is None:
            self.lights_line.setText(NO_LIGHTS)
        elif not self.found.enabled:
            self.lights_line.setText(f"Stick lights: {self.found.text()} Switch it on in {lights.SETTINGS}, then "
                                     "start the test again.")
        elif not self.found.available:
            self.lights_line.setText(f"Stick lights: {self.found.text()} {NOT_IN_FRONT}")
        else:
            self.lights_line.setText(f"Stick lights: {self.found.text()} {LIGHTS_HINT}")

    def close_lights(self) -> None:
        """Windows gets the lights back (Armoury Crate sets them again)."""
        if self.lamps is not None and self.lamps.array is not None:
            self.lamps.close()
            self.lights_line.setText(self.lights_line.text().split(" Now:")[0])

    def light(self, name: str, rgb: tuple[int, int, int], which: tuple[int, ...] | None) -> None:
        """*rgb* on *which* stick's ring (both when None), the other dark; only when it changes, and said on the
        pane's last line."""
        if self.lamps is None or self.lamps.array is None or (rgb, which) == self.lit:
            return
        try:
            done = self.lamps.show(rgb, which)
        except Exception as error:  # noqa: BLE001  (as above)
            self.lights_line.setText(f"Stick lights: Windows did not take it ({error}).")
            self.lamps.close()
            return
        if done:
            self.lit = (rgb, which)
            where = {lights.LEFT: "the left stick", lights.RIGHT: "the right stick"}.get(which, "both sticks")
            report = self.lights_line.text().split(" Now:")[0]
            self.lights_line.setText(f"{report} Now: {name} on {where}.")

    def buttons(self) -> list[str]:
        """The buttons this controller can answer with: M1/M2 only where the ASUS channel reports them."""
        return [name for name in BUTTONS if name != BACK or self.has_back]

    def set_back_buttons(self, available: bool) -> None:
        self.has_back = available
        self.chips[BACK].setVisible(available)
        self.back_buttons.info = BACK_BUTTONS if available else NO_BACK_BUTTONS
        self.update_count()

    def seen(self) -> list[str]:
        return [name for name in self.buttons() if self.chips[name].seen]

    def update_count(self) -> None:
        self.count.setText(f"{len(self.seen())} of {len(self.buttons())} buttons answered")

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
            if value and name in FACE_COLORS:
                self.light(*FACE_COLORS[name], None)
            elif value and name in ("leftstick", "rightstick"):
                self.light("White", lights.COLORS["White"], lights.LEFT if name == "leftstick" else lights.RIGHT)
            self.update_count()
        elif kind == "axis":
            if name in self.triggers:
                self.triggers[name].set_value(float(value))
            elif name in ("leftx", "lefty", "rightx", "righty"):
                stick = self.sticks[name[:-1]]
                stick.set_axis(name[-1], float(value))
                if max(abs(stick.x), abs(stick.y)) >= TILT:
                    self.light("White", lights.COLORS["White"], lights.LEFT if stick is self.sticks["left"]
                               else lights.RIGHT)

    def check_hold(self) -> None:
        if self.b_since is not None and self.clock() - self.b_since >= HOLD:
            self.finish()


# The stick lights are part of the button test (owner, 29-10-2026: "we were planning on including the LED test in
# the controller test"): while it runs, A, B, X and Y light both sticks in their color, a stick moved or pressed
# lights its own ring white, the other dark. Windows lets the app set them only while its window is in front, and
# gets them back when the test ends.
FACE_COLORS = {"a": ("Green", (0, 255, 0)), "b": ("Red", (255, 0, 0)), "x": ("Blue", (0, 0, 255)),
               "y": ("Yellow", (255, 200, 0))}
TILT = 0.5                      # a stick this far from the middle lights its ring
LIGHTS_HINT = "A, B, X and Y light both sticks in their color; a stick moved or pressed lights its own ring."
NO_LIGHTS = ("Stick lights: Windows reports none it can set. Where the controller has them (the ROG Xbox Ally's "
             f"rings around the sticks), switch Dynamic Lighting on in {lights.SETTINGS}, with the controller "
             "listed and on, then start the test again.")
NOT_IN_FRONT = ("Windows lets the app set them only while its window is in front: close what is over it (Armoury "
                "Crate's overlay, Steam's), then start the test again.")
