# SPDX-License-Identifier: GPL-3.0-or-later
"""Desktop notifications through notify-send (the desktop's notification service)."""

from __future__ import annotations

import shutil

from PyQt6.QtCore import QProcess

from . import DISPLAY_NAME, ICON_PATH


def notify(summary: str, body: str) -> bool:
    """Show a desktop notification; False when the desktop offers no notify-send."""
    exe = shutil.which("notify-send")
    if not exe:
        return False
    args = ["--app-name", DISPLAY_NAME, "--icon", str(ICON_PATH), summary, body]
    ok, _pid = QProcess.startDetached(exe, args)
    return ok
