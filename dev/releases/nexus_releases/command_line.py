# SPDX-License-Identifier: GPL-3.0-or-later
"""The command line under the steps: type a command, it runs with bash in the checkout and its output streams below.

Each command is its own `bash -lc`, started in the folder the last `cd` left; only that folder carries over, not
variables. Nothing can be typed into a running command (its input is closed), so a command that asks something gets
no answer and stops: git is told not to prompt, opens no editor (commit with -m) and pages nothing. Stop (or
Ctrl+C) interrupts the command and everything it started. The commands a step shows (Apply, Bump portal, Retract)
are offered under Commands, one per line, to put on the line, not to run straight away. The window's git buttons
run theirs here too (run_now)."""

from __future__ import annotations

import os
import re
import shutil
import signal
import tempfile
from pathlib import Path

from PyQt6.QtCore import QProcess, QProcessEnvironment, QSettings, Qt, QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QToolButton, QVBoxLayout, QWidget

from bc250_core.widgets import Terminal

HISTORY_KEY = "command_line/history"
HISTORY_MAX = 200
OUTPUT_MAX_LINES = 5000
STOP_GRACE_MS = 3000                    # after Stop: this long for a clean exit, then killed
BREW_BIN = Path("/home/linuxbrew/.linuxbrew/bin")      # Bazzite's brew, on PATH in a terminal but not always here
# What git would otherwise wait for: a password prompt, an editor, a pager. Their input is closed here.
NO_PROMPTS = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_EDITOR": "f() { echo 'No editor here: commit with -m \"message\".' >&2; exit 1; }; f",
    "GIT_PAGER": "cat",
    "PAGER": "cat",
    "TERM": "dumb",
}
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b[@-Z\\-_]")


def plain(text: str) -> str:
    """Output as plain text: color and cursor codes removed, a carriage return (a progress line) as a new line."""
    return _ANSI.sub("", text).replace("\r\n", "\n").replace("\r", "\n")


def without_comment(line: str) -> str:
    """*line* up to its shell comment: a # that starts a word, outside quotes."""
    quote = ""
    for i, char in enumerate(line):
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i].rstrip()
    return line.rstrip()


def command_lines(text: str) -> list[str]:
    """The commands in a block a step shows: its lines without comments or blank lines."""
    lines = [without_comment(line).strip() for line in text.splitlines()]
    return [line for line in lines if line]


def find_bash() -> str | None:
    return shutil.which("bash")


