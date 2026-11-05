# SPDX-License-Identifier: GPL-3.0-or-later
"""The view, the intro, the sound and the controller: the header, the pills, the tiles and their menu, the keys."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest
from PyQt6.QtCore import QEvent, QRect, Qt
from PyQt6.QtGui import QColor, QKeyEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

from bc250_portal import APP_NAME, MANIFEST, audio, bigpicture
from bc250_portal import main_window as mw
from bc250_portal.gamepad import DEADZONE, FIRST_REPEAT, Gamepad, stick_direction
from bc250_portal.manifest import load
from bc250_portal.sources import Records, Sources


class FakeSounds(audio.Sounds):
    def __init__(self, available: bool = True):
        super().__init__()
        self.output = available
        self.played: list[str] = []
        self.stopped = 0

    def available(self) -> bool:
        return self.output

    def play(self, name: str) -> bool:
        if not self.enabled or not self.output:
            return False
        self.played.append(name)
        return True

    def stop(self) -> None:
        self.stopped += 1


class FakePad:
    """Stands in for the pygame source: events() returns what the test queued."""

    def __init__(self):
        self.queue: list[tuple[str, str, object]] = []
        self.closed = False

    def events(self):
        out, self.queue = self.queue, []
        return out

    def close(self):
        self.closed = True


class Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


def make_window(tmp_path, sounds=None, pad=None, clock=None):
    pad = pad or FakePad()
    gamepad = Gamepad(source_factory=lambda: pad, clock=clock or Clock())
    window = mw.MainWindow(load(MANIFEST), Sources(tmp_path / "work"), Records(tmp_path / "installed.json"),
                           sounds=sounds or FakeSounds(), gamepad=gamepad)
    return window, pad


@pytest.fixture
def made(qapp, home, settings_dir, tmp_path):
    windows = []

    def make(**kwargs):
        window, pad = make_window(tmp_path, **kwargs)
        windows.append(window)
        return window, pad

    yield make
    for window in windows:
        window.close()


def key(window, which, modifiers=Qt.KeyboardModifier.NoModifier):
    target = window.focusWidget() or window
    QApplication.sendEvent(target, QKeyEvent(QEvent.Type.KeyPress, which, modifiers))


def start(window):
    """The portal as it opens: shown, the intro skipped, the focus on the first tile."""
    window.show()
    window.start_up()
    window.intro.skip()


# ---------------------------------------------------------------------------------------------------- the files
def test_the_sound_is_there_and_the_right_length():
    with wave.open(str(audio.SOUNDS / "bigpicture.wav"), "rb") as sound:
        seconds = sound.getnframes() / sound.getframerate()
        assert 2.8 <= seconds <= 3.6
        assert sound.getnchannels() == 2 and sound.getsampwidth() == 2
    assert not (audio.SOUNDS / "swoosh.wav").exists()                   # the desktop's swoosh is gone


def test_sounds_stay_silent_without_output_or_when_off(tmp_path):
    sounds = audio.Sounds(tmp_path)                 # no files here
    sounds.available = lambda: True
    assert not sounds.play(audio.INTRO)             # no file: silent, no error
    sounds.enabled = False
    assert not sounds.play(audio.INTRO)
    sounds.enabled, sounds.available = True, lambda: False
    assert not sounds.play(audio.INTRO)
    sounds.stop()


# --------------------------------------------------------------------------------------------------- the controller
def test_stick_needs_a_real_push_and_goes_along_its_stronger_axis():
    assert stick_direction(0, 0) is None
    assert stick_direction(DEADZONE - 0.01, 0) is None
    assert stick_direction(0.9, 0.3) == "right" and stick_direction(-0.9, 0.3) == "left"
    assert stick_direction(0.2, 0.9) == "down" and stick_direction(0.2, -0.9) == "up"


def test_steams_virtual_pad_only_when_steam_started_the_portal():
    from bc250_portal.gamepad import launched_by_steam, steam_virtual_pad
    outside = {"HOME": "/home/x"}
    steam_virtual_pad(outside)
    assert not launched_by_steam(outside) and "SDL_GAMECONTROLLER_ALLOW_STEAM_VIRTUAL_GAMEPAD" not in outside
    for env in ({"SteamGameId": "12345"}, {"SDL_GAMECONTROLLER_IGNORE_DEVICES": "0x28de/0x1302"}):
        steam_virtual_pad(env)
        assert launched_by_steam(env) and env["SDL_GAMECONTROLLER_ALLOW_STEAM_VIRTUAL_GAMEPAD"] == "1"
    chosen = {"SteamGameId": "1", "SDL_GAMECONTROLLER_ALLOW_STEAM_VIRTUAL_GAMEPAD": "0"}
    steam_virtual_pad(chosen)
    assert chosen["SDL_GAMECONTROLLER_ALLOW_STEAM_VIRTUAL_GAMEPAD"] == "0"         # a choice of the user's stays


def test_buttons_become_actions_and_a_held_direction_repeats():
    clock = Clock()
    pad = FakePad()
    gamepad = Gamepad(source_factory=lambda: pad, clock=clock)
    got: list[str] = []
    gamepad.action.connect(got.append)
    assert gamepad.start()
    pad.queue = [("button", "a", True), ("button", "a", False), ("button", "b", True), ("button", "x", True),
                 ("button", "leftshoulder", True), ("button", "rightshoulder", True), ("button", "y", True),
                 ("button", "start", True), ("button", "rightstick", True)]
    gamepad.poll()
    # Y updates and ☰ (Start) opens the Settings page (owner, 04-11-2026); R3 the on-screen keyboard (05-11-2026)
    assert got == ["accept", "back", "menu", "previous", "next", "update", "settings", "keyboard"]
    got.clear()
    pad.queue = [("button", "dpad_down", True)]
    gamepad.poll()
    clock.now = FIRST_REPEAT - 0.01
    gamepad.poll()
    assert got == ["down"]
    clock.now = FIRST_REPEAT + 0.01
    gamepad.poll()
    assert got == ["down", "down"]
    pad.queue = [("button", "dpad_down", False)]
    gamepad.poll()
    clock.now = 5
    gamepad.poll()
    assert got == ["down", "down"]                  # released: no more
    gamepad.stop()
    assert pad.closed


def test_the_stick_moves_once_per_push_and_a_new_direction_acts_at_once():
    pad = FakePad()
    gamepad = Gamepad(source_factory=lambda: pad, clock=Clock())
    got: list[str] = []
    gamepad.action.connect(got.append)
    gamepad.start()
    pad.queue = [("axis", "leftx", 0.9), ("axis", "leftx", 0.95), ("axis", "lefty", 0.1)]
    gamepad.poll()
    pad.queue = [("axis", "leftx", 0.0), ("axis", "lefty", -0.9)]
    gamepad.poll()
    assert got == ["right", "up"]
    gamepad.stop()


def test_no_pygame_means_no_controller_and_no_error():
    def missing():
        raise ImportError("no pygame")

    gamepad = Gamepad(source_factory=missing)
    assert gamepad.start() is False
    gamepad.poll()
    gamepad.stop()


# ----------------------------------------------------------------------------------------------------- the view
def test_nearest_tile_in_a_direction():
    grid = [QRect(x * 260, y * 330, 244, 316) for y in range(2) for x in range(3)]
    here, rest = grid[0], grid[1:]
    assert bigpicture.next_in_direction(here, rest, "right") == 0                   # grid[1]
    assert bigpicture.next_in_direction(here, rest, "down") == 2                    # grid[3]
    assert bigpicture.next_in_direction(here, rest, "left") is None
    assert bigpicture.next_in_direction(here, rest, "up") is None
    assert bigpicture.next_in_direction(grid[4], [grid[2], grid[1]], "up") == 1     # in line beats off to the side


def test_view_has_a_tile_per_app_and_shows_each_state(made):
    window, _ = made()
    assert set(window.big.tiles) == set(window.states)
    check = window.big.tiles["check"]
    assert check.name == "Bazzite Test" and check.pixmap and not check.pixmap.isNull()
    window.states["check"].show_state(False, "")
    window.big.sync(window.states)
    assert window.big.tiles["check"].status == "Not installed"
    window.states["check"].show_state(True, "check-v0.0.1")     # not the pinned tag
    window.big.sync(window.states)
    assert window.big.tiles["check"].marker == "update" and window.big.tiles["check"].status == "Update"
    window.states["check"].show_state(True, "")
    window.big.sync(window.states)
    assert window.big.tiles["check"].marker == "reinstall"
    window.states["check"].show_state(True, "local", busy="Installing…")
    window.big.sync(window.states)
    assert window.big.tiles["check"].status == "Installing…" and window.big.tiles["check"].status_colour == bigpicture.BLUE


def test_the_view_is_the_window_with_the_suites_name_and_a_big_icon(made):
    """One view (owner, 01-11-2026): the window's central widget, the header with the suite's icon larger than the
    96 px of an app's header, the suite's name as the title with the version and the stage."""
    window, _ = made()
    assert window.centralWidget() is window.big
    assert window.big.title.text() == APP_NAME == "BC250 Bazzite Suite"
    assert window.big.version.text() == f"v{mw.__version__}"
    assert window.big.logo.width() == window.big.logo.height() == bigpicture.LOGO_PX == bigpicture.ICON_PX
    assert "wiki" in window.big.logo.toolTip()
    import bc250_portal
    assert window.big.stage.text() == bc250_portal.STAGE
    assert window.big.stage.toolTip() == bc250_portal.STAGE_NOTE
    assert window.big.stage.isVisibleTo(window) == bool(bc250_portal.STAGE)
    assert "verified by checksum" in window.big.info.text_ and mw.CORE_VERSION in window.big.info.text_


def test_the_logo_opens_the_wiki(made, monkeypatch):
    from bc250_core import SUITE_MANUAL_URL
    window, _ = made()
    opened = []
    monkeypatch.setattr(mw.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    window.big.logo.clicked.emit()
    assert opened == [SUITE_MANUAL_URL]


# ----------------------------------------------------------------------------------------------- the intro
def test_the_portal_opens_with_the_intro_and_its_sound(made):
    """The intro plays before the portal shows itself (owner, 01-11-2026): dark from its first frame, the suite's
    name in capitals; its sound plays; when it ends the focus is on the first tile and the controller listens."""
    sounds = FakeSounds()
    window, pad = made(sounds=sounds)
    window.show()
    assert window.intro is None
    window.start_up()
    intro = window.intro
    assert intro is not None and intro.isVisible() and sounds.played == [audio.INTRO]
    assert window.gamepad.source is pad
    intro.progress = 0.0
    picture = intro.grab().toImage()
    assert picture.pixelColor(5, 5) == QColor("#04060c")                   # opaque from the first frame
    intro.animation.setCurrentTime(intro.animation.duration())
    assert window.intro is None
    assert window.big.focused_tile() is window.big.current_tiles()[0]


def test_the_intro_draws_the_suites_name_in_capitals_and_the_1024_px_icon(made):
    from PyQt6.QtGui import QPixmap
    assert bigpicture.INTRO_LOGO.is_file() and QPixmap(str(bigpicture.INTRO_LOGO)).width() == 1024
    window, _ = made()
    window.show()
    window.start_up()
    intro = window.intro
    assert intro.logo.width() == 1024
    intro.progress = 0.5
    intro.grab()
    first = intro._logo_scaled
    assert first.width() < 1024 and intro._logo_at is not None
    intro.progress = 0.55
    intro.grab()
    assert intro._logo_scaled is first                          # not scaled again on the next frame
    assert intro.title == "BC250 BAZZITE SUITE"
    intro.skip()


def test_any_key_skips_the_intro_and_stops_its_sound(made):
    sounds = FakeSounds()
    window, _ = made(sounds=sounds)
    window.show()
    window.start_up()
    assert window.intro.hasFocus() or window.intro.isVisible()
    QApplication.sendEvent(window.intro, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space,
                                                   Qt.KeyboardModifier.NoModifier))
    assert window.intro is None and sounds.stopped >= 1


def test_the_controller_skips_the_intro(made, monkeypatch):
    window, pad = made()
    window.show()
    window.start_up()
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: window))
    pad.queue = [("button", "a", True)]
    window.gamepad.poll()
    assert window.intro is None


def test_no_mode_is_kept_and_nothing_switches(made):
    """No Suite Desktop Mode (owner, 01-11-2026): no mode pill, no F11, no setting."""
    from PyQt6.QtGui import QShortcut
    window, _ = made()
    assert not hasattr(window, "mode_pill") and not hasattr(window, "toggle_mode")
    assert not any(s.key().toString() == "F11" for s in window.findChildren(QShortcut))
    assert window.settings.value("portal/mode") is None
    assert "F11" not in bigpicture.LEGEND and "mode" not in bigpicture.LEGEND.lower()


def test_escape_and_b_close_the_portal_but_skip_the_intro_first(made, monkeypatch):
    """Escape closes the portal (owner, 01-11-2026: "ESC does not close the board"), B too with nothing open, after a
    Yes to the exit question (owner, 05-11-2026); while the intro plays, either skips it instead."""
    from PyQt6.QtGui import QShortcut
    asked = []
    monkeypatch.setattr(mw.QMessageBox, "question", lambda *a, **k: (asked.append(a[2]),
                                                                      mw.QMessageBox.StandardButton.Yes)[1])
    window, pad = made()
    window.show()
    window.start_up()
    # A window shortcut, so it works from any widget; it fires only in the active window, which an offscreen test
    # has none of, so the test fires it.
    shortcut = next(s for s in window.findChildren(QShortcut) if s.key().toString() == "Esc")
    shortcut.activated.emit()                                # while the intro plays: it skips, nothing closes
    assert window.intro is None and window.isVisible()
    shortcut.activated.emit()
    assert not window.isVisible()
    again, pad = made()
    start(again)
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: again))
    pad.queue = [("button", "b", True)]
    again.gamepad.poll()
    assert not again.isVisible() and asked == [mw.EXIT_QUESTION, mw.EXIT_QUESTION]


def test_sound_off_is_kept_and_silences_the_intro(made):
    sounds = FakeSounds()
    window, _ = made(sounds=sounds)
    window.start_up()
    assert sounds.played == [audio.INTRO]
    window.intro.skip()
    window.sound_box.click()
    assert not window.sound_box.isChecked() and window.settings.value(mw.SOUND_KEY, type=bool) is False
    again_sounds = FakeSounds()
    again, _ = made(sounds=again_sounds)
    assert not again.sound_box.isChecked()                   # the choice is kept
    again.start_up()
    assert again_sounds.played == []
    again.intro.skip()


def test_without_an_audio_output_the_pill_is_disabled_with_a_reason(made):
    sounds = FakeSounds(available=False)
    window, _ = made(sounds=sounds)
    window.start_up()
    window.intro.skip()
    assert not window.sound_box.isEnabled() and window.sound_box.value.text() == "No"
    assert window.sound_box.toolTip() == audio.NO_OUTPUT and sounds.played == []
    assert window.settings.value(mw.SOUND_KEY, True, type=bool) is True          # the choice itself is untouched
    window.sounds.output = True                                                   # an output turns up
    window._show_sound()
    assert window.sound_box.isEnabled() and window.sound_box.isChecked()


# ------------------------------------------------------------------------------------------------ the header
def test_the_header_has_big_symbols_with_the_status_on_their_right(made):
    """Big symbols in place of the pills (owner, 05-11-2026): all the same square size, their row ending at the bottom
    of the suite's icon; ☰ at the top right, level with the title; on the right of the symbols the installed count
    over the status line. Scaled with the view on a handheld's screen."""
    window, _ = made()
    symbols = window.header_buttons
    assert len(symbols) == 4 and all(isinstance(s, bigpicture.SymbolButton) for s in symbols)
    window.show()
    window.resize(1920, 1080)
    QApplication.processEvents()
    QApplication.processEvents()
    big = window.big
    corner = window.settings_button
    assert {(s.width(), s.height()) for s in [*symbols, corner]} == {(bigpicture.SYMBOL_PX, bigpicture.SYMBOL_PX)}
    at = lambda w: w.mapTo(big, w.rect().topLeft())  # noqa: E731
    bottom = lambda w: w.mapTo(big, w.rect().bottomLeft()).y()  # noqa: E731
    assert abs(bottom(symbols[0]) - bottom(big.logo)) <= 2                # the row ends at the icon's bottom
    assert at(corner).y() <= at(big.title).y() + big.title.height()       # ☰ at the top ...
    assert at(corner).x() + corner.width() >= at(big.status).x() + big.status.width() - 2   # ... right
    assert at(big.status).x() > at(symbols[-1]).x() + symbols[-1].width()  # the status on the symbols' right
    assert at(big.installed).y() < at(big.status).y()
    window.resize(1280, 720)
    QApplication.processEvents()
    QApplication.processEvents()
    assert big.scale < 1 and {s.width() for s in symbols} == {round(bigpicture.SYMBOL_PX * big.scale)}
    assert abs(bottom(symbols[0]) - bottom(big.logo)) <= 2                # scaled with the view, still aligned


