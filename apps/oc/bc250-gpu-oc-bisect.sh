#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later

# bc250-gpu-oc-bisect.sh - finds your BC-250's safe GPU overclock and undervolt, one step at a time.
#
# The cyan-skillfish-governor-smu scales the BC-250 GPU along a frequency/voltage curve defined by
# the [[safe-points]] in /etc/cyan-skillfish-governor-smu/config.toml. There is no formula for the
# right values: the stable ceiling depends on your specific die, cooling and PSU rail. This script
# finds it empirically, the same way its sibling projects bisect CUs and cores:
#
#   control   the governor's current top safe-point, unchanged. If the control fails, power,
#             heat or the load tool is at fault and no step verdict can be trusted.
#   OC step   top frequency raised one step at a time (default +50 MHz) at a fixed voltage.
#   UV step   top voltage lowered one step at a time (default -25 mV) at the stock top frequency.
#
# For every step the script swaps in a temporary governor config whose top safe-point is the step
# under test, restarts the governor, runs a verified GPU load (memtest_vulkan finds wrong results,
# not only crashes), watches temperature/clock/busy, then restores your own config. Every step runs
# several rounds. Results are crash-safe: after a freeze, cold boot and run the script again - it
# restores your config first, records the crash and resumes.
#
# Verdict per step: "fails every time" = past your die's limit. "Random" = power or heat. Steps
# above/below a consistently failing step are skipped. The final recommendation is the best step
# that passed every round, with the next-best suggested as the margin pick.
#
# Run it as your desktop user; sudo is used for the governor config, systemctl and the kernel log.
#
# Usage: ./bc250-gpu-oc-bisect.sh [options]
#   -t, --time SECS      GPU load per attempt (default 180, minimum 60)
#   -r, --rounds N       attempts per step (default 3, 2-9)
#       --oc             sweep frequency up (default when neither --oc nor --uv is given: both)
#       --uv             sweep voltage down
#       --max-freq MHZ   highest frequency to try (default 2200, hard ceiling 2500)
#       --min-volt MV    lowest voltage to try (default 850, hard floor 700)
#       --oc-volt MV     voltage used for the OC ladder (default: your config's top voltage;
#                        hard ceiling 1100)
#       --freq-step MHZ  OC ladder step (default 50, minimum 25)
#       --volt-step MV   UV ladder step (default 25, minimum 5)
#       --per-boot       one attempt per boot for strict isolation (default: same boot, with a
#                        cooldown between attempts; the governor restart resets its state)
#       --install        write the best validated step into the governor config and exit
#       --uninstall      restore the governor config from the backup made by --install and exit
#       --status         show the results so far and write the report, then exit
#       --reset          delete the results and start over
#   -V, --version        show the version
#   -h, --help           show this help
#
# https://github.com/RobertoTorino/nexus/tree/main/apps/oc

set -u
if (( BASH_VERSINFO[0] < 4 )); then echo "bash 4 or newer is needed." >&2; exit 1; fi

VERSION="0.2.2"
STRESS_SECS="" ROUNDS_OPT="" MODE=run SWEEP="" PER_BOOT=0
MAX_FREQ=2200 MIN_VOLT=850 OC_VOLT_OPT="" FREQ_STEP=50 VOLT_STEP=25

# Hard rails. The community record of hard-locks above ~1850-2000 MHz and the bricked-board report
# from CPU overvolting are the reason these are not options.
HARD_MAX_FREQ=2500 HARD_MAX_VOLT=1100 HARD_MIN_VOLT=700 TEMP_ABORT=97

say()  { printf '%s\n' "$*"; }
hdr()  { printf '\n=== %s ===\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
ask()  { local a; read -rp "$1 " a; printf '%s' "$a"; }
usage() { sed -n '2,/^$/{s/^# \{0,1\}//;p;}' "$0"; }

while (( $# )); do
  case $1 in
    -t|--time)    STRESS_SECS=${2:-}; shift ;;
    -r|--rounds)  ROUNDS_OPT=${2:-}; shift ;;
    --oc)         SWEEP="${SWEEP}oc," ;;
    --uv)         SWEEP="${SWEEP}uv," ;;
    --max-freq)   MAX_FREQ=${2:-}; shift ;;
    --min-volt)   MIN_VOLT=${2:-}; shift ;;
    --oc-volt)    OC_VOLT_OPT=${2:-}; shift ;;
    --freq-step)  FREQ_STEP=${2:-}; shift ;;
    --volt-step)  VOLT_STEP=${2:-}; shift ;;
    --per-boot)   PER_BOOT=1 ;;
    --install)    MODE=install ;;
    --uninstall)  MODE=uninstall ;;
    --status)     MODE=status ;;
    --reset)      MODE=reset ;;
    -V|--version) echo "bc250-gpu-oc-bisect $VERSION"; exit 0 ;;
    -h|--help)    usage; exit 0 ;;
    *)            usage; die "unknown option: $1" ;;
  esac
  shift
