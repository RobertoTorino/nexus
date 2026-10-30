# SPDX-License-Identifier: GPL-3.0-or-later
"""Every app of every suite has the same layout: its Python package(s) and images/ directly in <suite>/apps/<name>/, no
wrapper folder; the Nexus apps in dev/<name>/ (Nexus Release Tool) the same."""

from __future__ import annotations

import re
from pathlib import Path

SUITE = Path(__file__).resolve().parents[2]         # the checkout
SKIP = {"tests", "__pycache__", ".pytest_cache"}


def _suites() -> list[Path]:
    """Every suite: a folder under the root with portal/apps.toml."""
    return sorted(p for p in SUITE.iterdir() if p.is_dir() and (p / "portal" / "apps.toml").is_file())


def _apps() -> list[Path]:
    folders = [suite / "apps" for suite in _suites()] + [SUITE / "dev"]
    return sorted(path for folder in folders if folder.is_dir() for path in folder.iterdir()
                  if (path / "VERSION").is_file())


def _visible(path: Path, app: Path) -> bool:
    parts = path.relative_to(app).parts
    return not (set(parts) & SKIP) and not any(part.startswith(".venv") for part in parts)


def test_packages_sit_at_the_app_root():
    """apps/<name>/<package>/__main__.py, never apps/<name>/<folder>/<package>/__main__.py."""
    nested = [str(main.relative_to(SUITE)) for app in _apps() for main in app.rglob("__main__.py")
              if _visible(main, app) and main.parent.parent != app]
    assert not nested, f"packages in a wrapper folder: {', '.join(nested)}"


def test_every_app_has_a_package_and_images_at_its_root():
    for app in _apps():
        if not any(app.glob("*/__main__.py")) and not any(app.glob("*.sh")):
            raise AssertionError(f"{app.name}: no package or script at the app root")
        assert (app / "images").is_dir(), f"{app.name}: no images/ at the app root"


def _windows(suite: Path) -> bool:
    return (suite / "SYSTEM").is_file() and (suite / "SYSTEM").read_text(encoding="utf-8").strip() == "windows"


def _installer(app: Path) -> Path:
    """An app's installer: install.ps1 in a Windows suite (windows-portable), install.sh everywhere else."""
    return app / ("install.ps1" if _windows(app.parent.parent) else "install.sh")


def _installers() -> list[Path]:
    """Every installer, with the install.ps1 a Nexus app has beside its install.sh (Nexus Release Tool on Windows)."""
    return [*(_installer(app) for app in _apps()),
            *(app / "install.ps1" for app in _apps() if _installer(app).name != "install.ps1"
              and (app / "install.ps1").is_file()),
            *(p for suite in _suites() if not _windows(suite)
              for p in (suite / "portal" / "install.sh", suite / "tools" / "installer-tests" / "gui" / "install.sh"))]


def test_every_app_has_an_installer_at_its_root():
    missing = [f"{app.name} ({_installer(app).name})" for app in _apps() if not _installer(app).is_file()]
    assert not missing, f"no installer at the app root: {', '.join(missing)}"


def test_installers_take_the_standard_options_and_refuse_root():
    """--no-desktop-shortcut, --uninstall, --uninstall --purge, --help; run as your own user, not with sudo (on
    Windows: not as administrator)."""
    for installer in _installers():
        text = installer.read_text(encoding="utf-8")
        windows = installer.suffix == ".ps1"
        for option in ("--no-desktop-shortcut", "--uninstall", "--purge", "--help"):
            assert (f"'{option}'" if windows else f"{option})") in text, \
                f"{installer.relative_to(SUITE)} does not handle {option}"
        assert "only goes with --uninstall" in text, f"{installer.relative_to(SUITE)} accepts --purge alone"
        refusal = "not as administrator" if windows else "not with sudo"
        assert refusal in text, \
            f"{installer.relative_to(SUITE)} does not refuse to run as {'administrator' if windows else 'root'}"


def test_installers_upgrade_the_python_packages():
    """pip install -r with --upgrade: installing again brings each package to the newest version its requirements
    allow, a security fix within the range included (owner's decision, 13-10-2026)."""
    installers = sorted([*SUITE.glob("*/apps/*/install.sh"), *SUITE.glob("*/apps/*/packaging/*/*.sh"),
                         *SUITE.glob("*/portal/install.sh")])
    calls = [(path, line) for path in installers for line in path.read_text(encoding="utf-8").splitlines()
             if re.search(r"\bpip\"? install\b.* -r ", line) and not line.lstrip().startswith("#")]
    assert len(calls) >= 18
    assert [(path.relative_to(SUITE), line) for path, line in calls if "--upgrade -r" not in line] == []


def test_every_suite_names_its_system():
    import importlib.util
    spec = importlib.util.spec_from_file_location("nexus_suites", SUITE / "tools" / "suites.py")
    suites = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(suites)
    for folder in _suites():
        assert suites.system(folder) in suites.SYSTEMS, f"{folder.name}/SYSTEM: one of {', '.join(suites.SYSTEMS)}"


