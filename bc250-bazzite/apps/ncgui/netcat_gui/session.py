# SPDX-License-Identifier: GPL-2.0-only
"""One session per tab. SessionWidget is the shared part (ncsessionwidget.cpp and its .ui: the header with
address, port and start button, the session log, the message box with the Send button), ConnectSessionWidget is
the connect session (ncsessionconnectwidget.cpp) and ListenSessionWidget the listen session
(ncsessionlistenwidget.cpp). MessageInput is the message box that sends on Enter (customplaintextedit.cpp).
TCP works as in the C++ tool. From the C++ tool's TODO: UDP and TLS per tab, pipes between tabs, file pipes,
automatic reconnect, message history in the message box, the hex view and hex input, the protocol highlighter,
and the session recording that can be replayed."""

from __future__ import annotations

import codecs
import locale
import re
import time
from enum import Enum
from typing import BinaryIO, Optional

from PyQt6.QtCore import QRegularExpression, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QTextDocument
from PyQt6.QtNetwork import (QAbstractSocket, QHostAddress, QNetworkInterface, QSslSocket, QTcpServer, QTcpSocket,
                             QUdpSocket)
from PyQt6.QtWidgets import (QComboBox, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton,
                             QSizePolicy, QVBoxLayout, QWidget)

DEFAULT_PORTS = ("80", "8080", "21", "25", "23")   # the port list of ncsessionwidget.ui
HISTORY_LIMIT = 20                                 # hosts and ports remembered between runs
MESSAGE_HISTORY_LIMIT = 100                        # messages the Up/Down keys walk through
RECONNECT_SECONDS = 3                              # the pause before an automatic reconnect
SocketError = QAbstractSocket.SocketError
SocketState = QAbstractSocket.SocketState


class Encoding(Enum):
    """How typed text is turned into bytes and received bytes into text (the Session > Encoding menu)."""
    LATIN1 = "Latin-1"
    UTF8 = "UTF-8"
    SYSTEM = "System"

    @property
    def codec(self) -> str:
        if self is Encoding.LATIN1:
            return "latin-1"
        if self is Encoding.UTF8:
            return "utf-8"
        return locale.getpreferredencoding(False) or "utf-8"

    @classmethod
    def from_name(cls, name: str, default: "Encoding") -> "Encoding":
        for member in cls:
            if member.name == name or member.value == name:
                return member
        return default


class LineEnding(Enum):
    """The line break sent for a new line in a message and appended by "End messages with newline" (the C++
    tool's menu said CRLF and sent LF)."""
    LF = "LF"
    CRLF = "CRLF"

    @property
    def text(self) -> str:
        return "\n" if self is LineEnding.LF else "\r\n"

    @classmethod
    def from_name(cls, name: str, default: "LineEnding") -> "LineEnding":
        for member in cls:
            if member.name == name:
                return member
        return default


class Protocol(Enum):
    TCP = "TCP"
    UDP = "UDP"
    TLS = "TLS"      # TCP with TLS, Connect tabs only: a Listen tab would need a certificate


class History:
    """Hosts and ports typed before, shared by all tabs and saved in the settings between runs."""

    def __init__(self) -> None:
        self.hosts: list[str] = []
        self.ports: list[str] = list(DEFAULT_PORTS)
        self.listen_ports: list[str] = list(DEFAULT_PORTS)

    @staticmethod
    def remember(items: list[str], value: str) -> None:
        value = value.strip()
        if not value:
            return
        if value in items:
            items.remove(value)
        items.insert(0, value)
        del items[HISTORY_LIMIT:]


class MessageInput(QPlainTextEdit):
    """The message box: Enter sends, Shift+Enter makes a new line, Up and Down (on the first and the last line)
    walk through the messages sent before, like a shell's history; the text being typed is kept as a draft."""

    enter_pressed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._history: list[str] = []
        self._index = 0
        self._draft = ""

    @property
    def history(self) -> list[str]:
        return list(self._history)

    def remember(self, text: str) -> None:
        if text and (not self._history or self._history[-1] != text):
            self._history.append(text)
            del self._history[:-MESSAGE_HISTORY_LIMIT]
        self._index = len(self._history)
        self._draft = ""

    def _recall(self, index: int) -> None:
        self._index = index
        self.setPlainText(self._history[index] if index < len(self._history) else self._draft)
        self.moveCursor(QTextCursor.MoveOperation.End)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.enter_pressed.emit()
            return
        if key == Qt.Key.Key_Up and self.textCursor().blockNumber() == 0 and self._index > 0:
            if self._index == len(self._history):
                self._draft = self.toPlainText()
            self._recall(self._index - 1)
            return
        if key == Qt.Key.Key_Down and self._index < len(self._history) \
                and self.textCursor().blockNumber() == self.document().blockCount() - 1:
            self._recall(self._index + 1)
            return
        super().keyPressEvent(event)


