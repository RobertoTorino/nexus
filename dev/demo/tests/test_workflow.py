# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
from types import SimpleNamespace

import pytest

from demo_recorder import workflow


def test_manifest_lists_optional_apps_and_excludes_required_default(tmp_path):
    manifest = tmp_path / "apps.toml"
    manifest.write_text(
        '[apps.default]\nrequired = true\n'
        '[apps.overlay]\nname = "Overlay"\ndetect = ["~/overlay"]\nlaunch = [["Open", "~/overlay"]]\n',
        encoding="utf-8",
    )

    apps = workflow.load_optional_apps(manifest)

    assert len(apps) == 1
    assert apps[0].key == "overlay"
    assert apps[0].name == "Overlay"


def test_invalid_portal_release_is_rejected(tmp_path):
    with pytest.raises(workflow.WorkflowError, match="not a portal release or suite checkout"):
        workflow.validate_release(tmp_path)


def test_validate_release_accepts_suite_checkout_and_tool_folder(tmp_path):
    (tmp_path / "install.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    portal = tmp_path / "portal"
    portal.mkdir()
    (portal / "apps.toml").write_text(
        '[apps.default]\nrequired = true\n'
        '[apps.overlay]\nname = "Overlay"\ndetect = ["~/overlay"]\nlaunch = [["Open", "~/overlay"]]\n',
        encoding="utf-8",
    )
    tool_folder = tmp_path / "apps" / "fan"
    (tool_folder / "fan_control").mkdir(parents=True)
    (tool_folder / "fan_control" / "__main__.py").touch()

    installer, apps = workflow.validate_release(tool_folder)

    assert installer == tmp_path / "install.sh"
    assert [app.key for app in apps] == ["overlay"]


def test_find_portal_release_selects_newest_valid_folder(tmp_path):
    older = tmp_path / "portal-v0.4.0"
    newer = tmp_path / "portal-v0.5.0"
    invalid = tmp_path / "unrelated-folder"
    for folder in (older, newer):
        folder.mkdir()
        (folder / "install.sh").touch()
        (folder / "apps.toml").write_text(
            '[apps.overlay]\nname = "Overlay"\ndetect = ["~/overlay"]\nlaunch = [["Open", "~/overlay"]]\n',
            encoding="utf-8",
        )
    invalid.mkdir()
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))

    assert workflow.find_portal_release(tmp_path) == newer


def test_find_portal_release_returns_none_for_missing_downloads(tmp_path):
    assert workflow.find_portal_release(tmp_path / "missing") is None


def test_downloads_dir_respects_xdg_download_dir(monkeypatch, tmp_path):
    configured = tmp_path / "My Downloads"
    monkeypatch.setenv("XDG_DOWNLOAD_DIR", str(configured))
    monkeypatch.setattr(workflow.shutil, "which", lambda _name: None)

    assert workflow.downloads_dir() == configured


def test_validate_release_and_detect_installed_paths(tmp_path):
    (tmp_path / "install.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    launcher = tmp_path / "launcher"
    (tmp_path / "apps.toml").write_text(
        f'[apps.overlay]\nname = "Overlay"\ndetect = ["{launcher.as_posix()}"]\nlaunch = [["Open", "{launcher.as_posix()}"]]\n',
        encoding="utf-8",
    )

    installer, apps = workflow.validate_release(tmp_path)

    assert installer == tmp_path / "install.sh"
    assert apps[0].key == "overlay"
    assert not workflow.is_installed(apps[0])
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.touch()
    assert workflow.is_installed(apps[0])


def test_launch_installer_uses_terminal_and_returns_exit_marker(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(workflow, "find_terminal", lambda: ("/usr/bin/konsole", "konsole"))
    monkeypatch.setattr(workflow.subprocess, "Popen", lambda argv, **kwargs: captured.append((argv, kwargs)))

    exit_file = workflow.launch_installer(tmp_path / "portal release" / "install.sh")

    assert captured[0][0][:3] == ["/usr/bin/konsole", "-e", "bash"]
    assert "portal release" in " ".join(captured[0][0])
    assert not exit_file.exists()


def test_recording_helpers_surface_server_errors(monkeypatch):
    class SdkError(Exception):
        pass

    monkeypatch.setitem(sys.modules, "obsws_python", SimpleNamespace(OBSSDKError=SdkError))

    class Client:
        def get_record_status(self):
            raise SdkError("disconnected")

    with pytest.raises(workflow.WorkflowError, match="Could not read OBS recording status"):
        workflow.recording_active(Client())


def test_set_recording_directory_configures_obs_folder(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "obsws_python", SimpleNamespace(OBSSDKError=Exception))
    recording_path = tmp_path / "MediaToolRecordings"
    monkeypatch.setattr(workflow, "RECORDINGS_DIRECTORY", recording_path)

    class Client:
        directory = None

        def set_record_directory(self, directory):
            self.directory = directory

    client = Client()

    assert workflow.set_recording_directory(client) == recording_path
    assert client.directory == str(recording_path)
    assert recording_path.is_dir()


def test_set_recording_directory_reports_obs_request_failure(monkeypatch, tmp_path):
    class SdkError(Exception):
        pass

    monkeypatch.setitem(sys.modules, "obsws_python", SimpleNamespace(OBSSDKError=SdkError))
    monkeypatch.setattr(workflow, "RECORDINGS_DIRECTORY", tmp_path / "MediaToolRecordings")

    class Client:
        def set_record_directory(self, _directory):
            raise SdkError("request rejected")

    with pytest.raises(workflow.WorkflowError, match="Could not set the OBS recording folder"):
        workflow.set_recording_directory(Client())


def test_recent_recordings_returns_newest_video_files(tmp_path):
    older = tmp_path / "older.mkv"
    newer = tmp_path / "newer.MP4"
    ignored = tmp_path / "notes.txt"
    folder = tmp_path / "not-a-recording.mp4"
    older.touch()
    newer.touch()
    ignored.touch()
    folder.mkdir()
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))

    assert workflow.recent_recordings(tmp_path) == (newer, older)


