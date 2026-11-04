# SPDX-License-Identifier: GPL-3.0-or-later
"""The Demo Recorder's window: OBS, the release and the app, the recording with the global shortcut. Ported from the
Media Tool's tests on 02-11-2026; the pills (the tours, the icons) went to Nexus Dashboard."""

from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage

from demo_recorder import APP_NAME, LOGO_PATH, main_window
from demo_recorder.workflow import WorkflowError


def no_release(monkeypatch, tmp_path):
    """No OBS, nothing in Downloads and no suite in the checkout: the window starts empty."""
    monkeypatch.setattr(main_window, "obs_install_command", lambda: None)
    monkeypatch.setattr(main_window, "find_portal_release", lambda: None)
    monkeypatch.setattr(main_window, "downloads_dir", lambda: tmp_path / "Downloads")
    monkeypatch.setattr(main_window, "SUITE_IN_CHECKOUT", tmp_path / "no-suite")


def test_the_icons_are_nexus_at_512_and_128_px():
    images = Path(main_window.__file__).resolve().parents[1] / "images"
    assert LOGO_PATH == images / "nexus-demo-recorder.webp"
    assert QImage(str(images / "nexus-demo-recorder.webp")).size().width() == 512
    assert QImage(str(images / "nexus-demo-recorder-128.png")).size().width() == 128


def test_window_starts_with_steps_and_no_unvalidated_release(qapp, monkeypatch, tmp_path):
    no_release(monkeypatch, tmp_path)

    window = main_window.MainWindow()

    assert window.windowTitle() == APP_NAME
    assert window.start_button.text() == "Start recording and install portal"
    assert not window.start_button.isEnabled()
    assert window.app_choice.count() == 0
    assert "No extracted portal release found" in window.release_status.text()
    window.close()


def test_without_a_release_in_downloads_the_suite_in_the_checkout_is_used(qapp, monkeypatch, tmp_path):
    """The real checkout's bc250-bazzite/: its portal/install.sh and portal/apps.toml, the optional apps of it."""
    monkeypatch.setattr(main_window, "obs_install_command", lambda: None)
    monkeypatch.setattr(main_window, "find_portal_release", lambda: None)
    monkeypatch.setattr(main_window, "downloads_dir", lambda: tmp_path / "Downloads")
    monkeypatch.setattr(main_window, "PORTAL_LAUNCHER", tmp_path / "not-installed")

    window = main_window.MainWindow()

    assert window.release_dir == main_window.SUITE_IN_CHECKOUT == main_window.CHECKOUT / "bc250-bazzite"
    assert "using the suite in this checkout" in window.release_status.text()
    assert window.app_choice.count() > 5 and window._selected_app().key == "overlay"
    window.close()


