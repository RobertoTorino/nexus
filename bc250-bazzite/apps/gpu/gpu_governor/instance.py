# SPDX-License-Identifier: GPL-3.0-or-later
"""One running instance per user, reachable over a local socket.

A second launch does not start a second poller and tray icon: it hands its request to the running instance
(`forward`) and exits. Requests are one line each: `show` raises the window, `profile <name>` applies a saved
profile. This is what makes `bc250-governor-manager --profile <name>` usable as a desktop hotkey command.

Two launches at the same moment both find no running instance yet, since the window and its socket take a while
to appear; so `already_running` also takes a lock file at once, and a launch that finds it taken waits for that
instance's socket instead of starting a second poller. The lock goes with its process.
"""

from __future__ import annotations

import os
import time

from PyQt6.QtCore import QDir, QLockFile, QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from . import APP_ID

SERVER_NAME = f"{APP_ID}-{os.getuid()}"
CONNECT_MS = 500
STARTUP_WAIT_S = 10                     # how long a launch waits for an instance that is still starting
SHOW = "show"
PROFILE = "profile "
_locks: dict[str, QLockFile] = {}       # held for the life of the process


def forward(message: str, name: str = SERVER_NAME) -> bool:
    """Deliver `message` to a running instance; False when none is listening."""
    socket = QLocalSocket()
    socket.connectToServer(name)

    if not socket.waitForConnected(CONNECT_MS):
        return False

    payload = (message + "\n").encode("utf-8")

    if socket.write(payload) == -1:
        socket.abort()
        return False

    if not socket.waitForBytesWritten(CONNECT_MS):
        socket.abort()
        return False

    # Give the peer a chance to receive the complete request before
    # closing the connection.
    socket.disconnectFromServer()
    if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        socket.waitForDisconnected(CONNECT_MS)

    return True


def already_running(message: str, name: str = SERVER_NAME) -> bool:
    """True when an instance runs (or is starting) and `message` was handed to it; False: this launch runs."""
    if forward(message, name):
        return True
    lock = QLockFile(os.path.join(QDir.tempPath(), f"{name}.lock"))
    lock.setStaleLockTime(0)            # never stale by age: only when its process is gone
    if lock.tryLock(0):
        _locks[name] = lock
        return False
    end = time.monotonic() + STARTUP_WAIT_S
    while time.monotonic() < end:
        if forward(message, name):
            return True
        time.sleep(0.1)
    return True                         # it holds the lock but does not answer: still no second instance


class InstanceServer(QObject):
    received = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None, name: str = SERVER_NAME):
        super().__init__(parent)
        self.name = name
        self._server = QLocalServer(self)
        self._sockets: set[QLocalSocket] = set()
        self._server.newConnection.connect(self._accept)

    def listen(self) -> bool:
        QLocalServer.removeServer(self.name)
        return self._server.listen(self.name)

    def close(self) -> None:
        self._server.close()

        for socket in list(self._sockets):
            socket.disconnectFromServer()
            socket.deleteLater()

        self._sockets.clear()

    def _accept(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            self._sockets.add(socket)

            socket.readyRead.connect(
                lambda s=socket: self._read(s)
            )
            socket.disconnected.connect(
                lambda s=socket: self._remove_socket(s)
            )

            if socket.bytesAvailable():
                self._read(socket)

    def _remove_socket(self, socket: QLocalSocket) -> None:
        self._sockets.discard(socket)
        socket.deleteLater()

    def _read(self, socket: QLocalSocket) -> None:
        while socket.canReadLine():
            line = bytes(socket.readLine()).decode(
                "utf-8", errors="replace"
            ).strip()

            if line:
                self.received.emit(line)
