# SPDX-License-Identifier: GPL-3.0-or-later
"""The beep when a transfer completes."""

from __future__ import annotations

import shutil
import subprocess

from PyQt6.QtWidgets import QApplication

COMPLETE_SOUND = "/usr/share/sounds/freedesktop/stereo/complete.oga"


def play_beep(run=subprocess.Popen, which=shutil.which) -> None:
    """The desktop's "complete" sound through paplay when there is one, else Qt's beep."""
    paplay = which("paplay")
    if paplay is not None:
        try:
            run([paplay, COMPLETE_SOUND], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            return
        except OSError:
            pass
    QApplication.beep()
