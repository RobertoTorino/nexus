# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/new_app.py writes a new app of a suite as the architecture chapter describes it, and lists it wherever the
suite lists its apps, on a small repository laid out as Nexus is."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SUITE = "bc250-bazzite"
ICONS = ROOT / SUITE / "icons" / "utilities"

spec = importlib.util.spec_from_file_location("new_app", ROOT / "tools" / "new_app.py")
na = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = na
spec.loader.exec_module(na)

MANIFEST = '''# the pins

[apps.alpha]
name = "Alpha"
summary = "s"
tag = "alpha-v0.1.0"
sha256 = ""
required = true
changes_board = false
category = "sustainable"
install = ["bash install.sh"]
uninstall = ["bash install.sh --uninstall"]
detect = ["~/.local/bin/bc250-alpha"]
'''

INDEX = '''# The apps

**Sustainable**: the board itself.

| App | What it does |
|---|---|
| ![](../assets/apps/alpha.webp){ .app-icon } [Alpha](alpha.md) | s |

**Utilities**: handy tools around the board.

| App | What it does |
|---|---|
| ![](../assets/apps/beta.webp){ .app-icon } [Beta](beta.md) | t |

Apps that **change the board** ask first.
'''

CATEGORIES_MD = '''# App categories

| App | Category |
|---|---|
| ![](../assets/apps/alpha.webp){ .app-icon } [Alpha](alpha.md) | Sustainable |
| ![](../assets/apps/beta.webp){ .app-icon } [Beta](beta.md) | Utilities |
| ![](../assets/apps/mtool.webp){ .app-icon } [Media Tool](../other-tools/media-tool.md) | Development |
'''

README = '''# BC250 Bazzite Suite

**Sustainable**: the board itself.

- <img src="portal/images/apps/alpha.webp" width="20" height="20" alt=""/> **[Alpha](apps/alpha)**: s

**Utilities**: handy tools around the board.

- <img src="portal/images/apps/beta.webp" width="20" height="20" alt=""/> **[Beta](apps/beta)**: t

How to install and use them: the wiki.
'''

MKDOCS = '''site_name: BC250 Bazzite Suite
site_url: https://example.invalid/nexus/bc250-bazzite-suite/
nav:
  - Home: index.md
  - Apps:
      - apps/index.md
      - Alpha: apps/alpha.md
  - Development:
      - development/index.md
'''

CATALOG = '''# Runtime dependencies. [[tool]] a tool; [[dependency]] a Python package.

[app.portal]
name = "Portal"
launchers = ["~/.local/bin/bc250-bazzite-suite"]

[app.alpha]
name = "Alpha"
launchers = ["~/.local/bin/bc250-alpha"]

[[tool]]
name = "pkexec"
description = "Runs a command as root."
executables = ["pkexec"]

[[dependency]]
name = "PyQt6"
description = "Qt 6."

[[dependency.source]]
owner = "portal"
specifier = ">=6.11,<7"

[[dependency.source]]
owner = "alpha"
specifier = ">=6.11,<7"

[[dependency]]
name = "pillow"
description = "Pictures."

[[dependency.source]]
owner = "alpha"
specifier = ">=10"
'''