def test_a_symbols_badge_and_its_disabled_look(made):
    """The badge holds a short figure; a disabled symbol draws its glyph muted, an enabled one in the theme's text."""
    window, _ = made()
    symbol = window.updates_button
    symbol.set_badge("3/7", bigpicture.BLUE)
    assert symbol.badge == "3/7" and symbol.badge_colour == bigpicture.BLUE
    symbol.setEnabled(False)
    symbol.grab()
    symbol.setEnabled(True)
    symbol.grab()
    theme = bigpicture.current_theme()
    assert set(symbol._icons) == {bigpicture.muted(theme), theme.text}


def test_the_symbols_and_the_pills_work_as_before(made):
    window, _ = made()
    refreshed = []
    window.refresh_button.clicked.connect(lambda: refreshed.append(1))
    from PyQt6.QtTest import QTest
    QTest.keyClick(window.refresh_button, Qt.Key.Key_Space)
    assert refreshed == [1]
    toggled = []
    window.icons_box.toggled.connect(toggled.append)
    window.icons_box.click()
    assert window.icons_box.isChecked() and window.icons_box.value.text() == "Yes" and toggled == [True]
    window.icons_box.setChecked(True)                       # no change: no signal
    assert toggled == [True]


def test_the_focus_reaches_the_symbols_and_back_with_the_controller(made, monkeypatch):
    window, pad = made()
    start(window)
    window.resize(1500, 1000)
    QApplication.processEvents()
    QApplication.processEvents()
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: window))
    first = window.big.current_tiles()[0]
    assert window.focusWidget() is first
    pad.queue = [("button", "dpad_up", True), ("button", "dpad_up", False)]
    window.gamepad.poll()
    assert window.focusWidget() in window.header_buttons          # up from the top row: the symbols
    pad.queue = [("button", "dpad_down", True), ("button", "dpad_down", False)]
    window.gamepad.poll()
    assert isinstance(window.focusWidget(), bigpicture.BigTile)
    window.refresh_button.setFocus()
    pressed = []
    window.refresh_button.clicked.connect(lambda: pressed.append(1))
    pad.queue = [("button", "a", True)]
    window.gamepad.poll()
    assert pressed == [1]                                      # A presses the focused symbol