done
[[ -z $STRESS_SECS ]] || { [[ $STRESS_SECS =~ ^[0-9]+$ ]] && (( STRESS_SECS >= 60 )); } || die "--time needs a number of seconds (60 or more)."
[[ -z $ROUNDS_OPT || $ROUNDS_OPT =~ ^[2-9]$ ]] || die "--rounds needs a number from 2 to 9."
[[ $MAX_FREQ =~ ^[0-9]+$ ]] && (( MAX_FREQ <= HARD_MAX_FREQ )) || die "--max-freq must be a number up to $HARD_MAX_FREQ MHz."
[[ $MIN_VOLT =~ ^[0-9]+$ ]] && (( MIN_VOLT >= HARD_MIN_VOLT )) || die "--min-volt must be a number of $HARD_MIN_VOLT mV or more."
[[ -z $OC_VOLT_OPT ]] || { [[ $OC_VOLT_OPT =~ ^[0-9]+$ ]] && (( OC_VOLT_OPT <= HARD_MAX_VOLT )); } || die "--oc-volt must be a number up to $HARD_MAX_VOLT mV. Hard ceiling; see the manual."
[[ $FREQ_STEP =~ ^[0-9]+$ ]] && (( FREQ_STEP >= 25 )) || die "--freq-step must be 25 MHz or more."
[[ $VOLT_STEP =~ ^[0-9]+$ ]] && (( VOLT_STEP >= 5 )) || die "--volt-step must be 5 mV or more."
SWEEP_OPT=$SWEEP
[[ -n $SWEEP ]] || SWEEP="oc,uv,"

STATE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/bc250-gpu-oc-bisect"
CONFIG="$STATE_DIR/config"
RUNS="$STATE_DIR/runs.tsv"
PENDING="$STATE_DIR/pending"
ORIG_CONF="$STATE_DIR/governor-config.orig"
TEST_MARKER="$STATE_DIR/test-config-active"
LOGS="$STATE_DIR/logs"
mkdir -p "$LOGS" && chmod 700 "$STATE_DIR" "$LOGS" 2>/dev/null
touch "$RUNS"
BOOT_ID=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo unknown)

GOV_SVC="cyan-skillfish-governor-smu"
GOV_CONF="/etc/cyan-skillfish-governor-smu/config.toml"
INSTALL_BAK="/etc/cyan-skillfish-governor-smu/config.toml.pre-oc-bisect"
FAULT_RE='ring .* timeout|GPU reset|amdgpu.*(fault|hang)|gfxhub|VM_L2|page fault|soft lockup|hard lockup|Oops|BUG:|general protection fault'
FAIL_RE='^(CRASH-LOAD|FAULT|ERRORS|LOAD-FAIL|NO-REACH|GOV-FAIL)$'

# ------------------------------------------------------------------ helpers --
cfg_get() { sed -n "s/^$1=//p" "$CONFIG" 2>/dev/null | head -1; }
cfg_set() {
  local tmp="$CONFIG.tmp"
  { grep -v "^$1=" "$CONFIG" 2>/dev/null; printf '%s=%s\n' "$1" "$2"; } >"$tmp" && mv "$tmp" "$CONFIG"
}

