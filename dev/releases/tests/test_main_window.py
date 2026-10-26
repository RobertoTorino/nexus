# SPDX-License-Identifier: GPL-3.0-or-later
"""The window on this checkout, offscreen, with no GitHub and no terminal."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication, QWidget


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    from nexus_releases.main_window import ReleaseWindow
    w = ReleaseWindow(runs_source=lambda etag: ([], ""), launch=lambda line: None, notify=lambda s, b: True,
                      status_source=None)
    w.build.checker.stop(2000)
    yield w, app
    w.build.stop()
    w.close()


def test_every_widget_keeps_qts_window_method(window):
    """An attribute named window on a widget hides QWidget.window(), which the suite's tooltip calls on the widget
    it is shown for: hovering the build indicator stopped the app that way."""
    w, _app = window
    for widget in [w, *w.findChildren(QWidget)]:
        assert callable(widget.window), type(widget).__name__


def test_tooltip_over_the_build_indicator(window):
    from bc250_core.widgets import RoundedToolTip
    w, app = window
    w.show()
    tip = RoundedToolTip(app)
    tip.show_text(QPoint(5, 5), w.build.toolTip(), w.build)
    assert tip.popup.isVisible() and tip.popup.parentWidget() is w
    tip.hide()


def test_the_header_is_a_row_of_pills(window):
    """Refresh, the working tree, GitHub's build, its API requests left and GitHub status: pills as in the apps'
    headers, all as wide as the widest (owner, 20-10-2026)."""
    from bc250_core.widgets import MetricBox, Pill
    w, _app = window
    pills = [w.refresh_pill, w.status, w.build, w.build.rate, w.github_status]
    assert all(isinstance(p, MetricBox) for p in pills)
    assert all(isinstance(p, Pill) for p in (w.refresh_pill, w.build, w.github_status))
    assert [p.caption.text() for p in pills] == \
        ["Click to refresh", "Working tree", "GitHub build", "GitHub API left", "GitHub status"]
    w.show()
    assert len({p.width() for p in pills if p.isVisible()}) == 1
    refreshed = []
    w.reload = lambda: refreshed.append(1)
    w.refresh_pill.click()
    assert refreshed == [1]
    w.status.set_value("A much longer value")                       # every pill grows with the widest
    assert len({p.minimumWidth() for p in pills}) == 1
    assert w.refresh_pill.minimumWidth() >= w.status.sizeHint().width()


def test_selection_is_a_teal_outline(window):
    """A selected cell and the focused input field: a rounded outline in Nexus's teal on a transparent background,
    not the desktop's solid highlight (rendered: the cell's middle keeps the table's own background)."""
    from PyQt6.QtGui import QColor
    from nexus_releases.style import NEXUS
    ACCENT = NEXUS.accent
    w, app = window
    w.show()
    table = w.apps_page.table
    table.setFocus()
    table.setCurrentCell(1, 1)
    app.processEvents()
    rect = table.visualRect(table.model().index(1, 1))
    image = table.viewport().grab().toImage()
    blank = rect.right() - 8                                        # right of "ace": background only
    inside = QColor(image.pixel(blank, rect.center().y()))
    other = QColor(image.pixel(blank, table.visualRect(table.model().index(0, 1)).center().y()))   # "core"
    edge = QColor(image.pixel(rect.center().x(), rect.top() + 1))
    assert inside.name() == other.name()                            # no solid highlight behind the text
    assert edge.name() == QColor(ACCENT).name()
    assert f"gridline-color:{NEXUS.edge};" in w.styleSheet()            # the tables' lines: the theme's thin edge
    assert f"QLineEdit:focus {{ background:transparent; border:2px solid {ACCENT}; border-radius:6px; }}" \
        in w.styleSheet()


