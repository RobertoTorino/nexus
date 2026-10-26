# SPDX-License-Identifier: GPL-3.0-or-later

import time
from unittest.mock import Mock, call, patch

import paramiko
import pytest
from PyQt6 import sip
from PyQt6.QtWidgets import QMessageBox, QWidget

from sftp_tools import client_tab, common, connection, main_window, server_tab, settings
from sftp_tools.connection import UnknownHostKeyError, server_status_after_action
from sftp_tools.main_window import MainWindow
from sftp_tools.server_tab import ServerManagerTab


def test_window_has_the_suite_header_and_shows_the_states(qapp) -> None:
    window = MainWindow()

    assert window.windowTitle() == "Bazzite SFTP Tools"
    assert window.sftp_tab.status.text() == "Not connected"
    assert window.sftp_box.value.text() == "Disconnected"
    assert window.server_box.value.text() == "Not checked"
    window.server_tab._show_status("active")
    assert window.server_box.value.text() == "sshd is running"
    assert "#2e7d32" in window.server_box.styleSheet()
    window.server_tab._show_status("inactive")
    assert "#ef6c00" in window.server_box.styleSheet()
    window.close()


def test_changed_settings_reach_the_queue_and_the_lists(qapp, tmp_path, monkeypatch) -> None:
    window = MainWindow()
    tab = window.sftp_tab
    refreshed: list[str] = []
    monkeypatch.setattr(tab, "refresh_local", lambda: refreshed.append("local"))
    monkeypatch.setattr(tab, "refresh_remote", lambda: refreshed.append("remote"))
    settings.load_settings(tmp_path / "config")
    settings.apply_settings(settings.AppSettings(preserve_timestamps=False, queue_autoclear=False,
                                                 invalid_char_replacement="-"))

    tab.settings_changed(False)
    assert (tab.queue.preserve_timestamps, tab.queue.queue_autoclear, tab.queue.char_replacement) == (False, False, "-")
    assert refreshed == []
    tab.settings_changed(True)
    assert refreshed == ["local", "remote"]
    window.close()


@pytest.mark.parametrize(
    ("state", "active", "button_text", "status_text", "tone"),
    [
        ("active", True, "Stop sshd", "sshd is running.", "success"),
        ("inactive", False, "Start sshd", "sshd is stopped.", "warning"),
    ],
)
def test_server_status_updates_pill_and_toggle_button(
    state: str,
    active: bool,
    button_text: str,
    status_text: str,
    tone: str,
) -> None:
    tab = ServerManagerTab()
    emitted: list[tuple[str, str]] = []
    tab.status_changed.connect(lambda value, color: emitted.append((value, color)))
    tab._ssh = Mock()

    tab._show_status(state)

    assert tab._sshd_active is active
    assert tab.toggle_service_button.text() == button_text
    assert tab.toggle_service_button.isEnabled()
    assert tab.status.text() == status_text
    assert emitted[-1] == (status_text.rstrip("."), tone)
    tab.close()


def test_unknown_server_status_disables_start_stop_button() -> None:
    tab = ServerManagerTab()
    tab._ssh = Mock()

    tab._show_status("activating")

    assert tab._sshd_active is None
    assert not tab.toggle_service_button.isEnabled()
    assert tab.status.text() == "sshd state: activating"
    tab.close()


@pytest.mark.parametrize(
    ("answer", "trusted"),
    [
        (QMessageBox.StandardButton.Yes, True),
        (QMessageBox.StandardButton.No, False),
    ],
)
def test_unknown_host_prompt_only_saves_after_yes(
    answer: QMessageBox.StandardButton,
    trusted: bool,
    monkeypatch,
) -> None:
    error = UnknownHostKeyError(
        "server.example",
        22,
        paramiko.RSAKey.generate(1024),
    )
    monkeypatch.setattr(common.PlainMessageBox, "question", lambda *args: answer)
    saved: list[UnknownHostKeyError] = []
    monkeypatch.setattr(
        common,
        "save_trusted_host_key",
        lambda host: saved.append(host),
    )
    monkeypatch.setattr(common.PlainMessageBox, "information", lambda *args: None)
    monkeypatch.setattr(common.PlainMessageBox, "critical", lambda *args: None)

    assert common.trust_unknown_host(QWidget(), error) is trusted
    assert saved == ([error] if trusted else [])