# The governor config without its [[safe-points]] blocks (everything else is kept as-is).
strip_safepoints() {
  awk '
    /^\[\[safe-points\]\]/ { skip = 1; next }
    /^\[/ && !/^\[\[safe-points\]\]/ { skip = 0 }
    !skip { print }
  ' "$1"
}
# "frequency voltage" of the highest-frequency safe-point in a config file.
top_safepoint() {
  awk '
    /^\[\[safe-points\]\]/ { inpt = 1; f = ""; v = ""; next }
    /^\[/ { inpt = 0 }
    inpt && /^[[:space:]]*frequency[[:space:]]*=/ { gsub(/[^0-9]/, "", $0); f = $0 }
    inpt && /^[[:space:]]*voltage[[:space:]]*=/   { gsub(/[^0-9]/, "", $0); v = $0 }
    inpt && f != "" && v != "" { if (f + 0 > bf + 0) { bf = f; bv = v }; f = ""; v = "" }
    END { if (bf != "") print bf, bv }
  ' "$1"
}
# "frequency voltage" of the lowest-frequency safe-point (kept in every test config so the
# governor still has a safe idle point).
low_safepoint() {
  awk '
    /^\[\[safe-points\]\]/ { inpt = 1; f = ""; v = ""; next }
    /^\[/ { inpt = 0 }
    inpt && /^[[:space:]]*frequency[[:space:]]*=/ { gsub(/[^0-9]/, "", $0); f = $0 }
    inpt && /^[[:space:]]*voltage[[:space:]]*=/   { gsub(/[^0-9]/, "", $0); v = $0 }
    inpt && f != "" && v != "" { if (bf == "" || f + 0 < bf + 0) { bf = f; bv = v }; f = ""; v = "" }
    END { if (bf != "") print bf, bv }
  ' "$1"
}

gov_restart() { sudo -n systemctl restart "$GOV_SVC" 2>/dev/null; }
gov_active()  { systemctl is-active --quiet "$GOV_SVC"; }

# Swap in a config whose top safe-point is "freq volt"; keep everything else from the original.
write_test_config() { # freq volt
  local tmp; tmp=$(mktemp) || return 1
  {
    strip_safepoints "$ORIG_CONF"
    printf '\n[[safe-points]]\nfrequency = %s # MHz\nvoltage = %s # mV\n' "$LOW_F" "$LOW_V"
    printf '\n[[safe-points]]\nfrequency = %s # MHz  (bc250-gpu-oc-bisect test point)\nvoltage = %s # mV\n' "$1" "$2"
  } >"$tmp" || { rm -f "$tmp"; return 1; }
  sudo -n cp "$tmp" "$GOV_CONF" && rm -f "$tmp" && touch "$TEST_MARKER"
}
restore_config() {
  [[ -f $TEST_MARKER ]] || return 0
  sudo -n cp "$ORIG_CONF" "$GOV_CONF" && rm -f "$TEST_MARKER" && gov_restart
}

record() { # round item freq volt outcome errors faults maxtemp maxsclk maxbusy note
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(date '+%F %T')" "${BOOT_ID:0:8}" "$@" >>"$RUNS"
  sync "$RUNS" 2>/dev/null
}
attempt_done() { awk -F'\t' -v r="$1" -v i="$2" '$3==r && $4==i && $7!="ABORTED"{f=1} END{exit !f}' "$RUNS"; }
item_verdict() { # item -> none|good|bad|random
  local outs fails=0 tries=0 o
  outs=$(awk -F'\t' -v i="$1" '$4==i && $7!="ABORTED" && $7!="SKIPPED"{print $7}' "$RUNS")
  for o in $outs; do (( tries++ )); [[ $o =~ $FAIL_RE ]] && (( fails++ )); done
  if (( tries == 0 )); then echo none
  elif (( fails == 0 )); then echo good
  elif (( fails == tries && tries >= 2 )); then echo bad
  elif (( fails == tries )); then echo failing
  else echo random
  fi
}
# A ladder step is pruned when an easier step in the same ladder already fails every time.
item_pruned() { # item
  local it=$1 lad=${1%%:*} prev
  for prev in "${ITEMS[@]}"; do
    [[ $prev == "$it" ]] && return 1
    [[ ${prev%%:*} == "$lad" && $lad != control ]] || continue
    [[ $(item_verdict "$prev") == bad ]] && return 0
  done
  return 1
}
next_attempt() { # prints "round item" of the first attempt without a result
  # Ladder order is depth-first: every round of a step runs before the next step is attempted,
  # so the sweep never drives past a step that is still failing.
  local r it
  for it in "${ITEMS[@]}"; do
    for (( r = 1; r <= ROUNDS; r++ )); do
      attempt_done "$r" "$it" && continue
      if item_pruned "$it"; then
        record "$r" "$it" "${ITEM_F[$it]}" "${ITEM_V[$it]}" SKIPPED - - - - - "an easier step already fails every time"
        continue
      fi
      echo "$r $it"; return 0
    done
  done
  return 1
}

# ---------------------------------------------------------------- plan ----
# Items: control (the current top safe-point), then "oc:FREQ" and/or "uv:VOLT" ladder steps.
build_plan() {
  local f v
  ITEMS=(control)
  declare -gA ITEM_F=([control]=$TOP_F) ITEM_V=([control]=$TOP_V)
  if [[ $SWEEP == *oc,* ]]; then
    for (( f = TOP_F + FREQ_STEP; f <= MAX_FREQ; f += FREQ_STEP )); do
      ITEMS+=("oc:$f"); ITEM_F[oc:$f]=$f; ITEM_V[oc:$f]=$OC_VOLT
    done
  fi
  if [[ $SWEEP == *uv,* ]]; then
    for (( v = TOP_V - VOLT_STEP; v >= MIN_VOLT; v -= VOLT_STEP )); do
      ITEMS+=("uv:$v"); ITEM_F[uv:$v]=$TOP_F; ITEM_V[uv:$v]=$v
    done
  fi
}

# ---------------------------------------------------------------- summary --
summary() {
  local it verdict total=0 done_n=0 ctrl_fail=0 best_oc="" best_uv="" oc_margin="" uv_margin="" prev_oc="" prev_uv=""
  hdr "Results  (stock top point: ${TOP_F} MHz @ ${TOP_V} mV, rounds: $ROUNDS, load: ${STRESS_SECS}s)"
  printf '%-10s %-18s %-6s %s\n' "Step" "Point" "Tries" "Verdict and outcomes"
  for it in "${ITEMS[@]}"; do
    local outs fails=0 tries=0 o skipped=0
    outs=$(awk -F'\t' -v i="$it" '$4==i && $7!="ABORTED" && $7!="SKIPPED"{print $7}' "$RUNS")
    awk -F'\t' -v i="$it" '$4==i && $7=="SKIPPED"{f=1} END{exit !f}' "$RUNS" && skipped=1
    for o in $outs; do (( tries++ )); [[ $o =~ $FAIL_RE ]] && (( fails++ )); done
    # Skipped steps are complete by definition; they add nothing to the remaining work.
    (( skipped && tries == 0 )) || (( total += ROUNDS, done_n += tries ))
    if (( tries == 0 )); then verdict=$([[ $skipped == 1 ]] && echo "skipped" || echo "not tested yet")
    elif (( fails == 0 )); then
      verdict="GOOD"
      case $it in
        oc:*) oc_margin=$prev_oc; best_oc=$it; prev_oc=$it ;;
        uv:*) uv_margin=$prev_uv; best_uv=$it; prev_uv=$it ;;
      esac
    elif (( fails == tries && tries >= 2 )); then verdict="FAILS EVERY TIME"
    elif (( fails == tries )); then verdict="failed (only 1 try so far)"
    else verdict="RANDOM ($fails of $tries failed)"
    fi
    [[ $it == control ]] && (( fails )) && ctrl_fail=1
    printf '%-10s %4s MHz @ %4s mV  %d/%-4d %s   %s\n' "$it" "${ITEM_F[$it]}" "${ITEM_V[$it]}" "$tries" "$ROUNDS" "$verdict" "$(echo $outs)"
  done
  say ""
  say "What this means:"
  if (( ctrl_fail )); then
    say "- The CONTROL failed: it changes nothing, it only restarts the governor with your own top"
    say "  point. Power, heat or the load tool is at fault; no step verdict can be trusted."
  fi
  if (( done_n < total )); then
    say "- $done_n of $total attempts done (skipped steps excluded). Run the script again to continue."
  elif (( ! ctrl_fail )); then
    if [[ -n $best_oc ]]; then
      say "- Best overclock that passed every round: ${ITEM_F[$best_oc]} MHz @ ${ITEM_V[$best_oc]} mV."
      [[ -n $oc_margin ]] && say "  With a margin step back: ${ITEM_F[$oc_margin]} MHz (recommended for daily use)."
    elif [[ $SWEEP == *oc,* ]]; then
      say "- No OC step passed every round; your board's stable ceiling is the stock ${TOP_F} MHz."
    fi
    if [[ -n $best_uv ]]; then
      say "- Lowest voltage that passed every round at ${TOP_F} MHz: ${ITEM_V[$best_uv]} mV."
      [[ -n $uv_margin ]] && say "  With a margin step back: ${ITEM_V[$uv_margin]} mV (recommended for daily use)."
    elif [[ $SWEEP == *uv,* ]]; then
      say "- No UV step passed every round; keep the stock ${TOP_V} mV."
    fi
    say "- A step that passed here can still fail under other conditions (heat, a long game)."
    say "  Pick the margin step, then make it permanent:  $0 --install"
    say "  Undo at any time:  sudo cp $INSTALL_BAK $GOV_CONF && sudo systemctl restart $GOV_SVC"
  fi
}

write_report() {
  local d; d=$(xdg-user-dir DESKTOP 2>/dev/null)
  [[ -z $d || ! -d $d ]] && d="$HOME/Desktop"
  [[ -d $d ]] || return 0
  local f
  f="$d/bc250-gpu-oc-bisect-results-$(date '+%Y%m%d-%H%M%S').txt"
  {
    echo "BC-250 GPU OC bisect $VERSION results ($(date '+%F %T'))"
    summary
    echo ""
    echo "All attempts (time, boot, round, step, MHz, mV, outcome, memtest errors, kernel faults,"
    echo "max temp C, max sclk MHz, max GPU busy %, note):"
    cat "$RUNS"
  } >"$f" && say "" && say "Report written to $f"
}

# ---------------------------------------------------------------- modes ----
if [[ $MODE == reset ]]; then
  [[ $(ask "Delete all results in $STATE_DIR and start over? [y/N]") =~ ^[Yy]$ ]] || exit 0
  rm -f "$CONFIG" "$RUNS" "$PENDING" "$ORIG_CONF" "$TEST_MARKER"; rm -rf "$LOGS"
  say "Results deleted."; exit 0
fi

(( EUID != 0 )) || die "run this as your normal desktop user, not as root; it uses sudo where needed."
[[ -r $GOV_CONF ]] || die "$GOV_CONF not found. Install cyan-skillfish-governor-smu first (see the manual)."
lspci -nn 2>/dev/null | grep -qi '1002:13fe' || die "no BC-250 GPU (1002:13fe) found."

say "The governor config and service need root. sudo may ask for your password once."
sudo -n true 2>/dev/null || sudo -v || die "sudo failed."
( while kill -0 $$ 2>/dev/null; do sudo -n true 2>/dev/null; sleep 50; done ) &
KEEPALIVE=$!
trap 'kill "$KEEPALIVE" 2>/dev/null' EXIT

# A crash can leave the test config installed; put the user's own config back before anything else.
if [[ -f $TEST_MARKER && -f $ORIG_CONF ]]; then
  say "A test config from an interrupted attempt is still installed; restoring your own config."
  restore_config || die "could not restore $GOV_CONF from $ORIG_CONF. Do it by hand, then rerun."
fi

if [[ $MODE == install || $MODE == uninstall ]]; then
  if [[ $MODE == uninstall ]]; then
    sudo -n test -f "$INSTALL_BAK" || die "no backup at $INSTALL_BAK; nothing to uninstall."
    sudo -n cp "$INSTALL_BAK" "$GOV_CONF" && gov_restart || die "restore failed."
    say "Restored $GOV_CONF from $INSTALL_BAK and restarted the governor."
    exit 0
  fi
  # install: the best GOOD step, preferring the margin pick (one step back from the edge).
  [[ -s $RUNS && -f $ORIG_CONF ]] || die "no finished results; run the sweep first."
  read -r TOP_F TOP_V < <(top_safepoint "$ORIG_CONF")
  read -r LOW_F LOW_V < <(low_safepoint "$ORIG_CONF")
  OC_VOLT=${OC_VOLT_OPT:-$(cfg_get OC_VOLT)}; OC_VOLT=${OC_VOLT:-$TOP_V}
  ROUNDS=$(cfg_get ROUNDS); ROUNDS=${ROUNDS:-3}; STRESS_SECS=$(cfg_get TIME); STRESS_SECS=${STRESS_SECS:-180}
  SWEEP=$(cfg_get SWEEP); SWEEP=${SWEEP:-oc,uv,}
  build_plan
  next_attempt >/dev/null && die "the sweep is not finished yet; run the script again first."
  BEST_F=$TOP_F BEST_V=$TOP_V PREV_F="" PREV_V=""
  for it in "${ITEMS[@]}"; do
    [[ $it == control ]] && continue
    [[ $(item_verdict "$it") == good ]] || continue
    case $it in
      oc:*) PREV_F=$BEST_F; BEST_F=${ITEM_F[$it]}; BEST_V=${ITEM_V[$it]} ;;
      uv:*) PREV_V=$BEST_V; BEST_V=${ITEM_V[$it]} ;;
    esac
  done
  # Margin: step back once from the last passing step where a previous passing step exists.
  [[ -n $PREV_F ]] && BEST_F=$PREV_F
  [[ -n $PREV_V ]] && BEST_V=$PREV_V
  [[ $BEST_F == "$TOP_F" && $BEST_V == "$TOP_V" ]] && die "nothing better than stock passed; there is nothing to install."
  say "Installing top safe-point ${BEST_F} MHz @ ${BEST_V} mV (margin pick) into $GOV_CONF."
  [[ $(ask "Continue? [y/N]") =~ ^[Yy]$ ]] || exit 0
  sudo -n test -f "$INSTALL_BAK" || sudo -n cp "$GOV_CONF" "$INSTALL_BAK"
  write_test_config "$BEST_F" "$BEST_V" || die "could not write $GOV_CONF."
  rm -f "$TEST_MARKER"   # this one is deliberate, not a test leftover
  gov_restart || die "governor restart failed; restore with: sudo cp $INSTALL_BAK $GOV_CONF"
  say "Done. Backup of your previous config: $INSTALL_BAK   Undo: $0 --uninstall"
  exit 0