def test_a_second_launch_opens_no_window(monkeypatch):
    """A double-click on the Desktop icon starts the app twice: the second launch hands over to the first."""
    from bc250_core import instance
    import nexus_releases.__main__ as entry
    import nexus_releases.main_window as main_window
    app = QApplication.instance() or QApplication([])
    asked = []
    monkeypatch.setattr(entry, "create_app", lambda *a, **k: app)
    monkeypatch.setattr(instance, "already_running", lambda app_id: asked.append(app_id) or True)
    monkeypatch.setattr(main_window, "ReleaseWindow", lambda *a, **k: pytest.fail("a second window was opened"))
    monkeypatch.setattr("sys.argv", ["nexus_releases"])
    assert entry.main() == 0 and asked == [entry.INFO.app_id]


def test_the_logs_are_tabs_of_their_own(window, monkeypatch):
    """Logs (the log of the step last open) and Commands (the command line) are tabs after the steps, each the whole
    tab area (owner, 17-10-2026: boxes under the steps were too flat to read). A step that writes its log opens
    Logs; opening a step makes Logs its log again. A finished command reads the checkout again (a commit, a push)."""
    w, _app = window
    pages = (w.apps_page, w.portal_page, w.withdraw_page, w.run_page)
    assert [w.tabs.tabText(i) for i in range(w.tabs.count())] == \
        ["1. Release apps", "2. Pin and release Portal", "3. Retract app", "Test on this board", "Logs", "Commands"]
    assert w.tabs.widget(w.log_tab) is w.outputs and w.tabs.widget(w.commands_tab) is w.commands
    assert [w.outputs.widget(i) for i in range(w.outputs.count())] == [p.output for p in pages]
    assert not any(p.isAncestorOf(p.output) for p in pages)             # no longer inside the step's tab
    assert w.tabs.widget(w.log_tab).parent() is not None and w.centralWidget().isAncestorOf(w.tabs)
    for index, page in enumerate(pages):
        w.tabs.setCurrentIndex(index)
        assert w.outputs.currentWidget() is page.output
    w.tabs.setCurrentIndex(w.log_tab)
    assert w.outputs.currentWidget() is w.run_page.output               # a log tab leaves it as it is
    w.tabs.setCurrentIndex(1)
    w.portal_page.output.set_text("Tags fetched.")                      # the open step wrote: Logs opens
    assert w.tabs.currentIndex() == w.log_tab and w.outputs.currentWidget() is w.portal_page.output
    w.tabs.setCurrentIndex(0)
    w.portal_page.output.set_text("later")                              # another step's log: no switch
    assert w.tabs.currentIndex() == 0
    w.run_page.output.appendPlainText("alpha started")                  # Test on this board never switches
    w.tabs.setCurrentIndex(3)
    w.run_page.output.appendPlainText("alpha closed.")
    assert w.tabs.currentIndex() == 3
    w.tabs.setCurrentIndex(0)
    assert w.commands.root == w.root
    refreshed = []
    monkeypatch.setattr(w, "refresh", lambda: refreshed.append(1))
    w.commands.finished_callback = w.refresh
    w.commands._done(0, w.commands.process.exitStatus())
    assert refreshed == [1]


def test_a_step_offers_its_commands(window):
    from nexus_releases import plan as rp
    w, _app = window
    w.commands.offer(rp.app_commands(["alpha-v0.1.1"]))
    assert w.commands.offered[-1] == f"{rp.TAG_SCRIPT} alpha-v0.1.1" and w.commands.commands_button.isEnabled()


SUMMARY_DOWN = {   # githubstatus.com's summary.json during the incident of 19-10-2026, shortened
    "status": {"indicator": "minor", "description": "Partially Degraded Service"},
    "components": [{"name": "Git Operations", "status": "operational"},
                   {"name": "Actions", "status": "degraded_performance"},
                   {"name": "Pages", "status": "major_outage"}],
    "incidents": [{"name": "Degraded availability for GitHub Actions, GitHub Pages and Webhooks"}],
}
SUMMARY_UP = {"status": {"indicator": "none", "description": "All Systems Operational"},
              "components": [{"name": "Actions", "status": "operational"}], "incidents": []}


