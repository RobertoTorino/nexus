#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/shadps4/install.sh: install from the checkout (core bundled, the app's own venv, both
# launchers in the caller's folder, the run wrapper, no sudo) over a standalone Bazzite pkgxtractor and an install
# from before the own venv, a staged release replacing it, the refusals, uninstall (the installed shadPS4 and the
# venv removed; shadPS4's own folder, the games, the settings and the log kept) and --purge.
# Runs with the shims from shims.sh (CI, or WSL on Windows).
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
T=/tmp/bc250-shadps4-manager-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
APP=bc250-shadps4-manager
A=$D/$APP/app
CLI=$HOME/.local/bin/bc250-shadps4-pkg-cli
RUN=$HOME/.local/bin/bc250-shadps4-run
SHARED=$D/bc250-bazzite-suite
OLD=bazzite-pkgxtractor
# sudo must never be needed: make it fail loudly.
printf '#!/bin/sh\necho "sudo called: $*" >&2\nexit 1\n' > "$T/shims/sudo"

# The launcher runs in the caller's folder and still takes the app's own package: a probe in place of the installed
# module, the real python instead of the stub venv's, started from a folder that holds a look-alike package.
probe_launcher() {   # probe_launcher <launcher> <module file under $A> <package>; prints what the probe saw
    local stub="$T/stub-python" out
    cp "$D/$APP/venv/bin/python" "$stub" && printf '#!/bin/sh\nexec /usr/bin/python3 "$@"\n' > "$D/$APP/venv/bin/python"
    cp "$A/$2" "$T/module.bak"
    printf 'import os, sys\nimport %s\nprint("cwd=" + os.getcwd())\nprint("pkg=" + os.path.dirname(%s.__file__))\nprint("args=" + "|".join(sys.argv[1:]))\n' "$3" "$3" > "$A/$2"
    rm -rf "$T/elsewhere"; mkdir -p "$T/elsewhere/$3" && echo 'raise SystemExit("look-alike package imported")' > "$T/elsewhere/$3/__init__.py"
    out=$(cd "$T/elsewhere" && "$1" "game 1.pkg" sub/out 2>&1)
    cp "$T/module.bak" "$A/$2"; mv "$stub" "$D/$APP/venv/bin/python"
    printf '%s\n' "$out"
}

echo "== 0. what an earlier install left: the standalone Bazzite pkgxtractor, and this app on the shared venv"
mkdir -p "$D/$OLD/app" "$D/$OLD/venv" "$D/applications" "$HOME/Desktop" "$HOME/.local/bin" "$XDG_CONFIG_HOME/$OLD" "$SHARED/venv/bin" \
    "$SHARED/venv-users"
touch "$HOME/.local/bin/$OLD" "$HOME/.local/bin/$OLD-cli" "$D/applications/$OLD.desktop" "$HOME/Desktop/$OLD.desktop" \
    "$D/$OLD/$OLD.log" "$XDG_CONFIG_HOME/$OLD/$OLD.ini" "$SHARED/venv/bin/python" "$SHARED/venv-users/$APP" \
    "$SHARED/venv-users/bc250-bazzite-test"

