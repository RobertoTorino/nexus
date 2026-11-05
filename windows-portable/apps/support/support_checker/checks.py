# SPDX-License-Identifier: GPL-3.0-or-later
"""What Support Checker reads, without Qt and without the network: Windows' version and its updates, the tools and
runtimes the suite's apps need (and which installed app needs each), and each app's installed version against the
portal's. The BC250 suite's Dependency Checker, for Windows (owner, 05-11-2026): its Bazzite card is the Windows
card here; its Python packages are left out, as every app of this suite is a program with its packages inside, its
release tested with them.

Every check only reads: the registry, files, and two commands without a window (Windows' tar, for its version;
PowerShell, for the last update Windows installed). Nothing is installed or changed."""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from bc250_core import steam, xbox
from bc250_core.platform import expand, suite_data

from . import ROOT, SUITE

NO_WINDOW = 0x08000000                  # CREATE_NO_WINDOW: a command runs without a console window of its own
TIMEOUT = 60
UPDATE_DAYS = 40                        # Windows installs a cumulative update every month: older than this is late
SYSTEM32 = Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32"
PORTAL = "portal"                       # the portal's folder in the suite's, and its key


# --- The apps, as the portal lists them -----------------------------------------------------------------------------

@dataclass(frozen=True)
class App:
    key: str
    name: str
    tag: str                            # the release the portal pins: wp-<key>-v<version>
    detect: tuple[str, ...]

    @property
    def version(self) -> str:
        return self.tag.rsplit("-v", 1)[-1] if "-v" in self.tag else ""


def portal_dir() -> Path:
    """The portal's folder: installed.json (what it installed), and app\\ with its program and apps.toml."""
    return suite_data(SUITE) / PORTAL


def manifest_path(folder: Path | None = None) -> Path | None:
    """The installed portal's apps.toml (in its program's _internal\\), else the checkout's beside this app (run from
    the checkout); None when there is neither."""
    folder = folder or portal_dir()
    for path in (folder / "app" / "_internal" / "apps.toml", folder / "app" / "apps.toml",
                 ROOT.parent.parent / "portal" / "apps.toml"):
        if path.is_file():
            return path
    return None


def load_apps(path: Path | None) -> list[App]:
    """The portal's apps, in its order; [] without a manifest."""
    if path is None:
        return []
    try:
        table = tomllib.loads(path.read_text(encoding="utf-8")).get("apps", {})
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [App(key, str(entry.get("name", key)), str(entry.get("tag", "")), tuple(entry.get("detect", ())))
            for key, entry in table.items()]


