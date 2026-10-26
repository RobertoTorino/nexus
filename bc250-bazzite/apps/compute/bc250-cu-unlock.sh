#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later

# bc250-cu-unlock.sh - persists a validated BC-250 CU unlock across reboots.
#
# Run bc250-cu-bisect.sh first and only use masks that:
#   - passed with the control (no crashes with just the baseline masks), and
#   - came back GOOD for every WGP in the combined mask, on its own, and
#   - were then tested together as the combined mask itself (WGPs that pass alone can still fail
#     combined - more power at the same voltage; see the CU Bisect manual), and
#   - unlock the same number of WGPs on all 4 shader arrays (SE0.SH0, SE0.SH1, SE1.SH0, SE1.SH1):
#     the GPU splits work across all 4 in lockstep, so an uneven unlock only ever runs as fast as
#     its smallest row while still drawing the extra power - this script refuses to install one.
#
# Because of that lockstep, this script only accepts the three even levels and refuses anything else:
#   3 WGPs per row = 24 CUs (stock/default)   4 per row = 32 CUs   5 per row = 40 CUs (max)
#
# This repeats the exact register writes bc250-cu-bisect.sh uses (umr: CC_GC_SHADER_ARRAY_CONFIG,
# SPI_PG_ENABLE_STATIC_WGP_MASK, RLC_PG_ALWAYS_ON_WGP_MASK), every boot, as a root systemd service, as
# early as the unit ordering below allows - before the display manager starts using the GPU. It is not
# a diagnostic: it does not retest anything, it trusts the masks you give it.
#
# Usage:
#   sudo ./bc250-cu-unlock.sh 0x0f,0x0f,0x0f,0x0f        apply the masks once, right now (not persisted)
#   sudo ./bc250-cu-unlock.sh --install 0x0f,0x0f,0x0f,0x0f   save + apply now + enable at every boot
#   sudo ./bc250-cu-unlock.sh --uninstall                 disable the service; stock 24 CUs from next boot
#        ./bc250-cu-unlock.sh --status                    show the installed masks, service and live state
#        ./bc250-cu-unlock.sh --help
#
# https://github.com/RobertoTorino/nexus/tree/main/bc250-bazzite/apps/compute

set -u
if (( BASH_VERSINFO[0] < 4 )); then echo "bash 4 or newer is needed." >&2; exit 1; fi

VERSION="0.3.1"
SELF=$(readlink -f -- "$0")
CONF_DIR=/etc/bc250-cu-bisect
CONF_FILE="$CONF_DIR/masks"
INSTALL_PATH=/usr/local/sbin/bc250-cu-unlock.sh
UNIT_NAME=bc250-cu-unlock.service
UNIT_PATH="/etc/systemd/system/$UNIT_NAME"
ASIC="${UMR_ASIC:-cyan_skillfish.gfx1013}"
REG_CC="mmCC_GC_SHADER_ARRAY_CONFIG"
REG_SPI="mmSPI_PG_ENABLE_STATIC_WGP_MASK"
REG_RLC="mmRLC_PG_ALWAYS_ON_WGP_MASK"
ROWS=(SE0.SH0 SE0.SH1 SE1.SH0 SE1.SH1)
MASK_RE='^0x[0-9a-fA-F]{1,2}(,0x[0-9a-fA-F]{1,2}){3}$'