def local_addresses() -> list[str]:
    """The interfaces a Listen tab can bind to: the machine's addresses, loopback, and "any" (the default)."""
    addresses: list[str] = []
    for address in QNetworkInterface.allAddresses():
        text = address.toString()
        if text and text not in addresses:
            addresses.append(text)
    for text in ("127.0.0.1", "::1", "0.0.0.0", "::"):
        if text not in addresses:
            addresses.append(text)
    return addresses


def hexdump(data: bytes, width: int = 16) -> str:
    """The classic hexdump: offset, the bytes in hex, the printable ASCII; one line per 16 bytes."""
    lines = []
    for offset in range(0, len(data), width):
        chunk = data[offset:offset + width]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{offset:08x}  {hex_part:<{width * 3 - 1}}  |{ascii_part}|")
    return "\n".join(lines) + ("\n" if lines else "")


def parse_hex(text: str) -> bytes:
    """Bytes typed as hex: "48 65 6c", "48:65:6c", "0x48 0x65", "\\x48\\x65" or "48656c" all give b"Hel"."""
    cleaned = re.sub(r"(0x|\\x)", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\s,:;-]+", "", cleaned)
    if not cleaned:
        return b""
    if len(cleaned) % 2 or not re.fullmatch(r"[0-9a-fA-F]+", cleaned):
        raise ValueError("hex input needs an even number of hex digits (0-9, a-f), spaces are fine")
    return bytes.fromhex(cleaned)


class ProtocolHighlighter(QSyntaxHighlighter):
    """Colors the lines text protocols produce: requests and commands, status and reply lines, header names,
    error replies, and the direction markers of the hex view. Plain data stays as it is."""

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self.enabled = True

        def fmt(colour: str, bold: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(colour))
            if bold:
                f.setFontWeight(QFont.Weight.Bold)
            return f

        self.rules: list[tuple[QRegularExpression, int, QTextCharFormat]] = [
            # HTTP requests and the commands of SMTP, POP3, IMAP, FTP, IRC, Redis, memcached.
            (QRegularExpression(r"^(GET|POST|PUT|DELETE|HEAD|OPTIONS|PATCH|CONNECT|TRACE) \S+ HTTP/\d(\.\d)?$"),
             0, fmt("#81c784", True)),
            (QRegularExpression(r"^(EHLO|HELO|MAIL FROM|RCPT TO|DATA|QUIT|USER|PASS|STAT|LIST|RETR|CAPA|NICK|JOIN|"
                                r"PRIVMSG|PING|PONG|STATS|SET|\w+ (CAPABILITY|LOGIN|SELECT|FETCH|LOGOUT))\b.*$",
                                QRegularExpression.PatternOption.CaseInsensitiveOption), 0, fmt("#81c784")),
            # Status lines: HTTP, and the three-digit replies of SMTP, FTP, IRC and friends.
            (QRegularExpression(r"^HTTP/\d(\.\d)? [123]\d\d\b.*$"), 0, fmt("#d2691e", True)),
            (QRegularExpression(r"^[123]\d\d[ -].*$"), 0, fmt("#d2691e")),
            # Errors: HTTP 4xx/5xx, SMTP/FTP 4xx/5xx, POP3 -ERR, Redis -ERR, memcached ERROR.
            (QRegularExpression(r"^(HTTP/\d(\.\d)? [45]\d\d\b.*|[45]\d\d[ -].*|-ERR.*|ERROR.*|-.*)$"),
             0, fmt("#e57373", True)),
            # Replies that start with + (POP3 +OK, Redis +PONG) and header names.
            (QRegularExpression(r"^\+.*$"), 0, fmt("#d2691e")),
            (QRegularExpression(r"^([A-Za-z][A-Za-z0-9-]*):\s"), 1, fmt("#3c7dd9", True)),
            # The hex view's direction markers.
            (QRegularExpression(r"^(<<|>>) \d+ bytes.*$"), 0, fmt("#8a8f98", True)),
        ]

    def set_enabled(self, enabled: bool) -> None:
        if enabled != self.enabled:
            self.enabled = enabled
            self.rehighlight()

    def matching_rules(self, line: str) -> list[int]:
        """The indexes of the rules a line matches (for the tests)."""
        return [i for i, (pattern, _, _) in enumerate(self.rules) if pattern.match(line).hasMatch()]

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        if not self.enabled or not text:
            return
        for pattern, group, char_format in self.rules:
            match = pattern.match(text)
            if match.hasMatch():
                self.setFormat(match.capturedStart(group), match.capturedLength(group), char_format)


