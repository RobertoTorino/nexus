# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py): it opens on the portable window with the header's battery, date and time, fits the
handheld's screen, B goes back and View exits; A on the Camera card does the camera's next step (look, Allow access,
load, look again); the Firmware card downloads or takes a file; the Bandwidth card picks. Fakes stand in for the
camera, Windows' prompt and the download."""

from __future__ import annotations

import re
import time

from PyQt6.QtCore import QObject, QSettings, pyqtSignal
from PyQt6.QtGui import QImage

from bc250_core import portable
from bc250_core.portable import EXIT, INFO as INFO_ITEM, VIEW
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private
from usb_hd_cam import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, camera, firmware, loader
from usb_hd_cam.camera import Camera
from usb_hd_cam.devices import Device, Speed
from usb_hd_cam.main_window import MainWindow
from usb_hd_cam.modes import Mode

HUB = "USB\\VID_0BDA&PID_0411\\6&1&0&2"
BOOT_ID = "USB\\VID_05A9&PID_0580\\7&1&0&1"
FAST = Speed(True, True)


class FakePad:
    def events(self):
        return []

    def close(self):
        pass

    def names(self):
        return []


def cam(state: str, service: str = "", webcam: str = "", speed: Speed | None = FAST, video: str = "") -> Camera:
    instance = BOOT_ID if state != camera.READY_STATE else BOOT_ID.replace("0580", "058C")
    return Camera(state, Device(instance, service, 0, HUB, 1, ""), speed, webcam, video)


NO_DRIVER = cam(camera.NO_DRIVER)
BOOT = cam(camera.BOOT_LOADER, "WinUSB")
VIDEO_ID = "USB\\VID_05A9&PID_058C&MI_00\\8&1&0&0000"
READY = cam(camera.READY_STATE, "usbccgp", "USB Camera-OV580", video=VIDEO_ID)


class Kept:
    """The webcam's driver as picture.keep() hands it over: closed when the app lets go."""

    def __init__(self, log: list):
        self.log = log

    def close(self):
        self.log.append("closed")


def make(qapp, tmp_path, **fakes):
    settings = QSettings(str(tmp_path / "hdcam.ini"), QSettings.Format.IniFormat)
    window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False),
                        home=tmp_path / "firmware", settings=settings, roots=lambda: [tmp_path],
                        user_home=tmp_path, **fakes)
    portable.scale((1280, 720))
    window.resize(1280, 720)
    window.show()
    qapp.processEvents()
    window.start()
    return window


def settle(qapp, window) -> None:
    """Until the window's workers are done and their signals arrived."""
    end = time.monotonic() + 5
    while time.monotonic() < end:
        qapp.processEvents()
        if not window.camera_worker.busy and not window.firmware_worker.busy and not window.shot_worker.busy \
                and not window.step:
            qapp.processEvents()
            return
        time.sleep(0.01)
    raise AssertionError("a worker did not finish")


def press_a(qapp, window) -> None:
    window.a_action()
    settle(qapp, window)


def legend(window) -> list[tuple[str, str]]:
    return window.legend.items


def test_the_window_opens_with_the_suites_header(qapp, tmp_path):
    window = make(qapp, tmp_path)
    assert window.header.title.text() == APP_NAME and window.header.version.text() == __version__
    assert re.fullmatch(r"\w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d  \|  82%", window.header.status.text())
    assert legend(window)[0] == ("A", "Look for it") and legend(window)[-1] == EXIT
    assert INFO_ITEM in legend(window)          # the pane's information icon, on Menu
    window.close()


def test_the_window_fits_the_handhelds_screen(qapp, tmp_path):
    window = make(qapp, tmp_path)
    assert window.minimumSizeHint().height() <= 720 and window.height() == 720
    window.close()


def test_b_goes_back_and_view_exits(qapp, tmp_path, monkeypatch):
    """The suite's buttons: B goes back (with nowhere to go, nothing happens) and View exits the app."""
    window = make(qapp, tmp_path)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("back")
    assert closed == []
    window.on_action("view")
    assert closed == [True]


