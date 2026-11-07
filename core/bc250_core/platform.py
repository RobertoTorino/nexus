# SPDX-License-Identifier: GPL-3.0-or-later
"""Desktop integration: XDG folders, opening files/URLs, and starting a command in a visible terminal window.

launch_in_terminal() is the bisect GUIs' terminal.py (identical in cu, cores and gpu-oc), plus an optional exit
file: the shell writes the command's exit status there when it ends, so a caller that cannot wait for the detached
terminal (the portal running an installer) can still tell when, and how, it finished.

The Windows side (the Windows Portable Suite, owner 26-10-2026): a suite's folders under %LOCALAPPDATA% and
%APPDATA% (suite_data(), suite_config()), open_path() with the file's own program, a PowerShell window for
launch_in_terminal(), and Start-menu shortcuts. data_home(), config_home(), bin_home() and xdg_open() return what
they always did, on Windows too: the BC250 suite's Windows executable (Bazzite SFTP) keeps its files where they are.

Windows allows 260 characters in a path unless long paths are switched on (an administrator's registry setting,
off on most machines), so the suites keep what they create under PATH_BUDGET; tests/test_platform.py checks it
with a long user name."""

from __future__ import annotations

import base64
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path, PurePath

WINDOWS = sys.platform == "win32"
PATH_BUDGET = 240               # of Windows' 260 (MAX_PATH): room for a file name the suite did not choose
# Windows' process flags (subprocess has them only on Windows; the values let the tests run the Windows side anywhere)
NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10)
NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

# (binary, args-builder) in order of preference. Each builder takes the shell command string
# (already quoted for `bash -lc`) and returns the full argv to exec that terminal with.
_TERMINALS = [
    ("konsole", lambda cmd: ["konsole", "-e", "bash", "-lc", cmd]),
    ("gnome-terminal", lambda cmd: ["gnome-terminal", "--", "bash", "-lc", cmd]),
    ("ptyxis", lambda cmd: ["ptyxis", "--", "bash", "-lc", cmd]),
    ("xfce4-terminal", lambda cmd: ["xfce4-terminal", "-e", f"bash -lc {subprocess.list2cmdline([cmd])}"]),
    ("foot", lambda cmd: ["foot", "bash", "-lc", cmd]),
    ("alacritty", lambda cmd: ["alacritty", "-e", "bash", "-lc", cmd]),
    ("kitty", lambda cmd: ["kitty", "bash", "-lc", cmd]),
    ("x-terminal-emulator", lambda cmd: ["x-terminal-emulator", "-e", f"bash -lc {subprocess.list2cmdline([cmd])}"]),
    ("xterm", lambda cmd: ["xterm", "-e", "bash", "-lc", cmd]),
]


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def bin_home() -> Path:
    return Path(os.environ.get("XDG_BIN_HOME") or Path.home() / ".local" / "bin")


def _windows_folder(variable: str, fallback: str) -> Path:
    return Path(os.environ.get(variable) or Path.home() / fallback)


def local_data() -> Path:
    """Where an app keeps its data on this machine: %LOCALAPPDATA% on Windows, data_home() elsewhere."""
    return _windows_folder("LOCALAPPDATA", "AppData/Local") if WINDOWS else data_home()


def roaming_config() -> Path:
    """Where an app keeps its settings: %APPDATA% on Windows (it roams with the account), config_home() elsewhere."""
    return _windows_folder("APPDATA", "AppData/Roaming") if WINDOWS else config_home()


def suite_data(suite: str) -> Path:
    """A suite's data folder, one for all its apps: %LOCALAPPDATA%\\windows-portable-suite, or
    ~/.local/share/<suite> as the BC250 suite's."""
    return local_data() / suite


def suite_config(suite: str) -> Path:
    """A suite's settings folder: %APPDATA%\\<suite> on Windows, ~/.config/<suite> elsewhere."""
    return roaming_config() / suite


