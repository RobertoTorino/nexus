# SPDX-License-Identifier: GPL-3.0-or-later
"""The global shortcut that stops the recording: on Linux the desktop portal's, owned by a process of its own
(shortcut_service.py), on Windows a hot key of Windows' own (RegisterHotKey), in a thread of its own."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import QProcess, pyqtSignal
from PyQt6.QtWidgets import QWidget


class PortalShortcutManager(QWidget):
    registered = pyqtSignal(str)
    activated = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.errorOccurred.connect(self._process_error)
        self.process.finished.connect(self._process_finished)
        self.process.setWorkingDirectory(str(Path(__file__).resolve().parents[1]))
        self._is_registered = False
        self._request_pending = False
        self._failed = False
        self._stopping = False

    def register(self) -> None:
        if self._is_registered:
            self.registered.emit(self.trigger_description)
            return
        if self._request_pending:
            return
        self._request_pending = True
        self._failed = False
        self._stopping = False
        self.trigger_description = ""
        self.process.start(sys.executable, ["-m", "demo_recorder.shortcut_service"])

    def stop(self) -> None:
        self._request_pending = False
        self._is_registered = False
        self._stopping = True
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1000):
                self.process.kill()
                self.process.waitForFinished(1000)

    def _read_output(self) -> None:
        while self.process.canReadLine():
            raw_line = bytes(self.process.readLine().data()).decode("utf-8").strip()
            if not raw_line:
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                self._fail(f"The shortcut service returned invalid data: {exc}")
                continue
            if event.get("event") == "registered":
                trigger_description = event.get("trigger")
                if not isinstance(trigger_description, str) or not trigger_description:
                    self._fail("The desktop registered the shortcut without describing its trigger.")
                    continue
                self._request_pending = False
                self._is_registered = True
                self.trigger_description = trigger_description
                self.registered.emit(trigger_description)
            elif event.get("event") == "activated":
                self.activated.emit()
            elif event.get("event") == "error":
                self._fail(str(event.get("message", "Unknown global-shortcut error")))

    def _process_error(self) -> None:
        if self._request_pending or self._is_registered:
            self._fail("Could not start or keep running the global-shortcut service.")

    def _process_finished(self) -> None:
        if not self._stopping and (self._request_pending or self._is_registered):
            self._fail("The global-shortcut service stopped unexpectedly.")

    def _fail(self, message: str) -> None:
        if self._failed:
            return
        self._failed = True
        self._request_pending = False
        self._is_registered = False
        self.failed.emit(message)


TRIGGER = "Ctrl+Alt+F12"            # as the desktop portal is asked for it (shortcut_service.py)
_MOD_ALT, _MOD_CONTROL, _MOD_NOREPEAT, _VK_F12 = 0x0001, 0x0002, 0x4000, 0x7B
_WM_HOTKEY, _WM_QUIT, _HOTKEY_ID = 0x0312, 0x0012, 1


class WindowsShortcutManager(QWidget):
    """Ctrl+Alt+F12 as a hot key of Windows: registered in a thread with a message loop of its own, which gets
    WM_HOTKEY however the windows are (this one hides while it records). The same signals as the portal's."""
    registered = pyqtSignal(str)
    activated = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.trigger_description = ""
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._started = threading.Event()       # set once the hot key is registered or has failed

    def register(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            if self.trigger_description:
                self.registered.emit(self.trigger_description)
            return
        self._started.clear()
        self._thread = threading.Thread(target=self._run, name="demo-recorder-hotkey", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32")
        msg = wintypes.MSG()
        self._thread_id = kernel32.GetCurrentThreadId()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)       # makes the thread's message queue
        if not user32.RegisterHotKey(None, _HOTKEY_ID, _MOD_CONTROL | _MOD_ALT | _MOD_NOREPEAT, _VK_F12):
            error = ctypes.get_last_error()
            self._started.set()
            self.failed.emit(f"Windows refused the hot key {TRIGGER}: {ctypes.FormatError(error).strip()} "
                             "Another program may use it.")
            return
        self.trigger_description = TRIGGER
        self._started.set()
        self.registered.emit(TRIGGER)
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                    self.activated.emit()
        finally:
            user32.UnregisterHotKey(None, _HOTKEY_ID)
            self.trigger_description = ""

    def stop(self) -> None:
        thread = self._thread
        if thread is None or not thread.is_alive():
            return
        import ctypes
        self._started.wait(1)
        ctypes.WinDLL("user32").PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
        thread.join(1)
        self._thread = None


GlobalShortcutManager = WindowsShortcutManager if sys.platform == "win32" else PortalShortcutManager
