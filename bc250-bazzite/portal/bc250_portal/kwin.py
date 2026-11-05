# SPDX-License-Identifier: GPL-3.0-or-later
"""An app's window brought to the front when its tile is pressed while it runs (owner, 05-11-2026: an app moved
behind the portal had no way back). Pressing the tile starts the app again, and that second start asks the running
one to show its window (bc250_core.instance); but on Wayland a window may only take the focus with an activation
token, which a program the portal starts has none of, so KWin leaves it behind the portal. KWin itself may do it: the
portal hands it a short script over the session bus (org.kde.KWin, /Scripting) that unminimizes the app's window
and makes it the active one. The window is found by its app id (each app sets it to its launcher's name,
QGuiApplication.setDesktopFileName) or by the process the portal started.

Without KWin (another desktop, Game Mode's gamescope) nothing happens here, and the app's own show request stays
what it was."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path

SERVICE, SCRIPTING, INTERFACE = "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting"
PLUGIN = "bc250-bazzite-suite-raise"
# KWin 6 names the windows windowList() and activeWindow; KWin 5 clientList() and activeClient.
SCRIPT = """const ids = %s, pids = %s;
const windows = workspace.windowList ? workspace.windowList() : workspace.clientList();
for (const w of windows) {
    if (w.normalWindow && (ids.includes(w.desktopFileName) || ids.includes(w.resourceClass) || pids.includes(w.pid))) {
        w.minimized = false;
        if (workspace.windowList) workspace.activeWindow = w; else workspace.activeClient = w;
        break;
    }
}
"""

# (path, interface, method, arguments) -> the reply's arguments; raises KWinError on an error reply
Call = Callable[[str, str, str, list], list]


class KWinError(RuntimeError):
    pass


def dbus_call(path: str, interface: str, method: str, arguments: list) -> list:
    """One call to KWin on the session bus (QtDBus: no process started)."""
    from PyQt6.QtDBus import QDBusConnection, QDBusMessage
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        raise KWinError("no session bus")
    message = QDBusMessage.createMethodCall(SERVICE, path, interface, method)
    message.setArguments(arguments)
    reply = bus.call(message)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        raise KWinError(reply.errorMessage())
    return reply.arguments()


def script_file() -> Path:
    """Where the script is written for KWin to read: the user's own, in the temp folder."""
    user = os.getuid() if hasattr(os, "getuid") else 0
    return Path(tempfile.gettempdir()) / f"{PLUGIN}-{user}.js"


class Raiser:
    """bring_to_front(app_ids, pids): the first normal window of those apps active, unminimized. False when KWin
    could not be asked (no KWin); True does not mean a window was found: an app not running yet has none."""

    def __init__(self, call: Call | None = None, file: Path | None = None):
        self.call = call or (lambda *args: dbus_call(*args))   # looked up when called: tests keep it off the bus
        self.file = file

    def bring_to_front(self, app_ids: Iterable[str], pids: Iterable[int] = ()) -> bool:
        file = self.file or script_file()
        try:
            file.write_text(SCRIPT % (json.dumps(sorted(set(app_ids))), json.dumps(sorted(set(pids)))),
                            encoding="utf-8")
            # KWin reads the file and runs the script after the call returns: the script loaded last time goes
            # now, before this one is loaded under the same name.
            self.call(SCRIPTING, INTERFACE, "unloadScript", [PLUGIN])
            (number,) = self.call(SCRIPTING, INTERFACE, "loadScript", [str(file), PLUGIN]) or (-1,)
            if int(number) < 0:
                return False
            self.call(f"{SCRIPTING}/Script{int(number)}", "org.kde.kwin.Script", "run", [])
        except (KWinError, OSError, ValueError, TypeError):
            return False
        return True

    def close(self) -> None:
        """The last script unloaded, when the portal closes."""
        try:
            self.call(SCRIPTING, INTERFACE, "unloadScript", [PLUGIN])
        except KWinError:
            pass
