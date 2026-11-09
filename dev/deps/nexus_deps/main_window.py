# SPDX-License-Identifier: GPL-3.0-or-later
"""The Nexus Deps window: Bazzite's update state (bazzite.py) and the machine's updates (system.py) on top, then the
Python packages and the external tools, with Fix (fixes.py) for what is missing, outdated or newer. In Nexus's
design (create_app(theme=NEXUS)): the colors come from the theme the widgets draw with, not the suite's."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from html import escape
from pathlib import Path
from urllib.parse import quote

from PyQt6.QtCore import QProcess, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QStyle, QToolButton, QVBoxLayout, QWidget,
)

from bc250_core.text import window_title
from bc250_core.theme import BLUE, GREEN, GREY, ORANGE, RED, header_font, surface_style
from bc250_core.updates import UpdateChecker
from bc250_core.widgets import (
    AppHeader, InfoButton, MetricBox, StatusPill, Terminal, accent, current_theme, hint_label, outline,
)

from . import APP_NAME, DEFAULT_SUITE, INFO, LOGO_PATH, __version__
from .bazzite import BazziteState, describe, read_state
from .dependencies import (
    App, CheckResult, Dependency, DependencyStatus, ExternalTool, ToolSource, ToolStatus, check_all, release,
    tool_need,
)
from .fixes import RESTART, Plan, Step, plan as fix_plan
from .system import Source, Update, read_sources, steps as system_steps, summary as system_summary
from .upstreams import read as read_upstreams


# The apps' manuals: each suite's wiki
DOCS = {"bc250-bazzite": "https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/{app}/"}
DOCS_URL = DOCS[DEFAULT_SUITE]
SUITE_NAMES = {"bc250-bazzite": "BC250 Bazzite Suite"}
CARD_STYLE = "QFrame#dependencyCard { border:1px solid palette(mid); border-radius:8px; }"
NEEDS_ROOT = f"<span style='color:{ORANGE}; font-weight:700;'>Needs root.</span>"
CVE_OK = f"<span style='color:{GREEN}; font-weight:700;'>✓ CVE</span>"
CVE_FOUND = f"<span style='color:{RED}; font-weight:700;'>✗ CVE</span>"
CVE_UNKNOWN = "<span style='color:palette(placeholder-text); font-weight:700;'>CVE ?</span>"


def _app_name(owner: str, apps: dict[str, App]) -> str:
    app = apps.get(owner)
    return app.name if app else owner


def _manual_link(source: ToolSource, apps: dict[str, App]) -> str:
    label = escape(_app_name(source.owner, apps))
    url = DOCS_URL.format(app=quote(source.owner, safe="-"))
    if source.anchor:
        url += f"#{quote(source.anchor, safe='-')}"
    return f"<a href='{escape(url, quote=True)}'>{label}</a>"


def _short_path(path: str) -> str:
    home = str(Path.home())
    return "~" + path[len(home):] if path == home or path.startswith(home + "/") else path


def _names(items: Iterable[str]) -> str:
    return ", ".join(items)


def tool_advice(tool: ExternalTool, installed: frozenset[str], apps: dict[str, App], note: str = "") -> str:
    """What a missing tool keeps from working: the features of the installed apps that use it."""
    sources = [source for source in tool.sources if source.owner in installed]
    if not sources:
        return ""
    name = " or ".join(tool.executables) if len(tool.executables) > 1 else tool.name
    lead = (f"{escape(note)} Install a {escape(tool.name)} that has it" if note else f"Install {escape(name)}")
    rows = [f"{_manual_link(source, apps)}: {escape(source.usage)}"
            f"{' <b>(required)</b>' if source.need == 'required' else ''}" for source in sources]
    if len(rows) == 1:
        return f"<b>Advice:</b> {lead} to be able to use {rows[0]}"
    items = "".join(f"<li>{row}</li>" for row in rows)
    return f"<b>Advice:</b> {lead} to be able to use:<ul style='margin:0;'>{items}</ul>"


def package_advice(result: DependencyStatus, apps: dict[str, App]) -> str:
    """What to do about a missing, wrong or vulnerable package, and which apps it keeps from working."""
    name = escape(result.dependency.name)
    parts = []
    for env in result.missing + result.unmet:
        users = escape(_names(_app_name(owner, apps) for owner in env.owners))
        parts.append(f"Fix installs {name} in {escape(_short_path(env.environment))}, which {users} needs; "
                     "installing the app again from the portal does too.")
    fixes = {}
    for version, vuln in result.vulnerabilities:
        if vuln.fixed:
            fixes.setdefault(version, []).append(vuln.fixed)
    users: dict[str, list[str]] = {}
    for env in result.environments:
        if env.version in fixes:
            users.setdefault(env.version, []).extend(_app_name(owner, apps) for owner in env.owners)
    for version, names in users.items():
        fixed = max(fixes[version], key=release)
        parts.append(f"Update {name} {escape(version)} to {escape(fixed)} or newer for "
                     f"{escape(_names(dict.fromkeys(names)))}: that release fixes the known vulnerabilities.")
    return ("<b>Advice:</b> " + " ".join(dict.fromkeys(parts))) if parts else ""


def needs_update_text(result: DependencyStatus, apps: dict[str, App]) -> str:
    """Why the package must be updated, per environment: the app wants a newer one, or a release fixes a known
    vulnerability."""
    reasons = []
    specifiers = {source.owner: source.specifier for source in result.dependency.sources}
    for env in result.needs_update:
        for owner in env.outdated:
            reasons.append(f"{_app_name(owner, apps)} needs {specifiers[owner]}, installed is {env.version}.")
        if env.fixes:
            fixed = max((vuln.fixed for vuln in env.fixes), key=release)
            reasons.append(f"{fixed} fixes known vulnerabilities in {env.version}.")
    return " ".join(dict.fromkeys(reasons))


def about_text(item: Dependency | ExternalTool, apps: dict[str, App]) -> str:
    """The description shown by the card's information button: what it is, and what each app uses it for."""
    parts = [f"<p>{escape(item.description)}</p>"]
    if isinstance(item, ExternalTool):
        if item.root:
            parts.append(f"<p>{NEEDS_ROOT} It does its work only as root; the apps run it through sudo or pkexec, "
                         "which ask for your password.</p>")
        rows = "".join(f"<li><b>{escape(_app_name(source.owner, apps))}</b> ({source.need}): "
                       f"{escape(source.usage)}</li>" for source in item.sources)
        commands = ", ".join(item.executables) or ", ".join(item.locations)
        parts.append(f"<p>Looked for: {escape(commands)}</p>")
    else:
        rows = "".join(f"<li><b>{escape(_app_name(source.owner, apps))}</b>: {escape(source.specifier)}</li>"
                       for source in item.sources)
        parts.append(f"<p>Python package on <a href='https://pypi.org/project/{quote(item.name)}/'>PyPI</a>.</p>")
    parts.append(f"<p>Used by:</p><ul>{rows}</ul>")
    return "".join(parts)


