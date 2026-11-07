#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise dev/deps/install.sh, Nexus Deps' installer: the launcher, menu entry and Desktop icon point at this
# checkout, the weekly reminder is a systemd user timer (systemctl only records what it is asked), an installed
# Dependency Checker of the suite (the app it was) and its timer go, --no-desktop-shortcut drops the icon, root and
# unknown options are refused, uninstall removes the timer and leaves the checkout and the settings, --purge removes
# them. Runs with the shims from shims.sh (CI, or WSL).
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: dev/ and core/
A=$NEXUS/dev/deps
T=/tmp/nexus-deps-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
printf '#!/bin/sh\necho "$*" >> "%s"\n' "$T/systemctl.log" > "$T/shims/systemctl"
chmod +x "$T/shims/systemctl"
APP=nexus-deps
L=$HOME/.local/bin/$APP
M=$XDG_DATA_HOME/applications/$APP.desktop
I=$HOME/Desktop/$APP.desktop
U=$XDG_CONFIG_HOME/systemd/user
R=nexus-deps-reminder
OLD=bc250-portal-dependency-checker
OLD_R=bc250-bazzite-update-reminder

echo "== 1. install over the suite's Dependency Checker"
mkdir -p "$HOME/.local/bin" "$XDG_DATA_HOME/applications" "$HOME/Desktop" "$U/timers.target.wants" \
         "$XDG_DATA_HOME/$OLD/app" "$XDG_DATA_HOME/bc250-bazzite-suite/venv-users"
printf '#!/bin/sh\n' > "$HOME/.local/bin/$OLD"; : > "$XDG_DATA_HOME/applications/$OLD.desktop"; : > "$HOME/Desktop/$OLD.desktop"
: > "$XDG_DATA_HOME/bc250-bazzite-suite/venv-users/$OLD"; : > "$XDG_DATA_HOME/bc250-bazzite-suite/venv-users/bc250-gpu"
: > "$U/$OLD_R.timer"; : > "$U/$OLD_R.service"; ln -sfn "../$OLD_R.timer" "$U/timers.target.wants/$OLD_R.timer"
bash "$A/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "the checker's launcher, menu entry, icon and copy are gone" "[ ! -e $HOME/.local/bin/$OLD ] && [ ! -e $XDG_DATA_HOME/applications/$OLD.desktop ] && [ ! -e $HOME/Desktop/$OLD.desktop ] && [ ! -e $XDG_DATA_HOME/$OLD ] && grep -q 'earlier name' $T/log1"
check "its use of the shared venv is gone, the other apps' stays" "[ ! -e $XDG_DATA_HOME/bc250-bazzite-suite/venv-users/$OLD ] && [ -e $XDG_DATA_HOME/bc250-bazzite-suite/venv-users/bc250-gpu ]"
check "its timer stopped and removed" "[ ! -e $U/$OLD_R.timer ] && [ ! -e $U/$OLD_R.service ] && [ ! -L $U/timers.target.wants/$OLD_R.timer ] && grep -qx -- '--user disable --now $OLD_R.timer' $T/systemctl.log"
check "launcher runs this checkout's run.sh" "[ -x $L ] && grep -qF 'exec \"$A/run.sh\"' $L"
check "menu entry" "grep -qx 'Exec=$L' $M && grep -qx 'Icon=$A/images/$APP-128.png' $M && grep -qx 'StartupWMClass=$APP' $M"
check "the icon exists" "[ -f $A/images/$APP.webp ] && [ -f $A/images/$APP-128.png ]"
check "desktop icon, executable" "[ -x $I ]"
check "reminder service runs the weekly check" "grep -qx 'ExecStart=$L --remind' $U/$R.service && grep -qx 'Type=oneshot' $U/$R.service"
check "reminder timer weekly, caught up after a missed Monday" "grep -qx 'OnCalendar=Mon \*-\*-\* 10:00' $U/$R.timer && grep -qx 'Persistent=true' $U/$R.timer && grep -qx 'WantedBy=timers.target' $U/$R.timer"
check "reminder timer enabled" "grep -qx -- '--user enable --now $R.timer' $T/systemctl.log"

echo "== 2. again without the Desktop icon, and no user session: the timer is enabled for the next login"
printf '#!/bin/sh\necho "$*" >> "%s"\ncase "$*" in *enable*) exit 1 ;; esac\n' "$T/systemctl.log" > "$T/shims/systemctl"
bash "$A/install.sh" --no-desktop-shortcut > "$T/log2" 2>&1; rc=$?
printf '#!/bin/sh\necho "$*" >> "%s"\n' "$T/systemctl.log" > "$T/shims/systemctl"
check "exit 0" "[ $rc -eq 0 ]"
check "desktop icon removed, menu entry kept" "[ ! -e $I ] && [ -f $M ]"
check "enabled by its link" "[ \"\$(readlink $U/timers.target.wants/$R.timer)\" = ../$R.timer ] && grep -q 'starts with your next login' $T/log2"

echo "== 3. refusals"
fakeroot -- bash "$A/install.sh" > "$T/log3" 2>&1; rc=$?
check "root refused" "[ $rc -ne 0 ] && grep -q 'not with sudo' $T/log3"
bash "$A/install.sh" --bogus > "$T/log3b" 2>&1; rc=$?
check "unknown option refused" "[ $rc -ne 0 ] && grep -q 'Unknown option: --bogus' $T/log3b"

echo "== 4. uninstall"
bash "$A/install.sh" --uninstall > "$T/log4" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "launcher, menu entry and icon gone" "[ ! -e $L ] && [ ! -e $M ] && [ ! -e $I ]"
check "reminder stopped and removed" "[ ! -e $U/$R.timer ] && [ ! -e $U/$R.service ] && [ ! -e $U/timers.target.wants/$R.timer ] && grep -qx -- '--user disable --now $R.timer' $T/systemctl.log"
check "checkout untouched" "[ -x $A/run.sh ] && [ -f $A/install.sh ]"

echo "== 5. --purge"
bash "$A/install.sh" --purge > "$T/log5" 2>&1; rc=$?
check "--purge alone refused" "[ $rc -ne 0 ] && grep -q 'only goes with --uninstall' $T/log5"
bash "$A/install.sh" > "$T/log5" 2>&1
mkdir -p "$XDG_CONFIG_HOME/$APP" && touch "$XDG_CONFIG_HOME/$APP/$APP.ini"
bash "$A/install.sh" --uninstall > "$T/log5" 2>&1
check "plain uninstall keeps the settings" "[ -f $XDG_CONFIG_HOME/$APP/$APP.ini ]"
bash "$A/install.sh" --uninstall --purge > "$T/log5" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "settings gone, checkout untouched" "[ ! -e $XDG_CONFIG_HOME/$APP ] && [ -x $A/run.sh ]"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 2 3 3b 4 5; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