def start_menu() -> Path:
    """The user's Start-menu programs folder (Windows): where an app's shortcut goes, as .desktop files go to
    ~/.local/share/applications on Linux."""
    return roaming_config() / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def private(text: str | PurePath) -> str:
    """*text* (a path, a message, a log line) with the user's folders written as Windows writes them for anyone:
    %LOCALAPPDATA%, %APPDATA% and %USERPROFILE% (Linux: ~ for the home folder), so the user's name never shows on the
    screen or in a log (owner, 29-10-2026: the privacy rule, "we don't do that anywhere"). Every place in the text,
    whatever its case on Windows."""
    text = str(text)
    if WINDOWS:
        folders = [(name, os.environ.get(name, "")) for name in ("LOCALAPPDATA", "APPDATA", "USERPROFILE")]
        folders.append(("USERPROFILE", str(Path.home())))
        for name, folder in sorted(((n, f.rstrip("\\/")) for n, f in folders if f), key=lambda nf: -len(nf[1])):
            if len(folder) > 3:                         # never a drive's root
                text = re.sub(re.escape(folder) + r"(?=[\\/]|\b|$)", lambda _m, n=name: f"%{n}%", text,
                              flags=re.IGNORECASE)
        return text
    home = str(Path.home()).rstrip("/")
    return re.sub(re.escape(home) + r"(?=/|\b|$)", "~", text) if len(home) > 1 else text


def expand(path: str) -> Path:
    """"~/.local/bin/x" and "$XDG_DATA_HOME/…" style paths, as written in a manifest."""
    return Path(os.path.expandvars(os.path.expanduser(path)))