class _Card(QFrame):
    """A frame with the name, an information button for its description, and a status pill."""

    def __init__(self, item: Dependency | ExternalTool, apps: dict[str, App], parent: QWidget | None = None):
        super().__init__(parent)
        self.item = item
        self.apps = apps
        self.about_box: QMessageBox | None = None
        self.setObjectName("dependencyCard")
        self.setStyleSheet(CARD_STYLE)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(14, 10, 14, 10)
        title_row = QHBoxLayout()
        title = QLabel(item.name)
        title.setStyleSheet(header_font() + "font-size:16px; font-weight:700;")
        title_row.addWidget(title)
        self.about_button = QToolButton()
        self.about_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
        self.about_button.setIconSize(QSize(18, 18))
        self.about_button.setAutoRaise(True)
        self.about_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.about_button.setToolTip(f"What is {item.name}?")
        self.about_button.clicked.connect(self.show_about)
        title_row.addWidget(self.about_button)
        if isinstance(item, ExternalTool) and item.root:
            root = QLabel(NEEDS_ROOT)
            root.setToolTip("It does its work only as root; the apps run it through sudo or pkexec.")
            title_row.addWidget(root)
        if isinstance(item, Dependency):
            self.cve = QLabel(CVE_UNKNOWN)
            self.cve.setToolTip("Not checked yet for known vulnerabilities (OSV.dev).")
            title_row.addWidget(self.cve)
        title_row.addStretch(1)
        self.status = StatusPill("Not checked")
        title_row.addWidget(self.status)
        self.layout_.addLayout(title_row)
        self.advice = QLabel()
        self.advice.setWordWrap(True)
        self.advice.setTextFormat(Qt.TextFormat.RichText)
        self.advice.setOpenExternalLinks(True)
        self.advice.hide()

    def _show_advice(self, text: str) -> None:
        self.advice.setText(text)
        self.advice.setVisible(bool(text))

    def show_about(self) -> None:
        box = QMessageBox(QMessageBox.Icon.Information, window_title(self.item.name), "", parent=self)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(f"<h3>{escape(self.item.name)}</h3>{about_text(self.item, self.apps)}")
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        box.open()
        self.about_box = box


