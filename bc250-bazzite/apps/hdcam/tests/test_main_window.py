# SPDX-License-Identifier: GPL-3.0-or-later
"""The window against a fake /sys, a fake preview and fake loads: its states, Allow access, the firmware, the load it
does by itself once per plug-in, and the preview's modes and views."""

from __future__ import annotations

import pytest
from conftest import FIRMWARE, plug, unplug
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QMessageBox

from usb_hdcam import access, controls, firmware, loader, main_window, runner
from test_controls import AUTO_WB, WB_TEMPERATURE, FakeKernel, open_fake
from test_modes import reported


class FakePreview(QObject):
    frame = pyqtSignal(QImage)
    failed = pyqtSignal(str)

    def __init__(self, listed=None):
        super().__init__()
        self.listed = reported() if listed is None else listed
        self.started = []
        self.running = False

    def modes(self, node):
        return list(self.listed)

    def start(self, node, mode):
        self.started.append((node, mode.key if mode else None))
        self.running = True
        return True

    def stop(self):
        self.running = False


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def make(qapp, tmp_path, monkeypatch):
    windows = []
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))

    def build(writable=True, rule=True, load=None, kernel=None, **kwargs):
        if rule:
            access.install(tmp_path / "root", run=lambda argv: None)
        loads = []

        def fake_load(boot, data, find, dev):
            loads.append((boot.port, data))
            return load(boot) if load else loader.Outcome(True, "ready")
        kernel = kernel or FakeKernel()
        window = main_window.MainWindow(sys_root=tmp_path / "sys", dev=tmp_path / "dev", rule_root=tmp_path / "root",
                                        load=fake_load, preview=FakePreview(), clock=Clock(),
                                        writable=lambda node: writable, open_controls=lambda node: open_fake(kernel),
                                        **kwargs)
        window.loads, window.warnings, window.kernel = loads, warnings, kernel
        windows.append(window)
        return window

    yield build
    for window in windows:
        window.shut_down()
        window.deleteLater()


def wait_load(qapp, window):
    import time
    end = time.monotonic() + 5
    while window.loading and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)
    assert not window.loading


def test_no_camera(make, tmp_path):
    window = make()
    assert window.badge.text() == "No camera" and not window.load_pill.isEnabled()
    assert "Unplug it and plug it in again" in window.picture.text() and "restart" in window.badge.toolTip()
    assert window.camera_box.value.text() == "—" and window.firmware_box.value.text() == "None"
    assert not window.access_box.isVisibleTo(window) and not window.preview_button.isEnabled()


def test_allow_access_is_offered_until_the_rule_is_there(make, tmp_path):
    commands = []

    def run_root(argv):
        commands.append(argv)
        access.install(tmp_path / "root", run=lambda a: None)
        return runner.Result(0, '{"error": ""}')
    window = make(rule=False, run_root=run_root)
    assert window.access_box.isVisibleTo(window)
    window.access_button.click()
    assert commands[0][0] == "pkexec" and commands[0][-1] == "install"
    assert not window.access_box.isVisibleTo(window) and window.warnings == []


def test_an_outdated_rule_is_offered_again(make, tmp_path):
    rule = tmp_path / "root/etc/udev/rules.d" / access.RULE
    rule.parent.mkdir(parents=True)
    rule.write_text("# an earlier rule\n")
    window = make(rule=False)
    assert window.access_box.isVisibleTo(window) and window.access_text.text() == main_window.ACCESS_OUTDATED


def test_allow_access_cancelled(make):
    window = make(rule=False, run_root=lambda argv: runner.Result(126, ""))
    window.allow_access()
    assert "canceled" in window.warnings[0] and window.access_box.isVisibleTo(window)


def test_boot_mode_needs_its_firmware(make, tmp_path):
    plug(tmp_path / "sys")
    window = make()
    assert window.badge.text() == "Needs its firmware" and window.camera_box.value.text() == "PS5 HD Camera"
    assert window.usb_box.value.text() == "5 Gbit/s" and not window.load_pill.isEnabled()


def test_a_camera_that_is_there_gets_no_restart_hint(make, tmp_path):
    plug(tmp_path / "sys")
    window = make()
    assert window.picture.text() == "The picture shows here once the camera is ready."


def test_boot_mode_without_access(make, tmp_path):
    plug(tmp_path / "sys")
    firmware.store("cfi-zey1", FIRMWARE)
    window = make(writable=False)
    assert window.badge.text() == "No access" and not window.load_pill.isEnabled()