def test_nothing_is_looked_for_before_a(qapp, tmp_path):
    looked = []
    window = make(qapp, tmp_path, find=lambda: looked.append(True) or [])
    qapp.processEvents()
    assert looked == []
    press_a(qapp, window)
    assert looked == [True]
    assert "Not found" in window.camera_pane.status.text() and legend(window)[0] == ("A", "Look again")
    window.close()


def test_the_camera_from_boot_loader_to_webcam(qapp, tmp_path):
    """A, A, A: found without a driver, Allow access (then found with WinUSB), loaded (a webcam)."""
    state = {"camera": NO_DRIVER}
    allowed, loaded = [], []

    def allow(instance):
        allowed.append(instance)
        state["camera"] = BOOT
        return ""

    def load(boot, data, bandwidth, **kwargs):
        loaded.append((boot.instance, data, bandwidth))
        state["camera"] = READY
        return loader.Outcome(True, "The PS5 HD Camera is ready: apps list it as \"USB Camera-OV580\".", READY)

    firmware.store(b"\x01" * 100, tmp_path / "firmware")
    kept = []
    window = make(qapp, tmp_path, find=lambda: [state["camera"]], allow=allow, load=load,
                  keep=lambda video: kept.append(video) or Kept(kept))
    press_a(qapp, window)
    assert window.camera.state == camera.NO_DRIVER and legend(window)[0] == ("A", "Allow access")
    assert "allows access" in window.camera_pane.status.text()
    press_a(qapp, window)
    assert allowed == [BOOT_ID]
    assert window.camera.state == camera.BOOT_LOADER and legend(window)[0] == ("A", "Load the firmware")
    press_a(qapp, window)
    assert loaded == [(BOOT_ID, b"\x01" * 100, "full")]
    assert window.camera.state == camera.READY_STATE and "ready" in window.camera_pane.status.text()
    assert kept == [VIDEO_ID] and "leave it open" in window.camera_pane.status.text()
    assert legend(window)[0] == ("A", "Look again")
    window.close()
    assert kept == [VIDEO_ID, "closed"]     # closing the app lets the webcam go


def test_a_declined_prompt_says_so(qapp, tmp_path):
    window = make(qapp, tmp_path, find=lambda: [NO_DRIVER], allow=lambda instance: "Windows' prompt was declined.")
    press_a(qapp, window)
    press_a(qapp, window)
    assert window.camera_pane.status.text() == "Windows' prompt was declined."
    assert window.camera.state == camera.NO_DRIVER
    window.close()


def test_no_firmware_yet(qapp, tmp_path):
    window = make(qapp, tmp_path, find=lambda: [BOOT], load=lambda *a, **k: None)
    press_a(qapp, window)
    press_a(qapp, window)
    assert "No firmware yet" in window.camera_pane.status.text()
    window.close()


def test_a_failed_load_says_why_after_looking_again(qapp, tmp_path):
    firmware.store(b"\x01", tmp_path / "firmware")
    window = make(qapp, tmp_path, find=lambda: [BOOT],
                  load=lambda *a, **k: loader.Outcome(False, "The camera did not come back."))
    press_a(qapp, window)
    press_a(qapp, window)
    assert window.camera_pane.status.text() == "The camera did not come back."
    assert window.camera.state == camera.BOOT_LOADER
    window.close()


def test_a_slow_port_and_a_ps4_camera_are_named(qapp, tmp_path):
    window = make(qapp, tmp_path, find=lambda: [cam(camera.BOOT_LOADER, "WinUSB", speed=Speed(False, True))])
    press_a(qapp, window)
    assert "USB 3" in window.camera_pane.status.text()
    window.close()
    window = make(qapp, tmp_path, find=lambda: [cam(camera.PS4, "WinUSB")], load=lambda *a, **k: None)
    press_a(qapp, window)
    press_a(qapp, window)                   # A on a PS4 Camera looks again, never loads
    assert "PS4 Camera" in window.camera_pane.status.text() and legend(window)[0] == ("A", "Look again")
    window.close()


