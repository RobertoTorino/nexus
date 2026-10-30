# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/nexus_release.py and release-nexus.yml: a Nexus release carries each suite on it whose portal version is not
out yet, and only those; each such suite has its job in release-nexus.yml, which calls the suite's own workflow."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("nexus_release", ROOT / "tools" / "nexus_release.py")
nr = importlib.util.module_from_spec(spec)
sys.modules["nexus_release"] = nr
spec.loader.exec_module(nr)
WORKFLOWS = ROOT / ".github" / "workflows"


def suite(root: Path, name: str, prefix: str, portal: str, called: bool) -> None:
    folder = root / name
    (folder / "portal").mkdir(parents=True)
    (folder / "portal" / "apps.toml").write_text("", encoding="utf-8")
    (folder / "portal" / "VERSION").write_text(f"{portal}\n", encoding="utf-8")
    if prefix:
        (folder / "TAG_PREFIX").write_text(prefix, encoding="utf-8")
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    trigger = "on:\n  push:\n" + ("  workflow_call:\n" if called else "")
    (workflows / f"release-{name}.yml").write_text(trigger, encoding="utf-8")


def test_only_the_suites_on_the_nexus_release_with_a_portal_not_out_yet(tmp_path):
    suite(tmp_path, "aa-suite", "aa-", "2.0.0", called=True)        # changed: its portal 2.0.0 is not out
    suite(tmp_path, "bb-suite", "bb-", "1.0.0", called=True)        # unchanged: its portal is out
    suite(tmp_path, "cc-suite", "cc-", "5.0.0", called=False)       # not on the Nexus release yet
    out = {"aa-portal-v1.0.0", "bb-portal-v1.0.0"}
    assert nr.carried(tmp_path, released=out.__contains__) == ["aa-suite"]
    assert nr.carried(tmp_path, released=lambda tag: True) == []


def test_a_suite_without_a_prefix_has_plain_portal_tags(tmp_path):
    suite(tmp_path, "plain", "", "1.2.3", called=True)
    assert nr.portal_tag(tmp_path / "plain") == "portal-v1.2.3"


def test_every_suite_on_the_nexus_release_has_its_job():
    nexus = (WORKFLOWS / "release-nexus.yml").read_text(encoding="utf-8")
    on = [folder for folder in nr.nexus_suites.suites(ROOT) if nr.on_nexus_release(ROOT, folder)]
    assert [folder.name for folder in on] == ["windows-portable"]  # bc250-bazzite joins in stage 3
    for folder in on:
        job = re.search(rf"^  {re.escape(folder.name)}:\n(.*?)(?=^  \S|\Z)", nexus, re.M | re.S)
        assert job, f"release-nexus.yml has no job {folder.name}"
        assert f"contains(fromJSON(needs.plan.outputs.suites), '{folder.name}')" in job[1]
        assert f"uses: ./.github/workflows/release-{folder.name}.yml" in job[1]
        assert "commit: ${{ inputs.commit }}" in job[1]


def test_a_release_without_a_suite_makes_the_index_and_the_index_follows_each_published_portal():
    nexus = (WORKFLOWS / "release-nexus.yml").read_text(encoding="utf-8")
    assert "if: needs.plan.outputs.suites == '[]'" in nexus and "uses: ./.github/workflows/nexus-index.yml" in nexus
    index = (WORKFLOWS / "nexus-index.yml").read_text(encoding="utf-8")
    assert "  workflow_call:" in index and "types: [published]" in index
    assert "paths: [VERSION]" not in index                          # the release commit bumps it: no index before


def test_the_release_starts_only_on_mains_newest_commit_after_nexus_ci():
    nexus = (WORKFLOWS / "release-nexus.yml").read_text(encoding="utf-8")
    assert "git rev-parse origin/main" in nexus and "ci_state.py --workflow ci-nexus.yml" in nexus
    assert "cancel-in-progress: false" in nexus