def test_a_slow_port_is_flagged(make, tmp_path):
    plug(tmp_path / "sys", port="1-3", speed=480, bus=1)
    window = make()
    assert window.usb_box.value.text() == "480 Mbit/s" and "USB 3" in window.usb_box.toolTip()


def test_load_firmware_by_hand(make, tmp_path, qapp):
    plug(tmp_path / "sys")
    firmware.store("cfi-zey1", FIRMWARE)
    main_window.CameraSettings(main_window.INFO).set("autoload", False)
    window = make()
    assert window.badge.text() == "Waiting for its firmware" and window.load_pill.isEnabled()
    window.load_pill.click()
    assert window.badge.text() == "Loading the firmware"
    wait_load(qapp, window)
    assert window.loads == [("7-1", FIRMWARE)]


def test_bandwidth_setting(make, tmp_path, qapp, monkeypatch):
    plug(tmp_path / "sys")
    firmware.store("cfi-zey1", FIRMWARE)
    main_window.CameraSettings(main_window.INFO).set("autoload", False)
    sent = []
    monkeypatch.setattr(loader, "with_bandwidth", lambda data, bursts: sent.append(bursts) or data)
    window = make()
    assert window.bandwidth_combo.currentData() == "reduced"
    window.start_load()
    wait_load(qapp, window)
    window.bandwidth_combo.setCurrentIndex(window.bandwidth_combo.findData("full"))
    window.bandwidth_combo.activated.emit(window.bandwidth_combo.currentIndex())
    assert main_window.CameraSettings(main_window.INFO).get("bandwidth") == "full"
    window.start_load()
    wait_load(qapp, window)
    assert sent == [2, 3]


def test_a_failed_load_by_hand_is_shown(make, tmp_path, qapp):
    plug(tmp_path / "sys")
    firmware.store("cfi-zey1", FIRMWARE)
    main_window.CameraSettings(main_window.INFO).set("autoload", False)
    window = make(load=lambda boot: loader.Outcome(False, "It did not work."))
    window.start_load()
    wait_load(qapp, window)
    assert window.warnings == ["It did not work."]
    assert window.badge.text() == "Firmware not loaded" and window.badge.toolTip() == "It did not work."


def test_loads_by_itself_once_per_plug_in(make, tmp_path, qapp):
    plug(tmp_path / "sys")
    firmware.store("cfi-zey1", FIRMWARE)
    window = make(load=lambda boot: loader.Outcome(False, "No."))
    assert window.loads == []                       # the load service has the first seconds
    window.clock.now += main_window.AUTO_GRACE_S
    window.refresh()
    wait_load(qapp, window)
    assert window.loads == [("7-1", FIRMWARE)] and window.warnings == []        # quiet: in the state only
    assert window.badge.text() == "Firmware not loaded"
    window.clock.now += 10
    window.refresh()
    assert len(window.loads) == 1                   # not again for the same plug-in
    unplug(tmp_path / "sys")
    window.refresh()
    plug(tmp_path / "sys")
    window.refresh()
    window.clock.now += main_window.AUTO_GRACE_S
    window.refresh()
    wait_load(qapp, window)
    assert len(window.loads) == 2


def test_not_by_itself_when_switched_off(make, tmp_path):
    plug(tmp_path / "sys")
    firmware.store("cfi-zey1", FIRMWARE)
    window = make()
    window.autoload.setChecked(False)
    window.clock.now += 60
    window.refresh()
    assert window.loads == [] and not main_window.CameraSettings(main_window.INFO).get("autoload")


def test_download(make, monkeypatch, qapp):
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(firmware, "download", lambda model, home, get: firmware.store(model, FIRMWARE, home))
    window = make()
    window.download_button.click()
    end = __import__("time").monotonic() + 5
    while window.download_job.running and __import__("time").monotonic() < end:
        qapp.processEvents()
    qapp.processEvents()
    assert firmware.read("cfi-zey1") == FIRMWARE and window.firmware_box.value.text() == "Own file"


def test_download_failure_is_shown(make, monkeypatch, qapp):
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)

    def fail(model, home, get):
        raise firmware.FirmwareError("The download failed: offline.")
    monkeypatch.setattr(firmware, "download", fail)
    window = make()
    window.download()
    while window.download_job.running:
        qapp.processEvents()
    qapp.processEvents()
    assert window.warnings == ["The download failed: offline."]


