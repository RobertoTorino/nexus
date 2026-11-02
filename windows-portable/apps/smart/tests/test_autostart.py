# SPDX-License-Identifier: GPL-3.0-or-later
"""Start with Windows: a shortcut in the Startup folder that starts the program minimized, and only the installed
program."""

from __future__ import annotations

import pytest

from smart_screen import APP_NAME, autostart


def test_the_shortcut_starts_the_program_minimized(tmp_path):
    made = []

    def make(link, target, arguments, **kwargs):
        made.append((link, target, arguments))
        link.parent.mkdir(parents=True, exist_ok=True)      # as core's make_shortcut
        link.write_text("lnk")

    program = tmp_path / "app" / "Smart-Screen.exe"
    autostart.set_enabled(True, tmp_path / "Startup", program, make)
    assert made == [(tmp_path / "Startup" / f"{APP_NAME}.lnk", program, autostart.MINIMIZED_FLAG)]
    assert autostart.enabled(tmp_path / "Startup")
    autostart.set_enabled(False, tmp_path / "Startup")
    assert not autostart.enabled(tmp_path / "Startup")


def test_only_the_installed_program_starts_with_windows(tmp_path):
    assert autostart.program() is None                              # the tests run from the checkout
    with pytest.raises(RuntimeError, match="install it"):
        autostart.set_enabled(True, tmp_path, make=lambda *a, **k: None)
    assert not autostart.enabled(tmp_path)


def test_the_startup_folder_is_the_users():
    assert autostart.startup_folder().parts[-5:] == ("Microsoft", "Windows", "Start Menu", "Programs", "Startup")
