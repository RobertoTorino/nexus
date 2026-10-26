# SPDX-License-Identifier: GPL-3.0-or-later

import stat
from pathlib import Path
from types import SimpleNamespace

from sftp_tools.transfers import download_tree, upload_tree


class FakeSftp:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _p(self, path: str) -> Path:
        return self.root / path.lstrip("/")

    def mkdir(self, path):
        self._p(path).mkdir()

    def stat(self, path):
        s = self._p(path).stat()
        return SimpleNamespace(
            st_mode=s.st_mode,
            st_mtime=s.st_mtime,
            st_atime=s.st_atime,
        )

    def put(self, src, dst, callback=None):
        self._p(dst).write_bytes(Path(src).read_bytes())

    def get(self, src, dst, callback=None):
        Path(dst).write_bytes(self._p(src).read_bytes())

    def listdir_attr(self, path):
        return [
            SimpleNamespace(filename=p.name, st_mode=p.stat().st_mode)
            for p in self._p(path).iterdir()
        ]


def test_round_trip(tmp_path):
    local = tmp_path / "local" / "src"
    (local / "sub").mkdir(parents=True)
    (local / "a.txt").write_text("a")
    (local / "sub" / "b.txt").write_text("b")
    remote_root = tmp_path / "remote"
    remote_root.mkdir()
    sftp = FakeSftp(remote_root)

    assert upload_tree(sftp, str(local), "/src") == 2
    assert (remote_root / "src" / "sub" / "b.txt").read_text() == "b"

    out = tmp_path / "out"
    assert download_tree(sftp, "/src", str(out)) == 2
    assert (out / "sub" / "b.txt").read_text() == "b"


def test_progress_reports_bytes(tmp_path):
    local = tmp_path / "f"
    local.write_text("abc")
    seen = []

    class Sftp(FakeSftp):
        def put(self, src, dst, callback=None):
            super().put(src, dst)
            if callback:
                callback(3, 3)

    from sftp_tools.transfers import put_file

    (tmp_path / "r").mkdir()
    put_file(Sftp(tmp_path / "r"), str(local), "/f", seen.append)
    assert seen == [3]


def test_skip_existing(tmp_path):
    local = tmp_path / "src"
    local.mkdir()
    (local / "a.txt").write_text("new")
    (local / "b.txt").write_text("b")
    root = tmp_path / "remote"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.txt").write_text("old")

    class Sftp(FakeSftp):
        def stat(self, path):
            return super().stat(path)

    assert upload_tree(Sftp(root), str(local), "/src", skip_existing=True) == 1
    assert (root / "src" / "a.txt").read_text() == "old"
    assert (root / "src" / "b.txt").read_text() == "b"


def test_download_rejects_traversal(tmp_path):
    import pytest

    class Evil(FakeSftp):
        def listdir_attr(self, path):
            return [SimpleNamespace(filename="../evil", st_mode=0o100644)]

    with pytest.raises(ValueError):
        download_tree(Evil(tmp_path), "/", str(tmp_path / "out"))
    assert not (tmp_path / "evil").exists()


def test_delete_local_and_symlink(tmp_path):
    from sftp_tools.transfers import delete_local

    target = tmp_path / "keep"
    target.mkdir()
    (target / "f").write_text("x")
    tree = tmp_path / "tree"
    (tree / "sub").mkdir(parents=True)
    (tree / "sub" / "a").write_text("a")
    (tree / "link").symlink_to(target)
    delete_local(str(tree))
    assert not tree.exists()
    assert (target / "f").exists()


def test_delete_remote_tree(tmp_path):
    from sftp_tools.transfers import delete_remote

    class Sftp(FakeSftp):
        def lstat(self, path):
            return self.stat(path)

        def remove(self, path):
            self._p(path).unlink()

        def rmdir(self, path):
            self._p(path).rmdir()

    (tmp_path / "d" / "s").mkdir(parents=True)
    (tmp_path / "d" / "s" / "f").write_text("x")
    delete_remote(Sftp(tmp_path), "/d")
    assert not (tmp_path / "d").exists()


def test_sanitize_filename():
    from sftp_tools.transfers import sanitize_filename
    
    # Test normal names unchanged
    assert sanitize_filename("document.txt") == "document.txt"
    assert sanitize_filename("folder_name") == "folder_name"
    
    # Test invalid Windows characters replaced
    assert sanitize_filename("file:name") == "file_name"
    assert sanitize_filename("file?name") == "file_name"
    assert sanitize_filename("file<name>") == "file_name_"
    assert sanitize_filename("file|name") == "file_name"
    assert sanitize_filename("file*name") == "file_name"
    assert sanitize_filename("file\"name") == "file_name"
    
    # Test multiple invalid characters
    assert sanitize_filename("file:?name<>") == "file__name__"
    
    # Test custom replacement
    assert sanitize_filename("file:name", "-") == "file-name"
    assert sanitize_filename("file?<name", "X") == "fileXXname"
    
    # Test that forward slash is NOT sanitized (path separator)
    assert sanitize_filename("path/to/file") == "path/to/file"
    
    # Test backslash NOT sanitized (path separator)
    assert sanitize_filename("path\\to\\file") == "path\\to\\file"
