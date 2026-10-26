#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/fan/install.sh: install from the checkout (core bundled, shared venv, no sudo), a staged
# release replacing it (and saying when the thermal guard in /etc is from another version), uninstall with and
# without other venv users (the guard stopped and removed with sudo), --purge (settings removed), and the refusal to
# run as root.
# Runs with the shims from shims.sh (CI, or WSL on Windows).
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
T=/tmp/bc250-fan-control-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
APP=bc250-fan-control
A=$D/$APP/app
export BC250_SYSTEM_ROOT=$T/system                  # the guard's /etc
GUARD=$BC250_SYSTEM_ROOT/etc
# sudo is only for removing the guard: until then make it fail loudly. systemctl only records what it was asked.
cp "$T/shims/sudo" "$T/sudo-fakeroot"
printf '#!/bin/sh\necho "sudo called: $*" >&2\nexit 1\n' > "$T/shims/sudo"
printf '#!/bin/sh\necho "$*" >> "%s"\n' "$T/systemctl.log" > "$T/shims/systemctl"
chmod +x "$T/shims/systemctl"

echo "== 1. install from the suite checkout"
bash "$SUITE/apps/fan/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "no sudo used" "! grep -q 'sudo called' $T/log1 && [ -z \"\$(ls -A $T/opt)\" ]"
check "app copied" "[ -f $A/fan_control/main_window.py ] && [ -f $A/images/$APP.webp ] && [ -f $A/images/$APP-128.png ]"
check "guard helper copied" "[ -f $A/fan_control/guard.py ]"
check "core bundled from checkout" "[ -f $A/bc250_core/theme.py ]"
check "no tests or caches copied" "[ ! -d $A/tests ] && ! find $A -name __pycache__ | grep -q ."
check "shared venv" "[ -x $D/bc250-bazzite-suite/venv/bin/python ]"
check "venv user marker" "[ -f $D/bc250-bazzite-suite/venv-users/$APP ]"
check "launcher uses shared venv" "grep -qF 'bc250-bazzite-suite/venv/bin/python\" -m fan_control' $HOME/.local/bin/$APP"
check "launcher cds into the app" "grep -qF 'cd \"$A\"' $HOME/.local/bin/$APP"
check "menu entry" "grep -qx 'Exec=$HOME/.local/bin/$APP' $D/applications/$APP.desktop"
check "desktop icon, executable" "[ -x $HOME/Desktop/$APP.desktop ]"
check "the guard is not installed by the installer" "[ ! -e $GUARD/$APP ] && [ ! -s $T/systemctl.log ]"
check "core imports from the app copy" "(cd $A && /usr/bin/python3 -c 'import importlib.util as u, sys; s=u.find_spec(\"bc250_core\"); sys.exit(0 if s and s.origin.startswith(\"$A\") else 1)')"

echo "== 2. install a staged release (core bundled in the tarball) without the Desktop icon, an older guard in /etc"
rm -rf "$T/stage"; /usr/bin/python3 "$NEXUS/tools/stage_app.py" fan "$T/stage" > /dev/null
echo "# release marker" >> "$T/stage/bc250_core/__init__.py"
mkdir -p "$GUARD/$APP" "$GUARD/systemd/system"
echo "# an older version" > "$GUARD/$APP/guard.py"
echo '{"warn_c": 85, "cool_c": 90, "shutdown_c": 95, "hold_s": 10}' > "$GUARD/$APP/guard.json"
echo "[Unit]" > "$GUARD/systemd/system/bc250-fan-control-guard.service"
bash "$T/stage/install.sh" --no-desktop-shortcut > "$T/log2" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "the release's own core used" "grep -q 'release marker' $A/bc250_core/__init__.py"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"
check "an older guard is reported, without sudo" "grep -q 'guard is from another version' $T/log2 && ! grep -q 'sudo called' $T/log2"
check "the guard is left as it is" "grep -q 'an older version' $GUARD/$APP/guard.py"
cp "$A/fan_control/guard.py" "$GUARD/$APP/guard.py"
bash "$T/stage/install.sh" --no-desktop-shortcut > "$T/log2b" 2>&1
check "the same version is not reported" "! grep -q 'another version' $T/log2b"

echo "== 3. refuses to run as root"
fakeroot -- bash "$T/stage/install.sh" > "$T/log3" 2>&1; rc=$?
check "exit non-zero" "[ $rc -ne 0 ] && grep -q 'not with sudo' $T/log3"

echo "== 4. uninstall while another suite app still uses the venv; the guard goes with the app"
touch "$D/bc250-bazzite-suite/venv-users/bc250-bazzite-test"
echo "[Unit]" > "$GUARD/systemd/system/other.service"
cp "$T/shims/sudo" "$T/sudo-failing" && cp "$T/sudo-fakeroot" "$T/shims/sudo"
bash "$T/stage/install.sh" --uninstall > "$T/log4" 2>&1; rc=$?
cp "$T/sudo-failing" "$T/shims/sudo"
check "exit 0" "[ $rc -eq 0 ]"
check "app gone" "[ ! -e $A ]"
check "guard stopped and removed" "[ ! -e $GUARD/$APP ] && [ ! -e $GUARD/systemd/system/bc250-fan-control-guard.service ] && grep -qx 'disable --now bc250-fan-control-guard.service' $T/systemctl.log"
check "systemd reloaded, other units kept" "grep -qx 'daemon-reload' $T/systemctl.log && [ -f $GUARD/systemd/system/other.service ]"
check "venv kept" "[ -x $D/bc250-bazzite-suite/venv/bin/python ]"
check "own marker gone" "[ ! -e $D/bc250-bazzite-suite/venv-users/$APP ]"
check "launcher and menu entry gone" "[ ! -e $HOME/.local/bin/$APP ] && [ ! -e $D/applications/$APP.desktop ]"

echo "== 5. reinstall, then uninstall --purge as the last venv user"
rm "$D/bc250-bazzite-suite/venv-users/bc250-bazzite-test"
mkdir -p "$XDG_CONFIG_HOME/$APP" && touch "$XDG_CONFIG_HOME/$APP/$APP.ini"
bash "$T/stage/install.sh" > "$T/log5" 2>&1 && bash "$T/stage/install.sh" --uninstall --purge >> "$T/log5" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "no sudo without a guard" "! grep -q 'sudo called' $T/log5"
check "venv removed" "[ ! -e $D/bc250-bazzite-suite/venv ] && [ ! -e $D/bc250-bazzite-suite/venv-users ]"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"
check "settings removed" "[ ! -e $XDG_CONFIG_HOME/$APP ] && [ ! -e $D/$APP ]"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 2 2b 3 4 5; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