class DependencyCard(_Card):
    def __init__(self, dependency: Dependency, apps: dict[str, App], parent: QWidget | None = None):
        super().__init__(dependency, apps, parent)
        self.dependency = dependency
        self.installed = QLabel("Installed: not checked")
        self.installed.setWordWrap(True)
        self.installed.setTextFormat(Qt.TextFormat.RichText)
        self.latest = QLabel("Latest on PyPI: not checked")
        self.layout_.addWidget(self.installed)
        self.layout_.addWidget(self.latest)
        requirements = "; ".join(f"{_app_name(source.owner, apps)} {source.specifier}"
                                 for source in dependency.sources)
        self.layout_.addWidget(hint_label(f"Requirements: {requirements}"))
        self.not_installed = hint_label("")
        self.not_installed.hide()
        self.layout_.addWidget(self.not_installed)
        self.vulnerabilities = QLabel()
        self.vulnerabilities.setWordWrap(True)
        self.vulnerabilities.setTextFormat(Qt.TextFormat.RichText)
        self.vulnerabilities.setOpenExternalLinks(True)
        self.vulnerabilities.hide()
        self.layout_.addWidget(self.vulnerabilities)
        self.layout_.addWidget(self.advice)

    def show_result(self, result: DependencyStatus, installed: frozenset[str]) -> None:
        apps = self.apps
        lines = []
        for env in result.environments:
            users = _names([_app_name(owner, apps) for owner in env.owners])
            where = escape(_short_path(env.environment))
            if env.version:
                text = f"<b>{escape(env.version)}</b> in {where}: {escape(users)}"
                if env.unmet:
                    text += (f" <span style='color:{ORANGE};'>(does not meet the requirement of "
                             f"{escape(_names([_app_name(owner, apps) for owner in env.unmet]))})</span>")
            else:
                text = f"<b>missing</b> in {where}: {escape(users)}"
            lines.append(text)
        self.installed.setText("Installed: " + ("<br>".join(lines) if lines else "no installed app uses it"))
        absent = [_app_name(source.owner, apps) for source in self.dependency.sources
                  if source.owner not in installed and apps.get(source.owner, App("", "")).launchers]
        self.not_installed.setText(f"Apps not installed: {_names(absent)}")
        self.not_installed.setVisible(bool(absent))
        self.latest.setText(f"Latest on PyPI: {result.latest or 'unavailable'}")
        self._show_cves(result)
        self._show_advice(package_advice(result, apps))

        if not result.needed:
            self.status.set_status("Not needed", "neutral", "No installed app uses this package.")
        elif result.missing:
            owners = _names([_app_name(owner, apps) for env in result.missing for owner in env.owners])
            self.status.set_status("Missing", "bad", f"Not in the environment of {owners}. Fix installs it.")
        elif result.needs_update:
            self.status.set_status("Needs update", "bad", needs_update_text(result, apps))
        elif result.unmet:
            self.status.set_status("Wrong version", "bad", "An installed version does not meet the app's "
                                   "requirement. Fix installs one that does.")
        elif result.vulnerabilities:
            self.status.set_status("Vulnerable", "bad", "An installed version has known vulnerabilities; see "
                                   "below.")
        elif result.error:
            self.status.set_status("Check failed", "bad", result.error)
        elif result.update_available:
            self.status.set_status("Update available", "warn", f"PyPI has {result.latest}. The apps update it "
                                   "when they are installed again; newer versions are tested with an app release.")
        elif result.latest:
            self.status.set_status("Up to date", "ok", f"PyPI: {result.latest}.")
        else:
            self.status.set_status("Unknown", "neutral")

    def _show_cves(self, result: DependencyStatus) -> None:
        found = result.vulnerabilities
        if found:
            self.cve.setText(CVE_FOUND)
            self.cve.setToolTip(f"Known vulnerabilities (OSV.dev): {_names(vuln.id for _version, vuln in found)}")
        elif result.cve_checked:
            self.cve.setText(CVE_OK)
            self.cve.setToolTip("No known vulnerabilities in the installed versions (OSV.dev).")
        else:
            self.cve.setText(CVE_UNKNOWN)
            self.cve.setToolTip(f"The vulnerability check failed: {result.cve_error}" if result.cve_error else
                                "Not installed for any installed app: nothing to check.")
        rows = "".join(
            f"<li><a href='{escape(vuln.url, quote=True)}'>{escape(vuln.id)}</a> in {escape(version)}"
            f"{': ' + escape(vuln.summary) if vuln.summary else ''}"
            f"{f' (fixed in {escape(vuln.fixed)})' if vuln.fixed else ''}</li>" for version, vuln in found)
        self.vulnerabilities.setText(f"<span style='color:{RED}; font-weight:700;'>Known vulnerabilities:</span>"
                                     f"<ul style='margin:0;'>{rows}</ul>" if found else "")
        self.vulnerabilities.setVisible(bool(found))


