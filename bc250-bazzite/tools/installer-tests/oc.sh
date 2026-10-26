#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/oc/install.sh: install from the checkout (root-owned versioned /opt copy, own venv,
# launcher), the Desktop icon on and off, a staged release replacing it, the refusal to run as root, and uninstall
# with and without --purge. Runs with the shims from shims.sh (CI, or WSL on Windows).
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
T=/tmp/bc250-gpu-oc-bisect-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
V=$(tr -d '[:space:]' < "$SUITE/apps/oc/VERSION")
APP=bc250-gpu-oc-bisect
L=$T/opt/$APP

echo "== 1. install from the suite checkout"
bash "$SUITE/apps/oc/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "versioned /opt copy" "[ -f $T/opt/$APP-v$V/bc250-gpu-oc-bisect.sh ]"
check "symlink" "[ \"\$(readlink $L)\" = $APP-v$V ]"
check "script executable" "[ -x $L/bc250-gpu-oc-bisect.sh ]"
check "no staging folder left" "! ls -d $T/opt/.$APP-* >/dev/null 2>&1"
check "no caches copied" "! find $L/ -name __pycache__ | grep -q ."
check "own venv" "[ -x $D/$APP-app/venv/bin/python ]"
check "launcher" "grep -qF 'exec \"$D/$APP-app/venv/bin/python\" -m oc_bisect --script \"$L/bc250-gpu-oc-bisect.sh\"' $HOME/.local/bin/$APP-gui"
check "launcher cds into the /opt link" "grep -q \"cd \\\"$L\\\"\" $HOME/.local/bin/$APP-gui"
check "menu entry" "grep -qx 'Exec=$HOME/.local/bin/$APP-gui' $D/applications/$APP-gui.desktop"
check "icon from /opt" "grep -qx 'Icon=$L/images/$APP-128.png' $D/applications/$APP-gui.desktop && [ -f $L/images/$APP.webp ] && [ -f $L/images/$APP-128.png ]"
check "desktop icon, executable" "[ -x $HOME/Desktop/$APP-gui.desktop ]"

echo "== 2. reinstall without the Desktop icon"
bash "$SUITE/apps/oc/install.sh" --no-desktop-shortcut > "$T/log2" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP-gui.desktop ]"
check "menu entry kept" "[ -f $D/applications/$APP-gui.desktop ]"

echo "== 3. install a staged release with a new version"
rm -rf "$T/stage"; /usr/bin/python3 "$NEXUS/tools/stage_app.py" oc "$T/stage" > /dev/null
check "manual bundled" "[ -f $T/stage/MANUAL.md ]"
echo 9.9.9 > "$T/stage/VERSION"
bash "$T/stage/install.sh" > "$T/log3" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "new version linked" "[ \"\$(readlink $L)\" = $APP-v9.9.9 ]"
check "old version removed" "[ ! -d $T/opt/$APP-v$V ]"

echo "== 4. refuses to run as root"
fakeroot -- bash "$T/stage/install.sh" > "$T/log4" 2>&1; rc=$?
check "exit non-zero" "[ $rc -ne 0 ]"
check "says why" "grep -q 'not with sudo' $T/log4"

echo "== 5. uninstall keeps results and settings"
mkdir -p "$D/$APP" "$XDG_CONFIG_HOME/$APP" && touch "$D/$APP/run.log" "$XDG_CONFIG_HOME/$APP/settings.ini"
bash "$T/stage/install.sh" --uninstall > "$T/log5" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "/opt copy gone" "[ ! -e $L ] && ! ls -d $T/opt/$APP-v* >/dev/null 2>&1"
check "venv gone" "[ ! -e $D/$APP-app ]"
check "launcher, menu entry and icon gone" "[ ! -e $HOME/.local/bin/$APP-gui ] && [ ! -e $D/applications/$APP-gui.desktop ] && [ ! -e $HOME/Desktop/$APP-gui.desktop ]"
check "results and settings kept" "[ -f $D/$APP/run.log ] && [ -f $XDG_CONFIG_HOME/$APP/settings.ini ]"

echo "== 6. uninstall --purge"
bash "$SUITE/apps/oc/install.sh" > "$T/log6" 2>&1 &&
    bash "$SUITE/apps/oc/install.sh" --uninstall --purge >> "$T/log6" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "results and settings gone" "[ ! -e $D/$APP ] && [ ! -e $XDG_CONFIG_HOME/$APP ]"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 2 3 4 5 6; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
