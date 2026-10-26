# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from installer_test_gui import TESTS_DIR
from installer_test_gui import APP_DIR
from installer_test_gui.main_window import MainWindow
from installer_test_gui import runner
from installer_test_gui.runner import InstallerTestRunner, discover_tests

INSTALLER = APP_DIR / "install.sh"


@pytest.fixture(scope="session", autouse=True)
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_discovery_excludes_shared_shims(tmp_path: Path) -> None:
    for name in ("zeta.sh", "shims.sh", "alpha.sh"):
        (tmp_path / name).write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    assert [path.name for path in discover_tests(tmp_path)] == ["alpha.sh", "zeta.sh"]


def test_runner_adds_homebrew_fakeroot_directory_to_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_homebrew_bin = tmp_path / "linuxbrew" / "bin"
    fake_homebrew_bin.mkdir(parents=True)
    fakeroot = fake_homebrew_bin / "fakeroot"
    fakeroot.write_text("#!/bin/sh\n", encoding="utf-8")
    fakeroot.chmod(0o755)
    monkeypatch.setattr(runner, "HOMEBREW_BIN_DIRS", (fake_homebrew_bin,))

    assert runner._path_with_fakeroot("/usr/bin:/bin") == f"{fake_homebrew_bin}:/usr/bin:/bin"
    assert runner._path_with_fakeroot(f"{fake_homebrew_bin}:/usr/bin") == f"{fake_homebrew_bin}:/usr/bin"


def test_runner_process_can_find_fakeroot_from_homebrew(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_homebrew_bin = tmp_path / "linuxbrew" / "bin"
    fake_homebrew_bin.mkdir(parents=True)
    fakeroot = fake_homebrew_bin / "fakeroot"
    fakeroot.write_text("#!/bin/sh\n", encoding="utf-8")
    fakeroot.chmod(0o755)
    script = tmp_path / "check-fakeroot.sh"
    script.write_text("command -v fakeroot\n", encoding="utf-8")
    monkeypatch.setattr(runner, "HOMEBREW_BIN_DIRS", (fake_homebrew_bin,))
    installer_runner = InstallerTestRunner(tmp_path, tmp_path)
    output: list[str] = []
    loop = QEventLoop()
    installer_runner.output.connect(output.append)
    installer_runner.run_finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)

    installer_runner.start([script])
    loop.exec()

    assert "".join(output).strip() == str(fakeroot)


def test_runner_executes_selected_tests_in_order_and_continues_after_failure(tmp_path: Path) -> None:
    scripts = [tmp_path / "first.sh", tmp_path / "second.sh"]
    scripts[0].write_text("printf 'first output\\n'\nexit 0\n", encoding="utf-8")
    scripts[1].write_text("printf 'second output\\n'\nexit 7\n", encoding="utf-8")
    runner = InstallerTestRunner(tmp_path, tmp_path)
    statuses: list[tuple[str, int, bool]] = []
    output: list[str] = []
    loop = QEventLoop()
    runner.test_finished.connect(lambda *result: statuses.append(result))
    runner.output.connect(output.append)
    runner.run_finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)

    runner.start(scripts)
    loop.exec()

    assert statuses == [("first.sh", 0, False), ("second.sh", 7, False)]
    assert "first output\n" in "".join(output)
    assert "second output\n" in "".join(output)
    assert not runner.busy


