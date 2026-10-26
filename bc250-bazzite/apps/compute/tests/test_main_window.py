# SPDX-License-Identifier: GPL-3.0-or-later
"""Both windows open offscreen with the suite's header; the bisect window turns its form into the right command,
and the unlock window shows the gate's verdict and the script's --status output."""

from __future__ import annotations

import shlex

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QLabel, QMessageBox, QPushButton

from cu_bisect import __version__ as BISECT_VERSION
from cu_bisect import main_window as bisect_window
from cu_unlock import main_window as unlock_window

SCRIPT = "/opt/test/bc250-cu-bisect.sh"


def _wait_for(predicate, ms=5000):
    loop = QEventLoop()
    timer = QTimer()
    timer.timeout.connect(lambda: predicate() and loop.quit())
    timer.start(10)
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    timer.stop()
    return predicate()


def _header(window):
    labels = window.findChildren(QLabel)
    logo = next(label for label in labels if label.pixmap() is not None and not label.pixmap().isNull())
    title = next(label for label in labels if "v" + BISECT_VERSION in label.text())
    return logo, title


@pytest.fixture
def started(monkeypatch):
    """Runs Start without a terminal: the command it would open, and Yes to its summary."""
    commands = []
    monkeypatch.setattr(bisect_window, "launch_in_terminal", commands.append)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    return commands


def test_bisect_window_has_the_suite_header(qapp):
    window = bisect_window.MainWindow(SCRIPT)
    logo, title = _header(window)
    assert logo.pixmap().width() == 96
    assert "BC-250 CU Bisect" in title.text()
    window.close()


def test_start_with_the_defaults(qapp, started):
    window = bisect_window.MainWindow(SCRIPT)
    window.start_btn.click()
    assert [shlex.split(c) for c in started] == [["bash", SCRIPT, "-t", "180", "-r", "3"]]


def test_start_with_a_custom_baseline_and_switches(qapp, started):
    window = bisect_window.MainWindow(SCRIPT)
    window.time_spin.setValue(300)
    window.baseline_combo.setCurrentText("Custom...")
    window.baseline_custom.setText("0x0f,0x0f,0x0f,0x0f")
    window.control_only_check.setChecked(True)
    window.rounds_spin.setValue(1)
    window.same_boot_check.setChecked(True)
    window.no_watch_check.setChecked(True)
    window.start_btn.click()
    assert shlex.split(started[0])[2:] == ["-t", "300", "-r", "1", "--baseline", "0x0f,0x0f,0x0f,0x0f",
                                           "--control-only", "--same-boot", "--no-watch"]


def test_unattended_offers_the_autostart_service(qapp, started, monkeypatch):
    installed = []
    monkeypatch.setattr("cu_bisect.service.install", lambda *args: installed.append(args))
    window = bisect_window.MainWindow(SCRIPT)
    assert not window.autostart_check.isEnabled()
    window.auto_check.setChecked(True)
    assert window.autostart_check.isEnabled() and window.autostart_check.isChecked()
    window.start_btn.click()
    assert installed == [(SCRIPT, 180, 3)]
    assert "--auto" in shlex.split(started[0])


def test_invalid_options_start_nothing(qapp, started, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text: warnings.append(text))
    window = bisect_window.MainWindow(SCRIPT)
    window.baseline_combo.setCurrentText("Custom...")
    window.baseline_custom.setText("0x07")
    window.start_btn.click()
    assert started == [] and "4 masks" in warnings[0]


def test_unlock_window_without_results(qapp, unlock_script, state):
    state()
    window = unlock_window.MainWindow(str(unlock_script))
    try:
        assert "NOT ACCEPTED" in window.gate_title.text()
        assert not window.install_btn.isEnabled()
        assert _wait_for(lambda: not window.runner.busy)
        assert "fake unlock: --status" in window.output.toPlainText()
    finally:
        window.close()


def test_unlock_window_accepts_a_retested_mask(qapp, unlock_script, state):
    state("0x1f,0x1f,0x1f,0x1f", rounds=1, runs=[(1, "control", "PASS")])
    window = unlock_window.MainWindow(str(unlock_script))
    try:
        assert _wait_for(lambda: not window.runner.busy)
        assert "ACCEPTED" in window.gate_title.text() and "NOT" not in window.gate_title.text()
        assert window.install_btn.isEnabled()
        logo = next(label for label in window.findChildren(QLabel)
                    if label.pixmap() is not None and not label.pixmap().isNull())
        assert logo.pixmap().width() == 96
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
    text = bisect_window.HelpDialog._help_text(str(Path(bisect_window.__file__).parents[1] / "bc250-cu-bisect.sh"))
    assert text.startswith("bc250-cu-bisect.sh - ") and "Usage:" in text and "SPDX" not in text
    window.close()
