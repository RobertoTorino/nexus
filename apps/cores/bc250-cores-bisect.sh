#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later

# bc250-cores-bisect.sh - finds out whether the BC-250's 2 fused-off CPU cores are healthy
# before you trust (or persist) the 8C/16T core unlock.
#
# The SMU primitive that enables the cores (queue-3 message 0x98) can only write 0xFF to the
# core presence mask: all 8 cores or none. So unlike a GPU CU bisect we cannot unlock one core
# at a time. Instead the script isolates the cores under test AFTER the unlock:
#
#   control       before the unlock, on the stock 6C/12T: a verified CPU load on all stock
#                 cores. If the control fails, the board, power, heat or the load tool is at
#                 fault, and the new-core verdicts can't blame your cores.
#   post-control  after the unlock: the same pinned load on a stock core. Separates "the
#                 unlock destabilises the whole SoC" from "a new core is bad".
#   coreN         each newly appeared core on its own: the load pinned to only its 2 threads.
#   combined      both new cores together (more power at the same voltage).
#
# Every item runs several rounds (interleaved). By default each attempt gets its own boot;
# warm reboots preserve the unlock, so that costs nothing. Failures are detected three ways:
# machine-check events in the kernel log (attributed to the tested CPUs when possible),
# stress-ng --verify computation errors (wrong results, not only crashes), and full crashes
# (recorded crash-safe on the next run, like a fsck journal).
#
# For a longer, harsher burn-in there are two optional extras, both off by default:
#   --load mprime|both  also (or instead) run mprime's self-checking torture test. Small in-place
#                       FFTs are the heaviest AVX/FMA load this SoC will ever see and mprime checks
#                       every result, so it catches silent miscalculation that stress-ng misses.
#   --rasdaemon         count hardware errors through rasdaemon's ras-mc-ctl as well as the kernel
#                       log. rasdaemon keeps a persistent database, so errors are still counted when
#                       the journal is volatile or the attempt ends in a crash.
#
# Verdict per core: "fails every time" = likely a genuinely bad core. "Random" = more likely
# power, heat or the unlock itself. Because the primitive is all-or-nothing, ONE bad core
# means: do not use the unlock at all - cold boot to revert, and don't install persistence.
#
# The script refuses boards whose presence mask isn't the usual 0x77: a different mask
# suggests a real harvest of defective silicon.
#
# Known side effect of the unlock: pp_dpm_sclk / hwmon freq1_input report nonsense GPU
# clocks afterwards. That is cosmetic and expected; this script ignores GPU clocks.
#
# Run it as your desktop user; sudo is used only for setpci and the kernel log.
#
# Usage: ./bc250-cores-bisect.sh [options]
#   -t, --time SECS       CPU load per attempt (default 600, minimum 60)
#   -r, --rounds N        attempts per item (default 3, 1-9)
#       --load TOOL       load tool: stress-ng (default), mprime, or both
#       --mprime-bin PATH mprime binary (default: $PATH, then ~/mprime/mprime)
#       --rasdaemon       also count hardware errors with ras-mc-ctl (needs rasdaemon)
#       --same-boot       don't reboot between bisect attempts (faster, less isolation)
#       --auto            no prompts; auto-reboot after each attempt and continue after every
#                         login (needs the autostart unit, see the manual) until all items are done
#       --status          show the results so far and write the report, then exit
#       --reset           delete the results and start over
#   -V, --version         show the version
#   -h, --help            show this help
#
# https://github.com/RobertoTorino/nexus/tree/main/apps/cores

set -u
if (( BASH_VERSINFO[0] < 4 )); then echo "bash 4 or newer is needed." >&2; exit 1; fi

VERSION="0.2.1"
STRESS_SECS="" ROUNDS_OPT="" SAME_BOOT=0 AUTO=0 MODE=run
LOAD_TOOL_OPT="" MPRIME_BIN_OPT="" RAS_OPT=""
LOAD_TOOL=stress-ng MPRIME_BIN="" STRESS_BIN="" RAS=0 MPRIME_DIR=""

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
usage() { sed -n '2,/^$/{s/^# \{0,1\}//;p;}' "$0"; }

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
    -t|--time)    STRESS_SECS=${2:-}; shift ;;
    -r|--rounds)  ROUNDS_OPT=${2:-}; shift ;;
    --load)       LOAD_TOOL_OPT=${2:-}; shift ;;
    --mprime-bin) MPRIME_BIN_OPT=${2:-}; shift ;;
    --rasdaemon)  RAS_OPT=1 ;;
    --same-boot)  SAME_BOOT=1 ;;
    --auto)       AUTO=1 ;;
    --status)     MODE=status ;;
    --reset)      MODE=reset ;;
    -V|--version) echo "bc250-cores-bisect $VERSION"; exit 0 ;;
    -h|--help)    usage; exit 0 ;;
    *)            usage; die "unknown option: $1" ;;
  esac
  shift
done
[[ -z $STRESS_SECS ]] || { [[ $STRESS_SECS =~ ^[0-9]+$ ]] && (( STRESS_SECS >= 60 )); } || die "--time needs a number of seconds (60 or more)."
[[ -z $ROUNDS_OPT || $ROUNDS_OPT =~ ^[1-9]$ ]] || die "--rounds needs a number from 1 to 9."
[[ -z $LOAD_TOOL_OPT || $LOAD_TOOL_OPT =~ ^(stress-ng|mprime|both)$ ]] || die "--load needs stress-ng, mprime or both."
[[ -z $MPRIME_BIN_OPT || -x $MPRIME_BIN_OPT ]] || die "--mprime-bin: $MPRIME_BIN_OPT is not an executable file."

STATE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/bc250-cores-bisect"
CONFIG="$STATE_DIR/config"
RUNS="$STATE_DIR/runs.tsv"
PENDING="$STATE_DIR/pending"
LASTBOOT="$STATE_DIR/lastboot"
LOGS="$STATE_DIR/logs"
mkdir -p "$LOGS" && chmod 700 "$STATE_DIR" "$LOGS" 2>/dev/null
touch "$RUNS"
BOOT_ID=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo unknown)