say()  { printf '%s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
usage() { sed -n '4,/^$/{s/^# \{0,1\}//;p;}' "$0"; }   # the header comment, after the SPDX line and the blank
hex2() { printf '0x%02x' $(( $1 & 31 )); }
popcount() { local n=$(( $1 )) c=0; while (( n )); do (( c += n & 1, n >>= 1 )); done; echo "$c"; }
cu_count() { local t=0 m; IFS=, read -ra M <<<"$1"; for m in "${M[@]}"; do (( t += $(popcount "$m") * 2 )); done; echo "$t"; }

# Only 24 (3 WGPs/row, stock), 32 (4/row) and 40 (5/row, max) are real configurations. The GPU
# front-end feeds all 4 shader arrays in lockstep, so an uneven mask performs like its *smallest*
# row while still drawing the extra power - it's never worth installing. Refuse it outright.
validate_even() { # masks
  local m i counts=() n
  IFS=, read -ra m <<<"$1"
  for i in 0 1 2 3; do counts+=("$(popcount $(( ${m[$i]} & 31 )) )"); done
  n=${counts[0]}
  for i in 1 2 3; do
    [[ ${counts[$i]} == "$n" ]] && continue
    die "uneven mask $1 - ${counts[0]}/${counts[1]}/${counts[2]}/${counts[3]} WGPs on SE0.SH0/SE0.SH1/SE1.SH0/SE1.SH1.
  The GPU drives all 4 shader arrays in lockstep, so an uneven unlock runs no faster than its
  smallest row while burning the extra power. Unlock the SAME number of WGPs on every row.
  Allowed: 3 per row = 24 CUs (stock), 4 per row = 32 CUs, 5 per row = 40 CUs (max).
  Example 32 CUs: 0x0f,0x0f,0x0f,0x0f     Example 40 CUs: 0x1f,0x1f,0x1f,0x1f"
  done
  case $n in
    3|4|5) return 0 ;;
    *) die "unsupported mask $1 ($(cu_count "$1") CUs, $n WGPs per row).
  Allowed: 3 per row = 24 CUs (stock), 4 per row = 32 CUs, 5 per row = 40 CUs (max)." ;;
  esac
}

root_safe() { # the file and every folder above it are owned by root and only root can write them
  local p; p=$(readlink -f -- "$1" 2>/dev/null) || return 1
  while :; do
    [[ $(stat -c %u -- "$p" 2>/dev/null) == 0 ]] || return 1
    [[ -z $(find "$p" -maxdepth 0 -perm /022 2>/dev/null) ]] || return 1
    [[ $p == / ]] && return 0
    p=$(dirname -- "$p")
  done
}
find_umr() {
  local p; for p in /usr/bin/umr /usr/sbin/umr /usr/local/bin/umr; do [[ -x $p ]] && { echo "$p"; return 0; }; done
  return 1
}
parse_hex() { awk '{for (i = NF; i >= 1; i--) if ($i ~ /^0x[0-9a-fA-F]+$/) {print $i; exit}}'; }
umr_failed() { grep -Eqi '(\[ERROR\]|error|failed|invalid|unknown|cannot|no such)' <<<"$1"; }