class SessionWidget(QWidget):
    """What the connect and the listen session share: the widgets, the settings and the message handling."""

    status_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None, *, history: Optional[History] = None,
                 end_with_newline: bool = False, line_ending: LineEnding = LineEnding.LF,
                 encoding: Encoding = Encoding.UTF8, echo_sent: bool = False, highlight: bool = True) -> None:
        super().__init__(parent)
        self.history = history if history is not None else History()
        self.end_with_newline = end_with_newline
        self.line_ending = line_ending
        self._encoding = encoding
        self.echo_sent = echo_sent
        self._session_name = ""
        self._status = "Disconnected"
        self.custom_title = ""                         # Rename Tab; empty means the session's own name
        self.tab_color = ""                            # Tab Color, a color name or empty
        self.hex_view = False                          # the log as a hexdump instead of text
        self.hex_input = False                         # the message box holds hex digits instead of text
        self.pipe_target: Optional["SessionWidget"] = None   # received data is sent on through this tab
        self.sink_path = ""                            # received data is also appended to this file
        self._sink: Optional[BinaryIO] = None
        self._chunks: list[tuple[bool, bytes]] = []    # what the log holds: (incoming, data), for re-rendering
        self._decoder = codecs.getincrementaldecoder(self._encoding.codec)(errors="replace")
        self.recording: list[tuple[float, bytes]] = []  # every message sent, with the time, for a replay
        self._replay: list[tuple[float, bytes]] = []
        self._replay_index = 0
        self._replay_timer = QTimer(self)
        self._replay_timer.setSingleShot(True)
        self._replay_timer.timeout.connect(self._replay_next)
        self._build_ui()
        self.highlighter = ProtocolHighlighter(self.log.document())
        self.highlighter.enabled = highlight

    # -- widgets ----------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.header = QGroupBox("Session")
        header_row = QHBoxLayout(self.header)
        self.address_label = QLabel("Hostname:")
        header_row.addWidget(self.address_label)
        self.address_combo = QComboBox()
        self.address_combo.setEditable(True)
        self.address_combo.setInsertPolicy(QComboBox.InsertPolicy.InsertAtTop)
        self.address_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.address_combo.setMinimumWidth(160)
        header_row.addWidget(self.address_combo, 1)
        self.port_label = QLabel("Port:")
        header_row.addWidget(self.port_label)
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setInsertPolicy(QComboBox.InsertPolicy.InsertAtTop)
        self.port_combo.setToolTip("Range between 1 and 65535")
        self.port_combo.setMinimumWidth(90)
        header_row.addWidget(self.port_combo)
        self.protocol_combo = QComboBox()
        for protocol in Protocol:
            self.protocol_combo.addItem(protocol.value, protocol)
        self.protocol_combo.setToolTip("TCP, UDP, or TCP with TLS")
        header_row.addWidget(self.protocol_combo)
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.on_start_button)
        header_row.addWidget(self.start_button)
        layout.addWidget(self.header)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setUndoRedoEnabled(False)
        layout.addWidget(self.log, 1)

        footer = QHBoxLayout()
        self.input = MessageInput()
        self.input.setPlaceholderText("Type a message, Enter sends, Shift+Enter makes a new line, Up recalls")
        self.input.setToolTip("Use Shift+Enter for new line; Up and Down walk through the messages sent before")
        self.input.setTabChangesFocus(True)
        self.input.setFixedHeight(self.input.fontMetrics().lineSpacing() * 3 + 12)
        self.input.enter_pressed.connect(self.send_message)
        footer.addWidget(self.input, 1)
        self.send_button = QPushButton("Send")
        self.send_button.setToolTip("Send Message (Enter)")
        self.send_button.setEnabled(False)
        self.send_button.clicked.connect(self.send_message)
        footer.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(footer)

    def _set_inputs_locked(self, locked: bool) -> None:
        for widget in (self.address_combo, self.port_combo, self.protocol_combo):
            widget.setEnabled(not locked)

    # -- state ----------------------------------------------------------------

    @property
    def session_name(self) -> str:
        return self._session_name

    def set_session_name(self, name: str) -> None:
        self._session_name = name

    @property
    def display_name(self) -> str:
        """The tab's title: the name given with Rename Tab, else the session's own name."""
        return self.custom_title or self._session_name

    @property
    def status(self) -> str:
        if self.is_replaying:
            return f"{self._status}, replaying {self._replay_index}/{len(self._replay)}"
        return self._status

    def set_status(self, message: str) -> None:
        """The status bar text (without the encoding); emits status_changed so the window refreshes."""
        self._status = message
        self.status_changed.emit()

    @property
    def encoding(self) -> Encoding:
        return self._encoding

    @encoding.setter
    def encoding(self, encoding: Encoding) -> None:
        self._encoding = encoding
        self._decoder = codecs.getincrementaldecoder(encoding.codec)(errors="replace")

    @property
    def protocol(self) -> Protocol:
        return self.protocol_combo.currentData()

    def set_protocol(self, protocol: Protocol) -> None:
        index = self.protocol_combo.findData(protocol)
        if index != -1:
            self.protocol_combo.setCurrentIndex(index)

    @property
    def is_active(self) -> bool:
        """Connected or connecting (connect tab); listening, with or without a client (listen tab)."""
        raise NotImplementedError

    def can_send(self) -> bool:
        raise NotImplementedError

    def start(self) -> None:
        """Connect or listen (Ctrl+O, the start button)."""
        raise NotImplementedError

    def stop(self) -> None:
        """One step back (Ctrl+D): disconnect, or on a listen tab drop the client, else stop listening."""
        raise NotImplementedError

    def shutdown(self) -> None:
        """Close everything without dialogs: the tab is closing."""
        self.stop_replay()
        self.close_sink()
        self.pipe_target = None

    def on_start_button(self) -> None:
        if self.is_active:
            self.stop()
        else:
            self.start()

    # -- port and address checks ------------------------------------------------

    def _port_from_combo(self) -> Optional[int]:
        text = self.port_combo.currentText().strip()
        if not text:
            QMessageBox.warning(self, "No port specified", "You need to specify a port number.")
            return None
        try:
            port = int(text)
        except ValueError:
            port = 0
        if not 1 <= port <= 65535:
            QMessageBox.warning(self, "Invalid port", "The port number you typed is invalid. Valid range is 1-65535.")
            return None
        return port

    # -- the session log ----------------------------------------------------------

    def session_log(self) -> str:
        return self.log.toPlainText()

    def clear_log(self) -> None:
        self._chunks.clear()
        self.log.clear()

    def _append_plain(self, text: str) -> None:
        """Text goes at the end of the log as it arrives, without an extra line break per chunk: the C++ tool's
        appendPlainText() put every chunk on a line of its own. The text widget shows CRLF and a lone CR as one
        line break, so Save Log writes LF where the wire had CRLF (as the C++ tool did)."""
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()

    def _render_chunk(self, incoming: bool, data: bytes) -> None:
        if self.hex_view:
            marker = "<<" if incoming else ">>"
            self._append_plain(f"{marker} {len(data)} bytes\n{hexdump(data)}")
        elif incoming:
            self._append_plain(self._decoder.decode(data))   # incremental: a character split over two chunks survives
        else:
            self._append_plain(data.decode(self._encoding.codec, errors="replace"))

    def _record(self, incoming: bool, data: bytes) -> None:
        """One chunk for the log, and, when incoming, for the file sink and the piped tab."""
        self._chunks.append((incoming, data))
        self._render_chunk(incoming, data)
        if not incoming:
            return
        if self._sink is not None:
            try:
                self._sink.write(data)
                self._sink.flush()
            except OSError as exc:
                path = self.sink_path
                self.close_sink()
                QMessageBox.critical(self, "File write error", f"Could not write received data to {path}:\n{exc}")
        if self.pipe_target is not None:
            self.pipe_target.send_raw(data)

    def show_received(self, data: bytes) -> None:
        self._record(True, data)

    def set_hex_view(self, enabled: bool) -> None:
        """Switch the log between text and hexdump; everything received so far is shown again the new way."""
        if enabled == self.hex_view:
            return
        self.hex_view = enabled
        self.log.clear()
        self._decoder.reset()
        for incoming, data in self._chunks:
            self._render_chunk(incoming, data)

    def set_highlight(self, enabled: bool) -> None:
        self.highlighter.set_enabled(enabled)

    # -- file pipes -------------------------------------------------------------------

    def set_sink(self, path: str) -> None:
        """Append every received byte to this file from now on (nc > file)."""
        self.close_sink()
        self._sink = open(path, "ab")
        self.sink_path = path
        self.status_changed.emit()

    def close_sink(self) -> None:
        if self._sink is not None:
            try:
                self._sink.close()
            except OSError:
                pass
        self._sink = None
        if self.sink_path:
            self.sink_path = ""
            self.status_changed.emit()

    def send_file(self, path: str) -> int:
        """Send a file's bytes as they are (nc < file); returns the byte count, -1 when nothing could be sent.
        OSError when the file cannot be read."""
        with open(path, "rb") as handle:
            data = handle.read()
        if not self.can_send():
            QMessageBox.warning(self, "Cannot send file", self._cannot_send_reason())
            return -1
        if data and not self.send_raw(data):
            return -1
        return len(data)

    # -- edit menu ----------------------------------------------------------------

    def select_all(self) -> None:
        if self.input.hasFocus():
            self.input.selectAll()
        else:
            self.log.selectAll()

    def copy(self) -> None:
        if self.input.hasFocus():
            self.input.copy()
        else:
            self.log.copy()

    def paste(self) -> None:
        self.input.paste()

    # -- sending ------------------------------------------------------------------

    def outgoing_bytes(self) -> Optional[bytes]:
        """The message box as bytes: hex digits when Hex Input is on, else the text with its line breaks in the
        session's line ending and that line ending appended when the session says so. None when hex is invalid."""
        text = self.input.toPlainText()
        if not text:
            return b""
        if self.hex_input:
            try:
                return parse_hex(text)
            except ValueError as exc:
                QMessageBox.warning(self, "Invalid hex input", str(exc).capitalize() + ".")
                return None
        if self.end_with_newline:
            text += "\n"
        if self.line_ending is not LineEnding.LF:
            text = text.replace("\n", self.line_ending.text)
        return text.encode(self._encoding.codec, errors="replace")

    def send_message(self) -> None:
        if not self.can_send():
            QMessageBox.warning(self, "Cannot send message", self._cannot_send_reason())
            return
        data = self.outgoing_bytes()
        if data is None:
            return
        if data and not self.send_raw(data):
            return
        self.input.remember(self.input.toPlainText())
        self.input.clear()

    def send_raw(self, data: bytes) -> bool:
        """Bytes to the connection, recorded for a replay and, with Echo on, shown in the log."""
        if not self.can_send() or not data:
            return False
        if not self._write(data):
            return False
        self.recording.append((time.monotonic(), data))
        if self.echo_sent:
            self._record(False, data)
        return True

    def _cannot_send_reason(self) -> str:
        return "Connect first before trying to send messages."

    def _write(self, data: bytes) -> bool:
        raise NotImplementedError

    # -- replay -------------------------------------------------------------------------

    def recording_as_delays(self) -> list[tuple[float, bytes]]:
        """The recording as (seconds since the previous message, data); the first delay is 0."""
        result = []
        previous = None
        for stamp, data in self.recording:
            result.append((0.0 if previous is None else max(0.0, stamp - previous), data))
            previous = stamp
        return result

    @property
    def is_replaying(self) -> bool:
        return self._replay_index < len(self._replay)

    def start_replay(self, messages: list[tuple[float, bytes]]) -> bool:
        """Send these (delay, data) messages with their delays; the first goes out at once."""
        if not messages or not self.can_send():
            return False
        self._replay = list(messages)
        self._replay_index = 0
        self._replay_next()
        return True

    def stop_replay(self) -> None:
        self._replay_timer.stop()
        if self._replay:
            self._replay = []
            self._replay_index = 0
            self.status_changed.emit()

    def _replay_next(self) -> None:
        if not self.is_replaying:
            return
        _, data = self._replay[self._replay_index]
        if not self.send_raw(data):
            self.stop_replay()
            return
        self._replay_index += 1
        if self.is_replaying:
            self._replay_timer.start(int(self._replay[self._replay_index][0] * 1000))
        self.status_changed.emit()


