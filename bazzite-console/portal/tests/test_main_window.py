# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal window, its app tiles, settings page and status header."""

from __future__ import annotations

import pytest

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QMessageBox

from bazzite_console_portal import APP_NAME, CARDS, MANIFEST
from bazzite_console_portal import desktop_icons
from bazzite_console_portal.bigpicture import ICON_PX
from bazzite_console_portal.main_window import DESKTOP_ICONS_KEY, MainWindow, Pending
from bazzite_console_portal.manifest import load, load_cards
from bazzite_console_portal.sources import Records, Sources


@pytest.fixture
def window(qapp, home, settings_dir, tmp_path):
    result = MainWindow(load(MANIFEST), Sources(tmp_path / "work"),
                        Records(tmp_path / "installed.json"), installed=tmp_path / "installed-portal")
    yield result
    result.close()


def test_portal_shows_required_app(window):
    assert window.windowTitle().startswith(APP_NAME)
    assert list(window.states) == [entry.key for entry in window.entries]
    assert [entry.key for entry in window.entries if entry.required] == ["bazzite"]
    assert window.states["bazzite"].title == "Bazzite Test"
    assert [action.text() for action in window.tile_menu(window.entries[0]).actions()][0] == "Open"
    assert window.big.categories == ["sustainable", "gaming", "utilities", "media"]
    assert "youtube" not in window.states
    assert window.big.tiles["youtube"].name == "YouTube"
    assert window.big.tiles["youtube"].status == "Brave Browser required"
    assert window.big.tiles["twitch"].name == "Twitch"
    assert window.big.tiles["twitch"].status == "Brave Browser required"
    assert window.big.tiles["stremio"].name == "Stremio"
    assert window.big.tiles["stremio"].status == "Stremio required"
    assert window.big.tiles["netflix"].status == "Brave Browser required"
    assert window.big.tiles["spotify"].status == "Spotify required"


@pytest.mark.parametrize("scale", [1.0, 0.68])
def test_media_card_icons_are_half_size_and_centered(window, scale):
    cards = load_cards(CARDS)
    assert all(window.big.tiles[card.key].icon_scale == 0.5 for card in cards if card.category == "media")
    for key, factor in (("youtube", 0.5), ("bazzite", 1.0)):
        tile = window.big.tiles[key]
        assert tile.icon_scale == factor
        tile.setParent(None)
        tile.set_scale(scale)
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("#00ff00"))
        tile.set_look("", pixmap, "", "", "")
        image = QPixmap(tile.size())
        image.fill(Qt.GlobalColor.transparent)
        tile.render(image)
        image = image.toImage()
        pixels = [(x, y) for y in range(image.height()) for x in range(image.width())
                  if image.pixelColor(x, y) == QColor("#00ff00")]
        side = round(ICON_PX * scale)
        picture_side = round(side * factor)
        left = (tile.width() - side) // 2 + (side - picture_side) // 2
        top = round(18 * scale) + (side - picture_side) // 2
        assert len(pixels) == picture_side * picture_side
        assert min(x for x, _ in pixels) == left
        assert max(x for x, _ in pixels) == left + picture_side - 1
        assert min(y for _, y in pixels) == top
        assert max(y for _, y in pixels) == top + picture_side - 1


