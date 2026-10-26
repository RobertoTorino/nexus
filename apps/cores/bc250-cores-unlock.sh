#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later

# bc250-cores-unlock.sh - persists the validated BC-250 8C/16T core unlock across reboots.
#
# Run bc250-cores-bisect.sh first and only install this when:
#   - the control (stock 6C/12T) passed, and
#   - the post-control (a stock core after the unlock) passed, and
#   - every new core came back GOOD alone AND in the combined item. The SMU primitive can
#     only enable ALL cores, so a single bad core means: do not install this at all.
#
# The unlock is volatile: it survives warm reboots but a full power off reverts it, and a
# fresh write only takes effect on the NEXT reboot. So "persistent" here means: a root
# systemd service checks the core presence mask early at every boot; after a cold boot it
# re-applies the mask (SMU queue-3 message 0x98 -> 0xFF at SMN 0x5A870) and warm-reboots
# once. A guard prevents reboot loops when the unlock stops taking effect.
#
# It is not a diagnostic: it does not retest anything, it trusts the bisect you already ran.
# It still refuses boards whose stock mask is not 0x77 (see the bisect script).
#
# Usage:
#   sudo ./bc250-cores-unlock.sh --apply        write the mask once, right now (not persisted;
#                                               takes effect on the next warm reboot)
#   sudo ./bc250-cores-unlock.sh --install      copy the script to /usr/local/sbin and enable
#                                               the re-apply service at every boot
#   sudo ./bc250-cores-unlock.sh --uninstall    remove the service and the installed copy;
#                                               stock 6C/12T after the next full power off
#        ./bc250-cores-unlock.sh --status       show the mask, threads, service and guard state
#        ./bc250-cores-unlock.sh --help
#
# https://github.com/RobertoTorino/nexus/tree/main/apps/cores

set -u
if (( BASH_VERSINFO[0] < 4 )); then echo "bash 4 or newer is needed." >&2; exit 1; fi

VERSION="0.3.1"
SELF=$(readlink -f -- "$0")
# --install copies the script here so the boot service never executes a user-owned file as root.
INSTALL_BIN=/usr/local/sbin/bc250-cores-unlock.sh
CONF_DIR=/etc/bc250-cores-bisect
GUARD="$CONF_DIR/reboot-guard"
UNIT_NAME=bc250-cores-unlock.service
UNIT_PATH="/etc/systemd/system/$UNIT_NAME"
GOVERNOR_UNIT="cyan-skillfish-governor-smu.service"

# Hardware constants of the Cyan Skillfish SoC (see the bisect script for details).
NB_BDF="0000:00:00.0"
SMN_INDEX=B8 SMN_DATA=BC
MASK_REG=$(( 0x5A870 ))
Q3_CMD=$(( 0x03B10A20 )) Q3_RSP=$(( 0x03B10A80 )) Q3_ARG=$(( 0x03B10A88 ))
MSG_WRITE_FF=$(( 0x98 ))

say() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
usage() { sed -n '4,/^$/{s/^# \{0,1\}//;p;}' "$0"; }   # the header comment, after the SPDX line and the blank
nthreads() { getconf _NPROCESSORS_ONLN 2>/dev/null || nproc; }

need_root() { (( EUID == 0 )) || die "$1 needs root. Run with sudo."; }
check_board() {
  command -v lspci >/dev/null 2>&1 && command -v setpci >/dev/null 2>&1 || die "lspci/setpci not found. Install pciutils."
  lspci -nn 2>/dev/null | grep -qi '1002:13fe' || die "no BC-250 (1002:13fe) found; refusing to touch the SMU."
}

