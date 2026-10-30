# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: enter the new versions, and it edits the files of a release (plan.py) of the suite ticked in the
first column (every suite in the checkout, tools/suites.py, with its portal's tag; hidden while there is one). The
steps, the pins and the board tests are the ticked suite's; the git buttons, the wikis and GitHub are the repository's.

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
what Claude Code on this machine used, from its transcripts; a click opens Claude's usage page. Under the pills, the
ticker says where the newest push's workflow runs stand: the job that runs and its step (owner, 28-10-2026).
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
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                             QLineEdit, QListView,
                             QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSizePolicy,
                             QStackedWidget, QSystemTrayIcon, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
                             QWidget)

from bc250_core.instance import server_name
from bc250_core.platform import launch_in_terminal
from bc250_core.theme import BLUE, GREEN, GREY, ORANGE, RED
from bc250_core.updates import UpdateChecker
from bc250_core.widgets import AppHeader, MetricBox, Pill, Terminal, accent_button, hint_label, same_width

from . import APP_NAME, LOGO_PATH, CHECKOUT, __version__
from . import plan as rp
from .command_line import CommandLine
from .release_page import ReleasePage
from .style import CHECK_STYLESHEET, NEXUS, TAB_TITLE_STYLESHEET, TEAL

COLUMNS = ("Release", "App", "VERSION", "Last tag", "Needs release", "New version", "Notes")
SUITE_KEY = "suite"                     # the chosen suite, in the settings
VERSION_FIELD_PX = 130                  # the portal version field: a version like 10.1.0 and room to type
SEMVER_TIP = ("Breaking. (an entry that starts with it) -> major: something removed or no longer working as "
              "before. Added. -> minor: a new feature. Fixed. -> patch: a bug or security fix.")