def test_the_firmware_download(qapp, tmp_path):
    def download():
        return firmware.store(b"\x02" * 10, tmp_path / "firmware")
    window = make(qapp, tmp_path, download=download)
    window.firmware_card.setFocus()
    qapp.processEvents()
    assert legend(window)[:2] == [("A", "Download"), ("X", "Pick a file")]
    press_a(qapp, window)
    assert "Downloaded and checked" in window.firmware_pane.status.text()
    assert legend(window)[0] == ("A", "Download again")
    window.close()


def test_a_failed_download_says_why(qapp, tmp_path):
    def download():
        raise firmware.FirmwareError("The download from github.com failed: offline.")
    window = make(qapp, tmp_path, download=download)
    window.firmware_card.setFocus()
    press_a(qapp, window)
    assert window.firmware_pane.status.text() == "The download from github.com failed: offline."
    window.close()


def test_an_own_file_is_picked_in_the_browser(qapp, tmp_path):
    folder = tmp_path / "files"
    folder.mkdir()
    (folder / "camera.bin").write_bytes(b"\x03" * 20)
    (folder / "notes.txt").write_text("not firmware")
    window = make(qapp, tmp_path)
    window.firmware_card.setFocus()
    window.x_action()
    assert window.panes.currentWidget() is window.browse_pane
    window.browse_picked(f"dir:{tmp_path}")
    window.browse_picked(f"dir:{folder}")
    keys = list(window.browse_pane.list.pills)
    assert f"file:{folder / 'camera.bin'}" in keys and not any("notes" in key for key in keys)
    window.browse_picked(f"file:{folder / 'camera.bin'}")
    assert firmware.read(tmp_path / "firmware") == b"\x03" * 20
    assert window.panes.currentWidget() is window.firmware_pane
    window.close()


def test_b_in_the_browser_goes_up_then_out(qapp, tmp_path):
    window = make(qapp, tmp_path)
    window.firmware_card.setFocus()
    window.x_action()
    window.browse_picked(f"dir:{tmp_path}")
    window.on_back()
    assert window.panes.currentWidget() is window.browse_pane and window.browser.path is None
    window.on_back()
    assert window.panes.currentWidget() is window.firmware_pane
    window.close()


def test_the_bandwidth_is_picked_and_used(qapp, tmp_path):
    loaded = []
    firmware.store(b"\x01", tmp_path / "firmware")
    window = make(qapp, tmp_path, find=lambda: [BOOT],
                  load=lambda boot, data, bandwidth, **k: loaded.append(bandwidth) or loader.Outcome(False, "no"))
    assert "✓" in window.bandwidth_pane.list.pills["full"].label.text()
    window.set_bandwidth("reduced")
    assert "✓" in window.bandwidth_pane.list.pills["reduced"].label.text()
    assert window.settings.value("bandwidth") == "reduced"
    window.camera_card.setFocus()
    press_a(qapp, window)
    press_a(qapp, window)
    assert loaded == ["reduced"]
    window.close()


def test_version_is_the_single_source():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__ == INFO.version


def test_icons_are_beside_the_package():
    assert LOGO_PATH.is_file() and LOGO_PATH.name == f"{APP_ID}.webp"
    assert (ROOT / "images" / f"{APP_ID}-128.png").is_file()
    assert re.fullmatch(r"[A-Za-z0-9-]+", EXE_NAME)


def test_a_ready_camera_found_later_is_kept_too(qapp, tmp_path):
    """The camera loaded before the app opened: A looks, and the app keeps its picture; A again opens it anew."""
    kept = []
    window = make(qapp, tmp_path, find=lambda: [READY], keep=lambda video: kept.append(video) or Kept(kept))
    press_a(qapp, window)
    assert kept == [VIDEO_ID] and window.kept is not None
    assert "Apps list it as" in window.camera_pane.status.text() and "leave it open" in window.camera_pane.status.text()
    assert ("Picture", "Auto exposure, while the app is open") in rows(window)
    press_a(qapp, window)
    assert kept == [VIDEO_ID, "closed", VIDEO_ID]
    window.close()