def test_the_settings_page_holds_the_settings(made, monkeypatch):
    """The Settings page behind ☰ (owner, 04-11-2026, as the Windows Portable Suite's portal): the ☰ pill or the
    controller's ☰ button shows it in place of the category strip and the tiles, under the same header; its pills
    (Desktop icons, Sound, the theme, the wallpaper), each with a short line, work as before; B, Escape or ☰ again
    go back to the tiles."""
    window, pad = made()
    start(window)
    window.resize(1500, 1000)
    QApplication.processEvents()
    big = window.big
    assert window.setting_pills == [window.icons_box, window.sound_box, window.theme_pill, window.wallpaper_pill]
    assert not any(p in window.header_buttons for p in window.setting_pills)
    assert all(big.settings_page.isAncestorOf(p) for p in window.setting_pills)
    assert [label.text() for label in big.setting_lines] == list(mw.SETTING_LINES)
    assert not big.in_settings() and big.keys.text() == bigpicture.LEGEND
    window.settings_button.click()
    QApplication.processEvents()
    assert big.in_settings() and big.strip.isHidden() and big.stack.isHidden()
    assert big.keys.text() == bigpicture.SETTINGS_LEGEND and big.hint.full == bigpicture.SETTINGS_HINT
    assert window.focusWidget() is window.icons_box             # the focus on its first pill
    assert big.current_tiles() and not any(t in big.focus_items() for t in big.current_tiles())
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: window))
    pad.queue = [("button", "dpad_down", True), ("button", "dpad_down", False)]
    window.gamepad.poll()
    assert window.focusWidget() is window.sound_box
    before = window.sound_box.isChecked()
    pad.queue = [("button", "a", True), ("button", "a", False)]
    window.gamepad.poll()
    assert window.sound_box.isChecked() is (not before)        # A changes the focused setting
    category = big.bar.currentIndex()
    pad.queue = [("button", "rightshoulder", True), ("button", "rightshoulder", False)]
    window.gamepad.poll()
    assert big.bar.currentIndex() == category                  # no category on the Settings page
    pad.queue = [("button", "b", True), ("button", "b", False)]
    window.gamepad.poll()
    assert not big.in_settings() and window.isVisible()         # B goes back, it does not close the portal
    assert isinstance(window.focusWidget(), bigpicture.BigTile) and big.keys.text() == bigpicture.LEGEND
    assert big.hint.full == big.hints[big.current_category()]
    pad.queue = [("button", "start", True), ("button", "start", False)]
    window.gamepad.poll()
    assert big.in_settings()
    key(window, Qt.Key.Key_Escape)
    assert not big.in_settings() and window.isVisible()
    window.toggle_settings()
    window.show_app("ncgui")                                    # a notice's line: back to the tiles
    assert not big.in_settings() and window.focusWidget() is big.tiles["ncgui"]


