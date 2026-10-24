# SPDX-License-Identifier: GPL-3.0-or-later
"""The Media Tool's setup and recording window."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon, QPixmap
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

from . import APP_NAME, __version__
from .global_shortcut import GlobalShortcutManager
from .icons import IconsDialog, find_checkout
from .tours import AppsTourDialog, Pill, PortalTourDialog
from .workflow import (
    PORTAL_LAUNCHER,
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
IMAGE_DIR = Path(__file__).resolve().parent.parent / "images"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Media Tool")
        self.setWindowIcon(QIcon(str(IMAGE_DIR / "media-tool.webp")))
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
        # The logo spans the title and the line below it, like every app of the suite.
        header = QHBoxLayout()
        header.setSpacing(14)
        logo = QLabel()
        logo.setObjectName("app_logo")
        logo.setPixmap(QPixmap(str(IMAGE_DIR / "media-tool-128.png")).scaled(
            96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        header.addWidget(logo)
        header_right = QVBoxLayout()
        header_right.setSpacing(6)
        title = QLabel(f"{APP_NAME}  <span style='color:#9aa0a6; font-size:14px;'>v{__version__}</span>")
        title.setStyleSheet("font-size:24px; font-weight:800;")
        header_right.addWidget(title)
        # The second line: the tools beside the demo recording, as pills.
        pills = QHBoxLayout()
        pills.setSpacing(8)
        self.portal_tour_pill = Pill("Portal video tour", "Record the portal's tour",
                                     "Record the portal's video tour from a suite checkout: about two minutes, "
                                     "with music, and the copy on the wiki's Portal Tour page if you like.")
        self.portal_tour_pill.clicked.connect(self._show_portal_tour)
        self.apps_tour_pill = Pill("Apps video tour", "Record the apps' tours",
                                   "Record a short video tour of each app you tick, from a suite checkout: about "
                                   "40 seconds each, with music.")
        self.apps_tour_pill.clicked.connect(self._show_apps_tour)
        self.icons_pill = Pill("Convert icons", "Make a category's icons",
                               "Make a category's icons from new images in a suite checkout.")
        self.icons_pill.clicked.connect(self._show_icons)
        for pill in (self.portal_tour_pill, self.apps_tour_pill, self.icons_pill):
            pills.addWidget(pill)
        pills.addStretch(1)
        header_right.addLayout(pills)
        header.addLayout(header_right, 1)
        layout.addLayout(header)
        intro = QLabel("Prepare OBS, install a portal release, and record a real optional-app install.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        obs_box = QGroupBox("1. OBS setup")
        obs_layout = QVBoxLayout(obs_box)
        self.obs_status = QLabel()
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
        self.release_path.setPlaceholderText(
            "Choose an extracted portal release, suite checkout, or apps/mtool folder"
        )
        choose_row.addWidget(self.release_path, 1)
        choose_button = QPushButton("Choose folder…")
        choose_button.clicked.connect(self._choose_release)
        choose_row.addWidget(choose_button)
        find_button = QPushButton("Find in Downloads")
        find_button.clicked.connect(self._find_release_automatically)
        choose_row.addWidget(find_button)
        release_layout.addLayout(choose_row)
        self.release_link = QPushButton("Open suite releases page")
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
        release_layout.addWidget(self.app_status)
        self.app_choice.currentIndexChanged.connect(self._update_app_status)
        layout.addWidget(release_box)

        action_box = QGroupBox("3. Record")
        action_layout = QVBoxLayout(action_box)
        self.instructions = QLabel(
            "The installer runs in a terminal so you can see its output and answer password prompts. "
            "Media Tool then hides and opens the portal automatically. Use the displayed global shortcut to stop "
            "recording and bring this window back."
        )
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
            subprocess.Popen(command, stdin=subprocess.DEVNULL, start_new_session=True)
        except OSError as exc:
            QMessageBox.critical(self, "Could not open OBS", str(exc))

    def _show_obs_help(self) -> None:
        QMessageBox.information(
            self,
            "Prepare OBS",
            "In OBS:\n"
            "1. Create a scene and add a screen-capture source.\n"
            "2. On Wayland, choose Screen Capture (PipeWire) and approve the sharing prompt.\n"
            "3. Open Tools → WebSocket Server Settings and enable the server.\n"
            "4. Note the server port (usually 4455) and password, then test the connection here.\n\n"
            "Media Tool does not change OBS settings or select a capture source for you.",
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

    def _checkout(self) -> Path | None:
        """The suite checkout: the chosen portal release when it is one, else the one the tool runs from."""
        return find_checkout(self.release_dir, Path(__file__).resolve().parent)

    def _show_icons(self) -> None:
        IconsDialog(self._checkout(), self).exec()

    def _show_portal_tour(self) -> None:
        PortalTourDialog(self._checkout(), self._open_recording, self).exec()

    def _show_apps_tour(self) -> None:
        AppsTourDialog(self._checkout(), self._open_recording, self).exec()

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
            time_label.setText(
                f"{timestamp(milliseconds)} / {timestamp(player.duration())}"
            )

        def update_duration(milliseconds: int) -> None:
            position_slider.setRange(0, milliseconds)
            update_position(player.position())

        def update_play_button(state: QMediaPlayer.PlaybackState) -> None:
            play_button.setText(
                "Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play"
            )

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
        selected = QFileDialog.getExistingDirectory(self, "Choose portal release or local suite checkout")
        if not selected:
            return
        try:
            self._set_release(Path(selected))
        except WorkflowError as exc:
            QMessageBox.warning(self, "Invalid portal release", str(exc))
            return

    def _find_release_automatically(self) -> None:
        release = find_portal_release()
        if release is None:
            self.release_status.setText(
                f"No extracted portal release found in {downloads_dir()}. Download a portal release, extract it "
                "there, then choose Find in Downloads."
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
                f"Recording is active. Finish installing the portal in its terminal. Media Tool will "
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
            "The portal is installed. Open it, show BC-250 Bazzite Test, install the selected optional app, "
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

    def closeEvent(self, event) -> None:
        if self.recording:
            answer = QMessageBox.question(
                self,
                "Recording in progress",
                "Stop the OBS recording before closing Media Tool?",
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
