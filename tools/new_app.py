#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""A new app of a suite, written from the architecture chapter, so the template cannot drift from the checks:

    python3 tools/new_app.py <suite> <name> "<App Name>" [--id APP_ID] [--package PACKAGE] [--category CATEGORY]
                             [--summary TEXT] [--no-check]

It writes <suite>/apps/<name>/ (the package with __main__.py and a window on AppHeader, images/, tests/, install.sh,
the requirements, VERSION 0.1.0, CHANGELOG, LICENSE, .gitignore and README.md), the installer test
<suite>/tools/installer-tests/<name>.sh and the wiki chapter <suite>/docs/apps/<name>.md, and lists the app wherever
the suite lists its apps: portal/apps.toml (and the root's copy while there is one), icons/categories.toml (with the
icon copies, tools/sync_icons.py), mkdocs.yml, docs/apps/index.md and categories.md, the suite README, the Dependency
Checker's catalog, and the pytest matrix, the installer step and the shellcheck list of .github/workflows/ci.yml.
Then it runs the checks on it (the layout test, the app's tests, the suite's installer, icon and manifest tests, the
catalog tests) unless --no-check. The portal bump the new entry asks for, the app's CHANGELOG and its release stay
the owner's.

Each suite has its template behind the same command: so far the BC250 Bazzite Suite's (a Linux app on the shared
venv, with the suite's installer). A suite without one is refused."""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATEGORIES = ("sustainable", "graphics", "gaming", "utilities")   # the portal's, when it has none
DESKTOP_CATEGORIES = {"sustainable": "System;", "graphics": "Game;Graphics;", "gaming": "Game;",
                      "utilities": "Utility;"}
TEMPLATES = {"bc250_portal": "bazzite"}     # the suite's portal package names its template
_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
_PREFIXES = ("BC-250 ", "BC250 ", "Bazzite ")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class Suite:
    """What the template takes from the suite: its folder, its name and id (the portal's), its wiki's address, its
    categories and the core package every app bundles."""
    folder: Path                        # <root>/bc250-bazzite
    name: str                           # "BC250 Bazzite Suite"
    app_id: str                         # "bc250-bazzite-suite": the shared venv's folder
    wiki: str                           # "https://robertotorino.github.io/nexus/bc250-bazzite-suite/"
    categories: tuple[str, ...]
    core: str                           # "bc250_core"
    template: str                       # "bazzite"

    @property
    def prefix(self) -> str:
        """The first word of the suite's id, for an app id: bc250-<name>."""
        return self.app_id.split("-")[0]


def read_suite(root: Path, name: str) -> Suite:
    folder = root / name
    if not (folder / "portal" / "apps.toml").is_file():
        suites = sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "portal" / "apps.toml").is_file())
        raise SystemExit(f"{name} is not a suite of {root} (the suites: {', '.join(suites) or 'none'})")
    packages = [p for p in (folder / "portal").iterdir() if p.is_dir() and (p / "__init__.py").is_file()]
    if len(packages) != 1:
        raise SystemExit(f"{name}/portal has no portal package (one folder with __init__.py)")
    if packages[0].name not in TEMPLATES:
        raise SystemExit(f"{name} has no app template yet (its portal is {packages[0].name}; the templates: "
                         f"{', '.join(TEMPLATES)})")
    init = (packages[0] / "__init__.py").read_text(encoding="utf-8")
    consts = dict(re.findall(r'^(APP_NAME|APP_ID)\s*=\s*"([^"]+)"', init, re.M))
    if "APP_NAME" not in consts or "APP_ID" not in consts:
        raise SystemExit(f"{packages[0].relative_to(root)}/__init__.py sets no APP_NAME and APP_ID")
    categories = CATEGORIES
    if (packages[0] / "manifest.py").is_file():
        categories = tuple(_load("new_app_manifest", packages[0] / "manifest.py").CATEGORIES)
    config = folder / "mkdocs.yml"
    site = re.search(r"^site_url:\s*(\S+)", config.read_text(encoding="utf-8"), re.M) if config.is_file() else None
    cores = [p.name for p in (root / "core").iterdir() if p.is_dir() and (p / "__init__.py").is_file()] \
        if (root / "core").is_dir() else []
    if len(cores) != 1:
        raise SystemExit(f"{root}/core has no core package (one folder with __init__.py)")
    return Suite(folder, consts["APP_NAME"], consts["APP_ID"], site[1].rstrip("/") + "/" if site else "",
                 categories, cores[0], TEMPLATES[packages[0].name])


@dataclass
class NewApp:
    """The names of the app: the folder (its key), the shown name, the app id, the package, the category, the
    one-line summary."""
    name: str
    app_name: str
    app_id: str
    package: str
    category: str
    summary: str

    @property
    def category_title(self) -> str:
        return self.category.title()