def test_github_status_is_read_from_the_status_page(monkeypatch):
    import io
    import json
    from nexus_releases import plan as rp
    down = rp.parse_github_status(SUMMARY_DOWN)
    assert not down.up and down.description == "Partially Degraded Service"
    assert down.affected == ("Actions: degraded performance", "Pages: major outage")
    assert down.incidents == ("Degraded availability for GitHub Actions, GitHub Pages and Webhooks",)
    assert rp.parse_github_status(SUMMARY_UP).up
    assert not rp.parse_github_status("not json").up                 # an odd answer is never "up"
    asked = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout):
        asked.append(request.full_url)
        return Response(json.dumps(SUMMARY_UP).encode())

    monkeypatch.setattr(rp.urllib.request, "urlopen", urlopen)
    assert rp.fetch_github_status().up and asked == ["https://www.githubstatus.com/api/v2/summary.json"]


def test_github_status_is_a_pill_that_opens_the_status_page(window, monkeypatch):
    """Green while GitHub is up, red while githubstatus.com reports a problem, gray while not known; a click opens
    https://www.githubstatus.com/ (owner, 19-10-2026). A pill, as the apps' status boxes (owner, 20-10-2026)."""
    from PyQt6.QtGui import QColor, QDesktopServices
    from bc250_core.theme import GREEN, GREY, RED
    from nexus_releases import main_window
    from nexus_releases import plan as rp
    w, _app = window
    status = main_window.GitHubStatusIndicator(lambda: rp.parse_github_status(SUMMARY_DOWN))
    assert not status.isHidden() and status.caption.text() == "GitHub status" and status.state == ""

    def color() -> str:
        return next((c for c in (RED, GREEN) if c in status.styleSheet()), GREY)

    assert color() == GREY and status.value.text() == "Unknown"
    status.checked(status._fetch())
    assert status.state == "down" and color() == RED and status.value.text() == "Problem"
    assert "Actions: degraded performance" in status.toolTip() and "Partially Degraded Service" in status.toolTip()
    assert status.timer.interval() == main_window.BUILD_IDLE_MS
    status.checked(rp.parse_github_status(SUMMARY_UP))
    assert status.state == "up" and color() == GREEN and status.value.text() == "Up"
    status.checked(OSError("offline"))
    assert status.state == "" and color() == GREY and "offline" in status.toolTip()
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    status.click()
    assert opened == ["https://www.githubstatus.com/"]
    status.stop()
    assert w.github_status.isHidden() and main_window.GitHubStatusIndicator(None).isHidden()


def _answer(at: str, msg: str, req: str, model: str = "claude-opus-5-5", **usage) -> str:
    import json
    return json.dumps({"type": "assistant", "timestamp": at, "requestId": req,
                       "message": {"id": msg, "model": model, "usage": usage}})


def test_claude_usage_counts_each_answer_once(tmp_path):
    """Today's tokens and the last 5 hours' from Claude Code's transcripts, subagents' included; an answer of
    several parts counts once, Claude Code's own notes (<synthetic>) and other lines not at all."""
    import datetime
    import os
    from nexus_releases import plan as rp
    now = datetime.datetime(2026, 10, 21, 12, 0).timestamp()

    def at(hours_ago: float) -> str:
        moment = datetime.datetime.fromtimestamp(now - hours_ago * 3600, datetime.timezone.utc)
        return moment.isoformat().replace("+00:00", "Z")

    assert rp.fetch_claude_usage(now, tmp_path) is None                       # no Claude Code here
    session = tmp_path / "projects" / "-home-x-repo"
    (session / "s1" / "subagents").mkdir(parents=True)
    (session / "s1.jsonl").write_text("\n".join([
        _answer(at(1), "m1", "r1", input_tokens=10, output_tokens=100, cache_read_input_tokens=1000),
        _answer(at(1), "m1", "r1", input_tokens=10, output_tokens=100, cache_read_input_tokens=1000),   # part 2
        _answer(at(8), "m2", "r2", input_tokens=1, output_tokens=2, cache_creation_input_tokens=3),     # today
        _answer(at(1), "m3", "r3", model="<synthetic>", output_tokens=50),
        '{"type": "user", "message": {"content": "usage"}}', "not json"]))
    (session / "s1" / "subagents" / "a.jsonl").write_text(
        _answer(at(2), "m4", "r4", model="claude-haiku-5-5", input_tokens=5, output_tokens=5))
    (session / "old.jsonl").write_text(_answer(at(30), "m5", "r5", output_tokens=999))
    for path in session.rglob("*.jsonl"):                                    # written as of *now*; old.jsonl before
        os.utime(path, (now - 30 * 3600,) * 2 if path.name == "old.jsonl" else (now,) * 2)
    today, recent = rp.fetch_claude_usage(now, tmp_path)
    assert (today.messages, today.input, today.output, today.cache_write, today.cache_read) == (3, 16, 107, 3, 1000)
    assert today.total == 1126 and today.models == (("claude-opus-5-5", 1116), ("claude-haiku-5-5", 10))
    assert recent.messages == 2 and recent.total == 1120
    assert [rp.short_count(n) for n in (999, 1126, 4_567_890)] == ["999", "1.1k", "4.6M"]


