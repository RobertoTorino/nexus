# SPDX-License-Identifier: GPL-3.0-or-later
"""What is behind the Warnings, Failures and Info / hints boxes: the lines and hints of each test.

For every test the counters count (its latest result), the run log of that result is parsed with the
same parser as a live run, and the WARNING/ERROR/INFO lines and the hints of that test are shown.
Logs are read only when a box is clicked, once per file.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from . import window_title
from .catalog import TESTS
from .runner import ERROR, INFO, WARNING

MAX_LOG_BYTES = 4 * 1024 * 1024

KINDS = {
    # kind: (title, statuses whose tests are listed, line levels shown, include hints of every test)
    "warnings": ("Warnings", {WARNING}, {WARNING}, False),
    "failures": ("Failures", {ERROR}, {ERROR}, False),
    "info": ("Info / hints", {INFO}, {INFO}, True),
}
LEVEL_COLOR = {ERROR: "#e57373", WARNING: "#ffb74d", INFO: "#64b5f6", "hint": "#64b5f6", "note": "#9aa0a6"}
STATUS_WORD = {ERROR: "failure", WARNING: "warning", INFO: "info"}


@dataclass
class TestFindings:
    lines: list[tuple[str, str]] = field(default_factory=list)     # (level, text without timestamp/tag)
    hints: list[tuple[str, str]] = field(default_factory=list)     # (severity, text)


@dataclass
class Entry:
    test_id: str
    status: str
    hints: int
    when: str | None
    logs: list[Path]            # candidate files, first readable one wins


def parse_findings(lines: list[str]) -> dict[str, TestFindings]:
    """Per test: its tagged lines and hints, parsed exactly like a live run."""
    from .runner import _TAG, _TS_PREFIX, TestRunner     # same parsing rules as the live run

    parser = TestRunner("", use_sudo=False)
    found: dict[str, TestFindings] = {}

    def on_line(raw: str, level: str, tid: str | None) -> None:
        if tid and level in (ERROR, WARNING, INFO):
            body = _TS_PREFIX.sub("", raw)
            found.setdefault(tid, TestFindings()).lines.append((level, _TAG.sub("", body).strip()))

    parser.line.connect(on_line)
    parser.hint.connect(lambda tid, text, sev: found.setdefault(tid, TestFindings()).hints.append((sev, text)))
    for raw in lines:
        parser._handle_line(raw.rstrip("\r"))
    parser._close_current()
    parser.deleteLater()
    return found


def _read_lines(path: Path) -> list[str] | None:
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - MAX_LOG_BYTES))
            return fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None


def render(kind: str, entries: list[Entry]) -> tuple[str, int]:
    """(HTML, number of tests listed) for the dialog. All text from logs is escaped."""
    title, statuses, levels, all_hints = KINDS[kind]
    cache: dict[Path, dict[str, TestFindings] | None] = {}

    def findings_for(e: Entry) -> tuple[TestFindings | None, Path | None]:
        for path in e.logs:
            if path not in cache:
                lines = _read_lines(path)
                cache[path] = parse_findings(lines) if lines is not None else None
            if cache[path] is not None:
                return cache[path].get(e.test_id, TestFindings()), path
        return None, None

    shown = [e for e in entries if e.status in statuses or (all_hints and e.hints)]
    shown.sort(key=lambda e: (e.status not in statuses, e.test_id))
    if not shown:
        return f"<p>No {title.lower()} in the latest results.</p>", 0
    parts: list[str] = []
    for e in shown:
        test = TESTS.get(e.test_id)
        name = html.escape(test.name if test else "?")
        color = LEVEL_COLOR.get(e.status, "#9aa0a6")
        when = f" · {html.escape(e.when[:16])}" if e.when else ""
        parts.append(
            f"<h3 style='margin-bottom:2px;'><a href='test:{e.test_id}' style='color:{color}; text-decoration:none;'>"
            f"[{e.test_id}] {name}</a> <span style='font-size:small; font-weight:normal; color:#9aa0a6;'>"
            f"{STATUS_WORD.get(e.status, e.status)}{when}</span></h3>")
        f, path = findings_for(e)
        if f is None:
            parts.append("<p style='color:#9aa0a6;'>The log of this result is no longer available "
                         "(removed, or not readable). Run the test again to see the details.</p>")
            continue
        items = [(lvl, txt) for lvl, txt in f.lines if lvl in levels and e.status in statuses]
        hints = f.hints if (all_hints or e.status in statuses) else []
        rows = [f"<li><span style='color:{LEVEL_COLOR[lvl]}; font-weight:600;'>{lvl.upper()}</span> "
                f"{html.escape(txt)}</li>" for lvl, txt in items]
        rows += [f"<li><span style='color:{LEVEL_COLOR['hint']}; font-weight:600;'>💡 HINT</span> "
                 f"{html.escape(txt)}</li>" for _sev, txt in hints]
        if not rows:
            rows = ["<li style='color:#9aa0a6;'>No details in the log.</li>"]
        parts.append("<ul style='margin-top:0;'>" + "".join(rows) + "</ul>")
        parts.append(f"<p style='color:#9aa0a6; font-size:small; margin-top:-6px;'>From "
                     f"{html.escape(str(path))} · <a href='log:{e.test_id}:{quote(str(path))}' "
                     f"style='color:#ce93d8;'>Show in log</a></p>")
    return "".join(parts), len(shown)


class FindingsDialog(QDialog):
    """Lists the warnings, failures or info/hints behind a stat box; a test name opens its page."""

    open_test = pyqtSignal(str)
    open_log = pyqtSignal(str, str)     # log path, test id

    def __init__(self, kind: str, entries: list[Entry], parent: QWidget | None = None):
        super().__init__(parent)
        title = KINDS[kind][0]
        self.setWindowTitle(window_title(title))
        self.resize(820, 600)
        layout = QVBoxLayout(self)
        body, count = render(kind, entries)
        head = QLabel(f"<b>{title}</b> — {count} test(s), from the latest result of each test. "
                      "Click a test to open its page, or <i>Show in log</i> to read its part of the run log.")
        head.setWordWrap(True)
        layout.addWidget(head)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.setStyleSheet("QTextBrowser { background:#1e1f24; color:#e6e6e6; border-radius:6px; padding:6px; }")
        self.view.setHtml(body)
        self.view.anchorClicked.connect(self._link)
        layout.addWidget(self.view, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)

    def _link(self, url: QUrl) -> None:
        text = url.toString()
        if text.startswith("test:") and text[5:] in TESTS:
            self.open_test.emit(text[5:])
            self.accept()
        elif text.startswith("log:"):
            test_id, _, path = text[4:].partition(":")
            self.open_log.emit(unquote(path), test_id)

