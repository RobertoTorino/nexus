# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/merge_changelog.py, git's merge driver for the CHANGELOGs, and tools/git-setup.sh, which registers it: an
entry written on each machine above the same old entry merges without a conflict, in a pull --rebase --autostash as
Nexus Release Tool runs it (owner, 01-11-2026: that pull ended in a conflict every time)."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

spec = importlib.util.spec_from_file_location("merge_changelog", TOOLS / "merge_changelog.py")
mc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mc
spec.loader.exec_module(mc)


def entry(time: str, text: str) -> str:
    return f"Changelog: {time}\n\n{text}\n\n"


OLD_TOP = entry("01-11-2026 17:36:48", "Version 2.4.0.")
OLD = entry("01-11-2026 14:10:30", "Added. InfoButton.")
BASE = OLD_TOP + OLD.rstrip("\n") + "\n"
HERE = entry("01-11-2026 20:36:00", "Fixed. latest_release() follows GitHub's pages.")
RELEASE = entry("01-11-2026 18:11:40", "Version 2.5.0.") + entry("01-11-2026 16:56:02", "Added. keep.py.")


def headers(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("Changelog: ")]


def test_split_keeps_every_byte_and_numbers_equal_headers():
    text = "note\n" + OLD_TOP + OLD_TOP + OLD
    preamble, entries = mc.split(text)
    assert preamble == "note\n" and preamble + "".join(chunk for _, chunk in entries) == text
    assert [key for key, _ in entries] == [("Changelog: 01-11-2026 17:36:48", 0), ("Changelog: 01-11-2026 17:36:48", 1),
                                           ("Changelog: 01-11-2026 14:10:30", 0)]


def test_new_entries_on_both_sides_merge_newest_first():
    # Today's case: Claude's entry here, a release's two entries from the other machine, all above Version 2.4.0.
    merged = mc.merge(BASE, HERE + BASE, RELEASE + BASE)
    assert merged == HERE + RELEASE + BASE
    # The other way round (the release is ours, Claude's entry theirs) gives the same file.
    assert mc.merge(BASE, RELEASE + BASE, HERE + BASE) == merged


def test_an_older_entry_of_ours_goes_under_a_newer_one_of_theirs():
    ours_new = entry("01-11-2026 15:00:00", "Fixed. Written early, committed late.")
    merged = mc.merge(BASE, ours_new + BASE, RELEASE + BASE)
    assert headers(merged) == ["Changelog: 01-11-2026 18:11:40", "Changelog: 01-11-2026 16:56:02",
                               "Changelog: 01-11-2026 15:00:00", "Changelog: 01-11-2026 17:36:48",
                               "Changelog: 01-11-2026 14:10:30"]


def test_theirs_sits_above_the_entry_it_sat_above_and_old_entries_keep_their_place():
    # An unsorted old file stays as it is; theirs' entry inserted in the middle goes to the middle.
    base = OLD + OLD_TOP
    middle = entry("01-11-2026 15:00:00", "Fixed. In between.")
    merged = mc.merge(base, HERE + base, OLD + middle + OLD_TOP)
    assert merged == HERE + OLD + middle + OLD_TOP


def test_theirs_changes_and_removals_are_taken():
    corrected = OLD.replace("InfoButton", "InfoButton (widgets.py)")
    assert mc.merge(BASE, HERE + BASE, OLD_TOP + corrected.rstrip("\n") + "\n") == HERE + OLD_TOP + corrected.rstrip("\n") + "\n"
    assert mc.merge(BASE, HERE + BASE, OLD_TOP) == HERE + OLD_TOP
    assert mc.merge(BASE, BASE, BASE) == BASE                   # nothing changed: nothing moves


def test_the_same_entry_changed_on_both_sides_is_a_conflict():
    assert mc.merge(BASE, HERE + BASE, HERE.replace("GitHub's", "the") + BASE) is None
    assert mc.merge(BASE, OLD_TOP + OLD.replace("Added", "Fixed"), OLD_TOP + OLD.replace("Added", "Breaking")) is None
    assert mc.merge(BASE, OLD_TOP + OLD.replace("Added", "Fixed"), OLD_TOP) is None    # changed here, removed there
    assert mc.merge(BASE, "x\n" + BASE, "y\n" + BASE) is None                          # the text before the first entry


