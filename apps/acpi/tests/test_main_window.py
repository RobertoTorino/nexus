# SPDX-License-Identifier: MIT
"""The window: the state beside the title and the status boxes from the real script on a fake board, and the
install flow with sudo and the script replaced by fakes."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QMessageBox

from locked_acpi import main_window as mw
from conftest import SCRIPT, needs_bash

YES, NO = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No


def wait_for(predicate, ms=5000):
    loop = QEventLoop()
    timer = QTimer()
    timer.timeout.connect(lambda: predicate() and loop.quit())
    timer.start(20)
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    timer.stop()
    return predicate()


@pytest.mark.parametrize("line, state", [
    ("Override: installed (/boot/acpi_override.cpio and the GRUB line)", "installed"),
    ("Override: not installed", "not installed"),
    ("Override: incomplete (GRUB line missing); install again or uninstall", "incomplete"),
    ("Kernel log: run with sudo to also check this.", None),
])
def test_override_state(line, state):
    assert mw.override_state(line) == state


@pytest.mark.parametrize("line, found", [
    ("Frequency steps: 8 (800-3200 MHz; the override gives 8, 800-3200 MHz)",
     ("steps", "8", "800-3200 MHz; the override gives 8, 800-3200 MHz")),
    ("Frequency steps: none listed (the BIOS tables give none; the override gives 8)",
     ("steps", "none listed", "the BIOS tables give none; the override gives 8")),
    ("Idle states: POLL,C1,C2 (the override gives POLL,C1,C2)", ("idle", "POLL,C1,C2", "the override gives POLL,C1,C2")),
    ("Override: installed (/boot/acpi_override.cpio and the GRUB line)", None),
])
def test_status_value(line, found):
    assert mw.status_value(line) == found


@needs_bash
def test_banner_follows_the_status(qapp, board, monkeypatch):
    """The suite's header (owner, 26-10-2026): the state beside the title and the three status boxes follow the
    script's status lines."""
    monkeypatch.setenv("BC250_ACPI_ROOT", str(board.root))
    window = mw.MainWindow(str(SCRIPT))
    assert wait_for(lambda: window.banner.text() == "Not installed")
    assert wait_for(lambda: not window.runner.busy)
    assert "Idle states: POLL" in window.output.toPlainText()
    assert window.banner.kind == "neutral" and window.override_box.value.text() == "Not installed"
    assert window.steps_box.value.text() == "none listed" and "the override gives 8" in window.steps_box.toolTip()
    assert window.idle_box.value.text() == "POLL" and "#1565c0" in window.idle_box.styleSheet()
    board.cpio.write_bytes(b"x")
    board.grub.write_text('GRUB_EARLY_INITRD_LINUX_CUSTOM="../../acpi_override.cpio"\n')
    window.status_btn.click()
    assert wait_for(lambda: window.banner.text() == "Installed")
    assert window.banner.kind == "ok" and "#2e7d32" in window.override_box.styleSheet()
    window.close()


class FakeRunner:
    """Stands in for ScriptRunner: records the root runs and lets the test finish them."""

    def __init__(self, window):
        self.window = window
        self.runs: list[tuple[list[str], str | None]] = []
        self.busy = False

    @staticmethod
    def sudo_ready():
        return True

    def run(self, args, pw=None):
        self.runs.append((args, pw))

    def run_unprivileged(self, args):
        pass

    def finish(self, code, lines=()):
        for line in lines:
            self.window._append_line(line)
        self.window._on_finished(code)


@pytest.fixture
def window(qapp, monkeypatch):
    monkeypatch.setattr(mw.ScriptRunner, "run_unprivileged", lambda self, args: None)
    w = mw.MainWindow(str(SCRIPT))
    w.runner = FakeRunner(w)
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(("info", a[2])))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: (shown.append(("warning", a[2])), NO)[1])
    w.shown = shown
    yield w
    w.close()


def test_install_asks_first(window, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: NO)
    window.install_btn.click()
    assert window.runner.runs == []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: YES)
    window.install_btn.click()
    assert window.runner.runs == [(["--install"], None)]
    window.runner.finish(0)
    assert window.shown == [("info", "The override is installed. Reboot to load it.")]


def test_install_warning_is_confirmed_then_rerun_with_yes(window, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: YES)
    window.install_btn.click()
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: (window.shown.append(("warning", a[2])), YES)[1])
    window.runner.finish(mw.NEEDS_CONFIRMATION, [
        "[WARN] No BC-250 GPU (1002:13fe) detected. This fix is only meant for the AMD BC-250.",
        "[WARN] Not installed: confirm the warning above to continue (--yes).",
    ])
    kind, text = window.shown[0]
    assert kind == "warning" and text.startswith("No BC-250 GPU") and "--yes" not in text
    assert window.runner.runs[-1] == (["--install", "--yes"], None)


def test_install_warning_declined(window, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: YES)
    window.install_btn.click()
    window.runner.finish(mw.NEEDS_CONFIRMATION, ["[WARN] BIOS version 'x' looks modded."])
    assert len(window.runner.runs) == 1
    assert window.output.toPlainText().endswith("Not installed.")


def test_failed_uninstall_is_reported(window, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: YES)
    window.uninstall_btn.click()
    assert window.runner.runs == [(["--uninstall"], None)]
    window.runner.finish(1)
    assert window.shown == [("warning", "uninstall failed (exit code 1). See the output above.")]


def test_status_with_sudo_runs_as_root(window):
    window.sudo_status_btn.click()
    assert window.runner.runs == [(["--status"], None)]
    window.runner.finish(0)
    assert window.shown == []