LOG_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "nexus-release-tool" / "run"
COMMAND_LOG_DIR = LOG_DIR.parent / "commands"   # every command line's output, a file a day (command_line.py)
# A selected cell and the input field being typed in: a teal outline (Nexus's accent) with rounded corners on a
# transparent background, not the desktop's solid highlight. The line edit inside an editable combo box keeps the
# combo's frame. The tables' grid lines are the thin dimmed-silver edge of the theme, as the border around a table
# (owner, 26-10-2026: Qt's own lines were brighter and heavier).
SELECTION_STYLESHEET = (
    "QTableWidget { outline:0; selection-background-color:transparent; selection-color:palette(text); "
    f"gridline-color:{NEXUS.edge}; }}"
    "QTableWidget::item { border:2px solid transparent; border-radius:6px; }"
    f"QTableWidget::item:selected {{ background:transparent; color:palette(text); border-color:{NEXUS.accent}; }}"
    f"QLineEdit:focus {{ background:transparent; border:2px solid {NEXUS.accent}; border-radius:6px; }}"
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
    if unit.kind == rp.NEXUS:
        text = ("Nexus's own version: the root VERSION, with a \"Release x.y.z.\" entry in the root CHANGELOG. Not "
                "tagged here: once the push is on main, GitHub's Latest release (the Nexus index) becomes "
                f"{unit.tag_head}<VERSION>.\n\n")
        if not unit.released_as:
            return text + "Never released."
        if not unit.changed:
            return text + f"No CHANGELOG entries since Release {unit.released_as}."
        entries = unit.changed[:25] + ([f"… and {len(unit.changed) - 25} more"] if len(unit.changed) > 25 else [])
        return text + f"CHANGELOG entries since Release {unit.released_as}:\n" + "\n".join(entries)
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
        # A pill in the window's header, beside Refresh (owner, 28-10-2026), greyed out once applied until something
        # new is to be applied
        self.apply_button = Pill("Apply", "New app releases", "Write the new versions and CHANGELOG entries of the "
                                 "ticked apps (step 1)", TEAL)
        self.apply_button.clicked.connect(self.apply_from_header)
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
            "apps and gets a version only, no tag. <b>nexus</b> is the repository's own version (the root VERSION and "
            "CHANGELOG): no tag either, its push makes GitHub's Latest release nexus-v&lt;version&gt;. "
            "<b>Needs release</b> (orange): something the app ships (its "
            "folder without tests, the core it bundles, its manual chapter) differs from its last tag, committed or "
            "not; hover it for the files."))
        lay.addWidget(self.table, 2)
        row = QHBoxLayout()
        row.addWidget(self.tick_button)
        row.addStretch(1)
        lay.addLayout(row)
        self.rows: list[tuple[rp.Unit, QCheckBox, QComboBox, QLineEdit]] = []
        self.handled: set[tuple[str, str]] = set()  # (key, version) that needed a release when Apply was pressed

    def fill(self, units: list[rp.Unit]) -> None:
        shown = [u for u in units if u.kind != "portal"]
        self.table.setRowCount(len(shown))
        self.rows = []
        # The CHANGELOGs at the last tags, for the suggested versions: one git process for the table (owner,
        # 27-10-2026: one per row made the window slow on Windows).
        blobs = rp.read_blobs(self.release_window.root, rp.changelog_specs(shown))
        for i, unit in enumerate(shown):
            tick = QCheckBox()
            if unit.kind == "core" and unit.current:        # its version already covers it: nothing to write
                tick.setEnabled(False)
                tick.setToolTip(f"Core {unit.version} already holds every change since its last version; the app "
                                "releases carry it as it is")
            else:                                           # ticked from the start; untick what waits. After
                tick.setChecked(unit.needs_release           # Apply, not what was there then: what was left
                                and (unit.key, unit.version) not in self.handled)    # unticked waits
            self.table.setCellWidget(i, 0, tick)
            reason = unit.release_reason
            if unit.needs_release and unit.last_tag and not unit.released:
                reason += f" · {unit.version} not tagged yet"
            tip = needs_tooltip(unit)
            last = unit.last_tag or (f"{unit.tag_head}{unit.released_as}" if unit.released_as else "—")
            for col, text in ((1, unit.key), (2, unit.version), (3, last), (4, reason)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setToolTip(tip)
                if unit.needs_release:
                    item.setForeground(QColor(ORANGE))
                self.table.setItem(i, col, item)
            combo = QComboBox()
            combo.setEditable(True)
            choices, why = rp.version_choices(self.release_window.root, unit, blobs)
            combo.addItems(choices)
            combo.setToolTip(f"{choices[0]}: {why}.\n\n{SEMVER_TIP}")
            notes = QLineEdit()
            notes.setPlaceholderText("What this release brings (optional)")
            self.table.setCellWidget(i, 5, combo)
            self.table.setCellWidget(i, 6, notes)
            self.rows.append((unit, tick, combo, notes))
            tick.toggled.connect(lambda _on: self.enable_apply())
        # An app's release is a suite's release: the Nexus index lists it, so Nexus's number moves with it (owner,
        # 28-10-2026). Ticking an app ticks the nexus row; it can be unticked.
        nexus = next((tick for unit, tick, _, _ in self.rows if unit.kind == rp.NEXUS), None)
        if nexus is not None:
            for unit, tick, _, _ in self.rows:
                if unit.kind == "app":
                    tick.toggled.connect(lambda on, nexus=nexus: on and nexus.setChecked(True))
        self.enable_apply()

    def enable_apply(self) -> None:
        """Apply works while a ticked row has something to write: greyed out once it is applied (its "Release
        x.y.z." entry on top, the version not tagged yet), until a new release is to be applied (owner, 28-10-2026)."""
        root = self.release_window.root
        new = [u for u, tick, _, _ in self.rows if tick.isChecked() and not rp.applied(root, u)]
        self.apply_button.setEnabled(bool(new))
        self.apply_button.setToolTip("Write the new versions and CHANGELOG entries of the ticked apps" if new else
                                     "Applied: the ticked releases are written. It works again when another release "
                                     "is to be applied.")

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

    def apply_from_header(self) -> None:
        """Apply from the header: on step 1, where the ticks are and its log shows what it wrote."""
        self.release_window.tabs.setCurrentWidget(self)
        self.apply()

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
        root, suite = self.release_window.root, self.release_window.suite
        self.handled = {(u.key, u.version) for u, _, _, _ in self.rows if u.needs_release} | \
            {(u.key, new) for u, new, _ in picked}
        log, tags, pins_moved, nexus = [], [], [], ""
        # Nexus last: its entry names the suites' releases, the ones written here among them.
        picked.sort(key=lambda p: p[0].kind == rp.NEXUS)
        for unit, new, notes in picked:
            if unit.kind == rp.NEXUS:
                nexus = new
                notes = rp.nexus_notes(notes, rp.suite_releases(root))
            if new != unit.version:
                changed = rp.set_version(root, unit, new)
                log.append(f"{unit.key}: {new} in " + ", ".join(p.relative_to(root).as_posix() for p in changed))
            text = f"Version {new}." if unit.kind == "core" else rp.release_text(new, notes)
            if unit.kind == "core" and notes.strip():
                text += f" {notes.strip()}"
            rp.add_changelog_entry(root, unit, text, base=self.release_window.base())
            log.append(f"{unit.key}: CHANGELOG entry \"{text}\"")
            if unit.kind == "app":
                tags.append(unit.tag)
                if rp.follow_unreleased_pin(root, unit, suite):
                    pins_moved.append(unit.tag)
        if pins_moved:
            log.append(f"apps.toml: the never-released pins move along ({', '.join(pins_moved)}).")
        # apps.toml may also have changed before this release (an app added, removed or moved, a pin moved): CI
        # checks it against the last portal release, with the portal bump it needs. That bump is made here, so the push
        # passes CI as it is (the owner's release of 17-10-2026 was committed without it and failed ci-local); the
        # portal release itself is step 2, once the apps are pinned.
        base, portal_version = self.release_window.base(), self.release_window.portal_version()
        minimum, why = rp.portal_minimum(root, base, portal_version, suite)
        if minimum and minimum != portal_version:
            portal = next(u for u in rp.load_units(root, suite) if u.kind == "portal")
            changed = rp.set_version(root, portal, minimum)
            text = rp.portal_text(minimum, rp.changed_pins(root, base, suite), "",
                                  rp.changed_withdrawals(root, base, suite))
            rp.add_changelog_entry(root, portal, text, base=base)
            log.append(f"portal: {minimum} in " + ", ".join(p.relative_to(root).as_posix() for p in changed)
                       + f" and CHANGELOG entry \"{text}\": apps.toml changed since {base} ({why}), so CI needs this "
                       "bump in the same push. The portal release follows in step 2, once the apps are pinned.")
        log += ["", run_check(root, rp.VERSIONS_CHECK),
                run_check(root, rp.manifest_check(root, suite), "--base", base)]
        # Nexus's version is not tagged here: its push is enough (nexus-index.yml); with app releases it joins theirs.
        commands = rp.app_commands(tags) if tags else rp.nexus_commands(nexus) if nexus else ""
        if tags and nexus:
            commands += "\n" + rp.NEXUS_INDEX_NOTE.format(version=nexus)
        if commands:
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
        # Pin and Bump are ordinary buttons, as Retract and Run (owner, 29-10-2026: the pills were too big)
        self.pin_button = accent_button("Pin", "Read each ticked release's SHA256SUMS from GitHub and pin tag and "
                                        "sha256")
        self.pin_button.clicked.connect(lambda: self.pin())
        self.empty_note = hint_label("")
        self.minimum = QLabel()
        self.portal_needs = QLabel()
        self.portal_version = QComboBox()
        self.portal_version.setEditable(True)
        # Wide enough for a three-part version with room to type: the field's own width cut "10.1.0" off (owner,
        # 26-10-2026).
        self.portal_version.setMinimumWidth(VERSION_FIELD_PX)
        self.portal_notes = QLineEdit()
        self.portal_notes.setPlaceholderText("What this portal release brings (optional)")
        self.nexus_too = QCheckBox("Nexus too:")
        self.nexus_too.setToolTip("A portal release is a suite's release: the Nexus index (GitHub's Latest) lists it, "
                                  "so Bump portal bumps Nexus's version too, with a Release entry that says what the "
                                  "suites bring (owner, 28-10-2026)")
        self.nexus_version = QComboBox()
        self.nexus_version.setEditable(True)
        self.nexus_version.setMinimumWidth(VERSION_FIELD_PX)
        self.bump_button = accent_button("Bump", "Write portal/VERSION, its copies and the CHANGELOG entry (and "
                                         "Nexus's version with Nexus too)")
        self.bump_button.clicked.connect(lambda: self.bump())
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
        # Two lines, the portal's and Nexus's version, with the Bump button beside them (owner, 28-10-2026)
        versions = QGridLayout()
        versions.addWidget(QLabel("Portal version:"), 0, 0)
        versions.addWidget(self.portal_version, 0, 1)
        versions.addWidget(self.portal_notes, 0, 2)
        versions.addWidget(self.nexus_too, 1, 0)
        versions.addWidget(self.nexus_version, 1, 1)
        versions.setColumnStretch(2, 1)
        portal_row = QHBoxLayout()
        portal_row.addLayout(versions, 1)
        portal_row.addSpacing(12)
        portal_row.addWidget(self.bump_button, 0, Qt.AlignmentFlag.AlignVCenter)
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
            tick.toggled.connect(lambda _on: self.enable_pin())
        portal = next(u for u in units if u.kind == "portal")
        self.portal_unit = portal
        # Nothing to pin never holds the portal back: what apps.toml pins now is what it releases.
        self.empty_note.setText("" if cands else
                                "Nothing to pin: every app whose VERSION is tagged is already pinned with its checksum. "
                                "Tagged on another machine? Fetch tags. Not tagged yet? Do step 1, push, and push the "
                                "app tags first."
                                + (f" The portal can be released with the pins it has: {portal.tag} is not tagged yet "
                                   "(Bump portal when its version is not set yet, commit, push, git tag)."
                                   if not portal.released else ""))
        self.empty_note.setVisible(not cands)
        if portal.needs_release:
            self.portal_needs.setText(f"The portal needs a release: {portal.release_reason}"
                                      + (f" since {portal.last_tag}." if portal.last_tag else "."))
            self.portal_needs.setStyleSheet(f"color:{ORANGE}; font-weight:600;")
        else:
            self.portal_needs.setText(f"Nothing the portal ships changed since {portal.last_tag}.")
            self.portal_needs.setStyleSheet("")
        self.portal_needs.setToolTip(needs_tooltip(portal))
        minimum, why = rp.portal_minimum(self.release_window.root, self.release_window.base(), portal.version,
                                         self.release_window.suite)
        if minimum:
            self.minimum.setText(f"apps.toml changed since {self.release_window.base()} ({why}): the portal needs at least "
                                 f"{minimum}.")
        else:
            self.minimum.setText(f"apps.toml is unchanged since {self.release_window.base()}.")
        # The higher of what CI asks (since the last portal release) and what semantic versioning gives since it.
        suggested, semver = rp.portal_suggestion(self.release_window.root, portal, self.release_window.suite)
        if minimum and rp.version_tuple(minimum) > rp.version_tuple(suggested):
            suggested, semver = minimum, f"CI's minimum: {why}"
        choices = [suggested, *([] if portal.released else [portal.version]),
                   *rp.next_versions(portal.version).values()]
        choices = [v for i, v in enumerate(choices) if v not in choices[:i]
                   and not rp.check_new_version(portal.version, v, portal.released)]
        self.portal_version.clear()
        self.portal_version.addItems(choices)
        self.portal_version.setToolTip(f"{suggested}: {semver}.\n\n{SEMVER_TIP}")
        # Nexus with the portal: a suite's release is at least minor for it, a new suite major (owner, 28-10-2026).
        nexus = next((u for u in units if u.kind == rp.NEXUS), None)
        self.nexus_too.setVisible(nexus is not None and bool(nexus.released_as))
        self.nexus_version.setVisible(not self.nexus_too.isHidden())
        if not self.nexus_too.isHidden():
            choices, why = rp.version_choices(self.release_window.root, nexus)
            if not nexus.suite_releases:                # the portal bumped here is the suites' release then
                minor = rp.next_versions(nexus.version)["minor"]
                choices, why = [minor, *(c for c in choices if c != minor)], "minor: the portal's release"
            self.nexus_version.clear()
            self.nexus_version.addItems(choices)
            self.nexus_version.setToolTip(f"{choices[0]}: {why}.\n\n{SEMVER_TIP}")
            self.nexus_too.setChecked(True)
        self.show_builds()

    def waiting_tags(self) -> list[str]:
        """The app releases step 2 waits for: tagged, not pinned with their checksum yet."""
        return [unit.tag for unit, _tick in self.candidates if unit.released]

    def enable_pin(self) -> None:
        """Pin works once every ticked release is built: GitHub published it (owner, 28-10-2026: the releases to pin
        show from Apply on, Pin greyed out until they are built). Without GitHub's runs (offline, no source), once
        they are tagged."""
        ticked = [unit for unit, tick in self.candidates if tick.isChecked()]
        if self.release_window.build.source is None:
            ready = [u for u in ticked if u.released]
        else:
            ready = [u for u in ticked if rp.release_state(self.release_window.build.runs, u.tag) == "passed"]
        self.pin_button.setEnabled(bool(ticked) and len(ready) == len(ticked))

    def show_builds(self) -> None:
        """What GitHub shows for each release to pin and for the portal's own release (the header's indicator
        reads the runs; this is read from them, so it costs no request)."""
        runs = self.release_window.build.runs
        for i, (unit, _tick) in enumerate(self.candidates):
            state = rp.release_state(runs, unit.tag)
            item = QTableWidgetItem(RELEASE_TEXT[state])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setToolTip(RELEASE_TIP[state].format(tag=unit.tag))
            if not unit.released:
                item.setText("not tagged yet")
                item.setToolTip(f"{unit.tag} is not tagged yet: commit, push and tag step 1 ({rp.TAG_SCRIPT} "
                                f"{unit.tag}); GitHub then builds it, and Pin works once it is built")
            self.pins.setItem(i, 3, item)
        self.enable_pin()
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
            if not unit.released:
                log.append(f"{unit.tag}: not tagged yet, so GitHub has not built it: commit, push and tag step 1 "
                           f"({rp.TAG_SCRIPT} {unit.tag}). Not pinned.")
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
                rp.pin(self.release_window.root, unit, sha, self.release_window.suite)
            except SystemExit as exc:           # pin_app refuses (no such table, no tag line): say so, go on
                log.append(f"{unit.tag}: not pinned ({exc}).")
                continue
            log.append(f"{unit.tag}: pinned ({sha[:16]}…)")
        self.release_window.reload()
        self.output.set_text("\n".join(log) or "Tick a release to pin.")

    def bump(self) -> None:
        root, suite = self.release_window.root, self.release_window.suite
        units = rp.load_units(root, suite)
        portal = next(u for u in units if u.kind == "portal")
        new = self.portal_version.currentText().strip()
        problem = rp.check_new_version(portal.version, new, portal.released)
        if problem:
            QMessageBox.warning(self, "Bump portal", problem)
            return
        log = []
        if new != portal.version:
            changed = rp.set_version(root, portal, new)
            log.append(f"portal: {new} in " + ", ".join(p.relative_to(root).as_posix() for p in changed))
        pins = rp.changed_pins(root, self.release_window.base(), suite)
        withdrawn = rp.changed_withdrawals(root, self.release_window.base(), suite)
        text = rp.portal_text(new, pins, self.portal_notes.text(), withdrawn)
        rp.add_changelog_entry(root, portal, text, base=self.release_window.base())
        log.append(f"portal: CHANGELOG entry \"{text}\"")
        nexus = ""
        if not self.nexus_too.isHidden() and self.nexus_too.isChecked():
            nexus = self.nexus_version.currentText().strip()
            entry = rp.bump_nexus(root, nexus, base=self.release_window.base())
            log.append(f"nexus: {nexus}, CHANGELOG entry \"{entry}\": the Nexus index lists this portal, so its "
                       "number moves with it")
        log += ["",
                run_check(root, rp.VERSIONS_CHECK),
                run_check(root, rp.manifest_check(root, suite), "--base", self.release_window.base())]
        # Bumped before step 1's push (an app added, a pin moved): the bump goes into that push, with the app tags
        # after it; the portal release comes after Pin. Otherwise commit, test on a board, push and tag the portal.
        pending = rp.untagged_releases(units)
        if pending:
            amend = bool(rp.unpushed_release_commit(root, self.release_window.base()))
            commands = rp.app_commands(pending, amend=amend)
            log += [f"Then (step 1's releases are not tagged yet: {', '.join(pending)}; the bump goes into their "
                    "push, and the portal release follows once they are pinned):", commands]
        else:
            commands = rp.portal_commands(self.release_window.portal_tag(new), check=rp.check_script(root, suite),
                                          run_script=rp.portal_run_script(root, suite))
            log += ["Then:", commands]
        if nexus:
            note = rp.NEXUS_INDEX_NOTE.format(version=nexus)
            commands += "\n" + note
            log.append(note)
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
        self.units = rp.withdrawable(self.release_window.root, units, self.release_window.suite)
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
        reason = rp.withdrawn_reason(self.release_window.root, unit.key, self.release_window.suite) if unit else ""
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
        root = self.release_window.root
        changed = rp.withdraw(root, unit, reason, suite=self.release_window.suite)
        commands = rp.withdraw_commands(unit.pinned_tag, reason,
                                        run_script=rp.portal_run_script(root, self.release_window.suite))
        self.output.set_text("\n".join([f"{unit.pinned_tag}: withdrawn in " +
                                        ", ".join(p.relative_to(root).as_posix() for p in changed), "", commands]))
        self.release_window.offer(commands)
        self.reason_edit.clear()
        self.release_window.reload()

    def take_back(self) -> None:
        unit = self.unit()
        if unit is None:
            return
        rp.withdraw(self.release_window.root, unit, "", suite=self.release_window.suite)
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


# What the test buttons do for a Windows suite (its check-release.ps1, on the handheld)
WINDOWS_TIPS = {
    "Test app updates": "Start the portal from this checkout (check-release.ps1 local): it installs the apps "
                        "apps.toml pins from their GitHub releases",
    "Test withdrawal": "Start the portal from this checkout on a handheld with the withdrawn app installed "
                       "(check-release.ps1 local); it must show the app as not available and remove it",
    "Installer tests": "Run every installer test of the suite in turn, in a PowerShell window "
                       "(check-release.ps1 installer)",
}


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
        self.tooltips = {button: button.toolTip() for button in (self.local_button, self.release_button,
                                                                 self.withdraw_button, self.installer_button,
                                                                 self.tour_button)}
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
            "The ticked suite's portal is the first icon; when a portal is already open it warns instead, as a second one "
            "would only show the open one. The last icons are the ticked suite's wiki and the Nexus page: each is "
            "served with <code>mkdocs serve</code> on a port of its own and opens in the browser with its design "
            "panel; it rebuilds on every save. With <b>Wikis on the network</b> they are served for the other devices "
            "too, on ports of their own; the addresses show below."))
        lay.addWidget(self.apps, 2)
        self.running: list[tuple[rp.Launch, subprocess.Popen, Path]] = []
        self.waiting: list[str] = []            # servers started, whose page opens once they answer
        self.timer = QTimer(self, interval=1000)
        self.timer.timeout.connect(self.poll)

    def fill(self, targets: list[rp.Launch]) -> None:
        self.enable_tests()
        if self.release_button.isEnabled():
            self.release_button.setToolTip(
                f"After GitHub built {self.release_window.portal_tag()}: download it, check it against "
                f"its SHA256SUMS, install it and start it ({Path(self._check_path()).name} release)")
        self.apps.clear()
        for target in targets:
            icon = QIcon(str(target.icon)) if target.icon else QIcon()
            item = QListWidgetItem(board_badge(icon) if target.changes_board else icon, target.label)
            item.setData(Qt.ItemDataRole.UserRole, target)
            item.setToolTip(("\u26a0 Changes how the board runs: it asks first.\n" if target.changes_board else "") +
                            " ".join(("python -m", target.module, *target.args)) + f" in {target.folder}" +
                            (f"\nopens {target.url}" if target.url else ""))
            self.apps.addItem(item)

    def _check_path(self) -> str:
        return rp.check_script(self.release_window.root, self.release_window.suite)

    def windows_suite(self) -> bool:
        return rp.suite_system(self.release_window.root, self.release_window.suite) == "windows"

    def enable_tests(self) -> None:
        """The board tests of the ticked suite, on its own system (owner, 28-10-2026: on Windows they were all off):
        a Bazzite suite's on Linux, a Windows suite's on Windows (its check-release.ps1). The portal tour is recorded
        on Linux only."""
        here = rp.tests_here(self.release_window.root, self.release_window.suite)
        windows = self.windows_suite()
        for button, tip in self.tooltips.items():
            on = here and not (button is self.tour_button and windows)
            button.setEnabled(on)
            if on:
                button.setToolTip(WINDOWS_TIPS.get(button.text(), tip) if windows else tip)
            elif button is self.tour_button and windows:
                button.setToolTip("The portal tour is recorded on Linux, for the BC250 suite")
            else:
                button.setToolTip("This suite's tests run on " + ("Windows (the handheld)" if windows else
                                                                  "Linux (the board)"))

    def _script_line(self, mode: str) -> str:
        """The check script's command line: bash's on Linux, PowerShell's call operator on Windows."""
        script = str(self.release_window.root / self._check_path())
        if self.windows_suite():
            return "& '" + script.replace("'", "''") + f"' {mode}"
        return f"{shlex.quote(script)} {mode}"

    def check(self, test: str) -> None:
        """Run the suite's check-release script in a terminal: it installs or starts a portal and keeps it running
        there."""
        path = self._check_path()
        if not (self.release_window.root / path).is_file():
            self.output.appendPlainText(f"This suite has no {path}.")
            return
        mode = "release" if test == "release" else "local"
        try:
            self.release_window.launch(self._script_line(mode))
        except RuntimeError as exc:
            self.output.appendPlainText(str(exc))
            return
        if self.windows_suite():
            self.output.appendPlainText({
                "local": "A PowerShell window starts the portal from this checkout; it installs the apps from their "
                         "GitHub releases. Close the portal to finish.",
                "release": f"A PowerShell window downloads the published {self.release_window.portal_tag()} release, "
                           "checks it, installs it and starts it.",
                "withdrawal": "A PowerShell window starts the portal from this checkout. With the app installed, the "
                              "portal removes it and its tile shows it is not available. Close the portal to finish."
            }[test])
            return
        self.output.appendPlainText({
            "local": "A terminal installs the portal from this checkout, then starts it with --source release. "
                     "Close the portal there to finish.",
            "release": f"A terminal installs the published {self.release_window.portal_tag()} release, "
                       "then starts it. Close the portal there to finish.",
            "withdrawal": "A terminal installs the portal from this checkout and starts it. With the app installed, "
                          "the portal says it is not available any more and removes it; its tile then shows \"App not "
                          "available\". Close the portal there to finish."}[test])

    def installer_tests(self) -> None:
        if self.windows_suite():                    # no window of its own: every .ps1 in turn, in PowerShell
            try:
                self.release_window.launch(self._script_line("installer"))
            except RuntimeError as exc:
                self.output.appendPlainText(str(exc))
                return
            self.output.appendPlainText("A PowerShell window runs every installer test of the suite in turn.")
            return
        target = rp.installer_tests_target(self.release_window.root, self.release_window.suite)
        if target is None:
            self.output.appendPlainText("This suite has no tools/installer-tests/gui.")
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
        """The suite's tools/record-tour.sh in the background, its output in Logs; the video opens when it is done."""
        path = rp.record_script(self.release_window.root, self.release_window.suite)
        script = self.release_window.root / path
        if not script.is_file():
            self.output.appendPlainText(f"This suite has no {path}.")
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
        self.output.appendPlainText(f"$ {path} {out}")
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