def test_recent_recordings_surfaces_unreadable_folder(tmp_path):
    with pytest.raises(workflow.WorkflowError, match="Could not read the OBS recording folder"):
        workflow.recent_recordings(tmp_path / "missing")


def test_start_recording_trusts_successful_obs_request_without_immediate_status_check(monkeypatch):
    class SdkError(Exception):
        pass

    monkeypatch.setitem(sys.modules, "obsws_python", SimpleNamespace(OBSSDKError=SdkError))

    class Client:
        started = False

        def start_record(self):
            self.started = True

        def get_record_status(self):
            raise AssertionError("a status poll can be stale immediately after StartRecord")

    client = Client()
    workflow.start_recording(client)

    assert client.started


def test_start_recording_reports_obs_request_failure(monkeypatch):
    class SdkError(Exception):
        pass

    monkeypatch.setitem(sys.modules, "obsws_python", SimpleNamespace(OBSSDKError=SdkError))

    class Client:
        def start_record(self):
            raise SdkError("request rejected")

    with pytest.raises(workflow.WorkflowError, match="OBS could not start recording"):
        workflow.start_recording(Client())


def test_stop_recording_trusts_successful_obs_request_without_immediate_status_check(monkeypatch):
    class SdkError(Exception):
        pass

    monkeypatch.setitem(sys.modules, "obsws_python", SimpleNamespace(OBSSDKError=SdkError))

    class Client:
        stopped = False

        def stop_record(self):
            self.stopped = True

        def get_record_status(self):
            raise AssertionError("a status poll can be stale immediately after StopRecord")

    client = Client()
    workflow.stop_recording(client)

    assert client.stopped


def test_stop_recording_reports_obs_request_failure(monkeypatch):
    class SdkError(Exception):
        pass

    monkeypatch.setitem(sys.modules, "obsws_python", SimpleNamespace(OBSSDKError=SdkError))

    class Client:
        def stop_record(self):
            raise SdkError("request rejected")

    with pytest.raises(workflow.WorkflowError, match="OBS could not stop recording"):
        workflow.stop_recording(Client())


def test_connect_obs_converts_websocket_timeout_to_user_error(monkeypatch):
    class WebSocketException(Exception):
        pass

    class WebSocketTimeoutException(WebSocketException):
        pass

    class ReqClient:
        def __init__(self, **_kwargs):
            raise WebSocketTimeoutException("timed out")

    monkeypatch.setitem(
        sys.modules,
        "obsws_python",
        SimpleNamespace(OBSSDKError=Exception, ReqClient=ReqClient),
    )
    monkeypatch.setitem(sys.modules, "websocket", SimpleNamespace(WebSocketException=WebSocketException))

    with pytest.raises(workflow.WorkflowError, match="Could not connect to OBS"):
        workflow.connect_obs("127.0.0.1", 4455, "")