def default_package(app_name: str) -> str:
    """The app's name without its BC-250 or Bazzite prefix, as a Python identifier: "BC-250 Fan Control" ->
    fan_control."""
    for prefix in _PREFIXES:
        if app_name.startswith(prefix):
            app_name = app_name[len(prefix):]
    package = re.sub(r"[^a-z0-9]+", "_", app_name.lower()).strip("_")
    return package if package and not package[0].isdigit() else f"app_{package}"


def amsterdam_now() -> str:
    """The CHANGELOG's time, Europe/Amsterdam (CLAUDE.md)."""
    try:
        import zoneinfo
        now = datetime.datetime.now(zoneinfo.ZoneInfo("Europe/Amsterdam"))
    except (ImportError, KeyError):       # Windows without tzdata: the machine's time, which CLAUDE.md warns about
        now = datetime.datetime.now()
    return now.strftime("%d-%m-%Y %H:%M:%S")


# --- The template of the BC250 Bazzite Suite -------------------------------------------------------------------
# Each file as the architecture chapter describes it; @WORD@ is replaced (fill()).

INIT_PY = '''# SPDX-License-Identifier: GPL-3.0-or-later
"""@SUMMARY@"""

APP_NAME = "@APP_NAME@"
APP_ID = "@APP_ID@"
__version__ = "0.1.0"

from pathlib import Path

from @CORE@ import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/@APP_ID@/@APP_ID@.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="@NAME@-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
'''

MAIN_PY = '''# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m @PACKAGE@"""

from __future__ import annotations

import argparse
import sys

from @CORE@ import __version__ as CORE_VERSION, instance
from @CORE@.app import create_app, exec_app

from . import APP_NAME, INFO, __version__
from .main_window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(prog="@PACKAGE@", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    _args, qt_args = parser.parse_known_args()

    app = create_app(INFO, qt_args)
    if instance.already_running(INFO.app_id):       # a second launch brings the open window to the front
        return 0
    window = MainWindow()
    window.show()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
'''

WINDOW_PY = '''# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's header (the icon at 96 px, the name with the version, the state beside it, Refresh at the
right end, a status box on the second row) and the page below it."""

from __future__ import annotations

from PyQt6.QtWidgets import QMainWindow, QPushButton, QVBoxLayout, QWidget

from @CORE@.theme import GREY
from @CORE@.widgets import AppHeader, MetricBox, StatusText, hint_label

from . import APP_NAME, LOGO_PATH, __version__


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(900, 600)
        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.state = StatusText()
        header.add_state(self.state)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Read again")
        self.refresh_button.clicked.connect(self.refresh)
        header.add_action(self.refresh_button)
        self.status_box = MetricBox("Status")
        header.add_second(self.status_box)
        contents = QWidget()
        layout = QVBoxLayout(contents)
        layout.addLayout(header)
        layout.addWidget(hint_label("@SUMMARY@"))
        layout.addStretch(1)
        self.setCentralWidget(contents)
        self.refresh()

    def refresh(self) -> None:
        """Reads what the window shows; the state and the status box follow it."""
        self.state.set_status("Ready", "ok")
        self.status_box.set_value("\\u2014", "Nothing to show yet.")
        self.status_box.set_colour(GREY)
'''

CONFTEST_PY = '''# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, @CORE@ from the checkout and settings in a temp folder."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # @CORE@ from the checkout, as the installer bundles it


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def settings_dir(tmp_path):
    """The app keeps an .ini (AppInfo.settings_ini), so this also keeps the tests out of the Windows registry."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    return tmp_path / "settings"
'''

TEST_WINDOW_PY = '''# SPDX-License-Identifier: GPL-3.0-or-later
"""The window opens offscreen with the suite's header; the version and the icons are where the checks expect them."""

from __future__ import annotations

from @PACKAGE@ import APP_ID, APP_NAME, INFO, LOGO_PATH, ROOT, __version__
from @PACKAGE@.main_window import MainWindow


def test_version_is_the_single_source():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__ == INFO.version


def test_icons_are_beside_the_package():
    assert LOGO_PATH.is_file() and LOGO_PATH.name == f"{APP_ID}.webp"
    assert (ROOT / "images" / f"{APP_ID}-128.png").is_file()


def test_window_opens_with_the_suites_header(qapp):
    window = MainWindow()
    window.show()
    assert window.windowTitle() == APP_NAME
    assert window.state.text() == "Ready" and window.state.kind == "ok"
    assert window.status_box.caption.text() == "Status"
    window.refresh()
    window.close()
'''

