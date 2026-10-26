# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: enter the new versions, and it edits the files of a release (plan.py).

Step 1, Release apps: tick the apps to release, enter their versions and notes, Apply. It writes VERSION, the copies
check_versions.py checks and a "Release x.y.z." CHANGELOG entry, runs check_versions.py and check_manifest.py (an
apps.toml changed since the last portal release needs a portal bump in the same push) and shows the git commands.
Step 2, Pin and release Portal: once GitHub has built the app releases, Pin fills in their tag and sha256 in apps.toml;
Bump portal writes the portal version (at least what check_manifest.py asks) and its CHANGELOG entry, runs
check_manifest.py and shows the git commands: the portal release's, or step 1's with the bump in them while step
1's releases are not tagged yet (an app added to apps.toml needs the bump in the push that adds it). Under the tabs,
git add, git commit, git push and git tag are buttons with their checks in between: add sets the exec bits
(fix-modes.sh), commit runs check_versions.py and check_manifest.py first, push runs tools/ci-local.sh first (Linux)
and pushes only when CI's jobs pass, tag runs tag-release.sh (a pushed HEAD that CI passed) with the tags of the step
open: step 2's portal tag, else step 1's app tags. Push and tag ask first, with what they send, and warn when the
GitHub token on the machine reaches every repository of the account.
The header is a row of pills, as the apps' status boxes (owner, 20-10-2026): Refresh, the working tree, whether
GitHub built the last push (CI, Release, Manual; it notifies when a build it saw running passes or fails), how many
of GitHub's API requests are left (green, orange under a tenth, red at none), GitHub status: green while
githubstatus.com reports GitHub up, red while it reports a problem; a click opens that page, and Claude tokens today:
what Claude Code on this machine used, from its transcripts; a click opens Claude's usage page.
Test on this board: Test app updates and Test withdrawal install the portal from the checkout and start it with the
apps from their releases, Test Portal release installs the published portal release (check-release.sh, in a
terminal); Installer tests opens BC-250 Installer Tests; Record portal tour records the portal's video tour
from this checkout (tools/record-tour.sh) into ~/Videos and opens it; Close issues lists the open GitHub issues,
and closes the ticked ones with gh issue close in the Commands tab. Test local apps: click an app's icon to start it from this
checkout, to try it before its release (the portal is the first icon); a wiki's icon (one per mkdocs.yml) serves it
from the checkout (mkdocs serve, a port each) and opens it with its design panel; Wikis on the network serves them
for the other devices too.
The Commands tab is a command line in the checkout (command_line.py), where the git buttons run too; its Commands
menu offers the ones the last step showed."""

from __future__ import annotations

import os
import shlex
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QProcess, QRectF, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtNetwork import QLocalSocket
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListView,
                             QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QStackedWidget,
                             QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from bc250_core.instance import server_name
from bc250_core.platform import launch_in_terminal
from bc250_core.theme import ACCENT, BLUE, GREEN, GREY, ORANGE, RED
from bc250_core.updates import UpdateChecker
from bc250_core.widgets import AppHeader, MetricBox, Pill, Terminal, accent_button, hint_label, same_width

from . import APP_NAME, LOGO_PATH, SUITE, __version__
from . import plan as rp
from .command_line import CommandLine

COLUMNS = ("Release", "App", "VERSION", "Last tag", "Needs release", "New version", "Notes")
SEMVER_TIP = ("Breaking. (an entry that starts with it) -> major: something removed or no longer working as "
              "before. Added. -> minor: a new feature. Fixed. -> patch: a bug or security fix.")
LOG_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "bc250-release" / "run"
# A selected cell and the input field being typed in: a purple outline with rounded corners on a transparent
# background, not the desktop's solid highlight. The line edit inside an editable combo box keeps the combo's frame.
SELECTION_STYLESHEET = (
    "QTableWidget { outline:0; selection-background-color:transparent; selection-color:palette(text); }"
    "QTableWidget::item { border:2px solid transparent; border-radius:6px; }"
    f"QTableWidget::item:selected {{ background:transparent; color:palette(text); border-color:{ACCENT}; }}"
    f"QLineEdit:focus {{ background:transparent; border:2px solid {ACCENT}; border-radius:6px; }}"
    "QComboBox QLineEdit:focus { border:none; }"
)


def run_check(root: Path, *args: str) -> str:
    result = subprocess.run([sys.executable, *args], cwd=root, capture_output=True, text=True)
    out = (result.stdout + result.stderr).strip()
    return f"$ python3 {' '.join(args)}\n{out or '(no output)'}\n" + ("" if result.returncode == 0 else
                                                                        f"exit code {result.returncode}\n")


def needs_tooltip(unit: rp.Unit) -> str:
    if unit.kind == "core":
        text = "Core is never tagged: each app that imports it ships its own copy, so a core change needs a release " \
               "of those apps (ticked with them, not here)."
        if unit.in_apps:
            text += "\n\nChanged: " + ", ".join(unit.changed) + "\nGoes into: " + ", ".join(unit.in_apps)
            if unit.current:
                text += f"\n\nCore {unit.version} already has these changes: it needs no new version."
        return text
    if unit.last_tag is None:
        return "Never released."
    if not unit.changed:
        return f"Nothing it ships changed since {unit.last_tag}."
    files = unit.changed[:25] + ([f"… and {len(unit.changed) - 25} more"] if len(unit.changed) > 25 else [])
    return f"Changed since {unit.last_tag} ({unit.commits} commits, plus what is not committed):\n" + "\n".join(files)


class AppsPage(QWidget):
    """Step 1: the apps (and core) with their new versions."""

    def __init__(self, window: "ReleaseWindow"):
        super().__init__()
        self.release_window = window
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        self.apply_button = accent_button("Apply", "Write the new versions and CHANGELOG entries of the ticked apps")
        self.apply_button.clicked.connect(self.apply)
        self.tick_button = QPushButton("Tick what needs a release")
        self.tick_button.setToolTip("Tick every app whose shipped files changed since its last tag")
        self.tick_button.clicked.connect(self.tick_needed)
        self.output = Terminal()                 # the window shows it under the steps, beside the command line
        lay = QVBoxLayout(self)
        lay.addWidget(hint_label(
            "The apps that need a release are ticked; untick what waits and enter their version: a never-tagged "
            "version can be released as it is. Apply writes VERSION, its copies (__version__, VERSION=, pyproject, Cargo.toml and Cargo.lock) and a "
            "\"Release x.y.z.\" CHANGELOG entry with the notes, which become the release notes on GitHub. Core is "
            "bundled with the "
            "apps and gets a version only, no tag. <b>Needs release</b> (orange): something the app ships (its "
            "folder without tests, the core it bundles, its manual chapter) differs from its last tag, committed or "
            "not; hover it for the files."))
        lay.addWidget(self.table, 2)
        row = QHBoxLayout()
        row.addWidget(self.tick_button)
        row.addStretch(1)
        row.addWidget(self.apply_button)
        lay.addLayout(row)
        self.rows: list[tuple[rp.Unit, QCheckBox, QComboBox, QLineEdit]] = []

    def fill(self, units: list[rp.Unit]) -> None:
        shown = [u for u in units if u.kind != "portal"]
        self.table.setRowCount(len(shown))
        self.rows = []
        for i, unit in enumerate(shown):
            tick = QCheckBox()
            if unit.kind == "core" and unit.current:        # its version already covers it: nothing to write
                tick.setEnabled(False)
                tick.setToolTip(f"Core {unit.version} already holds every change since its last version; the app "
                                "releases carry it as it is")
            else:
                tick.setChecked(unit.needs_release)         # ticked from the start; untick what waits
            self.table.setCellWidget(i, 0, tick)
            reason = unit.release_reason
            if unit.needs_release and unit.last_tag and not unit.released:
                reason += f" · {unit.version} not tagged yet"
            tip = needs_tooltip(unit)
            for col, text in ((1, unit.key), (2, unit.version), (3, unit.last_tag or "—"), (4, reason)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setToolTip(tip)
                if unit.needs_release:
                    item.setForeground(QColor(ORANGE))
                self.table.setItem(i, col, item)
            combo = QComboBox()
            combo.setEditable(True)
            choices, why = rp.version_choices(self.release_window.root, unit)
            combo.addItems(choices)
            combo.setToolTip(f"{choices[0]}: {why}.\n\n{SEMVER_TIP}")
            notes = QLineEdit()
            notes.setPlaceholderText("What this release brings (optional)")
            self.table.setCellWidget(i, 5, combo)
            self.table.setCellWidget(i, 6, notes)
            self.rows.append((unit, tick, combo, notes))

    def typed(self) -> dict[str, tuple[bool, str | None, str, bool]]:
        """What was entered per app: the tick, a version only if it differs from the one offered, the notes; and
        whether it needed a release then."""
        return {unit.key: (tick.isChecked(), None if combo.currentText() == combo.itemText(0) else combo.currentText(),
                           notes.text(), unit.needs_release) for unit, tick, combo, notes in self.rows}

    def restore(self, typed: dict[str, tuple[bool, str | None, str, bool]]) -> None:
        """Puts back what was entered; an app that needs a release only since then is ticked, as fill() does."""
        for unit, tick, combo, notes in self.rows:
            if unit.key in typed:
                checked, version, text, needed = typed[unit.key]
                tick.setChecked(checked or (unit.needs_release and not needed and tick.isEnabled()))
                if version is not None:
                    combo.setEditText(version)
                notes.setText(text)

    def tick_needed(self) -> None:
        for unit, tick, _, _ in self.rows:
            tick.setChecked(unit.needs_release)

    def apply(self) -> None:
        picked = [(u, combo.currentText().strip(), notes.text()) for u, tick, combo, notes in self.rows
                  if tick.isChecked()]
        if not picked:
            self.output.set_text("Tick at least one app.")
            return
        problems = [f"{u.key}: {msg}" for u, new, _ in picked
                    if (msg := rp.check_new_version(u.version, new, u.released or u.kind == "core"))]
        if problems:
            QMessageBox.warning(self, "Release", "\n".join(problems))
            return
        root = self.release_window.root
        log, tags, pins_moved = [], [], []
        for unit, new, notes in picked:
            if new != unit.version:
                changed = rp.set_version(root, unit, new)
                log.append(f"{unit.key}: {new} in " + ", ".join(str(p.relative_to(root)) for p in changed))
            text = f"Version {new}." if unit.kind == "core" else rp.release_text(new, notes)
            if unit.kind == "core" and notes.strip():
                text += f" {notes.strip()}"
            rp.add_changelog_entry(root, unit, text)
            log.append(f"{unit.key}: CHANGELOG entry \"{text}\"")
            if unit.kind == "app":
                tags.append(unit.tag)
                if rp.follow_unreleased_pin(root, unit):
                    pins_moved.append(unit.tag)
        if pins_moved:
            log.append(f"apps.toml: the never-released pins move along ({', '.join(pins_moved)}).")
        # apps.toml may also have changed before this release (an app added, removed or moved, a pin moved): CI
        # checks it against the last portal release, with the portal bump it needs. That bump is made here, so the push
        # passes CI as it is (the owner's release of 17-10-2026 was committed without it and failed ci-local); the
        # portal release itself is step 2, once the apps are pinned.
        base, portal_version = self.release_window.base(), self.release_window.portal_version()
        minimum, why = rp.portal_minimum(root, base, portal_version)
        if minimum and minimum != portal_version:
            portal = next(u for u in rp.load_units(root) if u.kind == "portal")
            changed = rp.set_version(root, portal, minimum)
            text = rp.portal_text(minimum, rp.changed_pins(root, base), "", rp.changed_withdrawals(root, base))
            rp.add_changelog_entry(root, portal, text)
            log.append(f"portal: {minimum} in " + ", ".join(str(p.relative_to(root)) for p in changed)
                       + f" and CHANGELOG entry \"{text}\": apps.toml changed since {base} ({why}), so CI needs this "
                       "bump in the same push. The portal release follows in step 2, once the apps are pinned.")
        log += ["", run_check(root, "tools/check_versions.py"),
                run_check(root, "tools/check_manifest.py", "--base", base)]
        if tags:
            commands = rp.app_commands(tags)
            log += ["Then:", commands]
            self.release_window.offer(commands)
        self.output.set_text("\n".join(log))
        self.release_window.reload()


class PortalPage(QWidget):
    """Step 2: pin the released apps and bump the portal."""

    def __init__(self, window: "ReleaseWindow"):
        super().__init__()
        self.release_window = window
        self.base_edit = QLineEdit("origin/main")
        self.base_edit.setToolTip("The last push: Bump portal lists the pins changed since it, and CI compares "
                                  "apps.toml with it while there is no portal release yet (else with the last one)")
        self.fetch_button = QPushButton("Fetch tags")
        self.fetch_button.setToolTip("git fetch --tags: see the tags pushed from another machine")
        self.fetch_button.clicked.connect(self.fetch_tags)
        self.pins = QTableWidget(0, 4)
        self.pins.setHorizontalHeaderLabels(("Pin", "Release", "Pinned now", "GitHub"))
        self.pins.verticalHeader().setVisible(False)
        self.pins.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pin_button = QPushButton("Pin")
        self.pin_button.setToolTip("Read each ticked release's SHA256SUMS from GitHub and pin tag and sha256")
        self.pin_button.clicked.connect(self.pin)
        self.empty_note = hint_label("")
        self.minimum = QLabel()
        self.portal_needs = QLabel()
        self.portal_version = QComboBox()
        self.portal_version.setEditable(True)
        self.portal_notes = QLineEdit()
        self.portal_notes.setPlaceholderText("What this portal release brings (optional)")
        self.bump_button = accent_button("Bump portal", "Write portal/VERSION, its copies and the CHANGELOG entry")
        self.bump_button.clicked.connect(self.bump)
        self.portal_state = QLabel()             # the portal's own release: not tagged yet, building, built
        self.portal_state.setWordWrap(True)
        self.portal_state.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.output = Terminal()                 # the window shows it under the steps, beside the command line

        top = QHBoxLayout()
        top.addWidget(QLabel("Compare with:"))
        top.addWidget(self.base_edit)
        top.addWidget(self.fetch_button)
        top.addStretch(1)
        pin_row = QHBoxLayout()
        pin_row.addStretch(1)
        pin_row.addWidget(self.pin_button)
        portal_row = QHBoxLayout()
        portal_row.addWidget(QLabel("Portal version:"))
        portal_row.addWidget(self.portal_version)
        portal_row.addWidget(self.portal_notes, 1)
        portal_row.addWidget(self.bump_button)
        lay = QVBoxLayout(self)
        lay.addWidget(hint_label(
            "After step 1 is pushed and tagged, and GitHub has built those releases (the GitHub column says where "
            "each one stands; a desktop notification comes when one is ready to pin):<br>"
            "<b>1.</b> Pin: the new tags and their checksums go into apps.toml.<br>"
            "<b>2.</b> Bump portal: the portal version and a CHANGELOG entry that lists the pinned releases.<br>"
            "<b>3.</b> Commit, then <b>Test app updates</b> (tab Test on this board) on a BC-250: it installs the portal from the checkout and "
            "starts it with <code>--source release</code>, so the changed apps install from GitHub and must work.<br>"
            "<b>4.</b> Only then push and tag the portal (<b>git push</b>, then <b>git tag</b> at the bottom): the tag "
            "is what reaches the users. The commands appear in the log after Bump portal (done before step 1's "
            "push, for an added app, they are step 1's commands with the bump in them).<br>"
            "<b>5.</b> Once GitHub's release workflow has built the portal: <b>Test Portal release</b> (tab Test on "
            "this board) downloads and installs "
            "that published release and starts it, so the board runs the official release again."))
        lay.addLayout(top)
        lay.addWidget(self.pins, 1)
        lay.addWidget(self.empty_note)
        lay.addLayout(pin_row)
        lay.addWidget(self.minimum)
        lay.addWidget(self.portal_needs)
        lay.addLayout(portal_row)
        lay.addWidget(self.portal_state)
        self.candidates: list[tuple[rp.Unit, QCheckBox]] = []
        self.portal_unit: rp.Unit | None = None

    def fill(self, units: list[rp.Unit]) -> None:
        cands = rp.pin_candidates(units)
        self.pins.setRowCount(len(cands))
        self.candidates = []
        for i, unit in enumerate(cands):
            tick = QCheckBox()
            tick.setChecked(True)
            self.pins.setCellWidget(i, 0, tick)
            for col, text in ((1, unit.tag), (2, unit.pinned_tag + ("" if unit.pinned_sha else " (no sha256)"))):
                self.pins.setItem(i, col, QTableWidgetItem(text))
            self.candidates.append((unit, tick))
        self.pin_button.setEnabled(bool(cands))
        self.empty_note.setText("" if cands else
                                "Nothing to pin: every app whose VERSION is tagged is already pinned with its checksum. "
                                "Tagged on another machine? Fetch tags. Not tagged yet? Do step 1, push, and push the "
                                "app tags first.")
        self.empty_note.setVisible(not cands)
        portal = next(u for u in units if u.kind == "portal")
        self.portal_unit = portal
        if portal.needs_release:
            self.portal_needs.setText(f"The portal needs a release: {portal.release_reason}"
                                      + (f" since {portal.last_tag}." if portal.last_tag else "."))
            self.portal_needs.setStyleSheet(f"color:{ORANGE}; font-weight:600;")
        else:
            self.portal_needs.setText(f"Nothing the portal ships changed since {portal.last_tag}.")
            self.portal_needs.setStyleSheet("")
        self.portal_needs.setToolTip(needs_tooltip(portal))
        minimum, why = rp.portal_minimum(self.release_window.root, self.release_window.base(), portal.version)
        if minimum:
            self.minimum.setText(f"apps.toml changed since {self.release_window.base()} ({why}): the portal needs at least "
                                 f"{minimum}.")
        else:
            self.minimum.setText(f"apps.toml is unchanged since {self.release_window.base()}.")
        # The higher of what CI asks (since the last portal release) and what semantic versioning gives since it.
        suggested, semver = rp.portal_suggestion(self.release_window.root, portal)
        if minimum and rp.version_tuple(minimum) > rp.version_tuple(suggested):
            suggested, semver = minimum, f"CI's minimum: {why}"
        choices = [suggested, *([] if portal.released else [portal.version]),
                   *rp.next_versions(portal.version).values()]
        choices = [v for i, v in enumerate(choices) if v not in choices[:i]
                   and not rp.check_new_version(portal.version, v, portal.released)]
        self.portal_version.clear()
        self.portal_version.addItems(choices)
        self.portal_version.setToolTip(f"{suggested}: {semver}.\n\n{SEMVER_TIP}")
        self.show_builds()

    def waiting_tags(self) -> list[str]:
        """The app releases step 2 waits for: tagged, not pinned with their checksum yet."""
        return [unit.tag for unit, _tick in self.candidates]

    def show_builds(self) -> None:
        """What GitHub shows for each release to pin and for the portal's own release (the header's indicator
        reads the runs; this is read from them, so it costs no request)."""
        runs = self.release_window.build.runs
        for i, (unit, _tick) in enumerate(self.candidates):
            state = rp.release_state(runs, unit.tag)
            item = QTableWidgetItem(RELEASE_TEXT[state])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setToolTip(RELEASE_TIP[state].format(tag=unit.tag))
            self.pins.setItem(i, 3, item)
        portal = self.portal_unit
        if portal is None:
            return
        if not portal.released:
            text = (f"{portal.tag} is not tagged yet: nothing reaches the users until it is. After the test on a "
                    f"board, push and tag it ({rp.TAG_SCRIPT} {portal.tag}); GitHub then builds the release.")
            color = ORANGE
        else:
            state = rp.release_state(runs, portal.tag)
            text = {"": f"{portal.tag} is tagged; GitHub shows no release run on it among its newest runs (is the "
                        "tag pushed?).",
                    "running": f"{portal.tag} is tagged and GitHub is building its release; a notification comes "
                               "when it is ready for Test Portal release.",
                    "passed": f"{portal.tag} is released: GitHub built it. Test Portal release installs it on this board.",
                    "failed": f"{portal.tag} is tagged but GitHub's release workflow failed on it: click GitHub in "
                              "the header to open the run."}[state]
            color = {"": ORANGE, "running": ORANGE, "passed": GREEN, "failed": RED}[state]
        self.portal_state.setText(text)
        self.portal_state.setStyleSheet(f"color:{color}; font-weight:600;")

    def fetch_tags(self) -> None:
        out = rp.git(self.release_window.root, "fetch", "--tags", "--quiet")
        self.output.set_text("Tags fetched." if out is not None else "git fetch --tags failed.")
        self.release_window.reload()

    def pin(self) -> None:
        log = []
        for unit, tick in self.candidates:
            if not tick.isChecked():
                continue
            state = rp.release_state(self.release_window.build.runs, unit.tag)
            if state == "running":
                log.append(f"{unit.tag}: GitHub is still building that release; a notification comes when it is "
                           "ready. Not pinned.")
                continue
            if state == "failed":
                log.append(f"{unit.tag}: GitHub's release workflow failed on it, so there is nothing to pin: click "
                           "GitHub in the header to open the run. Not pinned.")
                continue
            try:
                sha = self.release_window.sha256_source(unit.tag)
            except (OSError, SystemExit) as exc:
                log.append(f"{unit.tag}: no checksum yet ({exc}). Has GitHub finished that release?")
                continue
            try:
                rp.pin(self.release_window.root, unit, sha)
            except SystemExit as exc:           # pin_app refuses (no such table, no tag line): say so, go on
                log.append(f"{unit.tag}: not pinned ({exc}).")
                continue
            log.append(f"{unit.tag}: pinned ({sha[:16]}…)")
        self.release_window.reload()
        self.output.set_text("\n".join(log) or "Tick a release to pin.")

    def bump(self) -> None:
        root = self.release_window.root
        units = rp.load_units(root)
        portal = next(u for u in units if u.kind == "portal")
        new = self.portal_version.currentText().strip()
        problem = rp.check_new_version(portal.version, new, portal.released)
        if problem:
            QMessageBox.warning(self, "Bump portal", problem)
            return
        log = []
        if new != portal.version:
            changed = rp.set_version(root, portal, new)
            log.append(f"portal: {new} in " + ", ".join(str(p.relative_to(root)) for p in changed))
        pins = rp.changed_pins(root, self.release_window.base())
        withdrawn = rp.changed_withdrawals(root, self.release_window.base())
        text = rp.portal_text(new, pins, self.portal_notes.text(), withdrawn)
        rp.add_changelog_entry(root, portal, text)
        log += [f"portal: CHANGELOG entry \"{text}\"", "",
                run_check(root, "tools/check_versions.py"),
                run_check(root, "tools/check_manifest.py", "--base", self.release_window.base())]
        # Bumped before step 1's push (an app added, a pin moved): the bump goes into that push, with the app tags
        # after it; the portal release comes after Pin. Otherwise commit, test on a board, push and tag the portal.
        pending = rp.untagged_releases(units)
        if pending:
            amend = bool(rp.unpushed_release_commit(root, self.release_window.base()))
            commands = rp.app_commands(pending, amend=amend)
            log += [f"Then (step 1's releases are not tagged yet: {', '.join(pending)}; the bump goes into their "
                    "push, and the portal release follows once they are pinned):", commands]
        else:
            commands = rp.portal_commands(f"portal-v{new}")
            log += ["Then:", commands]
        self.release_window.offer(commands)
        self.output.set_text("\n".join(log))
        self.release_window.reload()


class WithdrawPage(QWidget):
    """Withdrawing a release: marked in apps.toml (and, with the commands shown, on GitHub); tested on a board before
    the portal release that removes it from the boards."""

    def __init__(self, window: "ReleaseWindow"):
        super().__init__()
        self.release_window = window
        self.app_box = QComboBox()
        self.app_box.currentIndexChanged.connect(lambda _: self._show_state())
        self.state = QLabel()
        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText("Why: what is wrong with this release (shown on the boards)")
        self.withdraw_button = accent_button("Retract", "Mark the pinned release withdrawn in apps.toml, with a "
                                             "CHANGELOG entry in the app")
        self.withdraw_button.clicked.connect(self.withdraw)
        self.back_button = QPushButton("Take back")
        self.back_button.setToolTip("Remove the mark again (after a test, or a mistake)")
        self.back_button.clicked.connect(self.take_back)
        self.output = Terminal()                 # the window shows it under the steps, beside the command line
        row = QHBoxLayout()
        row.addWidget(QLabel("App:"))
        row.addWidget(self.app_box)
        row.addWidget(self.state, 1)
        reason_row = QHBoxLayout()
        reason_row.addWidget(self.reason_edit, 1)
        reason_row.addWidget(self.withdraw_button)
        reason_row.addWidget(self.back_button)
        lay = QVBoxLayout(self)
        lay.addWidget(hint_label(
            "For a release that must not be used any more (privacy, security, any reason):<br>"
            "<b>1.</b> Retract: apps.toml marks the pinned release withdrawn, with the reason the boards show.<br>"
            "<b>2.</b> <b>Test withdrawal</b> (tab Test on this board) on a BC-250 that has the app installed: the portal from this checkout shows "
            "it as \"App not available\" and removes it. Take back undoes the mark.<br>"
            "<b>3.</b> Mark the release on GitHub with the command shown (it stays, as a pre-release, so no update "
            "check offers it), then release the portal in step 2: it removes the app from the boards."))
        lay.addLayout(row)
        lay.addLayout(reason_row)
        self.units: list[rp.Unit] = []

    def fill(self, units: list[rp.Unit]) -> None:
        current = self.app_box.currentData()
        self.units = rp.withdrawable(self.release_window.root, units)
        self.app_box.blockSignals(True)
        self.app_box.clear()
        for unit in self.units:
            self.app_box.addItem(unit.pinned_tag, unit.key)
        if current in [u.key for u in self.units]:
            self.app_box.setCurrentIndex([u.key for u in self.units].index(current))
        self.app_box.blockSignals(False)
        self._show_state()

    def unit(self) -> rp.Unit | None:
        key = self.app_box.currentData()
        return next((u for u in self.units if u.key == key), None)

    def _show_state(self) -> None:
        unit = self.unit()
        reason = rp.withdrawn_reason(self.release_window.root, unit.key) if unit else ""
        self.state.setText(f"Withdrawn: {reason}" if reason else "Not withdrawn.")
        self.state.setStyleSheet(f"color:{ORANGE}; font-weight:600;" if reason else "")
        self.withdraw_button.setEnabled(unit is not None and not reason)
        self.back_button.setEnabled(bool(reason))

    def withdraw(self) -> None:
        unit = self.unit()
        reason = self.reason_edit.text().strip()
        if unit is None:
            return
        if not reason:
            QMessageBox.warning(self, "Retract", "Say why the release is withdrawn: the boards show it.")
            return
        changed = rp.withdraw(self.release_window.root, unit, reason)
        root = self.release_window.root
        self.output.set_text("\n".join([f"{unit.pinned_tag}: withdrawn in " +
                                        ", ".join(str(p.relative_to(root)) for p in changed), "",
                                        rp.withdraw_commands(unit.pinned_tag, reason)]))
        self.release_window.offer(rp.withdraw_commands(unit.pinned_tag, reason))
        self.reason_edit.clear()
        self.release_window.reload()

    def take_back(self) -> None:
        unit = self.unit()
        if unit is None:
            return
        rp.withdraw(self.release_window.root, unit, "")
        self.output.set_text(f"{unit.pinned_tag}: no longer withdrawn in portal/apps.toml (and a CHANGELOG entry). "
                             "Marked on GitHub already? Edit that release back: gh release edit "
                             f"{unit.pinned_tag} --prerelease=false --title {unit.pinned_tag}")
        self.release_window.reload()


def start_app(command: list[str], env: dict[str, str], cwd: Path, log: Path) -> subprocess.Popen:
    """Starts an app in its own session, so it keeps running when this window closes; its output goes to *log*."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "wb") as out:
        return subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.STDOUT, start_new_session=True)


