# SPDX-License-Identifier: GPL-3.0-or-later
"""The XDG autostart entry."""

from __future__ import annotations

from usb_ips35 import APP_ID, autostart


def test_on_and_off(tmp_path):
    config, home = tmp_path / "config", tmp_path / "home"
    assert not autostart.enabled(config)
    autostart.set_enabled(True, config, home)
    entry = config / "autostart" / f"{APP_ID}.desktop"
    assert autostart.enabled(config)
    assert f"Exec={home}/.local/bin/{APP_ID} --minimized" in entry.read_text().splitlines()
    autostart.set_enabled(False, config, home)
    assert not entry.exists()
    autostart.set_enabled(False, config, home)