smn_read() { # addr -> 0xXXXXXXXX
  setpci -s "$NB_BDF" "$SMN_INDEX.L=$(printf '%08x' "$1")" 2>/dev/null || return 1
  local v; v=$(setpci -s "$NB_BDF" "$SMN_DATA.L" 2>/dev/null) || return 1
  [[ $v =~ ^[0-9a-fA-F]{1,8}$ ]] || return 1
  echo "0x$v"
}
smn_write() { # addr value
  setpci -s "$NB_BDF" "$SMN_INDEX.L=$(printf '%08x' "$1")" 2>/dev/null || return 1
  setpci -s "$NB_BDF" "$SMN_DATA.L=$(printf '%08x' "$2")" 2>/dev/null || return 1
}
core_mask() { # double-read until stable: the SMN index/data pair is shared with the governor
  local a b t
  for (( t = 0; t < 5; t++ )); do
    a=$(smn_read "$MASK_REG") || return 1
    b=$(smn_read "$MASK_REG") || return 1
    [[ $a == "$b" ]] && { printf '0x%02x' $(( a & 0xff )); return 0; }
    sleep 0.05
  done
  return 1
}

smu_rsp_done() { case $1 in 0x01|0xff|0xfe|0xfd|0xfc) return 0 ;; esac; return 1; }
smu_send() { # msg arg -> prints final status (0x01 = OK)
  local msg=$1 arg=$2 st t
  for (( t = 0; t < 500; t++ )); do
    st=$(smn_read "$Q3_RSP") || return 1
    smu_rsp_done "$(printf '0x%02x' $(( st & 0xff )))" && break
    sleep 0.01
  done
  smn_write "$Q3_RSP" 0 || return 1
  smn_write "$Q3_ARG" "$arg" || return 1
  smn_write $(( Q3_ARG + 4 )) 0 || return 1
  smn_write "$Q3_CMD" "$msg" || return 1
  for (( t = 0; t < 500; t++ )); do
    st=$(smn_read "$Q3_RSP") || return 1
    st=$(printf '0x%02x' $(( st & 0xff )))
    smu_rsp_done "$st" && { echo "$st"; return 0; }
    sleep 0.01
  done
  return 1
}

apply_mask() { # writes 0xFF; takes effect on the next reboot
  need_root "writing the SMU mailbox"
  check_board
  local mask st was_active=0
  mask=$(core_mask) || die "could not read the core presence mask via $NB_BDF."
  if [[ $mask == 0xff ]]; then say "The mask is already 0xFF."; return 0; fi
  [[ $mask == 0x77 ]] || die "the mask is $mask, not the usual 0x77: the disabled cores were very
       likely fused off for real defects. Refusing to unlock."
  if systemctl is-active --quiet "$GOVERNOR_UNIT" 2>/dev/null; then
    was_active=1
    systemctl stop "$GOVERNOR_UNIT" || die "could not stop $GOVERNOR_UNIT (it shares the SMU mailbox)."
  fi
  st=$(smu_send "$MSG_WRITE_FF" "$MASK_REG"); local rc=$?
  (( was_active )) && systemctl start "$GOVERNOR_UNIT" 2>/dev/null
  (( rc == 0 )) || die "SMU mailbox timed out. Do NOT retry blindly; reboot first."
  [[ $st == 0x01 ]] || die "SMU message 0x98 returned $st (expected 0x01)."
  sleep 0.5
  mask=$(core_mask) || die "could not read the mask back."
  [[ $mask == 0xff ]] || die "the mask did not take (still $mask)."
  say "Core presence mask set to 0xFF. It takes effect on the next (warm) reboot."
}

apply_from_boot() { # the systemd service entry point: re-apply after a cold boot, reboot once
  need_root "--apply-from-boot"
  local mask boot_id
  boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo unknown)
  mask=$(core_mask) || die "could not read the core presence mask."
  if [[ $mask == 0xff ]] && (( $(nthreads) >= 16 )); then
    rm -f "$GUARD"
    say "All 8 cores online, mask 0xFF: nothing to do."
    return 0
  fi
  if [[ -s $GUARD ]]; then
    say "ERROR: a previous boot already re-applied the unlock and rebooted, but the cores are"
    say "still not up (mask $mask, $(nthreads) threads). Not rebooting again to avoid a loop."
    say "Remove $GUARD after fixing the cause to re-arm."
    return 1
  fi
  [[ $mask == 0xff ]] || apply_mask
  echo "$boot_id" >"$GUARD"
  say "Unlock re-applied after a cold boot; warm-rebooting once to bring the cores up..."
  systemctl reboot
}