@pytest.mark.parametrize(
    ("state", "expected_action"),
    [("active", "stop"), ("inactive", "start")],
)
def test_service_button_runs_action_matching_observed_state(
    state: str, expected_action: str
) -> None:
    tab = ServerManagerTab()
    tab._ssh = Mock()
    actions: list[str] = []
    tab.perform_action = actions.append

    tab._show_status(state)
    tab.toggle_service()

    assert actions == [expected_action]
    tab.close()


@pytest.mark.parametrize("action", ["status", "start", "stop"])
def test_server_status_after_action_runs_action_then_checks_state(action: str) -> None:
    client = Mock()
    responses = ["active"] if action == "status" else [None, "active"]
    with patch("sftp_tools.connection.run_server_action", side_effect=responses) as command:
        assert server_status_after_action(client, action) == "active"

    expected = [call(client, "status")]
    if action != "status":
        expected.insert(0, call(client, action))
    assert command.call_args_list == expected


def test_worker_is_kept_alive_until_its_thread_finishes(qapp, monkeypatch) -> None:
    results: list[str] = []

    class DelayedFinishTask(client_tab.TaskRunner):
        def run(self) -> None:
            try:
                self.succeeded.emit(self.operation())
                time.sleep(0.1)
            except Exception as error:
                self.failed.emit(str(error))

    monkeypatch.setattr(client_tab, "TaskRunner", DelayedFinishTask)
    tab = client_tab.SftpClientTab()

    def launch_follow_up(result: str) -> None:
        results.append(result)
        if result == "connected":
            tab._run(lambda: "listed", results.append)

    tab._run(lambda: "connected", launch_follow_up)
    deadline = time.monotonic() + 3
    while (tab._workers or results != ["connected", "listed"]) and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)

    assert results == ["connected", "listed"]
    assert not tab._workers
    assert not tab.has_running_tasks


def test_error_dot_shows_after_an_error_and_goes_with_its_window(qapp) -> None:
    from sftp_tools.app_logging import get_logger

    handlers = len(get_logger().handlers)
    window = MainWindow()
    window.show()
    assert len(get_logger().handlers) == handlers + 1
    assert not window.error_indicator.isVisible()
    get_logger().error("boom")
    assert window.error_indicator.isVisible()
    window.close()
    sip.delete(window)
    assert len(get_logger().handlers) == handlers
    get_logger().error("after the window is gone")


def test_local_list_keeps_every_cell_of_a_row_together(qapp, tmp_path) -> None:
    (tmp_path / "b.txt").write_text("12345")
    (tmp_path / "a-folder").mkdir()
    (tmp_path / "c.txt").write_text("")
    tab = client_tab.SftpClientTab()
    tab.local_path.setText(str(tmp_path))
    tab.refresh_local()

    rows = {tab.local_table.item(row, 0).text(): tab.local_table.item(row, 1).text()
            for row in range(tab.local_table.rowCount())}
    assert rows == {"..": "Folder", "a-folder": "Folder", "b.txt": "File", "c.txt": "File"}
    assert tab.local_table.isSortingEnabled()


def _local_tab(tmp_path, names=("a.txt", "b.txt", "c.txt")):
    for name in names:
        (tmp_path / name).write_text(name)
    tab = client_tab.SftpClientTab()
    tab.local_path.setText(str(tmp_path))
    tab.refresh_local()
    rows = {tab.local_table.item(row, 0).text(): row for row in range(tab.local_table.rowCount())}
    return tab, rows


def test_upload_queues_every_selected_row_but_the_parent(qapp, tmp_path, monkeypatch) -> None:
    from PyQt6.QtCore import QItemSelectionModel
    tab, rows = _local_tab(tmp_path)
    tab._sftp = Mock()
    tab.remote_path.setText("/var/home/user")
    monkeypatch.setattr(client_tab, "remote_exists", lambda _sftp, _path: False)
    enqueued = []
    monkeypatch.setattr(tab.queue, "enqueue", enqueued.append)
    model = tab.local_table.selectionModel()
    for name in ("..", "a.txt", "c.txt"):
        model.select(tab.local_table.model().index(rows[name], 0),
                     QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)

    tab.upload_selected()

    assert sorted((job.source, job.destination) for job in enqueued) == [
        (str(tmp_path / "a.txt"), "/var/home/user/a.txt"),
        (str(tmp_path / "c.txt"), "/var/home/user/c.txt"),
    ]


def test_local_rows_drag_as_file_urls(qapp, tmp_path) -> None:
    tab, rows = _local_tab(tmp_path)
    items = [tab.local_table.item(rows[name], column) for name in ("..", "b.txt") for column in range(4)]

    urls = tab.local_table.mimeData(items).urls()

    assert [url.toLocalFile() for url in urls] == [str(tmp_path / "b.txt")]


