# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller as a drawing of the app's own (no Sony artwork), in the theme's colors with the gaming apps' blue
for what is lit. It shows the controller live: each button lights while it is pressed, the sticks move and the
triggers fill, and the light bar takes the color the controller has. A page can light whole parts (the sticks, the
Edge's back buttons) to show what it is about. It also draws a USB-C cable going into the port (the page that asks
to connect), data flowing down that cable with the touchpad filling (a firmware update), and a shake (the vibration
test).

Everything is drawn in a fixed box (the controller seen from the front, its top edge at y 38), the body 85 % as wide
as it is high would make it (owner, 23-10-2026), scaled to the widget, keeping the proportions."""

from __future__ import annotations

import math

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QTransform
from PyQt6.QtWidgets import QSizePolicy, QWidget

from bc250_core.theme import THEME
from bc250_core.widgets import hide_tooltip, show_tooltip

from . import style

NARROW = 0.85                       # the body's width against the first drawing
STRETCH = 36.0                      # the touchpad this much wider, all else out by half (owner, 23-10-2026)
BOX = QRectF(25 - STRETCH / 2, 0, 350 + STRETCH, 270)
CABLE_SPACE = 120.0                 # above the controller, for the cable
# Whole parts, as pages and profiles light them, and the buttons each is made of.
PART_BUTTONS = {
    "body": (), "touchpad": ("touchpad",), "lightbar": (), "usb": (), "ps": ("ps",),
    "dpad": ("up", "down", "left", "right"), "face": ("triangle", "circle", "cross", "square"),
    "sticks": ("l3", "r3"), "bumpers": ("l1", "r1"), "triggers": ("l2", "r2"), "create": ("create", "options"),
    "fn": ("fn_left", "fn_right"), "back": ("back_left", "back_right"),
}
PARTS = tuple(PART_BUTTONS)
BUTTONS = tuple(button for buttons in PART_BUTTONS.values() for button in buttons) + ("mute",)
# The face buttons' symbols in the colors of the first PlayStation pads.
FACE_COLOURS = {"triangle": "#3dbf9c", "circle": "#e8505b", "cross": "#6f9fe8", "square": "#e48fc0"}
CABLE_PERIOD_MS = 2400
FRAME_MS = 33
SHAKE_AMPLITUDE = 3.0


def x(value: float) -> float:
    """A horizontal position of the first drawing, 85 % as far from the middle and then moved out by half of STRETCH,
    so that only the touchpad, across the middle, gets wider; sizes are not scaled."""
    offset = value - 200
    return 200 + offset * NARROW + math.copysign(STRETCH / 2, offset) if offset else 200.0


# The d-pad and the face buttons, each moved towards its edge by 80 % of a face button's size (owner, 23-10-2026).
PAD_SHIFT = 0.8 * 26
DPAD_X = x(92) - PAD_SHIFT
FACE_X = x(308) + PAD_SHIFT


def body_path() -> QPainterPath:
    """The outline: a wide top with the touchpad, and two grips."""
    # The top runs nearly straight out to small corners (owner, 23-10-2026: a sturdier look, so that the bumpers and
    # triggers sit on the body instead of above a rounded top).
    path = QPainterPath(QPointF(x(90), 36))
    for c1, c2, end in (((150, 32), (250, 32), (310, 36)), ((350, 38), (368, 44), (374, 62)),
                        ((382, 95), (395, 200), (372, 245)), ((352, 262), (322, 250), (308, 220)),
                        ((296, 192), (285, 172), (260, 168)), ((230, 165), (170, 165), (140, 168)),
                        ((115, 172), (104, 192), (92, 220)), ((78, 250), (48, 262), (28, 245)),
                        ((5, 200), (18, 95), (26, 62)), ((32, 44), (50, 38), (90, 36))):
        path.cubicTo(QPointF(x(c1[0]), c1[1]), QPointF(x(c2[0]), c2[1]), QPointF(x(end[0]), end[1]))
    return path


def _rect(left: float, top: float, width: float, height: float, radius: float = 0.0) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(QRectF(left, top, width, height), radius, radius)
    return path


def _circle(cx: float, cy: float, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), radius, radius)
    return path


def regions(edge: bool) -> list[tuple[str, QPainterPath]]:
    """Each part's name and its shape, as _draw draws them (the sticks at rest), the topmost last: what the
    tooltip names under the mouse (owner, 23-10-2026: one text for the whole drawing said nothing)."""
    found: list[tuple[str, QPainterPath]] = [
        ("L2 trigger", _rect(x(62), 14, 74 * NARROW, 30, 10)), ("R2 trigger", _rect(x(264), 14, 74 * NARROW, 30, 10)),
        ("L1", _rect(x(58), 28, 82 * NARROW, 16, 7)), ("R1", _rect(x(260), 28, 82 * NARROW, 16, 7)),
    ]
    if edge:
        for name, (cx, cy), angle in (("Left back button", (x(112), 214), 62),
                                      ("Right back button", (x(288), 214), -62)):
            turn = QTransform().translate(cx, cy).rotate(angle)
            found.append((name, turn.map(_rect(-20, -7, 40, 14, 7))))
    found += [
        ("USB-C port: the cable for charging and the firmware update", _rect(190, 33, 20, 7, 2)),
        ("Light bar", _rect(x(136) - 2, 50, 10, 54)), ("Light bar", _rect(x(264) - 8, 50, 10, 54)),
        ("Touchpad: press it to click", _rect(x(138) + 6, 46, x(262) - x(138) - 12, 64, 10)),
        ("Create", _rect(x(112) - 4, 50, 8, 16, 4)), ("Options", _rect(x(280) - 4, 50, 8, 16, 4)),
    ]
    cx, cy = DPAD_X, 106.0
    for name, (dx, dy) in (("D-pad up", (0, -1)), ("D-pad down", (0, 1)), ("D-pad left", (-1, 0)),
                           ("D-pad right", (1, 0))):
        found.append((name, _rect(cx + dx * 20 - 8.5, cy + dy * 20 - 8.5, 17, 17, 4)))
    cx = FACE_X
    for name, (dx, dy) in (("Triangle", (0, -25)), ("Circle", (25, 0)), ("Cross", (0, 25)), ("Square", (-25, 0))):
        found.append((name, _circle(cx + dx, cy + dy, 13)))
    found += [("Left stick: press it for L3", _circle(x(150), 150, 22)),
              ("Right stick: press it for R3", _circle(x(250), 150, 22)),
              ("Player indicator", _rect(167, 112, 66, 11, 3)),
              ("PS button", _circle(200, 140, 7)), ("Mute", _rect(194, 150, 12, 8, 2))]
    if edge:
        found += [("Fn, left: hold it and press a face button to switch profiles", _rect(x(150) - 10, 180, 20, 8, 4)),
                  ("Fn, right: hold it and press a face button to switch profiles", _rect(x(250) - 10, 180, 20, 8, 4))]
    return found


def part_at(edge: bool, point: QPointF) -> str:
    """The name of the part at *point* (in the drawing's box), or "" off the parts."""
    for name, shape in reversed(regions(edge)):
        if shape.contains(point):
            return name
    return ""


def cable_offset(phase: float) -> float:
    """How far the plug is above the port, 0 (in) to 70: it comes down, stays in a moment, and starts again."""
    phase %= 1.0
    if phase < 0.6:
        return 70 * (1 - math.sin(phase / 0.6 * math.pi / 2))
    return 0.0


class ControllerView(QWidget):
    """The drawing. *edge* adds the Edge's Fn and back buttons."""

    resized = pyqtSignal()

    def __init__(self, edge: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.edge = edge
        self.lit_parts: set[str] = set()
        self.pressed: set[str] = set()                  # BUTTONS held down now
        self.sticks = (0.0, 0.0, 0.0, 0.0)              # left x, y, right x, y: -1 to 1
        self.triggers = (0.0, 0.0)                      # L2, R2: 0 to 1
        self.light: QColor | None = None                # the light bar's color; None: unknown, drawn dark
        self.players: tuple[bool, ...] | None = None    # the five player lights, left to right; None: unknown
        self.cable_phase: float | None = None
        self.data_progress: float | None = None         # 0 to 1 while an update sends the firmware
        self.data_phase = 0.0
        self.shake_side = ""                            # "left" or "right" while that motor runs
        self.shake_phase = 0.0
        self.hovered = ""                               # the part under the mouse, named in the tooltip
        self.setMouseTracking(True)
        self.timer = QTimer(self, interval=FRAME_MS)
        self.timer.timeout.connect(self._step)
        self.setMinimumSize(240, 170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # ------------------------------------------------------------------ state
    def set_edge(self, edge: bool) -> None:
        if edge != self.edge:
            self.edge = edge
            self.update()

    def lit(self, parts: set[str] | tuple[str, ...]) -> None:
        unknown = set(parts) - set(PARTS)
        if unknown:
            raise ValueError(f"no such part: {', '.join(sorted(unknown))}")
        if set(parts) != self.lit_parts:
            self.lit_parts = set(parts)
            self.update()

    def show_input(self, pressed: set[str], sticks: tuple[float, float, float, float],
                   triggers: tuple[float, float]) -> None:
        """What the controller reports now; drawn when it changed."""
        if (pressed, sticks, triggers) != (self.pressed, self.sticks, self.triggers):
            self.pressed, self.sticks, self.triggers = set(pressed), sticks, triggers
            self.update()

    def clear_input(self) -> None:
        self.show_input(set(), (0.0, 0.0, 0.0, 0.0), (0.0, 0.0))

    def set_light(self, colour: QColor | None) -> None:
        self.light = colour
        self.update()

    def set_players(self, lights: tuple[bool, ...] | None) -> None:
        if lights != self.players:
            self.players = lights
            self.update()

    def _name(self, name: str) -> str:
        """A part's name for the tooltip; the player indicator says which player it shows."""
        if name != "Player indicator":
            return name
        from .controller import PLAYER_LIGHTS
        number = PLAYER_LIGHTS.get(self.players) if self.players else None
        return f"Player indicator: player {number}" if number else "Player indicator"

    def animate_cable(self, on: bool) -> None:
        """The cable going into the port, again and again, while the page is shown."""
        self.cable_phase = 0.0 if on else None
        self._run()

    def show_data(self, progress: float | None) -> None:
        """Data flowing down the plugged-in cable, the touchpad filling with *progress* (0 to 1); None stops it."""
        self.data_progress = None if progress is None else max(0.0, min(1.0, progress))
        self._run()

    def shake(self, side: str) -> None:
        """The grip of the motor that runs ("left" or "right") shakes; "" stops it."""
        self.shake_side = side
        self._run()

    def _run(self) -> None:
        busy = self.cable_phase is not None or self.data_progress is not None or bool(self.shake_side)
        if busy and not self.timer.isActive():
            self.timer.start()
        elif not busy and self.timer.isActive():
            self.timer.stop()
        self.update()

    def _step(self) -> None:
        if self.cable_phase is not None:
            self.cable_phase = (self.cable_phase + FRAME_MS / CABLE_PERIOD_MS) % 1.0
        self.data_phase = (self.data_phase + FRAME_MS / 600) % 1.0
        self.shake_phase += 1
        self._run()

    # ---------------------------------------------------------------- tooltip
    def to_box(self, point: QPointF) -> QPointF:
        """A point of the widget in the drawing's box, as paintEvent maps the box onto the widget."""
        box = self._box()
        scale = min(self.width() / box.width(), self.height() / box.height())
        return QPointF((point.x() - self.width() / 2) / scale + box.center().x(),
                       (point.y() - self.height() / 2) / scale + box.center().y())

    def body_span(self) -> tuple[float, float]:
        """Where the drawn body starts and ends, left to right, in the widget: for lining things up with it."""
        box = self._box()
        scale = min(self.width() / box.width(), self.height() / box.height())
        bounds = body_path().boundingRect()
        return (self.width() / 2 + (bounds.left() - box.center().x()) * scale,
                self.width() / 2 + (bounds.right() - box.center().x()) * scale)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self.resized.emit()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        name = part_at(self.edge, self.to_box(event.position()))
        if name != self.hovered:
            self.hovered = name
            if name:
                show_tooltip(event.globalPosition().toPoint(), self._name(name), self)
            else:
                hide_tooltip()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self.hovered:
            self.hovered = ""
            hide_tooltip()
        super().leaveEvent(event)

    def event(self, event) -> bool:  # noqa: N802 (Qt override)
        if event.type() == QEvent.Type.ToolTip:   # the part's name comes with the mouse, not after a pause
            return True
        return super().event(event)

    # ------------------------------------------------------------------ paint
    def _box(self) -> QRectF:
        top = -CABLE_SPACE if self.cable_phase is not None or self.data_progress is not None else BOX.top()
        return QRectF(BOX.left(), top, BOX.width(), BOX.bottom() - top)

    def is_lit(self, button: str) -> bool:
        return button in self.pressed or any(button in PART_BUTTONS[part] for part in self.lit_parts)

    def _colours(self, lit: bool) -> tuple[QColor, QColor]:
        if lit:
            return QColor(style.BLUE_LIGHT), QColor(style.BLUE)
        return QColor(THEME.button_low), QColor(THEME.edge)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = self._box()
        scale = min(self.width() / box.width(), self.height() / box.height())
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(scale, scale)
        painter.translate(-box.center().x(), -box.center().y())
        if self.shake_side:
            painter.translate(SHAKE_AMPLITUDE * math.sin(self.shake_phase * 2.4), 0)
        self._draw(painter)
        painter.end()

    def _draw(self, p: QPainter) -> None:
        if self.cable_phase is not None:
            self._draw_cable(p, cable_offset(self.cable_phase))
        elif self.data_progress is not None:
            self._draw_cable(p, 0.0, data=True)
        self._draw_triggers(p)
        for button, left in (("l1", x(58)), ("r1", x(260))):
            self._shape(p, self.is_lit(button), lambda left=left: p.drawRoundedRect(QRectF(left, 28, 82 * NARROW, 16),
                                                                                  7, 7))
        if self.edge:
            self._draw_paddles(p)
        p.setBrush(QColor(style.BLUE_LIGHT) if "body" in self.lit_parts else QColor(THEME.button))
        p.setPen(QPen(QColor(THEME.edge), 2))
        p.drawPath(body_path())
        if self.shake_side:
            self._draw_shake(p)
        self._shape(p, "usb" in self.lit_parts, lambda: p.drawRoundedRect(QRectF(190, 33, 20, 7), 2, 2))
        self._draw_lightbar(p)
        self._draw_touchpad(p)
        for button, left in (("create", x(112)), ("options", x(280))):
            self._shape(p, self.is_lit(button), lambda left=left: p.drawRoundedRect(QRectF(left - 4, 50, 8, 16),
                                                                                  4, 4))
        self._draw_dpad(p)
        self._draw_face(p)
        self._draw_sticks(p)
        self._draw_players(p)
        self._shape(p, self.is_lit("ps"), lambda: p.drawEllipse(QPointF(200, 140), 7, 7))
        self._shape(p, self.is_lit("mute"), lambda: p.drawRoundedRect(QRectF(194, 152, 12, 4), 2, 2))
        if self.edge:
            for button, centre in (("fn_left", x(150)), ("fn_right", x(250))):
                self._shape(p, self.is_lit(button),
                            lambda centre=centre: p.drawRoundedRect(QRectF(centre - 10, 180, 20, 8), 4, 4))

    def _shape(self, p: QPainter, lit: bool, draw) -> None:
        fill, outline = self._colours(lit)
        p.setBrush(fill)
        p.setPen(QPen(outline, 1.6))
        draw()

    def _draw_paddles(self, p: QPainter) -> None:
        """The Edge's back buttons, paddles under the grips: drawn behind the body, each sticking out from its
        grip's inner edge into the gap between the grips (owner, 23-10-2026; first drawn dashed on the grips)."""
        for button, (cx, cy), angle in (("back_left", (x(112), 214), 62), ("back_right", (x(288), 214), -62)):
            fill, outline = self._colours(self.is_lit(button))
            p.save()
            p.translate(cx, cy)
            p.rotate(angle)
            p.setBrush(fill)
            p.setPen(QPen(outline, 1.6))
            p.drawRoundedRect(QRectF(-20, -7, 40, 14), 7, 7)
            p.restore()

    def _draw_triggers(self, p: QPainter) -> None:
        """L2 and R2 behind the top edge; a pulled trigger fills down from its top edge as far as it is pulled."""
        for index, (button, left) in enumerate((("l2", x(62)), ("r2", x(264)))):
            rect = QRectF(left, 14, 74 * NARROW, 30)
            self._shape(p, button in [b for part in self.lit_parts for b in PART_BUTTONS[part]],
                        lambda rect=rect: p.drawRoundedRect(rect, 10, 10))
            pulled = self.triggers[index]
            if pulled > 0.02:
                p.save()
                clip = QPainterPath()
                clip.addRoundedRect(rect, 10, 10)
                p.setClipPath(clip)
                # From the top edge: the lower part is behind the bumper.
                p.fillRect(QRectF(rect.left(), rect.top(), rect.width(), 14 * pulled + 1), QColor(style.BLUE_LIGHT))
                p.restore()

    def _draw_lightbar(self, p: QPainter) -> None:
        """Two strips along the touchpad, in the light bar's color (dark while it is not known)."""
        if "lightbar" in self.lit_parts:
            colour = QColor(style.BLUE_LIGHT)
        elif self.light is not None:
            colour = QColor(self.light)
        else:
            colour = QColor(THEME.edge)
        p.setPen(QPen(colour, 4, cap=Qt.PenCapStyle.RoundCap))
        for left in (x(136) + 3, x(264) - 3):
            p.drawLine(QPointF(left, 54), QPointF(left, 100))

    def _draw_players(self, p: QPainter) -> None:
        """The five player lights under the touchpad, white where the controller's are on; large enough to see on a
        big screen (owner, 23-10-2026)."""
        p.setPen(Qt.PenStyle.NoPen)
        for index in range(5):
            on = self.players is not None and self.players[index]
            p.setBrush(QColor("#ffffff") if on else QColor(THEME.edge))
            p.drawRoundedRect(QRectF(200 + (index - 2) * 13 - 5, 115, 10, 5), 2.5, 2.5)

    def _draw_touchpad(self, p: QPainter) -> None:
        rect = QRectF(x(138) + 6, 46, x(262) - x(138) - 12, 64)
        self._shape(p, self.is_lit("touchpad"), lambda: p.drawRoundedRect(rect, 10, 10))
        if self.data_progress is not None:
            p.save()
            clip = QPainterPath()
            clip.addRoundedRect(rect, 10, 10)
            p.setClipPath(clip)
            p.fillRect(QRectF(rect.left(), rect.top(), rect.width() * self.data_progress, rect.height()),
                       QColor(style.BLUE_LIGHT))
            p.restore()
            p.setPen(QColor(THEME.text))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self.data_progress:.0%}")

    def _draw_dpad(self, p: QPainter) -> None:
        """Four white arms with a black border and a gap between them (owner, 23-10-2026); a pressed one blue."""
        cx, cy = DPAD_X, 106.0
        for button, (dx, dy) in (("up", (0, -1)), ("down", (0, 1)), ("left", (-1, 0)), ("right", (1, 0))):
            lit = self.is_lit(button)
            p.setBrush(QColor(style.BLUE_LIGHT) if lit else QColor("white"))
            p.setPen(QPen(QColor(style.BLUE) if lit else QColor("black"), 1.6))
            p.drawRoundedRect(QRectF(cx + dx * 20 - 8.5, cy + dy * 20 - 8.5, 17, 17), 4, 4)

    def _draw_face(self, p: QPainter) -> None:
        cx, cy = FACE_X, 106.0
        centres = {"triangle": (0, -25), "circle": (25, 0), "cross": (0, 25), "square": (-25, 0)}
        for button, (dx, dy) in centres.items():
            centre = QPointF(cx + dx, cy + dy)
            colour = QColor(FACE_COLOURS[button])
            lit = self.is_lit(button)
            p.setBrush(colour if lit else QColor(THEME.button_low))
            p.setPen(QPen(colour.darker(150) if lit else QColor(THEME.edge), 1.6))
            p.drawEllipse(centre, 13, 13)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("white") if lit else colour, 1.8))
            if button == "triangle":
                p.drawPolygon([centre + QPointF(0, -6), centre + QPointF(6, 4.5), centre + QPointF(-6, 4.5)])
            elif button == "circle":
                p.drawEllipse(centre, 6, 6)
            elif button == "cross":
                p.drawLine(centre + QPointF(-5, -5), centre + QPointF(5, 5))
                p.drawLine(centre + QPointF(-5, 5), centre + QPointF(5, -5))
            else:
                p.drawRect(QRectF(centre.x() - 5, centre.y() - 5, 10, 10))

    def _draw_sticks(self, p: QPainter) -> None:
        """Each stick's base, and its cap moved as far as the stick is pushed."""
        for index, (button, cx) in enumerate((("l3", x(150)), ("r3", x(250)))):
            dx, dy = self.sticks[2 * index], self.sticks[2 * index + 1]
            lit = self.is_lit(button)
            self._shape(p, False, lambda cx=cx: p.drawEllipse(QPointF(cx, 150), 22, 22))
            pushed = abs(dx) > 0.08 or abs(dy) > 0.08
            fill, outline = self._colours(lit or pushed)
            centre = QPointF(cx + dx * 9, 150 + dy * 9)
            p.setBrush(fill)
            p.setPen(QPen(outline, 1.6))
            p.drawEllipse(centre, 15, 15)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(outline, 1.0))
            p.drawEllipse(centre, 10, 10)

    def _draw_shake(self, p: QPainter) -> None:
        """Motion lines beside the grip whose motor runs."""
        p.setPen(QPen(QColor(style.BLUE_LIGHT), 2, cap=Qt.PenCapStyle.RoundCap))
        left = self.shake_side == "left"
        edge = x(14) if left else x(386)
        sign = -1 if left else 1
        for row, length in ((170, 10), (190, 14), (210, 10)):
            wobble = 2 * math.sin(self.shake_phase * 1.7 + row)
            p.drawLine(QPointF(edge + sign * 4 + wobble, row), QPointF(edge + sign * (4 + length) + wobble, row))

    def _draw_cable(self, p: QPainter, offset: float, data: bool = False) -> None:
        """A USB-C plug above the port, *offset* away from it, and its cable up to the top; with *data*, dots
        flowing down the cable into the controller."""
        plug_top = 33 - 26 - offset
        p.setPen(QPen(QColor(THEME.edge), 5, cap=Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(200, -CABLE_SPACE), QPointF(200, plug_top))
        if data:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(style.BLUE_LIGHT))
            span = plug_top + CABLE_SPACE
            for dot in range(6):
                y = -CABLE_SPACE + ((dot / 6 + self.data_phase) % 1.0) * span
                p.drawEllipse(QPointF(200, y), 3.5, 3.5)
        p.setPen(QPen(QColor(THEME.edge), 1.6))
        p.setBrush(QColor(THEME.button))
        p.drawRoundedRect(QRectF(186, plug_top, 28, 20), 4, 4)        # the plug's grip
        p.setBrush(QColor(style.BLUE_LIGHT))
        p.drawRoundedRect(QRectF(192, plug_top + 20, 16, 7), 2, 2)    # the metal end, in the blue
