# SPDX-License-Identifier: GPL-3.0-or-later
"""The Nexus release tab (owner, 30-10-2026): what the release holds, its one action Start new release, and what
follows: the run on GitHub (stopped or resumed from here), the device test of each suite's draft portal and Publish.
The logic is flow.py's; the window (main_window.py) holds the command line the commands run in and the GitHub runs
the header reads."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from bc250_core.theme import GREEN, GREY, ORANGE, RED
from bc250_core.widgets import Terminal, accent_button, hint_label

from . import flow
from . import plan as rp

if TYPE_CHECKING:
    from .main_window import ReleaseWindow

COLUMNS = ("Release", "Now", "New version", "Why", "Notes")
SEMVER_TIP = ("Breaking. (an entry that starts with it) -> major, Added. -> minor, Fixed. -> patch. auto: worked out "
              "when Start writes the release.")


class ReleasePage(QWidget):
    """The Nexus release: the rows to release, Start new release, and the run, device test and Publish after it."""

    def __init__(self, window: "ReleaseWindow"):
        super().__init__()
        self.release_window = window
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
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
        self.resume_button = QPushButton("Resume run")
        self.resume_button.setToolTip("Start the jobs that failed or were stopped again (gh run rerun --failed): what "
                                      "is out already is skipped, the draft made anew")
        self.resume_button.clicked.connect(self.resume_run)
        self.portal_choice = QComboBox()        # the suites' portal tags waiting for their device test
        self.test_button = QPushButton("Device test")
        self.test_button.setToolTip("Install the draft portal on this device from GitHub and start it "
                                    "(check-release draft): test it as a user would")
        self.test_button.clicked.connect(self.device_test)
        self.publish_button = accent_button("Publish", "The device test passed: publish the draft, which makes the "
                                            "portal tag; the portals offer it from then on")
        self.publish_button.clicked.connect(self.publish)
        self.reject_button = QPushButton("Not OK")
        self.reject_button.setToolTip("The device test failed: the draft stays unpublished")
        self.reject_button.clicked.connect(self.reject)
        self.output = Terminal()                # the window shows it in Logs
        self.picks: list[flow.Pick] = []
        self.rows: list[tuple[flow.Pick, QComboBox, QLineEdit]] = []

        start_row = QHBoxLayout()
        start_row.addWidget(self.why_not, 1)
        start_row.addWidget(self.start_button)
        after_row = QHBoxLayout()
        after_row.addWidget(self.stop_button)
        after_row.addWidget(self.resume_button)
        after_row.addStretch(1)
        after_row.addWidget(QLabel("Portal:"))
        after_row.addWidget(self.portal_choice)
        after_row.addWidget(self.test_button)
        after_row.addWidget(self.publish_button)
        after_row.addWidget(self.reject_button)
        lay = QVBoxLayout(self)
        lay.addWidget(hint_label(
            "One release for every suite on it: the apps that changed, their portal, core and Nexus's version. Check "
            "the versions (type another to override; <b>auto</b> is worked out at Start), then <b>Start new "
            "release</b>: it writes the release, commits and pushes it and starts it on GitHub, which builds, "
            "publishes and pins the apps and makes each portal a draft. Then, on the suite's device: <b>Device "
            "test</b> installs that draft; <b>Publish</b> when it works, which the portals then offer, or <b>Not "
            "OK</b>. A run that failed: <b>Resume run</b>; one that must not go on: <b>Stop run</b>."))
        lay.addWidget(self.table, 1)
        lay.addLayout(start_row)
        lay.addWidget(self.state)
        lay.addLayout(after_row)

    # --- before Start ---------------------------------------------------------------------------------------------

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

    # --- after Start ----------------------------------------------------------------------------------------------

    def run(self) -> rp.BuildRun | None:
        return flow.release_run(self.release_window.build.runs)

    def show_state(self) -> None:
        """Start only when it can go; the run's state and what to do next; its buttons only when they have
        something to do. Read from the runs the header fetched, so it costs no request."""
        window = self.release_window
        idle = not window.commands.is_running() and bool(window.commands.bash)
        pending = flow.unpushed_release(window.root, window.base())
        reasons = flow.ready(window.root, window.base()) if self.picks and not pending else []
        self.why_not.setText(f"The release commit is not pushed yet ({pending}): Push and start." if pending else
                             " ".join(reasons))
        self.start_button.setText("Push and start" if pending else "Start new release")
        self.start_button.setEnabled(idle and (bool(pending) or bool(self.picks) and not reasons))
        self.start_button.setToolTip("Push the release commit and start it on GitHub" if pending else
                                     "Nothing to release: no app of a suite on the Nexus release changed since its "
                                     "last release." if not self.picks else " ".join(reasons) or
                                     "Write the release, commit it, push it and start it on GitHub")
        run = self.run()
        head = (rp.git(window.root, "rev-parse", "HEAD") or "").strip()
        if run is None:
            text, color = "No Nexus release has run on GitHub yet." if window.build.source is not None else "", GREY
        elif not run.done:
            text, color = f"{flow.WORKFLOW_NAME} is running on {run.sha[:7]} ({run.status.replace('_', ' ')}).", \
                ORANGE
        elif run.passed:
            text = (f"{flow.WORKFLOW_NAME} on {run.sha[:7]} passed: each suite's portal is a draft. Device test on "
                    "the suite's device, then Publish.")
            color = GREEN
        else:
            text, color = (f"{flow.WORKFLOW_NAME} on {run.sha[:7]} ended {run.outcome}: open it, fix what failed, "
                           "then Resume run (what is out already is skipped)."), RED
        if run is not None:
            text += f' <a href="{run.url}">Open the run</a>'
            if run.sha != head and run.done:
                text += " · git pull brings its pin commit"
        self.state.setText(text)
        self.state.setStyleSheet(f"color:{color}; font-weight:600;")
        self.stop_button.setEnabled(idle and run is not None and not run.done)
        self.resume_button.setEnabled(idle and run is not None and run.done and not run.passed)
        waiting = self.portal_choice.count() > 0
        windows = sys.platform == "win32"
        here = waiting and rp.tests_here(window.root, self.waiting_suite())
        self.test_button.setEnabled(idle and here)
        self.test_button.setToolTip("Install the draft portal on this device and start it" if here else
                                    "The device test runs on the suite's own system: " +
                                    ("Linux (the board)" if windows else "Windows (the handheld)"))
        self.publish_button.setEnabled(idle and waiting)
        self.reject_button.setEnabled(waiting)

    def waiting_suite(self) -> str | None:
        tag = self.portal_choice.currentText()
        root = self.release_window.root
        return next((s for s in flow.release_suites(root) if tag.startswith(f"{rp.tag_prefix(root, s)}portal-v")),
                    None)

    def stop_run(self) -> None:
        run = self.run()
        if run is not None and QMessageBox.question(
                self, "Stop run", f"Stop {flow.WORKFLOW_NAME} on {run.sha[:7]}? What is published stays; no "
                                  "portal is published by it.") == QMessageBox.StandardButton.Yes:
            self.release_window.run_git(flow.stop_command(run))

    def resume_run(self) -> None:
        run = self.run()
        if run is not None:
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
        tag = self.portal_choice.currentText()
        self.output.set_text(f"{tag} stays a draft: no portal sees it. Fix what the device test showed, commit and "
                             "push the fix, then Start new release again: the apps already out are skipped and the "
                             "portal is built anew.")
        self.release_window.tabs.setCurrentWidget(self)
