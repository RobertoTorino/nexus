# SPDX-License-Identifier: GPL-3.0-or-later
"""The header's shortcuts: what each one starts, from what the machine has."""

import subprocess
from pathlib import Path

import pytest

from bc250_portal import shortcuts


def has(*programs):
    return lambda name: f"/usr/bin/{name}" if name in programs else None


def flatpak(code=0, error=None):
    def run(argv, **kwargs):
        assert argv == ["flatpak", "info", "com.brave.Browser"] and kwargs["timeout"] == 5
        if error is not None:
            raise error
        return subprocess.CompletedProcess(argv, code, "", "")
    return run


def test_steam_and_the_file_manager():
    assert shortcuts.steam(has("steam")).argv == ["steam"]
    with pytest.raises(shortcuts.Missing, match="Steam is not installed"):
        shortcuts.steam(has())
    assert shortcuts.files(has("xdg-open"), Path("/home/someone")).argv == ["xdg-open", "/home/someone"]
    with pytest.raises(shortcuts.Missing, match="xdg-open"):
        shortcuts.files(has())


def test_youtube_needs_brave_browsers_flatpak():
    start = shortcuts.youtube(flatpak())
    assert start.argv == ["flatpak", "run", "com.brave.Browser", "--kiosk", "https://www.youtube.com/"]
    assert "com.brave.Browser" in start.app_ids
    with pytest.raises(shortcuts.Missing, match="Brave Browser is required"):
        shortcuts.youtube(flatpak(1))
    with pytest.raises(shortcuts.Missing, match="Flatpak is not available"):
        shortcuts.youtube(flatpak(error=FileNotFoundError()))
    with pytest.raises(shortcuts.Missing, match="could not be asked"):
        shortcuts.youtube(flatpak(error=subprocess.TimeoutExpired("flatpak", 5)))


@pytest.mark.parametrize("page, kcm, panel", [("bluetooth", "kcm_bluetooth", "bluetooth"),
                                              ("network", "kcm_networkmanagement", "network")])
def test_the_settings_of_the_desktop_that_is_there(page, kcm, panel):
    """KDE Plasma's System Settings, else the module alone, else GNOME's Settings (not only the owner's desktop)."""
    assert shortcuts.settings(page, has("systemsettings", "kcmshell6")).argv == ["systemsettings", kcm]
    assert shortcuts.settings(page, has("kcmshell6")).argv == ["kcmshell6", kcm]
    assert shortcuts.settings(page, has("gnome-control-center")).argv == ["gnome-control-center", panel]
    with pytest.raises(shortcuts.Missing, match="settings of this desktop"):
        shortcuts.settings(page, has())
