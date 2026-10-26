# SPDX-License-Identifier: GPL-3.0-or-later

"""Starts a command in a visible terminal window, detached from this process.

bc250-gpu-oc-bisect.sh needs a real TTY: it asks interactive questions (resume after a crash?
install the result?), and its output is exactly what a user running it by hand would want to see
on screen. So the launcher GUI doesn't run the script itself - it hands the fully-assembled
command line to a terminal emulator and gets out of the way, same as the sibling projects' GUIs.
"""

from __future__ import annotations

import os
import shutil
import subprocess

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


def find_terminal() -> str | None:
    """Best-guess terminal emulator for this session, or None if none could be found."""
    env_term = os.environ.get("TERMINAL")
    if env_term and shutil.which(env_term):
        return env_term
    for name, _ in _TERMINALS:
        if shutil.which(name):
            return name
    return None


def launch_in_terminal(shell_command: str, *, keep_open: bool = True) -> None:
    """Runs ``shell_command`` (a single already-quoted shell command line) in a new terminal
    window, detached from this process so closing the launcher GUI doesn't touch it.

    Raises RuntimeError if no terminal emulator could be found.
    """
    if keep_open:
        # So the window stays open after the script exits (success, error or Ctrl+C), letting the
        # user read the final summary/report path instead of the window vanishing instantly.
        shell_command = f"{shell_command}; echo; read -rp 'Press Enter to close... ' _"

    term = find_terminal()
    if term is None:
        raise RuntimeError(
            "No terminal emulator found (tried konsole, gnome-terminal, ptyxis, xfce4-terminal, "
            "foot, alacritty, kitty, x-terminal-emulator, xterm, and $TERMINAL)."
        )

    builder = dict(_TERMINALS).get(term)
    argv = builder(shell_command) if builder else [term, "-e", "bash", "-lc", shell_command]

    # start_new_session detaches it from this process group so it outlives the GUI.
    subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