def records(folder: Path | None = None) -> dict[str, str]:
    """installed.json: the tag of each app the portal installed."""
    try:
        data = json.loads(((folder or portal_dir()) / "installed.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def is_installed(app: App) -> bool:
    return any(expand(path).exists() for path in app.detect)


@dataclass(frozen=True)
class AppState:
    app: App
    status: str                         # Up to date, Update in the portal, Version unknown, Not installed
    installed: str = ""                 # the version installed, "" when unknown


def app_states(apps: list[App], recorded: dict[str, str],
               installed: Callable[[App], bool] = is_installed) -> list[AppState]:
    """Each app's state: its installed version (as the portal recorded it) against the one the portal pins."""
    states = []
    for app in apps:
        if not installed(app):
            states.append(AppState(app, "Not installed"))
            continue
        tag = recorded.get(app.key, "")
        version = tag.rsplit("-v", 1)[-1] if "-v" in tag else ""
        if not version:
            states.append(AppState(app, "Version unknown"))
        elif _version(version) < _version(app.version):
            states.append(AppState(app, "Update in the portal", version))
        else:
            states.append(AppState(app, "Up to date", version))
    return states


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split(".") if part.isdigit())


# --- The tools ------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Found:
    ok: bool                            # there, in a form the apps can use
    where: str = ""                     # where it was found, or what is missing
    unsupported: str = ""               # there, but not usable: why


@dataclass(frozen=True)
class Tool:
    key: str
    name: str
    about: str                          # what it is and what the apps use it for
    users: dict[str, str] = field(default_factory=dict)     # app key: "required" or "optional"
    advice: str = ""                    # how to get it


RUNTIME_DLLS = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_atomic_wait.dll")
TOOLS = (
    Tool("powershell", "Windows PowerShell",
         "Windows' own shell. The portal runs each app's installer (install.ps1) in it, and the apps run it for a "
         "few steps of their own.",
         {PORTAL: "required"}, "It comes with Windows; a Windows without it cannot install the suite's apps."),
    Tool("vcruntime", "Microsoft Visual C++ runtime",
         "The runtime libraries of programs built with Visual C++ (vcruntime140.dll, msvcp140.dll and the like in "
         "System32). The emulators RPCS3, shadPS4, Vita3K and Xenia are built with it and do not start without it; "
         "Steam and most games bring it.",
         {"rpcs3": "required", "shadps4": "required", "vita3k": "required", "xenia": "required"},
         "Install vc_redist.x64.exe from Microsoft (https://aka.ms/vs/17/release/vc_redist.x64.exe)."),
    Tool("tar", "Windows' tar (with 7z)",
         "Windows' own tar (C:\\Windows\\System32\\tar.exe, bsdtar). The managers of RPCS3, Vita3K, Xenia and PCSX2 "
         "unpack the emulator's archive with it; a .7z needs a tar built with liblzma, which Windows 11 has.",
         {"pcsx2": "required", "rpcs3": "required", "vita3k": "required", "xenia": "required"},
         "Windows 11 brings it; Windows 10's tar cannot unpack a .7z."),
    Tool("steam", "Steam",
         "Valve's Steam. The game managers put your games in its library and start them through it (in Big "
         "Picture mode, with Steam Input), Remote Play is started from it, and the portal's RT opens it. Without "
         "Steam each game manager starts a game in its emulator itself.",
         {"pcsx2": "optional", "ppsspp": "optional", "rpcs3": "optional", "rplay": "optional",
          "shadps4": "optional", "vita3k": "optional", "xenia": "optional", PORTAL: "optional"},
         "Install it from https://store.steampowered.com/about/, and start it once."),
    Tool("xbox", "XBOX app",
         "Microsoft's XBOX app, the home of the handheld's XBOX mode. The portal's XBOX menu setting puts the suite "
         "in its library, so XBOX mode starts it.",
         {PORTAL: "optional"}, "It comes with the handheld; else from the Microsoft Store."),
)


def find_powershell(system32: Path = SYSTEM32) -> Found:
    path = system32 / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return Found(path.is_file(), str(path) if path.is_file() else f"{path} is not there")


def find_vcruntime(system32: Path = SYSTEM32) -> Found:
    missing = [name for name in RUNTIME_DLLS if not (system32 / name).is_file()]
    if missing:
        return Found(False, f"missing in System32: {', '.join(missing)}")
    return Found(True, f"{system32} ({len(RUNTIME_DLLS)} files)")


def _run(argv: list[str], timeout: int = TIMEOUT) -> str:
    """A command's output, without a window; "" when it does not run."""
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                                creationflags=NO_WINDOW if sys.platform == "win32" else 0)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout


def find_tar(system32: Path = SYSTEM32, run: Callable[[list[str]], str] = _run) -> Found:
    tar = system32 / "tar.exe"
    if not tar.is_file():
        return Found(False, f"{tar} is not there")
    version = run([str(tar), "--version"])
    if "liblzma" not in version:
        first = version.splitlines()[0] if version else "it did not run"
        return Found(True, str(tar), f"built without liblzma ({first}): it cannot unpack a .7z")
    return Found(True, f"{tar} ({version.splitlines()[0]})")


def find_steam() -> Found:
    folder = steam.find_steam()
    return Found(folder is not None, str(folder) if folder is not None else "no Steam folder was found")


def find_xbox() -> Found:
    there = xbox.installed()
    return Found(there, "installed" if there else "not installed")


FINDERS: dict[str, Callable[[], Found]] = {"powershell": find_powershell, "vcruntime": find_vcruntime,
                                           "tar": find_tar, "steam": find_steam, "xbox": find_xbox}


@dataclass(frozen=True)
class ToolState:
    tool: Tool
    status: str                         # Available, Missing, Not installed, Unsupported build, Not needed
    found: Found
    needed_by: tuple[str, ...]          # the installed apps that use it (their names)
    required: bool                      # an installed app needs it


