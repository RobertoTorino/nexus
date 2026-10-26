# SPDX-License-Identifier: GPL-2.0-only
"""The features from the C++ tool's TODO: pipes between tabs, file pipes, automatic reconnect, TLS, the message
history, the hex view and hex input, the protocol highlighter and templates, recordings and their replay, and the
tab bar's rename, color and context menu."""

from __future__ import annotations

import shutil
import socket as socketlib
import ssl
import subprocess
import threading

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtNetwork import QSslSocket
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from netcat_gui.main_window import TAB_COLORS, TEMPLATES, MainWindow, recording_from_json, recording_to_json
from netcat_gui.session import (ConnectSessionWidget, History, LineEnding, ListenSessionWidget, MessageInput,
                                       Protocol, hexdump, parse_hex)


def loopback_pair(free_port, history=None):
    history = history or History()
    port = free_port()
    listen = ListenSessionWidget(history=history)
    listen.address_combo.setCurrentIndex(listen.address_combo.findText("127.0.0.1"))
    listen.port_combo.setCurrentText(str(port))
    connect = ConnectSessionWidget(history=history)
    connect.address_combo.setCurrentText("127.0.0.1")
    connect.port_combo.setCurrentText(str(port))
    return listen, connect, port


@pytest.fixture
def connected(qapp, dialogs, free_port, pump):
    listen, connect, port = loopback_pair(free_port)
    listen.start()
    connect.start()
    assert pump(lambda: connect.can_send() and listen.can_send())
    yield listen, connect, port
    connect.shutdown()
    listen.shutdown()


# -- pipes between tabs and file pipes ------------------------------------------------------------

def test_pipe_between_tabs(connected, free_port, pump):
    listen_a, connect_a, _ = connected
    listen_b, connect_b, _ = loopback_pair(free_port)
    listen_b.start()
    connect_b.start()
    assert pump(lambda: connect_b.can_send() and listen_b.can_send())

    # What listen_a receives goes out through connect_b: A's client -> A -> B -> B's listener.
    listen_a.pipe_target = connect_b
    connect_a.input.setPlainText("through")
    connect_a.send_message()
    assert pump(lambda: listen_b.session_log() == "through")
    assert listen_a.session_log() == "through"

    # Both ways: a reply from B's listener arrives on connect_b and goes out through listen_a to A's client.
    connect_b.pipe_target = listen_a
    listen_b.input.setPlainText("back")
    listen_b.send_message()
    assert pump(lambda: connect_a.session_log() == "back")
    assert connect_b.session_log() == "back"

    # A target that cannot send drops the data; nothing crashes.
    connect_b.stop()
    connect_a.input.setPlainText("lost")
    connect_a.send_message()
    assert pump(lambda: listen_a.session_log() == "throughlost")
    assert listen_b.session_log() == "through"
    listen_b.shutdown()
    connect_b.shutdown()


def test_file_sink_and_send_file(connected, pump, tmp_path, dialogs):
    listen, connect, _ = connected
    sink = tmp_path / "received.bin"
    listen.set_sink(str(sink))
    assert listen.sink_path == str(sink)
    connect.input.setPlainText("one")
    connect.send_message()
    assert pump(lambda: listen.session_log() == "one")
    listen.close_sink()
    assert listen.sink_path == ""
    connect.input.setPlainText("two")
    connect.send_message()
    assert pump(lambda: listen.session_log() == "onetwo")
    assert sink.read_bytes() == b"one"

    payload = tmp_path / "payload.bin"
    payload.write_bytes(bytes(range(256)) * 3)
    assert connect.send_file(str(payload)) == 768
    assert pump(lambda: len(listen._chunks) >= 3 and b"".join(d for _, d in listen._chunks[2:]) == payload.read_bytes())
    assert connect.recording[-1][1] == payload.read_bytes()

    disconnected = ConnectSessionWidget()
    assert disconnected.send_file(str(payload)) == -1
    assert dialogs.titles()[-1] == "Cannot send file"
    with pytest.raises(OSError):
        connect.send_file(str(tmp_path / "missing.bin"))