NOTIFY_MS = 10_000                      # how long a notification from the tray icon shows
_tray: QSystemTrayIcon | None = None    # made at the first notification, kept while the app runs


def tray_notify(summary: str, body: str) -> bool:
    """A notification from the app's icon in the notification area, Qt's QSystemTrayIcon: Windows shows it as one of
    its own notifications (owner, 28-10-2026: Windows has no notify-send, so none came there). A click on it, or on
    the icon, brings the window to the front. False without a notification area."""
    global _tray
    app = QApplication.instance()
    if app is None or not QSystemTrayIcon.isSystemTrayAvailable():
        return False
    if _tray is None:
        _tray = QSystemTrayIcon(QIcon(str(LOGO_PATH)), app)
        _tray.setToolTip(APP_NAME)
        _tray.messageClicked.connect(_raise_window)
        _tray.activated.connect(lambda _reason: _raise_window())
    _tray.show()
    _tray.showMessage(summary, body, _tray.icon(), NOTIFY_MS)
    return True


def _raise_window() -> None:
    for widget in QApplication.topLevelWidgets():
        if isinstance(widget, ReleaseWindow) and widget.isVisible():
            if widget.isMinimized():
                widget.showNormal()
            widget.raise_()
            widget.activateWindow()


def desktop_notify(summary: str, body: str) -> bool:
    """A desktop notification through notify-send (Linux); without it (Windows), from the tray icon (tray_notify).
    False when the desktop has neither."""
    exe = shutil.which("notify-send")
    if not exe:
        return tray_notify(summary, body)
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
        self.signed_in = False                  # the last answer came with a token: the ticker reads the jobs
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
        # Told about: the runs of the suite ticked and Nexus's own, as the ticker shows them (owner, 28-10-2026: the
        # Windows Portable Suite's CI notified while BC250 was released, as every push starts every suite's CI).
        others = [r for r in finished if r not in releases and r.file not in self.release_window.ticker.hidden]
        if others:
            self.announce(others)
        for release in releases:
            self.announce_release(release, pin=release.ref != (portal.tag if portal else ""))
        page.show_builds()
        self.release_window.release_page.show_state()   # the Nexus release's run, from the same runs
        latest = rp.latest_push(self.runs)
        state = rp.build_state(latest)
        self.show_state(state, self.details(latest))
        self.release_window.ticker.show_runs(latest, self.signed_in)
        self.release_window._show_git_state()          # a push from elsewhere: git pull says so
        running = any(not r.done for r in self.runs)
        self.timer.start(BUILD_BUSY_MS if running else BUILD_IDLE_MS)

    def details(self, latest: list[rp.BuildRun]) -> str:
        if not latest:
            return "No workflow runs on GitHub."
        head = f"{latest[0].sha[:7]} {latest[0].title}"
        return "\n".join([head, *(f"{r.label}: {'replaced by a later run' if rp.superseded(r, latest) else r.outcome}"
                                  for r in latest), "", "Click to open it on GitHub."])

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
            self.signed_in = rate.signed_in
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
        failed = [r for r in finished if not r.passed and not rp.superseded(r, self.runs)]
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
        pick = next((r for r in latest if r.done and not r.passed and not rp.superseded(r, latest)), None) or \
            next((r for r in latest if not r.done), None)
        return pick.url if pick else rp.ACTIONS_URL.format(repo_url=rp.pin_app.REPO_URL)

    def open(self) -> None:
        QDesktopServices.openUrl(QUrl(self.target()))

    def stop(self) -> None:
        self.timer.stop()
        self.checker.stop(2000)