def test_a_picture_that_cannot_be_set_says_so(qapp, tmp_path):
    def refuse(video):
        raise OSError("The webcam kept its own exposure.")
    window = make(qapp, tmp_path, find=lambda: [READY], keep=refuse)
    press_a(qapp, window)
    assert "could not be set" in window.camera_pane.status.text() and window.kept is None
    assert ("Picture", "The camera's own exposure: dark") in rows(window)
    window.close()


def test_view_asks_again_while_the_picture_is_kept(qapp, tmp_path, monkeypatch):
    kept = []
    window = make(qapp, tmp_path, find=lambda: [READY], keep=lambda video: kept.append(video) or Kept(kept))
    press_a(qapp, window)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.exit_app()
    assert closed == [] and legend(window) == [(VIEW, "Press again to exit")]
    assert "goes dark" in window.camera_pane.status.text()
    window._confirm_over()                  # five seconds without a second press
    assert legend(window)[-1] == EXIT and not window.close_asked
    window.exit_app()
    window.exit_app()
    assert closed == [True]


def rows(window) -> list[tuple[str, str]]:
    grid = window.camera_pane.grid
    cells = [grid.itemAt(i).widget().text() for i in range(grid.count())]
    return list(zip(cells[0::2], cells[1::2]))


class FakePreview(QObject):
    """The camera's picture without a camera: what start() was asked for, and pictures and failures sent by hand."""

    picture = pyqtSignal(QImage)
    failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.started: list[str] = []
        self.running = False

    def start(self, mode) -> str:
        self.started.append(mode.key)
        self.running = True
        return ""

    def stop(self):
        self.running = False

    def fail(self, text: str) -> None:
        """As Preview does: it stops, then says why."""
        self.running = False
        self.failed.emit(text)


class FakeRecording(QObject):
    """A recording without an encoder: what start() was asked for and the sizes of the pictures added; written()
    ends it as Windows does once the file is written."""

    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.started: list[tuple] = []
        self.added: list[tuple[int, int]] = []
        self.running = self.busy = False

    def start(self, path, width, height) -> str:
        self.started.append((path, width, height))
        self.running = self.busy = True
        return ""

    def add(self, image) -> None:
        if self.running:
            self.added.append((image.width(), image.height()))

    def seconds(self) -> int:
        return 75 if self.running else 0

    def stop(self, wait_s: float = 0.0) -> None:
        self.running = False

    def written(self) -> None:
        self.busy = False
        self.finished.emit(str(self.started[-1][0]))


MODES = [Mode(1920, 1080, 30), Mode(1280, 800, 60), Mode(2560, 800, 30), Mode(1920, 1080, 15)]


def picture_window(qapp, tmp_path, found=None):
    live = FakePreview()
    kept = []
    window = make(qapp, tmp_path, find=lambda: found if found is not None else [READY],
                  keep=lambda video: kept.append(video) or Kept(kept), live=live, camera_modes=lambda: MODES,
                  recording=FakeRecording(), pictures=lambda: tmp_path / "Pictures", videos=lambda: tmp_path / "Videos")
    return window, live


def full_screen(qapp, window):
    """The camera found (A on the Camera card), then A on the Picture card: the picture full screen."""
    press_a(qapp, window)
    window.picture_card.setFocus()
    qapp.processEvents()
    window.a_action()
    qapp.processEvents()


def frame(width: int = 64, height: int = 36) -> QImage:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(0xFF3366CC)
    return image


