# SPDX-License-Identifier: GPL-3.0-or-later
"""Every installable part of the suite has an installer test, and CI runs every installer test. Nexus Installer
Tests finds the scripts by itself (tools/installer-tests/*.sh), so a new script appears there without a change."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

SUITE = Path(__file__).resolve().parents[2]
TESTS = SUITE / "tools" / "installer-tests"
HELPERS = {"shims.sh"}
NOT_INSTALLERS = {"release.sh"}         # the release tarballs end to end, not one app's installer


def _scripts() -> set[str]:
    return {path.name for path in TESTS.glob("*.sh")} - HELPERS


def test_every_app_has_an_installer_test():
    apps = {path.name for path in (SUITE / "apps").iterdir() if (path / "VERSION").is_file()}
    missing = sorted(app for app in apps | {"portal"} if not (TESTS / f"{app}.sh").is_file())
    assert not missing, f"no tools/installer-tests/<name>.sh for: {', '.join(missing)}"


def _from_the_checkout() -> set[str]:
    """The tools that run from the checkout, outside the portal: the Nexus apps in dev/ (Nexus Dashboard, Nexus
    Release Tool, Nexus Demo Recorder, Nexus Installer Tests, Nexus Sound Lab), each with an install.sh."""
    return {path.parent.name for path in (SUITE.parent / "dev").glob("*/install.sh")}


def test_every_portal_entry_and_checkout_tool_has_an_installer_test():
    manifest = tomllib.loads((SUITE / "portal" / "apps.toml").read_text(encoding="utf-8"))
    names = set(manifest.get("apps", {})) | _from_the_checkout()
    missing = sorted(name for name in names if not (TESTS / f"{name}.sh").is_file())
    assert not missing, f"no tools/installer-tests/<name>.sh for: {', '.join(missing)}"
    assert {"dash", "demo", "itests", "nrt", "sounds"} <= _from_the_checkout()


def test_every_installer_test_is_for_something_that_exists():
    known = {path.name for path in (SUITE / "apps").iterdir()} | {"portal"} | _from_the_checkout()
    stale = sorted(name for name in _scripts() - NOT_INSTALLERS if name.removesuffix(".sh") not in known)
    assert not stale, f"installer tests for nothing in the suite: {', '.join(stale)}"


def test_ci_runs_every_installer_test():
    """CI's installers job runs every tools/installer-tests/*.sh it finds (stage 2, 04-11-2026: a new app's test
    runs without an edit to the workflow), the helper left out and the release tarballs last."""
    ci = (SUITE.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    step = re.search(r"for t in bc250-bazzite/tools/installer-tests/\*\.sh; do\n(.*?)done\n(.*?)\n", ci, re.S)
    assert step, "no loop over bc250-bazzite/tools/installer-tests/*.sh"
    assert "shims.sh|release.sh) continue" in step.group(1) and 'run "$t"' in step.group(1)
    assert step.group(2).strip() == "run bc250-bazzite/tools/installer-tests/release.sh"
    assert not re.findall(r"bash bc250-bazzite/tools/installer-tests/[\w.-]+\.sh", ci)     # no step by name