JOBS_BUSY_MS = 10_000                   # how often the ticker reads the jobs while a run runs
TICK_MS = 1000                          # and counts its time


class WorkflowTicker(QFrame):
    """Between the header's pills and the tabs: where GitHub's workflows on the newest push stand (owner,
    28-10-2026: no switching to the browser for it), those of the suite ticked and Nexus's own; the other suites'
    CI and releases are left out (owner, 28-10-2026). Each run that runs with its jobs done of all, the job that runs
    and its step, and the time since it started, counted every second; a failed run names its job and step; a run
    that passed says so. Signed in with gh it reads the jobs of every run that runs every 10 seconds, and of a run
    that failed once (unchanged answers do not count against GitHub's limit); without a token, the 60 requests an
    hour are the build pill's, so it shows the runs only. A click opens the job that runs (or failed), else the run.
    Hidden until GitHub shows a run."""

    def __init__(self, source):
        super().__init__()
        self.source = source            # rp.fetch_jobs(url, etag): (jobs | None when unchanged, etag, rate)
        self.pushed: list[rp.BuildRun] = []     # every run of the newest push
        self.hidden: set[str] = set()           # the workflow files left out: the other suites'
        self.runs: list[rp.BuildRun] = []       # the runs shown
        self.jobs: dict[str, list[rp.BuildJob]] = {}    # by the run's url
        self.etags: dict[str, str] = {}
        self.final: set[str] = set()            # the runs whose jobs were read after they finished
        self.signed_in = False
        self.line = ""
        self.setObjectName("ticker")
        self.setStyleSheet(f"#ticker {{ border:1px solid {NEXUS.edge}; border-radius:6px; }}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dot = QLabel("●")
        self.text = QLabel()
        self.text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)  # elided, never wider
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.addWidget(self.dot)
        lay.addWidget(self.text, 1)
        self.checker = UpdateChecker(self)
        self.checker.finished.connect(self.fetched)
        self.timer = QTimer(self, singleShot=True)
        self.timer.timeout.connect(self.fetch)
        self.clock = QTimer(self, interval=TICK_MS)
        self.clock.timeout.connect(self.render)
        self.setVisible(False)

    def follow(self, hidden: set[str]) -> None:
        """Another suite ticked: leave out the runs of these workflow files (the other suites' CI and releases)."""
        self.hidden = hidden
        self.show_runs(self.pushed, self.signed_in)

    def show_runs(self, runs: list[rp.BuildRun], signed_in: bool) -> None:
        """The build pill looked: these are the newest push's runs; the ticker shows those of the suite ticked and
        Nexus's own."""
        self.pushed, self.signed_in = runs, signed_in
        self.runs = [r for r in runs if r.file not in self.hidden]
        urls = {r.url for r in self.runs}
        self.jobs = {url: jobs for url, jobs in self.jobs.items() if url in urls}
        self.etags = {url: etag for url, etag in self.etags.items() if url in urls}
        self.fetch()
        self.render()

    def wanted(self) -> list[rp.BuildRun]:
        """The runs whose jobs to read: those that run, and a failed one not read since it finished."""
        if self.source is None or not self.signed_in:
            return []
        return [r for r in self.runs if r.jobs_url and (not r.done or (not r.passed and r.url not in self.final))]

    def fetch(self) -> None:
        wanted = [(r.url, r.jobs_url, self.etags.get(r.url, ""), r.done) for r in self.wanted()]
        if wanted:
            self.checker.start(lambda: self._fetch(wanted))

    def _fetch(self, wanted: list[tuple[str, str, str, bool]]) -> dict:
        """Worker thread: each run's jobs (None when unchanged) with its ETag; a run GitHub did not answer for keeps
        what was read before."""
        found = {}
        for url, jobs_url, etag, done in wanted:
            try:
                jobs, etag, *_rate = self.source(jobs_url, etag)
            except (OSError, ValueError):
                continue
            found[url] = (jobs, etag, done)
        return found

    def fetched(self, found: dict) -> None:
        urls = {r.url for r in self.runs}
        for url, (jobs, etag, done) in found.items():
            if url not in urls:                 # a newer push meanwhile
                continue
            if jobs is not None:
                self.jobs[url] = jobs
            self.etags[url] = etag
            if done:
                self.final.add(url)
        self.render()

    def render(self) -> None:
        now = time.time()
        self.setVisible(bool(self.runs))
        state = rp.build_state(self.runs)
        running = state == "running"
        if running and not self.clock.isActive():
            self.clock.start()
        elif not running:
            self.clock.stop()
        if running and self.wanted() and not self.timer.isActive():
            self.timer.start(JOBS_BUSY_MS)
        if not self.runs:
            return
        self.dot.setStyleSheet(f"color:{BUILD_LOOK[state][0]};")
        self.line = rp.ticker_line(self.runs, self.jobs, now)
        self._elide()
        sign_in = "" if self.signed_in or self.source is None else \
            "\n\nSigned in with gh (gh auth login), the ticker shows each job and the step it is at too."
        self.setToolTip(rp.ticker_details(self.runs, self.jobs, now) + sign_in + "\n\nClick to open it on GitHub.")

    def _elide(self) -> None:
        self.text.setText(self.text.fontMetrics().elidedText(self.line, Qt.TextElideMode.ElideRight,
                                                             max(0, self.text.width())))

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._elide()

    def target(self) -> str:
        return rp.ticker_target(self.runs, self.jobs)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton and self.target():
            open_url(self.target())
        super().mouseReleaseEvent(event)

    def stop(self) -> None:
        self.timer.stop()
        self.clock.stop()
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


