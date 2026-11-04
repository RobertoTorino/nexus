# SPDX-License-Identifier: GPL-3.0-or-later
"""The runner (each script in its own process, in order, with its output) and the window (the suite's tests with
their results, the suite chosen in the header). Ported from BC-250 Installer Tests on 02-11-2026."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import QEventLoop, QTimer

from installer_tests import APP_NAME, CHECKOUT, ROOT, runner
from installer_tests.main_window import SUITE_KEY, MainWindow, suites_here
from installer_tests.runner import InstallerTestRunner, command_for, discover_tests, suffix_here
from installer_tests.runner import tests_dir as suite_tests_dir     # not tests_dir: pytest would collect it

INSTALLER = ROOT / "install.sh"
BC250 = CHECKOUT / "bc250-bazzite"


def test_discovery_excludes_the_helpers_and_takes_this_systems_kind(tmp_path: Path) -> None:
    for name in ("zeta.sh", "shims.sh", "alpha.sh", "beta.ps1", "test.ps1"):
        (tmp_path / name).write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    assert [path.name for path in discover_tests(tmp_path, ".sh")] == ["alpha.sh", "zeta.sh"]
    assert [path.name for path in discover_tests(tmp_path, ".ps1")] == ["beta.ps1"]
    assert discover_tests(tmp_path) == discover_tests(tmp_path, suffix_here())
    assert suffix_here("win32") == ".ps1" and suffix_here("linux") == ".sh"


def test_each_kind_of_script_has_its_runner(tmp_path: Path) -> None:
    assert command_for(tmp_path / "a.sh") == ["bash", str(tmp_path / "a.sh")]
    assert command_for(tmp_path / "a.ps1") == ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                               str(tmp_path / "a.ps1")]


def test_the_suites_with_tests_for_this_system_are_listed() -> None:
    """The checkout's BC250 suite has .sh tests (Linux), the Windows Portable Suite .ps1 tests (Windows)."""
    assert suites_here(CHECKOUT, ".sh") == ["bc250-bazzite"]
    assert suites_here(CHECKOUT, ".ps1") == ["windows-portable"]
    assert suite_tests_dir(BC250) == BC250 / "tools" / "installer-tests"


def test_runner_adds_homebrew_fakeroot_directory_to_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_homebrew_bin = tmp_path / "linuxbrew" / "bin"
    fake_homebrew_bin.mkdir(parents=True)
    fakeroot = fake_homebrew_bin / "fakeroot"
    fakeroot.write_text("#!/bin/sh\n", encoding="utf-8")
    fakeroot.chmod(0o755)
    monkeypatch.setattr(runner, "HOMEBREW_BIN_DIRS", (fake_homebrew_bin,))

    sep = os.pathsep
    assert runner._path_with_fakeroot(f"/usr/bin{sep}/bin") == f"{fake_homebrew_bin}{sep}/usr/bin{sep}/bin"
    assert runner._path_with_fakeroot(f"{fake_homebrew_bin}{sep}/usr/bin") == f"{fake_homebrew_bin}{sep}/usr/bin"


@pytest.mark.skipif(sys.platform == "win32", reason="bash scripts")
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


@pytest.mark.skipif(sys.platform == "win32", reason="bash scripts")
def test_runner_executes_selected_tests_in_order_and_continues_after_failure(tmp_path: Path) -> None:
    scripts = [tmp_path / "first.sh", tmp_path / "second.sh"]
    scripts[0].write_text("printf 'first output\\n'\nexit 0\n", encoding="utf-8")
    scripts[1].write_text("printf 'second output\\n'\nexit 7\n", encoding="utf-8")
    test_runner = InstallerTestRunner(tmp_path, tmp_path)
    statuses: list[tuple[str, int, bool]] = []
    output: list[str] = []
    loop = QEventLoop()
    test_runner.test_finished.connect(lambda *result: statuses.append(result))
    test_runner.output.connect(output.append)
    test_runner.run_finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)

    test_runner.start(scripts)
    loop.exec()

    assert statuses == [("first.sh", 0, False), ("second.sh", 7, False)]
    assert "first output\n" in "".join(output)
    assert "second output\n" in "".join(output)
    assert not test_runner.busy


