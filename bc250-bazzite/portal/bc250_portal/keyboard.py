# SPDX-License-Identifier: GPL-3.0-or-later
"""Bazzite's on-screen keyboard, Plasma Keyboard (KDE's own), shown and hidden with R3 (owner, 05-11-2026: "the
virtual Bazzite keyboard", as R3 shows Windows' touch keyboard in the Windows Portable Suite's portal). KWin runs it
as the session's input method and answers on the session bus: org.kde.kwin.VirtualKeyboard at /VirtualKeyboard.
`available` says whether one is chosen (System Settings, Keyboard, Virtual Keyboard), `visible` whether it shows,
forceActivate() asks for it, and `active` false hides it.

KWin shows it only as its `mode` allows (KWin 6.7, VirtualKeyboardVisibility): 0 never, 1 after touch or pen input
(Bazzite's default), 2 for any input. A controller is not touch, so R3 sets mode 2 while the keyboard shows and sets
the user's mode back when R3 hides it or the portal closes (owner, 05-11-2026: the desktop stays as the user has it).
Tried on the owner's board, 05-11-2026: with mode 1 forceActivate() left it hidden, with mode 2 it showed."""

from __future__ import annotations

from collections.abc import Callable

SERVICE, PATH, INTERFACE = "org.kde.KWin", "/VirtualKeyboard", "org.kde.kwin.VirtualKeyboard"
PROPERTIES = "org.freedesktop.DBus.Properties"
ANY_INPUT = 2                   # KWin's VirtualKeyboardVisibility::AnyInput
NOT_CHOSEN = ("No on-screen keyboard is chosen for the desktop: choose Plasma Keyboard in System Settings, Keyboard, "
              "Virtual Keyboard, then press R3 again.")
NO_KWIN = "The on-screen keyboard is KDE's, on a Wayland desktop: this desktop does not offer it."

# (interface, method, arguments) -> the reply's arguments; raises KeyboardError on an error reply
Call = Callable[[str, str, list], list]


class KeyboardError(RuntimeError):
    pass


def dbus_call(interface: str, method: str, arguments: list) -> list:
    """One call to KWin's virtual keyboard on the session bus (QtDBus: no process started)."""
    from PyQt6.QtDBus import QDBusConnection, QDBusMessage
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        raise KeyboardError(NO_KWIN)
    message = QDBusMessage.createMethodCall(SERVICE, PATH, interface, method)
    message.setArguments(arguments)
    reply = bus.call(message)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        raise KeyboardError(f"{NO_KWIN} ({reply.errorMessage()})")
    return reply.arguments()


def variant(value):
    """A value for a D-Bus property's Set, wrapped as a variant."""
    from PyQt6.QtDBus import QDBusVariant
    return QDBusVariant(value)


class OnScreenKeyboard:
    """R3's keyboard: toggle() shows or hides it, restore() sets the user's mode back (also when the keyboard was
    closed some other way since)."""

    def __init__(self, call: Call | None = None):
        self.call = call or (lambda *args: dbus_call(*args))   # looked up when called: tests keep it off the bus
        self.user_mode: int | None = None       # the mode before R3 changed it; None: not changed

    def _get(self, name: str):
        values = self.call(PROPERTIES, "Get", [INTERFACE, name])
        return values[0] if values else None

    def _set(self, name: str, value) -> None:
        self.call(PROPERTIES, "Set", [INTERFACE, name, variant(value)])

    def toggle(self) -> bool:
        """The keyboard shown, or hidden when it shows. True when it is shown now. KeyboardError, with what to do,
        when the desktop has none."""
        if not self._get("available"):
            raise KeyboardError(NOT_CHOSEN)
        if self._get("visible"):
            self._set("active", False)
            self.restore()
            return False
        mode = int(self._get("mode") or 0)
        if mode != ANY_INPUT:
            if self.user_mode is None:
                self.user_mode = mode
            self._set("mode", ANY_INPUT)
        self.call(INTERFACE, "forceActivate", [])
        return True

    def restore(self) -> None:
        """The user's mode back, when R3 changed it."""
        if self.user_mode is not None:
            mode, self.user_mode = self.user_mode, None
            self._set("mode", mode)
