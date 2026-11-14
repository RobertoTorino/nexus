# SPDX-License-Identifier: GPL-3.0-or-later
"""A new launch takes the place of the open dashboard: the app runs from the checkout, so the one started last is
the one with the code as it is now.

    replace.close_running(APP_ID)               # before instance.already_running()
    ...
    replace.serve(server, window)               # after instance.serve()

The new launch asks the open dashboard to close (QUIT on its instance socket, core's instance.py) and waits until
its lock is free. A dashboard that does not answer the request (one started before it knew QUIT, or one that hangs)
is ended by its process ID, which the lock file holds. A launch that is still starting has no socket yet and is
left alone: core's already_running() then shows its window, as before."""

from __future__ import annotations

import os
import signal

from bc250_core import instance
from PyQt6.QtCore import QLockFile
from PyQt6.QtNetwork import QLocalSocket
from PyQt6.QtWidgets import QWidget

QUIT = "quit"
CLOSE_MS = 5000                         # how long the open dashboard gets to close by itself
END_MS = 3000                           # and how long its process gets after it was ended


def _free(lock: QLockFile, wait_ms: int) -> bool:
    """Whether the instance lock is free within *wait_ms*: its holder is gone. The lock is not kept."""
    if not lock.tryLock(wait_ms):
        return False
    lock.unlock()
    return True


def _ask(name: str, wait_ms: int) -> bool:
    """Send QUIT to the instance listening on *name*; False when none is. Waits until that instance hangs up (it
    closed), *wait_ms* at most."""
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(instance.CONNECT_MS):
        return False
    if socket.write((QUIT + "\n").encode("utf-8")) != -1 and socket.waitForBytesWritten(instance.CONNECT_MS):
        socket.waitForDisconnected(wait_ms)
    socket.abort()
    return True


def close_running(app_id: str, close_ms: int = CLOSE_MS, end_ms: int = END_MS) -> bool:
    """Close the dashboard that is open for this user; False when it is still there."""
    name = instance.server_name(app_id)
    if not _ask(name, close_ms):
        return True                     # none open (or one still starting: already_running() hands over to it)
    lock = QLockFile(instance.lock_path(name))
    lock.setStaleLockTime(0)
    if _free(lock, instance.CONNECT_MS):
        return True
    known, pid, _host, _app = lock.getLockInfo()
    if known and pid > 0 and pid != os.getpid():
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    return _free(lock, end_ms)


def serve(server: instance.InstanceServer, window: QWidget) -> None:
    """Close *window* (the app ends with it) when a later launch asks for it."""
    server.received.connect(lambda message: window.close() if message == QUIT else None)
