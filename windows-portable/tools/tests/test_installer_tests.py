# SPDX-License-Identifier: GPL-3.0-or-later
"""Every app of the Windows Portable Suite, its portal, and every Nexus app with a Windows installer
(dev/<name>/install.ps1: Nexus Release Tool), has an installer test (tools/installer-tests/<name>.ps1), and the suite's
CI (ci-windows-portable.yml) runs each one; it also builds each app's release and the portal's and runs its test on
that release."""

from __future__ import annotations

import tomllib
from pathlib import Path

SUITE = Path(__file__).resolve().parents[2]
REPO = SUITE.parent
TESTS = SUITE / "tools" / "installer-tests"
CI = REPO / ".github" / "workflows" / "ci-windows-portable.yml"


def _apps() -> set[str]:
    """The apps and the portal: each is released by build_release.py and installed by its install.ps1."""
    return {path.name for path in (SUITE / "apps").iterdir() if (path / "VERSION").is_file()} | {"portal"}


def _nexus_apps() -> set[str]:
    """The Nexus apps that install on Windows too."""
    return {path.parent.name for path in (REPO / "dev").glob("*/install.ps1")}


def test_every_app_and_portal_entry_has_an_installer_test():
    manifest = tomllib.loads((SUITE / "portal" / "apps.toml").read_text(encoding="utf-8"))
    names = _apps() | set(manifest["apps"]) | _nexus_apps()
    missing = sorted(name for name in names if not (TESTS / f"{name}.ps1").is_file())
    assert not missing, f"no tools/installer-tests/<name>.ps1 for: {', '.join(missing)}"


def test_every_installer_test_is_for_something_that_exists():
    stale = sorted(path.name for path in TESTS.glob("*.ps1") if path.stem not in _apps() | _nexus_apps())
    assert not stale, f"installer tests for nothing in the suite: {', '.join(stale)}"


def test_nexus_release_tool_installs_on_windows():
    assert "nrt" in _nexus_apps()


def test_ci_runs_each_installer_test_and_each_release_in_a_job_of_its_own():
    """The installers job is a matrix, one job per app and the portal (29-10-2026: one job doing them all in a row
    took six to fifteen minutes): each runs the installer test, builds the release (never published, owner
    28-10-2026) and installs it; the Nexus Release Tool's Windows installer has a job of its own."""
    import re
    ci = CI.read_text(encoding="utf-8")
    matrix = re.search(r"app: \[([^\]]*)\]", ci).group(1)
    assert {entry.strip() for entry in matrix.split(",")} == _apps()
    assert matrix.strip().endswith("portal")                   # the portal last: new_app.py puts an app before it
    for step in ("- name: Installer test\n", "- name: Build the release zip, not published\n",
                 "- name: Installer test on the release\n"):
        assert step in ci, step
    assert "windows-portable/tools/installer-tests/${{ matrix.app }}.ps1" in ci
    for name in sorted(_nexus_apps()):
        assert f'- name: "Installer test: {name}"' in ci, name
        assert f"windows-portable/tools/installer-tests/{name}.ps1" in ci, name


def test_the_installer_tests_never_touch_the_users_own_folders():
    for path in TESTS.glob("*.ps1"):
        text = path.read_text(encoding="utf-8")
        for variable in ("$env:LOCALAPPDATA = ", "$env:APPDATA = ", "$env:WPS_DESKTOP_DIR = ", "$env:WPS_ELEVATED = '0'"):
            assert variable in text, f"{path.name} does not set {variable.split(' =')[0]}"
        assert text.index("$env:WPS_DESKTOP_DIR = ") < text.index("Run 'log1'"), path.name