def test_youtube_card_launches_fullscreen_in_brave(window, monkeypatch):
    calls = []
    checks = []

    def installed(*args, **kwargs):
        checks.append(args[0])
        return type("Result", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("bazzite_console_portal.main_window.subprocess.run", installed)
    window.launch = lambda argv: calls.append(argv) or True

    window._open_tile(load_cards(CARDS)[0])

    assert calls == [["flatpak", "run", "com.brave.Browser", "--kiosk", "https://www.youtube.com/"]]
    assert checks == [["flatpak", "info", "com.brave.Browser"]]


def test_twitch_card_launches_fullscreen_in_brave(window, monkeypatch):
    calls = []
    monkeypatch.setattr("bazzite_console_portal.main_window.subprocess.run",
                        lambda *args, **kwargs: type("Result", (), {"returncode": 0, "stderr": ""})())
    window.launch = lambda argv: calls.append(argv) or True

    window._open_tile(load_cards(CARDS)[1])

    assert calls == [["flatpak", "run", "com.brave.Browser", "--kiosk", "https://www.twitch.tv/"]]


def test_stremio_card_launches_its_flatpak(window, monkeypatch):
    calls = []
    checks = []

    def installed(*args, **kwargs):
        checks.append(args[0])
        return type("Result", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("bazzite_console_portal.main_window.subprocess.run", installed)
    window.launch = lambda argv: calls.append(argv) or True

    window._open_tile(load_cards(CARDS)[2])

    assert calls == [["flatpak", "run", "com.stremio.Stremio"]]
    assert checks == [["flatpak", "info", "com.stremio.Stremio"]]


def test_spotify_card_launches_its_flatpak(window, monkeypatch):
    calls = []
    checks = []

    def installed(*args, **kwargs):
        checks.append(args[0])
        return type("Result", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("bazzite_console_portal.main_window.subprocess.run", installed)
    window.launch = lambda argv: calls.append(argv) or True

    window.open_card(load_cards(CARDS)[-1])

    assert calls == [["flatpak", "run", "com.spotify.Client"]]
    assert checks == [["flatpak", "info", "com.spotify.Client"]]


def test_youtube_card_has_no_app_menu_or_update_action(window):
    window.big.tiles["youtube"].setFocus()

    window.act("menu")
    window.act("update")


def test_youtube_card_requires_brave_flatpak(window, monkeypatch):
    calls = []
    monkeypatch.setattr("bazzite_console_portal.main_window.subprocess.run",
                        lambda *args, **kwargs: type("Result", (), {"returncode": 1, "stderr": ""})())
    monkeypatch.setattr("bazzite_console_portal.main_window.QMessageBox.information",
                        lambda *args: calls.append(args[2]))
    window.launch = lambda argv: pytest.fail("launched without Brave")

    window.open_card(load_cards(CARDS)[0])

    assert "Brave Browser is required" in calls[0]


def test_twitch_card_requires_brave_flatpak(window, monkeypatch):
    calls = []
    monkeypatch.setattr("bazzite_console_portal.main_window.subprocess.run",
                        lambda *args, **kwargs: type("Result", (), {"returncode": 1, "stderr": ""})())
    monkeypatch.setattr("bazzite_console_portal.main_window.QMessageBox.information",
                        lambda *args: calls.append(args[2]))
    window.launch = lambda argv: pytest.fail("launched without Brave")

    window.open_card(load_cards(CARDS)[1])

    assert "Brave Browser is required" in calls[0]


def test_stremio_card_requires_its_flatpak(window, monkeypatch):
    calls = []
    monkeypatch.setattr("bazzite_console_portal.main_window.subprocess.run",
                        lambda *args, **kwargs: type("Result", (), {"returncode": 1, "stderr": ""})())
    monkeypatch.setattr("bazzite_console_portal.main_window.QMessageBox.information",
                        lambda *args: calls.append(args[2]))
    window.launch = lambda argv: pytest.fail("launched without Stremio")

    window.open_card(load_cards(CARDS)[2])

    assert "Stremio is required" in calls[0]


def test_spotify_card_requires_its_flatpak(window, monkeypatch):
    calls = []
    monkeypatch.setattr("bazzite_console_portal.main_window.subprocess.run",
                        lambda *args, **kwargs: type("Result", (), {"returncode": 1, "stderr": ""})())
    monkeypatch.setattr("bazzite_console_portal.main_window.QMessageBox.information",
                        lambda *args: calls.append(args[2]))
    window.launch = lambda argv: pytest.fail("launched without Spotify")

    window.open_card(load_cards(CARDS)[-1])

    assert "Spotify is required" in calls[0]


def test_settings_page_and_clock_menu(window):
    assert not window.big.in_settings()
    window.toggle_settings()
    assert window.big.in_settings()
    assert not window.icons_box.isChecked()

    actions = [action.text() for action in window.clock_menu().actions()]
    assert "12-hour clock (AM/PM)" in actions
    assert "24-hour clock" in actions
    assert "Seconds" in actions
    assert "UTC" in actions

    window.toggle_settings()
    assert not window.big.in_settings()


def test_clock_header_shows_date_and_time(window):
    text = window.big.status.text()
    assert "|" in text
    assert any(day in text for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"))


def test_console_release_tags_are_pruned_by_app_key(tmp_path):
    source = Sources(tmp_path / "releases")
    old = source.work / "ps5-bazzite-v0.0.9"
    current = source.work / "ps5-bazzite-v0.1.0"
    other = source.work / "ps5-other-v0.1.0"
    for folder in (old, current, other):
        folder.mkdir(parents=True)

    source.prune(load(MANIFEST)[0])

    assert not old.exists()
    assert current.is_dir()
    assert other.is_dir()


def test_desktop_icon_toggle_only_manages_console_apps(tmp_path):
    menu = tmp_path / "applications"
    menu.mkdir()
    (menu / "bazzite-test.desktop").touch()
    (menu / "bazzite-console-suite.desktop").touch()
    (menu / "unrelated-app.desktop").touch()

    assert [path.name for path in desktop_icons.launchers(menu)] == ["bazzite-test.desktop"]


@pytest.mark.parametrize("show", [False, True])
def test_finished_install_respects_desktop_icon_setting(window, tmp_path, desktop, show):
    menu = tmp_path / "applications"
    menu.mkdir()
    name = "ps5-rpcs3-manager.desktop"
    (menu / name).write_text("[Desktop Entry]\n")
    (desktop / name).write_text("[Desktop Entry]\n")
    window.menu = menu
    window.icons_box.setChecked(show)
    window.settings.setValue(DESKTOP_ICONS_KEY, show)
    exit_file = tmp_path / "installer.exit"
    exit_file.write_text("0\n")
    entry = next(entry for entry in window.entries if entry.key == "rpcs3")
    window.pending = Pending(entry, "install", exit_file, entry.tag)

    window._check_pending()

    assert (desktop / name).exists() is show
    assert (menu / name).exists()


def test_start_with_icons_off_removes_existing_console_shortcuts(window, tmp_path, desktop):
    menu = tmp_path / "applications"
    menu.mkdir()
    for name in ("bazzite-test.desktop", "ps5-sftp-tools.desktop", "bazzite-console-suite.desktop"):
        (menu / name).touch()
        (desktop / name).touch()
    window.menu = menu
    window.settings.setValue(DESKTOP_ICONS_KEY, False)
    window.icons_box.setChecked(False)

    window.settle_icons()

    assert sorted(path.name for path in desktop.iterdir()) == ["bazzite-console-suite.desktop"]


def test_first_start_detects_console_shortcuts_and_toggle_restores_them(window, tmp_path, desktop, monkeypatch):
    menu = tmp_path / "applications"
    menu.mkdir()
    name = "ps5-rpcs3-manager.desktop"
    (menu / name).write_text("[Desktop Entry]\n")
    (desktop / name).write_text("[Desktop Entry]\n")
    window.menu = menu
    window.settings.remove(DESKTOP_ICONS_KEY)
    questions = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args: questions.append(args[2]) or
                        QMessageBox.StandardButton.No)
    monkeypatch.setattr(desktop_icons.shutil, "which", lambda _: None)

    window.settle_icons()

    assert len(questions) == 1
    assert not (desktop / name).exists()
    window.icons_box.setChecked(True)
    assert (desktop / name).is_file()
    window.icons_box.setChecked(False)
    assert not (desktop / name).exists()
