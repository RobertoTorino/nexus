# SPDX-License-Identifier: GPL-3.0-or-later
"""The suite's stage (STAGE in portal/bc250_portal/__init__.py) is said the same way wherever it shows: the portal's
header, a portal release's notes, the suite README's badge and notice, and the wiki's home page. Clearing STAGE fails
this test until the README and the wiki drop it too."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_release  # noqa: E402

SUITE = Path(__file__).resolve().parent.parent.parent


def test_readme_and_wiki_follow_the_portal_stage():
    stage, note = build_release.portal_stage()
    readme = (SUITE / "bc250-bazzite" / "README.md").read_text(encoding="utf-8")
    home = (SUITE / "bc250-bazzite" / "docs" / "index.md").read_text(encoding="utf-8")
    if stage:
        assert note
        assert f"https://img.shields.io/badge/status-{stage}-" in readme
        assert f"**{stage}:** {note}" in readme
        assert f'<p class="home-hero__stage"><strong>{stage}</strong> {note}</p>' in home
    else:
        assert "img.shields.io/badge/status-" not in readme
        assert "home-hero__stage" not in home
