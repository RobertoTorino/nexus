# SPDX-License-Identifier: AGPL-3.0-or-later
"""Steam's Guide Button Focus Steam from the app (steam_settings.py), on Steam folders made in a temp folder: reading
and writing localconfig.vdf, and the change with Steam running (closed, changed, started again) or not."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from consoles_link import jobs, steam_settings
from consoles_link.steam_settings import KEY, SteamError

CONFIG = '''"UserLocalConfigStore"
{
\t"apps"
\t{
\t\t"851670"
\t\t{
\t\t\t"OverlayAppEnable"\t\t"0"
\t\t}
\t}
%s}
'''


def _steam(tmp_path: Path, *values: str | None) -> Path:
    """A Steam folder with one user per value: the key's value, or None for a user without it."""
    steam = tmp_path / ".local/share/Steam"
    for n, value in enumerate(values):
        config = steam / "userdata" / str(1000 + n) / "config" / "localconfig.vdf"
        config.parent.mkdir(parents=True)
        config.write_text(CONFIG % (f'\t"{KEY}"\t\t"{value}"\n' if value is not None else ""), encoding="utf-8")
        config.chmod(0o600)
    return steam


@pytest.fixture(autouse=True)
def desktop(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")


def test_find_steam(tmp_path):
    assert steam_settings.find_steam(tmp_path) is None
    flatpak = tmp_path / ".var/app/com.valvesoftware.Steam/.local/share/Steam/userdata"
    flatpak.mkdir(parents=True)
    assert steam_settings.find_steam(tmp_path) == flatpak.parent
    steam = _steam(tmp_path, "1")
    assert steam_settings.find_steam(tmp_path) == steam            # the native one first


@pytest.mark.parametrize("values, on", [(("0",), False), (("1",), True), ((None,), True), (("0", "1"), True),
                                        (("0", "0"), False), ((), None)])
def test_read(tmp_path, values, on):
    steam = _steam(tmp_path, *values)
    assert steam_settings.guide_focus(steam_settings.user_configs(steam)) is on


def test_write_keeps_the_rest_of_the_file(tmp_path):
    steam = _steam(tmp_path, "1", None)
    first, second = steam_settings.user_configs(steam)
    steam_settings.write_guide_focus(first, False)
    steam_settings.write_guide_focus(second, False)                 # missing: added at the end of the top block
    assert first.read_text() == CONFIG % f'\t"{KEY}"\t\t"0"\n'
    assert second.read_text() == CONFIG % f'\t"{KEY}"\t\t"0"\n'
    assert oct(first.stat().st_mode & 0o777) == "0o600" and not list(first.parent.glob("*.bc250-tmp"))
    steam_settings.write_guide_focus(first, True)
    assert steam_settings.guide_focus([first]) is True
    broken = first.parent / "broken.vdf"
    broken.write_text("nothing")
    with pytest.raises(SteamError):
        steam_settings.write_guide_focus(broken, True)


def test_change_while_steam_runs(tmp_path):
    steam = _steam(tmp_path, "1")
    commands, state = [], {"running": True, "polls": 0}

    def run(command):
        commands.append(command)
        if command[1:] == ["-shutdown"]:
            state["closing"] = True

    def running():
        if state.get("closing"):
            state["polls"] += 1
            if state["polls"] > 2:                              # closes after a moment
                state["running"] = False
        return state["running"]
    assert steam_settings.set_guide_focus(False, steam, run, running, sleep=lambda s: None) is True
    assert commands == [["steam", "-shutdown"], steam_settings.start_command()]
    assert commands[1][0] in ("steam", "bazzite-steam") and commands[1][1] == "-silent"
    assert steam_settings.guide_focus(steam_settings.user_configs(steam)) is False


def test_steam_that_does_not_close_changes_nothing(tmp_path):
    steam = _steam(tmp_path, "1")
    commands = []
    with pytest.raises(SteamError, match="did not close"):
        steam_settings.set_guide_focus(False, steam, commands.append, lambda: True, timeout=1.0, sleep=lambda s: None)
    assert commands == [["steam", "-shutdown"]]                     # not started again: it never closed
    assert steam_settings.guide_focus(steam_settings.user_configs(steam)) is True


def test_change_without_steam_running(tmp_path):
    steam = _steam(tmp_path, "0")
    commands = []
    assert steam_settings.set_guide_focus(True, steam, commands.append, lambda: False) is False
    assert commands == [] and steam_settings.guide_focus(steam_settings.user_configs(steam)) is True


def test_game_mode_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "gamescope")
    steam = _steam(tmp_path, "1")
    with pytest.raises(SteamError, match="Game Mode"):
        steam_settings.set_guide_focus(False, steam, lambda c: None, lambda: False)
    assert steam_settings.game_mode()


def test_steam_running_reads_process_names(tmp_path):
    def process(pid, name, state="S"):
        (tmp_path / str(pid)).mkdir()
        (tmp_path / str(pid) / "comm").write_text(name + "\n")
        (tmp_path / str(pid) / "stat").write_text(f"{pid} ({name}) {state} 1 {pid} {pid} 0 -1\n")
    process(10, "bash")
    process(11, "steamwebhelper")
    process(12, "steam", "Z")               # the app's own finished steam -shutdown (the owner's board, 13-10-2026)
    assert not steam_settings.steam_running(tmp_path)
    process(13, "steam")
    assert steam_settings.steam_running(tmp_path)


def test_a_steam_command_leaves_no_zombie():
    import os
    import time
    steam_settings._run(["true"])
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        children = [line for line in os.popen(f"ps --ppid {os.getpid()} -o stat=").read().split() if "Z" in line]
        if not children:
            break
        time.sleep(0.05)
    assert not children


def test_job_says_what_happened(tmp_path):
    steam = _steam(tmp_path, "1")
    done = jobs.steam_guide_focus(False, steam, run=lambda c: None, running=lambda: False)
    assert done.ok and done.message == "Steam no longer comes to the front on the PS button." and done.value is False
    failed = jobs.steam_guide_focus(False, tmp_path / "nowhere")
    assert not failed.ok and "Steam has no users" in failed.message
