# SPDX-License-Identifier: GPL-3.0-or-later
import json
import sys
import tomllib
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QDialog, QMessageBox

from hdmi_cec import boot, main_window
from hdmi_cec.main_window import MainWindow
from hdmi_cec.runner import Result
from conftest import ACK, INFO, NACK, POWER_ON, TOPOLOGY_TV, UNCONFIGURED


KSCREEN = json.loads((Path(__file__).parent / "kscreen.json").read_text())       # the owner's board, 11-10-2026
TV_ANSWERS = json.loads((Path(__file__).parent / "tv_answers.json").read_text())  # the owner's TV, 11-10-2026


class FakeBoard:
    """cec-ctl, systemctl and kscreen-doctor as the board answers them; tv=False is the owner's board with CEC off
    in the TV: nothing acknowledges."""

    def __init__(self, tv=True, info=INFO, native=False, receiver=False, kscreen=True):
        self.tv, self.info, self.native, self.receiver = tv, info, native, receiver
        self.kscreen = json.loads(json.dumps(KSCREEN)) if kscreen else None
        self.watching = False
        self.calls = []

    @property
    def output(self):
        return self.kscreen["outputs"][0]

    def __call__(self, argv):
        self.calls.append(argv)
        if argv[0] == "kscreen-doctor":
            if self.kscreen is None:
                return Result(127, "kscreen-doctor: not found")
            if argv[1] == "-j":
                return Result(0, json.dumps(self.kscreen))
            _out, name, field, value = argv[1].split(".", 3)
            if field == "maxbpc":
                self.output["maxBpc"] = 0 if value == "automatic" else int(value)
            elif field == "mode":
                self.output["currentModeId"] = value
            return Result(0, "")
        if argv[0] == "systemctl" and argv[-1] == "bc250-hdmi-cec-watch.service":
            if "is-enabled" in argv:
                return Result(0, "enabled\n") if self.watching else Result(1, "disabled\n")
            if "enable" in argv or "disable" in argv:
                self.watching = "enable" in argv
            return Result(0, "")
        if argv[0] == "systemctl" and "try-restart" in argv:
            return Result(0 if self.native else 1, "")
        if argv[0] == "cec-ctl" and self.tv and "-s" in argv and not (self.receiver and argv[-1] == "5"):
            answer = TV_ANSWERS.get(" ".join(argv[4:]))
            if answer is not None:
                return Result(0, answer)
        if argv[0] == "systemctl":
            unit = argv[-1]
            if "is-enabled" in argv:
                return Result(0, "enabled\n") if self.native and unit == "cecd.service" else Result(1, "disabled\n")
            if "is-active" in argv:
                return Result(0, "active\n") if self.native else Result(3, "inactive\n")
            return Result(0 if self.native else 1, "")
        args = argv[1:]
        if len(args) == 2 or "--playback" in args:          # the adapter's state; configuring prints it too
            if "--playback" in args:                        # the adapter takes the name it is given
                self.info = INFO.replace("'Playback'", f"'{args[args.index('--osd-name') + 1]}'")
            return Result(0, self.info)
        if "--show-topology" in args:
            return Result(0, TOPOLOGY_TV if self.tv else self.info + "\n\tTopology:\n\n\t    1.0.0.0: Playback\n")
        if not self.tv:
            return Result(0, NACK)
        if "--give-device-power-status" in args:
            return Result(0, POWER_ON)
        if "--poll" in args and args[-1] == "5" and not self.receiver:
            return Result(0, NACK)
        return Result(0, ACK)

    def sent(self, option):
        return [c for c in self.calls if option in c]

    def target(self, option):
        """The logical address the first message with *option* went to."""
        call = self.sent(option)[0]
        return call[call.index("--to") + 1]