def test_connect_obs_reports_when_obs_is_not_running(monkeypatch):
    class ReqClient:
        def __init__(self, **_kwargs):
            raise ConnectionRefusedError("connection refused")

    monkeypatch.setitem(
        sys.modules,
        "obsws_python",
        SimpleNamespace(OBSSDKError=Exception, ReqClient=ReqClient),
    )
    monkeypatch.setitem(sys.modules, "websocket", SimpleNamespace(WebSocketException=Exception))

    with pytest.raises(workflow.WorkflowError, match="Warning! OBS is not running, start OBS first\\."):
        workflow.connect_obs("127.0.0.1", 4455, "")


def _windows_release(folder, detect: str):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "install.ps1").touch()
    (folder / "apps.toml").write_text(
        "[apps.test]\nrequired = true\n"
        f"[apps.pcsx2]\nname = 'PCSX2'\ndetect = ['{detect}']\nlaunch = [['Open', '{detect}']]\n",
        encoding="utf-8",
    )
    return folder


def test_on_windows_a_release_has_install_ps1_and_its_detect_paths_expand(on_windows, tmp_path, monkeypatch):
    """The Windows Portable Suite's apps.toml names %LOCALAPPDATA%; there is no install from a checkout there."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(workflow.os.path, "expandvars",
                        lambda path: path.replace("%LOCALAPPDATA%", str(tmp_path / "local")))
    release = _windows_release(tmp_path / "wp-portal-v1.0.0", "%LOCALAPPDATA%/pcsx2/PCSX2-Manager.exe")

    installer, apps = workflow.validate_release(release)

    assert installer == release / "install.ps1"
    assert apps[0].detect_paths == (tmp_path / "local" / "pcsx2" / "PCSX2-Manager.exe",)
    (tmp_path / "suite" / "portal").mkdir(parents=True)               # a BC250 suite's folder: not on Windows
    (tmp_path / "suite" / "install.sh").touch()
    (tmp_path / "suite" / "portal" / "apps.toml").write_text((release / "apps.toml").read_text(), encoding="utf-8")
    with pytest.raises(workflow.WorkflowError, match="Windows Portable Suite portal release"):
        workflow.validate_release(tmp_path / "suite")
    assert workflow.find_portal_release(tmp_path) == release


def test_on_windows_the_installer_runs_in_a_powershell_window_of_its_own(on_windows, tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(workflow.subprocess, "Popen", lambda argv, **kwargs: captured.append((argv, kwargs)))
    installer = tmp_path / "it's a release" / "install.ps1"

    exit_file = workflow.launch_installer(installer)

    argv, kwargs = captured[0]
    assert argv[:5] == ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"]
    assert "-File '" + str(installer).replace("'", "''") + "'" in argv[5]     # quoted for PowerShell
    assert str(exit_file) in argv[5] and "$LASTEXITCODE" in argv[5]
    assert kwargs["cwd"] == installer.parent
    assert kwargs["creationflags"] == getattr(workflow.subprocess, "CREATE_NEW_CONSOLE", 0)
    assert not exit_file.exists()


def test_on_windows_obs_is_found_in_program_files(on_windows, tmp_path, monkeypatch):
    monkeypatch.setattr(workflow.shutil, "which", lambda _name: None)
    for variable in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        monkeypatch.delenv(variable, raising=False)
    assert workflow.obs_install_command() is None
    obs = tmp_path / "obs-studio" / "bin" / "64bit" / "obs64.exe"
    obs.parent.mkdir(parents=True)
    obs.touch()
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    assert workflow.obs_install_command() == [str(obs)]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' installer and PowerShell")
def test_on_windows_the_installer_window_writes_the_installers_status(on_windows, tmp_path, monkeypatch):
    """The real window, without its console (the test cannot press Enter): the status file has the exit code."""
    installer = tmp_path / "release" / "install.ps1"
    installer.parent.mkdir()
    installer.write_text("exit 3\n", encoding="utf-8")
    real = workflow.subprocess.Popen
    started = []
    monkeypatch.setattr(workflow.subprocess, "Popen", lambda argv, **kwargs: started.append(
        real(argv, **{**kwargs, "creationflags": workflow.subprocess.CREATE_NO_WINDOW})))

    exit_file = workflow.launch_installer(installer)
    try:
        import time
        end = time.monotonic() + 30
        while not exit_file.exists() and time.monotonic() < end:
            time.sleep(0.1)
        assert exit_file.read_text(encoding="ascii") == "3"
    finally:
        started[0].kill()
        exit_file.unlink(missing_ok=True)