fi

# ------------------------------------------------------------ run / status --
# Baseline: snapshot the user's config on the first run; every later run must use the same one.
if [[ ! -f $ORIG_CONF ]]; then
  [[ $MODE == status ]] && die "no results yet."
  cp "$GOV_CONF" "$ORIG_CONF" || die "could not snapshot $GOV_CONF."
  cfg_set CREATED "$(date '+%F %T')"
elif ! cmp -s "$GOV_CONF" "$ORIG_CONF"; then
  die "the governor config changed since this run started. Finish or --reset before editing it."
fi
read -r TOP_F TOP_V < <(top_safepoint "$ORIG_CONF")
read -r LOW_F LOW_V < <(low_safepoint "$ORIG_CONF")
[[ -n ${TOP_F:-} && -n ${TOP_V:-} ]] || die "no [[safe-points]] found in $GOV_CONF."
(( TOP_V <= HARD_MAX_VOLT )) || die "your config's top voltage (${TOP_V} mV) is already above the ${HARD_MAX_VOLT} mV rail; not touching it."

ROUNDS=${ROUNDS_OPT:-$(cfg_get ROUNDS)}; ROUNDS=${ROUNDS:-3}
STRESS_SECS=${STRESS_SECS:-$(cfg_get TIME)}; STRESS_SECS=${STRESS_SECS:-180}
OC_VOLT=${OC_VOLT_OPT:-$(cfg_get OC_VOLT)}; OC_VOLT=${OC_VOLT:-$TOP_V}
SWEEP_SAVED=$(cfg_get SWEEP)
if [[ -n $SWEEP_SAVED ]]; then
  [[ -n $SWEEP_OPT && $SWEEP_OPT != "$SWEEP_SAVED" ]] && die "results exist for sweep '$SWEEP_SAVED'. Run with --reset first to change the sweep."
  SWEEP=$SWEEP_SAVED
