#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later

# bc250-cu-bisect.sh - finds out whether CU-unlock crashes come from bad WGPs or from the unlock itself.
#
# The script writes the WGP masks itself with umr: the three GPU registers a runtime CU unlock uses
# (CC_GC_SHADER_ARRAY_CONFIG, SPI_PG_ENABLE_STATIC_WGP_MASK, RLC_PG_ALWAYS_ON_WGP_MASK).
#
#   control   the same register writes, but with your baseline masks (no extra CUs). If the
#             control crashes, the unlock method, power or heat is at fault, not your CUs.
#   WGP step  baseline + one locked WGP (2 CUs). Every locked WGP is tested on its own.
#             Skipped entirely with --control-only (e.g. to re-validate a combined mask whose
#             WGPs were already bisected, without re-testing already-known-bad ones).
#
# Every item runs several rounds (interleaved, so heat and time of day don't favor one item).
# By default each attempt gets its own boot, so it starts from the clean driver state. Masks are
# only written while the GPU is idle, they are read back to check they took, and they are read
# again during the load to see if they drift. memtest_vulkan checks for wrong results, not only
# for crashes. After a crash, cold boot and run the script again: it records the crash and resumes.
#
# Verdict per WGP: "fails every time" = likely a bad WGP. "Random" = more likely the unlock
# method, power or heat. A failing control means the WGP verdicts can't blame your CUs.
#
# Run it as your desktop user; sudo is used only for umr and the kernel log.
#
# Usage: ./bc250-cu-bisect.sh [options]
#   -t, --time SECS       GPU load per attempt (default 180, minimum 60)
#   -r, --rounds N        attempts per item (default 3, 1-9; minimum 2 unless --control-only)
#   -b, --baseline MASKS  baseline SPI masks, e.g. 0x07,0x07,0x07,0x07
#                         (default: the live masks of a clean boot = the stock driver state)
#       --control-only    only run the control item, no per-WGP bisecting. For re-validating a
#                         combined mask you already bisected (e.g. after a full run found some
#                         good WGPs and you want to confirm they also hold together), without
#                         re-testing WGPs already known to be bad.
#       --same-boot       don't reboot between attempts; restore the baseline live instead
#                         (faster, but every attempt then inherits the previous one's state)
#       --auto            don't ask anything; auto-reboot after each attempt and keep going on
#                         its own after every login (needs the autostart unit, see the manual) until
#                         every item is done. Still one attempt per boot: no loss of isolation.
#       --no-watch        don't read the registers back during the load
#       --status          show the results so far and write the report, then exit
#       --reset           delete the results and start over
#   -V, --version         show the version
#   -h, --help            show this help
#
# https://github.com/RobertoTorino/nexus/tree/main/bc250-bazzite/apps/compute

set -u
if (( BASH_VERSINFO[0] < 4 )); then echo "bash 4 or newer is needed." >&2; exit 1; fi

VERSION="0.4.0"
STRESS_SECS="" ROUNDS_OPT="" BASE_OPT="" SAME_BOOT=0 AUTO=0 WATCH=1 MODE=run CONTROL_ONLY_OPT=""

say()  { printf '%s\n' "$*"; }
hdr()  { printf '\n=== %s ===\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
ask()  { # prompt [default-used-in---auto-mode]; only the answer goes to stdout (callers capture it)
  local prompt=$1 def=${2:-}
  if (( AUTO )); then say "$prompt -> auto: ${def:-(none)}" >&2; printf '%s' "$def"; return 0; fi
  local a; read -rp "$prompt " a; printf '%s' "$a"
}
do_reboot() { # --no-ask-password: fail instead of raising a GUI auth popup, then fall back to sudo
  systemctl reboot --no-ask-password 2>/dev/null || sudo -n systemctl reboot 2>/dev/null \
    || { say "Could not reboot automatically; reboot WARM by hand (do not power off)."; exit 1; }
}
usage() { sed -n '4,/^$/{s/^# \{0,1\}//;p;}' "$0"; }   # the header comment, after the SPDX line and the blank

# Colors for the CU map; off when stdout isn't a terminal (e.g. the saved report file),
# NO_COLOR is set, or tput is missing. Checked fresh on every call, not just once at startup.
set_colors() {
  if [[ -t 1 ]] && [[ -z ${NO_COLOR:-} ]] && command -v tput >/dev/null 2>&1; then
    C_RESET=$(tput sgr0); C_DIM=$(tput dim); C_BOLD=$(tput bold); C_REV=$(tput rev)
    C_GREEN=$(tput setaf 2); C_RED=$(tput setaf 1); C_YELLOW=$(tput setaf 3)
    C_CYAN=$(tput setaf 6); C_MAGENTA=$(tput setaf 5)
  else
    C_RESET="" C_DIM="" C_BOLD="" C_REV="" C_GREEN="" C_RED="" C_YELLOW="" C_CYAN="" C_MAGENTA=""
  fi
}

while (( $# )); do
  case $1 in
    -t|--time)     STRESS_SECS=${2:-}; shift ;;
    -r|--rounds)   ROUNDS_OPT=${2:-}; shift ;;
    -b|--baseline) BASE_OPT=${2:-}; shift ;;
    --control-only) CONTROL_ONLY_OPT=1 ;;
    --same-boot)   SAME_BOOT=1 ;;
    --auto)        AUTO=1 ;;
    --no-watch)    WATCH=0 ;;
    --status)      MODE=status ;;
    --reset)       MODE=reset ;;
    -V|--version)  echo "bc250-cu-bisect $VERSION"; exit 0 ;;
    -h|--help)     usage; exit 0 ;;
    [0-9]*)        STRESS_SECS=$1 ;;   # old form: ./bc250-cu-bisect.sh 300
    *)             usage; die "unknown option: $1" ;;
  esac
  shift