class CommandLine(QWidget):
    """The output, and below it the line to type in with Commands, Run/Stop and Clear."""

    def __init__(self, root: Path, settings: QSettings | None = None, bash: str | None = None, finished=None):
        """*settings* keeps the history between sessions (None: this session only); *finished* is called after each
        command, so the window can read the checkout again."""
        super().__init__()
        self.root = root
        self.cwd = root
        self.settings = settings
        self.bash = bash if bash is not None else find_bash()
        self.finished_callback = finished
        self.history: list[str] = []
        if settings is not None:
            stored = settings.value(HISTORY_KEY, [])
            self.history = [stored] if isinstance(stored, str) else list(stored or [])
        self.history_pos = len(self.history)
        self.draft = ""
        self.offered: list[str] = []
        self.cwd_file = Path(tempfile.gettempdir()) / f"nexus-releases-cwd-{os.getpid()}"
        self.running = ""
        self.grouped = False                    # the running command has its own process group
        self.pid = 0
        self.stopping = False
        self.last_code: int | None = None       # how the last command ended: its exit code, None when stopped

        self.output = Terminal()
        self.output.setMaximumBlockCount(OUTPUT_MAX_LINES)
        self.prompt = QLabel()
        self.prompt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.line = QLineEdit()
        self.line.setFont(self.output.font())
        self.line.setPlaceholderText("A command, run with bash in the checkout (Enter); ↑ ↓ for earlier ones")
        self.line.returnPressed.connect(self.submit)
        self.line.installEventFilter(self)
        self.commands_button = QToolButton()
        self.commands_button.setText("Commands")
        self.commands_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.commands_button.setMenu(QMenu(self.commands_button))
        self.commands_button.menu().aboutToShow.connect(self._fill_menu)
        self.run_button = QPushButton("Run")
        self.run_button.clicked.connect(self.run_or_stop)
        self.clear_button = QPushButton("Clear")
        self.clear_button.setToolTip("Empty the output")
        self.clear_button.clicked.connect(self.output.clear)

        row = QHBoxLayout()
        row.addWidget(self.prompt)
        row.addWidget(self.line, 1)
        row.addWidget(self.commands_button)
        row.addWidget(self.run_button)
        row.addWidget(self.clear_button)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.output, 1)
        lay.addLayout(row)

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._done)
        self.process.errorOccurred.connect(self._error)
        self.kill_timer = QTimer(self, singleShot=True, interval=STOP_GRACE_MS)
        self.kill_timer.timeout.connect(lambda: self._signal(signal.SIGKILL if hasattr(signal, "SIGKILL") else None))
        self.offer("")
        self._show_state()
        if not self.bash:
            self.line.setEnabled(False)
            self.run_button.setEnabled(False)
            self.output.setPlainText("No bash found: the command line needs it (on Windows, Git Bash's bash on PATH).")

    # --- what the steps offer ----------------------------------------------------------------------------------

    def offer(self, text: str) -> None:
        """The commands a step just showed: the Commands menu lists them, one per line."""
        self.offered = command_lines(text)
        self.commands_button.setEnabled(bool(self.offered))
        self.commands_button.setToolTip(
            "The commands the last step showed: pick one to put it on the line" if self.offered else
            "Apply, Bump portal and Retract show the commands to run next; they are offered here then")

    def _fill_menu(self) -> None:
        menu = self.commands_button.menu()
        menu.clear()
        for command in self.offered:
            menu.addAction(command, lambda c=command: self.put(c))

    def put(self, command: str) -> None:
        self.line.setText(command)
        self.line.setFocus()

    # --- running -----------------------------------------------------------------------------------------------

    def is_running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def run_or_stop(self) -> None:
        if self.is_running():
            self.stop()
        else:
            self.submit()

    def submit(self) -> None:
        command = self.line.text().strip()
        if not command or self.is_running() or not self.bash:
            return
        self._remember(command)
        self.line.clear()
        if command == "clear":
            self.output.clear()
            return
        self.run(command)

    def run_now(self, command: str) -> bool:
        """Run *command* as if typed (the git buttons); False while another runs or without bash."""
        if self.is_running() or not self.bash:
            return False
        self._remember(command)
        self.run(command)
        return True

    def run(self, command: str) -> None:
        self._append(f"{self._prompt_text()} {command}\n")
        self.running = command
        script = 'cd -- "$1" || exit; eval "$2"; rc=$?; printf %s "$PWD" > "$3"; exit $rc'
        args = ["-lc", script, "bash", str(self.cwd), command, str(self.cwd_file)]
        program = self.bash
        setsid = shutil.which("setsid")
        self.grouped = bool(setsid) and hasattr(os, "killpg")
        if self.grouped:                        # its own process group: Stop reaches everything it started
            program, args = setsid, [self.bash, *args]
        self.process.setProcessEnvironment(self._environment())
        self.process.setWorkingDirectory(str(self.cwd))
        self.stopping = False
        self.process.start(program, args)
        self.pid = self.process.processId()
        self.process.closeWriteChannel()
        self._show_state()

    def stop(self) -> None:
        """Interrupt the command as Ctrl+C in a terminal would; killed if it has not ended a moment later. What it
        started in the background (which ignores Ctrl+C in a script) ends with it."""
        if not self.is_running():
            return
        self.stopping = True
        self._signal(signal.SIGINT)
        self.kill_timer.start()

    def _signal(self, sig) -> None:
        """*sig* to the command's process group; without one (Windows), terminate or kill (*sig* None) bash."""
        try:
            if self.grouped:
                os.killpg(self.pid, sig)
                return
        except ProcessLookupError:
            return
        except OSError:
            pass
        if sig == signal.SIGINT:
            self.process.terminate()
        else:
            self.process.kill()

    def _interrupt(self) -> None:
        """Ctrl+C in the line: stop a running command, else drop what was typed, as a shell does."""
        if self.is_running():
            self.stop()
        else:
            self.line.clear()

    def _environment(self) -> QProcessEnvironment:
        env = QProcessEnvironment.systemEnvironment()
        for key, value in NO_PROMPTS.items():
            env.insert(key, value)
        path = env.value("PATH", "")
        if BREW_BIN.is_dir() and str(BREW_BIN) not in path.split(os.pathsep):
            env.insert("PATH", path + os.pathsep + str(BREW_BIN) if path else str(BREW_BIN))
        return env

    def _read(self) -> None:
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._append(plain(data))

    def _done(self, code: int, status: QProcess.ExitStatus) -> None:
        self.kill_timer.stop()
        self._read()
        if self.stopping:
            self._signal(signal.SIGTERM)            # what it left running in the background
            self.stopping = False
        try:
            folder = Path(self.cwd_file.read_text(encoding="utf-8"))
            if folder.is_dir():
                self.cwd = folder
        except OSError:
            pass
        self.last_code = None if status == QProcess.ExitStatus.CrashExit else code
        if status == QProcess.ExitStatus.CrashExit or code == 130:
            self._end_line("stopped")
        elif code != 0:
            self._end_line(f"exit code {code}")
        self.running = ""
        self._show_state()
        if self.finished_callback:
            self.finished_callback()

    def _error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._end_line(f"could not start bash ({self.process.errorString()})")
            self.running = ""
            self._show_state()

    # --- output, prompt, history -------------------------------------------------------------------------------

    def _append(self, text: str) -> None:
        bar = self.output.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 2
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        if at_end:
            bar.setValue(bar.maximum())

    def _end_line(self, note: str) -> None:
        text = self.output.toPlainText()
        self._append(("" if not text or text.endswith("\n") else "\n") + f"[{note}]\n")

    def _prompt_text(self) -> str:
        try:
            where = self.cwd.relative_to(self.root).as_posix()
            where = "" if where == "." else where
        except ValueError:
            where = str(self.cwd)
        return f"{self.root.name}{'/' + where if where else ''} $"

    def _show_state(self) -> None:
        self.prompt.setText(self._prompt_text())
        self.prompt.setToolTip(f"Commands run in {self.cwd}")
        running = self.is_running()
        self.run_button.setText("Stop" if running else "Run")
        self.run_button.setToolTip(f"Interrupt {self.running} (Ctrl+C)" if running else "Run the command (Enter)")

    def _remember(self, command: str) -> None:
        if command in self.history:
            self.history.remove(command)
        self.history = (self.history + [command])[-HISTORY_MAX:]
        self.history_pos = len(self.history)
        self.draft = ""
        if self.settings is not None:
            self.settings.setValue(HISTORY_KEY, self.history)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.line and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                self._browse(-1 if event.key() == Qt.Key.Key_Up else 1)
                return True
            if event.key() == Qt.Key.Key_C and event.modifiers() == Qt.KeyboardModifier.ControlModifier \
                    and not self.line.hasSelectedText():        # with a selection, Ctrl+C copies it
                self._interrupt()
                return True
        return super().eventFilter(obj, event)

    def _browse(self, step: int) -> None:
        if not self.history:
            return
        if self.history_pos == len(self.history):
            self.draft = self.line.text()
        self.history_pos = max(0, min(len(self.history), self.history_pos + step))
        self.line.setText(self.draft if self.history_pos == len(self.history) else self.history[self.history_pos])

    def shutdown(self) -> None:
        """The window closes: stop a running command and remove the folder note."""
        if self.is_running():
            self.stop()
            if not self.process.waitForFinished(STOP_GRACE_MS):
                self.process.kill()
                self.process.waitForFinished(1000)
        try:
            self.cwd_file.unlink()
        except OSError:
            pass