class ExternalToolCard(_Card):
    def __init__(self, tool: ExternalTool, apps: dict[str, App], parent: QWidget | None = None):
        super().__init__(tool, apps, parent)
        self.tool = tool
        self.location = QLabel("Detected: not checked")
        self.layout_.addWidget(self.location)
        self.usages: dict[str, QLabel] = {}
        for source in tool.sources:
            usage = QLabel()
            usage.setTextFormat(Qt.TextFormat.RichText)
            usage.setOpenExternalLinks(True)
            usage.setWordWrap(True)
            self.usages[source.owner] = usage
            self.layout_.addWidget(usage)
        self.layout_.addWidget(self.advice)
        self._show_usages(None)

    def _show_usages(self, installed: frozenset[str] | None) -> None:
        for source in self.tool.sources:
            need = "Required" if source.need == "required" else "Optional"
            text = f"{_manual_link(source, self.apps)} ({need.lower()}): {escape(source.usage)}"
            if installed is not None and source.owner not in installed:
                text += " <span style='color:palette(placeholder-text);'>(app not installed)</span>"
            self.usages[source.owner].setText(text)

    def show_result(self, result: ToolStatus, installed: frozenset[str]) -> None:
        self._show_usages(installed)
        need = tool_need(self.tool, installed)
        if result.note:
            self.status.set_status("Unsupported build", "warn", result.note)
        elif result.path and result.version:
            self.status.set_status("Available", "ok", f"Version {result.version}, found at {result.path}")
        elif result.path:
            self.status.set_status("Available", "ok", f"Found at {result.path}")
        elif need == "required":
            how = ("Fix installs it with Homebrew" if self.tool.brew else
                   "Fix layers it into the Bazzite image" if self.tool.rpm else
                   "The app's manual (linked below) says how to install it")
            self.status.set_status("Missing", "bad", f"An installed app needs it. {how}.")
        elif need == "optional":
            self.status.set_status("Not installed", "info", "Optional: the apps work without it and use it when "
                                   "it is there. The app's manual (linked below) says how to install it.")
        else:
            self.status.set_status("Not needed", "neutral", "No installed app uses it.")
        found = _short_path(result.path) if result.path else "not found"
        if result.version:
            found += f" (version {result.version})"
        self.location.setText(f"Detected: {found}")
        missing = not result.path or bool(result.note)
        self._show_advice(tool_advice(self.tool, installed, self.apps, result.note) if missing else "")


class BazziteCard(QFrame):
    """Bazzite's update state: the running image, an update waiting for a reboot, the updater's last run."""

    PILLS = {"ok": ("Up to date", "ok"), "warn": ("Look at this", "warn"), "neutral": ("Not known", "neutral")}

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dependencyCard")
        self.setStyleSheet(CARD_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        title_row = QHBoxLayout()
        title = QLabel("Bazzite")
        title.setStyleSheet(header_font() + "font-size:16px; font-weight:700;")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.status = StatusPill("Not checked")
        title_row.addWidget(self.status)
        layout.addLayout(title_row)
        self.text = QLabel("Reading Bazzite's update state…")
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.text)

    def show_state(self, state: BazziteState) -> None:
        kind, text = describe(state)
        word, colour = self.PILLS[kind]
        if state.update_waiting:
            word = "Reboot to update"
        self.status.set_status(word, colour, "Read from rpm-ostree and systemd; updating is Bazzite's own")
        self.text.setText(text)


def update_row(update: Update) -> str:
    """"node 26.13.0_1 → 26.13.0_2"; a package pip would add: "pytest 9.2.0 (missing)"."""
    if not update.current:
        return f"{update.name} {update.latest}" + (" (missing)" if update.latest else "")
    return f"{update.name} {update.current} → {update.latest}" + (" (major)" if update.major else "")


class SystemCard(QFrame):
    """One source of the machine's updates (system.py): what is newer, what the requirements hold back, and Update,
    which runs the source's step after the same question as Fix."""

    SHOWN = 12                              # rows listed; the rest by name

    def __init__(self, source: Source, update: Callable[[Step], None], parent: QWidget | None = None):
        super().__init__(parent)
        self.source = source
        self.setObjectName("dependencyCard")
        self.setStyleSheet(CARD_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        title_row = QHBoxLayout()
        title = QLabel(source.name)
        title.setStyleSheet(header_font() + "font-size:16px; font-weight:700;")
        title_row.addWidget(title)
        self.info = InfoButton(source.about, f"{source.name}: what Update does and how to handle it")
        self.info.setVisible(bool(source.about))
        title_row.addWidget(self.info)
        title_row.addStretch(1)
        self.status = StatusPill()
        title_row.addWidget(self.status)
        self.update_button = QPushButton("Update")
        self.update_button.setAccessibleName(f"Update {source.name}")
        title_row.addWidget(self.update_button)
        layout.addLayout(title_row)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.TextFormat.RichText)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.text)
        self.held = hint_label("")
        layout.addWidget(self.held)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet(f"color:{ORANGE};")
        layout.addWidget(self.note)

        step = source.step if not source.error else None
        self.update_button.setVisible(step is not None)
        if step is not None:
            self.update_button.setToolTip(f"Runs, after asking: {' '.join(step.command)}")
            self.update_button.clicked.connect(lambda _checked=False: update(step))
        if not source.checked:
            self.status.set_status("On the device", "neutral", "Nothing a program can ask: the i says where to look.")
        elif source.error:
            self.status.set_status("Check failed", "bad", source.error)
            self.text.setText(escape(f"Could not be checked: {source.error}"))
        elif source.manual:
            self.status.set_status("By hand", "warn", "Not installed from here: the i beside the name says how.")
            rows = "".join(f"<li>{escape(update_row(item))}</li>" for item in source.updates)
            self.text.setText(f"<ul style='margin:0;'>{rows}</ul>" + (escape(source.detail) if source.detail else ""))
        elif source.updates:
            count = len(source.updates)
            self.status.set_status(f"{count} update{'s' if count != 1 else ''}", "warn",
                                   "Update installs them" + (" (used after a restart)" if step and step.restart
                                                             else ""))
            rows = "".join(f"<li>{escape(update_row(item))}</li>" for item in source.updates[:self.SHOWN])
            rest = source.updates[self.SHOWN:]
            more = (f"<p style='margin:0;'>And {len(rest)} more: "
                    f"{escape(_names(item.name for item in rest))}.</p>") if rest else ""
            self.text.setText(f"<ul style='margin:0;'>{rows}</ul>{more}")
        elif source.known:
            # Sony's latest versions, not the device's own: no news since the last look, nothing more is known
            self.status.set_status("Nothing new", "neutral", "No new version since the last look; the device's own "
                                   "version: the i says where to see it.")
            self.text.setText(escape(source.detail))
        else:
            self.status.set_status("Up to date", "ok")
            self.text.setText(escape(source.detail or "Nothing newer."))
        if not source.checked:
            self.text.setText(escape(source.detail))
        self.held.setText(f"Held back by requirements-dev.txt: {_names(update_row(item) for item in source.held)}."
                          if source.held else "")
        self.held.setVisible(bool(source.held))
        self.note.setText(source.note)
        self.note.setVisible(bool(source.note))


