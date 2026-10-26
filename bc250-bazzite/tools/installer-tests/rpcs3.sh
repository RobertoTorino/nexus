#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/rpcs3/install.sh: install from the checkout (core bundled, shared venv, the run wrapper,
# no sudo), a staged release replacing it, the refusals, uninstall with another venv user (the installed RPCS3
# removed; RPCS3's own folder, the games, the settings and the log kept) and --purge as the last venv user (the
# settings, covers and log removed).
# Runs with the shims from shims.sh (CI, or WSL on Windows).
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
T=/tmp/bc250-rpcs3-manager-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
APP=bc250-rpcs3-manager
A=$D/$APP/app
RUN=$HOME/.local/bin/bc250-rpcs3-run
# sudo must never be needed: make it fail loudly.
printf '#!/bin/sh\necho "sudo called: $*" >&2\nexit 1\n' > "$T/shims/sudo"

echo "== 1. install from the suite checkout"
bash "$SUITE/apps/rpcs3/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "no sudo used" "! grep -q 'sudo called' $T/log1 && [ -z \"\$(ls -A $T/opt)\" ]"
check "app copied" "[ -f $A/rpcs3_manager/main_window.py ] && [ -f $A/images/$APP.webp ] && [ -f $A/images/$APP-128.png ]"
check "core bundled from checkout" "[ -f $A/bc250_core/steam.py ]"
check "controller state and core's log copied" "[ -f $A/rpcs3_manager/controllers.py ] && [ -f $A/bc250_core/applog.py ]"
check "no tests or caches copied" "[ ! -d $A/tests ] && ! find $A -name __pycache__ | grep -q ."
check "shared venv and its user marker" "[ -x $D/bc250-bazzite-suite/venv/bin/python ] && [ -f $D/bc250-bazzite-suite/venv-users/$APP ]"
check "launcher uses shared venv" "grep -qF 'bc250-bazzite-suite/venv/bin/python\" -m rpcs3_manager' $HOME/.local/bin/$APP"
check "launcher cds into the app" "grep -qF 'cd \"$A\"' $HOME/.local/bin/$APP"
check "run wrapper installed, executable" "[ -x $RUN ] && cmp -s $RUN $SUITE/apps/rpcs3/bc250-rpcs3-run"
check "menu entry" "grep -qx 'Exec=$HOME/.local/bin/$APP' $D/applications/$APP.desktop"
check "desktop icon, executable" "[ -x $HOME/Desktop/$APP.desktop ]"
check "core imports from the app copy" "(cd $A && /usr/bin/python3 -c 'import importlib.util as u, sys; s=u.find_spec(\"bc250_core\"); sys.exit(0 if s and s.origin.startswith(\"$A\") else 1)')"

echo "== 2. the run wrapper"
bash "$RUN" --no-gui /games/x/USRDIR/EBOOT.BIN > "$T/run.log" 2>&1; rc=$?
check "without RPCS3 it says so" "[ $rc -eq 1 ] && grep -q 'RPCS3 is not installed' $T/run.log"
mkdir -p "$D/$APP/emulator/0.0.43-20395"
printf '#!/bin/sh\necho "args: $*"\n' > "$D/$APP/emulator/0.0.43-20395/rpcs3.AppImage"
chmod +x "$D/$APP/emulator/0.0.43-20395/rpcs3.AppImage"
ln -sfn 0.0.43-20395 "$D/$APP/emulator/current"
bash "$RUN" --no-gui --fullscreen "/games/My Game/PS3_GAME/USRDIR/EBOOT.BIN" > "$T/run.log" 2>&1; rc=$?
check "starts the current RPCS3 with the arguments as given" "[ $rc -eq 0 ] && grep -qxF 'args: --no-gui --fullscreen /games/My Game/PS3_GAME/USRDIR/EBOOT.BIN' $T/run.log"
check "the game started goes to the app's log, by its folder's name" "grep -q ' INFO Started My Game from a terminal, with' $D/$APP/$APP.log && ! grep -q '/games/' $D/$APP/$APP.log"
bash "$RUN" --installpkg "/downloads/My Packages" > "$T/run.log" 2>&1; rc=$?
check "a folder of packages is passed on and not logged as a game" "[ $rc -eq 0 ] && grep -qxF 'args: --installpkg /downloads/My Packages' $T/run.log && ! grep -q 'My Packages' $D/$APP/$APP.log"
bash "$RUN" --headless --installpkg "/downloads/My Packages/Game.pkg" > "$T/run.log" 2>&1; rc=$?
check "a headless install of one package is passed on and not logged as a game" "[ $rc -eq 0 ] && grep -qxF 'args: --headless --installpkg /downloads/My Packages/Game.pkg' $T/run.log && ! grep -q 'Game.pkg' $D/$APP/$APP.log"

echo "== 3. install a staged release (core bundled in the tarball) without the Desktop icon"
rm -rf "$T/stage"; /usr/bin/python3 "$NEXUS/tools/stage_app.py" rpcs3 "$T/stage" > /dev/null
echo "# release marker" >> "$T/stage/bc250_core/__init__.py"
bash "$T/stage/install.sh" --no-desktop-shortcut > "$T/log3" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "the release's own core used" "grep -q 'release marker' $A/bc250_core/__init__.py"
check "manual bundled" "[ -f $A/MANUAL.md ]"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"
check "the installed RPCS3 kept across an update" "[ -x $D/$APP/emulator/current/rpcs3.AppImage ]"

echo "== 4. refusals"
fakeroot -- bash "$T/stage/install.sh" > "$T/log4" 2>&1; rc=$?
check "root refused" "[ $rc -ne 0 ] && grep -q 'not with sudo' $T/log4"
bash "$T/stage/install.sh" --purge > "$T/log4" 2>&1; rc=$?
check "--purge alone refused" "[ $rc -ne 0 ] && grep -q 'only goes with --uninstall' $T/log4"
bash "$T/stage/install.sh" --bogus > "$T/log4" 2>&1; rc=$?
check "unknown option refused" "[ $rc -ne 0 ] && grep -q 'Unknown option: --bogus' $T/log4"

echo "== 5. uninstall while another suite app uses the venv: RPCS3's own folder, the settings and the log kept"
touch "$D/bc250-bazzite-suite/venv-users/bc250-bazzite-test"
mkdir -p "$XDG_CONFIG_HOME/rpcs3/dev_flash" "$XDG_CONFIG_HOME/$APP" && touch "$XDG_CONFIG_HOME/rpcs3/config.yml" "$XDG_CONFIG_HOME/$APP/$APP.ini"
echo "24-10-2026 04:00:00 INFO RPCS3 Manager started" > "$D/$APP/$APP.log"
bash "$T/stage/install.sh" --uninstall > "$T/log5" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "app and installed RPCS3 gone" "[ ! -e $A ] && [ ! -e $D/$APP/emulator ]"
check "launchers and menu entry gone" "[ ! -e $HOME/.local/bin/$APP ] && [ ! -e $RUN ] && [ ! -e $D/applications/$APP.desktop ]"
check "RPCS3's own folder and the settings kept" "[ -f $XDG_CONFIG_HOME/rpcs3/config.yml ] && [ -d $XDG_CONFIG_HOME/rpcs3/dev_flash ] && [ -f $XDG_CONFIG_HOME/$APP/$APP.ini ]"
check "the log kept" "[ -f $D/$APP/$APP.log ]"
check "venv kept, own marker gone" "[ -x $D/bc250-bazzite-suite/venv/bin/python ] && [ ! -e $D/bc250-bazzite-suite/venv-users/$APP ]"

echo "== 6. reinstall, then uninstall --purge as the last venv user"
rm "$D/bc250-bazzite-suite/venv-users/bc250-bazzite-test"
mkdir -p "$D/$APP/covers" && touch "$D/$APP/covers/CUSA00001p.png"       # covers found on SteamGridDB
bash "$T/stage/install.sh" > "$T/log6" 2>&1 && bash "$T/stage/install.sh" --uninstall --purge >> "$T/log6" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "venv removed" "[ ! -e $D/bc250-bazzite-suite/venv ] && [ ! -e $D/bc250-bazzite-suite/venv-users ]"
check "settings, covers and log removed" "[ ! -e $XDG_CONFIG_HOME/$APP ] && [ ! -e $D/$APP ]"
check "RPCS3's own folder still there" "[ -f $XDG_CONFIG_HOME/rpcs3/config.yml ]"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 3 4 5 6; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