def test_the_suites_tags_never_mix():
    """One suite has plain tags (bc250-bazzite: installed portals find its releases by them); every other has a
    TAG_PREFIX of its own, and no app of the plain suite starts with one, so a tag names one suite."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("nexus_suites", SUITE / "tools" / "suites.py")
    suites = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(suites)
    prefixes = [suites.tag_prefix(folder) for folder in _suites()]
    assert prefixes.count("") == 1 and len(set(prefixes)) == len(prefixes), prefixes
    for prefix in filter(None, prefixes):
        assert re.fullmatch(r"[a-z0-9]+-", prefix), f"TAG_PREFIX {prefix!r}: lowercase letters and digits, then -"
    plain = next(folder for folder in _suites() if not suites.tag_prefix(folder))
    for app in (plain / "apps").iterdir():
        assert not any(app.name.startswith(prefix) for prefix in filter(None, prefixes)), app.name


def test_every_app_has_tests_and_ci_runs_them():
    import re
    for app in _apps():
        assert (app / "tests").is_dir(), f"{app.name}: no tests/"
        assert (app / "requirements-dev.txt").is_file(), f"{app.name}: no requirements-dev.txt (CI installs it)"
    # ci-nexus.yml (core, tools, dev/), ci.yml (the BC250 Bazzite Suite) and a suite's own ci-<suite>.yml
    listed = set()
    for workflow in sorted((SUITE / ".github" / "workflows").glob("ci*.yml")):
        matrix = re.search(r"dir: \[([^\]]*)\]", workflow.read_text(encoding="utf-8")).group(1)
        listed |= {entry.strip() for entry in matrix.replace("\n", " ").split(",")}
    folders = {path.parent.relative_to(SUITE).as_posix() for path in SUITE.glob("**/tests")
               if path.is_dir() and not (set(path.relative_to(SUITE).parts) & {".git", "site", "node_modules"})
               and not any(part.startswith(".venv") for part in path.relative_to(SUITE).parts)}
    assert folders <= listed, f"CI's pytest matrix misses {sorted(folders - listed)}"


def test_each_suite_has_its_own_ci_and_release_workflows():
    """A change to one suite never touches another's checks or releases (owner, 27-10-2026). A suite with a tag
    prefix has its own ci-<suite>.yml and release-<suite>.yml, which name no other suite's folder; ci.yml and
    release.yml (Nexus and the plain-tag suite, bc250-bazzite) name no prefixed suite's folder, and release.yml leaves
    the prefixed tags alone."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("nexus_suites", SUITE / "tools" / "suites.py")
    suites = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(suites)
    workflows = SUITE / ".github" / "workflows"
    names = [folder.name for folder in _suites()]
    plain = [folder.name for folder in _suites() if not suites.tag_prefix(folder)]
    for folder in _suites():
        prefix = suites.tag_prefix(folder)
        if not prefix:
            continue
        own = [workflows / f"ci-{folder.name}.yml", workflows / f"release-{folder.name}.yml"]
        for workflow in own:
            assert workflow.is_file(), f"{folder.name} has no {workflow.name}"
            text = workflow.read_text(encoding="utf-8")
            assert not [name for name in names if name != folder.name and f"{name}/" in text], workflow.name
        assert f'tags: ["{prefix}*-v' in own[1].read_text(encoding="utf-8")
        for shared in ("ci.yml", "release.yml"):
            assert f"{folder.name}/" not in (workflows / shared).read_text(encoding="utf-8"), shared
        assert f'"!{prefix}*"' in (workflows / "release.yml").read_text(encoding="utf-8")
    assert plain == ["bc250-bazzite"]


def test_nexus_checks_have_a_workflow_of_their_own():
    """Nexus's shared checks (core, tools, dev/, the repository's rules) run in ci-nexus.yml, apart from every
    suite's CI, so a failure there is Nexus's and holds every suite's tags alike: tools/tag-release.sh and the ci
    job of each release workflow wait for it besides the suite's own CI (owner, 27-10-2026)."""
    workflows = SUITE / ".github" / "workflows"
    nexus = (workflows / "ci-nexus.yml").read_text(encoding="utf-8")
    assert not [folder.name for folder in _suites() if f"{folder.name}/" in nexus], "ci-nexus.yml names a suite"
    shared = {"core", "tools"} | {f"dev/{p.name}" for p in (SUITE / "dev").iterdir() if (p / "tests").is_dir()}
    matrix = re.search(r"dir: \[([^\]]*)\]", nexus).group(1)
    assert {entry.strip() for entry in matrix.split(",")} == shared
    for folder in _suites():
        own = workflows / (f"ci-{folder.name}.yml" if (workflows / f"ci-{folder.name}.yml").is_file() else "ci.yml")
        matrix = re.search(r"dir: \[([^\]]*)\]", own.read_text(encoding="utf-8")).group(1)
        entries = {entry.strip() for entry in matrix.split(",")}
        assert not entries & (shared - {"core"}), f"{own.name} runs Nexus's tests"   # core: a suite may run it too
    for release in sorted(workflows.glob("release*.yml")):
        assert "ci_state.py --workflow ci-nexus.yml" in release.read_text(encoding="utf-8"), release.name
    assert "workflows+=(ci-nexus.yml)" in (SUITE / "tools" / "tag-release.sh").read_text(encoding="utf-8")