INSTALL_SH = '''#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs @APP_NAME@ as a desktop app, from a clone or the extracted release tarball:
#
#   ./install.sh                         # install or update
#   ./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
#   ./install.sh --uninstall             # remove the app; keeps its settings
#   ./install.sh --uninstall --purge     # also remove its settings
#
# Run it as your own user; it needs no root.
#  * ~/.local/share/@APP_ID@/app: the app, with the @CORE@ it was tested with (bundled in the release; taken from
#    the suite checkout when run from there).
#  * ~/.local/share/@VENV_ID@/venv, the @SUITE_NAME@'s shared venv with PyQt6 (the wheels bundle Qt; nothing is
#    layered). It is removed with the last suite app that uses it.
#  * ~/.local/bin/@APP_ID@ to start it from a terminal, plus an app menu entry and a Desktop icon.
set -euo pipefail

APP_ID="@APP_ID@"
APP_NAME="@APP_NAME@"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
APP_DIR="$DATA_DIR/$APP_ID/app"
SUITE_DIR="$DATA_DIR/@VENV_ID@"
VENV="$SUITE_DIR/venv"                       # shared by the suite's apps
VENV_USERS="$SUITE_DIR/venv-users"           # one file per app that uses it
LAUNCHER="$HOME/.local/bin/$APP_ID"
MENU_ENTRY="$DATA_DIR/applications/$APP_ID.desktop"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
DESKTOP_ICON="$DESKTOP_DIR/$APP_ID.desktop"

SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# @CORE@: bundled next to @PACKAGE@ in a release; in the suite checkout it lives in core/ at the root.
if [ -d "$SRC/@CORE@" ]; then CORE_SRC="$SRC/@CORE@"; else CORE_SRC="$SRC/../../../core/@CORE@"; fi

info() { printf '\\033[1;35m==>\\033[0m %s\\n' "$1"; }
die()  { printf '\\033[1;31mERROR:\\033[0m %s\\n' "$1" >&2; exit 1; }

usage() { sed -n '3,8p' "$0" | sed 's/^# \\{0,1\\}//'; }

DESKTOP_SHORTCUT=true
UNINSTALL=false
PURGE=false
for arg in "$@"; do
    case "$arg" in
        --no-desktop-shortcut) DESKTOP_SHORTCUT=false ;;
        --uninstall) UNINSTALL=true ;;
        --purge) PURGE=true ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "Unknown option: $arg" ;;
    esac
done
$PURGE && ! $UNINSTALL && die "--purge only goes with --uninstall."

[ "$(id -u)" -ne 0 ] || die "Run this as your own user, not with sudo: the app, the venv and the launcher belong in your home folder."

if $UNINSTALL; then
    info "Removing the launcher, the menu entry and the app"
    rm -f "$LAUNCHER" "$MENU_ENTRY" "$DESKTOP_ICON"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_DIR/applications" || true
    rm -rf "${DATA_DIR:?}/${APP_ID:?}"
    rm -f "${VENV_USERS:?}/${APP_ID:?}"
    rmdir "$VENV_USERS" 2>/dev/null || true
    if [ -d "$VENV_USERS" ]; then
        info "Keeping the suite venv: other suite apps still use it"
    else
        info "Removing the suite venv"
        rm -rf "${VENV:?}"
    fi
    if $PURGE; then
        info "Removing the settings"
        rm -rf "${CONFIG_DIR:?}/${APP_ID:?}"
    fi
    info "$APP_NAME is uninstalled."
    exit 0
fi

# --- Checks ------------------------------------------------------------------------------------
[ "$(uname -s)" = Linux ] || die "This app runs on Linux (Bazzite) only."
for f in requirements.txt VERSION @PACKAGE@/__main__.py "images/$APP_ID.webp" "images/$APP_ID-128.png"; do
    [ -f "$SRC/$f" ] || die "$f is missing: run install.sh from a clone or the extracted release folder."
done
[ -f "$CORE_SRC/__init__.py" ] || die "@CORE@ is missing: run install.sh from a clone or the extracted release folder."
CORE_SRC=$(cd "$CORE_SRC" && pwd -P)
VERSION=$(tr -d '[:space:]' <"$SRC/VERSION")
command -v python3 >/dev/null 2>&1 || die "python3 is not installed."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die "Python 3.10 or newer is needed."
python3 -c 'import venv, ensurepip' 2>/dev/null || die "python3 has no venv/ensurepip module."

info "Installing $APP_NAME $VERSION"

# --- 1. The app and its @CORE@ --------------------------------------------------------------
info "Copying the app to $APP_DIR"
rm -rf "${APP_DIR:?}"
mkdir -p "$APP_DIR"
(cd "$SRC" && tar --exclude='./.git' --exclude='./.idea' --exclude='./tests' --exclude='__pycache__' -cf - .) |
    tar -xf - -C "$APP_DIR"
if [ "$CORE_SRC" != "$SRC/@CORE@" ]; then         # from the checkout: bundle core like a release
    mkdir -p "$APP_DIR/@CORE@"
    (cd "$CORE_SRC" && tar --exclude='__pycache__' -cf - .) | tar -xf - -C "$APP_DIR/@CORE@"
fi

# --- 2. Shared suite venv with PyQt6 ------------------------------------------------------------
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c 'import sys' 2>/dev/null; then
    info "Creating the suite venv in $VENV"
    rm -rf "${VENV:?}"
    mkdir -p "$SUITE_DIR"
    python3 -m venv "$VENV"
fi
mkdir -p "$VENV_USERS"
touch "$VENV_USERS/$APP_ID"
info "Installing PyQt6 into the venv (downloads ~100 MB the first time)"
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade -r "$APP_DIR/requirements.txt"
"$VENV/bin/python" -c 'import PyQt6.QtWidgets' || die "PyQt6 does not load from the venv."

# --- 3. Launcher, menu entry, Desktop icon ------------------------------------------------------
info "Creating the launcher $LAUNCHER"
mkdir -p "$(dirname "$LAUNCHER")"
cat >"$LAUNCHER" <<LAUNCH
#!/usr/bin/env bash
# $APP_NAME launcher, written by install.sh. Starts from the app folder, so python -m never picks up a
# @PACKAGE@ folder from the current directory, and imports the @CORE@ bundled there.
cd "$APP_DIR" || { echo "$APP_NAME is not installed in $APP_DIR; run install.sh again." >&2; exit 1; }
exec "$VENV/bin/python" -m @PACKAGE@ "\\$@"
LAUNCH
chmod 755 "$LAUNCHER"

DESKTOP_FILE_CONTENT="[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
GenericName=@APP_NAME@
Comment=@SUMMARY@
Exec=$LAUNCHER
Icon=$APP_DIR/images/$APP_ID-128.png
Terminal=false
Categories=@DESKTOP_CATEGORIES@
Keywords=BC-250;Bazzite;@NAME@;
StartupNotify=true
StartupWMClass=$APP_ID"

info "Adding the app menu entry"
mkdir -p "$(dirname "$MENU_ENTRY")"
printf '%s\\n' "$DESKTOP_FILE_CONTENT" >"$MENU_ENTRY"
chmod 644 "$MENU_ENTRY"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_DIR/applications" || true

if $DESKTOP_SHORTCUT && [ -d "$DESKTOP_DIR" ]; then
    info "Adding the Desktop icon"
    printf '%s\\n' "$DESKTOP_FILE_CONTENT" >"$DESKTOP_ICON"
    # KDE and GNOME only start Desktop launchers that are executable (GNOME also wants them trusted).
    chmod 755 "$DESKTOP_ICON"
    command -v gio >/dev/null 2>&1 && gio set "$DESKTOP_ICON" metadata::trusted true 2>/dev/null || true
elif ! $DESKTOP_SHORTCUT; then
    rm -f "$DESKTOP_ICON"
fi

info "Done. Start \\"$APP_NAME\\" from the app menu$($DESKTOP_SHORTCUT && echo ' or the Desktop'), or run: $APP_ID"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) info "Note: ~/.local/bin is not on your PATH, so the terminal command needs the full path: $LAUNCHER" ;; esac
'''

