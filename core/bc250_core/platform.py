# SPDX-License-Identifier: GPL-3.0-or-later
"""Desktop integration: XDG folders, opening files/URLs, and starting a command in a visible terminal window.

launch_in_terminal() is the bisect GUIs' terminal.py (identical in cu, cores and gpu-oc), plus an optional exit
file: the shell writes the command's exit status there when it ends, so a caller that cannot wait for the detached
terminal (the portal running an installer) can still tell when, and how, it finished."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path, PurePath

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

    Raises RuntimeError if no terminal emulator could be found."""
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
