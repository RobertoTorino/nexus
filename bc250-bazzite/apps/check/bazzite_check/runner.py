# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs test-bazzite.sh through QProcess and turns its output into per-test events."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field

from PyQt6.QtCore import QObject, QProcess, pyqtSignal

from .bench import parse_bench_line

# Severity order; a test ends up with the worst level it logged.
SUCCESS, INFO, WARNING, ERROR = "success", "info", "warning", "error"
RUNNING, IDLE = "running", "idle"
_RANK = {INFO: 0, SUCCESS: 1, WARNING: 2, ERROR: 3}

_TS_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} - ")
_HEADER = re.compile(r"^\[TEST (\d{2})\]")
_TAG = re.compile(r"^(SUCCESS|INFO|WARNING|ERROR|FAILURE|HINT|NOTE):\s*")
_TAG_LEVEL = {"SUCCESS": SUCCESS, "INFO": INFO, "WARNING": WARNING,
              "ERROR": ERROR, "FAILURE": ERROR, "HINT": "hint", "NOTE": "note"}


def line_level(raw: str) -> str:
    """The color level of a stored log line, as in the live terminal: "header", a result level, "hint",
    "note" or ""."""
    body = _TS_PREFIX.sub("", raw)
    if _HEADER.match(body):
        return "header"
    m = _TAG.match(body)
    return _TAG_LEVEL[m.group(1)] if m else ""


_SUDO_AUTH_FAIL = ("incorrect password", "Sorry, try again", "no password was provided",
                   "a password is required")


@dataclass
class RunRequest:
    scope: str                      # "all", a category key or "test-NN"; used for log names
    test_ids: list[str] | None      # None = every test the script knows
    stress: bool = False
    stress_duration: int = 120
    stress_interval: int = 2
    bench: bool = False
    bench_seconds: int = 20
    save_baseline: bool = False
    disk: bool = False
    disk_write_gib: int = 0         # 0 = read-only
    speedtest: bool = False
    copy_desktop: bool = False      # let the script copy the report to ~/Desktop/bc250-bazzite-test
    extra_args: list[str] = field(default_factory=list)