# SMU / SMN plumbing (hardware constants of the Cyan Skillfish SoC):
# the SMN index/data pair lives at 0xB8/0xBC in the PCI config space of the root complex
# 0000:00:00.0. The core presence mask is SMN 0x5A870 (reads 0x77 stock, 0xFF unlocked;
# host writes are silently dropped). SMU queue 3 (CMD 0x03B10A20, RSP 0x03B10A80,
# ARG 0x03B10A88) message 0x98 makes the SMU itself store 0xFF at any SMN address.
NB_BDF="0000:00:00.0"
SMN_INDEX=B8 SMN_DATA=BC
MASK_REG=$(( 0x5A870 ))
Q3_CMD=$(( 0x03B10A20 )) Q3_RSP=$(( 0x03B10A80 )) Q3_ARG=$(( 0x03B10A88 ))
MSG_WRITE_FF=$(( 0x98 ))
GOVERNOR_UNIT="cyan-skillfish-governor-smu.service"
MCE_RE='mce: |mce_|Machine [Cc]heck|Hardware Error|MC[0-9]+ Error'
# mprime reports a miscalculation without necessarily exiting non-zero, so its log is scanned too
MPRIME_FAIL_RE='FATAL ERROR|TORTURE TEST FAILED|Hardware failure detected|ILLEGAL SUMOUT|Rounding was [0-9.]+, expected|Torture Test completed.*[1-9][0-9]* error'
FAIL_RE='^(CRASH-LOAD|MCE|VERIFY-FAIL|LOAD-FAIL|OFFLINE|MPRIME-FAIL|RAS-ERROR)$'

# ------------------------------------------------------------------ helpers --
cfg_get() { sed -n "s/^$1=//p" "$CONFIG" 2>/dev/null | head -1; }
cfg_set() {
  local tmp="$CONFIG.tmp"
  { grep -v "^$1=" "$CONFIG" 2>/dev/null; printf '%s=%s\n' "$1" "$2"; } >"$tmp" && mv "$tmp" "$CONFIG"
}

smn_read() { # addr -> 0xXXXXXXXX (SMN index/data; best-effort, racy only against other SMN users)
  sudo -n setpci -s "$NB_BDF" "$SMN_INDEX.L=$(printf '%08x' "$1")" 2>/dev/null || return 1
  local v; v=$(sudo -n setpci -s "$NB_BDF" "$SMN_DATA.L" 2>/dev/null) || return 1
  [[ $v =~ ^[0-9a-fA-F]{1,8}$ ]] || return 1
  echo "0x$v"
}
smn_write() { # addr value
  sudo -n setpci -s "$NB_BDF" "$SMN_INDEX.L=$(printf '%08x' "$1")" 2>/dev/null || return 1
  sudo -n setpci -s "$NB_BDF" "$SMN_DATA.L=$(printf '%08x' "$2")" 2>/dev/null || return 1
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
  return 1  # mailbox timeout: do not retry blindly
}

apply_unlock() { # one SMU write of 0xFF to the presence mask; takes effect on the next reboot
  local was_active=0 st mask
  if systemctl is-active --quiet "$GOVERNOR_UNIT" 2>/dev/null; then
    was_active=1
    say "Stopping $GOVERNOR_UNIT (it shares the SMU mailbox)..."
    sudo -n systemctl stop "$GOVERNOR_UNIT" || { say "Could not stop the governor."; return 1; }
  fi
  st=$(smu_send "$MSG_WRITE_FF" "$MASK_REG"); local rc=$?
  (( was_active )) && sudo -n systemctl start "$GOVERNOR_UNIT" 2>/dev/null
  (( rc == 0 )) || { say "SMU mailbox timed out. Do NOT retry blindly; reboot first."; return 1; }
  [[ $st == 0x01 ]] || { say "SMU message 0x98 returned $st (expected 0x01)."; return 1; }
  sleep 0.5
  mask=$(core_mask) || { say "Could not read the mask back."; return 1; }
  [[ $mask == 0xff ]] || { say "The mask did not take (still $mask)."; return 1; }
  return 0
}

# ------------------------------------------------------------- CPU topology --
# core_cpus CORE_ID -> comma list of the online logical CPUs of that physical core
core_cpus() {
  local c list=()
  for c in /sys/devices/system/cpu/cpu[0-9]*; do
    [[ $(cat "$c/topology/core_id" 2>/dev/null) == "$1" ]] && list+=("${c##*cpu}")
  done
  (IFS=,; echo "${list[*]}")
}
online_core_ids() { # sorted unique core_ids of the online CPUs
  cat /sys/devices/system/cpu/cpu[0-9]*/topology/core_id 2>/dev/null | sort -n | uniq | tr '\n' ' ' | sed 's/ $//'
}
nthreads() { getconf _NPROCESSORS_ONLN 2>/dev/null || nproc; }

cpu_temp() { # Tctl from k10temp, degrees C
  local h
  for h in /sys/class/hwmon/hwmon*; do
    [[ $(cat "$h/name" 2>/dev/null) == k10temp ]] && { echo $(( $(cat "$h/temp1_input" 2>/dev/null || echo 0) / 1000 )); return; }
  done
  echo 0
}
cpu_freq() { # current frequency of the first tested CPU, MHz ("3,11" and "0-15" both -> cpu3/cpu0)
  local c=${1%%[,-]*} v f="/sys/devices/system/cpu/cpu${1%%[,-]*}/cpufreq/scaling_cur_freq"
  if [[ -r $f ]]; then echo $(( $(cat "$f") / 1000 )); return; fi
  # the BC-250 exposes no cpufreq scaling driver; fall back to /proc/cpuinfo
  v=$(awk -v c="$c" '$1=="processor" && $3==c {hit=1} hit && $1=="cpu" && $2=="MHz" {printf "%d", $4; exit}' /proc/cpuinfo)
  echo "${v:-0}"
}
mces_since() { sudo -n journalctl -k --since "$1" --no-pager 2>/dev/null | grep -E "$MCE_RE"; }

