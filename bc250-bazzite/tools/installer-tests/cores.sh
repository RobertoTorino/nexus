#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/cores/install.sh: install from the checkout (root-owned versioned /opt copy, one venv, two
# launchers), --bisect-only and --no-desktop-shortcut, a staged release replacing it, the refusal to run as root,
# and uninstall with and without --purge. Runs with the shims from shims.sh (CI, or WSL on Windows).
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
T=/tmp/bc250-cores-bisect-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
V=$(tr -d '[:space:]' < "$SUITE/apps/cores/VERSION")
APP=bc250-cores-bisect
L=$T/opt/$APP

echo "== 1. install both GUIs from the suite checkout"
bash "$SUITE/apps/cores/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "versioned /opt copy" "[ -f $T/opt/$APP-v$V/bc250-cores-bisect.sh ]"
check "symlink" "[ \"\$(readlink $L)\" = $APP-v$V ]"
check "scripts executable" "[ -x $L/bc250-cores-bisect.sh ] && [ -x $L/bc250-cores-unlock.sh ]"
check "no staging folder left" "! ls -d $T/opt/.$APP-* >/dev/null 2>&1"
check "no caches copied" "! find $L/ -name __pycache__ | grep -q ."
check "own venv" "[ -x $D/$APP-app/venv/bin/python ]"
check "bisect launcher" "grep -qF 'exec \"$D/$APP-app/venv/bin/python\" -m cores_bisect' $HOME/.local/bin/bc250-cores-bisect-gui"
check "unlock launcher" "grep -qF 'exec \"$D/$APP-app/venv/bin/python\" -m cores_unlock' $HOME/.local/bin/bc250-cores-unlock-gui"
check "launchers cd into the /opt link" "grep -q \"cd \\\"$L\\\"\" $HOME/.local/bin/bc250-cores-bisect-gui && grep -q \"cd \\\"$L\\\"\" $HOME/.local/bin/bc250-cores-unlock-gui"
check "menu entries" "grep -qx 'Exec=$HOME/.local/bin/bc250-cores-bisect-gui' $D/applications/bc250-cores-bisect-gui.desktop && grep -qx 'Exec=$HOME/.local/bin/bc250-cores-unlock-gui' $D/applications/bc250-cores-unlock.desktop"
check "icons from /opt" "grep -qx 'Icon=$L/images/bc250-cores-unlock-128.png' $D/applications/bc250-cores-unlock.desktop && [ -f $L/images/$APP.webp ] && [ -f $L/images/$APP-128.png ]"
check "desktop icons, executable" "[ -x $HOME/Desktop/bc250-cores-bisect-gui.desktop ] && [ -x $HOME/Desktop/bc250-cores-unlock.desktop ]"

echo "== 2. bisect GUI only, without the Desktop icon"
bash "$SUITE/apps/cores/install.sh" --bisect-only --no-desktop-shortcut > "$T/log2" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "unlock launcher and entries removed" "[ ! -e $HOME/.local/bin/bc250-cores-unlock-gui ] && [ ! -e $D/applications/bc250-cores-unlock.desktop ] && [ ! -e $HOME/Desktop/bc250-cores-unlock.desktop ]"
check "bisect kept, Desktop icon removed" "[ -x $HOME/.local/bin/bc250-cores-bisect-gui ] && [ ! -e $HOME/Desktop/bc250-cores-bisect-gui.desktop ]"
bash "$SUITE/apps/cores/install.sh" --bisect-only --unlock-only > "$T/log2b" 2>&1; rc=$?
check "--bisect-only with --unlock-only refused" "[ $rc -ne 0 ] && grep -q 'cannot be combined' $T/log2b"

echo "== 3. install a staged release with a new version"
rm -rf "$T/stage"; /usr/bin/python3 "$NEXUS/tools/stage_app.py" cores "$T/stage" > /dev/null
check "manual bundled" "[ -f $T/stage/MANUAL.md ]"
echo 9.9.9 > "$T/stage/VERSION"
bash "$T/stage/install.sh" > "$T/log3" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "new version linked" "[ \"\$(readlink $L)\" = $APP-v9.9.9 ]"
check "old version removed" "[ ! -d $T/opt/$APP-v$V ]"
check "both launchers back" "[ -x $HOME/.local/bin/bc250-cores-bisect-gui ] && [ -x $HOME/.local/bin/bc250-cores-unlock-gui ]"

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
check "launchers, menu entries and icons gone" "! ls $HOME/.local/bin/bc250-cores-* $D/applications/bc250-cores-* $HOME/Desktop/bc250-cores-* 2>/dev/null | grep -q ."
check "results and settings kept" "[ -f $D/$APP/run.log ] && [ -f $XDG_CONFIG_HOME/$APP/settings.ini ]"

echo "== 6. uninstall --purge"
bash "$SUITE/apps/cores/install.sh" > "$T/log6" 2>&1 &&
    bash "$SUITE/apps/cores/install.sh" --uninstall --purge >> "$T/log6" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "results and settings gone" "[ ! -e $D/$APP ] && [ ! -e $XDG_CONFIG_HOME/$APP ]"
bash "$SUITE/apps/cores/install.sh" --purge > "$T/log6b" 2>&1; rc=$?
check "--purge alone refused" "[ $rc -ne 0 ] && grep -q 'only goes with --uninstall' $T/log6b"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 2 3 4 5 6; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
