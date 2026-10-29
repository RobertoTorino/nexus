# SPDX-License-Identifier: GPL-3.0-or-later
"""shadPS4's own folder (userdata.py), as the BC250 suite's shadPS4 Manager's tests have it: config.json as shadPS4
0.19.0 and 0.20.0 write it, the system modules, the play time, the quit hotkeys, and the users with their shadNet
accounts, read and written as shadPS4 writes them; here also before shadPS4's first start, as on the handheld its
own window never shows."""

from __future__ import annotations

import json

import pytest

from shadps4_manager import userdata


def test_the_module_folder(tmp_path):
    home = tmp_path / "user"
    assert userdata.read_config(home) == {}
    config = {"General": {"sys_modules_dir": ""}}
    assert userdata.modules_folder(home, config) == home / "sys_modules"
    config["General"]["sys_modules_dir"] = r"D:\modules"
    assert str(userdata.modules_folder(home, config)) == r"D:\modules"
    assert userdata.modules_folder(home, {"General": {"sys_modules_dir": 5}}) == home / "sys_modules"


def test_a_config_that_is_not_what_was_expected(tmp_path):
    (tmp_path / "config.json").write_text("{not json")
    assert userdata.read_config(tmp_path) == {}
    (tmp_path / "config.json").write_text("[]")
    assert userdata.read_config(tmp_path) == {}


def test_modules(tmp_path):
    folder = tmp_path / "sys_modules"
    none = userdata.check_modules(folder)
    assert none.needed == () and none.missing == userdata.NEEDED and not none.complete
    folder.mkdir()
    for name in ("libSceJson.sprx", "libSceNgs2.sprx", "notes.txt"):
        (folder / name).touch()
    some = userdata.check_modules(folder)
    assert some.needed == ("libSceJson.sprx",) and some.optional == ("libSceNgs2.sprx",)
    assert len(some.missing) == len(userdata.NEEDED) - 1
    for name in userdata.NEEDED:
        (folder / name).touch()
    assert userdata.check_modules(folder).complete
    assert not set(userdata.NEEDED) & set(userdata.OPTIONAL) and len(userdata.NEEDED) + len(userdata.OPTIONAL) == 34


def test_modules_copied_from_a_folder(tmp_path):
    source = tmp_path / "dump"
    source.mkdir()
    assert userdata.install_modules(source, tmp_path / "target") == [] and not (tmp_path / "target").exists()
    (source / "libSceNgs2.sprx").write_bytes(b"a")
    (source / "LIBSCEULT.SPRX").write_bytes(b"b")
    (source / "readme.txt").write_text("")
    assert userdata.install_modules(source, tmp_path / "target") == ["libSceNgs2.sprx", "LIBSCEULT.SPRX"]
    assert sorted(p.name for p in (tmp_path / "target").iterdir()) == ["LIBSCEULT.SPRX", "libSceNgs2.sprx"]
    assert userdata.install_modules(source, source) == ["libSceNgs2.sprx", "LIBSCEULT.SPRX"]   # the folder itself


def test_the_users_and_shadnet(shad_files):
    users = userdata.read_users(shad_files)
    assert [(u.user_id, u.name, u.shadnet) for u in users] == [
        (1000, "shadPS4", False), (1001, "shadPS4-2", False), (1002, "shadPS4-3", False), (1003, "shadPS4-4", False)]
    config = userdata.read_config(shad_files)
    assert not userdata.shadnet_on(config) and userdata.shadnet_server(config) == "srv.shadps4.net:31313"
    assert userdata.shadnet_server({}) == "srv.shadps4.net:31313" and userdata.signing_in(config, users) == []
    (shad_files / "users.json").write_text("{not json")
    assert userdata.read_users(shad_files) == []