class FakeRoot:
    """pkexec with boot.py: does what boot.main would, in the test's /etc; cancel=True is a canceled password."""

    def __init__(self, etc_root, cancel=False):
        self.paths, self.cancel = boot.Paths(etc_root), cancel
        self.calls = []
        self.greeter = []

    def __call__(self, argv):
        assert argv[:3] == boot.command([])[:3] and argv[3] == str(Path(boot.__file__).resolve())
        args = argv[4:]
        self.calls.append(args)
        if self.cancel:
            return Result(126, "")
        if args[0] == "install":
            boot.install(self.paths, args[args.index("--name") + 1], "--wake" in args, run=lambda a: Result(0, ""))
        elif args[0] == "uninstall":
            boot.uninstall(self.paths, run=lambda a: Result(0, ""))
        else:
            self.greeter.append(args[1])
        return Result(0, '{"ok": true}\n')


@pytest.fixture(autouse=True)
def answer(monkeypatch):
    """Every question is answered Yes unless a test says otherwise, so no dialog waits for a click."""
    replies = {"value": QMessageBox.StandardButton.Yes, "asked": []}
    monkeypatch.setattr(QMessageBox, "question", lambda _p, _t, text, *a, **k: (replies["asked"].append(text),
                                                                                  replies["value"])[1])
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text, *a, **k: replies["asked"].append(text))
    return replies


@pytest.fixture
def make(qapp, dev_root, sys_root, etc_root, usr_root, tmp_path):
    made = []

    def build(board, terminal=None, run_root=None):
        w = MainWindow(dev_root, sys_root, tmp_path / "config", etc_root, usr_root, run=board,
                       terminal=terminal or (lambda cmd: None), listen=False,
                       run_root=run_root if run_root is not None else FakeRoot(etc_root))
        made.append(w)
        return w
    yield build
    for w in made:
        w.close()


def test_shows_the_adapter_and_tv(make):
    w = make(FakeBoard())
    assert w.adapter_box.value.text() == "DP-1"
    assert w.address_box.value.text() == "1.0.0.0"
    assert w.display_box.value.text() == "Mi TV"
    assert w.badge.text() == "Not checked"
    assert w.on_button.isEnabled()


def test_opening_sends_nothing_on_the_bus(make):
    board = FakeBoard()
    w = make(board)
    assert [c[1:] for c in board.calls if c[0] == "cec-ctl"] == [["-d", w.adapter.device]]


def test_no_adapter(make, dev_root):
    (dev_root / "cec0").unlink()
    w = make(FakeBoard())
    assert w.badge.text() == "No CEC adapter" and w.adapter_box.value.text() == "None"
    assert "DP-to-HDMI" in w.adapter_note.text()
    assert not w.on_button.isEnabled() and not w.check_button.isEnabled()


def test_no_display(make):
    w = make(FakeBoard(info=INFO.replace("1.0.0.0", "f.f.f.f")))
    assert w.badge.text() == "No display seen" and w.address_box.value.text() == "None"


def test_turn_tv_on_wakes_and_switches(make):
    board = FakeBoard()
    w = make(board)
    w.tv_on()
    assert board.sent("--image-view-on") and board.sent("--active-source")
    assert board.sent("--active-source")[0][-1] == "phys-addr=1.0.0.0"
    assert w.badge.text() == "TV answers" and "BC-250" in w.result.text()


def test_tv_that_does_not_answer(make):
    board = FakeBoard(tv=False)
    w = make(board)
    w.tv_on()
    assert board.sent("--image-view-on") and not board.sent("--active-source")
    assert w.badge.text() == "TV does not answer" and "settings" in w.result.text()
    w.check_tv()
    assert w.power_box.value.text() == "No answer"


def test_check_tv_and_the_receiver(make):
    board = FakeBoard(receiver=True)
    w = make(board)
    w.check_tv()
    assert w.power_box.value.text() == "On" and "AV receiver" in w.result.text()
    w.press("volume-up")
    assert board.target("ui-cmd=volume-up") == "5" and board.sent("--user-control-released")


def test_volume_goes_to_the_tv_without_a_receiver(make):
    board = FakeBoard()
    w = make(board)
    w.check_tv()
    w.press("mute")
    assert board.target("ui-cmd=mute") == "0"


def test_unconfigured_adapter_is_configured_once(make):
    board = FakeBoard(info=UNCONFIGURED)
    w = make(board)
    w.tv_standby()
    w.tv_standby()
    assert len(board.sent("--playback")) == 1 and len(board.sent("--standby")) == 2