# ------------------------------------------------------- rasdaemon (--rasdaemon) --
# rasdaemon logs every hardware error the kernel reports (MCE, extlog, ...) into its own sqlite
# database. Counting rows before and after an attempt survives a volatile journal and a crash,
# which the journalctl scrape above does not.
ras_error_lines() { # every recorded error, one per line (empty when rasdaemon has nothing)
  (( RAS )) || return 0
  sudo -n ras-mc-ctl --errors 2>/dev/null \
    | grep -vaE '^[[:space:]]*$|^No .* errors.$|^(Memory|MCE|Extlog|ARM|DEP|aer|devlink|Vendor|Non-standard|PCIe AER) errors:?$'
}
ras_error_count() { ras_error_lines | grep -c . ; }

# ----------------------------------------------------------- mprime (--load) --
# mprime's torture test is driven entirely by prime.txt/local.txt, so each item gets a private
# working directory and runs fully unattended. Small in-place FFTs give the hottest AVX/FMA load
# and mprime verifies every result, which is what makes it useful here on top of stress-ng.
mprime_workdir() { # item nthreads -> a prepared, private working directory
  local d="$STATE_DIR/mprime/$1"
  mkdir -p "$d" || return 1
  printf '%s\n' "StressTester=1" "UsePrimenet=0" "V24OptionsConverted=1" "WGUID_version=2" >"$d/prime.txt"
  printf '%s\n' "TortureThreads=$2" "TortureMem=0" "TortureTime=3" \
                "MinTortureFFT=4" "MaxTortureFFT=32" "TortureWeak=0" >"$d/local.txt"
  : >"$d/results.txt"
  echo "$d"
}
mprime_start() { # item cpus nthreads secs log -> starts mprime in the background, sets LOAD_PID
  local item=$1 cpus=$2 n=$3 secs=$4 log=$5
  MPRIME_DIR=$(mprime_workdir "$item" "$n") || return 1
  # -t torture test, -d debug output to stdout. mprime's torture test never ends on its own, so
  # timeout stops it; SIGINT (not TERM) lets it flush results.txt on the way out.
  ( cd "$MPRIME_DIR" && exec taskset -c "$cpus" timeout -s INT "${secs}s" "$MPRIME_BIN" -t -d ) \
    </dev/null >"$log" 2>&1 &
  LOAD_PID=$!
}
mprime_failed() { # log exit-code -> 0 when mprime reported an error (or died early)
  local log=$1 rc=$2
  cat "$MPRIME_DIR/results.txt" >>"$log" 2>/dev/null
  # 124 = timeout fired, i.e. mprime ran the full time without dying: the normal exit here
  (( rc == 0 || rc == 124 )) || return 0
  grep -qaE "$MPRIME_FAIL_RE" "$log"
}