def test_window_file_pipes_and_pipe_menu(qapp, dialogs, free_port, pump, tmp_path, monkeypatch):
    window = MainWindow()
    window.show()
    listen = window.new_listen_tab(port=(port := free_port()))
    listen.address_combo.setCurrentIndex(listen.address_combo.findText("127.0.0.1"))
    listen.start()
    connect = window.new_connect_tab(host="127.0.0.1", port=port, start=True)
    assert pump(lambda: connect.can_send() and listen.can_send())

    # Save Received Data to File on the Listen tab, Send File from the Connect tab.
    window.tabs.setCurrentWidget(listen)
    sink = tmp_path / "sink.bin"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(sink), ""))
    window.action_sink.setChecked(True)
    assert listen.sink_path == str(sink)
    assert window.statusBar().currentMessage().endswith("→ sink.bin")
    window.tabs.setCurrentWidget(connect)
    payload = tmp_path / "payload.txt"
    payload.write_bytes(b"from a file\n")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(payload), ""))
    window.send_file()
    assert pump(lambda: sink.read_bytes() == b"from a file\n")
    window.tabs.setCurrentWidget(listen)
    assert window.action_sink.isChecked()
    window.action_sink.setChecked(False)
    assert listen.sink_path == ""

    # The pipe menu lists the other tab; the status bar shows the pipe.
    window.pipe_menu.aboutToShow.emit()
    labels = [a.text() for a in window.pipe_menu.actions()]
    assert labels == ["None", connect.display_name]
    window.pipe_menu.actions()[1].trigger()
    assert listen.pipe_target is connect
    assert "→ piped to tab" in window.statusBar().currentMessage()
    window.close_tab_at(window.tabs.indexOf(connect))
    assert listen.pipe_target is None
    window.close()


# -- automatic reconnect and TLS ----------------------------------------------------------------------

def test_auto_reconnect(qapp, dialogs, free_port, pump, monkeypatch):
    from netcat_gui import session as session_module
    monkeypatch.setattr(session_module, "RECONNECT_SECONDS", 1)
    listen, connect, _ = loopback_pair(free_port)
    connect.auto_reconnect = True
    listen.start()
    connect.start()
    assert pump(lambda: connect.can_send())
    listen.stop()                                   # drops the client: the Connect tab waits, then reconnects
    assert pump(lambda: connect.status.startswith("Disconnected by peer, reconnecting"))
    assert connect.is_active and connect.start_button.text() == "Disconnect"
    assert pump(lambda: connect.can_send(), 5000)
    assert connect.status == "Connected"
    listen.shutdown()                               # the listener goes away: refused connections, no dialogs
    assert pump(lambda: connect.status.startswith("Disconnected"))
    assert pump(lambda: connect.status.startswith("Disconnected, reconnecting"), 12000)   # refused: ~4 s on Windows
    assert dialogs.titles("critical") == []
    connect.stop()                                  # Disconnect cancels the pending reconnect
    assert not connect.is_active and connect.status == "Disconnected"
    connect.shutdown()


@pytest.mark.skipif(not shutil.which("openssl"), reason="openssl is needed to make a test certificate")
def test_tls_connect_with_self_signed_certificate(qapp, dialogs, free_port, pump, tmp_path, monkeypatch):
    if not QSslSocket.supportsSsl():
        pytest.skip("this Qt build has no TLS backend")
    key, cert = tmp_path / "key.pem", tmp_path / "cert.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out",
                    str(cert), "-subj", "/CN=localhost", "-days", "1"], check=True, capture_output=True)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))
    server = socketlib.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    received: list[bytes] = []

    def serve() -> None:
        raw, _ = server.accept()
        try:
            with context.wrap_socket(raw, server_side=True) as tls:
                tls.sendall(b"hello over tls\n")
                received.append(tls.recv(64))
        except (OSError, ssl.SSLError):
            pass
        finally:
            server.close()

    threading.Thread(target=serve, daemon=True).start()
    questions: list[str] = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda parent, title, text, *a, **k: (questions.append(title), QMessageBox.StandardButton.Yes)[1])
    connect = ConnectSessionWidget()
    connect.address_combo.setCurrentText("127.0.0.1")
    connect.port_combo.setCurrentText(str(port))
    connect.set_protocol(Protocol.TLS)
    connect.start()
    assert connect.status == "Connecting (TLS)..."
    assert pump(lambda: connect.can_send(), 10000), connect.status
    assert connect.status == "Connected (TLS)"
    assert questions == ["Certificate problem"]      # self-signed: asked, answered Yes
    assert pump(lambda: connect.session_log() == "hello over tls\n")
    connect.input.setPlainText("thanks")
    connect.send_message()
    assert pump(lambda: received == [b"thanks"])
    connect.shutdown()


def test_listen_tab_has_no_tls(qapp):
    listen = ListenSessionWidget()
    assert [listen.protocol_combo.itemData(i) for i in range(listen.protocol_combo.count())] == \
        [Protocol.TCP, Protocol.UDP]
    listen.set_protocol(Protocol.TLS)                # ignored, stays TCP
    assert listen.protocol is Protocol.TCP


# -- the message box history, hex view and hex input ---------------------------------------------------