def _set_box_colour(box: MetricBox, colour: str) -> None:
    box.set_colour(colour)


def _text_icon(icon: QIcon, size: int) -> QIcon:
    """The icon in the theme's text color, like the text of the boxes, whatever the desktop theme."""
    pixmap = icon.pixmap(size, size)
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(current_theme().text))
    painter.end()
    return QIcon(pixmap)


def summary(result: CheckResult) -> tuple[list[str], list[str]]:
    """The tools that are missing although an installed app needs them, and the optional ones that are not
    installed (with their notes, such as a flashrom without the internal programmer)."""
    missing, optional = [], []
    for item in result.tools:
        need = tool_need(item.tool, result.installed)
        if item.path and not item.note:
            continue
        name = f"{item.tool.name} ({item.note.rstrip('.').lower()})" if item.note else item.tool.name
        if need == "required":
            missing.append(name)
        elif need == "optional":
            optional.append(name)
    return missing, optional


def confirm_text(plan: Plan) -> str:
    """The question Fix asks before it runs anything: each step with its command, and what a restart is for."""
    rows = "".join(f"<li><b>{escape(step.title)}</b><br><code>{escape(' '.join(step.command))}</code></li>"
                   for step in plan.steps)
    text = f"<p>Fix runs these commands, one after the other:</p><ul>{rows}</ul>"
    if plan.restart:
        text += ("<p>rpm-ostree changes the Bazzite image: what it installs is there after a restart, which "
                 f"{escape(APP_NAME)} never does by itself (<code>{RESTART}</code>). rpm-ostree may ask for your "
                 "password.</p>")
    if plan.manual:
        text += f"<p>Not by Fix: {escape(_names(plan.manual))}. Each app's manual says how to install them.</p>"
    return text + "<p>Run them now?</p>"


