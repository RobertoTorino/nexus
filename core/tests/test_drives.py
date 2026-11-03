# SPDX-License-Identifier: GPL-3.0-or-later
"""The removable drives and an app's own game folders (drives.py; owner, 03-11-2026)."""

from __future__ import annotations

import os
from pathlib import Path

from bc250_core import drives


def test_removable_drives_are_the_mount_points_under_the_media_folders(tmp_path, monkeypatch):
    """udisks mounts a drive at /run/media/<user>/<drive>, Bazzite's media-automount at /run/media/system/<drive>
    (media-automount links to it): each mount point once, a plain folder never, a missing root skipped."""
    run_media = tmp_path / "run" / "media"
    for name in ("admin/USB", "admin/notes", "system/SD"):
        (run_media / name).mkdir(parents=True)
    (run_media / "media-automount").symlink_to(run_media / "system")
    (tmp_path / "media" / "cdrom").mkdir(parents=True)
    mounted = {run_media / "admin" / "USB", run_media / "system" / "SD", tmp_path / "media" / "cdrom"}
    monkeypatch.setattr(os.path, "ismount", lambda p: Path(p) in mounted)
    found = drives.removable_drives((run_media, tmp_path / "media", tmp_path / "none"))
    assert found == [run_media / "admin" / "USB", run_media / "system" / "SD", tmp_path / "media" / "cdrom"]


def test_game_folders_are_made_and_found(tmp_path):
    games = Path("Games") / "PS2"
    (tmp_path / "sd" / games).mkdir(parents=True)
    (tmp_path / "stick").mkdir()
    found = drives.game_folders(tmp_path, games, lambda: [tmp_path / "sd", tmp_path / "stick", tmp_path / "gone"],
                                make=("BIOS",))
    assert found == [tmp_path / games, tmp_path / "sd" / games]
    assert (tmp_path / games / "BIOS").is_dir()
    assert drives.game_folders(tmp_path, games, lambda: []) == [tmp_path / games]
