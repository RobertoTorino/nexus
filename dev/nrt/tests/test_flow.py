# SPDX-License-Identifier: GPL-3.0-or-later
"""flow.py, the Nexus release: what it holds, what Start writes (as steps 1 and 2 would, with the portal's and
Nexus's versions worked out), when Start can go, its one command, and the commands that follow the run."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from nexus_release_tool import flow
from nexus_release_tool import plan as rp

APPS_TOML = ('[apps.test]\nname = "T"\nsummary = "s"\ntag = "wp-test-v0.1.0"\nsha256 = "' + "ab" * 32 + '"\n'
             'required = true\ncategory = "sustainable"\ninstall = ["i"]\nuninstall = ["u"]\ndetect = ["d"]\n')


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def sh(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def nexus(tmp_path) -> Path:
    """Nexus with the Windows Portable Suite's kind on the Nexus release (wp), released once, then a change in its
    test app."""
    root = tmp_path / "nexus"
    write(root / ".gitignore", "__pycache__/\n")                    # as the repository's: the manifest tools' caches
    write(root / "VERSION", "0.5.0\n")
    write(root / "CHANGELOG", "Changelog: 01-01-2026 00:00:00\n\nRelease 0.5.0.\n")
    write(root / "core/VERSION", "0.1.0\n")
    write(root / "core/CHANGELOG", "Changelog: 01-01-2026 00:00:00\n\nVersion 0.1.0.\n")
    write(root / "core/bc250_core/__init__.py", '__version__ = "0.1.0"\n')
    wp = root / "wp"
    write(wp / "SYSTEM", "windows\n")
    write(wp / "TAG_PREFIX", "wp-\n")
    write(wp / "portal/VERSION", "1.0.0\n")
    write(wp / "portal/CHANGELOG", "Changelog: 01-01-2026 00:00:00\n\nRelease 1.0.0.\n")
    write(wp / "apps/test/VERSION", "0.1.0\n")
    write(wp / "apps/test/CHANGELOG", "Changelog: 01-01-2026 00:00:00\n\nRelease 0.1.0.\n")
    write(wp / "apps/test/app.py", "print('hi')\n")
    real = rp.CHECKOUT / "windows-portable"
    for path in ("tools/check_manifest.py", "portal/portable_portal/manifest.py"):
        write(wp / path, (real / path).read_text(encoding="utf-8"))
    write(wp / "portal/apps.toml", APPS_TOML)
    write(root / ".github/workflows/release-wp.yml", "on:\n  workflow_call:\n")
    sh(root, "init", "-q", "-b", "main")
    sh(root, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    sh(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "start")
    for tag in ("wp-test-v0.1.0", "wp-portal-v1.0.0"):
        sh(root, "tag", tag)
    write(wp / "apps/test/app.py", "print('hello')\n")
    write(wp / "apps/test/CHANGELOG", "Changelog: 02-01-2026 00:00:00\n\nAdded. A greeting.\n\n"
                                      "Changelog: 01-01-2026 00:00:00\n\nRelease 0.1.0.\n")
    sh(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-am", "greeting")
    return root


def test_only_the_suites_on_the_nexus_release(nexus):
    assert flow.release_suites(nexus) == ["wp"]
    (nexus / ".github/workflows/release-wp.yml").write_text("on:\n  push:\n", encoding="utf-8")
    assert flow.release_suites(nexus) == []


def test_the_release_holds_the_changed_app_its_portal_and_nexus(nexus):
    found = {p.unit.key: p for p in flow.picks(nexus)}
    assert set(found) == {"test", "portal", rp.NEXUS}               # core did not change
    assert found["test"].choices[0] == "0.2.0" and found["test"].suite == "wp"     # Added. -> minor
    assert found["portal"].version == flow.AUTO and found[rp.NEXUS].version == flow.AUTO
    assert found["test"].label == "wp · test" and found[rp.NEXUS].label == "nexus"


def test_nothing_changed_nothing_to_release(nexus):
    sh(nexus, "tag", "-f", "wp-test-v0.1.0")                        # the change is in the tag now
    assert flow.picks(nexus) == []


def test_start_writes_the_release_as_steps_one_and_two_would(nexus):
    log, tags = flow.write(nexus, flow.picks(nexus), base="HEAD")
    assert tags == ["wp-test-v0.2.0", "wp-portal-v1.1.0", "nexus-v0.6.0"]
    assert (nexus / "wp/apps/test/VERSION").read_text() == "0.2.0\n"
    manifest = (nexus / "wp/portal/apps.toml").read_text()
    assert 'tag = "wp-test-v0.2.0"\nsha256 = ""\n' in manifest          # the sha256 is the workflow's
    assert (nexus / "wp/portal/VERSION").read_text() == "1.1.0\n"       # an app minor: a portal minor
    assert "Release 1.1.0. Pins wp-test-v0.2.0." in (nexus / "wp/portal/CHANGELOG").read_text()
    assert "Release 0.2.0." in (nexus / "wp/apps/test/CHANGELOG").read_text()
    assert (nexus / "VERSION").read_text() == "0.6.0\n"                 # a suite's release: Nexus minor
    assert "Release 0.6.0. Brings wp-portal-v1.1.0, wp-test-v0.2.0." in (nexus / "CHANGELOG").read_text()
    assert len(log) == 3


def test_a_typed_version_overrides_the_suggestion(nexus):
    chosen = flow.picks(nexus)
    for pick in chosen:
        pick.version = {"test": "1.0.0", "portal": "2.0.0", rp.NEXUS: "1.0.0"}[pick.unit.key]
        pick.notes = "notes" if pick.unit.key == "test" else ""
    _log, tags = flow.write(nexus, chosen, base="HEAD")
    assert tags == ["wp-test-v1.0.0", "wp-portal-v2.0.0", "nexus-v1.0.0"]
    assert "Release 1.0.0. notes" in (nexus / "wp/apps/test/CHANGELOG").read_text()


def test_a_portal_typed_too_low_gets_what_ci_asks(nexus):
    chosen = flow.picks(nexus)
    for pick in chosen:
        if pick.unit.key == "test":
            pick.version = "1.0.0"                                  # a major app release
        if pick.unit.key == "portal":
            pick.version = "1.0.1"
    log, tags = flow.write(nexus, chosen, base="HEAD")
    assert "wp-portal-v2.0.0" in tags and any("less than CI asks" in line for line in log)


def test_wrong_versions_are_refused_before_anything_is_written(nexus):
    chosen = flow.picks(nexus)
    chosen[0].version = "0.0.9"
    assert flow.problems(chosen) == ["wp · test: 0.0.9 is not higher than 0.1.0, which is already tagged"]
    chosen[0].version = "abc"
    assert "is not x.y.z" in flow.problems(chosen)[0]


def test_start_needs_a_clean_tree_at_the_last_push(nexus):
    assert flow.ready(nexus, base="HEAD") == []
    (nexus / "wp/apps/test/app.py").write_text("changed\n")
    assert flow.ready(nexus, base="HEAD")[0].startswith("The working tree has changes")
    sh(nexus, "checkout", "-q", "--", ".")
    assert "not pushed" in flow.ready(nexus, base="HEAD~1")[0]
    assert "git fetch" in flow.ready(nexus, base="origin/main")[0]


def test_the_one_command_commits_pushes_and_starts_the_workflow():
    command = flow.start_command(flow.commit_message(["wp-test-v0.2.0", "wp-portal-v1.1.0", "nexus-v0.6.0"]))
    assert command.startswith("git commit -a -q -m 'Release wp-test-v0.2.0, wp-portal-v1.1.0, nexus-v0.6.0' && ")
    assert "git push origin HEAD:main && gh workflow run release-nexus.yml --ref main" in command
    assert '-f commit="$(git rev-parse HEAD)"' in command


def test_the_run_is_followed_stopped_and_resumed():
    other = rp.BuildRun("CI Nexus", "main", "completed", "success", "https://github.com/o/r/actions/runs/1", "abc", "t",
                        file="ci-nexus.yml")
    run = rp.BuildRun("Release Nexus", "main", "in_progress", "", "https://github.com/o/r/actions/runs/42", "abc", "t",
                      file="release-nexus.yml")
    assert flow.release_run([other, run]) is run and flow.release_run([other, run], "def") is None
    assert flow.stop_command(run) == "gh run cancel 42"
    assert flow.resume_command(run) == "gh run rerun 42 --failed"


def test_the_device_test_and_publish_work_on_the_portals_draft(nexus):
    assert flow.waiting_portals(nexus) == ["wp-portal-v1.0.0"]
    assert flow.publish_command("wp-portal-v1.1.0") == "gh release edit wp-portal-v1.1.0 --draft=false --latest=false"
    line = flow.device_test_line(nexus, "wp", "wp-portal-v1.1.0", windows=True)
    assert line.startswith("& '") and line.endswith("check-release.ps1' draft wp-portal-v1.1.0")


def test_a_release_commit_whose_push_stopped_is_pushed_and_started(nexus):
    assert flow.unpushed_release(nexus, base="HEAD") == ""
    sh(nexus, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m",
       "Release wp-test-v0.2.0, wp-portal-v1.1.0")
    assert flow.unpushed_release(nexus, base="HEAD~1") == "Release wp-test-v0.2.0, wp-portal-v1.1.0"
    sh(nexus, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "other")
    assert flow.unpushed_release(nexus, base="HEAD~2") == ""             # not right on top of the last push
    assert flow.push_and_start_command().startswith("git push origin HEAD:main && gh workflow run release-nexus.yml")


@pytest.fixture
def release_window(nexus, tmp_path):
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])          # noqa: F841 (kept alive for the window)
    from nexus_release_tool import main_window
    launched: list[str] = []
    w = main_window.ReleaseWindow(nexus, launch=launched.append, runs_source=None, status_source=None,
                                  claude_source=None, suite="wp")
    w.portal_page.base_edit.setText("HEAD")
    w.reload()
    w.launched = launched
    yield w
    w.close()


def test_the_window_opens_on_the_nexus_release(release_window):
    w = release_window
    page = w.release_page
    assert w.tabs.widget(0) is page and w.tabs.tabText(0) == "Nexus release"
    assert [pick.label for pick, _combo, _notes in page.rows] == ["wp · test", "wp · portal", "nexus"]
    assert page.rows[0][1].currentText() == "0.2.0" and page.rows[1][1].currentText() == flow.AUTO
    assert page.start_button.isEnabled() and page.portal_choice.currentText() == "wp-portal-v1.0.0"
    assert not page.stop_button.isEnabled() and not page.resume_button.isEnabled()


def test_start_writes_the_release_and_runs_the_one_command(release_window, monkeypatch):
    w = release_window
    page = w.release_page
    ran = []
    monkeypatch.setattr(w, "confirm_git", lambda *a: True)
    monkeypatch.setattr(w, "run_git", ran.append)
    page.rows[0][2].setText("A greeting")
    page.start()
    assert ran == [flow.start_command("Release wp-test-v0.2.0, wp-portal-v1.1.0, nexus-v0.6.0")]
    assert "Release 0.2.0. A greeting" in (w.root / "wp/apps/test/CHANGELOG").read_text()
    assert "wp · test: 0.2.0" in page.output.toPlainText()


def test_start_fetches_the_tags_and_main_first_and_goes_on(release_window, monkeypatch, tmp_path):
    """A portal is tagged on GitHub when it is published, and a release pins on main after it: neither is here until
    fetched (owner, 31-10-2026: Release 6.2.0 again after 6.2.0 was out; the Pin ... commit refused the push). Start
    fetches the tags and brings in main's commits under this checkout, reads the versions again and goes on to its
    question, with nothing to do by hand."""
    w = release_window
    page = w.release_page
    origin = tmp_path / "origin.git"
    sh(tmp_path, "init", "-q", "--bare", str(origin))
    sh(w.root, "remote", "add", "origin", str(origin))
    sh(w.root, "push", "-q", "origin", "main")
    sh(w.root, "push", "-q", "origin", "HEAD:refs/tags/wp-portal-v1.1.0")    # published on GitHub, not fetched
    other = tmp_path / "other"                                       # the release's Pin ... commit, on GitHub only
    sh(tmp_path, "clone", "-q", str(origin), str(other))
    write(other / "wp/portal/apps.toml", (other / "wp/portal/apps.toml").read_text() + "\n")
    sh(other, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-am", "Pin wp-test-v0.1.0")
    sh(other, "push", "-q", "origin", "HEAD:main")
    w.portal_page.base_edit.setText("origin/main")
    ran, asked = [], []
    monkeypatch.setattr(w, "confirm_git", lambda *a: asked.append(a[1]) or True)
    monkeypatch.setattr(w, "run_git", ran.append)
    page.start()
    assert sh(w.root, "tag", "--list", "wp-portal-v1.1.0").strip() == "wp-portal-v1.1.0"
    assert "Pin wp-test-v0.1.0" in sh(w.root, "log", "--format=%s")       # brought in, under the release
    assert len(ran) == 1 and "wp-portal-v1.2.0" in ran[0] and "wp · portal: 1.0.0 -> auto" in asked[0]
    assert flow.fetch_tags(w.root) == []                            # nothing new the second time


def test_catch_up_brings_in_mains_commits_under_this_checkouts(nexus, tmp_path):
    origin = tmp_path / "origin.git"
    sh(tmp_path, "init", "-q", "--bare", str(origin))
    sh(nexus, "remote", "add", "origin", str(origin))
    sh(nexus, "push", "-q", "origin", "main")
    sh(nexus, "fetch", "-q", "origin")
    assert flow.catch_up(nexus) == 0                                # nothing to bring in
    other = tmp_path / "other"
    sh(tmp_path, "clone", "-q", str(origin), str(other))
    write(other / "wp/portal/apps.toml", (other / "wp/portal/apps.toml").read_text() + "\n")
    sh(other, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-am", "Pin wp-test-v0.1.0")
    sh(other, "push", "-q", "origin", "HEAD:main")
    write(nexus / "wp/apps/test/app.py", "print('hello again')\n")   # this checkout's own commit, not pushed
    sh(nexus, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-am", "mine")
    sh(nexus, "fetch", "-q", "origin")
    write(nexus / "wp/apps/test/app.py", "not committed\n")
    assert flow.catch_up(nexus) is None                             # changes not committed: nothing is done
    sh(nexus, "checkout", "-q", "--", ".")
    assert flow.catch_up(nexus) == 1
    assert sh(nexus, "log", "--format=%s", "-2").split("\n")[:2] == ["mine", "Pin wp-test-v0.1.0"]


def test_a_version_only_offered_follows_the_next_offer(release_window):
    """After the tags are read again the table offers anew; what the owner typed stays (owner, 31-10-2026: the old
    offer 5.3.0 stayed as if typed, and Start refused it)."""
    page = release_window.release_page
    pick, combo, _notes = page.rows[0]
    pick.choices[0] = "0.1.5"                                       # what it offered before the tags were read
    combo.setEditText("0.1.5")
    page.fill()
    assert page.rows[0][1].currentText() == "0.2.0"
    page.rows[0][1].setEditText("0.4.0")                            # typed: stays
    page.fill()
    assert page.rows[0][1].currentText() == "0.4.0"


def test_changes_not_committed_make_commit_the_step_to_do(release_window, monkeypatch):
    """The steps in their order (owner, 30-10-2026: "exactly what has to be done in their logical sequence"): with
    changes in the tree, step 2 Commit is the one lit, and Start waits."""
    w = release_window
    page = w.release_page
    (w.root / "wp/apps/test/app.py").write_text("changed\n")
    w.reload()
    states = flow.step_states(page.facts)
    assert states["pull"] == "done" and states["commit"] == "now" and states["start"] == "later"
    assert page.marks["commit"].text() == "▶" and "1 file changed" in page.details["commit"].text()
    assert not page.start_button.isEnabled() and not page.push_button.isEnabled()
    assert not page.commit_button.isEnabled()                   # a message first
    page.commit_message.setText("A greeting")
    assert page.commit_button.isEnabled()
    ran = []
    monkeypatch.setattr(w, "run_git", ran.append)
    page.commit()
    assert ran[0].startswith("git add -A && tools/fix-modes.sh") and "git commit" in ran[0] and "A greeting" in ran[0]
    assert "check_manifest.py" in ran[0] and w.committing
    warned = []
    monkeypatch.setattr("nexus_release_tool.release_page.QMessageBox.warning", lambda *a: warned.append(a[2]))
    page.start()
    assert warned and "working tree has changes" in warned[0]


def _run(sha="abc1234", file="release-nexus.yml", workflow="Release Nexus", status="completed",
         conclusion="success", ref="main"):
    return rp.BuildRun(workflow, ref, status, conclusion, f"https://github.com/o/r/actions/runs/{abs(hash(sha+file))}",
                       sha, "title", file=file)


def test_the_step_to_do_follows_the_release():
    """Every step in turn: pull, commit, push, CI, Start, the run, the device test and Publish, the pin commit."""
    assert flow.current_step(flow.Facts(behind=2, dirty=True)) == "pull"
    assert flow.current_step(flow.Facts(dirty=True, ahead=1)) == "commit"
    assert flow.current_step(flow.Facts(ahead=1)) == "push"
    assert flow.current_step(flow.Facts(ci="building", something=True)) == "ci"
    states = flow.step_states(flow.Facts(ci="failed", something=True))
    assert states["ci"] == "failed" and states["commit"] == "done" and states["start"] == "later"
    assert flow.current_step(flow.Facts(ci="passed", something=True)) == "start"
    assert flow.current_step(flow.Facts(ci="unknown", something=True)) == "start"      # no GitHub here: not held
    assert flow.current_step(flow.Facts(ci="passed")) == ""                             # nothing to release
    assert set(flow.step_states(flow.Facts(ci="passed")).values()) == {"done"}
    assert flow.current_step(flow.Facts(ahead=1, unpushed="Release x")) == "start"     # Push and start
    running = _run(status="in_progress", conclusion="")
    assert flow.current_step(flow.Facts(run=running)) == "run"
    failed = flow.step_states(flow.Facts(run=_run(conclusion="failure")))
    assert failed["run"] == "failed" and failed["start"] == "done" and failed["test"] == "later"
    states = flow.step_states(flow.Facts(run=_run(), drafts=["wp-portal-v2.0.0"]))
    assert states["test"] == states["publish"] == "now" and states["run"] == "done"
    assert flow.current_step(flow.Facts(run=_run(), behind=1)) == "finish"
    assert flow.current_step(flow.Facts(run=_run())) == ""                               # out and pulled
    assert flow.current_step(flow.Facts(run=_run(), drafts=["x"], dirty=True)) == "commit"  # a fix after Not OK


def test_a_failed_release_gets_its_fix_then_starts_again_on_it():
    """CI failed on the release commit (30-10-2026): the release is written and pushed, so its fix goes through Commit,
    Push and CI, then the run starts again on it; Start never writes it a second time."""
    failed = _run(conclusion="failure")
    states = flow.step_states(flow.Facts(run=failed, dirty=True, restart=True))
    assert flow.current_step(flow.Facts(run=failed, dirty=True, restart=True)) == "commit"
    assert states["start"] == "done" and states["run"] == "failed" and states["commit"] == "now"
    assert flow.current_step(flow.Facts(run=failed, ahead=1, restart=True)) == "push"
    assert flow.current_step(flow.Facts(run=failed, restart=True, ci="building")) == "ci"
    assert flow.current_step(flow.Facts(run=failed, restart=True, ci="passed", something=True)) == "run"
    assert flow.current_step(flow.Facts(run=failed, ci="passed")) == "run"             # no fix: Resume run
    assert flow.restart_command().startswith('gh workflow run release-nexus.yml --ref main -f commit="$(git rev-parse '
                                             'HEAD)"')


def test_a_failed_release_run_lasts_with_fixes_on_top(nexus):
    head = sh(nexus, "rev-parse", "HEAD").strip()
    failed = _run(head, conclusion="failure")
    sh(nexus, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "Fix CI")
    assert flow.cycle_run(nexus, [failed]) is failed               # still that release: its fix is on top
    assert flow.cycle_run(nexus, [_run(head)]) is None              # one that passed: other work ends it


def test_failed_ci_runs_again(release_window, monkeypatch):
    """CI failed for GitHub's own trouble (30-10-2026, Actions degraded): step 4 lights Run CI again, which starts
    the failed CI runs of HEAD again; a passed one and another commit's are left alone."""
    runs = [_run("aaa", "ci.yml", "CI", conclusion="failure"), _run("aaa", "ci-nexus.yml", "CI Nexus"),
            _run("bbb", "ci.yml", "CI", conclusion="failure")]
    assert flow.failed_ci(runs, "aaa") == [runs[0]]
    assert flow.rerun_ci_command(flow.failed_ci(runs, "aaa")) == f"gh run rerun {flow.run_id(runs[0])} --failed"
    w = release_window
    page = w.release_page
    head = sh(w.root, "rev-parse", "HEAD").strip()
    monkeypatch.setattr(w.build, "runs", [_run(head, "ci.yml", "CI", conclusion="failure")])
    monkeypatch.setattr(w.build, "source", object())
    page.show_state()
    assert page.facts.ci == "failed" and page.rerun_ci_button.isEnabled()
    assert "Run CI again" in page.details["ci"].text()
    ran = []
    monkeypatch.setattr(w, "run_git", ran.append)
    page.rerun_ci()
    assert ran and ran[0].startswith("gh run rerun ") and ran[0].endswith(" --failed")


