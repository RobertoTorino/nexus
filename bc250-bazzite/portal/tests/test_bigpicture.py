# SPDX-License-Identifier: GPL-3.0-or-later
"""Suite Big Picture Mode, the sound and the controller: the view, the modes, the pills, what is kept, the keys."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest
from PyQt6.QtCore import QEvent, QRect, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

from bc250_portal import MANIFEST, audio, bigpicture
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


# ---------------------------------------------------------------------------------------------------- the files
@pytest.mark.parametrize("name, low, high", [("swoosh", 0.5, 1.5), ("bigpicture", 2.8, 3.6)])
def test_the_sounds_are_there_and_the_right_length(name, low, high):
    with wave.open(str(audio.SOUNDS / f"{name}.wav"), "rb") as sound:
        seconds = sound.getnframes() / sound.getframerate()
        assert low <= seconds <= high
        assert sound.getnchannels() == 2 and sound.getsampwidth() == 2


def test_sounds_stay_silent_without_output_or_when_off(tmp_path):
    sounds = audio.Sounds(tmp_path)                 # no files here
    sounds.available = lambda: True
    assert not sounds.play(audio.SWOOSH)            # no file: silent, no error
    sounds.enabled = False
    assert not sounds.play(audio.SWOOSH)
    sounds.enabled, sounds.available = True, lambda: False
    assert not sounds.play(audio.SWOOSH)
    sounds.stop()


# --------------------------------------------------------------------------------------------------- the controller
def test_stick_needs_a_real_push_and_goes_along_its_stronger_axis():
    assert stick_direction(0, 0) is None
    assert stick_direction(DEADZONE - 0.01, 0) is None
    assert stick_direction(0.9, 0.3) == "right" and stick_direction(-0.9, 0.3) == "left"
    assert stick_direction(0.2, 0.9) == "down" and stick_direction(0.2, -0.9) == "up"


def test_buttons_become_actions_and_a_held_direction_repeats():
    clock = Clock()
    pad = FakePad()
    gamepad = Gamepad(source_factory=lambda: pad, clock=clock)
    got: list[str] = []
    gamepad.action.connect(got.append)
    assert gamepad.start()
    pad.queue = [("button", "a", True), ("button", "a", False), ("button", "b", True), ("button", "x", True),
                 ("button", "leftshoulder", True), ("button", "rightshoulder", True), ("button", "y", True),
                 ("button", "start", True)]
    gamepad.poll()
    assert got == ["accept", "back", "previous", "next", "mode", "mode"]
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
    assert set(window.big.tiles) == set(window.cards)
    check = window.big.tiles["check"]
    assert check.name == "Bazzite Test" and check.pixmap and not check.pixmap.isNull()
    window.cards["check"].show_state(False, "")
    window.big.sync(window.cards)
    assert window.big.tiles["check"].status == "Not installed"
    window.cards["check"].show_state(True, "check-v0.0.1")      # not the pinned tag
    window.big.sync(window.cards)
    assert window.big.tiles["check"].marker == "update" and window.big.tiles["check"].status == "Update"
    window.cards["check"].show_state(True, "")
    window.big.sync(window.cards)
    assert window.big.tiles["check"].marker == "reinstall"


# ---------------------------------------------------------------------------------------------------- the modes
def test_it_starts_in_desktop_mode_with_the_pills(made):
    window, _ = made()
    assert not window.in_big_picture() and not window.isFullScreen()
    assert window.mode_pill.value.text() == "Desktop" and window.sound_box.isChecked()
    assert window.settings.value(mw.MODE_KEY) is None
    assert bigpicture.NAME in window.mode_pill.toolTip() and bigpicture.DESKTOP_NAME in window.mode_pill.toolTip()


def test_the_mode_pill_switches_to_big_picture_with_an_intro_and_back(made):
    sounds = FakeSounds()
    window, pad = made(sounds=sounds)
    window.show()
    window.mode_pill.click()
    assert window.in_big_picture() and window.isFullScreen()
    assert window.stack.currentWidget() is window.big
    assert window.intro is not None and sounds.played == [audio.INTRO]
    assert window.mode_pill.value.text() == "BPM mode"
    assert window.pill_box.parent() is window.big and window.pill_box.isVisibleTo(window.big)   # the same pills
    assert window.gamepad.source is pad and window.settings.value(mw.MODE_KEY) == "bigpicture"
    window.intro.skip()                                      # any key, click or button
    assert window.intro is None and sounds.stopped >= 1
    assert window.big.focused_tile() is window.big.current_tiles()[0]
    window.mode_pill.click()                                 # the same pill, in Big Picture Mode
    assert not window.in_big_picture() and not window.isFullScreen()
    assert window.pill_box.parent() is window.backdrop and window.header_words.indexOf(window.pill_box) >= 0
    assert window.mode_pill.value.text() == "Desktop" and window.gamepad.source is None and pad.closed
    assert window.settings.value(mw.MODE_KEY) == "desktop"
    assert sounds.played == [audio.INTRO, audio.SWOOSH]       # back on the desktop: the start-up swoosh again


def test_the_intro_draws_the_1024_px_icon_and_scales_it_once(made):
    from PyQt6.QtGui import QPixmap
    assert bigpicture.INTRO_LOGO.is_file() and QPixmap(str(bigpicture.INTRO_LOGO)).width() == 1024
    window, _ = made()
    window.show()
    window.enter_big_picture()
    intro = window.intro
    assert intro.logo.width() == 1024
    intro.progress = 0.5
    intro.grab()
    first = intro._logo_scaled
    assert first.width() < 1024 and intro._logo_at is not None
    intro.progress = 0.55
    intro.grab()
    assert intro._logo_scaled is first                          # not scaled again on the next frame
    intro.skip()


def test_f11_switches_both_ways(made):
    window, _ = made()
    window.show()
    from PyQt6.QtGui import QShortcut
    shortcut = next(s for s in window.findChildren(QShortcut) if s.key().toString() == "F11")
    shortcut.activated.emit()
    assert window.in_big_picture()
    shortcut.activated.emit()
    assert not window.in_big_picture()


def test_any_key_skips_the_intro(made):
    window, _ = made()
    window.show()
    window.enter_big_picture()
    assert window.intro.hasFocus() or window.intro.isVisible()
    QApplication.sendEvent(window.intro, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space,
                                                   Qt.KeyboardModifier.NoModifier))
    assert window.intro is None


def test_the_intro_runs_to_its_end_by_itself(made):
    window, _ = made()
    window.show()
    window.enter_big_picture()
    window.intro.animation.setCurrentTime(window.intro.animation.duration())
    assert window.intro is None


def test_it_opens_in_the_last_mode_and_keeps_the_desktop_size(made, tmp_path):
    window, _ = made()
    window.show()
    window.enter_big_picture()
    window.close()
    assert window.settings.value("window/geometry") is not None
    again, _ = made(sounds=FakeSounds())
    again.show()
    assert not again.isFullScreen()                          # the saved size is the window's, not the screen's
    again.start_up()
    assert again.in_big_picture() and again.sounds.played == [audio.INTRO]


def test_the_swoosh_plays_at_start_unless_sound_is_off(made):
    sounds = FakeSounds()
    window, _ = made(sounds=sounds)
    window.start_up()
    assert sounds.played == [audio.SWOOSH]
    window.sound_box.click()
    assert not window.sound_box.isChecked() and window.settings.value(mw.SOUND_KEY, type=bool) is False
    again_sounds = FakeSounds()
    again, _ = made(sounds=again_sounds)
    assert not again.sound_box.isChecked()                   # the choice is kept
    again.start_up()
    assert again_sounds.played == []
    again.enter_big_picture()
    assert again_sounds.played == []                         # off is off for the intro too


def test_every_header_pill_is_in_big_picture_mode_too(made):
    window, _ = made()
    window.show()
    window.enter_big_picture()
    window.intro.skip()
    assert all(window.big.isAncestorOf(pill) for pill in window.header_pills)
    assert len(window.header_pills) == 9
    window.sound_box.click()                                 # a click there works as on the desktop
    assert not window.sounds.enabled
    window.leave_big_picture()
    assert all(window.backdrop.isAncestorOf(pill) for pill in window.header_pills)


def test_the_local_build_banner_is_in_big_picture_mode_too(made, tmp_path):
    window, _ = made()
    assert window.big.banner.isHidden()                      # not a local build: no banner
    local = mw.MainWindow(load(MANIFEST), Sources(tmp_path / "w2"), Records(tmp_path / "i2.json"),
                          local_build=tmp_path, sounds=FakeSounds())
    local.show()
    local.enter_big_picture()
    local.intro.skip()
    assert not local.big.banner.isHidden() and str(tmp_path) in local.big.banner.text()
    assert local.big.banner.text() == local.local_banner.text()
    local.close()


def test_the_focus_reaches_the_pills_and_back_with_the_controller(made, monkeypatch):
    window, pad = made()
    enter(window)
    window.show()
    window.resize(1500, 1000)
    QApplication.processEvents()
    QApplication.processEvents()
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: window))
    first = window.big.current_tiles()[0]
    assert window.focusWidget() is first
    pad.queue = [("button", "dpad_up", True), ("button", "dpad_up", False)]
    window.gamepad.poll()
    assert window.focusWidget() in window.header_pills          # up from the top row: the pills
    pad.queue = [("button", "dpad_down", True), ("button", "dpad_down", False)]
    window.gamepad.poll()
    assert isinstance(window.focusWidget(), bigpicture.BigTile)
    window.sound_box.setFocus()
    before = window.sound_box.isChecked()
    pad.queue = [("button", "a", True)]
    window.gamepad.poll()
    assert window.sound_box.isChecked() is (not before)        # A presses the focused pill


def test_an_install_leaves_big_picture_for_the_terminal(made, monkeypatch):
    window, _ = made()
    enter(window)
    monkeypatch.setattr(window.worker, "start", lambda job: None)
    window._start(window.entries[0], "install")
    assert not window.in_big_picture()


def test_without_an_audio_output_the_pill_is_disabled_with_a_reason(made):
    sounds = FakeSounds(available=False)
    window, _ = made(sounds=sounds)
    window.start_up()
    assert not window.sound_box.isEnabled() and window.sound_box.value.text() == "No"
    assert window.sound_box.toolTip() == audio.NO_OUTPUT and sounds.played == []
    assert window.settings.value(mw.SOUND_KEY, True, type=bool) is True          # the choice itself is untouched
    window.sounds.output = True                                                   # an output turns up
    window.start_up()
    assert window.sound_box.isEnabled() and window.sound_box.isChecked()


# ----------------------------------------------------------------------------------------- keys and the controller
def enter(window):
    window.show()
    window.enter_big_picture()
    window.intro.skip()


def test_arrow_keys_move_between_tiles_and_enter_opens(made, monkeypatch):
    window, _ = made()
    enter(window)
    opened = []
    monkeypatch.setattr(window, "open_app", lambda entry, command: opened.append(entry.key))
    window.cards["check"].show_state(True, "local")
    window.big.sync(window.cards)
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
    enter(window)
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
    pad.queue = [("button", "y", True)]
    window.gamepad.poll()
    assert not window.in_big_picture()


def test_the_controller_is_ignored_while_the_portal_has_no_focus(made, monkeypatch):
    window, pad = made()
    enter(window)
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: None))
    pad.queue = [("button", "y", True)]
    window.gamepad.poll()
    assert window.in_big_picture()                           # a game's input never moves the portal


def test_the_controller_skips_the_intro(made, monkeypatch):
    window, pad = made()
    window.show()
    window.enter_big_picture()
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: window))
    pad.queue = [("button", "a", True)]
    window.gamepad.poll()
    assert window.intro is None and window.in_big_picture()


def test_a_tile_that_is_not_installed_asks_and_goes_to_the_desktop_to_install(made, monkeypatch):
    window, _ = made()
    enter(window)
    installed = []
    monkeypatch.setattr(window, "install", lambda entry: installed.append(entry.key))
    window.cards["gpu"].show_state(False, "")
    answers = iter([QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: next(answers))
    window.big.tiles["gpu"].click()
    assert window.in_big_picture() and installed == []
    window.big.tiles["gpu"].click()
    assert not window.in_big_picture() and installed == ["gpu"]


def test_an_app_with_several_ways_to_open_offers_a_menu(made, monkeypatch):
    window, _ = made()
    enter(window)
    window.cards["compute"].show_state(True, "local")
    shown = []
    monkeypatch.setattr(mw.QMenu, "exec", lambda self, *a: shown.append([a.text() for a in self.actions()]))
    window.big.tiles["compute"].click()
    assert shown and len(shown[0]) == len(window.cards["compute"].entry.launch) > 1


def test_the_controller_drives_a_menu_with_keys(made, monkeypatch):
    window, _ = made()
    enter(window)
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


def test_wallpaper_and_veil_reach_big_picture_too(made):
    window, _ = made()
    window.set_transparency(75)
    assert window.big.veil == 75 and window.backdrop.veil == 75
    window.apply_wallpaper(Path(mw.wallpaper.EXAMPLE))
    assert not window.big.picture.isNull()


# ------------------------------------------------------------------------------------- a handheld's 1280 px screen
@pytest.mark.parametrize("width, columns", [(1280, 5), (1000, 5), (700, 3), (1900, 9)])
def test_the_header_pills_wrap_to_the_width_in_even_rows(made, width, columns):
    window, _ = made()
    window.show()
    window.resize(width, 800)
    QApplication.processEvents()
    assert window.pill_columns == columns
    rows = {window.pill_grid.getItemPosition(i)[0] for i in range(window.pill_grid.count())
            if window.pill_grid.itemAt(i).widget() in window.header_pills}
    assert len(rows) == -(-len(window.header_pills) // columns)
    assert window.minimumSizeHint().width() <= 700                     # the window may be narrower than the pills


def test_the_theme_note_follows_the_last_pill(made):
    window, _ = made()
    window.show()
    window.resize(1280, 800)
    QApplication.processEvents()
    row, column, _, span = window.pill_grid.getItemPosition(window.pill_grid.indexOf(window.theme_note))
    assert (row, column) == (1, 4) and span == 1                        # five and four pills: it follows the fourth


@pytest.mark.parametrize("height, small", [(720, True), (800, True), (1080, False)])
def test_big_picture_scales_down_for_a_handheld_screen(made, height, small):
    window, _ = made()
    window.big.setParent(None)
    window.big.resize(1280 if small else 1920, height)
    window.big.show()
    QApplication.processEvents()
    tile = window.big.tiles["check"]
    assert (window.big.scale < 1.0) is small and window.big.scale >= bigpicture.SMALLEST
    assert (tile.width() < bigpicture.TILE_W) is small
    assert window.big.columns["sustainable"] * tile.width() <= window.big.width()
    assert window.big.minimumSizeHint().width() <= 640 or window.big.minimumWidth() <= 640


def test_each_category_keeps_its_own_columns(made):
    window, _ = made()
    big = window.big
    big.setParent(None)
    big.show()
    big.resize(1900, 1000)
    QApplication.processEvents()
    QApplication.processEvents()
    wide = big.columns["sustainable"]
    big.bar.setCurrentIndex(1)
    big.resize(900, 1000)
    QApplication.processEvents()
    QApplication.processEvents()
    big.bar.setCurrentIndex(0)                          # it was laid out for 1900 px; now the window is narrower
    assert big.columns["sustainable"] < wide