def test_the_arrow_keys_move_from_a_symbol_and_enter_presses_a_button(made):
    window, _ = made()
    start(window)
    window.resize(1500, 1000)
    QApplication.processEvents()
    QApplication.processEvents()
    window.refresh_button.setFocus()
    key(window, Qt.Key.Key_Right)
    assert window.focusWidget() is window.sysinfo_button
    key(window, Qt.Key.Key_Right)
    assert window.focusWidget() is window.apps_button
    key(window, Qt.Key.Key_Right)                              # Install all updates is disabled without updates
    assert window.focusWidget() is not window.updates_button
    key(window, Qt.Key.Key_Down)
    assert isinstance(window.focusWidget(), bigpicture.BigTile)
    window.restart_button.setText("● Restart: portal 99.0.0 is installed")
    window.restart_button.show()
    pressed = []
    window.restart_button.clicked.disconnect()
    window.restart_button.clicked.connect(lambda: pressed.append(1))
    window.restart_button.setFocus()
    key(window, Qt.Key.Key_Return)
    assert pressed == [1]                                      # Enter presses a title-row button
    key(window, Qt.Key.Key_Down)
    assert window.focusWidget() is not window.restart_button


def test_the_local_build_banner_is_in_the_view(made, tmp_path):
    window, _ = made()
    assert window.big.banner.isHidden()                      # not a local build: no banner
    local = mw.MainWindow(load(MANIFEST), Sources(tmp_path / "w2"), Records(tmp_path / "i2.json"),
                          local_build=tmp_path, sounds=FakeSounds())
    assert not local.big.banner.isHidden() and str(tmp_path) in local.big.banner.text()
    local.close()