# ------------------------------------------------------------------- plan ---
# Phase control: item "control" only (stock cores, before the unlock).
# Phase bisect:  "post-control" + one "coreN" per new core + "combined".
build_plan() {
  local c
  ITEMS=(); declare -gA ITEM_CPUS=()
  if [[ $PHASE == control ]]; then
    ITEMS=(control); ITEM_CPUS[control]="0-$(( $(nthreads) - 1 ))"
    return
  fi
  read -ra BASE_IDS <<<"$BASE_CORES"
  read -ra NEW_IDS <<<"$NEW_CORES"
  ITEMS=(post-control); ITEM_CPUS[post-control]=$(core_cpus "${BASE_IDS[0]}")
  local all=()
  for c in "${NEW_IDS[@]}"; do
    ITEMS+=("core$c"); ITEM_CPUS["core$c"]=$(core_cpus "$c")
    all+=("${ITEM_CPUS[core$c]}")
  done
  if (( ${#NEW_IDS[@]} > 1 )); then
    ITEMS+=(combined); ITEM_CPUS[combined]=$(IFS=,; echo "${all[*]}")
  fi
}

# --------------------------------------------------------------- core map ---
item_verdict() { # item -> none|good|bad|random
  local outs fails=0 tries=0 o
  outs=$(awk -F'\t' -v i="$1" '$4==i && $6!="ABORTED"{print $6}' "$RUNS")
  for o in $outs; do (( tries++ )); [[ $o =~ $FAIL_RE ]] && (( fails++ )); done
  if (( tries == 0 )); then echo none
  elif (( fails == 0 )); then echo good
  elif (( fails == tries )); then echo bad
  else echo random; fi
}
draw_core_map() { # [current item]
  local cur=${1:-} c cell verdict
  set_colors
  hdr "Core map (physical cores; 2 threads each)"
  read -ra BASE_IDS <<<"${BASE_CORES:-}"
  read -ra NEW_IDS <<<"${NEW_CORES:-}"
  if (( ! ${#NEW_IDS[@]} )); then # before the unlock: the fused-off cores are the IDs missing from 0-7
    for c in 0 1 2 3 4 5 6 7; do [[ " ${BASE_IDS[*]} " == *" $c "* ]] || NEW_IDS+=("$c"); done
  fi
  printf '%-8s' ""
  for c in "${BASE_IDS[@]}" "${NEW_IDS[@]}"; do printf ' %-6s' "core$c"; done; echo
  printf '%-8s' ""
  for c in "${BASE_IDS[@]}"; do printf ' %s' "${C_GREEN}${C_BOLD}  ██  ${C_RESET}"; done
  for c in "${NEW_IDS[@]}"; do
    if [[ $cur == "core$c" ]]; then cell="${C_YELLOW}${C_BOLD}${C_REV}  >>  ${C_RESET}"
    else
      verdict=$(item_verdict "core$c")
      case $verdict in
        good)   cell="${C_CYAN}  ok  ${C_RESET}" ;;
        bad)    cell="${C_RED}  xx  ${C_RESET}" ;;
        random) cell="${C_MAGENTA}  ??  ${C_RESET}" ;;
        *)      cell="${C_DIM}  ..  ${C_RESET}" ;;
      esac
    fi
    printf ' %s' "$cell"
  done
  echo; say ""
  say "Legend: ${C_GREEN}██${C_RESET} stock core  ${C_YELLOW}${C_REV}>>${C_RESET} testing now  ${C_CYAN}ok${C_RESET} passed every round  ${C_RED}xx${C_RESET} fails every time  ${C_MAGENTA}??${C_RESET} random  ${C_DIM}..${C_RESET} not tested yet"
}

record() { # round item cpus outcome mces verify_errs maxtemp maxfreq note load_secs [tool] [ras_errs]
  # load_secs and everything after it are appended at the end, so result files written by older
  # versions (11 or 12 columns) stay readable; missing trailing columns are filled with "-"
  local fields=("$(date '+%F %T')" "${BOOT_ID:0:8}" "$@")
  while (( ${#fields[@]} < 14 )); do fields+=("-"); done
  local IFS=$'\t'
  printf '%s\n' "${fields[*]}" >>"$RUNS"
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

# ---------------------------------------------------------------- summary ---
item_loads() { # item -> "120s stress-ng x2, 1800s both x3" (unknown = written by an older version)
  awk -F'\t' -v i="$1" '$4==i && $6!="ABORTED" {
      l = ($12 == "" || $12 == "-") ? "unknown" : $12 "s"
      if ($13 != "" && $13 != "-" && $13 != "stress-ng") l = l " " $13
      if (!(l in c)) o[++n] = l; c[l]++ }
    END { for (k = 1; k <= n; k++) printf "%s%s x%d", (k > 1 ? ", " : ""), o[k], c[o[k]] }' "$RUNS"
}
item_ras_errors() { # item -> total hardware errors rasdaemon attributed to its attempts
  awk -F'\t' -v i="$1" '$4==i && $6!="ABORTED" && $14 ~ /^[0-9]+$/ {s += $14} END {print s + 0}' "$RUNS"
}

summary() {
  local it total=0 done_n=0 verdict ctrl_fail=0 postctrl_fail=0 consistent=() random=() good=()
  local shown=("${ITEMS[@]}") ctrl_tries=0 mixed=() loads want
  # after the unlock the control is history, but its verdict still frames everything else
  [[ $PHASE != control ]] && shown=(control "${ITEMS[@]}")
  hdr "Results  (phase: $PHASE, rounds: $ROUNDS, load: $(load_desc) per attempt)"
  [[ -n ${BASE_CORES:-} ]] && draw_core_map
  printf '%-14s %-6s %s\n' "Item" "Tries" "Verdict and outcomes"
  for it in "${shown[@]}"; do
    local outs fails=0 tries=0 mces=0 o mprime_fails=0 ras_errs=0
    outs=$(awk -F'\t' -v i="$it" '$4==i && $6!="ABORTED"{print $6}' "$RUNS")
    for o in $outs; do
      (( tries++ ))
      [[ $o =~ $FAIL_RE ]] && (( fails++ ))
      [[ $o == MCE ]] && (( mces++ ))
      [[ $o == MPRIME-FAIL ]] && (( mprime_fails++ ))
    done
    want=$ROUNDS
    if [[ $it == control && $PHASE != control ]]; then
      want=$tries; ctrl_tries=$tries   # finished phase: not counted in the remaining attempts
    else
      (( total += ROUNDS, done_n += tries ))
    fi
    if (( tries == 0 )); then verdict="not tested yet"
    elif (( fails == 0 )); then verdict="GOOD"; [[ $it == core* || $it == combined ]] && good+=("$it")
    elif (( fails == tries && tries >= 2 )); then
      verdict="FAILS EVERY TIME"; (( mces )) && verdict+=" (machine-check events)"
      (( ! mces && mprime_fails )) && verdict+=" (mprime miscalculations)"
      [[ $it == core* || $it == combined ]] && consistent+=("$it")
    elif (( fails == tries )); then verdict="failed (only 1 try so far)"
    else verdict="RANDOM ($fails of $tries failed)"; [[ $it == core* || $it == combined ]] && random+=("$it")
    fi
    [[ $it == control ]] && (( fails )) && ctrl_fail=1
    [[ $it == post-control ]] && (( fails )) && postctrl_fail=1
    printf '%-14s %d/%-4d %s   %s\n' "$it" "$tries" "$want" "$verdict" "$(echo $outs)"
    loads=$(item_loads "$it")
    if [[ -n $loads && $loads != "${STRESS_SECS}s x$tries" && $loads != "unknown x$tries" ]]; then
      printf '%-14s %-6s load per attempt: %s\n' "" "" "$loads"
    fi
    ras_errs=$(item_ras_errors "$it")
    (( ras_errs )) && printf '%-14s %-6s rasdaemon hardware errors: %s\n' "" "" "$ras_errs"
    # only a recorded, different load proves a settings change ("unknown" = older version)
    awk -F'\t' -v i="$it" -v s="$STRESS_SECS" -v t="$LOAD_TOOL" \
      '$4==i && $6!="ABORTED" && (($12 ~ /^[0-9]+$/ && $12 != s) || ($13 != "" && $13 != "-" && $13 != t)) {f=1}
       END{exit !f}' "$RUNS" && mixed+=("$it")
  done
  say ""
  say "What this means:"
  if (( ${#mixed[@]} )); then
    say "- Not every attempt ran the current load ($(load_desc)): ${mixed[*]}"
    say "  (see 'load per attempt'). The settings changed during the run. Shorter or lighter"
    say "  attempts still count, but they are weaker evidence; use --reset for a uniform result."
  fi
  if (( ctrl_tries && ctrl_tries < ROUNDS )); then
    say "- The control ran $ctrl_tries round(s), fewer than the current $ROUNDS: it finished before"
    say "  the rounds were raised. It still passed, but with less evidence than the other items."
  fi
  if (( ctrl_fail )); then
    say "- The CONTROL failed on the stock 6 cores, before any unlock. The board, power, heat or"
    say "  the load tool is at fault. Fix that first; nothing can be concluded about the new cores."
  fi
  if (( postctrl_fail )); then
    say "- POST-CONTROL failed: a stock core fails after the unlock. The unlock destabilises the"
    say "  whole SoC on this board (or power/heat changed). Cold boot to revert; don't persist."
  fi
  if (( ${#consistent[@]} )) && (( ! ctrl_fail && ! postctrl_fail )); then
    say "- Fail every time: ${consistent[*]}. This looks like genuinely bad silicon. The SMU"
    say "  primitive can only enable ALL cores, so a single bad core means: do not use this"
    say "  unlock at all. Cold boot (full power off) to revert, and don't install persistence."
  fi
  if (( ${#random[@]} )); then
    say "- Fail at random: ${random[*]}. A bad core normally fails every time, so this points to"
    say "  power or heat. Improve cooling, close background load, and retest."
  fi
  if awk -F'\t' '$6=="MPRIME-FAIL"{f=1} END{exit !f}' "$RUNS"; then
    say "- MPRIME-FAIL means mprime computed a wrong result without the kernel noticing anything."
    say "  That is silent data corruption: treat it exactly like a machine-check event."
  fi
  if awk -F'\t' '$6=="RAS-ERROR"{f=1} END{exit !f}' "$RUNS"; then
    say "- RAS-ERROR means rasdaemon recorded a hardware error the load itself survived. Check the"
    say "  details with 'ras-mc-ctl --errors'; corrected errors still indicate marginal silicon."
  fi
  if (( done_n < total )); then
    say "- $done_n of $total attempts done. Run the script again to continue."
  elif [[ $PHASE == bisect ]] && (( ! ctrl_fail && ! postctrl_fail && ! ${#consistent[@]} && ! ${#random[@]} )); then
    say "- Every new core passed every round, alone and combined. The unlock looks safe on this"
    say "  board. Make it survive reboots (reapplied + one warm reboot after each cold boot):"
    say "  sudo ./bc250-cores-unlock.sh --install"
  fi
}

write_report() { # report + every raw file of the run in ~/Desktop/bc250-cores-bisect/ for easy sharing
  local d; d=$(xdg-user-dir DESKTOP 2>/dev/null)
  [[ -z $d || ! -d $d ]] && d="$HOME/Desktop"
  [[ -d $d ]] || return 0
  d="$d/bc250-cores-bisect"
  mkdir -p "$d/logs" || return 0
  local f; f="$d/bc250-cores-bisect-results-$(date '+%Y%m%d-%H%M%S').txt"
  {
    echo "BC-250 cores bisect $VERSION results ($(date '+%F %T'))"
    summary
    echo ""
    echo "All attempts (time, boot, round, item, cpus, outcome, MCE lines, verify errors,"
    echo "max temp C, max freq MHz, note, load secs, load tool, rasdaemon errors):"
    cat "$RUNS"
  } >"$f" || return 0
  # the raw data behind the report: load output per attempt, results table, settings, --auto log
  cp -p "$LOGS"/*.log "$d/logs/" 2>/dev/null
  cp -p "$RUNS" "$CONFIG" "$d/" 2>/dev/null
  [[ -s $STATE_DIR/auto.log ]] && cp -p "$STATE_DIR/auto.log" "$d/"
  # the file is written as the user (sudo only reads the rasdaemon database), so no tee is needed
  # shellcheck disable=SC2024
  (( RAS )) && sudo -n ras-mc-ctl --errors >"$d/ras-mc-ctl-errors.txt" 2>/dev/null
  say ""; say "Report and all logs copied to $d/"; say "  $(basename "$f")"
  return 0
}

# ------------------------------------------------------------------ state ---
if [[ $MODE == reset ]]; then
  [[ $(ask "Delete all results in $STATE_DIR and start over? [y/N]" n) =~ ^[Yy]$ ]] || exit 0
  rm -f "$CONFIG" "$RUNS" "$PENDING" "$LASTBOOT"; rm -rf "$LOGS" "$STATE_DIR/mprime"
  say "Results deleted."; exit 0
fi

PHASE=$(cfg_get PHASE); PHASE=${PHASE:-control}
BASE_CORES=$(cfg_get BASE_CORES)
NEW_CORES=$(cfg_get NEW_CORES)
OLD_ROUNDS=$(cfg_get ROUNDS) OLD_TIME=$(cfg_get TIME)
OLD_LOAD_TOOL=$(cfg_get LOAD_TOOL)
ROUNDS=${ROUNDS_OPT:-$OLD_ROUNDS}; ROUNDS=${ROUNDS:-3}
STRESS_SECS=${STRESS_SECS:-$OLD_TIME}; STRESS_SECS=${STRESS_SECS:-600}
LOAD_TOOL=${LOAD_TOOL_OPT:-$OLD_LOAD_TOOL}; LOAD_TOOL=${LOAD_TOOL:-stress-ng}
# --rasdaemon is remembered like the other settings, so a resumed/--auto run keeps counting
RAS=${RAS_OPT:-$(cfg_get RAS)}; RAS=${RAS:-0}
MPRIME_BIN=$MPRIME_BIN_OPT
[[ -n $MPRIME_BIN ]] || MPRIME_BIN=$(cfg_get MPRIME_BIN)
load_desc() { # one line describing the load, used in the banner, the summary and the report
  case $LOAD_TOOL in
    mprime)    echo "mprime torture, ${STRESS_SECS}s" ;;
    both)      echo "stress-ng --verify + mprime torture, ${STRESS_SECS}s each" ;;
    *)         echo "stress-ng --verify, ${STRESS_SECS}s" ;;
  esac
}

if [[ $MODE == status ]]; then
  [[ -s $CONFIG ]] || die "no results yet."
  build_plan; summary; write_report; exit 0
fi

# -------------------------------------------------------------- preflight ---
(( EUID != 0 )) || die "run this as your normal desktop user, not as root; it uses sudo only for setpci and the kernel log."
command -v lspci >/dev/null 2>&1 && command -v setpci >/dev/null 2>&1 || die "lspci/setpci not found. Install pciutils."
lspci -nn 2>/dev/null | grep -qi '1002:13fe' || die "no BC-250 (1002:13fe) found; refusing to touch the SMU."
if [[ $LOAD_TOOL == stress-ng || $LOAD_TOOL == both ]]; then
  STRESS_BIN=$(command -v stress-ng 2>/dev/null) || die "stress-ng not found. Install it, or use --load mprime."
fi
if [[ $LOAD_TOOL == mprime || $LOAD_TOOL == both ]]; then
  if [[ -z $MPRIME_BIN || ! -x $MPRIME_BIN ]]; then
    MPRIME_BIN=$(command -v mprime 2>/dev/null) \
      || { for p in "$HOME/mprime/mprime" "$HOME/.local/bin/mprime" /opt/mprime/mprime /usr/local/bin/mprime; do
             [[ -x $p ]] && { MPRIME_BIN=$p; break; }
           done; }
  fi
  [[ -n $MPRIME_BIN && -x $MPRIME_BIN ]] || die "mprime not found. Install it (or pass --mprime-bin PATH); see the manual. Prime95/mprime is a separate download from mersenne.org."
  command -v timeout >/dev/null 2>&1 || die "timeout not found (coreutils); it is what stops mprime after --time seconds."
  cfg_set MPRIME_BIN "$MPRIME_BIN"
fi
if (( RAS )); then
  command -v ras-mc-ctl >/dev/null 2>&1 || die "--rasdaemon: ras-mc-ctl not found. Install rasdaemon (Fedora/Bazzite: rpm-ostree install rasdaemon)."
  if ! systemctl is-active --quiet rasdaemon 2>/dev/null; then
    say "WARNING: --rasdaemon: the rasdaemon service is not active, so nothing is being recorded."
    say "         Start it first: sudo systemctl enable --now rasdaemon"
  fi
  sudo -n ras-mc-ctl --errors >/dev/null 2>&1 || RAS_NEEDS_PROBE=1
fi
command -v taskset >/dev/null 2>&1 || die "taskset not found. Install util-linux."

say "SMN access needs root (setpci). sudo may ask for your password once."
# not `sudo -v`: with the default verifypw=all a mixed sudoers (e.g. wheel + NOPASSWD drop-in)
# makes -v prompt even though commands run passwordless
sudo -n true 2>/dev/null || sudo -v || die "sudo failed."
( while kill -0 $$ 2>/dev/null; do sudo -n true 2>/dev/null; sleep 50; done ) &
KEEPALIVE=$!
# re-probe now that sudo credentials are cached: ras-mc-ctl always needs root
if (( RAS )) && [[ -n ${RAS_NEEDS_PROBE:-} ]] && ! sudo -n ras-mc-ctl --errors >/dev/null 2>&1; then
  say "WARNING: --rasdaemon: 'sudo -n ras-mc-ctl --errors' failed; hardware errors will not be counted."
fi

MASK=$(core_mask) || die "could not read the core presence mask (SMN $(printf '0x%X' "$MASK_REG")) via $NB_BDF."
NT=$(nthreads)

# -------------------------------------------------- crash from last boot ----
if [[ -s $PENDING ]]; then
  read -r P_ROUND P_ITEM P_BOOT P_CPUS P_SECS P_TOOL <"$PENDING"
  P_TOOL=${P_TOOL:-stress-ng}
  if [[ $P_BOOT != "$BOOT_ID" ]]; then
    hdr "The last attempt did not finish"
    say "Round $P_ROUND, $P_ITEM (CPUs $P_CPUS): the system went down while the load was running."
    PREV=$(sudo -n journalctl -k -b -1 --no-pager 2>/dev/null | grep -E "$MCE_RE" | tail -5)
    [[ -n $PREV ]] && { say "Machine-check lines in the previous boot:"; say "$PREV"; }
    # rasdaemon survives the crash the journal may not have recorded, so show what it kept
    if (( RAS )); then
      PREV_RAS=$(ras_error_lines | tail -5)
      [[ -n $PREV_RAS ]] && { say "Most recent hardware errors recorded by rasdaemon:"; say "$PREV_RAS"; }
    fi
    if [[ $(ask "Did the system freeze, crash or reboot by itself? [Y/n]" y) =~ ^[Nn]$ ]]; then
      record "$P_ROUND" "$P_ITEM" "$P_CPUS" ABORTED - - - - "rebooted by hand during the attempt" - "$P_TOOL" -
      say "Recorded as interrupted; this attempt will run again."
    else
      record "$P_ROUND" "$P_ITEM" "$P_CPUS" CRASH-LOAD "$(grep -c . <<<"$PREV")" - - - "system went down" "${P_SECS:--}" "$P_TOOL" -
      say "Recorded as CRASH-LOAD."
    fi
  else
    record "$P_ROUND" "$P_ITEM" "$P_CPUS" ABORTED - - - - "script stopped" - "$P_TOOL" -
  fi
  rm -f "$PENDING"
fi

# ----------------------------------------------- --auto needs the autostart unit ----
AUTO_UNIT=bc250-cores-bisect-auto.service
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
    say "reboot, so --auto cannot continue on its own. See bc250-cores-bisect-auto.service.example."
  fi
fi

# ----------------------------------------------------------- phase logic ----
if [[ $PHASE == control ]]; then
  if [[ $MASK == 0xff ]]; then
    if (( NT >= 16 )); then
      die "all 8 cores are already enabled and online: an unlock is already active. The control
       must run on the stock 6C/12T. Full power off (cold boot) to revert, then run this again."
    fi
    die "the presence mask is already 0xFF (an unlock was applied this boot). The control must run
       on the stock state: full power off (cold boot) to revert, then run this again."
  fi
  if [[ $MASK != 0x77 ]]; then
    die "the core presence mask is $MASK, not the usual 0x77. On this board the disabled cores
       were very likely fused off for real defects. Not unlocking; nothing to bisect."
  fi
  if [[ -z $BASE_CORES ]]; then
    BASE_CORES=$(online_core_ids)
    cfg_set BASE_CORES "$BASE_CORES"; cfg_set CREATED "$(date '+%F %T')"
  fi
elif [[ $PHASE == unlock-pending ]]; then
  BASE_THREADS=$(cfg_get BASE_THREADS); BASE_THREADS=${BASE_THREADS:-12}
  if [[ $MASK == 0xff ]] && (( NT > BASE_THREADS )); then
    NOW_IDS=$(online_core_ids)
    NEW_CORES=$(comm -13 <(tr ' ' '\n' <<<"$BASE_CORES" | sort) <(tr ' ' '\n' <<<"$NOW_IDS" | sort) | sort -n | tr '\n' ' ' | sed 's/ $//')
    [[ -n $NEW_CORES ]] || die "mask is 0xFF and extra threads are online, but no new core_ids found. Topology unclear; stopping."
    cfg_set NEW_CORES "$NEW_CORES"; cfg_set PHASE bisect; PHASE=bisect
    say "Unlock took effect: new cores detected: $NEW_CORES ($NT threads online)."
  elif [[ $MASK == 0xff ]]; then
    die "the mask is 0xFF but the extra cores are not online yet. Reboot (warm) and run this again."
  else
    say "The unlock did not survive (mask $MASK): a cold boot reverts it. Re-applying..."
    cfg_set PHASE control; PHASE=control   # fall through: control is already done, re-offer unlock below
  fi
fi

build_plan

hdr "BC-250 cores bisect $VERSION"
say "Phase: $PHASE   Presence mask: $MASK   Threads online: $NT"
say "Stock cores: ${BASE_CORES:-?}${NEW_CORES:+   New cores: $NEW_CORES}"
say "Items: ${ITEMS[*]}"
say "Rounds: $ROUNDS   Load: $(load_desc)   Mode: $([[ $SAME_BOOT == 1 ]] && echo 'same boot' || echo 'one attempt per boot')"
(( RAS )) && say "Hardware errors: kernel log + rasdaemon (ras-mc-ctl)"
[[ -n ${BASE_CORES:-} ]] && draw_core_map
# changing -t/-r mid-run silently mixes evidence; say so before the new values are saved
if awk -F'\t' '$6!="ABORTED"{f=1} END{exit !f}' "$RUNS"; then
  CHANGES=()
  [[ -n $OLD_TIME && $OLD_TIME != "$STRESS_SECS" ]] && CHANGES+=("load ${OLD_TIME}s -> ${STRESS_SECS}s: earlier attempts keep their ${OLD_TIME}s and still count")
  [[ -n $OLD_ROUNDS && $OLD_ROUNDS != "$ROUNDS" ]] && CHANGES+=("rounds $OLD_ROUNDS -> $ROUNDS$([[ $PHASE != control ]] && echo ': the control is already done and keeps its rounds')")
  [[ -n $OLD_LOAD_TOOL && $OLD_LOAD_TOOL != "$LOAD_TOOL" ]] && CHANGES+=("load tool $OLD_LOAD_TOOL -> $LOAD_TOOL: earlier attempts were run with $OLD_LOAD_TOOL and still count")
  if (( ${#CHANGES[@]} )); then
    hdr "Settings changed during a run"
    for w in "${CHANGES[@]}"; do say "- $w"; done
    say "The report will list the load per attempt. For a uniform result: --reset and start over."
    [[ $(ask "Continue with the new settings? [y/N]" y) =~ ^[Yy]$ ]] || exit 0
  fi
fi
cfg_set ROUNDS "$ROUNDS"; cfg_set TIME "$STRESS_SECS"; cfg_set LOAD_TOOL "$LOAD_TOOL"; cfg_set RAS "$RAS"

# control phase complete and passed -> offer the unlock
offer_unlock() {
  local it outs fails=0 o
  outs=$(awk -F'\t' '$4=="control" && $6!="ABORTED"{print $6}' "$RUNS")
  for o in $outs; do [[ $o =~ $FAIL_RE ]] && (( fails++ )); done
  if (( fails )); then
    summary
    say ""; say "The control failed: fix the board/power/heat first. Not offering the unlock."
    exit 1
  fi
  summary
  hdr "Control passed - ready to unlock"
  say "Next step: one SMU write sets the presence mask to 0xFF (all 8 cores). It only takes"
  say "effect on the next reboot, and a full power off reverts it. Nothing is persisted yet."
  [[ $(ask "Apply the unlock now? [y/N]" y) =~ ^[Yy]$ ]] || { say "Stopped before the unlock."; exit 0; }
  cfg_set BASE_THREADS "$NT"
  apply_unlock || die "the unlock failed; nothing was changed persistently. See the message above."
  cfg_set PHASE unlock-pending
  say "Mask is 0xFF. Reboot (warm - do NOT power off) to bring the cores up."
  if (( AUTO )); then say "Auto-rebooting (--auto)..."; do_reboot
  else
    [[ $(ask "Reboot now? [Y/n]" y) =~ ^[Nn]$ ]] || do_reboot
  fi
  exit 0
}

if ! NEXT=$(next_attempt); then
  if [[ $PHASE == control ]]; then offer_unlock
  else summary; write_report; exit 0; fi
fi

# ---------------------------------------------------------- safety checks ---
if [[ $SAME_BOOT == 0 && $(cat "$LASTBOOT" 2>/dev/null) == "$BOOT_ID" ]]; then
  say ""
  say "An attempt already ran in this boot. Reboot (warm, to keep the unlock) and run the"
  say "script again (or use --same-boot). Next: round ${NEXT% *}, ${NEXT#* }."
  (( AUTO )) && { say "Auto-rebooting (--auto)..."; do_reboot; }
  exit 0
fi
WARNINGS=()
[[ $PHASE == bisect && $MASK != 0xff ]] && die "phase is bisect but the mask is $MASK: a cold boot reverted the unlock. Run the script again; it will re-apply and reboot."
LOADAVG=$(awk '{print int($1)}' /proc/loadavg)
(( LOADAVG > 1 )) && WARNINGS+=("The system is busy (load $LOADAVG). Background work on the tested cores muddies the result.")
if (( ${#WARNINGS[@]} )); then
  hdr "Before you start"
  for w in "${WARNINGS[@]}"; do say "- $w"; done
  [[ $(ask "Continue anyway? [y/N]" y) =~ ^[Yy]$ ]] || exit 0
fi
say ""
say "WARNING: a genuinely bad core can freeze the system or corrupt data under load."
say "Save your work. After a freeze: reboot and run the script again; it records the crash."

# ----------------------------------------------------------------- attempt --
LOAD_PID=""
on_exit() {
  [[ -n $LOAD_PID ]] && kill "$LOAD_PID" 2>/dev/null
  if [[ -s $PENDING ]]; then
    read -r P_ROUND P_ITEM _ P_CPUS _ P_TOOL <"$PENDING"
    record "$P_ROUND" "$P_ITEM" "$P_CPUS" ABORTED - - - - "stopped (Ctrl+C)" - "${P_TOOL:-$LOAD_TOOL}" -
    rm -f "$PENDING"
  fi
  kill "$KEEPALIVE" 2>/dev/null
}
trap on_exit EXIT
trap 'exit 130' INT TERM

set_pending() { printf '%s %s %s %s %s %s\n' "$1" "$2" "$BOOT_ID" "$3" "$STRESS_SECS" "$LOAD_TOOL" >"$PENDING"; sync "$PENDING" 2>/dev/null; }

MON_MAXT=0 MON_MAXF=0
monitor_load() { # cpus - watch $LOAD_PID, track the peaks, return the load's exit code
  local cpus=$1 start=$SECONDS v rc
  while kill -0 "$LOAD_PID" 2>/dev/null; do
    sleep 5
    v=$(cpu_temp); (( v > MON_MAXT )) && MON_MAXT=$v
    v=$(cpu_freq "$cpus"); (( v > MON_MAXF )) && MON_MAXF=$v
    printf '\r  %3ds  %s C  %s MHz   ' "$(( SECONDS - start ))" "$MON_MAXT" "$MON_MAXF"
  done
  wait "$LOAD_PID"; rc=$?; LOAD_PID=""; echo
  return $rc
}

run_attempt() { # round item
  local r=$1 it=$2 cpus=${ITEM_CPUS[$2]} t0 mces verrs=0 rc=0 note="" o n
  local log mlog ras0=0 ras_new=0 mp_failed=0
  log="$LOGS/$(date '+%Y%m%d-%H%M%S')-r$1-$2.log"; mlog="${log%.log}-mprime.log"
  hdr "Round $r/$ROUNDS: $it  (CPUs $cpus)"
  [[ -n ${BASE_CORES:-} ]] && draw_core_map "$it"
  if [[ -z $cpus ]]; then
    record "$r" "$it" "-" OFFLINE - - - - "no online CPUs found for this item" - "$LOAD_TOOL" -; return 0
  fi
  n=$(( $(tr -cd , <<<"$cpus" | wc -c) + 1 )); [[ $cpus == *-* ]] && n=$(nthreads)
  t0=$(date '+%F %T')
  set_pending "$r" "$it" "$cpus"
  echo "$BOOT_ID" >"$LASTBOOT"; sync "$LASTBOOT" 2>/dev/null
  ras0=$(ras_error_count)
  MON_MAXT=0 MON_MAXF=0

  if [[ $LOAD_TOOL == stress-ng || $LOAD_TOOL == both ]]; then
    say "Running stress-ng --verify on CPUs $cpus for ${STRESS_SECS}s..."
    taskset -c "$cpus" "$STRESS_BIN" --cpu "$n" --cpu-method all --verify \
      --timeout "${STRESS_SECS}s" --metrics-brief </dev/null >"$log" 2>&1 &
    LOAD_PID=$!
    monitor_load "$cpus"; rc=$?
  else
    : >"$log"   # no stress-ng this run; keep the per-attempt log file for the report
  fi
  # mprime runs after stress-ng (not next to it) so the two never fight over the same threads
  if [[ $LOAD_TOOL == mprime || $LOAD_TOOL == both ]] && (( rc == 0 )); then
    say "Running mprime torture test on CPUs $cpus for ${STRESS_SECS}s..."
    if mprime_start "$it" "$cpus" "$n" "$STRESS_SECS" "$mlog"; then
      local mp_rc; monitor_load "$cpus"; mp_rc=$?
      mprime_failed "$mlog" "$mp_rc" && mp_failed=1
    else
      mp_failed=2
    fi
  fi

  mces=$(mces_since "$t0")
  verrs=$(grep -c 'fail:' "$log" 2>/dev/null); verrs=${verrs:-0}
  ras_new=$(( $(ras_error_count) - ras0 )); (( ras_new > 0 )) || ras_new=0
  [[ -n $mces ]] && say "$mces"
  (( ras_new )) && { say "rasdaemon recorded $ras_new new hardware error(s):"; ras_error_lines | tail -n "$ras_new"; }

  if [[ -n $mces ]]; then o=MCE; note="machine-check events in the kernel log"
  elif (( rc == 2 )); then o=VERIFY-FAIL; note="stress-ng verification failures: $verrs"
  elif (( rc != 0 )); then o=LOAD-FAIL; note="stress-ng exit $rc: $(tail -1 "$log" | tr '\t' ' ' | cut -c1-80)"
  elif (( mp_failed == 2 )); then o=LOAD-FAIL; note="could not start mprime"
  elif (( mp_failed )); then o=MPRIME-FAIL
    note="mprime: $(grep -aEm1 "$MPRIME_FAIL_RE" "$mlog" | tr '\t' ' ' | cut -c1-80)"
    note=${note:-mprime stopped early}
  elif (( ras_new )); then o="RAS-ERROR"; note="rasdaemon recorded $ras_new new hardware error(s)"
  else o=PASS; verrs=0; fi
  record "$r" "$it" "$cpus" "$o" "$(grep -c . <<<"$mces")" "$verrs" "$MON_MAXT" "$MON_MAXF" \
    "${note:--}" "$STRESS_SECS" "$LOAD_TOOL" "$( (( RAS )) && echo "$ras_new" || echo - )"
  rm -f "$PENDING"
  say "Result: $o${note:+ ($note)}"
}

auto_cleanup() { # the run is finished: stop the --auto loop from coming back at the next login
  (( AUTO )) || return 0
  rm -f "$HOME/.config/autostart/bc250-cores-bisect-watch.desktop"
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
    say "Cooling down 30 s..."; sleep 30
  done
  if [[ $PHASE == control ]] && ! next_attempt >/dev/null; then offer_unlock; fi
  summary; next_attempt >/dev/null || { write_report; auto_cleanup; }
else
  run_attempt ${NEXT% *} "${NEXT#* }"
  if [[ $PHASE == control ]] && ! next_attempt >/dev/null; then offer_unlock; fi
  summary
  if NEXT=$(next_attempt); then
    say ""
    say "Next: round ${NEXT% *}, ${NEXT#* }. Each attempt needs a fresh boot."
    say "Reboot WARM (do not power off): a cold boot reverts the unlock."
    if (( AUTO )); then say "Auto-rebooting to continue (--auto)..."; do_reboot
    else
      [[ $(ask "Reboot now? [Y/n]" y) =~ ^[Nn]$ ]] || do_reboot
    fi
  else
    write_report
    auto_cleanup
    say "Done. A full power off (cold boot) reverts the unlock to the stock 6C/12T."
  fi
fi
