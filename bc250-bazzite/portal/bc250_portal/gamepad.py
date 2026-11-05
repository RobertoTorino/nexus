# SPDX-License-Identifier: GPL-3.0-or-later
"""A game controller for the portal, read with pygame-ce (SDL's game controller layer, which gives every pad the
same button names): d-pad and left stick move, A accepts, B goes back, X opens the focused tile's menu, the shoulder
buttons change the category. The portal only listens while its own window has the focus, so a game's input never
moves it. Without pygame-ce, or without a controller, nothing happens.

The touchpad of a DualShock 4 or a DualSense moves the mouse pointer (owner, 05-11-2026: as Steam Input does for the
Steam Controller): a finger moves it as on a laptop's touchpad, a press of the pad clicks, and a press with two
fingers on it is a right click. The window moves the pointer (pointer.py); the gamepad says how far
(pointer_moved, in pixels) and when the pad is pressed (pointer_pressed).

A pad that Steam Input owns (the Steam Controller, a Steam Deck's, any pad with Steam Input on) reaches SDL only as
Steam's virtual pad, and only for a program Steam started: the desktop layout turns its buttons into keys
(owner, 05-11-2026: the portal does all of its actions by keys too). Started from Steam, as a non-Steam game, the
portal reads the virtual pad (steam_virtual_pad()); Steam then names the real pads behind it for SDL to skip, so no
press arrives twice."""

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
    "a": "accept", "b": "back", "x": "menu", "y": "update", "start": "settings",
    "rightstick": "keyboard",   # R3: Bazzite's on-screen keyboard (keyboard.py, owner 05-11-2026)
    "leftshoulder": "previous", "rightshoulder": "next",
}
TOUCH_SPEED = 1000              # pixels the pointer moves for a finger across the touchpad's whole width at 100 %
                                # (owner, 05-11-2026, on a DualShock 4: 1400 was a bit too fast); the Settings page
                                # sets a share of it (touch_speed)
TOUCH_ASPECT = 0.49             # the pad's height over its width (DualShock 4 and DualSense alike): y is a share of it
TOUCHPAD_BUTTON = 20            # SDL_CONTROLLER_BUTTON_TOUCHPAD, which pygame-ce has no name for


def launched_by_steam(env: dict | None = None) -> bool:
    """Whether Steam started the portal: it sets SteamGameId (a non-Steam game has one too) and the pads SDL skips."""
    env = os.environ if env is None else env
    return bool(env.get("SteamGameId") or env.get("SDL_GAMECONTROLLER_IGNORE_DEVICES"))


