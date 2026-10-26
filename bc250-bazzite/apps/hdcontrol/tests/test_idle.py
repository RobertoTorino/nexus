# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
import socket

from conftest import plug
from usb_hdcontrol import controller, idle, inputs


class FakeReports:
    def __init__(self, path):
        self.path, self.used, self.closed = path, [], False

    def in_use(self):
        return self.used.pop(0) if self.used else False

    def close(self):
        self.closed = True


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def watcher(tmp_path, minutes=10, disconnect=None):
    opened, asked, logged, clock = [], [], [], Clock()
    notified = []

    def open_reports(path):
        opened.append(FakeReports(path))
        return opened[-1]

    def fake_disconnect(address):
        asked.append(address)
        return disconnect(address) if disconnect else ""
    found = lambda: controller.find(tmp_path / "sys")  # noqa: E731
    w = idle.Watcher(lambda: minutes, find=found, open_reports=open_reports, disconnect=fake_disconnect,
                     clock=clock, log=logged.append, notify=lambda *text: notified.append(text) or True,
                     dev=tmp_path / "dev")
    w.notified = notified
    return w, opened, asked, logged, clock


def test_what_counts_as_use():
    assert not idle.active(inputs.Reading())
    assert not idle.active(inputs.Reading(sticks=(0.1, -0.2, 0.05, 0.0), triggers=(0.05, 0.0)))    # drift
    assert idle.active(inputs.Reading(frozenset({"cross"})))
    assert idle.active(inputs.Reading(sticks=(0.0, 0.0, 0.0, -0.6)))
    assert idle.active(inputs.Reading(triggers=(0.0, 0.3)))


def test_a_controller_on_bluetooth_is_switched_off_after_the_minutes_unused(tmp_path):
    plug(tmp_path / "sys", bus=0x05)
    w, opened, asked, logged, clock = watcher(tmp_path)
    w.step()
    [reports] = opened
    assert reports.path == tmp_path / "dev" / "hidraw2"
    clock.now += 9 * 60
    reports.used.append(True)                       # used at 9 minutes: the wait starts again
    w.step()
    clock.now += 9 * 60
    w.step()
    assert asked == []
    clock.now += 60
    w.step()
    assert asked == ["aa:bb:cc:dd:ee:ff"] and logged == ["DualSense Edge (player 1) on Bluetooth unused for 10 "
                                                         "minutes: switched off."]
    assert w.notified == [("DualSense Edge (player 1) switched off",
                           "Not used for 10 minutes. Press the PS button to switch it on again.")]


def test_on_the_cable_it_is_left_alone(tmp_path):
    plug(tmp_path / "sys", bus=0x03)
    w, opened, asked, _logged, clock = watcher(tmp_path)
    w.step()
    clock.now += 3600
    w.step()
    assert opened == [] and asked == []


def test_off_reads_nothing_and_closes_what_it_read(tmp_path):
    plug(tmp_path / "sys", bus=0x05)
    minutes = [10]
    w, opened, asked, _logged, clock = watcher(tmp_path)
    w.minutes = lambda: minutes[0]
    w.step()
    minutes[0] = 0
    clock.now += 3600
    w.step()
    assert opened[0].closed and asked == [] and w.watched == {}


def test_a_failed_switch_off_is_logged_and_tried_again_after_another_wait(tmp_path):
    plug(tmp_path / "sys", bus=0x05)
    w, _opened, asked, logged, clock = watcher(tmp_path, minutes=30,
                                               disconnect=lambda a: "Bluetooth did not let go of the controller.")
    w.step()
    clock.now += 30 * 60
    w.step()
    clock.now += 60
    w.step()
    assert len(asked) == 1 and "not switched off, Bluetooth did not let go" in logged[0]
    [(summary, body)] = w.notified
    assert summary == "DualSense Edge (player 1) not switched off" and "Hold the PS button for 10 seconds" in body
    clock.now += 30 * 60
    w.step()
    assert len(asked) == 2


def test_a_controller_that_leaves_is_let_go(tmp_path):
    from conftest import unplug
    plug(tmp_path / "sys", bus=0x05)
    w, opened, _asked, _logged, clock = watcher(tmp_path)
    w.step()
    unplug(tmp_path / "sys")
    clock.now += idle.LOOK
    w.step()
    assert opened[0].closed and w.watched == {}


def test_reports_tell_use_from_rest():
    """A hidraw node gives one report per read: a SEQPACKET socket pair keeps them apart as it does."""
    ours, theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    read_end, write_end = os.dup(ours.fileno()), os.dup(theirs.fileno())
    ours.close()
    theirs.close()
    os.set_blocking(read_end, False)
    reports = idle.Reports.__new__(idle.Reports)
    reports.fd = read_end
    at_rest = bytes([0x31, 0x00, 128, 128, 128, 128, 0, 0, 0, 0x08, 0, 0]) + bytes(52)
    pressed = bytes([0x31, 0x00, 128, 128, 128, 128, 0, 0, 0, 0x28, 0, 0]) + bytes(52)    # Cross
    os.write(write_end, at_rest)
    assert not reports.in_use()
    os.write(write_end, at_rest)
    os.write(write_end, pressed)
    assert reports.in_use() and not reports.in_use()       # nothing new waiting
    reports.close()
    os.close(write_end)