done
[[ -z $STRESS_SECS ]] || { [[ $STRESS_SECS =~ ^[0-9]+$ ]] && (( STRESS_SECS >= 60 )); } || die "--time needs a number of seconds (60 or more)."
[[ -z $ROUNDS_OPT || $ROUNDS_OPT =~ ^[1-9]$ ]] || die "--rounds needs a number from 1 to 9."
(( CONTROL_ONLY_OPT )) || [[ -z $ROUNDS_OPT ]] || (( ROUNDS_OPT >= 2 )) || die "--rounds needs 2 or more (control-only runs may use 1)."
MASK_RE='^0x[0-9a-fA-F]{1,2}(,0x[0-9a-fA-F]{1,2}){3}$'
[[ -z $BASE_OPT || $BASE_OPT =~ $MASK_RE ]] || die "--baseline needs 4 masks, e.g. 0x07,0x07,0x07,0x07"

STATE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/bc250-cu-bisect"
CONFIG="$STATE_DIR/umr-config"
RUNS="$STATE_DIR/umr-runs.tsv"
PENDING="$STATE_DIR/umr-pending"
LASTBOOT="$STATE_DIR/umr-lastboot"
LOGS="$STATE_DIR/logs"
mkdir -p "$LOGS" && chmod 700 "$STATE_DIR" "$LOGS" 2>/dev/null
touch "$RUNS"
BOOT_ID=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo unknown)

ASIC="${UMR_ASIC:-cyan_skillfish.gfx1013}"
REG_CC="mmCC_GC_SHADER_ARRAY_CONFIG"
REG_SPI="mmSPI_PG_ENABLE_STATIC_WGP_MASK"
REG_RLC="mmRLC_PG_ALWAYS_ON_WGP_MASK"
ROWS=(SE0.SH0 SE0.SH1 SE1.SH0 SE1.SH1)        # row i = SE i/2, SH i%2
GOV_CONF="/etc/cyan-skillfish-governor-smu/config.toml"
FAULT_RE='ring .* timeout|GPU reset|amdgpu.*(fault|hang)|gfxhub|VM_L2|page fault|soft lockup|hard lockup|Oops|BUG:|general protection fault'
# Outcomes that count as a failed attempt. DRIFT and MISMATCH are about the unlock itself.
FAIL_RE='^(CRASH-APPLY|CRASH-LOAD|FAULT|ERRORS|LOAD-FAIL|DRIFT|MISMATCH)$'

# ------------------------------------------------------------------ helpers --
cfg_get() { sed -n "s/^$1=//p" "$CONFIG" 2>/dev/null | head -1; }
cfg_set() {
  local tmp="$CONFIG.tmp"
  { grep -v "^$1=" "$CONFIG" 2>/dev/null; printf '%s=%s\n' "$1" "$2"; } >"$tmp" && mv "$tmp" "$CONFIG"
}
hex2() { printf '0x%02x' $(( $1 & 31 )); }
popcount() { local n=$(( $1 )) c=0; while (( n )); do (( c += n & 1, n >>= 1 )); done; echo "$c"; }
cu_count() { local t=0 m; IFS=, read -ra M <<<"$1"; for m in "${M[@]}"; do (( t += $(popcount "$m") * 2 )); done; echo "$t"; }
norm_masks() { local m out=(); IFS=, read -ra M <<<"$1"; for m in "${M[@]}"; do out+=("$(hex2 "$m")"); done; (IFS=,; echo "${out[*]}"); }

root_safe() { # the file and every folder above it are owned by root and only root can write them
  local p; p=$(readlink -f -- "$1" 2>/dev/null) || return 1
  while :; do
    [[ $(stat -c %u -- "$p" 2>/dev/null) == 0 ]] || return 1
    [[ -z $(find "$p" -maxdepth 0 -perm /022 2>/dev/null) ]] || return 1
    [[ $p == / ]] && return 0
    p=$(dirname -- "$p")
  done
}

# ------------------------------------------------------------------- plan --
# Items: "control" plus one "SEx.SHy.WGPn" per WGP that is locked in the baseline.
build_plan() {
  local i b n
  IFS=, read -ra BASE_M <<<"$BASE"
  ITEMS=(control); declare -gA ITEM_MASKS=([control]="$BASE")
  (( CONTROL_ONLY )) && return
  for i in 0 1 2 3; do
    n=$(( BASE_M[i] ))
    for b in 0 1 2 3 4; do
      (( n >> b & 1 )) && continue
      local m=("${BASE_M[@]}"); m[$i]=$(hex2 $(( n | 1 << b )))
      ITEMS+=("${ROWS[$i]}.WGP$b"); ITEM_MASKS["${ROWS[$i]}.WGP$b"]=$(IFS=,; echo "${m[*]}")
    done
  done
}

