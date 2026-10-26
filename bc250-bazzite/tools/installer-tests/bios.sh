#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/bios/install.sh: install from the checkout (core bundled, shared venv, no sudo), a staged
# release replacing it, uninstall with and without other venv users (BIOS dumps kept), --purge (dumps removed), and
# the refusal to run as root.
# Runs with the shims from shims.sh (CI, or WSL on Windows).
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
T=/tmp/bc250-bios-reader-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
APP=bc250-bios-reader
A=$D/$APP/app
# sudo must never be needed: make it fail loudly.
printf '#!/bin/sh\necho "sudo called: $*" >&2\nexit 1\n' > "$T/shims/sudo"

echo "== 1. install from the suite checkout"
bash "$SUITE/apps/bios/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "no sudo used" "! grep -q 'sudo called' $T/log1 && [ -z \"\$(ls -A $T/opt)\" ]"
check "app copied" "[ -f $A/bios_reader/bios.py ] && [ -f $A/images/$APP.webp ] && [ -f $A/images/$APP-128.png ]"
check "built-in table copied" "[ -f $A/bios_reader/tables/P5.00.json.gz ]"
check "core bundled from checkout" "[ -f $A/bc250_core/theme.py ]"
check "no tests or caches copied" "[ ! -d $A/tests ] && ! find $A -name __pycache__ | grep -q ."
check "shared venv" "[ -x $D/bc250-bazzite-suite/venv/bin/python ]"
check "venv user marker" "[ -f $D/bc250-bazzite-suite/venv-users/$APP ]"
check "launcher uses shared venv" "grep -qF 'bc250-bazzite-suite/venv/bin/python\" -m bios_reader' $HOME/.local/bin/$APP"
check "launcher cds into the app" "grep -qF 'cd \"$A\"' $HOME/.local/bin/$APP"
check "menu entry" "grep -qx 'Exec=$HOME/.local/bin/$APP' $D/applications/$APP.desktop"
check "desktop icon, executable" "[ -x $HOME/Desktop/$APP.desktop ]"
check "core imports from the app copy" "(cd $A && /usr/bin/python3 -c 'import importlib.util as u, sys; s=u.find_spec(\"bc250_core\"); sys.exit(0 if s and s.origin.startswith(\"$A\") else 1)')"

echo "== 2. install a staged release (core bundled in the tarball) without the Desktop icon"
rm -rf "$T/stage"; /usr/bin/python3 "$NEXUS/tools/stage_app.py" bios "$T/stage" > /dev/null
echo "# release marker" >> "$T/stage/bc250_core/__init__.py"
bash "$T/stage/install.sh" --no-desktop-shortcut > "$T/log2" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "the release's own core used" "grep -q 'release marker' $A/bc250_core/__init__.py"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"

echo "== 3. refuses to run as root"
fakeroot -- bash "$T/stage/install.sh" > "$T/log3" 2>&1; rc=$?
check "exit non-zero" "[ $rc -ne 0 ] && grep -q 'not with sudo' $T/log3"

echo "== 4. uninstall while another suite app still uses the venv; a dump is kept"
touch "$D/bc250-bazzite-suite/venv-users/bc250-bazzite-test"
mkdir -p "$D/$APP/dumps" && touch "$D/$APP/dumps/bios-1.bin"
bash "$T/stage/install.sh" --uninstall > "$T/log4" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "app gone, dump kept" "[ ! -e $A ] && [ -f $D/$APP/dumps/bios-1.bin ]"
check "venv kept" "[ -x $D/bc250-bazzite-suite/venv/bin/python ]"
check "own marker gone" "[ ! -e $D/bc250-bazzite-suite/venv-users/$APP ]"
check "launcher and menu entry gone" "[ ! -e $HOME/.local/bin/$APP ] && [ ! -e $D/applications/$APP.desktop ]"

echo "== 5. reinstall, then uninstall --purge as the last venv user"
rm "$D/bc250-bazzite-suite/venv-users/bc250-bazzite-test"
mkdir -p "$XDG_CONFIG_HOME/$APP" && touch "$XDG_CONFIG_HOME/$APP/$APP.ini"
bash "$T/stage/install.sh" > "$T/log5" 2>&1 && bash "$T/stage/install.sh" --uninstall --purge >> "$T/log5" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "venv removed" "[ ! -e $D/bc250-bazzite-suite/venv ] && [ ! -e $D/bc250-bazzite-suite/venv-users ]"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"
check "settings and dumps removed" "[ ! -e $XDG_CONFIG_HOME/$APP ] && [ ! -e $D/$APP ]"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 2 3 4 5; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
