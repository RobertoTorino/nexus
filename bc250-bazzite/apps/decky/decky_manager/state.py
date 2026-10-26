# SPDX-License-Identifier: GPL-3.0-or-later
"""What the app reads as your own user: the installed Decky version, its service, Steam's switch for it, and the
plugins. Nothing here changes the system except Steam's switch, a file in your own Steam folder.

Decky loads itself into Steam's interface through Steam's remote debugging (CEF), which Steam only opens when the
file .cef-enable-remote-debugging is in its folder when it starts. Decky's installer creates it, its uninstaller
removes it; so does this app."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bc250_core.platform import data_home

from . import APP_ID, __version__
from .loader import SERVICE, Paths

CEF_FILE = ".cef-enable-remote-debugging"
STEAM_DIRS = (                          # Decky's installer: the native Steam and the Flatpak's data folder
    "~/.steam/steam",
    "~/.local/share/Steam",
    "~/.var/app/com.valvesoftware.Steam/data/Steam",
)
JOURNAL_LINES = 60
CHUNK = 1 << 20
TIMEOUT = 30

Command = Callable[[list[str]], tuple[int, str]]
Progress = Callable[[int, int], None]                   # bytes so far, total (0 when unknown)
Download = Callable[[str, Path, Progress | None], None]


def command(argv: list[str]) -> tuple[int, str]:
    try:
        done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return done.returncode, done.stdout


# --- Decky itself ------------------------------------------------------------------------------------------------

def installed_version(paths: Paths) -> str:
    """The installed Decky version ("3.3.0"); "unknown" when the binary is there without its version file; "" when
    Decky is not installed. Decky's own updater writes the same file."""
    if not paths.binary.is_file():
        return ""
    try:
        text = paths.version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return text.removeprefix("v") or "unknown"


@dataclass(frozen=True)
class Service:
    unit: bool                          # /etc/systemd/system/plugin_loader.service is there
    enabled: str                        # systemctl is-enabled: enabled, disabled, not-found, ...
    active: str                         # systemctl is-active: active, inactive, failed, activating, ...

    @property
    def running(self) -> bool:
        return self.active == "active"

    @property
    def at_boot(self) -> bool:
        return self.enabled == "enabled"


def service(paths: Paths, run: Command = command) -> Service:
    def word(argv: list[str]) -> str:
        _code, out = run(argv)
        return (out.strip().splitlines() or ["unknown"])[-1].strip()
    return Service(paths.unit.is_file(), word(["systemctl", "is-enabled", SERVICE]),
                   word(["systemctl", "is-active", SERVICE]))


def journal(run: Command = command, lines: int = JOURNAL_LINES) -> str:
    """Decky's log in the system journal. Bazzite lets members of the wheel group read it."""
    code, out = run(["journalctl", "-u", SERVICE, "-n", str(lines), "--no-pager", "-o", "short-iso"])
    if code != 0 and not out.strip():
        return f"journalctl could not read Decky's log (exit code {code})."
    return out.rstrip()


# --- Steam's switch for it ---------------------------------------------------------------------------------------

def steam_folders(home: Path | None = None) -> list[Path]:
    """The Steam folders that are there, each once (~/.steam/steam is a link to ~/.local/share/Steam)."""
    seen: set[str] = set()
    found = []
    for folder in STEAM_DIRS:
        path = Path(folder.replace("~", str(home), 1) if home else os.path.expanduser(folder))
        if path.is_dir() and os.path.realpath(path) not in seen:
            seen.add(os.path.realpath(path))
            found.append(path)
    return found


def cef_enabled(folders: list[Path]) -> bool:
    return bool(folders) and all((f / CEF_FILE).is_file() for f in folders)


def enable_cef(folders: list[Path]) -> None:
    for folder in folders:
        (folder / CEF_FILE).touch()


def disable_cef(folders: list[Path]) -> None:
    for folder in folders:
        (folder / CEF_FILE).unlink(missing_ok=True)


# --- Plugins -----------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Plugin:
    name: str
    version: str
    author: str
    folder: Path
    disabled: bool = False


def _json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def plugins(paths: Paths) -> list[Plugin]:
    """The plugins as Decky finds them: a folder in ~/homebrew/plugins with plugin.json (name, author), the version
    from package.json beside it, and whether it is switched off in Decky's settings (disabled_plugins)."""
    disabled = _json(paths.loader_settings).get("disabled_plugins") or []
    try:
        folders = sorted(p for p in paths.plugins.iterdir() if (p / "plugin.json").is_file())
    except OSError:
        return []
    found = []
    for folder in folders:
        info = _json(folder / "plugin.json")
        name = str(info.get("name") or folder.name)
        found.append(Plugin(name, str(_json(folder / "package.json").get("version") or ""),
                            str(info.get("author") or ""), folder, name in disabled))
    return sorted(found, key=lambda p: p.name.lower())


# --- The download ------------------------------------------------------------------------------------------------

def download_folder() -> Path:
    return data_home() / APP_ID / "download"


def download(url: str, dest: Path, progress: Progress | None = None) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": f"{APP_ID}/{__version__}"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response, dest.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(CHUNK):
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
