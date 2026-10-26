# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the temperatures and fans of the owner's board, the guard off, on, stopped and outdated, and the
helper calls behind Turn on, Apply and Turn off."""

from __future__ import annotations

import pytest
from conftest import set_rpm, set_temps, write
from PyQt6.QtWidgets import QMessageBox

from fan_control import guard
from fan_control.main_window import MainWindow


class Helper:
    """Stands in for pkexec guard.py: installs into the test's paths."""

    def __init__(self, paths, error: str = ""):
        self.paths, self.error, self.calls = paths, error, []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        if self.error:
            return self.error
        if args[0] == "install":
            values = dict(zip(args[1::2], map(int, args[2::2])))
            guard.install(self.paths, guard.Limits(values["--warn"], values["--cool"], values["--shutdown"],
                                                   values["--hold"]), lambda _a: guard.Result(0, ""))
        else:
            guard.uninstall(self.paths, lambda _a: guard.Result(0, ""))
        return ""


@pytest.fixture
def yes(monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text: warnings.append(text))
    return warnings


def window(qapp, sys_root, paths, helper=None, now=1000.0) -> MainWindow:
    return MainWindow(sys_root=sys_root, paths=paths, runner=helper or Helper(paths), clock=lambda: now)


def test_shows_the_board(qapp, sys_root, paths):
    w = window(qapp, sys_root, paths)
    assert w.gpu_box.value.text() == "42 °C" and w.cpu_box.value.text() == "44 °C"
    assert w.fan_box.value.text() == "1166 RPM" and w.fan_box.caption.text() == "CPU_FAN1"
    assert "CPU_FAN1</b>: 1166 RPM, firmware curve" in w.fans_label.text()
    assert "No speed from J4003 fan 5, J4003 fan 2" in w.fans_label.text()
    assert w.badge.text() == "Guard off" and w.guard_box.value.text() == "Off"
    assert w.apply_button.text() == "Turn on…" and w.apply_button.isEnabled()
    assert not w.off_button.isEnabled()
    assert w.events_view.toPlainText() == "The guard is off."
    assert (w.warn_spin.value(), w.cool_spin.value(), w.shutdown_spin.value(), w.hold_spin.value()) == (85, 90, 95, 10)


def test_no_fan_turning(qapp, sys_root, paths):
    set_rpm(sys_root, 2, 0)
    w = window(qapp, sys_root, paths)
    assert w.fan_box.value.text() == "—"
    assert "No fan reports a speed" in w.fans_note.text()


def test_no_fan_controller(qapp, sys_root, paths):
    write(sys_root / "class/hwmon/hwmon1/name", "other")
    w = window(qapp, sys_root, paths)
    assert w.fans_label.text() == "No fan controller found."
    assert "nct6687" in w.fans_note.text()


def test_turn_on_installs_with_the_limits(qapp, sys_root, paths, yes):
    helper = Helper(paths)
    w = window(qapp, sys_root, paths, helper)
    w.warn_spin.setValue(80)
    w.apply()
    assert helper.calls == [["install", "--warn", "80", "--cool", "90", "--shutdown", "95", "--hold", "10"]]
    assert guard.installed(paths) == guard.Limits(80, 90, 95, 10)
    assert w.badge.text() == "Guard not running"          # no state file in the test
    assert w.apply_button.text() == "Apply…" and not w.apply_button.isEnabled()
    w.shutdown_spin.setValue(93)
    assert w.apply_button.isEnabled()
    assert w.off_button.isEnabled()


def test_bad_limits_block_apply(qapp, sys_root, paths):
    w = window(qapp, sys_root, paths)
    w.warn_spin.setValue(92)
    assert not w.apply_button.isEnabled() and "rise" in w.apply_button.toolTip()


def test_running_guard_and_its_events(qapp, sys_root, paths, yes):
    w = window(qapp, sys_root, paths)
    w.apply()
    g = guard.Guard(guard.Limits(), paths, sys_root, lambda _a: guard.Result(0, ""), lambda *_a: None,
                    lambda: 1000.0, lambda: 1000.0)
    set_temps(sys_root, gpu=87)
    g.step()
    w.refresh()
    assert w.badge.text() == "Hot" and w.guard_box.value.text() == "Hot"
    assert "GPU is at 87 °C" in w.events_view.toPlainText()
    assert "orange" not in w.gpu_box.styleSheet()               # a color code, not a word
    assert "#ef6c00" in w.gpu_box.styleSheet()
    assert "#1565c0" in w.cpu_box.styleSheet()                  # the suite's blue edge while nothing is wrong


def test_stale_state_is_not_running(qapp, sys_root, paths, yes):
    w = window(qapp, sys_root, paths, now=1000.0 + guard.STALE_S + 5)
    w.apply()
    guard.Guard(guard.Limits(), paths, sys_root, lambda _a: guard.Result(0, ""), lambda *_a: None,
                lambda: 1000.0, lambda: 1000.0).step()
    w.refresh()
    assert w.badge.text() == "Guard not running"
    assert guard.UNIT in w.guard_note.text()


def test_outdated_guard(qapp, sys_root, paths, yes):
    w = window(qapp, sys_root, paths)
    w.apply()
    paths.script.write_text("# another version\n")
    w.refresh()
    assert "another version" in w.guard_note.text() and w.apply_button.isEnabled()


def test_turn_off(qapp, sys_root, paths, yes):
    helper = Helper(paths)
    w = window(qapp, sys_root, paths, helper)
    w.apply()
    w.turn_off()
    assert helper.calls[-1] == ["uninstall"]
    assert w.badge.text() == "Guard off" and not w.off_button.isEnabled()


def test_helper_error_is_shown(qapp, sys_root, paths, yes):
    w = window(qapp, sys_root, paths, Helper(paths, "Not authorized: the password dialog was canceled or refused."))
    w.apply()
    assert yes == ["Not authorized: the password dialog was canceled or refused."]
    assert w.badge.text() == "Guard off"


def test_no_question_no_change(qapp, sys_root, paths, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.No)
    helper = Helper(paths)
    w = window(qapp, sys_root, paths, helper)
    w.apply()
    assert helper.calls == []