# ----------------------------------------------------------------------------------------- keys and the controller
def test_arrow_keys_move_between_tiles_and_enter_opens(made, monkeypatch):
    window, _ = made()
    start(window)
    opened = []
    monkeypatch.setattr(window, "open_app", lambda entry, command: opened.append(entry.key))
    window.states["check"].show_state(True, "local")
    window.big.sync(window.states)
    tiles = window.big.current_tiles()
    assert window.focusWidget() is tiles[0]
    window.big.resize(1600, 900)
    window.big.reflow()
    key(window, Qt.Key.Key_Right)
    assert window.focusWidget() is tiles[1]
    key(window, Qt.Key.Key_Left)
    key(window, Qt.Key.Key_Return)
    assert opened == ["check"]


def test_the_controller_moves_opens_and_switches_category(made, monkeypatch):
    window, pad = made()
    start(window)
    window.big.resize(1600, 900)
    window.big.reflow()
    tiles = window.big.current_tiles()
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: window))
    pad.queue = [("button", "dpad_right", True), ("button", "dpad_right", False)]
    window.gamepad.poll()
    assert window.focusWidget() is tiles[1]
    pad.queue = [("button", "rightshoulder", True)]
    window.gamepad.poll()
    assert window.big.bar.currentIndex() == 1
    pad.queue = [("button", "leftshoulder", True)]
    window.gamepad.poll()
    assert window.big.bar.currentIndex() == 0
    key(window, Qt.Key.Key_PageDown)                         # on a tile: the category, not the page's scroll
    assert window.big.bar.currentIndex() == 1
    window.refresh_button.setFocus()
    key(window, Qt.Key.Key_PageUp)                           # on a symbol too
    assert window.big.bar.currentIndex() == 0