INSTALLER_TEST_SH = '''#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/@NAME@/install.sh: install from the checkout (core bundled, shared venv, no sudo), a staged release
# replacing it, uninstall with and without other venv users, --purge, and the refusal to run as root.
# Runs with the shims from shims.sh (CI, or WSL on Windows).
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
T=/tmp/@APP_ID@-test
# shellcheck source=@SUITE@/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
APP=@APP_ID@
A=$D/$APP/app
printf '#!/bin/sh\\necho "sudo called: $*" >&2\\nexit 1\\n' > "$T/shims/sudo"     # nothing here needs root

echo "== 1. install from the suite checkout"
bash "$SUITE/apps/@NAME@/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "no sudo used" "! grep -q 'sudo called' $T/log1 && [ -z \\"\\$(ls -A $T/opt)\\" ]"
check "app copied" "[ -f $A/@PACKAGE@/main_window.py ] && [ -f $A/images/$APP.webp ] && [ -f $A/images/$APP-128.png ]"
check "core bundled from checkout" "[ -f $A/@CORE@/theme.py ] && [ -f $A/@CORE@/widgets.py ]"
check "no tests or caches copied" "[ ! -d $A/tests ] && ! find $A -name __pycache__ | grep -q ."
check "shared venv" "[ -x $D/@VENV_ID@/venv/bin/python ]"
check "venv user marker" "[ -f $D/@VENV_ID@/venv-users/$APP ]"
check "launcher uses shared venv" "grep -qF '@VENV_ID@/venv/bin/python\\" -m @PACKAGE@' $HOME/.local/bin/$APP"
check "launcher cds into the app" "grep -qF 'cd \\"$A\\"' $HOME/.local/bin/$APP"
check "menu entry" "grep -qx 'Exec=$HOME/.local/bin/$APP' $D/applications/$APP.desktop"
check "desktop icon, executable" "[ -x $HOME/Desktop/$APP.desktop ]"
check "core imports from the app copy" "(cd $A && /usr/bin/python3 -c 'import importlib.util as u, sys; s=u.find_spec(\\"@CORE@\\"); sys.exit(0 if s and s.origin.startswith(\\"$A\\") else 1)')"

echo "== 2. install a staged release (core bundled in the tarball) without the Desktop icon"
rm -rf "$T/stage"; /usr/bin/python3 "$NEXUS/tools/stage_app.py" --suite @SUITE@ @NAME@ "$T/stage" > /dev/null
echo "# release marker" >> "$T/stage/@CORE@/__init__.py"
bash "$T/stage/install.sh" --no-desktop-shortcut > "$T/log2" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "the release's own core used" "grep -q 'release marker' $A/@CORE@/__init__.py"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"

echo "== 3. refuses to run as root"
fakeroot -- bash "$T/stage/install.sh" > "$T/log3" 2>&1; rc=$?
check "exit non-zero" "[ $rc -ne 0 ] && grep -q 'not with sudo' $T/log3"

echo "== 4. uninstall while another suite app still uses the venv"
touch "$D/@VENV_ID@/venv-users/@VENV_ID@-test"
bash "$T/stage/install.sh" --uninstall > "$T/log4" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "app gone" "[ ! -e $D/$APP ]"
check "venv kept" "[ -x $D/@VENV_ID@/venv/bin/python ]"
check "own marker gone" "[ ! -e $D/@VENV_ID@/venv-users/$APP ]"
check "launcher and menu entry gone" "[ ! -e $HOME/.local/bin/$APP ] && [ ! -e $D/applications/$APP.desktop ]"

echo "== 5. reinstall, then uninstall --purge as the last venv user"
rm "$D/@VENV_ID@/venv-users/@VENV_ID@-test"
mkdir -p "$XDG_CONFIG_HOME/$APP" && touch "$XDG_CONFIG_HOME/$APP/$APP.ini"
bash "$T/stage/install.sh" --purge > "$T/log5" 2>&1; rc=$?
check "--purge alone refused" "[ $rc -ne 0 ] && grep -q 'only goes with --uninstall' $T/log5"
bash "$T/stage/install.sh" > "$T/log5" 2>&1 && bash "$T/stage/install.sh" --uninstall --purge >> "$T/log5" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "venv removed" "[ ! -e $D/@VENV_ID@/venv ] && [ ! -e $D/@VENV_ID@/venv-users ]"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"
check "settings removed" "[ ! -e $XDG_CONFIG_HOME/$APP ]"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 2 3 4 5; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
'''

