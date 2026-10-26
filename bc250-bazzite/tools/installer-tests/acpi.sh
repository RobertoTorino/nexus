#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/acpi/install.sh: install from the checkout, Desktop icon on and off, a staged release
# replacing it, uninstall with --purge, and the refusal to run as root. Runs with the shims from shims.sh (CI, or
# WSL on Windows). The ACPI override itself is tested in apps/acpi/tests.
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
T=/tmp/bc250-acpi-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
V=$(tr -d '[:space:]' < "$SUITE/apps/acpi/VERSION")
APP=bc250-persistent-acpi

echo "== 1. install from the suite checkout"
bash "$SUITE/apps/acpi/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "versioned /opt copy" "[ -f $T/opt/$APP-v$V/bc250-acpi-override.sh ]"
check "symlink" "[ \"\$(readlink $T/opt/$APP)\" = $APP-v$V ]"
check "override script executable" "[ -x $T/opt/$APP/bc250-acpi-override.sh ]"
check "tables copied" "[ -f $T/opt/$APP/tables/acpi_override.cpio ]"
check "no tests or caches copied" "[ ! -d $T/opt/$APP/tests ] && ! find $T/opt/$APP/ -name __pycache__ | grep -q ."
check "own venv" "[ -x $D/$APP-app/venv/bin/python ]"
check "launcher" "grep -qF '$APP-app/venv/bin/python\" -m locked_acpi' $HOME/.local/bin/$APP-gui"
check "launcher cds into /opt link" "grep -q \"cd \\\"$T/opt/$APP\\\"\" $HOME/.local/bin/$APP-gui"
check "menu entry" "grep -qx 'Exec=$HOME/.local/bin/$APP-gui' $D/applications/$APP.desktop"
check "desktop icon, executable" "[ -x $HOME/Desktop/$APP.desktop ]"
check "board untouched message" "grep -q 'changed nothing on the board' $T/log1"

echo "== 2. reinstall without the Desktop icon"
bash "$SUITE/apps/acpi/install.sh" --no-desktop-shortcut > "$T/log2" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"
check "menu entry kept" "[ -f $D/applications/$APP.desktop ]"

echo "== 3. install a staged release with a new version"
rm -rf "$T/stage"; /usr/bin/python3 "$NEXUS/tools/stage_app.py" acpi "$T/stage" > /dev/null
echo 9.9.9 > "$T/stage/VERSION"
bash "$T/stage/install.sh" > "$T/log3" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "new version linked" "[ \"\$(readlink $T/opt/$APP)\" = $APP-v9.9.9 ]"
check "old version removed" "[ ! -d $T/opt/$APP-v$V ]"
check "no core bundled (MIT app, own code only)" "[ ! -d $T/stage/bc250_core ]"

echo "== 4. refuses to run as root"
fakeroot -- bash "$T/stage/install.sh" > "$T/log4" 2>&1; rc=$?
check "exit non-zero" "[ $rc -ne 0 ]"
check "points at the override script" "grep -q 'bc250-acpi-override.sh --install' $T/log4"

echo "== 5. uninstall --purge"
mkdir -p "$XDG_CONFIG_HOME/$APP" && touch "$XDG_CONFIG_HOME/$APP/$APP.conf"
bash "$T/stage/install.sh" --uninstall --purge > "$T/log5" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "/opt copy gone" "[ ! -e $T/opt/$APP ] && ! ls -d $T/opt/$APP-v* >/dev/null 2>&1"
check "venv gone" "[ ! -e $D/$APP-app ]"
check "launcher, menu entry and icon gone" "[ ! -e $HOME/.local/bin/$APP-gui ] && [ ! -e $D/applications/$APP.desktop ] && [ ! -e $HOME/Desktop/$APP.desktop ]"
check "settings gone" "[ ! -e $XDG_CONFIG_HOME/$APP ]"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 2 3 4 5; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