fi
[[ $STRESS_SECS =~ ^[0-9]+$ ]] && (( STRESS_SECS >= 60 )) || die "load time must be 60 seconds or more."
[[ $ROUNDS =~ ^[2-9]$ ]] || die "rounds must be a number from 2 to 9."
(( OC_VOLT <= HARD_MAX_VOLT )) || die "OC voltage ${OC_VOLT} mV is above the ${HARD_MAX_VOLT} mV rail."
cfg_set ROUNDS "$ROUNDS"; cfg_set TIME "$STRESS_SECS"; cfg_set OC_VOLT "$OC_VOLT"; cfg_set SWEEP "$SWEEP"
build_plan

if [[ $MODE == status ]]; then summary; write_report; exit 0; fi

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

gov_active || die "$GOV_SVC is not running. Start it first: sudo systemctl enable --now $GOV_SVC"

gpu_busy() { cat "$GPU_DEV/gpu_busy_percent" 2>/dev/null || echo 0; }
gpu_temp() { local f; for f in "$GPU_DEV"/hwmon/hwmon*/temp1_input; do [[ -r $f ]] && { echo $(( $(cat "$f") / 1000 )); return; }; done; echo 0; }
gpu_sclk() {
  local f; for f in "$GPU_DEV"/hwmon/hwmon*/freq1_input; do [[ -r $f ]] && { echo $(( $(cat "$f") / 1000000 )); return; }; done
  sed -n 's/.*: *\([0-9]*\)[Mm][Hh]z *\*.*/\1/p' "$GPU_DEV/pp_dpm_sclk" 2>/dev/null | head -1 || echo 0
}
faults_since() { sudo -n journalctl -k --since "$1" --no-pager 2>/dev/null | grep -E "$FAULT_RE"; }

