#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/sftp/install.sh: install from the checkout (core bundled, the app's own venv, no sudo), a staged
# release replacing it, the refusal to run as root, uninstall (profiles, settings and log kept) and --purge.
# Runs with the shims from shims.sh (CI, or WSL on Windows).
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
T=/tmp/bc250-sftp-tools-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
APP=bc250-bazzite-sftp-tools
A=$D/$APP/app
# sudo must never be needed: make it fail loudly.
printf '#!/bin/sh\necho "sudo called: $*" >&2\nexit 1\n' > "$T/shims/sudo"

echo "== 1. install from the suite checkout"
bash "$SUITE/apps/sftp/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "no sudo used" "! grep -q 'sudo called' $T/log1 && [ -z \"\$(ls -A $T/opt)\" ]"
check "app copied" "[ -f $A/sftp_tools/main_window.py ] && [ -f $A/images/$APP.webp ] && [ -f $A/images/$APP-128.png ]"
check "core bundled from checkout" "[ -f $A/bc250_core/theme.py ]"
check "no tests or caches copied" "[ ! -d $A/tests ] && ! find $A -name __pycache__ | grep -q ."
check "own venv, not the suite's" "[ -x $D/$APP/venv/bin/python ] && [ ! -e $D/bc250-bazzite-suite/venv ]"
check "launcher uses the own venv" "grep -qF '$APP/venv/bin/python\" -m sftp_tools' $HOME/.local/bin/$APP"
check "launcher cds into the app" "grep -qF 'cd \"$A\"' $HOME/.local/bin/$APP"
check "menu entry" "grep -qx 'Exec=$HOME/.local/bin/$APP' $D/applications/$APP.desktop"
check "desktop icon, executable" "[ -x $HOME/Desktop/$APP.desktop ]"
check "core imports from the app copy" "(cd $A && /usr/bin/python3 -c 'import importlib.util as u, sys; s=u.find_spec(\"bc250_core\"); sys.exit(0 if s and s.origin.startswith(\"$A\") else 1)')"

echo "== 2. install a staged release (core bundled in the tarball) without the Desktop icon"
rm -rf "$T/stage"; /usr/bin/python3 "$NEXUS/tools/stage_app.py" sftp "$T/stage" > /dev/null
echo "# release marker" >> "$T/stage/bc250_core/__init__.py"
bash "$T/stage/install.sh" --no-desktop-shortcut > "$T/log2" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "the release's own core used" "grep -q 'release marker' $A/bc250_core/__init__.py"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"

echo "== 3. refusals"
fakeroot -- bash "$T/stage/install.sh" > "$T/log3" 2>&1; rc=$?
check "root refused" "[ $rc -ne 0 ] && grep -q 'not with sudo' $T/log3"
bash "$T/stage/install.sh" --purge > "$T/log3" 2>&1; rc=$?
check "--purge alone refused" "[ $rc -ne 0 ] && grep -q 'only goes with --uninstall' $T/log3"
bash "$T/stage/install.sh" --bogus > "$T/log3" 2>&1; rc=$?
check "unknown option refused" "[ $rc -ne 0 ] && grep -q 'Unknown option: --bogus' $T/log3"

echo "== 4. uninstall keeps the profiles, the settings and the log; known_hosts untouched"
mkdir -p "$XDG_CONFIG_HOME/$APP" "$HOME/.ssh" && touch "$XDG_CONFIG_HOME/$APP/profiles.json" "$D/$APP/$APP.log" "$HOME/.ssh/known_hosts"
bash "$T/stage/install.sh" --uninstall > "$T/log4" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "app and venv gone" "[ ! -e $A ] && [ ! -e $D/$APP/venv ]"
check "profiles, settings, log and known_hosts kept" "[ -f $XDG_CONFIG_HOME/$APP/profiles.json ] && [ -f $D/$APP/$APP.log ] && [ -f $HOME/.ssh/known_hosts ]"
check "launcher and menu entry gone" "[ ! -e $HOME/.local/bin/$APP ] && [ ! -e $D/applications/$APP.desktop ]"

echo "== 5. reinstall, then uninstall --purge"
bash "$T/stage/install.sh" > "$T/log5" 2>&1 && bash "$T/stage/install.sh" --uninstall --purge >> "$T/log5" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"
check "profiles, settings and log removed" "[ ! -e $XDG_CONFIG_HOME/$APP ] && [ ! -e $D/$APP ]"
check "known_hosts still there" "[ -f $HOME/.ssh/known_hosts ]"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 2 3 4 5; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