def answers(url: str) -> bool:
    """True when something listens at the host and port of *url* (a local server that is up)."""
    address = QUrl(url)
    try:
        with socket.create_connection((address.host(), address.port(80)), timeout=0.2):
            return True
    except OSError:
        return False


def open_url(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


def log_tail(log: Path, lines: int = 20) -> str:
    try:
        return "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


ICON_PX = 64                            # the apps' icons under Test local apps
BADGE_PX = 26                           # the warning in the corner of an app's icon that changes the board


def board_badge(icon: QIcon) -> QIcon:
    """*icon* with a warning in its lower right corner: the app changes how the board runs. On the icon, not in the
    label, so a name that wraps never pushes it out of the grid's cell."""
    pixmap = QPixmap(ICON_PX, ICON_PX)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    icon.paint(painter, 0, 0, ICON_PX, ICON_PX)
    corner = QRectF(ICON_PX - BADGE_PX, ICON_PX - BADGE_PX, BADGE_PX, BADGE_PX)
    painter.setPen(QPen(QColor("white"), 2))
    painter.setBrush(QColor(ORANGE))
    painter.drawEllipse(corner.adjusted(1, 1, -1, -1))
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(BADGE_PX - 8)
    painter.setFont(font)
    painter.drawText(corner, Qt.AlignmentFlag.AlignCenter, "!")
    painter.end()
    return QIcon(pixmap)


def instance_running(app_id: str) -> bool:
    """Whether *app_id* is open for this user: something listens on its instance socket (core's instance.py). It only
    connects and lets go, so the open window is not asked to show itself."""
    connection = QLocalSocket()
    connection.connectToServer(server_name(app_id))
    found = connection.waitForConnected(500)
    connection.abort()
    return found


class RunPage(QWidget):
    """Test on this board: the board checks of a release (check-release.sh in a terminal), the installer tests, and
    every app window in the checkout as an icon: a click starts it from the checkout, as it is before a release."""

    def __init__(self, window: "ReleaseWindow"):
        super().__init__()
        self.release_window = window
        self.local_button = QPushButton("Test app updates")
        self.local_button.setToolTip("Before the push: install the portal from this checkout and start it with the "
                                     "apps from the pinned GitHub releases (check-release.sh local)")
        self.local_button.clicked.connect(lambda: self.check("local"))
        self.release_button = QPushButton("Test Portal release")
        self.release_button.clicked.connect(lambda: self.check("release"))
        self.withdraw_button = QPushButton("Test withdrawal")
        self.withdraw_button.setToolTip("On a board with the app installed: install the portal from this checkout "
                                        "and start it (check-release.sh local); it must show the app as not available "
                                        "and remove it")
        self.withdraw_button.clicked.connect(lambda: self.check("withdrawal"))
        self.installer_button = QPushButton("Installer tests")
        self.installer_button.setToolTip("Open BC-250 Installer Tests from this checkout: every installer test, one "
                                         "at a time, with its output live")
        self.installer_button.clicked.connect(self.installer_tests)
        self.tour_button = QPushButton("Record portal tour")
        self.tour_button.setToolTip("Record the portal's video tour from this checkout, for the wiki and YouTube "
                                    f"({rp.RECORD_SCRIPT}, about a minute), into ~/Videos, and open it")
        self.tour_button.clicked.connect(self.record_tour)
        self.recorder: QProcess | None = None
        self.issues_button = QPushButton("Close issues")
        self.issues_button.setToolTip("The open issues on GitHub: tick the ones that are handled, and Run closes "
                                      "them (gh issue close, in the Commands tab)")
        self.issues_button.clicked.connect(self.close_issues)
        if not sys.platform.startswith("linux"):
            for button in (self.local_button, self.release_button, self.withdraw_button, self.installer_button,
                           self.tour_button):
                button.setEnabled(False)
                button.setToolTip("Runs on the board: Linux only")
        self.apps = QListWidget()
        self.apps.setViewMode(QListView.ViewMode.IconMode)
        self.apps.setIconSize(QSize(ICON_PX, ICON_PX))
        self.apps.setGridSize(QSize(150, 120))
        self.apps.setResizeMode(QListView.ResizeMode.Adjust)
        self.apps.setMovement(QListView.Movement.Static)
        self.apps.setWordWrap(True)
        self.apps.itemClicked.connect(lambda item: self.run(item.data(Qt.ItemDataRole.UserRole)))
        self.network_box = QCheckBox("Wikis on the network")
        self.network_box.setToolTip("Serve the wikis on every address of this computer, on ports of their own, so "
                                    "the other devices on the network (a handheld, a laptop, the TV) open them too; "
                                    "their addresses show below once a wiki started")
        self.network_box.toggled.connect(lambda _on: self.release_window.reload())
        self.output = Terminal()                 # the window shows it under the steps, beside the command line
        checks = QHBoxLayout()
        for button in (self.local_button, self.release_button, self.withdraw_button, self.installer_button,
                       self.tour_button, self.issues_button):
            checks.addWidget(button)
        checks.addStretch(1)
        local = QLabel("Test local apps")
        local.setStyleSheet("font-weight:700;")
        local_row = QHBoxLayout()
        local_row.addWidget(local)
        local_row.addStretch(1)
        local_row.addWidget(self.network_box)
        lay = QVBoxLayout(self)
        lay.addWidget(hint_label(
            "The tests of a release, on a BC-250. <b>Test app updates</b> (step 2, before the portal's push): the "
            "portal from this checkout, with the apps from their GitHub releases. <b>Test Portal release</b> (after "
            "GitHub built the portal): the published portal release. <b>Test withdrawal</b> (step 3): the portal from "
            "this checkout on a board with the withdrawn app installed. Each runs in a terminal; close the portal "
            "there to finish. <b>Installer tests</b> opens BC-250 Installer Tests. <b>Record portal tour</b> records "
            "the portal's video tour from this checkout, as it is now, and opens it when it is done. <b>Close "
            "issues</b> lists the open issues on GitHub, such as the weekly Upstream review, and closes the ones "
            "you tick once they are handled."))
        lay.addLayout(checks)
        lay.addSpacing(8)
        lay.addLayout(local_row)
        lay.addWidget(hint_label(
            "Click an app to start it from this checkout, to try it before its release: <code>python -m</code> with "
            "this venv and the checkout's core, as <code>run.sh</code> starts this app. An app that changes how the "
            "board runs (an orange <b>!</b> on its icon) asks first; it uses the scripts in the checkout. Each app "
            f"writes its output to <code>{LOG_DIR}</code>; when it stops with an error, the end of that log shows below. "
            "The portal is the first icon; when a portal is already open it warns instead, as a second one would only "
            "show the open one. The last icons are the wikis in the checkout (each <code>mkdocs.yml</code>): each is "
            "served with <code>mkdocs serve</code> on a port of its own and opens in the browser with its design "
            "panel; it rebuilds on every save. With <b>Wikis on the network</b> they are served for the other devices "
            "too, on ports of their own; the addresses show below."))
        lay.addWidget(self.apps, 2)
        self.running: list[tuple[rp.Launch, subprocess.Popen, Path]] = []
        self.waiting: list[str] = []            # servers started, whose page opens once they answer
        self.timer = QTimer(self, interval=1000)
        self.timer.timeout.connect(self.poll)

    def fill(self, targets: list[rp.Launch]) -> None:
        if sys.platform.startswith("linux"):
            self.release_button.setToolTip(
                f"After GitHub built portal-v{self.release_window.portal_version()}: download it, check it against "
                "its SHA256SUMS, install it and start it (check-release.sh release)")
        self.apps.clear()
        for target in targets:
            icon = QIcon(str(target.icon)) if target.icon else QIcon()
            item = QListWidgetItem(board_badge(icon) if target.changes_board else icon, target.label)
            item.setData(Qt.ItemDataRole.UserRole, target)
            item.setToolTip(("\u26a0 Changes how the board runs: it asks first.\n" if target.changes_board else "") +
                            " ".join(("python -m", target.module, *target.args)) + f" in {target.folder}" +
                            (f"\nopens {target.url}" if target.url else ""))
            self.apps.addItem(item)

    def check(self, test: str) -> None:
        """Run check-release.sh in a terminal: it installs a portal and keeps it running there."""
        script = shlex.quote(str(self.release_window.root / rp.CHECK_SCRIPT))
        mode = "release" if test == "release" else "local"
        try:
            self.release_window.launch(f"{script} {mode}")
        except RuntimeError as exc:
            self.output.appendPlainText(str(exc))
            return
        self.output.appendPlainText({
            "local": "A terminal installs the portal from this checkout, then starts it with --source release. "
                     "Close the portal there to finish.",
            "release": f"A terminal installs the published portal-v{self.release_window.portal_version()} release, "
                       "then starts it. Close the portal there to finish.",
            "withdrawal": "A terminal installs the portal from this checkout and starts it. With the app installed, "
                          "the portal says it is not available any more and removes it; its tile then shows \"App not "
                          "available\". Close the portal there to finish."}[test])

    def installer_tests(self) -> None:
        target = rp.installer_tests_target(self.release_window.root)
        if target is None:
            self.output.appendPlainText("This checkout has no tools/installer-tests/gui.")
            return
        self.run(target)

    def close_issues(self) -> None:
        dialog = IssuesDialog(self, self.release_window.issues_source)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.run_close(dialog.numbers(), dialog.comment.text())

    def run_close(self, numbers: list[int], comment: str) -> None:
        """gh issue close for each ticked issue, in the Commands tab, as the git buttons run."""
        if not numbers:
            return
        if self.release_window.commands.run_now(rp.close_issues_command(numbers, comment)):
            self.release_window.tabs.setCurrentIndex(self.release_window.commands_tab)
        else:
            self.output.appendPlainText("Close issues: the command line is busy or has no bash; nothing was closed.")

    def tour_file(self) -> Path:
        return Path.home() / "Videos" / f"bc250-portal-tour-v{self.release_window.portal_version()}.mp4"

    def record_tour(self) -> None:
        """tools/record-tour.sh in the background, its output in Logs; the video opens when it is done."""
        script = self.release_window.root / rp.RECORD_SCRIPT
        if not script.is_file():
            self.output.appendPlainText(f"This checkout has no {rp.RECORD_SCRIPT}.")
            return
        if self.recorder is not None:
            return
        out = self.tour_file()
        self.recorder = QProcess(self)
        self.recorder.setWorkingDirectory(str(self.release_window.root))
        self.recorder.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.recorder.readyReadStandardOutput.connect(self._recorder_output)
        self.recorder.finished.connect(lambda code, _status: self._recorded(code, out))
        self.tour_button.setEnabled(False)
        self.output.appendPlainText(f"$ {rp.RECORD_SCRIPT} {out}")
        self.release_window._show_log(self)
        self.recorder.start("bash", [str(script), str(out)])

    def _recorder_output(self) -> None:
        if self.recorder is not None:
            text = bytes(self.recorder.readAllStandardOutput()).decode(errors="replace").rstrip("\n")
            if text:
                self.output.appendPlainText(text)

    def _recorded(self, code: int, out: Path) -> None:
        self._recorder_output()
        self.recorder.deleteLater()
        self.recorder = None
        self.tour_button.setEnabled(True)
        if code == 0 and out.is_file():
            self.output.appendPlainText(f"The portal tour is in {out}; it opens in your video player.")
            open_url(QUrl.fromLocalFile(str(out)).toString())
        else:
            self.output.appendPlainText(f"Recording the portal tour stopped with exit code {code}; see above.")

    def run(self, target: rp.Launch) -> None:
        if target.changes_board and QMessageBox.question(
                self, "Local app test",
                f"{target.name} changes how the board runs. Like every app of the suite it is software-only and "
                f"reversible; started from the checkout it uses the scripts in {target.folder}.\n\nStart it?") \
                != QMessageBox.StandardButton.Yes:
            return
        if target.app_id and instance_running(target.app_id):
            QMessageBox.warning(
                self, "Local app test",
                f"{target.name} is already open (the installed one, or one started here).\n\nA second one never "
                "opens: starting it again only brings the open window to the front, so the checkout would not be "
                f"tested. Close {target.name} first, then click its icon again.")
            return
        if target.url and answers(target.url):
            # Already up (started here or before): mkdocs would only fail on the taken port.
            open_url(target.url)
            self.output.appendPlainText(f"{target.label} is already running: opened {target.url}" +
                                        (f"\n{target.note}" if target.note else ""))
            return
        command, env = rp.launch_command(self.release_window.root, target)
        log = LOG_DIR / target.log_name
        try:
            process = self.release_window.start(command, env, target.folder, log)
        except OSError as exc:
            self.output.appendPlainText(f"{target.label}: could not start ({exc})")
            return
        self.running.append((target, process, log))
        if target.url:
            self.waiting.append(target.url)
        self.timer.start()
        self.output.appendPlainText(f"{target.label} started from {target.folder} (log: {log})" +
                                    (f"; {target.url} opens once it is up" if target.url else "") +
                                    (f"\n{target.note}" if target.note else ""))

    def poll(self) -> None:
        for entry in list(self.running):
            target, process, log = entry
            code = process.poll()
            if code is None:
                if target.url in self.waiting and answers(target.url):
                    self.waiting.remove(target.url)
                    open_url(target.url)
                continue
            self.running.remove(entry)
            if target.url in self.waiting:
                self.waiting.remove(target.url)
            if code == 0:
                self.output.appendPlainText(f"{target.label} closed.")
            else:
                tail = log_tail(log)
                self.output.appendPlainText(f"{target.label} stopped with exit code {code}" +
                                        (f"; the end of {log}:\n{tail}" if tail else "."))
        if not self.running:
            self.timer.stop()


class IssuesDialog(QDialog):
    """The open issues on GitHub, read in the background (plan.fetch_open_issues), each with a tick box; Run closes
    the ticked ones."""

    def __init__(self, parent: QWidget, source):
        super().__init__(parent)
        self.setWindowTitle("Close issues")
        self.resize(640, 420)
        self.state = QLabel("Reading the open issues on GitHub…")
        self.state.setWordWrap(True)
        self.list = QListWidget()
        self.list.itemChanged.connect(self._show_state)
        self.list.itemDoubleClicked.connect(lambda item: open_url(item.data(Qt.ItemDataRole.UserRole + 1)))
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
            "Tick the issues that are handled and press <b>Run</b>: it closes them with <code>gh issue close</code> "
            "in the Commands tab, with the comment when you write one. A double click opens an issue on GitHub. "
            "The weekly Upstream review and Backlog review open a new issue when they have something again."))
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


