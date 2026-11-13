# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/ci_matrix.py: the CI matrices read from a suite's folders (stage 2 of the release redesign), as the plan
job of each suite's CI and tools/ci_local.py read them."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ci_matrix", ROOT / "tools" / "ci_matrix.py")
cm = importlib.util.module_from_spec(spec)
sys.modules["ci_matrix"] = cm
spec.loader.exec_module(cm)


def suite(root: Path, name: str, system: str, apps: dict[str, bool]) -> Path:
    """A suite with *apps* (name: whether it has tests/), its portal and tools with tests, and some folders that
    never count."""
    folder = root / name
    (folder / "portal" / "tests").mkdir(parents=True)
    (folder / "portal" / "apps.toml").write_text("", encoding="utf-8")
    (folder / "tools" / "tests").mkdir(parents=True)
    (folder / "SYSTEM").write_text(f"{system}\n", encoding="utf-8")
    for app, tested in apps.items():
        (folder / "apps" / app).mkdir(parents=True)
        (folder / "apps" / app / "VERSION").write_text("0.1.0\n", encoding="utf-8")
        if tested:
            (folder / "apps" / app / "tests").mkdir()
    (folder / "apps" / "zed" / "node_modules" / "tests").mkdir(parents=True)        # no VERSION, and never listed
    (folder / "site" / "tests").mkdir(parents=True)
    (folder / ".venv-linux" / "lib" / "tests").mkdir(parents=True)
    return folder


def test_the_pytest_matrix_is_every_folder_with_tests(tmp_path):
    bazzite = suite(tmp_path, "bc", "bazzite", {"gpu": True, "fan": True, "noui": False})
    assert cm.pytest_dirs(bazzite, tmp_path) == ["bc/apps/fan", "bc/apps/gpu", "bc/portal", "bc/tools"]
    windows = suite(tmp_path, "wp", "windows", {"test": True})
    assert cm.pytest_dirs(windows, tmp_path) == ["core", "wp/apps/test", "wp/portal", "wp/tools"]


def test_the_installers_matrix_is_every_app_then_the_portal(tmp_path):
    windows = suite(tmp_path, "wp", "windows", {"test": True, "pcsx2": True, "noui": False})
    assert cm.installer_apps(windows) == ["noui", "pcsx2", "test", "portal"]


def test_the_real_suites_match_their_workflows_and_the_layout_rule():
    """Each suite's CI reads its matrix from this tool (the workflow names the suite and the key), and the list is
    what tools/tests/test_layout.py wants: every folder with tests/."""
    for folder in cm.nexus_suites.suites(ROOT):
        name = "ci.yml" if not cm.nexus_suites.tag_prefix(folder) else f"ci-{folder.name}.yml"
        workflows = ROOT / ".github" / "workflows"
        if cm.nexus_suites.own_repository(folder):      # a repository of its own, cloned here: its own ci.yml
            name, workflows = "ci.yml", folder / ".github" / "workflows"
        text = (workflows / name).read_text(encoding="utf-8")
        assert f"tools/ci_matrix.py --suite {folder.name} pytest" in text, name
        assert "dir: ${{ fromJSON(needs.plan.outputs.dirs) }}" in text, name
        dirs = cm.pytest_dirs(folder)
        assert dirs and all((ROOT / d / "tests").is_dir() for d in dirs)
        if cm.nexus_suites.system(folder) == "windows":
            assert dirs[0] == "core" and "tools/ci_matrix.py --suite" in text
            assert f"tools/ci_matrix.py --suite {folder.name} installers" in text
            assert "app: ${{ fromJSON(needs.plan.outputs.apps) }}" in text
            apps = cm.installer_apps(folder)
            assert apps[-1] == "portal" and all((folder / "apps" / a / "VERSION").is_file() for a in apps[:-1])


def test_the_command_line(capsys):
    assert cm.main(["--suite", "bc250-bazzite", "pytest"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("dirs=[") and "bc250-bazzite/portal" in json.loads(out.removeprefix("dirs="))
    if (ROOT / "windows-portable" / "portal" / "apps.toml").is_file():     # a repository of its own, when cloned here
        assert cm.main(["--suite", "windows-portable", "installers"]) == 0
        assert json.loads(capsys.readouterr().out.removeprefix("apps="))[-1] == "portal"
    assert cm.main(["--suite", "nowhere", "pytest"]) == 2 and "no suite" in capsys.readouterr().err
