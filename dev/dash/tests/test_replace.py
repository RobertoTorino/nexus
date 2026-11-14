# SPDX-License-Identifier: GPL-3.0-or-later
"""A new launch takes the open dashboard's place: nobody open, an open one that closes when asked, and one that
does not answer and is ended by the process ID in its lock."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest
from bc250_core import instance
from PyQt6.QtCore import QCoreApplication, QLockFile
from PyQt6.QtWidgets import QWidget

from nexus_dashboard import replace

# On Windows the socket is a named pipe, which the server and the client in one thread do not get through (two
# processes, two launches of the app, do).
ONE_THREAD = pytest.mark.skipif(sys.platform == "win32", reason="a named pipe on Windows: server and client in one thread")


def pump_until(predicate, seconds: float = 10) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end and not predicate():
        QCoreApplication.processEvents()
        time.sleep(0.01)
    return predicate()


def test_nobody_open(qapp):
    assert replace.close_running(f"nexus-test-nobody-{os.getpid()}")


@ONE_THREAD
def test_the_open_window_closes_when_asked_and_only_then(qapp):
    app_id = f"nexus-test-quit-{os.getpid()}"
    window = QWidget()
    window.show()
    server = instance.serve(app_id, window)
    replace.serve(server, window)
    assert instance.forward(instance.SHOW, instance.server_name(app_id))
    QCoreApplication.processEvents()
    assert window.isVisible()                               # a show request closes nothing
    assert instance.forward(replace.QUIT, instance.server_name(app_id))
    assert pump_until(lambda: not window.isVisible())
    server.close()
    window.deleteLater()


# A dashboard that listens and holds the lock, but never reads what a launch asks.
DEAF = """
import sys, time
from PyQt6.QtCore import QCoreApplication, QLockFile
from PyQt6.QtNetwork import QLocalServer
app = QCoreApplication(sys.argv)
lock = QLockFile(sys.argv[2]); lock.setStaleLockTime(0); assert lock.tryLock(0)
QLocalServer.removeServer(sys.argv[1])
server = QLocalServer(); assert server.listen(sys.argv[1])
print("up", flush=True)
app.exec()
"""


@pytest.mark.skipif(sys.platform == "win32", reason="ends a process by its signal")
def test_a_dashboard_that_does_not_answer_is_ended(qapp):
    app_id = f"nexus-test-deaf-{os.getpid()}"
    name = instance.server_name(app_id)
    deaf = subprocess.Popen([sys.executable, "-c", DEAF, name, instance.lock_path(name)], stdout=subprocess.PIPE)
    try:
        assert deaf.stdout.readline().strip() == b"up"
        assert replace.close_running(app_id, close_ms=300, end_ms=5000)
        assert deaf.wait(5) is not None
        lock = QLockFile(instance.lock_path(name))
        assert lock.tryLock(0)                              # free again: the new launch runs
        lock.unlock()
    finally:
        deaf.kill()
        deaf.stdout.close()
