# SPDX-License-Identifier: GPL-3.0-or-later
"""The stop shortcut on Windows: Ctrl+Alt+F12 as a hot key of Windows' own, in a thread with a message loop."""

from __future__ import annotations

import sys
import time

import pytest

from demo_recorder import global_shortcut

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows' RegisterHotKey")


def _pump(qapp, until, seconds: float = 3) -> None:
    end = time.monotonic() + seconds
    while not until() and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)


def test_the_windows_manager_is_the_one_on_windows():
    assert global_shortcut.GlobalShortcutManager is global_shortcut.WindowsShortcutManager


def test_the_hot_key_is_registered_reports_presses_and_is_freed(qapp):
    import ctypes
    events: list = []
    manager = global_shortcut.WindowsShortcutManager()
    manager.registered.connect(lambda trigger: events.append(("registered", trigger)))
    manager.activated.connect(lambda: events.append("activated"))
    manager.register()
    _pump(qapp, lambda: events)
    assert events == [("registered", "Ctrl+Alt+F12")]

    # Windows posts WM_HOTKEY to the thread that registered the key, as a press of Ctrl+Alt+F12 does
    ctypes.WinDLL("user32").PostThreadMessageW(manager._thread_id, global_shortcut._WM_HOTKEY,
                                               global_shortcut._HOTKEY_ID, 0)
    _pump(qapp, lambda: "activated" in events)
    assert events[-1] == "activated"

    second = global_shortcut.WindowsShortcutManager()          # the key is taken while the first one holds it
    failures: list[str] = []
    second.failed.connect(failures.append)
    second.register()
    _pump(qapp, lambda: failures)
    assert failures and "Ctrl+Alt+F12" in failures[0]
    second.stop()

    manager.stop()
    again = global_shortcut.WindowsShortcutManager()           # freed when stopped
    again.registered.connect(lambda trigger: events.append(("again", trigger)))
    again.register()
    _pump(qapp, lambda: events[-1] == ("again", "Ctrl+Alt+F12"))
    assert events[-1] == ("again", "Ctrl+Alt+F12")
    again.stop()