def xdg_open(target: str | Path) -> bool:
    """Open a file, folder or URL with the desktop's default handler; False when xdg-open is missing."""
    opener = shutil.which("xdg-open")
    if opener is None:
        return False
    subprocess.Popen([opener, str(target)], start_new_session=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def open_path(target: str | Path) -> bool:
    """Open a file, folder or URL with its default program: os.startfile on Windows, xdg-open elsewhere. False when
    nothing could open it."""
    if not WINDOWS:
        return xdg_open(target)
    try:
        os.startfile(str(target))  # type: ignore[attr-defined]  # Windows only
    except OSError:
        return False
    return True


def show_in_folder(path: str | Path) -> bool:
    """The folder of the file at *path* in the file manager, with the file selected: Explorer on Windows, else the
    desktop's file manager over D-Bus (org.freedesktop.FileManager1, Dolphin on Bazzite), else the folder opened with
    xdg-open. False when nothing opened it. A saved screenshot shows itself so (owner, 06-11-2026)."""
    path = Path(path)
    if WINDOWS:
        # Explorer may take the front: without it, its window opened behind the full-screen app (owner, 07-11-2026)
        import ctypes
        windll = getattr(ctypes, "windll", None)        # None where Windows is only played (the tests on Linux)
        if windll is not None:
            windll.user32.AllowSetForegroundWindow(-1)
        try:
            # Explorer's own syntax: one argument, "/select," and the path; it exits with 1 even when it worked.
            subprocess.Popen(f'explorer /select,"{path}"', stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError:
            return open_path(path.parent)
        return True
    gdbus = shutil.which("gdbus")
    if gdbus is not None:
        try:
            done = subprocess.run([gdbus, "call", "--session", "--dest", "org.freedesktop.FileManager1",
                                   "--object-path", "/org/freedesktop/FileManager1",
                                   "--method", "org.freedesktop.FileManager1.ShowItems",
                                   f"['{path.resolve().as_uri()}']", ""],
                                  stdin=subprocess.DEVNULL, capture_output=True, timeout=5)
            if done.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass
    return xdg_open(path.parent)


# Windows' touch keyboard (owner, 31-10-2026: R3 in the portable window): its host's own interface, ITipInvocation,
# shows or hides it; the host, TabTip.exe, is started first when it does not run. No administrator, no registry.
TABTIP = r"%CommonProgramFiles%\microsoft shared\ink\TabTip.exe"
TIP_HOST = "{4CE576FA-83DC-4F88-951C-9D0782B4E376}"         # UIHostNoLaunch: the running host only
TIP_INVOCATION = "{37C994E7-432B-4834-A2F7-DCE1F13B834B}"   # ITipInvocation: Toggle(HWND), after IUnknown's three


def toggle_touch_keyboard() -> None:
    """Windows' touch keyboard shown, or hidden when it shows. OSError when its host does not run (start it with
    start_touch_keyboard() and try again) or not on Windows."""
    if not WINDOWS:
        raise OSError("The touch keyboard is Windows'.")
    import ctypes
    from ctypes import wintypes

    class Guid(ctypes.Structure):
        _fields_ = [("data1", ctypes.c_ulong), ("data2", ctypes.c_ushort), ("data3", ctypes.c_ushort),
                    ("data4", ctypes.c_ubyte * 8)]

    ole32, user32 = ctypes.windll.ole32, ctypes.windll.user32  # type: ignore[attr-defined]
    host, invocation = Guid(), Guid()
    ole32.CLSIDFromString(TIP_HOST, ctypes.byref(host))
    ole32.CLSIDFromString(TIP_INVOCATION, ctypes.byref(invocation))
    started = ole32.CoInitialize(None) in (0, 1)              # S_OK, S_FALSE; Qt's thread has COM already
    try:
        tip = ctypes.c_void_p()
        result = ole32.CoCreateInstance(ctypes.byref(host), None, 0x1 | 0x4, ctypes.byref(invocation),
                                        ctypes.byref(tip))    # in-process or local server
        if result != 0 or not tip:
            raise OSError(f"The touch keyboard's host does not answer (0x{result & 0xFFFFFFFF:08x}).")
        table = ctypes.cast(tip, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[2])
        toggle = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND)(table[3])
        try:
            result = toggle(tip, user32.GetDesktopWindow())
        finally:
            release(tip)
        if result != 0:
            raise OSError(f"The touch keyboard did not open (0x{result & 0xFFFFFFFF:08x}).")
    finally:
        if started:
            ole32.CoUninitialize()


def start_touch_keyboard() -> None:
    """The touch keyboard's host started (Windows' shell, as it asks for UI access); OSError when it cannot."""
    if not WINDOWS:
        raise OSError("The touch keyboard is Windows'.")
    program = expand(TABTIP)
    if not program.is_file():
        raise OSError("This Windows has no touch keyboard.")
    os.startfile(str(program))  # type: ignore[attr-defined]  # Windows only


# A window and its monitor as Windows has them, in the screen's own pixels (Qt's apps are per-monitor DPI aware): a
# full-screen window is placed on its monitor's rectangle exactly, as WindowManager does (owner, 07-11-2026: the
# portal's bottom row was cut off again on the TV). Rectangles are (left, top, width, height).
WS_CAPTION, WS_THICKFRAME = 0x00C00000, 0x00040000
SWP_NOACTIVATE, SWP_NOOWNERZORDER, SWP_FRAMECHANGED = 0x0010, 0x0200, 0x0020


def _user32():
    import ctypes
    windll = getattr(ctypes, "windll", None)            # None where Windows is only played (the tests on Linux)
    if not WINDOWS or windll is None:
        raise OSError("A window's place on its monitor is Windows'.")
    return windll.user32


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    """The window's rectangle on the desktop (GetWindowRect); OSError off Windows or when Windows has no answer."""
    import ctypes
    from ctypes import wintypes
    rect = wintypes.RECT()
    if not _user32().GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        raise OSError("Windows did not give the window's rectangle.")
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def monitor_rect(hwnd: int) -> tuple[int, int, int, int]:
    """The whole rectangle of the monitor the window is on (most of it, else the nearest): MonitorFromWindow and
    GetMonitorInfo's rcMonitor, the taskbar included."""
    import ctypes
    from ctypes import wintypes

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]

    user32 = _user32()
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    monitor = user32.MonitorFromWindow(wintypes.HWND(hwnd), 2)     # MONITOR_DEFAULTTONEAREST
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(MonitorInfo)
    if not monitor or not user32.GetMonitorInfoW(wintypes.HMONITOR(monitor), ctypes.byref(info)):
        raise OSError("Windows did not give the window's monitor.")
    rect = info.rcMonitor
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def fill_monitor(hwnd: int, rect: tuple[int, int, int, int]) -> None:
    """The window on *rect* exactly (its monitor's), without a title bar or a sizing frame: they are taken away
    when Windows gave it one, as a full-screen window has none."""
    from ctypes import wintypes
    user32 = _user32()
    style = user32.GetWindowLongW(wintypes.HWND(hwnd), -16)        # GWL_STYLE
    if style & (WS_CAPTION | WS_THICKFRAME):
        user32.SetWindowLongW(wintypes.HWND(hwnd), -16, style & ~(WS_CAPTION | WS_THICKFRAME))
    left, top, width, height = rect
    if not user32.SetWindowPos(wintypes.HWND(hwnd), None, left, top, width, height,
                               SWP_NOACTIVATE | SWP_NOOWNERZORDER | SWP_FRAMECHANGED):
        raise OSError("Windows did not move the window onto its monitor.")


