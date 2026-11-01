# SPDX-License-Identifier: GPL-3.0-or-later
"""Files and folders up and down (transfers.py), on a fake server: whole trees, a file that is there skipped when
asked, the server's time kept, a name Windows refuses made safe, the sizes counted, and deleting on either side."""

from __future__ import annotations

import os

import pytest

from fake_sftp import FakeSFTP
from sftp_tools import transfers


@pytest.fixture
def server(tmp_path):
    return FakeSFTP(tmp_path / "server")


def test_a_folder_goes_up_and_down_again(server, tmp_path):
    source = tmp_path / "photos"
    (source / "2026").mkdir(parents=True)
    (source / "a.jpg").write_bytes(b"a" * 10)
    (source / "2026" / "b.jpg").write_bytes(b"b" * 5)
    moved = []
    assert transfers.upload_tree(server, str(source), "/var/home/me/photos", moved.append) == 2
    assert sum(moved) == 15
    assert (server.local("/var/home/me/photos/2026/b.jpg")).read_bytes() == b"b" * 5
    assert transfers.remote_size(server, "/var/home/me/photos") == 15 == transfers.local_size(str(source))
    back = tmp_path / "back"
    assert transfers.download_tree(server, "/var/home/me/photos", str(back)) == 2
    assert (back / "2026" / "b.jpg").read_bytes() == b"b" * 5


def test_a_file_that_is_there_is_skipped_when_asked(server, tmp_path):
    (server.local("/var/home/me/notes.txt")).write_text("server")
    local = tmp_path / "notes.txt"
    local.write_text("mine")
    assert not transfers.get_file(server, "/var/home/me/notes.txt", str(local), skip_existing=True)
    assert local.read_text() == "mine"
    assert not transfers.put_file(server, str(local), "/var/home/me/notes.txt", skip_existing=True)
    assert transfers.get_file(server, "/var/home/me/notes.txt", str(local))
    assert local.read_text() == "server"


def test_a_download_keeps_the_servers_time(server, tmp_path):
    remote = server.local("/var/home/me/old.txt")
    remote.write_text("old")
    os.utime(remote, (1_600_000_000, 1_600_000_000))
    local = tmp_path / "old.txt"
    transfers.get_file(server, "/var/home/me/old.txt", str(local))
    assert int(local.stat().st_mtime) == 1_600_000_000
    transfers.get_file(server, "/var/home/me/old.txt", str(local), preserve_times=False)
    assert int(local.stat().st_mtime) != 1_600_000_000


def test_a_name_windows_refuses_is_made_safe():
    assert transfers.windows_name('a<b>c:d"e|f?g*h.txt') == "a_b_c_d_e_f_g_h.txt"
    for unsafe in ("..", "a/b", "a\\b", ""):
        with pytest.raises(ValueError):
            transfers.safe_name(unsafe)


def test_deleting_on_both_sides(server, tmp_path):
    folder = server.local("/var/home/me/old")
    (folder / "inner").mkdir(parents=True)
    (folder / "inner" / "x").write_text("x")
    transfers.delete_remote(server, "/var/home/me/old")
    assert not folder.exists()
    mine = tmp_path / "mine"
    (mine / "inner").mkdir(parents=True)
    (mine / "inner" / "y").write_text("y")
    transfers.delete_local(str(mine))
    assert not mine.exists()
