# SPDX-License-Identifier: GPL-3.0-or-later
"""The Nexus release tab (owner, 30-10-2026): the whole release as numbered steps in their order, from your own
changes to the portal published (owner: "if I open NRT I want to see exactly what has to be done in their logical
sequence"): Get up to date, Commit your changes, Push them, CI passes, Start new release (with what the release holds
above it), the release on GitHub (Stop or Resume), Device test, Publish (or Not OK) and Bring in the pin commit. Each
step says where it stands; only the step to do now has its pill lit (owner: "if that means I have to do 3 actions we
make pills for them that can be clicked"). The logic is flow.py's (current_step, step_states); the window
(main_window.py) holds the command line the commands run in and the GitHub runs the header reads."""

from __future__ import annotations

import shlex
import sys
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                             QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from bc250_core.theme import GREEN, GREY, ORANGE, RED
from bc250_core.widgets import Terminal, accent_button, hint_label

from . import flow
from . import plan as rp

if TYPE_CHECKING:
    from .main_window import ReleaseWindow

COLUMNS = ("Release", "Now", "New version", "Why", "Notes")
SEMVER_TIP = ("Breaking. (an entry that starts with it) -> major, Added. -> minor, Fixed. -> patch. auto: worked out "
              "when Start writes the release.")
MARKS = {"done": ("✓", GREEN), "now": ("▶", ORANGE), "failed": ("!", RED), "later": ("", GREY)}
REJECTED_KEY = "release/rejected"     # "<run url>|<portal tag>" of each Not OK, the newest 20


