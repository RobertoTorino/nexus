# SPDX-License-Identifier: GPL-3.0-or-later
"""plan.py (and the window on top of it) in a small git repo of its own."""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from nexus_releases import plan as rp
from nexus_releases.command_line import command_lines

SHA = "cd" * 32
SUITE_DIR = "bc250-bazzite"                 # the first suite's folder, as Nexus lays the checkout out


def card(key: str, required: bool = False) -> str:
    return (f'[apps.{key}]\nname = "{key}"\nsummary = "s"\ntag = "{key}-v0.1.0"\nsha256 = ""\n'
            f'required = {"true" if required else "false"}\nchanges_board = false\ninstall = ["bash install.sh"]\n'
            f'uninstall = ["bash install.sh --uninstall"]\ndetect = ["~/.local/bin/{key}"]\n\n')


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())


def sh(root: Path, *args: str) -> None:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=env)


@pytest.fixture
def repo(tmp_path) -> Path:
    root = tmp_path / "suite"
    write(root / "core/VERSION", "0.1.0\n")
    write(root / "core/bc250_core/__init__.py", '__version__ = "0.1.0"\n')
    write(root / "core/pyproject.toml", '[project]\nname = "c"\nversion = "0.1.0"\n')
    write(root / "core/CHANGELOG", "Changelog: 01-01-2026 00:00:00\n\nCore.\n")
    write(root / "portal/VERSION", "0.1.0\n")
    write(root / "portal/bc250_portal/__init__.py", '__version__ = "0.1.0"\n')
    write(root / "portal/CHANGELOG", "Changelog: 01-01-2026 00:00:00\n\nPortal.\n")
    write(root / "portal/apps.toml", "# the pins\n\n" + card("alpha", required=True) + card("beta"))
    for key in ("alpha", "beta"):
        write(root / f"apps/{key}/VERSION", "0.1.0\n")
        write(root / f"apps/{key}/{key}/__init__.py", f'APP = "{key}"\n__version__ = "0.1.0"\n')
        write(root / f"apps/{key}/run.sh", 'VERSION="0.1.0"\necho "$VERSION"\n')
        write(root / f"apps/{key}/tests/test_x.py", '__version__ = "0.1.0"\n')
        write(root / f"apps/{key}/CHANGELOG", "Changelog: 01-01-2026 00:00:00\n\nFirst.\n")
    write(root / "apps/standalone/VERSION", "0.1.0\n")
    write(root / "apps/standalone/.standalone", "Standalone app; do not add to portal/apps.toml.\n")
    write(root / "apps/releases/VERSION", "0.1.0\n")                  # like this app: never released
    write(root / "apps/releases/.standalone", "Not in the portal.\n")
    write(root / "apps/releases/.checkout-only", "No releases.\n")
    write(root / "apps/alpha/alpha/ui.py", "from bc250_core import widgets\n")      # alpha bundles core, beta not
    # A Rust crate, as Console Link has: Cargo.lock repeats the crate's version, next to another crate's.
    write(root / "apps/alpha/native/Cargo.toml", '[package]\nname = "alpha-core"\nversion = "0.1.0"\n')
    write(root / "apps/alpha/native/Cargo.lock", 'version = 4\n\n[[package]]\nname = "aes"\nversion = "0.1.0"\n\n'
                                                '[[package]]\nname = "alpha-core"\nversion = "0.1.0"\n')
    write(root / "docs/apps/alpha.md", "# Alpha\n")
    sh(root, "init", "-q", "-b", "main")
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", "start")
    sh(root, "tag", "alpha-v0.1.0")
    sh(root, "tag", "standalone-v0.1.0")
    sh(root, "branch", "pushed")                # stands in for origin/main
    write(root / "apps/alpha/alpha/extra.py", "x = 1\n")
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", "work")
    return root


def unit(root: Path, key: str) -> rp.Unit:
    return next(u for u in rp.load_units(root) if u.key == key)


@pytest.fixture
def two_suites(tmp_path) -> Path:
    """Nexus with a suite of plain tags (bc) and the Windows Portable Suite's kind (wp: wp- tags, its own manifest
    and check_manifest.py, copied from the checkout)."""
    root = tmp_path / "nexus"
    write(root / "core/VERSION", "0.1.0\n")
    write(root / "core/bc250_core/__init__.py", '__version__ = "0.1.0"\n')
    write(root / "bc/portal/VERSION", "3.0.0\n")
    write(root / "bc/portal/apps.toml", card("check", required=True))
    write(root / "bc/apps/check/VERSION", "0.1.0\n")
    wp = root / "wp"
    write(wp / "SYSTEM", "windows\n")
    write(wp / "TAG_PREFIX", "wp-\n")
    write(wp / "portal/VERSION", "0.1.0\n")
    write(wp / "apps/test/VERSION", "0.2.0\n")
    write(wp / "apps/test/CHANGELOG", "Changelog: 01-01-2026 00:00:00\n\nAdded. More.\n")
    real = rp.CHECKOUT / "windows-portable"
    for path in ("tools/check_manifest.py", "portal/portable_portal/manifest.py"):
        write(wp / path, (real / path).read_text(encoding="utf-8"))
    write(wp / "portal/apps.toml", '[apps.test]\nname = "T"\nsummary = "s"\ntag = "wp-test-v0.1.0"\nsha256 = ""\n'
                                   'required = true\ncategory = "sustainable"\ninstall = ["i"]\nuninstall = ["u"]\n'
                                   'detect = ["d"]\n')
    sh(root, "init", "-q", "-b", "main")
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", "start")
    for tag in ("wp-test-v0.1.0", "test-v9.9.9", "portal-v3.0.0", "check-v0.1.0"):
        sh(root, "tag", tag)
    return root


def test_a_suites_tags_carry_its_prefix(two_suites):
    assert rp.suites(two_suites) == ["bc", "wp"]
    assert (rp.tag_prefix(two_suites, "bc"), rp.tag_prefix(two_suites, "wp")) == ("", "wp-")
    units = {u.key: u for u in rp.load_units(two_suites, "wp")}
    test, portal = units["test"], units["portal"]
    assert test.last_tag == "wp-test-v0.1.0"                    # not test-v9.9.9, whatever suite that would be
    assert (test.tag, test.pinned_tag) == ("wp-test-v0.2.0", "wp-test-v0.1.0")   # read with the suite's own parser
    assert rp.version_choices(two_suites, test)[0][0] == "0.2.0"
    assert portal.last_tag is None and portal.tag == "wp-portal-v0.1.0"     # the BC250 portal's tag is not its own
    assert units["core"].prefix == ""
    bc = {u.key: u for u in rp.load_units(two_suites, "bc")}
    assert (bc["portal"].last_tag, bc["check"].tag) == ("portal-v3.0.0", "check-v0.1.0")
    assert rp.manifest_tools(two_suites, "bc") is rp.check_manifest
    assert rp.manifest_tools(two_suites, "wp").PORTAL_TAG == "wp-portal-v"


def test_a_windows_suites_pin_and_portal_bump(two_suites):
    test = next(u for u in rp.load_units(two_suites, "wp") if u.key == "test")
    assert rp.follow_unreleased_pin(two_suites, test, suite="wp") is False     # wp-test-v0.1.0 is tagged
    rp.pin(two_suites, test, "AB" * 32, suite="wp")
    assert 'tag = "wp-test-v0.2.0"\nsha256 = "' + "ab" * 32 + '"' in (two_suites / "wp/portal/apps.toml").read_text()
    assert rp.changed_pins(two_suites, "HEAD", suite="wp") == ["wp-test-v0.2.0"]
    assert rp.portal_minimum(two_suites, "HEAD", "0.1.0", suite="wp")[0] == "0.2.0"     # an app minor: a portal minor


def test_a_windows_suites_release_is_a_zip(two_suites):
    assert rp.release_asset("wp-test-v0.2.0", two_suites) == "wp-test-v0.2.0.zip"
    assert rp.release_asset("check-v0.1.0", two_suites) == "check-v0.1.0.tar.gz"


def test_units(repo):
    units = {u.key: u for u in rp.load_units(repo)}
    assert list(units) == ["core", "portal", "alpha", "beta", "standalone"]   # not the checkout-only app
    alpha = units["alpha"]
    assert (alpha.version, alpha.last_tag, alpha.commits, alpha.released) == ("0.1.0", "alpha-v0.1.0", 1, True)
    assert alpha.pinned_tag == "alpha-v0.1.0" and alpha.pinned_sha == ""
    assert units["beta"].last_tag is None and not units["beta"].released
    assert units["standalone"].standalone and units["standalone"].released
    assert units["core"].kind == "core" and units["core"].last_tag is None


def test_versions():
    assert rp.next_versions("1.2.3") == {"patch": "1.2.4", "minor": "1.3.0", "major": "2.0.0"}
    assert rp.check_new_version("0.1.0", "0.1.0", released=False) == ""        # a first release as it is
    assert "already tagged" in rp.check_new_version("0.1.0", "0.1.0", released=True)
    assert "not higher" in rp.check_new_version("0.2.0", "0.1.9", released=False)
    assert "not x.y.z" in rp.check_new_version("0.1.0", "0.2", released=False)


def test_set_version_changes_a_copy_with_a_comment(repo):
    init = repo / "apps/alpha/alpha/__init__.py"
    init.write_text('APP = "alpha"\n__version__ = "0.1.0"   # equal to VERSION\n')
    rp.set_version(repo, unit(repo, "alpha"), "0.2.0")
    assert init.read_text() == 'APP = "alpha"\n__version__ = "0.2.0"   # equal to VERSION\n'      # comment kept


def test_set_version_changes_every_copy_but_tests(repo):
    alpha = unit(repo, "alpha")
    changed = rp.set_version(repo, alpha, "0.2.0")
    assert {p.relative_to(repo).as_posix() for p in changed} == {
        "apps/alpha/VERSION", "apps/alpha/alpha/__init__.py", "apps/alpha/run.sh", "apps/alpha/native/Cargo.toml",
        "apps/alpha/native/Cargo.lock"}
    lock = (repo / "apps/alpha/native/Cargo.lock").read_text()
    assert 'name = "alpha-core"\nversion = "0.2.0"' in lock and 'name = "aes"\nversion = "0.1.0"' in lock
    assert (repo / "apps/alpha/VERSION").read_text() == "0.2.0\n"
    assert (repo / "apps/alpha/alpha/__init__.py").read_text() == 'APP = "alpha"\n__version__ = "0.2.0"\n'
    assert (repo / "apps/alpha/run.sh").read_text().startswith('VERSION="0.2.0"\n')
    assert '"0.1.0"' in (repo / "apps/alpha/tests/test_x.py").read_text()
    core = unit(repo, "core")
    rp.set_version(repo, core, "0.2.0")
    assert 'version = "0.2.0"' in (repo / "core/pyproject.toml").read_text()


@pytest.mark.parametrize("utc, local", [
    ((2026, 10, 10, 18, 0), "10-10-2026 20:00:00"),          # CEST
    ((2026, 10, 25, 0, 59), "25-10-2026 02:59:00"),          # the last minute of CEST
    ((2026, 10, 25, 1, 0), "25-10-2026 02:00:00"),           # CET
    ((2026, 3, 29, 1, 0), "29-03-2026 03:00:00"),            # CEST again
    ((2026, 1, 5, 12, 0), "05-01-2026 13:00:00"),
])
def test_amsterdam_time(utc, local):
    now = datetime.datetime(*utc, tzinfo=datetime.timezone.utc)
    assert rp.amsterdam_now(now).strftime("%d-%m-%Y %H:%M:%S") == local


def test_changelog_entry(repo):
    now = datetime.datetime(2026, 10, 10, 18, 0, tzinfo=datetime.timezone.utc)
    rp.add_changelog_entry(repo, unit(repo, "beta"), rp.release_text("0.1.0", "  The first one. "), now)
    assert (repo / "apps/beta/CHANGELOG").read_text() == (
        "Changelog: 10-10-2026 20:00:00\n\nRelease 0.1.0. The first one.\n\n"
        "Changelog: 01-01-2026 00:00:00\n\nFirst.\n")
    assert rp.portal_text("0.2.0", ["alpha-v0.2.0"], "") == "Release 0.2.0. Pins alpha-v0.2.0."


def test_unreleased_pin_follows_the_version(repo):
    beta = unit(repo, "beta")                                 # pinned beta-v0.1.0, never tagged
    rp.set_version(repo, beta, "0.2.0")
    assert rp.follow_unreleased_pin(repo, beta)
    assert 'tag = "beta-v0.2.0"' in (repo / "portal/apps.toml").read_text()
    alpha = unit(repo, "alpha")                               # its pinned tag exists: the pin stays
    rp.set_version(repo, alpha, "0.2.0")
    assert not rp.follow_unreleased_pin(repo, alpha)
    assert 'tag = "alpha-v0.1.0"' in (repo / "portal/apps.toml").read_text()
    assert rp.portal_minimum(repo, "pushed", "0.1.0") == ("0.2.0", "beta 0.1.0 -> 0.2.0")


def test_pin_and_portal(repo):
    assert [u.key for u in rp.pin_candidates(rp.load_units(repo))] == ["alpha"]     # tagged, no sha256 yet
    assert rp.portal_minimum(repo, "pushed", "0.1.0") == ("", "")
    alpha = unit(repo, "alpha")
    rp.set_version(repo, alpha, "0.1.1")
    sh(repo, "tag", "alpha-v0.1.1")
    alpha = unit(repo, "alpha")
    assert rp.pin_candidates(rp.load_units(repo)) and alpha.released
    rp.pin(repo, alpha, SHA.upper())
    text = (repo / "portal/apps.toml").read_text()
    assert f'tag = "alpha-v0.1.1"\nsha256 = "{SHA}"' in text and text.startswith("# the pins\n")
    assert rp.pin_candidates(rp.load_units(repo)) == []
    assert rp.changed_pins(repo, "pushed") == ["alpha-v0.1.1"]
    assert rp.portal_minimum(repo, "pushed", "0.1.0") == ("0.1.1", "apps.toml changed")
    assert rp.portal_minimum(repo, "pushed", "0.2.0")[0] == "0.2.0"     # already bumped far enough


def test_commands():
    text = rp.app_commands(["alpha-v0.2.0", "beta-v0.1.0"])
    assert "tools/tag-release.sh alpha-v0.2.0 beta-v0.1.0" in text and "git push\n" in text
    assert text.index("git commit") < text.index("git push\n") < text.index("tag-release.sh")
    assert "\ntools/ci-local.sh && git push\n" in rp.app_commands(["alpha-v0.2.0"], linux=True)  # CI's jobs first
    text = rp.portal_commands("portal-v0.2.0")
    assert "\ntools/tag-release.sh portal-v0.2.0\n" in text
    assert "\ntools/ci-local.sh && git push\n" in rp.portal_commands("portal-v0.2.0", linux=True)
    assert "\ngit push\n" in rp.portal_commands("portal-v0.2.0", linux=False)
    assert text.endswith(f"{rp.CHECK_SCRIPT} release portal-v0.2.0   # installs and starts the published portal release")
    order = [text.index(s) for s in ("git commit", "check-release.sh local", "git push\n", "tag-release.sh",
                                     "check-release.sh release")]
    assert order == sorted(order)                             # commit, test, push and tag, then check the release