def test_main_writes_ours_or_falls_back_to_gits_line_merge(tmp_path):
    base, ours, theirs = tmp_path / "base", tmp_path / "ours", tmp_path / "theirs"
    base.write_text(BASE); ours.write_text(HERE + BASE); theirs.write_text(RELEASE + BASE)
    assert mc.main([str(base), str(ours), str(theirs)]) == 0 and ours.read_text() == HERE + RELEASE + BASE
    if shutil.which("git") is None:
        pytest.skip("needs git")
    theirs.write_text(HERE.replace("GitHub's", "the") + BASE)
    ours.write_text(HERE + BASE)
    assert mc.main([str(base), str(ours), str(theirs)]) == 1
    assert "<<<<<<< ours" in ours.read_text() and ">>>>>>> theirs" in ours.read_text()
    assert mc.main(["only-one"]) == 2


@pytest.mark.skipif(shutil.which("git") is None or shutil.which("bash") is None, reason="needs git, bash")
def test_pull_rebase_autostash_merges_both_machines_entries(tmp_path):
    """The real thing: machine A has Claude's entry uncommitted, machine B pushed a release's entries; A's git pull
    --rebase --autostash comes back clean with the driver (tools/git-setup.sh), and conflicts without it."""
    def git(cwd, *args):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=ENV)

    remote, a, b = tmp_path / "remote.git", tmp_path / "a", tmp_path / "b"
    assert git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote)).returncode == 0
    assert git(tmp_path, "clone", "-q", str(remote), str(a)).returncode == 0
    (a / "tools").mkdir()
    for name in ("merge_changelog.py", "git-setup.sh"):
        shutil.copy(TOOLS / name, a / "tools" / name)
    (a / ".gitattributes").write_text("CHANGELOG merge=changelog\n")
    (a / "core").mkdir()
    (a / "core" / "CHANGELOG").write_text(BASE)
    for args in (("add", "-A"), ("commit", "-qm", "first"), ("push", "-q", "origin", "main")):
        assert git(a, *args).returncode == 0, args
    assert git(tmp_path, "clone", "-q", str(remote), str(b)).returncode == 0
    (b / "core" / "CHANGELOG").write_text(RELEASE + BASE)
    for args in (("commit", "-qam", "release"), ("push", "-q", "origin", "main")):
        assert git(b, *args).returncode == 0, args

    (a / "core" / "CHANGELOG").write_text(HERE + BASE)              # uncommitted, as Claude leaves it
    setup = subprocess.run(["bash", "tools/git-setup.sh"], cwd=a, capture_output=True, text=True, env=ENV)
    assert setup.returncode == 0 and "merge.changelog.driver" in setup.stdout, setup.stderr
    assert git(a, "config", "--local", "--get", "core.hooksPath").stdout.strip() == "tools/hooks"
    again = subprocess.run(["bash", "tools/git-setup.sh"], cwd=a, capture_output=True, text=True, env=ENV)
    assert again.returncode == 0 and again.stdout == ""            # set already: silent
    pull = git(a, "pull", "-q", "--rebase", "--autostash")
    assert pull.returncode == 0, pull.stderr
    assert (a / "core" / "CHANGELOG").read_text() == HERE + RELEASE + BASE
    assert git(a, "status", "--porcelain").stdout.strip() == "M core/CHANGELOG"

    # Without the driver, the same pull leaves the conflict the owner saw.
    assert git(a, "config", "--local", "--unset", "merge.changelog.driver").returncode == 0
    assert git(a, "reset", "-q", "--hard", "HEAD~1").returncode == 0
    (a / "core" / "CHANGELOG").write_text(HERE + BASE)
    pull = git(a, "pull", "-q", "--rebase", "--autostash")      # exit 0: the rebase itself went fine
    assert "stash" in pull.stderr and git(a, "stash", "list").stdout.strip()   # "could not apply autostash", the wording varies