def test_message_history_keys(qapp):
    box = MessageInput()
    for text in ("first", "second", "second", "third"):
        box.remember(text)
    assert box.history == ["first", "second", "third"]
    QTest.keyClicks(box, "draft")
    QTest.keyClick(box, Qt.Key.Key_Up)
    assert box.toPlainText() == "third"
    QTest.keyClick(box, Qt.Key.Key_Up)
    QTest.keyClick(box, Qt.Key.Key_Up)
    QTest.keyClick(box, Qt.Key.Key_Up)               # no further back than the first
    assert box.toPlainText() == "first"
    QTest.keyClick(box, Qt.Key.Key_Down)
    assert box.toPlainText() == "second"
    QTest.keyClick(box, Qt.Key.Key_Down)
    QTest.keyClick(box, Qt.Key.Key_Down)
    assert box.toPlainText() == "draft"              # back to what was being typed
    QTest.keyClick(box, Qt.Key.Key_Down)
    assert box.toPlainText() == "draft"
    box.setPlainText("line one\nline two")
    box.moveCursor(box.textCursor().MoveOperation.Start)
    QTest.keyClick(box, Qt.Key.Key_Down)             # inside a multi-line message Down moves the cursor
    assert box.toPlainText() == "line one\nline two"


def test_hexdump_and_parse_hex():
    assert hexdump(b"") == ""
    assert hexdump(b"Hello\n") == f"00000000  {'48 65 6c 6c 6f 0a':<47}  |Hello.|\n"
    lines = hexdump(bytes(range(20))).splitlines()
    assert len(lines) == 2 and lines[1].startswith("00000010  10 11 12 13")
    for text in ("48 65 6c", "48:65:6c", "0x48 0x65 0x6c", "\\x48\\x65\\x6c", "48656c", "48,65,6c"):
        assert parse_hex(text) == b"Hel", text
    assert parse_hex("  ") == b""
    for bad in ("4", "4g", "48 6"):
        with pytest.raises(ValueError):
            parse_hex(bad)


def test_hex_view_and_hex_input(connected, pump, dialogs):
    listen, connect, _ = connected
    connect.hex_input = True
    connect.input.setPlainText("48 69 0a")
    connect.send_message()
    assert pump(lambda: listen.session_log() == "Hi\n")
    assert connect.input.toPlainText() == ""
    connect.input.setPlainText("4")
    connect.send_message()
    assert dialogs.titles()[-1] == "Invalid hex input"
    assert connect.input.toPlainText() == "4"       # kept for correction

    listen.set_hex_view(True)
    assert listen.session_log() == f"<< 3 bytes\n00000000  {'48 69 0a':<47}  |Hi.|\n"
    listen.echo_sent = True
    listen.input.setPlainText("ok")
    listen.send_message()
    assert listen.session_log().endswith(f">> 2 bytes\n00000000  {'6f 6b':<47}  |ok|\n")
    listen.set_hex_view(False)
    assert listen.session_log() == "Hi\nok"
    listen.clear_log()
    assert listen.session_log() == "" and listen._chunks == []


def test_incremental_decoding_survives_a_split_character(qapp):
    widget = ConnectSessionWidget()
    widget.show_received("é".encode()[:1])
    widget.show_received("é".encode()[1:])
    assert widget.session_log() == "é"


# -- the protocol highlighter and templates ----------------------------------------------------------------

def test_highlighter_rules(qapp):
    widget = ConnectSessionWidget()
    rules = widget.highlighter.matching_rules
    assert rules("GET / HTTP/1.1") == [0]
    assert rules("HTTP/1.1 200 OK") == [2]
    assert rules("HTTP/1.1 404 Not Found") == [4]
    assert rules("Content-Type: text/plain") == [6]
    assert rules("220 mail.example.org ESMTP") == [3]
    assert rules("550 no such user") == [4]
    assert rules("-ERR no such message") == [4]
    assert rules("+OK POP3 ready") == [5]
    assert rules("EHLO localhost") == [1]
    assert rules("<< 12 bytes") == [7]
    assert rules("just some data") == []
    widget.show_received(b"HTTP/1.1 200 OK\r\nServer: x\r\n\r\nbody")
    widget.set_highlight(False)
    assert not widget.highlighter.enabled
    widget.set_highlight(True)
    assert widget.highlighter.enabled


