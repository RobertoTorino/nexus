# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings: stored preferences and the Settings panel that opens over the main window."""

from __future__ import annotations

import platform
import shutil
import subprocess
from datetime import datetime

from PyQt6.QtCore import QT_VERSION_STR, QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtCore import QPointF, QSize
from PyQt6.QtGui import (
    QKeyEvent, QMouseEvent, QPainter, QPalette, QPen, QColor, QPaintEvent, QPixmap,
)
from PyQt6.QtWidgets import (
    QAbstractButton, QCheckBox, QFrame, QHBoxLayout, QLabel, QListWidget, QPushButton, QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget,
)

from bc250_core import __version__ as CORE_VERSION
from bc250_core.settings import SettingsStore

from . import APP_NAME, INFO, LOGO_PATH, REPO_URL, ROOT, __version__
from .dashboard import ACCENT, RED, header_font
from .history import db_path
from .logstore import log_dir
from .sysoverview import SystemOverviewPage

class AppSettings(SettingsStore):
    """Preferences in ~/.config/bc250-bazzite-test/bc250-bazzite-test.ini. Defaults keep as little as possible.
    get()/set()/changed and the window state come from bc250_core's SettingsStore."""

    DEFAULTS = {
        "privacy/keep_history": True,
        "privacy/store_system_details": False,
        "privacy/mask_logs": True,
        "privacy/use_sudo": True,
        "general/notify": True,
        "run/stress_duration": 120,
        "run/stress_interval": 2,
        "run/copy_to_desktop": True,
    }

    def __init__(self, parent: QObject | None = None):
        super().__init__(INFO, parent)

    @property
    def keep_history(self) -> bool:
        return self.get("privacy/keep_history")

    @property
    def store_system_details(self) -> bool:
        return self.get("privacy/store_system_details")

    @property
    def mask_logs(self) -> bool:
        return self.get("privacy/mask_logs")

    @property
    def use_sudo(self) -> bool:
        return self.get("privacy/use_sudo")


def build_date() -> str:
    """Recorded at packaging time; else the date of the last commit (git checkout) or the newest file."""
    try:
        from ._build_info import BUILD_DATE
        return BUILD_DATE
    except ImportError:
        pass
    if shutil.which("git") and (ROOT / ".git").exists():
        try:
            out = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%cd", "--date=format:%Y-%m-%d %H:%M"],
                                 capture_output=True, text=True, timeout=3).stdout.strip()
            if out:
                return out
        except (OSError, subprocess.SubprocessError):
            pass
    newest = max((p.stat().st_mtime for p in (ROOT / "bazzite_check").glob("*.py")), default=0)
    return datetime.fromtimestamp(newest).strftime("%Y-%m-%d %H:%M") if newest else "unknown"


def _text(html: str) -> QLabel:
    label = QLabel(html)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    return label


def _heading(text: str, top: int = 0) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"font-size:16px; font-weight:700; margin-top:{top}px;")
    return label


def _note(text: str) -> QLabel:
    label = _text(text)
    label.setStyleSheet("color:#9aa0a6; margin-left:26px;")
    return label


