<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![BC-250 Cores Bisect](../assets/cores/bc250-cores-bisect.webp){ .app-logo }

# BC-250 Cores Bisect

Tells **bad CPU cores** apart from an **unstable core unlock** on the AMD BC-250 (Cyan Skillfish),
*before* you trust or persist the 8C/16T unlock.

The BC-250 ships with 6 of its 8 Zen 2 cores enabled (presence mask `0x77`: core 3 of each CCX fused
off, symmetric — which smells like product segmentation, not harvesting). The SMU exposes a quirk
(queue-3 message `0x98`) that writes `0xFF` to any SMN address, including the core presence mask at
SMN `0x5A870`, which the host can't write. That enables all 8 cores on the next warm reboot.

**The catch:** that primitive is all-or-nothing. Unlike a GPU CU unlock there is no per-core mask, so
you can't leave one bad core disabled. If *either* extra core is bad, the unlock is unusable on your
board — and you want to know that before you persist it and let a flaky core corrupt data.

`bc250-cores-bisect.sh` does its own unlock, so no other tool is involved, and tests in a way that
separates the possible causes. Sibling project of
[bc250-cu-bisect](compute.md), which does the same for the GPU CUs.

> **Warning:** this talks to the SMU and runs heavy CPU load. A bad core can freeze the system or
> corrupt data. Save your work first. Use at your own risk.

## How it works

Since the cores can't be enabled one at a time, the isolation happens **after** the unlock, with the
load pinned (`taskset`) to exactly the threads under test:

| Item           | When            | Pinned to                       | Separates                                       |
|----------------|-----------------|---------------------------------|-------------------------------------------------|
| `control`      | before unlock   | all stock cores (6C/12T)        | board / power / heat / load tool problems       |
| `post-control` | after unlock    | one stock core (2 threads)      | "the unlock destabilises the SoC" from bad cores |
| `coreN`        | after unlock    | one new core on its own         | which new core (if any) is bad                  |
| `combined`     | after unlock    | both new cores together         | cores that pass alone but fail together         |

```
          core0   core1   core2   core4   core5   core6   core3   core7
           ██      ██      ██      ██      ██      ██      ..      ..

██ stock, always enabled (6C/12T)    .. fused off, enabled by the unlock, tested one by one
```