def test_before_shadps4_ran_its_default_users_are_there(tmp_path):
    """shadPS4 0.20.0's four default users (CreateDefaultUsers), with every field of its User, read as they would be
    after its first start."""
    users = userdata.read_users(tmp_path / "none")
    assert [(u.user_id, u.name, u.npid, u.shadnet) for u in users] == [
        (1000, "shadPS4", "", False), (1001, "shadPS4-2", "", False), (1002, "shadPS4-3", "", False),
        (1003, "shadPS4-4", "", False)]
    first = userdata.default_users()["Users"]["user"][0]
    assert sorted(first) == sorted(["user_id", "user_color", "user_name", "player_index", "shadnet_npid",
                                    "shadnet_password", "shadnet_token", "shadnet_email", "shadnet_enabled",
                                    "np_country", "np_language", "np_age", "np_date_of_birth"])


def test_saving_shadnet_changes_only_its_settings(shad_files):
    config_before = json.loads((shad_files / "config.json").read_text())
    users_before = json.loads((shad_files / "users.json").read_text())
    userdata.save_shadnet(shad_files, 1001, "Player_1", "secret", "me@example.com", True, "192.168.1.20:31313")
    config = json.loads((shad_files / "config.json").read_text())
    users = json.loads((shad_files / "users.json").read_text())
    config_before["Network"].update(shad_net_enabled=True, shadnet_server="192.168.1.20:31313")
    users_before["Users"]["user"][1].update(shadnet_npid="Player_1", shadnet_password="secret",
                                            shadnet_email="me@example.com", shadnet_enabled=True)
    assert config == config_before and users == users_before
    for name in ("config.json", "users.json"):                                    # written as shadPS4 writes them
        data = (shad_files / name).read_bytes()
        assert data == json.dumps(json.loads(data), indent=2).encode() and not data.endswith(b"\n")
    assert sorted(p.name for p in shad_files.iterdir()) == ["config.json", "users.json"]   # no temporary file left
    users = userdata.read_users(shad_files)
    assert [u.npid for u in users] == ["", "Player_1", "", ""]
    assert [u.npid for u in userdata.signing_in(userdata.read_config(shad_files), users)] == ["Player_1"]
    # Off for that user, and no other user has it on: shadPS4's own switch goes off too.
    userdata.save_shadnet(shad_files, 1001, "Player_1", "secret", "me@example.com", False, "192.168.1.20:31313")
    assert not userdata.shadnet_on(userdata.read_config(shad_files))


def test_saving_shadnet_before_shadps4_ran_makes_its_files(tmp_path):
    home = tmp_path / "user"
    userdata.save_shadnet(home, 1000, "Player_1", "secret", "", True, "srv.shadps4.net:31313")
    assert json.loads((home / "config.json").read_text()) == {
        "Network": {"shad_net_enabled": True, "shadnet_server": "srv.shadps4.net:31313"}}
    users = json.loads((home / "users.json").read_text())["Users"]["user"]
    assert len(users) == 4 and users[0]["shadnet_npid"] == "Player_1" and users[0]["shadnet_enabled"]
    assert users[1:] == userdata.default_users()["Users"]["user"][1:]


def test_saving_shadnet_for_no_user_or_a_file_that_cannot_be_read(shad_files):
    with pytest.raises(userdata.UserDataError, match="no user 5"):
        userdata.save_shadnet(shad_files, 5, "Player_1", "x", "", True, "srv:1")
    (shad_files / "users.json").write_text("{not json")
    with pytest.raises(userdata.UserDataError, match="could not be read"):
        userdata.save_shadnet(shad_files, 1000, "Player_1", "x", "", True, "srv:1")
    assert (shad_files / "users.json").read_text() == "{not json"                    # never written over