def test_runner_rejects_shim_and_scripts_outside_test_directory(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "tests"
    scripts_dir.mkdir()
    shim = scripts_dir / "shims.sh"
    shim.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    outside = tmp_path / "outside.sh"
    outside.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    runner = InstallerTestRunner(scripts_dir, tmp_path)

    for script in (shim, outside):
        with pytest.raises(ValueError):
            runner.start([script])


def test_window_lists_all_installer_scripts_except_shims() -> None:
    window = MainWindow()

    assert not window.header_icon.pixmap().isNull()
    assert window.header_icon.pixmap().width() <= 96
    assert window.header_icon.pixmap().height() <= 96
    assert window.test_list.count() == len(discover_tests(TESTS_DIR))
    assert all(
        window.test_list.item(index).text() == ""
        and window._items[window.test_list.item(index).toolTip()][2].text()
        for index in range(window.test_list.count())
    )
    window.close()


def test_window_shows_green_check_and_red_cross_at_row_end() -> None:
    window = MainWindow()
    passed_name, failed_name = list(window._items)[:2]
    _passed_item, _passed_title, _passed_checkbox, passed_status = window._items[passed_name]
    _failed_item, _failed_title, _failed_checkbox, failed_status = window._items[failed_name]

    window._test_finished(passed_name, 0, False)
    window._test_finished(failed_name, 1, False)

    assert passed_status.text() == "✓"
    assert "color: #2e7d32" in passed_status.styleSheet()
    assert passed_status.toolTip().endswith("passed")
    assert failed_status.text() == "✗"
    assert "color: #c62828" in failed_status.styleSheet()
    assert failed_status.toolTip().endswith("exit code 1)")
    window.close()


def test_window_keeps_previous_results_when_another_test_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    window = MainWindow()
    passed_name, failed_name, running_name = list(window._items)[:3]
    _item1, _title1, _checkbox1, passed_status = window._items[passed_name]
    _item2, _title2, _checkbox2, failed_status = window._items[failed_name]

    window._test_finished(passed_name, 0, False)
    window._test_finished(failed_name, 1, False)
    previous_results = (
        passed_status.text(),
        passed_status.styleSheet(),
        passed_status.toolTip(),
        failed_status.text(),
        failed_status.styleSheet(),
        failed_status.toolTip(),
    )
    monkeypatch.setattr(window.runner, "start", lambda _scripts: None)

    window._run([TESTS_DIR / running_name])
    window._test_started(running_name)

    assert (
        passed_status.text(),
        passed_status.styleSheet(),
        passed_status.toolTip(),
        failed_status.text(),
        failed_status.styleSheet(),
        failed_status.toolTip(),
    ) == previous_results
    window.close()


def test_cancel_stops_the_current_test_and_skips_queued_tests(tmp_path: Path) -> None:
    first = tmp_path / "first.sh"
    second = tmp_path / "second.sh"
    marker = tmp_path / "second-ran"
    first.write_text("exec sleep 30\n", encoding="utf-8")
    second.write_text('touch "$PWD/second-ran"\n', encoding="utf-8")
    runner = InstallerTestRunner(tmp_path, tmp_path)
    statuses: list[tuple[str, int, bool]] = []
    cancelled_runs: list[bool] = []
    loop = QEventLoop()

    def finish_run(cancelled: bool) -> None:
        cancelled_runs.append(cancelled)
        loop.quit()

    runner.test_finished.connect(lambda *result: statuses.append(result))
    runner.run_finished.connect(finish_run)
    QTimer.singleShot(50, runner.cancel)
    QTimer.singleShot(5000, loop.quit)

    runner.start([first, second])
    loop.exec()

    assert len(statuses) == 1
    assert statuses[0][0] == "first.sh" and statuses[0][2]
    assert cancelled_runs == [True]
    assert not marker.exists()


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="installer requires a non-root Linux user")
def test_installer_creates_desktop_entries_and_uninstalls_only_them(tmp_path: Path) -> None:
    home = tmp_path / "home"
    desktop = home / "Desktop"
    data = home / ".local" / "share"
    desktop.mkdir(parents=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    xdg_user_dir = fake_bin / "xdg-user-dir"
    xdg_user_dir.write_text('#!/bin/sh\nprintf "%s\\n" "$HOME/Desktop"\n', encoding="utf-8")
    xdg_user_dir.chmod(0o755)
    env = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(data), PATH=f"{fake_bin}:{os.environ['PATH']}")
    launcher = home / ".local" / "bin" / "bc250-installer-test-gui"
    menu_entry = data / "applications" / "bc250-installer-test-gui.desktop"
    desktop_entry = desktop / "bc250-installer-test-gui.desktop"

    install = subprocess.run(["bash", str(INSTALLER)], env=env, capture_output=True, text=True, check=False)

    assert install.returncode == 0, install.stderr
    assert launcher.stat().st_mode & 0o777 == 0o755
    assert f'exec "{APP_DIR}/run.sh" "$@"' in launcher.read_text(encoding="utf-8")
    assert f'Exec="{launcher}"' in menu_entry.read_text(encoding="utf-8")
    assert f"Icon={APP_DIR}/images/bc250-installer-test-gui-128.png" in desktop_entry.read_text(encoding="utf-8")
    assert desktop_entry.stat().st_mode & 0o111

    without_desktop = subprocess.run(
        ["bash", str(INSTALLER), "--no-desktop-shortcut"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert without_desktop.returncode == 0, without_desktop.stderr
    assert launcher.exists()
    assert menu_entry.exists()
    assert not desktop_entry.exists()

    uninstall = subprocess.run(
        ["bash", str(INSTALLER), "--uninstall"], env=env, capture_output=True, text=True, check=False
    )

    assert uninstall.returncode == 0, uninstall.stderr
    assert not launcher.exists()
    assert not menu_entry.exists()
    assert not desktop_entry.exists()
    assert (APP_DIR / "run.sh").is_file()
    assert (APP_DIR / "installer_test_gui" / "__main__.py").is_file()


def test_a_second_launch_opens_no_window(monkeypatch):
    """A double-click on the Desktop icon starts the app twice: the second launch hands over to the first."""
    from PyQt6.QtWidgets import QApplication
    import installer_test_gui.__main__ as entry
    app = QApplication.instance() or QApplication([])
    asked = []
    monkeypatch.setattr(entry, "QApplication", lambda argv: app)
    monkeypatch.setattr(entry.instance, "already_running", lambda app_id: asked.append(app_id) or True)
    monkeypatch.setattr(entry, "MainWindow", lambda *a, **k: (_ for _ in ()).throw(AssertionError("a second window")))
    assert entry.main() == 0 and asked == [entry.APP_ID]