def test_the_notification_goes_through_notify_send():
    calls = []
    assert idle.notify("Edge switched off", "Not used.", run=lambda args, timeout: calls.append(args),
                       which=lambda name: "/usr/bin/notify-send")
    assert calls[0][0] == "/usr/bin/notify-send" and calls[0][-2:] == ["Edge switched off", "Not used."]
    assert "--app-name" in calls[0] and "USB HD Control" in calls[0]
    assert not idle.notify("x", "y", which=lambda name: None)                 # not installed: nothing sent


def test_several_controllers_each_have_their_own_wait_and_are_named_by_player(tmp_path):
    plug(tmp_path / "sys", bus=0x05, players="00100")
    plug(tmp_path / "sys", node="hidraw5", bus=0x05, instance=5, players="01010")
    w, opened, asked, logged, clock = watcher(tmp_path)
    w.step()
    first, second = opened
    clock.now += 9 * 60
    first.used.append(True)                         # player 1 is in use, player 2 is not
    w.step()
    clock.now += 60
    w.step()
    assert [summary for summary, _body in w.notified] == ["DualSense Edge (player 2) switched off"]
    assert len(asked) == 1


def test_without_player_lights_the_name_alone(tmp_path):
    plug(tmp_path / "sys", bus=0x05, players=None)
    assert idle.label(controller.find(tmp_path / "sys")[0]) == "DualSense Edge"


def test_the_last_used_times_go_to_the_state_file_for_the_window(tmp_path):
    plug(tmp_path / "sys", bus=0x05)
    state = tmp_path / "run" / "idle.json"
    state.parent.mkdir()
    w, opened, _asked, _logged, clock = watcher(tmp_path)
    w.state = state
    w.step()
    assert idle.read_state(state) == {"hidraw2": 1000.0}           # a controller came: written at once
    clock.now += 2
    opened[0].used.append(True)
    w.step()
    assert idle.read_state(state) == {"hidraw2": 1000.0}           # used, but within SAVE of the last write
    clock.now += idle.SAVE
    w.step()
    assert idle.read_state(state) == {"hidraw2": 1002.0}
    w.minutes = lambda: 0                                           # Never: nothing is watched
    w.step()
    assert idle.read_state(state) == {}


def test_while_a_game_from_steam_runs_the_controllers_stay_on(tmp_path):
    """A game Steam started (SteamGameId in a process's environment) keeps every controller on, used or not; the
    wait starts over when it ends. Looked for only while a controller is there, once per LOOK."""
    plug(tmp_path / "sys", bus=0x05)
    game = [False]
    looks = []
    w, opened, asked, logged, clock = watcher(tmp_path)
    w.game = lambda: looks.append(clock.now) or game[0]
    w.step()
    clock.now += 9 * 60
    game[0] = True
    w.step()
    assert logged == ["A game started from Steam runs: the controllers stay on."]
    clock.now += 60 * 60
    w.step()
    assert asked == []                                                      # an hour unused in the game: on
    game[0] = False
    clock.now += idle.LOOK
    w.step()
    assert logged[-1] == "The game ended: a controller unused from now on is switched off after the wait."
    clock.now += 9 * 60
    w.step()
    assert asked == []                                                      # the wait started over
    clock.now += 60
    w.step()
    assert asked == ["aa:bb:cc:dd:ee:ff"]
    assert len(looks) == 6 and len(set(looks)) == 6                        # once per step here: each a LOOK apart


def test_a_game_from_steam_is_known_by_its_environment(tmp_path):
    proc = tmp_path / "proc"
    for pid, environ in (("100", b"HOME=/home/x\0SHELL=/bin/bash\0"), ("200", b"STEAM_RUNTIME=1\0")):
        (proc / pid).mkdir(parents=True)
        (proc / pid / "environ").write_bytes(environ)
    (proc / "self").mkdir()
    assert not idle.game_running(proc)
    (proc / "300").mkdir()
    (proc / "300" / "environ").write_bytes(b"SteamGameId=3710761059\0SteamAppId=0\0")
    assert idle.game_running(proc)
    (proc / "400").mkdir()                                                  # another user's: not readable
    (proc / "400" / "environ").write_bytes(b"SteamGameId=1\0")
    (proc / "400" / "environ").chmod(0)
    (proc / "300" / "environ").unlink()
    assert not idle.game_running(proc) or os.getuid() == 0


def test_read_state_without_the_service(tmp_path):
    assert idle.read_state(tmp_path / "none.json") == {}
    (tmp_path / "bad.json").write_text("not json")
    assert idle.read_state(tmp_path / "bad.json") == {}