def test_the_picture_waits_for_a_webcam(qapp, tmp_path):
    window, live = picture_window(qapp, tmp_path, found=[BOOT])
    window.picture_card.setFocus()
    qapp.processEvents()
    assert legend(window)[:3] == [("A", "Start"), ("LB", "Mode before"), ("RB", "Next mode")]
    window.a_action()
    assert live.started == [] and "not a webcam yet" in window.picture_pane.status.text()
    window.close()




def test_the_picture_starts_full_screen_changes_mode_and_b_ends_it(qapp, tmp_path):
    window, live = picture_window(qapp, tmp_path)
    press_a(qapp, window)                                   # the Camera card: found, the picture kept
    window.picture_card.setFocus()
    qapp.processEvents()
    assert window.picture_pane.summary.text() == "1920 × 1080, 30 fps (one camera)"
    assert [m.key for m in window.modes] == ["1920x1080@30", "1280x800@60", "2560x800@30"]     # 15 fps: silent
    window.a_action()
    qapp.processEvents()
    assert live.started == ["1920x1080@30"] and window.full_screen
    assert not window.header.isVisible() and not window.picture_card.isVisible() and window.full.isVisible()
    assert window.full.hasFocus() and window.legend.isVisible()
    assert legend(window) == [("A", "Screenshot"), ("X", "Record"), ("Y", "Gray"), ("LB", "Mode −"),
                              ("RB", "Mode +"), ("LT", "Zoom −"), ("RT", "Zoom +"), INFO_ITEM,
                              portable.BACK, EXIT]
    image = frame()
    live.picture.emit(image)
    assert window.full.view.image.size() == image.size()            # a copy: Qt passes it by value
    assert window.full.summary.text() == "1920 × 1080, 30 fps (one camera)  |  1x"
    window.step_mode(1)                                     # RB: the next mode, the picture starts again in it
    assert live.started == ["1920x1080@30", "1280x800@60"] and window.settings.value("mode") == "1280x800@60"
    window.step_mode(-1)
    window.step_mode(-1)                                    # LB from the first: the last
    assert live.started[-1] == "2560x800@30" and window.full_screen
    window.on_back()                                        # B: the picture stops, the Picture card again
    qapp.processEvents()
    assert not live.running and not window.full_screen and window.header.isVisible()
    assert window.picture_card.hasFocus() and legend(window)[0] == ("A", "Start")
    window.close()


def test_the_full_screen_legend_fits_the_handhelds_screen(qapp, tmp_path):
    """Ten entries in the window's width, recording or not, in color or black and white."""
    window, live = picture_window(qapp, tmp_path)
    full_screen(qapp, window)
    for _ in range(2):
        for _ in range(2):
            qapp.processEvents()                            # the legend's new entries laid out
            assert window.legend.sizeHint().width() <= 1280     # its own margins included, full screen
            window.toggle_recording()
        window.toggle_gray()
    assert window.minimumSizeHint().height() <= 720
    window.close()


def test_a_failed_picture_stays_full_screen_so_another_mode_can_be_tried(qapp, tmp_path):
    window, live = picture_window(qapp, tmp_path)
    full_screen(qapp, window)
    live.fail("The camera sends nothing in this mode: choose another with LB or RB.")
    assert window.full_screen and "sends nothing" in window.full.status.text()
    assert window.full.view.image is None and "sends nothing" in window.full.view.text
    window.step_mode(1)
    assert live.running and live.started[-1] == "1280x800@60"
    window.close()


def test_a_screenshot_is_what_shows(qapp, tmp_path):
    window, live = picture_window(qapp, tmp_path)
    full_screen(qapp, window)
    window.a_action()
    assert window.full.status.text() == "There is no picture to save yet."
    live.picture.emit(frame(64, 36))
    window.zoom(1)                                          # RT: 1.5x
    window.toggle_gray()
    press_a(qapp, window)
    saved = list((tmp_path / "Pictures").glob("*.png"))
    assert len(saved) == 1 and saved[0].name.startswith(f"{APP_NAME} 20")
    shot = QImage(str(saved[0]))
    assert (shot.width(), shot.height()) == (43, 24) and shot.isGrayscale()
    assert window.full.status.text().startswith("Screenshot saved: ") and saved[0].name in window.full.status.text()
    press_a(qapp, window)                                   # a second one in the same second: its own file
    assert len(list((tmp_path / "Pictures").glob("*.png"))) == 2
    window.close()