def test_claude_usage_is_a_pill_that_opens_the_usage_page(window, monkeypatch):
    """Claude tokens today (the blue edge every neutral pill has, owner 26-10-2026), hidden without Claude Code; a
    click opens Claude's usage page."""
    from PyQt6.QtGui import QDesktopServices
    from bc250_core.theme import BLUE
    from nexus_releases import main_window
    from nexus_releases import plan as rp
    w, _app = window
    w.claude.checked(w.claude._fetch())
    assert w.claude.isHidden()                                                # conftest: no Claude Code
    today = rp.ClaudeUsage(0, 3, 16, 107, 3, 1_234_567, (("claude-opus-5-5", 1_234_693),))
    pill = main_window.ClaudeUsageIndicator(lambda: (today, rp.ClaudeUsage(0, 1, output=5)))
    assert not pill.isHidden() and pill.caption.text() == "Claude tokens today" and pill.value.text() == "—"
    pill.checked(pill._fetch())
    assert pill.value.text() == "1.2M" and BLUE in pill.styleSheet() and pill.timer.interval() == main_window.BUILD_IDLE_MS
    assert "Today: 1,234,693 tokens in 3 answers" in pill.toolTip() and "Last 5 hours: 5 tokens" in pill.toolTip()
    assert "claude-opus-5-5: 1,234,693" in pill.toolTip()
    pill.checked(OSError("denied"))
    assert BLUE in pill.styleSheet() and "denied" in pill.toolTip()
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    pill.click()
    assert opened == ["https://claude.ai/settings/usage"]
    pill.checked(None)
    assert pill.isHidden()
    pill.stop()
    assert main_window.ClaudeUsageIndicator(None).isHidden()


def test_close_issues_lists_the_open_ones_and_closes_the_ticked(window):
    """Close issues (Test on this board): the open issues with a tick box each; Run closes the ticked ones with gh
    issue close in the Commands tab."""
    from PyQt6.QtCore import Qt
    from nexus_releases import main_window
    from nexus_releases import plan as rp
    w, _app = window
    issues = [rp.Issue(12, "Upstream review", "https://github.com/o/r/issues/12", "2026-10-20"),
              rp.Issue(9, "Backlog review", "https://github.com/o/r/issues/9", "2026-10-19")]
    dialog = main_window.IssuesDialog(w, lambda: issues)
    dialog.checker.stop(2000)
    dialog.fill(dialog._fetch(lambda: issues))
    assert dialog.list.count() == 2 and dialog.list.item(0).text() == "#12 Upstream review (updated 2026-10-20)"
    assert dialog.state.text() == "2 open issues on GitHub." and not dialog.run_button.isEnabled()
    dialog.list.item(0).setCheckState(Qt.CheckState.Checked)
    assert dialog.numbers() == [12] and dialog.run_button.isEnabled()
    dialog.reject()

    failed = main_window.IssuesDialog(w, lambda: [])
    failed.checker.stop(2000)
    failed.fill(failed._fetch(lambda: (_ for _ in ()).throw(OSError("offline"))))
    assert "offline" in failed.state.text() and failed.list.count() == 0 and not failed.run_button.isEnabled()
    failed.fill([])
    assert failed.state.text() == "No open issues on GitHub."
    failed.reject()

    ran = []
    w.commands.run_now = lambda command: ran.append(command) or True
    w.run_page.run_close([12], "Decky pinned at v3.3.0")
    assert ran == [rp.close_issues_command([12], "Decky pinned at v3.3.0")]
    assert w.tabs.currentIndex() == w.commands_tab
    w.run_page.run_close([], "")
    assert len(ran) == 1
    w.commands.run_now = lambda command: False
    w.run_page.run_close([9], "")
    assert "nothing was closed" in w.run_page.output.toPlainText()