def test_use_a_file(make, tmp_path):
    window = make()
    own = tmp_path / "firmware_fix.bin"
    own.write_bytes(FIRMWARE)
    window.use_path(own)
    assert firmware.read("cfi-zey1") == FIRMWARE and "Unknown file" in window.firmware_text.text()
    window.use_path(tmp_path / "missing.bin")
    empty = tmp_path / "empty.bin"
    empty.write_bytes(b"")
    window.use_path(empty)
    assert "could not be read" in window.warnings[0] and "was not used: The file is empty." in window.warnings[1]


def test_playstation_camera_gets_its_own_file(make, tmp_path):
    plug(tmp_path / "sys", port="7-1.1", hub="054c:0d0b")
    window = make()
    assert window.camera_box.value.text() == "PS4 Camera" and window.download_button.isEnabled()
    assert "github.com/psxdev/luke_firmwares" in window.download_button.toolTip()
    own = tmp_path / "ps4-camera.bin"
    own.write_bytes(FIRMWARE)
    window.use_path(own)
    assert firmware.read("ps4-camera") == FIRMWARE and firmware.read("cfi-zey1") is None


def test_ready_camera_and_its_preview(make, tmp_path):
    plug(tmp_path / "sys", product="058c", address=4, videos=(2,))
    window = make()
    assert window.badge.text() == "Ready" and window.video_box.value.text() == "video2"
    assert window.mode_combo.count() == 14 and window.mode_combo.currentData() == "1920x1080@30"
    assert not window.view_combo.isEnabled()        # one camera: no halves
    window.preview_button.click()
    assert window.preview.started == [("/dev/video2", "1920x1080@30")]
    assert window.preview_button.text() == "Stop preview"
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("3840x1080@30"))
    window.set_mode(window.mode_combo.currentIndex())
    assert window.preview.started[-1] == ("/dev/video2", "3840x1080@30") and window.view_combo.isEnabled()
    assert main_window.CameraSettings(main_window.INFO).get("mode") == "3840x1080@30"
    window.preview_button.click()
    assert not window.preview.running and window.preview_button.text() == "Start preview"


def test_views_of_a_stereo_frame(make, tmp_path):
    plug(tmp_path / "sys", product="058c", address=4, videos=(2,))
    main_window.CameraSettings(main_window.INFO).set("mode", "3840x1080@30")
    window = make()
    frame = QImage(3840, 1080, QImage.Format.Format_RGB32)
    frame.fill(QColor("blue"))
    for x in range(1920, 3840):
        frame.setPixelColor(x, 0, QColor("red"))
    window.preview.frame.emit(frame)
    assert window.shown_image().width() == 3840 and window.save_button.isEnabled()
    window.view_combo.setCurrentIndex(window.view_combo.findData("right"))
    window.set_view(window.view_combo.currentIndex())
    shown = window.shown_image()
    assert (shown.width(), shown.height()) == (1920, 1080) and shown.pixelColor(0, 0) == QColor("red")
    assert main_window.CameraSettings(main_window.INFO).get("view") == "right"


def test_unplugging_stops_the_preview(make, tmp_path):
    plug(tmp_path / "sys", product="058c", address=4, videos=(2,))
    window = make()
    window.preview_button.click()
    unplug(tmp_path / "sys")
    window.refresh()
    assert not window.preview.running and not window.preview_button.isChecked()
    assert window.badge.text() == "No camera" and window.mode_combo.count() == 0


def test_a_preview_failure_is_shown(make, tmp_path):
    plug(tmp_path / "sys", product="058c", address=4, videos=(2,))
    window = make()
    window.preview_button.click()
    window.preview.failed.emit("The camera is used by another app.")
    assert not window.preview_button.isChecked() and window.picture.text() == "The camera is used by another app."