def test_topology_dialog(make, monkeypatch):
    shown = []
    monkeypatch.setattr(main_window.TextDialog, "exec", lambda self: shown.append(self.terminal.toPlainText()))
    make(FakeBoard()).show_topology()
    assert "0.0.0.0  TV" in shown[0] and "No device answered" not in shown[0]
    make(FakeBoard(tv=False)).show_topology()
    assert "No device answered" in shown[1]


def test_automatic_needs_native_mode(make):
    w = make(FakeBoard())
    assert not w.native_button.isHidden() and "Off" in w.mode_label.text()
    assert not any(box.isEnabled() for box in w.boxes.values())
    assert w.boxes["uinput"].isChecked() and not w.boxes["wake_tv"].isChecked()      # cecd's defaults


def test_native_mode_saves_and_reloads(make, tmp_path):
    board = FakeBoard(native=True)
    w = make(board)
    assert w.native_button.isHidden() and "cecd is running" in w.mode_label.text()
    w.boxes["wake_tv"].setChecked(True)
    fragment = tmp_path / "config/cecd/config.d/99-bc250-hdmi-cec.toml"
    assert tomllib.loads(fragment.read_text())["wake_tv"] is True
    assert ["systemctl", "--user", "kill", "-s", "HUP", "cecd.service"] in board.calls
    w.refresh()
    assert w.boxes["wake_tv"].isChecked()


def test_use_native_runs_ujust(make, monkeypatch):
    ran = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    w = make(FakeBoard(), terminal=ran.append)
    w.use_native()
    assert ran == ["ujust cec-mode native"]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    w.use_native()
    assert len(ran) == 1


def test_key_tester(make):
    w = make(FakeBoard(native=True))
    for _ in range(main_window.KEYS_SHOWN + 3):
        w.key_pressed(0x41, 0)
    assert w.keys.count() == main_window.KEYS_SHOWN
    assert "volume-up" in w.keys.item(0).text() and "from the TV" in w.keys.item(0).text()


def test_picture_choice_reads_the_system(make):
    w = make(FakeBoard())
    assert w.picture_buttons["nothing"].isChecked() and w.picture_buttons["8bit"].isEnabled()
    board = FakeBoard()
    board.output["maxBpc"] = 8
    assert make(board).picture_buttons["8bit"].isChecked()


def test_eight_bit_and_back(make):
    board = FakeBoard()
    w = make(board)
    w.picture_buttons["8bit"].click()
    assert board.output["maxBpc"] == 8 and w.picture_buttons["8bit"].isChecked()
    assert ["kscreen-doctor", "output.DP-1.maxbpc.8"] in board.calls
    w.picture_buttons["nothing"].click()
    assert board.output["maxBpc"] == 0 and ["kscreen-doctor", "output.DP-1.maxbpc.automatic"] in board.calls


def test_restart_installs_the_watcher(make, tmp_path):
    board = FakeBoard()
    board.output["maxBpc"] = 8
    w = make(board)
    w.picture_buttons["restart"].click()
    unit = tmp_path / "config/systemd/user/bc250-hdmi-cec-watch.service"
    assert board.watching and unit.is_file() and "-m hdmi_cec.watcher --restart-picture" in unit.read_text()
    assert board.output["maxBpc"] == 0                                          # full color again
    assert ["systemctl", "--user", "restart", "bc250-hdmi-cec-watch.service"] in board.calls
    w.close()
    assert make(board).picture_buttons["restart"].isChecked()
    make(board).picture_buttons["8bit"].click()
    assert not board.watching and not unit.exists() and board.output["maxBpc"] == 8


def test_a_choice_set_by_the_user_is_left_alone(make):
    board = FakeBoard()
    board.output["maxBpc"] = 10                                                 # set in Display settings
    w = make(board)
    w.picture_buttons["nothing"].click()
    assert board.output["maxBpc"] == 10 and not [c for c in board.calls if c[0] == "kscreen-doctor" and c[1] != "-j"]