# ----------------------------------------------------------------- apply ---
apply_masks() { # masks (must run as root)
  (( EUID == 0 )) || die "writing GPU registers needs root. Run with sudo."
  [[ $1 =~ $MASK_RE ]] || die "masks must look like 0x0f,0x0f,0x0f,0x0f (same number of WGPs on every row)"
  validate_even "$1"
  lspci -nn 2>/dev/null | grep -qi '1002:13fe' || die "no BC-250 GPU (1002:13fe) found; refusing to write GPU registers."
  local UMR; UMR=$(find_umr) || die "umr not found. Install it: rpm-ostree install umr, then reboot."
  root_safe "$UMR" || die "$UMR is not owned by root (or others can write to it)."

  local UMR_I=() BDF INST
  if [[ -n ${UMR_INSTANCE:-} ]]; then UMR_I=(-i "$UMR_INSTANCE")
  else
    BDF=$(lspci -Dn -d 1002:13fe 2>/dev/null | awk 'NR==1{print $1}')
    INST=$(grep -l -s -F "$BDF" /sys/kernel/debug/dri/[0-9]*/name 2>/dev/null | head -1 | awk -F/ '{print $(NF-1)}')
    [[ $INST =~ ^[0-9]+$ ]] && UMR_I=(-i "$INST")
  fi
  reg_write_rc() { # reg value se sh
    local out; out=$("$UMR" "${UMR_I[@]}" -w "$ASIC.$1" "$2" -b "$3" "$4" 0xffffffff 2>&1); ! umr_failed "$out"
  }
  reg_write_global() { # reg value, no se/sh
    local out; out=$("$UMR" "${UMR_I[@]}" -w "$ASIC.$1" "$2" 2>&1); ! umr_failed "$out"
  }
  reg_read_rc() { # reg se sh
    local v; v=$("$UMR" "${UMR_I[@]}" -r "$ASIC.$1" -b "$2" "$3" 0xffffffff 2>&1 | parse_hex)
    [[ -n $v ]] || v=$("$UMR" "${UMR_I[@]}" -r "$ASIC.$1" -b "$2" "$3" 2>&1 | parse_hex)
    [[ -n $v ]] && echo "$v"
  }

  local m i union=0
  IFS=, read -ra m <<<"$1"
  reg_write_global "$REG_CC" 0x0 || true
  for i in 0 1 2 3; do
    reg_write_rc "$REG_CC" 0x0 $((i / 2)) $((i % 2)) || die "could not clear $REG_CC on ${ROWS[$i]}"
    reg_write_rc "$REG_SPI" "$(hex2 "${m[$i]}")" $((i / 2)) $((i % 2)) || die "could not write $REG_SPI on ${ROWS[$i]}"
    (( union |= m[i] ))
  done
  reg_write_global "$REG_RLC" "$(hex2 $union)" || true

  local now ok=1
  for i in 0 1 2 3; do
    now=$(reg_read_rc "$REG_SPI" $((i / 2)) $((i % 2))) || { ok=0; continue; }
    [[ $(hex2 "$now") == $(hex2 "${m[$i]}") ]] || ok=0
  done
  (( ok )) || die "masks did not read back as written; the unlock may be partially applied. Reboot."
  say "CU unlock applied: $1 ($(cu_count "$1") CUs)"
}

# --------------------------------------------------------- install/remove --
install_service() { # masks
  (( EUID == 0 )) || die "--install needs root: sudo $0 --install $1"
  [[ $1 =~ $MASK_RE ]] || die "masks must look like 0x0f,0x0f,0x0f,0x0f (same number of WGPs on every row)"
  validate_even "$1"
  mkdir -p "$CONF_DIR" && chmod 755 "$CONF_DIR"
  printf '%s\n' "$1" >"$CONF_FILE" && chmod 644 "$CONF_FILE"
  # Copy the script itself under /usr/local, never reference $SELF directly: a unit that execs a
  # path under /home or /var/home fails at boot with a bare "Permission denied" (SELinux denies
  # executing user_home_t from a system service), and the checkout it was run from might move or
  # vanish anyway.
  install -m 0755 -o root -g root "$SELF" "$INSTALL_PATH" || die "could not install $INSTALL_PATH."
  cat >"$UNIT_PATH" <<EOF
[Unit]
Description=BC-250 persistent CU unlock (bc250-cu-bisect)
After=local-fs.target sys-kernel-debug.mount
Before=display-manager.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=$INSTALL_PATH --apply-from-config

[Install]
WantedBy=multi-user.target
EOF
  chmod 644 "$UNIT_PATH"
  systemctl daemon-reload || die "systemctl daemon-reload failed; the service was not enabled. Check: systemctl status $UNIT_NAME, journalctl -u $UNIT_NAME, and that /etc/systemd/system is writable."
  apply_masks "$1"
  systemctl enable "$UNIT_NAME" || die "systemctl enable $UNIT_NAME failed (see the error above); the unlock will NOT survive a reboot even though it's applied right now. Common causes: SELinux, or /etc/systemd/system not writable on this image. Check: systemctl status $UNIT_NAME, journalctl -u $UNIT_NAME."
  systemctl is-enabled --quiet "$UNIT_NAME" || die "systemctl enable reported success but $UNIT_NAME is still not enabled; the unlock will NOT survive a reboot. Check: systemctl status $UNIT_NAME, journalctl -u $UNIT_NAME."
  say "Installed and enabled. $1 is applied now and on every future boot."
  say "Remove with: sudo $0 --uninstall"
}