def test_picture_settings(make, tmp_path):
    plug(tmp_path / "sys", product="058c", address=4, videos=(2,))
    window = make()
    assert window.controls_box.isEnabled() and len(window.control_rows) == 11
    control, slider, value, _name = window.control_rows[0x980900]
    assert control.name == "Brightness" and slider.value() == 4 and value.text() == "4"
    slider.setValue(7)
    assert window.kernel.values[0x980900] == 7 and value.text() == "7"
    assert main_window.CameraSettings(main_window.INFO).controls() == {"auto_exposure": 0, "brightness": 7}
    _c, temperature, _v, name = window.control_rows[WB_TEMPERATURE]
    assert not temperature.isEnabled() and not name.isEnabled()             # decided by the automatic white balance
    assert "does not let this be changed" in name.toolTip()
    _c, automatic, _v, _n = window.control_rows[AUTO_WB]
    automatic.setChecked(False)
    assert temperature.isEnabled() and name.isEnabled()
    _c, exposure, _v, _n = window.control_rows[0x9a0901]
    assert [exposure.itemText(i) for i in range(exposure.count())] == ["Auto Mode", "Shutter Priority Mode"]
    exposure.setCurrentIndex(exposure.findData(2))
    exposure.activated.emit(exposure.currentIndex())
    assert window.kernel.values[0x9a0901] == 2
    window.defaults_button.click()
    assert window.kernel.values[0x980900] == 4 and window.kernel.values[AUTO_WB] == 1 and slider.value() == 4
    assert window.kernel.values[0x9a0901] == 0 and exposure.currentData() == 0           # the app's default: Auto
    assert main_window.CameraSettings(main_window.INFO).controls() == {"auto_exposure": 0}


def test_auto_exposure_is_the_default_and_the_exposure_time_stays_grey(make, tmp_path):
    plug(tmp_path / "sys", product="058c", address=4, videos=(2,))
    window = make()
    assert window.kernel.values[0x9a0901] == 0                          # set at plug-in, before anything is chosen
    _c, widget, value, name = window.control_rows[0x9a0902]
    assert not any(part.isEnabled() for part in (widget, value, name))


def test_chosen_settings_come_back_at_the_next_plug_in(make, tmp_path):
    main_window.CameraSettings(main_window.INFO).set_controls({"brightness": 6, "gain": 8})
    plug(tmp_path / "sys", product="058c", address=4, videos=(2,))
    window = make()
    assert (window.kernel.values[0x980900], window.kernel.values[0x980913]) == (6, 8)
    assert window.control_rows[0x980913][1].value() == 8
    unplug(tmp_path / "sys")
    window.refresh()
    assert not window.controls_box.isEnabled() and window.control_rows == {}


def test_a_refused_setting_is_shown(make, tmp_path):
    plug(tmp_path / "sys", product="058c", address=4, videos=(2,))
    window = make(kernel=FakeKernel(refuse={0x980900}))
    window.control_rows[0x980900][1].setValue(8)
    assert "refused Brightness" in window.controls_text.text()
    assert main_window.CameraSettings(main_window.INFO).controls() == {"auto_exposure": 0}


def test_unreadable_settings(make, tmp_path):
    plug(tmp_path / "sys", product="058c", address=4, videos=(2,))

    def busy(*args):
        raise OSError(16, "Device or resource busy")
    window = make(kernel=busy)
    assert "could not be read: Device or resource busy" in window.controls_text.text()
    assert not window.controls_box.isEnabled()


def test_the_firmware_check_shows_green_for_a_known_file_orange_for_an_own_one(make, monkeypatch):
    from bc250_core.theme import GREY, STATE_COLORS
    window = make()
    colours = []
    monkeypatch.setattr(window.firmware_box, "set_colour", colours.append)
    window.refresh()
    assert colours[-1] == GREY and window.firmware_box.value.text() == "None"
    firmware.store("cfi-zey1", FIRMWARE)
    window.refresh()
    assert colours[-1] == STATE_COLORS["warn"] and window.firmware_box.value.text() == "Own file"
    assert "not a file the app knows" in window.firmware_text.text()
    assert firmware.sha256(FIRMWARE) in window.firmware_box.toolTip()
    monkeypatch.setitem(firmware.KNOWN, firmware.sha256(FIRMWARE),
                        firmware.Known("cfi-zey1", "21.01-03.20.00.04", "21.01", "0" * 40))
    window.refresh()
    assert colours[-1] == STATE_COLORS["ok"] and window.firmware_box.value.text() == "21.01"
    assert "it is the known file 21.01-03.20.00.04" in window.firmware_text.text()


def test_show_names_the_lens_of_each_half(make, tmp_path):
    plug(tmp_path / "sys", product="058c", address=4, videos=(2,))
    window = make()
    texts = {window.view_combo.itemData(i): window.view_combo.itemText(i) for i in range(window.view_combo.count())}
    assert texts == {"both": "Whole frame", "left": "Left half: the lens on your left",
                     "right": "Right half: the lens on your right"}
    assert "as you face the camera" in window.view_combo.toolTip()
