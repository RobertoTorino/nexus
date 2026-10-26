# SPDX-License-Identifier: GPL-3.0-or-later
"""The command line under the steps: real bash in a temp folder, offscreen."""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QEvent, QSettings, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from suite_releases import plan as rp
from suite_releases.command_line import HISTORY_KEY, CommandLine, command_lines, plain

needs_bash = pytest.mark.skipif(not shutil.which("bash") or not sys.platform.startswith("linux"),
                                reason="runs bash as on the board")


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def finish(pane: CommandLine, seconds: float = 10) -> None:
    end = time.monotonic() + seconds
    while pane.is_running() and time.monotonic() < end:
        pane.process.waitForFinished(50)
        QApplication.processEvents()
    QApplication.processEvents()
    assert not pane.is_running()


def until(condition, seconds: float = 5) -> None:
    end = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < end
        QApplication.processEvents()
        time.sleep(0.02)


def alive(pid: int) -> bool:
    """Running, not a zombie waiting to be reaped."""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def type_and_run(pane: CommandLine, command: str) -> None:
    pane.line.setText(command)
    pane.submit()
    finish(pane)


def key(pane: CommandLine, k: Qt.Key, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
    QApplication.sendEvent(pane.line, QKeyEvent(QEvent.Type.KeyPress, k, modifiers))


def test_plain_drops_colours_and_progress_returns():
    assert plain("\x1b[1;32mok\x1b[0m\r\n50%\r100%\n") == "ok\n50%\n100%\n"


def test_the_commands_a_step_shows():
    """Apply's block: its commands without the comments; a # inside quotes is part of the command."""
    assert command_lines(rp.app_commands(["alpha-v0.1.1"], linux=True)) == [
        "git add -A && tools/fix-modes.sh", 'git commit -m "Release alpha-v0.1.1"', "tools/ci-local.sh && git push",
        f"{rp.TAG_SCRIPT} alpha-v0.1.1"]
    assert command_lines(rp.app_commands(["alpha-v0.1.1"], linux=False))[2] == "git push"     # no container there
    portal = command_lines(rp.portal_commands("portal-v1.2.0"))
    assert portal[-1] == f"{rp.CHECK_SCRIPT} release portal-v1.2.0" and not any("#" in c for c in portal)
    withdraw = command_lines(rp.withdraw_commands("alpha-v0.1.1", "issue #12  # broken"))
    assert withdraw[0].startswith("gh release edit alpha-v0.1.1") and "issue #12  # broken" in withdraw[0]


def test_commands_offered_go_on_the_line_not_run(app, tmp_path):
    pane = CommandLine(tmp_path, bash="")
    assert not pane.commands_button.isEnabled()
    pane.offer("# commit\ngit push   # then tag\n")
    assert pane.commands_button.isEnabled()
    pane._fill_menu()
    actions = pane.commands_button.menu().actions()
    assert [a.text() for a in actions] == ["git push"]
    actions[0].trigger()
    assert pane.line.text() == "git push" and not pane.is_running()


def test_without_bash_it_says_so(app, tmp_path, monkeypatch):
    monkeypatch.setattr("suite_releases.command_line.find_bash", lambda: None)
    pane = CommandLine(tmp_path)
    assert not pane.line.isEnabled() and "No bash found" in pane.output.toPlainText()


@needs_bash
def test_runs_in_the_checkout_and_streams_the_output(app, tmp_path):
    done = []
    pane = CommandLine(tmp_path, finished=lambda: done.append(1))
    type_and_run(pane, "pwd; echo out; echo err >&2")
    text = pane.output.toPlainText()
    assert f"{tmp_path.name} $ pwd; echo out; echo err >&2" in text
    assert str(tmp_path) in text and "out\n" in text and "err\n" in text
    assert done == [1] and pane.line.text() == ""
    pane.shutdown()


@needs_bash
def test_cd_carries_over_and_a_failure_shows_its_code(app, tmp_path):
    (tmp_path / "sub").mkdir()
    pane = CommandLine(tmp_path)
    type_and_run(pane, "cd sub")
    assert pane.cwd == tmp_path / "sub" and pane.prompt.text() == f"{tmp_path.name}/sub $"
    type_and_run(pane, "pwd")
    assert pane.output.toPlainText().rstrip().endswith(str(tmp_path / "sub"))
    type_and_run(pane, "cd nowhere")
    assert pane.cwd == tmp_path / "sub" and "[exit code 1]" in pane.output.toPlainText()
    pane.shutdown()


@needs_bash
def test_nothing_waits_for_input(app, tmp_path):
    """Input is closed and git asks nothing: a read ends at once, git commit without -m names the way out."""
    pane = CommandLine(tmp_path)
    type_and_run(pane, "read -r x; echo \"got [$x]\"; echo \"$GIT_TERMINAL_PROMPT $GIT_PAGER\"")
    assert "got []\n0 cat" in pane.output.toPlainText()
    if shutil.which("git"):
        type_and_run(pane, "git init -q . && git -c user.name=t -c user.email=t@t commit -q --allow-empty")
        assert "commit with -m" in pane.output.toPlainText()
    pane.shutdown()


@needs_bash
def test_stop_interrupts_the_command_and_what_it_started(app, tmp_path):
    """Ctrl+C ends the command; a job it started in the background (which ignores Ctrl+C in a script) ends too."""
    pane = CommandLine(tmp_path)
    pane.line.setText("sleep 30 & echo $! > bg; sleep 30; echo after")
    pane.submit()
    assert pane.is_running() and pane.run_button.text() == "Stop"
    until(lambda: (tmp_path / "bg").is_file() and (tmp_path / "bg").read_text(encoding="utf-8").strip())
    background = int((tmp_path / "bg").read_text(encoding="utf-8"))
    pane.submit()                                   # Enter while it runs: ignored
    key(pane, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    finish(pane, 5)
    output = pane.output.toPlainText().splitlines()
    assert output[1:] == ["[stopped]"] and pane.run_button.text() == "Run"
    until(lambda: not alive(background))
    pane.shutdown()


@needs_bash
def test_clear_empties_the_output(app, tmp_path):
    pane = CommandLine(tmp_path)
    type_and_run(pane, "echo hi")
    type_and_run(pane, "clear")
    assert pane.output.toPlainText() == ""
    pane.shutdown()


def test_history_with_up_and_down_kept_in_the_settings(app, tmp_path):
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    pane = CommandLine(tmp_path, settings, bash="")
    for command in ("git status", "git push", "git status"):
        pane._remember(command)
    assert pane.history == ["git push", "git status"]            # once each, the newest last
    pane.line.setText("half typed")
    key(pane, Qt.Key.Key_Up)
    assert pane.line.text() == "git status"
    key(pane, Qt.Key.Key_Up)
    key(pane, Qt.Key.Key_Up)                                       # stays at the oldest
    assert pane.line.text() == "git push"
    key(pane, Qt.Key.Key_Down)
    key(pane, Qt.Key.Key_Down)
    assert pane.line.text() == "half typed"
    settings.sync()
    again = CommandLine(tmp_path, QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat), bash="")
    assert again.history == ["git push", "git status"]
    assert settings.value(HISTORY_KEY) == ["git push", "git status"]


@needs_bash
def test_run_now_runs_a_button_command(app, tmp_path):
    """The window's git buttons: their command runs as if typed (in the history too), not while another runs; how it
    ended is kept, so a commit's message goes only when it passed."""
    pane = CommandLine(tmp_path)
    assert pane.run_now("echo one; exit 3")
    assert not pane.run_now("echo two")                     # one at a time
    finish(pane)
    assert pane.last_code == 3 and "one" in pane.output.toPlainText() and "two" not in pane.output.toPlainText()
    assert pane.history == ["echo one; exit 3"]
    assert pane.run_now("true")
    finish(pane)
    assert pane.last_code == 0
    pane.shutdown()