def test_ticker_follows_the_suite_ticked(two_suites, tmp_path):
    """Every push starts every suite's CI: the ticker shows the ticked suite's runs and Nexus's, not another
    suite's (owner, 28-10-2026: the BC250 portal's release showed CI Windows Portable first)."""
    assert rp.suite_workflows(two_suites, "bc") == {"ci.yml", "release.yml"}
    assert rp.other_suites_workflows(two_suites, "bc") == {"ci-wp.yml", "release-wp.yml"}
    assert rp.other_suites_workflows(two_suites, "wp") == {"ci.yml", "release.yml"}
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    app = QApplication.instance() or QApplication([])          # noqa: F841 (kept alive for the window)
    from nexus_releases import main_window
    w = main_window.ReleaseWindow(two_suites, status_source=None, runs_source=lambda etag: (None, etag),
                                  notify=lambda *a: None, claude_source=None, jobs_source=None, suite="bc")
    runs = [run("CI Windows Portable", status="in_progress", n=4), run("CI Nexus", n=3), run(n=2),
            run("Release", "portal-v3.0.1", status="in_progress", n=1)]
    for data, path in zip(runs, ("ci-wp.yml", "ci-nexus.yml", "ci.yml", "release.yml")):
        data["path"] = f".github/workflows/{path}"
    w.build.checked((rp.parse_runs({"workflow_runs": runs}), "e1"))
    assert w.ticker.line == "Release on portal-v3.0.1: in progress   |   CI Nexus on main: passed   |   CI on main: passed"
    w.choose_suite("wp")
    w.ticker.checker.stop(2000)
    assert w.ticker.line.startswith("CI Windows Portable on main: in progress   |   CI Nexus on main: passed")
    assert "Release on" not in w.ticker.line and "|   CI on main" not in w.ticker.line
    w.close()


def test_notifications_follow_the_suite_ticked(two_suites, tmp_path):
    """A run that finishes is told about only when it is the ticked suite's or Nexus's (owner, 28-10-2026: CI Windows
    Portable notified while BC250 was released)."""
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    app = QApplication.instance() or QApplication([])          # noqa: F841 (kept alive for the window)
    from nexus_releases import main_window
    notes = []
    w = main_window.ReleaseWindow(two_suites, status_source=None, runs_source=lambda etag: (None, etag),
                                  notify=lambda *a: notes.append(a), claude_source=None, jobs_source=None, suite="bc")

    def runs(status, conclusion="success"):
        found = [run(name, status=status, conclusion=conclusion, n=n) for n, name in
                 ((3, "CI Windows Portable"), (2, "Nexus index"), (1, "CI"))]
        for data, path in zip(found, ("ci-wp.yml", "nexus-index.yml", "ci.yml")):
            data["path"] = f".github/workflows/{path}"
        return rp.parse_runs({"workflow_runs": found})
    w.build.checked((runs("in_progress"), "e1"))
    w.build.checked((runs("completed", "failure"), "e2"))
    assert notes[-1][0] == "GitHub build failed"
    assert "Nexus index on main" in notes[-1][1] and "CI on main" in notes[-1][1]
    assert "Windows Portable" not in notes[-1][1]
    w.close()


def test_a_windows_suite_tests_its_portal_on_the_handheld(two_suites):
    """The Windows Portable Suite has no check-release.sh and no BC-250: its portal and a withdrawal are tried from
    the checkout with its portal/run.ps1, and the published release is downloaded to install on the handheld."""
    assert rp.portal_run_script(two_suites, "bc") == "" and rp.portal_run_script(two_suites, "wp") == "wp/portal/run.ps1"
    text = rp.portal_commands("wp-portal-v1.0.1", linux=False, check="wp/tools/check-release.sh",
                              run_script="wp/portal/run.ps1")
    assert "BC-250" not in text and "check-release.sh" not in text and "bc250" not in text
    assert "\npowershell -NoProfile -ExecutionPolicy Bypass -File wp/portal/run.ps1 --windowed\n" in text
    assert text.endswith('\ngh release download wp-portal-v1.0.1 --dir "$TEMP/wp-portal-v1.0.1" --clobber')
    order = [text.index(s) for s in ("git commit", "run.ps1", "git push\n", "tag-release.sh", "gh release download")]
    assert order == sorted(order)
    withdraw = rp.withdraw_commands("wp-test-v0.1.0", "Broken.", run_script="wp/portal/run.ps1")
    assert "BC-250" not in withdraw and "check-release.sh" not in withdraw
    assert "\npowershell -NoProfile -ExecutionPolicy Bypass -File wp/portal/run.ps1 --windowed\n" in withdraw


def test_app_commands_put_the_portal_bump_first_when_the_push_needs_it():
    text = rp.app_commands(["alpha-v0.2.0"], linux=True, portal="1.9.0")
    first, second = text.splitlines()[:2]
    assert first.startswith("# First: step 2's Bump portal (portal 1.9.0)") and second.startswith("git add -A")
    assert command_lines(text) == command_lines(rp.app_commands(["alpha-v0.2.0"], linux=True))   # a comment only
    assert not rp.app_commands(["alpha-v0.2.0"]).startswith("#")


def test_app_commands_amend_the_unpushed_release_commit():
    text = rp.app_commands(["alpha-v0.2.0"], linux=True, amend=True)
    assert "git commit --amend --no-edit" in text and "git commit -m" not in text
    assert text.index("git add -A") < text.index("--amend") < text.index("ci-local.sh && git push") \
        < text.index("tag-release.sh alpha-v0.2.0")
    assert not text.startswith("#")


def test_git_button_commands():
    assert rp.add_command() == "git add -A && tools/fix-modes.sh && git status --short"
    checks = " && ".join(f"python3 {check} --base origin/main" for check in rp.manifest_checks(rp.CHECKOUT))
    assert rp.commit_command("Release alpha-v0.2.0", "origin/main") == (
        f"python3 {rp.VERSIONS_CHECK} && {checks} && "
        "git commit -m 'Release alpha-v0.2.0'")                       # the checks first, the commit only after
    assert f"python3 {rp.manifest_check(rp.CHECKOUT)} --base origin/main" in checks    # the default suite's among them
    assert rp.commit_command("it's", "pushed", python="/v/python").endswith("git commit -m 'it'\"'\"'s'")
    assert rp.commit_command("", "pushed", amend=True).endswith(" && git commit --amend --no-edit")
    two = rp.commit_command("m", "pushed", manifests=["a/tools/check_manifest.py", "b/tools/check_manifest.py"])
    assert two == (f"python3 {rp.VERSIONS_CHECK} && python3 a/tools/check_manifest.py --base pushed && "
                   "python3 b/tools/check_manifest.py --base pushed && git commit -m m")   # every suite's check
    assert rp.commit_message(rp.app_commands(["alpha-v0.2.0", "beta-v0.1.0"])) == \
        ("Release alpha-v0.2.0, beta-v0.1.0", False)
    assert rp.commit_message(rp.app_commands(["alpha-v0.2.0"], amend=True)) == ("", True)
    assert rp.commit_message(rp.portal_commands("portal-v0.2.0")) == ("Release portal-v0.2.0", False)
    assert rp.commit_message(rp.withdraw_commands("beta-v0.1.0", "Privacy.")) == ("", False)


def test_git_state(repo):
    assert rp.git_state(repo, "pushed") == (False, False, 1)         # clean, one commit ("work") not pushed
    write(repo / "apps/alpha/alpha/extra.py", "x = 2\n")
    write(repo / "apps/alpha/new.py", "y = 1\n")
    assert rp.git_state(repo, "pushed") == (True, False, 1)
    sh(repo, "add", "apps/alpha/alpha/extra.py")
    assert rp.git_state(repo, "pushed") == (True, True, 1)           # the new file is not staged yet
    sh(repo, "add", "-A")
    assert rp.git_state(repo, "pushed") == (False, True, 1)
    assert rp.git_state(repo, "main")[2] == 0


def test_untagged_releases_and_the_unpushed_release_commit(repo):
    assert rp.untagged_releases(rp.load_units(repo)) == ["beta-v0.1.0"]          # never tagged; alpha-v0.1.0 is
    rp.set_version(repo, unit(repo, "alpha"), "0.1.1")
    assert rp.untagged_releases(rp.load_units(repo)) == ["alpha-v0.1.1", "beta-v0.1.0"]
    sh(repo, "tag", "alpha-v0.1.1")
    sh(repo, "tag", "beta-v0.1.0")
    assert rp.untagged_releases(rp.load_units(repo)) == []
    assert rp.unpushed_release_commit(repo, "pushed") == ""                      # HEAD "work": not a release
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "Release alpha-v0.1.1")
    assert rp.unpushed_release_commit(repo, "pushed") == "Release alpha-v0.1.1"
    sh(repo, "branch", "-f", "pushed", "HEAD")                                   # pushed: nothing to amend
    assert rp.unpushed_release_commit(repo, "pushed") == ""


def test_window_bump_before_the_push_gives_step_ones_commands(window, repo):
    """The owner's case of 17-10-2026: step 1 said the push needs a portal bump (apps.toml gained an app), but the
    release was committed first. Bump portal then shows step 1's commands with the bump amended in, not the portal
    release's; the plain commit when the release is not committed yet."""
    _, tick, combo, notes = row(window, "alpha")
    tick.setChecked(True)
    window.apps_page.apply()                                  # alpha 0.1.1, beta 0.1.0 wait for their tags
    page = window.portal_page
    page.portal_version.setEditText("0.2.0")
    page.bump()
    out = page.output.toPlainText()
    assert "step 1's releases are not tagged yet: alpha-v0.1.1, beta-v0.1.0" in out
    assert 'git commit -m "Release alpha-v0.1.1, beta-v0.1.0"' in out and "--amend" not in out
    assert "tools/tag-release.sh alpha-v0.1.1 beta-v0.1.0" in out and "portal-v0.2.0" not in out
    assert window.commands.offered == command_lines(
        rp.app_commands(["alpha-v0.1.1", "beta-v0.1.0"]))

    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "Release alpha-v0.1.1, beta-v0.1.0")
    (repo / "portal/VERSION").write_text("0.1.0\n")             # as if the bump had not been made before the commit
    window.reload()
    page.portal_version.setEditText("0.2.0")
    page.bump()
    out = page.output.toPlainText()
    assert "git commit --amend --no-edit" in out and "tools/tag-release.sh alpha-v0.1.1 beta-v0.1.0" in out
    assert "portal-v0.2.0" not in out


def test_window_git_buttons(window, repo, monkeypatch):
    """git add, git commit and git push as buttons (owner, 19-10-2026): each only when it has something to do, with
    the message of the commit the last step showed, and run in the command line, whose tab opens. Push asks first
    (owner, 21-10-2026)."""
    from PyQt6.QtWidgets import QMessageBox
    ran = []
    monkeypatch.setattr(window.commands, "run_now", lambda command: ran.append(command) or True)
    add, commit, push = window.add_button, window.commit_button, window.push_button
    assert (add.isEnabled(), commit.isEnabled(), push.isEnabled()) == (False, False, True)   # "work" not pushed
    _, tick, _, _ = row(window, "alpha")
    tick.setChecked(True)
    window.apps_page.apply()
    assert window.commit_message.text() == "Release alpha-v0.1.1, beta-v0.1.0" and not window.amend_box.isChecked()
    assert add.isEnabled() and not commit.isEnabled()                # nothing staged yet
    add.click()
    assert ran[-1] == rp.add_command() and window.tabs.currentIndex() == window.commands_tab
    sh(repo, "add", "-A")
    window.reload()
    assert not add.isEnabled() and commit.isEnabled()
    window.commit_message.clear()
    assert not commit.isEnabled() and "Type a commit message first." in commit.toolTip()
    window.commit_message.setText("Release alpha-v0.1.1, beta-v0.1.0")
    commit.click()
    assert ran[-1].endswith(f" {rp.MANIFEST_CHECK} --base pushed && git commit -m 'Release alpha-v0.1.1, beta-v0.1.0'")
    window.commands.last_code, window.committing = 1, True           # the checks failed: the message stays
    window.refresh()
    assert window.commit_message.text() == "Release alpha-v0.1.1, beta-v0.1.0"
    window.commands.last_code, window.committing = 0, True
    window.refresh()
    assert window.commit_message.text() == ""
    monkeypatch.setattr(rp, "_token", "github_pat_x")                    # fine-grained: no warning
    with mock_question(QMessageBox.StandardButton.No) as asked:
        push.click()                                                 # it asks first: no, nothing runs
    text = asked.call_args.args[2]
    assert asked.called and ran[-1] != rp.push_command() and "work" in text and rp.push_command() in text
    assert "\u26a0" not in text
    with mock_question(QMessageBox.StandardButton.Yes):
        push.click()
    assert ran[-1] == rp.push_command()
    window.amend_box.setChecked(True)                                # HEAD is not pushed: it may be amended
    assert commit.isEnabled()
    window.portal_page.base_edit.setText("main")
    window.reload()
    assert not commit.isEnabled() and not push.isEnabled() and "pushed already" in commit.toolTip()


def test_window_git_pull_button(window, repo, monkeypatch):
    """git pull (owner, 28-10-2026: a push from the other machine only showed as a push that failed): always there
    when no command runs; it counts what the remote has that HEAD does not, and says (new) when GitHub's newest
    push on main is no commit here."""
    ran = []
    monkeypatch.setattr(window.commands, "run_now", lambda command: ran.append(command) or True)
    pull = window.pull_button
    assert pull.isEnabled() and pull.text() == "git pull" and rp.pull_command() in pull.toolTip()
    pull.click()
    assert ran[-1] == "git pull --rebase --autostash" and window.tabs.currentIndex() == window.commands_tab
    sh(repo, "checkout", "-q", "pushed")                                 # the other machine pushes two commits
    for name in ("a", "b"):
        write(repo / f"{name}.txt", name)
        sh(repo, "add", "-A")
        sh(repo, "commit", "-q", "-m", name)
    sh(repo, "checkout", "-q", "main")
    assert rp.behind(repo, "pushed") == 2
    window.reload()
    assert pull.text() == "git pull (2)" and "2 commits this checkout does not" in pull.toolTip()
    sh(repo, "branch", "-f", "pushed", "main")
    window.reload()
    assert pull.text() == "git pull"
    elsewhere = run(sha="f" * 40)                                         # GitHub saw a push this checkout lacks
    window.build.checked((rp.parse_runs({"workflow_runs": [elsewhere]}), "e1"))
    assert pull.text() == "git pull (new)" and "GitHub has a push this checkout does not (fffffff Fix it)" in pull.toolTip()
    here = run(sha=subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip())
    window.build.checked((rp.parse_runs({"workflow_runs": [here]}), "e2"))
    assert pull.text() == "git pull"


