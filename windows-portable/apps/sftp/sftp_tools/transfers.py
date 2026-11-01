# SPDX-License-Identifier: GPL-3.0-or-later
"""Files and folders up and down over SFTP, as the BC250 suite's SFTP Tools moves them (transfers.py there), and
deleting them on either side. A downloaded name gets the characters Windows refuses in a name replaced (< > : " | ? *),
as a file named so on the server could not be written here otherwise. Qt-free; *progress* is told each block's bytes.
"""

from __future__ import annotations

import os
import posixpath
import shutil
import stat
from collections.abc import Callable

import paramiko

Progress = Callable[[int], None]
INVALID = '<>:"|?*'
REPLACEMENT = "_"


def _delta_callback(progress: Progress | None) -> Callable[[int, int], None] | None:
    if progress is None:
        return None
    last = [0]

    def callback(done: int, _total: int) -> None:
        progress(done - last[0])
        last[0] = done

    return callback


def remote_exists(sftp: paramiko.SFTPClient, path: str) -> bool:
    try:
        sftp.stat(path)
    except OSError:
        return False
    return True


def remote_is_dir(sftp: paramiko.SFTPClient, path: str) -> bool:
    try:
        return stat.S_ISDIR(sftp.stat(path).st_mode or 0)
    except OSError:
        return False


def safe_name(name: str) -> str:
    """A server's name that could leave the folder it is downloaded to is refused."""
    if name in ("", ".", "..") or "/" in name or "\\" in name or "\0" in name:
        raise ValueError(f"Refusing an unsafe file name from the server: {name!r}")
    return name


def windows_name(name: str) -> str:
    """*name* with the characters Windows refuses in a file name replaced."""
    for char in INVALID:
        name = name.replace(char, REPLACEMENT)
    return name


def put_file(sftp: paramiko.SFTPClient, source: str, destination: str, progress: Progress | None = None,
             skip_existing: bool = False) -> bool:
    """Upload one file; False when skipped because it is there."""
    if skip_existing and remote_exists(sftp, destination):
        return False
    sftp.put(source, destination, callback=_delta_callback(progress))
    return True


def get_file(sftp: paramiko.SFTPClient, source: str, destination: str, progress: Progress | None = None,
             skip_existing: bool = False, preserve_times: bool = True) -> bool:
    """Download one file; False when skipped because it is there. With *preserve_times* it keeps the server's
    modification time."""
    if skip_existing and os.path.exists(destination):
        return False
    remote = sftp.stat(source) if preserve_times else None
    sftp.get(source, destination, callback=_delta_callback(progress))
    if remote is not None and remote.st_mtime is not None:
        os.utime(destination, (remote.st_atime or remote.st_mtime, remote.st_mtime))
    return True


def _ensure_remote_dir(sftp: paramiko.SFTPClient, path: str) -> None:
    try:
        sftp.mkdir(path)
    except OSError:
        if not stat.S_ISDIR(sftp.stat(path).st_mode or 0):
            raise


def upload_tree(sftp: paramiko.SFTPClient, source: str, destination: str, progress: Progress | None = None,
                skip_existing: bool = False) -> int:
    """Upload a local folder to *destination*; the files uploaded."""
    _ensure_remote_dir(sftp, destination)
    count = 0
    for entry in os.scandir(source):
        target = posixpath.join(destination, entry.name)
        if entry.is_dir(follow_symlinks=True):
            count += upload_tree(sftp, entry.path, target, progress, skip_existing)
        elif put_file(sftp, entry.path, target, progress, skip_existing):
            count += 1
    return count


def download_tree(sftp: paramiko.SFTPClient, source: str, destination: str, progress: Progress | None = None,
                  skip_existing: bool = False, preserve_times: bool = True) -> int:
    """Download a server's folder to *destination*; the files downloaded."""
    os.makedirs(destination, exist_ok=True)
    count = 0
    for entry in sftp.listdir_attr(source):
        name = windows_name(safe_name(entry.filename))
        remote = posixpath.join(source, entry.filename)
        target = os.path.join(destination, name)
        if stat.S_ISDIR(entry.st_mode or 0):
            count += download_tree(sftp, remote, target, progress, skip_existing, preserve_times)
        elif get_file(sftp, remote, target, progress, skip_existing, preserve_times):
            count += 1
    return count


def local_size(path: str) -> int:
    """The bytes of a file, or of every file in a folder."""
    if not os.path.isdir(path):
        return os.path.getsize(path)
    total = 0
    for folder, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(folder, name))
            except OSError:
                continue
    return total


def remote_size(sftp: paramiko.SFTPClient, path: str) -> int:
    """The bytes of a server's file, or of every file in its folder."""
    attributes = sftp.stat(path)
    if not stat.S_ISDIR(attributes.st_mode or 0):
        return attributes.st_size or 0
    total = 0
    for entry in sftp.listdir_attr(path):
        if stat.S_ISDIR(entry.st_mode or 0):
            total += remote_size(sftp, posixpath.join(path, entry.filename))
        else:
            total += entry.st_size or 0
    return total


def delete_remote(sftp: paramiko.SFTPClient, path: str) -> None:
    """Delete a server's file or folder tree; a link is removed, not followed."""
    mode = sftp.lstat(path).st_mode or 0
    if not stat.S_ISDIR(mode):
        sftp.remove(path)
        return
    for entry in sftp.listdir_attr(path):
        delete_remote(sftp, posixpath.join(path, safe_name(entry.filename)))
    sftp.rmdir(path)


def delete_local(path: str) -> None:
    """Delete a local file or folder tree; a link is removed, not followed."""
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.remove(path)
