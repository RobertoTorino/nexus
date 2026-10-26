# SPDX-License-Identifier: GPL-3.0-or-later
import re
from pathlib import Path

from bc250_portal import desktop_icons

APPS = Path(__file__).resolve().parents[2] / "apps"


def menu_with(tmp_path, *names):
    menu = tmp_path / "applications"
    menu.mkdir()
    for name in names:
        (menu / name).write_text(f"[Desktop Entry]\nName={name}\n")
    return menu


def test_add_and_remove_only_the_apps_icons(tmp_path, desktop):
    menu = menu_with(tmp_path, "bc250-bazzite-suite.desktop", "bc250-hdmi-cec.desktop", "bc250-cu-unlock.desktop",
                     "firefox.desktop")
    (desktop / "bc250-bazzite-suite.desktop").write_text("portal")
    (desktop / "notes.desktop").write_text("mine")
    assert desktop_icons.add(desktop, menu) == ["bc250-cu-unlock.desktop", "bc250-hdmi-cec.desktop"]
    icon = desktop / "bc250-hdmi-cec.desktop"
    assert icon.read_text() == (menu / "bc250-hdmi-cec.desktop").read_text() and icon.stat().st_mode & 0o111
    assert desktop_icons.add(desktop, menu) == []                                   # already there
    assert desktop_icons.remove(desktop, menu) == ["bc250-cu-unlock.desktop", "bc250-hdmi-cec.desktop"]
    assert sorted(p.name for p in desktop.iterdir()) == ["bc250-bazzite-suite.desktop", "notes.desktop"]


def test_an_icon_without_a_menu_entry_is_not_the_suites(tmp_path, desktop):
    menu = menu_with(tmp_path)
    (desktop / "bc250-something-else.desktop").write_text("not installed by the suite")
    assert desktop_icons.remove(desktop, menu) == [] and (desktop / "bc250-something-else.desktop").exists()


def test_no_menu_or_desktop_folder(tmp_path):
    assert desktop_icons.launchers(tmp_path / "none") == []
    assert desktop_icons.add(tmp_path / "no-desktop", menu_with(tmp_path, "bc250-hdmi-cec.desktop")) == []


def test_the_apps_not_named_bc250_are_the_suites_too(tmp_path, desktop):
    menu = menu_with(tmp_path, "media-tool.desktop", "bazzite-netcatgui.desktop", "bazzite-datstation.desktop",
                     "bazzite-other.desktop")
    assert desktop_icons.add(desktop, menu) == ["bazzite-datstation.desktop", "bazzite-netcatgui.desktop",
                                                "media-tool.desktop"]
    assert desktop_icons.remove(desktop, menu) == ["bazzite-datstation.desktop", "bazzite-netcatgui.desktop",
                                                   "media-tool.desktop"]
    assert list(desktop.iterdir()) == []


def test_every_installers_menu_entry_is_known():
    """A new app whose menu entry is not bc250-*.desktop needs adding to OTHERS, or its Desktop icon stays."""
    for installer in sorted(APPS.glob("*/install.sh")):
        app_id = re.search(r'^APP_ID="([^"]+)"', installer.read_text(encoding="utf-8"), re.M)
        if app_id is None:
            continue
        name = f"{app_id[1]}.desktop"
        assert Path(name).match(desktop_icons.PATTERN) or name in desktop_icons.OTHERS, installer
