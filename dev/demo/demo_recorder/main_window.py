# SPDX-License-Identifier: GPL-3.0-or-later
"""The Demo Recorder's window: OBS, the portal release and the app to show, and the recording. The release is an
extracted portal release in Downloads, found by itself, or the suite in the checkout the app lives in; while the
recording runs the window hides, and the global shortcut (the desktop portal's, on Windows a hot key of Windows')
stops it and brings it back."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from bc250_core.widgets import AppHeader, InfoButton

from . import APP_NAME, CHECKOUT, LOGO_PATH, __version__
from .global_shortcut import GlobalShortcutManager
from .workflow import (
    PORTAL_LAUNCHER,
    WINDOWS,
    DemoApp,
    WorkflowError,
    connect_obs,
    downloads_dir,
    find_portal_release,
    is_installed,
    launch_installer,
    obs_install_command,
    recording_active,
    recordings_directory,
    recent_recordings,
    set_recording_directory,
    start_recording,
    stop_recording,
    validate_release,
)

RELEASES_URL = "https://github.com/RobertoTorino/nexus/releases"
SUITE_IN_CHECKOUT = CHECKOUT / "bc250-bazzite"           # the suite whose portal install the demo records
ABOUT = ("The demo is a real portal installation recorded with OBS: a portal release extracted in Downloads (found by "
         "itself), or the BC250 Bazzite Suite in this checkout, installed in a terminal while OBS records the screen, "
         "then the portal opened and one optional app installed and shown.\n\n"
         "OBS needs a screen-capture source and its WebSocket server (Setup instructions). The portal and the "
         "chosen app must not be installed yet: the demo is a fresh install. While it records, this window hides; "
         "the global shortcut stops the recording and brings it back. The recordings are in ~/Videos/demos.")
INSTRUCTIONS = ("The installer runs in a terminal, for its output and its password prompts. This window then hides "
                "and opens the portal; the global shortcut shown stops the recording and brings it back.")
# On Windows: the Windows Portable Suite, from a portal release only, installed in a PowerShell window
WINDOWS_ABOUT = ("The demo is a real portal installation recorded with OBS: a Windows Portable Suite portal release "
                 "extracted in Downloads (found by itself), installed in a PowerShell window while OBS records the "
                 "screen, then the portal opened and one optional app installed and shown.\n\n"
                 "OBS needs a Display Capture source and its WebSocket server (Setup instructions). The portal and "
                 "the chosen app must not be installed yet: the demo is a fresh install. While it records, this "
                 "window hides; Ctrl+Alt+F12 stops the recording and brings it back. The recordings are in "
                 "Videos\\demos.")
WINDOWS_INSTRUCTIONS = ("The installer runs in a PowerShell window, for its output. This window then hides and "
                        "opens the portal; the global shortcut shown stops the recording and brings it back.")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(620, 520)
        self.client = None
        self.recording = False
        self.install_exit_file: Path | None = None
        self.release_dir: Path | None = None
        self.apps: tuple[DemoApp, ...] = ()
        self._pending_start: tuple[DemoApp, Path] | None = None
        self.stop_shortcut = "Ctrl+Alt+F12"
        self._build_ui()
        self.shortcut_manager = GlobalShortcutManager(self)
        self.shortcut_manager.registered.connect(self._start_demo_after_shortcut)
        self.shortcut_manager.activated.connect(self._stop_from_shortcut)
        self.shortcut_manager.failed.connect(self._shortcut_failed)
        self.poller = QTimer(self)
        self.poller.setInterval(500)
        self.poller.timeout.connect(self._poll_installer)
        self._refresh_obs_status()
        self._find_release_automatically()

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        header.add_action(InfoButton(WINDOWS_ABOUT if WINDOWS else ABOUT, "What this app does"))
        header.add_second(QLabel("A portal installation, recorded with OBS."))
        header.second_row.addStretch(1)
        layout.addLayout(header)

        obs_box = QGroupBox("1. OBS setup")
        obs_layout = QVBoxLayout(obs_box)
        self.obs_status = QLabel()
        self.obs_status.setWordWrap(True)
        obs_layout.addWidget(self.obs_status)
        obs_form = QFormLayout()
        self.host = QLineEdit("127.0.0.1")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(4455)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        obs_form.addRow("Host", self.host)
        obs_form.addRow("WebSocket port", self.port)
        obs_form.addRow("Password (if enabled)", self.password)
        obs_layout.addLayout(obs_form)
        obs_buttons = QHBoxLayout()
        self.open_obs_button = QPushButton("Open OBS")
        self.open_obs_button.clicked.connect(self._open_obs)
        self.check_obs_button = QPushButton("Test connection")
        self.check_obs_button.clicked.connect(self._check_obs)
        self.obs_help_button = QPushButton("Setup instructions")
        self.obs_help_button.clicked.connect(self._show_obs_help)
        for button in (self.open_obs_button, self.check_obs_button, self.obs_help_button):
            obs_buttons.addWidget(button)
        obs_layout.addLayout(obs_buttons)
        layout.addWidget(obs_box)

        release_box = QGroupBox("2. Portal release and app")
        release_layout = QVBoxLayout(release_box)
        choose_row = QHBoxLayout()
        self.release_path = QLineEdit()
        self.release_path.setReadOnly(True)
        self.release_path.setPlaceholderText("An extracted portal release" if WINDOWS else
                                             "An extracted portal release, or the suite's folder in a checkout")
        choose_row.addWidget(self.release_path, 1)
        choose_button = QPushButton("Choose folder…")
        choose_button.clicked.connect(self._choose_release)
        choose_row.addWidget(choose_button)
        find_button = QPushButton("Find in Downloads")
        find_button.clicked.connect(self._find_release_automatically)
        choose_row.addWidget(find_button)
        release_layout.addLayout(choose_row)
        self.release_link = QPushButton("Open the releases page")
        self.release_link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(RELEASES_URL)))
        release_layout.addWidget(self.release_link)
        self.release_status = QLabel()
        self.release_status.setWordWrap(True)
        release_layout.addWidget(self.release_status)
        app_row = QHBoxLayout()
        app_row.addWidget(QLabel("Optional app to show:"))
        self.app_choice = QComboBox()
        app_row.addWidget(self.app_choice, 1)
        release_layout.addLayout(app_row)
        self.app_status = QLabel("Choose an extracted release to load its optional apps.")
        self.app_status.setWordWrap(True)
        release_layout.addWidget(self.app_status)
        self.app_choice.currentIndexChanged.connect(self._update_app_status)
        layout.addWidget(release_box)

        action_box = QGroupBox("3. Record")
        action_layout = QVBoxLayout(action_box)
        self.instructions = QLabel(WINDOWS_INSTRUCTIONS if WINDOWS else INSTRUCTIONS)
        self.instructions.setWordWrap(True)
        action_layout.addWidget(self.instructions)
        self.start_button = QPushButton("Start recording and install portal")
        self.start_button.clicked.connect(self._start_demo)
        self.start_button.setEnabled(False)
        action_layout.addWidget(self.start_button)
        self.open_portal_button = QPushButton("Open portal")
        self.open_portal_button.clicked.connect(self._open_portal)
        self.open_portal_button.setEnabled(False)
        self.stop_button = QPushButton("Stop recording")
        self.stop_button.clicked.connect(lambda: self._stop_demo())
        self.stop_button.setEnabled(False)
        self.recent_recordings_button = QPushButton("Recent recordings…")
        self.recent_recordings_button.clicked.connect(self._show_recent_recordings)
        self.recent_recordings_button.setEnabled(False)
        recording_buttons = QHBoxLayout()
        recording_buttons.addWidget(self.open_portal_button)
        recording_buttons.addWidget(self.stop_button)
        recording_buttons.addWidget(self.recent_recordings_button)
        action_layout.addLayout(recording_buttons)
        layout.addWidget(action_box)

        layout.addStretch(1)
        self.setCentralWidget(central)

    def _refresh_obs_status(self) -> None:
        command = obs_install_command()
        if command is None:
            self.obs_status.setText("OBS was not found. Install or launch OBS, then configure a capture scene.")
            self.open_obs_button.setEnabled(False)
            return
        self.obs_status.setText(f"OBS found: {command[0]}. A screen-capture source and WebSocket setup are still needed.")

    def _open_obs(self) -> None:
        command = obs_install_command()
        if command is None:
            QMessageBox.warning(self, "OBS not found", "Install OBS Studio, then use this button to open it.")
            return
        try:
            # on Windows OBS starts only from its own folder (it finds its data from there)
            subprocess.Popen(command, stdin=subprocess.DEVNULL, start_new_session=True,
                             cwd=Path(command[0]).parent if WINDOWS else None)
        except OSError as exc:
            QMessageBox.critical(self, "Could not open OBS", str(exc))

    def _show_obs_help(self) -> None:
        capture = ("2. Choose Display Capture and the screen the portal shows on.\n" if WINDOWS else
                   "2. On Wayland, choose Screen Capture (PipeWire) and approve the sharing prompt.\n")
        QMessageBox.information(
            self,
            "Prepare OBS",
            "In OBS:\n"
            "1. Create a scene and add a screen-capture source.\n"
            f"{capture}"
            "3. Open Tools → WebSocket Server Settings and enable the server.\n"
            "4. Note the server port (usually 4455) and password, then test the connection here.\n\n"
            f"{APP_NAME} does not change OBS settings or select a capture source for you.",
        )

    def _check_obs(self) -> bool:
        try:
            self.client, version = connect_obs(self.host.text().strip(), self.port.value(), self.password.text())
            recordings_path = set_recording_directory(self.client)
        except WorkflowError as exc:
            QMessageBox.warning(self, "OBS connection failed", str(exc))
            self.client = None
            self.recent_recordings_button.setEnabled(False)
            self._update_start_button()
            return False
        self.obs_status.setText(
            f"Connected to OBS {version}. Recordings will be saved in {recordings_path}. "
            "Check the preview shows your desktop before recording."
        )
        self.recent_recordings_button.setEnabled(True)
        self._update_start_button()
        return True

    def _show_recent_recordings(self) -> None:
        if self.client is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Recent recordings")
        dialog.resize(560, 380)
        layout = QVBoxLayout(dialog)
        status = QLabel()
        status.setWordWrap(True)
        layout.addWidget(status)
        recordings_list = QListWidget()
        layout.addWidget(recordings_list, 1)
        buttons = QHBoxLayout()
        refresh_button = QPushButton("Refresh")
        open_button = QPushButton("Play selected video")
        open_button.setEnabled(False)
        buttons.addWidget(refresh_button)
        buttons.addWidget(open_button)
        layout.addLayout(buttons)

        def refresh() -> None:
            try:
                directory = recordings_directory()
                recordings = recent_recordings(directory)
            except WorkflowError as exc:
                recordings_list.clear()
                status.setText(str(exc))
                open_button.setEnabled(False)
                return
            recordings_list.clear()
            for recording in recordings:
                item = QListWidgetItem(recording.name)
                item.setData(Qt.ItemDataRole.UserRole, str(recording))
                item.setToolTip(str(recording))
                recordings_list.addItem(item)
            if recordings:
                status.setText(f"Showing {len(recordings)} recent video(s) in {directory}.")
            else:
                status.setText(f"No recordings found in {directory}.")
            open_button.setEnabled(False)

        def open_selected() -> None:
            item = recordings_list.currentItem()
            if item is not None:
                self._open_recording(Path(item.data(Qt.ItemDataRole.UserRole)))

        refresh_button.clicked.connect(refresh)
        open_button.clicked.connect(open_selected)
        recordings_list.currentRowChanged.connect(lambda row: open_button.setEnabled(row >= 0))
        recordings_list.itemDoubleClicked.connect(lambda _item: open_selected())
        refresh()
        dialog.exec()

    def _open_recording(self, recording: Path) -> bool:
        if not recording.is_file():
            QMessageBox.warning(self, "Recording not found", f"Could not find {recording}. Refresh the list.")
            return False
        dialog = QDialog(self)
        dialog.setWindowTitle(recording.name)
        dialog.resize(800, 520)
        layout = QVBoxLayout(dialog)
        video = QVideoWidget(dialog)
        layout.addWidget(video, 1)
        status = QLabel()
        status.setWordWrap(True)
        layout.addWidget(status)
        controls = QHBoxLayout()
        play_button = QPushButton("Pause")
        position_slider = QSlider(Qt.Orientation.Horizontal)
        position_slider.setRange(0, 0)
        time_label = QLabel("00:00 / 00:00")
        controls.addWidget(play_button)
        controls.addWidget(position_slider, 1)
        controls.addWidget(time_label)
        layout.addLayout(controls)

        audio = QAudioOutput(dialog)
        player = QMediaPlayer(dialog)
        player.setAudioOutput(audio)
        player.setVideoOutput(video)
        player.setSource(QUrl.fromLocalFile(str(recording.resolve())))

        def timestamp(milliseconds: int) -> str:
            seconds = max(milliseconds, 0) // 1000
            return f"{seconds // 60:02d}:{seconds % 60:02d}"

        def update_position(milliseconds: int) -> None:
            if not position_slider.isSliderDown():
                position_slider.setValue(milliseconds)
            time_label.setText(f"{timestamp(milliseconds)} / {timestamp(player.duration())}")

        def update_duration(milliseconds: int) -> None:
            position_slider.setRange(0, milliseconds)
            update_position(player.position())

        def update_play_button(state: QMediaPlayer.PlaybackState) -> None:
            play_button.setText("Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play")

        def toggle_playback() -> None:
            if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                player.pause()
            else:
                player.play()

        player.errorOccurred.connect(lambda _error, message: status.setText(message))
        player.positionChanged.connect(update_position)
        player.durationChanged.connect(update_duration)
        player.playbackStateChanged.connect(update_play_button)
        position_slider.sliderMoved.connect(player.setPosition)
        play_button.clicked.connect(toggle_playback)
        player.play()
        dialog.exec()
        return True

    def _choose_release(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose a portal release" if WINDOWS else
                                                    "Choose a portal release or a suite's folder in a checkout")
        if not selected:
            return
        try:
            self._set_release(Path(selected))
        except WorkflowError as exc:
            QMessageBox.warning(self, "Invalid portal release", str(exc))
            return

    def _find_release_automatically(self) -> None:
        """The newest extracted portal release in Downloads; without one, the suite in this checkout (Linux)."""
        release = find_portal_release()
        if release is None and WINDOWS:
            self.release_status.setText(
                f"No extracted portal release found in {downloads_dir()}. Download a Windows Portable Suite portal "
                "release (wp-portal-v<x.y.z>.zip), extract it there, then choose Find in Downloads."
            )
            return
        if release is None:
            try:
                self._set_release(SUITE_IN_CHECKOUT)
            except WorkflowError:
                self.release_status.setText(
                    f"No extracted portal release found in {downloads_dir()}. Download a portal release, extract it "
                    "there, then choose Find in Downloads."
                )
                return
            self.release_status.setText(
                f"No extracted portal release in {downloads_dir()}: using the suite in this checkout, "
                f"{SUITE_IN_CHECKOUT} (its portal/install.sh installs the released apps from the checkout's source)."
            )
            return
        try:
            self._set_release(release)
        except WorkflowError as exc:
            self.release_status.setText(f"Found {release}, but could not load it: {exc}")
            return
        self.release_status.setText(f"Found the extracted portal release automatically: {release}")

    def _set_release(self, folder: Path) -> None:
        _installer, apps = validate_release(folder)
        self.release_dir = folder.expanduser().resolve()
        self.apps = apps
        self.release_path.setText(str(self.release_dir))
        self.release_status.setText(f"Using portal release: {self.release_dir}")
        self.app_choice.clear()
        for app in apps:
            self.app_choice.addItem(app.name, app.key)
        preferred = self.app_choice.findData("overlay")
        if preferred >= 0:
            self.app_choice.setCurrentIndex(preferred)
        self._update_app_status()
        self._update_start_button()

    def _selected_app(self) -> DemoApp | None:
        key = self.app_choice.currentData()
        return next((app for app in self.apps if app.key == key), None)

    def _update_app_status(self, _index: int = -1) -> None:
        app = self._selected_app()
        if PORTAL_LAUNCHER.exists() or PORTAL_LAUNCHER.is_symlink():
            self.app_status.setText("The portal is already installed; remove it first to record a fresh install.")
        elif app is None:
            self.app_status.setText("Choose an extracted release to load its optional apps.")
        elif is_installed(app):
            self.app_status.setText(f"{app.name} is already installed; uninstall it to record a fresh install.")
        else:
            self.app_status.setText(f"{app.name} is not installed and is ready for the demo.")
        self._update_start_button()

    def _update_start_button(self) -> None:
        app = self._selected_app()
        fresh = not PORTAL_LAUNCHER.exists() and not PORTAL_LAUNCHER.is_symlink()
        self.start_button.setEnabled(
            self.client is not None and app is not None and self.release_dir is not None and
            not is_installed(app) and fresh and not self.recording and self.install_exit_file is None
        )

    def _start_demo(self) -> None:
        app = self._selected_app()
        if app is None or self.release_dir is None:
            return
        if not self._check_obs():
            return
        try:
            if recording_active(self.client):
                QMessageBox.warning(self, "OBS is already recording", "Stop the current OBS recording first.")
                return
            installer, _apps = validate_release(self.release_dir)
            if is_installed(app):
                raise WorkflowError(f"{app.name} is already installed; uninstall it before recording.")
            if PORTAL_LAUNCHER.exists() or PORTAL_LAUNCHER.is_symlink():
                raise WorkflowError("The portal is already installed. Remove it first for a fresh-install demo.")
            self._pending_start = (app, installer)
            self.start_button.setEnabled(False)
            self.shortcut_manager.register()
        except (WorkflowError, OSError) as exc:
            self._pending_start = None
            self._update_start_button()
            QMessageBox.critical(self, "Could not start demo", str(exc))

    def _start_demo_after_shortcut(self, trigger_description: str) -> None:
        pending = self._pending_start
        if pending is None:
            return
        self._pending_start = None
        _, installer = pending
        self.stop_shortcut = trigger_description
        try:
            start_recording(self.client)
            self.recording = True
            self.recent_recordings_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.start_button.setEnabled(False)
            self.install_exit_file = launch_installer(installer)
            self.instructions.setText(
                f"Recording is active. Finish installing the portal in its terminal. {APP_NAME} will "
                f"open it automatically, then stay hidden until you press {self.stop_shortcut} to stop recording."
            )
            self.poller.start()
            self.hide()
        except (WorkflowError, OSError) as exc:
            try:
                self._stop_recording_after_error()
            except WorkflowError as stop_exc:
                QMessageBox.critical(self, "Could not start demo", f"{exc}\n\n{stop_exc}")
            else:
                QMessageBox.critical(self, "Could not start demo", str(exc))

    def _shortcut_failed(self, message: str) -> None:
        if self._pending_start is not None:
            self._pending_start = None
            self._update_start_button()
            QMessageBox.critical(
                self,
                "Could not enable stop shortcut",
                f"Recording was not started because Ctrl+Alt+F12 could not be registered: {message}",
            )
            return
        if self.recording:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            QMessageBox.critical(self, "Stop shortcut unavailable", message)

    def _stop_from_shortcut(self) -> None:
        if self.recording:
            self._stop_demo(check_app=False)

    def _poll_installer(self) -> None:
        if self.install_exit_file is None or not self.install_exit_file.exists():
            return
        marker = self.install_exit_file
        self.install_exit_file = None
        self.poller.stop()
        try:
            result = int(marker.read_text(encoding="ascii"))
        except (OSError, ValueError) as exc:
            result = -1
            detail = f"The installer status could not be read: {exc}"
        else:
            detail = "The portal installer finished successfully." if result == 0 else \
                f"The portal installer exited with status {result}."
        marker.unlink(missing_ok=True)
        if result:
            self.instructions.setText(detail)
            self.showNormal()
            self.raise_()
            self.activateWindow()
            QMessageBox.warning(self, "Portal installation failed", detail + "\n\nThe recording remains active.")
            self._update_start_button()
            return
        self.instructions.setText(
            f"The portal is installed. Open it, show {'Windows Portable Test' if WINDOWS else 'BC-250 Bazzite Test'}, "
            "install the selected optional app, "
            "then open that app for the peek."
        )
        self.open_portal_button.setEnabled(True)
        self._open_portal()

    def _open_portal(self) -> None:
        if not PORTAL_LAUNCHER.is_file():
            self.showNormal()
            self.raise_()
            self.activateWindow()
            QMessageBox.warning(self, "Portal launcher missing", f"Could not find {PORTAL_LAUNCHER}.")
            self.open_portal_button.setEnabled(False)
            return
        try:
            subprocess.Popen([str(PORTAL_LAUNCHER)], stdin=subprocess.DEVNULL, start_new_session=True)
        except OSError as exc:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            QMessageBox.critical(self, "Could not open portal", str(exc))

    def _stop_demo(self, *, check_app: bool = True) -> None:
        app = self._selected_app()
        if check_app and app is not None and not is_installed(app):
            answer = QMessageBox.question(
                self,
                "App not detected",
                f"{app.name} is not detected as installed. Stop recording anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            self._stop_recording_after_error()
        except WorkflowError as exc:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            QMessageBox.critical(self, "Could not stop recording", str(exc))
            return
        self.instructions.setText("Recording stopped. OBS saved the video to its configured recording location.")
        self.recent_recordings_button.setEnabled(self.client is not None)
        self.open_portal_button.setEnabled(False)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _stop_recording_after_error(self) -> None:
        if self.recording and self.client is not None:
            stop_recording(self.client)
        self.recording = False
        self.stop_button.setEnabled(False)
        self.recent_recordings_button.setEnabled(self.client is not None)
        self._update_start_button()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self.recording:
            answer = QMessageBox.question(
                self,
                "Recording in progress",
                f"Stop the OBS recording before closing {APP_NAME}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            try:
                self._stop_recording_after_error()
            except WorkflowError as exc:
                QMessageBox.critical(self, "Could not stop recording", str(exc))
                event.ignore()
                return
        self.poller.stop()
        if self.install_exit_file is not None:
            self.install_exit_file.unlink(missing_ok=True)
        self.shortcut_manager.stop()
        event.accept()