def desktop_notify(summary: str, body: str) -> bool:
    """A desktop notification through notify-send; False when the desktop has none."""
    exe = shutil.which("notify-send")
    if not exe:
        return False
    ok, _pid = QProcess.startDetached(exe, ["--app-name", APP_NAME, "--icon", str(LOGO_PATH), summary, body])
    return ok


BUILD_BUSY_MS = 30_000                  # how often to look while a build runs
BUILD_IDLE_MS = 300_000                 # and otherwise (unchanged answers do not count against GitHub's limit)
BUILD_LOOK = {"running": (BLUE, "Building"), "passed": (GREEN, "Passed"), "failed": (RED, "Failed"),
              "": (GREY, "No builds")}
RELEASE_TEXT = {"": "no run seen", "running": "building\u2026", "passed": "ready", "failed": "failed"}
RELEASE_TIP = {"": "GitHub shows no release run on {tag} among its newest runs: is the tag pushed?",
               "running": "GitHub's release workflow is building {tag}; Pin waits for it, and a notification "
                          "comes when it is ready",
               "passed": "GitHub published {tag}: Pin reads its checksum",
               "failed": "GitHub's release workflow failed on {tag}: click GitHub in the header to open the run"}


class BuildIndicator(Pill):
    """Whether GitHub built the newest push: CI, Release and Manual on its commit. Looks every 30 s while a build
    runs and every 5 minutes otherwise; a run seen running that finishes gives a desktop notification, and so does
    the release of an app waiting to be pinned, seen running or not (each once), and the portal's release. A
    click opens the run that failed (or still runs), else the Actions page. When GitHub's hourly limit is used up
    it says until when and waits till then. Requests carry the token of a gh login when there is one
    (plan.github_token)."""

    def __init__(self, window: "ReleaseWindow", source, notify):
        super().__init__("—", "GitHub build")
        self.release_window = window
        self.source = source            # rp.fetch_runs: (runs | None when unchanged, etag)
        self.notify = notify
        self.etag = ""
        self.runs: list[rp.BuildRun] = []
        self.seen: dict[str, rp.BuildRun] = {}
        self.announced: set[str] = set()        # the Release runs told about, by url
        self.clicked.connect(self.open)
        self.checker = UpdateChecker(self)
        self.checker.finished.connect(self.checked)
        self.timer = QTimer(self, singleShot=True)
        self.timer.timeout.connect(self.check)
        self.rate = MetricBox("GitHub API left")    # GitHub's hourly limit: placed beside it by the window
        self.rate.setVisible(source is not None)
        self.show_state("", "Not looked yet.")
        self.show_rate(None)
        self.setVisible(source is not None)

    def check(self) -> None:
        if self.source is None:
            return
        etag = self.etag
        self.checker.start(lambda: self._fetch(etag))

    def _fetch(self, etag: str) -> object:
        """Worker thread: the runs, or the error to show."""
        try:
            return self.source(etag)
        except (OSError, ValueError) as exc:
            return exc

    def checked(self, result: object) -> None:
        if isinstance(result, rp.RateLimited):
            self.show_rate(result.rate)
            back = time.strftime("%H:%M", time.localtime(result.reset))
            hint = "" if result.signed_in else \
                "\n\nSigned in with gh (gh auth login), GitHub allows 5,000 requests an hour instead of 60."
            self.show_state("", f"{result}; looking again then.{hint}", limited=back)
            self.timer.start(max(BUILD_IDLE_MS, int((result.reset - time.time()) * 1000) + 5_000))
            return
        if isinstance(result, Exception):
            self.show_state("", f"GitHub could not be reached: {result}", unreachable=True)
            self.timer.start(BUILD_IDLE_MS)
            return
        runs, self.etag, *rate = result         # the limit as a third value (rp.fetch_runs); tests may leave it out
        if rate:
            self.show_rate(rate[0])
        finished: list[rp.BuildRun] = []
        if runs is not None:
            finished = rp.just_finished(self.seen, runs)
            self.runs, self.seen = runs, {r.url: r for r in runs}
        # The releases waited for (apps to pin, the portal) are told once each, seen running or not; a portal
        # release counts when it was seen running, as every older portal tag has a finished run too.
        page = self.release_window.portal_page
        waiting = page.waiting_tags()
        portal = page.portal_unit
        if portal is not None and portal.released and any(r.ref == portal.tag for r in finished):
            waiting.append(portal.tag)
        releases = rp.finished_releases(self.announced, self.runs, waiting)
        self.announced.update(r.url for r in releases)
        others = [r for r in finished if r not in releases]
        if others:
            self.announce(others)
        for release in releases:
            self.announce_release(release, pin=release.ref != (portal.tag if portal else ""))
        page.show_builds()
        latest = rp.latest_push(self.runs)
        state = rp.build_state(latest)
        self.show_state(state, self.details(latest))
        running = any(not r.done for r in self.runs)
        self.timer.start(BUILD_BUSY_MS if running else BUILD_IDLE_MS)

    def details(self, latest: list[rp.BuildRun]) -> str:
        if not latest:
            return "No workflow runs on GitHub."
        head = f"{latest[0].sha[:7]} {latest[0].title}"
        return "\n".join([head, *(f"{r.label}: {r.outcome}" for r in latest), "", "Click to open it on GitHub."])

    def show_state(self, state: str, tooltip: str, unreachable: bool = False, limited: str = "") -> None:
        if limited:
            color, text, self.state = ORANGE, "Limited", "limited"
            tooltip = f"GitHub's limit is reached, back at {limited}.\n\n{tooltip}"
        else:
            color, text = (GREY, "Offline") if unreachable else BUILD_LOOK[state]
            self.state = "unreachable" if unreachable else state
        self.set_colour(color)
        self.set_value(text, tooltip)

    def show_rate(self, rate: "rp.RateInfo | None") -> None:
        """How many of GitHub's requests are left this hour: none left is GitHub's limit, not a fault here."""
        if rate is None:
            value, color, now = "—", GREY, "The limit is not known yet."
        else:
            value, now = f"{rate.remaining:,}", f"{rate.text}."
            color = RED if rate.remaining == 0 else ORANGE if rate.remaining < rate.limit / 10 else GREEN
        sign_in = "" if rate is not None and rate.signed_in else \
            " Signed in with gh (gh auth login), it is 5,000 an hour instead of 60."
        self.rate.set_colour(color)
        self.rate.set_value(value, f"{now}\n\n"
            "GitHub's API answers a limited number of requests an hour; answers that did not change since the last "
            "look do not count. The limit is shared by everything on this network that asks GitHub without signing "
            f"in.{sign_in} When none are left, nothing is broken: GitHub answers again after the time shown.")

    def announce(self, finished: list[rp.BuildRun]) -> None:
        failed = [r for r in finished if not r.passed]
        summary = f"GitHub build {'failed' if failed else 'passed'}"
        body = "\n".join(f"{r.label}: {r.outcome}" for r in (failed or finished))
        self.notify(summary, body)
        QApplication.alert(self.release_window)

    def announce_release(self, release: rp.BuildRun, pin: bool) -> None:
        """A release step 2 waits for has finished: an app's, ready to pin, or the portal's, ready to test."""
        if release.passed:
            summary = f"{release.ref} is ready" + (" to pin" if pin else "")
            body = "GitHub published it. " + ("Pin reads its checksum (step 2)." if pin else
                                              "Test Portal release installs it on this board (step 2).")
        else:
            summary = f"{release.ref}: release failed"
            body = f"GitHub's release workflow ended with {release.outcome}: click GitHub in the header to open it."
        self.notify(summary, body)
        QApplication.alert(self.release_window)

    def target(self) -> str:
        latest = rp.latest_push(self.runs)
        pick = next((r for r in latest if r.done and not r.passed), None) or \
            next((r for r in latest if not r.done), None)
        return pick.url if pick else rp.ACTIONS_URL.format(repo_url=rp.pin_app.REPO_URL)

    def open(self) -> None:
        QDesktopServices.openUrl(QUrl(self.target()))

    def stop(self) -> None:
        self.timer.stop()
        self.checker.stop(2000)