def test_without_kscreen_the_choice_is_off(make):
    w = make(FakeBoard(kscreen=False))
    assert not any(b.isEnabled() for b in w.picture_buttons.values())
    assert "Game Mode" in w.picture_note.text()


def test_standby_asks_first_only_without_a_fix(make, answer):
    board = FakeBoard()
    w = make(board)
    answer["value"] = QMessageBox.StandardButton.No
    w.tv_standby()
    assert not board.sent("--standby") and "stays black" in answer["asked"][0]
    w.picture_buttons["8bit"].click()
    answer["asked"].clear()
    w.tv_standby()
    assert board.sent("--standby") and answer["asked"] == []


def test_tv_info(make, monkeypatch):
    shown = []
    monkeypatch.setattr(main_window.TableDialog, "exec",
                        lambda self: shown.append({self.table.item(r, 0).text(): self.table.item(r, 1).text()
                                                   for r in range(self.table.rowCount())}))
    make(FakeBoard()).show_tv_info()
    rows = shown[0]
    assert rows["CEC version"] == "1.4" and rows["Power status"] == "yes (on)"
    assert rows["Its name and type"] == 'name "Game", type TV, HDMI address 0.0.0.0'
    assert rows["Vendor ID"] == '0x6d746b = "mtk"' and rows["Menu language"] == "English"
    assert rows["CEC 2.0 feature list"] == "not supported"
    assert rows["Lip-sync delay"] == "no answer (a CEC 2.0 feature)"
    assert rows["AV receiver or soundbar"] == "none connected"


def test_pause_option(make, tmp_path):
    board = FakeBoard()
    w = make(board)
    w.pause_box.setChecked(True)
    unit = tmp_path / "config/systemd/user/bc250-hdmi-cec-watch.service"
    assert board.watching and "--pause-media" in unit.read_text() and "--restart-picture" not in unit.read_text()
    w.picture_buttons["restart"].click()
    assert "--pause-media --restart-picture" not in unit.read_text()            # the app's own order
    assert "--restart-picture --pause-media" in unit.read_text() and w.pause_box.isChecked()
    w.pause_box.setChecked(False)
    assert "--pause-media" not in unit.read_text() and w.picture_buttons["restart"].isChecked()
    w.picture_buttons["nothing"].click()
    assert not board.watching and not unit.exists()


def test_name_without_cecd(make, tmp_path):
    board = FakeBoard()
    w = make(board)
    assert w.name_edit.text() == "BC-250"
    w.name_edit.setText("Gaming PC")
    w.save_name()
    assert ["cec-ctl", "-d", w.adapter.device, "--playback", "--osd-name", "Gaming PC"] in board.calls
    assert board.sent("name=Gaming PC") and "Gaming PC" in w.result.text()
    assert 'osd_name = "Gaming PC"' in (tmp_path / "config/cecd/config.d/99-bc250-hdmi-cec.toml").read_text()
    w.name_edit.setText("Ünïcode")
    w.save_name()
    assert "plain letters" in w.result.text()


def test_name_with_cecd_restarts_it(make):
    board = FakeBoard(native=True)
    w = make(board)
    w.name_edit.setText("BC-250 Lounge")
    w.save_name()
    assert ["systemctl", "--user", "try-restart", "cecd.service"] in board.calls and not board.sent("--playback")


def test_remote_buttons(make, tmp_path, monkeypatch):
    board = FakeBoard(native=True)
    w = make(board)

    def pick(dialog):
        combo = dialog.combos["f2"]
        combo.setCurrentIndex(combo.findData("KEY_F12"))                      # red: Steam screenshot
        dialog.combos["f3"].setCurrentIndex(dialog.combos["f3"].findData(None))
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(main_window.RemoteDialog, "exec", pick)
    w.edit_remote()
    table = tomllib.loads((tmp_path / "config/cecd/config.d/99-bc250-hdmi-cec.toml").read_text())["mappings"]
    assert table["f2"] == 88 and "f3" not in table and table["select"] == 28 and len(table) == 73
    assert ["systemctl", "--user", "try-restart", "cecd.service"] in board.calls

    seen = []
    monkeypatch.setattr(main_window.RemoteDialog, "exec", lambda d: (seen.append(d.choices()),
                                                                     QDialog.DialogCode.Rejected)[1])
    w.edit_remote()
    assert seen[0]["f2"] == "KEY_F12" and seen[0]["f3"] is None and seen[0]["select"] == ""


