# SPDX-License-Identifier: GPL-3.0-or-later
"""The window against the real script on the fake board (conftest.Board): the steps it shows, the buttons it
enables, and the commands its buttons run."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from ace_queues import main_window
from ace_queues.main_window import MainWindow
from conftest import SCRIPT, needs_bash

pytestmark = needs_bash


@pytest.fixture
def window(qapp, board, monkeypatch):
    for key, value in board.env.items():
        monkeypatch.setenv(key, value)
    w = MainWindow(SCRIPT)
    yield w
    w.close()


def test_fresh_board(window):
    assert window.pill.text() == "Not built"
    assert window.build_state.text().startswith("Not built.")
    assert window.build_button.isEnabled()
    assert not window.install_button.isEnabled() and not window.remove_button.isEnabled()
    assert not window.test_button.isEnabled() and not window.all_button.isEnabled()
    assert "kernel 7.2.8-ogc5.1.fc44.x86_64" in window.system.text()


def test_installed_and_tested(window, board):
    board.make_build()
    board.install()
    window.refresh()
    assert window.pill.text() == "Test needed"
    assert window.test_button.isEnabled() and not window.install_button.isEnabled()
    assert not window.all_button.isEnabled()
    board.pass_test()
    window.refresh()
    assert window.pill.text() == "Ready"
    assert window.test_state.text().startswith("<span style='color:#2e7d32'><b>Passed</b></span> on this kernel")
    assert window.all_button.isEnabled() and window.all_button.text() == "All apps: on"
    window.copy_launch_options()
    assert QApplication.clipboard().text() == "/usr/local/bin/bc250-ace-queues-run %command%"


def test_newer_build_waits_to_be_installed(window, board):
    board.make_build(mesa="26.2.3")
    board.install()
    board.make_build(mesa="26.2.4")
    window.refresh()
    assert "A newer build is waiting" in window.install_state.text()
    assert window.install_button.isEnabled()


def test_system_mesa_moved_on(window, board, monkeypatch):
    board.make_build()
    monkeypatch.setenv("FAKE_MESA", "26.2.5")
    window.refresh()
    assert "The system has Mesa 26.2.5 now" in window.build_state.text()


def test_commands(window):
    assert window.command("build") == ["bash", str(SCRIPT), "--build"]
    assert window.command("install") == ["pkexec", "/usr/bin/bash", str(SCRIPT), "--install-driver"]
    assert window.command("all-on") == ["pkexec", "/usr/bin/bash", str(SCRIPT), "--all-apps", "on"]


def test_buttons_ask_first(window, monkeypatch):
    ran = []
    monkeypatch.setattr(window, "run", ran.append)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    window.on_build()
    window.on_install()
    window.on_all_apps()
    assert ran == []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.on_build()
    window.on_install()
    assert ran == ["build", "install"]


def test_run_shows_the_output_and_refreshes(window, board, qapp, monkeypatch):
    monkeypatch.setitem(main_window.ACTIONS, "test", (["--launch-options"], False, "Testing…"))
    window.run("test")
    assert window.process is not None and not window.build_button.isEnabled()
    assert window.process.waitForFinished(10000)
    qapp.processEvents()
    assert window.running.text() == "Done."
    assert "bc250-ace-queues-run %command%" in window.output.toPlainText()
    assert window.process is None and window.build_button.isEnabled()


def test_not_authorised(window):
    window.action = "install"
    window.process = object()
    window._finished(126)
    assert window.running.text().startswith("Not authorized")
