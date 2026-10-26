# SPDX-License-Identifier: GPL-2.0-only
"""The main window: the first line with the logo, the title and the tab buttons, the tabs with one session each,
the menus with the keyboard shortcuts, the status bar with the current session's state, Save Log and About.
Port of src/netcatgui.cpp and netcatgui.ui. From the C++ tool's TODO: the tab bar's context menu, Rename Tab,
Tab Color, the pipes between tabs, the file pipes, the hex view, the protocol templates and the recordings."""

from __future__ import annotations

import binascii
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction, QActionGroup, QCloseEvent, QColor, QIcon, QKeySequence, QPixmap
from PyQt6.QtWidgets import (QFileDialog, QHBoxLayout, QInputDialog, QMainWindow, QMenu, QMessageBox,
                             QPushButton, QTabWidget, QVBoxLayout, QWidget)

from bc250_core.settings import open_settings
from bc250_core.widgets import AppHeader

from . import APP_ID, APP_NAME, ICONS_DIR, INFO, LOGO_PATH, __version__
from .session import (ConnectSessionWidget, Encoding, History, LineEnding, ListenSessionWidget, Protocol,
                      SessionWidget)


ORIGINAL_AUTHOR = "Shinnok (Teodor Mircea Ionita)"
ORIGINAL_EMAIL = "admin@shinnok.com"

TAB_COLORS = {"Red": "#d04545", "Orange": "#e08a1e", "Green": "#2e9e5b", "Blue": "#3c7dd9", "Purple": "#8e5bd0",
              "Grey": "#8a8f98"}

# Session > Insert Protocol Template: the first lines of a conversation with common text protocols. {host} is the
# tab's hostname. Inserting one switches the tab to "End Messages with Newline" and CRLF, which they all want.
TEMPLATES: dict[str, str] = {
    "HTTP GET /": "GET / HTTP/1.1\nHost: {host}\nUser-Agent: bazzite-netcatgui\nConnection: close\n",
    "HTTP HEAD /": "HEAD / HTTP/1.1\nHost: {host}\nUser-Agent: bazzite-netcatgui\nConnection: close\n",
    "SMTP EHLO": "EHLO {host}",
    "POP3 CAPA": "CAPA",
    "IMAP CAPABILITY": "a1 CAPABILITY",
    "FTP USER anonymous": "USER anonymous",
    "IRC NICK and USER": "NICK ncgui\nUSER ncgui 0 * :Bazzite NetcatGUI",
    "Redis PING": "PING",
    "memcached stats": "stats",
}

RECORDING_FILTER = "Session recordings (*.ncrec.json);;All files (*)"


def icon(name: str) -> QIcon:
    path = ICONS_DIR / f"{name}.png"
    return QIcon(str(path)) if path.is_file() else QIcon()


def recording_to_json(session_name: str, messages: list[tuple[float, bytes]]) -> str:
    """A recording as JSON: the messages as hex with the seconds since the previous one."""
    payload = {"app": APP_ID, "version": 1, "session": session_name,
               "messages": [{"delay": round(delay, 3), "hex": data.hex()} for delay, data in messages]}
    return json.dumps(payload, indent=1) + "\n"


