#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/consoles/install.sh: install from the checkout (core bundled, the app's own venv, no sudo), a
# staged release replacing it without the Desktop icon, the refusals, uninstall (settings and registered consoles
# kept, the suite's shared venv untouched) and --purge (removed). Runs with the shims from shims.sh (CI, or WSL on
# Windows).
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
T=/tmp/bc250-console-link-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
APP=bc250-console-link
A=$D/$APP/app
CONSOLES=$XDG_CONFIG_HOME/$APP/consoles.json
printf '#!/bin/sh\necho "sudo called: $*" >&2\nexit 1\n' > "$T/shims/sudo"

# cargo's build output, there after a local build of the native core: it must not be installed or staged. Made
# here when missing (CI), and removed again at the end.
TARGET=$SUITE/apps/consoles/native/target
[ -e "$TARGET" ] && made_target=false || { mkdir -p "$TARGET/release"; touch "$TARGET/release/marker"; made_target=true; }

# BC250 Remote Play, the app's former name, installed with a registered console.
OLD=bc250-remote-play
mkdir -p "$D/$OLD/app" "$XDG_CONFIG_HOME/$OLD" "$HOME/.local/bin" "$D/applications"
echo '{"consoles": ["old"]}' > "$XDG_CONFIG_HOME/$OLD/consoles.json"; echo "[General]" > "$XDG_CONFIG_HOME/$OLD/$OLD.ini"
touch "$HOME/.local/bin/$OLD" "$D/applications/$OLD.desktop" "$HOME/Desktop/$OLD.desktop"

echo "== 1. install from the suite checkout"
bash "$SUITE/apps/consoles/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "no sudo used" "! grep -q 'sudo called' $T/log1"
check "app copied" "[ -f $A/consoles_link/main_window.py ] && [ -f $A/consoles_link/keys.py ] && [ -f $A/images/$APP.webp ] && [ -f $A/images/$APP-128.png ]"
check "core bundled from checkout" "[ -f $A/bc250_core/theme.py ]"
check "no tests or caches copied" "[ ! -d $A/tests ] && ! find $A -name __pycache__ | grep -q ."
check "native core source copied, no build output" "[ -f $A/native/src/takion.rs ] && [ ! -e $A/native/target ]"
check "native core built when Rust is there, a note when not" "grep -q 'native core' $T/log1 && ! grep -q 'from the release' $T/log1"
check "own venv, not the suite's" "[ -x $D/$APP/venv/bin/python ] && [ ! -e $D/bc250-bazzite-suite/venv ]"
check "launcher uses the app's venv" "grep -qF '$APP/venv/bin/python\" -m consoles_link' $HOME/.local/bin/$APP"
check "launcher cds into the app" "grep -qF 'cd \"$A\"' $HOME/.local/bin/$APP"
check "menu entry" "grep -qx 'Exec=$HOME/.local/bin/$APP' $D/applications/$APP.desktop"
check "desktop icon, executable" "[ -x $HOME/Desktop/$APP.desktop ]"
check "former name's program files removed" "[ ! -e $D/$OLD ] && [ ! -e $HOME/.local/bin/$OLD ] && [ ! -e $D/applications/$OLD.desktop ] && [ ! -e $HOME/Desktop/$OLD.desktop ]"
check "former name's consoles and settings moved" "grep -q old $CONSOLES && [ -f $XDG_CONFIG_HOME/$APP/$APP.ini ] && [ ! -e $XDG_CONFIG_HOME/$OLD ]"
rm -f "$CONSOLES" "$XDG_CONFIG_HOME/$APP/$APP.ini"
check "core imports from the app copy" "(cd $A && /usr/bin/python3 -c 'import importlib.util as u, sys; s=u.find_spec(\"bc250_core\"); sys.exit(0 if s and s.origin.startswith(\"$A\") else 1)')"

echo "== 2. install a staged release (core bundled in the tarball) without the Desktop icon"
rm -rf "$T/stage"; /usr/bin/python3 "$NEXUS/tools/stage_app.py" consoles "$T/stage" > /dev/null
echo "# release marker" >> "$T/stage/bc250_core/__init__.py"
mkdir -p "$T/stage/native/wheel" && touch "$T/stage/native/wheel/bc250_console_link_core-0.1.0-cp310-abi3-linux_x86_64.whl"
bash "$T/stage/install.sh" --no-desktop-shortcut > "$T/log2" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "the release's own core used" "grep -q 'release marker' $A/bc250_core/__init__.py"
check "staged release has no build output" "[ -f $T/stage/native/Cargo.toml ] && [ ! -e $T/stage/native/target ]"
check "the release's wheel installed, nothing built" "grep -q 'from the release (bc250_console_link_core-0.1.0-' $T/log2 && ! grep -q 'Building the native core' $T/log2"
check "license and key tables shipped" "[ -f $A/LICENSE ] && grep -q 'AFFERO' $A/LICENSE && [ -f $A/consoles_link/keys.py ]"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"

echo "== 3. refusals"
bash "$T/stage/install.sh" --purge > "$T/log3" 2>&1; rc=$?
check "--purge alone refused" "[ $rc -ne 0 ] && grep -q 'only goes with --uninstall' $T/log3"
bash "$T/stage/install.sh" --bogus > "$T/log3" 2>&1; rc=$?
check "unknown option refused" "[ $rc -ne 0 ] && grep -q 'Unknown option: --bogus' $T/log3"
fakeroot -- bash "$T/stage/install.sh" > "$T/log3" 2>&1; rc=$?
check "root refused" "[ $rc -ne 0 ] && grep -q 'not with sudo' $T/log3"

echo "== 4. uninstall keeps the settings and the registered consoles"
mkdir -p "$(dirname "$CONSOLES")" && echo '{"consoles": []}' > "$CONSOLES"
mkdir -p "$D/bc250-bazzite-suite/venv/bin" && touch "$D/bc250-bazzite-suite/venv/bin/python"
bash "$T/stage/install.sh" --uninstall > "$T/log4" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "app, venv, launcher and menu entry gone" "[ ! -e $D/$APP ] && [ ! -e $HOME/.local/bin/$APP ] && [ ! -e $D/applications/$APP.desktop ]"
check "registered consoles kept" "[ -f $CONSOLES ] && grep -q 'kept' $T/log4"
check "the suite's shared venv untouched" "[ -e $D/bc250-bazzite-suite/venv/bin/python ]"

echo "== 5. reinstall, then uninstall --purge"
bash "$T/stage/install.sh" > "$T/log5" 2>&1 && bash "$T/stage/install.sh" --uninstall --purge >> "$T/log5" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "settings and consoles removed" "[ ! -e $XDG_CONFIG_HOME/$APP ] && [ ! -e $D/$APP ]"
check "says to remove the board on the console too" "grep -q 'Link Device' $T/log5"

$made_target && rm -rf "$TARGET"
[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 2 3 4 5; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