uninstall_service() {
  (( EUID == 0 )) || die "--uninstall needs root: sudo $0 --uninstall"
  systemctl disable "$UNIT_NAME" 2>/dev/null || true
  rm -f "$UNIT_PATH" "$CONF_FILE" "$INSTALL_PATH"
  systemctl daemon-reload
  say "Removed. The unlock is still active in this boot; reboot to go back to the stock 24 CUs."
}

status() {
  say "Config file: $CONF_FILE"
  if [[ -r $CONF_FILE ]]; then
    local masks; masks=$(<"$CONF_FILE")
    say "  Configured masks: $masks ($(cu_count "$masks") CUs) - saved on disk; NOT proof it's active now, see 'Live masks now' below."
  else
    say "  Not installed."
  fi
  if [[ -r $UNIT_PATH ]] && [[ ! -x $INSTALL_PATH ]]; then
    say "  WARNING: $UNIT_PATH references $INSTALL_PATH but it's missing - the service will fail at"
    say "    next boot. Reinstall with: sudo $0 --install \$(cat $CONF_FILE 2>/dev/null)."
  fi
  if command -v systemctl >/dev/null 2>&1; then
    local enabled active
    enabled=$(systemctl is-enabled "$UNIT_NAME" 2>/dev/null); [[ -n $enabled ]] || enabled="not installed"
    active=$(systemctl is-active "$UNIT_NAME" 2>/dev/null); [[ -n $active ]] || active="inactive"
    say "Service: $enabled, $active"
  fi
  local UMR; UMR=$(find_umr) || return 0
  local UMR_I=() BDF INST i v out=() AS_ROOT=()
  if (( EUID == 0 )); then
    AS_ROOT=()
  elif sudo -n true 2>/dev/null; then
    AS_ROOT=(sudo -n)
  else
    say "Live masks: run with sudo (or cached sudo credentials) to also show these - this is the only"
    say "  number that's 100% certain; other tools (config file above, driver-cached CU counts in"
    say "  third-party apps) can be stale or just reflect what was requested, not what's live now."
    return 0
  fi
  BDF=$("${AS_ROOT[@]}" lspci -Dn -d 1002:13fe 2>/dev/null | awk 'NR==1{print $1}')
  INST=$("${AS_ROOT[@]}" sh -c 'grep -l -s -F "$1" /sys/kernel/debug/dri/[0-9]*/name' _ "$BDF" 2>/dev/null | head -1 | awk -F/ '{print $(NF-1)}')
  [[ $INST =~ ^[0-9]+$ ]] && UMR_I=(-i "$INST")
  for i in 0 1 2 3; do
    v=$("${AS_ROOT[@]}" "$UMR" "${UMR_I[@]}" -r "$ASIC.$REG_SPI" -b $((i / 2)) $((i % 2)) 0xffffffff 2>&1 | parse_hex)
    [[ -n $v ]] || v=$("${AS_ROOT[@]}" "$UMR" "${UMR_I[@]}" -r "$ASIC.$REG_SPI" -b $((i / 2)) $((i % 2)) 2>&1 | parse_hex)
    out+=("$(hex2 "${v:-0}")")
  done
  v=$(IFS=,; echo "${out[*]}")
  say "Live masks now: $v ($(cu_count "$v") CUs) - read straight from the GPU registers; this is the"
  say "  authoritative, ground-truth number for this boot."
}

# ------------------------------------------------------------------- CLI ---
case "${1:-}" in
  --install)       shift; [[ -n ${1:-} ]] || die "usage: $0 --install 0x0f,0x0f,0x0f,0x0f"; install_service "$1" ;;
  --uninstall)     uninstall_service ;;
  --apply-from-config)
                   [[ -r $CONF_FILE ]] || die "$CONF_FILE not found; install first with --install."
                   apply_masks "$(<"$CONF_FILE")" ;;
  --status)        status ;;
  -V|--version)     echo "bc250-cu-unlock $VERSION" ;;
  -h|--help|"")     usage ;;
  0x*)              apply_masks "$1" ;;
  *)                usage; die "unknown option: $1" ;;
esac
