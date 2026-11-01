# SPDX-License-Identifier: GPL-3.0-or-later
"""The two sides as rows (folders.py): the server's folders from the home, shown as ~ (no user name on the screen),
B up to the home; this device's from the places; folders first, files with their size; the hidden ones on request;
the private keys in .ssh."""

from __future__ import annotations

from pathlib import Path

from fake_sftp import FakeSFTP
from sftp_tools import folders
from sftp_tools.folders import LocalFolder, RemoteFolder


def test_sizes_read_as_the_bc250_apps_auto():
    assert [folders.size_text(n) for n in (0, 512, 2458, 12_897_485, 1_288_490_189)] == [
        "0 B", "512 B", "2.4 KB", "12.3 MB", "1.2 GB"]


def test_the_servers_folder_lists_folders_first_without_the_hidden(tmp_path):
    server = FakeSFTP(tmp_path)
    home = server.local("/var/home/me")
    (home / "Games").mkdir()
    (home / ".config").mkdir()
    (home / "b.txt").write_bytes(b"12345")
    (home / "A.txt").write_bytes(b"1")
    entries = folders.remote_entries(server, "/var/home/me")
    assert [(e.name, e.is_dir) for e in entries] == [("Games", True), ("A.txt", False), ("b.txt", False)]
    assert [e.name for e in folders.remote_entries(server, "/var/home/me", hidden=True)][:2] == [".config", "Games"]
    remote = RemoteFolder("/var/home/me")
    assert remote.rows(entries) == [
        ("up", "‹ /var/home"), ("dir:/var/home/me/Games", "Games  ›"),
        ("file:/var/home/me/A.txt", "A.txt  ·  1 B"), ("file:/var/home/me/b.txt", "b.txt  ·  5 B")]


def test_the_servers_paths_are_shown_from_the_home_and_b_stops_there():
    remote = RemoteFolder("/var/home/me")
    assert remote.shown() == "~" and not remote.back()            # at the home: B goes to the card
    assert remote.open("dir:/var/home/me/Games") and remote.shown() == "~/Games"
    assert remote.back() and remote.path == "/var/home/me"
    assert remote.open("up") and remote.shown() == "/var/home"   # the ‹ row goes above it
    assert remote.back() and remote.path == "/var"
    remote.path = "/"
    assert remote.parent() is None and not remote.back() and remote.rows([]) == []
    assert not remote.open("file:/x")


def test_this_device_starts_at_the_places_and_lists_every_file(tmp_path):
    (tmp_path / "Downloads").mkdir()
    (tmp_path / "Downloads" / "save.bin").write_bytes(b"x" * 2048)
    (tmp_path / "Downloads" / ".hidden").write_text("")
    drive = tmp_path / "E"
    drive.mkdir()
    local = LocalFolder([tmp_path / "Downloads", drive])
    assert [key for key, _ in local.rows()] == [f"dir:{tmp_path / 'Downloads'}", f"dir:{drive}"]
    assert local.target(tmp_path) == tmp_path                   # at the places: the downloads folder
    local.open(f"dir:{tmp_path / 'Downloads'}")
    assert local.rows()[1:] == [(f"file:{tmp_path / 'Downloads' / 'save.bin'}", "save.bin  ·  2.0 KB")]
    local.hidden = True
    assert len(local.rows()) == 3
    assert local.target(tmp_path) == tmp_path / "Downloads"
    assert local.up() and local.path is None


def test_the_downloads_folder_and_the_keys(tmp_path):
    assert folders.downloads_folder(tmp_path) == tmp_path
    (tmp_path / "Downloads").mkdir()
    assert folders.downloads_folder(tmp_path) == tmp_path / "Downloads"
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    for name in ("id_ed25519", "id_ed25519.pub", "board", "board.pub", "known_hosts", "config", "notes"):
        (ssh / name).write_text("")
    assert [p.name for p in folders.private_keys(tmp_path)] == ["board", "id_ed25519"]
    assert folders.private_keys(Path(tmp_path / "nobody")) == []