def test_zoom_pan_and_black_and_white(qapp, tmp_path):
    window, live = picture_window(qapp, tmp_path)
    full_screen(qapp, window)
    live.picture.emit(frame(400, 200))
    window.act("right")                                     # at 1x there is nothing to move
    assert "Zoom in first" in window.full.status.text() and window.look.x == 0.5
    window.act("rt")                                        # RT, as the controller sends it
    window.act("rt")
    assert window.look.zoom == 2.0 and window.full.view.image.width() == 200
    assert window.full.summary.text().endswith("|  2x")
    window.act("right")                                     # the d-pad moves the zoomed picture, not the focus
    assert window.look.x > 0.5 and window.full.hasFocus()
    for _ in range(20):
        window.act("right")
    assert window.look.x == 0.75                            # never past the picture's edge
    window.full.view.dragged.emit(0.25, 0.0)                # a finger drags it back to the right
    assert window.look.x == 0.625
    for _ in range(6):
        window.act("rt")
    assert window.look.zoom == 4.0 and "largest, 4x" in window.full.status.text()
    window.act("lt")
    assert window.look.zoom == 3.0
    window.act("y")
    assert window.look.gray and window.full.view.image.isGrayscale() and legend(window)[2] == ("Y", "Color")
    assert window.settings.value("black_and_white", type=bool) is True
    assert window.full.summary.text().endswith("3x, black and white")
    window.close()
    again, _live = picture_window(qapp, tmp_path)           # black and white is kept for next time
    assert again.look.gray
    again.close()


def test_a_recording_of_what_shows(qapp, tmp_path):
    window, live = picture_window(qapp, tmp_path)
    full_screen(qapp, window)
    recording = window.recording
    window.act("x")
    path, width, height = recording.started[0]
    assert path.parent == tmp_path / "Videos" and path.suffix == ".mp4" and (width, height) == (1920, 1080)
    assert legend(window)[1] == ("X", "Stop") and window.full.recording.isVisible()
    assert window.full.recording.text() == "● 1:15"
    live.picture.emit(frame(1920, 1080))
    window.zoom(1)
    live.picture.emit(frame(1920, 1080))
    assert recording.added == [(1920, 1080), (1280, 720)]  # zoomed: the part that shows (scaled up by Recording)
    window.step_mode(1)                                     # a video keeps one mode
    assert live.started == ["1920x1080@30"] and "Stop the recording first" in window.full.status.text()
    window.act("x")
    assert not recording.running and window.full.status.text() == "Writing the video …"
    assert legend(window)[1] == ("X", "Record") and not window.full.recording.isVisible()
    recording.written()
    assert window.full.status.text() == f"Video saved: {private(path)}"
    window.close()


def test_b_while_recording_keeps_the_video(qapp, tmp_path):
    window, live = picture_window(qapp, tmp_path)
    full_screen(qapp, window)
    window.toggle_recording()
    window.on_back()
    assert not window.recording.running and not live.running and not window.full_screen
    assert window.picture_pane.status.text() == "Writing the video …"
    window.recording.written()
    assert window.picture_pane.status.text().startswith("Video saved: ")
    window.close()


def test_view_asks_again_while_recording(qapp, tmp_path, monkeypatch):
    window, live = picture_window(qapp, tmp_path)
    full_screen(qapp, window)
    window.toggle_recording()
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.exit_app()
    assert closed == [] and "the recording stops and is saved" in window.full.status.text()
    window._confirm_over()
    assert window.full.status.text() == "" and legend(window)[-1] == EXIT
    window.exit_app()
    window.exit_app()
    assert closed == [True]