class GitHubStatusIndicator(Pill):
    """GitHub status: green while githubstatus.com reports every part of GitHub working, red while it
    reports a problem (a build that waits in "queued" may be GitHub's), gray while it is not known. Looks every 5
    minutes; a click opens the status page."""

    def __init__(self, source):
        super().__init__("—", "GitHub status")
        self.source = source            # rp.fetch_github_status
        self.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(rp.STATUS_PAGE)))
        self.checker = UpdateChecker(self)
        self.checker.finished.connect(self.checked)
        self.timer = QTimer(self, singleShot=True)
        self.timer.timeout.connect(self.check)
        self.show_state("", "Not looked yet.")
        self.setVisible(source is not None)

    def check(self) -> None:
        if self.source is not None:
            self.checker.start(self._fetch)

    def _fetch(self) -> object:
        """Worker thread: the status, or the error to show."""
        try:
            return self.source()
        except (OSError, ValueError) as exc:
            return exc

    def checked(self, result: object) -> None:
        self.timer.start(BUILD_IDLE_MS)
        if isinstance(result, Exception):
            self.show_state("", f"githubstatus.com could not be reached: {result}")
            return
        lines = [result.description or "No status given.", *result.incidents, *result.affected]
        self.show_state("up" if result.up else "down", "\n".join(lines))

    def show_state(self, state: str, details: str) -> None:
        self.state = state
        self.set_colour({"up": GREEN, "down": RED}.get(state, GREY))
        self.set_value({"up": "Up", "down": "Problem"}.get(state, "Unknown"),
                       f"{details}\n\nClick to open {rp.STATUS_PAGE}")

    def stop(self) -> None:
        self.timer.stop()
        self.checker.stop(2000)