CI = '''jobs:
  pytest:
    strategy:
      matrix:
        dir: [bc250-bazzite/portal,
              bc250-bazzite/apps/alpha]   # every folder with tests/
  shell:
    steps:
      - name: shellcheck (warnings)
        run: |
          shellcheck -S warning bc250-bazzite/apps/alpha/install.sh
          shellcheck -S warning bc250-bazzite/tools/check-release.sh

      # The repository's rules: ci-nexus.yml.
      - name: Every former repo has its LICENSE, .gitignore, VERSION and CHANGELOG
        run: ls
  installers:
    steps:
      - name: alpha installer
        run: bash bc250-bazzite/tools/installer-tests/alpha.sh
      - name: release tarballs, end to end
        run: bash bc250-bazzite/tools/installer-tests/release.sh
'''


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def checkout(tmp_path) -> Path:
    """A repository laid out as Nexus is: core at the root, one suite with the files the generator lists an app
    in, the suite's sync_icons.py (the real one) and one category's icons."""
    root = tmp_path / "nexus"
    suite = root / SUITE
    write(root / "core" / "bc250_core" / "__init__.py", "")
    write(suite / "portal" / "apps.toml", MANIFEST)
    write(root / "portal" / "apps.toml", MANIFEST)                       # the root's copy, identical
    write(suite / "portal" / "bc250_portal" / "__init__.py", 'APP_NAME = "BC250 Bazzite Suite"\nAPP_ID = "bc250-bazzite-suite"\n')
    write(suite / "portal" / "LICENSE", "GPL-3.0-or-later\n")
    write(suite / "mkdocs.yml", MKDOCS)
    write(suite / "docs" / "apps" / "index.md", INDEX)
    write(suite / "docs" / "apps" / "categories.md", CATEGORIES_MD)
    write(suite / "README.md", README)
    write(suite / "icons" / "categories.toml", "# the apps' icons\n")
    (suite / "icons" / "utilities").mkdir(parents=True)
    for size, kind in ((1024, "webp"), (512, "webp"), (256, "webp"), (128, "png")):   # real pictures: sync_icons reads them
        shutil.copy(ICONS / f"utilities-{size}.{kind}", suite / "icons" / "utilities" / f"utilities-{size}.{kind}")
    (suite / "tools" / "installer-tests").mkdir(parents=True)
    shutil.copy(ROOT / SUITE / "tools" / "sync_icons.py", suite / "tools" / "sync_icons.py")
    write(suite / "apps" / "package" / "package_checker" / "dependencies.toml", CATALOG)
    write(root / ".github" / "workflows" / "ci.yml", CI)
    return root


def test_defaults():
    assert na.default_package("BC-250 Fan Control") == "fan_control"
    assert na.default_package("Bazzite NetcatGUI") == "netcatgui"
    assert na.default_package("USB IPS3.5") == "usb_ips3_5"
    assert na.default_package("3D Thing") == "app_3d_thing"
    suite = na.read_suite(ROOT, SUITE)
    assert (suite.name, suite.app_id, suite.prefix, suite.core) == ("BC250 Bazzite Suite", "bc250-bazzite-suite",
                                                                   "bc250", "bc250_core")
    assert suite.wiki == "https://robertotorino.github.io/nexus/bc250-bazzite-suite/"
    assert suite.categories == ("sustainable", "graphics", "gaming", "utilities")      # no Development tab


