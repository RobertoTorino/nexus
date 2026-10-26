# SPDX-License-Identifier: GPL-3.0-or-later
"""The udev rule that gives the logged-in user the screen's port, in a temp root."""

from __future__ import annotations

import json

from usb_ips35 import access, screen


def test_rule_names_the_screen_only():
    text = access.rule_text()
    assert 'ATTRS{idVendor}=="1a86"' in text and 'ATTRS{idProduct}=="5722"' in text and 'TAG+="uaccess"' in text
    assert (access.VENDOR, access.PRODUCT) == (screen.VENDOR, screen.PRODUCT)      # the copy in this file matches


def test_install_and_uninstall(tmp_path):
    calls = []
    access.install(tmp_path, run=calls.append)
    rule = tmp_path / "etc/udev/rules.d" / access.RULE
    assert access.installed(tmp_path) and rule.read_text() == access.rule_text()
    assert rule.stat().st_mode & 0o777 == 0o644
    assert ["udevadm", "control", "--reload"] in calls and ["udevadm", "trigger", "--subsystem-match=tty"] in calls
    calls.clear()
    access.uninstall(tmp_path, run=calls.append)
    assert not rule.exists() and ["udevadm", "control", "--reload"] in calls
    access.uninstall(tmp_path, run=calls.append)                    # twice is fine


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
