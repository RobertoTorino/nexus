# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hdmi_cec import bazzite, boot, cec
from conftest import INFO, UNCONFIGURED

LINUX = pytest.mark.skipif(sys.platform == "win32", reason="file modes, owners and symlinks as on Linux")
NO_DISPLAY = INFO.replace("1.0.0.0", "f.f.f.f")
NAMED = INFO.replace("'Playback'", "'BC-250'")


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, argv):
        self.calls.append(argv)
        return boot.Result(0, "")


class Clock:
    """time.monotonic and time.sleep for the boot loop: sleeping moves the clock."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Adapter:
    """cec-ctl for one adapter whose state changes over time: *states* is (from when, Driver Info); configuring adds
    one from now on."""

    def __init__(self, clock, states):
        self.clock, self.states = clock, states
        self.calls = []

    def info(self):
        return [text for start, text in sorted(self.states, key=lambda s: s[0]) if self.clock.now >= start][-1]

    def __call__(self, argv):
        self.calls.append((self.clock.now, argv))
        args = argv[1:]
        if "--playback" in args:                     # configuring takes the name it is given
            name = args[args.index("--osd-name") + 1]
            self.states.append((self.clock.now, INFO.replace("'Playback'", f"'{name}'")))
            return boot.Result(0, self.info())
        return boot.Result(0, self.info() if len(args) == 2 else "")

    def sent(self, option):
        return [(t, c) for t, c in self.calls if option in c]


@pytest.fixture
def paths(tmp_path):
    return boot.Paths(tmp_path / "etc")


def boot_run(tmp_path, states, wake=True, cecd=lambda: False, name="BC-250"):
    clock = Clock()
    adapter = Adapter(clock, states)
    told = []
    dev = tmp_path / "dev"
    dev.mkdir(exist_ok=True)
    (dev / "cec0").touch()
    done = boot.Boot(boot.Config(name, wake), run=adapter, sleep=clock.sleep, clock=clock,
                     notify=lambda s: told.append((clock.now, s)), cecd=cecd, dev_root=dev).loop()
    return done, adapter, told


# --- The messages are cec.py's ------------------------------------------------------------------------------------

def test_messages_match_the_app():
    d = "/dev/cec0"
    assert boot.configure(d, "BC-250") == cec.configure(d, "BC-250")
    assert boot.set_osd_name(d, "BC-250") == cec.set_osd_name(d, "BC-250")
    assert boot.image_view_on(d) == cec.image_view_on(d)
    assert boot.active_source(d, "1.0.0.0") == cec.active_source(d, "1.0.0.0")


@pytest.mark.parametrize("text", [INFO, UNCONFIGURED, NO_DISPLAY, NAMED])
def test_parse_matches_the_app(text):
    mine, app = boot.parse_info("/dev/cec0", text), cec.parse_info("/dev/cec0", text)
    assert (mine.physical_address, mine.osd_name, mine.configured, mine.has_display) == \
        (app.physical_address, app.osd_name, app.configured, app.has_display)


@pytest.mark.parametrize("name", ["", " ", "BC-250", "Ünïcode", "x" * 14, "x" * 15, "tab\there"])
def test_name_rules_match_the_app(name):
    assert boot.name_problem(name) == bazzite.osd_name_problem(name)


# --- Install and uninstall ----------------------------------------------------------------------------------------

@LINUX
def test_install_writes_the_four_files(paths):
    run = Recorder()
    boot.install(paths, "BC-250", True, run=run)
    assert paths.script.read_bytes() == Path(boot.__file__).read_bytes()
    assert json.loads(paths.config.read_text()) == {"name": "BC-250", "wake": True}
    unit = paths.unit.read_text()
    assert "ExecStart=/usr/bin/python3 -I /etc/bc250-hdmi-cec/boot.py run" in unit       # the real /etc, always
    assert "Type=notify" in unit and "RemainAfterExit=yes" in unit and "Before=display-manager.service" in unit
    rule = paths.rule.read_text()
    assert 'SUBSYSTEM=="cec"' in rule and 'ENV{SYSTEMD_WANTS}+="bc250-hdmi-cec-boot.service"' in rule
    for path in (paths.script, paths.config, paths.unit, paths.rule):
        assert path.stat().st_mode & 0o777 == 0o644
    assert ["systemctl", "daemon-reload"] in run.calls and ["udevadm", "control", "--reload"] in run.calls
    assert not [c for c in run.calls if c[:2] in (["systemctl", "start"], ["systemctl", "enable"])]  # not run now
    assert boot.installed(paths) == boot.Config("BC-250", True) and not boot.outdated(paths)


def test_install_refuses_a_bad_name(paths):
    with pytest.raises(ValueError):
        boot.install(paths, "x" * 15, False, run=Recorder())
    assert not paths.folder.exists()


def test_installed_needs_every_file(paths):
    boot.install(paths, "Lounge", False, run=Recorder())
    paths.rule.unlink()
    assert boot.installed(paths) is None


def test_another_version_is_outdated(paths, tmp_path):
    other = tmp_path / "other.py"
    other.write_text("# another version\n")
    boot.install(paths, "BC-250", False, run=Recorder(), own=other)
    assert boot.outdated(paths)


def test_uninstall_removes_everything(paths):
    run = Recorder()
    boot.install(paths, "BC-250", False, run=run)
    (paths.etc / "systemd/system/other.service").write_text("kept")
    boot.uninstall(paths, run=run)
    assert not paths.folder.exists() and not paths.unit.exists() and not paths.rule.exists()
    assert (paths.etc / "systemd/system/other.service").exists()
    assert ["systemctl", "stop", boot.UNIT] in run.calls


@LINUX
def test_cli_answers_in_json(paths, tmp_path):
    env = dict(os.environ, BC250_SYSTEM_ROOT=str(tmp_path), PATH=str(tmp_path / "nothing"))
    script = str(Path(boot.__file__))
    done = subprocess.run([sys.executable, "-I", script, "install", "--name", "Lounge", "--wake"],
                          env=env, capture_output=True, text=True)
    assert boot.answer(done.returncode, done.stdout) == "" and boot.installed(paths) == boot.Config("Lounge", True)
    done = subprocess.run([sys.executable, "-I", script, "install", "--name", "x" * 15], env=env, capture_output=True,
                          text=True)
    assert "At most 14" in boot.answer(done.returncode, done.stdout)


def test_answer():
    assert boot.answer(126, "") == boot.answer(127, "") != ""
    assert boot.answer(0, 'noise\n{"ok": true}\n') == ""
    assert boot.answer(1, '{"ok": false, "error": "no"}') == "no"
    assert "exit code 2" in boot.answer(2, "Traceback")


def test_command_runs_this_file_isolated():
    cmd = boot.command(["uninstall"])
    assert cmd[0] == "pkexec" and cmd[2] == "-I" and cmd[3] == str(Path(boot.__file__).resolve())
    assert cmd[-1] == "uninstall"


# --- The login screen ---------------------------------------------------------------------------------------------

def greeter_home(paths, tmp_path, unit="plasmalogin.service"):
    system = paths.etc / "systemd/system"
    system.mkdir(parents=True, exist_ok=True)
    (system / "display-manager.service").symlink_to(f"/usr/lib/systemd/system/{unit}")
    home = tmp_path / "greeter"
    home.mkdir()
    entry = SimpleNamespace(pw_dir=str(home), pw_uid=os.getuid(), pw_gid=os.getgid())
    return home, (lambda user: entry)


@LINUX
@pytest.mark.parametrize("unit, user", [("plasmalogin.service", "plasmalogin"), ("sddm.service", "sddm"),
                                        ("gdm.service", "")])
def test_greeter_user(paths, tmp_path, unit, user):
    greeter_home(paths, tmp_path, unit)
    assert boot.greeter_user(paths) == user


def test_no_display_manager(paths):
    assert boot.greeter_user(paths) == ""


@LINUX
def test_greeter_display_copies_kwins_file(paths, tmp_path):
    home, getpwnam = greeter_home(paths, tmp_path)
    source = tmp_path / "kwinoutputconfig.json"
    source.write_text(json.dumps([{"name": "outputs", "data": [{"maxBitsPerColor": 8}]}]))
    target = boot.greeter_display(paths, source, run=Recorder(), getpwnam=getpwnam)
    assert target == home / ".config/kwinoutputconfig.json" and target.read_text() == source.read_text()


@LINUX
def test_greeter_display_refuses_other_files_and_greeters(paths, tmp_path):
    _home, getpwnam = greeter_home(paths, tmp_path, "gdm.service")
    source = tmp_path / "kwinoutputconfig.json"
    source.write_text("[]")
    with pytest.raises(ValueError, match="not KDE"):
        boot.greeter_display(paths, source, run=Recorder(), getpwnam=getpwnam)
    (paths.etc / "systemd/system/display-manager.service").unlink()
    (paths.etc / "systemd/system/display-manager.service").symlink_to("/usr/lib/systemd/system/sddm.service")
    source.write_text('{"not": "a list"}')
    with pytest.raises(ValueError):
        boot.greeter_display(paths, source, run=Recorder(), getpwnam=getpwnam)


# --- At boot ------------------------------------------------------------------------------------------------------

def test_names_wakes_and_switches_at_once(tmp_path):
    """The owner's board when the converter sees the TV at boot: Bazzite's cec-control already named it Playback."""
    done, adapter, told = boot_run(tmp_path, [(0, INFO)])
    assert done == 0
    configure = adapter.sent("--playback")[0]
    assert configure == (0, ["cec-ctl", *cec.configure(str(tmp_path / "dev/cec0"), "BC-250")])
    assert adapter.sent("--set-osd-name") and adapter.sent("--image-view-on")
    assert adapter.sent("--active-source")[0][1][-1] == "phys-addr=1.0.0.0"
    assert told == [(0, "READY=1")]                                  # the login screen does not wait
    assert len(adapter.sent("--playback")) == 1                     # the name held: nothing sent again


def test_without_wake_only_names(tmp_path):
    _done, adapter, _told = boot_run(tmp_path, [(0, UNCONFIGURED)], wake=False)
    assert adapter.sent("--playback") and not adapter.sent("--image-view-on") and not adapter.sent("--active-source")


def test_a_late_display_lets_the_login_screen_go_on(tmp_path):
    """The converter sees the TV only after 20 s: ready after READY_S, the name and the wake follow."""
    _done, adapter, told = boot_run(tmp_path, [(0, NO_DISPLAY), (20, INFO)])
    assert told == [(boot.READY_S, "READY=1")]
    assert adapter.sent("--image-view-on")[0][0] == 20


def test_never_a_display(tmp_path):
    _done, adapter, told = boot_run(tmp_path, [(0, NO_DISPLAY)])
    assert told == [(boot.READY_S, "READY=1")] and not adapter.sent("--playback")
    assert max(t for t, _c in adapter.calls) <= boot.GUARD_S


def test_a_rename_to_playback_is_undone(tmp_path):
    """Bazzite's cec-control configures the adapter as Playback a few seconds after the app named it."""
    _done, adapter, _told = boot_run(tmp_path, [(0, INFO), (5, INFO)])
    assert [t for t, _c in adapter.sent("--playback")] == [0, 6]      # the next look after the rename
    assert adapter.info() == NAMED
    assert len(adapter.sent("--image-view-on")) == 1                 # the wake is sent once


def test_steps_aside_for_cecd(tmp_path):
    _done, adapter, told = boot_run(tmp_path, [(0, INFO)], cecd=lambda: True)
    assert not adapter.calls and told == [(0, "READY=1")]


def test_cecd_running(tmp_path):
    for pid, comm in (("1", "systemd"), ("2200", "cecd"), ("self", "cecd")):
        (tmp_path / pid).mkdir()
        (tmp_path / pid / "comm").write_text(comm + "\n")
    assert boot.cecd_running(tmp_path)
    (tmp_path / "2200/comm").write_text("bash\n")
    assert not boot.cecd_running(tmp_path)


def test_run_without_settings_is_ready_at_once(tmp_path, monkeypatch):
    monkeypatch.setenv("BC250_SYSTEM_ROOT", str(tmp_path))
    told = []
    monkeypatch.setattr(boot, "notify", told.append)
    assert boot.main(["run"]) == 0 and told == ["READY=1"]