def recording_from_json(text: str) -> list[tuple[float, bytes]]:
    """The messages of a recording file; ValueError when the file is not one."""
    try:
        payload = json.loads(text)
        if payload.get("app") != APP_ID or payload.get("version") != 1:
            raise ValueError("not a recording of this app")
        return [(max(0.0, float(m["delay"])), bytes.fromhex(m["hex"])) for m in payload["messages"]]
    except (KeyError, TypeError, ValueError, binascii.Error) as exc:
        raise ValueError(f"not a recording file: {exc}") from exc


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(820, 600)
        self.setMinimumSize(640, 460)
        if LOGO_PATH.exists():
            self.setWindowIcon(QIcon(str(LOGO_PATH)))

        # ~/.config/bazzite-netcatgui/bazzite-netcatgui.ini: the session defaults, the hosts and ports
        # typed before, the window size.
        self._settings = open_settings(INFO)
        self.history = History()
        self._load_settings()

        self._current: Optional[SessionWidget] = None
        self._build_ui()
        self._build_menus()
        self._apply_defaults_to_menus()
        self._update_status()

        geometry = self._settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    # -- settings -------------------------------------------------------------

    def _load_settings(self) -> None:
        s = self._settings
        self.default_encoding = Encoding.from_name(str(s.value("session/encoding", "") or ""), Encoding.UTF8)
        self.default_line_ending = LineEnding.from_name(str(s.value("session/lineEnding", "") or ""), LineEnding.LF)
        self.default_end_with_newline = s.value("session/endWithNewline", False, type=bool)
        self.default_echo_sent = s.value("session/echoSent", False, type=bool)
        self.default_auto_reconnect = s.value("session/autoReconnect", False, type=bool)
        self.default_highlight = s.value("session/highlight", True, type=bool)
        for key, items in (("hosts", self.history.hosts), ("ports", self.history.ports),
                           ("listenPorts", self.history.listen_ports)):
            saved = s.value(f"history/{key}")
            if isinstance(saved, list) and saved:
                items[:] = [str(v) for v in saved if str(v).strip()]
            elif isinstance(saved, str) and saved.strip():
                items[:] = [saved]

    def _save_settings(self) -> None:
        s = self._settings
        s.setValue("session/encoding", self.default_encoding.name)
        s.setValue("session/lineEnding", self.default_line_ending.name)
        s.setValue("session/endWithNewline", self.default_end_with_newline)
        s.setValue("session/echoSent", self.default_echo_sent)
        s.setValue("session/autoReconnect", self.default_auto_reconnect)
        s.setValue("session/highlight", self.default_highlight)
        s.setValue("history/hosts", self.history.hosts)
        s.setValue("history/ports", self.history.ports)
        s.setValue("history/listenPorts", self.history.listen_ports)
        s.setValue("window/geometry", self.saveGeometry())
        s.sync()

    # -- UI construction ------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 6)
        main_layout.setSpacing(8)

        # The first line, as in every suite app: the logo, the title with the version, and below it the app's main
        # controls: the buttons that open a tab, save and clear the log.
        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        buttons = QHBoxLayout()
        self.connect_button = QPushButton(icon("connect"), "New Connect Tab")
        self.connect_button.setToolTip("Open a tab that connects to a host (Ctrl+T)")
        self.connect_button.clicked.connect(lambda: self.new_connect_tab())
        buttons.addWidget(self.connect_button)
        self.listen_button = QPushButton(icon("listen"), "New Listen Tab")
        self.listen_button.setToolTip("Open a tab that listens on a port (Ctrl+L)")
        self.listen_button.clicked.connect(lambda: self.new_listen_tab())
        buttons.addWidget(self.listen_button)
        self.save_button = QPushButton(icon("save"), "Save Log")
        self.save_button.setToolTip("Save the current session's log to a text file (Ctrl+S)")
        self.save_button.clicked.connect(self.save_log)
        buttons.addWidget(self.save_button)
        self.clear_button = QPushButton("Clear Log")
        self.clear_button.setToolTip("Empty the current session's log (Ctrl+K)")
        self.clear_button.clicked.connect(self.clear_log)
        buttons.addWidget(self.clear_button)
        buttons.addStretch()
        header.add_second(buttons, 1)
        main_layout.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab_at)
        self.tabs.currentChanged.connect(self._on_current_tab_changed)
        self.tabs.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.tabBar().customContextMenuRequested.connect(self._on_tab_context_menu)
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self._on_tab_area_context_menu)
        main_layout.addWidget(self.tabs, 1)

        self.statusBar().showMessage("No session open")

    def _build_menus(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        self.action_save_log = self._action(file_menu, "&Save Log", "Ctrl+S", self.save_log, icon("save"))
        self.action_clear_log = self._action(file_menu, "Clear &Log", "Ctrl+K", self.clear_log)
        file_menu.addSeparator()
        self._action(file_menu, "Send &File...", "Ctrl+Shift+F", self.send_file)
        self.action_sink = self._action(file_menu, "Save &Received Data to File...", None, self._on_sink_toggled,
                                        checkable=True)
        file_menu.addSeparator()
        self._action(file_menu, "Save Session &Recording...", None, self.save_recording)
        self._action(file_menu, "Replay &Recording...", None, self.replay_recording)
        file_menu.addSeparator()
        self.action_exit = self._action(file_menu, "E&xit", "Ctrl+Q", self.close)

        edit_menu = bar.addMenu("&Edit")
        self._action(edit_menu, "&Copy", QKeySequence.StandardKey.Copy, self.copy)
        self._action(edit_menu, "&Paste", QKeySequence.StandardKey.Paste, self.paste)
        self._action(edit_menu, "Select &All", QKeySequence.StandardKey.SelectAll, self.select_all)
        edit_menu.addSeparator()
        self.template_menu = edit_menu.addMenu("Insert Protocol &Template")
        for name in TEMPLATES:
            self.template_menu.addAction(name, lambda checked=False, n=name: self.insert_template(n))

        tabs_menu = bar.addMenu("&Tabs")
        self._action(tabs_menu, "New Connec&t Tab", "Ctrl+T", lambda: self.new_connect_tab(), icon("connect"))
        self._action(tabs_menu, "New &Listen Tab", "Ctrl+L", lambda: self.new_listen_tab(), icon("listen"))
        tabs_menu.addSeparator()
        self._action(tabs_menu, "&Rename Tab...", "F2", self.rename_tab)
        self.color_menu = tabs_menu.addMenu("Tab &Color")
        self._fill_color_menu(self.color_menu)
        tabs_menu.addSeparator()
        self._action(tabs_menu, "&Close Tab", "Ctrl+W", self.close_current_tab)
        self._action(tabs_menu, "Close &Other Tabs", None, self.close_other_tabs)
        self._action(tabs_menu, "Close &All Tabs", "Ctrl+Shift+W", self.close_all_tabs)
        tabs_menu.addSeparator()
        self._action(tabs_menu, "&Next Tab", "Ctrl+Tab", lambda: self._cycle_tab(1))
        self._action(tabs_menu, "&Previous Tab", "Ctrl+Shift+Tab", lambda: self._cycle_tab(-1))

        session_menu = bar.addMenu("&Session")
        self._action(session_menu, "C&onnect / Listen", "Ctrl+O", self.connect_listen)
        self._action(session_menu, "&Disconnect / Stop", "Ctrl+D", self.disconnect)
        self._action(session_menu, "Send &Message", "Ctrl+M", self.send)
        self.action_reconnect = self._action(session_menu, "&Reconnect Automatically", None,
                                             self._on_reconnect_toggled, checkable=True)
        session_menu.addSeparator()
        self.action_newline = self._action(session_menu, "&End Messages with Newline", None,
                                           self._on_newline_toggled, checkable=True)
        ending_menu = session_menu.addMenu("Line Ending")
        self.ending_group = QActionGroup(self)
        self.ending_actions: dict[LineEnding, QAction] = {}
        for ending, label in ((LineEnding.LF, "LF (\\n)"), (LineEnding.CRLF, "CRLF (\\r\\n)")):
            action = self._action(ending_menu, label, None, None, checkable=True)
            action.setData(ending)
            self.ending_group.addAction(action)
            self.ending_actions[ending] = action
        self.ending_group.triggered.connect(self._on_line_ending_triggered)
        encoding_menu = session_menu.addMenu("Encoding")
        self.encoding_group = QActionGroup(self)
        self.encoding_actions: dict[Encoding, QAction] = {}
        for encoding, label in ((Encoding.LATIN1, "Latin-1 (ISO 8859-1)"), (Encoding.UTF8, "UTF-8"),
                                (Encoding.SYSTEM, "System")):
            action = self._action(encoding_menu, label, None, None, checkable=True)
            action.setData(encoding)
            self.encoding_group.addAction(action)
            self.encoding_actions[encoding] = action
        self.encoding_group.triggered.connect(self._on_encoding_triggered)
        self.action_echo = self._action(session_menu, "Echo Sent &Messages in the Log", None,
                                        self._on_echo_toggled, checkable=True)
        session_menu.addSeparator()
        self.action_hex_view = self._action(session_menu, "He&x View", "Ctrl+H", self._on_hex_view_toggled,
                                            checkable=True)
        self.action_hex_input = self._action(session_menu, "Hex &Input", "Ctrl+Shift+H", self._on_hex_input_toggled,
                                             checkable=True)
        self.action_highlight = self._action(session_menu, "Highlight &Protocol Lines", None,
                                             self._on_highlight_toggled, checkable=True)
        session_menu.addSeparator()
        self.pipe_menu = session_menu.addMenu("&Pipe Received Data To")
        self.pipe_menu.aboutToShow.connect(self._fill_pipe_menu)

        help_menu = bar.addMenu("&Help")
        self._action(help_menu, "&Keyboard Shortcuts", None, self.show_shortcuts)
        self._action(help_menu, "&About", None, self.show_about)

    def _action(self, menu, text: str, shortcut, slot, action_icon: Optional[QIcon] = None,
                checkable: bool = False) -> QAction:
        action = QAction(action_icon, text, self) if action_icon is not None else QAction(text, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        if slot is not None:
            if checkable:
                action.toggled.connect(slot)
            else:
                action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _fill_color_menu(self, menu: QMenu, index: Optional[int] = None) -> None:
        menu.addAction("None", lambda: self.set_tab_color("", index))
        for name, value in TAB_COLORS.items():
            swatch = QPixmap(14, 14)
            swatch.fill(QColor(value))
            menu.addAction(QIcon(swatch), name, lambda checked=False, n=name: self.set_tab_color(n, index))

    # -- tabs ---------------------------------------------------------------------

    def _session_options(self) -> dict:
        return {"history": self.history, "end_with_newline": self.default_end_with_newline,
                "line_ending": self.default_line_ending, "encoding": self.default_encoding,
                "echo_sent": self.default_echo_sent, "highlight": self.default_highlight}

    def new_connect_tab(self, host: Optional[str] = None, port: Optional[int] = None,
                        protocol: Protocol = Protocol.TCP, start: bool = False) -> ConnectSessionWidget:
        widget = ConnectSessionWidget(self, auto_reconnect=self.default_auto_reconnect, **self._session_options())
        widget.set_protocol(protocol)
        if host:
            widget.address_combo.setCurrentText(host)
        if port is not None:
            widget.port_combo.setCurrentText(str(port))
        self._add_tab(widget, icon("connect"))
        widget.address_combo.setFocus()
        if start:
            widget.start()
        return widget

    def new_listen_tab(self, port: Optional[int] = None, protocol: Protocol = Protocol.TCP,
                       start: bool = False) -> ListenSessionWidget:
        widget = ListenSessionWidget(self, **self._session_options())
        widget.set_protocol(protocol)
        if port is not None:
            widget.port_combo.setCurrentText(str(port))
        self._add_tab(widget, icon("listen"))
        widget.port_combo.setFocus()
        if start:
            widget.start()
        return widget

    def _add_tab(self, widget: SessionWidget, tab_icon: QIcon) -> None:
        widget.status_changed.connect(self._on_session_status_changed)
        self.tabs.addTab(widget, tab_icon, widget.display_name)
        self.tabs.setCurrentWidget(widget)

    def sessions(self) -> list[SessionWidget]:
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def current_session(self) -> Optional[SessionWidget]:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, SessionWidget) else None

    def close_tab_at(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is None:
            return
        self.tabs.removeTab(index)
        if isinstance(widget, SessionWidget):
            for other in self.sessions():
                if other.pipe_target is widget:
                    other.pipe_target = None
            widget.shutdown()
        widget.deleteLater()
        self._update_status()

    def close_current_tab(self) -> None:
        if self.tabs.currentIndex() != -1:
            self.close_tab_at(self.tabs.currentIndex())

    def close_other_tabs(self, keep: Optional[int] = None) -> None:
        keep_widget = self.tabs.widget(self.tabs.currentIndex() if keep is None else keep)
        for widget in self.sessions():
            if widget is not keep_widget:
                self.close_tab_at(self.tabs.indexOf(widget))

    def close_all_tabs(self) -> None:
        while self.tabs.count():
            self.close_tab_at(self.tabs.count() - 1)

    def _cycle_tab(self, step: int) -> None:
        count = self.tabs.count()
        if count:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + step) % count)

    def rename_tab(self, index: Optional[int] = None) -> None:
        index = self.tabs.currentIndex() if index is None else index
        session = self.tabs.widget(index)
        if not isinstance(session, SessionWidget):
            QMessageBox.warning(self, "No session active", "You have no session currently active, thus no tab to rename.")
            return
        title, ok = QInputDialog.getText(self, "Rename Tab", "Tab title (empty for the session's own name):",
                                         text=session.custom_title)
        if ok:
            session.custom_title = title.strip()
            self.tabs.setTabText(index, session.display_name)

    def set_tab_color(self, name: str, index: Optional[int] = None) -> None:
        index = self.tabs.currentIndex() if index is None else index
        session = self.tabs.widget(index)
        if not isinstance(session, SessionWidget):
            return
        session.tab_color = name if name in TAB_COLORS else ""
        colour = QColor(TAB_COLORS[name]) if name in TAB_COLORS else QColor()
        self.tabs.tabBar().setTabTextColor(index, colour)

    def _on_tab_context_menu(self, pos: QPoint) -> None:
        index = self.tabs.tabBar().tabAt(pos)
        menu = self.tab_context_menu(index)
        menu.exec(self.tabs.tabBar().mapToGlobal(pos))

    def _on_tab_area_context_menu(self, pos: QPoint) -> None:
        if self.tabs.tabBar().geometry().contains(pos) or self.tabs.count() == 0:
            menu = self.tab_context_menu(-1 if self.tabs.count() == 0 else self.tabs.tabBar().tabAt(
                self.tabs.tabBar().mapFrom(self.tabs, pos)))
            menu.exec(self.tabs.mapToGlobal(pos))

    def tab_context_menu(self, index: int) -> QMenu:
        """The right-click menu of a tab handle (index >= 0) or of the empty tab bar (index -1)."""
        menu = QMenu(self)
        menu.addAction(icon("connect"), "New Connect Tab", lambda: self.new_connect_tab())
        menu.addAction(icon("listen"), "New Listen Tab", lambda: self.new_listen_tab())
        if index >= 0:
            menu.addSeparator()
            menu.addAction("Rename Tab...", lambda: self.rename_tab(index))
            self._fill_color_menu(menu.addMenu("Tab Color"), index)
            menu.addSeparator()
            menu.addAction("Close Tab", lambda: self.close_tab_at(index))
            menu.addAction("Close Other Tabs", lambda: self.close_other_tabs(index))
            menu.addAction("Close All Tabs", self.close_all_tabs)
        return menu

    def _on_current_tab_changed(self, index: int) -> None:
        self._update_status()

    def _on_session_status_changed(self) -> None:
        sender = self.sender()
        if isinstance(sender, SessionWidget):
            index = self.tabs.indexOf(sender)
            if index != -1:
                self.tabs.setTabText(index, sender.display_name)
        if sender is self.current_session():
            self._update_status()
        self._save_settings()      # the host and port history grows when a session starts

    def _update_status(self) -> None:
        session = self.current_session()
        if session is None:
            self.statusBar().showMessage("No session open: Ctrl+T opens a Connect tab, Ctrl+L a Listen tab")
            self.action_reconnect.setEnabled(False)
            return
        parts = [session.encoding.value]
        if session.end_with_newline:
            parts.append(session.line_ending.value)
        if session.hex_view:
            parts.append("hex")
        text = f"{session.status} ({', '.join(parts)})"
        if session.pipe_target is not None:
            text += f"  → piped to tab '{session.pipe_target.display_name}'"
        if session.sink_path:
            text += f"  → {Path(session.sink_path).name}"
        self.statusBar().showMessage(text)
        self.tabs.setTabText(self.tabs.currentIndex(), session.display_name)
        self._apply_session_to_menus(session)

    # -- the session menu ---------------------------------------------------------

    def _apply_defaults_to_menus(self) -> None:
        self._set_menu_state(self.default_end_with_newline, self.default_line_ending, self.default_encoding,
                             self.default_echo_sent, self.default_auto_reconnect, False, False,
                             self.default_highlight, None)

    def _apply_session_to_menus(self, session: SessionWidget) -> None:
        reconnect = session.auto_reconnect if isinstance(session, ConnectSessionWidget) else None
        self._set_menu_state(session.end_with_newline, session.line_ending, session.encoding, session.echo_sent,
                             reconnect, session.hex_view, session.hex_input, session.highlighter.enabled,
                             bool(session.sink_path))

    def _set_menu_state(self, newline: bool, ending: LineEnding, encoding: Encoding, echo: bool,
                        reconnect: Optional[bool], hex_view: bool, hex_input: bool, highlight: bool,
                        sink: Optional[bool]) -> None:
        checks = [(self.action_newline, newline), (self.action_echo, echo), (self.action_hex_view, hex_view),
                  (self.action_hex_input, hex_input), (self.action_highlight, highlight)]
        if reconnect is not None:
            checks.append((self.action_reconnect, reconnect))
        if sink is not None:
            checks.append((self.action_sink, sink))
        for action, value in checks:
            action.blockSignals(True)
            action.setChecked(value)
            action.blockSignals(False)
        self.action_reconnect.setEnabled(reconnect is not None)
        self.ending_actions[ending].setChecked(True)
        self.encoding_actions[encoding].setChecked(True)

    def _on_newline_toggled(self, checked: bool) -> None:
        self.default_end_with_newline = checked
        session = self.current_session()
        if session is not None:
            session.end_with_newline = checked
        self._update_status()

    def _on_line_ending_triggered(self, action: QAction) -> None:
        self.default_line_ending = action.data()
        session = self.current_session()
        if session is not None:
            session.line_ending = action.data()
        self._update_status()

    def _on_encoding_triggered(self, action: QAction) -> None:
        self.default_encoding = action.data()
        session = self.current_session()
        if session is not None:
            session.encoding = action.data()
        self._update_status()

    def _on_echo_toggled(self, checked: bool) -> None:
        self.default_echo_sent = checked
        session = self.current_session()
        if session is not None:
            session.echo_sent = checked

    def _on_reconnect_toggled(self, checked: bool) -> None:
        self.default_auto_reconnect = checked
        session = self.current_session()
        if isinstance(session, ConnectSessionWidget):
            session.auto_reconnect = checked

    def _on_hex_view_toggled(self, checked: bool) -> None:
        session = self.current_session()
        if session is not None:
            session.set_hex_view(checked)
        self._update_status()

    def _on_hex_input_toggled(self, checked: bool) -> None:
        session = self.current_session()
        if session is not None:
            session.hex_input = checked
            session.input.setPlaceholderText(
                "Type bytes as hex: 48 65 6c 6c 6f, Enter sends" if checked else
                "Type a message, Enter sends, Shift+Enter makes a new line, Up recalls")

    def _on_highlight_toggled(self, checked: bool) -> None:
        self.default_highlight = checked
        session = self.current_session()
        if session is not None:
            session.set_highlight(checked)

    def _fill_pipe_menu(self) -> None:
        self.pipe_menu.clear()
        session = self.current_session()
        if session is None:
            self.pipe_menu.addAction("No session open").setEnabled(False)
            return
        none = self.pipe_menu.addAction("None")
        none.setCheckable(True)
        none.setChecked(session.pipe_target is None)
        none.triggered.connect(lambda: self.set_pipe(session, None))
        others = [s for s in self.sessions() if s is not session]
        if not others:
            self.pipe_menu.addAction("No other tab open").setEnabled(False)
        for other in others:
            action = self.pipe_menu.addAction(other.display_name)
            action.setCheckable(True)
            action.setChecked(session.pipe_target is other)
            action.triggered.connect(lambda checked=False, o=other: self.set_pipe(session, o))

    def set_pipe(self, session: SessionWidget, target: Optional[SessionWidget]) -> None:
        """Everything the session receives from now on is sent through the target tab's connection."""
        session.pipe_target = target if target is not session else None
        self._update_status()

    # -- session actions ------------------------------------------------------------

    def _require_session(self, what: str) -> Optional[SessionWidget]:
        session = self.current_session()
        if session is None:
            QMessageBox.warning(self, "No session active", f"You have no session currently active, thus {what}.")
        return session

    def connect_listen(self) -> None:
        session = self._require_session("you have nothing to connect")
        if session is not None:
            session.start()

    def disconnect(self) -> None:
        session = self._require_session("you have nothing to disconnect")
        if session is not None:
            session.stop()

    def send(self) -> None:
        session = self._require_session("you need a connected session in order to send messages")
        if session is not None:
            session.send_message()

    def select_all(self) -> None:
        session = self._require_session("you have nothing to select")
        if session is not None:
            session.select_all()

    def copy(self) -> None:
        session = self._require_session("you have nothing to copy")
        if session is not None:
            session.copy()

    def paste(self) -> None:
        session = self._require_session("you have nowhere to paste")
        if session is not None:
            session.paste()

    def clear_log(self) -> None:
        session = self._require_session("you have no log to clear")
        if session is not None:
            session.clear_log()

    def insert_template(self, name: str) -> None:
        """Put a protocol's opening lines in the message box and switch the tab to newline + CRLF."""
        session = self._require_session("you have nowhere to insert a template")
        if session is None:
            return
        host = session.address_combo.currentText().strip() or "localhost"
        session.input.setPlainText(TEMPLATES[name].replace("{host}", host))
        session.input.moveCursor(session.input.textCursor().MoveOperation.End)
        session.end_with_newline = True
        session.line_ending = LineEnding.CRLF
        session.hex_input = False
        self._update_status()
        session.input.setFocus()

    # -- file pipes -------------------------------------------------------------------

    def send_file(self) -> None:
        session = self._require_session("you have no connection to send a file through")
        if session is None:
            return
        if not session.can_send():
            QMessageBox.warning(self, "Cannot send file", "Connect first before trying to send a file.")
            return
        last_dir = str(self._settings.value("paths/lastFileDir", "") or "")
        file_name, _ = QFileDialog.getOpenFileName(self, "Send File", last_dir, "All files (*)")
        if not file_name:
            return
        self._settings.setValue("paths/lastFileDir", str(Path(file_name).parent))
        try:
            count = session.send_file(file_name)
        except OSError as exc:
            QMessageBox.critical(self, "File read error", f"The file could not be read:\n{exc}")
            return
        if count >= 0:
            self.statusBar().showMessage(f"Sent {Path(file_name).name} ({count} bytes)", 5000)

    def _on_sink_toggled(self, checked: bool) -> None:
        session = self.current_session()
        if session is None:
            self.action_sink.blockSignals(True)
            self.action_sink.setChecked(False)
            self.action_sink.blockSignals(False)
            QMessageBox.warning(self, "No session active", "You have no session currently active, thus nothing to save.")
            return
        if not checked:
            session.close_sink()
            self._update_status()
            return
        last_dir = str(self._settings.value("paths/lastFileDir", "") or "")
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save Received Data to File (appended)", last_dir, "All files (*)",
            options=QFileDialog.Option.DontConfirmOverwrite)
        if not file_name:
            self.action_sink.blockSignals(True)
            self.action_sink.setChecked(False)
            self.action_sink.blockSignals(False)
            return
        self._settings.setValue("paths/lastFileDir", str(Path(file_name).parent))
        try:
            session.set_sink(file_name)
        except OSError as exc:
            self.action_sink.blockSignals(True)
            self.action_sink.setChecked(False)
            self.action_sink.blockSignals(False)
            QMessageBox.critical(self, "File open error", f"The file could not be opened for writing:\n{exc}")
            return
        self._update_status()

    # -- recordings -----------------------------------------------------------------------

    def save_recording(self) -> None:
        session = self._require_session("you have no session to record")
        if session is None:
            return
        messages = session.recording_as_delays()
        if not messages:
            QMessageBox.warning(self, "Nothing recorded", "No message has been sent in this session yet.")
            return
        suggested = re.sub(r"[^A-Za-z0-9._-]+", "_", session.display_name).strip("_") or "session"
        last_dir = str(self._settings.value("paths/lastRecordingDir", "") or "")
        start = str(Path(last_dir) / f"{suggested}.ncrec.json") if last_dir else f"{suggested}.ncrec.json"
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Session Recording", start, RECORDING_FILTER)
        if not file_name:
            return
        try:
            Path(file_name).write_text(recording_to_json(session.display_name, messages), encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "File write error", f"The recording could not be written:\n{exc}")
            return
        self._settings.setValue("paths/lastRecordingDir", str(Path(file_name).parent))
        self.statusBar().showMessage(f"Recorded {len(messages)} messages to {Path(file_name).name}", 5000)

    def replay_recording(self) -> None:
        session = self._require_session("you have no connection to replay into")
        if session is None:
            return
        if not session.can_send():
            QMessageBox.warning(self, "Cannot replay", "Connect first; the recording is sent through the current tab.")
            return
        last_dir = str(self._settings.value("paths/lastRecordingDir", "") or "")
        file_name, _ = QFileDialog.getOpenFileName(self, "Replay Recording", last_dir, RECORDING_FILTER)
        if not file_name:
            return
        try:
            messages = recording_from_json(Path(file_name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Cannot read recording", f"{file_name}:\n{exc}")
            return
        self._settings.setValue("paths/lastRecordingDir", str(Path(file_name).parent))
        if not session.start_replay(messages):
            QMessageBox.warning(self, "Cannot replay", "The recording is empty or the tab cannot send.")

    # -- save log -----------------------------------------------------------------------

    @staticmethod
    def log_text(session_name: str, log: str, when: Optional[datetime] = None) -> str:
        """The saved file: the C++ tool's header, then the log."""
        stamp = (when or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        return f"--\n[{stamp}]\n{APP_NAME} log session for {session_name}\n---\n{log}\n-----\n"

    def save_log(self) -> None:
        session = self._require_session("you have no log to save")
        if session is None:
            return
        log = session.session_log()
        if not log:
            QMessageBox.warning(self, "Session log empty", "The session log is empty, thus you have nothing to save.")
            return
        suggested = re.sub(r"[^A-Za-z0-9._-]+", "_", session.display_name).strip("_") or "session"
        last_dir = str(self._settings.value("paths/lastLogDir", "") or "")
        start = str(Path(last_dir) / f"{suggested}.txt") if last_dir and Path(last_dir).is_dir() \
            else f"{suggested}.txt"
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Session Log", start, "Text files (*.txt);;All files (*)")
        if not file_name:
            return
        try:
            Path(file_name).write_text(self.log_text(session.session_name, log), encoding="utf-8", newline="")
        except OSError as exc:
            QMessageBox.critical(self, "File write error", f"The log could not be written:\n{exc}\nLog not saved.")
            return
        self._settings.setValue("paths/lastLogDir", str(Path(file_name).parent))
        QMessageBox.information(self, "Log saved successfully", "The session log has been saved successfully.")

    # -- help ---------------------------------------------------------------------------

    def show_shortcuts(self) -> None:
        rows = (("Ctrl+T", "new Connect tab"), ("Ctrl+L", "new Listen tab"), ("F2", "rename the tab"),
                ("Ctrl+W", "close tab"), ("Ctrl+Shift+W", "close all tabs"),
                ("Ctrl+Tab / Ctrl+Shift+Tab", "next / previous tab"),
                ("Ctrl+O", "connect, or listen, on the current tab"),
                ("Ctrl+D", "disconnect; on a Listen tab drop the client, then stop listening"),
                ("Enter", "send the message"), ("Shift+Enter", "new line in the message"),
                ("Up / Down", "earlier / later message in the message box"),
                ("Ctrl+M", "send the message from anywhere in the window"),
                ("Ctrl+Shift+F", "send a file"), ("Ctrl+H / Ctrl+Shift+H", "hex view / hex input"),
                ("Ctrl+S", "save the log"), ("Ctrl+K", "clear the log"),
                ("Ctrl+A / Ctrl+C / Ctrl+V", "select all, copy, paste"), ("Ctrl+Q", "quit"))
        table = "".join(f"<tr><td><b>{keys}</b>&nbsp;&nbsp;</td><td>{what}</td></tr>" for keys, what in rows)
        QMessageBox.information(self, "Keyboard Shortcuts", f"<table>{table}</table>")

    def show_about(self) -> None:
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> v{__version__}<br><br>"
            "A graphical netcat for Bazzite: connect to a host or listen on a port, TCP, UDP or TLS, one session "
            "per tab.<br><br>"
            f"The Python + Qt port of NetcatGUI 1.0 by {ORIGINAL_AUTHOR}, {ORIGINAL_EMAIL}.<br><br>"
            "License: GNU GPL version 2.<br>"
            "Icons: Silk icon set 1.3 by Mark James, famfamfam.com (CC BY 2.5).")

    # -- closing --------------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        for session in self.sessions():
            session.shutdown()
        self._save_settings()
        super().closeEvent(event)