def test_ci_state_reads_the_ci_runs_of_the_commit():
    runs = [_run("aaa", "ci.yml", "CI"), _run("aaa", "ci-nexus.yml", "CI Nexus", "in_progress", ""),
            _run("aaa", "release-nexus.yml"), _run("bbb", "ci.yml", "CI", conclusion="failure")]
    assert flow.ci_state(runs, "aaa") == "building" and flow.ci_state(runs, "bbb") == "failed"
    assert flow.ci_state(runs[:1], "aaa") == "passed" and flow.ci_state(runs, "ccc") == "none"


def test_the_release_run_lasts_until_other_work_is_committed(nexus):
    head = sh(nexus, "rev-parse", "HEAD").strip()
    run = _run(head)
    assert flow.cycle_run(nexus, [run]) is run
    sh(nexus, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "Pin wp-test-v0.2.0")
    assert flow.cycle_run(nexus, [run]) is run                    # the pin commit pulled: still this release
    sh(nexus, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "Other work")
    assert flow.cycle_run(nexus, [run]) is None
    assert flow.cycle_run(nexus, []) is None
    assert flow.published(nexus, [_run(ref="wp-portal-v9.9.9", file="nexus-index.yml")], "wp-portal-v9.9.9")
    assert not flow.published(nexus, [], "wp-portal-v9.9.9")