def test_writes_the_app_and_lists_it_everywhere(checkout, capsys):
    assert na.main([SUITE, "fan2", "BC-250 Fan Two", "--summary", "A second fan.", "--no-check", "--root",
                    str(checkout)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("BC-250 Fan Two (bc250-bazzite/apps/fan2, package fan_two, id bc250-fan2, utilities):")
    suite = checkout / SUITE
    app = suite / "apps" / "fan2"
    for name in ("fan_two/__init__.py", "fan_two/__main__.py", "fan_two/main_window.py", "tests/conftest.py",
                 "tests/test_main_window.py", "install.sh", "requirements.txt", "requirements-dev.txt", "VERSION",
                 "CHANGELOG", "LICENSE", ".gitignore", "README.md", "images/bc250-fan2.webp",
                 "images/bc250-fan2-128.png"):
        assert (app / name).is_file(), name
    assert (app / "VERSION").read_text() == "0.1.0\n" and (app / "LICENSE").read_text() == "GPL-3.0-or-later\n"
    assert (app / "CHANGELOG").read_text().startswith("Changelog: ") and "\n\nAdded. BC-250 Fan Two" in (app / "CHANGELOG").read_text()
    init = (app / "fan_two" / "__init__.py").read_text()
    assert 'APP_NAME = "BC-250 Fan Two"' in init and 'APP_ID = "bc250-fan2"' in init and '__version__ = "0.1.0"' in init
    assert 'tag_prefix="fan2-v"' in init and "from bc250_core import AppInfo" in init
    for name in ("fan_two/__init__.py", "fan_two/__main__.py", "fan_two/main_window.py", "tests/conftest.py",
                 "tests/test_main_window.py"):
        compile((app / name).read_text(), name, "exec")                   # valid Python
    window = (app / "fan_two" / "main_window.py").read_text()
    assert "AppHeader(LOGO_PATH, APP_NAME, __version__)" in window and "A second fan." in window
    # The installer: the standard options, the refusal of root, pip --upgrade -r (tools/tests/test_layout.py).
    installer = (app / "install.sh").read_text()
    for option in ("--no-desktop-shortcut)", "--uninstall)", "--purge)", "--help)"):
        assert option in installer
    assert "only goes with --uninstall" in installer and "not with sudo" in installer
    assert "--upgrade -r" in installer and 'APP_ID="bc250-fan2"' in installer and "-m fan_two" in installer
    assert "bc250-bazzite-suite/venv" in installer.replace("$DATA_DIR/bc250-bazzite-suite", "x/bc250-bazzite-suite/venv")
    test = suite / "tools" / "installer-tests" / "fan2.sh"
    if sys.platform != "win32":                               # Windows has no exec bits (git has them)
        assert (app / "install.sh").stat().st_mode & 0o111 and test.stat().st_mode & 0o111
    assert "apps/fan2/install.sh" in test.read_text()
    assert "--suite bc250-bazzite fan2" in test.read_text()
    if shutil.which("bash"):
        subprocess.run(["bash", "-n", str(app / "install.sh"), str(test)], check=True)
    # The icons: copies of the category's, written by sync_icons.py; the tile too.
    assert (app / "images" / "bc250-fan2.webp").read_bytes() == (ICONS / "utilities-512.webp").read_bytes()
    assert (app / "images" / "bc250-fan2-128.png").read_bytes() == (ICONS / "utilities-128.png").read_bytes()
    assert (suite / "portal" / "images" / "apps" / "fan2.webp").read_bytes() == (ICONS / "utilities-256.webp").read_bytes()
    categories = (suite / "icons" / "categories.toml").read_text()
    assert '[fan2]\ncategory = "utilities"\nicons = ["apps/fan2/images/bc250-fan2"]\ntile = "portal/images/apps/fan2.webp"' in categories
    # The portal's manifest, at its end, and the root's copy with it.
    manifest = (suite / "portal" / "apps.toml").read_text()
    entry = manifest.index("[apps.fan2]")
    assert manifest.index("[apps.alpha]") < entry
    assert 'tag = "fan2-v0.1.0"\nsha256 = ""' in manifest and 'detect = ["~/.local/bin/bc250-fan2"]' in manifest
    assert "\n\n[apps.fan2]" in manifest and manifest.endswith("]]\n")
    assert (checkout / "portal" / "apps.toml").read_text() == manifest
    # The wiki: the chapter with its icon, the nav before Development, the rows in the category's table.
    chapter = (suite / "docs" / "apps" / "fan2.md").read_text()
    assert "![BC-250 Fan Two](../assets/fan2/bc250-fan2.webp){ .app-logo }\n\n# BC-250 Fan Two" in chapter
    nav = (suite / "mkdocs.yml").read_text()
    assert "      - Alpha: apps/alpha.md\n      - BC-250 Fan Two: apps/fan2.md\n  - Development:" in nav
    index = (suite / "docs" / "apps" / "index.md").read_text()
    assert ("[Beta](beta.md) | t |\n| ![](../assets/apps/fan2.webp){ .app-icon } [BC-250 Fan Two](fan2.md) | "
            "A second fan. |\n\nApps that") in index
    table = (suite / "docs" / "apps" / "categories.md").read_text()
    assert ("[Beta](beta.md) | Utilities |\n| ![](../assets/apps/fan2.webp){ .app-icon } [BC-250 Fan Two](fan2.md) "
            "| Utilities |\n| ![](../assets/apps/mtool.webp)") in table
    readme = (suite / "README.md").read_text()
    assert ("**[Beta](apps/beta)**: t\n- <img src=\"portal/images/apps/fan2.webp\" width=\"20\" height=\"20\" alt=\"\"/> "
            "**[BC-250 Fan Two](apps/fan2)**: A second fan.\n\nHow to install") in readme
    # The Dependency Checker's catalog: the app before the tools, PyQt6 with the app as a source.
    catalog = (suite / "apps" / "package" / "package_checker" / "dependencies.toml").read_text()
    assert ('launchers = ["~/.local/bin/bc250-alpha"]\n\n[app.fan2]\nname = "BC-250 Fan Two"\n'
            'launchers = ["~/.local/bin/bc250-fan2"]\n\n[[tool]]') in catalog
    assert ('owner = "alpha"\nspecifier = ">=6.11,<7"\n\n[[dependency.source]]\nowner = "fan2"\n'
            'specifier = ">=6.11,<7"\n\n[[dependency]]\nname = "pillow"') in catalog
    import tomllib
    assert tomllib.loads(catalog)["app"]["fan2"]["name"] == "BC-250 Fan Two"
    assert tomllib.loads(manifest)["apps"]["fan2"]["category"] == "utilities"
    # CI: the pytest matrix, the installer step and the shellcheck list.
    ci = (checkout / ".github" / "workflows" / "ci.yml").read_text()
    assert "bc250-bazzite/apps/alpha, bc250-bazzite/apps/fan2]   # every folder with tests/" in ci
    assert ("shellcheck -S warning bc250-bazzite/tools/check-release.sh\n"
            "          shellcheck -S warning bc250-bazzite/apps/fan2/install.sh"
            "\n\n      # The repository's rules") in ci
    assert ("      - name: fan2 installer\n        run: bash bc250-bazzite/tools/installer-tests/fan2.sh\n"
            "      - name: release tarballs") in ci


def test_names_are_the_owners(checkout):
    assert na.main([SUITE, "cam", "USB Cam Thing", "--id", "bc250-usb-cam", "--package", "usb_cam", "--category",
                    "utilities", "--no-check", "--root", str(checkout)]) == 0
    init = (checkout / SUITE / "apps" / "cam" / "usb_cam" / "__init__.py").read_text()
    assert 'APP_ID = "bc250-usb-cam"' in init
    assert (checkout / SUITE / "apps" / "cam" / "install.sh").read_text().count("-m usb_cam") == 1


@pytest.mark.parametrize("argv, message", [
    (["nope", "x", "X"], "not a suite"),
    ([SUITE, "Bad Name", "X"], "not a name"),
    ([SUITE, "x", "X", "--category", "games"], "not a category"),
    ([SUITE, "x", "X", "--package", "Not-Valid"], "not a package name"),
    ([SUITE, "x", "X", "--id", "Bad_Id"], "not an app id"),
    ([SUITE, "alpha", "Alpha again"], "exists already"),
])
def test_refusals(checkout, argv, message):
    (checkout / SUITE / "apps" / "alpha").mkdir(parents=True, exist_ok=True)
    with pytest.raises(SystemExit, match=message):
        na.main([*argv, "--no-check", "--root", str(checkout)])
    assert not (checkout / SUITE / "apps" / "x").exists()


def test_a_suite_without_a_template_is_refused(checkout):
    write(checkout / "windows-portable" / "portal" / "apps.toml", "[apps.check]\n")
    write(checkout / "windows-portable" / "portal" / "nexus_portable_portal" / "__init__.py", 'APP_NAME = "W"\nAPP_ID = "w"\n')
    with pytest.raises(SystemExit, match="no app template yet"):
        na.main(["windows-portable", "x", "X", "--no-check", "--root", str(checkout)])


def test_the_help_names_the_steps():
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "new_app.py"), "--help"], capture_output=True,
                            text=True)
    assert result.returncode == 0 and "--category" in result.stdout and "architecture chapter" in result.stdout


