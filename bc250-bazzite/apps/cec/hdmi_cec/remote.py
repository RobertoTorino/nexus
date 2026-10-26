# SPDX-License-Identifier: GPL-3.0-or-later
"""The TV remote's keys as cecd announces them on the session bus (signal UserControlPressed of
com.steampowered.CecDaemon1.CecDevice1): what each key press arrives as, for the key tester. Only while cecd runs."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import QDBusConnection, QDBusMessage

SERVICE = "com.steampowered.CecDaemon1"
INTERFACE = "com.steampowered.CecDaemon1.CecDevice1"


def first_byte(value) -> int | None:
    """The UI command from the signal's byte array (a QByteArray or bytes; extra bytes are its parameters)."""
    data = bytes(value) if value is not None else b""
    return data[0] if data else None


class RemoteListener(QObject):
    pressed = pyqtSignal(int, int)          # UI command, initiator's logical address

    def start(self) -> bool:
        """Listens on the session bus; False when there is none."""
        bus = QDBusConnection.sessionBus()
        return bus.isConnected() and bus.connect(SERVICE, "", INTERFACE, "UserControlPressed", self.on_message)

    @pyqtSlot(QDBusMessage)
    def on_message(self, message: QDBusMessage) -> None:
        args = message.arguments()
        command = first_byte(args[0]) if args else None
        if command is not None:
            self.pressed.emit(command, int(args[1]) if len(args) > 1 else -1)
