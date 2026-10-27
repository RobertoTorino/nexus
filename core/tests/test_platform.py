# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import base64
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from bc250_core import platform


def _working_bash() -> bool:
    """A bash that runs a command: on GitHub's Windows runner the first bash is WSL's launcher, without a Linux to
    run it in, so a test that runs bash skips there; with Git Bash first, as ./test.sh has it, it runs."""
    if shutil.which("bash") is None:
        return False
    try:
        result = subprocess.run(["bash", "-c", "echo ok"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout.strip() == "ok"


NEEDS_BASH = pytest.mark.skipif(not _working_bash(), reason="needs a bash that runs (not WSL's launcher alone)")


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


@NEEDS_BASH
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


@NEEDS_BASH
@pytest.mark.parametrize("command, status", [("true", "0"), ("true && false", "1"), ("exit 3", "3")])
def test_exit_file_gets_the_status(tmp_path, command, status):
    exit_file = tmp_path / "status"
    line = platform.terminal_command(command, keep_open=False, exit_file=Path(exit_file.as_posix()))
    subprocess.run(["bash", "-c", line.replace(str(exit_file.as_posix()), "status")], cwd=tmp_path, check=False)
    assert (tmp_path / "status").read_text().strip() == status


def test_no_terminal_raises(monkeypatch):
    monkeypatch.setattr(platform, "WINDOWS", False)                    # Linux's terminals, on either system
    monkeypatch.delenv("TERMINAL", raising=False)
    monkeypatch.setattr(platform.shutil, "which", lambda name: None)
    assert platform.find_terminal() is None
    with pytest.raises(RuntimeError, match="No terminal emulator found"):
        platform.launch_in_terminal("true")


def test_terminal_preference_and_argv(monkeypatch):
    started = []
    monkeypatch.setattr(platform, "WINDOWS", False)
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


# The Windows side (the Windows Portable Suite): faked here on either system, run for real on Windows below.

WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="runs PowerShell and writes a shortcut")


@pytest.fixture
def windows(monkeypatch, tmp_path):
    monkeypatch.setattr(platform, "WINDOWS", True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    return tmp_path


def test_the_suites_folders_on_windows(windows):
    assert platform.suite_data("windows-portable-suite") == windows / "Local" / "windows-portable-suite"
    assert platform.suite_config("windows-portable-suite") == windows / "Roaming" / "windows-portable-suite"
    assert platform.start_menu() == windows / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def test_the_old_folders_stay_where_they_were_on_windows(windows, monkeypatch):
    """Bazzite SFTP's Windows executable keeps its settings and data in ~/.config and ~/.local/share."""
    for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_BIN_HOME"):
        monkeypatch.delenv(name, raising=False)
    assert platform.data_home() == Path.home() / ".local" / "share"
    assert platform.config_home() == Path.home() / ".config"
    assert platform.bin_home() == Path.home() / ".local" / "bin"


def test_the_suites_folders_on_linux(monkeypatch, tmp_path):
    monkeypatch.setattr(platform, "WINDOWS", False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert platform.suite_data("bc250-bazzite-suite") == tmp_path / "data" / "bc250-bazzite-suite"
    assert platform.suite_config("bc250-bazzite-suite") == tmp_path / "config" / "bc250-bazzite-suite"


def test_a_long_user_name_stays_within_the_path_budget():
    """Windows' 260 characters (long paths are off on most machines): the suite folder under a 20-character user
    name, with a venv holding PyQt6's deepest file, stays under PATH_BUDGET."""
    import PyQt6
    package = Path(PyQt6.__file__).parent
    deepest = max((p.relative_to(package.parent) for p in package.rglob("*")), key=lambda p: len(str(p)))
    local = PureWindowsPath("C:/Users") / ("u" * 20) / "AppData" / "Local"
    path = local / "windows-portable-suite" / "venv" / "Lib" / "site-packages" / PureWindowsPath(deepest.as_posix())
    assert len(str(path)) <= platform.PATH_BUDGET < 260, path


def test_open_path_on_windows(windows, monkeypatch):
    opened = []
    monkeypatch.setattr(platform.os, "startfile", opened.append, raising=False)
    assert platform.open_path(windows / "a file.txt") and opened == [str(windows / "a file.txt")]

    def refuse(target):
        raise OSError("no program for it")
    monkeypatch.setattr(platform.os, "startfile", refuse, raising=False)
    assert not platform.open_path("x.unknown")


def test_open_path_elsewhere_is_xdg_open(monkeypatch):
    monkeypatch.setattr(platform, "WINDOWS", False)
    monkeypatch.setattr(platform, "xdg_open", lambda target: target == "https://example.org")
    assert platform.open_path("https://example.org")


def test_powershell_command():
    exit_file = PureWindowsPath("C:/Users/it's me/status")
    script = platform.powershell_command("cmd.exe /c exit 3", keep_open="on_error", exit_file=exit_file)
    assert script.splitlines() == [
        "$ErrorActionPreference = 'Stop'", "$global:LASTEXITCODE = 0",
        "try { cmd.exe /c exit 3 } catch { Write-Host $_ -ForegroundColor Red; $global:LASTEXITCODE = 1 }",
        "$s = [int]$LASTEXITCODE",
        r"Set-Content -LiteralPath 'C:\Users\it''s me\status' -Value $s -Encoding Ascii",
        "if ($s -ne 0) { Write-Host; Read-Host 'Press Enter to close' | Out-Null }",
        "exit $s"]
    assert "Read-Host" in platform.powershell_command("x")                      # keep_open=True: always
    plain = platform.powershell_command("x", keep_open=False)
    assert "Read-Host" not in plain and "Set-Content" not in plain


def test_powershell_argv_carries_the_script_encoded():
    argv = platform.powershell_argv("Write-Output \"a; b & 'c'\"")
    assert argv[:-1] == ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand"]
    assert base64.b64decode(argv[-1]).decode("utf-16-le") == "Write-Output \"a; b & 'c'\""


def test_launch_in_terminal_on_windows_opens_powershell(windows, monkeypatch):
    started = []
    monkeypatch.setattr(platform.subprocess, "Popen", lambda argv, **kw: started.append((argv, kw)))
    platform.launch_in_terminal("Write-Output hi", keep_open=False, exit_file=PureWindowsPath("C:/t/status"))
    argv, kw = started[0]
    assert argv == platform.powershell_argv(platform.powershell_command(
        "Write-Output hi", keep_open=False, exit_file=PureWindowsPath("C:/t/status")))
    assert kw["creationflags"] == platform.NEW_CONSOLE | platform.NEW_PROCESS_GROUP   # a window of its own


def test_a_shortcut_is_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(platform, "WINDOWS", False)
    with pytest.raises(RuntimeError, match=".desktop"):
        platform.make_shortcut(tmp_path / "x.lnk", tmp_path / "x.exe")


@WINDOWS_ONLY
@pytest.mark.parametrize("command, status", [("Write-Output hi", 0), ("cmd.exe /c exit 3", 3),
                                             ("Get-Item -LiteralPath 'C:/no/such/file'", 1),
                                             ("Write-Output \"it's; & fine\"", 0),
                                             ("cmd.exe /c exit 3; Write-Output after", 3)])
def test_powershell_reports_the_status(tmp_path, command, status):
    """The last program's exit code, 1 for PowerShell's own error, in the exit file (a quote in its path too)."""
    exit_file = tmp_path / "it's" / "status"
    exit_file.parent.mkdir()
    script = platform.powershell_command(command, keep_open=False, exit_file=exit_file)
    result = subprocess.run(platform.powershell_argv(script), capture_output=True, text=True, timeout=60)
    assert result.returncode == status
    assert exit_file.read_text().strip() == str(status)


@WINDOWS_ONLY
def test_make_shortcut_writes_a_link(tmp_path):
    link = tmp_path / "Start Menu" / "It's an app.lnk"
    platform.make_shortcut(link, Path(sys.executable), '-c "print(1)"', description="A test")
    assert link.is_file() and link.read_bytes()[:4] == b"L\x00\x00\x00"                # a Shell Link header