CHAPTER_MD = '''<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![@APP_NAME@](../assets/@NAME@/@APP_ID@.webp){ .app-logo }

# @APP_NAME@

@SUMMARY@

## Install

Install it from the portal (the **@CATEGORY_TITLE@** tab), or from a checkout of the repository:

```bash
@SUITE@/apps/@NAME@/install.sh                         # the app, its launcher, a menu entry and a Desktop icon
@SUITE@/apps/@NAME@/install.sh --no-desktop-shortcut   # without the Desktop icon
@SUITE@/apps/@NAME@/install.sh --uninstall             # remove it; --purge removes its settings too
```

The launcher is `~/.local/bin/@APP_ID@`; the app runs on the suite's shared Python environment.

## The window

The header shows the app's state beside its name and a status box under it; **Refresh** reads again.
'''

README_MD = '''<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# @APP_NAME@

@SUMMARY@

How to install and use it: [@APP_NAME@ in the wiki](@WIKI@apps/@NAME@/).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
'''

GITIGNORE = "/.idea/\n.DS_Store\n__pycache__/\n*.pyc\n\n.pytest_cache/\n"
REQUIREMENTS = "# SPDX-License-Identifier: GPL-3.0-or-later\nPyQt6>=6.11,<7\n"
REQUIREMENTS_DEV = "# SPDX-License-Identifier: GPL-3.0-or-later\n-r requirements.txt\npytest>=8\n"

MANIFEST_ENTRY = '''[apps.@NAME@]
name = "@APP_NAME@"
summary = "@SUMMARY@"
tag = "@NAME@-v0.1.0"
sha256 = ""
required = false
changes_board = false
category = "@CATEGORY@"
install = ["bash install.sh"]
uninstall = ["bash install.sh --uninstall"]
detect = ["~/.local/bin/@APP_ID@"]
launch = [["Open", "~/.local/bin/@APP_ID@"]]
'''