# The device's own screen, as Windows reports its connection (owner, 07-11-2026: no screen found by its name, hardware
# changes): QueryDisplayConfig's output technology of each active screen, the built-in ones' top-left corners.
BUILT_IN = (0x80000000, 6, 11, 13)      # DISPLAYCONFIG_OUTPUT_TECHNOLOGY_ INTERNAL, LVDS, DISPLAYPORT_ and UDI_EMBEDDED


def built_in_screens() -> list[tuple[int, int]]:
    """The top-left corners, on the desktop, of the screens built into the device (a handheld's own panel): Windows'
    QueryDisplayConfig for each active screen's connection, its source's monitor from EnumDisplayMonitors. Empty
    without one (a desktop PC, only a TV); OSError off Windows or when Windows has no answer."""
    import ctypes
    from ctypes import wintypes
    user32 = _user32()

    class Luid(ctypes.Structure):                       # two DWORDs, aligned as one
        _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_int32)]

    class Path(ctypes.Structure):                       # DISPLAYCONFIG_PATH_INFO, 72 bytes
        _fields_ = [("source_adapter", Luid), ("source_id", ctypes.c_uint32), ("source_rest", ctypes.c_uint32 * 2),
                    ("target_adapter", Luid), ("target_id", ctypes.c_uint32), ("target_mode", ctypes.c_uint32),
                    ("output", ctypes.c_uint32), ("target_rest", ctypes.c_uint32 * 7), ("flags", ctypes.c_uint32)]

    class SourceName(ctypes.Structure):                 # DISPLAYCONFIG_SOURCE_DEVICE_NAME
        _fields_ = [("type", ctypes.c_uint32), ("size", ctypes.c_uint32), ("adapter", Luid),
                    ("id", ctypes.c_uint32), ("gdi", ctypes.c_wchar * 32)]

    class MonitorInfo(ctypes.Structure):                # MONITORINFOEXW
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD), ("device", ctypes.c_wchar * 32)]

    paths, modes = ctypes.c_uint32(), ctypes.c_uint32()
    if user32.GetDisplayConfigBufferSizes(2, ctypes.byref(paths), ctypes.byref(modes)):     # QDC_ONLY_ACTIVE_PATHS
        raise OSError("Windows did not give its screens.")
    path_info, mode_info = (Path * paths.value)(), (ctypes.c_byte * (64 * max(modes.value, 1)))()
    if user32.QueryDisplayConfig(2, ctypes.byref(paths), path_info, ctypes.byref(modes), mode_info, None):
        raise OSError("Windows did not give its screens.")
    built_in = set()
    for path in path_info[:paths.value]:
        if path.output not in BUILT_IN:
            continue
        name = SourceName(type=1, size=ctypes.sizeof(SourceName), adapter=path.source_adapter, id=path.source_id)
        if not user32.DisplayConfigGetDeviceInfo(ctypes.byref(name)):    # DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME
            built_in.add(name.gdi)
    corners: list[tuple[int, int]] = []
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                  wintypes.LPARAM)

    def each(monitor, _hdc, _rect, _data):
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(MonitorInfo)
        if user32.GetMonitorInfoW(monitor, ctypes.byref(info)) and info.device in built_in:
            corners.append((info.rcMonitor.left, info.rcMonitor.top))
        return True

    user32.EnumDisplayMonitors(None, None, callback(each), 0)
    return corners


_OUTSIDE = threading.Lock()
BUNDLE_VARIABLES = ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH")     # what PyInstaller's PyQt6 hook sets for the app itself
# What the app's own controller reader sets for SDL (gamepad.PygameSource), for itself only
APP_VARIABLES = ("SDL_VIDEODRIVER", "SDL_AUDIODRIVER", "SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS",
                 "SDL_JOYSTICK_RAWINPUT", "PYGAME_HIDE_SUPPORT_PROMPT")


def _get_dll_directory() -> str:
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    ctypes.windll.kernel32.GetDllDirectoryW(len(buffer), buffer)  # type: ignore[attr-defined]
    return buffer.value