# -------------------------------------------------- crash from last boot ----
if [[ -s $PENDING ]]; then
  read -r P_ROUND P_ITEM P_F P_V P_BOOT <"$PENDING"
  if [[ $P_BOOT != "$BOOT_ID" ]]; then
    hdr "The last attempt did not finish"
    say "Round $P_ROUND, $P_ITEM (${P_F} MHz @ ${P_V} mV): the system went down during the load."
    PREV=$(sudo -n journalctl -k -b -1 --no-pager 2>/dev/null | grep -E "$FAULT_RE" | tail -5)
    [[ -n $PREV ]] && { say "Kernel faults in the previous boot:"; say "$PREV"; }
    if [[ $(ask "Did the system freeze, crash or reboot by itself? [Y/n]") =~ ^[Nn]$ ]]; then
      record "$P_ROUND" "$P_ITEM" "$P_F" "$P_V" ABORTED - - - - - "rebooted by hand during the attempt"
      say "Recorded as interrupted; this attempt will run again."
    else
      record "$P_ROUND" "$P_ITEM" "$P_F" "$P_V" CRASH-LOAD - "$(grep -c . <<<"$PREV")" - - - "system went down"
      say "Recorded as CRASH-LOAD."
    fi
  else
    record "$P_ROUND" "$P_ITEM" "$P_F" "$P_V" ABORTED - - - - - "script stopped"
  fi
  rm -f "$PENDING"
