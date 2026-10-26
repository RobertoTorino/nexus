# SPDX-License-Identifier: GPL-3.0-or-later
"""Single-instance socket: forwarding to a listener, and nobody-there detection."""

from __future__ import annotations

import os

from PyQt6.QtCore import QCoreApplication

from gpu_governor import instance


def _pump(ms: int = 50) -> None:
    import time
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        QCoreApplication.processEvents()


def test_forward_without_listener(qapp):
    assert not instance.forward("show", name=f"bc250-test-nobody-{os.getpid()}")

def test_forward_reaches_listener(qapp):
    name = f"bc250-test-{os.getpid()}"
    server = instance.InstanceServer(name=name)
    assert server.listen()
    got = []
    server.received.connect(got.append)
    assert instance.forward(instance.SHOW, name=name)
    assert instance.forward(instance.PROFILE + "Quiet night", name=name)

    # Wait up to 10 seconds for both messages
    import time
    start = time.monotonic()
    while time.monotonic() - start < 10:
        _pump(ms=100)
        if len(got) == 2:
            break

    assert got == ["show", "profile Quiet night"]
    server.close()
    assert not instance.forward("show", name=name)


def test_listen_recovers_stale_socket(qapp):
    name = f"bc250-test-stale-{os.getpid()}"
    first = instance.InstanceServer(name=name)
    assert first.listen()
    # Simulate a crash: the server object goes away without close(), the socket file stays behind.
    first._server.newConnection.disconnect()
    second = instance.InstanceServer(name=name)
    assert second.listen()
    second.close()
    first.close()


def test_launch_during_startup_hands_over_once_the_socket_is_up(qapp, monkeypatch):
    from PyQt6.QtCore import QDir, QLockFile
    name = f"bc250-test-gov-starting-{os.getpid()}"
    assert not instance.already_running(instance.SHOW, name=name)    # the first launch: it runs
    instance._locks.pop(name).unlock()
    starting = QLockFile(os.path.join(QDir.tempPath(), f"{name}.lock"))  # another launch, still starting
    starting.setStaleLockTime(0)
    assert starting.tryLock(0)
    monkeypatch.setattr(instance, "STARTUP_WAIT_S", 0.3)
    assert instance.already_running(instance.SHOW, name=name)        # waits; still no second instance
    server = instance.InstanceServer(name=name)
    assert server.listen()
    got = []
    server.received.connect(got.append)
    assert instance.already_running(instance.PROFILE + "Quiet", name=name)
    _pump(200)
    assert got == [instance.PROFILE + "Quiet"]
    server.close()
    starting.unlock()