def test_runner_rejects_helpers_and_scripts_outside_the_tests_folder(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "tests"
    scripts_dir.mkdir()
    shim = scripts_dir / "shims.sh"
    shim.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    outside = tmp_path / "outside.sh"
    outside.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    other = scripts_dir / "notes.txt"
    other.write_text("", encoding="utf-8")
    test_runner = InstallerTestRunner(scripts_dir, tmp_path)

    for script in (shim, outside, other):
        with pytest.raises(ValueError):
            test_runner.start([script])


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A checkout with two suites: one with .sh tests, one with .ps1 tests."""
    root = tmp_path / "nexus"
    for suite, scripts in (("bc250-bazzite", ("fan.sh", "check.sh", "shims.sh")),
                           ("windows-portable", ("test.ps1", "bios.ps1"))):
        folder = root / suite / "tools" / "installer-tests"
        folder.mkdir(parents=True)
        (root / suite / "portal").mkdir()
        (root / suite / "portal" / "apps.toml").write_text("", encoding="utf-8")
        for name in scripts:
            (folder / name).write_text("exit 0\n", encoding="utf-8")
    return root


def test_window_lists_the_suites_tests_and_remembers_the_suite(checkout: Path) -> None:
    from PyQt6.QtCore import QSettings
    settings = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "test", "test")
    window = MainWindow(checkout, settings)

    assert window.windowTitle() == APP_NAME
    if sys.platform == "win32":
        assert window.suites == ["windows-portable"] and list(window._items) == ["bios.ps1"]
    else:
        assert window.suites == ["bc250-bazzite"] and list(window._items) == ["check.sh", "fan.sh"]
    assert settings.value(SUITE_KEY) == window.suite
    assert all(
        window.test_list.item(index).text() == ""
        and window._items[window.test_list.item(index).toolTip()][2].text()
        for index in range(window.test_list.count())
    )
    assert window.runner is not None and window.runner.tests_directory == suite_tests_dir(checkout / window.suite)
    window.close()

    window = MainWindow(checkout, settings, suite="nope")          # an unknown suite: the remembered one
    assert window.suite == settings.value(SUITE_KEY)
    window.close()


def test_window_on_the_real_checkout_lists_the_suites_installer_tests() -> None:
    window = MainWindow()
    if sys.platform != "win32":
        assert window.suite == "bc250-bazzite" and "nrt.sh" in window._items and "shims.sh" not in window._items
    window.close()


def test_a_checkout_without_tests_for_this_system_says_so(tmp_path: Path) -> None:
    window = MainWindow(tmp_path)
    assert window.suite is None and window.runner is None
    assert "No suite in" in window.statusBar().currentMessage()
    assert not window.run_all_button.isEnabled()
    window.close()


def test_window_shows_green_check_and_red_cross_at_row_end(checkout: Path) -> None:
    window = MainWindow(checkout)
    passed_name, failed_name = list(window._items)[:2] if len(window._items) > 1 else (list(window._items)[0],) * 2
    _passed_item, _passed_title, _passed_checkbox, passed_status = window._items[passed_name]
    _failed_item, _failed_title, _failed_checkbox, failed_status = window._items[failed_name]

    window._test_finished(passed_name, 0, False)
    window._test_finished(failed_name, 1, False)

    assert failed_status.text() == "✗"
    assert "color: #c62828" in failed_status.styleSheet()
    assert failed_status.toolTip().endswith("exit code 1)")
    if passed_name != failed_name:
        assert passed_status.text() == "✓"
        assert "color: #2e7d32" in passed_status.styleSheet()
        assert passed_status.toolTip().endswith("passed")
    window.close()


@pytest.mark.skipif(sys.platform == "win32", reason="bash scripts")
def test_window_keeps_previous_results_when_another_test_starts(checkout: Path, monkeypatch) -> None:
    window = MainWindow(checkout)
    passed_name, running_name = list(window._items)[:2]
    _item1, _title1, _checkbox1, passed_status = window._items[passed_name]

    window._test_finished(passed_name, 0, False)
    previous = (passed_status.text(), passed_status.styleSheet(), passed_status.toolTip())
    monkeypatch.setattr(window.runner, "start", lambda _scripts: None)

    window._run([window.tests_dir / running_name])
    window._test_started(running_name)

    assert (passed_status.text(), passed_status.styleSheet(), passed_status.toolTip()) == previous
    assert not window.suite_box.isEnabled()            # no other suite while a run is on
    window._run_finished(False)
    assert window.suite_box.isEnabled()
    window.close()


@pytest.mark.skipif(sys.platform == "win32", reason="bash scripts")
def test_cancel_stops_the_current_test_and_skips_queued_tests(tmp_path: Path) -> None:
    first = tmp_path / "first.sh"
    second = tmp_path / "second.sh"
    marker = tmp_path / "second-ran"
    first.write_text("exec sleep 30\n", encoding="utf-8")
    second.write_text('touch "$PWD/second-ran"\n', encoding="utf-8")
    test_runner = InstallerTestRunner(tmp_path, tmp_path)
    statuses: list[tuple[str, int, bool]] = []
    cancelled_runs: list[bool] = []
    loop = QEventLoop()

    def finish_run(cancelled: bool) -> None:
        cancelled_runs.append(cancelled)
        loop.quit()

    test_runner.test_finished.connect(lambda *result: statuses.append(result))
    test_runner.run_finished.connect(finish_run)
    QTimer.singleShot(50, test_runner.cancel)
    QTimer.singleShot(5000, loop.quit)

    test_runner.start([first, second])
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
    launcher = home / ".local" / "bin" / "nexus-installer-tests"
    menu_entry = data / "applications" / "nexus-installer-tests.desktop"
    desktop_entry = desktop / "nexus-installer-tests.desktop"

    install = subprocess.run(["bash", str(INSTALLER)], env=env, capture_output=True, text=True, check=False)

    assert install.returncode == 0, install.stderr
    assert launcher.stat().st_mode & 0o777 == 0o755
    assert f'exec "{ROOT}/run.sh" "$@"' in launcher.read_text(encoding="utf-8")
    assert f"Exec={launcher}" in menu_entry.read_text(encoding="utf-8")
    assert f"Icon={ROOT}/images/nexus-installer-tests-128.png" in desktop_entry.read_text(encoding="utf-8")
    assert desktop_entry.stat().st_mode & 0o111

    without_desktop = subprocess.run(["bash", str(INSTALLER), "--no-desktop-shortcut"], env=env,
                                     capture_output=True, text=True, check=False)

    assert without_desktop.returncode == 0, without_desktop.stderr
    assert launcher.exists() and menu_entry.exists() and not desktop_entry.exists()

    uninstall = subprocess.run(["bash", str(INSTALLER), "--uninstall"], env=env, capture_output=True, text=True,
                               check=False)

    assert uninstall.returncode == 0, uninstall.stderr
    assert not launcher.exists() and not menu_entry.exists() and not desktop_entry.exists()
    assert (ROOT / "run.sh").is_file()
    assert (ROOT / "installer_tests" / "__main__.py").is_file()


def test_a_second_launch_opens_no_window(qapp, monkeypatch):
    """A double-click on the Desktop icon starts the app twice: the second launch hands over to the first."""
    import installer_tests.__main__ as entry
    asked = []
    monkeypatch.setattr(entry, "create_app", lambda *a, **k: qapp)
    monkeypatch.setattr(entry.instance, "already_running", lambda app_id: asked.append(app_id) or True)
    monkeypatch.setattr("sys.argv", ["installer_tests"])
    assert entry.main() == 0 and asked == [entry.APP_ID]
