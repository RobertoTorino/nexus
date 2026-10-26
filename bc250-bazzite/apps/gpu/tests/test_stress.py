# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
import shutil
import stat

import pytest
from PyQt6.QtCore import QEventLoop, QTimer

from gpu_governor import stress


def spin(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture
def fake_tools(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    # Absolute paths inside the scripts, so PATH can hold only the fake directory: a real glmark2 or vkcube
    # installed on the machine running the tests must not show up.
    sleep = shutil.which("sleep") or "/bin/sleep"
    (bindir / "vkmark").write_text(f"#!/bin/sh\nexec {sleep} 60\n")
    (bindir / "glxgears").write_text("#!/bin/sh\nexit 3\n")
    for tool in bindir.iterdir():
        tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(bindir))
    return bindir


def test_available_tools_in_preference_order(fake_tools):
    assert stress.available_tools() == ["vkmark", "glxgears"]
    assert stress.tool_arguments("vkmark") == ["--run-forever"] and stress.tool_arguments("glxgears") == []


def test_runner_stop_is_silent_and_early_exit_is_reported(qapp, fake_tools):
    runner = stress.StressRunner()
    got = []
    runner.finished.connect(lambda code, crashed: got.append((code, crashed)))
    ok, error = runner.start("vkmark")
    assert ok and runner.running, error
    assert runner.start("vkmark") == (False, "A load tool is already running.")
    runner.stop()
    assert not runner.running and got == []
    ok, _ = runner.start("glxgears")
    assert ok
    spin(500)
    assert got == [(3, False)] and not runner.running
    assert runner.start("nope") == (False, "nope was not found on PATH.")