def _scroll(inner: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(inner)
    return area


class PrivacyPage(QWidget):
    forget_sudo_requested = pyqtSignal()

    def __init__(self, settings: AppSettings, sudo_locked: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(_heading("Privacy"))
        layout.addWidget(_text(
            "<b>Nothing is sent anywhere by this app.</b> There is no telemetry, no analytics, no crash "
            "reporting, no account and no update check. Everything it stores stays on this computer."))
        layout.addWidget(_text(
            "<b>Tests that do contact the internet</b> (only when you run them):<ul>"
            "<li>04–06 network tests: ping and resolve <code>google.com</code>, open <code>https://www.example.com</code>.</li>"
            "<li>33 updates: <code>rpm-ostree upgrade --check</code> asks Bazzite's image registry for a newer image.</li>"
            "<li>44 internet speed test: Ookla's (or speedtest.net's) servers see your public IP address, and the "
            "result is stored on speedtest.net; their privacy policy applies. The GUI asks before it runs.</li></ul>"))
        layout.addWidget(_text(
            "<b>What is stored on this computer:</b><ul>"
            f"<li>GUI run logs: <code>{log_dir()}</code></li>"
            f"<li>Test history: <code>{db_path()}</code> (status and hint count per test, benchmark, "
            "stress, disk and speed numbers; no test output)</li>"
            "<li>Full test reports: <code>/var/log/bc250-bazzite-test</code> (readable by root only) "
            "and a copy in <code>~/Desktop/bc250-bazzite-test</code>. Test 45 adds the names and versions of "
            "installed packages and apps to them, but no paths, user names or container names, so a report "
            "is safe to share.</li></ul>"
            "<b>Logs &amp; history</b> in Settings removes old logs, or all logs and the history."))

        self.keep_history = QCheckBox("Keep a test history")
        layout.addWidget(self.keep_history)
        layout.addWidget(_note("The counters and button colors then survive a restart. Off: results are kept "
                               "for this session only and nothing is added to the database."))
        self.system_details = QCheckBox("Store the kernel version and CPU mitigation state in the history")
        layout.addWidget(self.system_details)
        layout.addWidget(_note("Off by default: together they show which known vulnerabilities a system may be "
                               "open to. Turning this off also removes them from earlier runs. The number of "
                               "CUs and CPU cores is always stored, it is needed to compare runs."))
        self.mask_logs = QCheckBox("Mask personal data in saved GUI logs")
        layout.addWidget(self.mask_logs)
        layout.addWidget(_note("Host and user name, home folder, drive serial numbers, MAC and IP addresses, "
                               "machine id, and the speed test's ISP and result URL are replaced by &lt;name&gt;, "
                               "&lt;serial&gt;, &lt;ip&gt;... in the log files, so they are safer to share. The "
                               "terminal still shows everything. The full reports are not masked; check "
                               "them before posting them anywhere."))

        layout.addWidget(_heading("Admin privileges", top=12))
        layout.addWidget(_text(
            "Most checks read root-only logs and hardware information, so the tests run through "
            "<code>sudo</code>. All tests are read-only: they install, change or delete nothing (the disk "
            "speed test writes one temporary file and removes it)."))
        layout.addWidget(_text(
            "<b>Your password is never shown, saved or logged.</b> When sudo needs it, a masked prompt "
            "appears; the password is handed straight to sudo and dropped from memory. sudo itself then "
            "remembers that you authenticated for its usual timeout (5 minutes on Bazzite), so you are not "
            "asked for every test."))
        self.use_sudo = QCheckBox("Run the tests with admin privileges (sudo)")
        layout.addWidget(self.use_sudo)
        self.sudo_note = _note("Off: no password is ever asked, but checks that need root report less or are skipped.")
        layout.addWidget(self.sudo_note)
        if sudo_locked:
            self.use_sudo.setEnabled(False)
            self.sudo_note.setText("Turned off for this session (the app runs as root, or in developer mode).")
        forget = QPushButton("Forget sudo authentication now")
        forget.setToolTip("Runs sudo -k: the next test that needs root asks for the password again.")
        forget.clicked.connect(self.forget_sudo_requested)
        row = QHBoxLayout()
        row.addWidget(forget)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)

        for box, key in ((self.keep_history, "privacy/keep_history"),
                         (self.system_details, "privacy/store_system_details"),
                         (self.mask_logs, "privacy/mask_logs"),
                         (self.use_sudo, "privacy/use_sudo")):
            box.setChecked(settings.get(key))
            box.toggled.connect(lambda on, k=key: settings.set(k, on))


class GeneralPage(QWidget):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(_heading("General"))
        notify = QCheckBox("Notify me when a long run finishes (1 minute or more) while I'm in another window")
        notify.setChecked(settings.get("general/notify"))
        notify.toggled.connect(lambda on: settings.set("general/notify", on))
        layout.addWidget(notify)
        copy_desktop = QCheckBox("Copy the full reports to ~/Desktop/bc250-bazzite-test after each run")
        copy_desktop.setChecked(settings.get("run/copy_to_desktop"))
        copy_desktop.toggled.connect(lambda on: settings.set("run/copy_to_desktop", on))
        layout.addWidget(copy_desktop)
        layout.addWidget(_note("The script's report, stress/disk CSVs and benchmark/speed test JSONs are then "
                               "easy to find and share. Off: they stay in /var/log/bc250-bazzite-test only."))
        layout.addStretch(1)


class PrintResultsPage(QWidget):
    print_results_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(_heading("Print results"))
        layout.addWidget(_note("Saves a compact \"BC-250 Bazzite Test Results\" card as results.png — Base and "
                               "Extended System scores on top and the other header boxes below, in a small image, "
                               "easy to share and compare with other users."))
        row = QHBoxLayout()
        print_btn = QPushButton("Print results")
        print_btn.clicked.connect(self.print_results_requested)
        row.addWidget(print_btn)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)