def test_the_controller_is_ignored_while_the_portal_has_no_focus(made, monkeypatch):
    window, pad = made()
    start(window)
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: None))
    first = window.focusWidget()
    pad.queue = [("button", "dpad_right", True)]
    window.gamepad.poll()
    assert window.focusWidget() is first                     # a game's input never moves the portal


def test_a_tile_that_is_not_installed_offers_to_install_it(made, monkeypatch):
    window, _ = made()
    start(window)
    started = []
    monkeypatch.setattr(window, "_start", lambda entry, action: started.append((entry.key, action)))
    overlay = next(e for e in window.entries if e.key == "overlay")       # not installed, no board change
    assert not window.states["overlay"].installed and not overlay.changes_board
    asked = []
    answers = iter([QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(a[2]), next(answers))[1])
    window.big.tiles["overlay"].click()
    assert asked[0].startswith(f"Install {overlay.name}?") and "terminal" in asked[0] and started == []
    window.big.tiles["overlay"].click()
    assert started == [("overlay", "install")]
    # An app that changes the board: its board warning is the question.
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: (warned.append(a[2]), QMessageBox.StandardButton.Yes)[1])
    window.big.tiles["acpi"].click()
    assert len(asked) == 2 and "changes how your BC-250 runs" in warned[0] and started[-1] == ("acpi", "install")


def test_an_app_with_several_ways_to_open_offers_a_menu(made, monkeypatch):
    window, _ = made()
    start(window)
    window.states["compute"].show_state(True, "local")
    shown = []
    monkeypatch.setattr(mw.QMenu, "exec", lambda self, *a: shown.append([a.text() for a in self.actions()]))
    window.big.tiles["compute"].click()
    assert shown == [["Bisect", "Unlock"]]


def test_the_tile_menu_holds_every_action(made, monkeypatch, home):
    """X or the Menu key (owner, 01-11-2026: the desktop's buttons are gone): Open, Install (Update, Reinstall) and
    Uninstall, grayed out where they cannot act now; check has no Uninstall. A right click opens it on a tile with
    nothing to update (owner, 04-11-2026: a right click updates)."""
    window, pad = made()
    start(window)
    names = lambda menu: [(a.text(), a.isEnabled()) for a in menu.actions() if not a.isSeparator()]  # noqa: E731
    gpu = next(e for e in window.entries if e.key == "gpu")
    assert names(window.tile_menu(gpu)) == [("Open", False), ("Install", True), ("Uninstall", False)]
    (home / ".local" / "bin" / "bc250-governor-manager").write_text("#!/bin/sh\n")
    window.records.set("gpu", "gpu-v0.0.9")
    window.refresh()
    menu = window.tile_menu(gpu)
    assert names(menu) == [("Open", True), ("Update", True), ("Uninstall", True)]
    assert menu.actions()[2].toolTip().startswith("Update BC-250 GPU Governor Manager v")
    check = window.entries[0]                                  # check goes with the portal: no Uninstall
    assert [a.text() for a in window.tile_menu(check).actions() if not a.isSeparator()] == ["Open", "Install"]
    compute = next(e for e in window.entries if e.key == "compute")
    assert [a.text() for a in window.tile_menu(compute).actions()][:2] == ["Bisect", "Unlock"]
    shown = []
    monkeypatch.setattr(mw.QMenu, "exec", lambda self, *a: shown.append([a.text() for a in self.actions()]))
    window.big.tiles["gpu"].setFocus()
    key(window, Qt.Key.Key_Menu)
    assert shown and "Uninstall" in shown[-1]
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: window))
    pad.queue = [("button", "x", True)]
    window.gamepad.poll()
    assert len(shown) == 2
    from PyQt6.QtGui import QContextMenuEvent
    from PyQt6.QtCore import QPoint
    tile = window.big.tiles["acpi"]                            # not installed: nothing to update
    QApplication.sendEvent(tile, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5)))
    assert len(shown) == 3
    installed = []
    monkeypatch.setattr(window, "install", lambda entry: installed.append(entry.key))
    window.tile_menu(gpu).actions()[2].trigger()
    assert installed == ["gpu"]