# -------------------------------------------------------------- CU map -----
item_verdict() { # item -> none|good|bad|random
  local it=$1 outs fails=0 tries=0 o
  outs=$(awk -F'\t' -v i="$it" '$4==i && $6!="ABORTED" && $6!="SKIPPED"{print $6}' "$RUNS")
  for o in $outs; do
    (( tries++ ))
    [[ $o =~ $FAIL_RE ]] && (( fails++ ))
  done
  if (( tries == 0 )); then echo none
  elif (( fails == 0 )); then echo good
  elif (( fails == tries )); then echo bad
  else echo random
  fi
}
draw_cu_map() { # [current item, e.g. SE0.SH1.WGP3]
  local cur=${1:-} i b row it verdict cell
  set_colors
  hdr "CU map (SE.SH x WGP, 2 CUs per WGP)"
  printf '%-10s' ""
  for b in 0 1 2 3 4; do printf ' %-4s' "WGP$b"; done; echo
  for i in 0 1 2 3; do
    row=${ROWS[$i]}
    printf '%-10s' "$row"
    for b in 0 1 2 3 4; do
      if (( BASE_M[i] >> b & 1 )); then
        cell="${C_GREEN}${C_BOLD} ██ ${C_RESET}"
      else
        it="$row.WGP$b"
        if [[ $cur == "$it" ]]; then
          cell="${C_YELLOW}${C_BOLD}${C_REV} >> ${C_RESET}"
        else
          verdict=$(item_verdict "$it")
          case $verdict in
            good)   cell="${C_CYAN} ok ${C_RESET}" ;;
            bad)    cell="${C_RED} xx ${C_RESET}" ;;
            random) cell="${C_MAGENTA} ?? ${C_RESET}" ;;
            *)      cell="${C_DIM} .. ${C_RESET}" ;;
          esac
        fi
      fi
      printf ' %s' "$cell"
    done
    echo
  done
  say ""
  say "Legend: ${C_GREEN}██${C_RESET} baseline (always unlocked)  ${C_YELLOW}${C_REV}>>${C_RESET} testing now  ${C_CYAN}ok${C_RESET} passed every round  ${C_RED}xx${C_RESET} fails every time  ${C_MAGENTA}??${C_RESET} random  ${C_DIM}..${C_RESET} not tested yet"
  say "$(cu_count "$BASE") of 40 CUs unlocked by default; up to 40 possible if every WGP is healthy."
}
record() { # round item masks outcome errors faults drift maxtemp maxsclk maxbusy note
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(date '+%F %T')" "${BOOT_ID:0:8}" "$@" >>"$RUNS"
  sync "$RUNS" 2>/dev/null
}
attempt_done() { awk -F'\t' -v r="$1" -v i="$2" '$3==r && $4==i && $6!="ABORTED"{f=1} END{exit !f}' "$RUNS"; }
next_attempt() { # prints "round item" of the first attempt without a result
  local r it
  for (( r = 1; r <= ROUNDS; r++ )); do
    for it in "${ITEMS[@]}"; do
      attempt_done "$r" "$it" || { echo "$r $it"; return 0; }
    done
  done
  return 1
}