class AboutPage(QWidget):
    def __init__(self, script: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        logo = QLabel()
        pix = QPixmap(str(LOGO_PATH))
        if not pix.isNull():
            logo.setPixmap(pix.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        top.addWidget(logo)
        name = QLabel(f"{APP_NAME}<br><span style='font-size:14px; color:#9aa0a6;'>version {__version__}</span>")
        name.setStyleSheet(header_font() + "font-size:24px; font-weight:800;")
        top.addWidget(name, 1)
        layout.addLayout(top)
        layout.addWidget(_text(
            "<table cellspacing='6'>"
            f"<tr><td><b>Version</b></td><td>{__version__}</td></tr>"
            f"<tr><td><b>Core</b></td><td>{CORE_VERSION} (the suite's shared code, bundled with this app)</td></tr>"
            f"<tr><td><b>Build date</b></td><td>{build_date()}</td></tr>"
            f"<tr><td><b>Repository</b></td><td><a href='{REPO_URL}'>{REPO_URL}</a></td></tr>"
            "<tr><td><b>License</b></td><td><a href='https://www.gnu.org/licenses/gpl-3.0.html'>GNU GPL v3</a> or later."
            " This program comes with ABSOLUTELY NO WARRANTY. It is free software: you may redistribute and change it"
            " under the terms of that license.</td></tr>"
            f"<tr><td><b>Source code</b></td><td>Attached to every release on <a href='{REPO_URL}/releases'>"
            "GitHub releases</a>.</td></tr>"
            "<tr><td><b>Third party</b></td><td>Qt 6 (LGPL v3), PyQt6 (GPL v3), header font Inter"
            " (SIL Open Font License 1.1)</td></tr>"
            f"<tr><td><b>System</b></td><td>Qt {QT_VERSION_STR}, {platform.system()} {platform.release()}"
            "</td></tr></table>"))
        layout.addWidget(_text("Read-only diagnostics, stress test and benchmarks for the AMD BC-250 running Bazzite."))
        layout.addWidget(_text(f"Report problems or ideas on <a href='{REPO_URL}/issues'>GitHub issues</a>."))
        layout.addStretch(1)


class LogsPage(QWidget):
    """Clean up logs: the dialog itself (cleanup.CleanupDialog) is opened by the main window."""

    cleanup_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(_heading("Logs & history"))
        layout.addWidget(_text(
            "Every run leaves a log, and the stress, disk and speed tests also write CSV and JSON files. "
            "Clean them up to prevent clutter:<ul>"
            "<li><b>Older than N days</b> (default 30): removes old run logs and their history entries.</li>"
            "<li><b>Everything</b>: removes all logs and the whole test history, to start fresh.</li></ul>"
            "The dialog lists what will be removed before anything happens. Always kept: "
            "<code>bench-baseline.json</code> and the benchmark and speed test history CSVs. The full "
            "reports in <code>/var/log/bc250-bazzite-test</code> belong to root, so removing those asks for "
            "the administrator password."))
        row = QHBoxLayout()
        self.button = QPushButton("Clean up logs…")
        self.button.setToolTip("Remove logs older than a month, or all logs and the test history.")
        self.button.clicked.connect(self.cleanup_requested)
        self.button.setStyleSheet(       # red: it deletes data
            f"QPushButton {{ background:{RED}; color:white; font-weight:600; border:none; border-radius:6px; "
            "padding:6px 14px; }"
            "QPushButton:hover { background:#b71c1c; }"
            "QPushButton:pressed { background:#b71c1c; }"
            "QPushButton:disabled { background:#3a3f4b; color:#d0d0d0; }")
        row.addWidget(self.button)
        row.addStretch(1)
        layout.addLayout(row)
        self.busy = _note("Not available while tests are running.")
        self.busy.hide()
        layout.addWidget(self.busy)
        layout.addStretch(1)

    def set_running(self, running: bool) -> None:
        self.button.setEnabled(not running)
        self.busy.setVisible(running)


class CloseButton(QAbstractButton):
    """Round close button with a drawn ✕: a font glyph looks stretched or thin depending on the font."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(26, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Close (Esc)")

    def sizeHint(self) -> QSize:
        return QSize(26, 26)

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        hot = self.underMouse() or self.isDown()
        if hot:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(ACCENT).darker(120) if self.isDown() else QColor(ACCENT))
            p.drawEllipse(self.rect().adjusted(1, 1, -1, -1))
        color = QColor("white") if hot else self.palette().color(QPalette.ColorRole.WindowText)
        pen = QPen(color, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        c, r = QPointF(self.width() / 2, self.height() / 2), 4.5
        p.drawLine(c + QPointF(-r, -r), c + QPointF(r, r))
        p.drawLine(c + QPointF(-r, r), c + QPointF(r, -r))

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)


class SettingsOverlay(QWidget):
    """Dims the main window and shows the settings in a panel on top; X, Esc or a click outside closes it."""

    forget_sudo_requested = pyqtSignal()
    cleanup_requested = pyqtSignal()
    print_results_requested = pyqtSignal()
    SECTIONS = ("Privacy", "General", "System overview", "Logs & history", "About", "Print results")

    def __init__(self, settings: AppSettings, script: str, sudo_locked: bool, parent: QWidget,
                 history_provider=lambda: None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.panel = QFrame(self)
        self.panel.setObjectName("settingsPanel")
        self.panel.setStyleSheet(
            "#settingsPanel { background:palette(window); border:1px solid palette(mid); border-radius:10px; }")
        outer = QVBoxLayout(self.panel)
        outer.setContentsMargins(16, 10, 10, 16)

        head = QHBoxLayout()
        title = QLabel("Settings")
        title.setStyleSheet(header_font() + "font-size:20px; font-weight:800;")
        head.addWidget(title)
        head.addStretch(1)
        close = CloseButton()
        close.clicked.connect(self.close_overlay)
        head.addWidget(close)
        outer.addLayout(head)

        body = QHBoxLayout()
        self.sections = QListWidget()
        self.sections.setFixedWidth(150)
        self.sections.setStyleSheet(
            "QListWidget { outline:0; border:none; background:transparent; }"
            "QListWidget::item { padding:6px; margin:2px 0; border:2px solid transparent; border-radius:6px; }"
            "QListWidget::item:hover { border-color:palette(mid); }"
            "QListWidget::item:selected { background:transparent; color:palette(text);"
            f" border-color:{ACCENT}; }}")
        self.sections.addItems(self.SECTIONS)
        self.pages = QStackedWidget()
        self.privacy = PrivacyPage(settings, sudo_locked)
        self.privacy.forget_sudo_requested.connect(self.forget_sudo_requested)
        self.pages.addWidget(_scroll(self.privacy))
        self.general = GeneralPage(settings)
        self.pages.addWidget(self.general)
        self.overview = SystemOverviewPage(history_provider)
        self.pages.addWidget(_scroll(self.overview))
        self.logs = LogsPage()
        self.logs.cleanup_requested.connect(self.cleanup_requested)
        self.pages.addWidget(_scroll(self.logs))
        self.pages.addWidget(_scroll(AboutPage(script)))
        self.print_page = PrintResultsPage()
        self.print_page.print_results_requested.connect(self.print_results_requested)
        self.pages.addWidget(self.print_page)
        self.sections.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.sections.currentRowChanged.connect(self._bold)
        self.sections.currentRowChanged.connect(self._refresh_overview)
        self.sections.setCurrentRow(0)
        body.addWidget(self.sections)
        body.addWidget(self.pages, 1)
        outer.addLayout(body, 1)

        parent.installEventFilter(self)
        self.hide()

    def open(self, section: str | None = None) -> None:
        if section in self.SECTIONS:
            self.sections.setCurrentRow(self.SECTIONS.index(section))
        self._fit()
        self._refresh_overview(self.sections.currentRow())
        self.show()
        self.raise_()
        self.setFocus()

    def close_overlay(self) -> None:
        self.hide()

    def _refresh_overview(self, row: int) -> None:
        # Read only when the page is shown, so it costs nothing the rest of the time.
        if 0 <= row < len(self.SECTIONS) and self.SECTIONS[row] == "System overview":
            self.overview.refresh()

    def set_running(self, running: bool) -> None:
        self.logs.set_running(running)

    def _bold(self, row: int) -> None:
        for i in range(self.sections.count()):
            font = self.sections.item(i).font()
            font.setBold(i == row)
            self.sections.item(i).setFont(font)

    def _fit(self) -> None:
        parent = self.parentWidget()
        self.setGeometry(parent.rect())
        w = min(980, int(parent.width() * 0.8))
        h = min(760, int(parent.height() * 0.88))
        self.panel.setGeometry((parent.width() - w) // 2, (parent.height() - h) // 2, w, h)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.parentWidget() and event.type() == QEvent.Type.Resize and self.isVisible():
            self._fit()
        return super().eventFilter(obj, event)

    def paintEvent(self, event: QPaintEvent) -> None:
        QPainter(self).fillRect(self.rect(), QColor(0, 0, 0, 120))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.panel.geometry().contains(event.position().toPoint()):
            self.close_overlay()
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_overlay()
        else:
            super().keyPressEvent(event)
