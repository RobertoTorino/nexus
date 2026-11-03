# SPDX-License-Identifier: GPL-3.0-or-later
"""The Help page's paths (owner, 03-11-2026: the privacy rule, the user's folders as ~)."""

from __future__ import annotations

from upscaler.help import help_html


def test_the_help_page_shows_the_users_folders_as_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    html = help_html(str(tmp_path / "payload"), str(tmp_path / "deployments.json"), str(tmp_path / "work"))
    assert "<code>~/payload</code>" in html and "<code>~/deployments.json</code>" in html and "~/work" in html
    assert str(tmp_path) not in html