WINDOWS = "windows-portable"
W_MANIFEST = '''# the pins

[apps.test]
name = "Windows Portable Test"
summary = "s"
tag = "wp-test-v0.1.0"
required = true
category = "sustainable"
install = ["i"]
uninstall = ["u"]
detect = ["d"]
'''

W_MKDOCS = '''site_name: Windows Portable Suite
site_url: https://example.invalid/nexus/windows-portable-suite/
nav:
  - Home: index.md
  - Portal: portal.md
  - Apps:
      - Windows Portable Test: apps/test.md
'''

W_HOME = '''# Windows Portable Suite

## The apps

| App | What it does |
|---|---|
| [Portal](portal.md) | Installs the apps. |
| [Windows Portable Test](apps/test.md) | The handheld. |

## Get started
'''

W_CI = '''jobs:
  pytest:
    strategy:
      matrix:
        dir: [core, windows-portable/portal,
              windows-portable/apps/test]   # every folder of the suite with tests/, and core, which its apps bundle
  installers:
    steps:
      - name: "Installer test: test"
        run: powershell -File windows-portable/tools/installer-tests/test.ps1
      - name: "Installer test: releases"
        run: powershell -File windows-portable/tools/installer-tests/releases.ps1
      - name: "Build the release zip, not published: test"
        run: python build
      - name: "Build the release zip, not published: portal"
        run: python build portal
'''


