# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the cards on the left (Camera, Picture, Firmware, Bandwidth), what the focused one shows on the right,
the controller's buttons at the bottom. A on the Camera card does the camera's next step: look for it, Allow access (the
driver, once per USB port, with Windows' administrator prompt), Load the firmware, look again. The Picture card shows
the camera's picture (A starts and stops it, LB and RB change the mode; it stops when another card is chosen). The
Firmware card gets
the pinned file (A) or takes one of yours (X, in core's browser); the Bandwidth card picks what the firmware asks of
the USB controller. Nothing runs before A asks for it (owner, 28-10-2026). Slow steps run off the window's thread.

Once the camera is a webcam, the app sets its exposure to automatic and keeps its driver open while the app runs
(picture.py): Windows powers an unused camera down, and it wakes with its own dark exposure again. View asks for a
second press then, since the picture goes dark when the app closes."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, QTimer, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, browse, power
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private
from bc250_core.portable import VIEW, Card, Legend, PortableHeader, PortableWindow, px, status_clock

from . import APP_ID, APP_NAME, __version__, camera, driver, firmware, loader, modes, picture, preview, winusb
from .camera import Camera
from .modes import Mode
from .panes import InfoPane, ListPane, PicturePane

STATUS_MS = 30_000              # the header's time and battery
CONFIRM_MS = 5000               # View, while the app keeps the picture, asks for a second press within this
KEPT = ("The picture stays right while USB HD Cam is open: leave it open in the background while you use the "
        "camera.")
CARDS_WIDTH = 520
BANDWIDTH_KEY = "bandwidth"     # the setting: loader.BANDWIDTHS
MODE_KEY = "mode"               # the setting: the Picture card's mode (Mode.key)
BROWSED = "firmware"            # the browser's folder kept for next time (browse.remember)
BANDWIDTH_NAMES = {
    "full": "Full: what the firmware asks for, every mode at its full rate",
    "reduced": "Reduced: for a USB controller that refuses full; the three largest side-by-side modes give no picture",
}

CAMERA_INFO = (
    "The PS5 HD Camera has no memory of its own: it starts as a boot loader (\"USB Boot\") and needs its firmware "
    "each time it is plugged in, as a PlayStation sends it. Then it is an ordinary webcam, \"USB Camera-OV580\", for "
    "OBS, a browser, Discord or any other app.\n\n"
    "The A button does the next step. The first time on a USB port, Allow access gives the boot loader Microsoft's own "
    "WinUSB driver, which ships with Windows: Windows asks for an administrator once. That is the app's only "
    "administrator step; another USB port asks once more. Then Load the firmware sends it; the camera comes back as "
    "a webcam within a second and stays one until it is unplugged.\n\n"
    "Then the app sets the camera's exposure to automatic: left to itself, the camera keeps a very short exposure and "
    "its picture is close to black. Windows switches an unused camera off, and the camera forgets the setting, so "
    "the app keeps the camera open while it runs: leave USB HD Cam open in the background while you use the camera "
    "in OBS, a browser or Discord. The camera has no microphone.\n\n"
    "The video needs a USB 3 port (5 Gbit/s). A PS4 Camera on Sony's adapter is found, but its firmware is not this "
    "app's yet.")
PICTURE_INFO = (
    "The camera's picture, as other apps get it. The A button starts it and stops it; LB and RB choose the mode before "
    "or the next one: one camera's picture first, from the largest, then both cameras side by side, as the camera "
    "sends them for depth. Only the modes that give a picture are listed. The picture stops when you choose another "
    "card, and other apps can show the camera meanwhile.")
FIRMWARE_INFO = (
    "The camera's firmware is Sony's, so the suite does not ship it. The A button downloads the file the app knows, "
    f"21.01-03.20.00.04 from {firmware.PINNED.source}, and uses it only when its SHA-256 is the expected one. The X "
    "button picks a file of your own (a .bin) with the controller; the app says whether it knows it. The file is kept "
    "in the suite's folder and used for every load.")
BANDWIDTH_INFO = (
    "The firmware asks the USB controller for the most video bandwidth USB 3 has. Some controllers refuse it; then "
    "the largest modes give no picture. Reduced asks for two thirds: every one-camera mode still runs at its full "
    "rate, side by side up to 2560 x 800 at 30 fps. The file stays as it is; only the copy sent changes. It counts "
    "from the next load: unplug the camera and plug it in again, then load it.")
BROWSE_INFO = (
    "Find the firmware file. The A button opens the folder the focus is on, or takes the file; the B button goes a "
    "level up, and from the places back to the Firmware card. The places are your usual folders and every drive.")


class _Worker(QObject):
    """Runs a slow step off the window's thread; done or failed arrive on the window's."""

    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.busy = False

    def start(self, work: Callable[[], object]) -> bool:
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=self._run, args=(work,), daemon=True).start()
        return True

    def _run(self, work: Callable[[], object]) -> None:
        try:
            result = work()
        except Exception as error:  # noqa: BLE001  (shown in the pane, not raised)
            self.busy = False
            self.failed.emit(str(error) or type(error).__name__)
            return
        self.busy = False
        self.done.emit(result)


class MainWindow(PortableWindow):
    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery,
                 find: Callable[[], list[Camera]] = camera.find,
                 allow: Callable[[str], str] = driver.ask,
                 load: Callable[..., loader.Outcome] = loader.load,
                 open_device: Callable[[str], object] = winusb.Device,
                 download: Callable[[], Path] = firmware.download,
                 keep: Callable[[str], object] = picture.keep,
                 live: preview.Preview | None = None,
                 camera_modes: Callable[[], list[Mode]] = preview.camera_modes,
                 home: Path | None = None, settings: QSettings | None = None,
                 roots: Callable[[], list[Path]] = browse.drives, user_home: Path | None = None):
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.find, self.allow, self.load, self.open_device, self.download = find, allow, load, open_device, download
        self.keep = keep
        self.live = live or preview.Preview(parent=self)
        self.camera_modes = camera_modes
        self.modes: list[Mode] = []                     # what the Picture card offers, read when it is chosen
        self.home = home                                # the firmware's folder (None: the suite's)
        self.settings = settings or QSettings()
        self.roots, self.user_home = roots, user_home
        self.camera: Camera | None = None
        self.looked = False                             # A has looked for the camera at least once
        self.step = ""                                  # what the camera worker is doing: find, allow, load
        self.carry = ""                                 # said after the next find instead of the next step
        self.kept = None                                # the webcam's driver, kept open with Auto Exposure
        self.close_asked = False                        # View pressed once while the picture is kept
        self.browser: browse.Browser | None = None

        page = QVBoxLayout(self)
        page.setContentsMargins(*self.margins())
        self.header = PortableHeader(APP_NAME, __version__)
        page.addWidget(self.header)
        page.addSpacing(px(14))
        body = QHBoxLayout()
        column = QWidget()
        column.setFixedWidth(px(CARDS_WIDTH))
        cards = QVBoxLayout(column)
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(px(12))
        self.camera_card = Card("Camera", "Plug it in, then the A button: the app does the next step.")
        self.picture_card = Card("Picture", "The camera's picture, in each mode that gives one.")
        self.firmware_card = Card("Firmware", "")
        self.bandwidth_card = Card("Bandwidth", "")
        for card in (self.camera_card, self.picture_card, self.firmware_card, self.bandwidth_card):
            card.setFixedHeight(px(100))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()
        self.camera_pane = InfoPane("Camera", "The PS5 HD Camera as Windows sees it: a boot loader until it has its "
                                    "firmware, then a webcam.", CAMERA_INFO, "Look for it")
        self.picture_pane = PicturePane("Picture", PICTURE_INFO, preview.PictureView())
        self.firmware_pane = InfoPane("Firmware", "Sony's firmware for the camera, sent each time it is plugged in.",
                                      FIRMWARE_INFO, "Download")
        self.bandwidth_pane = ListPane("Bandwidth", BANDWIDTH_INFO)
        self.browse_pane = ListPane("Pick the firmware", BROWSE_INFO)
        for pane in (self.camera_pane, self.picture_pane, self.firmware_pane, self.bandwidth_pane, self.browse_pane):
            self.panes.addWidget(pane)
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend()
        page.addWidget(self.legend)
        self.cards = {self.camera_pane: self.camera_card, self.picture_pane: self.picture_card,
                      self.firmware_pane: self.firmware_card,
                      self.bandwidth_pane: self.bandwidth_card, self.browse_pane: self.firmware_card}

        self.camera_worker = _Worker()
        self.camera_worker.done.connect(self.camera_done)
        self.camera_worker.failed.connect(self.camera_failed)
        self.firmware_worker = _Worker()
        self.firmware_worker.done.connect(self.firmware_done)
        self.firmware_worker.failed.connect(self.firmware_failed)
        self.camera_card.focused.connect(lambda: self.show_pane(self.camera_pane))
        self.camera_card.activated.connect(self.camera_step)
        self.picture_card.focused.connect(lambda: self.show_pane(self.picture_pane))
        self.picture_card.activated.connect(self.toggle_picture)
        self.live.picture.connect(self.picture_pane.view.show_image)
        self.live.failed.connect(self.picture_failed)
        self.firmware_card.focused.connect(lambda: self.show_pane(self.firmware_pane))
        self.firmware_card.activated.connect(self.get_firmware)
        self.bandwidth_card.focused.connect(lambda: self.show_pane(self.bandwidth_pane))
        self.bandwidth_card.activated.connect(lambda: self.focus_list(self.bandwidth_pane))
        self.bandwidth_pane.list.picked.connect(self.set_bandwidth)
        self.browse_pane.list.picked.connect(self.browse_picked)
        self.bind("accept", self.a_action)
        self.bind("x", self.x_action)
        self.bind("previous", lambda: self.step_mode(-1))
        self.bind("next", lambda: self.step_mode(1))
        self.back.connect(self.on_back)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(self.update_status)
        self.confirm_timer = QTimer(self)
        self.confirm_timer.setSingleShot(True)
        self.confirm_timer.setInterval(CONFIRM_MS)
        self.confirm_timer.timeout.connect(self._confirm_over)
        self.show_camera()
        self.show_firmware()
        self.show_bandwidth()
        self.show_pane(self.camera_pane)

    def start(self) -> None:
        """After the window is shown: the controller and the status line; the camera is looked for on A."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.camera_card.setFocus()

    def update_status(self) -> None:
        self.header.set_status([*status_clock(), power.text(self.battery())])   # the battery last (owner, 30-10-2026)

    def show_pane(self, pane) -> None:
        if pane is not self.picture_pane and self.live.running:
            self.stop_picture()                         # another card: the picture stops
        self.panes.setCurrentWidget(pane)
        if pane is self.picture_pane:
            self.show_picture()
        self.update_legend()

    def focus_list(self, pane: ListPane) -> None:
        """The list's first row, or the pane's card while the list is empty."""
        (pane.list.first() or self.cards[pane]).setFocus()

    def update_legend(self) -> None:
        """The pane's buttons, then core's Menu Info, B Back and View Exit (the suite's rule)."""
        if not hasattr(self, "legend"):
            return
        if self.close_asked:
            self.legend.set_items([(VIEW, "Press again to exit")])
            return
        pane = self.panes.currentWidget()
        if pane is self.camera_pane:
            items = [("A", self.camera_pane.action)]
        elif pane is self.firmware_pane:
            items = [("A", self.firmware_pane.action), ("X", "Pick a file")]
        elif pane is self.browse_pane:
            items = [("A", "Open")]
        elif pane is self.picture_pane:
            items = [("A", "Stop" if self.live.running else "Start"), ("LB", "Mode before"), ("RB", "Next mode")]
        else:
            items = [("A", "Pick")]
        self.legend.set_items([*items, *self.common_items(back=True if pane is self.browse_pane else None)])

    def a_action(self) -> None:
        """A beside a card (a tap on the legend's A, A in a pane): the pane's action, as A on its card."""
        pane = self.panes.currentWidget()
        if pane is self.camera_pane:
            self.camera_step()
        elif pane is self.picture_pane:
            self.toggle_picture()
        elif pane is self.firmware_pane:
            self.get_firmware()
        elif pane is self.bandwidth_pane:
            self.focus_list(self.bandwidth_pane)
        elif pane is self.browse_pane:
            self.focus_list(self.browse_pane)

    def x_action(self) -> None:
        if self.panes.currentWidget() is self.firmware_pane:
            self.show_browser()

    def on_back(self) -> None:
        """B: in the browser a level up, from its places back to the Firmware card; in a pane back to its card."""
        if self.panes.currentWidget() is self.browse_pane and self.browser is not None:
            if self.browser.up():
                self.show_browse()
            else:
                self.leave_browser()
            return
        self.go_back()

    # The Camera card

    def camera_step(self) -> None:
        """A on the camera: the next step for what was found; while one runs, the pane says so (owner, 29-10-2026:
        nothing is grayed out)."""
        if self.camera_worker.busy:
            self.camera_pane.status.setText("The camera is still busy with the step before.")
            return
        found = self.camera
        if found is not None and found.state == camera.NO_DRIVER:
            self.step = "allow"
            self.camera_pane.status.setText("Windows asks for an administrator: its prompt may be behind this "
                                            "window. The app installs only Microsoft's WinUSB driver.")
            self.log.info("Allow access: asking Windows for an administrator.")
            self.camera_worker.start(lambda: self.allow(found.instance))
        elif found is not None and found.state == camera.BOOT_LOADER:
            data = firmware.read(self.home)
            if data is None:
                self.camera_pane.status.setText("No firmware yet: the Firmware card gets it, then the A button here "
                                                "loads it.")
                return
            bandwidth = self.bandwidth()
            self.step = "load"
            self.camera_pane.status.setText(f"Sending the firmware ({firmware.short(data)}, {bandwidth} bandwidth) …")
            self.log.info(f"Loading the firmware: {firmware.describe(data)}, {bandwidth} bandwidth.")
            self.camera_worker.start(lambda: self.load(found, data, bandwidth, open_device=self.open_device,
                                                       find=self.find))
        else:
            self.step = "find"
            self.camera_pane.status.setText("Looking for the camera …")
            self.camera_worker.start(self.find)

    def camera_done(self, result) -> None:
        step, self.step = self.step, ""
        if step == "find":
            self.looked = True
            self.camera = result[0] if result else None
            self.camera_pane.status.setText(self.carry or self.next_text())
            self.carry = ""
            self.log.info(f"Looked for the camera: {self.state_text()}.")
            if self.keep_picture():
                self.show_camera()
                return
        elif step == "allow":
            if result:
                self.camera_pane.status.setText(result)
                self.log.warning(f"Allow access: {result}")
                return
            self.log.info("Allow access: WinUSB is the boot loader's driver.")
            self.step = "find"
            self.camera_worker.start(self.find)
        elif step == "keep":
            self.kept = result
            self.camera_pane.status.setText(" ".join(part for part in (self.carry, KEPT) if part))
            self.carry = ""
            self.log.info("The picture: Auto Exposure set, the webcam kept open.")
        elif step == "load":
            outcome: loader.Outcome = result
            self.camera = outcome.camera or self.camera
            if outcome.ok:
                self.camera_pane.status.setText(outcome.message)
                self.log.info(outcome.message)
                self.carry = outcome.message
                self.keep_picture()
                self.show_camera()
                return
            self.log.error(outcome.message)
            self.step, self.carry = "find", outcome.message     # what the camera is now; the status says why
            self.camera_worker.start(self.find)
            return
        self.show_camera()

    def camera_failed(self, error: str) -> None:
        step, self.step = self.step, ""
        if step == "keep":
            text = f"The webcam's picture could not be set, so it may be dark: {error} The A button tries again."
            self.camera_pane.status.setText(" ".join(part for part in (self.carry, text) if part))
            self.carry = ""
            self.log.error(f"Setting the picture failed: {error}")
            self.show_camera()
            return
        self.camera_pane.status.setText(f"That did not work: {error}")
        self.log.error(f"The camera's step failed: {error}")

    def keep_picture(self) -> bool:
        """The webcam's driver let go of, then, when the camera is ready, kept open with Auto Exposure (off the
        window's thread); whether that started. A camera plugged in again on the same port has the same instance ID,
        so the driver is opened anew each time."""
        self.release_picture()
        found = self.camera
        if found is None or found.state != camera.READY_STATE or not found.video:
            return False
        self.carry = self.carry or self.camera_pane.status.text()      # said again once the picture is set
        self.step = "keep"
        self.camera_worker.start(lambda: self.keep(found.video))
        return True

    def release_picture(self) -> None:
        if self.kept is not None:
            try:
                self.kept.close()
            except OSError:
                pass
            self.kept = None

    def state_text(self) -> str:
        found = self.camera
        if found is None:
            return "Not found" if self.looked else "Not looked for yet"
        return {camera.NO_DRIVER: "Boot loader, without a driver",
                camera.BOOT_LOADER: "Boot loader, waiting for its firmware",
                camera.READY_STATE: "Ready: a webcam",
                camera.PS4: "A PS4 Camera's boot loader"}[found.state]

    def next_text(self) -> str:
        """What the A button does now, as the status line says it."""
        found = self.camera
        if found is None:
            return ("Not found. Plug the camera into a USB 3 port, then press the A button again."
                    if self.looked else "")
        slow = (" It is on a port slower than USB 3: the video needs USB 3 (5 Gbit/s), so plug it into another "
                "port." if found.slow else "")
        if found.state == camera.NO_DRIVER:
            return "The boot loader has no driver yet: the A button allows access, once for this USB port." + slow
        if found.state == camera.BOOT_LOADER:
            return "The A button loads the firmware." + slow
        if found.state == camera.PS4:
            return "This is a PS4 Camera on Sony's adapter: the app does not load its firmware yet."
        return f"Apps list it as \"{found.webcam or 'USB Camera-OV580'}\"." + slow

    def show_camera(self) -> None:
        found = self.camera
        state = self.state_text()
        self.camera_card.set_text(state)
        if found is None:
            self.camera_pane.show_rows([("State", state)])
            self.camera_pane.action = "Look again" if self.looked else "Look for it"
        else:
            rows = [("Camera", found.name), ("State", state),
                    ("USB", found.speed.text if found.speed is not None else "Not known"),
                    ("Driver", {"winusb": "WinUSB (Microsoft)", "usbccgp": "Windows' own (USB video)"}.get(
                        found.device.service.lower(), found.device.service or "None"))]
            if found.webcam:
                rows.append(("Webcam", found.webcam))
            if found.state == camera.READY_STATE:
                rows.append(("Picture", "Auto exposure, while the app is open" if self.kept is not None else
                             "The camera's own exposure: dark"))
            self.camera_pane.show_rows(rows)
            self.camera_pane.action = {camera.NO_DRIVER: "Allow access",
                                       camera.BOOT_LOADER: "Load the firmware"}.get(found.state, "Look again")
        self.update_legend()

    # The Picture card

    def mode(self) -> Mode | None:
        return modes.chosen(self.modes, str(self.settings.value(MODE_KEY, "")))

    def show_picture(self) -> None:
        """The modes the camera gives a picture in now, and the chosen one."""
        self.modes = modes.offered(self.camera_modes(), self.bandwidth())
        chosen = self.mode()
        self.picture_pane.summary.setText(chosen.label if chosen else "The camera is not a webcam yet.")
        if not self.live.running:
            self.picture_pane.view.clear("The A button starts the picture." if chosen else
                                         "Make the camera a webcam on the Camera card first.")

    def toggle_picture(self) -> None:
        if self.live.running:
            self.stop_picture()
            self.picture_pane.status.setText("")
            return
        self.start_picture()

    def start_picture(self) -> None:
        """A: the picture in the chosen mode, once the Camera card made the camera a webcam and set its picture."""
        found = self.camera
        if found is None or found.state != camera.READY_STATE:
            self.picture_pane.status.setText("The camera is not a webcam yet: the A button on the Camera card makes it "
                                             "one first.")
            return
        self.show_picture()
        chosen = self.mode()
        if chosen is None:
            self.picture_pane.status.setText("Windows does not list the webcam: look for the camera again on the "
                                             "Camera card.")
            return
        problem = self.live.start(chosen)
        if problem:
            self.picture_pane.status.setText(problem)
            return
        self.picture_pane.view.clear("Starting the picture …")
        self.picture_pane.status.setText("" if self.kept is not None else
                                          "The camera's own exposure is set, so the picture may be dark.")
        self.log.info(f"Picture started: {chosen.key}.")
        self.update_legend()

    def stop_picture(self) -> None:
        self.live.stop()
        self.picture_pane.view.clear("The A button starts the picture.")
        self.update_legend()

    def picture_failed(self, text: str) -> None:
        self.picture_pane.view.clear(text)
        self.picture_pane.status.setText(text)
        self.log.warning(f"The picture stopped: {text}")
        self.update_legend()

    def step_mode(self, delta: int) -> None:
        """LB and RB on the Picture card: the mode before or the next one; a running picture restarts in it."""
        if self.panes.currentWidget() is not self.picture_pane or not self.modes:
            return
        chosen = self.mode()
        at = self.modes.index(chosen) if chosen in self.modes else 0
        picked = self.modes[(at + delta) % len(self.modes)]
        self.settings.setValue(MODE_KEY, picked.key)
        self.picture_pane.summary.setText(picked.label)
        if self.live.running:
            self.start_picture()

    # The Firmware card

    def show_firmware(self) -> None:
        data = firmware.read(self.home)
        if data is None:
            self.firmware_card.set_text("None yet: the A button downloads it.")
            self.firmware_pane.show_rows([("File", "None yet")])
            self.firmware_pane.action = "Download"
        else:
            self.firmware_card.set_text(firmware.describe(data))
            known = firmware.known(data)
            self.firmware_pane.show_rows([("File", firmware.describe(data)),
                                          ("Known", "Yes, by its SHA-256" if known else "No: your own file"),
                                          ("Kept in", private(firmware.path(self.home)))])
            self.firmware_pane.action = "Download again"
        self.update_legend()

    def get_firmware(self) -> None:
        if self.firmware_worker.busy:
            self.firmware_pane.status.setText("Still downloading …")
            return
        self.firmware_pane.status.setText(f"Downloading from {firmware.PINNED.source} …")
        self.firmware_worker.start(self.download)

    def firmware_done(self, _path) -> None:
        self.firmware_pane.status.setText("Downloaded and checked: the Camera card loads it.")
        self.log.info("Firmware downloaded and checked.")
        self.show_firmware()

    def firmware_failed(self, error: str) -> None:
        self.firmware_pane.status.setText(error)
        self.log.error(f"The firmware download failed: {error}")

    # The firmware browser (core's browse)

    def show_browser(self) -> None:
        self.browser = browse.Browser(browse.places(self.user_home, self.roots), firmware.SUFFIXES,
                                      path=browse.remembered(self.settings, BROWSED))
        self.browse_pane.status.setText("")
        self.show_pane(self.browse_pane)
        self.show_browse()

    def show_browse(self) -> None:
        path = self.browser.path if self.browser is not None else None
        self.browse_pane.summary.setText(private(path) if path is not None else
                                         "Where is the firmware file? Open a place, then the folder it is in.")
        self.browse_pane.list.set_items(self.browser.rows() if self.browser is not None else [])
        self.focus_list(self.browse_pane)
        self.update_legend()

    def browse_picked(self, key: str) -> None:
        if self.browser is None:
            return
        picked = self.browser.open(key)
        if picked is None:
            self.show_browse()
            return
        try:
            firmware.take(picked, self.home)
        except firmware.FirmwareError as error:
            self.browse_pane.status.setText(str(error))
            return
        browse.remember(self.settings, BROWSED, picked.parent)
        self.log.info(f"Firmware taken from a file: {firmware.describe(firmware.read(self.home) or b'')}.")
        self.leave_browser()
        self.firmware_pane.status.setText("Your file is the camera's firmware now.")

    def leave_browser(self) -> None:
        self.browser = None
        self.show_firmware()
        self.show_pane(self.firmware_pane)
        self.firmware_card.setFocus()

    # The Bandwidth card

    def bandwidth(self) -> str:
        value = str(self.settings.value(BANDWIDTH_KEY, loader.DEFAULT_BANDWIDTH))
        return value if value in loader.BANDWIDTHS else loader.DEFAULT_BANDWIDTH

    def show_bandwidth(self) -> None:
        chosen = self.bandwidth()
        self.bandwidth_card.set_text(BANDWIDTH_NAMES[chosen].split(":")[0])
        self.bandwidth_pane.summary.setText("What the firmware asks of the USB controller.")
        self.bandwidth_pane.list.set_items([(key, ("✓ " if key == chosen else "") + text)
                                            for key, text in BANDWIDTH_NAMES.items()])

    def set_bandwidth(self, key: str) -> None:
        self.settings.setValue(BANDWIDTH_KEY, key)
        self.show_bandwidth()
        self.bandwidth_pane.status.setText("It counts from the next load." if not (
            self.camera and self.camera.state == camera.READY_STATE) else
            "It counts from the next load: unplug the camera, plug it in again and load it.")
        self.log.info(f"Bandwidth: {key}.")

    def exit_app(self) -> None:
        """View: while the app keeps the picture, a second press within five seconds exits (the picture goes dark)."""
        if self.kept is not None and not self.close_asked:
            self.close_asked = True
            self.confirm_timer.start()
            self.camera_pane.status.setText("Press View again to exit: the camera's picture goes dark when the app "
                                            "closes.")
            self.update_legend()
            return
        self.close()

    def _confirm_over(self) -> None:
        self.confirm_timer.stop()
        if self.close_asked:
            self.close_asked = False
            if self.camera_pane.status.text().startswith("Press View again"):
                self.camera_pane.status.setText(KEPT)
            self.update_legend()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        self.confirm_timer.stop()
        self.live.stop()
        self.release_picture()
        super().closeEvent(event)
