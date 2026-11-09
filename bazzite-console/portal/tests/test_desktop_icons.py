# SPDX-License-Identifier: GPL-3.0-or-later
import re
from pathlib import Path

from bazzite_console_portal import desktop_icons

APPS = Path(__file__).resolve().parents[2] / "apps"


def test_add_and_remove_only_console_suite_icons(tmp_path, desktop, monkeypatch):
    menu = tmp_path / "applications"
    menu.mkdir()
    names = ("bazzite-test.desktop", "ps5-rpcs3-manager.desktop", "bazzite-console-suite.desktop",
             "bazzite-unrelated.desktop", "ps5-unrelated.desktop")
    for name in names:
        (menu / name).write_text(f"[Desktop Entry]\nName={name}\n")
    for name in names[2:]:
        (desktop / name).write_text("keep")
    (desktop / "ps5-orphan.desktop").write_text("keep")
    monkeypatch.setattr(desktop_icons.shutil, "which", lambda _: None)

    assert desktop_icons.add(desktop, menu) == ["bazzite-test.desktop", "ps5-rpcs3-manager.desktop"]
    assert (desktop / "ps5-rpcs3-manager.desktop").stat().st_mode & 0o111
    assert desktop_icons.add(desktop, menu) == []
    assert desktop_icons.remove(desktop, menu) == ["bazzite-test.desktop", "ps5-rpcs3-manager.desktop"]
    assert sorted(p.name for p in desktop.iterdir()) == sorted((*names[2:], "ps5-orphan.desktop"))


def test_every_installer_menu_entry_is_known():
    names = set()
    for installer in sorted(APPS.glob("*/install.sh")):
        app_id = re.search(r'^APP_ID="([^"]+)"', installer.read_text(encoding="utf-8"), re.M)
        assert app_id, installer
        names.add(f"{app_id[1]}.desktop")
    assert names == desktop_icons.APP_LAUNCHERS
