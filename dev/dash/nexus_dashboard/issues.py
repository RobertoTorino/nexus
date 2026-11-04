# SPDX-License-Identifier: GPL-3.0-or-later
"""Close issues: the repository's open issues on GitHub (the weekly Upstream review and Backlog review, or one
someone opened), each with a tick box; Run closes the ticked ones with gh issue close, its output in the dashboard.
It moved here from Nexus Release Tool's Test on this board (owner, 04-11-2026: the release tool is the release)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import urllib.request
from dataclasses import dataclass

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, \
    QVBoxLayout, QWidget

from bc250_core.updates import UpdateChecker
from bc250_core.widgets import accent_button, hint_label

REPO = "RobertoTorino/nexus"            # as tools/nexus_index.py and the suites' pin_app.py name it
ISSUES_URL = f"https://api.github.com/repos/{REPO}/issues?state=open&per_page=100"
GH_FALLBACK = "/home/linuxbrew/.linuxbrew/bin/gh"   # Homebrew's gh on Bazzite: not on PATH when started from the menu


@dataclass(frozen=True)
class Issue:
    """One open issue on GitHub."""
    number: int
    title: str
    url: str
    updated: str                        # "2026-10-20", the day of its last change

    @property
    def label(self) -> str:
        return f"#{self.number} {self.title} (updated {self.updated})"


def parse_issues(data: object) -> list[Issue]:
    """The issues of GitHub's answer, without the pull requests it lists among them."""
    return [Issue(int(i.get("number") or 0), str(i.get("title") or ""), str(i.get("html_url") or ""),
                  str(i.get("updated_at") or "")[:10])
            for i in data if isinstance(i, dict) and "pull_request" not in i] if isinstance(data, list) else []


def gh_program() -> str:
    """The gh program: on PATH, else Homebrew's; "" without one."""
    return shutil.which("gh") or (GH_FALLBACK if os.access(GH_FALLBACK, os.X_OK) else "")


_token: str | None = None               # the token found once per run; "" when there is none
_token_lock = threading.Lock()


def github_token(run=subprocess.run) -> str:
    """GITHUB_TOKEN or GH_TOKEN, else the token of a gh login (gh auth token); "" without one. With a token GitHub
    allows 5,000 requests an hour instead of 60. It is only sent to GitHub's API and never stored here."""
    global _token
    with _token_lock:
        if _token is None:
            token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
            gh = gh_program()
            if not token and gh:
                try:
                    out = run([gh, "auth", "token"], capture_output=True, text=True, timeout=10)
                    token = out.stdout.strip() if out.returncode == 0 else ""
                except (OSError, subprocess.SubprocessError):
                    token = ""
            _token = token
        return _token


def fetch_open_issues() -> list[Issue]:
    """The repository's open issues, newest first. Raises OSError offline, urllib.error.HTTPError on GitHub's
    refusal (its hourly limit)."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "nexus-dashboard"}
    token = github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(ISSUES_URL, headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        return parse_issues(json.load(response))


def close_commands(numbers: list[int], comment: str = "", gh: str = "gh") -> list[list[str]]:
    """gh issue close for each of *numbers*, with *comment* on each when there is one; it needs a gh login."""
    note = ["--comment", comment.strip()] if comment.strip() else []
    return [[gh, "issue", "close", str(n), "--repo", REPO, *note] for n in numbers]


class IssuesDialog(QDialog):
    """The open issues on GitHub, read in the background, each with a tick box; Run closes the ticked ones."""

    def __init__(self, parent: QWidget, source=fetch_open_issues):
        super().__init__(parent)
        self.setWindowTitle("Close issues")
        self.resize(640, 420)
        self.state = QLabel("Reading the open issues on GitHub…")
        self.state.setWordWrap(True)
        self.list = QListWidget()
        self.list.itemChanged.connect(self._show_state)
        self.list.itemDoubleClicked.connect(
            lambda item: QDesktopServices.openUrl(QUrl(item.data(Qt.ItemDataRole.UserRole + 1))))
        self.comment = QLineEdit()
        self.comment.setPlaceholderText("Comment on each (optional), e.g. Decky pinned at v3.3.0")
        self.run_button = accent_button("Run", "Close the ticked issues with gh issue close; it needs a gh login "
                                               "(gh auth login)")
        self.run_button.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(self.run_button)
        lay = QVBoxLayout(self)
        lay.addWidget(hint_label(
            "Tick the issues that are handled and press <b>Run</b>: it closes them with <code>gh issue close</code>, "
            "with the comment when you write one. A double click opens an issue on GitHub. The weekly Upstream "
            "review and Backlog review open a new issue when they have something again."))
        lay.addWidget(self.state)
        lay.addWidget(self.list, 1)
        lay.addWidget(self.comment)
        lay.addLayout(buttons)
        self.run_button.setEnabled(False)
        self.checker = UpdateChecker(self)
        self.checker.finished.connect(self.fill)
        self.checker.start(lambda: self._fetch(source))

    @staticmethod
    def _fetch(source) -> object:
        """Worker thread: the issues, or the error to show."""
        try:
            return source()
        except (OSError, ValueError) as exc:
            return exc

    def fill(self, result: object) -> None:
        if isinstance(result, Exception):
            self.state.setText(f"Could not read the issues from GitHub: {result}")
            return
        self.list.blockSignals(True)
        for issue in result:
            item = QListWidgetItem(issue.label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, issue.number)
            item.setData(Qt.ItemDataRole.UserRole + 1, issue.url)
            item.setToolTip(issue.url)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self.state.setText(f"{len(result)} open issue{'' if len(result) == 1 else 's'} on GitHub." if result
                           else "No open issues on GitHub.")
        self._show_state()

    def numbers(self) -> list[int]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.CheckState.Checked]

    def _show_state(self) -> None:
        self.run_button.setEnabled(bool(self.numbers()))

    def done(self, code: int) -> None:
        self.checker.stop(2000)
        super().done(code)