def test_remote_buttons_offers_every_button_of_cecd(make, monkeypatch):
    sizes = []
    monkeypatch.setattr(main_window.RemoteDialog, "exec", lambda d: (sizes.append(d.table.rowCount()),
                                                                     QDialog.DialogCode.Rejected)[1])
    make(FakeBoard(native=True)).edit_remote()
    assert sizes == [74]


def test_the_note_follows_the_mode(make):
    board = FakeBoard()
    w = make(board)
    assert "at 8 bits" not in w.picture_note.text() and "another cause" not in w.picture_note.text()   # 1080p120
    board.output["currentModeId"] = "1"                                                                 # 4K60
    w.refresh_picture()
    assert "3840 × 2160 at 60 Hz" in w.picture_note.text() and "8 bits does not help" in w.picture_note.text()
    board.output["currentModeId"] = "23"                                                                # 1080p60
    w.refresh_picture()
    assert "another cause" in w.picture_note.text()


def test_two_adapters_uses_the_one_with_a_display(make, dev_root):
    (dev_root / "cec1").touch()

    class TwoAdapters(FakeBoard):
        def __call__(self, argv):
            if argv[0] == "cec-ctl" and argv[1:] == ["-d", str(dev_root / "cec0")]:
                return Result(0, INFO.replace("1.0.0.0", "f.f.f.f"))
            return super().__call__(argv)
    w = make(TwoAdapters())
    assert w.adapter.device == str(dev_root / "cec1")
    assert f"Also here: {dev_root / 'cec0'}" in w.adapter_note.text()


def test_an_adapter_named_playback_gets_the_boards_name(make):
    board = FakeBoard()                         # configured by a plain cec-ctl --playback: the TV lists "Playback"
    w = make(board)
    assert w.adapter.osd_name == "Playback"
    w.tv_standby()
    w.tv_standby()
    assert len(board.sent("--playback")) == 1 and w.adapter.osd_name == "BC-250"
    assert board.sent("name=BC-250")                    # the TV hears the new name at once


def test_cecd_names_the_adapter_itself(make):
    board = FakeBoard(native=True)
    make(board).tv_standby()
    assert not board.sent("--playback")


# --- At boot ------------------------------------------------------------------------------------------------------

def test_boot_is_off_and_asks_nothing(make):
    w = make(FakeBoard())
    assert not w.boot_box.isChecked() and w.wake_box.isChecked() and w.wake_box.isEnabled()
    assert not w.boot_update_button.isVisible() and "Off" in w.boot_note.text()
    assert not w.run_root.calls


def test_boot_on_with_wake_asks_once(make, etc_root):
    w = make(FakeBoard())
    w.boot_box.setChecked(True)
    assert w.run_root.calls == [["install", "--name", "BC-250", "--wake"]]
    assert boot.installed(boot.Paths(etc_root)) == boot.Config("BC-250", True)
    assert w.boot_box.isChecked() and "On:" in w.boot_note.text() and "turns it on" in w.boot_note.text()
    w.wake_box.setChecked(False)
    assert w.run_root.calls[-1] == ["install", "--name", "BC-250"]
    assert boot.installed(boot.Paths(etc_root)) == boot.Config("BC-250", False)
    w.boot_box.setChecked(False)
    assert w.run_root.calls[-1] == ["uninstall"] and boot.installed(boot.Paths(etc_root)) is None
    assert not w.wake_box.isChecked()                       # the choice it gets installed with next time


def test_boot_shows_what_is_installed(make, etc_root):
    boot.install(boot.Paths(etc_root), "BC-250", False, run=lambda a: Result(0, ""))
    w = make(FakeBoard())
    assert w.boot_box.isChecked() and not w.wake_box.isChecked() and not w.run_root.calls