def _set_dll_directory(folder: str | None) -> None:
    import ctypes
    ctypes.windll.kernel32.SetDllDirectoryW(folder)  # type: ignore[attr-defined]


def without_folder(path: str, folder: str) -> str:
    """PATH *path* without its entries that are *folder*."""
    gone = os.path.normcase(os.path.normpath(folder))
    return os.pathsep.join(p for p in path.split(os.pathsep) if p and os.path.normcase(os.path.normpath(p)) != gone)


@contextmanager
def outside_bundle() -> Iterator[None]:
    """A program started within it does not see what the app set up for itself. Windows only; elsewhere nothing.

    The controller reader's SDL variables (APP_VARIABLES): gamepad.py sets SDL_VIDEODRIVER=dummy, so SDL needs no
    window of its own, and a program the app starts inherits it. Steam draws its windows with SDL3, so a Steam started
    by a game manager made its login window without a window (System window 0) and never signed in (the owner's
    Ally, 30-10-2026, in Steam's logs: started with these variables Logged Off, without them signed in within 15 s);
    an emulator that draws with SDL would show no game either. Gone from a release and from the checkout alike.

    In an app built with PyInstaller (the Windows Portable Suite's) also the bundle: the bootloader sets the DLL
    directory to the app's _internal folder and the PyQt6 hook puts that folder first on PATH (and sets
    BUNDLE_VARIABLES), and a program the app starts inherits them: Windows searches the DLL directory before
    System32, and Steam's folder has no VCRUNTIME140.dll, ucrtbase.dll or OpenSSL of its own.

    steam.py starts Steam within it, start_program() and play.py any other program. All of it is put back after."""
    if not WINDOWS:
        yield
        return
    bundle = getattr(sys, "_MEIPASS", None) if getattr(sys, "frozen", False) else None
    names = (*APP_VARIABLES, *(("PATH", *BUNDLE_VARIABLES) if bundle else ()))
    with _OUTSIDE:
        folder = _get_dll_directory() if bundle else ""
        saved = {name: os.environ.get(name) for name in names}
        try:
            if bundle:
                _set_dll_directory(None)
                os.environ["PATH"] = without_folder(saved["PATH"] or "", bundle)
            for name in names:
                if name != "PATH":
                    os.environ.pop(name, None)
            yield
        finally:
            if bundle:
                _set_dll_directory(folder or None)
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def start_program(argv: Sequence[str], cwd: Path | None = None) -> None:
    """*argv* started on its own, outside the app's bundle, in folder *cwd* (a game manager's emulator with a game,
    without Steam: owner, 30-10-2026); a thread collects it when it ends. OSError when it cannot start."""
    with outside_bundle():
        process = subprocess.Popen(list(argv), cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, start_new_session=True)
    threading.Thread(target=process.wait, name="program", daemon=True).start()


def _ps_quote(text: str | PurePath) -> str:
    """*text* as a PowerShell string literal: single quotes, a quote inside doubled."""
    return "'" + str(text).replace("'", "''") + "'"


