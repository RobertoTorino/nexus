# SPDX-License-Identifier: GPL-3.0-or-later
"""Vita3K's own files (userdata.py): its portable folder, the config.yml build 4186 writes read and its lines the app
owns written with the rest kept, the three parts of the firmware as Vita3K counts them, what one install wrote, and the
package's license key."""

from __future__ import annotations

import os

from conftest import CONFIG_4186, install_firmware, make_game, write_config

from vita3k_manager import userdata


def test_vita3ks_files_are_in_its_portable_folder(tmp_path):
    assert userdata.config_path(tmp_path) == tmp_path / "portable" / "config.yml"
    assert userdata.vita_fs(tmp_path) == tmp_path / "portable" / "fs"
    assert userdata.log_path(tmp_path) == tmp_path / "portable" / "vita3k.log"


def test_the_config_yml_of_build_4186():
    config = userdata.read_map(CONFIG_4186)
    assert config["backend-renderer"] == "Vulkan" and config["boot-apps-full-screen"] == "false"
    assert config["pref-path"] == "" and config["user-id"] == ""                  # "": Vita3K's default
    assert "controller-binds" not in config and not any(k.startswith(("-", ".")) for k in config)   # lists left out
    assert userdata.read_map(CONFIG_4186.parent / "none.yml") == {}


def test_prepare_sets_the_apps_lines_and_keeps_the_rest(tmp_path):
    path = write_config(tmp_path)
    before = path.read_text(encoding="utf-8").splitlines()
    assert userdata.prepare(tmp_path) == ["games full screen", "its welcome window off", "its update check off"]
    after = path.read_text(encoding="utf-8").splitlines()
    assert len(after) == len(before) and after[0] == "---" and after[-1] == "..."
    changed = [(old, new) for old, new in zip(before, after) if old != new]
    assert changed == [("boot-apps-full-screen: false", "boot-apps-full-screen: true"),
                       ("show-welcome: true", "show-welcome: false"),
                       ("check-for-updates-mode: 1", "check-for-updates-mode: 0")]
    stamp = path.stat().st_mtime_ns
    assert userdata.prepare(tmp_path) == [] and path.stat().st_mtime_ns == stamp   # nothing to change: not written
    assert b"\r\n" not in path.read_bytes()


def test_prepare_before_vita3k_ever_started(tmp_path):
    """No config.yml yet: the app's lines in a file Vita3K reads, its defaults for the rest (config::update_members)."""
    assert userdata.prepare(tmp_path) == ["games full screen", "its welcome window off", "its update check off"]
    assert userdata.config_path(tmp_path).read_text(encoding="utf-8") == (
        "---\nboot-apps-full-screen: true\nshow-welcome: false\ncheck-for-updates-mode: 0\n...\n")


def test_set_values_adds_a_key_before_the_end(tmp_path):
    path = tmp_path / "config.yml"
    path.write_text("---\nv-sync: true\nime-langs:\n  - 4\n...\n", encoding="utf-8")
    assert userdata.set_values(path, {"v-sync": "false", "fps-hack": "true"}) == ["v-sync", "fps-hack"]
    assert path.read_text(encoding="utf-8") == "---\nv-sync: false\nime-langs:\n  - 4\nfps-hack: true\n...\n"
    assert userdata.read_map(path) == {"v-sync": "false", "fps-hack": "true"}


def test_the_firmware_parts(tmp_path):
    fs = tmp_path / "fs"
    none = userdata.firmware(fs)
    assert (none.system, none.fonts, none.preinstalled, none.ready) == (False, False, False, False)
    (fs / "vs0").mkdir(parents=True)
    assert not userdata.firmware(fs).system                                       # an empty folder is not installed
    install_firmware(fs, fonts=False)
    assert userdata.firmware(fs).system and not userdata.firmware(fs).ready
    install_firmware(fs)
    fw = userdata.firmware(fs)
    assert fw.ready and not fw.preinstalled                                        # the preinstalled apps are optional
    install_firmware(fs, preinstalled=True)
    assert userdata.firmware(fs).preinstalled


def test_what_one_firmware_install_wrote(tmp_path):
    fs = tmp_path / "fs"
    install_firmware(fs, preinstalled=True)
    for path in fs.rglob("*"):
        os.utime(path, (1000, 1000))                                               # installed long ago
    old = userdata.firmware_written(fs, 2000)
    assert (old.system, old.fonts, old.preinstalled) == (False, False, False)
    assert userdata.firmware_parts(old) == ""
    (fs / "os0").mkdir()
    (fs / "os0" / "psp2bootconfig.skprx").write_bytes(b"\0")                     # the system software writes os0 too
    (fs / "sa0" / "data" / "font" / "pvf" / "ltn0.pvf").write_bytes(b"\1")
    now = userdata.firmware_written(fs, 2000)
    assert (now.system, now.fonts, now.preinstalled) == (True, True, False)
    assert userdata.firmware_parts(now) == "the system software and the font package"
    assert userdata.firmware_parts(userdata.Firmware(False, True, False)) == "the font package"
    assert userdata.firmware_parts(userdata.Firmware(True, True, True)) == (
        "the system software, the font package and the preinstalled apps")
    assert not userdata.firmware_written(tmp_path / "none", 0).system


def test_what_one_game_install_wrote(tmp_path):
    fs = tmp_path / "fs"
    make_game(fs, "Old", "PCSB00001")
    for path in fs.rglob("*"):
        os.utime(path, (1000, 1000))
    assert userdata.content_written(fs, 2000) == []
    make_game(fs, "New", "PCSB00002")
    make_game(fs, "Its update", "PCSB00001", kind="patch")
    make_game(fs, "Extra", "PCSB00001", kind="addcont")
    assert userdata.content_written(fs, 2000) == [("game", "PCSB00002"), ("update", "PCSB00001"),
                                                  ("extra content", "PCSB00001")]
    assert userdata.content_written(tmp_path / "none", 0) == []


def test_the_license_key():
    assert userdata.check_zrif("KO5ifR1dQ+eHBlOi4mY2h6aW0=") == ""
    assert "empty" in userdata.check_zrif("")
    assert "no zRIF" in userdata.check_zrif("abcdef") and "no zRIF" in userdata.check_zrif("KO5i not one")


def test_a_dumped_games_own_folder(tmp_path):
    """The folder the app gives Vita3K: the game's own, with sce_sys\\param.sfo; not a folder with games below."""
    game = make_game(tmp_path / "fs", "A", "PCSB00001")
    assert userdata.is_dump(game)
    assert not userdata.is_dump(game.parent) and not userdata.is_dump(tmp_path / "none")
