# SPDX-License-Identifier: GPL-3.0-or-later
"""A game controller for Suite Big Picture Mode, read with pygame-ce (SDL's game controller layer, which gives every
pad the same button names): d-pad and left stick move, A accepts, B goes back, the shoulder buttons change the
category, Y or Start switch to Suite Desktop Mode. The portal only listens while its own window has the focus, so a
game's input never moves it. Without pygame-ce, or without a controller, nothing happens."""

from __future__ import annotations

import os
import time
from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

POLL_MS = 16
DEADZONE = 0.55                 # of the stick's travel: beyond it the stick counts as pushed
FIRST_REPEAT = 0.4              # s before a held direction repeats, then every REPEAT s
REPEAT = 0.12
DIRECTIONS = ("up", "down", "left", "right")

BUTTONS = {                     # SDL's button names (pygame's CONTROLLER_BUTTON_*, in lower case) to actions
    "dpad_up": "up", "dpad_down": "down", "dpad_left": "left", "dpad_right": "right",
    "a": "accept", "b": "back", "y": "mode", "start": "mode",
    "leftshoulder": "previous", "rightshoulder": "next",
}


def stick_direction(x: float, y: float) -> str | None:
    """The direction a stick (each axis -1 to 1, y down) is pushed, along its stronger axis; None in the dead zone."""
    if max(abs(x), abs(y)) < DEADZONE:
        return None
    if abs(x) >= abs(y):
        return "right" if x > 0 else "left"
    return "down" if y > 0 else "up"


class PygameSource:
    """The controllers' events, as ("button", name, pressed) and ("axis", name, value from -1 to 1)."""

    def __init__(self):
        # SDL needs no window or sound: a dummy video driver gives it the event queue. The events of a pad come
        # also when nothing of ours has the focus; the portal itself only acts while its window is active.
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame
        from pygame._sdl2 import controller
        self.pygame, self.controller = pygame, controller
        pygame.display.init()
        controller.init()
        self.pads: dict[int, object] = {}               # SDL's instance id: the open controller
        for index in range(controller.get_count()):
            self._open(index)
        self.buttons = {getattr(pygame, f"CONTROLLER_BUTTON_{name.upper()}"): name
                        for name in ("a", "b", "x", "y", "start", "back", "leftshoulder", "rightshoulder",
                                     "dpad_up", "dpad_down", "dpad_left", "dpad_right")}
        self.axes = {pygame.CONTROLLER_AXIS_LEFTX: "leftx", pygame.CONTROLLER_AXIS_LEFTY: "lefty"}

    def _open(self, index: int) -> None:
        try:
            if self.controller.is_controller(index):
                pad = self.controller.Controller(index)
                self.pads[pad.id] = pad
        except Exception:  # noqa: BLE001  (a pad that cannot be opened is left alone)
            pass

    def events(self) -> list[tuple[str, str, float | bool]]:
        pygame = self.pygame
        found: list[tuple[str, str, float | bool]] = []
        for event in pygame.event.get():
            if event.type == pygame.CONTROLLERDEVICEADDED:
                self._open(event.device_index)
            elif event.type == pygame.CONTROLLERDEVICEREMOVED:
                self.pads.pop(event.instance_id, None)
                found.append(("released", "", False))
            elif event.type in (pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLERBUTTONUP):
                name = self.buttons.get(event.button)
                if name:
                    found.append(("button", name, event.type == pygame.CONTROLLERBUTTONDOWN))
            elif event.type == pygame.CONTROLLERAXISMOTION:
                name = self.axes.get(event.axis)
                if name:
                    found.append(("axis", name, max(-1.0, min(1.0, event.value / 32767))))
        return found

    def close(self) -> None:
        self.pads.clear()
        try:
            self.controller.quit()
            self.pygame.display.quit()
        except Exception:  # noqa: BLE001  (closing never fails the portal)
            pass


class Gamepad(QObject):
    """Turns what the controllers do into actions (action(name)): up, down, left, right (a held direction repeats),
    accept, back, previous, next, mode."""

    action = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None, source_factory: Callable[[], object] = PygameSource,
                 clock: Callable[[], float] = time.monotonic):
        super().__init__(parent)
        self.source_factory = source_factory
        self.clock = clock
        self.source = None
        self.held: dict[str, tuple[str, float]] = {}    # a d-pad button or the stick: its direction, its next repeat
        self.stick = [0.0, 0.0]
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self.poll)

    def start(self) -> bool:
        """Start listening; False when pygame-ce is missing or SDL cannot start (the portal then has the keyboard)."""
        if self.source is None:
            try:
                self.source = self.source_factory()
            except Exception:  # noqa: BLE001  (no pygame-ce, or no SDL: no controller support, no message)
                return False
        self.timer.start()
        return True

    def stop(self) -> None:
        self.timer.stop()
        self.held.clear()
        self.stick = [0.0, 0.0]
        if self.source is not None:
            self.source.close()
            self.source = None

    def poll(self) -> None:
        if self.source is None:
            return
        for kind, name, value in self.source.events():
            self.handle(kind, name, value)
        now = self.clock()
        for source, (direction, due) in list(self.held.items()):
            if now >= due:
                self.held[source] = (direction, now + REPEAT)
                self.action.emit(direction)

    def handle(self, kind: str, name: str, value: float | bool) -> None:
        if kind == "released":                          # a pad was unplugged with a direction held
            self.held.clear()
            return
        if kind == "axis":
            self.stick[0 if name == "leftx" else 1] = float(value)
            self._push("stick", stick_direction(*self.stick))
            return
        action = BUTTONS.get(name)
        if action is None:
            return
        if action in DIRECTIONS:
            self._push(name, action if value else None)
        elif value:
            self.action.emit(action)

    def _push(self, source: str, direction: str | None) -> None:
        """A direction pressed or released by *source* (a d-pad button or the stick): a new one acts at once."""
        if direction is None:
            self.held.pop(source, None)
        elif source not in self.held or self.held[source][0] != direction:
            self.held[source] = (direction, self.clock() + FIRST_REPEAT)
            self.action.emit(direction)