def test_a_right_click_or_y_updates_the_app(made, monkeypatch, home):
    """A right click on a tile, or Y on it (owner, 04-11-2026, as the Windows Portable Suite's portal): its update,
    through install() and so with the board warning for an app that changes the board; no menu."""
    window, pad = made()
    start(window)
    shown, installed = [], []
    monkeypatch.setattr(mw.QMenu, "exec", lambda self, *a: shown.append(1))
    monkeypatch.setattr(window, "install", lambda entry: installed.append(entry.key))
    (home / ".local" / "bin" / "bc250-governor-manager").write_text("#!/bin/sh\n")
    window.records.set("gpu", "gpu-v0.0.9")
    window.refresh()
    assert window.states["gpu"].update
    from PyQt6.QtGui import QContextMenuEvent
    from PyQt6.QtCore import QPoint
    tile = window.big.tiles["gpu"]
    QApplication.sendEvent(tile, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5)))
    assert installed == ["gpu"] and shown == []
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: window))
    tile.setFocus()
    pad.queue = [("button", "y", True)]
    window.gamepad.poll()
    assert installed == ["gpu", "gpu"] and shown == []
    window.big.tiles["acpi"].setFocus()                        # nothing to update: Y does nothing
    pad.queue = [("button", "y", False), ("button", "y", True)]
    window.gamepad.poll()
    assert installed == ["gpu", "gpu"] and shown == []


def test_the_controller_drives_a_menu_with_keys(made, monkeypatch):
    window, _ = made()
    start(window)
    seen = []
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: window))
    popup = mw.QMenu(window)
    popup.addAction("One")
    popup.addAction("Two", lambda: seen.append("two"))
    monkeypatch.setattr(QApplication, "activePopupWidget", staticmethod(lambda: popup))
    sent = []
    monkeypatch.setattr(QApplication, "sendEvent", staticmethod(lambda target, event: sent.append(
        (target, event.key(), event.type())) or True))
    window._gamepad_action("down")
    window._gamepad_action("accept")
    window._gamepad_action("back")
    assert [k for _, k, t in sent if t == QEvent.Type.KeyPress] == [Qt.Key.Key_Down, Qt.Key.Key_Return,
                                                                    Qt.Key.Key_Escape]
    assert all(target is popup for target, _, _ in sent)


def test_an_install_stays_in_the_view(made, monkeypatch):
    window, _ = made()
    start(window)
    monkeypatch.setattr(window.worker, "start", lambda job: None)
    window._start(window.entries[0], "install")
    assert window.centralWidget() is window.big and window.states["check"].busy == "Downloading…"
    assert window.big.tiles["check"].status == "Downloading…"


def test_the_legend_names_the_keys(made):
    window, _ = made()
    text = window.big.keys.text()
    assert "A / Enter" in text and "Y / Right click  Update" in text and "X / Menu key" in text and "LB / RB" in text \
        and "B / Esc" in text
    assert "font-size:24px" in window.big.keys.styleSheet()                   # readable from the couch


def test_wallpaper_and_veil_reach_the_view(made):
    window, _ = made()
    window.set_transparency(75)
    assert window.big.veil == 75
    window.apply_wallpaper(Path(mw.wallpaper.EXAMPLE))
    assert not window.big.picture.isNull()


# ------------------------------------------------------------------------------------- a handheld's 1280 px screen
@pytest.mark.parametrize("height, small", [(720, True), (800, True), (1080, False)])
def test_the_view_scales_down_for_a_handheld_screen(made, height, small):
    window, _ = made()
    window.resize(1280 if small else 1920, height)
    window.show()
    QApplication.processEvents()
    tile = window.big.tiles["check"]
    assert (window.big.scale < 1.0) is small and window.big.scale >= bigpicture.SMALLEST
    assert (tile.width() < bigpicture.TILE_W) is small
    assert window.big.columns["sustainable"] * tile.width() <= window.big.width()
    assert window.big.minimumSizeHint().width() <= 640 or window.big.minimumWidth() <= 640
    assert (window.big.logo.width() < bigpicture.LOGO_PX) is small
    symbols = window.header_buttons
    row = (sum(s.width() for s in symbols) + len(symbols) * window.big.symbol_row.spacing()
           + window.big.status.sizeHint().width())
    room = window.big.width() - 2 * window.big.outer.contentsMargins().left() - window.big.logo.width()
    assert row <= room                                      # the symbols and the status line fit in one row


