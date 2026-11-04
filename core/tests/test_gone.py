# SPDX-License-Identifier: GPL-3.0-or-later
"""The screen for a game that is no longer there: the BC250 suite's desktop wording (gone.py; owner, 03-11-2026)."""

from __future__ import annotations

from pathlib import Path

from bc250_core import gone, platform


def test_the_desktop_message_names_the_file_and_what_to_do(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    game = tmp_path / "Games" / "PS2" / "Two.iso"
    text = gone.desktop_message("PCSX2 Manager", game)
    # The user's folders masked as platform.private() does: ~ on Linux; on Windows the temp folder lies under
    # %LOCALAPPDATA%, which the suite's CI on windows-latest runs core's tests with too (04-11-2026).
    masked = platform.private(game) if platform.WINDOWS else "~/Games/PS2/Two.iso"
    assert text.startswith(f"{masked}\n\n") and str(tmp_path) not in text
    assert "Open PCSX2 Manager: Refresh finds the game again" in text and "Update Steam" in text
