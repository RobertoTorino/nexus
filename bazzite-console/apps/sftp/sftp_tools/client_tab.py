# SPDX-License-Identifier: GPL-3.0-or-later
"""The SFTP Client tab: the local and the remote folder side by side, the transfer queue below them."""

from __future__ import annotations

import os
import posixpath
import stat
from collections.abc import Callable
from typing import Any

import paramiko
from PyQt6.QtCore import QMimeData, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .app_logging import get_logger
from .common import (
    connection_header,
    ConnectionFields,
    PlainMessageBox,
    TaskRunner,
    add_file_row,
    default_profile_store,
    make_file_table,
    trust_unknown_host,
)
from .connection import UnknownHostKeyError, connect_ssh, validate_password_requirements
from .formatting import format_datetime, format_size
from .settings import current_settings
from .sound import play_beep
from .transfer_queue import TransferJob, TransferQueue
from .transfers import delete_local, delete_remote, remote_exists


class SftpClientTab(QWidget):
    status_changed = pyqtSignal(str, str)
    connect_changed = pyqtSignal(str, bool)      # the Connect pill's text (Connect, Disconnect) and whether it can be clicked

    def __init__(self) -> None:
        super().__init__()
        self.queue = TransferQueue(self)
        self.queue.filter_invalid_chars = current_settings().filter_invalid_chars
        self.queue.char_replacement = current_settings().invalid_char_replacement
        self.queue.queue_autoclear = current_settings().queue_autoclear
        self.queue.preserve_timestamps = current_settings().preserve_timestamps
        self.queue.job_finished.connect(self._transfer_finished)
        self.queue.beep_requested.connect(self._play_completion_beep)
        self.connection = ConnectionFields(rules_beside=True)
        self.connection.bind_profiles(default_profile_store())
        self.status = QLabel("Not connected")
        self.status.setWordWrap(True)
        self.local_path = QLineEdit(
            os.path.expanduser(current_settings().default_local_folder or "~")
        )
        self.remote_path = QLineEdit("/")
        self.local_table = make_file_table(LocalFileTable)
        self.remote_table = make_file_table(RemoteFileTable)
        self.local_refresh_button = QPushButton("Refresh")
        self.remote_refresh_button = QPushButton("Refresh")
        self.upload_button = QPushButton("Upload →")
        self.download_button = QPushButton("← Download")
        self._connection_values: tuple[str, int, str, str, str] | None = None
        self._pending_connection_error: Exception | None = None
        self._ssh: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None
        self._worker: TaskRunner | None = None
        self._workers: set[TaskRunner] = set()

        local_group = QGroupBox("Local")
        local_layout = QVBoxLayout(local_group)
        local_path_row = QHBoxLayout()
        local_path_row.addWidget(self.local_path, 1)
        local_path_row.addWidget(self.local_refresh_button)
        local_layout.addLayout(local_path_row)
        local_layout.addWidget(self.local_table)
        remote_group = QGroupBox("Remote SFTP")
        remote_layout = QVBoxLayout(remote_group)
        remote_path_row = QHBoxLayout()
        remote_path_row.addWidget(self.remote_path, 1)
        remote_path_row.addWidget(self.remote_refresh_button)
        remote_layout.addLayout(remote_path_row)
        remote_layout.addWidget(self.remote_table)
        file_row = QHBoxLayout()
        file_row.addWidget(local_group)
        file_row.addWidget(remote_group)
        transfer_row = QHBoxLayout()
        transfer_row.addStretch()
        transfer_row.addWidget(self.upload_button)
        transfer_row.addWidget(self.download_button)

        files = QWidget()
        files_layout = QVBoxLayout(files)
        files_layout.setContentsMargins(0, 0, 0, 0)
        files_layout.addLayout(file_row, 1)
        files_layout.addLayout(transfer_row)
        # Drag the handle between the file panes and the transfer lists to resize.
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(files)
        splitter.addWidget(TransferPanel(self.queue))
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([480, 140])

        layout = QVBoxLayout(self)
        beside = QVBoxLayout()                  # the column where Connect was: the password rules, always shown
        self.connection.rules_beside(beside)
        beside.addStretch()
        layout.addLayout(connection_header(self.connection, beside, wide=True))
        layout.addWidget(splitter, 1)

        self.local_path.editingFinished.connect(self.refresh_local)
        self.remote_path.editingFinished.connect(self.refresh_remote)
        self.local_table.cellDoubleClicked.connect(self.open_local_directory)
        self.remote_table.cellDoubleClicked.connect(self.open_remote_directory)
        self.local_table.customContextMenuRequested.connect(
            lambda pos: self._show_menu(self.local_table, pos, "Upload", self.upload_selected, self.delete_local_selected)
        )
        self.remote_table.customContextMenuRequested.connect(
            lambda pos: self._show_menu(self.remote_table, pos, "Download", self.download_selected, self.delete_remote_selected)
        )
        self.local_refresh_button.clicked.connect(self.refresh_local)
        self.remote_refresh_button.clicked.connect(self.refresh_remote)
        self.upload_button.clicked.connect(self.upload_selected)
        self.download_button.clicked.connect(self.download_selected)
        self.remote_table.files_dropped.connect(self.upload_paths)
        self.refresh_local()
        self.status_changed.emit("Disconnected", "neutral")

    def settings_changed(self, hidden_files_changed: bool) -> None:
        """The settings dialog saved: the queue takes the new transfer settings, the lists the hidden-files choice."""
        settings = current_settings()
        self.queue.filter_invalid_chars = settings.filter_invalid_chars
        self.queue.char_replacement = settings.invalid_char_replacement
        self.queue.queue_autoclear = settings.queue_autoclear
        self.queue.preserve_timestamps = settings.preserve_timestamps
        if hidden_files_changed:
            self.refresh_local()
            self.refresh_remote()

    def _run(self, operation: Callable[[], Any], done: Callable[[Any], None]) -> None:
        if self._worker is not None:
            return
        worker = TaskRunner(operation, self)
        self._worker = worker
        self._workers.add(worker)
        worker.succeeded.connect(lambda result: self._finish_task(done, result))
        worker.failed.connect(self._show_task_error)
        worker.finished.connect(lambda worker=worker: self._release_worker(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _release_worker(self, worker: TaskRunner) -> None:
        self._workers.discard(worker)

    @property
    def has_running_tasks(self) -> bool:
        return self.queue.is_busy or any(w.isRunning() for w in self._workers)

    def _finish_task(self, done: Callable[[Any], None], result: Any) -> None:
        self._worker = None
        done(result)

    def _show_task_error(self, message: str) -> None:
        self._worker = None
        self.connect_changed.emit("Disconnect" if self._ssh is not None else "Connect", True)
        self.status.setText("Operation failed")
        self.status_changed.emit("Connection/operation error", "error")
        if (
            isinstance(self._pending_connection_error, UnknownHostKeyError)
            and self._connection_values is not None
        ):
            trusted = trust_unknown_host(
                self,
                self._pending_connection_error,
            )
            self._pending_connection_error = None
            if trusted:
                self._start_connection(self._connection_values)
                return
            self._connection_values = None
            return
        PlainMessageBox.critical(self, "SFTP operation failed", message)

    def toggle_connection(self) -> None:
        if self._worker is not None:
            return
        if self._ssh is not None:
            self._close_connection()
            return
        self._connection_values = self.connection.values()

        # Validate password requirements if password is being used
        host, port, username, password, key_filename = self._connection_values
        if password and not key_filename.strip():
            is_valid, error_msg = validate_password_requirements(password)
            if not is_valid:
                PlainMessageBox.critical(
                    self,
                    "Password Security Requirements",
                    f"Connection refused: {error_msg}\n\n"
                    "Password must have:\n"
                    "• At least 8 characters\n"
                    "• At least 1 uppercase letter\n"
                    "• At least 1 number\n"
                    "• At least 1 special character (!@#$%^&*()_+-=[]{}|;:,.<>?.)"
                )
                return

        self._start_connection(self._connection_values)

    def _start_connection(
        self, values: tuple[str, int, str, str, str]
    ) -> None:

        def open_sftp() -> tuple[paramiko.SSHClient, paramiko.SFTPClient]:
            try:
                client = connect_ssh(
                    *values,
                    timeout=current_settings().connection_timeout,
                    compression=current_settings().sftp_compression,
                    keepalive_interval=current_settings().keepalive_interval,
                    reconnect_count=current_settings().reconnect_count,
                    reconnect_delay=current_settings().reconnect_delay,
                )
            except UnknownHostKeyError as error:
                self._pending_connection_error = error
                raise
            try:
                return client, client.open_sftp()
            except Exception:
                client.close()
                raise

        self.connect_changed.emit("Connecting…", False)
        self.status.setText("Connecting…")
        self.status_changed.emit("Connecting…", "warning")
        self._pending_connection_error = None
        self._run(open_sftp, self._connected)

    def _connected(
        self, result: tuple[paramiko.SSHClient, paramiko.SFTPClient]
    ) -> None:
        self._ssh, self._sftp = result
        self.queue.set_sftp(self._sftp)
        self.connect_changed.emit("Disconnect", True)
        self.status.setText("Connected")
        get_logger().info("SFTP connected")
        self.status_changed.emit("Connected", "success")
        self.remote_table.accept_files = True
        self.remote_path.setText(self._remote_home())
        self.refresh_remote()

    def _remote_home(self) -> str:
        # Start in the login home: /var/home/<user> on Bazzite, /C:/Users/<user> on Windows.
        assert self._sftp is not None
        try:
            home = self._sftp.normalize(".")
        except OSError:
            return "/"
        if home.startswith("/home/"):
            home = "/var" + home
        return home

    def _close_connection(self) -> None:
        self.queue.abort_all()
        if self._sftp is not None:
            self._sftp.close()
        if self._ssh is not None:
            self._ssh.close()
        self._sftp = None
        self._ssh = None
        self.connect_changed.emit("Connect", True)
        self.status.setText("Not connected")
        self.status_changed.emit("Disconnected", "neutral")
        self.remote_table.accept_files = False
        self.remote_table.setRowCount(0)

    def refresh_local(self) -> None:
        path = os.path.abspath(os.path.expanduser(self.local_path.text()))
        try:
            entries = list(os.scandir(path))
            entries.sort(key=lambda item: (not item.is_dir(follow_symlinks=True), item.name.casefold()))
        except OSError as error:
            get_logger().error("Cannot read local folder %s: %s", path, error)
            PlainMessageBox.critical(self, "Cannot read local folder", str(error))
            return

        self.local_path.setText(path)
        self.local_table.setSortingEnabled(False)      # a sorted insert moves the row the next cell goes to
        self.local_table.setRowCount(0)
        parent = os.path.dirname(path)
        if parent != path:
            add_file_row(self.local_table, "..", "Folder", "", parent, "")
        settings = current_settings()
        for entry in entries:
            if not settings.view_hidden_files and entry.name.startswith("."):
                continue
            try:
                stat_info = entry.stat(follow_symlinks=True)
                is_dir = entry.is_dir(follow_symlinks=True)
                size = "" if is_dir else format_size(stat_info.st_size, settings)
                modified = format_datetime(stat_info.st_mtime, settings)
            except OSError:
                is_dir, size, modified = False, "", ""
            add_file_row(
                self.local_table,
                entry.name,
                "Folder" if is_dir else "File",
                size,
                entry.path,
                modified,
            )
        self.local_table.setSortingEnabled(True)

    def refresh_remote(self) -> None:
        if self._sftp is None:
            return
        path = self.remote_path.text().strip() or "/"
        self.status.setText("Reading remote folder…")

        def list_remote() -> tuple[str, list[paramiko.SFTPAttributes]]:
            assert self._sftp is not None
            return path, self._sftp.listdir_attr(path)

        self._run(list_remote, self._show_remote_entries)

    def _show_remote_entries(
        self, result: tuple[str, list[paramiko.SFTPAttributes]]
    ) -> None:
        path, entries = result
        path = posixpath.normpath(path)
        self.remote_path.setText(path)
        self.remote_table.setSortingEnabled(False)      # a sorted insert moves the row the next cell goes to
        self.remote_table.setRowCount(0)
        parent = posixpath.dirname(path)
        if parent != path:
            add_file_row(self.remote_table, "..", "Folder", "", parent, "")
        settings = current_settings()
        entries.sort(
            key=lambda item: (
                not stat.S_ISDIR(item.st_mode or 0),
                item.filename.casefold(),
            )
        )
        for entry in entries:
            if not settings.view_hidden_files and entry.filename.startswith("."):
                continue
            is_dir = stat.S_ISDIR(entry.st_mode or 0)
            size = "" if is_dir else format_size(entry.st_size, settings)
            modified = format_datetime(entry.st_mtime, settings)
            add_file_row(
                self.remote_table,
                entry.filename,
                "Folder" if is_dir else "File",
                size,
                posixpath.join(path, entry.filename),
                modified,
            )
        self.remote_table.setSortingEnabled(True)
        self.status.setText("Connected")

    def open_local_directory(self, row: int, _column: int) -> None:
        item = self.local_table.item(row, 0)
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if os.path.isdir(path):
            self.local_path.setText(path)
            self.refresh_local()

    def open_remote_directory(self, row: int, _column: int) -> None:
        item = self.remote_table.item(row, 0)
        if item is None or self._sftp is None:
            return
        kind = self.remote_table.item(row, 1)
        if kind is None or kind.text() != "Folder":
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        self.remote_path.setText(path)
        self.refresh_remote()

    @staticmethod
    def _selected_rows(table: QTableWidget) -> list[tuple[str, str, bool]]:
        """The selected rows as (name, path, is folder), in list order, without the parent folder's row."""
        rows = sorted(index.row() for index in table.selectionModel().selectedRows())
        selected = []
        for row in rows:
            item, kind = table.item(row, 0), table.item(row, 1)
            if item is None or kind is None or item.text() == "..":
                continue
            selected.append((item.text(), item.data(Qt.ItemDataRole.UserRole), kind.text() == "Folder"))
        return selected

    def upload_selected(self) -> None:
        self.upload_paths([path for _name, path, _is_dir in self._selected_rows(self.local_table)])

    def upload_paths(self, paths: list[str]) -> None:
        """Queue local files and folders for the remote folder that is open (the Upload button, or a drop)."""
        if self._sftp is None:
            return
        sftp = self._sftp
        batch = []
        for source in paths:
            destination = posixpath.join(self.remote_path.text(), os.path.basename(source))
            job = TransferJob("upload", source, destination, os.path.isdir(source))
            batch.append((job, lambda destination=destination: remote_exists(sftp, destination)))
        self._submit_all(batch)

    def download_selected(self) -> None:
        if self._sftp is None:
            return
        local = os.path.abspath(os.path.expanduser(self.local_path.text()))
        batch = []
        for _name, source, is_dir in self._selected_rows(self.remote_table):
            destination = os.path.join(local, posixpath.basename(source))
            job = TransferJob("download", source, destination, is_dir)
            batch.append((job, lambda destination=destination: os.path.exists(destination)))
        self._submit_all(batch)

    def _show_menu(
        self,
        table: QTableWidget,
        pos: Any,
        transfer_label: str,
        transfer: Callable[[], None],
        delete: Callable[[], None],
    ) -> None:
        item = table.itemAt(pos)
        if item is None or table.item(item.row(), 0).text() == "..":
            return
        if not item.isSelected():
            table.clearSelection()
            table.selectRow(item.row())
        menu = QMenu(table)
        transfer_action = menu.addAction(transfer_label)
        transfer_action.setEnabled(self._sftp is not None)
        delete_action = menu.addAction("Delete")
        delete_action.setEnabled(table is not self.remote_table or self._sftp is not None)
        chosen = menu.exec(table.viewport().mapToGlobal(pos))
        if chosen is transfer_action:
            transfer()
        elif chosen is delete_action:
            delete()

    def _confirm_delete(self, selected: list[tuple[str, str, bool]], where: str) -> bool:
        if len(selected) == 1:
            _name, path, is_dir = selected[0]
            kind = "folder" if is_dir else "file"
            what, names, lost = f"this {kind}", path, f"your {kind} will be lost"
        else:
            what = f"these {len(selected)} files and folders"
            names = "\n".join(path for _name, path, _is_dir in selected)
            lost = "they will be lost"
        answer = PlainMessageBox.question(
            self,
            "Delete",
            f"Are you sure you want to delete {what} ({where})?\n\n{names}\n\n"
            f"This action is irreversible and {lost} forever.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def delete_local_selected(self) -> None:
        selected = self._selected_rows(self.local_table)
        if not selected or not self._confirm_delete(
            [(name, path, os.path.isdir(path) and not os.path.islink(path)) for name, path, _d in selected],
            "on this computer",
        ):
            return
        for _name, path, _is_dir in selected:
            try:
                delete_local(path)
            except OSError as error:
                get_logger().error("Could not delete %s: %s", path, error)
                PlainMessageBox.critical(self, "Could not delete", str(error))
        self.refresh_local()

    def delete_remote_selected(self) -> None:
        selected = self._selected_rows(self.remote_table)
        if not selected or self._sftp is None:
            return
        if not self._confirm_delete(selected, "on the server"):
            return
        sftp = self._sftp
        paths = [path for _name, path, _is_dir in selected]
        self.status.setText(f"Deleting {selected[0][0]}…" if len(selected) == 1 else f"Deleting {len(selected)} items…")

        def delete_all() -> None:
            for path in paths:
                delete_remote(sftp, path)

        self._run(delete_all, lambda _r: self.refresh_remote())

    def _submit_all(self, batch: list[tuple[TransferJob, Callable[[], bool]]]) -> None:
        """Queue the jobs; when the question about an existing target is answered for the rest, it is asked once."""
        settings = current_settings()
        for_the_rest: str | None = None
        for index, (job, exists) in enumerate(batch):
            job.limit_kbps = settings.speed_limit_kbps
            if exists():
                mode = for_the_rest or settings.overwrite_mode
                if mode == "ask":
                    answer = self._ask_existing(job, more=index + 1 < len(batch))
                    if answer is None:
                        return
                    mode, same_for_rest = answer
                    if same_for_rest:
                        for_the_rest = mode
                if mode == "skip":
                    if not job.is_dir:
                        continue
                    job.skip_existing = True
            self.queue.enqueue(job)

    def _ask_existing(self, job: TransferJob, more: bool) -> tuple[str, bool] | None:
        """Overwrite or skip an existing target: the choice and whether it holds for the rest, or None to cancel."""
        what = "merge into the existing folder" if job.is_dir else "overwrite it"
        box = QMessageBox(self)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setWindowTitle("Already exists")
        box.setText(f"{job.destination} already exists. Do you want to {what}?")
        overwrite = box.addButton("Overwrite", QMessageBox.ButtonRole.AcceptRole)
        skip = box.addButton("Skip existing", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        if more:
            box.setCheckBox(QCheckBox("Do the same for the other files that exist"))
        box.exec()
        clicked = box.clickedButton()
        same_for_rest = box.checkBox() is not None and box.checkBox().isChecked()
        if clicked is skip:
            return "skip", same_for_rest
        if clicked is overwrite:
            return "overwrite", same_for_rest
        return None

    def _transfer_finished(self, job: TransferJob) -> None:
        if job.direction == "upload":
            self.refresh_remote()
        else:
            self.refresh_local()

    def _play_completion_beep(self) -> None:
        if current_settings().sound_on_transfer_complete:
            play_beep()


class LocalFileTable(QTableWidget):
    """The local list: dragged rows carry their paths as file URLs, for the remote list or a file manager."""

    def __init__(self, rows: int, columns: int) -> None:
        super().__init__(rows, columns)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def mimeData(self, items: Any) -> QMimeData:
        data = QMimeData()
        data.setUrls([
            QUrl.fromLocalFile(item.data(Qt.ItemDataRole.UserRole))
            for item in items
            if item.column() == 0 and item.text() != ".."
        ])
        return data

    def startDrag(self, _actions: Any) -> None:
        # Copy only: a move would let a file manager take the files and the view drop their rows.
        super().startDrag(Qt.DropAction.CopyAction)


class RemoteFileTable(QTableWidget):
    """The remote list: local files and folders dropped on it, from the local list or a file manager, are
    offered to files_dropped while it is connected."""

    files_dropped = pyqtSignal(list)

    def __init__(self, rows: int, columns: int) -> None:
        super().__init__(rows, columns)
        self.accept_files = False
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

    def _local_paths(self, event: QDragEnterEvent | QDragMoveEvent | QDropEvent) -> list[str]:
        if not self.accept_files or not event.mimeData().hasUrls():
            return []
        return [os.path.normpath(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        # Always a copy: a file manager that is told "moved" deletes its files.
        if self._local_paths(event):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        self.dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        paths = self._local_paths(event)
        if not paths:
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.files_dropped.emit(paths)


class TransferPanel(QTabWidget):
    """Queued, failed and successful transfer lists."""

    def __init__(self, queue: TransferQueue) -> None:
        super().__init__()
        self.queue = queue
        self.lists = {
            state: QListWidget() for state in ("queued", "failed", "done")
        }
        self.titles = {"queued": "Queued files", "failed": "Failed transfers", "done": "Successful transfers"}
        for state, widget in self.lists.items():
            self.addTab(widget, self.titles[state])
        self.setMinimumHeight(60)
        queue.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        for index, state in enumerate(self.lists):
            jobs = self.queue.jobs_in(state)
            if state == "queued":
                jobs = self.queue.jobs_in("running") + jobs
            widget = self.lists[state]
            widget.clear()
            for job in jobs:
                text = job.label
                if job.state == "running":
                    text += "  (in progress)"
                elif job.error:
                    text += f"  — {job.error}"
                widget.addItem(text)
            self.setTabText(index, f"{self.titles[state]} ({len(jobs)})")