def test_a_cancelled_password_changes_nothing(make, etc_root, answer):
    w = make(FakeBoard(), run_root=FakeRoot(etc_root, cancel=True))
    w.boot_box.setChecked(True)
    assert not w.boot_box.isChecked() and boot.installed(boot.Paths(etc_root)) is None
    assert "Not authorized" in answer["asked"][-1]


def test_another_version_or_name_offers_update(make, etc_root, tmp_path):
    other = tmp_path / "old_boot.py"
    other.write_text("# an older version\n")
    boot.install(boot.Paths(etc_root), "BC-250", True, run=lambda a: Result(0, ""), own=other)
    w = make(FakeBoard())
    assert not w.boot_update_button.isHidden() and "Update" in w.boot_note.text()
    w.update_boot()
    assert w.run_root.calls == [["install", "--name", "BC-250", "--wake"]]
    assert w.boot_update_button.isHidden() and not boot.outdated(boot.Paths(etc_root))


def test_a_new_name_goes_to_the_boot_service(make, etc_root):
    w = make(FakeBoard())
    w.boot_box.setChecked(True)
    w.name_edit.setText("Lounge")
    w.save_name()
    assert w.run_root.calls[-1] == ["install", "--name", "Lounge", "--wake"]
    assert boot.installed(boot.Paths(etc_root)).name == "Lounge" and w.boot_update_button.isHidden()


@pytest.mark.skipif(sys.platform == "win32", reason="the display manager is a symlink, as on Linux")
def test_display_settings_to_the_login_screen(make, etc_root, tmp_path, answer):
    w = make(FakeBoard())
    assert not w.greeter_button.isEnabled()                 # no KDE login screen, no display settings
    (etc_root / "systemd/system").mkdir(parents=True)
    (etc_root / "systemd/system/display-manager.service").symlink_to("/usr/lib/systemd/system/plasmalogin.service")
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config/kwinoutputconfig.json").write_text("[]")
    w.refresh_boot()
    assert w.greeter_button.isEnabled()
    answer["value"] = QMessageBox.StandardButton.No
    w.greeter_button.click()
    assert not w.run_root.calls
    answer["value"] = QMessageBox.StandardButton.Yes
    w.greeter_button.click()
    assert w.run_root.greeter == [str(tmp_path / "config/kwinoutputconfig.json")]
    assert "login screen" in w.result.text()


def test_no_horizontal_scrollbar(make, qapp):
    """The window's lines fit its width, also with a larger font than KDE's default (Noto Sans 10)."""
    from PyQt6.QtGui import QFont
    font = qapp.font()
    qapp.setFont(QFont(font.family(), 11))
    try:
        w = make(FakeBoard())
        scroll = w.centralWidget()
        assert scroll.widget().minimumSizeHint().width() <= w.width() - scroll.verticalScrollBar().sizeHint().width()
    finally:
        qapp.setFont(font)


def test_buttons_keep_the_desktops_look(make):
    """Plain buttons in the desktop's own gray; Turn TV on has no outline of its own."""
    from PyQt6.QtWidgets import QPushButton
    w = make(FakeBoard())
    assert w.centralWidget().widget().styleSheet() == "" and w.on_button.styleSheet() == ""
    assert not any(b.isCheckable() for b in w.centralWidget().widget().findChildren(QPushButton))


def test_the_boot_note_shows_quotes_as_quotes(make):
    w = make(FakeBoard())
    assert '"Playback"' in w.boot_note.text() and "&quot;" not in w.boot_note.text()


def test_the_four_boxes_have_four_colours(make):
    """Left to right: dark blue, orange, black, purple, as each box's left edge on the theme's surface."""
    w = make(FakeBoard())
    boxes = (w.adapter_box, w.address_box, w.display_box, w.power_box)
    colours = [box.styleSheet().split("border-left:4px solid ")[1].split(";")[0] for box in boxes]
    assert colours == [main_window.DARK_BLUE, main_window.ORANGE, main_window.BLACK, main_window.PURPLE]