def test_window_git_tag_button(window, repo, monkeypatch):
    """git tag after git push (owner, 20-10-2026): tag-release.sh with step 1's untagged app releases, or on step 2's
    tab the portal's release; only once HEAD is pushed and something has no tag yet. It asks first, and warns about
    a token that reaches every repository (owner, 21-10-2026)."""
    from PyQt6.QtWidgets import QMessageBox
    ran = []
    monkeypatch.setattr(window.commands, "run_now", lambda command: ran.append(command) or True)
    tag = window.tag_button
    assert window.tags_to_push() == ["beta-v0.1.0"]                  # beta was never tagged
    assert not tag.isEnabled() and "Push first" in tag.toolTip()     # "work" is not pushed
    window.portal_page.base_edit.setText("main")
    window.reload()
    assert tag.isEnabled() and tag.toolTip().startswith("tools/tag-release.sh beta-v0.1.0\n")
    monkeypatch.setattr(rp, "_token", "gho_login")                       # a gh login reaches every repository
    with mock_question(QMessageBox.StandardButton.No) as asked:
        tag.click()
    assert not ran and "beta-v0.1.0" in asked.call_args.args[2] and "every repository" in asked.call_args.args[2]
    with mock_question(QMessageBox.StandardButton.Yes):
        tag.click()
    assert ran[-1] == "tools/tag-release.sh beta-v0.1.0" and window.tabs.currentIndex() == window.commands_tab
    window.tabs.setCurrentWidget(window.portal_page)
    portal = window.portal_page.portal_unit
    assert window.tags_to_push() == ([] if portal.released else [portal.tag])
    sh(repo, "tag", "beta-v0.1.0")
    window.tabs.setCurrentWidget(window.apps_page)
    window.reload()
    assert window.tags_to_push() == [] and not tag.isEnabled() and "Nothing to tag" in tag.toolTip()


def test_window_apply_bumps_the_portal_when_the_push_needs_it(window, repo):
    """The owner's case of 17-10-2026, second time: step 1 only said that the push needs a portal bump, the release
    was committed without it and ci-local failed. Apply now makes that bump itself (the lowest version CI accepts,
    with the portal's CHANGELOG entry), so the commands it lists pass CI; the portal release stays step 2."""
    row(window, "alpha")[1].setChecked(False)                 # ticked by default: it needs a release
    _, tick, combo, _ = row(window, "beta")
    tick.setChecked(True)
    combo.setEditText("0.2.0")                                # beta's never-released pin moves: apps.toml changes
    window.apps_page.apply()
    out = window.apps_page.output.toPlainText()
    assert (repo / "portal/VERSION").read_text() == "0.2.0\n"
    assert (repo / "portal/bc250_portal/__init__.py").read_text() == '__version__ = "0.2.0"\n'
    assert (repo / "portal/CHANGELOG").read_text().split("\n\n")[1] == "Release 0.2.0. Pins beta-v0.2.0."
    assert "portal: 0.2.0 in portal/VERSION, portal/bc250_portal/__init__.py and CHANGELOG entry" in out
    assert "apps.toml changed since pushed (beta 0.1.0 -> 0.2.0)" in out and "step 2" in out
    assert "needs at least a minor bump" not in out           # check_manifest passes against the last push
    assert window.commands.offered == command_lines(rp.app_commands(["beta-v0.2.0"]))
    assert not window.commands.offered[0].startswith("#")
    window.apps_page.apply()                                  # again: the bump is there, nothing more to do
    assert "portal: 0.2.0 in" not in window.apps_page.output.toPlainText()
    assert (repo / "portal/CHANGELOG").read_text().count("Release 0.2.0.") == 1


def test_the_minimum_needs_no_second_bump_for_the_pins(repo):
    """The owner's case of 17-10-2026: the push with the apps' releases carried the portal bump; the next push, with
    their checksums pinned, was offered 1.13.1 (a patch over the last push). Against the last portal release the
    bump already made covers it, so the minimum stays the version in the tree and Apply makes no second bump."""
    sh(repo, "tag", "portal-v0.1.0")
    rp.set_version(repo, unit(repo, "beta"), "0.2.0")
    assert rp.follow_unreleased_pin(repo, unit(repo, "beta"))
    rp.set_version(repo, unit(repo, "portal"), "0.2.0")
    sh(repo, "commit", "-qam", "Release beta-v0.2.0")
    sh(repo, "branch", "-f", "pushed")                                        # pushed with the bump in it
    text = (repo / "portal/apps.toml").read_text()
    write(repo / "portal/apps.toml", text.replace('name = "beta"\nsummary = "s"', 'name = "beta"\nsummary = "pinned"'))
    assert rp.portal_minimum(repo, "pushed", "0.2.0") == ("0.2.0", "beta 0.1.0 -> 0.2.0")
    assert rp.portal_minimum(repo, "pushed", "0.3.0") == ("0.3.0", "beta 0.1.0 -> 0.2.0")   # bumped further: kept


def test_withdrawal(repo):
    now = datetime.datetime(2026, 10, 13, 12, 0, tzinfo=datetime.timezone.utc)
    units = rp.load_units(repo)
    assert [u.key for u in rp.withdrawable(repo, units)] == ["beta"]             # alpha is the required app
    beta = unit(repo, "beta")
    before = (repo / "portal/apps.toml").read_text()
    changed = rp.withdraw(repo, beta, 'Privacy: shows the "account ID".', now)
    text = (repo / "portal/apps.toml").read_text()
    assert text == before.replace('[apps.beta]\nname = "beta"\nsummary = "s"\n',
                                  '[apps.beta]\nname = "beta"\nsummary = "s"\n'
                                  'withdrawn = "Privacy: shows the \\"account ID\\"."\n')
    assert rp.withdrawn_reason(repo, "beta") == 'Privacy: shows the "account ID".'
    assert [p.relative_to(repo).as_posix() for p in changed] == ["portal/apps.toml", "apps/beta/CHANGELOG"]
    assert (repo / "apps/beta/CHANGELOG").read_text().startswith(
        'Changelog: 13-10-2026 14:00:00\n\nWithdrawn: beta-v0.1.0. Privacy: shows the "account ID".\n')
    # The portal release that follows: a minor bump, and its CHANGELOG entry names the withdrawal.
    assert rp.changed_withdrawals(repo, "pushed") == [("beta-v0.1.0", 'Privacy: shows the "account ID".')]
    assert rp.portal_minimum(repo, "pushed", "0.1.0") == ("0.2.0", "beta was withdrawn")
    assert rp.portal_text("0.2.0", [], "", rp.changed_withdrawals(repo, "pushed")) == (
        'Release 0.2.0. Withdraws beta-v0.1.0: Privacy: shows the "account ID".')
    commands = rp.withdraw_commands("beta-v0.1.0", "Privacy.", now)
    assert ("gh release edit beta-v0.1.0 --prerelease --title 'Withdrawn: beta-v0.1.0' --notes 'Withdrawn on "
            "13-10-2026: Privacy. Do not install this release.'") in commands
    # Taken back: apps.toml as it was, and a CHANGELOG entry that says so.
    rp.withdraw(repo, beta, "", now)
    assert (repo / "portal/apps.toml").read_text() == before
    assert "Withdrawal of beta-v0.1.0 taken back." in (repo / "apps/beta/CHANGELOG").read_text()
    with pytest.raises(ValueError, match="no \\[apps.gamma\\]"):
        rp.set_withdrawn(before, "gamma", "x")


# --- The window -------------------------------------------------------------------------------------------------

launched: list[str] = []


@pytest.fixture
def window(repo, tmp_path):
    pytest.importorskip("PyQt6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    app = QApplication.instance() or QApplication([])          # noqa: F841 (kept alive for the window)
    from nexus_releases import main_window
    w = main_window.ReleaseWindow(repo, sha256_source=lambda tag: SHA, launch=launched.append, runs_source=None,
                                  status_source=None)
    w.portal_page.base_edit.setText("pushed")
    w.reload()
    yield w
    w.close()


def row(w, key):
    return next(r for r in w.apps_page.rows if r[0].key == key)


def test_window_release_then_portal(window, repo):
    keys = [r[0].key for r in window.apps_page.rows]
    assert keys == ["core", "alpha", "beta", "standalone"]   # standalone apps release independently
    _, tick, combo, notes = row(window, "alpha")
    assert combo.currentText() == "0.1.1"                     # alpha 0.1.0 is tagged: a bump first
    _, btick, bcombo, _ = row(window, "beta")
    assert bcombo.currentText() == "0.1.0"                    # never tagged: as it is
    tick.setChecked(True)
    notes.setText("Fixes.")
    window.apps_page.apply()
    out = window.apps_page.output.toPlainText()
    assert (repo / "apps/alpha/VERSION").read_text() == "0.1.1\n"
    assert "Release 0.1.1. Fixes." in (repo / "apps/alpha/CHANGELOG").read_text()
    assert "tools/tag-release.sh alpha-v0.1.1" in out
    assert "check_versions.py" in out

    sh(repo, "tag", "alpha-v0.1.1")                           # the owner tagged it; GitHub built it
    window.reload()
    page = window.portal_page
    assert [u.tag for u, _ in page.candidates] == ["alpha-v0.1.1"]
    page.pin()
    assert f'sha256 = "{SHA}"' in (repo / "portal/apps.toml").read_text()
    assert "at least 0.1.1" in page.minimum.text() and page.portal_version.currentText() == "0.1.1"
    sh(repo, "tag", "beta-v0.1.0")                            # every pinned tag exists: a portal release can follow
    page.bump()
    assert (repo / "portal/VERSION").read_text() == "0.1.1\n"
    assert '__version__ = "0.1.1"' in (repo / "portal/bc250_portal/__init__.py").read_text()
    assert "Release 0.1.1. Pins alpha-v0.1.1." in (repo / "portal/CHANGELOG").read_text()
    assert "tools/tag-release.sh portal-v0.1.1" in page.output.toPlainText()


def test_window_refuses_a_tagged_version(window, repo, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text: warnings.append(text))
    _, tick, combo, _ = row(window, "alpha")
    tick.setChecked(True)
    combo.setEditText("0.1.0")
    window.apps_page.apply()
    assert "already tagged" in warnings[0]
    assert (repo / "apps/alpha/CHANGELOG").read_text().startswith("Changelog: 01-01-2026")


def test_nexus_has_a_version_of_its_own(repo):
    """The root VERSION and CHANGELOG are Nexus's (owner, 28-10-2026): a row beside core, released with a "Release
    x.y.z." entry, never tagged here; a checkout without a root VERSION has no row."""
    assert all(u.key != rp.NEXUS for u in rp.load_units(repo))
    write(repo / "VERSION", "0.1.0\n")
    write(repo / "CHANGELOG", "Changelog: 01-01-2026 00:00:00\n\nFrom before.\n")
    nexus = unit(repo, rp.NEXUS)
    assert (nexus.kind, nexus.path, nexus.tag) == ("nexus", ".", "nexus-v0.1.0")
    assert nexus.needs_release and nexus.release_reason == "first release" and not nexus.released
    assert rp.version_choices(repo, nexus) == (["0.1.0", "0.1.1", "0.2.0", "1.0.0"], "the first release")
    assert rp.set_version(repo, nexus, "0.1.0") == [repo / "VERSION"]         # never the copies of the units
    assert (repo / "apps/alpha/alpha/__init__.py").read_text() == 'APP = "alpha"\n__version__ = "0.1.0"\n'
    rp.add_changelog_entry(repo, nexus, rp.release_text("0.1.0", ""))
    nexus = unit(repo, rp.NEXUS)
    assert nexus.released and nexus.released_as == "0.1.0" and not nexus.needs_release
    assert nexus.release_reason == "no"
    rp.add_changelog_entry(repo, nexus, "Added. The ticker.")
    rp.add_changelog_entry(repo, nexus, "Fixed. A typo.")
    nexus = unit(repo, rp.NEXUS)
    assert nexus.needs_release and nexus.release_reason == "yes: 2 CHANGELOG entries"
    assert nexus.changed == ["Fixed. A typo.", "Added. The ticker."]
    choices, why = rp.version_choices(repo, nexus)
    assert choices[0] == "0.2.0" and why == "minor: 1 Added, 1 Fixed since Release 0.1.0"
    assert rp.last_release("Changelog: x\n\nRelease 2.0.0. Notes.\n\nChangelog: y\n\nRelease 1.0.0.\n") == "2.0.0"
    commands = rp.nexus_commands("0.2.0", linux=False)
    assert commands.splitlines()[:3] == ["git add -A && tools/fix-modes.sh", 'git commit -m "Release nexus-v0.2.0"',
                                         "git push"]
    assert "nexus-v0.2.0" in commands.splitlines()[-1] and rp.TAG_SCRIPT not in commands


def test_window_releases_nexus(window, repo):
    write(repo / "VERSION", "0.1.0\n")
    write(repo / "CHANGELOG", "Changelog: 01-01-2026 00:00:00\n\nRelease 0.1.0.\n")
    rp.add_changelog_entry(repo, unit(repo, rp.NEXUS), "Added. The ticker.")
    window.reload()
    for unit_, tick, _, _ in window.apps_page.rows:
        tick.setChecked(unit_.kind == rp.NEXUS)
    nexus_row = row(window, rp.NEXUS)
    assert nexus_row[2].currentText() == "0.2.0"
    assert window.apps_page.table.item(window.apps_page.rows.index(nexus_row), 3).text() == "nexus-v0.1.0"
    window.apps_page.apply()
    out = window.apps_page.output.toPlainText()
    assert (repo / "VERSION").read_text() == "0.2.0\n"
    assert (repo / "CHANGELOG").read_text().split("\n\n")[1] == "Release 0.2.0."
    assert 'git commit -m "Release nexus-v0.2.0"' in out and rp.TAG_SCRIPT not in out
    assert window.commit_message.text() == "Release nexus-v0.2.0"


def test_window_reads_new_tags_when_step_2_opens(window, repo):
    _, tick, combo, _ = row(window, "alpha")
    tick.setChecked(True)                                     # typed in step 1: kept
    assert [u.tag for u, _ in window.portal_page.candidates] == ["alpha-v0.1.0"]
    rp.set_version(repo, unit(repo, "alpha"), "0.1.1")
    sh(repo, "tag", "alpha-v0.1.1")                           # tagged in a terminal while the window is open
    window.tabs.setCurrentIndex(1)
    assert [u.tag for u, _ in window.portal_page.candidates] == ["alpha-v0.1.1"]
    assert window.portal_page.empty_note.isHidden()
    assert row(window, "alpha")[1].isChecked()


def test_window_refresh_reads_changes_and_keeps_what_was_typed(window, repo):
    _, tick, combo, notes = row(window, "alpha")
    row(window, "beta")[1].setChecked(False)                  # ticked by fill(); unticked: it waits
    combo.setEditText("0.2.0")
    notes.setText("Fixes.")
    window.portal_page.portal_notes.setText("Pins.")
    assert window.status.value.text() == "Clean"
    rp.set_version(repo, unit(repo, "beta"), "0.1.1")         # changed in a terminal while the window is open
    window.refresh()
    assert window.status.value.text() == "Changed" and "has changes" in window.status.toolTip()
    _, tick, combo, notes = row(window, "alpha")
    assert (tick.isChecked(), combo.currentText(), notes.text()) == (True, "0.2.0", "Fixes.")
    _, btick, bcombo, _ = row(window, "beta")
    assert not btick.isChecked() and bcombo.currentText() == "0.1.1"   # the untick kept; the version offered now
    assert window.portal_page.portal_notes.text() == "Pins."


def test_window_pins_a_new_app_listed_without_a_sha256_line(window, repo, monkeypatch):
    """A new app's entry has a tag but no sha256 line until its first release (apps.toml allows it): Pin adds the
    line. And when pin_app refuses an entry, the window says so and pins the others, instead of exiting."""
    toml = repo / "portal/apps.toml"
    text = toml.read_text()
    toml.write_text(text.replace('tag = "beta-v0.1.0"\nsha256 = ""\n', 'tag = "beta-v0.1.0"\n'))
    sh(repo, "tag", "beta-v0.1.0")                            # released; alpha-v0.1.0 is tagged in the fixture
    window.reload()
    page = window.portal_page
    assert [u.tag for u, _ in page.candidates] == ["alpha-v0.1.0", "beta-v0.1.0"]
    page.pin()
    assert f'tag = "beta-v0.1.0"\nsha256 = "{SHA}"\nrequired = false' in toml.read_text()
    assert "beta-v0.1.0: pinned" in page.output.toPlainText()
    assert page.candidates == []

    rp.set_version(repo, unit(repo, "alpha"), "0.1.1")
    sh(repo, "tag", "alpha-v0.1.1")
    window.reload()
    monkeypatch.setattr(rp, "pin", lambda root, unit, sha, suite=None: (_ for _ in ()).throw(SystemExit("no [apps.alpha]")))
    page.pin()                                                # the window stays; the log says why
    assert "alpha-v0.1.1: not pinned (no [apps.alpha])." in page.output.toPlainText()


def test_window_explains_an_empty_pin_list(window, repo):
    rp.pin(repo, unit(repo, "alpha"), SHA)
    window.reload()
    assert window.portal_page.candidates == []
    assert not window.portal_page.empty_note.isHidden()
    assert "Fetch tags" in window.portal_page.empty_note.text()
    portal = window.portal_page.portal_unit                   # nothing to pin never holds an untagged portal back
    assert not portal.released and f"{portal.tag} is not tagged yet" in window.portal_page.empty_note.text()
    sh(repo, "tag", portal.tag)
    window.reload()
    assert "is not tagged yet" not in window.portal_page.empty_note.text()


def needs(root):
    return {u.key: (u.needs_release, u.release_reason, u.changed) for u in rp.load_units(root)}


def test_needs_release_follows_what_ships(repo):
    alpha = needs(repo)["alpha"]
    assert alpha == (True, "yes: 1 file", ["apps/alpha/alpha/extra.py"])          # committed after the tag
    assert needs(repo)["beta"][:2] == (True, "first release")
    assert needs(repo)["core"][0] is False
    sh(repo, "tag", "alpha-v0.1.1")                                               # released: nothing left
    assert needs(repo)["alpha"][:2] == (False, "no")
    write(repo / "apps/alpha/tests/test_y.py", "x = 2\n")                         # tests do not ship
    write(repo / "apps/alpha/requirements-dev.txt", "pytest\n")
    assert needs(repo)["alpha"][0] is False
    write(repo / "apps/alpha/alpha/__init__.py", 'APP = "alpha"\n__version__ = "0.1.0"\n# changed\n')
    assert needs(repo)["alpha"][2] == ["apps/alpha/alpha/__init__.py"]           # not committed yet
    write(repo / "apps/alpha/alpha/new.py", "y = 1\n")
    assert "apps/alpha/alpha/new.py" in needs(repo)["alpha"][2]                  # new, untracked


def test_core_and_manual_changes_count_for_the_apps_that_ship_them(repo):
    sh(repo, "tag", "alpha-v0.1.1")
    sh(repo, "tag", "beta-v0.1.0")
    write(repo / "core/bc250_core/widgets.py", "class StatusText: pass\n")
    state = needs(repo)
    assert state["alpha"][:2] == (True, "yes: core") and state["beta"][0] is False   # beta does not import core
    core = next(u for u in rp.load_units(repo) if u.kind == "core")
    assert (core.in_apps, core.changed, core.release_reason) == (
        ["alpha"], ["core/bc250_core/widgets.py"], "changed: goes into 1 app release")
    assert not core.needs_release                                                 # core itself is never tagged
    write(repo / "docs/apps/alpha.md", "# Alpha\n\nMore.\n")                      # shipped as MANUAL.md
    assert needs(repo)["alpha"][1] == "yes: 1 file + core"


def test_core_bumped_with_its_change_needs_no_new_version(repo):
    """Core went to a new version with its change (released with some apps), and another app's release still
    carries it: that version already holds the change, so core offers itself as it is, not a higher one."""
    sh(repo, "tag", "alpha-v0.1.1")
    write(repo / "core/bc250_core/widgets.py", "class StatusText: pass\n")
    assert rp.core_is_current(repo) is False                                      # changed, not bumped
    core = unit(repo, "core")
    rp.set_version(repo, core, "0.1.1")
    assert rp.core_is_current(repo) is True                                       # the bump, not committed yet
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "core 0.1.1")
    core = unit(repo, "core")
    assert core.current and core.in_apps == ["alpha"]                             # alpha-v0.1.1 has the old core
    assert core.release_reason == "0.1.1 has it: goes into 1 app release"
    write(repo / "core/bc250_core/widgets.py", "class StatusText: pass\n# more\n")
    assert not unit(repo, "core").current                                         # a change after the bump