def powershell_argv(script: str) -> list[str]:
    """powershell.exe running *script*, passed encoded (UTF-16LE, base64), so no quote, semicolon or ampersand in it
    reaches a command line parser."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded]


def powershell_command(command: str, *, keep_open: bool | str = True, exit_file: PurePath | None = None) -> str:
    """The PowerShell script launch_in_terminal() runs on Windows, as terminal_command() is bash's: the command,
    its status written to *exit_file*, and a "Press Enter" pause (always, only after a failure with
    keep_open="on_error", or none). The status is the last program's exit code, or 1 for an error PowerShell
    raised (errors stop the command, as bash's set -e would)."""
    lines = ["$ErrorActionPreference = 'Stop'", "$global:LASTEXITCODE = 0",
             f"try {{ {command} }} catch {{ Write-Host $_ -ForegroundColor Red; $global:LASTEXITCODE = 1 }}",
             "$s = [int]$LASTEXITCODE"]
    if exit_file is not None:
        lines.append(f"Set-Content -LiteralPath {_ps_quote(exit_file)} -Value $s -Encoding Ascii")
    pause = "Write-Host; Read-Host 'Press Enter to close' | Out-Null"
    if keep_open == "on_error":
        lines.append(f"if ($s -ne 0) {{ {pause} }}")
    elif keep_open:
        lines.append(pause)
    lines.append("exit $s")
    return "\n".join(lines)


def make_shortcut(link: Path, target: Path, arguments: str = "", *, workdir: Path | None = None,
                  icon: Path | None = None, description: str = "") -> None:
    """A Windows shortcut (.lnk) at *link* that starts *target* with *arguments*: the Start-menu or Desktop entry of
    an app. Written by Windows itself (WScript.Shell), so Explorer and the Start menu read it as their own.
    Raises RuntimeError when it could not be written."""
    if not WINDOWS:
        raise RuntimeError("Shortcuts (.lnk) are Windows'; on Linux an app gets a .desktop file")
    link.parent.mkdir(parents=True, exist_ok=True)
    script = [f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(link)})",
              f"$s.TargetPath = {_ps_quote(target)}", f"$s.Arguments = {_ps_quote(arguments)}",
              f"$s.WorkingDirectory = {_ps_quote(workdir or target.parent)}",
              f"$s.Description = {_ps_quote(description)}"]
    if icon is not None:
        script.append(f"$s.IconLocation = {_ps_quote(icon)}")
    script.append("$s.Save()")
    result = subprocess.run(powershell_argv("\n".join(script)), capture_output=True, text=True,
                            creationflags=NO_WINDOW)
    if result.returncode != 0 or not link.is_file():
        raise RuntimeError(f"Could not write the shortcut {link}: {result.stderr.strip() or result.stdout.strip()}")


def find_terminal() -> str | None:
    """Best-guess terminal emulator for this session, or None if none could be found."""
    env_term = os.environ.get("TERMINAL")
    if env_term and shutil.which(env_term):
        return env_term
    for name, _ in _TERMINALS:
        if shutil.which(name):
            return name
    return None


def terminal_command(shell_command: str, *, keep_open: bool | str = True,
                     exit_file: PurePath | None = None) -> str:
    """The shell line launch_in_terminal() runs: the command, its exit status written to *exit_file*, and a
    "Press Enter" pause so the window stays readable after the command ends (success, error or Ctrl+C).
    keep_open="on_error" pauses only when the command failed: a window whose command ended well closes by itself
    (the portal's installs, owner 26-10-2026), one that shows an error stays until Enter."""
    line = shell_command
    pause = "echo; read -rp 'Press Enter to close... ' _"
    # A subshell, so the status is the whole command's, also for "a && b" and an early exit.
    if keep_open == "on_error":
        written = f" echo $s > {shlex.quote(str(exit_file))};" if exit_file is not None else ""
        return f"( {line} ); s=$?;{written} [ \"$s\" = 0 ] || {{ {pause}; }}"
    if exit_file is not None:
        line = f"( {line} ); echo $? > {shlex.quote(str(exit_file))}"
    if keep_open:
        line = f"{line}; {pause}"
    return line


def launch_in_terminal(shell_command: str, *, keep_open: bool | str = True,
                       exit_file: PurePath | None = None) -> None:
    """Runs ``shell_command`` (a single already-quoted shell command line) in a new terminal window, detached from
    this process so closing the GUI doesn't touch it.

    Raises RuntimeError if no terminal emulator could be found.

    On Windows ``shell_command`` is a PowerShell command, run in a window of its own (Windows' default terminal:
    Windows Terminal on Windows 11) by powershell_command()."""
    if WINDOWS:
        subprocess.Popen(powershell_argv(powershell_command(shell_command, keep_open=keep_open, exit_file=exit_file)),
                         creationflags=NEW_CONSOLE | NEW_PROCESS_GROUP,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    line = terminal_command(shell_command, keep_open=keep_open, exit_file=exit_file)
    term = find_terminal()
    if term is None:
        raise RuntimeError(
            "No terminal emulator found (tried konsole, gnome-terminal, ptyxis, xfce4-terminal, "
            "foot, alacritty, kitty, x-terminal-emulator, xterm, and $TERMINAL)."
        )
    builder = dict(_TERMINALS).get(term)
    argv = builder(line) if builder else [term, "-e", "bash", "-lc", line]
    # start_new_session detaches it from this process group so it outlives the GUI.
    subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