def test_shadnet_in_the_general_section_of_a_config_from_before(shad_files):
    """shadPS4 0.19.0 kept shadNet's settings in General; 0.20.0 takes them from there only while Network does not
    have them, and the app writes them where they are."""
    assert userdata.shadnet_server({"General": {"shadnet_server": "old:1"}, "Network": {}}) == "old:1"
    config = json.loads((shad_files / "config.json").read_text())
    network = config.pop("Network")
    config["General"].update(network)
    (shad_files / "config.json").write_text(json.dumps(config, indent=2))
    userdata.save_shadnet(shad_files, 1000, "Player_1", "secret", "", True, "192.168.1.20:31313")
    saved = json.loads((shad_files / "config.json").read_text())
    assert "Network" not in saved and saved["General"]["shadnet_server"] == "192.168.1.20:31313"
    assert userdata.shadnet_on(saved)


def test_the_quit_hotkeys(tmp_path):
    # Not there yet: shadPS4's header and the three lines; shadPS4 adds the rest of its defaults when it starts.
    path = tmp_path / "input_config" / "global.ini"
    assert userdata.add_quit_bindings(tmp_path) == list(userdata.QUIT_BINDINGS)
    assert path.read_text() == userdata.GLOBAL_INI_HEADER + "".join(f"{b}\n" for b in userdata.QUIT_BINDINGS)
    assert "hotkey_quit = back, options" in userdata.QUIT_BINDINGS            # View + Menu on the handheld
    assert userdata.add_quit_bindings(tmp_path) == []
    # As shadPS4 0.20.0 writes it (the BC250 owner's board): its own Ctrl+Shift+End stays, the other two are added,
    # every other line stays as it is; spacing as shadPS4 reads it, and a file without a newline at the end.
    written = (userdata.GLOBAL_INI_HEADER + "hotkey_pause = f9\nhotkey_quit=lctrl,lshift,end\n"
               "hotkey_volume_up = kpplus")
    path.write_bytes(written.encode())
    assert userdata.add_quit_bindings(tmp_path) == ["hotkey_quit = lctrl, lshift, kp1", "hotkey_quit = back, options"]
    assert path.read_text() == (written + "\nhotkey_quit = lctrl, lshift, kp1\nhotkey_quit = back, options\n")
    assert userdata.add_quit_bindings(tmp_path) == []


def test_one_setting_written_the_rest_kept(tmp_path):
    """write_config sets one key as shadPS4 writes the file (indented by two, no newline at the end); a missing
    file is made, an unreadable one is never written over."""
    home = tmp_path / "user"
    userdata.write_config(home, "GPU", "fsr_enabled", True)
    assert (home / "config.json").read_bytes() == b'{\n  "GPU": {\n    "fsr_enabled": true\n  }\n}'
    userdata.write_config(home, "General", "volume_slider", 150)
    userdata.write_config(home, "GPU", "present_mode", "Fifo")
    assert json.loads((home / "config.json").read_text()) == {
        "GPU": {"fsr_enabled": True, "present_mode": "Fifo"}, "General": {"volume_slider": 150}}
    (home / "config.json").write_text("{ broken")
    with pytest.raises(userdata.UserDataError, match="could not be read"):
        userdata.write_config(home, "GPU", "hdr_allowed", True)
    assert (home / "config.json").read_text() == "{ broken"


def test_play_time_as_shadps4_writes_it(tmp_path):
    """play_time.txt as shadPS4 0.20.0 writes it, from the BC250 owner's board (24-10-2026)."""
    assert userdata.play_times(tmp_path) == {}
    (tmp_path / "play_time.txt").write_text("CUSA11624 1:22:47 1792613335\nCUSA53672 0:43:31 1792710015\n"
                                            "CUSA00001 0:01:02\nnonsense\nCUSA00002 x:y:z 1\n")
    assert userdata.play_times(tmp_path) == {"CUSA11624": (4967, 1792613335.0), "CUSA53672": (2611, 1792710015.0),
                                             "CUSA00001": (62, 0.0)}
    assert [userdata.played(s) for s in (4967, 2611, 62, 40)] == ["1 h 22 min", "43 min 31 s", "1 min 2 s", "40 s"]