class SuiteList(QListWidget):
    """The suites of the checkout as the window's first column, left of the steps (owner, 27-10-2026: in place of a
    chooser in the header): each portal with its icon, its name and the tag of its current version. The checkmark is
    the suite this window releases, always exactly one; a click on a row, or on its box, moves it there and calls
    *chosen* with the suite's folder. Hidden while the checkout holds one suite."""

    WIDTH = 230

    def __init__(self, root: Path, suites: list[str], current: str | None, chosen):
        super().__init__()
        self.root, self.chosen = root, chosen
        self.setFixedWidth(self.WIDTH)
        self.setIconSize(QSize(32, 32))
        self.setSpacing(2)
        self.setToolTip("The suite this window releases: its apps, its portal and its pins. The git buttons, the "
                        "wikis and GitHub are the repository's, whatever the suite.")
        for name in suites:
            icon = rp.suite_icon(root, name)
            item = QListWidgetItem(QIcon(str(icon)) if icon else QIcon(), "")
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            self.addItem(item)
        self.show_texts()
        self.check(current)
        self.itemClicked.connect(lambda item: self._pick(item.data(Qt.ItemDataRole.UserRole)))
        self.itemChanged.connect(self._box)
        self.setVisible(len(suites) > 1)

    def show_texts(self) -> None:
        """Each row's name and its portal's tag, read again (after Bump portal the version moved)."""
        self.blockSignals(True)
        for row in range(self.count()):
            item = self.item(row)
            name = item.data(Qt.ItemDataRole.UserRole)
            version_file = rp.suite_dir(self.root, name) / "portal" / "VERSION"
            version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "?"
            item.setText(f"{rp.suite_name(self.root, name)}\n{rp.tag_prefix(self.root, name)}portal-v{version}")
            item.setToolTip(f"{name}/: its apps, its portal and its pins")
        self.blockSignals(False)

    def check(self, name: str | None) -> None:
        self.blockSignals(True)
        for row in range(self.count()):
            item = self.item(row)
            mine = item.data(Qt.ItemDataRole.UserRole) == name
            item.setCheckState(Qt.CheckState.Checked if mine else Qt.CheckState.Unchecked)
        self.blockSignals(False)

    def current(self) -> str | None:
        return next((self.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.count())
                     if self.item(row).checkState() == Qt.CheckState.Checked), None)

    def _box(self, item: QListWidgetItem) -> None:
        """The box of a row clicked: checking it picks that suite; unchecking the checked one keeps it checked."""
        name = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self._pick(name)
        else:
            self.check(name)

    def _pick(self, name: str) -> None:
        self.check(name)
        self.chosen(name)


