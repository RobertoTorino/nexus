# SPDX-License-Identifier: GPL-3.0-or-later
"""Vita3K's own folders (userdata.py): the config.yml build 4186 writes, its storage where pref-path moves it, and the
three parts of the firmware as Vita3K counts them."""

from __future__ import annotations

import os

from conftest import CONFIG_4186, install_firmware, write_vita3k_files

from vita3k_manager import userdata


def test_vita3ks_folders_follow_xdg(tmp_path):
    assert userdata.config_dir() == tmp_path / "config" / "Vita3K"
    assert userdata.default_storage() == tmp_path / "data" / "Vita3K" / "Vita3K"


def test_the_config_yml_of_build_4186():
    config = userdata.read_map(CONFIG_4186)
    assert config["backend-renderer"] == "Vulkan" and config["boot-apps-full-screen"] == "false"
    assert config["pref-path"] == "" and config["user-id"] == ""                  # "": Vita3K's default
    assert "controller-binds" not in config and not any(k.startswith(("-", ".")) for k in config)   # lists left out


def test_the_storage_where_vita3k_keeps_it(tmp_path):
    assert userdata.storage(write_vita3k_files(tmp_path / "a")) == userdata.default_storage()
    assert userdata.storage(tmp_path / "none") == userdata.default_storage()      # Vita3K never started
    moved = write_vita3k_files(tmp_path / "b", "/run/media/ssd/Vita3K/")
    assert str(userdata.storage(moved)) == "/run/media/ssd/Vita3K"
    quoted = write_vita3k_files(tmp_path / "c", "'/mnt/games/it''s Vita/'")
    assert str(userdata.storage(quoted)) == "/mnt/games/it's Vita"
    (quoted / "config.yml").write_bytes(b"\xff\xfe")
    assert userdata.storage(quoted) == userdata.default_storage()                   # not text: the default, no error


def test_the_firmware_parts(tmp_path):
    vita_fs = tmp_path / "Vita3K"
    none = userdata.firmware(vita_fs)
    assert (none.system, none.fonts, none.preinstalled, none.ready) == (False, False, False, False)
    (vita_fs / "vs0").mkdir(parents=True)
    assert not userdata.firmware(vita_fs).system                                  # an empty folder is not installed
    install_firmware(vita_fs, fonts=False)
    assert userdata.firmware(vita_fs).system and not userdata.firmware(vita_fs).ready
    install_firmware(vita_fs)
    fw = userdata.firmware(vita_fs)
    assert fw.ready and not fw.preinstalled                                        # the preinstalled apps are optional
    install_firmware(vita_fs, preinstalled=True)
    assert userdata.firmware(vita_fs).preinstalled


def test_what_one_install_wrote(tmp_path):
    vita_fs = tmp_path / "Vita3K"
    install_firmware(vita_fs, preinstalled=True)
    for path in vita_fs.rglob("*"):
        os.utime(path, (1000, 1000))                                               # installed long ago
    old = userdata.firmware_written(vita_fs, 2000)
    assert (old.system, old.fonts, old.preinstalled) == (False, False, False)
    (vita_fs / "os0").mkdir()
    (vita_fs / "os0" / "psp2bootconfig.skprx").write_bytes(b"\0")                 # the system software writes os0 too
    (vita_fs / "sa0" / "data" / "font" / "pvf" / "ltn0.pvf").write_bytes(b"\1")
    now = userdata.firmware_written(vita_fs, 2000)
    assert (now.system, now.fonts, now.preinstalled) == (True, True, False)
    assert not userdata.firmware_written(tmp_path / "none", 0).system