install_service() {
  need_root "--install"
  check_board
  mkdir -p "$CONF_DIR" && chmod 755 "$CONF_DIR"
  local mask; mask=$(core_mask) || die "could not read the core presence mask."
  [[ $mask == 0x77 || $mask == 0xff ]] || die "the mask is $mask, not 0x77 or 0xFF. Refusing."
  if [[ $SELF != "$INSTALL_BIN" ]]; then
    install -m 755 -o root -g root "$SELF" "$INSTALL_BIN" || die "could not copy the script to $INSTALL_BIN."
    say "Copied the script to $INSTALL_BIN (root-owned; the boot service runs that copy)."
  fi
  cat >"$UNIT_PATH" <<EOF
[Unit]
Description=BC-250 persistent 8-core unlock (bc250-cores-bisect)
After=local-fs.target
Before=$GOVERNOR_UNIT display-manager.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=$INSTALL_BIN --apply-from-boot

[Install]
WantedBy=multi-user.target
EOF
  chmod 644 "$UNIT_PATH"
  systemctl daemon-reload
  systemctl enable "$UNIT_NAME"
  say "Installed and enabled. At every boot the service checks the mask; after a cold boot it"
  say "re-applies the unlock and warm-reboots once (a guard prevents reboot loops)."
  if [[ $mask != 0xff ]]; then
    apply_mask
    say "Reboot (warm) now to bring the cores up."
  fi
  say "Remove with: sudo $0 --uninstall"
}

uninstall_service() {
  need_root "--uninstall"
  systemctl disable "$UNIT_NAME" 2>/dev/null || true
  rm -f "$UNIT_PATH" "$GUARD" "$INSTALL_BIN"
  systemctl daemon-reload
  say "Removed. The unlock is still active until the next full power off (cold boot)."
}

status() {
  # is-enabled/is-active print their answer (not-found, disabled, inactive, ...) and also exit non-zero
  # for most of them, so keep the printed answer and only fall back when there is none.
  local enabled active
  enabled=$(systemctl is-enabled "$UNIT_NAME" 2>/dev/null) || true
  active=$(systemctl is-active "$UNIT_NAME" 2>/dev/null) || true
  [[ -z $enabled || $enabled == not-found ]] && enabled="not installed"
  say "Service: $enabled, ${active:-inactive}"
  say "Threads online: $(nthreads)"
  [[ -s $GUARD ]] && say "Reboot guard: SET ($GUARD) - the service re-applied and rebooted but the cores did not come up."
  if (( EUID == 0 )) || sudo -n true 2>/dev/null; then
    local mask
    if (( EUID == 0 )); then mask=$(core_mask)
    else mask=$(sudo -n bash "$SELF" --read-mask 2>/dev/null); fi
    say "Core presence mask: ${mask:-unreadable} (0x77 = stock 6C, 0xFF = 8C unlocked)"
  else
    say "Core presence mask: run with sudo (or cached sudo credentials) to also show this."
  fi
}

case "${1:-}" in
  --apply)           apply_mask ;;
  --apply-from-boot) apply_from_boot ;;
  --install)         install_service ;;
  --uninstall)       uninstall_service ;;
  --status)          status ;;
  --read-mask)       need_root "--read-mask"; check_board; core_mask ;;
  -V|--version)      echo "bc250-cores-unlock $VERSION" ;;
  -h|--help|"")      usage ;;
  *)                 usage; die "unknown option: $1" ;;
esac
