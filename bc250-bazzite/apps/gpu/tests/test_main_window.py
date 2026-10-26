# SPDX-License-Identifier: GPL-3.0-or-later
"""Main-window state machines with the bus, systemd and dialogs mocked out."""

from __future__ import annotations

from unittest import mock

import pytest
from PyQt6.QtWidgets import QInputDialog, QMessageBox

from gpu_governor.backends.base import PerformanceState, ServiceStatus
from gpu_governor.stress import NO_TOOL

YES = QMessageBox.StandardButton.Yes


@pytest.fixture
def window(qapp, backend, tmp_path, monkeypatch):
    from gpu_governor import main_window as mw
    monkeypatch.setattr(mw.ProfileStore.__init__, "__defaults__", (tmp_path / "profiles.json",))
    w = mw.MainWindow(backend)
    perf = PerformanceState(available=True, allowed_min=500, allowed_max=2000, current_min=1000, current_max=2000,
                            load_min=0.8, load_max=0.95, temp_throttling=85)
    with mock.patch.object(backend, "performance_state", return_value=perf), \
         mock.patch.object(backend, "service_status", return_value=ServiceStatus(True, True, True, "running")), \
         mock.patch.object(backend.bus, "set_test_mode", return_value=(True, "")), \
         mock.patch.object(backend.bus, "set_enabled", return_value=(True, "")), \
         mock.patch.object(backend.bus, "set_range", return_value=(True, "")), \
         mock.patch.object(backend.bus, "set_load_target", return_value=(True, "")), \
         mock.patch.object(QMessageBox, "warning", return_value=YES), \
         mock.patch.object(QMessageBox, "question", return_value=YES), \
         mock.patch.object(mw.KernelWatch, "start"):      # no journalctl in tests; drive feed() directly
        w.refresh()
        yield w
    w._timer.stop()
    w.close()


def test_test_mode_start_stop(window):
    page = window.safe_points
    window._test_point(1800, 850, 0, NO_TOOL)
    assert window._test is not None and page.stop_test_button.isEnabled() and not page.test_button.isEnabled()
    assert "Testing 1800 MHz @ 850 mV" in page.test_status.text()
    window._stop_test()
    assert window._test is None and window.backend.bus.set_enabled.call_args.args == (False,)
    assert "stopped after" in page.test_status.text() and page.test_button.isEnabled()


def test_test_mode_timer_auto_stop(window):
    window._test_point(1800, 850, 30, NO_TOOL)
    assert window._test_timer.isActive()
    window._test_timer.timeout.emit()
    assert window._test is None and "ended by the timer" in window.safe_points.test_status.text()


def test_performance_actions_end_test_but_load_target_does_not(window):
    window._test_point(1800, 850, 0, NO_TOOL)
    window._perf_load(0.7, 0.95)
    assert window._test is not None
    window._perf_range(0, 0)
    assert window._test is None and "Performance page" in window.safe_points.test_status.text()


def test_kernel_error_aborts_test(window):
    page = window.safe_points
    window._test_point(1900, 800, 0, NO_TOOL)
    window._kernel.feed("2026-10-07T06:00:00+0200 bc250 kernel: amdgpu 0000:03:00.0: amdgpu: ring gfx timeout")
    assert window._test is None and window.backend.bus.set_enabled.call_args.args == (False,)
    text = page.test_status.text()
    assert "aborted after a GPU error" in text and "ring gfx timeout" in text
    # A late line after the test ended must not do anything.
    window._kernel.feed("… kernel: amdgpu: GPU reset begin!")
    assert window._test is None


def test_verdict_mentions_clean_kernel_log(window):
    window._test_point(1800, 850, 0, NO_TOOL)
    window._stop_test()
    assert "no GPU errors in the kernel log" in window.safe_points.test_status.text()


def test_governor_vanishing_ends_test(window):
    window._test_point(1800, 850, 0, NO_TOOL)
    window._update_test(PerformanceState(available=False))
    assert window._test is None and "governor stopped" in window.safe_points.test_status.text()


def test_close_stops_test_quietly(window):
    window._test_point(1800, 850, 0, NO_TOOL)
    window._stop_test(quiet=True)
    assert window._test is None and window.backend.bus.set_enabled.call_args.args == (False,)


def test_profile_save_load_apply_delete(window):
    box = window.tuning.profiles
    window.tuning.freq_max.setValue(1700)
    with mock.patch.object(QInputDialog, "getText", return_value=(" Mine ", True)):
        box.save_button.click()
    assert box.combo.currentText() == "Mine"
    window._reload_config()
    assert window.tuning.freq_max.value() == 2000 and not window.tuning.is_dirty()
    box.load_button.click()
    assert window.tuning.freq_max.value() == 1700 and window.tuning.is_dirty() and window.tuning.apply.isEnabled()
    with mock.patch.object(window.backend, "write_config", return_value=None) as write, \
         mock.patch.object(window.backend, "service_action", return_value=(True, "")) as restart:
        box.apply_button.click()
    assert write.call_args.args[0].freq_max == 1700 and restart.called
    box.delete_button.click()
    assert box.combo.count() == 0


def test_performance_page_prefill_and_validation(window):
    page = window.performance
    assert (page.load_lower.value(), page.load_upper.value()) == (80, 95)
    assert page.temp_throttle.value() == 85 and page.temp_recover.value() == 0
    page.load_lower.setValue(70)
    window.refresh()                                        # same runtime values: the edit survives the poll
    assert page.load_lower.value() == 70
    page.load_lower.setValue(96)
    assert not page.load_button.isEnabled() and "lower load target" in page.target_warning.text()
    page.load_lower.setValue(70)
    page.temp_recover.setValue(90)
    assert not page.temp_button.isEnabled()
    page.temp_recover.setValue(75)
    assert page.temp_button.isEnabled() and page.target_warning.text() == ""


def test_performance_mode_button_shows_its_whole_label(window):
    button = window.performance.mode_button
    for enabled in (False, True):
        window.performance.update(PerformanceState(available=True, enabled=enabled), mock.Mock(), True)
        assert button.text().startswith("Performance mode")
        assert button.width() >= button.fontMetrics().horizontalAdvance(button.text())
        assert button.minimumWidth() >= button.sizeHint().width()


def test_hotkey_requests(window):
    from gpu_governor import instance
    box = window.tuning.profiles
    window.tuning.freq_max.setValue(1600)
    with mock.patch.object(QInputDialog, "getText", return_value=("Quiet", True)):
        box.save_button.click()
    window._reload_config()
    with mock.patch.object(window.backend, "write_config", return_value=None) as write, \
         mock.patch.object(window.backend, "service_action", return_value=(True, "")):
        window.handle_request(instance.PROFILE + "Quiet")
    assert write.call_args.args[0].freq_max == 1600
    with mock.patch.object(window.backend, "write_config") as write:
        window.handle_request(instance.PROFILE + "Nope")
    assert not write.called and "No profile named 'Nope'" in window.statusBar().currentMessage()
    window.hide()
    window.handle_request(instance.SHOW)
    assert window.isVisible()


def test_copy_hotkey_command(window):
    from PyQt6.QtWidgets import QApplication
    box = window.tuning.profiles
    with mock.patch.object(QInputDialog, "getText", return_value=("Night mode", True)):
        box.save_button.click()
    box.copy_button.click()
    text = QApplication.clipboard().text()
    assert text.endswith("--profile 'Night mode'") and ("gpu_governor" in text or "bc250-governor-manager" in text)
    assert box.hint.text().startswith("Copied: ")
