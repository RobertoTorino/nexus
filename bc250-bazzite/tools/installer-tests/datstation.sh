#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/datstation/install.sh: install from the checkout (the app's own venv, the launcher, core
# bundled, no sudo), a staged release replacing it, the refusals, uninstall (settings and scores kept) and --purge.
# Runs with the shims from shims.sh (CI, or WSL on Windows).
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
T=/tmp/bazzite-datstation-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
APP=bazzite-datstation
A=$D/$APP/app
# sudo must never be needed: make it fail loudly.
printf '#!/bin/sh\necho "sudo called: $*" >&2\nexit 1\n' > "$T/shims/sudo"

# The launcher runs in the caller's folder and still takes the app's own package: a probe in place of the installed
# module, the real python instead of the stub venv's, started from a folder that holds a look-alike package.
probe_launcher() {   # probe_launcher <launcher> <module file under $A> <package>; prints what the probe saw
    local stub="$T/stub-python" out
    cp "$D/$APP/venv/bin/python" "$stub" && printf '#!/bin/sh\nexec /usr/bin/python3 "$@"\n' > "$D/$APP/venv/bin/python"
    cp "$A/$2" "$T/module.bak"
    printf 'import os, sys\nimport %s\nprint("cwd=" + os.getcwd())\nprint("pkg=" + os.path.dirname(%s.__file__))\nprint("args=" + "|".join(sys.argv[1:]))\n' "$3" "$3" > "$A/$2"
    rm -rf "$T/elsewhere"; mkdir -p "$T/elsewhere/$3" && echo 'raise SystemExit("look-alike package imported")' > "$T/elsewhere/$3/__init__.py"
    out=$(cd "$T/elsewhere" && "$1" "game 1.pkg" sub/out 2>&1)
    cp "$T/module.bak" "$A/$2"; mv "$stub" "$D/$APP/venv/bin/python"
    printf '%s\n' "$out"
}

echo "== 1. install from the suite checkout"
bash "$SUITE/apps/datstation/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "no sudo used" "! grep -q 'sudo called' $T/log1 && [ -z \"\$(ls -A $T/opt)\" ]"
check "app copied" "[ -f $A/datstation/main_window.py ] && [ -f $A/images/$APP.webp ] && [ -f $A/images/$APP-128.png ]"
check "data and music copied" "[ -f $A/datstation/data/questions.json ] && [ -f $A/datstation/sounds/sea_breeze.ogg ]"
check "core bundled from checkout" "[ -f $A/bc250_core/widgets.py ] && [ ! -d $A/bc250_core/__pycache__ ]"
check "no tests or caches copied" "[ ! -d $A/tests ] && ! find $A -name __pycache__ | grep -q ."
check "own venv, not the suite's" "[ -x $D/$APP/venv/bin/python ] && [ ! -e $D/bc250-bazzite-suite/venv ]"
check "launcher uses the own venv" "grep -qF '$APP/venv/bin/python\" -c ' $HOME/.local/bin/$APP && grep -qF '\"$A\" datstation \"' $HOME/.local/bin/$APP"
check "launcher does not change folder" "! grep -q '^cd ' $HOME/.local/bin/$APP"
out=$(probe_launcher $HOME/.local/bin/$APP datstation/__main__.py datstation); here=$(cd "$T/elsewhere" && pwd -P)
check "launcher runs in the caller's folder" "printf '%s\n' \"$out\" | grep -qxF \"cwd=$here\""
check "launcher imports the app's package, not the folder's" "printf '%s\n' \"$out\" | grep -qxF \"pkg=$A/datstation\""
check "launcher passes relative paths as given" "printf '%s\n' \"$out\" | grep -qxF 'args=game 1.pkg|sub/out'"
check "core imports from the app copy" "(cd $A && /usr/bin/python3 -c 'import importlib.util as u, sys; s=u.find_spec(\"bc250_core\"); sys.exit(0 if s and s.origin.startswith(\"$A\") else 1)')"
check "launcher executable" "[ -x $HOME/.local/bin/$APP ]"
check "menu entry starts the launcher" "grep -qx 'Exec=$HOME/.local/bin/$APP' $D/applications/$APP.desktop"
check "desktop icon, executable" "[ -x $HOME/Desktop/$APP.desktop ]"

echo "== 2. install a staged release (core bundled in the tarball) without the Desktop icon"
rm -rf "$T/stage"; /usr/bin/python3 "$NEXUS/tools/stage_app.py" datstation "$T/stage" > /dev/null
echo "# release marker" >> "$T/stage/datstation/__init__.py"
echo "# release marker" >> "$T/stage/bc250_core/__init__.py"
bash "$T/stage/install.sh" --no-desktop-shortcut > "$T/log2" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "the release's own code used" "grep -q 'release marker' $A/datstation/__init__.py"
check "the release's own core used" "grep -q 'release marker' $A/bc250_core/__init__.py"
check "manual bundled" "[ -f $A/MANUAL.md ]"
check "no development files bundled" "[ ! -e $A/requirements-dev.txt ] && [ ! -d $A/tests ]"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"

echo "== 3. refusals"
fakeroot -- bash "$T/stage/install.sh" > "$T/log3" 2>&1; rc=$?
check "root refused" "[ $rc -ne 0 ] && grep -q 'not with sudo' $T/log3"
bash "$T/stage/install.sh" --purge > "$T/log3" 2>&1; rc=$?
check "--purge alone refused" "[ $rc -ne 0 ] && grep -q 'only goes with --uninstall' $T/log3"
bash "$T/stage/install.sh" --bogus > "$T/log3" 2>&1; rc=$?
check "unknown option refused" "[ $rc -ne 0 ] && grep -q 'Unknown option: --bogus' $T/log3"

echo "== 4. uninstall keeps the settings and the scores"
mkdir -p "$XDG_CONFIG_HOME/$APP" && touch "$XDG_CONFIG_HOME/$APP/$APP.ini" && echo '{}' > "$D/$APP/scores.json"
bash "$T/stage/install.sh" --uninstall > "$T/log4" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "app and venv gone" "[ ! -e $A ] && [ ! -e $D/$APP/venv ]"
check "settings and scores kept" "[ -f $XDG_CONFIG_HOME/$APP/$APP.ini ] && [ -f $D/$APP/scores.json ]"
check "launcher and menu entry gone" "[ ! -e $HOME/.local/bin/$APP ] && [ ! -e $D/applications/$APP.desktop ]"

echo "== 5. reinstall, then uninstall --purge"
bash "$T/stage/install.sh" > "$T/log5" 2>&1 && bash "$T/stage/install.sh" --uninstall --purge >> "$T/log5" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"
check "settings and scores removed" "[ ! -e $XDG_CONFIG_HOME/$APP ] && [ ! -e $D/$APP ]"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 2 3 4 5; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