def test_window_offers_a_current_core_as_it_is(window, repo):
    sh(repo, "tag", "alpha-v0.1.1")
    write(repo / "core/bc250_core/widgets.py", "class StatusText: pass\n")
    rp.set_version(repo, unit(repo, "core"), "0.1.1")
    window.reload()
    core, tick, combo, _ = window.apps_page.rows[0]
    assert core.key == "core" and combo.itemText(0) == "0.1.1" and not tick.isEnabled()
    write(repo / "core/VERSION", "0.1.0\n")                                      # changed, not bumped
    sh(repo, "checkout", "-q", "--", "core")
    write(repo / "core/bc250_core/widgets.py", "class StatusText: pass\n")
    window.reload()
    core, tick, combo, _ = window.apps_page.rows[0]
    assert combo.itemText(0) == "0.1.1" and tick.isEnabled()                      # the next version, to tick


def test_window_ticks_what_needs_a_release_from_the_start(window, repo):
    ticked = lambda: [u.key for u, tick, _, _ in window.apps_page.rows if tick.isChecked()]   # noqa: E731
    assert ticked() == ["alpha", "beta"]                      # no click needed
    row(window, "alpha")[1].setChecked(False)
    write(repo / "apps/standalone/extra.py", "x = 1\n")      # needs a release only since the window filled
    window.refresh()
    assert ticked() == ["beta", "standalone"]                 # the untick kept, the new one ticked
    window.reload()
    assert ticked() == ["alpha", "beta", "standalone"]        # a reload without restore: what needs a release


def test_window_ticks_what_needs_a_release(window, repo):
    for _, tick, _, _ in window.apps_page.rows:
        tick.setChecked(False)
    window.apps_page.tick_needed()
    ticked = [u.key for u, tick, _, _ in window.apps_page.rows if tick.isChecked()]
    assert ticked == ["alpha", "beta"]
    item = window.apps_page.table.item(1, 4)
    assert item.text() == "yes: 1 file" and "apps/alpha/alpha/extra.py" in item.toolTip()
    assert "needs a release" in window.portal_page.portal_needs.text()


def test_a_tag_before_the_bump_is_reported(repo):
    rp.set_version(repo, unit(repo, "beta"), "0.2.0")
    sh(repo, "tag", "beta-v0.2.0")                            # tagged, but the bump is not committed
    assert rp.bad_tags(repo, rp.load_units(repo)) == ["beta-v0.2.0 points at a commit where apps/beta/VERSION is 0.1.0"]
    sh(repo, "tag", "-d", "beta-v0.2.0")
    sh(repo, "commit", "-qam", "bump")
    sh(repo, "tag", "beta-v0.2.0")
    assert rp.bad_tags(repo, rp.load_units(repo)) == []


def test_window_warns_about_a_bad_tag(window, repo):
    assert window.bad_tags.isHidden()
    rp.set_version(repo, unit(repo, "beta"), "0.2.0")
    sh(repo, "tag", "beta-v0.2.0")
    window.reload()
    text = window.bad_tags.text()
    assert not window.bad_tags.isHidden() and "git tag -d beta-v0.2.0" in text and "tag-release.sh beta-v0.2.0" in text


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the checks run on the board: Linux only")
def test_window_check_buttons(window, repo):
    """The board checks are on the Test on this board tab (owner, 20-10-2026), not on the steps."""
    page = window.run_page
    launched.clear()
    page.local_button.click()                                    # the suite has no check-release.sh yet
    assert launched == [] and f"no {rp.CHECK_SCRIPT}" in page.output.toPlainText()
    write(repo / rp.CHECK_SCRIPT, "#!/bin/sh\n")
    page.local_button.click()
    page.release_button.click()
    page.withdraw_button.click()
    script = str(repo / rp.CHECK_SCRIPT)
    assert launched == [f"{script} local", f"{script} release", f"{script} local"]
    log = page.output.toPlainText()
    assert "published portal-v0.1.0 release" in log and "App not available" in log
    assert "portal-v0.1.0" in page.release_button.toolTip()
    assert not hasattr(window.portal_page, "local_button") and not hasattr(window.withdraw_page, "test_button")



@pytest.mark.skipif(sys.platform == "win32", reason="the tour is a bash script that records a Linux desktop")
def test_window_records_the_portal_tour(window, repo, tmp_path, monkeypatch):
    """Record portal tour runs the suite's record-tour.sh in the background, its output in Logs, into
    ~/Videos/bc250-portal-tour-v<portal version>.mp4, and opens the video (owner, 20-10-2026)."""
    from PyQt6.QtWidgets import QApplication
    from nexus_releases import main_window
    page = window.run_page
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    opened = []
    monkeypatch.setattr(main_window, "open_url", opened.append)
    page.tour_button.click()
    assert f"has no {rp.RECORD_SCRIPT}" in page.output.toPlainText() and page.recorder is None

    def record(script: str) -> None:
        write(repo / rp.RECORD_SCRIPT, script)
        page.output.clear()
        window.tabs.setCurrentWidget(page)
        page.tour_button.click()
        assert not page.tour_button.isEnabled() and window.tabs.currentIndex() == window.log_tab
        page.recorder.waitForFinished(10000)
        for _ in range(20):
            QApplication.processEvents()
            if page.recorder is None:
                break
        assert page.recorder is None and page.tour_button.isEnabled()

    out = tmp_path / "home" / "Videos" / "bc250-portal-tour-v0.1.0.mp4"
    record('echo "Recording the portal tour into $1"\nmkdir -p "$(dirname "$1")"\necho video > "$1"\n')
    log = page.output.toPlainText()
    assert f"$ {rp.RECORD_SCRIPT} {out}" in log and f"Recording the portal tour into {out}" in log
    assert out.read_text() == "video\n" and opened == [out.as_uri()]
    record('echo "ffmpeg is needed" >&2\nexit 1\n')
    log = page.output.toPlainText()
    assert "ffmpeg is needed" in log and "stopped with exit code 1" in log and len(opened) == 1


# --- Run from the checkout ------------------------------------------------------------------------------------------

def test_installer_tests_target(repo):
    assert rp.installer_tests_target(repo) is None                   # no tools/installer-tests/gui
    gui = repo / "tools/installer-tests/gui"
    write(gui / "VERSION", "0.3.0\n")
    write(gui / "installer_test_gui/__init__.py", 'APP_NAME = "BC-250 Installer Tests"\n')
    target = rp.installer_tests_target(repo)
    assert (target.module, target.label, target.folder, target.changes_board) == \
        ("installer_test_gui", "BC-250 Installer Tests 0.3.0", gui, False)
    real = rp.installer_tests_target()                              # this checkout's
    assert real is not None and real.icon is not None and real.icon.is_file()


def add_windows(root: Path) -> None:
    """alpha and beta get a window each, beta changes the board, the standalone app keeps its package a level deeper
    (like mtool), and the checkout-only app has one too (like this app)."""
    for key in ("alpha", "beta"):
        write(root / f"apps/{key}/{key}/__main__.py", "print('hi')\n")
    write(root / "apps/alpha/alpha/__init__.py",
          'APP_NAME = "Alpha App"\nAPP_ID = "alpha-app"\nLOGO = ROOT / "images" / "alpha-logo.png"\n')
    for name in ("01-screenshot.png", "alpha-app.png", "alpha-logo.png"):
        write(root / f"apps/alpha/images/{name}", "png")
    write(root / "apps/alpha/tests/fake/__main__.py", "")                         # tests are never listed
    write(root / "apps/standalone/tool-dir/tool/__main__.py", "")
    write(root / "apps/releases/rel/__main__.py", "")
    toml = root / "portal/apps.toml"
    text = toml.read_text().replace('[apps.beta]\nname = "beta"\nsummary = "s"\ntag = "beta-v0.1.0"\nsha256 = ""\n'
                                    'required = false\nchanges_board = false',
                                    '[apps.beta]\nname = "beta"\nsummary = "s"\ntag = "beta-v0.1.0"\nsha256 = ""\n'
                                    'required = false\nchanges_board = true')
    assert "changes_board = true" in text
    toml.write_text(text)


def test_launch_targets(repo):
    add_windows(repo)
    targets = {t.module: t for t in rp.launch_targets(repo)}
    assert sorted(targets) == ["alpha", "beta", "tool"]                        # not the checkout-only app, not tests
    alpha, beta, tool = targets["alpha"], targets["beta"], targets["tool"]
    assert (alpha.name, alpha.label, alpha.folder) == ("Alpha App", "Alpha App 0.1.0", repo / "apps/alpha")
    assert alpha.icon == repo / "apps/alpha/images/alpha-logo.png"            # the one its __init__ names
    assert beta.changes_board and not alpha.changes_board and beta.name == "beta" and beta.icon is None
    assert tool.key == "standalone" and tool.folder == repo / "apps/standalone/tool-dir"
    command, env = rp.launch_command(repo, alpha, python="/venv/python")
    assert command == ["/venv/python", "-m", "alpha"]
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(repo / "core")


def test_portal_target(repo):
    assert rp.portal_target(repo) is None                                     # the fixture's portal has no window
    write(repo / "portal/bc250_portal/__main__.py", "print('portal')\n")
    write(repo / "portal/bc250_portal/__init__.py", 'APP_NAME = "Suite Portal"\n__version__ = "0.1.0"\n')
    write(repo / "portal/images/bc250-bazzite-suite.webp", "webp")
    portal = rp.portal_target(repo)
    assert (portal.key, portal.module, portal.folder, portal.label) == (
        "portal", "bc250_portal", repo / "portal", "Suite Portal 0.1.0")
    assert portal.icon == repo / "portal/images/bc250-bazzite-suite.webp" and not portal.changes_board
    command, env = rp.launch_command(repo, portal, python="/venv/python")
    assert command == ["/venv/python", "-m", "bc250_portal"]                  # --source auto: from the checkout
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(repo / "core")
    assert rp.portal_target() is not None and rp.portal_target().module == "bc250_portal"      # this checkout's