# ---------------------------------------------------------------- summary --
summary() {
  local it total=0 done_n=0 verdict ctrl_fail=0 consistent=() random=() good=() mech=()
  hdr "Results  (baseline $BASE = $(cu_count "$BASE") CUs, rounds: $ROUNDS, load: ${STRESS_SECS}s)"
  draw_cu_map
  printf '%-15s %-6s %s\n' "Item" "Tries" "Verdict and outcomes"
  for it in "${ITEMS[@]}"; do
    local outs fails=0 tries=0 errs=0 o
    outs=$(awk -F'\t' -v i="$it" '$4==i && $6!="ABORTED" && $6!="SKIPPED"{print $6}' "$RUNS")
    for o in $outs; do
      (( tries++ ))
      [[ $o =~ $FAIL_RE ]] && (( fails++ ))
      [[ $o == ERRORS ]] && (( errs++ ))
      [[ $o =~ ^(CRASH-APPLY|DRIFT|MISMATCH)$ ]] && mech+=("$it: $o")
    done
    (( total += ROUNDS, done_n += tries ))
    if (( tries == 0 )); then verdict="not tested yet"
    elif (( fails == 0 )); then verdict="GOOD"; [[ $it != control ]] && good+=("$it")
    elif (( fails == tries && tries >= 2 )); then
      verdict="FAILS EVERY TIME"; (( errs )) && verdict+=" (memory errors)"
      [[ $it != control ]] && consistent+=("$it")
    elif (( fails == tries )); then verdict="failed (only 1 try so far)"
    else verdict="RANDOM ($fails of $tries failed)"; [[ $it != control ]] && random+=("$it")
    fi
    [[ $it == control ]] && (( fails )) && ctrl_fail=1
    printf '%-15s %d/%-4d %s   %s\n' "$it" "$tries" "$ROUNDS" "$verdict" "$(echo $outs)"
  done
  say ""
  say "What this means:"
  if (( ctrl_fail )); then
    say "- The CONTROL failed: it adds no CUs, it only does the register writes. So the unlock method"
    say "  itself (or power/heat) causes failures. The WGP verdicts can't blame your CUs."
  fi
  if (( ${#mech[@]} )); then
    say "- Signs of the unlock method itself: ${mech[*]}"
    say "  (CRASH-APPLY = down while writing the masks on an idle GPU; DRIFT/MISMATCH = the"
    say "  registers didn't hold the masks.)"
  fi
  if (( ${#consistent[@]} )) && (( ! ctrl_fail )); then
    say "- Fail every time: ${consistent[*]}. These look like bad WGPs; leave them locked."
  fi
  if (( ${#random[@]} )); then
    say "- Fail at random: ${random[*]}. A bad WGP normally fails every time, so this points to"
    say "  the unlock method, power or heat. Cap the governor at 1500 MHz and retest."
  fi
  if (( done_n < total )); then
    say "- $done_n of $total attempts done. Run the script again to continue."
  elif (( ! ctrl_fail )) && (( ${#good[@]} )); then
    local final=("${BASE_M[@]}") g row b i rowcounts=() uneven=0
    for g in "${good[@]}"; do
      row=${g%.WGP*} b=${g##*.WGP}
      for i in 0 1 2 3; do [[ ${ROWS[$i]} == "$row" ]] && final[$i]=$(hex2 $(( final[i] | 1 << b ))); done
    done
    FINAL=$(IFS=,; echo "${final[*]}")
    for i in 0 1 2 3; do rowcounts+=("$(popcount "${final[$i]}")"); done
    for i in 1 2 3; do [[ ${rowcounts[$i]} == "${rowcounts[0]}" ]] || uneven=1; done
    # Only 24/32/40 CUs (3/4/5 WGPs on every row) are installable: the GPU feeds all 4 shader
    # arrays in lockstep, so an uneven mask performs like its smallest row. Trim the suggestion
    # down to the largest even level this board's good WGPs actually support.
    local level=${rowcounts[0]} even=() kept bit
    for i in 1 2 3; do (( rowcounts[i] < level )) && level=${rowcounts[$i]}; done
    (( level > 5 )) && level=5
    for i in 0 1 2 3; do
      kept=0
      for bit in 0 1 2 3 4; do
        (( $(popcount $kept) >= level )) && break
        (( final[i] & (1 << bit) )) && (( kept |= 1 << bit ))
      done
      even+=("$(hex2 $kept)")
    done
    EVEN=$(IFS=,; echo "${even[*]}")
    say "- WGPs that passed every round: ${good[*]}"
    say "  Combined: $FINAL ($(cu_count "$FINAL") CUs, WGPs per row: ${rowcounts[*]})."
    if (( uneven )); then
      say "  That is UNEVEN, and uneven masks cannot be installed: the GPU splits work across all 4"
      say "  rows in lockstep, so it would run exactly as fast as its smallest row ($level WGPs ="
      say "  $(cu_count "$EVEN") CUs) while burning the extra power. Only 3 WGPs per row (24 CUs,"
      say "  stock), 4 per row (32 CUs) and 5 per row (40 CUs, max) are supported."
      say "  Use the even version instead: $EVEN ($(cu_count "$EVEN") CUs)."
    fi
    say "  WGPs that pass one by one can still fail together (more power at the same voltage), so"
    say "  test the combination before saving it to boot:"
    say "  $0 --reset && $0 --baseline $EVEN --control-only --rounds 1"
    say "  Once the combination also passes, make it survive a reboot:"
    say "  sudo ./bc250-cu-unlock.sh --install $EVEN"
  fi
}

write_report() {
  local d; d=$(xdg-user-dir DESKTOP 2>/dev/null)
  [[ -z $d || ! -d $d ]] && d="$HOME/Desktop"
  [[ -d $d ]] || return 0
  local f="$d/bc250-cu-bisect-results-$(date '+%Y%m%d-%H%M%S').txt"
  {
    echo "BC-250 CU bisect $VERSION results ($(date '+%F %T'))"
    summary
    echo ""
    echo "All attempts (time, boot, round, item, masks, outcome, memtest errors, kernel faults,"
    echo "register drift, max temp C, max sclk MHz, max GPU busy %, note):"
    cat "$RUNS"
  } >"$f" && say "" && say "Report written to $f"
}

# ---------------------------------------------------------------- state ----
if [[ $MODE == reset ]]; then
  [[ $(ask "Delete all results in $STATE_DIR (umr-*) and start over? [y/N]" n) =~ ^[Yy]$ ]] || exit 0
  rm -f "$CONFIG" "$RUNS" "$PENDING" "$LASTBOOT"; rm -rf "$LOGS"
  say "Results deleted."; exit 0
fi

BASE=$(cfg_get BASE)
ROUNDS=${ROUNDS_OPT:-$(cfg_get ROUNDS)}; ROUNDS=${ROUNDS:-3}
STRESS_SECS=${STRESS_SECS:-$(cfg_get TIME)}; STRESS_SECS=${STRESS_SECS:-180}
CONTROL_ONLY=${CONTROL_ONLY_OPT:-$(cfg_get CONTROL_ONLY)}; CONTROL_ONLY=${CONTROL_ONLY:-0}
# Hard floors, re-checked even for values that came from a saved config (e.g. written by an older
# version of this script): load must be >=60s, and rounds must be >=2 unless this is a control-only
# run, where a single confirmation round is a legitimate, deliberate re-validation.
[[ $STRESS_SECS =~ ^[0-9]+$ ]] && (( STRESS_SECS >= 60 )) || die "load time must be 60 seconds or more (got ${STRESS_SECS}s)."
[[ $ROUNDS =~ ^[1-9]$ ]] || die "rounds must be a number from 1 to 9 (got $ROUNDS)."
(( CONTROL_ONLY )) || (( ROUNDS >= 2 )) || die "rounds must be 2 or more unless --control-only is set (got $ROUNDS)."
if [[ $MODE == status ]]; then
  [[ -n $BASE ]] || die "no results yet."
  build_plan; summary; write_report; exit 0
fi

# ------------------------------------------------------------ preflight ----
(( EUID != 0 )) || die "run this as your normal desktop user, not as root; it uses sudo only for umr."
lspci -nn 2>/dev/null | grep -qi '1002:13fe' || die "no BC-250 GPU (1002:13fe) found; refusing to write GPU registers."

UMR=""
for p in /usr/bin/umr /usr/sbin/umr /usr/local/bin/umr; do [[ -x $p ]] && { UMR=$p; break; }; done
[[ -n $UMR ]] || die "umr not found. Install it: sudo rpm-ostree install umr, then reboot."
root_safe "$UMR" || die "$UMR is not owned by root (or others can write to it); it would run as root."

GPU_DEV=""
for d in /sys/class/drm/card*/device; do
  [[ $(cat "$d/vendor" 2>/dev/null) == 0x1002 && $(cat "$d/device" 2>/dev/null) == 0x13fe ]] && { GPU_DEV=$d; break; }
done

LOAD="" LOAD_BIN=""
for t in memtest_vulkan vkpeak vkmark glmark2; do
  for p in "$(command -v "$t" 2>/dev/null)" "$HOME/.local/bin/$t" "/home/linuxbrew/.linuxbrew/bin/$t"; do
    [[ -n $p && -x $p && -f $p ]] && { LOAD=$t LOAD_BIN=$p; break 2; }
  done
done
[[ -n $LOAD ]] || die "no GPU load tool found. Put memtest_vulkan (github.com/GpuZelenograd/memtest_vulkan) in ~/.local/bin."

say "Register access needs root (umr). sudo may ask for your password once."
# not `sudo -v`: with the default verifypw=all a mixed sudoers (e.g. wheel + NOPASSWD drop-in)
# makes -v prompt even though commands run passwordless
sudo -n true 2>/dev/null || sudo -v || die "sudo failed."
( while kill -0 $$ 2>/dev/null; do sudo -n true 2>/dev/null; sleep 50; done ) &
KEEPALIVE=$!

UMR_I=()
if [[ -n ${UMR_INSTANCE:-} ]]; then UMR_I=(-i "$UMR_INSTANCE")
else
  BDF=$(lspci -Dn -d 1002:13fe 2>/dev/null | awk 'NR==1{print $1}')
  INST=$(sudo -n sh -c 'grep -l -s -F "$1" /sys/kernel/debug/dri/[0-9]*/name' _ "$BDF" 2>/dev/null | head -1 | awk -F/ '{print $(NF-1)}')
  [[ $INST =~ ^[0-9]+$ ]] && UMR_I=(-i "$INST")
fi

parse_hex() { awk '{for (i = NF; i >= 1; i--) if ($i ~ /^0x[0-9a-fA-F]+$/) {print $i; exit}}'; }
umr_failed() { grep -Eqi '(\[ERROR\]|error|failed|invalid|unknown|cannot|no such)' <<<"$1"; }
reg_read() { # reg [se sh]
  local v
  if (( $# == 3 )); then
    v=$(sudo -n "$UMR" "${UMR_I[@]}" -r "$ASIC.$1" -b "$2" "$3" 0xffffffff 2>&1 | parse_hex)
    [[ -n $v ]] || v=$(sudo -n "$UMR" "${UMR_I[@]}" -r "$ASIC.$1" -b "$2" "$3" 2>&1 | parse_hex)
  else
    v=$(sudo -n "$UMR" "${UMR_I[@]}" -r "$ASIC.$1" 2>&1 | parse_hex)
  fi
  [[ -n $v ]] && echo "$v"
}
reg_write() { # reg value [se sh]
  local out
  if (( $# == 4 )); then out=$(sudo -n "$UMR" "${UMR_I[@]}" -w "$ASIC.$1" "$2" -b "$3" "$4" 0xffffffff 2>&1)
  else out=$(sudo -n "$UMR" "${UMR_I[@]}" -w "$ASIC.$1" "$2" 2>&1); fi
  ! umr_failed "$out"
}
read_spi_all() { local i v out=(); for i in 0 1 2 3; do v=$(reg_read "$REG_SPI" $((i / 2)) $((i % 2))) || return 1; out+=("$(hex2 "$v")"); done; (IFS=,; echo "${out[*]}"); }
read_cc_all()  { local i v out=(); for i in 0 1 2 3; do v=$(reg_read "$REG_CC" $((i / 2)) $((i % 2))) || return 1; out+=("$v"); done; echo "${out[*]}"; }

# Runtime unlock sequence: clear CC, write SPI per row, RLC = union of the rows.
apply_masks() {
  local i union=0 m; IFS=, read -ra m <<<"$1"
  reg_write "$REG_CC" 0x0 || true
  for i in 0 1 2 3; do
    reg_write "$REG_CC" 0x0 $((i / 2)) $((i % 2)) || return 1
    reg_write "$REG_SPI" "$(hex2 "${m[$i]}")" $((i / 2)) $((i % 2)) || return 1
    (( union |= m[i] ))
  done
  reg_write "$REG_RLC" "$(hex2 $union)" || true
}

gpu_busy() { cat "$GPU_DEV/gpu_busy_percent" 2>/dev/null || echo 0; }
gpu_temp() { local f; for f in "$GPU_DEV"/hwmon/hwmon*/temp1_input; do [[ -r $f ]] && { echo $(( $(cat "$f") / 1000 )); return; }; done; echo 0; }
gpu_sclk() {
  local f; for f in "$GPU_DEV"/hwmon/hwmon*/freq1_input; do [[ -r $f ]] && { echo $(( $(cat "$f") / 1000000 )); return; }; done
  sed -n 's/.*: *\([0-9]*\)[Mm][Hh]z *\*.*/\1/p' "$GPU_DEV/pp_dpm_sclk" 2>/dev/null | head -1 || echo 0
}
faults_since() { sudo -n journalctl -k --since "$1" --no-pager 2>/dev/null | grep -E "$FAULT_RE"; }

SPI_NOW=$(read_spi_all) || die "umr could not read $ASIC.$REG_SPI. Set UMR_ASIC or UMR_INSTANCE if your setup differs."
CC_NOW=$(read_cc_all) || CC_NOW=""

# -------------------------------------------------- crash from last boot ----
if [[ -s $PENDING ]]; then
  read -r P_ROUND P_ITEM P_PHASE P_BOOT P_MASKS <"$PENDING"
  if [[ $P_BOOT != "$BOOT_ID" ]]; then
    hdr "The last attempt did not finish"
    say "Round $P_ROUND, $P_ITEM ($P_MASKS): the system went down while $([[ $P_PHASE == load ]] && echo 'the GPU load was running' || echo 'the masks were being written (GPU idle)')."
    PREV=$(sudo -n journalctl -k -b -1 --no-pager 2>/dev/null | grep -E "$FAULT_RE" | tail -5)
    [[ -n $PREV ]] && { say "Kernel faults in the previous boot:"; say "$PREV"; }
    if [[ $(ask "Did the system freeze, crash or reboot by itself? [Y/n]" y) =~ ^[Nn]$ ]]; then
      record "$P_ROUND" "$P_ITEM" "$P_MASKS" ABORTED - - - - - - "rebooted by hand during the attempt"
      say "Recorded as interrupted; this attempt will run again."
    else
      O=CRASH-LOAD; [[ $P_PHASE == apply ]] && O=CRASH-APPLY
      record "$P_ROUND" "$P_ITEM" "$P_MASKS" "$O" - "$(grep -c . <<<"$PREV")" - - - - "system went down"
      say "Recorded as $O."
    fi
  else
    record "$P_ROUND" "$P_ITEM" "$P_MASKS" ABORTED - - - - - - "script stopped"
  fi
  rm -f "$PENDING"
fi

# ----------------------------------------------- --auto needs the autostart unit ----
AUTO_UNIT=bc250-cu-bisect-auto.service
if (( AUTO )); then
  if systemctl --user cat "$AUTO_UNIT" >/dev/null 2>&1; then
    # a finished run disables the unit (auto_cleanup); re-arm it for this run
    if ! systemctl --user is-enabled --quiet "$AUTO_UNIT" 2>/dev/null; then
      systemctl --user enable "$AUTO_UNIT" 2>/dev/null \
        && say "Re-enabled $AUTO_UNIT so this run continues after every reboot." \
        || say "WARNING: could not enable $AUTO_UNIT; the run will stop at the next reboot."
    fi
  else
    say "WARNING: $AUTO_UNIT is not installed: nothing will restart this script after a"
    say "reboot, so --auto cannot continue on its own. See bc250-cu-bisect-auto.service.example."
  fi
fi

# -------------------------------------------------------------- baseline ----
if [[ -z $BASE ]]; then
  BASE=$(norm_masks "${BASE_OPT:-$SPI_NOW}")
  cfg_set BASE "$BASE"; cfg_set BASE_FROM "$([[ -n $BASE_OPT ]] && echo option || echo live)"; cfg_set CREATED "$(date '+%F %T')"
elif [[ -n $BASE_OPT && $(norm_masks "$BASE_OPT") != "$BASE" ]]; then
  die "results exist for baseline $BASE. Run with --reset first to use another baseline."
fi
cfg_set ROUNDS "$ROUNDS"; cfg_set TIME "$STRESS_SECS"; cfg_set CONTROL_ONLY "$CONTROL_ONLY"
build_plan

hdr "BC-250 CU unlock test $VERSION"
say "Baseline: $BASE ($(cu_count "$BASE") CUs)   Live now: $SPI_NOW   CC: ${CC_NOW:-?}"
say "Items: ${ITEMS[*]}$([[ $CONTROL_ONLY == 1 ]] && echo '   (--control-only: per-WGP bisecting skipped)')"
say "Rounds: $ROUNDS   Load: $LOAD, ${STRESS_SECS}s   Mode: $([[ $SAME_BOOT == 1 ]] && echo 'same boot' || echo 'one attempt per boot')"
draw_cu_map

if ! NEXT=$(next_attempt); then summary; write_report; exit 0; fi

# ------------------------------------------------------- safety checks ----
WARNINGS=()
if [[ $SAME_BOOT == 0 ]]; then
  if [[ $(cat "$LASTBOOT" 2>/dev/null) == "$BOOT_ID" ]]; then
    say ""
    say "An attempt already ran in this boot. Power off, wait 10 seconds, power on, and run"
    say "the script again (or use --same-boot). Next: round ${NEXT% *}, ${NEXT#* }."
    (( AUTO )) && { say "Auto-rebooting (--auto)..."; do_reboot; }
    exit 0
  fi
  if [[ -n $CC_NOW ]] && [[ -z $(tr -d '0x ' <<<"$CC_NOW") ]]; then
    die "the unlock is already active in this boot (CC registers are 0): something applied it at boot.
       Disable whatever applies a CU unlock at boot, then reboot and run this again."
  fi
fi
[[ $SPI_NOW != "$BASE" && $SAME_BOOT == 0 && $(cfg_get BASE_FROM) == live ]] && WARNINGS+=("The live masks ($SPI_NOW) differ from the baseline ($BASE).")
GOV_MAX=$(grep -oE "max[_a-z]*\s*=\s*[0-9]+" "$GOV_CONF" 2>/dev/null | grep -oE "[0-9]+" | sort -rn | head -1)
[[ -n $GOV_MAX ]] && (( GOV_MAX > 1500 )) &&
  WARNINGS+=("The governor may run the GPU up to ${GOV_MAX} MHz. For this test cap it at 1500 MHz in $GOV_CONF, so power and heat don't hide the result.")
[[ $LOAD != memtest_vulkan ]] &&
  WARNINGS+=("$LOAD only shows crashes. memtest_vulkan also finds wrong results; put it in ~/.local/bin.")
[[ -z $GPU_DEV ]] && WARNINGS+=("GPU sysfs node not found: no idle check, temperature or clock.")
if (( ${#WARNINGS[@]} )); then
  hdr "Before you start"
  for w in "${WARNINGS[@]}"; do say "- $w"; done
  [[ $(ask "Continue anyway? [y/N]" y) =~ ^[Yy]$ ]] || exit 0
fi
say ""
say "WARNING: this writes GPU registers. A bad WGP or the unlock itself can freeze the system."
say "Save your work. After a freeze: cold boot and run the script again; it records the crash."

# ---------------------------------------------------------------- attempt --
LOAD_PID=""
on_exit() {
  [[ -n $LOAD_PID ]] && kill "$LOAD_PID" 2>/dev/null
  if [[ -s $PENDING ]]; then
    read -r P_ROUND P_ITEM _ _ P_MASKS <"$PENDING"
    record "$P_ROUND" "$P_ITEM" "$P_MASKS" ABORTED - - - - - - "stopped (Ctrl+C)"
    rm -f "$PENDING"
    say ""; say "Stopped. The unlock may still be active: reboot before using the system normally."
  fi
  kill "$KEEPALIVE" 2>/dev/null
}
trap on_exit EXIT
trap 'exit 130' INT TERM

set_pending() { printf '%s %s %s %s %s\n' "$1" "$2" "$3" "$BOOT_ID" "$4" >"$PENDING"; sync "$PENDING" 2>/dev/null; }

wait_idle() {
  [[ -n $GPU_DEV ]] || return 0
  local calm=0 t=0
  say "Waiting for the GPU to be idle (close games and video)..."
  while (( calm < 3 )); do
    if (( $(gpu_busy) <= 15 )); then (( calm += 1 )); else calm=0; fi
    sleep 1; (( t++ ))
    if (( t == 60 )); then
      [[ $(ask "The GPU is still busy ($(gpu_busy)%). Write the masks anyway? [y/N]" n) =~ ^[Yy]$ ]] || return 1
      return 0
    fi
  done
}

memtest_bytes() {
  local avail vram mib
  avail=$(( $(awk '/^MemAvailable:/ {print $2}' /proc/meminfo) / 1024 ))
  vram=$(( $(cat "$GPU_DEV/mem_info_vram_total" 2>/dev/null || echo 0) / 1048576 ))
  mib=$(( vram * 3 / 4 )); (( mib <= 0 || mib > avail / 2 )) && mib=$(( avail / 2 ))
  echo $(( mib * 1048576 ))
}

run_attempt() { # round item
  local r=$1 it=$2 masks=${ITEM_MASKS[$2]} t0 now drift="" faults errs=0 rc note="" o
  local maxt=0 maxf=0 maxb=0 log="$LOGS/$(date '+%Y%m%d-%H%M%S')-r$1-$2.log"
  hdr "Round $r/$ROUNDS: $it  ($masks = $(cu_count "$masks") CUs)"
  draw_cu_map "$it"
  wait_idle || { record "$r" "$it" "$masks" ABORTED - - - - - - "GPU not idle"; return 1; }
  t0=$(date '+%F %T')
  set_pending "$r" "$it" apply "$masks"
  echo "$BOOT_ID" >"$LASTBOOT"; sync "$LASTBOOT" 2>/dev/null
  say "Writing the masks..."
  if ! apply_masks "$masks"; then
    record "$r" "$it" "$masks" MISMATCH - - - - - - "umr refused a write"; rm -f "$PENDING"; return 0
  fi
  now=$(read_spi_all)
  if [[ $now != "$masks" ]]; then
    record "$r" "$it" "$masks" MISMATCH - - - - - - "read back $now"; rm -f "$PENDING"; return 0
  fi
  say "Masks read back OK. Settling 15 s on the idle GPU..."
  sleep 15
  faults=$(faults_since "$t0")
  if [[ -n $faults ]]; then
    say "$faults"
    record "$r" "$it" "$masks" FAULT - "$(grep -c . <<<"$faults")" - - - - "kernel fault right after writing (idle GPU)"
    rm -f "$PENDING"; return 0
  fi
  now=$(read_spi_all); [[ $now != "$masks" ]] && drift="idle: $now"

  set_pending "$r" "$it" load "$masks"
  say "Running $LOAD for ${STRESS_SECS}s..."
  case $LOAD in
    memtest_vulkan) timeout -k 10 "$STRESS_SECS" "$LOAD_BIN" 0 "$(memtest_bytes)" </dev/null >"$log" 2>&1 & ;;
    vkpeak)  timeout -k 10 "$STRESS_SECS" bash -c 'while :; do "$0" 0 || exit $?; done' "$LOAD_BIN" </dev/null >"$log" 2>&1 & ;;
    vkmark)  timeout -k 10 "$STRESS_SECS" "$LOAD_BIN" --run-forever -s 2560x1440 -b effect2d:kernel=blur </dev/null >"$log" 2>&1 & ;;
    glmark2) timeout -k 10 "$STRESS_SECS" "$LOAD_BIN" --run-forever -s 2560x1440 </dev/null >"$log" 2>&1 & ;;
  esac
  LOAD_PID=$!
  local start=$SECONDS tick=0 v
  while kill -0 "$LOAD_PID" 2>/dev/null; do
    sleep 5; (( tick++ ))
    if [[ -n $GPU_DEV ]]; then
      v=$(gpu_temp); (( v > maxt )) && maxt=$v
      v=$(gpu_sclk); (( ${v:-0} > maxf )) && maxf=$v
      v=$(gpu_busy); (( v > maxb )) && maxb=$v
    fi
    if (( WATCH && tick % 2 == 0 )) && [[ -z $drift ]]; then
      now=$(read_spi_all) && [[ $now != "$masks" ]] && { drift="t+$(( SECONDS - start ))s: $now"; say "Masks changed under load: $now"; }
    fi
    printf '\r  %3ds  %s C  %s MHz  busy %s%%   ' "$(( SECONDS - start ))" "$maxt" "$maxf" "$maxb"
  done
  wait "$LOAD_PID"; rc=$?; LOAD_PID=""; echo
  faults=$(faults_since "$t0")
  [[ $LOAD == memtest_vulkan ]] && errs=$(grep -c 'Error found' "$log" 2>/dev/null); errs=${errs:-0}
  [[ -n $faults ]] && say "$faults"

  if [[ -n $faults ]]; then o=FAULT
  elif (( errs > 0 )); then o=ERRORS; note="memtest_vulkan error reports: $errs"
  elif (( rc != 124 && rc != 0 )); then o="LOAD-FAIL"; note="$LOAD exit $rc: $(tail -1 "$log" | tr '\t' ' ' | cut -c1-80)"
  elif [[ -n $drift ]]; then o=DRIFT
  else o=PASS; fi
  [[ -n $GPU_DEV ]] && (( maxb < 50 )) && note="${note:+$note; }GPU load only reached ${maxb}%"
  record "$r" "$it" "$masks" "$o" "$errs" "$(grep -c . <<<"$faults")" "${drift:--}" "$maxt" "$maxf" "$maxb" "${note:--}"
  rm -f "$PENDING"
  say "Result: $o${note:+ ($note)}"
}

revert() {
  say "Restoring the baseline masks live..."
  apply_masks "$BASE" && [[ $(read_spi_all) == "$BASE" ]] && return 0
  say "The baseline did not read back. Stopping: reboot, then run the script again."
  return 1
}

auto_cleanup() { # the run is finished: stop the --auto loop from coming back at the next login
  (( AUTO )) || return 0
  rm -f "$HOME/.config/autostart/bc250-cu-bisect-watch.desktop"
  # disable WITHOUT --now: this script may be running inside that very unit
  if systemctl --user disable "$AUTO_UNIT" 2>/dev/null; then
    say "All attempts are done: disabled $AUTO_UNIT and removed the"
    say "live-output autostart entry. Nothing will start at the next login."
    say "(A new --auto run re-enables the unit by itself.)"
  fi
}

if [[ $SAME_BOOT == 1 ]]; then
  while NEXT=$(next_attempt); do
    run_attempt ${NEXT% *} "${NEXT#* }" || break
    revert || break
    say "Cooling down 30 s..."; sleep 30
  done
  summary; next_attempt >/dev/null || { write_report; auto_cleanup; }
else
  run_attempt ${NEXT% *} "${NEXT#* }"
  summary
  if NEXT=$(next_attempt); then
    say ""
    say "Next: round ${NEXT% *}, ${NEXT#* }. Each attempt needs a fresh boot."
    if (( AUTO )); then
      say "Auto-rebooting to continue (--auto)..."; do_reboot
    else
      case $(ask "[p]ower off (best: cold boot), [r]eboot, or [n]othing? [p/r/N]") in
        [Pp]) systemctl poweroff ;;
        [Rr]) systemctl reboot ;;
        *) say "Reboot before you use the system normally: the unlock is still active." ;;
      esac
    fi
  else
    write_report
    auto_cleanup
    say "Reboot to return to the stock state."
  fi
fi
