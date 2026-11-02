# SPDX-License-Identifier: GPL-3.0-or-later
"""tour_frames.platform_path: the screen file in QT_QPA_PLATFORM's options, which Qt splits at every ':'. A Windows
path with its drive letter left the offscreen platform only "C" of it, and every tour stopped (exit code 127)."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("tour_frames", ROOT / "tools" / "tour_frames.py")
tour_frames = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tour_frames)


def test_a_path_without_a_drive_stays(tmp_path):
    path = Path("/tmp/portal-tour-x/screen.json")
    if os.path.splitdrive(str(path))[0]:
        pytest.skip("every absolute path has a drive here")
    assert tour_frames.platform_path(path) == str(path)


@pytest.mark.skipif(os.name != "nt", reason="drive letters are Windows'")
def test_the_drive_is_left_out_on_the_working_folders_drive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "screen.json"
    result = tour_frames.platform_path(path)
    assert ":" not in result
    assert Path(os.path.splitdrive(os.getcwd())[0] + result) == path


@pytest.mark.skipif(os.name != "nt", reason="drive letters are Windows'")
def test_on_another_drive_the_working_folder_moves_to_the_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    drive = os.path.splitdrive(str(tmp_path))[0]
    other = Path(("D:" if drive.upper() != "D:" else "E:") + r"\portal-tour-x\screen.json")
    moved = []
    monkeypatch.setattr(tour_frames.os, "chdir", moved.append)
    assert tour_frames.platform_path(other) == "screen.json"
    assert moved == [other.parent]
