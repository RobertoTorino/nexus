#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/xenia/install.sh: install from the checkout (core bundled, shared venv, the run wrapper,
# no sudo), a staged release replacing it, the refusals, uninstall with another venv user (the installed Xenia
# removed; Xenia's own folder, the games and the settings kept) and --purge as the last venv user (the settings
# removed).
# Runs with the shims from shims.sh (CI, or WSL on Windows).
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
T=/tmp/bc250-xenia-manager-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
APP=bc250-xenia-manager
A=$D/$APP/app
RUN=$HOME/.local/bin/bc250-xenia-run
# sudo must never be needed: make it fail loudly.
printf '#!/bin/sh\necho "sudo called: $*" >&2\nexit 1\n' > "$T/shims/sudo"

echo "== 1. install from the suite checkout"
bash "$SUITE/apps/xenia/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "no sudo used" "! grep -q 'sudo called' $T/log1 && [ -z \"\$(ls -A $T/opt)\" ]"
check "app copied" "[ -f $A/xenia_manager/main_window.py ] && [ -f $A/images/$APP.webp ] && [ -f $A/images/$APP-128.png ]"
check "core bundled from checkout" "[ -f $A/bc250_core/steam.py ]"
check "no tests or caches copied" "[ ! -d $A/tests ] && ! find $A -name __pycache__ | grep -q ."
check "shared venv and its user marker" "[ -x $D/bc250-bazzite-suite/venv/bin/python ] && [ -f $D/bc250-bazzite-suite/venv-users/$APP ]"
check "launcher uses shared venv" "grep -qF 'bc250-bazzite-suite/venv/bin/python\" -m xenia_manager' $HOME/.local/bin/$APP"
check "launcher cds into the app" "grep -qF 'cd \"$A\"' $HOME/.local/bin/$APP"
check "run wrapper installed, executable" "[ -x $RUN ] && cmp -s $RUN $SUITE/apps/xenia/bc250-xenia-run"
check "menu entry" "grep -qx 'Exec=$HOME/.local/bin/$APP' $D/applications/$APP.desktop"
check "desktop icon, executable" "[ -x $HOME/Desktop/$APP.desktop ]"
check "core imports from the app copy" "(cd $A && /usr/bin/python3 -c 'import importlib.util as u, sys; s=u.find_spec(\"bc250_core\"); sys.exit(0 if s and s.origin.startswith(\"$A\") else 1)')"

echo "== 2. the run wrapper"
bash "$RUN" --fullscreen=true /games/x.iso > "$T/run.log" 2>&1; rc=$?
check "without Xenia it says so" "[ $rc -eq 1 ] && grep -q 'Xenia is not installed' $T/run.log"
mkdir -p "$D/$APP/emulator/e6cd2e4"
printf '#!/bin/sh\necho "args: $*"\n' > "$D/$APP/emulator/e6cd2e4/xenia.AppImage"
chmod +x "$D/$APP/emulator/e6cd2e4/xenia.AppImage"
ln -sfn e6cd2e4 "$D/$APP/emulator/current"
bash "$RUN" --fullscreen=true "/games/My Game.iso" > "$T/run.log" 2>&1; rc=$?
check "starts the current Xenia with the arguments as given" "[ $rc -eq 0 ] && grep -qxF 'args: --fullscreen=true /games/My Game.iso' $T/run.log"

echo "== 3. install a staged release (core bundled in the tarball) without the Desktop icon"
rm -rf "$T/stage"; /usr/bin/python3 "$NEXUS/tools/stage_app.py" xenia "$T/stage" > /dev/null
echo "# release marker" >> "$T/stage/bc250_core/__init__.py"
bash "$T/stage/install.sh" --no-desktop-shortcut > "$T/log3" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "the release's own core used" "grep -q 'release marker' $A/bc250_core/__init__.py"
check "manual bundled" "[ -f $A/MANUAL.md ]"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"
check "the installed Xenia kept across an update" "[ -x $D/$APP/emulator/current/xenia.AppImage ]"

echo "== 4. refusals"
fakeroot -- bash "$T/stage/install.sh" > "$T/log4" 2>&1; rc=$?
check "root refused" "[ $rc -ne 0 ] && grep -q 'not with sudo' $T/log4"
bash "$T/stage/install.sh" --purge > "$T/log4" 2>&1; rc=$?
check "--purge alone refused" "[ $rc -ne 0 ] && grep -q 'only goes with --uninstall' $T/log4"
bash "$T/stage/install.sh" --bogus > "$T/log4" 2>&1; rc=$?
check "unknown option refused" "[ $rc -ne 0 ] && grep -q 'Unknown option: --bogus' $T/log4"

echo "== 5. uninstall while another suite app uses the venv: Xenia's own folder and the settings kept"
touch "$D/bc250-bazzite-suite/venv-users/bc250-bazzite-test"
mkdir -p "$D/Xenia" "$XDG_CONFIG_HOME/$APP" && touch "$D/Xenia/xenia-canary.config.toml" "$XDG_CONFIG_HOME/$APP/$APP.ini"
bash "$T/stage/install.sh" --uninstall > "$T/log5" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "app and installed Xenia gone" "[ ! -e $A ] && [ ! -e $D/$APP/emulator ]"
check "launchers and menu entry gone" "[ ! -e $HOME/.local/bin/$APP ] && [ ! -e $RUN ] && [ ! -e $D/applications/$APP.desktop ]"
check "Xenia's own folder and the settings kept" "[ -f $D/Xenia/xenia-canary.config.toml ] && [ -f $XDG_CONFIG_HOME/$APP/$APP.ini ]"
check "venv kept, own marker gone" "[ -x $D/bc250-bazzite-suite/venv/bin/python ] && [ ! -e $D/bc250-bazzite-suite/venv-users/$APP ]"

echo "== 6. reinstall, then uninstall --purge as the last venv user"
rm "$D/bc250-bazzite-suite/venv-users/bc250-bazzite-test"
mkdir -p "$D/$APP/covers" && touch "$D/$APP/covers/CUSA00001p.png"       # covers found on SteamGridDB
bash "$T/stage/install.sh" > "$T/log6" 2>&1 && bash "$T/stage/install.sh" --uninstall --purge >> "$T/log6" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "venv removed" "[ ! -e $D/bc250-bazzite-suite/venv ] && [ ! -e $D/bc250-bazzite-suite/venv-users ]"
check "settings and covers removed" "[ ! -e $XDG_CONFIG_HOME/$APP ] && [ ! -e $D/$APP ]"
check "Xenia's own folder still there" "[ -f $D/Xenia/xenia-canary.config.toml ]"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 3 4 5 6; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
