# SPDX-License-Identifier: GPL-3.0-or-later
"""Recursive SFTP transfer helpers."""

from __future__ import annotations

import os
import posixpath
import shutil
import stat
from collections.abc import Callable

import paramiko

Progress = Callable[[int], None]


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


def put_file(
    sftp: paramiko.SFTPClient,
    source: str,
    destination: str,
    progress: Progress | None = None,
    skip_existing: bool = False,
) -> bool:
    """Upload one file; return False when skipped because it exists."""
    if skip_existing and remote_exists(sftp, destination):
        return False
    sftp.put(source, destination, callback=_delta_callback(progress))
    return True


def get_file(
    sftp: paramiko.SFTPClient,
    source: str,
    destination: str,
    progress: Progress | None = None,
    skip_existing: bool = False,
    preserve_timestamps: bool = True,
) -> bool:
    """Download one file; return False when skipped because it exists."""
    if skip_existing and os.path.exists(destination):
        return False

    # Get remote file's stat for timestamp preservation
    remote_stat = sftp.stat(source) if preserve_timestamps else None

    sftp.get(source, destination, callback=_delta_callback(progress))

    # Set local file's modification time to match remote file
    if preserve_timestamps and remote_stat is not None:
        os.utime(destination, (remote_stat.st_atime, remote_stat.st_mtime))

    return True


def _safe_name(name: str) -> str:
    """Reject remote names that could escape the destination folder."""
    if name in ("", ".", "..") or "/" in name or "\\" in name or "\0" in name:
        raise ValueError(f"Refusing unsafe remote file name: {name!r}")
    return name


def sanitize_filename(name: str, replacement: str = "_") -> str:
    """
    Replace invalid Windows filename characters with a safe replacement.

    Invalid chars: < > : " / \\ | ? *
    These are invalid in Windows but valid on POSIX systems.
    On Linux, only control chars need replacement; we sanitize for Windows compatibility.
    """
    invalid_chars = '<>:"|?*'
    result = name
    for char in invalid_chars:
        result = result.replace(char, replacement)
    return result


def _ensure_remote_dir(sftp: paramiko.SFTPClient, path: str) -> None:
    try:
        sftp.mkdir(path)
    except OSError:
        if not stat.S_ISDIR(sftp.stat(path).st_mode or 0):
            raise


def upload_tree(
    sftp: paramiko.SFTPClient,
    source: str,
    destination: str,
    progress: Progress | None = None,
    skip_existing: bool = False,
) -> int:
    """Upload a local folder to ``destination``; return the file count."""
    _ensure_remote_dir(sftp, destination)
    count = 0
    for entry in os.scandir(source):
        target = posixpath.join(destination, entry.name)
        if entry.is_dir(follow_symlinks=True):
            count += upload_tree(sftp, entry.path, target, progress, skip_existing)
        else:
            if put_file(sftp, entry.path, target, progress, skip_existing):
                count += 1
    return count


def download_tree(
    sftp: paramiko.SFTPClient,
    source: str,
    destination: str,
    progress: Progress | None = None,
    skip_existing: bool = False,
    filter_invalid_chars: bool = True,
    char_replacement: str = "_",
    preserve_timestamps: bool = True,
) -> int:
    """Download a remote folder to ``destination``; return the file count.

    Args:
        sftp: SFTP client
        source: Remote path
        destination: Local path
        progress: Progress callback
        skip_existing: Skip files that exist locally
        filter_invalid_chars: Replace invalid Windows filename characters
        char_replacement: Character to replace invalid chars with
        preserve_timestamps: Preserve file modification times
    """
    os.makedirs(destination, exist_ok=True)
    count = 0
    for entry in sftp.listdir_attr(source):
        name = _safe_name(entry.filename)
        if filter_invalid_chars:
            name = sanitize_filename(name, char_replacement)
        remote = posixpath.join(source, entry.filename)
        target = os.path.join(destination, name)
        if stat.S_ISDIR(entry.st_mode or 0):
            count += download_tree(
                sftp, remote, target, progress, skip_existing,
                filter_invalid_chars, char_replacement, preserve_timestamps
            )
        else:
            if get_file(sftp, remote, target, progress, skip_existing, preserve_timestamps):
                count += 1
    return count


def delete_remote(sftp: paramiko.SFTPClient, path: str) -> None:
    """Delete a remote file or folder tree; symlinks are removed, not followed."""
    mode = sftp.lstat(path).st_mode or 0
    if not stat.S_ISDIR(mode):
        sftp.remove(path)
        return
    for entry in sftp.listdir_attr(path):
        delete_remote(sftp, posixpath.join(path, _safe_name(entry.filename)))
    sftp.rmdir(path)


def delete_local(path: str) -> None:
    """Delete a local file or folder tree; symlinks are removed, not followed."""
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.remove(path)
