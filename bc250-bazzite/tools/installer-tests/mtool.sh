#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/mtool/install.sh without network or root; its recording folder survives uninstall.
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
T=/tmp/bc250-media-tool-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
APP=media-tool
L=$HOME/.local/bin/$APP
M=$XDG_DATA_HOME/applications/$APP.desktop
R=$HOME/MediaToolRecordings
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
I=$DESKTOP_DIR/$APP.desktop
OLD=simple-demo-tool   # the tool before its rename (Simple Demo Tool)
plant_old() {
    mkdir -p "$XDG_DATA_HOME/$OLD/venv/bin" "$HOME/SimpleVideoToolRecordings" "$DESKTOP_DIR"
    printf '#!/bin/sh\n' > "$HOME/.local/bin/$OLD"
    printf '[Desktop Entry]\n' | tee "$XDG_DATA_HOME/applications/$OLD.desktop" > "$DESKTOP_DIR/$OLD.desktop"
    printf 'an old recording\n' > "$HOME/SimpleVideoToolRecordings/old.mkv"
}
old_gone() {
    [ ! -e "$HOME/.local/bin/$OLD" ] && [ ! -e "$XDG_DATA_HOME/applications/$OLD.desktop" ] &&
        [ ! -e "$DESKTOP_DIR/$OLD.desktop" ] && [ ! -e "$XDG_DATA_HOME/$OLD" ] &&
        [ -f "$HOME/SimpleVideoToolRecordings/old.mkv" ]
}

echo "== 1. install"
bash "$SUITE/apps/mtool/install.sh" > "$T/install.log" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "launcher and menu entry" "[ -x $L ] && grep -qx 'Exec=$L' $M"
check "package and icons installed" "[ -f $XDG_DATA_HOME/$APP/media_tool/__main__.py ] && [ -f $XDG_DATA_HOME/$APP/images/media-tool.webp ] && [ -f $XDG_DATA_HOME/$APP/images/media-tool-128.png ]"
check "desktop shortcut" "[ -x $I ]"
check "recordings folder created" "[ -d $R ]"
printf 'keep this recording\n' > "$R/keep.mkv"

echo "== 2. reinstall without the Desktop icon"
plant_old
bash "$SUITE/apps/mtool/install.sh" --no-desktop-shortcut > "$T/reinstall.log" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "desktop icon removed, menu entry kept" "[ ! -e $I ] && [ -f $M ]"
check "the copy before the rename removed, its recordings kept" "old_gone"

echo "== 3. refusals"
bash "$SUITE/apps/mtool/install.sh" --purge > "$T/refuse.log" 2>&1; rc=$?
check "--purge alone refused" "[ $rc -ne 0 ] && grep -q 'only goes with --uninstall' $T/refuse.log"
bash "$SUITE/apps/mtool/install.sh" --bogus > "$T/refuse.log" 2>&1; rc=$?
check "unknown option refused" "[ $rc -ne 0 ] && grep -q 'Unknown option: --bogus' $T/refuse.log"
fakeroot -- bash "$SUITE/apps/mtool/install.sh" > "$T/refuse.log" 2>&1; rc=$?
check "root refused" "[ $rc -ne 0 ] && grep -q 'not with sudo' $T/refuse.log"

echo "== 4. uninstall --purge"
plant_old
bash "$SUITE/apps/mtool/install.sh" --uninstall --purge > "$T/uninstall.log" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "app launchers and files removed" "[ ! -e $L ] && [ ! -e $M ] && [ ! -e $I ] && [ ! -e $XDG_DATA_HOME/$APP ]"
check "recordings remain" "[ -f $R/keep.mkv ]"
check "the copy before the rename removed too" "old_gone"

[ $fail -eq 0 ] && echo "ALL OK" || { cat "$T/install.log" "$T/reinstall.log" "$T/uninstall.log"; exit 1; }