def test_release_selection_prefers_system_overlay(qapp, monkeypatch, tmp_path):
    (tmp_path / "install.sh").touch()
    (tmp_path / "apps.toml").write_text(
        '[apps.governor]\nname = "Governor"\ndetect = ["~/governor"]\nlaunch = [["Open", "~/governor"]]\n'
        '[apps.overlay]\nname = "Overlay"\ndetect = ["~/overlay"]\nlaunch = [["Open", "~/overlay"]]\n',
        encoding="utf-8",
    )
    no_release(monkeypatch, tmp_path)
    monkeypatch.setattr(main_window.QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    monkeypatch.setattr(main_window, "PORTAL_LAUNCHER", tmp_path / "not-installed")
    monkeypatch.setattr(main_window, "is_installed", lambda _app: False)
    window = main_window.MainWindow()

    window._choose_release()

    selected = window._selected_app()
    assert selected is not None
    assert selected.key == "overlay"
    window.close()


def test_window_automatically_loads_release_found_in_downloads(qapp, monkeypatch, tmp_path):
    (tmp_path / "install.sh").touch()
    (tmp_path / "apps.toml").write_text(
        '[apps.overlay]\nname = "Overlay"\ndetect = ["~/overlay"]\nlaunch = [["Open", "~/overlay"]]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(main_window, "obs_install_command", lambda: None)
    monkeypatch.setattr(main_window, "find_portal_release", lambda: tmp_path)
    monkeypatch.setattr(main_window, "downloads_dir", lambda: tmp_path)
    window = main_window.MainWindow()

    selected = window._selected_app()
    assert window.release_dir == tmp_path
    assert selected is not None
    assert selected.key == "overlay"
    assert "Found the extracted portal release automatically" in window.release_status.text()
    window.close()


def test_choose_a_folder_inside_a_suite_loads_the_suite(qapp, monkeypatch, tmp_path):
    (tmp_path / "install.sh").touch()
    portal = tmp_path / "portal"
    portal.mkdir()
    (portal / "apps.toml").write_text(
        '[apps.overlay]\nname = "Overlay"\ndetect = ["~/overlay"]\nlaunch = [["Open", "~/overlay"]]\n',
        encoding="utf-8",
    )
    app_folder = tmp_path / "apps" / "fan"
    (app_folder / "fan_control").mkdir(parents=True)
    no_release(monkeypatch, tmp_path)
    monkeypatch.setattr(main_window.QFileDialog, "getExistingDirectory", lambda *args: str(app_folder))
    window = main_window.MainWindow()

    window._choose_release()

    assert window.release_dir == app_folder
    assert window._selected_app() is not None
    assert window._selected_app().key == "overlay"
    assert str(app_folder) in window.release_status.text()
    window.close()


def test_test_connection_shows_popup_if_obs_is_not_running(qapp, monkeypatch, tmp_path):
    warnings = []
    no_release(monkeypatch, tmp_path)
    monkeypatch.setattr(
        main_window, "connect_obs",
        lambda *_args: (_ for _ in ()).throw(WorkflowError("Warning! OBS is not running, start OBS first.")),
    )
    monkeypatch.setattr(main_window.QMessageBox, "warning", lambda *args: warnings.append(args))
    window = main_window.MainWindow()

    assert not window._check_obs()

    assert len(warnings) == 1
    assert warnings[0][1] == "OBS connection failed"
    assert warnings[0][2] == "Warning! OBS is not running, start OBS first."
    assert window.client is None
    window.close()


def test_test_connection_sets_and_reports_recordings_folder(qapp, monkeypatch, tmp_path):
    client = object()
    recordings_path = tmp_path / "Videos" / "demos"
    no_release(monkeypatch, tmp_path)
    monkeypatch.setattr(main_window, "connect_obs", lambda *_args: (client, "test"))
    monkeypatch.setattr(main_window, "set_recording_directory", lambda _client: recordings_path)
    window = main_window.MainWindow()

    assert window._check_obs()

    assert window.client is client
    assert str(recordings_path) in window.obs_status.text()
    window.close()


def test_recent_recordings_uses_the_recordings_folder(qapp, monkeypatch, tmp_path):
    recordings_path = tmp_path / "Videos" / "demos"
    folders = []
    no_release(monkeypatch, tmp_path)
    monkeypatch.setattr(main_window, "recordings_directory", lambda: recordings_path)
    monkeypatch.setattr(main_window, "recent_recordings", lambda folder: folders.append(folder) or ())
    monkeypatch.setattr(main_window.QDialog, "exec", lambda _dialog: 0)
    window = main_window.MainWindow()
    window.client = object()
    assert window.recent_recordings_button.text() == "Recent recordings…"

    window._show_recent_recordings()

    assert folders == [recordings_path]
    window.close()


def test_open_recording_starts_inline_player(qapp, monkeypatch, tmp_path):
    video = tmp_path / "demo.mkv"
    video.touch()
    players = []
    executed = []

    class Signal:
        def connect(self, callback):
            self.callback = callback

        def emit(self, *args):
            self.callback(*args)

    class FakeAudioOutput:
        def __init__(self, _parent):
            pass

    class FakeMediaPlayer:
        PlaybackState = main_window.QMediaPlayer.PlaybackState

        def __init__(self, _parent):
            self.errorOccurred = Signal()
            self.positionChanged = Signal()
            self.durationChanged = Signal()
            self.playbackStateChanged = Signal()
            self._state = self.PlaybackState.StoppedState
            players.append(self)

        def setAudioOutput(self, output):
            self.audio_output = output

        def setVideoOutput(self, output):
            self.video_output = output

        def setSource(self, source):
            self.source = source

        def play(self):
            self._state = self.PlaybackState.PlayingState
            self.playbackStateChanged.emit(self._state)

        def pause(self):
            self._state = self.PlaybackState.PausedState
            self.playbackStateChanged.emit(self._state)

        def playbackState(self):
            return self._state

        def duration(self):
            return 0

        def position(self):
            return 0

        def setPosition(self, _position):
            self.position_ms = _position

    no_release(monkeypatch, tmp_path)
    monkeypatch.setattr(main_window, "QAudioOutput", FakeAudioOutput)
    monkeypatch.setattr(main_window, "QMediaPlayer", FakeMediaPlayer)
    monkeypatch.setattr(main_window.QDialog, "exec", lambda dialog: executed.append(dialog) or 0)
    window = main_window.MainWindow()

    assert window._open_recording(video)
    assert len(players) == 1
    assert Path(players[0].source.toLocalFile()) == video
    assert players[0].audio_output is not None
    assert isinstance(players[0].video_output, main_window.QVideoWidget)
    assert players[0].playbackState() == FakeMediaPlayer.PlaybackState.PlayingState
    assert len(executed) == 1
    play_button = executed[0].findChild(main_window.QPushButton)
    position_slider = executed[0].findChild(main_window.QSlider)
    assert play_button.text() == "Pause"
    play_button.click()
    assert players[0].playbackState() == FakeMediaPlayer.PlaybackState.PausedState
    assert play_button.text() == "Play"
    position_slider.sliderMoved.emit(1234)
    assert players[0].position_ms == 1234
    window.close()


def test_start_hides_window_and_global_shortcut_stops_recording(qapp, monkeypatch, tmp_path):
    shortcut_registrations = []

    class FakeShortcutManager(QObject):
        registered = pyqtSignal(str)
        activated = pyqtSignal()
        failed = pyqtSignal(str)

        def __init__(self, _parent):
            super().__init__()

        def register(self):
            shortcut_registrations.append(True)

        def stop(self):
            pass

    release = tmp_path / "release"
    release.mkdir()
    (release / "install.sh").touch()
    (release / "apps.toml").write_text(
        '[apps.overlay]\nname = "Overlay"\ndetect = ["~/overlay"]\nlaunch = [["Open", "~/overlay"]]\n',
        encoding="utf-8",
    )
    launcher = tmp_path / "portal"
    marker = tmp_path / "installer-exit"
    started, stopped, opened, errors = [], [], [], []
    client = object()
    no_release(monkeypatch, tmp_path)
    monkeypatch.setattr(main_window, "GlobalShortcutManager", FakeShortcutManager)
    monkeypatch.setattr(main_window, "connect_obs", lambda *_args: (client, "test"))
    monkeypatch.setattr(main_window, "set_recording_directory", lambda _client: tmp_path)
    monkeypatch.setattr(main_window, "PORTAL_LAUNCHER", launcher)
    monkeypatch.setattr(main_window, "recording_active", lambda _client: False)
    monkeypatch.setattr(main_window, "start_recording", lambda client: started.append(client))
    monkeypatch.setattr(main_window, "stop_recording", lambda client: stopped.append(client))
    monkeypatch.setattr(main_window, "launch_installer", lambda _installer: marker)
    monkeypatch.setattr(main_window, "is_installed", lambda _app: False)
    monkeypatch.setattr(main_window.QMessageBox, "critical", lambda *args: errors.append(args))
    monkeypatch.setattr(
        main_window.QMessageBox, "question",
        lambda *_args: (_ for _ in ()).throw(AssertionError("Shortcut stop must not prompt before stopping")),
    )
    monkeypatch.setattr(main_window.subprocess, "Popen", lambda argv, **_kwargs: opened.append(argv))
    window = main_window.MainWindow()
    window.release_dir = release
    window.apps = (main_window.DemoApp("overlay", "Overlay", (tmp_path / "overlay",)),)
    window.app_choice.addItem("Overlay", "overlay")
    window.start_button.setEnabled(True)
    window.show()

    window._start_demo()

    assert shortcut_registrations == [True]
    assert started == []
    assert window.isVisible()

    window.shortcut_manager.registered.emit("Ctrl+Alt+End")

    assert started == [client]
    assert window.recording
    assert not window.isVisible()
    assert window.stop_shortcut == "Ctrl+Alt+End"
    assert "Ctrl+Alt+End" in window.instructions.text()
    assert errors == []

    marker.write_text("0", encoding="ascii")
    launcher.touch()
    window.install_exit_file = marker
    window._poll_installer()
    assert opened == [[str(launcher)]]
    assert not window.isVisible()

    window.shortcut_manager.activated.emit()

    assert stopped == [client]
    assert not window.recording
    assert window.isVisible()
    window.close()


def test_a_second_launch_opens_no_window(qapp, monkeypatch):
    """A double-click on the Desktop icon starts the app twice: the second launch hands over to the first."""
    import demo_recorder.__main__ as entry
    asked = []
    monkeypatch.setattr(entry, "create_app", lambda *a, **k: qapp)
    monkeypatch.setattr(entry.instance, "already_running", lambda app_id: asked.append(app_id) or True)
    monkeypatch.setattr("sys.argv", ["demo_recorder"])
    assert entry.main() == 0 and asked == [entry.APP_ID]


def test_on_windows_no_release_in_downloads_says_where_to_get_one(qapp, on_windows, monkeypatch, tmp_path):
    """The Windows Portable Suite's portal installs from a release only: no fallback to the checkout."""
    monkeypatch.setattr(main_window, "obs_install_command", lambda: None)
    monkeypatch.setattr(main_window, "find_portal_release", lambda: None)
    monkeypatch.setattr(main_window, "downloads_dir", lambda: tmp_path / "Downloads")

    window = main_window.MainWindow()

    assert window.release_dir is None
    assert "wp-portal-v<x.y.z>.zip" in window.release_status.text()
    assert "PowerShell window" in window.instructions.text()
    window.close()


def test_on_windows_obs_starts_from_its_own_folder(qapp, on_windows, monkeypatch, tmp_path):
    obs = tmp_path / "obs-studio" / "bin" / "64bit" / "obs64.exe"
    started = []
    no_release(monkeypatch, tmp_path)
    window = main_window.MainWindow()
    monkeypatch.setattr(main_window, "obs_install_command", lambda: [str(obs)])
    monkeypatch.setattr(main_window.subprocess, "Popen", lambda argv, **kwargs: started.append((argv, kwargs)))

    window._open_obs()

    assert started == [([str(obs)], {"stdin": main_window.subprocess.DEVNULL, "start_new_session": True,
                                     "cwd": obs.parent})]
    window.close()
