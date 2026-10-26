# SPDX-License-Identifier: MIT
"""One running instance per app and user, reachable over a local socket (after the governor's instance.py).

A second launch does not open a second window: it asks the running instance to show its window and exits.

    if instance.already_running(APP_ID):
        return 0
    window = MainWindow()
    window.show()
    server = instance.serve(APP_ID, window)     # keep the reference while the app runs

Two launches at the same moment (a double-click on a Desktop icon that opens on one click) both find no running
instance yet: the window and its socket take a while to appear. So the first launch also takes a lock file at once;
a launch that finds it taken waits for that instance's socket instead of opening a second window. The lock goes
with its process (Qt sees a dead holder's lock as stale).

On Wayland a window may only take the focus with an activation token; a launch from the menu or the Desktop gets
one (XDG_ACTIVATION_TOKEN), and the second launch hands it to the running instance, which Qt then uses.

An app that opens what it is given on the command line (a file from the menu entry's %f) passes its arguments on:
already_running(APP_ID, args) sends them after the show request, and serve(APP_ID, window, on_args) hands them to
on_args in the running instance. Without arguments the request is the plain show request it always was, and an
instance that has no on_args only shows its window.
The apps that are not on bc250_core yet carry a copy of this file; tools/tests checks that the copies match."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Sequence

from PyQt6.QtCore import QDir, QLockFile, QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QWidget

CONNECT_MS = 500
STARTUP_WAIT_S = 10                     # how long a launch waits for an instance that is still starting
SHOW = "show"
ARGS = "args"                           # a launch's own arguments, as a JSON list, after SHOW
_locks: dict[str, QLockFile] = {}       # held for the life of the process


def server_name(app_id: str) -> str:
    user = os.getuid() if hasattr(os, "getuid") else os.environ.get("USERNAME", "user")
    return f"{app_id}-{user}"


def forward(message: str, name: str) -> bool:
    """Deliver *message* to a running instance; False when none is listening."""
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(CONNECT_MS):
        return False
    if socket.write((message + "\n").encode("utf-8")) == -1 or not socket.waitForBytesWritten(CONNECT_MS):
        socket.abort()
        return False
    # Give the peer a chance to receive the complete request before closing the connection.
    socket.disconnectFromServer()
    if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        socket.waitForDisconnected(CONNECT_MS)
    return True


class InstanceServer(QObject):
    received = pyqtSignal(str)

    def __init__(self, parent: QObject | None, name: str):
        super().__init__(parent)
        self.name = name
        self._server = QLocalServer(self)
        self._sockets: set[QLocalSocket] = set()
        self._server.newConnection.connect(self._accept)

    def listen(self) -> bool:
        QLocalServer.removeServer(self.name)        # a socket file left behind by a crashed instance
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
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(lambda s=socket: self._remove_socket(s))
            if socket.bytesAvailable():
                self._read(socket)

    def _remove_socket(self, socket: QLocalSocket) -> None:
        self._sockets.discard(socket)
        socket.deleteLater()

    def _read(self, socket: QLocalSocket) -> None:
        while socket.canReadLine():
            line = bytes(socket.readLine()).decode("utf-8", errors="replace").strip()
            if line:
                self.received.emit(line)


def raise_window(window: QWidget) -> None:
    if window.isMinimized():
        window.showNormal()
    window.show()
    window.raise_()
    window.activateWindow()


def lock_path(name: str) -> str:
    return os.path.join(QDir.tempPath(), f"{name}.lock")


def already_running(app_id: str, args: Sequence[str] = ()) -> bool:
    """True when this app already runs (or is starting) for this user; it has been asked to show its window and,
    with *args*, been given them."""
    name = server_name(app_id)
    message = f"{SHOW} {os.environ.get('XDG_ACTIVATION_TOKEN', '')}".strip()
    if args:
        message += f"\n{ARGS} {json.dumps(list(args))}"
    if forward(message, name):
        return True
    lock = QLockFile(lock_path(name))
    lock.setStaleLockTime(0)            # never stale by age: only when its process is gone
    if lock.tryLock(0):
        _locks[name] = lock
        return False                    # the first launch: this one runs
    # Another launch holds the lock and is still building its window: hand over once its socket is up.
    end = time.monotonic() + STARTUP_WAIT_S
    while time.monotonic() < end:
        if forward(message, name):
            return True
        time.sleep(0.1)
    return True                         # it holds the lock but does not answer: still no second window


def serve(app_id: str, window: QWidget,
          on_args: Callable[[list[str]], None] | None = None) -> InstanceServer:
    """Listen for later launches of *app_id*; each one brings *window* to the front, and the arguments of a launch
    that has them go to *on_args*."""
    server = InstanceServer(window, server_name(app_id))

    def on_message(message: str) -> None:
        command, _, rest = message.partition(" ")
        if command == SHOW:
            if rest:
                os.environ["XDG_ACTIVATION_TOKEN"] = rest       # Qt's Wayland plugin activates with it
            raise_window(window)
        elif command == ARGS and on_args is not None:
            try:
                args = json.loads(rest)
            except ValueError:
                return
            if isinstance(args, list) and all(isinstance(arg, str) for arg in args):
                on_args(args)

    server.received.connect(on_message)
    server.listen()
    return server
