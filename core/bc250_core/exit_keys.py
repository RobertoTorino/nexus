# SPDX-License-Identifier: GPL-3.0-or-later
"""Escape and a controller's B close the app's window (owner, 12-11-2026: inside the apps, as they close the BC250
portal), for an app that asks for it: install(app) once the QApplication is there.

Escape: a key press nothing in the window took for itself (a text being edited, a list that goes back a level, a
page of the app's own) closes the window, as its close button does, so the window's own closeEvent still asks what
it asks. A dialog and a menu keep Qt's own Escape. A window that must not close on it (a stream, where the keys are
the game's) says so with a class attribute, exit_keys = False.

B: read with pygame-ce (SDL's game controller layer, where B is the right button of the four on every pad), and
only acted on while the app has the focus and has had it for a moment: every app reads the same press, so the one
that closes on it would otherwise take the app behind it along. B is Escape for whatever has the focus: it closes
an open menu, then a dialog, then the window. Without pygame-ce, or without a controller, there is no B and nothing
is said. An app in which the controller is the app's subject (a stream, a controller's test) installs it without:
install(app, controller=False).

SDL needs no window: it is started with the dummy video driver, set in the environment only while it starts, so a
program the app starts later (Steam, an emulator) does not inherit it.

Self-contained (PyQt6 and the standard library; pygame-ce only when it is there), so an app not on core yet carries
a copy; tools/tests/test_instance_copies.py keeps the copies equal."""

from __future__ import annotations

import os
import time
from collections.abc import Callable

from PyQt6.QtCore import QEvent, QObject, QTimer, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

POLL_MS = 30
GRACE_S = 0.5                   # B counts once the app has had the focus this long (the press that closed another)
# What SDL reads when it starts, gone from the environment again after (the names core's platform.py lists)
SDL_VARIABLES = {"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy", "SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS": "1",
                 "PYGAME_HIDE_SUPPORT_PROMPT": "1"}
# Windows that are not an app's window: Qt closes a menu on Escape itself, and the others never have the keyboard
NOT_WINDOWS = (Qt.WindowType.Popup, Qt.WindowType.ToolTip, Qt.WindowType.SplashScreen)


class BackButton:
    """The controllers' B: pressed() is how often it went down since the last call."""

    def __init__(self):
        saved = {name: os.environ.get(name) for name in SDL_VARIABLES}
        try:
            for name, value in SDL_VARIABLES.items():
                os.environ.setdefault(name, value)
            import pygame
            from pygame._sdl2 import controller
            self.pygame, self.controller = pygame, controller
            pygame.display.init()
            controller.init()
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
        self.pads: dict[int, object] = {}               # SDL's instance id: the open controller
        for index in range(controller.get_count()):
            self._open(index)

    def _open(self, index: int) -> None:
        try:
            if self.controller.is_controller(index):
                pad = self.controller.Controller(index)
                self.pads[pad.id] = pad
        except Exception:  # noqa: BLE001  (a pad that cannot be opened is left alone)
            pass

    def pressed(self) -> int:
        pygame, count = self.pygame, 0
        for event in pygame.event.get():
            if event.type == pygame.CONTROLLERDEVICEADDED:
                self._open(event.device_index)
            elif event.type == pygame.CONTROLLERDEVICEREMOVED:
                self.pads.pop(event.instance_id, None)
            elif event.type == pygame.CONTROLLERBUTTONDOWN and event.button == pygame.CONTROLLER_BUTTON_B:
                count += 1
        return count

    def close(self) -> None:
        self.pads.clear()
        try:
            self.controller.quit()
            self.pygame.display.quit()
        except Exception:  # noqa: BLE001  (closing never fails the app)
            pass


class ExitKeys(QObject):
    """Escape, and B when *controller*, close the window of *app* that has the focus. *source_factory* makes the
    reader of B (pressed(), close()); *clock* is the time in seconds (tests pass their own)."""

    def __init__(self, app: QApplication, controller: bool = True,
                 source_factory: Callable[[], object] = BackButton, clock: Callable[[], float] = time.monotonic):
        super().__init__(app)
        self.app = app
        self.clock = clock
        self.source_factory = source_factory
        self.source = None
        self.active_since = clock()
        self._own = False                               # the window is being given the key: not ours again
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self.poll)
        app.installEventFilter(self)
        if controller:
            app.applicationStateChanged.connect(self._state_changed)
            app.aboutToQuit.connect(self.stop)
            QTimer.singleShot(0, self.start)            # once the window shows: pygame-ce takes a moment to load

    # ---------------------------------------------------------------------------------------------- Escape
    @staticmethod
    def closes(window: QWidget) -> bool:
        """Whether Escape closes *window*: an app's window, not a dialog or a menu (Qt's own Escape), and not one
        that keeps its keys (exit_keys = False)."""
        return (window.isWindow() and not isinstance(window, QDialog) and window.windowType() not in NOT_WINDOWS
                and getattr(window, "exit_keys", True))

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 (Qt override)
        # A key nobody took goes up the parents to the window: there it is ours, after the window's own
        # keyPressEvent had it (an app's page that goes back on Escape accepts it).
        if (self._own or event.type() != QEvent.Type.KeyPress or event.key() != Qt.Key.Key_Escape
                or event.modifiers() != Qt.KeyboardModifier.NoModifier or event.isAutoRepeat()
                or not isinstance(watched, QWidget) or not self.closes(watched)):
            return False
        self._own = True
        try:
            event.accept()
            watched.event(event)
        finally:
            self._own = False
        if not event.isAccepted():
            event.accept()
            watched.close()
        return True

    # --------------------------------------------------------------------------------------------------- B
    def start(self) -> bool:
        """Start reading B; False without pygame-ce or SDL (the app then has Escape alone)."""
        if self.source is None:
            try:
                self.source = self.source_factory()
            except Exception:  # noqa: BLE001  (no pygame-ce, or no SDL: no controller support, no message)
                return False
        self.timer.start()
        return True

    def stop(self) -> None:
        self.timer.stop()
        if self.source is not None:
            self.source.close()
            self.source = None

    def _state_changed(self, state) -> None:
        if state == Qt.ApplicationState.ApplicationActive:
            self.active_since = self.clock()

    def poll(self) -> None:
        if self.source is None:
            return
        try:
            presses = self.source.pressed()             # read also without the focus: they must not wait in SDL
        except Exception:  # noqa: BLE001  (SDL went away under the reader: Escape alone from here on)
            self.stop()
            return
        if presses and self.app.activeWindow() is not None and self.clock() - self.active_since >= GRACE_S:
            self.back()

    def back(self) -> None:
        """B: Escape for what has the focus, the open menu first, then the dialog or the window."""
        target = self.app.activePopupWidget() or self.app.focusWidget() or self.app.activeWindow()
        if target is None:
            return
        for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(target, QKeyEvent(kind, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))


def install(app: QApplication, controller: bool = True) -> ExitKeys:
    """Escape and, with *controller*, B close the app's window from now on. The QApplication keeps it."""
    return ExitKeys(app, controller)