def steam_virtual_pad(env: dict | None = None) -> None:
    """Started by Steam: SDL reads Steam's virtual pad, which it skips by default (a program outside Steam would see
    each press twice, from the pad and from the virtual pad)."""
    env = os.environ if env is None else env
    if launched_by_steam(env):
        env.setdefault("SDL_GAMECONTROLLER_ALLOW_STEAM_VIRTUAL_GAMEPAD", "1")


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
        steam_virtual_pad()
        import pygame
        from pygame._sdl2 import controller
        self.pygame, self.controller = pygame, controller
        pygame.display.init()
        controller.init()
        self.pads: dict[int, object] = {}               # SDL's instance id: the open controller
        for index in range(controller.get_count()):
            self._open(index)
        self.buttons = {getattr(pygame, f"CONTROLLER_BUTTON_{name.upper()}"): name
                        for name in ("a", "b", "x", "y", "start", "back", "leftshoulder", "rightshoulder", "rightstick",
                                     "dpad_up", "dpad_down", "dpad_left", "dpad_right")}
        self.buttons[getattr(pygame, "CONTROLLER_BUTTON_TOUCHPAD", TOUCHPAD_BUTTON)] = "touchpad"
        self.touches = {pygame.CONTROLLERTOUCHPADDOWN: "down", pygame.CONTROLLERTOUCHPADMOTION: "motion",
                        pygame.CONTROLLERTOUCHPADUP: "up"}
        self.axes = {pygame.CONTROLLER_AXIS_LEFTX: "leftx", pygame.CONTROLLER_AXIS_LEFTY: "lefty"}

    def _open(self, index: int) -> None:
        try:
            if self.controller.is_controller(index):
                pad = self.controller.Controller(index)
                self.pads[pad.id] = pad
        except Exception:  # noqa: BLE001  (a pad that cannot be opened is left alone)
            pass

    def events(self) -> list[tuple[str, str, object]]:
        """Also ("touch", down, motion or up, (finger, x, y)), x and y from 0 to 1 across the touchpad."""
        pygame = self.pygame
        found: list[tuple[str, str, object]] = []
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
            elif event.type in self.touches:
                finger = getattr(event, "finger_id", getattr(event, "finger", 0))   # pygame-ce: finger_id
                found.append(("touch", self.touches[event.type], (finger, event.x, event.y)))
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
    accept, back, menu, previous, next; and the touchpad into the pointer's moves (pointer_moved, once per poll) and
    its clicks (pointer_pressed: right, down)."""

    action = pyqtSignal(str)
    pointer_moved = pyqtSignal(float, float)
    pointer_pressed = pyqtSignal(bool, bool)

    def __init__(self, parent: QObject | None = None, source_factory: Callable[[], object] = PygameSource,
                 clock: Callable[[], float] = time.monotonic):
        super().__init__(parent)
        self.source_factory = source_factory
        self.clock = clock
        self.source = None
        self.held: dict[str, tuple[str, float]] = {}    # a d-pad button or the stick: its direction, its next repeat
        self.stick = [0.0, 0.0]
        self.fingers: dict[int, tuple[float, float]] = {}   # on the touchpad: each finger's last place
        self.moved = [0.0, 0.0]                         # the pointer's move since the last poll
        self.right = False                              # the pad's press that is down is a right click
        self.touch_speed = TOUCH_SPEED                  # pixels for a finger across the pad, as the user set it
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
        self.fingers.clear()
        if self.source is not None:
            self.source.close()
            self.source = None

    def poll(self) -> None:
        if self.source is None:
            return
        for kind, name, value in self.source.events():
            self.handle(kind, name, value)
        if any(self.moved):
            dx, dy = self.moved
            self.moved = [0.0, 0.0]
            self.pointer_moved.emit(dx, dy)
        now = self.clock()
        for source, (direction, due) in list(self.held.items()):
            if now >= due:
                self.held[source] = (direction, now + REPEAT)
                self.action.emit(direction)

    def handle(self, kind: str, name: str, value) -> None:
        if kind == "released":                          # a pad was unplugged with a direction held
            self.held.clear()
            self.fingers.clear()
            return
        if kind == "touch":
            self._touch(name, *value)
            return
        if name == "touchpad":                          # the pad pressed: a click, with two fingers a right click
            if value:
                self.right = len(self.fingers) >= 2
            self.pointer_pressed.emit(self.right, bool(value))
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

    def _touch(self, what: str, finger: int, x: float, y: float) -> None:
        """A finger on the touchpad: the first one down moves the pointer by how far it goes; a second one only
        counts for the right click."""
        if what == "up":
            self.fingers.pop(finger, None)
            return
        last = self.fingers.get(finger)
        self.fingers[finger] = (x, y)
        if what == "motion" and last is not None and finger == min(self.fingers):
            self.moved[0] += (x - last[0]) * self.touch_speed
            self.moved[1] += (y - last[1]) * self.touch_speed * TOUCH_ASPECT

    def _push(self, source: str, direction: str | None) -> None:
        """A direction pressed or released by *source* (a d-pad button or the stick): a new one acts at once."""
        if direction is None:
            self.held.pop(source, None)
        elif source not in self.held or self.held[source][0] != direction:
            self.held[source] = (direction, self.clock() + FIRST_REPEAT)
            self.action.emit(direction)
