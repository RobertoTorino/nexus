# SPDX-License-Identifier: GPL-3.0-or-later
"""The wiki's Portal Tour keeps up with the portal (owner, 14-11-2026): tools/portal_tour.py --wiki writes a
fingerprint of what the video shows, and this fails when the portal changed since."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import portal_tour  # noqa: E402


def test_the_wikis_portal_tour_was_recorded_from_this_portal():
    assert not portal_tour.stale(), (
        "The portal changed since the wiki's Portal Tour was recorded. Record it again with "
        "bc250-bazzite/tools/record-tour.sh --wiki, or, when the change does not show in the video, run "
        "python3 bc250-bazzite/tools/portal_tour.py --stamp. When the change is one the wiki describes, its Portal page "
        "(bc250-bazzite/docs/portal.md) changes with it.")


def test_the_fingerprint_follows_the_portal_but_not_its_version(tmp_path, monkeypatch):
    package = tmp_path / "portal" / "package"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "1.0.0"\nNAME = "Portal"\n', encoding="utf-8")
    monkeypatch.setattr(portal_tour, "SUITE", tmp_path)
    monkeypatch.setattr(portal_tour, "SHOWN", (package,))
    monkeypatch.setattr(portal_tour, "STAMP", tmp_path / "portal-tour.stamp")
    monkeypatch.setattr(portal_tour, "__file__", str(package / "__init__.py"))
    assert portal_tour.stale()                              # no stamp yet
    portal_tour.write_stamp()
    assert not portal_tour.stale()
    (package / "__init__.py").write_text('__version__ = "1.1.0"\nNAME = "Portal"\n', encoding="utf-8")
    assert not portal_tour.stale()                          # a release: only the version
    (package / "__init__.py").write_text('__version__ = "1.1.0"\nNAME = "The Portal"\n', encoding="utf-8")
    assert portal_tour.stale()
