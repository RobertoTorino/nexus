#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise dev/releases/install.sh (and tools/release.sh, which forwards to it): the launcher, menu entry and
# Desktop icon point at this checkout, --no-desktop-shortcut drops the icon, root is refused, and uninstall leaves
# the checkout alone. Runs with the shims from shims.sh (CI, or WSL on Windows).
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
A=$NEXUS/dev/releases
T=/tmp/nexus-releases-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
APP=nexus-releases
L=$HOME/.local/bin/$APP
M=$XDG_DATA_HOME/applications/$APP.desktop
I=$HOME/Desktop/$APP.desktop

echo "== 1. install"
OLD=bc250-release                                # BC250 Suite Releases' launcher, menu entry and Desktop icon
mkdir -p "$HOME/.local/bin" "$XDG_DATA_HOME/applications" "$HOME/Desktop"
printf '#!/bin/sh\n' > "$HOME/.local/bin/$OLD"; : > "$XDG_DATA_HOME/applications/$OLD.desktop"; : > "$HOME/Desktop/$OLD.desktop"
bash "$A/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "the earlier name's launcher, menu entry and icon are gone" "[ ! -e $HOME/.local/bin/$OLD ] && [ ! -e $XDG_DATA_HOME/applications/$OLD.desktop ] && [ ! -e $HOME/Desktop/$OLD.desktop ] && grep -q 'earlier name' $T/log1"
check "launcher runs this checkout's run.sh" "[ -x $L ] && grep -qF 'exec \"$A/run.sh\"' $L"
check "menu entry" "grep -qx 'Exec=$L' $M && grep -qx 'Icon=$A/images/$APP-128.png' $M && grep -qx 'StartupWMClass=$APP' $M"
check "the icon exists" "[ -f $A/images/$APP.webp ] && [ -f $A/images/$APP-128.png ]"
check "desktop icon, executable" "[ -x $I ]"
check "launcher passes its arguments" "$L --help | grep -q -- 'install.sh'"
check "--list runs with the system python3" "PYTHON=/usr/bin/python3 $L --list | grep -q '^portal '"

echo "== 2. again through tools/release.sh, without the Desktop icon"
bash "$NEXUS/tools/release.sh" --install --no-desktop-shortcut > "$T/log2" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "desktop icon removed, menu entry kept" "[ ! -e $I ] && [ -f $M ]"

echo "== 3. refuses to run as root"
fakeroot -- bash "$A/install.sh" > "$T/log3" 2>&1; rc=$?
check "exit non-zero" "[ $rc -ne 0 ] && grep -q 'not with sudo' $T/log3"

echo "== 4. uninstall"
bash "$NEXUS/tools/release.sh" --uninstall > "$T/log4" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "launcher, menu entry and icon gone" "[ ! -e $L ] && [ ! -e $M ] && [ ! -e $I ]"
check "checkout untouched" "[ -x $A/run.sh ] && [ -f $A/nexus_releases/main_window.py ]"

echo "== 5. --purge"
bash "$A/install.sh" --purge > "$T/log5" 2>&1; rc=$?
check "--purge alone refused" "[ $rc -ne 0 ] && grep -q 'only goes with --uninstall' $T/log5"
bash "$A/install.sh" > "$T/log5" 2>&1
mkdir -p "$XDG_CONFIG_HOME/$APP" && touch "$XDG_CONFIG_HOME/$APP/$APP.ini"
bash "$NEXUS/tools/release.sh" --uninstall > "$T/log5" 2>&1
check "plain uninstall keeps the settings" "[ -f $XDG_CONFIG_HOME/$APP/$APP.ini ]"
bash "$NEXUS/tools/release.sh" --uninstall --purge > "$T/log5" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "settings gone, checkout untouched" "[ ! -e $XDG_CONFIG_HOME/$APP ] && [ -x $A/run.sh ]"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 2 3 4 5; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
