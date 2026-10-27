# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/check_versions.py: which version copies it finds, the Rust crate's own entry in Cargo.lock included, and
that a copy it cannot read is an error rather than skipped."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_versions  # noqa: E402


def test_cargo_lock_entry_of_the_crate_itself(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "my-core"\nversion = "0.2.0"\n')
    lock = tmp_path / "Cargo.lock"
    lock.write_text('version = 4\n\n[[package]]\nname = "aes"\nversion = "0.8.4"\n\n'
                    '[[package]]\nname = "my-core"\nversion = "0.1.0"\n')
    pattern = check_versions.version_pattern(lock)
    assert pattern.findall(lock.read_text()) == ["0.1.0"]            # not the lock format's 4, not aes's version
    assert check_versions.version_pattern(tmp_path / "Cargo.toml").findall('version = "0.2.0"') == ["0.2.0"]
    (tmp_path / "Cargo.toml").unlink()
    assert check_versions.version_pattern(lock) is None              # a lock file without its crate: nothing to check


def test_copies_with_a_comment_are_read_and_odd_ones_reported(tmp_path):
    py, sh = tmp_path / "x.py", tmp_path / "x.sh"
    text = '__version__ = "0.1.0"   # equal to VERSION\n'
    assert check_versions.version_pattern(py).findall(text) == ["0.1.0"]
    assert check_versions.version_pattern(sh).findall('VERSION="1.2.3"  # read by --version\n') == ["1.2.3"]
    assert check_versions.unreadable(py, text) == []
    assert check_versions.unreadable(py, "__version__ = '0.1.0'\n__version__  =  \"0.1.0\"\n") == [
        "__version__ = '0.1.0'", '__version__  =  "0.1.0"']
    assert check_versions.unreadable(sh, "VERSION='1.2.3'\nVERSION=1.2.3\n") == ["VERSION='1.2.3'", "VERSION=1.2.3"]
    # read at run time: no copies
    assert check_versions.unreadable(py, "__version__ = _read_version()\n") == []
    assert check_versions.unreadable(sh, "VERSION=$(tr -d '[:space:]' <\"$SRC/VERSION\")\n") == []


def test_the_suite_passes():
    assert check_versions.main() == 0


def test_one_suite_at_a_time(capsys):
    """Each suite's CI checks core, dev/ and its own folders: one suite never blocks another (owner, 27-10-2026)."""
    root = check_versions.ROOT
    folders = 1 + len([p for p in (root / "dev").glob("*") if p.is_dir()]) + 1 + len(
        [p for p in (root / "windows-portable" / "apps").iterdir() if p.is_dir()])   # core, dev/, its portal, its apps
    assert check_versions.main(["--suite", "windows-portable"]) == 0
    assert f"in {folders} folders" in capsys.readouterr().out
    assert check_versions.main(["--suite", "no-such-suite"]) == 1
    # Nexus's CI (ci-nexus.yml): core and dev/ alone, no suite's folders
    nexus = 1 + len([p for p in (root / "dev").glob("*") if p.is_dir()])
    assert check_versions.main(["--nexus"]) == 0
    assert f"in {nexus} folders" in capsys.readouterr().out