def test_templates_fill_the_message_box(qapp, dialogs):
    window = MainWindow()
    window.insert_template("HTTP GET /")
    assert dialogs.titles() == ["No session active"]
    session = window.new_connect_tab(host="example.org", port=80)
    window.insert_template("HTTP GET /")
    assert session.input.toPlainText().startswith("GET / HTTP/1.1\nHost: example.org\n")
    assert session.end_with_newline and session.line_ending is LineEnding.CRLF
    assert window.action_newline.isChecked() and window.ending_actions[LineEnding.CRLF].isChecked()
    assert session.outgoing_bytes().endswith(b"Connection: close\r\n\r\n")
    assert b"\n" not in session.outgoing_bytes().replace(b"\r\n", b"")
    assert [a.text() for a in window.template_menu.actions()] == list(TEMPLATES)
    window.close()


# -- recordings and replay -----------------------------------------------------------------------------------

def test_recording_round_trip_and_replay(connected, pump, tmp_path):
    listen, connect, _ = connected
    for text in ("a", "b"):
        connect.input.setPlainText(text)
        connect.send_message()
    messages = connect.recording_as_delays()
    assert [d for _, d in messages] == [b"a", b"b"] and messages[0][0] == 0.0
    text = recording_to_json("x", messages)
    assert recording_from_json(text) == [(0.0, b"a"), (round(messages[1][0], 3), b"b")]
    with pytest.raises(ValueError):
        recording_from_json('{"app": "other"}')
    with pytest.raises(ValueError):
        recording_from_json("not json")

    assert pump(lambda: listen.session_log() == "ab")
    assert connect.start_replay([(0.0, b"1"), (0.05, b"2"), (0.05, b"3")])
    assert connect.is_replaying
    assert pump(lambda: listen.session_log() == "ab123")
    assert pump(lambda: not connect.is_replaying)
    assert connect.status == "Connected"
    assert not connect.start_replay([])
    assert connect.start_replay([(0.0, b"x"), (5.0, b"never")])
    assert pump(lambda: listen.session_log() == "ab123x")
    assert connect.is_replaying
    connect.stop()                                  # disconnecting cancels a running replay
    assert not connect.is_replaying
    assert pump(lambda: listen.status == "Listening")
    assert listen.session_log() == "ab123x"


def test_window_recording_menu(qapp, dialogs, free_port, pump, tmp_path, monkeypatch):
    window = MainWindow()
    window.save_recording()
    assert dialogs.titles()[-1] == "No session active"
    listen = window.new_listen_tab(port=(port := free_port()))
    listen.address_combo.setCurrentIndex(listen.address_combo.findText("127.0.0.1"))
    listen.start()
    connect = window.new_connect_tab(host="127.0.0.1", port=port, start=True)
    assert pump(lambda: connect.can_send() and listen.can_send())
    window.save_recording()
    assert dialogs.titles()[-1] == "Nothing recorded"
    connect.input.setPlainText("rec")
    window.send()
    path = tmp_path / "s.ncrec.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(path), ""))
    window.save_recording()
    assert recording_from_json(path.read_text()) == [(0.0, b"rec")]
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    window.replay_recording()
    assert pump(lambda: listen.session_log() == "recrec")
    window.tabs.setCurrentWidget(listen)
    listen.stop()
    window.replay_recording()
    assert dialogs.titles()[-1] == "Cannot replay"
    window.close()


# -- tab rename, color and context menu -----------------------------------------------------------------------

def test_rename_color_and_context_menu(qapp, dialogs, monkeypatch):
    window = MainWindow()
    window.rename_tab()
    assert dialogs.titles() == ["No session active"]
    session = window.new_connect_tab()
    other = window.new_listen_tab()
    window.tabs.setCurrentWidget(session)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Game server", True))
    window.rename_tab()
    assert session.custom_title == "Game server" and session.display_name == "Game server"
    assert window.tabs.tabText(0) == "Game server"
    session.set_session_name("1.2.3.4:5")
    session.set_status("Connected")                 # the custom title stays while the session's name changes
    assert window.tabs.tabText(0) == "Game server"
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", True))
    window.rename_tab()
    assert window.tabs.tabText(0) == "1.2.3.4:5"

    window.set_tab_color("Green")
    assert session.tab_color == "Green"
    assert window.tabs.tabBar().tabTextColor(0).name() == TAB_COLORS["Green"]
    window.set_tab_color("None")
    assert session.tab_color == ""

    menu = window.tab_context_menu(1)
    labels = [a.text() for a in menu.actions() if a.text()]
    assert labels == ["New Connect Tab", "New Listen Tab", "Rename Tab...", "Tab Color", "Close Tab",
                      "Close Other Tabs", "Close All Tabs"]
    empty = window.tab_context_menu(-1)
    assert [a.text() for a in empty.actions()] == ["New Connect Tab", "New Listen Tab"]
    window.close_other_tabs(1)
    assert window.sessions() == [other]
    window.close()
