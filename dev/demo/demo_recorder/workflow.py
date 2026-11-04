# SPDX-License-Identifier: GPL-3.0-or-later
"""OBS connection, portal release validation, and terminal integration: on Linux a BC250 portal release (install.sh)
in a terminal emulator, on Windows a Windows Portable Suite portal release (install.ps1) in a PowerShell window."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

WINDOWS = sys.platform == "win32"
if WINDOWS:     # the Windows Portable Suite's portal, installed (its install.ps1)
    PORTAL_LAUNCHER = (Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") /
                       "windows-portable-suite" / "portal" / "app" / "Windows-Portable-Suite.exe")
else:
    PORTAL_LAUNCHER = Path.home() / ".local" / "bin" / "bc250-bazzite-suite"   # the BC250 suite's portal, installed
INSTALLER = "install.ps1" if WINDOWS else "install.sh"      # a portal release's installer, beside its apps.toml
OBS_WINDOWS = Path("obs-studio") / "bin" / "64bit" / "obs64.exe"    # under Program Files
OBS_FLATPAK_ID = "com.obsproject.Studio"
RECORDINGS_DIRECTORY = Path.home() / "Videos" / "demos"     # where OBS saves the demos (the tours go to ~/Videos too)
RECORDING_EXTENSIONS = frozenset({".avi", ".flv", ".mkv", ".mov", ".mp4", ".m3u8", ".ts", ".webm"})


class WorkflowError(RuntimeError):
    """A user-actionable failure while preparing or running a demo."""


@dataclass(frozen=True)
class DemoApp:
    key: str
    name: str
    detect_paths: tuple[Path, ...]


def load_optional_apps(manifest: Path) -> tuple[DemoApp, ...]:
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise WorkflowError(f"Could not read {manifest}: {exc}") from exc
    apps = data.get("apps")
    if not isinstance(apps, dict):
        raise WorkflowError(f"{manifest} has no [apps] table.")

    choices: list[DemoApp] = []
    for key, entry in apps.items():
        if not isinstance(entry, dict) or entry.get("required", False):
            continue
        name, detect, launch = entry.get("name"), entry.get("detect"), entry.get("launch")
        has_launch = isinstance(launch, list) and any(
            isinstance(action, list) and len(action) == 2 and all(isinstance(item, str) for item in action)
            for action in launch
        )
        if not isinstance(name, str) or not name or not isinstance(detect, list) or not detect or \
                not all(isinstance(path, str) for path in detect) or not has_launch:
            raise WorkflowError(f"{manifest}: apps.{key} has invalid name, detect, or launch settings.")
        choices.append(DemoApp(key, name, tuple(_detect_path(path) for path in detect)))
    if not choices:
        raise WorkflowError(f"{manifest} has no optional launchable apps.")
    return tuple(choices)


def _detect_path(path: str) -> Path:
    """A detect path of the manifest: the Windows suite's name %LOCALAPPDATA% and the like, the BC250 suite's ~."""
    return Path(os.path.expandvars(path)).expanduser() if WINDOWS else Path(path).expanduser()


def validate_release(folder: Path) -> tuple[Path, tuple[DemoApp, ...]]:
    selected = folder.expanduser().resolve()
    installer, manifest = selected / INSTALLER, selected / "apps.toml"
    if installer.is_file() and manifest.is_file():
        return installer, load_optional_apps(manifest)
    if WINDOWS:     # the Windows suite's portal installs from a release only: its program is built at release time
        raise WorkflowError(
            f"{selected} is not a portal release. Choose an extracted Windows Portable Suite portal release folder "
            "(wp-portal-v<x.y.z>.zip, extracted)."
        )

    for checkout in (selected, *selected.parents):
        checkout_installer = checkout / "install.sh"
        checkout_manifest = checkout / "portal" / "apps.toml"
        if checkout_installer.is_file() and checkout_manifest.is_file():
            return checkout_installer, load_optional_apps(checkout_manifest)

    raise WorkflowError(
        f"{selected} is not a portal release or suite checkout. Choose an extracted portal release folder, "
        "or a suite's folder in a checkout of the repository (bc250-bazzite/)."
    )


def downloads_dir() -> Path:
    configured = os.environ.get("XDG_DOWNLOAD_DIR")
    if configured:
        return Path(os.path.expandvars(os.path.expanduser(configured)))
    xdg_user_dir = shutil.which("xdg-user-dir")
    if xdg_user_dir:
        try:
            result = subprocess.run([xdg_user_dir, "DOWNLOAD"], capture_output=True, text=True,
                                    check=False, timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            result = None
        if result is not None and result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).expanduser()
    return Path.home() / "Downloads"


def find_portal_release(downloads: Path | None = None) -> Path | None:
    """Find the newest valid extracted portal release directly inside the Downloads folder."""
    folder = (downloads or downloads_dir()).expanduser()
    try:
        candidates = [path for path in folder.iterdir() if path.is_dir()]
    except OSError:
        return None
    valid: list[Path] = []
    for candidate in candidates:
        try:
            validate_release(candidate)
        except (OSError, WorkflowError):
            continue
        valid.append(candidate)
    if not valid:
        return None
    return max(valid, key=lambda path: path.stat().st_mtime)


def is_installed(app: DemoApp) -> bool:
    return any(path.exists() or path.is_symlink() for path in app.detect_paths)


def obs_install_command() -> list[str] | None:
    if WINDOWS:
        found = shutil.which("obs64")
        if found:
            return [found]
        for variable in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
            base = os.environ.get(variable)
            if base and (Path(base) / OBS_WINDOWS).is_file():
                return [str(Path(base) / OBS_WINDOWS)]
        return None
    for executable in ("obs", "obs-studio"):
        path = shutil.which(executable)
        if path:
            return [path]
    flatpak = shutil.which("flatpak")
    if flatpak:
        try:
            result = subprocess.run([flatpak, "info", OBS_FLATPAK_ID], check=False, capture_output=True,
                                    text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode == 0:
            return [flatpak, "run", OBS_FLATPAK_ID]
    return None


def connect_obs(host: str, port: int, password: str):
    try:
        import obsws_python as obs
        import websocket
    except ImportError as exc:
        raise WorkflowError("The OBS WebSocket client is missing: install the checkout's requirements-dev.txt "
                            "in the dev venv (obsws-python).") from exc
    try:
        client = obs.ReqClient(host=host, port=port, password=password, timeout=3)
        version = client.get_version()
        obs_version = version.obs_version
    except ConnectionRefusedError as exc:
        raise WorkflowError("Warning! OBS is not running, start OBS first.") from exc
    except (obs.OBSSDKError, websocket.WebSocketException, OSError, ValueError, AttributeError) as exc:
        raise WorkflowError(
            f"Could not connect to OBS at {host}:{port}: {exc}\n\n"
            "Open OBS → Tools → WebSocket Server Settings, enable the server, and check the port and password."
        ) from exc
    return client, obs_version


def recording_active(client) -> bool:
    import obsws_python as obs

    try:
        return client.get_record_status().output_active
    except (obs.OBSSDKError, OSError) as exc:
        raise WorkflowError(f"Could not read OBS recording status: {exc}") from exc


def set_recording_directory(client) -> Path:
    import obsws_python as obs

    try:
        RECORDINGS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise WorkflowError(f"Could not create the recordings folder {RECORDINGS_DIRECTORY}: {exc}") from exc
    try:
        client.set_record_directory(str(RECORDINGS_DIRECTORY))
    except (obs.OBSSDKError, OSError, AttributeError) as exc:
        raise WorkflowError(
            f"Could not set the OBS recording folder to {RECORDINGS_DIRECTORY}: {exc}\n"
            "OBS WebSocket 5.3 or newer is required."
        ) from exc
    return RECORDINGS_DIRECTORY


def recordings_directory() -> Path:
    return RECORDINGS_DIRECTORY


def recent_recordings(directory: Path, limit: int = 10) -> tuple[Path, ...]:
    try:
        recordings = [
            (path, path.stat().st_mtime_ns)
            for path in directory.iterdir()
            if path.suffix.lower() in RECORDING_EXTENSIONS and path.is_file()
        ]
    except OSError as exc:
        raise WorkflowError(f"Could not read the OBS recording folder {directory}: {exc}") from exc
    recordings.sort(key=lambda recording: recording[1], reverse=True)
    return tuple(recording[0] for recording in recordings[:limit])


def start_recording(client) -> None:
    import obsws_python as obs

    try:
        client.start_record()
    except (obs.OBSSDKError, OSError) as exc:
        raise WorkflowError(f"OBS could not start recording: {exc}") from exc


def stop_recording(client) -> None:
    import obsws_python as obs

    try:
        client.stop_record()
    except (obs.OBSSDKError, OSError) as exc:
        raise WorkflowError(f"OBS could not stop recording: {exc}") from exc


def find_terminal() -> tuple[str, str] | None:
    terminals = (
        ("konsole", "konsole"),
        ("gnome-terminal", "gnome"),
        ("ptyxis", "gnome"),
        ("xfce4-terminal", "xfce"),
        ("foot", "direct"),
        ("alacritty", "direct"),
        ("kitty", "kitty"),
        ("x-terminal-emulator", "xterm"),
        ("xterm", "direct"),
    )
    configured = os.environ.get("TERMINAL")
    if configured and shutil.which(configured):
        return configured, "direct"
    for executable, kind in terminals:
        path = shutil.which(executable)
        if path:
            return path, kind
    return None


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def launch_installer_windows(installer: Path) -> Path:
    """The release's install.ps1 in a PowerShell window of its own, for its output; the exit file gets its status."""
    descriptor, name = tempfile.mkstemp(prefix="nexus-demo-installer-")
    os.close(descriptor)
    exit_file = Path(name)
    exit_file.unlink()
    script = (
        f"& powershell -NoProfile -ExecutionPolicy Bypass -File {_ps_quote(str(installer))}; $result = $LASTEXITCODE; "
        f"Set-Content -LiteralPath {_ps_quote(str(exit_file))} -Value $result -NoNewline -Encoding ascii; "
        "Write-Host; Read-Host 'Installer finished. Press Enter to close this window'"
    )
    argv = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
    try:
        subprocess.Popen(argv, cwd=installer.parent, stdin=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    except OSError as exc:
        exit_file.unlink(missing_ok=True)
        raise WorkflowError(f"Could not open the installer window: {exc}") from exc
    return exit_file


def launch_installer(installer: Path) -> Path:
    if WINDOWS:
        return launch_installer_windows(installer)
    terminal = find_terminal()
    if terminal is None:
        raise WorkflowError("No supported terminal emulator was found to run the portal installer.")
    descriptor, name = tempfile.mkstemp(prefix="nexus-demo-installer-")
    os.close(descriptor)
    exit_file = Path(name)
    exit_file.unlink()
    command = shlex.join(["bash", str(installer)])
    line = (
        f"( {command} ); result=$?; printf '%s' \"$result\" > {shlex.quote(str(exit_file))}; "
        "echo; read -rp 'Installer finished. Press Enter to close this terminal. ' _"
    )
    executable, kind = terminal
    if kind == "konsole":
        argv = [executable, "-e", "bash", "-lc", line]
    elif kind == "gnome":
        argv = [executable, "--", "bash", "-lc", line]
    elif kind == "xfce":
        argv = [executable, "-e", f"bash -lc {shlex.quote(line)}"]
    elif kind == "kitty":
        argv = [executable, "bash", "-lc", line]
    elif kind == "xterm":
        argv = [executable, "-e", "bash", "-lc", line]
    else:
        argv = [executable, "bash", "-lc", line]
    try:
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, start_new_session=True)
    except OSError as exc:
        exit_file.unlink(missing_ok=True)
        raise WorkflowError(f"Could not open the installer terminal: {exc}") from exc
    return exit_file
