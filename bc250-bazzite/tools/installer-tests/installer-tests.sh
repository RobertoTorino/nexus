#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise tools/installer-tests/gui/install.sh, the installer of BC-250 Installer Tests: the launcher, menu entry and
# Desktop icon point at this checkout, --no-desktop-shortcut drops the icon, root and unknown options are refused,
# and uninstall leaves the checkout alone. Runs with the shims from shims.sh (CI, or WSL on Windows).
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
G=$SUITE/tools/installer-tests/gui
T=/tmp/bc250-installer-tests-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
APP=bc250-installer-test-gui
L=$HOME/.local/bin/$APP
M=$XDG_DATA_HOME/applications/$APP.desktop
I=$HOME/Desktop/$APP.desktop

echo "== 1. install"
bash "$G/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "launcher runs this checkout's run.sh" "[ -x $L ] && grep -qF 'exec \"$G/run.sh\"' $L"
check "menu entry" "grep -qx 'Exec=\"$L\"' $M && grep -qx 'Icon=$G/images/$APP-128.png' $M && grep -qx 'StartupWMClass=$APP' $M"
check "the icon exists" "[ -f $G/images/$APP.webp ] && [ -f $G/images/$APP-128.png ]"
check "desktop icon, executable" "[ -x $I ]"

echo "== 2. again without the Desktop icon"
bash "$G/install.sh" --no-desktop-shortcut > "$T/log2" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "desktop icon removed" "[ ! -e $I ]"
check "menu entry kept" "[ -f $M ]"

echo "== 3. refusals"
fakeroot -- bash "$G/install.sh" > "$T/log3" 2>&1; rc=$?
check "root refused" "[ $rc -ne 0 ] && grep -q 'not with sudo' $T/log3"
bash "$G/install.sh" --bogus > "$T/log3b" 2>&1; rc=$?
check "unknown option refused" "[ $rc -ne 0 ] && grep -q 'Unknown option: --bogus' $T/log3b"

echo "== 4. uninstall"
bash "$G/install.sh" --uninstall > "$T/log4" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "launcher, menu entry and icon gone" "[ ! -e $L ] && [ ! -e $M ] && [ ! -e $I ]"
check "checkout unchanged" "[ -x $G/run.sh ] && [ -f $G/install.sh ]"

echo "== 5. --purge"
bash "$G/install.sh" --purge > "$T/log5" 2>&1; rc=$?
check "--purge alone refused" "[ $rc -ne 0 ] && grep -q 'only goes with --uninstall' $T/log5"
bash "$G/install.sh" > "$T/log5" 2>&1 && bash "$G/install.sh" --uninstall --purge >> "$T/log5" 2>&1; rc=$?
check "uninstall --purge" "[ $rc -eq 0 ] && [ ! -e $L ] && [ -x $G/run.sh ]"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 2 3 4 5; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
