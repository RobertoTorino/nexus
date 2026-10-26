# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path, PurePosixPath

import pytest

from bc250_core import platform


def test_terminal_command_plain_keeps_window_open():
    assert platform.terminal_command("bash x.sh") == "bash x.sh; echo; read -rp 'Press Enter to close... ' _"
    assert platform.terminal_command("bash x.sh", keep_open=False) == "bash x.sh"


def test_terminal_command_exit_file_covers_whole_command():
    line = platform.terminal_command("cd /a && bash x.sh", keep_open=False, exit_file=PurePosixPath("/tmp/st 1"))
    assert line == "( cd /a && bash x.sh ); echo $? > '/tmp/st 1'"


def test_terminal_command_on_error_pauses_only_after_a_failure():
    """keep_open="on_error" (owner, 26-10-2026): the window of a command that ended well closes by itself, one with
    an error waits for Enter; the exit file gets the status either way."""
    pause = "echo; read -rp 'Press Enter to close... ' _"
    line = platform.terminal_command("cd /a && bash x.sh", keep_open="on_error", exit_file=PurePosixPath("/tmp/st 1"))
    assert line == "( cd /a && bash x.sh ); s=$?; echo $s > '/tmp/st 1'; [ \"$s\" = 0 ] || { " + pause + "; }"
    assert platform.terminal_command("bash x.sh", keep_open="on_error") == \
        "( bash x.sh ); s=$?; [ \"$s\" = 0 ] || { " + pause + "; }"


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize("command, status, paused", [("true", "0", False), ("true && false", "1", True),
                                                      ("exit 3", "3", True)])
def test_on_error_runs_the_pause_only_on_a_failure(tmp_path, command, status, paused):
    exit_file = tmp_path / "status"
    line = platform.terminal_command(command, keep_open="on_error", exit_file=Path(exit_file.as_posix()))
    # Without a terminal "read" shows no prompt and ends at once; the pause's echo leaves its blank line.
    result = subprocess.run(["bash", "-c", line.replace(str(exit_file.as_posix()), "status")], cwd=tmp_path,
                            check=False, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert (tmp_path / "status").read_text().strip() == status
    assert (result.stdout == "\n") is paused


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize("command, status", [("true", "0"), ("true && false", "1"), ("exit 3", "3")])
def test_exit_file_gets_the_status(tmp_path, command, status):
    exit_file = tmp_path / "status"
    line = platform.terminal_command(command, keep_open=False, exit_file=Path(exit_file.as_posix()))
    subprocess.run(["bash", "-c", line.replace(str(exit_file.as_posix()), "status")], cwd=tmp_path, check=False)
    assert (tmp_path / "status").read_text().strip() == status


def test_no_terminal_raises(monkeypatch):
    monkeypatch.delenv("TERMINAL", raising=False)
    monkeypatch.setattr(platform.shutil, "which", lambda name: None)
    assert platform.find_terminal() is None
    with pytest.raises(RuntimeError, match="No terminal emulator found"):
        platform.launch_in_terminal("true")


def test_terminal_preference_and_argv(monkeypatch):
    started = []
    monkeypatch.delenv("TERMINAL", raising=False)
    monkeypatch.setattr(platform.shutil, "which", lambda name: f"/usr/bin/{name}" if name in ("ptyxis", "xterm") else None)
    monkeypatch.setattr(platform.subprocess, "Popen", lambda argv, **kw: started.append((argv, kw)))
    platform.launch_in_terminal("bash x.sh", keep_open=False)
    argv, kw = started[0]
    assert argv == ["ptyxis", "--", "bash", "-lc", "bash x.sh"]           # ptyxis comes before xterm
    assert kw["start_new_session"] is True


def test_expand_and_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert platform.data_home() == tmp_path / "data"
    monkeypatch.setenv("BC250_X", "abc")
    assert platform.expand("$BC250_X/y").as_posix().endswith("abc/y")