def test_a_push_git_has_not_fetched_lights_the_pull(release_window, monkeypatch):
    """The release's Pin ... commit is on GitHub, not fetched (owner, 30-10-2026: step 9 stayed dark while git pull
    (new) was lit): GitHub's newest run on main names a commit this checkout lacks, so step 9 is the one to do."""
    w = release_window
    page = w.release_page
    head = sh(w.root, "rev-parse", "HEAD").strip()
    release = _run(head)
    assert flow.pushed_elsewhere(w.root, [_run(head, "ci.yml", "CI"), release]) is None
    pin = _run("f" * 40, "ci.yml", "CI")
    assert flow.pushed_elsewhere(w.root, [pin, release]) is pin
    monkeypatch.setattr(w.build, "runs", [pin, release])
    monkeypatch.setattr(flow, "waiting_portals", lambda root: [])
    page.show_state()
    assert page.facts.behind == 1 and flow.current_step(page.facts) == "finish"
    assert page.finish_button.isEnabled()


def test_the_device_test_and_publish(release_window, monkeypatch):
    w = release_window
    page = w.release_page
    monkeypatch.setattr("nexus_release_tool.release_page.rp.tests_here", lambda *a: True)
    page.show_state()
    page.device_test()
    assert w.launched and w.launched[-1].endswith("draft wp-portal-v1.0.0")
    ran = []
    monkeypatch.setattr(w, "confirm_git", lambda *a: True)
    monkeypatch.setattr(w, "run_git", ran.append)
    page.publish()
    assert ran == ["gh release edit wp-portal-v1.0.0 --draft=false --latest=false"]
    w.build.runs = [_run(sh(w.root, "rev-parse", "HEAD").strip())]   # the release run passed on HEAD: its draft
    monkeypatch.setattr(flow, "published", lambda *a: False)          # wp-portal-v1.0.0 a draft still
    page.show_state()
    assert flow.step_states(page.facts)["test"] == "now"
    page.reject()
    assert "stays a draft" in page.output.toPlainText()
    # Not OK shows on the step (owner, 30-10-2026: it seemed to do nothing): red, with what comes next
    assert flow.step_states(page.facts)["test"] == "failed" and page.facts.rejected == ["wp-portal-v1.0.0"]
    assert page.details["test"].text().startswith("Not OK: wp-portal-v1.0.0 stays a draft")
    assert page.marks["test"].text() == "!" and page.test_button.isEnabled() and page.publish_button.isEnabled()


def test_not_ok_is_the_runs_and_a_fix_goes_on_from_commit():
    run = _run()
    facts = flow.Facts(run=run, drafts=["wp-portal-v6.0.0"], rejected=["wp-portal-v6.0.0"])
    states = flow.step_states(facts)
    assert flow.current_step(facts) == "test" and states["test"] == "failed" and states["publish"] == "later"
    assert flow.step_states(flow.Facts(run=run, drafts=["wp-portal-v6.0.0"]))["test"] == "now"   # a run made anew
    assert flow.current_step(flow.Facts(run=run, drafts=["wp-portal-v6.0.0"], rejected=["wp-portal-v6.0.0"],
                                        dirty=True)) == "commit"
