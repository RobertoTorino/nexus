#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise the dependency checker's install, staged release and uninstall paths with the shared installer shims,
# with the weekly Bazzite update reminder (a systemd user timer; systemctl only records what it is asked).
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
T=/tmp/bc250-dependency-checker-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
APP=bc250-portal-dependency-checker
A=$D/$APP/app
printf '#!/bin/sh\necho "sudo called: $*" >&2\nexit 1\n' > "$T/shims/sudo"
printf '#!/bin/sh\necho "$*" >> "%s"\n' "$T/systemctl.log" > "$T/shims/systemctl"
chmod +x "$T/shims/systemctl"
U=$XDG_CONFIG_HOME/systemd/user
R=bc250-bazzite-update-reminder

echo "== 1. install from the suite checkout"
bash "$SUITE/apps/package/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "no sudo used" "! grep -q 'sudo called' $T/log1 && [ -z \"\$(ls -A $T/opt)\" ]"
check "app copied" "[ -f $A/package_checker/__main__.py ] && [ -f $A/package_checker/dependencies.toml ] && [ -f $A/images/bc250-dependency-checker.webp ] && [ -f $A/images/bc250-dependency-checker-128.png ] && [ -f $A/requirements.txt ]"
check "core bundled from checkout" "[ -f $A/bc250_core/theme.py ]"
check "no tests or caches copied" "[ ! -d $A/tests ] && [ ! -d $A/.pytest_cache ] && ! find $A -name __pycache__ | grep -q ."
check "shared venv marker" "[ -f $D/bc250-bazzite-suite/venv-users/$APP ]"
check "launcher uses module" "grep -qF ' -m package_checker' $HOME/.local/bin/$APP"
check "menu entry" "grep -qx 'Exec=$HOME/.local/bin/$APP' $D/applications/$APP.desktop"
check "reminder service runs the checker's reminder" "grep -qx 'ExecStart=$HOME/.local/bin/$APP --bazzite-reminder' $U/$R.service && grep -qx 'Type=oneshot' $U/$R.service"
check "reminder timer weekly, caught up after a missed Monday" "grep -qx 'OnCalendar=Mon \*-\*-\* 10:00' $U/$R.timer && grep -qx 'Persistent=true' $U/$R.timer && grep -qx 'WantedBy=timers.target' $U/$R.timer"
check "reminder timer enabled" "grep -qx -- '--user enable --now $R.timer' $T/systemctl.log"

echo "== 2. install a staged release without the Desktop icon"
rm -rf "$T/stage"; /usr/bin/python3 "$NEXUS/tools/stage_app.py" package "$T/stage" > /dev/null
check "manual bundled" "[ -f $T/stage/MANUAL.md ]"
echo "# release marker" >> "$T/stage/bc250_core/__init__.py"
bash "$T/stage/install.sh" --no-desktop-shortcut > "$T/log2" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "the release's own core used" "grep -q 'release marker' $A/bc250_core/__init__.py"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"

echo "== 2b. no user session: the timer is enabled for the next login"
printf '#!/bin/sh\necho "$*" >> "%s"\ncase "$*" in *enable*) exit 1 ;; esac\n' "$T/systemctl.log" > "$T/shims/systemctl"
bash "$T/stage/install.sh" --no-desktop-shortcut > "$T/log2b" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "enabled by its link" "[ \"\$(readlink $U/timers.target.wants/$R.timer)\" = ../$R.timer ] && grep -q 'starts with your next login' $T/log2b"
printf '#!/bin/sh\necho "$*" >> "%s"\n' "$T/systemctl.log" > "$T/shims/systemctl"

echo "== 3. uninstall while another suite app still uses the venv"
touch "$D/bc250-bazzite-suite/venv-users/bc250-bazzite-test"
bash "$T/stage/install.sh" --uninstall > "$T/log3" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "app gone and venv kept" "[ ! -e $D/$APP ] && [ -x $D/bc250-bazzite-suite/venv/bin/python ]"
check "own marker gone" "[ ! -e $D/bc250-bazzite-suite/venv-users/$APP ]"
check "reminder stopped and removed" "[ ! -e $U/$R.timer ] && [ ! -e $U/$R.service ] && [ ! -e $U/timers.target.wants/$R.timer ] && grep -qx -- '--user disable --now $R.timer' $T/systemctl.log"

echo "== 4. purge as the last venv user"
rm "$D/bc250-bazzite-suite/venv-users/bc250-bazzite-test"
mkdir -p "$XDG_CONFIG_HOME/$APP" && touch "$XDG_CONFIG_HOME/$APP/$APP.ini"
bash "$SUITE/apps/package/install.sh" > "$T/log4" 2>&1 &&
    bash "$SUITE/apps/package/install.sh" --uninstall --purge >> "$T/log4" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "venv and settings removed" "[ ! -e $D/bc250-bazzite-suite/venv ] && [ ! -e $XDG_CONFIG_HOME/$APP ]"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 2 2b 3 4; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