CATEGORIES_ENTRY = '''
[@NAME@]
category = "@CATEGORY@"
icons = ["apps/@NAME@/images/@APP_ID@"]
tile = "portal/images/apps/@NAME@.webp"
'''

CATALOG_APP = '''[app.@NAME@]
name = "@APP_NAME@"
launchers = ["~/.local/bin/@APP_ID@"]

'''
CATALOG_SOURCE = '''[[dependency.source]]
owner = "@NAME@"
specifier = ">=6.11,<7"
'''

INDEX_ROW = "| ![](../assets/apps/@NAME@.webp){ .app-icon } [@APP_NAME@](@NAME@.md) | @SUMMARY@ |\n"
CATEGORIES_ROW = "| ![](../assets/apps/@NAME@.webp){ .app-icon } [@APP_NAME@](@NAME@.md) | @CATEGORY_TITLE@ |\n"
README_ROW = ('- <img src="portal/images/apps/@NAME@.webp" width="20" height="20" alt=""/> '
              '**[@APP_NAME@](apps/@NAME@)**: @SUMMARY@\n')


def fill(template: str, app: NewApp, suite: Suite) -> str:
    words = {"NAME": app.name, "APP_NAME": app.app_name, "APP_ID": app.app_id, "PACKAGE": app.package,
             "CATEGORY": app.category, "CATEGORY_TITLE": app.category_title, "SUMMARY": app.summary,
             "SUITE": suite.folder.name, "SUITE_NAME": suite.name, "VENV_ID": suite.app_id, "WIKI": suite.wiki,
             "CORE": suite.core, "DESKTOP_CATEGORIES": DESKTOP_CATEGORIES.get(app.category, "Utility;")}
    out = template
    for word, value in words.items():
        out = out.replace(f"@{word}@", value)
    leftover = re.search(r"@[A-Z_]+@", out)
    if leftover:
        raise SystemExit(f"the template has no value for {leftover.group(0)}")
    return out


# --- Writing -----------------------------------------------------------------------------------------------------

def insert_before(text: str, marker: str, addition: str, where: str) -> str:
    at = text.find(marker)
    if at < 0:
        raise SystemExit(f"{where}: no {marker.strip()!r} to put the app before")
    return text[:at] + addition + text[at:]


def insert_after_table(text: str, heading: str, row: str, where: str) -> str:
    """*row* at the end of the first Markdown table after the paragraph that starts with *heading*."""
    at = text.find(heading)
    if at < 0:
        raise SystemExit(f"{where}: no {heading!r} paragraph")
    table = text.find("\n|", at)
    if table < 0:
        raise SystemExit(f"{where}: no table after {heading!r}")
    return _insert_after_block(text, table + 1, "|", row)


def insert_after_list(text: str, heading: str, line: str, where: str) -> str:
    """*line* at the end of the first list after the paragraph that starts with *heading*."""
    at = text.find(heading)
    if at < 0:
        raise SystemExit(f"{where}: no {heading!r} paragraph")
    item = text.find("\n- ", at)
    if item < 0:
        raise SystemExit(f"{where}: no list after {heading!r}")
    return _insert_after_block(text, item + 1, "- ", line)


def _insert_after_block(text: str, start: int, prefix: str, addition: str) -> str:
    """*addition* after the lines from *start* that begin with *prefix* (a table's rows, a list's items)."""
    end = start
    while end < len(text) and text.startswith(prefix, end):
        newline = text.find("\n", end)
        if newline < 0:
            text += "\n"
            newline = len(text) - 1
        end = newline + 1
    return text[:end] + addition + text[end:]


def insert_after_rows(text: str, ending: str, row: str, where: str) -> str:
    """*row* after the last table row that ends with *ending* ("| Utilities |"); after the last row of the table
    when the category has none yet."""
    lines = text.splitlines(keepends=True)
    rows = [i for i, line in enumerate(lines) if line.rstrip().endswith(ending)]
    if not rows:
        rows = [i for i, line in enumerate(lines) if line.startswith("|")]
    if not rows:
        raise SystemExit(f"{where}: no table")
    lines.insert(rows[-1] + 1, row)
    return "".join(lines)


