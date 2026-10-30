# SPDX-License-Identifier: GPL-3.0-or-later
"""A game played through an app's play mode (the Windows Portable Suite's game managers; owner, 30-10-2026: one way
out of every game, "Hold View + Menu, everywhere"): the app's own program, started by the game's Steam shortcut (or
by the app itself on a device without Steam) as <program> --play <the emulator's arguments>, starts the emulator
outside the app's bundle, watches the controller while it runs, and when View and Menu are held together for HOLD
seconds asks the emulator's windows to close, as Alt+F4 does, so it saves and ends as on any close; one still
running GRACE seconds later is ended. It ends with the emulator, with its exit code, so Steam sees the game end.

The emulators had five ways out (PCSX2's quit chord, shadPS4's and RPCS3's menus, PPSSPP's pause menu, Steam's
overlay for Vita3K and Xenia, which have none of their own), and none was on the screen. A press shorter than HOLD
still does what the emulator does with it.

launcher() is what a shortcut starts: the app's program in a release, its run.ps1 from the checkout (in a hidden
PowerShell window: Steam cannot set PYTHONPATH). Windows only; the standard library and core's gamepad reader."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from .platform import outside_bundle

HOLD = 2.0                      # s View and Menu are held together before the game is closed
GRACE = 10.0                    # s an emulator asked to close has before it is ended
ASK = 1.0                       # s after the close before an emulator's own quit question is answered
POLL = 0.05                     # s between two looks at the controller and the emulator
CHORD = ("back", "start")       # SDL's names of View and Menu
FLAG = "--play"                 # the app's argument for its play mode
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
QUIT_HINT = "In the game, hold View and Menu together to quit."


def launcher(app_root: Path, frozen: bool | None = None, program: str | None = None) -> tuple[str, list[str]]:
    """(the program a shortcut starts, the arguments before the emulator's): the app's own program with --play in a
    release (*frozen*: built with PyInstaller), its run.ps1 in a hidden PowerShell window from the checkout."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if frozen:
        return program or sys.executable, [FLAG]
    return POWERSHELL, ["-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File",
                        str(app_root / "run.ps1"), FLAG]


def launch_options(before: Sequence[str], options: str) -> str:
    """A shortcut's launch options: the launcher's arguments, then the emulator's, as Steam passes them on."""
    return f"{subprocess.list2cmdline(list(before))} {options}"


def programs(exe_name: str) -> set[str]:
    """The program names (in lower case) a shortcut of the app's play mode starts: the app's own, or PowerShell."""
    return {f"{exe_name}.exe".lower(), "powershell.exe"}


def played(exe: str, options: str, app_root: Path) -> bool:
    """Whether a shortcut starts the game through the play mode as launcher() says now: its program, and its launch
    options beginning with the launcher's arguments (False: one made before, which starts the emulator itself)."""
    program, before = launcher(app_root)
    return (os.path.normcase(exe.strip('"')) == os.path.normcase(program)
            and options.startswith(subprocess.list2cmdline(before)))


def _process_tree(pid: int) -> set[int]:
    """*pid* and every process it started, and theirs (an emulator that runs its game in a child)."""
    import ctypes

    class Entry(ctypes.Structure):               # PROCESSENTRY32W
        _fields_ = [("size", ctypes.c_ulong), ("usage", ctypes.c_ulong), ("pid", ctypes.c_ulong),
                    ("heap", ctypes.c_size_t), ("module", ctypes.c_ulong), ("threads", ctypes.c_ulong),
                    ("parent", ctypes.c_ulong), ("priority", ctypes.c_long), ("flags", ctypes.c_ulong),
                    ("exe", ctypes.c_wchar * 260)]
    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    snapshot = k32.CreateToolhelp32Snapshot(0x2, 0)    # TH32CS_SNAPPROCESS
    parents: dict[int, int] = {}
    if snapshot and snapshot != ctypes.c_void_p(-1).value:
        try:
            entry = Entry()
            entry.size = ctypes.sizeof(Entry)
            more = k32.Process32FirstW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
            while more:
                parents[entry.pid] = entry.parent
                more = k32.Process32NextW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
        finally:
            k32.CloseHandle(ctypes.c_void_p(snapshot))
    tree = {pid}
    grown = True
    while grown:
        grown = False
        for child, parent in parents.items():
            if parent in tree and child not in tree:
                tree.add(child)
                grown = True
    return tree


def main_windows(pid: int) -> list[int]:
    """The main windows of *pid* and the processes it started: visible, top-level, without an owner and not a tool
    window. Steam's overlay lives in the game's process too, with windows of its own: a close sent to every window
    opened it over the game (the owner's Ally, 30-10-2026, shadPS4 with Galaga)."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    tree = _process_tree(pid)
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _param):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if (owner.value in tree and user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, 4)  # GW_OWNER
                and not user32.GetWindowLongPtrW(hwnd, -20) & 0x80):                               # WS_EX_TOOLWINDOW
            found.append(hwnd)
        return True
    user32.EnumWindows(visit, 0)
    return found


def close_windows(pid: int) -> int:
    """WM_CLOSE to the main windows of *pid* and the processes it started, as Alt+F4 sends; how many were asked."""
    import ctypes
    windows = main_windows(pid)
    for hwnd in windows:
        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # type: ignore[attr-defined]  # WM_CLOSE
    return len(windows)


def press_enter(pid: int) -> int:
    """Enter pressed in the main windows of *pid*: the answer to an emulator's own "Are you sure you want to quit?"
    after a close (shadPS4's: "Press Enter or Cross/A button to quit"); how many got it."""
    import ctypes
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    windows = main_windows(pid)
    for hwnd in windows:
        user32.PostMessageW(hwnd, 0x0100, 0x0D, 0x001C0001)    # WM_KEYDOWN, VK_RETURN, its scan code
        user32.PostMessageW(hwnd, 0x0101, 0x0D, 0xC01C0001)    # WM_KEYUP
    return len(windows)


def _start(command: Sequence[str], cwd: Path) -> subprocess.Popen:
    with outside_bundle():
        return subprocess.Popen(list(command), cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)


def _pad():
    from .gamepad import PygameSource
    return PygameSource()


def run(command: Sequence[str], cwd: Path, log: Callable[[str], None] = lambda line: None,
        start: Callable[[Sequence[str], Path], subprocess.Popen] = _start, pad: Callable[[], object] = _pad,
        close: Callable[[int], int] = close_windows, clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep, hold: float = HOLD, grace: float = GRACE,
        confirm: Callable[[int], int] | None = None) -> int:
    """The emulator *command* run in *cwd* to its end, closed on View and Menu held for *hold* seconds; its exit
    code. *confirm*: for an emulator that asks before it quits (shadPS4), what answers yes (press_enter), ASK seconds
    after the close while it still runs. Without a controller reader (no pygame-ce, no SDL) the game still runs, only
    without the chord. OSError when the emulator cannot start."""
    process = start(command, cwd)
    log(f"Play: {Path(command[0]).name} started; View and Menu held for {hold:g} s close it.")
    try:
        source = pad()
    except Exception as error:  # noqa: BLE001  (no controller reader: the game runs, without the chord)
        source = None
        log(f"Play: no controller reader ({error}); the game runs without the quit chord.")
    pressed: set[str] = set()
    since = asked = None
    try:
        while process.poll() is None:
            for kind, name, value in (source.events() if source is not None else []):
                if kind == "button":
                    (pressed.add if value else pressed.discard)(name)
                elif kind == "removed":
                    pressed.clear()
            now = clock()
            since = (since if since is not None else now) if all(b in pressed for b in CHORD) else None
            if asked is None and since is not None and now - since >= hold:
                asked = now
                log(f"Play: View and Menu held; {close(process.pid)} window(s) of the emulator asked to close.")
            elif asked is not None and confirm is not None and now - asked >= ASK:
                log(f"Play: the emulator asks before it quits; answered in {confirm(process.pid)} window(s).")
                confirm = None
            elif asked is not None and now - asked >= grace:
                log(f"Play: the emulator did not close within {grace:g} s; ended.")
                process.terminate()
                process.wait()
                break
            sleep(POLL)
    finally:
        if source is not None:
            source.close()
    log(f"Play: the emulator ended (exit code {process.returncode}).")
    return process.returncode or 0
