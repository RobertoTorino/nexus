# SPDX-License-Identifier: GPL-2.0-only
"""The session widgets against each other over the loopback: a Listen tab and a Connect tab in the same process,
TCP and UDP, the encodings, the line ending, the refused connection, the port checks, and the message box keys."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from netcat_gui.session import (ConnectSessionWidget, Encoding, History, LineEnding, ListenSessionWidget,
                                     MessageInput, Protocol, local_addresses)


def select_loopback(listen: ListenSessionWidget) -> None:
    index = listen.address_combo.findText("127.0.0.1")
    assert index != -1, local_addresses()
    listen.address_combo.setCurrentIndex(index)


@pytest.fixture
def pair(qapp, dialogs, free_port):
    """A listening Listen tab and a Connect tab aimed at it, not yet connected; both are closed afterwards."""
    history = History()
    listen = ListenSessionWidget(history=history)
    connect = ConnectSessionWidget(history=history)
    port = free_port()
    select_loopback(listen)
    listen.port_combo.setCurrentText(str(port))
    connect.address_combo.setCurrentText("127.0.0.1")
    connect.port_combo.setCurrentText(str(port))
    yield listen, connect, port
    connect.shutdown()
    listen.shutdown()
    assert dialogs.shown == [], dialogs.shown


def test_tcp_session_both_ways(pair, pump):
    listen, connect, port = pair
    listen.start()
    assert listen.status == "Listening"
    assert listen.session_name == f"127.0.0.1:{port}"
    assert listen.start_button.text() == "Stop"
    assert not listen.port_combo.isEnabled()

    connect.start()
    assert connect.status == "Connecting..."
    assert pump(lambda: connect.can_send() and listen.can_send())
    assert connect.status == "Connected"
    assert connect.session_name == f"127.0.0.1:{port}"
    assert listen.status.startswith("Connected (client 127.0.0.1:")
    assert listen.start_button.text() == "Disconnect"
    assert connect.send_button.isEnabled() and listen.send_button.isEnabled()

    # Connect -> Listen with the newline appended; the message box empties.
    connect.end_with_newline = True
    connect.input.setPlainText("hello")
    connect.send_message()
    assert connect.input.toPlainText() == ""
    assert pump(lambda: listen.session_log() == "hello\n")

    # Listen -> Connect in Latin-1 on both sides, CRLF, echoed on the sender.
    for widget in (listen, connect):
        widget.encoding = Encoding.LATIN1
    listen.end_with_newline = True
    listen.line_ending = LineEnding.CRLF
    listen.echo_sent = True
    listen.input.setPlainText("héllo")
    listen.send_message()
    assert pump(lambda: connect.session_log() == "héllo\n")   # the log shows CRLF and CR as a line break
    assert listen.session_log() == "hello\nhéllo\n"

    # Chunks are appended as they come, without an extra line break per chunk.
    connect.end_with_newline = False
    for piece in ("a", "b", "c"):
        connect.input.setPlainText(piece)
        connect.send_message()
    assert pump(lambda: listen.session_log().endswith("abc"))

    # The client disconnects: the Listen tab goes back to listening and takes the next client.
    connect.stop()
    assert connect.status == "Disconnected"
    assert connect.start_button.text() == "Connect"
    assert pump(lambda: listen.status == "Listening")
    assert listen.start_button.text() == "Stop"
    assert not listen.can_send()
    connect.start()
    assert pump(lambda: connect.can_send() and listen.can_send())

    # The Listen tab drops the client (one step back), then stops listening (another).
    listen.stop()
    assert listen.status == "Listening"
    assert pump(lambda: connect.status == "Disconnected by peer")
    listen.stop()
    assert listen.status == "Disconnected"
    assert listen.start_button.text() == "Listen"
    assert listen.port_combo.isEnabled()


def test_second_tcp_client_is_turned_away(pair, pump):
    listen, connect, port = pair
    listen.start()
    connect.start()
    assert pump(lambda: connect.can_send() and listen.can_send())
    second = ConnectSessionWidget(history=listen.history)
    second.address_combo.setCurrentText("127.0.0.1")
    second.port_combo.setCurrentText(str(port))
    second.start()
    assert pump(lambda: second.status in ("Disconnected by peer", "Disconnected"))
    assert listen.can_send() and connect.can_send()
    second.shutdown()


def test_udp_session_both_ways(pair, pump, free_port):
    listen, connect, _ = pair
    port = free_port(kind=__import__("socket").SOCK_DGRAM)
    listen.port_combo.setCurrentText(str(port))
    connect.port_combo.setCurrentText(str(port))
    listen.set_protocol(Protocol.UDP)
    connect.set_protocol(Protocol.UDP)

    listen.start()
    assert listen.status == "Listening (UDP)"
    assert not listen.can_send()
    connect.start()
    assert pump(lambda: connect.can_send())
    assert connect.status == "Connected (UDP)"

    connect.input.setPlainText("ping")
    connect.send_message()
    assert pump(lambda: listen.session_log() == "ping")
    assert listen.can_send()
    assert listen.status.startswith("Listening (UDP, peer 127.0.0.1:")
    assert listen.udp_peer is not None and listen.udp_peer[0] == "127.0.0.1"

    listen.input.setPlainText("pong")
    listen.send_message()
    assert pump(lambda: connect.session_log() == "pong")

    listen.stop()
    assert listen.status == "Disconnected"
    assert listen.udp_peer is None


def test_udp_listen_cannot_send_before_a_peer(qapp, dialogs, free_port):
    listen = ListenSessionWidget()
    select_loopback(listen)
    listen.set_protocol(Protocol.UDP)
    listen.port_combo.setCurrentText(str(free_port(kind=__import__("socket").SOCK_DGRAM)))
    listen.start()
    listen.input.setPlainText("nobody")
    listen.send_message()
    assert dialogs.titles("warning") == ["Cannot send message"]
    assert listen.input.toPlainText() == "nobody"
    listen.shutdown()


def test_connection_refused_shows_the_dialog(qapp, dialogs, pump, free_port):
    connect = ConnectSessionWidget()
    connect.address_combo.setCurrentText("127.0.0.1")
    connect.port_combo.setCurrentText(str(free_port()))
    connect.start()
    assert pump(lambda: connect.status == "Disconnected", 10000)
    assert dialogs.titles("critical") == ["Connection refused"]
    assert connect.start_button.text() == "Connect"
    assert connect.address_combo.isEnabled()


def test_input_checks(qapp, dialogs):
    connect = ConnectSessionWidget()
    connect.start()
    assert dialogs.titles() == ["No host specified"]
    connect.address_combo.setCurrentText("localhost")
    connect.port_combo.setCurrentText("")
    connect.start()
    assert dialogs.titles()[-1] == "No port specified"
    for bad in ("0", "65536", "abc"):
        connect.port_combo.setCurrentText(bad)
        connect.start()
        assert dialogs.titles()[-1] == "Invalid port"
    connect.stop()
    assert dialogs.titles()[-1] == "Not Connected"
    connect.input.setPlainText("x")
    connect.send_message()
    assert dialogs.titles()[-1] == "Cannot send message"
    assert not connect.is_active

    listen = ListenSessionWidget()
    listen.stop()
    assert dialogs.titles()[-1] == "Not Listening"
    listen.port_combo.setCurrentText("")
    listen.start()
    assert dialogs.titles()[-1] == "No port specified"


def test_history_is_shared_and_remembered(pair, pump):
    listen, connect, port = pair
    listen.start()
    connect.start()
    assert pump(lambda: connect.can_send())
    assert connect.history.hosts == ["127.0.0.1"]
    assert connect.history.ports[0] == str(port)
    assert listen.history.listen_ports[0] == str(port)
    later = ConnectSessionWidget(history=connect.history)
    assert later.address_combo.itemText(0) == "127.0.0.1"
    assert later.port_combo.itemText(0) == str(port)
    assert later.address_combo.currentText() == ""


def test_history_limit():
    items: list[str] = []
    for i in range(30):
        History.remember(items, str(i))
    assert len(items) == 20 and items[0] == "29"
    History.remember(items, "10")
    assert items[0] == "10" and items.count("10") == 1
    History.remember(items, "   ")
    assert items[0] == "10"


def test_message_input_enter_sends_and_shift_enter_breaks_the_line(qapp):
    box = MessageInput()
    sent: list[int] = []
    box.enter_pressed.connect(lambda: sent.append(1))
    QTest.keyClicks(box, "one")
    QTest.keyClick(box, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    QTest.keyClicks(box, "two")
    assert box.toPlainText() == "one\ntwo"
    assert sent == []
    QTest.keyClick(box, Qt.Key.Key_Return)
    assert sent == [1]
    QTest.keyClick(box, Qt.Key.Key_Enter)
    assert sent == [1, 1]


def test_encoding_and_line_ending(qapp):
    widget = ConnectSessionWidget()
    widget.input.setPlainText("é")
    assert widget.outgoing_bytes() == "é".encode()
    widget.encoding = Encoding.LATIN1
    assert widget.outgoing_bytes() == b"\xe9"
    widget.end_with_newline = True
    widget.line_ending = LineEnding.CRLF
    assert widget.outgoing_bytes() == b"\xe9\r\n"
    widget.input.setPlainText("€")
    assert widget.outgoing_bytes() == b"?\r\n"         # not in Latin-1: replaced, as the C++ toLatin1() did
    widget.input.clear()
    assert widget.outgoing_bytes() == b""               # an empty message is not sent
    widget.show_received(b"\xe9")
    widget.encoding = Encoding.UTF8
    widget.show_received(b"\xff")
    assert widget.session_log() == "é�"
    assert Encoding.SYSTEM.codec                           # whatever the locale says, never empty
    assert Encoding.from_name("Latin-1", Encoding.UTF8) is Encoding.LATIN1
    assert Encoding.from_name("nonsense", Encoding.UTF8) is Encoding.UTF8
    assert LineEnding.from_name("CRLF", LineEnding.LF) is LineEnding.CRLF


def test_local_addresses_have_loopback_and_any():
    addresses = local_addresses()
    assert "127.0.0.1" in addresses and "0.0.0.0" in addresses and "::" in addresses
    assert len(addresses) == len(set(addresses))
