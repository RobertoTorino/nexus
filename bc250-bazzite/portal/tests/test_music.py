# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal's background music: the track (the portal's own or the user's), its player, and the window's Music and
Music track pills, with the player replaced by one that plays nothing (conftest's SilentPlayer)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from bc250_portal import MANIFEST, music, state_dir
from bc250_portal import main_window as mw
from bc250_portal.manifest import load
from bc250_portal.sources import Records, Sources


class Output:
    """Stands in for the portal's sounds where only the audio output counts."""

    enabled = True

    def __init__(self, there: bool = True):
        self.there = there

    def available(self) -> bool:
        return self.there

    def play(self, _name: str) -> bool:
        return False

    def stop(self) -> None:
        pass


@pytest.fixture
def make(qapp, home, settings_dir, tmp_path, monkeypatch):
    windows = []

    def window(output: bool = True, active: bool = True):
        state = Qt.ApplicationState.ApplicationActive if active else Qt.ApplicationState.ApplicationInactive
        monkeypatch.setattr(QApplication, "applicationState", staticmethod(lambda: state))
        w = mw.MainWindow(load(MANIFEST), Sources(tmp_path / "work"), Records(tmp_path / "installed.json"),
                          sounds=Output(output))
        windows.append(w)
        return w

    yield window
    for w in windows:
        w.close()


def test_the_portal_ships_its_own_track():
    assert music.BUILT_IN.is_file() and music.problem(music.BUILT_IN) == ""
    assert music.BUILT_IN.read_bytes()[:4] == b"OggS"


def test_a_track_of_your_own_is_a_copy_in_the_state_folder(home, tmp_path):
    """The user's track is copied into the portal's state folder, in place of the one before; without one the portal
    plays its own. A file that is no sound file is refused with the reason and the rules."""
    assert music.current() is None and music.track() == music.BUILT_IN
    assert music.track(built_in=tmp_path / "gone.ogg") is None
    own = tmp_path / "My Song.MP3"
    own.write_bytes(b"one")
    assert music.choose(own) == state_dir() / "music.mp3" and state_dir().is_relative_to(home)
    assert music.current() == state_dir() / "music.mp3" == music.track()
    other = tmp_path / "other.ogg"
    other.write_bytes(b"two")
    music.choose(other)
    assert [p.name for p in state_dir().glob("music.*")] == ["music.ogg"]
    assert not list(state_dir().glob(".music-new*"))
    notes = tmp_path / "notes.txt"
    notes.write_text("no sound")
    with pytest.raises(ValueError, match="not an Ogg") as refused:
        music.choose(notes)
    assert music.RULES in str(refused.value)
    assert "was not found" in music.problem(tmp_path / "missing.ogg")
    assert music.current() == state_dir() / "music.ogg"                 # a refused file changes nothing
    music.remove()
    assert music.current() is None and music.track() == music.BUILT_IN


def test_the_player_stays_silent_without_a_track(silent_music, tmp_path):
    """The real player: no track, or one that is gone, makes no player and no error; pause and stop before play too."""
    player = silent_music()
    player.pause()
    player.stop()
    player.play()
    assert player.player is None and not player.playing
    player.set_track(tmp_path / "gone.ogg")
    player.play()
    assert player.player is None and player.wanted
    player.pause()
    assert not player.wanted


def test_the_music_plays_while_the_portal_is_in_front(make):
    """The music starts once the intro is over, waits while another window has the focus (a game, an app), and plays
    on when the portal is back."""
    window = make()
    player = window.music
    assert player.path == music.BUILT_IN and not player.playing            # not shown yet
    window.show()
    window.start_up()
    assert not player.playing                                              # the intro plays
    window.intro.skip()
    assert player.playing
    QApplication.applicationState = staticmethod(lambda: Qt.ApplicationState.ApplicationInactive)
    window._focus_changed(Qt.ApplicationState.ApplicationInactive)
    assert not player.playing and player.calls[-1] == "pause"              # paused: it plays on from there
    QApplication.applicationState = staticmethod(lambda: Qt.ApplicationState.ApplicationActive)
    window._focus_changed(Qt.ApplicationState.ApplicationActive)
    assert player.playing
    window.close()
    assert player.calls[-1] == "stop"


def test_the_music_pill_is_apart_from_the_sound_pill(make):
    """Music has a switch of its own (owner, 14-11-2026): off, the music stops and Sound stays as it is, and the
    other way round; the choice is kept."""
    window = make()
    window.show()
    window._sync_music()
    assert window.music.playing and window.music_box.isChecked() and window.sound_box.isChecked()
    window.music_box.clicked.emit()
    assert not window.music.playing and window.music_box.value.text() == "No"
    assert window.sounds.enabled and window.sound_box.isChecked()          # Sound is as it was
    assert window.settings.value(mw.MUSIC_KEY, type=bool) is False
    assert window.settings.value(mw.SOUND_KEY, True, type=bool) is True
    window.music_box.clicked.emit()
    assert window.music.playing and window.music_box.value.text() == "Yes"
    window.sound_box.clicked.emit()                                        # Sound off: the music plays on
    assert not window.sounds.enabled and window.music.playing and window.music_box.isChecked()
    window._set_music(False)
    again = make()
    again.show()
    again._sync_music()
    assert not again.music_on and not again.music.playing and again.music_box.value.text() == "No"


def test_no_music_without_an_audio_output(make):
    window = make(output=False)
    window.show()
    window._sync_music()
    assert not window.music.playing
    assert not window.music_box.isEnabled() and window.music_box.value.text() == "No"
    assert window.music_box.toolTip() == mw.audio.NO_OUTPUT


def test_the_music_waits_for_the_portal_tour(make):
    class Tour:
        def isVisible(self):  # noqa: N802 (as the dialog)
            return True

    window = make()
    window.show()
    window._sync_music()
    assert window.music.playing
    window.tour = Tour()
    window._sync_music()
    assert not window.music.playing
    window.tour = None
    window._sync_music()
    assert window.music.playing


def test_the_music_track_pill(make, home, tmp_path, monkeypatch):
    """The Music track pill: Built-in until the user chooses a track of their own (Custom), which plays at once;
    The portal's track brings the portal's own back. A file that cannot be a track is refused with a warning."""
    window = make()
    window.show()
    window._sync_music()

    def menu():
        return {a.text(): (a.isChecked(), a.isEnabled()) for a in window.track_menu().actions()}

    assert window.track_pill.value.text() == "Built-in" and music.RULES in window.track_pill.toolTip()
    assert menu() == {"Choose a track…": (False, True), "The portal's track": (True, False)}
    own = tmp_path / "mine.ogg"
    own.write_bytes(b"OggS")
    monkeypatch.setattr(mw.QFileDialog, "getOpenFileName", lambda *a, **k: (str(own), ""))
    window.choose_track()
    assert music.current() == state_dir() / "music.ogg" and window.music.path == music.current()
    assert window.track_pill.value.text() == "Custom" and window.music.playing
    assert menu()["The portal's track"] == (False, True)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text, *a: warned.append(text))
    window.apply_track(tmp_path / "notes.txt")
    assert len(warned) == 1 and "not an Ogg" in warned[0] and window.track_pill.value.text() == "Custom"
    window.remove_track()
    assert music.current() is None and window.music.path == music.BUILT_IN
    assert window.track_pill.value.text() == "Built-in" and window.music.playing
    monkeypatch.setattr(mw.QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    window.choose_track()                                                  # canceled: nothing changes
    assert window.track_pill.value.text() == "Built-in"