@pytest.fixture
def windows_checkout(tmp_path) -> Path:
    """A repository with a Windows suite laid out as the Windows Portable Suite is: its portal package with the
    categories, TAG_PREFIX, the wiki's nav and home, the gaming category's icons, the suite's CI, and the real
    tools/make_icons.py, which copies the app's icons."""
    root = tmp_path / "nexus"
    suite = root / WINDOWS
    write(root / "core" / "bc250_core" / "__init__.py", "")
    write(suite / "portal" / "apps.toml", W_MANIFEST)
    write(suite / "portal" / "portable_portal" / "__init__.py",
          'APP_NAME = "Windows Portable Suite"\nAPP_ID = "windows-portable-suite"\n')
    write(suite / "portal" / "portable_portal" / "manifest.py",
          'CATEGORIES = {"sustainable": "Sustainable", "graphics": "Graphics", "gaming": "Gaming", '
          '"utilities": "Utilities"}\n')
    write(suite / "portal" / "LICENSE", "GPL-3.0-or-later\n")
    write(suite / "TAG_PREFIX", "wp-\n")
    write(suite / "mkdocs.yml", W_MKDOCS)
    write(suite / "docs" / "index.md", W_HOME)
    (suite / "icons" / "gaming").mkdir(parents=True)
    for size in (1024, 512, 256, 128):
        shutil.copy(ROOT / WINDOWS / "icons" / "gaming" / f"gaming-{size}.png", suite / "icons" / "gaming")
    (suite / "tools" / "installer-tests").mkdir(parents=True)
    (root / "tools").mkdir()
    shutil.copy(ROOT / "tools" / "make_icons.py", root / "tools" / "make_icons.py")
    write(root / ".github" / "workflows" / "ci-windows-portable.yml", W_CI)
    return root