fi

hdr "BC-250 GPU OC bisect $VERSION"
say "Stock top point: ${TOP_F} MHz @ ${TOP_V} mV   OC ladder voltage: ${OC_VOLT} mV"
say "Steps: ${#ITEMS[@]} (control + ladders)   Rounds: $ROUNDS   Load: $LOAD, ${STRESS_SECS}s"
say "Mode: $([[ $PER_BOOT == 1 ]] && echo 'one attempt per boot' || echo 'same boot, cooldown between attempts')"

if ! NEXT=$(next_attempt); then summary; write_report; exit 0; fi

say ""
say "WARNING: this drives the GPU past its validated point. A too-high step can freeze the"
say "system mid-load. Save your work. After a freeze: cold boot and run the script again -"
say "it restores your own governor config first, records the crash and resumes."
[[ $(ask "Continue? [y/N]") =~ ^[Yy]$ ]] || exit 0

# ---------------------------------------------------------------- attempt --
LOAD_PID=""
on_exit() {
  [[ -n $LOAD_PID ]] && kill "$LOAD_PID" 2>/dev/null
  if [[ -s $PENDING ]]; then
    read -r P_ROUND P_ITEM P_F P_V _ <"$PENDING"
    record "$P_ROUND" "$P_ITEM" "$P_F" "$P_V" ABORTED - - - - - "stopped (Ctrl+C)"
    rm -f "$PENDING"
  fi
  restore_config
  kill "$KEEPALIVE" 2>/dev/null
}
trap on_exit EXIT
trap 'exit 130' INT TERM

set_pending() { printf '%s %s %s %s %s\n' "$1" "$2" "$3" "$4" "$BOOT_ID" >"$PENDING"; sync "$PENDING" 2>/dev/null; }

