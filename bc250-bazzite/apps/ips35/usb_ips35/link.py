# SPDX-License-Identifier: GPL-3.0-or-later
"""The connection to the screen, in a thread of its own: a whole screen takes almost two seconds to send, and the
window must not wait for it. The window hands it the newest frame and the settings; the thread finds the screen,
opens it, sends what changed and reports its state. A screen that is unplugged is looked for again, and gets the
whole frame when it is back.

The first time it finds the screen, and after every lost connection, it resets the screen (screen.Screen.reset), so a
picture cut off halfway before cannot shift what follows; then it connects to the screen that comes back."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QObject, pyqtSignal

from . import frames, screen

RETRY_S = 2.0
RESET_WAIT_S = 3.0                              # the screen is back on USB about 2 s after a reset


@dataclass(frozen=True)
class State:
    kind: str                                   # "searching", "no-access", "resetting", "connected", "error"
    found: screen.Found | None = None
    model: screen.Model | None = None
    message: str = ""


class Link(QObject):
    state_changed = pyqtSignal(object)          # State
    sent = pyqtSignal(int)                      # bytes of the last update

    def __init__(self, find: Callable[[], list[screen.Found]] = screen.find,
                 open_port: Callable[[object], object] = screen.Port, parent: QObject | None = None):
        super().__init__(parent)
        self._find, self._open = find, open_port
        self._wake = threading.Condition()
        self._frame: tuple[bytes, int, int] | None = None   # newest frame, not sent yet: pixels, width, height
        self._brightness = 50
        self._on = True
        self._settings_dirty = True
        self._stop = False
        self._off_at_stop = True
        self._reset_done = False
        self._thread: threading.Thread | None = None
        self.model: screen.Model | None = None

    # ---------------------------------------------------------- from the window
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="usb-ips35", daemon=True)
        self._thread.start()

    def show(self, frame: bytes, width: int, height: int) -> None:
        with self._wake:
            self._frame = (frame, width, height)
            self._wake.notify()

    def set_brightness(self, percent: int) -> None:
        with self._wake:
            self._brightness, self._settings_dirty = percent, True
            self._wake.notify()

    def set_power(self, on: bool) -> None:
        with self._wake:
            self._on, self._settings_dirty = on, True
            self._wake.notify()

    def stop(self, screen_off: bool = True, timeout: float = 3.0) -> None:
        """Ends the thread; with *screen_off* the screen goes dark first, so it does not show values that no longer
        change."""
        with self._wake:
            self._stop, self._off_at_stop = True, screen_off
            self._wake.notify()
        if self._thread is not None:
            self._thread.join(timeout)

    # ------------------------------------------------------------- the thread
    def _report(self, state: State) -> None:
        self.state_changed.emit(state)

    def _connect(self) -> tuple[object, screen.Screen] | None:
        found = self._find()
        if not found:
            self._report(State("searching"))
            return None
        usable = [f for f in found if f.usable]
        if not usable:
            self._report(State("no-access", found[0]))
            return None
        try:
            port = self._open(usable[0].port)
        except OSError as exc:
            self._report(State("error", usable[0], message=str(exc)))
            return None
        lcd = screen.Screen(port)
        if not self._reset_done:
            self._report(State("resetting", usable[0]))
            try:
                lcd.reset()
            except OSError:
                pass                            # the screen left USB: it restarts
            port.close()
            self._reset_done = True
            self._sleep(RESET_WAIT_S)
            return None
        try:
            self.model = lcd.hello()
            lcd.start()
        except OSError as exc:
            port.close()
            self._report(State("error", usable[0], message=str(exc)))
            return None
        self._report(State("connected", usable[0], self.model))
        return port, lcd

    def _run(self) -> None:
        while not self._stop:
            link = self._connect()
            if link is None:
                self._sleep(RETRY_S)
                continue
            port, lcd = link
            try:
                self._serve(lcd)
            except OSError as exc:
                self._report(State("error", message=f"The screen stopped answering: {exc}"))
                self._reset_done = False
            finally:
                port.close()
            self.model = None

    def _sleep(self, seconds: float) -> None:
        with self._wake:
            self._wake.wait_for(lambda: self._stop, seconds)

    def _serve(self, lcd: screen.Screen) -> None:
        last: bytes | None = None
        self._settings_dirty = True
        while True:
            with self._wake:
                self._wake.wait_for(lambda: self._stop or self._settings_dirty or self._frame is not None)
                if self._stop:
                    if self._off_at_stop:
                        lcd.power(False)
                    return
                frame, self._frame = self._frame, None
                dirty, self._settings_dirty = self._settings_dirty, False
                brightness, on = self._brightness, self._on
            if dirty:
                lcd.brightness(brightness)
                lcd.power(on)
            if frame is None:
                continue
            pixels, width, height = frame
            if (width, height) != (lcd.model.width, lcd.model.height):
                continue                        # drawn before the model was known; the next one fits
            size = 0
            for rect in frames.changed(last, pixels, width, height):
                lcd.draw(pixels, rect)
                size += rect[2] * rect[3] * 2
            last = pixels
            self.sent.emit(size)