def test_files_dropped_on_the_remote_list_are_copied_while_connected(qapp, tmp_path) -> None:
    from PyQt6.QtCore import QMimeData, QPointF, QUrl, Qt
    from PyQt6.QtGui import QDropEvent
    table = client_tab.RemoteFileTable(0, 4)
    dropped = []
    table.files_dropped.connect(dropped.append)
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(tmp_path / "a.txt")), QUrl("https://example.org/b.txt")])

    def drop() -> QDropEvent:
        event = QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction | Qt.DropAction.MoveAction, data,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        table.dropEvent(event)
        return event

    assert not drop().isAccepted()
    table.accept_files = True
    event = drop()
    assert event.isAccepted() and event.dropAction() == Qt.DropAction.CopyAction
    assert dropped == [[str(tmp_path / "a.txt")]]


def test_existing_targets_ask_once_when_the_answer_holds_for_the_rest(qapp, monkeypatch) -> None:
    tab = client_tab.SftpClientTab()
    enqueued = []
    monkeypatch.setattr(tab.queue, "enqueue", enqueued.append)
    asked = []

    def ask(job, more):
        asked.append((job.source, more))
        return "skip", True

    monkeypatch.setattr(tab, "_ask_existing", ask)
    batch = [(client_tab.TransferJob("upload", name, "/r/" + name, is_dir), lambda: True)
             for name, is_dir in (("a", False), ("b", True), ("c", False))]

    tab._submit_all(batch)

    assert asked == [("a", True)]
    assert [(job.source, job.skip_existing) for job in enqueued] == [("b", True)]


def test_connect_is_a_pill_in_the_header(qapp, monkeypatch) -> None:
    """Connect sits beside the states as a pill (owner, 26-10-2026): a click connects the SFTP Client, and the
    pill reads what the tab says (Connecting…, Disconnect) and cannot be clicked while it connects."""
    window = MainWindow()
    toggled = []
    monkeypatch.setattr(window.sftp_tab, "toggle_connection", lambda: toggled.append(True))
    window.connect_pill.clicked.disconnect()
    window.connect_pill.clicked.connect(window.sftp_tab.toggle_connection)
    assert window.connect_pill.value.text() == "Connect" and window.connect_pill.caption.text() == "SFTP client"
    assert window.connect_pill.sizePolicy() == window.sftp_box.sizePolicy()      # as wide as the boxes beside it
    assert not hasattr(window.sftp_tab, "connect_button")
    window.connect_pill.click()
    assert toggled == [True]
    window.sftp_tab.connect_changed.emit("Connecting…", False)
    assert window.connect_pill.value.text() == "Connecting…" and not window.connect_pill.isEnabled()
    window.sftp_tab._close_connection()
    assert window.connect_pill.value.text() == "Connect" and window.connect_pill.isEnabled()
    window.close()


def test_the_password_rules_always_show_at_the_right(qapp) -> None:
    """In the SFTP Client the rules sit at the right of the form from the start, in muted text, and turn into what
    is missing (red) or a check (green) as a password is typed; the warning shows and hides as before. The Server
    Manager's form keeps the rules under the password, shown while one is typed."""
    server = common.ConnectionFields()
    assert server.password_requirements.parent() is server and not server.password_requirements.isVisibleTo(server)
    server.password.setText("abc")
    assert server.password_requirements.isVisibleTo(server) and server.password_requirements.text().startswith("✗")
    server.close()
    fields = common.ConnectionFields(rules_beside=True)
    rules, warning = fields.password_requirements, fields.password_warning
    assert rules.text().startswith("Password rules:") and rules.text().count("\n") == 1
    assert rules.parent() is None and not warning.isVisibleTo(fields)      # the tab places the rules beside the form
    tab = client_tab.SftpClientTab()
    assert tab.connection.password_requirements.parent() is tab and tab.connection.password_requirements.isVisibleTo(tab)
    tab.close()
    fields.password.setText("abc")
    assert rules.text().startswith("✗ Missing: 8 characters, 1 uppercase") and "#e57373" in rules.styleSheet()
    assert rules.text().count("\n") == 1 and warning.isVisibleTo(fields)
    fields.password.setText("Abcdefg1!")
    assert rules.text().startswith("✓") and "#81c784" in rules.styleSheet()
    fields.key_filename.setText("/home/user/.ssh/id_ed25519")
    assert rules.text().startswith("Password rules:") and not warning.isVisibleTo(fields)
    fields.close()
