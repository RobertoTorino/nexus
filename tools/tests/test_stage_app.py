# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/stage_app.py: what goes into an app's release tree, and what stays out."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import stage_app  # noqa: E402


def _suite(tmp_path: Path) -> Path:
    suite = tmp_path / "suite"
    app = suite / "apps" / "example"
    (app / "example_pkg").mkdir(parents=True)
    (app / "example_pkg" / "__main__.py").write_text("from bc250_core import AppInfo\n")
    (app / "VERSION").write_text("0.1.0\n")
    (app / "tests").mkdir()
    (app / "tests" / "test_x.py").write_text("")
    # A Rust crate with its build output, as Console Link has one.
    (app / "native" / "src").mkdir(parents=True)
    (app / "native" / "src" / "lib.rs").write_text("")
    (app / "native" / "target" / "release").mkdir(parents=True)
    (app / "native" / "target" / "release" / "big.so").write_bytes(b"\0" * 64)
    (tmp_path / "core" / "bc250_core").mkdir(parents=True)          # core: at the root, beside the suite
    (tmp_path / "core" / "bc250_core" / "__init__.py").write_text("")
    return suite


def test_stage_keeps_sources_and_drops_build_output(tmp_path):
    dest = stage_app.stage("example", tmp_path / "stage", _suite(tmp_path))
    assert (dest / "example_pkg" / "__main__.py").is_file() and (dest / "VERSION").is_file()
    assert (dest / "native" / "src" / "lib.rs").is_file()          # the source ships (AGPL: with the app)
    assert not (dest / "native" / "target").exists()                # cargo's build output does not
    assert not (dest / "tests").exists()
    assert (dest / "bc250_core" / "__init__.py").is_file()