The order isn't a typo: the map groups the stock cores first and the unlocked ones last, where their
verdict cells live. Why cores 3 and 7 specifically? The mask `0x77` is binary `0111 0111` — one
nibble per 4-core CCX, and in *each* CCX it's core 3 that is fused off. CCX0 keeps cores 0,1,2 and
CCX1 keeps 4,5,6; the unlock adds core 3 (CCX0) and core 7 (CCX1's "core 3"). That symmetry — the
same position disabled in both CCXs — is what smells like product segmentation rather than harvesting
of defective silicon.

The script shows this map live, with `>>` on the core under test and `ok`/`xx`/`??` once a core has a
verdict (GOOD / FAILS EVERY TIME / RANDOM).

Failures are detected four ways:

- **Machine-check events** in the kernel log (`journalctl -k`) — the classic symptom of marginal cores.
- **Wrong results, not only crashes:** `stress-ng --verify` recomputes and checks every stressor result.
- **Full crashes**, crash-safe: before every attempt the script saves what it's doing. After a freeze,
  reboot and run it again: it records the crash and shows the MCE lines of the previous boot.
- **Optional burn-in extras:** `mprime`'s torture test (`--load mprime|both`) and hardware error
  counters from `rasdaemon` (`--rasdaemon`); see [Longer burn-in](#longer-burn-in-mprime--rasdaemon).

The test plan, same philosophy as the CU bisect:

- **Control first:** the unlock is only offered after the stock cores pass every control round. A
  failing control means nothing can be concluded about the new cores.
- **Rounds:** every item runs several times (default 3), interleaved, so heat and time don't favour one.
- **One attempt per boot** (default): warm reboots preserve the unlock, so isolation costs nothing.
- **State machine across boots:** control → unlock → verify the cores actually came up → bisect →
  verdict. A cold boot mid-run is detected (mask back to `0x77`) and handled.
- **Mask gate:** boards whose stock mask isn't `0x77` are refused — a different mask strongly suggests
  genuinely defective silicon that was purposefully skipped.

## The verdict and the decision

- **`control` fails** → board, power, heat or load tool. Fix that first.
- **`post-control` fails** → the unlock destabilises even the stock cores on your board. Cold boot to
  revert; don't persist.
- **A core FAILS EVERY TIME** → likely genuinely bad silicon. Because the unlock is all-or-nothing:
  **don't use it at all.** Cold boot (full power off) reverts everything.
- **RANDOM failures** → points to power or heat, not silicon. Improve cooling and retest.
- **Everything GOOD, alone and combined** → the unlock looks safe; persist it (below).

## Requirements

- AMD BC-250, Linux with bash 4+. Tested against Bazzite (Fedora Atomic).
- `setpci` (pciutils) — SMN/SMU access goes through the PCI config space of `0000:00:00.0`.
- `stress-ng` and `taskset` (util-linux).
- sudo rights (for setpci and the kernel log only).
- Optional: `mprime` (Prime95) for the torture test and `rasdaemon` (`ras-mc-ctl`) for hardware
  error counters. Both are only needed if you ask for them.

## Before you start

1. Start from a **cold boot** (full power off) so the stock `0x77` state is guaranteed.
2. Close background workloads; the load must land only on the pinned cores.
3. The script stops `cyan-skillfish-governor-smu` for the few milliseconds of the SMU write (the
   governor shares the mailbox) and restarts it afterwards.

## Usage

Run it as your normal user:

```bash
chmod +x bc250-cores-bisect.sh
./bc250-cores-bisect.sh                 # 3 rounds, 600 s verified load per attempt
./bc250-cores-bisect.sh -t 1800 -r 5    # longer load, more rounds (recommended before trusting it)
./bc250-cores-bisect.sh --same-boot     # no reboots between bisect attempts (faster, less isolation)
./bc250-cores-bisect.sh --auto          # no prompts, auto-reboot, continues after every login
./bc250-cores-bisect.sh --load both     # stress-ng *and* the mprime torture test per attempt
./bc250-cores-bisect.sh --rasdaemon     # also count hardware errors via ras-mc-ctl
./bc250-cores-bisect.sh --status        # results so far, report + logs in ~/Desktop/bc250-cores-bisect/
./bc250-cores-bisect.sh --reset         # delete the results and start over
./bc250-cores-bisect.sh --help
```
Note: -t minimum = 60       

Flow: run → control rounds (one per boot) → it offers the unlock → warm reboot → it detects the new
cores → bisect rounds (one per warm reboot) → final summary, report and decision.

At the end of a run (and on every `--status`) everything is copied to `~/Desktop/bc250-cores-bisect/`
for easy sharing:

| File                                         | Contents                                                     |
|----------------------------------------------|--------------------------------------------------------------|
| `bc250-cores-bisect-results-<date>.txt`      | The report: core map, verdicts, decision, every attempt.     |
| `runs.tsv`                                   | The raw results table, one line per attempt.                 |
| `config`                                     | The run's settings and detected cores.                       |
| `logs/<date>-r<round>-<item>.log`            | stress-ng output of each attempt (verification failures etc).|
| `logs/<date>-r<round>-<item>-mprime.log`     | mprime torture output, when mprime is part of the load.      |
| `ras-mc-ctl-errors.txt`                      | rasdaemon's error table, when `--rasdaemon` is used.         |
| `auto.log`                                   | Everything the script printed in `--auto` runs.              |

The working copies live in `~/.local/share/bc250-cores-bisect/`; `--reset` deletes those, not the
Desktop folder.

Pick `-t`/`-r` before you start and keep them. You *can* change them mid-run (results so far are
kept and the script asks you to confirm), but the evidence is then mixed: the report lists the load of
every attempt, and a control that finished with fewer rounds keeps them. For a uniform result, use
`--reset` and start over.

For `--auto`, install the autostart unit (see `bc250-cores-bisect-auto.service.example`) so the script
resumes after every login.

### Running truly unattended (`--auto` checklist)

`--auto` makes the *script* hands-off, but the *system* must get back to your session on its own:

1. **Autologin** — after each reboot someone must log in, or the run stalls at the login screen.
   Enable it in your desktop (Bazzite/KDE: System Settings → Colors & Themes → Login Screen (SDDM) →
   Behavior → auto-login, or Users → auto-login on GNOME).
2. **Passwordless sudo** for your user — the script needs `setpci` and `journalctl -k` without a
   prompt (there is no terminal to type a password into when it runs from the unit):

   ```bash
   echo "$USER ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/bc250-bisect
   sudo chmod 440 /etc/sudoers.d/bc250-bisect
   sudo visudo -cf /etc/sudoers.d/bc250-bisect   # must print "parsed OK"
   sudo -k && sudo -n true && echo OK    # must print OK without asking
   ```
   Revert after testing with `sudo rm /etc/sudoers.d/bc250-bisect`.
   If you edit the file by hand, use `sudo visudo -f /etc/sudoers.d/bc250-bisect`: it refuses to save a broken line.
   A broken line makes every `sudo` command print a warning, or stops sudo working at all.
3. **The autostart unit installed** — without it nothing restarts the script after login and you'd
   have to start it manually every boot.
4. **No credential popups at login (KDE Wallet / ksshaskpass)** — with autologin the KDE Wallet
   can't auto-unlock, so a "SSH credentials" / wallet dialog can appear at session start and block
   the chain until answered. Either give the wallet a blank password (open it in `kwalletmanager5`
   first, then Change Password → empty), or disable the wallet subsystem (Plasma 6 has no UI
   checkbox for it anymore):

   ```bash
   kwriteconfig6 --file kwalletrc --group Wallet --key Enabled false   # kwriteconfig5 on Plasma 5
   ```
   Re-enable afterwards with `... --key Enabled true`. Also uncheck "Use KWallet for the Secret
   Service interface" in System Settings → KDE Wallet so apps don't route secrets to the disabled
   wallet.

Check on it while it runs:

```bash
systemctl --user status bc250-cores-bisect-auto.service   # ran / running / failed this boot
tail -f ~/.local/share/bc250-cores-bisect/auto.log        # live output of the current attempt
./bc250-cores-bisect.sh --status                          # progress and results so far
```

When all attempts are done the script stops rebooting on its own; in `--auto` mode it also disables
the autostart unit and removes the live-output entry (below) by itself, so nothing starts at the next
login. If you ran without `--auto`, disable the unit manually
(`systemctl --user disable --now bc250-cores-bisect-auto.service`).

Want the live output on the board's screen instead of a shell? Add a desktop autostart entry that
opens a terminal following the log at every login (KDE example; see the comments in
`bc250-cores-bisect-auto.service.example`):

```bash
cat > ~/.config/autostart/bc250-cores-bisect-watch.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=BC-250 bisect live output
Exec=konsole --title "bc250-cores-bisect" -e tail -n 40 -f .local/share/bc250-cores-bisect/auto.log
EOF
```

### How long does it take?

A full run is `5 × rounds` attempts (control, then post-control + core3 + core7 + combined), each
running the load for `--time` seconds, plus one warm reboot for the unlock. In the default
one-attempt-per-boot mode add a reboot-and-login (~1–2 min) per attempt; with `--same-boot` only 2–3
reboots total plus a 30 s cooldown between attempts. Indications:

| Invocation                           | Attempts | Pure load | Wall clock (approx.)   |
|--------------------------------------|----------|-----------|------------------------|
| default (`-t 600 -r 3`)              | 15       | 2 h 30 m  | ~3 h (15 reboots)      |
| `--same-boot` (`-t 600 -r 3`)        | 15       | 2 h 30 m  | ~2 h 45 m (3 reboots)  |
| `-t 1800 -r 5` (recommended)         | 25       | 12 h 30 m | ~13 h (25 reboots)     |
| `-t 1800 -r 5 --same-boot`           | 25       | 12 h 30 m | ~12 h 45 m (3 reboots) |

The longer runs are meant to be unattended: combine them with `--auto` (and the autostart unit) and
let it finish overnight. You don't have to do it in one sitting either — the state survives reboots,
so run the script again at any time and it continues where it left off (`--status` shows progress).

### Longer burn-in (`mprime` / `rasdaemon`)

`stress-ng --verify` is the default load and is enough for most boards. If you want a harder,
longer burn-in before you trust the unlock, two optional tools can be folded in:

```bash
./bc250-cores-bisect.sh --load mprime              # mprime torture test instead of stress-ng
./bc250-cores-bisect.sh --load both                # stress-ng first, then mprime
./bc250-cores-bisect.sh --mprime-bin ~/mprime/mprime
./bc250-cores-bisect.sh --rasdaemon                # count hardware errors around every attempt
./bc250-cores-bisect.sh -t 1800 -r 5 --load both --rasdaemon --auto --same-boot
```

- **`--load stress-ng|mprime|both`** (default `stress-ng`). `mprime` runs Prime95's torture test
  (`StressTester=1`, no PrimeNet) pinned to exactly the same CPUs as stress-ng, from a private
  working directory under `~/.local/share/bc250-cores-bisect/mprime/<item>/`. It is an
  AVX/FMA-heavy, in-cache FFT workload, which catches a different class of marginal silicon than
  stress-ng's mixed stressors. A torture error gives the attempt the outcome **`MPRIME-FAIL`**.
- With **`--load both`** the two tools run **one after the other**, never at the same time, so they
  don't fight over the same threads. Each attempt therefore takes **2 × `--time`** — budget double
  the wall clock from the table above.
- **`--mprime-bin PATH`** points at an mprime binary that isn't on `$PATH` (the official builds from
  mersenne.org are a plain tarball, so this is the normal case).
- **`--rasdaemon`** reads `ras-mc-ctl --errors` before and after every attempt and records the
  difference. Any new hardware error makes the attempt **`RAS-ERROR`**. It needs a running
  `rasdaemon` service; if `ras-mc-ctl` is missing or unusable the script says so and carries on
  without it. The full error table is exported as `ras-mc-ctl-errors.txt`.
- Both extras are recorded per attempt: `runs.tsv` gained a **load tool** and a **rasdaemon errors**
  column, and the report lists the load of every attempt, so a mixed run stays readable. Older
  result files from before this feature are still read correctly.

Like `-t`/`-r`, pick these before you start: the settings are stored in `config`, reused after
every reboot, and carried into the `--auto` service's command line.

## Making it persistent

Only after a clean verdict:

```bash
sudo ./bc250-cores-unlock.sh --install
```

The unlock is volatile: it survives warm reboots, a full power off reverts it, and a fresh write only
takes effect on the *next* reboot. So `--install` copies the script to `/usr/local/sbin` (root-owned)
and enables a root service that checks the mask early at every boot; after a cold boot it re-applies
the unlock and warm-reboots **once** (a guard file prevents reboot loops if the unlock ever stops
taking effect). `--uninstall` removes the service and the copy; the stock 6C/12T returns after the
next full power off. `--status` shows mask, threads, service and guard state.

A BIOS-mod route exists for true permanence
([RescueMei/BC250-DXEv3-BIOSMOD](https://github.com/RescueMei/BC250-DXEv3-BIOSMOD)) but is out of
scope here: this project stays software-only and reversible.

## GUI

![BC-250 Cores Unlock](../assets/cores/bc250-cores-unlock.webp){ width="96" }

Two separate PyQt6 front-ends ship with the project: a **setup GUI** that
starts a bisect run, and an **unlock GUI** for the persistence step afterwards. Both are optional —
everything they do can be typed by hand.

**Recommended: `install.sh`** (from a clone or the extracted release tarball). It installs both
GUIs at once: a root-owned copy of the toolset in `/opt/bc250-cores-bisect-v<version>` (with
`/opt/bc250-cores-bisect` pointing at it), a private PyQt6 venv in
`~/.local/share/bc250-cores-bisect-app/venv`, both launchers in `~/.local/bin`, app menu entries
and Desktop icons. Run it as your own user — only the copy to `/opt` asks for the sudo password.

```bash
./install.sh                         # install or update both GUIs
./install.sh --bisect-only           # or --unlock-only
./install.sh --no-desktop-shortcut   # app menu entries only
./install.sh --uninstall             # remove the apps; keeps results, settings and logs
./install.sh --uninstall --purge     # also remove results, settings, logs and the autostart unit
```

Your bisect results stay in `~/.local/share/bc250-cores-bisect`; the installer never touches that
folder unless you pass `--purge`. Installing also clears out any older per-user install made by the
`packaging/bazzite/` scripts below, so you don't end up with two menu entries per GUI.

### Setup GUI (`cores_bisect`)

A one-screen "initial setup" for `bc250-cores-bisect.sh`: pick the load time, the rounds per item,
the load tool and the two run-mode switches (`--same-boot`, `--auto`), then click
**Start Cores Bisect**. The
window closes and the real run continues in a terminal, exactly as if you had typed the command —
the GUI only assembles the command line, so the script stays the single source of truth.

- An estimate of the total runtime updates as you change the options.
- **Load tool** picks between stress-ng, mprime and both; **Also count hardware errors with
  rasdaemon** adds `--rasdaemon`. See [Longer burn-in](#longer-burn-in-mprime--rasdaemon).
- **Unattended** can also install and enable the auto-resume login service for you
  (`~/.config/systemd/user/bc250-cores-bisect-auto.service`), the same thing the
  [`--auto` checklist](#running-truly-unattended---auto-checklist) describes. The script removes it
  again once every item is done.
- **Show status** (`--status`) and **Reset** (`--reset`) run in a terminal too, so the script can
  still ask for its own confirmation.
- **Help** shows the script's own `--help`, so it can never drift out of sync.

Per-user alternative, one GUI only (no `/opt`, nothing root-owned):

```bash
bash packaging/bazzite/install-bisect-gui.sh     # venv + launcher + menu entry "BC-250 Cores Bisect"
bash packaging/bazzite/uninstall-bisect-gui.sh   # removes all of that again (keeps your results)
```

Installed per user under `~/.local/share/bc250-cores-bisect-gui`, launcher
`~/.local/bin/bc250-cores-bisect-gui`.

### Unlock GUI (`cores_unlock`)

`cores_unlock` is a small PyQt6 front-end for the **persistence** step.
It doesn't run the bisect — that stays a terminal job, because it reboots and runs for hours — but
it reads the results that `bc250-cores-bisect.sh` left in `~/.local/share/bc250-cores-bisect` and
puts `--install` behind a verdict gate:

- **ACCEPTED** only when the bisect phase is finished, no attempt is still in progress, control and
  post-control are clean, and every new core and the combined item passed **every** round. Notes
  (e.g. control ran fewer rounds, or loads changed mid-run) are shown but don't block.
- **NOT ACCEPTED YET** otherwise, with the reason (unfinished, failing core, random failures, …).
  Install stays disabled; Uninstall, Refresh status, Status with sudo and Re-check always work.
- A core map shows the 6 stock cores and the 2 unlocked ones (`ok` / `xx` fails / `??` random /
  `..` not tested).

Install/Uninstall run `bc250-cores-unlock.sh` via sudo; you're only asked for a password when sudo
actually needs one. Refresh status runs unprivileged (the mask is shown if sudo needs no password);
Status with sudo runs the same status as root, asking for the password if needed, so the mask is always shown.

**Bazzite (or any desktop, no root or rpm-ostree needed):** per-user alternative to `install.sh`,
this GUI only:

```bash
bash packaging/bazzite/install-gui.sh     # venv + launcher + menu entry "BC-250 Cores Unlock"
bash packaging/bazzite/uninstall-gui.sh   # removes all of that again (not the unlock service)
```

It installs per user under `~/.local/share/bc250-cores-unlock-gui`, with the launcher
`~/.local/bin/bc250-cores-unlock-gui`. The names don't clash with each other or with the
bc250-cu-bisect GUIs, so they can all be installed side by side.

**From a venv (development):**

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m cores_bisect  # --script PATH to use another bc250-cores-bisect.sh
.venv/bin/python -m cores_unlock         # --script PATH to use another bc250-cores-unlock.sh
```

## Known side effect

After the unlock, `pp_dpm_sclk` and `hwmon` `freq1_input` report nonsense GPU clocks (tens of MHz).
This is cosmetic — the SMU's own clock getters stay correct — and this script ignores GPU clocks.
Diagnostics that read those files (e.g. tests 19/40 of
[Bazzite Test](check.md)) will
flag it; that's expected while the unlock is active.

## Credits

The SMU quirk (queue-3 message `0x98` → `0xFF` at SMN `0x5A870`) was discovered and documented by
[rw-r-r-0644/bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) (MIT). This project
is an independent implementation built around those hardware facts, adding the control/bisect/verdict
methodology, crash-safe multi-boot state, and reversible persistence.

## License

GNU GPLv3, see [LICENSE](https://github.com/RobertoTorino/nexus/blob/main/apps/cores/LICENSE).
