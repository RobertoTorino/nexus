# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
from types import SimpleNamespace

import pytest

from media_tool import workflow


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
    tool_folder = tmp_path / "apps" / "mtool"
    (tool_folder / "media_tool").mkdir(parents=True)
    (tool_folder / "media_tool" / "__main__.py").touch()

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
        f'[apps.overlay]\nname = "Overlay"\ndetect = ["{launcher}"]\nlaunch = [["Open", "{launcher}"]]\n',
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
