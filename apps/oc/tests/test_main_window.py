# SPDX-License-Identifier: GPL-3.0-or-later
"""The window opens offscreen with the suite's header and turns its form into the right command; Install result and
Reset run only after their confirmation."""

from __future__ import annotations

import shlex

import pytest
from PyQt6.QtWidgets import QLabel, QMessageBox

from oc_bisect import __version__
from oc_bisect import main_window

SCRIPT = "/opt/bc250-gpu-oc-bisect/bc250-gpu-oc-bisect.sh"


@pytest.fixture
def commands(monkeypatch):
    """What the window would run in a terminal, and Yes to the start summary."""
    ran = []
    monkeypatch.setattr(main_window, "launch_in_terminal", ran.append)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    return ran


@pytest.fixture
def window(qapp):
    w = main_window.MainWindow(SCRIPT)
    yield w
    w.close()


def test_header(window):
    labels = window.findChildren(QLabel)
    logo = next(label for label in labels if label.pixmap() is not None and not label.pixmap().isNull())
    assert logo.pixmap().width() == 96
    assert any("BC-250 GPU OC Bisect" in label.text() and f"v{__version__}" in label.text() for label in labels)


def test_the_status_boxes_sum_up_the_sweep(window):
    """The suite's header (owner, 26-10-2026): four boxes under the title follow the options."""
    boxes = (window.load_box, window.rounds_box, window.oc_box, window.uv_box)
    assert [b.value.text() for b in boxes] == ["180 s", "3", "to 2200 MHz", "to 850 mV"]
    assert all("#1565c0" in b.styleSheet() for b in boxes)                # the suite's blue edge
    window.time_spin.setValue(240)
    window.max_freq_spin.setValue(2000)
    window.oc_volt_spin.setValue(950)
    assert window.load_box.value.text() == "240 s" and window.oc_box.value.text() == "to 2000 MHz"
    assert "950 mV" in window.oc_box.toolTip()
    window.uv_check.setChecked(False)
    assert window.uv_box.value.text() == "Off" and window.oc_box.value.text() == "to 2000 MHz"
    window.oc_check.setChecked(False)
    assert window.oc_box.value.text() == "Off" and not window.start_btn.isEnabled()


def test_start_with_the_defaults(window, commands):
    window.start_btn.click()
    assert [shlex.split(c) for c in commands] == [["bash", SCRIPT, "-t", "180", "-r", "3"]]


def test_undervolt_only(window, commands):
    window.oc_check.setChecked(False)
    assert not window.max_freq_spin.isEnabled() and window.min_volt_spin.isEnabled()
    window.min_volt_spin.setValue(800)
    window.start_btn.click()
    assert shlex.split(commands[0])[2:] == ["-t", "180", "-r", "3", "--uv", "--min-volt", "800"]


def test_no_sweep_no_start(window):
    window.oc_check.setChecked(False)
    window.uv_check.setChecked(False)
    assert not window.start_btn.isEnabled()


@pytest.mark.parametrize(("button", "flag"), [("install_btn", "--install"), ("reset_btn", "--reset")])
def test_confirmed_actions(window, commands, monkeypatch, button, flag):
    answer = {"value": QMessageBox.StandardButton.Cancel}
    monkeypatch.setattr(QMessageBox, "exec", lambda self: answer["value"])
    getattr(window, button).click()
    assert commands == []
    answer["value"] = QMessageBox.StandardButton.Yes
    getattr(window, button).click()
    assert [shlex.split(c) for c in commands] == [["bash", SCRIPT, flag]]


def test_the_status_boxes_are_as_wide_as_their_text(window, qapp):
    """A narrow window cut the text off (owner, 26-10-2026): the boxes are as wide as the widest of them, never
    narrower than their text, and follow a wider value."""
    window.show()
    qapp.processEvents()
    boxes = (window.load_box, window.rounds_box, window.oc_box, window.uv_box)

    def fits() -> bool:
        widest = max(box.sizeHint().width() for box in boxes)
        return all(box.width() == widest and box.caption.width() >= box.caption.sizeHint().width()
                   and box.value.width() >= box.value.sizeHint().width() for box in boxes)

    assert fits()
    window.time_spin.setValue(36000)
    qapp.processEvents()
    assert window.load_box.value.text() == "36000 s" and fits()
