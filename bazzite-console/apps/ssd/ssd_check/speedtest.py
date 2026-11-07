# SPDX-License-Identifier: GPL-3.0-or-later
"""The drive's read and write speed as measured in this board (owner, 05-11-2026): a test file of up to SIZE bytes
written to a folder on the drive and read back, both past the page cache (O_DIRECT, and the file's cached pages
dropped before the read), then deleted. Without root SSD Check cannot read the drive itself, so the file goes where
the user may write: the home folder when it is on the drive, else the first mount point of the drive that is
writable (a USB stick). Random data, so a file system that compresses cannot make it look faster.

A slow drive stops at LIMIT_S seconds of writing; the speed is what it wrote in that time."""

from __future__ import annotations

import mmap
import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path

SIZE = 1 << 30                  # 1 GiB
BLOCK = 8 << 20                 # written and read in blocks of 8 MiB
LIMIT_S = 10.0                  # the most it writes for
NAME = ".ps5-ssd-check-speed-test"


class SpeedError(RuntimeError):
    pass


def folder_for(mounts: list[str], home: Path | None = None) -> Path | None:
    """Where the test file goes on a drive mounted at *mounts*: ~/.cache/ps5-ssd-check when the home folder is on it,
    else the first writable mount point; None when there is none (the drive is not mounted)."""
    home = (home or Path.home()).resolve()
    points = sorted((Path(m) for m in mounts), key=lambda p: len(p.parts), reverse=True)
    if any(home == p or p in home.parents for p in points):
        return home / ".cache" / "ps5-ssd-check"
    return next((p for p in points if p != Path("/") and os.access(p, os.W_OK)), None)


def _open(path: Path, flags: int) -> tuple[int, bool]:
    """The file opened with O_DIRECT where the file system has it (tmpfs has not), else without."""
    direct = getattr(os, "O_DIRECT", 0)
    if direct:
        try:
            return os.open(path, flags | direct, 0o600), True
        except OSError:
            pass
    return os.open(path, flags, 0o600), False


def measure(folder: Path, size: int = SIZE, block: int = BLOCK, limit: float = LIMIT_S,
            clock: Callable[[], float] = time.monotonic) -> tuple[float, float]:
    """(read, write) in MB/s. SpeedError when the folder cannot take the file."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(folder).free
    except OSError as exc:
        raise SpeedError(f"The test folder cannot be used: {exc.strerror or exc}") from exc
    if free < 2 * size:
        raise SpeedError(f"Not enough free space on the drive: the test needs {2 * size / 1e9:.1f} GB")
    path = folder / NAME
    buffer = mmap.mmap(-1, block)               # page aligned, as O_DIRECT needs
    buffer.write(os.urandom(block))
    created = False
    try:
        fd, _direct = _open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        created = True
        written, start = 0, clock()
        try:
            while written < size and clock() - start < limit:
                written += os.write(fd, buffer)
            os.fsync(fd)
            write_s = clock() - start
        finally:
            os.close(fd)
        fd, _direct = _open(path, os.O_RDONLY)
        read, start = 0, clock()
        try:
            if hasattr(os, "posix_fadvise"):
                os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)     # what the write left in the cache
            while read < written:
                got = os.readv(fd, [buffer])
                if not got:
                    break
                read += got
            read_s = clock() - start
        finally:
            os.close(fd)
    except OSError as exc:
        raise SpeedError(f"The test could not write or read its file: {exc.strerror or exc}") from exc
    finally:
        buffer.close()
        if created:
            path.unlink(missing_ok=True)
    return read / 1e6 / max(read_s, 1e-6), written / 1e6 / max(write_s, 1e-6)