class FixDialog(QDialog):
    """Runs the steps of a Plan one after the other with QProcess and shows their output; it stops at the first
    step that fails. Closing it while a step runs stops that step."""

    def __init__(self, plan: Plan, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(window_title("Fix"))
        self.resize(760, 460)
        self.plan = plan
        self.steps = list(plan.steps)
        self.done: list[Step] = []
        self.failed: Step | None = None
        self.output = ""
        layout = QVBoxLayout(self)
        self.status = QLabel("Starting…")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.status)
        self.terminal = Terminal()
        layout.addWidget(self.terminal, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        self.buttons.setEnabled(False)
        layout.addWidget(self.buttons)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.current: Step | None = None

    def start(self) -> None:
        self._next()

    @property
    def running(self) -> bool:
        return self.current is not None

    def _append(self, text: str) -> None:
        self.output += text
        self.terminal.set_text(self.output)

    def _next(self) -> None:
        if not self.steps:
            self._end()
            return
        self.current = self.steps.pop(0)
        self.status.setText(f"<b>{escape(self.current.title)}</b>…")
        self._append(f"$ {' '.join(self.current.command)}\n")
        self.process.start(self.current.command[0], list(self.current.command[1:]))

    def _read(self) -> None:
        self._append(bytes(self.process.readAllStandardOutput()).decode(errors="replace"))

    def _finished(self, code: int, _status: QProcess.ExitStatus) -> None:
        step, self.current = self.current, None
        if step is None:
            return
        if code == 0:
            self.done.append(step)
            self._next()
        else:
            self.failed = step
            self._append(f"\n{step.command[0]} ended with {code}.\n")
            self._end()

    def _error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart and self.current is not None:
            step, self.current = self.current, None
            self.failed = step
            self._append(f"{step.command[0]} could not be started.\n")
            self._end()

    def _end(self) -> None:
        self.buttons.setEnabled(True)
        if self.failed:
            text = f"<span style='color:{RED}; font-weight:700;'>{escape(self.failed.title)} failed</span>; see below."
        else:
            text = f"<span style='color:{GREEN}; font-weight:700;'>Done.</span>"
        if any(step.restart for step in self.done):
            text += (f" Restart to use what rpm-ostree installed: <code>{RESTART}</code>. "
                     f"{escape(APP_NAME)} does not restart by itself.")
        self.status.setText(text)

    def reject(self) -> None:
        if self.running:
            self.steps.clear()
            self.process.kill()
            self.process.waitForFinished(3000)
        super().reject()


class DependencyWindow(QMainWindow):
    def __init__(
        self,
        dependencies: list[Dependency],
        tools: list[ExternalTool],
        apps: dict[str, App],
        parent: QWidget | None = None,
        check: Callable[[], CheckResult] | None = None,
        bazzite: Callable[[], BazziteState] | None = None,
        system: Callable[[], tuple[Source, ...]] | None = None,
        suite: str = DEFAULT_SUITE,
        offer_fix: bool = False,
        ask: Callable[[str], bool] | None = None,
    ):
        """*check*, *bazzite* and *system* read the packages and tools, Bazzite's state and the machine's updates,
        *ask* puts Fix's question (tests pass their own). *offer_fix* offers Fix once the first check is done
        (--fix)."""
        super().__init__(parent)
        self.resize(960, 760)
        self.suite = suite
        self.offer_fix = offer_fix
        self._ask = ask or self._ask_user
        self.plan = Plan()
        self.suite_plan = Plan()                # the packages' and tools' part of the plan
        self.sources: tuple[Source, ...] = ()   # the machine's updates, whose steps make the rest
        self.fix_dialog: FixDialog | None = None
        self.worker = UpdateChecker(self)
        self.worker.finished.connect(self._checked)
        self.bazzite_worker = UpdateChecker(self)
        self.bazzite_worker.finished.connect(self._bazzite_read)
        self._bazzite = bazzite or read_state
        self.system_worker = UpdateChecker(self)
        self.system_worker.finished.connect(self._system_read)
        self._system = system or (lambda: read_sources() + read_upstreams("seen"))
        self.system_cards: dict[str, SystemCard] = {}
        self.apps = apps
        self._check = check or (lambda: check_all(dependencies, tools, apps, INFO.user_agent))
        self.cards: dict[str, DependencyCard] = {}
        self.tool_cards: dict[str, ExternalToolCard] = {}

        central = QWidget()
        root = QVBoxLayout(central)

        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.box_packages = MetricBox("Python packages", accent())
        self.box_tools = MetricBox("Tools available", BLUE)
        self.box_missing = MetricBox("Missing", GREY)
        self.box_needs_update = MetricBox("Needs update", GREY)
        self.box_updates = MetricBox("Updates on PyPI", GREY)
        self.box_cves = MetricBox("Known CVEs", GREY)
        self.box_system = MetricBox("Updates", GREY)
        for box in (self.box_system, self.box_packages, self.box_tools, self.box_missing, self.box_needs_update,
                    self.box_updates, self.box_cves):
            header.add_second(box, 1)
        # An icon-only button the size of the boxes beside it
        self.check_button = QPushButton()
        self.check_button.setIcon(_text_icon(QIcon.fromTheme(
            "view-refresh", self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)), 32))
        self.check_button.setIconSize(QSize(32, 32))
        self.check_button.setAccessibleName("Check again")
        self.check_button.setToolTip("Check again: Bazzite's update state, the machine's updates, the apps, their "
                                     "packages and tools, and ask PyPI")
        self.check_button.setMinimumWidth(120)
        self.check_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        box_style = (surface_style(selector="QPushButton", theme=current_theme())     # a box like those beside it
                     + f"QPushButton:hover {{ border-color:{outline()}; }}")
        self.check_button.setStyleSheet(box_style)
        self.check_button.clicked.connect(self.check_updates)
        header.add_second(self.check_button, 1)
        # Fix: what is missing or must be updated, after a confirmation that lists every command
        self.fix_button = QPushButton("Fix")
        self.fix_button.setAccessibleName("Fix")
        self.fix_button.setToolTip("Nothing to fix yet: check first.")
        self.fix_button.setMinimumWidth(120)
        self.fix_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.fix_button.setStyleSheet(box_style + "QPushButton { font-size:16px; font-weight:700; }")
        self.fix_button.setEnabled(False)
        self.fix_button.clicked.connect(lambda _checked=False: self.fix())
        header.add_second(self.fix_button, 1)
        root.addLayout(header)
        about = QHBoxLayout()
        suite_name = escape(SUITE_NAMES.get(self.suite, self.suite))
        about.addWidget(hint_label(f"This machine's updates and the {suite_name}'s apps on it."), 1)
        about.addWidget(InfoButton(
            "<b>System</b> shows Bazzite's update state and what is newer on this machine: Bazzite's image, the "
            "Flatpaks, Homebrew's formulae and casks, the Rust toolchain and the checkout's development venv (within "
            "what requirements-dev.txt allows). <b>Update</b> on a card installs that source's updates; Bazzite's "
            "updater does it every night too. "
            "Each app's Python packages are checked in the environment that app runs in, compared with PyPI and "
            "looked up in OSV.dev for known vulnerabilities (CVE). External tools are checked for availability. "
            "<b>Fix</b> installs what is missing or must be updated: Python packages with pip into the app's own "
            "environment, a missing tool an installed app needs with Homebrew, else layered into the Bazzite image "
            "with rpm-ostree, and the machine's updates (a new image and layered tools are there after a restart, "
            f"<code>{RESTART}</code>, which this app never does by itself). It shows every command first and asks. "
            "Optional tools are left out; each app's manual says how to install them. Click the information button "
            "beside a name for what it is.", "What Nexus Deps checks and fixes"))
        root.addLayout(about)

        content = QWidget()
        cards_layout = QVBoxLayout(content)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(10)
        system_heading = QLabel("System")
        system_heading.setStyleSheet(header_font() + "font-size:18px; font-weight:700;")
        cards_layout.addWidget(system_heading)
        self.bazzite_card = BazziteCard()
        cards_layout.addWidget(self.bazzite_card)
        self.system_layout = QVBoxLayout()
        self.system_layout.setSpacing(10)
        self.system_waiting = hint_label("Looking for updates: Bazzite's image, the Flatpaks, Homebrew, Rust and the "
                                         "development venv…")
        self.system_layout.addWidget(self.system_waiting)
        cards_layout.addLayout(self.system_layout)
        self.apps_heading = QLabel("Emulators and firmware")
        self.apps_heading.setStyleSheet(header_font() + "font-size:18px; font-weight:700;")
        self.apps_heading.hide()                # shown when the check has cards for it
        cards_layout.addWidget(self.apps_heading)
        self.apps_layout = QVBoxLayout()
        self.apps_layout.setSpacing(10)
        cards_layout.addLayout(self.apps_layout)
        packages_heading = QLabel("Python packages")
        packages_heading.setStyleSheet(header_font() + "font-size:18px; font-weight:700;")
        cards_layout.addWidget(packages_heading)
        for dependency in dependencies:
            card = DependencyCard(dependency, apps)
            self.cards[dependency.name] = card
            cards_layout.addWidget(card)
        tools_heading = QLabel("External tools")
        tools_heading.setStyleSheet(header_font() + "font-size:18px; font-weight:700;")
        cards_layout.addWidget(tools_heading)
        for tool in tools:
            card = ExternalToolCard(tool, apps)
            self.tool_cards[tool.name] = card
            cards_layout.addWidget(card)
        cards_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        self.result_label = QLabel("Ready to check.")
        self.result_label.setWordWrap(True)
        self.result_label.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self.result_label)
        self.setCentralWidget(central)
        self.check_updates()

    def check_updates(self) -> None:
        if not self.bazzite_worker.running:
            self.bazzite_worker.start(self._bazzite)
        if not self.system_worker.running:
            self.system_waiting.setVisible(True)
            self.system_worker.start(self._system)
        self.check_button.setEnabled(False)
        if self.worker.running:
            return
        self.result_label.setText("Checking the apps, PyPI and external tools…")
        self.worker.start(self._check)

    @property
    def checking(self) -> bool:
        return self.worker.running or self.system_worker.running

    def _check_done(self) -> None:
        """Once the packages and the machine's updates are both read: Check again is back, and --fix asks."""
        if self.checking:
            return
        self.check_button.setEnabled(True)
        if self.offer_fix:
            self.offer_fix = False                  # once: the notification's Fix… button
            if self.plan:
                self.fix()

    def _bazzite_read(self, result: object) -> None:
        self.bazzite_card.show_state(result if isinstance(result, BazziteState) else
                                     BazziteState(error="Bazzite's update state could not be read."))

    def _system_read(self, result: object) -> None:
        sources = result if isinstance(result, tuple) and all(isinstance(item, Source) for item in result) else (
            Source("system", "This machine", error="The machine's updates could not be read."),)
        self.sources = sources
        self.system_waiting.setVisible(False)
        for card in self.system_cards.values():
            card.setParent(None)
            card.deleteLater()
        self.system_cards = {}
        for source in sources:
            card = SystemCard(source, self.update_source)
            self.system_cards[source.key] = card
            (self.apps_layout if source.group == "apps" else self.system_layout).addWidget(card)
        self.apps_heading.setVisible(any(source.group == "apps" for source in sources))
        count = sum(len(source.updates) for source in sources if source.outdated)
        failed = [source.name for source in sources if source.error]
        tip = system_summary(sources) or "Nothing newer on this machine."
        if failed:
            tip += f" Could not be checked: {_names(failed)}."
        self.box_system.set_value(str(count) if count or not failed else "?", tip)
        _set_box_colour(self.box_system, ORANGE if count else GREY if failed else GREEN)
        self._update_plan()
        self._check_done()

    def _checked(self, result: object) -> None:
        if (not isinstance(result, CheckResult)
                or not all(isinstance(item, DependencyStatus) for item in result.packages)
                or not all(isinstance(item, ToolStatus) for item in result.tools)):
            self.result_label.setText("The dependency check returned an invalid result.")
            self.suite_plan = Plan()
            self._update_plan()
            self._check_done()
            return
        self.suite_plan = fix_plan(result)
        self._update_plan()
        for item in result.packages:
            card = self.cards.get(item.dependency.name)
            if card is not None:
                card.show_result(item, result.installed)
        for item in result.tools:
            card = self.tool_cards.get(item.tool.name)
            if card is not None:
                card.show_result(item, result.installed)

        packages = result.packages
        failed = [item.dependency.name for item in packages if item.error]
        needs_update = [item.dependency.name for item in packages if item.needs_update and not item.missing]
        broken = [item.dependency.name for item in packages
                  if item.missing or (item.unmet and item.dependency.name not in needs_update)]
        updates = [item.dependency.name for item in packages if item.update_available]
        missing, optional = summary(result)
        available = sum(bool(item.path) and not item.note for item in result.tools)

        self.box_packages.set_value(str(len(packages)), _names(item.dependency.name for item in packages))
        self.box_tools.set_value(f"{available}/{len(result.tools)}")
        missing_count = len(missing) + len(broken)
        self.box_missing.set_value(str(missing_count), _names(broken + missing) or "Nothing an installed app needs.")
        _set_box_colour(self.box_missing, RED if missing_count else GREY)
        self.box_needs_update.set_value(str(len(needs_update)), _names(needs_update) or
                                        "Nothing must be updated.")
        _set_box_colour(self.box_needs_update, RED if needs_update else GREY)
        self.box_updates.set_value(str(len(updates)), _names(updates) or "Everything is at PyPI's latest version.")
        vulnerable = [f"{item.dependency.name} {version} ({vuln.id})" for item in packages
                      for version, vuln in item.vulnerabilities]
        cve_failed = [item.dependency.name for item in packages if item.cve_error]
        cves = {vuln.id for item in packages for _version, vuln in item.vulnerabilities}
        self.box_cves.set_value(str(len(cves)) if cves or not cve_failed else "?",
                                _names(vulnerable) or ("The check failed for " + _names(cve_failed) if cve_failed
                                                       else "No known vulnerabilities (OSV.dev)."))
        _set_box_colour(self.box_cves, RED if cves else GREY if cve_failed else GREEN)

        lines = [f"Checked {len(packages)} Python packages and {len(result.tools)} external tools."]
        if broken:
            lines.append(f"<b>Packages missing or at a wrong version:</b> {escape(_names(broken))}.")
        if needs_update:
            lines.append(f"<b>Needs update:</b> {escape(_names(needs_update))}.")
        if missing:
            lines.append(f"<b>Missing, needed by an installed app:</b> {escape(_names(missing))}.")
        if optional:
            lines.append(f"Optional, not installed: {escape(_names(optional))}.")
        if vulnerable:
            lines.append(f"<b>Known vulnerabilities:</b> {escape(_names(vulnerable))}.")
        if failed:
            lines.append(f"PyPI check failed: {escape(_names(failed))}.")
        if cve_failed:
            lines.append(f"Vulnerability check failed: {escape(_names(cve_failed))}.")
        if not (broken or needs_update or missing or optional or failed or vulnerable or cve_failed):
            lines.append(f"<span style='color:{GREEN};'>Every package and tool the installed apps use is "
                         "there.</span>")
        self.result_label.setText(" ".join(lines))
        self._check_done()

    # --- Fix ---------------------------------------------------------------------------------------------------

    def _update_plan(self) -> None:
        """Fix's plan: the packages' and tools' steps, then the machine's updates."""
        self._set_plan(Plan(self.suite_plan.steps + system_steps(self.sources), self.suite_plan.manual))

    def _set_plan(self, plan: Plan) -> None:
        self.plan = plan
        self.fix_button.setEnabled(bool(plan) and not self.fixing)
        if plan:
            self.fix_button.setToolTip("Fix: " + "; ".join(step.title for step in plan.steps))
        elif plan.manual:
            self.fix_button.setToolTip(f"Nothing Fix can install. By hand: {_names(plan.manual)}.")
        else:
            self.fix_button.setToolTip("Nothing to fix.")

    @property
    def fixing(self) -> bool:
        return self.fix_dialog is not None and self.fix_dialog.isVisible()

    def _ask_user(self, text: str) -> bool:
        box = QMessageBox(QMessageBox.Icon.Question, window_title("Fix"), text,
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    def update_source(self, step: Step) -> None:
        """A system card's Update: that source's step alone, asked and run as Fix does."""
        self.fix(Plan((step,)))

    def fix(self, plan: Plan | None = None) -> None:
        """Ask with every command listed, run them in a dialog, then check again. *plan*: one card's Update."""
        plan = plan or self.plan
        if not plan or self.fixing or not self._ask(confirm_text(plan)):
            return
        self.fix_button.setEnabled(False)
        self.fix_dialog = FixDialog(plan, self)
        self.fix_dialog.finished.connect(lambda _code: self.check_updates())
        self.fix_dialog.open()
        self.fix_dialog.start()