def test_the_window_has_nexus_design(window):
    """A Nexus app, not a suite's (owner, 26-10-2026): create_app() puts Nexus's theme on the application (ink,
    silver, teal: nexus/docs/stylesheets/nexus.css), the widgets draw with it, and the icon is the Nexus drawing."""
    from PyQt6.QtGui import QPalette
    from bc250_core import widgets
    from bc250_core.app import create_app
    from nexus_releases import INFO, LOGO_PATH
    from nexus_releases.style import EDGE, INK, MAIN, NEXUS, SILVER, TEAL
    w, _app = window
    app = create_app(INFO, [], theme=NEXUS)
    palette = app.palette()
    assert palette.color(QPalette.ColorRole.Window).name() == INK
    assert palette.color(QPalette.ColorRole.Base).name() == MAIN
    assert palette.color(QPalette.ColorRole.WindowText).name() == SILVER
    assert palette.color(QPalette.ColorRole.Highlight).name() == TEAL
    assert palette.color(QPalette.ColorRole.HighlightedText).name() == INK
    assert widgets.current_theme() is NEXUS and widgets.accent() == TEAL
    assert f"stop:0 {MAIN}, stop:1 {INK}" in w.status.styleSheet() and f"color:{SILVER}" in w.status.styleSheet()
    assert f"border:1px solid {EDGE}" in w.refresh_pill.styleSheet()
    assert f"border-color:{TEAL}" in w.refresh_pill.styleSheet()
    assert f"border:2px solid {TEAL}" in w.apps_page.apply_button.styleSheet()
    assert LOGO_PATH.name == "nexus-releases.webp" and app.windowIcon().availableSizes()
    assert "#6a1b9a" not in w.styleSheet() and "#7e97ad" not in w.styleSheet()        # nothing of the Bazzite suite


def test_the_icons_are_the_nexus_drawing():
    """The app's icon, its menu icon and its tile on the BC250 suite's portal are the Nexus drawing at 512, 128 and
    256 px (tools/make_icons.py writes them, lossless, so the pixels are the drawing's)."""
    Image = pytest.importorskip("PIL.Image")
    from nexus_releases import ROOT
    nexus = ROOT.parents[1] / "nexus" / "images"
    tile = ROOT.parents[1] / "bc250-bazzite" / "portal" / "images" / "apps" / "releases.webp"
    for copy, size in ((ROOT / "images" / "nexus-releases.webp", 512), (ROOT / "images" / "nexus-releases-128.png", 128),
                       (tile, 256)):
        with Image.open(copy) as got, Image.open(nexus / f"nexus-{size}.png") as want:
            assert got.size == (size, size) == want.size, copy.name
            assert got.convert("RGBA").tobytes() == want.convert("RGBA").tobytes(), copy.name


def test_the_portal_version_field_shows_a_whole_version(window):
    """The field on step 2 is wide enough for a version like 10.1.0 (owner, 26-10-2026: it cut the text off)."""
    from nexus_releases.main_window import VERSION_FIELD_PX
    w, _app = window
    w.show()
    field = w.portal_page.portal_version
    assert field.minimumWidth() == VERSION_FIELD_PX >= 120
    assert field.width() >= VERSION_FIELD_PX
    assert field.fontMetrics().horizontalAdvance("10.1.0") + 40 < field.width()     # the text and the arrow fit
