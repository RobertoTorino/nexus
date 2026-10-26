# SPDX-License-Identifier: GPL-3.0-or-later
"""The udev rule that gives the logged-in user the camera's boot loader and starts the load service, in a temp root."""

from __future__ import annotations

import json

from usb_hdcam import access, camera


def test_rule_names_the_boot_loader_only():
    text = access.rule_text()
    assert 'ATTR{idVendor}=="05a9"' in text and 'ATTR{idProduct}=="0580"' in text
    assert 'ENV{DEVTYPE}=="usb_device"' in text and 'TAG+="uaccess"' in text and 'TAG+="systemd"' in text
    assert 'ENV{SYSTEMD_USER_WANTS}+="bc250-usb-hdcam-load.service"' in text
    assert (access.VENDOR, access.PRODUCT) == (camera.VENDOR, camera.BOOT)        # the copy in this file matches
    rules = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert len(rules) == 2
    assert 'ATTR{idProduct}=="058c|058a"' in rules[1] and 'ATTR{power/control}="on"' in rules[1]
    assert "uaccess" not in rules[1]                                # the camera itself needs no rule for access


def test_install_and_uninstall(tmp_path):
    calls = []
    access.install(tmp_path, run=calls.append)
    rule = tmp_path / "etc/udev/rules.d" / access.RULE
    assert access.installed(tmp_path) and rule.read_text() == access.rule_text()
    assert rule.stat().st_mode & 0o777 == 0o644
    assert ["udevadm", "control", "--reload"] in calls
    assert ["udevadm", "trigger", "--subsystem-match=usb", "--attr-match=idVendor=05a9"] in calls
    calls.clear()
    access.uninstall(tmp_path, run=calls.append)
    assert not rule.exists() and ["udevadm", "control", "--reload"] in calls
    access.uninstall(tmp_path, run=calls.append)                    # twice is fine


def test_an_older_rule_is_offered_again(tmp_path):
    rule = tmp_path / "etc/udev/rules.d" / access.RULE
    rule.parent.mkdir(parents=True)
    rule.write_text(access.rule_text().split("# The camera with")[0])          # an earlier rule, without the power line
    assert not access.installed(tmp_path) and access.outdated(tmp_path)
    access.install(tmp_path, run=lambda argv: None)
    assert access.installed(tmp_path) and not access.outdated(tmp_path)


def test_main_in_another_root(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BC250_SYSTEM_ROOT", str(tmp_path))
    monkeypatch.setattr(access, "run", lambda argv: None)
    assert access.main(["install"]) == 0
    assert json.loads(capsys.readouterr().out) == {"error": ""}
    assert access.installed(tmp_path)


def test_a_missing_command_does_not_stop_the_change(tmp_path):
    access.run(["/nonexistent/udevadm", "control", "--reload"])     # no exception
    access.install(tmp_path, run=access.run)
    assert access.installed(tmp_path)


def test_command_runs_this_file_through_pkexec():
    argv = access.command(["install"])
    assert argv[0] == "pkexec" and argv[2] == "-I" and argv[3].endswith("access.py") and argv[-1] == "install"


def test_answer():
    assert access.answer(0, '{"error": ""}\n') == ""
    assert "canceled" in access.answer(126, "")
    assert access.answer(1, '{"error": "Read-only file system"}') == "Read-only file system"
    assert "exit code 2" in access.answer(2, "boom")
