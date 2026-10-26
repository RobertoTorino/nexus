# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller through pygame-ce, with a stand-in for pygame: SDL's buttons to the Xbox pad's, the sticks and
triggers, a pad connected later or taken out, and rumble."""

from __future__ import annotations

import sys
import types

import pytest

from console_linkb import pads
from console_linkb.inputs import Vibration

NAMES = list(pads.SDL_BUTTONS)
AXES = ["LEFTX", "LEFTY", "RIGHTX", "RIGHTY", "TRIGGERLEFT", "TRIGGERRIGHT"]


class Controller:
    def __init__(self, index):
        self.id = 100 + index
        self.name = f"Pad {index}"
        self.pressed: set[int] = set()
        self.axes: dict[int, int] = {}
        self.rumbles: list = []

    def get_button(self, button):
        return button in self.pressed

    def get_axis(self, axis):
        return self.axes.get(axis, 0)

    def rumble(self, low, high, duration):
        self.rumbles.append((low, high, duration))
        return True

    def stop_rumble(self):
        self.rumbles.append("stop")


@pytest.fixture
def fake_pygame(monkeypatch):
    pygame = types.ModuleType("pygame")
    for number, name in enumerate(NAMES):
        setattr(pygame, f"CONTROLLER_BUTTON_{name.upper()}", number)
    for number, name in enumerate(AXES):
        setattr(pygame, f"CONTROLLER_AXIS_{name}", number)
    pygame.CONTROLLERDEVICEADDED, pygame.CONTROLLERDEVICEREMOVED = 1, 2
    pygame.queue = []
    pygame.event = types.SimpleNamespace(get=lambda: [pygame.queue.pop(0) for _ in list(pygame.queue)])
    pygame.display = types.SimpleNamespace(init=lambda: None, quit=lambda: None)
    sdl2 = types.ModuleType("pygame._sdl2")
    controller = types.ModuleType("pygame._sdl2.controller")
    controller.connected = [0]
    controller.made = {}

    def make(index):
        controller.made[index] = Controller(index)
        return controller.made[index]
    controller.init = controller.quit = lambda: None
    controller.get_count = lambda: len(controller.connected)
    controller.is_controller = lambda index: True
    controller.Controller = make
    sdl2.controller = controller
    monkeypatch.setitem(sys.modules, "pygame", pygame)
    monkeypatch.setitem(sys.modules, "pygame._sdl2", sdl2)
    monkeypatch.setitem(sys.modules, "pygame._sdl2.controller", controller)
    return pygame, controller


def test_the_first_pad_as_the_xbox_pad(fake_pygame):
    pygame, controller = fake_pygame
    source = pads.PygameSource()
    pad = controller.made[0]
    pad.pressed = {pygame.CONTROLLER_BUTTON_A, pygame.CONTROLLER_BUTTON_BACK, pygame.CONTROLLER_BUTTON_START,
                   pygame.CONTROLLER_BUTTON_GUIDE, pygame.CONTROLLER_BUTTON_LEFTSTICK}
    pad.axes = {pygame.CONTROLLER_AXIS_LEFTX: 32767, pygame.CONTROLLER_AXIS_LEFTY: -32768,
                pygame.CONTROLLER_AXIS_TRIGGERRIGHT: 16384}
    state = source.read()
    assert state.buttons == {"a", "view", "menu", "nexus", "left_thumb"}
    assert (state.left_x, state.left_y, state.right_x) == (1.0, -1.0, 0.0)
    assert state.right_trigger == pytest.approx(0.5, abs=0.001) and state.left_trigger == 0.0
    assert source.name() == "Pad 0"


def test_pads_connected_later_and_taken_out(fake_pygame):
    pygame, controller = fake_pygame
    controller.connected = []
    source = pads.PygameSource()
    assert source.read() is None and source.name() == ""
    pygame.queue.append(types.SimpleNamespace(type=pygame.CONTROLLERDEVICEADDED, device_index=3))
    assert source.read() is not None
    pygame.queue.append(types.SimpleNamespace(type=pygame.CONTROLLERDEVICEREMOVED, instance_id=103))
    assert source.read() is None


def test_rumble_goes_to_the_pad(fake_pygame):
    _pygame, controller = fake_pygame
    source = pads.PygameSource()
    source.rumble(Vibration(0, 0.8, 0.3, 0, 0, 250, 0, 0))
    source.rumble(Vibration(0, 0, 0, 0, 0, 0, 0, 0))
    assert controller.made[0].rumbles == [(0.8, 0.3, 250), "stop"]
    source.close()
    source.rumble(Vibration(0, 1, 1, 0, 0, 10, 0, 0))   # no pad: nothing