class ReleaseWindow(QMainWindow):
    def __init__(self, root: Path = CHECKOUT, sha256_source=rp.fetch_sha256, launch=launch_in_terminal,
                 start=start_app, runs_source=rp.fetch_runs, notify=desktop_notify, settings=None,
                 status_source=rp.fetch_github_status, claude_source=rp.fetch_claude_usage,
                 issues_source=rp.fetch_open_issues, suite: str | None = None, jobs_source=rp.fetch_jobs):
        """*runs_source* reads the GitHub Actions runs (None: no build indicator and no ticker); *jobs_source* the
        jobs of a run, for the ticker (None: the runs only); *notify* shows a desktop
        notification; *settings* keeps the command line's history and the chosen suite (None: this session only);
        *status_source* reads githubstatus.com (None: no GitHub status); *claude_source* reads Claude Code's usage
        (None: no Claude pill); *issues_source* reads the open GitHub issues for Close issues; *suite* is the suite
        to open with (a folder name from plan.suites(); None: the one remembered, else the first)."""
        super().__init__()
        self.root = root
        self.settings = settings
        self.suites = rp.suites(root)
        remembered = str(settings.value(SUITE_KEY, "")) if settings is not None else ""
        self.suite = suite or (remembered if remembered in self.suites else self.suites[0] if self.suites else None)
        self.issues_source = issues_source
        self.sha256_source = sha256_source
        self.launch = launch
        self.start = start
        self.units: list[rp.Unit] = []
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 760)
        self.setStyleSheet(SELECTION_STYLESHEET + CHECK_STYLESHEET)
        stamp = rp.checkout_stamp(root)                 # never released: the commit says which code runs
        header = AppHeader(LOGO_PATH, APP_NAME, f"{__version__} · {stamp}" if stamp else __version__)
        # The suites, the first column left of the steps; hidden while the checkout holds one suite.
        self.suite_list = SuiteList(root, self.suites, self.suite, self.choose_suite)
        # The header's pills, all as wide as the widest (owner, 20-10-2026).
        self.refresh_pill = Pill("Refresh", "Click to refresh", "Read the checkout and its tags again, for changes "
                                 "made in a terminal; what you entered stays")
        self.refresh_pill.clicked.connect(self.refresh)
        self.status = MetricBox("Working tree")    # clean or changed
        self.build = BuildIndicator(self, runs_source, notify)
        self.ticker = WorkflowTicker(jobs_source)       # between the pills and the tabs, fed by the build's looks
        self.ticker.hidden = rp.other_suites_workflows(root, self.suite)
        self.github_status = GitHubStatusIndicator(status_source)
        self.claude = ClaudeUsageIndicator(claude_source)
        self.tabs = QTabWidget()
        self.apps_page = AppsPage(self)                 # its Apply is the header's third pill
        pills = [self.refresh_pill, self.status, self.apps_page.apply_button, self.build, self.build.rate,
                 self.github_status, self.claude]
        for pill in pills:
            header.add_second(pill)
        same_width(pills)
        header.second_row.addStretch(1)
        self.portal_page = PortalPage(self)
        # The Nexus release first (owner, 30-10-2026: one action, Start new release); the steps stay for a suite not
        # on it yet (bc250-bazzite) and for doing a step by hand.
        self.release_page = ReleasePage(self)
        self.tabs.addTab(self.release_page, "Nexus release")
        self.tabs.addTab(self.apps_page, "1. Release apps")
        self.tabs.addTab(self.portal_page, "2. Pin and release Portal")
        self.withdraw_page = WithdrawPage(self)
        self.tabs.addTab(self.withdraw_page, "3. Retract app")
        self.run_page = RunPage(self)
        self.tabs.addTab(self.run_page, "Test on this board")
        # Opening step 2 reads the tags again, so tags pushed from a terminal meanwhile show up; step 1 keeps what
        # was typed in it.
        self.tabs.currentChanged.connect(lambda i: self.tabs.widget(i) is self.portal_page
                                         and self.portal_page.fill(rp.load_units(self.root, self.suite)))
        self.commands = CommandLine(root, settings, finished=self.refresh,     # a commit or push: read it again
                                    log_dir=COMMAND_LOG_DIR if settings is not None else None)
        # The logs are tabs of their own, each the whole tab area (owner, 17-10-2026: boxes under the steps were
        # too flat to read). Logs shows the log of the step last open (what Apply, Pin, Bump portal, Retract or
        # a started app wrote); a step that writes its log opens it. Commands is the command line with its output.
        self.step_pages = (self.release_page, self.apps_page, self.portal_page, self.withdraw_page, self.run_page)
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
        for page in self.step_pages[:4]:                 # not Test on this board: its lines come while you click
            page.output.textChanged.connect(lambda page=page: self._show_log(page))
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(header)
        lay.addWidget(self.ticker)
        self.bad_tags = QLabel()
        self.bad_tags.setWordWrap(True)
        self.bad_tags.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.bad_tags.setStyleSheet("color:#c62828; font-weight:600;")
        lay.addWidget(self.bad_tags)
        columns = QHBoxLayout()
        # Twice the layout's spacing between the header's pills and the tabs (owner, 28-10-2026: too close).
        columns.setContentsMargins(0, lay.spacing(), 0, 0)
        self.suite_column = QWidget()                   # "Portals" over the list; hidden with it
        column = QVBoxLayout(self.suite_column)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)                            # the title sits on the list as a tab on its page
        title = QLabel("Portals")                       # as wide as the column (owner, 28-10-2026)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(TAB_TITLE_STYLESHEET)
        column.addWidget(title)
        column.addWidget(self.suite_list, 1)
        self.suite_column.setVisible(not self.suite_list.isHidden())
        columns.addWidget(self.suite_column)
        columns.addWidget(self.tabs, 1)
        lay.addLayout(columns, 1)
        lay.addLayout(self._git_row())
        self.footer = QLabel()
        self.footer.setStyleSheet("color:palette(placeholder-text);")
        lay.addWidget(self.footer, 0, Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(central)
        self.reload()
        self.build.check()
        self.github_status.check()
        self.claude.check()

    def choose_suite(self, name: str) -> None:
        """Another suite ticked in the first column: the steps, the pins and the board tests show it from now on,
        and the next start opens with it."""
        if not name or name == self.suite:
            return
        self.suite = name
        if self.settings is not None:
            self.settings.setValue(SUITE_KEY, name)
        self.ticker.follow(rp.other_suites_workflows(self.root, name))
        self.refresh()

    def _git_row(self) -> QHBoxLayout:
        """git add, git commit, git push and git tag as buttons, each with its checks (owner, 19-10-2026: no commands
        to type or copy; git tag, owner, 20-10-2026). They run in the command line, whose output opens."""
        # git pull first (owner, 28-10-2026: a push from the other machine only showed as a push that failed).
        self.pull_button = QPushButton("git pull")
        self.pull_button.clicked.connect(lambda: self.run_git(rp.pull_command()))
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
        row.addWidget(self.pull_button)
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
        touched = rp.staged_suites(self.root)           # the suites the commit changes: their checks alone
        self.run_git(rp.commit_command(message, self.base(), amend, shlex.quote(sys.executable),
                                       rp.manifest_checks(self.root, touched), rp.version_checks(touched)))

    def _show_git_state(self) -> None:
        """Each button only when it has something to do, and none while a command runs."""
        unstaged, staged, ahead = self.git_state
        idle = not self.commands.is_running() and bool(self.commands.bash)
        amend = self.amend_box.isChecked()
        message = self.commit_message.text().strip()
        self.pull_button.setEnabled(idle)
        waiting = rp.behind(self.root, self.base())
        # The build pill sees every push on GitHub: its newest on main that is no commit here was pushed elsewhere.
        pushed = next((r for r in self.build.runs if r.ref == "main"), None)
        newer = pushed is not None and rp.git(self.root, "cat-file", "-e", f"{pushed.sha}^{{commit}}") is None
        self.pull_button.setText(f"git pull ({waiting})" if waiting else "git pull (new)" if newer else "git pull")
        self.pull_button.setToolTip(
            rp.pull_command() + "\n\n" + (f"{self.base()} has {waiting} commit{'s' if waiting != 1 else ''} this "
                                         "checkout does not: pull before you go on. " if waiting else
                                         f"GitHub has a push this checkout does not ({pushed.sha[:7]} "
                                         f"{pushed.title}): pull before you go on. " if newer else "") +
            "Brings in what was pushed from the other machine (Linux or Windows), with this checkout's own commits on "
            "top of it and the changes not committed yet kept. Pull when you start working here, and when git push "
            "says the remote has commits this checkout does not.")
        self.add_button.setEnabled(idle and unstaged)
        if amend:                               # a pushed commit is never amended: its push would need --force
            why = "" if ahead else f"The last commit is pushed already ({self.base()}): commit without Amend."
        else:
            why = "Nothing is staged: git add first." if not staged else \
                "" if message else "Type a commit message first."
        self.commit_button.setEnabled(idle and not why)
        touched = rp.staged_suites(self.root)
        self.commit_button.setToolTip(
            rp.commit_command(message or "<message>", self.base(), amend, manifests=rp.manifest_checks(self.root, touched),
                              versions=rp.version_checks(touched))
            + "\n\n" + (why or "Runs check_versions.py and check_manifest.py first, of the suites the staged changes "
                              "touch (one suite's checks never hold another's commit), and commits only when they "
                              "pass"))
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
            "Commit first: the staged changes are not in a commit yet." if staged else \
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
        return (rp.suite_dir(self.root, self.suite) / "portal" / "VERSION").read_text(encoding="utf-8").strip()

    def portal_tag(self, version: str = "") -> str:
        """The suite's portal tag of *version* (default: portal/VERSION): portal-v10.1.0, wp-portal-v0.1.0."""
        return f"{rp.tag_prefix(self.root, self.suite)}portal-v{version or self.portal_version()}"

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
        units = self.units = rp.load_units(self.root, self.suite)
        self.suite_list.show_texts()                    # a portal bumped meanwhile shows its new tag
        self.release_page.fill()
        self.apps_page.fill(units)
        self.portal_page.fill(units)
        self.withdraw_page.fill(units)
        portal = rp.portal_target(self.root, self.suite)
        docs = rp.docs_targets(self.root, network=self.run_page.network_box.isChecked(), suite=self.suite)
        self.run_page.fill(([portal] if portal else []) + rp.launch_targets(self.root, self.suite) + docs)
        self.footer.setText(f"{APP_NAME} {__version__} · edits {self.root}"
                            + (f" · suite {self.suite}" if len(self.suites) > 1 else ""))
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
        self.ticker.stop()
        if _tray is not None:                           # no icon left behind in the notification area
            _tray.hide()
        self.github_status.stop()
        self.claude.stop()
        self.commands.shutdown()
        recorder = self.run_page.recorder
        if recorder is not None:                         # a tour being recorded: stopped, not left half-written
            recorder.finished.disconnect()
            recorder.kill()
            recorder.waitForFinished(3000)
        super().closeEvent(event)
