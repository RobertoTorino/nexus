# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/dev_versions.py: the version a dev app's CHANGELOG asks for, and setting it: VERSION, the copies
check_versions.py checks and the "Version x.y.z." entry; a version not pushed yet set again, a pushed one kept."""

from __future__ import annotations

import datetime
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dev_versions  # noqa: E402

NOW = datetime.datetime(2026, 11, 4, 19, 0, tzinfo=datetime.timezone.utc)      # 20:00 in Amsterdam


def entry(stamp: str, text: str) -> str:
    return f"Changelog: {stamp}\n\n{text}\n\n"


def checkout(tmp_path: Path, changelog: str, version: str = "0.1.0") -> Path:
    app = tmp_path / "dev" / "dash"
    (app / "nexus_dashboard").mkdir(parents=True)
    (app / "tests").mkdir()
    (app / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    (app / "nexus_dashboard" / "__init__.py").write_text(
        f'APP_NAME = "Nexus Dashboard"\n__version__ = "{version}"\n', encoding="utf-8")
    (app / "tests" / "test_x.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")   # no copy: a test
    (app / "CHANGELOG").write_text(changelog, encoding="utf-8")
    return tmp_path


def test_the_entries_since_the_last_version_give_the_offer(tmp_path):
    root = checkout(tmp_path, entry("03-11-2026 10:00:00", "Fixed. A fix.") +
                    entry("02-11-2026 10:00:00", "Added. A feature.") +
                    entry("01-11-2026 10:00:00", "Version 0.1.0.") +
                    entry("01-10-2026 10:00:00", "Breaking. Before the last version: not counted."))

    [app] = dev_versions.dev_apps(root, base="no-such-ref")

    assert (app.key, app.name, app.version, app.base) == ("dash", "Nexus Dashboard", "0.1.0", "0.1.0")
    assert app.entries == ["Fixed. A fix.", "Added. A feature."] and app.level == "minor"
    assert app.offered == "0.2.0" and app.why == "1 Fixed, 1 Added" and not app.redo
    (root / "dev" / "dash" / "CHANGELOG").write_text(entry("01-11-2026 10:00:00", "Version 0.1.0."), encoding="utf-8")
    [app] = dev_versions.dev_apps(root, base="no-such-ref")
    assert app.offered == "" and app.level == "" and app.why == "nothing since 0.1.0"


def test_setting_writes_version_its_copy_and_the_entry(tmp_path):
    root = checkout(tmp_path, entry("02-11-2026 10:00:00", "Breaking. Gone."))

    changed = dev_versions.set_version(root, "dash", notes="The first.", base="no-such-ref", now=NOW)

    app = root / "dev" / "dash"
    assert [p.relative_to(app).as_posix() for p in changed] == ["VERSION", "nexus_dashboard/__init__.py", "CHANGELOG"]
    assert (app / "VERSION").read_text() == "1.0.0\n"
    assert '__version__ = "1.0.0"' in (app / "nexus_dashboard" / "__init__.py").read_text()
    assert '__version__ = "0.1.0"' in (app / "tests" / "test_x.py").read_text()
    assert (app / "CHANGELOG").read_text().startswith("Changelog: 04-11-2026 20:00:00\n\nVersion 1.0.0. The first.\n\n"
                                                      "Changelog: 02-11-2026")


def test_a_version_not_pushed_is_replaced_and_wrong_ones_are_refused(tmp_path):
    root = checkout(tmp_path, entry("02-11-2026 10:00:00", "Fixed. A fix."))
    with pytest.raises(dev_versions.VersionError, match="no version"):
        dev_versions.set_version(root, "dash", "1.2", base="no-such-ref")
    with pytest.raises(dev_versions.VersionError, match="not above 0.1.0"):
        dev_versions.set_version(root, "dash", "0.1.0", base="no-such-ref")
    with pytest.raises(dev_versions.VersionError, match="no dev app"):
        dev_versions.set_version(root, "gone", base="no-such-ref")

    dev_versions.set_version(root, "dash", base="no-such-ref", now=NOW)          # the offer: 0.1.1
    [app] = dev_versions.dev_apps(root, base="no-such-ref")
    assert app.redo and app.version == "0.1.1" and app.base == "0.1.0" and app.offered == "0.1.1"

    dev_versions.set_version(root, "dash", "0.2.0", base="no-such-ref", now=NOW)  # set again: replaces it
    log = (root / "dev" / "dash" / "CHANGELOG").read_text()
    assert log.count("Version ") == 1 and log.startswith("Changelog: 04-11-2026 20:00:00\n\nVersion 0.2.0.\n\n")
    assert (root / "dev" / "dash" / "VERSION").read_text() == "0.2.0\n"


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_a_pushed_version_is_history(tmp_path):
    root = checkout(tmp_path, entry("02-11-2026 10:00:00", "Fixed. A fix."))
    dev_versions.set_version(root, "dash", base="no-such-ref", now=NOW)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run([*git, "add", "-A"], cwd=root, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "x"], cwd=root, check=True)

    [app] = dev_versions.dev_apps(root, base="HEAD")              # the entry is in the last push
    assert not app.redo and app.entries == [] and app.offered == ""
    with pytest.raises(dev_versions.VersionError, match="nothing in its CHANGELOG since 0.1.1"):
        dev_versions.set_version(root, "dash", "0.2.0", base="HEAD")


def test_the_real_dev_apps_are_listed():
    keys = [app.key for app in dev_versions.dev_apps()]
    assert {"dash", "demo", "itests", "nrt", "sounds"} <= set(keys)