class ClaudeUsageIndicator(Pill):
    """Claude tokens today: what Claude Code on this machine used since midnight, read from its own transcripts
    (plan.fetch_claude_usage), blue once known; the tooltip adds the last 5 hours (Claude's usage window), the kinds
    and the models. Hidden without Claude Code here. Looks every 5 minutes; a click opens Claude's usage page, which
    shows the plan's limits (they are not on this machine)."""

    def __init__(self, source):
        super().__init__("\u2014", "Claude tokens today")
        self.source = source            # rp.fetch_claude_usage: (today, last 5 hours) | None
        self.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(rp.CLAUDE_USAGE_PAGE)))
        self.checker = UpdateChecker(self)
        self.checker.finished.connect(self.checked)
        self.timer = QTimer(self, singleShot=True)
        self.timer.timeout.connect(self.check)
        self.set_value("\u2014", f"Not looked yet.\n\nClick to open {rp.CLAUDE_USAGE_PAGE}")
        self.setVisible(source is not None)

    def check(self) -> None:
        if self.source is not None:
            self.checker.start(self._fetch)

    def _fetch(self) -> object:
        """Worker thread: the usage, None without Claude Code, or the error to show."""
        try:
            return self.source()
        except (OSError, ValueError) as exc:
            return exc

    def checked(self, result: object) -> None:
        self.timer.start(BUILD_IDLE_MS)
        if result is None:
            self.setVisible(False)
            return
        if isinstance(result, Exception):
            self.set_colour(GREY)
            self.set_value("\u2014", f"Claude Code's transcripts could not be read: {result}")
            return
        today, recent = result
        self.set_colour(BLUE)
        self.set_value(rp.short_count(today.total), "\n".join([
            f"Today: {today.total:,} tokens in {today.messages:,} answers.",
            f"Last 5 hours: {recent.total:,} tokens in {recent.messages:,} answers.", "",
            f"Input {today.input:,}, output {today.output:,}, cache written {today.cache_write:,}, "
            f"cache read {today.cache_read:,}.",
            *(f"{model}: {tokens:,}" for model, tokens in today.models), "",
            "Claude Code on this machine, from its transcripts; other machines and claude.ai are not in it.",
            f"Click to open {rp.CLAUDE_USAGE_PAGE} for the plan's limits."]))

    def stop(self) -> None:
        self.timer.stop()
        self.checker.stop(2000)


