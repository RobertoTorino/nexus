# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path

from hdmi_cec import cec, media, watcher
from hdmi_cec.runner import Result
from conftest import INFO, NACK, POWER_ON, UNCONFIGURED

KSCREEN = (Path(__file__).parent / "kscreen.json").read_text()      # the owner's board, 11-10-2026
STANDBY = POWER_ON.replace("pwr-state: on (0x00)", "pwr-state: standby (0x01)")


class Board:
    """The TV's power as a sequence of answers, and kscreen-doctor; records the mode switches."""

    def __init__(self, powers, playing=()):
        self.powers = list(powers)
        self.playing = set(playing)                     # the media players that play
        self.calls, self.slept = [], []

    def __call__(self, argv):
        self.calls.append(argv)
        if argv[:2] == ["busctl", "--user"]:
            if argv[2] == "list":
                return Result(0, "".join(f"{media.PREFIX}{p} 123 {p} admin :1.9 - - -\n" for p in ("firefox", "mpv"))
                              + "org.kde.KWin 99 kwin_wayland admin :1.2 - - -\n")
            player = argv[3].removeprefix(media.PREFIX)
            if argv[2] == "get-property":
                return Result(0, 's "Playing"\n' if player in self.playing else 's "Paused"\n')
            if argv[-1] == "Pause":
                self.playing.discard(player)
            elif argv[-1] == "Play":
                self.playing.add(player)
            return Result(0, "")
        if argv[0] == "kscreen-doctor":
            return Result(0, KSCREEN) if argv[1] == "-j" else Result(0, "")
        if "--give-device-power-status" in argv:
            return Result(0, self.powers.pop(0))
        return Result(0, INFO)

    @property
    def switches(self):
        return [c[1] for c in self.calls if c[0] == "kscreen-doctor" and c[1] != "-j"]


def make(powers, restart=True, pause=False, playing=()):
    board = Board(powers, playing)
    w = watcher.Watcher(run=board, sleep=board.slept.append, restart_picture=restart, pause_media=pause)
    w.adapter = cec.parse_info("/dev/cec0", INFO)
    return w, board


def test_the_tv_coming_back_restarts_the_picture_once():
    w, board = make([POWER_ON, STANDBY, STANDBY, POWER_ON, POWER_ON])
    for _ in range(5):
        w.step()
    # 120 Hz (mode 21) -> 60 Hz (mode 23) for a moment, then back to mode 21.
    assert board.switches == ["output.DP-1.mode.23", "output.DP-1.mode.21"]
    assert board.slept == [watcher.SETTLE_S, watcher.HOLD_S]


def test_no_answer_counts_as_off_only_after_three():
    w, board = make([POWER_ON, NACK, NACK, POWER_ON])           # a glitch: no flicker
    for _ in range(4):
        w.step()
    assert board.switches == []
    w, board = make([POWER_ON, NACK, NACK, NACK, POWER_ON])     # unplugged and back
    for _ in range(5):
        w.step()
    assert board.switches == ["output.DP-1.mode.23", "output.DP-1.mode.21"]


def test_pause_while_the_tv_is_off():
    w, board = make([POWER_ON, STANDBY, STANDBY, POWER_ON], restart=False, pause=True, playing={"mpv"})
    w.step()
    w.step()
    assert board.playing == set() and w.paused == [media.PREFIX + "mpv"]
    w.step()
    w.step()
    assert board.playing == {"mpv"} and w.paused == []
    assert board.switches == []                                 # only pausing was asked
    pauses = [c for c in board.calls if c[-1] == "Pause"]
    assert pauses == [["busctl", "--user", "call", media.PREFIX + "mpv", media.PATH, media.PLAYER, "Pause"]]


def test_both_jobs():
    w, board = make([POWER_ON, STANDBY, POWER_ON], pause=True, playing={"firefox"})
    for _ in range(3):
        w.step()
    assert board.playing == {"firefox"} and board.switches == ["output.DP-1.mode.23", "output.DP-1.mode.21"]


def test_on_at_start_does_nothing():
    w, board = make([POWER_ON, POWER_ON])
    w.step()
    w.step()
    assert board.switches == []


def test_no_kscreen_output():
    w, board = make([STANDBY, POWER_ON])
    w.adapter = cec.parse_info("/dev/cec0", INFO.replace("DP-1", "HDMI-A-9"))
    w.step()
    w.step()
    assert board.switches == []


def test_find_adapter_takes_the_one_with_a_display_and_the_users_name(tmp_path):
    dev = tmp_path / "dev"
    dev.mkdir()
    for name in ("cec0", "cec1"):
        (dev / name).touch()
    calls = []

    def run(argv):
        calls.append(argv)
        if "--playback" in argv:
            return Result(0, INFO.replace("DP-1", "HDMI-A-1"))
        return Result(0, UNCONFIGURED.replace("1.0.0.0", "f.f.f.f") if argv[2].endswith("cec0") else
                      UNCONFIGURED.replace("DP-1", "HDMI-A-1"))
    config = tmp_path / "config"
    (config / "cecd/config.d").mkdir(parents=True)
    (config / "cecd/config.d/99-bc250-hdmi-cec.toml").write_text('osd_name = "Lounge PC"\n')
    w = watcher.Watcher(run=run, sleep=lambda s: None, config_dir=config)
    adapter = w.find_adapter(dev)
    assert adapter.device == str(dev / "cec1") and adapter.configured
    assert ["cec-ctl", "-d", str(dev / "cec1"), "--playback", "--osd-name", "Lounge PC"] in calls


def test_find_adapter_renames_a_playback_adapter_unless_cecd_runs(tmp_path):
    dev = tmp_path / "dev"
    dev.mkdir()
    (dev / "cec0").touch()
    for cecd, renamed in ((False, True), (True, False)):
        calls = []

        def run(argv):
            calls.append(argv)
            if argv[0] == "systemctl":
                return Result(0 if cecd else 3, "active\n" if cecd else "inactive\n")
            return Result(0, INFO)                      # configured, named "Playback"
        w = watcher.Watcher(run=run, sleep=lambda s: None, config_dir=tmp_path / "config")
        w.find_adapter(dev)
        assert any("--playback" in c for c in calls) == renamed