def test_the_portal_is_the_first_icon_under_test_local_apps(window, repo, tmp_path, monkeypatch):
    from nexus_releases import main_window
    add_windows(repo)
    write(repo / "portal/bc250_portal/__main__.py", "print('portal')\n")
    monkeypatch.setattr(main_window, "LOG_DIR", tmp_path / "logs")
    started = []
    window.start = lambda command, env, cwd, log: started.append((command, cwd, log)) or FakeProcess()
    window.reload()
    page = window.run_page
    modules = [page.apps.item(i).data(0x0100).module for i in range(page.apps.count())]
    assert modules[0] == "bc250_portal" and modules[1:] == ["alpha", "beta", "tool"]
    monkeypatch.setattr(main_window, "instance_running", lambda app_id: False)
    page.apps.itemClicked.emit(page.apps.item(0))
    assert started == [([sys.executable, "-m", "bc250_portal"], repo / "portal", tmp_path / "logs/bc250_portal.log")]


def test_an_open_portal_is_warned_about_and_not_started_again(window, repo, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from nexus_releases import main_window
    write(repo / "portal/bc250_portal/__main__.py", "print('portal')\n")
    write(repo / "portal/bc250_portal/__init__.py", 'APP_NAME = "Suite Portal"\nAPP_ID = "suite-portal"\n')
    monkeypatch.setattr(main_window, "LOG_DIR", tmp_path / "logs")
    started, asked = [], []
    window.start = lambda command, env, cwd, log: started.append(command) or FakeProcess()
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: asked.append(args[2]))
    seen = []
    monkeypatch.setattr(main_window, "instance_running", lambda app_id: seen.append(app_id) or True)
    window.reload()
    page = window.run_page
    page.apps.itemClicked.emit(page.apps.item(0))
    assert seen == ["suite-portal"] and started == []                          # open: warned, not started
    assert len(asked) == 1 and "already open" in asked[0] and "Close Suite Portal first" in asked[0]
    monkeypatch.setattr(main_window, "instance_running", lambda app_id: False)
    page.apps.itemClicked.emit(page.apps.item(0))
    assert len(started) == 1 and len(asked) == 1


def test_instance_running_sees_a_listening_app_and_does_not_disturb_it():
    pytest.importorskip("PyQt6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtNetwork import QLocalServer
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])          # noqa: F841 (kept alive for the sockets)
    from bc250_core.instance import server_name
    from nexus_releases import main_window
    name = server_name("suite-test-instance")
    QLocalServer.removeServer(name)
    assert not main_window.instance_running("suite-test-instance")
    server = QLocalServer()
    assert server.listen(name)
    try:
        assert main_window.instance_running("suite-test-instance")
    finally:
        server.close()
    assert not main_window.instance_running("suite-test-instance")


def test_docs_targets(repo):
    assert rp.docs_targets(repo) == []                                        # no mkdocs.yml
    write(repo / "mkdocs.yml", "site_name: S\nsite_url: https://example.invalid/suite/\n")
    write(repo / "nexus/mkdocs.yml", "INHERIT: ../mkdocs.yml\nsite_name: Nexus\nsite_url: https://example.invalid/\n")
    docs, nexus = rp.docs_targets(repo)
    assert (docs.module, docs.folder, docs.label) == ("mkdocs", repo, "S wiki (local)")
    assert docs.url == f"http://127.0.0.1:{rp.DOCS_PORT}/suite/?design"       # site_url's path, the design panel open
    command, _ = rp.launch_command(repo, docs, python="/venv/python")
    assert command == ["/venv/python", "-m", "mkdocs", "serve", "-f", "mkdocs.yml",
                       "--dev-addr", f"127.0.0.1:{rp.DOCS_PORT}"]
    assert nexus.label == "Nexus wiki (local)" and nexus.url == f"http://127.0.0.1:{rp.DOCS_PORT + 1}/?design"
    assert nexus.args[:3] == ("serve", "-f", "nexus/mkdocs.yml") and docs.log_name != nexus.log_name
    assert not docs.note
    write(repo / "mkdocs.yml", "site_name: S\n")
    assert rp.docs_targets(repo)[0].url == f"http://127.0.0.1:{rp.DOCS_PORT}/?design"


def test_docs_targets_on_the_network(repo):
    write(repo / "mkdocs.yml", "site_name: S\nsite_url: https://example.invalid/suite/\n")
    (docs,) = rp.docs_targets(repo, network=True, addresses=["192.0.2.7"])
    port = rp.NETWORK_PORT                                                    # not the local one: both can run
    assert docs.label == "S wiki (network)" and docs.args[-1] == f"0.0.0.0:{port}"
    assert docs.url == f"http://127.0.0.1:{port}/suite/?design"               # this computer's browser
    assert docs.note == f"On the other devices: http://192.0.2.7:{port}/suite/"
    assert docs.log_name != rp.docs_targets(repo)[0].log_name
    assert "no network address" in rp.docs_targets(repo, network=True, addresses=[])[0].note


def test_network_addresses_leave_out_loopback():
    assert all(not a.startswith("127.") for a in rp.network_addresses())


def test_window_serves_the_manual(window, repo, tmp_path, monkeypatch):
    from nexus_releases import main_window
    write(repo / "mkdocs.yml", "site_name: S\nsite_url: https://example.invalid/suite/\n")
    monkeypatch.setattr(main_window, "LOG_DIR", tmp_path / "logs")
    started, opened, up = [], [], [False]
    monkeypatch.setattr(main_window, "answers", lambda url: up[0])
    monkeypatch.setattr(main_window, "open_url", opened.append)
    window.start = lambda command, env, cwd, log: started.append((command, cwd)) or FakeProcess()
    window.reload()
    page = window.run_page
    items = [page.apps.item(i) for i in range(page.apps.count())]
    docs = items[-1]                                                          # after the apps
    assert docs.text() == "S wiki (local)"
    page.apps.itemClicked.emit(docs)
    assert started == [([sys.executable, "-m", "mkdocs", "serve", "-f", "mkdocs.yml",
                         "--dev-addr", f"127.0.0.1:{rp.DOCS_PORT}"], repo)]
    page.poll()
    assert opened == []                                                       # not up yet
    up[0] = True
    page.poll()
    page.poll()
    assert opened == [f"http://127.0.0.1:{rp.DOCS_PORT}/suite/?design"]       # once
    page.apps.itemClicked.emit(docs)                                          # already up: only the page again
    assert len(started) == 1 and len(opened) == 2


