# SPDX-License-Identifier: GPL-3.0-or-later
"""The drive's read and write speed as measured in this handheld (owner, 05-11-2026, the BC250 Bazzite Suite's SSD
Check's test on Windows): a test file of up to SIZE bytes written to the drive and read back, both past Windows'
cache (FILE_FLAG_NO_BUFFERING, and FILE_FLAG_WRITE_THROUGH for the write), then deleted. The file goes in the app's
own folder (%LOCALAPPDATA%\\windows-portable-suite\\windows-portable-ssd) when that is on the drive, else at the root
of the drive's first drive letter (an SD card, a USB stick), hidden. Random data, so a drive that compresses cannot
make it look faster.

A slow drive stops at LIMIT_S seconds of writing; the speed is what it wrote in that time."""

from __future__ import annotations

import ctypes
import mmap
import os
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path

SIZE = 1 << 30                  # 1 GiB
BLOCK = 8 << 20                 # written and read in blocks of 8 MiB (a multiple of every sector size)
LIMIT_S = 10.0                  # the most it writes for
NAME = ".windows-portable-ssd-speed-test"

GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
CREATE_ALWAYS, OPEN_EXISTING = 2, 3
FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_FLAG_NO_BUFFERING, FILE_FLAG_WRITE_THROUGH, FILE_FLAG_SEQUENTIAL_SCAN = 0x20000000, 0x80000000, 0x08000000


class SpeedError(RuntimeError):
    pass


def folder_for(letters: list[str], own: Path) -> Path | None:
    """Where the test file goes on a drive with the drive letters *letters*: *own* (the app's folder) when it is on
    the drive, else the root of its first drive letter; None when the drive has none."""
    drive = own.drive[:1].upper()
    upper = [letter[:1].upper() for letter in letters if letter]
    if drive and drive in upper:
        return own
    return Path(f"{upper[0]}:\\") if upper else None


class _File:
    """A file opened past Windows' cache, through kernel32 (Python's open() cannot ask for that)."""

    def __init__(self, path: Path, write: bool):
        from ctypes import wintypes
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k = self.kernel32
        k.CreateFileW.restype = wintypes.HANDLE
        k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                  wintypes.DWORD, wintypes.HANDLE]
        k.WriteFile.argtypes = k.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                                      ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        k.FlushFileBuffers.argtypes = k.CloseHandle.argtypes = [wintypes.HANDLE]
        flags = FILE_FLAG_NO_BUFFERING | (FILE_FLAG_WRITE_THROUGH | FILE_ATTRIBUTE_HIDDEN if write
                                          else FILE_FLAG_SEQUENTIAL_SCAN)
        self.handle = k.CreateFileW(str(path), GENERIC_WRITE if write else GENERIC_READ, 0, None,
                                    CREATE_ALWAYS if write else OPEN_EXISTING, flags, None)
        if self.handle in (None, wintypes.HANDLE(-1).value):
            raise OSError(ctypes.get_last_error(), ctypes.FormatError(ctypes.get_last_error()).strip())
        self.done = wintypes.DWORD()

    def _check(self, ok: int) -> int:
        if not ok:
            error = ctypes.get_last_error()
            raise OSError(error, ctypes.FormatError(error).strip())
        return self.done.value

    def write(self, address: int, length: int) -> int:
        return self._check(self.kernel32.WriteFile(self.handle, address, length, ctypes.byref(self.done), None))

    def read(self, address: int, length: int) -> int:
        return self._check(self.kernel32.ReadFile(self.handle, address, length, ctypes.byref(self.done), None))

    def flush(self) -> None:
        self._check(self.kernel32.FlushFileBuffers(self.handle))

    def close(self) -> None:
        self.kernel32.CloseHandle(self.handle)


def measure(folder: Path, size: int = SIZE, block: int = BLOCK, limit: float = LIMIT_S,
            clock: Callable[[], float] = time.monotonic) -> tuple[float, float]:
    """(read, write) in MB/s. SpeedError when the folder cannot take the file."""
    if sys.platform != "win32":
        raise SpeedError("The speed test runs on Windows")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(folder).free
    except OSError as exc:
        raise SpeedError(f"The test folder cannot be used: {exc.strerror or exc}") from exc
    if free < 2 * size:
        raise SpeedError(f"Not enough free space on the drive: the test needs {2 * size / 1e9:.1f} GB")
    path = folder / NAME
    buffer = mmap.mmap(-1, block)               # page aligned, as an unbuffered file needs
    buffer.write(os.urandom(block))
    view = ctypes.c_char.from_buffer(buffer)    # kernel32 reads and writes the buffer at its address
    address = ctypes.addressof(view)
    try:
        file = _File(path, write=True)
        written, start = 0, clock()
        try:
            while written < size and clock() - start < limit:
                written += file.write(address, block)
            file.flush()
            write_s = clock() - start
        finally:
            file.close()
        file = _File(path, write=False)
        read, start = 0, clock()
        try:
            while read < written:
                got = file.read(address, block)
                if not got:
                    break
                read += got
            read_s = clock() - start
        finally:
            file.close()
    except OSError as exc:
        raise SpeedError(f"The test could not write or read its file: {exc.strerror or exc}") from exc
    finally:
        del view                                # the buffer closes only without a view on it
        buffer.close()
        path.unlink(missing_ok=True)
    return read / 1e6 / max(read_s, 1e-6), written / 1e6 / max(write_s, 1e-6)