def tool_states(present: set[str], names: dict[str, str], finders: dict[str, Callable[[], Found]] | None = None
                ) -> list[ToolState]:
    """Each tool's state for the installed apps (*present*: their keys, the portal's included; *names*: key to name):
    the most urgent status that applies, as Dependency Checker's."""
    finders = finders or FINDERS
    states = []
    for tool in TOOLS:
        users = [key for key in tool.users if key in present]
        required = any(tool.users[key] == "required" for key in users)
        found = finders[tool.key]()
        if not users:
            status = "Not needed"
        elif found.unsupported:
            status = "Unsupported build"
        elif found.ok:
            status = "Available"
        else:
            status = "Missing" if required else "Not installed"
        states.append(ToolState(tool, status, found, tuple(names.get(key, key) for key in users), required))
    return states


# --- Windows --------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class WindowsState:
    name: str = ""                      # "Windows 11 Home"
    version: str = ""                   # "24H2"
    build: str = ""                     # "26100.4351"
    restart: bool = False               # an update waits for a restart
    last_update: str = ""               # the newest update installed: "2026-10-14 (KB5066835)", "" when not known
    last_date: datetime.date | None = None

    def status(self, today: datetime.date | None = None) -> str:
        """Restart to update, Update late, Up to date, or Unknown."""
        if self.restart:
            return "Restart to update"
        if self.last_date is None:
            return "Unknown"
        if ((today or datetime.date.today()) - self.last_date).days > UPDATE_DAYS:
            return "Update late"
        return "Up to date"


CURRENT_VERSION = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
RESTART_KEYS = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending")
LAST_UPDATE = ("Get-CimInstance Win32_QuickFixEngineering | Where-Object InstalledOn | Sort-Object InstalledOn "
               "-Descending | Select-Object -First 1 | ForEach-Object { $_.InstalledOn.ToString('yyyy-MM-dd') + ' ' "
               "+ $_.HotFixID }")


def _registry(path: str, name: str | None = None) -> object:
    """A value of HKEY_LOCAL_MACHINE\\*path* (with *name*), or whether the key is there (without); None elsewhere."""
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            return True if name is None else winreg.QueryValueEx(key, name)[0]
    except OSError:
        return False if name is None else None


def read_windows(registry: Callable[..., object] = _registry, run: Callable[[list[str]], str] = _run) -> WindowsState:
    """Windows' name, version and build (the registry), whether an update waits for a restart (Windows Update's and
    the component servicing's keys), and the newest update installed (PowerShell, without a window)."""
    name = str(registry(CURRENT_VERSION, "ProductName") or "Windows")
    build = str(registry(CURRENT_VERSION, "CurrentBuild") or "")
    ubr = registry(CURRENT_VERSION, "UBR")
    if build and isinstance(ubr, int):
        build = f"{build}.{ubr}"
    if build.split(".")[0].isdigit() and int(build.split(".")[0]) >= 22000:
        name = name.replace("Windows 10", "Windows 11")     # Windows 11 still names itself 10 in ProductName
    version = str(registry(CURRENT_VERSION, "DisplayVersion") or "")
    restart = any(registry(key) is True for key in RESTART_KEYS)
    last = run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", LAST_UPDATE]).strip()
    date = None
    try:
        date = datetime.date.fromisoformat(last.split()[0]) if last else None
    except ValueError:
        last = ""
    shown = f"{last.split()[0]} ({last.split()[1]})" if date and len(last.split()) > 1 else (last if date else "")
    return WindowsState(name, version, build, restart, shown, date)


# --- Everything at once ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Report:
    windows: WindowsState
    tools: list[ToolState]
    apps: list[AppState]
    manifest: Path | None


def check_all(folder: Path | None = None) -> Report:
    """Every check, for the window's worker thread."""
    folder = folder or portal_dir()
    manifest = manifest_path(folder)
    apps = load_apps(manifest)
    states = app_states(apps, records(folder))
    present = {state.app.key for state in states if state.status != "Not installed"} | {PORTAL}
    names = {app.key: app.name for app in apps} | {PORTAL: "the portal"}
    return Report(read_windows(), tool_states(present, names), states, manifest)
