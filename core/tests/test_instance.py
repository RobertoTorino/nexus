# SPDX-License-Identifier: GPL-3.0-or-later
"""Single instance: forwarding to a listener, nobody-there detection, a second launch raising the window, and a
second launch handing over its arguments."""

from __future__ import annotations

import os
import sys
import time

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QObject
from PyQt6.QtWidgets import QWidget

from bc250_core import instance

# On Windows the socket is a named pipe, which the server and the client in one thread do not get through (two
# processes, two launches of an app, do).
ONE_THREAD = pytest.mark.skipif(sys.platform == "win32", reason="a named pipe on Windows: server and client in one thread")


def dispose(*objects: QObject) -> None:
    """Delete Qt objects now, not when Python collects them at exit (that order can crash the interpreter)."""
    for obj in objects:
        obj.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    QCoreApplication.processEvents()


def pump_until(predicate, seconds: float = 10) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end and not predicate():
        QCoreApplication.processEvents()
        time.sleep(0.01)
    return predicate()


def test_server_name_is_per_app_and_user():
    assert instance.server_name("bc250-x") != instance.server_name("bc250-y")
    assert instance.server_name("bc250-x").startswith("bc250-x-")


def test_nobody_running(qapp):
    assert not instance.already_running(f"bc250-test-nobody-{os.getpid()}")


@ONE_THREAD
def test_forward_reaches_listener(qapp):
    name = f"bc250-test-{os.getpid()}"
    server = instance.InstanceServer(None, name)
    assert server.listen()
    got = []
    server.received.connect(got.append)
    assert instance.forward("show", name) and instance.forward("show token-1", name)
    assert pump_until(lambda: len(got) == 2)
    assert got == ["show", "show token-1"]
    server.close()
    dispose(server)


@ONE_THREAD
def test_second_launch_raises_the_window(qapp, monkeypatch):
    app_id = f"bc250-test-app-{os.getpid()}"
    window = QWidget()
    raised = []
    monkeypatch.setattr(instance, "raise_window", raised.append)
    server = instance.serve(app_id, window)
    monkeypatch.setenv("XDG_ACTIVATION_TOKEN", "abc")
    assert instance.already_running(app_id)                    # what a second launch does
    assert pump_until(lambda: raised == [window])
    assert os.environ["XDG_ACTIVATION_TOKEN"] == "abc"         # handed on for Wayland's activation
    server.close()
    window.close()
    dispose(window)                                            # the server is the window's child


def test_launch_without_arguments_sends_the_plain_show_request(qapp, monkeypatch):
    sent = []
    monkeypatch.setattr(instance, "forward", lambda message, name: sent.append(message) or True)
    monkeypatch.delenv("XDG_ACTIVATION_TOKEN", raising=False)
    assert instance.already_running("bc250-test-plain") and instance.already_running("bc250-test-plain", [])
    assert sent == ["show", "show"]                            # what every launch sent before arguments existed


@ONE_THREAD
def test_second_launch_hands_over_its_arguments(qapp, monkeypatch):
    app_id = f"bc250-test-args-{os.getpid()}"
    window = QWidget()
    raised, given = [], []
    monkeypatch.setattr(instance, "raise_window", raised.append)
    server = instance.serve(app_id, window, on_args=given.append)
    monkeypatch.delenv("XDG_ACTIVATION_TOKEN", raising=False)
    assert instance.already_running(app_id, ["/home/me/Downloads/My Game (EU).pkg", "-l", "4444", "ü\nx"])
    assert pump_until(lambda: given)
    assert raised == [window]                                  # shown first, then given the arguments
    assert given == [["/home/me/Downloads/My Game (EU).pkg", "-l", "4444", "ü\nx"]]
    server.close()
    window.close()
    dispose(window)


@ONE_THREAD
def test_arguments_without_a_handler_or_malformed_only_show(qapp, monkeypatch):
    app_id = f"bc250-test-noargs-{os.getpid()}"
    window = QWidget()
    raised = []
    monkeypatch.setattr(instance, "raise_window", raised.append)
    server = instance.serve(app_id, window)                    # an app that takes no arguments
    assert instance.already_running(app_id, ["file.iso"])
    assert pump_until(lambda: raised == [window])
    server.close()
    window.close()
    dispose(window)

    window = QWidget()
    given = []
    server = instance.serve(app_id, window, on_args=given.append)
    name = instance.server_name(app_id)
    assert instance.forward("args not json", name) and instance.forward('args {"a": 1}', name)
    assert instance.forward('args ["ok"]', name)
    assert pump_until(lambda: given)
    assert given == [["ok"]]                                   # the two bad lines were dropped
    server.close()
    window.close()
    dispose(window)


def test_first_launch_takes_the_lock(qapp):
    app_id = f"bc250-test-lock-{os.getpid()}"
    name = instance.server_name(app_id)
    assert not instance.already_running(app_id)                # the first: it runs and holds the lock
    assert name in instance._locks and instance._locks[name].isLocked()
    instance._locks.pop(name).unlock()


@ONE_THREAD
def test_launch_during_startup_waits_instead_of_opening_a_second_window(qapp, monkeypatch):
    from PyQt6.QtCore import QLockFile
    app_id = f"bc250-test-starting-{os.getpid()}"
    name = instance.server_name(app_id)
    starting = QLockFile(instance.lock_path(name))             # another launch, still building its window
    starting.setStaleLockTime(0)
    assert starting.tryLock(0)
    monkeypatch.setattr(instance, "STARTUP_WAIT_S", 0.3)
    began = time.monotonic()
    assert instance.already_running(app_id)                    # no socket yet: waits, still no second window
    assert time.monotonic() - began >= 0.3
    server = instance.InstanceServer(None, name)               # its socket is up now
    assert server.listen()
    monkeypatch.setattr(instance, "STARTUP_WAIT_S", 5)
    began = time.monotonic()
    assert instance.already_running(app_id) and time.monotonic() - began < 2
    server.close()
    dispose(server)
    starting.unlock()
