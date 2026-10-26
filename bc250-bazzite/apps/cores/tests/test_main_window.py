# SPDX-License-Identifier: GPL-3.0-or-later
"""Both windows open offscreen with the suite's header; the bisect window turns its form into the right command,
and the unlock window shows the gate's verdict and the script's --status output."""

from __future__ import annotations

import shlex

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QLabel, QMessageBox, QPushButton

from cores_bisect import __version__
from cores_bisect import main_window as bisect_window
from cores_unlock import gate
from cores_unlock import main_window as unlock_window
from conftest import all_passed

SCRIPT = "/opt/bc250-cores-bisect/bc250-cores-bisect.sh"


def _wait_for(predicate, ms=5000):
    loop = QEventLoop()
    timer = QTimer()
    timer.timeout.connect(lambda: predicate() and loop.quit())
    timer.start(10)
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    timer.stop()
    return predicate()


def _logo_and_title(window, name):
    labels = window.findChildren(QLabel)
    logo = next(label for label in labels if label.pixmap() is not None and not label.pixmap().isNull())
    title = next(label for label in labels if name in label.text() and f"v{__version__}" in label.text())
    return logo, title


@pytest.fixture
def started(monkeypatch):
    """Runs Start without a terminal: the command it would open, Yes to its summary, no About dialog after."""
    commands = []
    monkeypatch.setattr(bisect_window, "launch_in_terminal", commands.append)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(bisect_window.AboutDialog, "exec", lambda self: 0)
    return commands


@pytest.fixture
def gate_state(monkeypatch, state):
    """The unlock window's gate reads the test's state folder."""
    def use(**kwargs):
        folder = state(**kwargs)
        monkeypatch.setattr(unlock_window, "check", lambda: gate.check(folder))
    return use


def test_bisect_window_has_the_suite_header(qapp):
    window = bisect_window.MainWindow(SCRIPT)
    logo, _title = _logo_and_title(window, "BC-250 Cores Bisect")
    assert logo.pixmap().width() == 96
    window.close()


def test_start_with_the_defaults(qapp, started):
    window = bisect_window.MainWindow(SCRIPT)
    window.start_btn.click()
    assert [shlex.split(c) for c in started] == [["bash", SCRIPT, "-t", "600", "-r", "3"]]


def test_start_with_mprime_and_rasdaemon(qapp, started):
    window = bisect_window.MainWindow(SCRIPT)
    window.load_combo.setCurrentIndex(window.load_combo.findData("mprime"))
    window.ras_check.setChecked(True)
    window.rounds_spin.setValue(2)
    window.start_btn.click()
    assert shlex.split(started[0])[2:] == ["-t", "600", "-r", "2", "--load", "mprime", "--rasdaemon"]


def test_unattended_installs_the_resume_unit(qapp, started, monkeypatch):
    installed = []
    monkeypatch.setattr("cores_bisect.service.install", lambda script, opts: installed.append(opts))
    window = bisect_window.MainWindow(SCRIPT)
    window.auto_check.setChecked(True)
    window.start_btn.click()
    assert installed and installed[0].unattended
    assert "--auto" in shlex.split(started[0])


def test_unlock_window_without_results(qapp, unlock_script, gate_state):
    gate_state(phase=None)
    window = unlock_window.MainWindow(str(unlock_script))
    try:
        assert "NOT ACCEPTED" in window.gate_title.text()
        assert not window.install_btn.isEnabled()
        assert _wait_for(lambda: not window.runner.busy)
        assert "fake unlock: --status" in window.output.toPlainText()
        logo, _title = _logo_and_title(window, "BC-250 Cores Unlock")
        assert logo.pixmap().width() == 96
    finally:
        window.close()


def test_unlock_window_accepts_a_finished_bisect(qapp, unlock_script, gate_state):
    gate_state(runs=all_passed())
    window = unlock_window.MainWindow(str(unlock_script))
    try:
        assert _wait_for(lambda: not window.runner.busy)
        assert "ACCEPTED" in window.gate_title.text() and "NOT" not in window.gate_title.text()
        assert window.install_btn.isEnabled()
    finally:
        window.close()


def test_help_and_about_are_pills_under_the_title(qapp, monkeypatch):
    """Help and About are pills under the title (owner, 26-10-2026), of one width; a click opens the dialog. The
    help shows the script's own header comment, which starts after its SPDX line."""
    from pathlib import Path
    opened = []
    monkeypatch.setattr(bisect_window.HelpDialog, "exec", lambda self: opened.append(self.windowTitle()))
    monkeypatch.setattr(bisect_window.AboutDialog, "exec", lambda self: opened.append(self.windowTitle()))
    window = bisect_window.MainWindow(SCRIPT)
    window.show()
    qapp.processEvents()
    assert window.help_pill.value.text() == "Help" and window.about_pill.value.text() == "About"
    assert window.help_pill.width() == window.about_pill.width() >= window.help_pill.sizeHint().width()
    assert not [b for b in window.findChildren(QPushButton) if b.text() in ("Help", "About")]
    window.help_pill.click()
    window.about_pill.click()
    assert [t.split(" ")[0] for t in opened] == ["help", "about"]
    text = bisect_window.HelpDialog._help_text(str(Path(bisect_window.__file__).parents[1] / "bc250-cores-bisect.sh"))
    assert text.startswith("bc250-cores-bisect.sh - ") and "Usage:" in text and "SPDX" not in text
    window.close()