echo "== 1. install from the suite checkout"
bash "$SUITE/apps/shadps4/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "no sudo used" "! grep -q 'sudo called' $T/log1 && [ -z \"\$(ls -A $T/opt)\" ]"
check "app copied, with the package extractor" "[ -f $A/shadps4_manager/main_window.py ] && [ -f $A/shadps4_manager/extract_dialog.py ] && [ -f $A/shadps4_manager/pkgxtractor/cli.py ] && [ -f $A/images/$APP.webp ] && [ -f $A/images/$APP-128.png ]"
check "controller state, settings and core's log copied" "[ -f $A/shadps4_manager/controllers.py ] && [ -f $A/shadps4_manager/settings_page.py ] && [ -f $A/shadps4_manager/arrow-down.svg ] && [ -f $A/bc250_core/applog.py ]"
check "core bundled from checkout" "[ -f $A/bc250_core/steam.py ]"
check "no tests or caches copied" "[ ! -d $A/tests ] && ! find $A -name __pycache__ | grep -q ."
check "own venv" "[ -x $D/$APP/venv/bin/python ]"
check "off the shared venv, which another app still uses" "[ ! -e $SHARED/venv-users/$APP ] && [ -e $SHARED/venv/bin/python ] && grep -q 'other suite apps still use it' $T/log1"
check "launcher uses the own venv" "grep -qF '$APP/venv/bin/python\" -c ' $HOME/.local/bin/$APP && grep -qF '\"$A\" shadps4_manager \"' $HOME/.local/bin/$APP"
check "CLI launcher uses the own venv" "grep -qF '$APP/venv/bin/python\" -c ' $CLI && grep -qF '\"$A\" shadps4_manager.pkgxtractor.cli \"' $CLI"
check "launchers do not change folder" "! grep -q '^cd ' $HOME/.local/bin/$APP && ! grep -q '^cd ' $CLI"
out=$(probe_launcher $HOME/.local/bin/$APP shadps4_manager/__main__.py shadps4_manager); here=$(cd "$T/elsewhere" && pwd -P)
check "launcher runs in the caller's folder" "printf '%s\n' \"$out\" | grep -qxF \"cwd=$here\""
check "launcher imports the app's package, not the folder's" "printf '%s\n' \"$out\" | grep -qxF \"pkg=$A/shadps4_manager\""
check "launcher passes relative paths as given" "printf '%s\n' \"$out\" | grep -qxF 'args=game 1.pkg|sub/out'"
out=$(probe_launcher $CLI shadps4_manager/pkgxtractor/cli.py shadps4_manager); here=$(cd "$T/elsewhere" && pwd -P)
check "CLI launcher runs in the caller's folder" "printf '%s\n' \"$out\" | grep -qxF \"cwd=$here\""
check "CLI launcher imports the app's package, not the folder's" "printf '%s\n' \"$out\" | grep -qxF \"pkg=$A/shadps4_manager\""
check "CLI launcher passes relative paths as given" "printf '%s\n' \"$out\" | grep -qxF 'args=game 1.pkg|sub/out'"
check "launchers executable" "[ -x $HOME/.local/bin/$APP ] && [ -x $CLI ]"
check "run wrapper installed, executable" "[ -x $RUN ] && cmp -s $RUN $SUITE/apps/shadps4/bc250-shadps4-run"
check "menu entry opens a package" "grep -qx 'Exec=$HOME/.local/bin/$APP %f' $D/applications/$APP.desktop"
check "desktop icon, executable" "[ -x $HOME/Desktop/$APP.desktop ]"
check "core imports from the app copy" "(cd $A && /usr/bin/python3 -c 'import importlib.util as u, sys; s=u.find_spec(\"bc250_core\"); sys.exit(0 if s and s.origin.startswith(\"$A\") else 1)')"
check "standalone pkgxtractor removed" "[ ! -e $D/$OLD ] && [ ! -e $HOME/.local/bin/$OLD ] && [ ! -e $HOME/.local/bin/$OLD-cli ] && [ ! -e $D/applications/$OLD.desktop ] && [ ! -e $HOME/Desktop/$OLD.desktop ] && grep -q 'Removing the standalone Bazzite pkgxtractor' $T/log1"
check "its settings kept, for the app to adopt" "[ -f $XDG_CONFIG_HOME/$OLD/$OLD.ini ]"

echo "== 2. the run wrapper"
bash "$RUN" -g /games/x/eboot.bin > "$T/run.log" 2>&1; rc=$?
check "without shadPS4 it says so" "[ $rc -eq 1 ] && grep -q 'shadPS4 is not installed' $T/run.log"
mkdir -p "$D/$APP/emulator/0.19.0"
printf '#!/bin/sh\necho "args: $*"\necho "dir: $(pwd)"\n' > "$D/$APP/emulator/0.19.0/Shadps4-sdl.AppImage"
chmod +x "$D/$APP/emulator/0.19.0/Shadps4-sdl.AppImage"
ln -sfn 0.19.0 "$D/$APP/emulator/current"
(cd "$T" && bash "$RUN" -f true -g "/games/My Game/eboot.bin") > "$T/run.log" 2>&1; rc=$?
check "starts the current shadPS4 with the arguments as given" "[ $rc -eq 0 ] && grep -qxF 'args: -f true -g /games/My Game/eboot.bin' $T/run.log"
check "started beside the AppImage (no portable user folder)" "grep -qxF \"dir: $D/$APP/emulator/0.19.0\" $T/run.log || grep -qxF \"dir: $D/$APP/emulator/current\" $T/run.log"
check "the game started goes to the app's log, by its folder's name" "grep -q ' INFO Started My Game from a terminal, with' $D/$APP/$APP.log && ! grep -q '/games/' $D/$APP/$APP.log"
(cd "$T" && bash "$RUN" -b) > "$T/run.log" 2>&1; rc=$?
check "shadPS4's own window is passed on and not logged as a game" "[ $rc -eq 0 ] && grep -qxF 'args: -b' $T/run.log && [ \$(grep -c Started $D/$APP/$APP.log) -eq 1 ]"

echo "== 3. install a staged release (core bundled in the tarball) without the Desktop icon"
rm -rf "$T/stage"; /usr/bin/python3 "$NEXUS/tools/stage_app.py" shadps4 "$T/stage" > /dev/null
echo "# release marker" >> "$T/stage/bc250_core/__init__.py"
echo "# release marker" >> "$T/stage/shadps4_manager/pkgxtractor/__init__.py"
bash "$T/stage/install.sh" --no-desktop-shortcut > "$T/log3" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "the release's own core used" "grep -q 'release marker' $A/bc250_core/__init__.py"
check "the release's own extractor used" "grep -q 'release marker' $A/shadps4_manager/pkgxtractor/__init__.py"
check "manual bundled" "[ -f $A/MANUAL.md ]"
check "no development files bundled" "[ ! -e $A/requirements-dev.txt ] && [ ! -d $A/tests ]"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"
check "the installed shadPS4 kept across an update" "[ -x $D/$APP/emulator/current/Shadps4-sdl.AppImage ]"
check "no standalone to remove this time" "! grep -q 'Removing the standalone' $T/log3"

echo "== 4. refusals"
fakeroot -- bash "$T/stage/install.sh" > "$T/log4" 2>&1; rc=$?
check "root refused" "[ $rc -ne 0 ] && grep -q 'not with sudo' $T/log4"
bash "$T/stage/install.sh" --purge > "$T/log4" 2>&1; rc=$?
check "--purge alone refused" "[ $rc -ne 0 ] && grep -q 'only goes with --uninstall' $T/log4"
bash "$T/stage/install.sh" --bogus > "$T/log4" 2>&1; rc=$?
check "unknown option refused" "[ $rc -ne 0 ] && grep -q 'Unknown option: --bogus' $T/log4"

echo "== 5. uninstall: shadPS4's own folder, the settings and the log kept"
mkdir -p "$D/shadPS4/sys_modules" "$XDG_CONFIG_HOME/$APP" && touch "$D/shadPS4/config.json" "$XDG_CONFIG_HOME/$APP/$APP.ini" \
    "$D/$APP/pkgxtractor.log"
bash "$T/stage/install.sh" --uninstall > "$T/log5" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "app, venv and installed shadPS4 gone" "[ ! -e $A ] && [ ! -e $D/$APP/venv ] && [ ! -e $D/$APP/emulator ]"
check "launchers and menu entry gone" "[ ! -e $HOME/.local/bin/$APP ] && [ ! -e $CLI ] && [ ! -e $RUN ] && [ ! -e $D/applications/$APP.desktop ]"
check "shadPS4's own folder, the settings and the log kept" "[ -f $D/shadPS4/config.json ] && [ -d $D/shadPS4/sys_modules ] && [ -f $XDG_CONFIG_HOME/$APP/$APP.ini ] && [ -f $D/$APP/pkgxtractor.log ]"
check "the shared venv untouched" "[ -e $SHARED/venv/bin/python ] && [ -e $SHARED/venv-users/bc250-bazzite-test ]"

echo "== 6. an install on the shared venv as its last user: the shared venv goes"
rm "$SHARED/venv-users/bc250-bazzite-test" && touch "$SHARED/venv-users/$APP"
bash "$T/stage/install.sh" > "$T/log6" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "shared venv removed" "[ ! -e $SHARED/venv ] && [ ! -e $SHARED/venv-users ] && grep -q 'no other suite app uses it' $T/log6"

echo "== 7. uninstall --purge"
bash "$T/stage/install.sh" --uninstall --purge > "$T/log7" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "settings and logs removed" "[ ! -e $XDG_CONFIG_HOME/$APP ] && [ ! -e $D/$APP ]"
check "shadPS4's own folder still there" "[ -f $D/shadPS4/config.json ]"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 3 4 5 6 7; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
