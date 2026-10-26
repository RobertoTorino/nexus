# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the camera's state in the header (model, USB speed, firmware, video node), access to its boot loader
(a udev rule, once), its firmware (the pinned download or a file of the user's own, and whether it is sent by itself
at plug-in) and a preview of its picture in every mode it reports. Every second it looks in /sys for the camera. The
load service sends the firmware when the camera is plugged in; the window sends it when the service could not (no
access or no firmware yet at that moment), once per plug-in, and on Load firmware."""

from __future__ import annotations

import html
import time
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QSlider,
                             QMessageBox, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from bc250_core import window_title
from bc250_core.settings import restore_geometry, save_geometry
from bc250_core.theme import GREY, STATE_COLORS
from bc250_core.updates import UpdateChecker
from bc250_core.widgets import AppHeader, MetricBox, Pill, StatusText, accent_button, hint_label, same_width

from . import APP_NAME, INFO, LOGO_PATH, __version__, access, camera, controls, firmware, loader, modes, runner
from .camera import Camera
from .settings import BANDWIDTH_NAMES, CONTROL_DEFAULTS, VIEWS, CameraSettings

INTERVAL_MS = 1000
AUTO_GRACE_S = 3.0                  # the load service sends the firmware at plug-in; the window takes what it left
PICTURE_MIN = (640, 360)
ACCESS_NEW = ("Before its firmware is loaded, the camera is a boot loader that only root may use. Allow access adds a "
              "udev rule for it (it asks for your password, once): then your user sends the firmware, by itself each "
              "time the camera is plugged in, and the camera stays powered, so it keeps its picture settings.")
ACCESS_OUTDATED = ("The camera's udev rule is from an earlier version of the app. Allow access updates it (it asks for "
                   "your password): the camera then stays powered while it is plugged in, so it keeps its picture "
                   "settings; without it, the picture falls back to dark a moment after an app lets go of it.")


def _job(function: Callable, *args) -> Callable[[], object]:
    """A job for UpdateChecker: its result, or the FirmwareError it raised (a thread must not raise)."""
    def run():
        try:
            return function(*args)
        except firmware.FirmwareError as exc:
            return exc
    return run


def widget_tip(control: controls.Control) -> str:
    default = control.menu.get(control.default, control.default)
    if not control.active:
        return f"The camera does not let this be changed now. Its default is {default}."
    return f"Default {default}."


def _speed(mbps: int) -> str:
    if mbps >= 1000:
        return f"{mbps / 1000:g} Gbit/s"
    return f"{mbps} Mbit/s" if mbps else "—"


class MainWindow(QWidget):
    def __init__(self, sys_root: Path = camera.SYS, dev: Path = camera.DEV, rule_root: Path | str = "/",
                 run_root: Callable[[list[str]], runner.Result] = runner.run_root, firmware_home: Path | None = None,
                 get: firmware.Get | None = None, load: Callable[..., loader.Outcome] = loader.load,
                 preview=None, clock: Callable[[], float] = time.monotonic,
                 writable: Callable[[Path], bool] = camera.writable,
                 open_controls: Callable[[str], controls.Camera] = controls.Camera):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.settings = CameraSettings(INFO, self)
        self.sys_root = sys_root
        self.dev = dev
        self.rule_root = rule_root
        self.run_root = run_root
        self.firmware_home = firmware_home
        self.get = get or firmware._get
        self.load = load
        self.clock = clock
        self.writable = writable
        self.open_controls = open_controls
        self.control_camera: controls.Camera | None = None     # the node, open for its controls while it is there
        # control id -> (the control as last read, its widget, its value label, its name label)
        self.control_rows: dict[int, tuple[controls.Control, QWidget, QLabel, QLabel]] = {}
        self.cameras: list[Camera] = []
        self.loading = False
        self.quiet = False                  # the running load was the window's own: a failure goes in the state
        self.loading_port = ""
        self.problem: dict[str, str] = {}   # port -> why its firmware was not loaded, until it is unplugged
        self.tried: set[str] = set()        # ports the window loaded by itself; again only after a replug
        self.seen: dict[str, float] = {}    # port -> when its boot loader was first seen
        self.node = ""                      # the preview's /dev/video<n>
        self.modes: list[modes.Mode] = []
        self.image: QImage | None = None    # the last frame, whole

        layout = QVBoxLayout(self)
        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.badge = StatusText("Looking for the camera")
        header.add_state(self.badge)
        self.camera_box = MetricBox("Camera")
        self.usb_box = MetricBox("USB")
        self.firmware_box = MetricBox("Firmware")
        self.video_box = MetricBox("Video")
        # Load firmware is a pill beside the boxes (owner, 26-10-2026), as the portal's header has its actions.
        self.load_pill = Pill("Load firmware", "Click to send", "Sends the firmware to the camera now.")
        self.load_pill.clicked.connect(lambda: self.start_load(quiet=False))
        boxes = [self.camera_box, self.usb_box, self.firmware_box, self.video_box, self.load_pill]
        for box in boxes:
            header.add_second(box)
        same_width(boxes)
        header.add_second(QWidget(), 1)
        layout.addLayout(header)

        self.access_box = QGroupBox("Access to the camera")
        access_layout = QVBoxLayout(self.access_box)
        self.access_text = hint_label(ACCESS_NEW)
        access_layout.addWidget(self.access_text)
        self.access_button = accent_button("Allow access…")
        self.access_button.clicked.connect(self.allow_access)
        access_layout.addWidget(self.access_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.access_box)

        firmware_group = QGroupBox("Firmware")
        firmware_layout = QVBoxLayout(firmware_group)
        firmware_layout.addWidget(hint_label(
            "The camera has no memory of its own: it needs its firmware each time it is plugged in, as a PlayStation "
            "sends it. The firmware is Sony's, so the suite does not include it: Download gets it from a project that "
            "publishes it and checks that it is the expected file, or use a file of your own."))
        self.firmware_text = QLabel()
        self.firmware_text.setWordWrap(True)
        self.firmware_text.setTextFormat(Qt.TextFormat.RichText)
        self.firmware_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        firmware_layout.addWidget(self.firmware_text)
        buttons = QHBoxLayout()
        self.download_button = QPushButton("Download…")
        self.download_button.clicked.connect(self.download)
        self.file_button = QPushButton("Use a file…")
        self.file_button.setToolTip("Uses a firmware file you have, for example one with a fix for a dark picture.")
        self.file_button.clicked.connect(self.use_file)
        self.autoload = QCheckBox("Load it by itself when the camera is plugged in")
        self.autoload.setChecked(self.settings.get("autoload"))
        self.autoload.toggled.connect(lambda on: self.settings.set("autoload", on))
        buttons.addWidget(self.download_button)
        buttons.addWidget(self.file_button)
        buttons.addSpacing(12)
        buttons.addWidget(self.autoload)
        buttons.addStretch(1)
        firmware_layout.addLayout(buttons)
        bandwidth = QHBoxLayout()
        self.bandwidth_combo = QComboBox()
        for key, text in BANDWIDTH_NAMES.items():
            self.bandwidth_combo.addItem(text, key)
        self.bandwidth_combo.setCurrentIndex(max(0, self.bandwidth_combo.findData(self.settings.get("bandwidth"))))
        self.bandwidth_combo.setToolTip(
            "The firmware asks for the most video bandwidth USB 3 has, which some USB controllers refuse: then the "
            "camera sends no picture at all. Reduced asks for two thirds of it; every one-camera mode still runs at "
            "its full rate. It takes effect the next time the firmware is sent: unplug the camera and plug it in "
            "again.")
        self.bandwidth_combo.activated.connect(lambda _i: self.settings.set("bandwidth",
                                                                            self.bandwidth_combo.currentData()))
        bandwidth.addWidget(QLabel("USB bandwidth"))
        bandwidth.addWidget(self.bandwidth_combo)
        bandwidth.addStretch(1)
        firmware_layout.addLayout(bandwidth)
        layout.addWidget(firmware_group)

        picture_group = QGroupBox("Picture")
        picture_layout = QVBoxLayout(picture_group)
        controls = QGridLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.setMinimumContentsLength(32)
        self.mode_combo.setToolTip("Every mode the camera reports: one camera's picture, or both side by side.")
        self.mode_combo.activated.connect(self.set_mode)
        self.view_combo = QComboBox()
        for key, text in VIEWS.items():
            self.view_combo.addItem(text, key)
        self.view_combo.setCurrentIndex(max(0, self.view_combo.findData(self.settings.get("view"))))
        self.view_combo.setToolTip("A mode with both cameras sends their pictures side by side in one frame. Each half "
                                   "is the lens on that side as you face the camera.")
        self.view_combo.activated.connect(self.set_view)
        self.preview_button = QPushButton("Start preview")
        self.preview_button.setCheckable(True)
        self.preview_button.setToolTip("While the preview runs, other apps cannot use the camera.")
        self.preview_button.toggled.connect(self.toggle_preview)
        self.save_button = QPushButton("Save picture…")
        self.save_button.setToolTip("Saves what the preview shows, at the camera's own size, as a PNG.")
        self.save_button.clicked.connect(self.save_picture)
        controls.addWidget(QLabel("Mode"), 0, 0)
        controls.addWidget(self.mode_combo, 0, 1)
        controls.addWidget(QLabel("Show"), 0, 2)
        controls.addWidget(self.view_combo, 0, 3)
        controls.addWidget(self.preview_button, 0, 4)
        controls.addWidget(self.save_button, 0, 5)
        controls.setColumnStretch(6, 1)
        picture_layout.addLayout(controls)
        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setWordWrap(True)                  # its texts: no camera, a preview that failed
        self.picture.setMinimumSize(*PICTURE_MIN)
        self.picture.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        picture_row = QHBoxLayout()
        picture_row.addWidget(self.picture, 1)
        picture_row.addWidget(self._controls_box())
        picture_layout.addLayout(picture_row, 1)
        layout.addWidget(picture_group, 1)

        self.load_job = UpdateChecker(self)
        self.load_job.finished.connect(self._load_done)
        self.download_job = UpdateChecker(self)
        self.download_job.finished.connect(self._download_done)
        if preview is None:
            from .preview import Preview
            preview = Preview(self)
        self.preview = preview
        self.preview.frame.connect(self._frame)
        self.preview.failed.connect(self._preview_failed)

        self.timer = QTimer(self, interval=INTERVAL_MS)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        if not restore_geometry(self, self.settings.qsettings):
            self.resize(900, 820)
        self.refresh()

    # ------------------------------------------------------------------ state
    def current(self) -> Camera | None:
        """The camera the window shows: a ready one first, else one waiting for its firmware."""
        ready = [found for found in self.cameras if found.booted]
        return (ready or self.cameras or [None])[0]

    def model(self) -> str:
        found = self.current()
        return found.model if found else "cfi-zey1"

    def can_load(self, boot: Camera) -> bool:
        return firmware.read(boot.model, self.firmware_home) is not None and self.writable(boot.node(self.dev))

    def refresh(self) -> None:
        self.cameras = camera.find(self.sys_root)
        now = self.clock()
        boots = [found for found in self.cameras if not found.booted]
        ports = {found.port for found in boots}
        self.seen = {port: self.seen.get(port, now) for port in ports}
        self.tried &= ports
        self.problem = {port: text for port, text in self.problem.items() if port in ports}
        self._auto_load(boots, now)
        self.show_state()
        self._sync_preview()

    def _auto_load(self, boots: list[Camera], now: float) -> None:
        if self.loading or not self.settings.get("autoload"):
            return
        for boot in boots:
            if boot.port not in self.tried and now - self.seen[boot.port] >= AUTO_GRACE_S and self.can_load(boot):
                self.tried.add(boot.port)
                self.start_load(boot, quiet=True)
                return

    def show_state(self) -> None:
        found = self.current()
        data = firmware.read(self.model(), self.firmware_home)
        self.access_box.setVisible(not access.installed(self.rule_root))
        self.access_text.setText(ACCESS_OUTDATED if access.outdated(self.rule_root) else ACCESS_NEW)
        if self.loading:
            state = ("Loading the firmware", "info", "The camera comes back as a camera in a few seconds.")
        elif found is None:
            state = ("No camera", "neutral", "Plug in the PS5 HD Camera, into a USB 3 port; the app finds "
                                             f"it by itself. {camera.NOT_FOUND}")
        elif found.booted:
            state = (("Ready", "ok", f"The {found.name} is a camera: other apps can use it while the preview is off.")
                     if found.videos else ("Starting", "info", "The camera is back; its video node follows."))
        elif data is None:
            state = ("Needs its firmware", "warn", "Download it or use a file of your own, below.")
        elif not self.writable(found.node(self.dev)):
            state = ("No access", "warn", "Allow access gives your user the camera's boot loader.")
        elif found.port in self.problem:
            state = ("Firmware not loaded", "bad", self.problem[found.port])
        else:
            state = ("Waiting for its firmware", "info", "Load firmware sends it now.")
        self.badge.set_status(*state)

        self.camera_box.set_value(found.name if found else "—", f"Port {found.port}" if found else "")
        slow = found is not None and found.slow
        self.usb_box.set_value(_speed(found.speed_mbps) if found else "—",
                               "The camera's video needs a USB 3 port (5 Gbit/s); this one is slower. Use a blue "
                               "port." if slow else "")
        self.usb_box.set_colour(STATE_COLORS["warn"] if slow else GREY)
        self._show_firmware(data)
        self.video_box.set_value(found.videos[0].removeprefix("/dev/") if found and found.videos else "—")
        model_name = camera.MODELS[self.model()]
        self.load_pill.setEnabled(found is not None and not found.booted and not self.loading
                                    and self.can_load(found))
        pinned = firmware.PINNED.get(self.model())
        self.download_button.setEnabled(not self.download_job.running and pinned is not None)
        self.download_button.setToolTip(f"Downloads the {model_name}'s firmware ({pinned.size // 1024} KB) from "
                                        f"{pinned.source} and checks it." if pinned else
                                        "There is no download for this camera's firmware: use a file.")

    # --------------------------------------------------------------- firmware
    def _show_firmware(self, data: bytes | None) -> None:
        """The file and its SHA-256 check: green for a file the app knows, orange for one of the user's own."""
        model_name = camera.MODELS[self.model()]
        if data is None:
            self.firmware_box.set_value("None", "")
            self.firmware_box.set_colour(GREY)
            self.firmware_text.setText(f"{model_name}: no firmware yet.")
            return
        found, digest = firmware.known(data), firmware.sha256(data)
        where = firmware.path(self.model(), self.firmware_home)
        check = (f"SHA-256 checked: it is the known file {found.name}." if found else
                 "SHA-256 checked: not a file the app knows. It is your choice; the camera may not take it.")
        colour = STATE_COLORS["ok" if found else "warn"]
        self.firmware_box.set_value(firmware.short(data), f"{check}\nSHA-256 {digest}")
        self.firmware_box.set_colour(colour)
        self.firmware_text.setText(f"{html.escape(model_name)}: {html.escape(firmware.describe(data))}, in "
                                   f"{html.escape(str(where))}<br>"
                                   f"<span style='color:{colour}'>{'✓' if found else '!'} {check}</span> "
                                   f"SHA-256 <code>{digest}</code>")

    def start_load(self, boot: Camera | None = None, quiet: bool = False) -> None:
        boot = boot or self.current()
        data = firmware.read(boot.model, self.firmware_home) if boot and not boot.booted else None
        if data is None or self.loading:
            return
        sys_root, dev = self.sys_root, self.dev
        self.loading, self.quiet, self.loading_port = True, quiet, boot.port
        data = loader.with_bandwidth(data, loader.bursts(self.settings.get("bandwidth")))
        self.load_job.start(lambda: self.load(boot, data, find=lambda: camera.find(sys_root), dev=dev))
        self.show_state()

    def _load_done(self, outcome: loader.Outcome) -> None:
        self.loading = False
        if not outcome.ok:
            self.problem[self.loading_port] = outcome.message
            if not self.quiet:
                QMessageBox.warning(self, window_title("Load firmware"), outcome.message)
        self.refresh()

    def allow_access(self) -> None:
        result = self.run_root(access.command(["install"]))
        problem = access.answer(result.code, result.out)
        if problem:
            QMessageBox.warning(self, window_title("Access to the camera"), problem)
        self.refresh()

    def download(self) -> None:
        model = self.model()
        pinned = firmware.PINNED[model]
        answer = QMessageBox.question(
            self, window_title("Download the firmware"),
            f"This downloads the {camera.MODELS[model]}'s firmware ({pinned.size // 1024} KB) from {pinned.source} "
            "and checks that it is the expected file. It is the app's only use of the network.")
        if answer == QMessageBox.StandardButton.Yes:
            self.download_job.start(_job(firmware.download, model, self.firmware_home, self.get))
            self.show_state()

    def _download_done(self, result) -> None:
        if isinstance(result, firmware.FirmwareError):
            QMessageBox.warning(self, window_title("Download the firmware"), str(result))
        self.problem.clear()
        self.refresh()

    def use_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, window_title("Use a firmware file"), str(Path.home()),
                                              "Firmware (*.bin);;All files (*)")
        if path:
            self.use_path(Path(path))

    def use_path(self, path: Path) -> None:
        try:
            firmware.store(self.model(), path.read_bytes(), self.firmware_home)
        except firmware.FirmwareError as exc:
            QMessageBox.warning(self, window_title("Use a firmware file"), f"{path.name} was not used: {exc}")
            return
        except OSError as exc:
            QMessageBox.warning(self, window_title("Use a firmware file"), f"{path} could not be read: {exc.strerror}.")
            return
        self.problem.clear()
        self.tried.clear()                  # a new file is worth one more try by itself
        self.refresh()

    # --------------------------------------------------------------- controls
    def _controls_box(self) -> QGroupBox:
        self.controls_box = QGroupBox("Picture settings")
        self.controls_box.setMinimumWidth(300)
        box = QVBoxLayout(self.controls_box)
        self.controls_grid = QGridLayout()
        box.addLayout(self.controls_grid)
        self.controls_text = hint_label("The camera's own settings, as it reports them. The app sets them again each "
                                        "time the camera is plugged in; other apps get the same picture.")
        box.addWidget(self.controls_text)
        self.defaults_button = QPushButton("Defaults")
        self.defaults_button.setToolTip("Puts every setting back to its default: the camera's own, with the exposure "
                                        "on Auto Mode, which the camera's own default leaves dark.")
        self.defaults_button.clicked.connect(self.reset_controls)
        box.addWidget(self.defaults_button, 0, Qt.AlignmentFlag.AlignLeft)
        box.addStretch(1)
        self.controls_box.setEnabled(False)
        return self.controls_box

    def _open_controls(self, node: str) -> None:
        """The new camera's controls, with the values the user chose set again: the camera forgets them unplugged."""
        self._close_controls()
        if not node:
            return
        try:
            self.control_camera = self.open_controls(node)
            refused = controls.apply(self.control_camera, self.settings.controls())
            listed = self.control_camera.list()
        except OSError as exc:
            self._close_controls()
            self.controls_text.setText(f"The camera's settings could not be read: {exc.strerror or exc}.")
            return
        for row, control in enumerate(listed):
            if control.kind == controls.BOOLEAN:
                widget = QCheckBox()
                widget.toggled.connect(lambda on, c=control: self.set_control(c, int(on)))
            elif control.kind == controls.MENU:
                widget = QComboBox()
                for index, text in control.menu.items():
                    widget.addItem(text, index)
                widget.activated.connect(lambda _i, c=control, w=widget: self.set_control(c, w.currentData()))
            else:
                widget = QSlider(Qt.Orientation.Horizontal)
                widget.setRange(control.minimum, control.maximum)
                widget.setSingleStep(max(1, control.step))
                widget.setPageStep(max(1, control.step) * max(1, (control.maximum - control.minimum) // 10))
                widget.valueChanged.connect(lambda value, c=control: self.set_control(c, value))
            value = QLabel()
            value.setMinimumWidth(36)
            name = QLabel(control.name)
            self.controls_grid.addWidget(name, row, 0)
            self.controls_grid.addWidget(widget, row, 1)
            self.controls_grid.addWidget(value, row, 2)
            self.control_rows[control.id] = (control, widget, value, name)
        self._show_controls(listed)
        self.controls_box.setEnabled(True)
        self.controls_text.setText(
            f"The camera refused {', '.join(refused)}." if refused else
            "The camera's own settings, as it reports them. The app sets them again each time the camera is plugged "
            "in; other apps get the same picture.")

    def _show_controls(self, listed: list[controls.Control]) -> None:
        """Values and what may be changed: a setting the camera does not let be changed is grayed, the whole row
        (an automatic setting grays the one it decides; the PS5 HD Camera's exposure time stays grayed, as it keeps
        it at 1000 in either exposure mode)."""
        for control in listed:
            if control.id not in self.control_rows:
                continue
            _old, widget, value, name = self.control_rows[control.id]
            self.control_rows[control.id] = (control, widget, value, name)
            widget.blockSignals(True)
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(control.value))
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(max(0, widget.findData(control.value)))
            else:
                widget.setValue(control.value)
                value.setText(str(control.value))
            widget.blockSignals(False)
            for part in (widget, value, name):
                part.setEnabled(control.active)
                part.setToolTip(widget_tip(control))

    def _close_controls(self) -> None:
        if self.control_camera is not None:
            camera_, self.control_camera = self.control_camera, None
            try:
                camera_.close()
            except OSError:
                pass
        while self.controls_grid.count():
            item = self.controls_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.control_rows.clear()
        self.controls_box.setEnabled(False)

    def set_control(self, control: controls.Control, value: int) -> None:
        if self.control_camera is None:
            return
        try:
            self.control_camera.set(control.id, value)
            listed = self.control_camera.list()
        except OSError as exc:
            self.controls_text.setText(f"The camera refused {control.name}: {exc.strerror or exc}.")
            return
        chosen = self.settings.controls()
        chosen[control.key] = value
        self.settings.set_controls(chosen)
        self._show_controls(listed)

    def reset_controls(self) -> None:
        if self.control_camera is None:
            return
        try:
            listed = self.control_camera.list()
            defaults = {**{control.key: control.default for control in listed}, **CONTROL_DEFAULTS}
            controls.apply(self.control_camera, defaults)
            listed = self.control_camera.list()
        except OSError as exc:
            self.controls_text.setText(f"The camera's settings could not be reset: {exc.strerror or exc}.")
            return
        self.settings.set_controls({})
        self._show_controls(listed)

    # ---------------------------------------------------------------- picture
    def _sync_preview(self) -> None:
        found = self.current()
        node = found.videos[0] if found and found.booted and found.videos else ""
        if node != self.node:
            self.preview.stop()
            self.preview_button.setChecked(False)
            self.node, self.modes = node, []
            self.mode_combo.clear()
            self.image = None
            self.picture.clear()
            self._open_controls(node)
        if node and not self.modes:         # Qt may list a new camera a moment after its node appears
            self.modes = modes.ordered(self.preview.modes(node))
            self.mode_combo.clear()
            for mode in self.modes:
                self.mode_combo.addItem(mode.label, mode.key)
            chosen = modes.chosen(self.modes, self.settings.get("mode"))
            if chosen is not None:
                self.mode_combo.setCurrentIndex(self.mode_combo.findData(chosen.key))
        if not node:
            self.picture.setText("The picture shows here once the camera is ready." if self.cameras else
                                 f"No camera found.\n\n{camera.NOT_FOUND}")
        self.mode_combo.setEnabled(bool(self.modes))
        self.preview_button.setEnabled(bool(node))
        mode = self.mode()
        self.view_combo.setEnabled(mode is not None and mode.stereo)
        self.save_button.setEnabled(self.image is not None)

    def mode(self) -> modes.Mode | None:
        return modes.chosen(self.modes, self.mode_combo.currentData() or "")

    def set_mode(self, _index: int) -> None:
        mode = self.mode()
        if mode is None:
            return
        self.settings.set("mode", mode.key)
        self.view_combo.setEnabled(mode.stereo)
        if self.preview.running:
            self.preview.start(self.node, mode)

    def set_view(self, _index: int) -> None:
        self.settings.set("view", self.view_combo.currentData())
        self._show_image()

    def view(self) -> str:
        mode = self.mode()
        return self.view_combo.currentData() if mode is not None and mode.stereo else "both"

    def toggle_preview(self, on: bool) -> None:
        self.preview_button.setText("Stop preview" if on else "Start preview")
        if on and self.node:
            if not self.preview.start(self.node, self.mode()):
                self.preview_button.setChecked(False)
        elif not on:
            self.preview.stop()

    def shown_image(self) -> QImage | None:
        if self.image is None:
            return None
        x, y, width, height = modes.crop(self.image.width(), self.image.height(), self.view())
        return self.image.copy(QRect(x, y, width, height))

    def _frame(self, image: QImage) -> None:
        self.image = image
        self._show_image()
        self.save_button.setEnabled(True)

    def _show_image(self) -> None:
        image = self.shown_image()
        if image is not None:
            self.picture.setPixmap(QPixmap.fromImage(image).scaled(
                self.picture.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _preview_failed(self, text: str) -> None:
        self.preview_button.setChecked(False)
        self.picture.setText(text)

    def save_picture(self) -> None:
        image = self.shown_image()
        if image is None:
            return
        start = Path.home() / "Pictures" / time.strftime("bc250-usb-hdcam-%Y%m%d-%H%M%S.png")
        path, _ = QFileDialog.getSaveFileName(self, window_title("Save picture"), str(start), "PNG image (*.png)")
        if path and not image.save(path, "PNG"):
            QMessageBox.warning(self, window_title("Save picture"), f"{path} could not be written.")

    # ------------------------------------------------------------------- quit
    def shut_down(self) -> None:
        self.timer.stop()
        self.preview.stop()
        self._close_controls()
        self.load_job.stop(15000)
        self.download_job.stop(1000)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        save_geometry(self, self.settings.qsettings)
        self.preview.stop()
        super().closeEvent(event)
