# SPDX-License-Identifier: GPL-3.0-or-later
"""Close issues: the open issues on GitHub with a tick box each; Run closes the ticked ones with gh issue close, one
after the other, their output in the dashboard (moved from Nexus Release Tool's Test on this board, owner
04-11-2026)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import QDeadlineTimer, Qt
from PyQt6.QtWidgets import QApplication

from nexus_dashboard import issues, main_window
from nexus_dashboard.issues import Issue, IssuesDialog
from nexus_dashboard.main_window import MainWindow

ISSUES = [Issue(12, "Upstream review", "https://github.com/o/r/issues/12", "2026-10-20"),
          Issue(9, "Backlog review", "https://github.com/o/r/issues/9", "2026-10-19")]


def test_open_issues_without_pull_requests():
    """GitHub's issues list holds the pull requests too: Close issues shows the issues only."""
    data = [{"number": 12, "title": "Upstream review", "html_url": "https://github.com/o/r/issues/12",
             "updated_at": "2026-10-20T06:01:02Z"},
            {"number": 13, "title": "A pull request", "pull_request": {}, "html_url": "", "updated_at": ""},
            "not an issue"]
    assert issues.parse_issues(data) == [ISSUES[0]]
    assert issues.parse_issues(data)[0].label == "#12 Upstream review (updated 2026-10-20)"
    assert issues.parse_issues({"message": "Not Found"}) == []


def test_close_commands():
    assert issues.close_commands([12]) == [["gh", "issue", "close", "12", "--repo", issues.REPO]]
    assert issues.close_commands([12, 14], " Decky pinned at v3.3.0, it's in step ", gh="/bin/gh") == [
        ["/bin/gh", "issue", "close", "12", "--repo", issues.REPO, "--comment", "Decky pinned at v3.3.0, it's in step"],
        ["/bin/gh", "issue", "close", "14", "--repo", issues.REPO, "--comment", "Decky pinned at v3.3.0, it's in step"]]


def test_the_dialog_lists_the_open_ones_and_ticks(qapp):
    dialog = IssuesDialog(None, lambda: ISSUES)
    dialog.checker.stop(2000)
    dialog.fill(dialog._fetch(lambda: ISSUES))
    assert dialog.list.count() == 2 and dialog.list.item(0).text() == "#12 Upstream review (updated 2026-10-20)"
    assert dialog.state.text() == "2 open issues on GitHub." and not dialog.run_button.isEnabled()
    dialog.list.item(0).setCheckState(Qt.CheckState.Checked)
    assert dialog.numbers() == [12] and dialog.run_button.isEnabled()
    dialog.reject()

    failed = IssuesDialog(None, lambda: [])
    failed.checker.stop(2000)
    failed.fill(failed._fetch(lambda: (_ for _ in ()).throw(OSError("offline"))))
    assert "offline" in failed.state.text() and failed.list.count() == 0 and not failed.run_button.isEnabled()
    failed.fill([])
    assert failed.state.text() == "No open issues on GitHub."
    failed.reject()


def test_the_tile_opens_the_dialog_and_closes_the_ticked(qapp, monkeypatch):
    from PyQt6.QtWidgets import QDialog
    closed = []

    class Fake:
        def __init__(self, parent, source):
            assert source() == ISSUES
            self.comment = type("Line", (), {"text": lambda self: "done"})()

        def exec(self):
            return QDialog.DialogCode.Accepted

        def numbers(self):
            return [12]

    monkeypatch.setattr(main_window, "IssuesDialog", Fake)
    window = MainWindow(settings=None, suite="bc250-bazzite", issues_source=lambda: ISSUES)
    window.close_issues = lambda numbers, comment: closed.append((numbers, comment))
    tile = next(window.tiles.item(i).data(Qt.ItemDataRole.UserRole) for i in range(window.tiles.count())
                if window.tiles.item(i).text() == "Close issues")
    window.click(tile)
    assert closed == [([12], "done")]
    window.close()


def wait_for(window: MainWindow) -> None:
    deadline = QDeadlineTimer(10000)
    while window.closer is not None and not deadline.hasExpired():
        window.closer.waitForFinished(100)
        QApplication.processEvents()


@pytest.mark.skipif(sys.platform == "win32", reason="the stand-in for gh is a shell script")
def test_close_issues_runs_gh_for_each_in_turn(qapp, tmp_path, monkeypatch):
    gh = tmp_path / "gh"
    gh.write_text('#!/bin/sh\necho "closed $3"\n[ "$3" != 7 ]\n', encoding="utf-8")
    gh.chmod(0o755)
    monkeypatch.setattr(main_window, "gh_program", lambda: str(gh))
    window = MainWindow(settings=None, suite="bc250-bazzite")
    window.close_issues([12, 14], "")
    wait_for(window)
    out = window.output.toPlainText()
    assert f"$ gh issue close 12 --repo {issues.REPO}" in out and "closed 12" in out and "closed 14" in out
    window.output.clear()
    window.close_issues([7, 8], "")                     # gh fails on 7: 8 stays open
    wait_for(window)
    out = window.output.toPlainText()
    assert "closed 7" in out and "exit code 1" in out and "close 8" not in out
    window.close_issues([], "")
    assert window.closer is None
    window.close()


def test_close_issues_without_gh_closes_nothing(qapp, monkeypatch):
    monkeypatch.setattr(main_window, "gh_program", lambda: "")
    window = MainWindow(settings=None, suite="bc250-bazzite")
    window.close_issues([12], "")
    assert "not installed; nothing was closed" in window.output.toPlainText() and window.closer is None
    window.close()


def test_a_gh_that_does_not_start_is_said(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(main_window, "gh_program", lambda: str(Path(tmp_path / "missing-gh")))
    window = MainWindow(settings=None, suite="bc250-bazzite")
    window.close_issues([12, 14], "")
    for _ in range(50):
        QApplication.processEvents()
        if window.closer is None:
            break
    assert window.closer is None and "exit code -1" in window.output.toPlainText()
    assert "close 14" not in window.output.toPlainText()
    window.close()