def write_app(root: Path, suite: Suite, app: NewApp) -> list[Path]:
    """Writes the app and lists it; returns the files written or changed, relative to *root*."""
    folder = suite.folder / "apps" / app.name
    if folder.exists():
        raise SystemExit(f"{folder.relative_to(root)} exists already")
    written: list[Path] = []

    def put(path: Path, text: str, executable: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))           # LF, as every text file in the repository
        if executable:
            path.chmod(0o755)
        written.append(path)

    def change(path: Path, text: str) -> None:
        path.write_bytes(text.encode("utf-8"))
        written.append(path)

    package = folder / app.package
    put(package / "__init__.py", fill(INIT_PY, app, suite))
    put(package / "__main__.py", fill(MAIN_PY, app, suite))
    put(package / "main_window.py", fill(WINDOW_PY, app, suite))
    put(folder / "tests" / "conftest.py", fill(CONFTEST_PY, app, suite))
    put(folder / "tests" / "test_main_window.py", fill(TEST_WINDOW_PY, app, suite))
    put(folder / "install.sh", fill(INSTALL_SH, app, suite), executable=True)
    put(folder / "requirements.txt", REQUIREMENTS)
    put(folder / "requirements-dev.txt", REQUIREMENTS_DEV)
    put(folder / "VERSION", "0.1.0\n")
    put(folder / "CHANGELOG", f"Changelog: {amsterdam_now()}\n\nAdded. {app.app_name}: the first version, written "
                              "by tools/new_app.py from the architecture chapter.\n")
    put(folder / "LICENSE", (suite.folder / "portal" / "LICENSE").read_text(encoding="utf-8"))
    put(folder / ".gitignore", GITIGNORE)
    put(folder / "README.md", fill(README_MD, app, suite))
    put(suite.folder / "tools" / "installer-tests" / f"{app.name}.sh", fill(INSTALLER_TEST_SH, app, suite),
        executable=True)
    put(suite.folder / "docs" / "apps" / f"{app.name}.md", fill(CHAPTER_MD, app, suite))

    # The portal's manifest, at its end; the root's copy follows while it is identical.
    manifest = suite.folder / "portal" / "apps.toml"
    old = manifest.read_text(encoding="utf-8")
    copy = root / "portal" / "apps.toml"
    follow = copy.is_file() and copy.read_bytes() == manifest.read_bytes()
    entry = fill(MANIFEST_ENTRY, app, suite)
    new = old.rstrip("\n") + "\n\n" + entry
    change(manifest, new)
    if follow:
        change(copy, new)
    categories = suite.folder / "icons" / "categories.toml"
    change(categories, categories.read_text(encoding="utf-8").rstrip("\n") + "\n" + fill(CATEGORIES_ENTRY, app, suite))
    sync = suite.folder / "tools" / "sync_icons.py"
    result = subprocess.run([sys.executable, str(sync)], cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"{sync.relative_to(root)} failed:\n{result.stdout}{result.stderr}")
    written += [folder / "images" / f"{app.app_id}.webp", folder / "images" / f"{app.app_id}-128.png",
                suite.folder / "portal" / "images" / "apps" / f"{app.name}.webp"]
    # The wiki: the nav, the apps overview (its category's table), the categories table.
    config = suite.folder / "mkdocs.yml"
    title = f'"{app.app_name}"' if ":" in app.app_name else app.app_name
    change(config, insert_before(config.read_text(encoding="utf-8"), "\n  - Development:\n",
                                 f"\n      - {title}: apps/{app.name}.md", "mkdocs.yml"))
    index = suite.folder / "docs" / "apps" / "index.md"
    change(index, insert_after_table(index.read_text(encoding="utf-8"), f"**{app.category_title}**",
                                     fill(INDEX_ROW, app, suite), "docs/apps/index.md"))
    table = suite.folder / "docs" / "apps" / "categories.md"
    change(table, insert_after_rows(table.read_text(encoding="utf-8"), f"| {app.category_title} |",
                                    fill(CATEGORIES_ROW, app, suite), "docs/apps/categories.md"))
    readme = suite.folder / "README.md"
    change(readme, insert_after_list(readme.read_text(encoding="utf-8"), f"**{app.category_title}**",
                                     fill(README_ROW, app, suite), "README.md"))
    # The Dependency Checker's catalog: the app with its launcher, and PyQt6 as one of its packages.
    catalog = suite.folder / "apps" / "package" / "package_checker" / "dependencies.toml"
    if catalog.is_file():
        text = insert_before(catalog.read_text(encoding="utf-8"), "\n[[tool]]\n", "\n" + fill(CATALOG_APP, app, suite).rstrip("\n") + "\n",
                             "dependencies.toml")
        start = text.find('name = "PyQt6"')
        if start < 0:
            raise SystemExit("dependencies.toml: no PyQt6 dependency")
        end = text.find("\n[[dependency]]", start)
        end = len(text) if end < 0 else end + 1
        text = text[:end].rstrip("\n") + "\n\n" + fill(CATALOG_SOURCE, app, suite) + "\n" + text[end:]
        change(catalog, text)
    # CI: the pytest matrix, the installer step and the shellcheck list.
    ci = root / ".github" / "workflows" / "ci.yml"
    text = ci.read_text(encoding="utf-8")
    text = insert_before(text, "]   # every folder with tests/", f", {suite.folder.name}/apps/{app.name}", "ci.yml")
    text = insert_before(text, "      - name: release tarballs, end to end\n",
                         f"      - name: {app.name} installer\n"
                         f"        run: bash {suite.folder.name}/tools/installer-tests/{app.name}.sh\n", "ci.yml")
    text = insert_before(text, "\n\n      # The repository's rules",
                         f"\n          shellcheck -S warning {suite.folder.name}/apps/{app.name}/install.sh", "ci.yml")
    change(ci, text)
    return [p.relative_to(root) for p in written]