def test_each_category_keeps_its_own_columns(made):
    window, _ = made()
    big = window.big
    window.show()
    window.resize(1900, 1000)
    QApplication.processEvents()
    QApplication.processEvents()
    wide = big.columns["sustainable"]
    big.bar.setCurrentIndex(1)
    window.resize(900, 1000)
    QApplication.processEvents()
    QApplication.processEvents()
    big.bar.setCurrentIndex(0)                          # it was laid out for 1900 px; now the window is narrower
    assert big.columns["sustainable"] < wide


def test_r3_toggles_the_on_screen_keyboard_in_a_dialog_too(made, monkeypatch):
    """R3 (owner, 05-11-2026): Bazzite's on-screen keyboard, also while a question or the file dialog is open, where
    text is typed; when the desktop has none, the window says what to do. The legend names it."""
    window, pad = made()
    start(window)
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: window))
    toggled = []
    monkeypatch.setattr(window.keyboard, "toggle", lambda: toggled.append(1) or True)
    pad.queue = [("button", "rightstick", True), ("button", "rightstick", False)]
    window.gamepad.poll()
    assert toggled == [1]
    monkeypatch.setattr(QApplication, "activeModalWidget", staticmethod(lambda: window))   # a dialog is open
    window._gamepad_action("keyboard")
    assert toggled == [1, 1]
    from bc250_portal import keyboard
    told = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: told.append(a[2]))

    def none():
        raise keyboard.KeyboardError(keyboard.NOT_CHOSEN)
    monkeypatch.setattr(window.keyboard, "toggle", none)
    window._gamepad_action("keyboard")
    assert told == [keyboard.NOT_CHOSEN]
    assert "R3  Keyboard" in bigpicture.LEGEND


def test_every_controller_action_plays_the_short_sound(made, monkeypatch):
    """blob.wav on every controller action (owner, 05-11-2026), not on the button that skips the intro, and not with
    the Sound setting off."""
    import wave
    with wave.open(str(audio.SOUNDS / f"{audio.ACTION}.wav"), "rb") as sound:
        assert sound.getnframes() / sound.getframerate() < 0.5            # short: a held direction repeats
    window, pad = made()
    window.start_up()
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: window))
    pad.queue = [("button", "a", True)]
    window.gamepad.poll()                                                  # skips the intro: silent
    assert window.sounds.played == [audio.INTRO]
    pad.queue = [("button", "a", False), ("button", "dpad_right", True), ("button", "dpad_right", False),
                 ("button", "rightshoulder", True), ("button", "rightshoulder", False)]
    window.gamepad.poll()
    assert window.sounds.played == [audio.INTRO, audio.ACTION, audio.ACTION]
    window.sound_box.setChecked(False)
    pad.queue = [("button", "leftshoulder", True)]
    window.gamepad.poll()
    assert window.sounds.played.count(audio.ACTION) == 2


def test_keys_and_clicks_play_the_short_sound_too(made, monkeypatch):
    """The short sound on every action whatever it comes from (owner, 05-11-2026): a key that acts, a click on a
    tile or a symbol, the shortcuts, and a controller Steam turns into keys; not on a key that does nothing, a held
    key's repeats, a click on the room around the tiles or on text that only shows, and once for a click."""
    from PyQt6.QtTest import QTest
    window, _ = made()
    start(window)
    actions = lambda: window.sounds.played.count(audio.ACTION)               # noqa: E731
    tile = window.focusWidget()
    QTest.keyClick(tile, Qt.Key.Key_Right)
    assert actions() == 1
    QTest.keyClick(window.focusWidget(), Qt.Key.Key_X)                       # no action of the portal's
    QApplication.sendEvent(window.focusWidget(), QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Left,
                                                           Qt.KeyboardModifier.NoModifier, "", True))
    assert actions() == 1                                                    # nor a repeat (not spontaneous either)
    QTest.mouseClick(window.refresh_button, Qt.MouseButton.LeftButton)       # a symbol: once
    assert actions() == 2
    QTest.mouseClick(window.big.installed, Qt.MouseButton.LeftButton)        # only shows
    QTest.mouseClick(window.big.status, Qt.MouseButton.LeftButton)
    QTest.mouseClick(window.big, Qt.MouseButton.LeftButton, pos=window.big.rect().bottomRight())
    assert actions() == 2
    monkeypatch.setattr(window, "confirm_exit", lambda: False)
    window._escape_key()                                                     # Escape's shortcut
    assert actions() == 3
    window.sound_box.setChecked(False)
    QTest.keyClick(window.focusWidget(), Qt.Key.Key_Right)
    assert actions() == 3


def test_the_key_that_skips_the_intro_is_silent(made):
    from PyQt6.QtTest import QTest
    window, _ = made()
    window.show()
    window.start_up()
    QTest.keyClick(window.intro, Qt.Key.Key_Return)
    assert window.sounds.played == [audio.INTRO]