class ConnectSessionWidget(SessionWidget):
    """A tab that connects to a host: TCP (as the C++ tool), UDP, or TLS; with "Reconnect Automatically" it
    connects again a few seconds after the connection drops or fails, until Disconnect."""

    def __init__(self, parent: Optional[QWidget] = None, auto_reconnect: bool = False, **options) -> None:
        super().__init__(parent, **options)
        self.set_session_name("Connect")
        self.header.setTitle("Connect to")
        self.address_label.setText("Hostname:")
        self.address_combo.setToolTip("Hostname to connect to, as a name or an IP address")
        self.address_combo.addItems(self.history.hosts)
        self.address_combo.setCurrentText("")
        self.port_combo.setToolTip("Port to connect to")
        self.port_combo.addItems(self.history.ports)
        self.start_button.setText("Connect")
        self.auto_reconnect = auto_reconnect
        self._socket: Optional[QAbstractSocket] = None
        self._target: Optional[tuple[str, int]] = None
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._reconnect)

    @property
    def is_active(self) -> bool:
        return self._socket is not None or self._reconnect_timer.isActive()

    def can_send(self) -> bool:
        socket = self._socket
        if socket is None or socket.state() != SocketState.ConnectedState:
            return False
        return socket.isEncrypted() if isinstance(socket, QSslSocket) else True

    def start(self) -> None:
        if self.is_active:
            QMessageBox.warning(self, "Already Connected", "You are already connected. Disconnect first.")
            return
        host = self.address_combo.currentText().strip()
        if not host:
            QMessageBox.warning(self, "No host specified",
                                "You need to type a hostname, as a domain name or an IP address, to connect to.")
            return
        port = self._port_from_combo()
        if port is None:
            return
        History.remember(self.history.hosts, host)
        History.remember(self.history.ports, str(port))
        if self.address_combo.findText(host) == -1:
            self.address_combo.insertItem(0, host)
        if self.port_combo.findText(str(port)) == -1:
            self.port_combo.insertItem(0, str(port))
        self._target = (host, port)
        self._connect(host, port)

    def _connect(self, host: str, port: int) -> None:
        protocol = self.protocol
        if protocol is Protocol.UDP:
            socket: QAbstractSocket = QUdpSocket(self)
        elif protocol is Protocol.TLS:
            ssl_socket = QSslSocket(self)
            ssl_socket.encrypted.connect(self._on_encrypted)
            ssl_socket.sslErrors.connect(self._on_ssl_errors)
            socket = ssl_socket
        else:
            socket = QTcpSocket(self)
        socket.connected.connect(self._on_connected)
        socket.disconnected.connect(self._on_disconnected)
        socket.errorOccurred.connect(self._on_error)
        socket.readyRead.connect(self._on_ready_read)
        self._socket = socket
        self._set_inputs_locked(True)
        self.start_button.setText("Disconnect")
        self.set_status("Connecting..." if protocol is not Protocol.TLS else "Connecting (TLS)...")
        if isinstance(socket, QSslSocket):
            socket.connectToHostEncrypted(host, port)
        else:
            socket.connectToHost(host, port)   # the name lookup happens in the socket; the C++ tool blocked on it

    def stop(self) -> None:
        if not self.is_active:
            QMessageBox.warning(self, "Not Connected", "You need to be connected in order to disconnect.")
            return
        self._reconnect_timer.stop()
        self._teardown("Disconnected")

    def shutdown(self) -> None:
        super().shutdown()
        self._reconnect_timer.stop()
        if self._socket is not None:
            self._teardown("Disconnected")

    def _teardown(self, status: str) -> None:
        self.stop_replay()
        socket, self._socket = self._socket, None
        if socket is not None:
            socket.blockSignals(True)
            if socket.state() == SocketState.ConnectedState:
                socket.flush()                  # a message sent just before Disconnect still goes out
            socket.abort()
            socket.deleteLater()
        self.send_button.setEnabled(False)
        self.start_button.setText("Connect")
        self._set_inputs_locked(False)
        self.set_status(status)

    def _lost(self, status: str) -> bool:
        """The connection dropped or failed: with automatic reconnect on, wait and try again (no dialog)."""
        if self.auto_reconnect and self._target is not None:
            self._teardown(f"{status}, reconnecting in {RECONNECT_SECONDS} s...")
            self.start_button.setText("Disconnect")
            self._set_inputs_locked(True)
            self._reconnect_timer.start(RECONNECT_SECONDS * 1000)
            return True
        self._teardown(status)
        return False

    def _reconnect(self) -> None:
        if self._socket is None and self.auto_reconnect and self._target is not None:
            self._connect(*self._target)

    def _mark_connected(self, label: str) -> None:
        socket = self._socket
        if socket is None:
            return
        peer = socket.peerName() or socket.peerAddress().toString()
        self.set_session_name(f"{peer}:{socket.peerPort()}")
        self.send_button.setEnabled(True)
        self.start_button.setText("Disconnect")
        self.set_status(label)

    def _on_connected(self) -> None:
        protocol = self.protocol
        if protocol is Protocol.TLS:
            self.set_status("Handshaking (TLS)...")
        else:
            self._mark_connected("Connected" if protocol is Protocol.TCP else "Connected (UDP)")

    def _on_encrypted(self) -> None:
        self._mark_connected("Connected (TLS)")

    def _on_ssl_errors(self, errors: list) -> None:
        socket = self._socket
        if not isinstance(socket, QSslSocket):
            return
        details = "\n".join(error.errorString() for error in errors)
        answer = QMessageBox.question(
            self, "Certificate problem",
            f"The server's certificate could not be verified:\n{details}\n\nConnect anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            socket.ignoreSslErrors()
        else:
            self._reconnect_timer.stop()
            self._teardown("Disconnected")

    def _on_disconnected(self) -> None:
        if self._socket is not None:
            self._lost("Disconnected by peer")

    def _on_error(self, error: QAbstractSocket.SocketError) -> None:
        socket = self._socket
        if socket is None:
            return
        if error == SocketError.RemoteHostClosedError:
            self._lost("Disconnected by peer")   # no dialog: the status bar says it (the C++ tool popped one)
            return
        text = socket.errorString()
        if self._lost("Disconnected"):
            return
        if error == SocketError.ConnectionRefusedError:
            QMessageBox.critical(self, "Connection refused", "The connection was refused by the peer (or timed out).")
        elif error == SocketError.HostNotFoundError:
            QMessageBox.critical(self, "Hostname fail", "The hostname dns lookup has failed or ip address invalid.")
        elif error == SocketError.SslHandshakeFailedError:
            QMessageBox.critical(self, "TLS handshake failed", f"The TLS handshake failed: {text}.")
        else:
            QMessageBox.critical(self, "Network error", f"The following network error occurred: {text}.")

    def _on_ready_read(self) -> None:
        socket = self._socket
        if socket is None:
            return
        if isinstance(socket, QUdpSocket):
            while socket.hasPendingDatagrams():
                self.show_received(socket.receiveDatagram().data().data())
        else:
            self.show_received(socket.readAll().data())

    def _write(self, data: bytes) -> bool:
        assert self._socket is not None
        return self._socket.write(data) != -1


class ListenSessionWidget(SessionWidget):
    """A tab that listens on a port: TCP with one client at a time (as the C++ tool), or UDP, where the last
    sender is the peer that Send goes to. No TLS: that would need a certificate."""

    def __init__(self, parent: Optional[QWidget] = None, **options) -> None:
        super().__init__(parent, **options)
        self.set_session_name("Listen")
        self.header.setTitle("Listen on")
        self.address_label.setText("Interface:")
        self.address_combo.setEditable(False)
        self.address_combo.setToolTip("Interface to listen on")
        self.address_combo.addItems(local_addresses())
        self.address_combo.setCurrentIndex(self.address_combo.findText("0.0.0.0"))
        self.port_combo.setToolTip("Port to listen on")
        self.port_combo.addItems(self.history.listen_ports)
        self.protocol_combo.removeItem(self.protocol_combo.findData(Protocol.TLS))
        self.protocol_combo.setToolTip("TCP or UDP")
        self.start_button.setText("Listen")
        self._server: Optional[QTcpServer] = None
        self._client: Optional[QTcpSocket] = None
        self._udp: Optional[QUdpSocket] = None
        self._udp_peer: Optional[tuple[QHostAddress, int]] = None

    @property
    def is_active(self) -> bool:
        return self._server is not None or self._udp is not None

    @property
    def has_client(self) -> bool:
        return self._client is not None

    @property
    def udp_peer(self) -> Optional[tuple[str, int]]:
        if self._udp_peer is None:
            return None
        return self._udp_peer[0].toString(), self._udp_peer[1]

    def can_send(self) -> bool:
        if self._client is not None:
            return self._client.state() == SocketState.ConnectedState
        return self._udp is not None and self._udp_peer is not None

    def _cannot_send_reason(self) -> str:
        if self._udp is not None:
            return "No peer yet: a message must arrive first, Send then answers its sender."
        return "You must have a client connected before trying to send messages."

    def start(self) -> None:
        if self.is_active:
            QMessageBox.warning(self, "Already Listening", "You already started listening.")
            return
        port = self._port_from_combo()
        if port is None:
            return
        address = QHostAddress(self.address_combo.currentText())
        if self.protocol is Protocol.TCP:
            server = QTcpServer(self)
            server.setMaxPendingConnections(1)
            server.newConnection.connect(self._on_new_connection)
            if not server.listen(address, port):
                error = server.errorString()
                server.deleteLater()
                QMessageBox.critical(self, "Cannot start listen",
                                     f"Could not bind to the specified port and interface.\n{error}")
                return
            self._server = server
            bound = f"{server.serverAddress().toString()}:{server.serverPort()}"
        else:
            udp = QUdpSocket(self)
            if not udp.bind(address, port):
                error = udp.errorString()
                udp.deleteLater()
                QMessageBox.critical(self, "Cannot start listen",
                                     f"Could not bind to the specified port and interface.\n{error}")
                return
            udp.readyRead.connect(self._on_udp_ready_read)
            self._udp = udp
            bound = f"{udp.localAddress().toString()}:{udp.localPort()}"
        History.remember(self.history.listen_ports, str(port))
        if self.port_combo.findText(str(port)) == -1:
            self.port_combo.insertItem(0, str(port))
        self.set_session_name(bound)
        self._set_inputs_locked(True)
        self.start_button.setText("Stop")
        self.set_status(self._listening_status())

    def _listening_status(self) -> str:
        if self._udp is None:
            return "Listening"
        if self._udp_peer is None:
            return "Listening (UDP)"
        return f"Listening (UDP, peer {self._udp_peer[0].toString()}:{self._udp_peer[1]})"

    def stop(self) -> None:
        if self._client is not None:
            self._drop_client()
            self.set_status("Listening")
            return
        if not self.is_active:
            QMessageBox.warning(self, "Not Listening", "Listening not started.")
            return
        self._stop_listening()

    def shutdown(self) -> None:
        super().shutdown()
        if self._client is not None:
            self._drop_client()
        if self.is_active:
            self._stop_listening()

    def _stop_listening(self) -> None:
        self.stop_replay()
        if self._server is not None:
            self._server.close()
            self._server.deleteLater()
            self._server = None
        if self._udp is not None:
            self._udp.blockSignals(True)
            self._udp.close()
            self._udp.deleteLater()
            self._udp = None
        self._udp_peer = None
        self.send_button.setEnabled(False)
        self.start_button.setText("Listen")
        self._set_inputs_locked(False)
        self.set_status("Disconnected")

    def _drop_client(self) -> None:
        self.stop_replay()
        client, self._client = self._client, None
        if client is not None:
            client.blockSignals(True)
            if client.state() == SocketState.ConnectedState:
                client.flush()
            client.abort()
            client.deleteLater()
        self.send_button.setEnabled(False)
        self.start_button.setText("Stop")

    def _on_new_connection(self) -> None:
        server = self._server
        if server is None:
            return
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            if self._client is not None:      # one client at a time, like nc -l; a second one is turned away
                socket.abort()
                socket.deleteLater()
                continue
            socket.readyRead.connect(self._on_client_ready_read)
            socket.disconnected.connect(self._on_client_disconnected)
            socket.errorOccurred.connect(self._on_client_error)
            self._client = socket
            self.send_button.setEnabled(True)
            self.start_button.setText("Disconnect")
            self.set_status(f"Connected (client {socket.peerAddress().toString()}:{socket.peerPort()})")
            if socket.bytesAvailable():
                self._on_client_ready_read()

    def _on_client_ready_read(self) -> None:
        if self._client is not None:
            self.show_received(self._client.readAll().data())

    def _on_client_disconnected(self) -> None:
        if self._client is not None:
            self._drop_client()
            self.set_status("Listening")

    def _on_client_error(self, error: QAbstractSocket.SocketError) -> None:
        client = self._client
        if client is None or error == SocketError.RemoteHostClosedError:
            return                            # the disconnected signal follows and resets the tab
        text = client.errorString()
        self._drop_client()
        self.set_status("Listening")
        QMessageBox.critical(self, "Network error", f"The following network error occurred: {text}.")

    def _on_udp_ready_read(self) -> None:
        udp = self._udp
        if udp is None:
            return
        while udp.hasPendingDatagrams():
            datagram = udp.receiveDatagram()
            peer = (datagram.senderAddress(), datagram.senderPort())
            if self._udp_peer is None or self._udp_peer[0] != peer[0] or self._udp_peer[1] != peer[1]:
                self._udp_peer = peer
                self.send_button.setEnabled(True)
                self.set_status(self._listening_status())
            self.show_received(datagram.data().data())

    def _write(self, data: bytes) -> bool:
        if self._client is not None:
            return self._client.write(data) != -1
        assert self._udp is not None and self._udp_peer is not None
        return self._udp.writeDatagram(data, self._udp_peer[0], self._udp_peer[1]) != -1