# --- The checks --------------------------------------------------------------------------------------------------

def checks(root: Path, suite: Suite, app: NewApp) -> list[tuple[str, bool, str]]:
    """The checks of the architecture chapter on the new app: (what, passed, output)."""
    folder = suite.folder / "apps" / app.name
    python = sys.executable
    pytest = [python, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    scripts = [str(folder / "install.sh"), str(suite.folder / "tools" / "installer-tests" / f"{app.name}.sh")]
    runs: list[tuple[str, list[str], Path]] = [
        ("the layout test", [*pytest, "tools/tests/test_layout.py"], root),
        ("the app's tests", [*pytest, "tests"], folder),
        ("the suite's installer, icon and manifest tests",
         [*pytest, "tests/test_installer_tests.py", "tests/test_icons.py", "tests/test_check_manifest.py"],
         suite.folder / "tools"),
        ("the Dependency Checker's catalog tests", [*pytest, "tests/test_dependencies.py", "-k", "catalog"],
         suite.folder / "apps" / "package"),
        ("the manifest check", [python, str(suite.folder / "tools" / "check_manifest.py")], root),
        ("bash -n", ["bash", "-n", *scripts], root),
    ]
    if shutil.which("shellcheck"):
        runs.append(("shellcheck", ["shellcheck", "-x", "-S", "warning", *scripts], root))
    results = []
    for what, command, cwd in runs:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
        results.append((what, result.returncode == 0, (result.stdout + result.stderr).strip()))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("suite", help="the suite's folder, such as bc250-bazzite")
    parser.add_argument("name", help="the app's key: its folder under apps/, its tag prefix (<name>-v), a short name")
    parser.add_argument("app_name", metavar="app-name", help='the name shown: "BC-250 Fan Control"')
    parser.add_argument("--id", dest="app_id", help="the app id (the launcher, the settings, the desktop file; "
                                                   "default: <suite prefix>-<name>, bc250-<name>)")
    parser.add_argument("--package", help="the Python package (default: the name without its BC-250 or Bazzite "
                                          "prefix, as an identifier)")
    parser.add_argument("--category", default="utilities", help="the portal's tab and the icon (default: utilities)")
    parser.add_argument("--summary", help="one line on what the app does (the portal's pill, the wiki's tables)")
    parser.add_argument("--no-check", action="store_true", help="write the app and stop; do not run the checks")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)      # the tests' repositories
    args = parser.parse_args(argv)
    root = args.root.resolve()
    suite = read_suite(root, args.suite)
    if not _NAME.match(args.name):
        raise SystemExit(f"{args.name!r} is not a name: lowercase letters, digits and hyphens, starting with a letter")
    if args.category not in suite.categories:
        raise SystemExit(f"{args.category!r} is not a category of {suite.name}: one of {', '.join(suite.categories)}")
    package = args.package or default_package(args.app_name)
    if not package.isidentifier() or package != package.lower():
        raise SystemExit(f"{package!r} is not a package name: a lowercase Python identifier")
    app = NewApp(args.name, args.app_name.strip(), args.app_id or f"{suite.prefix}-{args.name}", package,
                 args.category, (args.summary or f"{args.app_name.strip()}: what it does, in one line.").strip())
    if not _NAME.match(app.app_id):
        raise SystemExit(f"{app.app_id!r} is not an app id: lowercase letters, digits and hyphens")
    written = write_app(root, suite, app)
    print(f"{app.app_name} ({suite.folder.name}/apps/{app.name}, package {app.package}, id {app.app_id}, "
          f"{app.category}):")
    for path in written:
        print(f"  {path.as_posix()}")
    if args.no_check:
        return 0
    print("The checks:")
    failed = False
    for what, passed, output in checks(root, suite, app):
        print(f"  {'ok  ' if passed else 'FAIL'} {what}")
        if not passed:
            failed = True
            print("       " + output.replace("\n", "\n       "))
    print("Next: the window and its tests, the chapter, the app's CHANGELOG entries, the Dependency Checker's catalog "
          "for a package or tool beyond PyQt6, and the portal bump the new entry asks for (check_manifest.py --base; "
          "the release stays the owner's).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
