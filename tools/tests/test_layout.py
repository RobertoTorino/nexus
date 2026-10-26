# SPDX-License-Identifier: GPL-3.0-or-later
"""Every app of every suite has the same layout: its Python package(s) and images/ directly in <suite>/apps/<name>/, no
wrapper folder."""

from __future__ import annotations

import re
from pathlib import Path

SUITE = Path(__file__).resolve().parents[2]         # the checkout
SKIP = {"tests", "__pycache__", ".pytest_cache"}


def _suites() -> list[Path]:
    """Every suite: a folder under the root with portal/apps.toml."""
    return sorted(p for p in SUITE.iterdir() if p.is_dir() and (p / "portal" / "apps.toml").is_file())


def _apps() -> list[Path]:
    return sorted(path for suite in _suites() for path in (suite / "apps").iterdir() if (path / "VERSION").is_file())


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


def _installers() -> list[Path]:
    return [*(app / "install.sh" for app in _apps()),
            *(p for suite in _suites() for p in (suite / "portal" / "install.sh", suite / "tools" / "installer-tests" / "gui" / "install.sh"))]


def test_every_app_has_an_installer_at_its_root():
    missing = [app.name for app in _apps() if not (app / "install.sh").is_file()]
    assert not missing, f"no install.sh at the app root: {', '.join(missing)}"


def test_installers_take_the_standard_options_and_refuse_root():
    """--no-desktop-shortcut, --uninstall, --uninstall --purge, --help; run as your own user, not with sudo."""
    for installer in _installers():
        text = installer.read_text(encoding="utf-8")
        for option in ("--no-desktop-shortcut)", "--uninstall)", "--purge)", "--help)"):
            assert option in text, f"{installer.relative_to(SUITE)} does not handle {option.rstrip(')')}"
        assert "only goes with --uninstall" in text, f"{installer.relative_to(SUITE)} accepts --purge alone"
        assert "not with sudo" in text, f"{installer.relative_to(SUITE)} does not refuse to run as root"


def test_installers_upgrade_the_python_packages():
    """pip install -r with --upgrade: installing again brings each package to the newest version its requirements
    allow, a security fix within the range included (owner's decision, 13-10-2026)."""
    installers = sorted([*SUITE.glob("*/apps/*/install.sh"), *SUITE.glob("*/apps/*/packaging/*/*.sh"),
                         *SUITE.glob("*/portal/install.sh")])
    calls = [(path, line) for path in installers for line in path.read_text(encoding="utf-8").splitlines()
             if re.search(r"\bpip\"? install\b.* -r ", line) and not line.lstrip().startswith("#")]
    assert len(calls) >= 18
    assert [(path.relative_to(SUITE), line) for path, line in calls if "--upgrade -r" not in line] == []


def test_every_app_has_tests_and_ci_runs_them():
    import re
    for app in _apps():
        assert (app / "tests").is_dir(), f"{app.name}: no tests/"
        assert (app / "requirements-dev.txt").is_file(), f"{app.name}: no requirements-dev.txt (CI installs it)"
    ci = (SUITE / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    matrix = re.search(r"dir: \[([^\]]*)\]", ci).group(1)
    listed = {entry.strip() for entry in matrix.replace("\n", " ").split(",")}
    folders = {str(path.parent.relative_to(SUITE)) for path in SUITE.glob("**/tests")
               if path.is_dir() and not (set(path.relative_to(SUITE).parts) & {".git", "site", "node_modules"})
               and not any(part.startswith(".venv") for part in path.relative_to(SUITE).parts)}
    assert folders <= listed, f"CI's pytest matrix misses {sorted(folders - listed)}"
