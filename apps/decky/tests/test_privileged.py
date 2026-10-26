# SPDX-License-Identifier: GPL-3.0-or-later
"""The root part's command line through pkexec and its answer."""

from __future__ import annotations

from decky_manager import privileged


def test_command_runs_the_helper_isolated():
    command = privileged.command(["install", "/tmp/x"])
    assert command[0] == "pkexec" and command[2] == "-I" and command[3].endswith("decky_manager/loader.py")
    assert command[4:] == ["install", "/tmp/x"]


def test_parse():
    assert privileged.parse(0, 'noise\n{"ok": true, "message": "Done."}\n') == privileged.Result(True, "Done.")
    assert privileged.parse(1, '{"ok": false, "error": "No."}') == privileged.Result(False, "No.")
    assert "canceled" in privileged.parse(126, "").message
    result = privileged.parse(2, "Traceback")
    assert not result.ok and "exit code 2" in result.message and "Traceback" in result.message