wait_idle() {
  [[ -n $GPU_DEV ]] || return 0
  local calm=0 t=0
  say "Waiting for the GPU to be idle (close games and video)..."
  while (( calm < 3 )); do
    if (( $(gpu_busy) <= 15 )); then (( calm += 1 )); else calm=0; fi
    sleep 1; (( t++ ))
    (( t == 60 )) && { say "The GPU stayed busy; skipping this attempt."; return 1; }
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
  local r=$1 it=$2 f=${ITEM_F[$2]} v=${ITEM_V[$2]} t0 faults errs=0 rc note="" o
  local maxt=0 maxf=0 maxb=0 log
  log="$LOGS/$(date '+%Y%m%d-%H%M%S')-r$1-${2//:/-}.log"
  hdr "Round $r/$ROUNDS: $it  (${f} MHz @ ${v} mV)"
  wait_idle || { record "$r" "$it" "$f" "$v" ABORTED - - - - - "GPU not idle"; return 1; }
  t0=$(date '+%F %T')
  set_pending "$r" "$it" "$f" "$v"
  say "Installing the test point and restarting the governor..."
  if ! write_test_config "$f" "$v" || ! gov_restart || { sleep 3; ! gov_active; }; then
    record "$r" "$it" "$f" "$v" GOV-FAIL - - - - - "governor did not come up with the test point"
    rm -f "$PENDING"; restore_config; return 0
  fi

  say "Running $LOAD for ${STRESS_SECS}s..."
  case $LOAD in
    memtest_vulkan) timeout -k 10 "$STRESS_SECS" "$LOAD_BIN" 0 "$(memtest_bytes)" </dev/null >"$log" 2>&1 & ;;
    vkpeak)  timeout -k 10 "$STRESS_SECS" bash -c 'while :; do "$0" 0 || exit $?; done' "$LOAD_BIN" </dev/null >"$log" 2>&1 & ;;
    vkmark)  timeout -k 10 "$STRESS_SECS" "$LOAD_BIN" --run-forever -s 2560x1440 -b effect2d:kernel=blur </dev/null >"$log" 2>&1 & ;;
    glmark2) timeout -k 10 "$STRESS_SECS" "$LOAD_BIN" --run-forever -s 2560x1440 </dev/null >"$log" 2>&1 & ;;
  esac
  LOAD_PID=$!
  local start=$SECONDS vv
  while kill -0 "$LOAD_PID" 2>/dev/null; do
    sleep 5
    if [[ -n $GPU_DEV ]]; then
      vv=$(gpu_temp); (( vv > maxt )) && maxt=$vv
      vv=$(gpu_sclk); (( ${vv:-0} > maxf )) && maxf=$vv
      vv=$(gpu_busy); (( vv > maxb )) && maxb=$vv
      if (( maxt >= TEMP_ABORT )); then
        kill "$LOAD_PID" 2>/dev/null; wait "$LOAD_PID" 2>/dev/null; LOAD_PID=""
        record "$r" "$it" "$f" "$v" ABORTED - - "$maxt" "$maxf" "$maxb" "aborted at ${maxt}C - fix cooling first"
        rm -f "$PENDING"; restore_config
        die "GPU reached ${maxt}C; aborting the run. Improve cooling, then continue."
      fi
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
  elif [[ -n $GPU_DEV ]] && (( maxf < f - 75 )); then o=NO-REACH; note="clock only reached ${maxf} MHz of ${f}"
  else o=PASS; fi
  [[ -n $GPU_DEV ]] && (( maxb < 50 )) && note="${note:+$note; }GPU load only reached ${maxb}%"
  record "$r" "$it" "$f" "$v" "$o" "$errs" "$(grep -c . <<<"$faults")" "$maxt" "$maxf" "$maxb" "${note:--}"
  rm -f "$PENDING"
  restore_config
  say "Result: $o${note:+ ($note)}"
}

if (( PER_BOOT )); then
  run_attempt ${NEXT% *} "${NEXT#* }"
  summary
  if NEXT=$(next_attempt); then
    say ""
    say "Next: round ${NEXT% *}, ${NEXT#* }. Reboot, then run the script again (--per-boot)."
  else
    write_report
  fi
else
  while NEXT=$(next_attempt); do
    run_attempt ${NEXT% *} "${NEXT#* }" || break
    say "Cooling down 30 s..."; sleep 30
  done
  summary; next_attempt >/dev/null || write_report
fi
