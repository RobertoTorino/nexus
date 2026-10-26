# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller for the stream, read with pygame-ce (SDL's game controller layer, which names every pad's
buttons the same way, as the portal reads them): the first controller connected is the Xbox's pad. SDL's names
are the Xbox pad's own: back is View, start is Menu, guide the Xbox button. The rumble the stream sends goes to
its motors (the strong, low-frequency one left, the weak one right); a pad without motors ignores it."""

from __future__ import annotations

import os
from collections.abc import Callable

from .inputs import PadState, Vibration

SDL_BUTTONS = {                             # pygame's CONTROLLER_BUTTON_* (lower case) to the report's names
    "a": "a", "b": "b", "x": "x", "y": "y", "back": "view", "start": "menu", "guide": "nexus",
    "leftstick": "left_thumb", "rightstick": "right_thumb", "leftshoulder": "left_shoulder",
    "rightshoulder": "right_shoulder", "dpad_up": "dpad_up", "dpad_down": "dpad_down", "dpad_left": "dpad_left",
    "dpad_right": "dpad_right",
}
AXIS_MAX = 32767


def _stick(value: int) -> float:
    return max(-1.0, min(1.0, value / AXIS_MAX))


def _trigger(value: int) -> float:
    return max(0.0, min(1.0, value / AXIS_MAX))


class PygameSource:
    """The controllers through pygame-ce: the first one's state, and rumble for it."""

    def __init__(self):
        # SDL needs no window or sound of its own: the dummy video driver gives it the event queue (as the portal)
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame
        from pygame._sdl2 import controller
        self.pygame, self.controller = pygame, controller
        pygame.display.init()
        controller.init()
        self.pads: dict[int, object] = {}               # SDL's instance id: the open controller, oldest first
        for index in range(controller.get_count()):
            self._open(index)
        self.buttons = {getattr(pygame, f"CONTROLLER_BUTTON_{name.upper()}"): ours
                        for name, ours in SDL_BUTTONS.items()}

    def _open(self, index: int) -> None:
        try:
            if self.controller.is_controller(index):
                pad = self.controller.Controller(index)
                self.pads[pad.id] = pad
        except Exception:  # noqa: BLE001  (a pad that cannot be opened is left alone)
            pass

    def _first(self):
        return next(iter(self.pads.values()), None)

    def name(self) -> str:
        pad = self._first()
        return str(getattr(pad, "name", "") or "Controller") if pad is not None else ""

    def read(self) -> PadState | None:
        """The first controller's state, None without one."""
        pygame = self.pygame
        for event in pygame.event.get():
            if event.type == pygame.CONTROLLERDEVICEADDED:
                self._open(event.device_index)
            elif event.type == pygame.CONTROLLERDEVICEREMOVED:
                self.pads.pop(event.instance_id, None)
        pad = self._first()
        if pad is None:
            return None
        axis = pad.get_axis
        return PadState(
            0, frozenset(ours for button, ours in self.buttons.items() if pad.get_button(button)),
            _stick(axis(pygame.CONTROLLER_AXIS_LEFTX)), _stick(axis(pygame.CONTROLLER_AXIS_LEFTY)),
            _stick(axis(pygame.CONTROLLER_AXIS_RIGHTX)), _stick(axis(pygame.CONTROLLER_AXIS_RIGHTY)),
            _trigger(axis(pygame.CONTROLLER_AXIS_TRIGGERLEFT)), _trigger(axis(pygame.CONTROLLER_AXIS_TRIGGERRIGHT)))

    def rumble(self, vibration: Vibration) -> None:
        pad = self._first()
        if pad is None:
            return
        try:
            if vibration.left or vibration.right:
                pad.rumble(vibration.left, vibration.right, max(1, vibration.duration_ms))
            else:
                pad.stop_rumble()
        except Exception:  # noqa: BLE001  (a pad without motors)
            pass

    def close(self) -> None:
        self.pads.clear()
        try:
            self.controller.quit()
            self.pygame.display.quit()
        except Exception:  # noqa: BLE001  (closing never fails the app)
            pass


def open_source(factory: Callable[[], object] = PygameSource) -> object | None:
    """The controller source; None when pygame-ce or SDL cannot start (the stream then has the keyboard only)."""
    try:
        return factory()
    except Exception:  # noqa: BLE001  (no pygame-ce, or no SDL)
        return None