class ReleaseWindow(QMainWindow):
    def __init__(self, root: Path = SUITE, sha256_source=rp.fetch_sha256, launch=launch_in_terminal,
                 start=start_app, runs_source=rp.fetch_runs, notify=desktop_notify, settings=None,
                 status_source=rp.fetch_github_status, claude_source=rp.fetch_claude_usage,
                 issues_source=rp.fetch_open_issues):
        """*runs_source* reads the GitHub Actions runs (None: no build indicator); *notify* shows a desktop
        notification; *settings* keeps the command line's history (None: this session only); *status_source*
        reads githubstatus.com (None: no GitHub status); *claude_source* reads Claude Code's usage (None: no
        Claude pill); *issues_source* reads the open GitHub issues for Close issues."""
        super().__init__()
        self.root = root
        self.issues_source = issues_source
        self.sha256_source = sha256_source
        self.launch = launch
        self.start = start
        self.units: list[rp.Unit] = []
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 760)
        self.setStyleSheet(SELECTION_STYLESHEET)
        stamp = rp.checkout_stamp(root)                 # never released: the commit says which code runs
        header = AppHeader(LOGO_PATH, APP_NAME, f"{__version__} · {stamp}" if stamp else __version__)
        # The header's pills, all as wide as the widest (owner, 20-10-2026).
        self.refresh_pill = Pill("Refresh", "Click to refresh", "Read the checkout and its tags again, for changes "
                                 "made in a terminal; what you entered stays")
        self.refresh_pill.clicked.connect(self.refresh)
        self.status = MetricBox("Working tree")    # clean or changed
        self.build = BuildIndicator(self, runs_source, notify)
        self.github_status = GitHubStatusIndicator(status_source)
        self.claude = ClaudeUsageIndicator(claude_source)
        pills = [self.refresh_pill, self.status, self.build, self.build.rate, self.github_status, self.claude]
        for pill in pills:
            header.add_second(pill)
        same_width(pills)
        header.second_row.addStretch(1)
        self.tabs = QTabWidget()
        self.apps_page = AppsPage(self)
        self.portal_page = PortalPage(self)
        self.tabs.addTab(self.apps_page, "1. Release apps")
        self.tabs.addTab(self.portal_page, "2. Pin and release Portal")
        self.withdraw_page = WithdrawPage(self)
        self.tabs.addTab(self.withdraw_page, "3. Retract app")
        self.run_page = RunPage(self)
        self.tabs.addTab(self.run_page, "Test on this board")
        # Opening step 2 reads the tags again, so tags pushed from a terminal meanwhile show up; step 1 keeps what
        # was typed in it.
        self.tabs.currentChanged.connect(lambda i: i == 1 and self.portal_page.fill(rp.load_units(self.root)))
        self.commands = CommandLine(root, settings, finished=self.refresh)    # a commit or push: read it again
        # The logs are tabs of their own, each the whole tab area (owner, 17-10-2026: boxes under the steps were
        # too flat to read). Logs shows the log of the step last open (what Apply, Pin, Bump portal, Retract or
        # a started app wrote); a step that writes its log opens it. Commands is the command line with its output.
        self.step_pages = (self.apps_page, self.portal_page, self.withdraw_page, self.run_page)
        self.outputs = QStackedWidget()
        for page in self.step_pages:
            self.outputs.addWidget(page.output)
        self.log_tab = self.tabs.addTab(self.outputs, "Logs")
        self.commands_tab = self.tabs.addTab(self.commands, "Commands")
        self.tabs.setTabToolTip(self.log_tab, "The log of the step last open: what Apply, Pin, Bump portal, Retract "
                                              "or a test on this board wrote")
        self.tabs.setTabToolTip(self.commands_tab, "The command line: runs a command in the checkout and shows its "
                                                   "output; Commands offers what the last step showed")
        self.tabs.currentChanged.connect(self._tab_changed)
        for page in self.step_pages[:3]:                 # not Test on this board: its lines come while you click
            page.output.textChanged.connect(lambda page=page: self._show_log(page))
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(header)
        self.bad_tags = QLabel()
        self.bad_tags.setWordWrap(True)
        self.bad_tags.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.bad_tags.setStyleSheet("color:#c62828; font-weight:600;")
        lay.addWidget(self.bad_tags)
        lay.addWidget(self.tabs, 1)
        lay.addLayout(self._git_row())
        version = QLabel(f"{APP_NAME} {__version__} · edits {self.root}")
        version.setStyleSheet("color:palette(placeholder-text);")
        lay.addWidget(version, 0, Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(central)
        self.reload()
        self.build.check()
        self.github_status.check()
        self.claude.check()

    def _git_row(self) -> QHBoxLayout:
        """git add, git commit, git push and git tag as buttons, each with its checks (owner, 19-10-2026: no commands
        to type or copy; git tag, owner, 20-10-2026). They run in the command line, whose output opens."""
        self.add_button = QPushButton("git add")
        self.add_button.setToolTip(f"{rp.add_command()}\n\nStages every change and new file, sets the exec bits CI "
                                   "checks and lists what is staged")
        self.add_button.clicked.connect(lambda: self.run_git(rp.add_command()))
        self.commit_message = QLineEdit()
        self.commit_message.setPlaceholderText("Commit message (Apply and Bump portal fill it in)")
        self.amend_box = QCheckBox("Amend")
        self.amend_box.setToolTip("Add the staged changes to the last commit, with its message: only for a commit "
                                  "that is not pushed yet")
        self.amend_box.toggled.connect(self._show_git_state)
        self.commit_message.textChanged.connect(self._show_git_state)
        self.commit_button = QPushButton("git commit")
        self.commit_button.clicked.connect(self.commit)
        self.push_button = QPushButton("git push")
        self.push_button.clicked.connect(self.push)
        self.tag_button = QPushButton("git tag")
        self.tag_button.clicked.connect(self.tag)
        self.git_state = (False, False, 0)
        self.committing = False                 # the commit button's command runs: its message goes when it passes
        row = QHBoxLayout()
        row.addWidget(self.add_button)
        row.addWidget(self.commit_message, 1)
        row.addWidget(self.amend_box)
        row.addWidget(self.commit_button)
        row.addWidget(self.push_button)
        row.addWidget(self.tag_button)
        return row

    def tags_to_push(self) -> list[str]:
        """What git tag tags: the portal's release on step 2's tab (once its VERSION has no tag), else step 1's app
        releases that have none yet."""
        if self.tabs.currentWidget() is self.portal_page:
            portal = self.portal_page.portal_unit
            return [portal.tag] if portal is not None and not portal.released else []
        return rp.untagged_releases(self.units)

    def offer(self, commands: str) -> None:
        """A step showed the commands to run next: the Commands menu lists them, and their commit's message (or
        amend) goes into the git row."""
        self.commands.offer(commands)
        message, amend = rp.commit_message(commands)
        if message or amend:
            self.commit_message.setText(message)
            self.amend_box.setChecked(amend)

    def run_git(self, command: str) -> None:
        if self.commands.run_now(command):
            self.tabs.setCurrentIndex(self.commands_tab)
        self._show_git_state()

    def confirm_git(self, title: str, what: str, command: str) -> bool:
        """Push and tag reach GitHub: they ask first, with the command and what it sends, and say when the token on
        this machine reaches more than this repository."""
        warning = rp.token_warning(rp.github_token())
        text = f"{what}\n\n{command}" + (f"\n\n\u26a0 {warning}" if warning else "") + "\n\nGo ahead?"
        return QMessageBox.question(self, title, text) == QMessageBox.StandardButton.Yes

    def push(self) -> None:
        commits = (rp.git(self.root, "log", "--oneline", f"{self.base()}..HEAD") or "").strip()
        if self.confirm_git("git push", f"Push to GitHub:\n\n{commits}", rp.push_command()):
            self.run_git(rp.push_command())

    def tag(self) -> None:
        tags = self.tags_to_push()
        if self.confirm_git("git tag", "Tag and push these releases; GitHub then builds and publishes them:\n\n"
                            + "\n".join(tags),
                            rp.tag_command(tags)):
            self.run_git(rp.tag_command(tags))

    def commit(self) -> None:
        amend = self.amend_box.isChecked()
        message = self.commit_message.text().strip()
        if not message and not amend:
            return
        self.committing = True
        self.run_git(rp.commit_command(message, self.base(), amend, shlex.quote(sys.executable)))

    def _show_git_state(self) -> None:
        """Each button only when it has something to do, and none while a command runs."""
        unstaged, staged, ahead = self.git_state
        idle = not self.commands.is_running() and bool(self.commands.bash)
        amend = self.amend_box.isChecked()
        message = self.commit_message.text().strip()
        self.add_button.setEnabled(idle and unstaged)
        if amend:                               # a pushed commit is never amended: its push would need --force
            why = "" if ahead else f"The last commit is pushed already ({self.base()}): commit without Amend."
        else:
            why = "Nothing is staged: git add first." if not staged else \
                "" if message else "Type a commit message first."
        self.commit_button.setEnabled(idle and not why)
        self.commit_button.setToolTip(rp.commit_command(message or "<message>", self.base(), amend) + "\n\n" + (
            why or "Runs check_versions.py and check_manifest.py first and commits only when they pass"))
        self.push_button.setEnabled(idle and ahead > 0)
        linux = sys.platform.startswith("linux")
        self.push_button.setToolTip(rp.push_command() + "\n\n" + (
            f"Nothing to push: HEAD is at {self.base()}." if ahead == 0 else
            f"{ahead} commit{'s' if ahead != 1 else ''} to push. " +
            ("Runs CI's jobs here first (tools/ci-local.sh) and pushes only when they pass." if linux else
             "CI's jobs run on GitHub.")))
        tags = self.tags_to_push()
        what = "the portal" if self.tabs.currentWidget() is self.portal_page else "step 1's apps"
        why = f"Nothing to tag: every release of {what} has its tag." if not tags else \
            "Push first: a tag goes only on a pushed commit." if ahead else ""
        self.tag_button.setEnabled(idle and not why)
        self.tag_button.setToolTip((rp.tag_command(tags) if tags else rp.TAG_SCRIPT) + "\n\n" + (
            why or "Tags the releases and pushes the tags once CI passed on HEAD on GitHub (it waits while CI runs); "
                   "GitHub then builds the releases"))

    def _tab_changed(self, index: int) -> None:
        """A step opened: Logs shows that step's log from now on (a log tab opened leaves it as it is)."""
        if index < len(self.step_pages):
            self.outputs.setCurrentIndex(index)
        self._show_git_state()                  # git tag tags what the open step releases

    def _show_log(self, page: QWidget) -> None:
        """The open step wrote its log: show it in Logs, the whole window wide."""
        if self.tabs.currentWidget() is page and page.output.toPlainText().strip():
            self.outputs.setCurrentWidget(page.output)
            self.tabs.setCurrentIndex(self.log_tab)

    def base(self) -> str:
        return self.portal_page.base_edit.text().strip() or "origin/main"

    def portal_version(self) -> str:
        return (rp.suite_dir(self.root) / "portal" / "VERSION").read_text(encoding="utf-8").strip()

    def refresh(self) -> None:
        """reload(), keeping what was entered: step 1's ticks, versions and notes, step 2's portal version (if it
        is not the one offered) and notes."""
        typed = self.apps_page.typed()
        combo = self.portal_page.portal_version
        version = None if combo.currentText() == combo.itemText(0) else combo.currentText()
        notes = self.portal_page.portal_notes.text()
        self.reload()
        self.apps_page.restore(typed)
        if version is not None:
            combo.setEditText(version)
        self.portal_page.portal_notes.setText(notes)
        if self.committing and not self.commands.is_running():
            self.committing = False
            if self.commands.last_code == 0:
                self.commit_message.clear()
                self.amend_box.setChecked(False)
        self.build.check()                      # a push from a terminal: its build
        self.github_status.check()
        self.claude.check()

    def reload(self) -> None:
        units = self.units = rp.load_units(self.root)
        self.apps_page.fill(units)
        self.portal_page.fill(units)
        self.withdraw_page.fill(units)
        portal = rp.portal_target(self.root)
        docs = rp.docs_targets(self.root, network=self.run_page.network_box.isChecked())
        self.run_page.fill(([portal] if portal else []) + rp.launch_targets(self.root) + docs)
        problems = rp.bad_tags(self.root, units)
        self.bad_tags.setText("\n".join(
            f"\u26a0 {p}: release.yml cannot build it. Delete it (git tag -d {p.split()[0]} && git push origin "
            f":refs/tags/{p.split()[0]}), commit and push the bump, then tag again with {rp.TAG_SCRIPT} "
            f"{p.split()[0]}." for p in problems))
        self.bad_tags.setVisible(bool(problems))
        dirty = rp.git(self.root, "status", "--porcelain")
        self.status.set_colour(ORANGE if dirty else GREEN if dirty is not None else GREY)
        self.status.set_value("Changed" if dirty else "Clean" if dirty is not None else "No git",
                              "The working tree has changes." if dirty else "The working tree is clean."
                              if dirty is not None else "This folder is not a git checkout.")
        self.git_state = rp.git_state(self.root, self.base())
        self._show_git_state()

    def closeEvent(self, event) -> None:
        self.build.stop()
        self.github_status.stop()
        self.claude.stop()
        self.commands.shutdown()
        recorder = self.run_page.recorder
        if recorder is not None:                         # a tour being recorded: stopped, not left half-written
            recorder.finished.disconnect()
            recorder.kill()
            recorder.waitForFinished(3000)
        super().closeEvent(event)
