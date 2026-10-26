# SPDX-License-Identifier: GPL-3.0-or-later
import tomllib

from hdmi_cec import bazzite
from hdmi_cec.runner import Result


def systemctl(enabled: set[str], active: set[str] = frozenset()):
    """systemctl as it answers: is-enabled prints enabled/disabled, is-active active/inactive."""
    calls = []

    def run(argv):
        calls.append(argv)
        unit = argv[-1]
        if "is-enabled" in argv:
            return Result(0, "enabled\n") if unit in enabled else Result(1, "disabled\n")
        if "is-active" in argv:
            return Result(0, "active\n") if unit in active else Result(3, "inactive\n")
        return Result(0, "")
    run.calls = calls
    return run


def test_modes(usr_root, tmp_path):
    assert bazzite.read_mode(systemctl(set()), usr_root) == bazzite.Mode("disabled", True, False)
    assert bazzite.read_mode(systemctl({"cec-onsleep.service"}), usr_root).name == "dgpu"
    mode = bazzite.read_mode(systemctl({"cecd.service", "cec-onboot.service"}, {"cecd.service"}), usr_root)
    assert mode == bazzite.Mode("native", True, True) and mode.label == "Native (Valve's cecd)"
    assert not bazzite.read_mode(systemctl(set()), tmp_path / "nothing").cecd_installed


def test_cecd_is_asked_as_a_user_unit(usr_root):
    run = systemctl(set())
    bazzite.read_mode(run, usr_root)
    assert ["systemctl", "--user", "is-enabled", "cecd.service"] in run.calls
    assert ["systemctl", "is-enabled", "cec-onboot.service"] in run.calls


def test_settings_follow_cecd_load_order(tmp_path, etc_root, usr_root):
    config = tmp_path / "config"
    assert bazzite.read_settings(config, etc_root, usr_root) == bazzite.DEFAULTS
    (usr_root / "share/cecd/config.d").mkdir(parents=True)
    (usr_root / "share/cecd/config.toml").write_text("wake_tv = true\n")
    (config / "cecd/config.d").mkdir(parents=True)
    # What `ujust cec-mode native` writes.
    (config / "cecd/config.d/98-bazzite-cec-mode.toml").write_text(
        'logical_address = "playback"\nsuspend_tv = true\nallow_standby = false\n')
    got = bazzite.read_settings(config, etc_root, usr_root)
    assert got == {"wake_tv": True, "suspend_tv": True, "allow_standby": False, "uinput": True}
    # SteamOS Manager's file sorts after the app's and wins.
    bazzite.write_settings(config, dict(got, uinput=False, suspend_tv=False))
    (config / "cecd/config.d/99-steamos-manager.toml").write_text("suspend_tv = true\n")
    assert bazzite.read_settings(config, etc_root, usr_root)["uinput"] is False
    assert bazzite.read_settings(config, etc_root, usr_root)["suspend_tv"] is True


def test_written_fragment(tmp_path):
    path = bazzite.write_settings(tmp_path, {"wake_tv": True, "suspend_tv": False, "allow_standby": False,
                                             "uinput": True})
    assert path == tmp_path / "cecd/config.d/99-bc250-hdmi-cec.toml"
    assert tomllib.loads(path.read_text()) == {"wake_tv": True, "suspend_tv": False, "allow_standby": False,
                                               "uinput": True}


def test_a_broken_file_is_skipped(tmp_path, etc_root, usr_root):
    (etc_root / "cecd").mkdir()
    (etc_root / "cecd/config.toml").write_text("wake_tv = \n")
    assert bazzite.read_settings(tmp_path, etc_root, usr_root) == bazzite.DEFAULTS


def test_reload_sends_hup():
    run = systemctl(set())
    bazzite.reload_cecd(run)
    assert run.calls == [["systemctl", "--user", "kill", "-s", "HUP", "cecd.service"]]