class ReleasePage(QWidget):
    """The Nexus release: what it holds, and its steps in order, each with its pills."""

    def __init__(self, window: "ReleaseWindow"):
        super().__init__()
        self.release_window = window
        self.rejected_here: dict[str, list[str]] = {}     # Not OK without settings: by run url
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        self.pull_button = QPushButton("git pull")
        self.pull_button.clicked.connect(self.pull)
        self.commit_message = QLineEdit()
        self.commit_message.setPlaceholderText("What these changes do (the commit message)")
        self.commit_message.setMinimumWidth(420)
        self.commit_message.textChanged.connect(self.show_state)
        self.commit_button = accent_button("Commit", "Stage every change and new file and commit them, after the "
                                           "version and manifest checks")
        self.commit_button.clicked.connect(self.commit)
        self.push_button = accent_button("Push", "Push your commits to GitHub; the pre-push hook checks them first")
        self.push_button.clicked.connect(self.release_window.push)
        self.rerun_ci_button = accent_button("Run CI again", "Start CI's failed jobs on this commit again: for a "
                                             "failure of GitHub's own; when the code is wrong, fix it and commit")
        self.rerun_ci_button.clicked.connect(self.rerun_ci)
        self.start_button = accent_button("Start new release", "Write the release, commit it, push it and start the "
                                          "release on GitHub")
        self.start_button.clicked.connect(self.start)
        self.why_not = QLabel()                 # why Start cannot go yet
        self.why_not.setWordWrap(True)
        self.why_not.setStyleSheet(f"color:{ORANGE}; font-weight:600;")
        self.state = QLabel()                   # where the release on GitHub stands
        self.state.setWordWrap(True)
        self.state.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.state.setOpenExternalLinks(True)
        self.stop_button = QPushButton("Stop run")
        self.stop_button.setToolTip("Stop the release on GitHub (gh run cancel). Safe until a portal is published: "
                                    "the portals see only portal tags")
        self.stop_button.clicked.connect(self.stop_run)
        self.resume_button = accent_button("Resume run", "Start the jobs that failed or were stopped again (gh run "
                                           "rerun --failed): what is out already is skipped, the draft made anew")
        self.resume_button.clicked.connect(self.resume_run)
        self.portal_choice = QComboBox()        # the suites' portal tags waiting for their device test
        self.test_button = accent_button("Device test", "Install the draft portal on this device from GitHub and "
                                         "start it (check-release draft): test it as a user would")
        self.test_button.clicked.connect(self.device_test)
        self.publish_button = accent_button("Publish", "The device test passed: publish the draft, which makes the "
                                            "portal tag; the portals offer it from then on")
        self.publish_button.clicked.connect(self.publish)
        self.reject_button = QPushButton("Not OK")
        self.reject_button.setToolTip("The device test failed: the draft stays unpublished")
        self.reject_button.clicked.connect(self.reject)
        self.finish_button = accent_button("git pull", "Bring in the release's Pin ... commit")
        self.finish_button.clicked.connect(self.pull)
        self.output = Terminal()                # the window shows it in Logs
        self.picks: list[flow.Pick] = []
        self.rows: list[tuple[flow.Pick, QComboBox, QLineEdit]] = []
        self.facts = flow.Facts()

        pills = {"pull": [self.pull_button], "commit": [self.commit_message, self.commit_button],
                 "push": [self.push_button], "ci": [self.rerun_ci_button], "start": [self.start_button],
                 "run": [self.stop_button, self.resume_button], "test": [self.portal_choice, self.test_button],
                 "publish": [self.publish_button, self.reject_button], "finish": [self.finish_button]}
        steps = QGridLayout()
        steps.setColumnStretch(2, 1)
        self.marks: dict[str, QLabel] = {}
        self.titles: dict[str, QLabel] = {}
        self.details: dict[str, QLabel] = {}
        for row, (key, title, what) in enumerate(flow.STEPS):
            mark = QLabel()
            mark.setFixedWidth(22)
            name = QLabel(f"{row + 1}. {title}")
            detail = QLabel(what)
            detail.setWordWrap(True)
            detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            detail.setOpenExternalLinks(True)
            box = QHBoxLayout()
            box.setContentsMargins(0, 0, 0, 0)
            for widget in pills[key]:
                box.addWidget(widget, 1 if isinstance(widget, QLineEdit) else 0)
            steps.addWidget(mark, row, 0)
            steps.addWidget(name, row, 1)
            steps.addWidget(detail, row, 2)
            steps.addLayout(box, row, 3)
            self.marks[key], self.titles[key], self.details[key] = mark, name, detail
        lay = QVBoxLayout(self)
        lay.addWidget(hint_label(
            "One release for every suite on it: the apps that changed, their portal, core and Nexus's version. Do the "
            "steps below in their order: the one to do now has its pill lit and an orange ▶, done ones a green "
            "✓. The versions in the table are offered by the CHANGELOG entries; type another to override "
            "(<b>auto</b> is worked out at Start)."))
        lay.addWidget(self.table, 1)
        lay.addWidget(self.why_not)
        lay.addLayout(steps)
        lay.addWidget(self.state)

    # --- what the release holds -----------------------------------------------------------------------------------

    def fill(self) -> None:
        """The rows of the release as the checkout is now; what was typed in a row that is still there stays."""
        typed = {pick.label: (combo.currentText(), notes.text()) for pick, combo, notes in self.rows}
        root = self.release_window.root
        self.picks = flow.picks(root) if flow.release_suites(root) else []
        self.table.setRowCount(len(self.picks))
        self.rows = []
        for i, pick in enumerate(self.picks):
            for col, text in ((0, pick.label), (1, pick.unit.version), (3, pick.why)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setToolTip(pick.why)
                if col == 0 and pick.unit.kind == "app":
                    item.setForeground(QColor(ORANGE))
                self.table.setItem(i, col, item)
            combo = QComboBox()
            combo.setEditable(True)
            combo.addItems(pick.choices)
            combo.setToolTip(f"{pick.choices[0]}: {pick.why}.\n\n{SEMVER_TIP}")
            notes = QLineEdit()
            notes.setPlaceholderText("What this release brings (optional)")
            if pick.label in typed:
                combo.setEditText(typed[pick.label][0])
                notes.setText(typed[pick.label][1])
            self.table.setCellWidget(i, 2, combo)
            self.table.setCellWidget(i, 4, notes)
            self.rows.append((pick, combo, notes))
        self.portal_choice.clear()
        self.portal_choice.addItems(flow.waiting_portals(root))
        self.show_state()

    def chosen(self) -> list[flow.Pick]:
        for pick, combo, notes in self.rows:
            pick.version, pick.notes = combo.currentText().strip(), notes.text()
        return [pick for pick, _combo, _notes in self.rows]

    # --- the steps ------------------------------------------------------------------------------------------------

    def read_facts(self) -> flow.Facts:
        """What the steps stand on, from git and the runs the header fetched (it costs no request)."""
        window = self.release_window
        root, base = window.root, window.base()
        runs = window.build.runs
        head = (rp.git(root, "rev-parse", "HEAD") or "").strip()
        run = flow.cycle_run(root, runs)
        unstaged, staged, ahead = rp.git_state(root, base)
        return flow.Facts(
            behind=rp.behind(root, base), dirty=unstaged or staged, ahead=ahead,
            ci=flow.ci_state(runs, head) if window.build.source is not None else "unknown",
            unpushed=flow.unpushed_release(root, base), something=bool(self.picks), run=run,
            drafts=[t for t in flow.waiting_portals(root) if not flow.published(root, runs, t)] if run else [],
            restart=run is not None and run.sha != head, rejected=self.rejected(run))

    def rejected(self, run: rp.BuildRun | None) -> list[str]:
        """The drafts of *run* the owner said Not OK to, kept in NRT's settings by the run (a run made again makes its
        draft anew, untested); without settings, for this session."""
        if run is None:
            return []
        settings = self.release_window.settings
        if settings is None:
            return list(self.rejected_here.get(run.url, []))
        marks = str(settings.value(REJECTED_KEY, "") or "").split()
        return [mark.split("|", 1)[1] for mark in marks if mark.startswith(f"{run.url}|")]

    def show_state(self) -> None:
        """Each step's mark and line, and only the pills of the step to do now lit (none while a command runs)."""
        window = self.release_window
        idle = not window.commands.is_running() and bool(window.commands.bash)
        facts = self.facts = self.read_facts()
        states = flow.step_states(facts)
        now = flow.current_step(facts)
        for key, _title, what in flow.STEPS:
            sign, color = MARKS[states[key]]
            self.marks[key].setText(sign)
            self.marks[key].setStyleSheet(f"color:{color}; font-weight:800;")
            lit = states[key] in ("now", "failed")
            self.titles[key].setStyleSheet(f"font-weight:800; color:{color};" if lit else
                                           "font-weight:600;" if states[key] == "done" else f"color:{GREY};")
            self.details[key].setText(self.detail(key, states[key], facts) or what)
        reasons = flow.ready(window.root, window.base()) if self.picks and not facts.unpushed else []
        self.why_not.setText("Nothing to release: no app of a suite on the Nexus release changed since its last "
                             "release." if not self.picks and not now else "")
        self.why_not.setVisible(bool(self.why_not.text()))
        self.pull_button.setEnabled(idle and now == "pull")
        self.commit_button.setEnabled(idle and now == "commit" and bool(self.commit_message.text().strip()))
        self.commit_message.setEnabled(now == "commit")
        self.push_button.setEnabled(idle and now == "push")
        self.rerun_ci_button.setEnabled(idle and now == "ci" and facts.ci == "failed")
        self.start_button.setText("Push and start" if facts.unpushed else "Start new release")
        self.start_button.setEnabled(idle and now == "start" and (bool(facts.unpushed) or not reasons))
        run = facts.run
        self.stop_button.setEnabled(idle and now == "run" and run is not None and not run.done)
        self.resume_button.setEnabled(idle and now == "run" and run is not None and run.done and not run.passed)
        self.resume_button.setText("Start again on this commit" if facts.restart else "Resume run")
        here = bool(facts.drafts) and rp.tests_here(window.root, self.waiting_suite())
        self.portal_choice.setVisible(self.portal_choice.count() > 1)
        self.test_button.setEnabled(idle and now == "test" and here)
        self.test_button.setToolTip("Install the draft portal on this device and start it" if here or not facts.drafts
                                    else "The device test runs on the suite's own system: " +
                                    ("Linux (the board)" if sys.platform == "win32" else "Windows (the handheld)"))
        self.publish_button.setEnabled(idle and now == "test")
        self.reject_button.setEnabled(now == "test")
        self.finish_button.setEnabled(idle and now == "finish")
        last = flow.release_run(window.build.runs)
        self.state.setText(f'Last {flow.WORKFLOW_NAME}: {last.outcome} on {last.sha[:7]}. <a href="{last.url}">Open '
                           "the run</a>" if last is not None else "")
        self.state.setStyleSheet(f"color:{GREY};")

    def detail(self, key: str, state: str, facts: flow.Facts) -> str:
        """The step's line while it is the one to do or failed: what is there to do, in words; "" for its usual
        line."""
        if key == "test" and state == "later" and facts.drafts and flow.current_step(facts) in (
                "pull", "commit", "push", "ci", "start"):
            # After Not OK, or after a restart of NRT, which keeps nothing of its own: the draft says it is still there
            return (f"{', '.join(facts.drafts)} is still a draft, not published: Start new release replaces it with "
                    "a new one.")
        if state not in ("now", "failed"):
            return ""
        window = self.release_window
        if key == "pull":
            return f"{facts.behind} commit{'s' if facts.behind != 1 else ''} on GitHub that this checkout lacks."
        if key == "commit":
            files = len(flow.dirty_paths(window.root))
            return f"{files} file{'s' if files != 1 else ''} changed. Type what they do, then Commit."
        if key == "push":
            return f"{facts.ahead} commit{'s' if facts.ahead != 1 else ''} to push."
        if key == "ci":
            if facts.ci == "failed":
                return ("CI failed on this commit. When it was GitHub's own trouble (an error of its servers, a job "
                        "that never started): Run CI again. When a test failed: fix it, then Commit and Push.")
            return ("CI is running on this commit: wait until it passed." if facts.ci == "building" else
                    "GitHub has no CI run on this commit yet: wait a moment.")
        if key == "start":
            return (f"The release commit is not pushed yet ({facts.unpushed}): Push and start." if facts.unpushed
                    else "Check the versions in the table above, then Start new release.")
        if key == "run" and facts.run is not None:
            link = f' <a href="{facts.run.url}">Open the run</a>'
            if not facts.run.done:
                return f"{flow.WORKFLOW_NAME} is {facts.run.outcome} on {facts.run.sha[:7]}: wait, or Stop run.{link}"
            if facts.restart:
                return (f"{flow.WORKFLOW_NAME} ended {facts.run.outcome} on {facts.run.sha[:7]}; the fix is pushed and "
                        f"passed CI: Start again on this commit (the release is not written anew).{link}")
            return (f"{flow.WORKFLOW_NAME} ended {facts.run.outcome}: when it failed on something of GitHub's, Resume "
                    f"run; when the code must change, fix it, then Commit, Push, and start it again here.{link}")
        if key == "test" and state == "failed":
            return (f"Not OK: {', '.join(facts.drafts)} stays a draft, no portal sees it. Fix what the test showed, "
                    "then Commit your changes, Push them and, once CI passes, Start new release: the portal is built "
                    "anew, the apps already out are skipped. Device test tests this draft again; Publish still "
                    "publishes it.")
        if key in ("test", "publish") and facts.drafts:
            return (f"{', '.join(facts.drafts)} is a draft: Device test, then Publish when it works or Not OK."
                    if key == "test" else "After the device test: Publish, or Not OK.")
        if key == "finish":
            return "The release is out: git pull brings in its Pin ... commit."
        return ""

    def waiting_suite(self) -> str | None:
        tag = self.portal_choice.currentText()
        root = self.release_window.root
        return next((s for s in flow.release_suites(root) if tag.startswith(f"{rp.tag_prefix(root, s)}portal-v")),
                    None)

    # --- the pills ------------------------------------------------------------------------------------------------

    def rerun_ci(self) -> None:
        window = self.release_window
        head = (rp.git(window.root, "rev-parse", "HEAD") or "").strip()
        failed = flow.failed_ci(window.build.runs, head)
        if failed:
            window.run_git(flow.rerun_ci_command(failed))

    def pull(self) -> None:
        self.release_window.run_git(rp.pull_command())

    def commit(self) -> None:
        message = self.commit_message.text().strip()
        if not message:
            return
        window = self.release_window
        window.committing = True
        window.run_git(flow.commit_work_command(window.root, message, window.base(), shlex.quote(sys.executable)))
        self.commit_message.clear()

    def start(self) -> None:
        window = self.release_window
        pending = flow.unpushed_release(window.root, window.base())
        if pending:                             # the release commit is made; its push stopped: push and start
            if window.confirm_git("Push and start", f"Push the release commit and start it on GitHub:\n\n{pending}",
                                  flow.push_and_start_command()):
                window.run_git(flow.push_and_start_command())
            return
        reasons = flow.ready(window.root, window.base())
        chosen = self.chosen()
        problems = flow.problems(chosen)
        if reasons or problems or not chosen:
            QMessageBox.warning(self, "Start new release", "\n".join(reasons + problems) or "Nothing to release.")
            return
        rows = "\n".join(f"{p.label}: {p.unit.version} -> {p.version or p.choices[0]}" for p in chosen)
        if not window.confirm_git("Start new release", "Write this release, commit it, push it to main and start "
                                  f"it on GitHub:\n\n{rows}", flow.start_command("Release ...")):
            return
        log, tags = flow.write(window.root, chosen, window.base())
        message = flow.commit_message(tags)
        log += ["", f"Commit \"{message}\", push, and {flow.NEXUS_WORKFLOW} on GitHub: see Commands."]
        self.output.set_text("\n".join(log))
        window.run_git(flow.start_command(message))

    def run(self) -> rp.BuildRun | None:
        return flow.release_run(self.release_window.build.runs)

    def stop_run(self) -> None:
        run = self.run()
        if run is not None and QMessageBox.question(
                self, "Stop run", f"Stop {flow.WORKFLOW_NAME} on {run.sha[:7]}? What is published stays; no "
                                  "portal is published by it.") == QMessageBox.StandardButton.Yes:
            self.release_window.run_git(flow.stop_command(run))

    def resume_run(self) -> None:
        """Resume run: the failed jobs again on the same commit; with a fix on top (restart), the release started
        again on HEAD, written as it is."""
        run = self.run()
        if run is None:
            return
        if self.facts.restart:
            window = self.release_window
            if window.confirm_git("Start again on this commit", f"Start {flow.WORKFLOW_NAME} again on HEAD, the fix on "
                                  f"top of {run.sha[:7]}: the release as it is written, nothing new is written.",
                                  flow.restart_command()):
                window.run_git(flow.restart_command())
            return
        self.release_window.run_git(flow.resume_command(run))

    def device_test(self) -> None:
        tag, suite = self.portal_choice.currentText(), self.waiting_suite()
        if not tag or suite is None:
            return
        windows = rp.suite_system(self.release_window.root, suite) == "windows"
        try:
            self.release_window.launch(flow.device_test_line(self.release_window.root, suite, tag, windows))
        except RuntimeError as exc:
            self.output.set_text(str(exc))
            return
        self.output.set_text(f"A terminal downloads the draft of {tag}, checks it against its SHA256SUMS, installs "
                             "it and starts it. Test it as a user would; then Publish, or Not OK.")

    def publish(self) -> None:
        tag = self.portal_choice.currentText()
        if tag and self.release_window.confirm_git(
                "Publish", f"The device test of {tag} passed: publish it. Its tag is made, the portals offer it from "
                           "now on and the Nexus index follows.", flow.publish_command(tag)):
            self.release_window.run_git(flow.publish_command(tag))

    def reject(self) -> None:
        """Not OK: the draft stays unpublished, and the Device test step says so in red until the fix is committed
        (owner, 30-10-2026: it only wrote a line below, which looked like nothing)."""
        tag = self.portal_choice.currentText()
        run = self.run()
        if tag and run is not None:
            settings = self.release_window.settings
            if settings is not None:
                kept = str(settings.value(REJECTED_KEY, "") or "").split()
                settings.setValue(REJECTED_KEY, " ".join([*kept, f"{run.url}|{tag}"][-20:]))
            else:
                self.rejected_here.setdefault(run.url, []).append(tag)
        self.output.set_text(f"{tag} stays a draft: no portal sees it. Fix what the device test showed, then do the "
                             "steps again from Commit your changes: the apps already out are skipped and the portal "
                             "is built anew.")
        self.release_window.tabs.setCurrentWidget(self)
        self.show_state()