class TestRunner(QObject):
    run_started = pyqtSignal(object)            # RunRequest
    line = pyqtSignal(str, str, object)         # text, level ("" for plain output), test id or None
    hint = pyqtSignal(str, str, str)            # test id, text, severity ("note" or the test's status so far)
    test_started = pyqtSignal(str)
    test_finished = pyqtSignal(str, str)        # test id, final status
    run_finished = pyqtSignal(int, bool)        # exit code, canceled
    auth_failed = pyqtSignal(str)
    bench_result = pyqtSignal(dict)             # key=value pairs of the script's "BENCH:" line

    def __init__(self, script: str, use_sudo: bool = True, parent: QObject | None = None):
        super().__init__(parent)
        self.script = os.path.realpath(script)     # the file that is checked is the file that runs
        self.use_sudo = use_sudo and os.geteuid() != 0
        self._proc: QProcess | None = None
        self._buf = ""
        self._current: str | None = None
        self._status: dict[str, str] = {}
        self._auth_error = False
        self._saw_test = False
        self._cancelled = False
        self._pending_hint: tuple[str, str, list[str]] | None = None   # test id, severity, lines
        self.request: RunRequest | None = None

    # ----------------------------------------------------------------- state
    @property
    def busy(self) -> bool:
        return self._proc is not None

    def sudo_ready(self) -> bool:
        """True when no password is needed (not using sudo, or credentials are cached)."""
        if not self.use_sudo:
            return True
        if not shutil.which("sudo"):
            return False
        return subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode == 0

    # --------------------------------------------------------------- control
    def start(self, req: RunRequest, password: str | None = None) -> None:
        if self.busy:
            raise RuntimeError("A run is already in progress")
        self.request = req
        self._buf, self._current, self._status = "", None, {}
        self._auth_error = self._saw_test = self._cancelled = False
        self._pending_hint = None

        args = [self.script, "--gui"]
        if not req.copy_desktop:
            args.append("--no-desktop")
        if req.test_ids:
            args.append("--only=" + ",".join(req.test_ids))
        if req.stress:
            args += [f"--stress={req.stress_duration}", f"--interval={req.stress_interval}"]
        if req.bench:
            args.append(f"--bench={req.bench_seconds}")
            if req.save_baseline:
                args.append("--save-baseline")
        if req.disk:
            args.append(f"--disk-write={req.disk_write_gib}" if req.disk_write_gib else "--disk-bench")
        if req.speedtest:
            args.append("--speedtest")
        args += req.extra_args

        if self.use_sudo:
            # -S reads the password from stdin, -p '' suppresses the prompt text.
            mode = ["-S", "-p", ""] if password is not None else ["-n"]
            program, argv = "sudo", [*mode, "--", "bash", *args]
        else:
            program, argv = "bash", args

        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.readyReadStandardOutput.connect(self._on_output)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)
        self._proc = proc
        self.run_started.emit(req)
        proc.start(program, argv)
        if password is not None:
            # Handed straight to sudo's stdin; never kept on this object or written anywhere.
            proc.write((password + "\n").encode())
        proc.closeWriteChannel()

    def cancel(self) -> None:
        """Ask the script to stop (SIGTERM, relayed by sudo): its traps end the stress load and remove temp files."""
        if self._proc is not None:
            self._cancelled = True
            self._proc.terminate()

    def kill(self) -> None:
        """Last resort when the script does not stop after cancel(); its own cleanup does not run."""
        if self._proc is not None:
            self._cancelled = True
            self._proc.kill()

    def shutdown(self, timeout_ms: int = 15000) -> None:
        """Stop a run synchronously, for when the app is quitting and the event loop is ending."""
        proc = self._proc
        if proc is None:
            return
        self.cancel()
        if not proc.waitForFinished(timeout_ms):
            proc.kill()
            proc.waitForFinished(3000)

    # --------------------------------------------------------------- parsing
    def _on_output(self) -> None:
        assert self._proc is not None
        self._buf += bytes(self._proc.readAllStandardOutput()).decode(errors="replace")
        *lines, self._buf = self._buf.split("\n")
        for raw in lines:
            self._handle_line(raw.rstrip("\r"))

    def _handle_line(self, raw: str) -> None:
        if self.use_sudo and not self._saw_test and any(s in raw for s in _SUDO_AUTH_FAIL):
            self._auth_error = True
            return

        body = _TS_PREFIX.sub("", raw)
        if m := _HEADER.match(body):
            self._close_current()
            self._current = m.group(1)
            self._saw_test = True
            self._status[self._current] = INFO
            self.test_started.emit(self._current)
            self.line.emit(raw, "header", self._current)
            return
        if body.startswith("[SUMMARY]") or body.startswith("All tests completed"):
            self._close_current()

        if (bench := parse_bench_line(body)) is not None:
            self.bench_result.emit(bench)

        level = ""
        if m := _TAG.match(body):
            level = _TAG_LEVEL[m.group(1)]
        if level in ("hint", "note") and self._current:
            self._add_hint_line(level, body[m.end():])
        else:
            self._flush_hint()
            if self._current and level in _RANK and _RANK[level] > _RANK[self._status[self._current]]:
                self._status[self._current] = level
        self.line.emit(raw, level, self._current)

    def _add_hint_line(self, kind: str, text: str) -> None:
        # The script wraps long hints over several HINT/NOTE lines; a line that does not end a
        # sentence continues on the next one, so those are joined into a single hint.
        severity = "note" if kind == "note" else self._status[self._current]
        pending = self._pending_hint
        if (pending and pending[0] == self._current and (pending[1] == "note") == (kind == "note")
                and not pending[2][-1].rstrip().endswith((".", "!", "?", ":"))):
            pending[2].append(text)
        else:
            self._flush_hint()
            self._pending_hint = (self._current, severity, [text])

    def _flush_hint(self) -> None:
        if self._pending_hint:
            test_id, severity, lines = self._pending_hint
            self._pending_hint = None
            self.hint.emit(test_id, " ".join(lines), severity)

    def _close_current(self) -> None:
        self._flush_hint()
        if self._current is not None:
            self.test_finished.emit(self._current, self._status[self._current])
            self._current = None

    def _on_error(self, err: QProcess.ProcessError) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self.line.emit(f"Failed to start: {self._proc.program() if self._proc else '?'}", ERROR, None)
            self._finish(-1)

    def _on_finished(self, code: int, _status: QProcess.ExitStatus) -> None:
        if self._buf:
            self._handle_line(self._buf)
            self._buf = ""
        if self._current is not None and self._cancelled:
            # A canceled test never reached a verdict.
            self._status[self._current] = IDLE
        self._close_current()
        self._finish(code)

    def _finish(self, code: int) -> None:
        if self._proc is None:
            return
        self._proc.deleteLater()
        self._proc = None
        if self._auth_error:
            self.auth_failed.emit("Incorrect password, or this user may not use sudo.")
        self.run_finished.emit(code, self._cancelled)


def parse_report(lines: list[str]):
    """Statuses, hint counts and RunInfo of a saved report, parsed exactly like a live run."""
    from .history import RunInfo

    parser = TestRunner("", use_sudo=False)
    statuses: dict[str, str] = {}
    hints: dict[str, int] = {}
    info = RunInfo()
    parser.test_finished.connect(lambda tid, status: statuses.__setitem__(tid, status))
    parser.hint.connect(lambda tid, _text, _sev: hints.__setitem__(tid, hints.get(tid, 0) + 1))
    for raw in lines:
        parser._handle_line(raw.rstrip("\r"))
        info.scan(raw)
    parser._close_current()
    parser.deleteLater()
    return {t: s for t, s in statuses.items() if s != IDLE}, hints, info
