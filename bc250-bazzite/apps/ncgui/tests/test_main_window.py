# SPDX-License-Identifier: GPL-2.0-only
"""The main window: tabs, the status bar, the session menu applied to the current tab and remembered for the next
run, Save Log, the actions without a session, the command line (also as a second launch hands it over), and the
version file."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QFileDialog

import netcat_gui
from netcat_gui import __main__ as entry
from netcat_gui.main_window import MainWindow
from netcat_gui.session import Encoding, LineEnding, ListenSessionWidget, Protocol


@pytest.fixture
def window(qapp, dialogs):
    win = MainWindow()
    win.show()
    yield win
    win.close()


def test_tabs_and_status_bar(window, free_port, pump):
    assert window.tabs.count() == 0
    assert window.statusBar().currentMessage().startswith("No session open")

    connect = window.new_connect_tab()
    assert window.tabs.count() == 1 and window.tabs.tabText(0) == "Connect"
    assert window.statusBar().currentMessage() == "Disconnected (UTF-8)"

    port = free_port()
    listen = window.new_listen_tab(port=port)
    assert isinstance(listen, ListenSessionWidget)
    assert window.tabs.currentWidget() is listen and window.tabs.tabText(1) == "Listen"
    index = listen.address_combo.findText("127.0.0.1")
    listen.address_combo.setCurrentIndex(index)
    window.connect_listen()
    assert window.statusBar().currentMessage() == "Listening (UTF-8)"
    assert window.tabs.tabText(1) == f"127.0.0.1:{port}"

    window.tabs.setCurrentWidget(connect)
    connect.address_combo.setCurrentText("127.0.0.1")
    connect.port_combo.setCurrentText(str(port))
    window.connect_listen()
    assert pump(lambda: connect.can_send())
    assert window.statusBar().currentMessage() == "Connected (UTF-8)"
    assert window.tabs.tabText(0) == f"127.0.0.1:{port}"

    connect.input.setPlainText("hi")
    window.send()
    assert pump(lambda: listen.session_log() == "hi")

    # The status bar follows the current tab, also when the other tab's state changes.
    window.tabs.setCurrentWidget(listen)
    assert window.statusBar().currentMessage().startswith("Connected (client 127.0.0.1:")
    window.tabs.setCurrentWidget(connect)
    window.disconnect()
    assert window.statusBar().currentMessage() == "Disconnected (UTF-8)"
    assert pump(lambda: listen.status == "Listening")
    window.tabs.setCurrentWidget(listen)
    assert window.statusBar().currentMessage() == "Listening (UTF-8)"

    window._cycle_tab(1)
    assert window.tabs.currentWidget() is connect
    window._cycle_tab(-1)
    assert window.tabs.currentWidget() is listen

    window.close_current_tab()
    assert window.tabs.count() == 1 and not listen.is_active
    window.close_all_tabs()
    assert window.tabs.count() == 0
    assert window.statusBar().currentMessage().startswith("No session open")


def test_session_menu_applies_to_the_current_tab_and_is_remembered(window, qapp):
    first = window.new_connect_tab()
    window.action_newline.setChecked(True)
    window.ending_actions[LineEnding.CRLF].trigger()
    window.encoding_actions[Encoding.LATIN1].trigger()
    window.action_echo.setChecked(True)
    assert (first.end_with_newline, first.line_ending, first.encoding, first.echo_sent) == \
        (True, LineEnding.CRLF, Encoding.LATIN1, True)
    assert window.statusBar().currentMessage() == "Disconnected (Latin-1, CRLF)"

    # A new tab takes the menu's state; switching back shows the first tab's own state in the menu.
    second = window.new_listen_tab()
    assert second.encoding is Encoding.LATIN1 and second.end_with_newline
    window.encoding_actions[Encoding.UTF8].trigger()
    window.action_newline.setChecked(False)
    assert second.encoding is Encoding.UTF8 and not second.end_with_newline
    assert first.encoding is Encoding.LATIN1 and first.end_with_newline
    window.tabs.setCurrentWidget(first)
    assert window.encoding_actions[Encoding.LATIN1].isChecked()
    assert window.action_newline.isChecked()
    assert window.statusBar().currentMessage() == "Disconnected (Latin-1, CRLF)"

    # The last menu state is the default of the next run.
    window.close()
    again = MainWindow()
    assert again.default_encoding is Encoding.UTF8
    assert again.default_line_ending is LineEnding.CRLF
    assert not again.default_end_with_newline
    assert again.default_echo_sent
    assert again.action_echo.isChecked() and again.ending_actions[LineEnding.CRLF].isChecked()
    again.close()


def test_history_survives_a_restart(window, free_port, pump):
    port = free_port()
    listen = window.new_listen_tab(port=port)
    listen.address_combo.setCurrentIndex(listen.address_combo.findText("127.0.0.1"))
    listen.start()
    connect = window.new_connect_tab(host="localhost", port=port)
    connect.start()
    assert pump(lambda: connect.can_send())
    window.close()
    again = MainWindow()
    assert again.history.hosts == ["localhost"]
    assert again.history.ports[0] == str(port)
    assert again.history.listen_ports[0] == str(port)
    tab = again.new_connect_tab()
    assert tab.address_combo.itemText(0) == "localhost"
    again.close()


def test_save_log(window, dialogs, tmp_path, monkeypatch):
    window.save_log()
    assert dialogs.titles() == ["No session active"]
    session = window.new_connect_tab()
    window.save_log()
    assert dialogs.titles()[-1] == "Session log empty"

    session.show_received(b"GET / HTTP/1.0\r\n\r\n")
    target = tmp_path / "log.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    window.save_log()
    assert dialogs.titles()[-1] == "Log saved successfully"
    text = target.read_bytes().decode("utf-8")              # as written, line endings untranslated
    assert text.startswith("--\n[") and "log session for Connect\n---\nGET / HTTP/1.0\n\n\n-----\n" in text
    assert window._settings.value("paths/lastLogDir") == str(tmp_path)

    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    window.save_log()
    assert dialogs.titles()[-1] == "Log saved successfully"    # canceled: nothing new shown

    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "missing" / "x.txt"), ""))
    window.save_log()
    assert dialogs.titles()[-1] == "File write error"

    when = datetime(2026, 10, 14, 15, 0, 0)
    assert MainWindow.log_text("a:1", "x", when) == \
        f"--\n[2026-10-14 15:00:00]\n{netcat_gui.APP_NAME} log session for a:1\n---\nx\n-----\n"


def test_actions_without_a_session_warn(window, dialogs):
    for action in (window.connect_listen, window.disconnect, window.send, window.select_all, window.copy,
                   window.paste, window.clear_log):
        action()
    assert dialogs.titles() == ["No session active"] * 7
    session = window.new_connect_tab()
    session.show_received(b"old")
    window.clear_log()
    assert session.session_log() == ""
    window.show_about()
    window.show_shortcuts()
    assert dialogs.titles()[-2:] == [f"About {netcat_gui.APP_NAME}", "Keyboard Shortcuts"]


def test_new_tabs_from_the_command_line(window, free_port, pump):
    port = free_port()
    listen = window.new_listen_tab(port=port, protocol=Protocol.UDP, start=False)
    assert listen.protocol is Protocol.UDP and listen.port_combo.currentText() == str(port)
    listen.set_protocol(Protocol.TCP)
    listen.address_combo.setCurrentIndex(listen.address_combo.findText("127.0.0.1"))
    listen.start()
    connect = window.new_connect_tab(host="127.0.0.1", port=port, protocol=Protocol.TCP, start=True)
    assert connect.status == "Connecting..."
    assert pump(lambda: connect.can_send())


def test_command_line_parser():
    parser = entry.build_parser()
    args = parser.parse_args([])
    assert args.host is None and args.listen is None and not args.udp
    args = parser.parse_args(["-u", "-l", "4000"])
    assert args.listen == 4000 and args.udp
    args = parser.parse_args(["example.org", "80"])
    assert (args.host, args.port) == ("example.org", 80)
    with pytest.raises(SystemExit):
        parser.parse_args(["--listen", "abc"])


def test_second_launch_arguments_round_trip():
    parser = entry.build_parser()
    for argv in ([], ["-u", "-l", "4000"], ["-l", "4000"], ["example.org", "80"], ["-u", "10.0.0.2", "53"]):
        args = parser.parse_known_args(argv)[0]
        assert vars(parser.parse_known_args(entry.own_arguments(args))[0]) == vars(args)
    assert entry.own_arguments(parser.parse_args([])) == []    # no arguments: the open window is only shown


def test_forwarded_arguments_open_their_tab(window, free_port, pump):
    import socket
    port = free_port(socket.SOCK_DGRAM)
    parser = entry.build_parser()
    forwarded = entry.own_arguments(parser.parse_args(["-u", "-l", str(port)]))
    entry.open_tab(window, parser.parse_known_args(forwarded)[0])
    tab = window.tabs.widget(window.tabs.count() - 1)
    assert isinstance(tab, ListenSessionWidget) and tab.protocol is Protocol.UDP
    assert pump(lambda: tab.is_active)                         # started, as from the command line
    tab.stop()


def test_version_file_matches_package() -> None:
    assert (netcat_gui.ROOT / "VERSION").read_text().strip() == netcat_gui.__version__
    assert netcat_gui.LOGO_PATH.is_file()
    assert (netcat_gui.ROOT / "images" / f"{netcat_gui.APP_ID}-128.png").is_file()
    for name in ("connect", "listen", "save"):
        assert (netcat_gui.ICONS_DIR / f"{name}.png").is_file()
    assert Path(netcat_gui.ROOT / "LICENSE").is_file()
