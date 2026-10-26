<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# BC-250 Bazzite Test - development

Based on the Diagnostic script for **Bazzite** (Fedora Atomic / rpm-ostree) running on an **AMD BC-250** board (Cyan Skillfish APU,
`gfx1013`, PCI `1002:13fe`).

It is **read-only**: nothing is installed, enabled, disabled or reconfigured. The only exception is
the opt-in `--stress` mode, which deliberately puts the board under load.

---

## Getting started

### Requirements

| What         | Version                        | Notes                                                                           |
|--------------|--------------------------------|---------------------------------------------------------------------------------|
| Python       | 3.10 or newer                  | Developed on 3.13. Bazzite ships a recent Python 3 (3.13+), no layering needed. |
| PyQt6        | 6.11 – 6.x (`requirements.txt`) | The pip wheel bundles Qt, including the Wayland and X11 platform plugins.       |
| PyQt6-Charts | same minor version as PyQt6    | Qt Charts, for **Show graph**. Optional: without it the rest of the app works.  |
| bash, sudo   | —                              | Present on Bazzite. The GUI runs `test-bazzite.sh` through `sudo`.              |

Install nothing with `rpm-ostree` for the GUI itself — a venv in your home directory is enough.

### Develop elsewhere (e.g. macOS)

The real script needs systemd, journald and the BC-250 sysfs nodes. For UI work use the stand-in, which accepts the same options and prints the same line format:

```bash
_python/bin/python -m bazzite_check --script development/tools/fake-test-bazzite.sh --no-sudo
```

To drive the GUI with a real report from the board instead of simulated output, point `BC250_REPLAY`at a `/var/log/bc250-bazzite-test/bc250-test-results-*.log` file. Selected tests (`--only`) are cut from that report:

```bash
BC250_REPLAY=debug/bc250-test-results-20260929-093526.log \
  _python/bin/python -m bazzite_check --script development/tools/fake-test-bazzite.sh --no-sudo
```

### Local Bazzite image build (package testing)

`development/tools/bazzite-image/` builds a custom Bazzite OCI image with Podman, so a package or setup can be
tested against a fully set-up system without touching a board first:

```bash
cd development/tools/bazzite-image
./build.sh --test        # builds bazzite-custom:<timestamp> and :latest, then a sanity check
```

The `Containerfile` layers the same RPMs as `development/tools/install-requirements.sh --rpms`; a locally built
RPM of this project can be added via the commented `COPY`/`RUN` lines. On a board, rebase onto the
local image (undo with `rpm-ostree rollback`):

```bash
sudo rpm-ostree rebase ostree-unverified-image:containers-storage:localhost/bazzite-custom:latest
```

### How it works

* The GUI calls `test-bazzite.sh --gui [--no-desktop] [--only=NN,..] [--stress=S --interval=I]` (`--no-desktop` when *Settings › General › Copy the full reports to Desktop* is off). `--gui` words the how-to-run hints for the GUI ("Start test 42 (Performance page)" instead of "Re-run with --bench").
* Output is parsed per `[TEST NN]` block; the worst tag in a block (`ERROR` > `WARNING` > `SUCCESS` > `INFO`) sets the button color: red = error, orange = warning, green = OK, blue = info. A running test is yellow and labeled `running…`.
* `HINT:` lines (fix suggestions, ⚠ icon) and `NOTE:` lines (background, ℹ icon) are collected in the hints panel. Lines the script wrapped over several `HINT:`/`NOTE:` lines are joined into one hint.
* The stats toolbar counts the latest result of every test over all runs, kept in an SQLite history (`~/.local/share/bc250-bazzite-test/history.db`; script reports are imported at startup; inspect it during development with `sqlite3 ~/.local/share/bc250-bazzite-test/history.db .tables` — on Bazzite layer it once with `development/tools/install-requirements.sh --dev`). **Settings › Logs & history › Clean up logs…** removes logs older than N days, or all logs and the history. The **health score** is passed + info at 100%, warnings at 50%, failures at 0%, averaged over the tests that ran (green ≥ 90%, orange ≥ 70%, red below).
* **Settings** (last item in the navigation) opens a panel over the window: *Privacy* explains what is stored and what reaches the internet, and has the options *keep a test history*, *store kernel version and mitigation state* (off by default), *mask personal data in saved GUI logs* (on by default) and *run with sudo* / *forget sudo authentication*; *General* has the notifications and the copy of the reports to the Desktop; *System overview* shows unlocked CUs (e.g. 36/40), CPU cores and threads (6/8, 12/16), the latest speed test download/upload and the NVMe size and free space and the package count (test 45) as colored boxes, read only when the page is opened; *Logs & history* has **Clean up logs…**; *About* shows version, build date and the repository. Preferences are stored in `~/.config/bc250-bazzite-test/bc250-bazzite-test.ini`.
* Test 41 only runs when the stress test is requested; otherwise it is left out, not counted as run.
* Every run is written to `~/.local/share/bc250-bazzite-test/logs/<YYYYmmdd-HHMMSS>_<scope>.log`; open them with **Show Logs**. The script still writes its own report to `/var/log/bc250-bazzite-test/`.