def test_a_windows_suites_app(windows_checkout, capsys):
    root = windows_checkout
    assert na.main([WINDOWS, "emu", "Emu Manager", "--category", "gaming", "--summary", "An emulator.", "--no-check",
                    "--root", str(root)]) == 0
    assert capsys.readouterr().out.startswith(
        "Emu Manager (windows-portable/apps/emu, package emu_manager, id windows-portable-emu, gaming):")
    suite = root / WINDOWS
    app = suite / "apps" / "emu"
    for name in ("emu_manager/__init__.py", "emu_manager/__main__.py", "emu_manager/main_window.py",
                 "tests/conftest.py", "tests/test_main_window.py", "install.ps1", "run.ps1", "requirements.txt",
                 "requirements-dev.txt", "VERSION", "CHANGELOG", "LICENSE", ".gitignore", "README.md"):
        assert (app / name).is_file(), name
        if name.endswith(".py"):
            compile((app / name).read_text(), name, "exec")
    init = (app / "emu_manager" / "__init__.py").read_text()
    assert 'APP_ID = "windows-portable-emu"' in init and 'EXE_NAME = "Emu-Manager"' in init
    assert 'tag_prefix="wp-emu-v"' in init and 'SUITE = "windows-portable-suite"' in init
    assert "PortableWindow" in (app / "emu_manager" / "main_window.py").read_text()
    installer = (app / "install.ps1").read_text()
    for option in ("'--no-desktop-shortcut'", "'--uninstall'", "'--purge'", "'--help'"):
        assert option in installer
    assert "not as administrator" in installer and "$Exe = 'Emu-Manager.exe'" in installer
    assert "(wp-emu-v<x.y.z>.zip" in installer and "\n# Installs Emu Manager from" in installer
    test = (suite / "tools" / "installer-tests" / "emu.ps1").read_text()
    assert "$env:WPS_DESKTOP_DIR = " in test and test.index("$env:WPS_DESKTOP_DIR = ") < test.index("Run 'log1'")
    assert r"apps\emu\install.ps1" in test and r"Start Menu\Programs\Windows Portable Suite" in test
    # The icons: the category's, copied by tools/make_icons.py.
    from PIL import Image
    assert Image.open(app / "images" / "windows-portable-emu.webp").size == (512, 512)
    assert Image.open(app / "images" / "windows-portable-emu-128.png").size == (128, 128)
    assert Image.open(suite / "portal" / "images" / "apps" / "emu.webp").size == (128, 128)
    assert Image.open(suite / "docs" / "images" / "apps" / "emu.webp").size == (256, 256)
    import tomllib
    entry = tomllib.loads((suite / "portal" / "apps.toml").read_text())["apps"]["emu"]
    assert entry["tag"] == "wp-emu-v0.1.0" and entry["category"] == "gaming" and "required" not in entry
    assert entry["detect"] == [r"%LOCALAPPDATA%\windows-portable-suite\windows-portable-emu\app\Emu-Manager.exe"]
    chapter = (suite / "docs" / "apps" / "emu.md").read_text()
    assert "![Emu Manager](../images/apps/emu.webp){ .app-logo }\n\n# Emu Manager\n\nAn emulator." in chapter
    assert "**Gaming** tab" in chapter and "wp-emu-v<x.y.z>.zip" in chapter
    assert "      - Windows Portable Test: apps/test.md\n      - Emu Manager: apps/emu.md\n" in \
        (suite / "mkdocs.yml").read_text()
    assert "| The handheld. |\n| [Emu Manager](apps/emu.md) | An emulator. |\n\n## Get started" in \
        (suite / "docs" / "index.md").read_text()
    ci = (root / ".github" / "workflows" / "ci-windows-portable.yml").read_text()
    assert "windows-portable/apps/test,\n              windows-portable/apps/emu]   # every folder" in ci
    assert ('      - name: "Installer test: emu"\n        run: powershell -NoProfile -ExecutionPolicy Bypass -File '
            'windows-portable/tools/installer-tests/emu.ps1\n      - name: "Installer test: releases"') in ci
    assert ('wpdist/emu\n      - name: "Installer test on the release: emu"') in ci
    assert ci.index('not published: emu"') < ci.index('not published: portal"')


def test_a_windows_category_without_icons_is_refused(windows_checkout):
    with pytest.raises(SystemExit, match="has no icons yet"):
        na.main([WINDOWS, "tool", "A Tool", "--category", "utilities", "--no-check", "--root", str(windows_checkout)])
