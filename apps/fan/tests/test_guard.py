# SPDX-License-Identifier: GPL-3.0-or-later
"""guard.py: the sensors, the limits, the three actions and their re-arming, the fans put back, the files it
installs and its answers to the app."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import set_rpm, set_temps, write

from fan_control import guard


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Recorder:
    def __init__(self, answers: dict[str, guard.Result] | None = None):
        self.calls: list[list[str]] = []
        self.answers = answers or {}

    def __call__(self, argv: list[str]) -> guard.Result:
        self.calls.append(argv)
        for key, result in self.answers.items():
            if key in argv:
                return result
        return guard.Result(0, "")


@pytest.fixture
def setup(sys_root, paths):
    clock, run, alerts = Clock(), Recorder({"get-property": guard.Result(0, "b true\n")}), []
    g = guard.Guard(guard.Limits(), paths, sys_root, run, lambda title, body: alerts.append(body), clock, clock)
    return g, clock, run, alerts


def nct(sys_root: Path, name: str) -> str:
    return (sys_root / "class/hwmon/hwmon1" / name).read_text().strip()


# --- sensors -------------------------------------------------------------------------------------------------------

def test_reads_the_owners_board(sys_root):
    r = guard.read_sensors(sys_root)
    assert (r.gpu_c, r.cpu_c, r.fan_driver) == (42.0, 44.125, "nct6686")
    assert r.hottest == ("CPU", 44.125)
    assert [f.header for f in r.fans] == ["CPU_FAN1", "J4003 fan 5", "J4003 fan 2", "J4003 fan 3", "J4003 fan 4"]
    cpu_fan = r.fans[0]
    assert (cpu_fan.channel, cpu_fan.rpm, cpu_fan.pwm, cpu_fan.mode_text) == (2, 1166, 127, "firmware curve")
    assert r.turning == (cpu_fan,)


def test_another_board_keeps_the_drivers_labels_and_channels(sys_root):
    write(sys_root / "class/dmi/id/board_name", "X570 AORUS")
    r = guard.read_sensors(sys_root)
    assert [f.header for f in r.fans][:2] == ["CPU Fan", "Pump Fan"]
    assert len(r.fans) == 8


def test_hwmon_numbers_do_not_matter(sys_root):
    hw = sys_root / "class/hwmon"
    (hw / "hwmon2").rename(hw / "hwmon7")
    assert guard.read_sensors(sys_root).gpu_c == 42.0


def test_a_broken_reading_is_no_temperature(sys_root):
    set_temps(sys_root, gpu=0, cpu=200)
    assert guard.read_sensors(sys_root).hottest is None


def test_no_fan_driver(sys_root):
    write(sys_root / "class/hwmon/hwmon1/name", "something")
    r = guard.read_sensors(sys_root)
    assert r.fans == () and r.fan_driver == ""


def test_manual_mode_text():
    fan = guard.Fan(2, "CPU_FAN1", 900, 90, 1, "/x")
    assert fan.mode_text == "manual 35 %"


# --- limits --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("limits, ok", [
    (guard.Limits(), True),
    (guard.Limits(80, 88, 93, 10), True),
    (guard.Limits(90, 85, 95, 10), False),            # not rising
    (guard.Limits(85, 90, 90, 10), False),
    (guard.Limits(55, 90, 95, 10), False),            # below 60
    (guard.Limits(85, 90, 110, 10), False),           # above 105
    (guard.Limits(85, 90, 95, 1), False),             # hold too short
])
def test_limits_problem(limits, ok):
    assert (guard.limits_problem(limits) == "") is ok


# --- the guard -----------------------------------------------------------------------------------------------------

def test_cool_board_does_nothing(setup, sys_root):
    g, _clock, run, alerts = setup
    g.step()
    assert alerts == [] and run.calls == [] and g.level() == "ok"


def test_warns_once_and_rearms_5_below(setup, sys_root):
    g, _clock, run, alerts = setup
    set_temps(sys_root, gpu=86)
    g.step()
    g.step()
    assert len(alerts) == 1 and "GPU is at 86 °C" in alerts[0] and g.level() == "warn"
    set_temps(sys_root, gpu=81)
    g.step()
    assert g.level() == "warn"                         # 81 is not below 80
    set_temps(sys_root, gpu=79)
    g.step()
    assert g.level() == "ok"
    set_temps(sys_root, gpu=85)
    g.step()
    assert len(alerts) == 2
    assert run.calls == []


def test_cooling_turns_fans_full_and_performance_off_then_puts_fans_back(setup, sys_root):
    g, _clock, run, alerts = setup
    set_temps(sys_root, cpu=91)
    g.step()
    assert g.level() == "cooling"
    assert all(nct(sys_root, f"pwm{c}_enable") == "1" and nct(sys_root, f"pwm{c}") == "255" for c in range(1, 6))
    assert nct(sys_root, "pwm6") == "0"                # not a header on the BC-250
    assert ["busctl", "--system", "set-property", *guard.GOVERNOR, "Enabled", "b", "false"] in run.calls
    assert "the fans to full speed and performance mode off" in alerts[-1]
    set_temps(sys_root, cpu=85)
    g.step()
    assert g.level() == "cooling"                      # stays until below the warning's re-arm
    set_temps(sys_root, cpu=79)
    g.step()
    assert g.level() == "ok"
    assert all(nct(sys_root, f"pwm{c}_enable") == "2" and nct(sys_root, f"pwm{c}") == "127" for c in range(1, 6))
    assert sum("set-property" in c for c in run.calls) == 1   # performance mode is not turned back on


def test_performance_mode_already_off_is_left_alone(sys_root, paths):
    run = Recorder({"get-property": guard.Result(0, "b false\n")})
    g = guard.Guard(guard.Limits(), paths, sys_root, run, lambda *_a: None, Clock(), Clock())
    set_temps(sys_root, gpu=92)
    g.step()
    assert not any("set-property" in c for c in run.calls)


def test_a_manual_fan_value_is_put_back(setup, sys_root):
    g, _clock, _run, _alerts = setup
    write(sys_root / "class/hwmon/hwmon1/pwm2_enable", "1")
    write(sys_root / "class/hwmon/hwmon1/pwm2", "150")
    set_temps(sys_root, gpu=95)
    g.step()
    assert nct(sys_root, "pwm2") == "255"
    g.stop()                                           # the service stops while it cools
    assert (nct(sys_root, "pwm2_enable"), nct(sys_root, "pwm2")) == ("1", "150")


def test_shutdown_after_the_hold(setup, sys_root):
    g, clock, run, alerts = setup
    set_temps(sys_root, gpu=96)
    g.step()
    assert g.level() == "shutdown" and "shuts down in 10 s" in alerts[-1]
    clock.now += 9
    g.step()
    assert ["systemctl", "poweroff"] not in run.calls
    clock.now += 1
    g.step()
    g.step()
    assert run.calls.count(["systemctl", "poweroff"]) == 1
    assert "shutting down to protect the board" in alerts[-1]


def test_no_shutdown_when_it_cools_in_time(setup, sys_root):
    g, clock, run, alerts = setup
    set_temps(sys_root, gpu=96)
    g.step()
    clock.now += 5
    set_temps(sys_root, gpu=93)
    g.step()
    clock.now += 20
    set_temps(sys_root, gpu=96)
    g.step()                                           # the hold starts again
    assert ["systemctl", "poweroff"] not in run.calls
    assert "no shutdown" in g.events[-2]["text"]


def test_a_broken_sensor_never_shuts_down(setup, sys_root):
    g, clock, run, alerts = setup
    set_temps(sys_root, gpu=0, cpu=0)
    for _ in range(3):
        g.step()
        clock.now += 30
    assert ["systemctl", "poweroff"] not in run.calls
    assert sum("No GPU or CPU temperature" in e["text"] for e in g.events) == 1


def test_one_sensor_is_enough(setup, sys_root):
    g, _clock, _run, alerts = setup
    write(sys_root / "class/hwmon/hwmon2/temp1_input", "garbage")
    set_temps(sys_root, cpu=87)
    g.step()
    assert "CPU is at 87 °C" in alerts[-1]


def test_a_fan_that_stops_is_reported(setup, sys_root):
    g, clock, _run, alerts = setup
    g.step()
    set_rpm(sys_root, 2, 0)
    g.step()
    clock.now += guard.FAN_STOP_S
    g.step()
    g.step()
    assert len(alerts) == 1 and "CPU_FAN1 has stopped" in alerts[0]
    set_rpm(sys_root, 2, 1100)
    g.step()
    assert "CPU_FAN1 turns again" in g.events[-1]["text"]


def test_a_fan_that_never_turned_is_not_reported(setup, sys_root):
    g, clock, _run, alerts = setup
    for _ in range(3):
        g.step()
        clock.now += 30
    assert alerts == []


def test_state_file(setup, sys_root, paths):
    g, clock, _run, _alerts = setup
    set_temps(sys_root, gpu=86)
    g.step()
    state = guard.read_state(paths, clock.now)
    assert state["level"] == "warn" and state["gpu_c"] == 86.0
    assert state["fans"][0]["header"] == "CPU_FAN1" and state["limits"]["shutdown_c"] == 95
    assert guard.read_state(paths, clock.now + guard.STALE_S + 1) is None


def test_desktop_notification_per_user(tmp_path, monkeypatch):
    import pwd
    run = Recorder()
    for uid in ("1000", "0", "42"):
        write(tmp_path / "user" / uid / "bus", "")
    monkeypatch.setattr(pwd, "getpwuid", lambda uid: type("P", (), {"pw_name": f"user{uid}"})())
    guard.notify_desktop(run, "Title", "Body", tmp_path)
    assert len(run.calls) == 1
    call = run.calls[0]
    assert call[:4] == ["runuser", "-u", "user1000", "--"]
    assert f"DBUS_SESSION_BUS_ADDRESS=unix:path={tmp_path}/user/1000/bus" in call
    assert call[-2:] == ["Title", "Body"]


# --- install, uninstall, answers -----------------------------------------------------------------------------------

def test_install_and_uninstall(paths):
    run = Recorder()
    guard.install(paths, guard.Limits(80, 88, 93, 15), run)
    assert paths.script.read_bytes() == Path(guard.__file__).read_bytes()
    assert json.loads(paths.config.read_text()) == {"warn_c": 80, "cool_c": 88, "shutdown_c": 93, "hold_s": 15}
    unit = paths.unit.read_text()
    assert "ExecStart=/usr/bin/python3 -I /etc/bc250-fan-control/guard.py run" in unit
    assert "Restart=always" in unit and "WantedBy=multi-user.target" in unit
    assert ["systemctl", "enable", guard.UNIT] in run.calls and ["systemctl", "restart", guard.UNIT] in run.calls
    assert guard.installed(paths) == guard.Limits(80, 88, 93, 15)
    assert not guard.outdated(paths)
    guard.uninstall(paths, run)
    assert ["systemctl", "disable", "--now", guard.UNIT] in run.calls
    assert not paths.unit.exists() and not paths.folder.exists()
    assert guard.installed(paths) is None


def test_install_refuses_bad_limits(paths):
    with pytest.raises(ValueError):
        guard.install(paths, guard.Limits(95, 90, 85, 10), Recorder())
    assert not paths.script.exists()


def test_install_says_when_the_service_does_not_start(paths):
    with pytest.raises(ValueError, match="did not start"):
        guard.install(paths, guard.Limits(), Recorder({"restart": guard.Result(1, "failed\n")}))


def test_broken_config_means_defaults(paths):
    guard.install(paths, guard.Limits(80, 88, 93, 15), Recorder())
    paths.config.write_text("{broken")
    assert guard.read_limits(paths) is None
    assert guard.installed(paths) == guard.Limits()


def test_outdated(paths, tmp_path):
    guard.install(paths, guard.Limits(), Recorder())
    other = tmp_path / "other.py"
    other.write_text("# another version\n")
    assert guard.outdated(paths, other)


def test_main_install_prints_an_answer(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BC250_SYSTEM_ROOT", str(tmp_path))
    monkeypatch.setattr(guard, "run", Recorder())
    monkeypatch.setattr(guard.install, "__defaults__", (guard.run, Path(guard.__file__)))
    assert guard.main(["install", "--warn", "80", "--cool", "85", "--shutdown", "90", "--hold", "5"]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True}
    assert guard.installed(guard.paths_from_env()) == guard.Limits(80, 85, 90, 5)
    assert guard.main(["install", "--warn", "99"]) == 1
    assert "rise" in json.loads(capsys.readouterr().out)["error"]


def test_command_and_answer():
    cmd = guard.command(["uninstall"])
    assert cmd[0] == "pkexec" and cmd[2] == "-I" and cmd[3].endswith("guard.py") and cmd[-1] == "uninstall"
    assert guard.answer(0, '{"ok": true}\n') == ""
    assert guard.answer(1, 'noise\n{"ok": false, "error": "nope"}\n') == "nope"
    assert "canceled" in guard.answer(126, "")
    assert "without an answer" in guard.answer(1, "Traceback")
