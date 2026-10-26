# SPDX-License-Identifier: GPL-3.0-or-later
"""Integrity of the test engine (test-bazzite.sh), checked before every run.

The engine runs as root through sudo, so a copy that anyone but root can change would hand out root.
Before each run the engine file and every folder above it must be owned by root and writable by
nobody else, and the file must have the SHA-256 recorded when the package was built.

* Release build (`_build_info.SCRIPT_SHA256` set): a failed check blocks the run.
* Development (no recorded hash, e.g. the git checkout): the problems are shown in a banner, the run
  goes ahead.

With root-owned folders the file cannot be swapped between this check and its start, because only
root can write there.
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

try:
    from ._build_info import SCRIPT_SHA256       # written by development/tools/build_info.py when packaging
except ImportError:
    SCRIPT_SHA256 = None

MAX_ENGINE_BYTES = 4 * 1024 * 1024


@dataclass
class Verdict:
    path: Path
    release: bool
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def blocked(self) -> bool:
        return self.release and not self.ok


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _owner_problem(path: Path, st: os.stat_result, what: str) -> str | None:
    if st.st_uid != 0:
        return f"{what} {path} is owned by uid {st.st_uid}, not root."
    if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        return f"{what} {path} is writable by {'others' if st.st_mode & stat.S_IWOTH else 'its group'}."
    return None


def check_engine(script: str | Path, expected_sha256: str | None = None, release: bool | None = None) -> Verdict:
    expected = SCRIPT_SHA256 if expected_sha256 is None else expected_sha256
    path = Path(os.path.realpath(script))      # symlinks resolved: the real file is what runs
    v = Verdict(path, bool(expected) if release is None else release)
    try:
        st = path.stat()
    except OSError as exc:
        v.problems.append(f"Test engine {path} cannot be read: {exc.strerror}.")
        return v
    if not stat.S_ISREG(st.st_mode):
        v.problems.append(f"Test engine {path} is not a regular file.")
        return v
    if st.st_size > MAX_ENGINE_BYTES:
        v.problems.append(f"Test engine {path} is unexpectedly large ({st.st_size} bytes).")
        return v
    if p := _owner_problem(path, st, "Test engine"):
        v.problems.append(p)
    for folder in path.parents:
        try:
            if p := _owner_problem(folder, folder.stat(), "Folder"):
                v.problems.append(p)
        except OSError as exc:
            v.problems.append(f"Folder {folder} cannot be checked: {exc.strerror}.")
    if expected:
        try:
            actual = sha256_of(path)
        except OSError as exc:
            v.problems.append(f"Test engine {path} cannot be read: {exc.strerror}.")
        else:
            if actual != expected.lower():
                v.problems.append(f"Test engine {path} does not match this release (SHA-256 {actual[:16]}…, "
                                  f"expected {expected[:16]}…): it was changed or replaced.")
    elif v.release:
        v.problems.append("No checksum of the test engine was recorded for this release.")
    return v