def test_window_serves_the_wikis_on_the_network(window, repo, tmp_path, monkeypatch):
    from nexus_releases import main_window
    write(repo / "mkdocs.yml", "site_name: S\n")
    monkeypatch.setattr(main_window, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(rp, "network_addresses", lambda: ["192.0.2.7"])
    monkeypatch.setattr(main_window, "answers", lambda url: False)
    started = []
    window.start = lambda command, env, cwd, log: started.append((command, log)) or FakeProcess()
    window.reload()
    page = window.run_page
    page.network_box.setChecked(True)                                         # the icons follow
    docs = page.apps.item(page.apps.count() - 1)
    assert docs.text() == "S wiki (network)"
    page.apps.itemClicked.emit(docs)
    assert started[0][0][-1] == f"0.0.0.0:{rp.NETWORK_PORT}"
    assert started[0][1].name == "mkdocs-root-network.log"
    assert f"http://192.0.2.7:{rp.NETWORK_PORT}/" in page.output.toPlainText()


class FakeProcess:
    def __init__(self, code=None):
        self.code = code

    def poll(self):
        return self.code


def test_window_runs_an_app_from_the_checkout(window, repo, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from nexus_releases import main_window
    add_windows(repo)
    monkeypatch.setattr(main_window, "LOG_DIR", tmp_path / "logs")
    started = []
    window.start = lambda command, env, cwd, log: started.append((command, cwd, log)) or FakeProcess()
    window.reload()
    page = window.run_page
    items = {page.apps.item(i).data(0x0100).module: page.apps.item(i) for i in range(page.apps.count())}
    assert sorted(items) == ["alpha", "beta", "tool"] and "Changes how the board runs" in items["beta"].toolTip()
    assert "Changes how the board runs" not in items["alpha"].toolTip()
    assert "\n" not in items["beta"].text()                         # the warning is on the icon, not in the label

    from PyQt6.QtGui import QColor

    def corner(item) -> str:                                        # the badge's orange, low right on the icon
        image = item.icon().pixmap(main_window.ICON_PX, main_window.ICON_PX).toImage()
        edge = main_window.ICON_PX - main_window.BADGE_PX // 2
        return QColor(image.pixel(edge - 6, edge)).name()

    assert corner(items["beta"]) == QColor(main_window.ORANGE).name() != corner(items["alpha"])
    page.apps.itemClicked.emit(items["alpha"])
    assert started == [([sys.executable, "-m", "alpha"], repo / "apps/alpha", tmp_path / "logs/alpha.log")]
    with mock_question(QMessageBox.StandardButton.No) as asked:
        page.apps.itemClicked.emit(items["beta"])                              # a board app asks first
    assert asked.called and len(started) == 1
    with mock_question(QMessageBox.StandardButton.Yes):
        page.apps.itemClicked.emit(items["beta"])
    assert len(started) == 2 and page.timer.isActive()
    # alpha stops with an error: the end of its log shows; beta closes normally
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs/alpha.log").write_text("Traceback (most recent call last):\nImportError: no module x\n")
    page.running[0][1].code, page.running[1][1].code = 1, 0
    page.poll()
    out = page.output.toPlainText()
    assert "Alpha App 0.1.0 stopped with exit code 1" in out and "ImportError: no module x" in out
    assert "beta 0.1.0 closed." in out and not page.running and not page.timer.isActive()


def mock_question(answer):
    from unittest import mock
    from PyQt6.QtWidgets import QMessageBox
    return mock.patch.object(QMessageBox, "question", return_value=answer)


def test_start_app_keeps_the_output_in_a_log(tmp_path):
    from nexus_releases import main_window
    log = tmp_path / "logs" / "x.log"
    process = main_window.start_app([sys.executable, "-c", "print('hello'); raise SystemExit(3)"], dict(os.environ),
                                    tmp_path, log)
    assert process.wait(30) == 3
    assert main_window.log_tail(log) == "hello"


# --- GitHub builds ----------------------------------------------------------------------------------------------

def run(workflow="CI", ref="main", status="completed", conclusion="success", n=1, sha="abc1234def"):
    return {"name": workflow, "head_branch": ref, "status": status, "conclusion": conclusion if status == "completed"
            else None, "html_url": f"https://github.invalid/runs/{n}", "head_sha": sha, "display_title": "Fix it"}


def test_build_state_of_the_latest_push():
    runs = rp.parse_runs({"workflow_runs": [run(n=3), run("Release", "governor-v0.1.1", "in_progress", n=2),
                                            run(n=1, sha="older", conclusion="failure")]})
    latest = rp.latest_push(runs)
    assert [r.url[-1] for r in latest] == ["3", "2"]                          # not the older commit
    assert rp.build_state(latest) == "running" and latest[1].outcome == "in progress"
    done = [replace(latest[1], status="completed", conclusion="failure")]
    assert rp.build_state([latest[0], *done]) == "failed" and done[0].outcome == "failure"
    assert rp.build_state([latest[0], replace(latest[1], status="completed", conclusion="skipped")]) == "passed"
    assert rp.build_state([]) == "" and rp.parse_runs({"message": "rate limit"}) == []
    before = {r.url: r for r in runs}
    assert rp.just_finished(before, [latest[0], *done]) == done              # only what was seen running
    assert rp.just_finished({}, done) == []                                   # finished before the first look


def job(name, status="completed", conclusion="success", steps=(), n=1):
    return {"name": name, "status": status, "conclusion": conclusion if status == "completed" else None,
            "html_url": f"https://github.invalid/jobs/{n}",
            "steps": [{"name": s, "status": st, "conclusion": c} for s, st, c in steps]}


def test_jobs_and_the_step_each_is_at():
    jobs = rp.parse_jobs({"jobs": [
        job("lint"),
        job("pytest (core)", "in_progress", steps=[("Set up", "completed", "success"),
                                                   ("Run tests", "in_progress", None), ("Post", "queued", None)], n=2),
        job("pytest (tools)", conclusion="failure", steps=[("Set up", "completed", "success"),
                                                           ("Run tests", "completed", "failure"),
                                                           ("Post", "completed", "skipped")], n=3),
        job("build", "in_progress", steps=[("Set up", "completed", "success"), ("Build", "queued", None)], n=4),
        "not a job"]})
    assert [(j.name, j.step, j.step_number, j.steps) for j in jobs] == [
        ("lint", "", 0, 0), ("pytest (core)", "Run tests", 2, 3), ("pytest (tools)", "Run tests", 2, 3),
        ("build", "Build", 2, 2)]                                             # between two steps: the next one
    assert jobs[2].outcome == "failure" and jobs[1].outcome == "in progress" and jobs[0].passed
    assert rp.parse_jobs({"message": "Not Found"}) == []
    data = run(status="in_progress", n=7)
    data.update(jobs_url="https://api.github.invalid/runs/7/jobs", run_started_at="2026-10-28T09:00:00Z")
    ci, nexus = rp.parse_runs({"workflow_runs": [data, run("Nexus CI", n=8)]})
    assert ci.jobs_url.endswith("/runs/7/jobs") and nexus.jobs_url == "" and nexus.started == 0.0
    now = ci.started + 134
    by_url = {ci.url: jobs}
    assert rp.run_line(ci, jobs, now) == ("CI on main: 2 of 4 jobs done · 1 failed · pytest (core): Run tests (2/3) "
                                          "· build: Build (2/2) · 2:14")
    assert rp.run_line(ci, None, now) == "CI on main: in progress · 2:14"     # its jobs not read: the run only
    assert rp.ticker_line([nexus, ci], by_url, now).startswith("CI on main")  # the running one first
    assert rp.ticker_line([nexus, ci], by_url, now).endswith("   |   Nexus CI on main: passed")
    failed = replace(ci, status="completed", conclusion="failure")
    assert rp.run_line(failed, jobs, now) == "CI on main: failure in pytest (tools), step Run tests"
    assert rp.run_line(failed, None, now) == "CI on main: failure"
    assert rp.ticker_target([nexus, ci], by_url) == "https://github.invalid/jobs/2"     # the job that runs
    assert rp.ticker_target([nexus, failed], {failed.url: jobs[:1] + jobs[2:3]}) == "https://github.invalid/jobs/3"
    assert rp.ticker_target([nexus, failed], {}) == failed.url and rp.ticker_target([nexus], {}) == nexus.url
    assert rp.ticker_target([], {}) == ""
    details = rp.ticker_details([nexus, ci], by_url, now)
    assert details.startswith("abc1234 Fix it\n\nCI on main: in progress, 2:14\n    lint: passed\n")
    assert "    pytest (core): in progress, step 2 of 3: Run tests" in details
    assert "    pytest (tools): failure, step 2 of 3: Run tests" in details and details.endswith("Nexus CI on main: passed")
    assert rp.elapsed(3723) == "1:02:03" and rp.elapsed(-5) == "0:00" and rp.epoch(None) == 0.0


def test_window_ticker_shows_the_jobs_of_the_runs(repo, tmp_path):
    pytest.importorskip("PyQt6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    app = QApplication.instance() or QApplication([])          # noqa: F841 (kept alive for the window)
    from nexus_releases import main_window
    asked = []

    def jobs_source(url, etag):
        asked.append((url, etag))
        return (rp.parse_jobs({"jobs": [job("pytest (core)", "in_progress",
                                            steps=[("Run tests", "in_progress", None)])]}), "j1", None)

    w = main_window.ReleaseWindow(repo, status_source=None, sha256_source=lambda tag: SHA, launch=launched.append,
                                  runs_source=lambda etag: (None, etag), notify=lambda *a: None, claude_source=None,
                                  jobs_source=jobs_source)
    ticker = w.ticker
    assert ticker.isHidden()                                                   # no runs seen yet
    going = run(status="in_progress", n=2)
    going["jobs_url"] = "https://api.github.invalid/runs/2/jobs"
    w.build.checked((rp.parse_runs({"workflow_runs": [going, run(n=1)]}), "e1"))
    assert not ticker.isHidden() and asked == []                               # not signed in: the runs only
    assert ticker.line == "CI on main: in progress   |   CI on main: passed"
    assert "gh auth login" in ticker.toolTip() and ticker.clock.isActive()
    assert main_window.BLUE in ticker.dot.styleSheet()
    w.build.checked((None, "e1", rp.RateInfo(5000, 4900, 1_900_000_000, signed_in=True)))
    ticker.checker.stop(5000)                                                  # the worker: run it here instead
    ticker.fetched(ticker._fetch([(r.url, r.jobs_url, "", r.done) for r in ticker.wanted()]))
    assert asked[-1] == ("https://api.github.invalid/runs/2/jobs", "")
    assert ticker.line.startswith("CI on main: 0 of 1 jobs done · pytest (core): Run tests (1/1)")
    assert ticker.etags == {going["html_url"]: "j1"} and ticker.timer.isActive()
    assert ticker.target() == "https://github.invalid/jobs/1" and "gh auth login" not in ticker.toolTip()
    done = dict(going, status="completed", conclusion="success")
    w.build.checked((rp.parse_runs({"workflow_runs": [done, run(n=1)]}), "e2"))
    ticker.checker.stop(5000)
    assert ticker.wanted() == [] and not ticker.clock.isActive()               # all passed: nothing more to read
    assert ticker.line == "CI on main: passed   |   CI on main: passed" and main_window.GREEN in ticker.dot.styleSheet()
    w.close()
    assert not ticker.timer.isActive()


def test_release_runs_of_the_tags_waited_for():
    runs = rp.parse_runs({"workflow_runs": [run("Release", "alpha-v0.1.1", "in_progress", n=4),
                                            run("Release", "alpha-v0.1.1", conclusion="failure", n=3),
                                            run("Release", "beta-v0.1.0", n=2), run(n=1)]})
    assert rp.release_run(runs, "alpha-v0.1.1").url.endswith("/4")           # the newest run on the tag
    assert rp.release_run(runs, "gamma-v0.1.0") is None
    assert rp.release_state(runs, "alpha-v0.1.1") == "running"
    assert rp.release_state(runs, "beta-v0.1.0") == "passed" and rp.release_state(runs, "gamma-v0.1.0") == ""
    announced: set[str] = set()
    ready = rp.finished_releases(announced, runs, ["alpha-v0.1.1", "beta-v0.1.0", "gamma-v0.1.0"])
    assert [r.ref for r in ready] == ["beta-v0.1.0"]                           # finished, whenever that was
    announced.update(r.url for r in ready)
    assert rp.finished_releases(announced, runs, ["beta-v0.1.0"]) == []        # told once
    assert rp.finished_releases(announced, runs, []) == []


def test_a_suites_own_release_workflow_counts_too():
    # The Windows Portable Suite's release-windows-portable.yml, "Release Windows Portable" (owner, 28-10-2026: its
    # GitHub column said no run seen while it had built wp-test-v1.1.1).
    named = {**run("Release Windows Portable", "wp-test-v1.1.1", n=2),
             "path": ".github/workflows/release-windows-portable.yml"}
    unnamed = run("Release Windows Portable", "wp-portal-v1.0.2", "in_progress", n=1)
    ci = {**run("CI Windows Portable", "wp-test-v1.1.1", n=3), "path": ".github/workflows/ci-windows-portable.yml"}
    runs = rp.parse_runs({"workflow_runs": [ci, named, unnamed]})
    assert rp.release_run(runs, "wp-test-v1.1.1").url.endswith("/2")        # not the CI run on the tag
    assert rp.release_state(runs, "wp-test-v1.1.1") == "passed"
    assert rp.release_state(runs, "wp-portal-v1.0.2") == "running"


def test_fetch_runs_sends_the_etag(monkeypatch):
    import io
    import urllib.error
    sent = []

    rate = {"X-RateLimit-Limit": "60", "X-RateLimit-Remaining": "57", "X-RateLimit-Reset": "1900000000"}

    class Response(io.BytesIO):
        headers = {"ETag": 'W/"new"', **rate}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout):
        sent.append(request.get_header("If-none-match"))
        if sent[-1] == 'W/"new"':
            headers = dict(rate, **{"X-RateLimit-Remaining": "56"})
            raise urllib.error.HTTPError(request.full_url, 304, "Not Modified", headers, None)
        return Response(json.dumps({"workflow_runs": [run()]}).encode())

    monkeypatch.setattr(rp.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(rp, "_token", "")                                      # no login: never the real gh
    runs, etag, limit = rp.fetch_runs()
    assert [r.label for r in runs] == ["CI on main"] and etag == 'W/"new"' and sent == [None]
    assert limit == rp.RateInfo(60, 57, 1_900_000_000, signed_in=False)
    unchanged = rp.fetch_runs(etag)                                           # unchanged: 304, the limit still read
    assert unchanged[:2] == (None, 'W/"new"') and unchanged[2].remaining == 56
    assert "57 of 60 left until" in limit.text and limit.text.endswith("not signed in")
    assert rp.RateInfo.from_headers({}, False) is None


def test_github_token_from_the_environment_or_a_gh_login(monkeypatch):
    monkeypatch.setattr(rp, "_token", None)
    monkeypatch.setenv("GH_TOKEN", "from-env")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert rp.github_token(run=lambda *a, **k: pytest.fail("gh asked although a token was set")) == "from-env"
    monkeypatch.setattr(rp, "_token", None)
    monkeypatch.delenv("GH_TOKEN")
    monkeypatch.setattr(rp.shutil, "which", lambda name: "/usr/bin/gh")
    asked = []

    def gh(argv, **kw):
        asked.append(argv)
        return subprocess.CompletedProcess(argv, 0, "gho_login\n", "")
    assert rp.github_token(run=gh) == "gho_login" and asked == [["/usr/bin/gh", "auth", "token"]]
    assert rp.github_token(run=gh) == "gho_login" and len(asked) == 1         # asked once per run
    monkeypatch.setattr(rp, "_token", None)
    assert rp.github_token(run=lambda argv, **kw: subprocess.CompletedProcess(argv, 1, "", "not logged in")) == ""


def test_token_warning():
    assert rp.token_warning("") == rp.token_warning("github_pat_abc") == ""
    assert "every repository" in rp.token_warning("gho_abc") and "every repository" in rp.token_warning("ghp_abc")


def test_github_token_asked_once_while_checks_overlap(monkeypatch):
    import threading
    import time
    monkeypatch.setattr(rp, "_token", None)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(rp.shutil, "which", lambda name: "/usr/bin/gh")
    asked = []

    def slow_gh(argv, **kw):
        asked.append(argv)
        time.sleep(0.3)                                                       # gh still answering ...
        return subprocess.CompletedProcess(argv, 0, "gho_login\n", "")
    got = []
    first = threading.Thread(target=lambda: got.append(rp.github_token(run=slow_gh)))
    first.start()
    time.sleep(0.05)
    got.append(rp.github_token(run=slow_gh))                                  # ... when a second check asks
    first.join()
    assert got == ["gho_login", "gho_login"] and len(asked) == 1


def test_fetch_runs_signs_in_and_reports_the_limit(monkeypatch):
    import urllib.error
    from email.message import Message
    sent = []

    def limited(reset):
        headers = Message()
        headers["X-RateLimit-Remaining"] = "0"
        headers["X-RateLimit-Reset"] = str(reset)
        return headers

    def urlopen(request, timeout):
        sent.append(request.get_header("Authorization"))
        if sent[-1] == "Bearer expired":
            raise urllib.error.HTTPError(request.full_url, 401, "Bad credentials", Message(), None)
        raise urllib.error.HTTPError(request.full_url, 403, "rate limit exceeded", limited(1_900_000_000), None)

    monkeypatch.setattr(rp.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(rp, "_token", "expired")
    with pytest.raises(rp.RateLimited) as caught:
        rp.fetch_runs()
    assert sent == ["Bearer expired", None]                                   # a refused login: on without it
    assert caught.value.reset == 1_900_000_000 and not caught.value.signed_in and rp._token == ""
    monkeypatch.setattr(rp, "_token", "gho_login")
    with pytest.raises(rp.RateLimited) as caught:
        rp.fetch_runs()
    assert sent[-1] == "Bearer gho_login" and caught.value.signed_in


def test_window_build_indicator_notifies_when_a_run_ends(repo, tmp_path):
    pytest.importorskip("PyQt6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    app = QApplication.instance() or QApplication([])          # noqa: F841 (kept alive for the window)
    from nexus_releases import main_window
    notes = []
    w = main_window.ReleaseWindow(repo, status_source=None, sha256_source=lambda tag: SHA, launch=launched.append,
                                  runs_source=lambda etag: (None, etag), notify=lambda *a: notes.append(a))
    build = w.build
    assert not build.isHidden()
    build.checked((rp.parse_runs({"workflow_runs": [run(n=2), run("Release", "governor-v0.1.1", "in_progress")]}),
                   "e1"))
    assert build.state == "running" and build.value.text() == "Building" and notes == []
    assert build.caption.text() == "GitHub build" and main_window.BLUE in build.styleSheet()
    assert build.timer.interval() == main_window.BUILD_BUSY_MS
    assert build.target() == "https://github.invalid/runs/1"                  # the run still going
    assert "Release on governor-v0.1.1: in progress" in build.toolTip()
    build.checked((None, "e1"))                                               # unchanged
    assert build.state == "running" and notes == []
    build.checked((rp.parse_runs({"workflow_runs": [run(n=2), run("Release", "governor-v0.1.1",
                                                                  conclusion="failure")]}), "e2"))
    assert build.state == "failed" and build.value.text() == "Failed" and main_window.RED in build.styleSheet()
    assert notes == [("GitHub build failed", "Release on governor-v0.1.1: failure")]
    assert build.target() == "https://github.invalid/runs/1" and build.timer.interval() == main_window.BUILD_IDLE_MS
    assert build.rate.value.text() == "—" and "not known yet" in build.rate.toolTip()
    build.checked((None, "e2", rp.RateInfo(5000, 4905, 1_900_000_000, signed_in=True)))
    assert build.rate.value.text() == "4,905" and "4,905 of 5,000 left" in build.rate.toolTip()
    assert "signed in" in build.rate.toolTip() and "gh auth login" not in build.rate.toolTip()
    assert main_window.ORANGE not in build.rate.styleSheet() and main_window.RED not in build.rate.styleSheet()
    assert main_window.GREEN in build.rate.styleSheet()                    # a left edge while plenty are left
    build.checked((None, "e2", rp.RateInfo(60, 3, 1_900_000_000, signed_in=False)))
    assert main_window.ORANGE in build.rate.styleSheet() and "gh auth login" in build.rate.toolTip()
    build.checked(OSError("offline"))
    assert build.state == "unreachable" and "offline" in build.toolTip()
    import time
    build.checked(rp.RateLimited(time.time() + 1800, signed_in=False))
    assert build.state == "limited" and build.value.text() == "Limited" and "back at" in build.toolTip()
    assert "gh auth login" in build.toolTip()
    assert "0 of 60 left" in build.rate.toolTip() and main_window.RED in build.rate.styleSheet()
    assert build.timer.interval() >= 1800_000                                 # waits for the reset
    build.checked(rp.RateLimited(time.time() + 60, signed_in=True))
    assert "gh auth login" not in build.toolTip() and build.timer.interval() == main_window.BUILD_IDLE_MS
    w.close()
    assert main_window.ReleaseWindow(repo, status_source=None, runs_source=None).build.isHidden()


def test_window_tells_when_a_release_is_ready_to_pin(repo, tmp_path):
    pytest.importorskip("PyQt6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    app = QApplication.instance() or QApplication([])          # noqa: F841 (kept alive for the window)
    from nexus_releases import main_window
    notes, asked = [], []

    def sha256(tag):
        asked.append(tag)
        return SHA

    w = main_window.ReleaseWindow(repo, status_source=None, sha256_source=sha256, launch=launched.append,
                                  runs_source=lambda etag: (None, etag), notify=lambda *a: notes.append(a))
    w.portal_page.base_edit.setText("pushed")
    page, build = w.portal_page, w.build
    assert page.waiting_tags() == ["alpha-v0.1.0"]                            # tagged, no checksum yet
    assert page.pins.horizontalHeaderItem(3).text() == "GitHub" and page.pins.item(0, 3).text() == "no run seen"
    assert "portal-v0.1.0 is not tagged yet" in page.portal_state.text()      # bumped and committed, no tag
    assert f"{rp.TAG_SCRIPT} portal-v0.1.0" in page.portal_state.text()
    # The release workflow runs: Pin waits for it instead of failing on the checksum that is not there yet.
    build.checked((rp.parse_runs({"workflow_runs": [run(n=2), run("Release", "alpha-v0.1.0", "in_progress")]}),
                   "e1"))
    assert page.pins.item(0, 3).text() == "building\u2026" and notes == []
    page.pin()
    assert asked == [] and "still building" in page.output.toPlainText()
    assert 'tag = "alpha-v0.1.0"\nsha256 = ""' in (repo / "portal/apps.toml").read_text()
    build.checked((None, "e1"))                                               # unchanged: nothing new
    assert notes == []
    # It finishes: one notification that the release is ready to pin, not the general "build passed" one.
    build.checked((rp.parse_runs({"workflow_runs": [run(n=2), run("Release", "alpha-v0.1.0")]}), "e2"))
    assert notes == [("alpha-v0.1.0 is ready to pin", "GitHub published it. Pin reads its checksum (step 2).")]
    assert page.pins.item(0, 3).text() == "ready" and build.state == "passed"
    build.checked((rp.parse_runs({"workflow_runs": [run(n=2), run("Release", "alpha-v0.1.0")]}), "e3"))
    assert len(notes) == 1                                                    # told once
    page.pin()
    assert asked == ["alpha-v0.1.0"] and page.waiting_tags() == []
    # The portal's tag exists: its release is followed too, and announced when it is built.
    sh(repo, "tag", "portal-v0.1.0")
    w.reload()
    assert "GitHub shows no release run" in page.portal_state.text()
    build.checked((rp.parse_runs({"workflow_runs": [run("Release", "portal-v0.1.0", "in_progress", n=3),
                                                    run(n=2)]}), "e4"))
    assert "building its release" in page.portal_state.text()
    assert main_window.ORANGE in page.portal_state.styleSheet()                # the warning color, as the others
    build.checked((rp.parse_runs({"workflow_runs": [run("Release", "portal-v0.1.0", n=3), run(n=2)]}), "e5"))
    assert notes[-1] == ("portal-v0.1.0 is ready", "GitHub published it. Test Portal release installs it on this board "
                                                   "(step 2).")
    assert "portal-v0.1.0 is released" in page.portal_state.text()
    w.close()
    # Finished before the first look (the window opened after GitHub was done): still told, and a failed release
    # is told too, with Pin saying so.
    notes.clear()
    rp.pin(repo, unit(repo, "alpha"), "")
    w = main_window.ReleaseWindow(repo, status_source=None, sha256_source=sha256, launch=launched.append,
                                  runs_source=lambda etag: (None, etag), notify=lambda *a: notes.append(a))
    w.build.checked((rp.parse_runs({"workflow_runs": [run("Release", "alpha-v0.1.0", n=5)]}), "f1"))
    assert [n[0] for n in notes] == ["alpha-v0.1.0 is ready to pin"]
    w.build.checked((rp.parse_runs({"workflow_runs": [run("Release", "alpha-v0.1.0", conclusion="failure", n=6)]}),
                     "f2"))
    assert notes[-1][0] == "alpha-v0.1.0: release failed" and "failure" in notes[-1][1]
    assert w.portal_page.pins.item(0, 3).text() == "failed"
    asked.clear()
    w.portal_page.pin()
    assert asked == [] and "nothing to pin" in w.portal_page.output.toPlainText()
    w.close()


def test_title_names_the_checkouts_commit_and_date(window, repo, tmp_path):
    from PyQt6.QtWidgets import QLabel
    from nexus_releases import __version__
    head = subprocess.run(["git", "log", "-1", "--format=%h %ct"], cwd=repo, capture_output=True, text=True).stdout.split()
    when = rp.amsterdam_now(datetime.datetime.fromtimestamp(int(head[1]), datetime.timezone.utc))
    stamp = f"{head[0]} · {when:%d-%m-%Y %H:%M}"
    assert rp.checkout_stamp(repo) == stamp
    assert any(f"v{__version__} · {stamp}" in label.text() for label in window.findChildren(QLabel))
    elsewhere = tmp_path / "not-a-checkout"
    elsewhere.mkdir()
    assert rp.checkout_stamp(elsewhere) == ""


def test_window_withdraws(window, repo, monkeypatch):
    page = window.withdraw_page
    assert [page.app_box.itemText(i) for i in range(page.app_box.count())] == ["beta-v0.1.0"]
    assert page.state.text() == "Not withdrawn." and not page.back_button.isEnabled()
    warned = []
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    page.withdraw_button.click()                                    # no reason: refused
    assert warned and rp.withdrawn_reason(repo, "beta") == ""
    page.reason_edit.setText("Security: a key in the log.")
    page.withdraw_button.click()
    assert rp.withdrawn_reason(repo, "beta") == "Security: a key in the log."
    assert page.state.text() == "Withdrawn: Security: a key in the log." and page.back_button.isEnabled()
    assert "gh release edit beta-v0.1.0 --prerelease" in page.output.toPlainText()
    page.back_button.click()
    assert rp.withdrawn_reason(repo, "beta") == "" and page.state.text() == "Not withdrawn."


# --- Semantic versioning from the CHANGELOG entries -------------------------------------------------------------

def entry(path: Path, body: str, stamp: str = "15-10-2026 23:00:00") -> None:
    path.write_bytes(f"Changelog: {stamp}\n\n{body}\n\n".encode() + path.read_bytes())


def test_the_kind_of_change_sets_the_level():
    assert rp.suggested_level([]) == ("patch", "no CHANGELOG entries")
    assert rp.suggested_level(["Fixed. A crash.", "Added. A button."]) == ("minor", "1 Added, 1 Fixed")
    assert rp.suggested_level(["Breaking. The --old option went.", "Added. x"])[0] == "major"
    level, why = rp.suggested_level(["A change from before the rule.", "Fixed. y"])
    assert level == "patch" and "1 without Breaking./Added./Fixed. (counted as a fix)" in why
    assert rp.change_word("Added.") == "Added." and rp.change_word("Addedx. no") == ""


def test_an_added_entry_since_the_tag_asks_for_a_minor_release(repo):
    alpha = repo / "apps/alpha/CHANGELOG"
    entry(alpha, "Fixed. The window opens on the right screen.")
    assert rp.version_choices(repo, unit(repo, "alpha"))[0][:3] == ["0.1.1", "0.2.0", "1.0.0"]
    entry(alpha, "Added. A Check before push button.")
    entry(alpha, "Release 0.1.1.")                              # the tool's own entries count for nothing
    choices, why = rp.version_choices(repo, unit(repo, "alpha"))
    assert choices[0] == "0.2.0" and why == "minor: 1 Added, 1 Fixed since alpha-v0.1.0"
    entry(alpha, "Breaking. Its settings from 0.1 are not read any more.")
    assert rp.version_choices(repo, unit(repo, "alpha"))[0][0] == "1.0.0"


def test_counted_from_the_last_tag_not_a_bump_already_made(repo):
    """VERSION bumped to 0.1.1 (not tagged) and then a feature: 0.2.0 from alpha-v0.1.0 comes first. A VERSION bumped
    further already comes first itself."""
    alpha = unit(repo, "alpha")
    rp.set_version(repo, alpha, "0.1.1")
    entry(repo / "apps/alpha/CHANGELOG", "Added. x")
    assert rp.version_choices(repo, unit(repo, "alpha"))[0][:2] == ["0.2.0", "0.1.1"]
    rp.set_version(repo, unit(repo, "alpha"), "0.3.0")
    assert rp.version_choices(repo, unit(repo, "alpha"))[0][0] == "0.3.0"


def test_a_core_change_counts_for_the_apps_that_carry_it(repo):
    entry(repo / "core/CHANGELOG", "Added. A widget.")
    write(repo / "core/bc250_core/widgets.py", "x = 1\n")
    assert rp.version_choices(repo, unit(repo, "alpha"))[0][0] == "0.2.0"     # alpha bundles core
    core = unit(repo, "core")
    assert rp.version_choices(repo, core)[0][0] == "0.2.0"


def test_a_first_release_is_offered_as_it_is(repo):
    choices, why = rp.version_choices(repo, unit(repo, "beta"))
    assert choices[0] == "0.1.0" and why == "the first release"
    entry(repo / "portal/CHANGELOG", "Added. The first portal.")          # a portal never tagged: the same
    assert rp.portal_suggestion(repo, unit(repo, "portal")) == (unit(repo, "portal").version, "the first release")


def test_the_portal_counts_apps_toml_since_its_last_tag(repo):
    """An app added to apps.toml and pushed before the portal release: the minimum (as check_manifest) and the
    suggestion both count it against the last portal tag, not the last push."""
    sh(repo, "tag", "portal-v0.1.0")
    write(repo / "portal/apps.toml", (repo / "portal/apps.toml").read_text() + card("gamma"))
    sh(repo, "commit", "-qam", "gamma")
    sh(repo, "branch", "-f", "pushed")
    assert rp.portal_minimum(repo, "pushed", "0.1.0") == ("0.2.0", "gamma was added")
    assert rp.portal_suggestion(repo, unit(repo, "portal")) == (
        "0.2.0", "minor: apps.toml changed since portal-v0.1.0 (gamma was added)")
    entry(repo / "portal/CHANGELOG", "Breaking. Reads only apps.toml format 2.")
    assert rp.portal_suggestion(repo, unit(repo, "portal"))[0] == "1.0.0"


def test_open_issues_without_pull_requests():
    """GitHub's issues list holds the pull requests too: Close issues shows the issues only."""
    data = [{"number": 12, "title": "Upstream review", "html_url": "https://github.com/o/r/issues/12",
             "updated_at": "2026-10-20T06:01:02Z"},
            {"number": 13, "title": "A pull request", "pull_request": {}, "html_url": "", "updated_at": ""},
            "not an issue"]
    assert rp.parse_issues(data) == [rp.Issue(12, "Upstream review", "https://github.com/o/r/issues/12", "2026-10-20")]
    assert rp.parse_issues(data)[0].label == "#12 Upstream review (updated 2026-10-20)"
    assert rp.parse_issues({"message": "Not Found"}) == []


def test_close_issues_command():
    repo = rp.repo_slug()
    assert rp.close_issues_command([12]) == f"gh issue close 12 --repo {repo}"
    assert rp.close_issues_command([12, 14], " Decky pinned at v3.3.0, it's in step ") == (
        f"gh issue close 12 --repo {repo} --comment 'Decky pinned at v3.3.0, it'\"'\"'s in step' && "
        f"gh issue close 14 --repo {repo} --comment 'Decky pinned at v3.3.0, it'\"'\"'s in step'")


def test_the_root_copy_of_apps_toml_follows_the_suites(repo, tmp_path):
    """Nexus keeps a copy of apps.toml at the root for the portals installed before the suite moved into
    bc250-bazzite/ (check_manifest.py wants it identical; the owner's portal-v10.0.0 commit stopped on it,
    26-10-2026): every write of the suite's apps.toml, a pin, a moved unreleased pin or a withdrawal, writes the
    copy too, as long as there is one. A checkout laid out as a suite (the fixture) has no copy."""
    assert rp.manifest_copy(repo) is None
    nexus = nexus_layout(repo, tmp_path)
    suite_toml, copy = nexus / SUITE_DIR / "portal/apps.toml", nexus / "portal/apps.toml"
    assert rp.manifest_path(nexus) == suite_toml and rp.manifest_copy(nexus) is None
    copy.parent.mkdir()
    shutil.copy(suite_toml, copy)
    assert rp.manifest_copy(nexus) == copy
    alpha = unit(nexus, "alpha")
    rp.pin(nexus, alpha, SHA)
    assert f'sha256 = "{SHA}"' in suite_toml.read_text() and suite_toml.read_bytes() == copy.read_bytes()
    beta = unit(nexus, "beta")
    rp.set_version(nexus, beta, "0.2.0")
    assert rp.follow_unreleased_pin(nexus, beta)
    assert 'tag = "beta-v0.2.0"' in copy.read_text() and suite_toml.read_bytes() == copy.read_bytes()
    changed = rp.withdraw(nexus, unit(nexus, "beta"), "Broken.")
    assert [p.relative_to(nexus).as_posix() for p in changed] == [
        f"{SUITE_DIR}/portal/apps.toml", "portal/apps.toml", f"{SUITE_DIR}/apps/beta/CHANGELOG"]
    assert 'withdrawn = "Broken."' in copy.read_text() and suite_toml.read_bytes() == copy.read_bytes()
    copy.unlink()                                             # the owner removed the copy: the suite's alone
    rp.withdraw(nexus, unit(nexus, "beta"), "")
    assert "withdrawn" not in suite_toml.read_text() and not copy.exists()


def nexus_layout(repo: Path, tmp_path: Path, *names: str) -> Path:
    """The fixture's repository laid out as Nexus is: core and .git at the root, the suite (and a copy of it under
    each of *names*) in a folder of its own."""
    nexus = tmp_path / "nexus"
    for name in (SUITE_DIR, *names):
        shutil.copytree(repo, nexus / name)
        if name == SUITE_DIR:
            shutil.move(nexus / name / ".git", nexus / ".git")
            shutil.move(nexus / name / "core", nexus / "core")
        else:
            for file in (nexus / name / ".git").rglob("*"):     # git's objects are read-only: Windows refuses
                if file.is_file():                                # to remove them
                    file.chmod(0o600)
            shutil.rmtree(nexus / name / ".git")
            shutil.rmtree(nexus / name / "core")
    sh(nexus, "add", "-A")
    sh(nexus, "commit", "-q", "-m", "move")
    return nexus


def test_the_suites_of_a_checkout(repo, tmp_path):
    """Every folder with portal/apps.toml is a suite (tools/suites.py); the per-suite functions take one by name
    and default to the first. The fixture, laid out as a suite itself, is its own one suite."""
    assert rp.suites(repo) == [] and rp.suite_dir(repo) == repo
    assert rp.check_script(repo) == rp.CHECK_SCRIPT == "tools/check-release.sh"
    assert rp.manifest_checks(repo) == [rp.MANIFEST_CHECK] == ["tools/check_manifest.py"]
    nexus = nexus_layout(repo, tmp_path, "zz-suite")
    assert rp.suites(nexus) == [SUITE_DIR, "zz-suite"]
    assert rp.suite_dir(nexus) == nexus / SUITE_DIR and rp.suite_dir(nexus, "zz-suite") == nexus / "zz-suite"
    assert rp.check_script(nexus) == f"{SUITE_DIR}/tools/check-release.sh"
    assert rp.record_script(nexus, "zz-suite") == "zz-suite/tools/record-tour.sh"
    assert rp.manifest_checks(nexus) == [f"{SUITE_DIR}/tools/check_manifest.py", "zz-suite/tools/check_manifest.py"]
    # The commit checks the suites it changes alone (owner, 28-10-2026: one suite's checks never hold another's).
    assert rp.touched_suites(repo, ["apps/alpha/x.py"]) is None                  # no suite folders: every check
    assert rp.touched_suites(nexus, [f"{SUITE_DIR}/apps/alpha/x.py", "core/x.py"]) == [SUITE_DIR]
    assert rp.touched_suites(nexus, ["core/x.py", "tools/x.py"]) == []
    assert rp.manifest_checks(nexus, ["zz-suite"]) == ["zz-suite/tools/check_manifest.py"]
    assert rp.version_checks(None) == [rp.VERSIONS_CHECK] and rp.version_checks([]) == [f"{rp.VERSIONS_CHECK} --nexus"]
    assert rp.version_checks(["zz-suite"]) == [f"{rp.VERSIONS_CHECK} --suite zz-suite"]
    command = rp.commit_command("m", "pushed", manifests=rp.manifest_checks(nexus, ["zz-suite"]),
                                versions=rp.version_checks(["zz-suite"]))
    assert command == ("python3 tools/check_versions.py --suite zz-suite && python3 zz-suite/tools/check_manifest.py "
                       "--base pushed && git commit -m m")
    write(nexus / "zz-suite/apps/alpha/new.txt", "x")
    sh(nexus, "add", "zz-suite/apps/alpha/new.txt")
    assert rp.staged_suites(nexus) == ["zz-suite"]
    assert rp.manifest_path(nexus, "zz-suite") == nexus / "zz-suite/portal/apps.toml"
    first, second = rp.load_units(nexus), rp.load_units(nexus, "zz-suite")
    assert [u.path for u in first][:3] == ["core", f"{SUITE_DIR}/portal", f"{SUITE_DIR}/apps/alpha"]
    assert [u.path for u in second][:3] == ["core", "zz-suite/portal", "zz-suite/apps/alpha"]
    write(nexus / "zz-suite/apps/alpha/alpha/__main__.py", "")
    assert [t.folder for t in rp.launch_targets(nexus, "zz-suite")] == [nexus / "zz-suite/apps/alpha"]
    (nexus / "portal").mkdir()
    shutil.copy(nexus / SUITE_DIR / "portal/apps.toml", nexus / "portal/apps.toml")
    assert rp.manifest_copy(nexus) == nexus / "portal/apps.toml"      # the root's copy is the first suite's
    assert rp.manifest_copy(nexus, "zz-suite") is None
    assert rp.wiki_icon(nexus / "zz-suite") is None
    write(nexus / "zz-suite/portal/images/zz-suite-suite.webp", "webp")
    assert rp.wiki_icon(nexus / "zz-suite") == nexus / "zz-suite/portal/images/zz-suite-suite.webp"
    write(nexus / "nexus/images/nexus-256.png", "png")
    assert rp.wiki_icon(nexus / "nexus") == nexus / "nexus/images/nexus-256.png"


def test_window_suite_column(repo, tmp_path):
    """The first column lists the suites of the checkout (owner, 27-10-2026: in place of the header's chooser), each
    by its portal's name with the tag of its version, and is hidden while there is one. Exactly one is ticked: the
    steps follow it, a click on another row moves the tick there, and the choice is remembered. The git buttons run
    every suite's manifest check."""
    pytest.importorskip("PyQt6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QSettings, Qt
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])          # noqa: F841 (kept alive for the window)
    from nexus_releases import main_window
    one = main_window.ReleaseWindow(repo, status_source=None, runs_source=None, claude_source=None)
    assert one.suite is None and one.suite_list.isHidden() and "· suite" not in one.footer.text()
    one.close()
    nexus = nexus_layout(repo, tmp_path, "zz-suite")
    write(nexus / "zz-suite/portal/bc250_portal/__init__.py", 'APP_NAME = "Zed Suite"\n__version__ = "0.1.0"\n')
    write(nexus / "zz-suite/TAG_PREFIX", "zz-\n")
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    w = main_window.ReleaseWindow(nexus, status_source=None, runs_source=None, claude_source=None, settings=settings)
    column = w.suite_list
    assert w.suite == SUITE_DIR and not column.isHidden() and column.current() == SUITE_DIR
    rows = [column.item(i) for i in range(column.count())]
    assert [r.text() for r in rows] == [f"{SUITE_DIR}\nportal-v0.1.0", "Zed Suite\nzz-portal-v0.1.0"]
    assert [r.checkState() for r in rows] == [Qt.CheckState.Checked, Qt.CheckState.Unchecked]
    assert w.units[1].path == f"{SUITE_DIR}/portal" and f"suite {SUITE_DIR}" in w.footer.text()
    tip = w.commit_button.toolTip()                               # nothing staged: no suite's check, core and dev/
    assert "check_versions.py --nexus" in tip and "check_manifest.py" not in tip
    write(nexus / "zz-suite/apps/alpha/new.txt", "x")
    sh(nexus, "add", "zz-suite/apps/alpha/new.txt")
    w.reload()
    tip = w.commit_button.toolTip()                               # the suite staged: its checks alone
    assert "check_versions.py --suite zz-suite" in tip and "zz-suite/tools/check_manifest.py" in tip
    assert f"{SUITE_DIR}/tools/check_manifest.py" not in tip
    sh(nexus, "reset", "-q", "zz-suite/apps/alpha/new.txt")
    (nexus / "zz-suite/apps/alpha/new.txt").unlink()
    w.reload()
    column.itemClicked.emit(rows[1])                              # a click on the row
    assert w.suite == "zz-suite" and column.current() == "zz-suite" and rows[0].checkState() == Qt.CheckState.Unchecked
    assert w.units[1].path == "zz-suite/portal" and "suite zz-suite" in w.footer.text()
    assert w.portal_page.portal_unit.path == "zz-suite/portal"
    assert settings.value("suite") == "zz-suite"
    rows[1].setCheckState(Qt.CheckState.Unchecked)                # its box unticked: one stays ticked
    assert column.current() == "zz-suite" and w.suite == "zz-suite"
    rows[0].setCheckState(Qt.CheckState.Checked)                  # the other box ticked: that suite
    assert column.current() == SUITE_DIR and w.suite == SUITE_DIR
    write(nexus / "zz-suite/portal/VERSION", "0.2.0\n")
    w.refresh()
    assert rows[1].text() == "Zed Suite\nzz-portal-v0.2.0"        # a bumped portal shows its new tag
    column.itemClicked.emit(rows[1])
    w.close()
    again = main_window.ReleaseWindow(nexus, status_source=None, runs_source=None, claude_source=None,
                                      settings=settings)
    assert again.suite == "zz-suite" and again.suite_list.current() == "zz-suite"    # remembered
    again.close()
    chosen = main_window.ReleaseWindow(nexus, status_source=None, runs_source=None, claude_source=None,
                                       settings=settings, suite=SUITE_DIR)
    assert chosen.suite == SUITE_DIR and chosen.suite_list.current() == SUITE_DIR
    chosen.close()


def test_the_suites_names_and_icons(tmp_path):
    """The first column's rows: each suite by its portal's name, with its portal's icon (both suites since the
    Windows portal got its images, 28-10-2026), or its own drawing while a portal has no images."""
    assert rp.suite_name(rp.CHECKOUT, "bc250-bazzite") == "BC250 Bazzite Suite"
    assert rp.suite_name(rp.CHECKOUT, "windows-portable") == "Windows Portable Suite"
    assert rp.suite_icon(rp.CHECKOUT, "bc250-bazzite").name == "bc250-bazzite-suite.webp"
    assert rp.suite_icon(rp.CHECKOUT, "windows-portable").name == "windows-portable-suite.webp"
    bare = tmp_path / "windows-portable"
    (bare / "portal").mkdir(parents=True)
    (bare / "portal" / "apps.toml").write_text("")
    (bare / "icons").mkdir()
    (bare / "icons" / "windows-portable-256.png").write_bytes(b"png")
    assert rp.suite_icon(tmp_path, "windows-portable").name == "windows-portable-256.png"


def test_the_git_questions_are_asked_once_or_side_by_side(repo, monkeypatch):
    """load_units() reads the tags and the untracked files once, and asks each unit's two questions side by side; the
    window's step 1 reads its CHANGELOGs at the tags with one git cat-file (owner, 27-10-2026: the window was slow on
    Windows, some 20 ms per git process). The answers are those of one process per question."""
    calls = []
    real = rp.subprocess.run

    def run(args, *a, **k):
        calls.append(args[1])
        return real(args, *a, **k)
    monkeypatch.setattr(rp.subprocess, "run", run)
    units = rp.load_units(repo)
    assert calls.count("tag") == 1 and calls.count("ls-files") == 1     # once, not once per unit
    for unit in units:
        if unit.kind == "core":
            continue
        tags = rp.tags_of(repo, unit.key, unit.prefix)                  # one git process, as before
        assert unit.last_tag == (tags[-1] if tags else None), unit.key
        if unit.last_tag:
            assert unit.changed == rp.changed_since(repo, unit.last_tag,
                                                    rp.shipped_sources(repo, unit.key, unit.path)), unit.key
    monkeypatch.setattr(rp, "GIT_WORKERS", 1)
    assert [vars(u) for u in rp.load_units(repo)] == [vars(u) for u in units]       # side by side or one by one
    shown = [u for u in units if u.kind != "portal"]
    calls.clear()
    blobs = rp.read_blobs(repo, rp.changelog_specs(shown))
    assert calls == ["cat-file"] and "alpha-v0.1.0:apps/alpha/CHANGELOG" in blobs
    assert [rp.version_choices(repo, u, blobs) for u in shown] == [rp.version_choices(repo, u) for u in shown]


def test_read_blobs_reads_each_file_or_none(repo):
    write(repo / "apps/alpha/CHANGELOG", "Changelog: 01-01-2026 00:00:00\n\nFirst. Café × 2.\n")
    sh(repo, "commit", "-qam", "accents")
    found = rp.read_blobs(repo, ["HEAD:apps/alpha/CHANGELOG", "HEAD:no/such/file", "HEAD:apps/alpha/VERSION"])
    assert found == {"HEAD:apps/alpha/CHANGELOG": "Changelog: 01-01-2026 00:00:00\n\nFirst. Café × 2.\n",
                     "HEAD:no/such/file": None, "HEAD:apps/alpha/VERSION": "0.1.0\n"}
    assert rp.read_blobs(repo, []) == {}


def test_git_answers_are_utf8_on_every_system(repo):
    """git() reads git's output as UTF-8: Windows' own encoding garbled a CHANGELOG's é and ×, so step 1 counted
    every entry of such a CHANGELOG as new since the tag."""
    write(repo / "apps/beta/CHANGELOG", "Changelog: 01-01-2026 00:00:00\n\nFixed. Naïve × 3.\n")
    sh(repo, "commit", "-qam", "accents")
    sh(repo, "tag", "beta-v0.1.0")
    assert rp.git(repo, "show", "beta-v0.1.0:apps/beta/CHANGELOG").endswith("Fixed. Naïve × 3.\n")
    beta = next(u for u in rp.load_units(repo) if u.key == "beta")
    assert rp.new_entries(repo, beta) == []                             # nothing new since its tag


def test_a_suites_release_moves_nexus(two_suites):
    """Latest, the Nexus index, lists every suite's newest portal: a suite's release since Nexus's last version
    needs a Nexus release too, minor; a new suite major (owner, 28-10-2026)."""
    root = two_suites
    write(root / "VERSION", "0.1.0\n")
    write(root / "CHANGELOG", "Changelog: 01-01-2026 00:00:00\n\nRelease 0.1.0.\n")
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", "Nexus 0.1.0")
    assert rp.suite_releases(root) == []
    nexus = next(u for u in rp.load_units(root, "wp") if u.kind == rp.NEXUS)
    assert not nexus.needs_release and nexus.release_reason == "no"

    write(root / "wp/apps/test/VERSION", "0.3.0\n")              # bumped, not committed or tagged yet: it counts
    write(root / "bc/apps/check/VERSION", "0.1.1\n")             # another suite's too
    write(root / "bc/apps/dev/VERSION", "0.2.0\n")
    write(root / "bc/apps/dev/.checkout-only", "Never released.\n")
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", "releases")
    assert rp.suite_releases(root) == ["check-v0.1.1", "wp-test-v0.3.0"]      # never a checkout-only app
    nexus = next(u for u in rp.load_units(root, "wp") if u.kind == rp.NEXUS)
    assert nexus.needs_release and nexus.release_reason == "yes: check-v0.1.1, wp-test-v0.3.0"
    choices, why = rp.version_choices(root, nexus)
    assert choices[0] == "0.2.0" and why == "minor: the suites' releases check-v0.1.1, wp-test-v0.3.0 since Release 0.1.0"
    assert rp.nexus_notes("", nexus.suite_releases) == "Brings check-v0.1.1, wp-test-v0.3.0."
    assert rp.nexus_notes("Mine.", nexus.suite_releases) == "Mine."

    assert rp.bump_nexus(root, "0.2.0") == "Release 0.2.0. Brings check-v0.1.1, wp-test-v0.3.0."
    assert (root / "VERSION").read_text() == "0.2.0\n" and rp.suite_releases(root) == []   # the bump takes them in
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", "Nexus 0.2.0")
    assert rp.suite_releases(root) == []

    write(root / "new/portal/apps.toml", card("x", required=True))       # a new suite: major
    write(root / "new/portal/VERSION", "0.1.0\n")
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", "a new suite")
    assert rp.suite_releases(root) == ["new suite new", "portal-v0.1.0"]
    nexus = next(u for u in rp.load_units(root, "wp") if u.kind == rp.NEXUS)
    choices, why = rp.version_choices(root, nexus)
    assert choices[0] == "1.0.0" and why.startswith("major: new suite new, the suites' releases portal-v0.1.0")
    assert rp.nexus_notes("", nexus.suite_releases) == "Brings the new suite new, portal-v0.1.0."


def test_window_an_apps_release_takes_nexus_along(window, repo):
    write(repo / "VERSION", "0.1.0\n")
    write(repo / "CHANGELOG", "Changelog: 01-01-2026 00:00:00\n\nRelease 0.1.0.\n")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "Nexus 0.1.0")
    window.reload()
    for _, tick, _, _ in window.apps_page.rows:
        tick.setChecked(False)
    _, tick, _, _ = row(window, "alpha")
    _, nexus_tick, nexus_combo, _ = row(window, rp.NEXUS)
    tick.setChecked(True)
    assert nexus_tick.isChecked()                                         # ticked along, visibly
    nexus_combo.setEditText("0.2.0")
    window.apps_page.apply()
    assert (repo / "VERSION").read_text() == "0.2.0\n"
    assert (repo / "CHANGELOG").read_text().split("\n\n")[1] == "Release 0.2.0. Brings alpha-v0.1.1."
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "Release alpha-v0.1.1")
    sh(repo, "tag", "alpha-v0.1.1")
    sh(repo, "tag", "beta-v0.1.0")
    window.reload()
    page = window.portal_page
    page.pin()
    assert not page.nexus_too.isHidden() and page.nexus_too.isChecked()
    assert page.nexus_version.currentText() == "0.3.0"                    # the portal's release: minor
    page.bump()
    assert (repo / "VERSION").read_text() == "0.3.0\n"
    assert (repo / "CHANGELOG").read_text().split("\n\n")[1] == "Release 0.3.0. Brings portal-v0.1.1."
    assert "nexus-v0.3.0" in page.output.toPlainText()


def test_a_windows_suites_release_checks(two_suites):
    """A Windows suite's board tests are its check-release.ps1, run on Windows (owner, 28-10-2026: on Windows every
    test button was off); a Bazzite suite's stay check-release.sh, on Linux."""
    assert rp.check_script(two_suites, "wp") == "wp/tools/check-release.ps1"
    assert rp.check_script(two_suites, "bc") == "bc/tools/check-release.sh"
    assert rp.tests_here(two_suites, "wp", "win32") and not rp.tests_here(two_suites, "wp", "linux")
    assert rp.tests_here(two_suites, "bc", "linux") and not rp.tests_here(two_suites, "bc", "win32")


def test_window_runs_a_windows_suites_checks_on_windows(two_suites, tmp_path, monkeypatch):
    pytest.importorskip("PyQt6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    app = QApplication.instance() or QApplication([])          # noqa: F841 (kept alive for the window)
    from nexus_releases import main_window
    tests_here = rp.tests_here                                  # this computer as Windows, for these tests alone:
    monkeypatch.setattr(rp, "tests_here", lambda root, suite=None, platform=None: tests_here(root, suite, "win32"))
    # (sys.platform itself stays: patched, shutil.which takes Windows' path on Linux and fails, as in CI 28-10-2026)
    write(two_suites / "wp/tools/check-release.ps1", "Write-Host hi\n")
    w = main_window.ReleaseWindow(two_suites, sha256_source=lambda tag: SHA, launch=launched.append,
                                  runs_source=None, status_source=None, suite="wp")
    w.reload()
    page = w.run_page
    assert page.local_button.isEnabled() and page.installer_button.isEnabled() and not page.tour_button.isEnabled()
    assert "check-release.ps1 local" in page.local_button.toolTip()
    launched.clear()
    page.local_button.click()
    page.release_button.click()
    page.installer_button.click()
    script = str(two_suites / "wp/tools/check-release.ps1")
    assert launched == [f"& '{script}' local", f"& '{script}' release", f"& '{script}' installer"]
    w.choose_suite("bc")                                        # the board's suite: its tests run on Linux
    assert not page.local_button.isEnabled() and "Linux (the board)" in page.local_button.toolTip()
    w.close()
