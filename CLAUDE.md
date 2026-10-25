<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# CLAUDE.md

Instructions for Claude Code in this repository. The owner works on it from both Windows and Bazzite (Linux) and
talks to Claude on both, so this file, not a local memory, carries the standing rules. Status and plans:
[MIGRATION.md](MIGRATION.md).
BC250
## What this is

The repository is **Nexus**, `github.com/RobertoTorino/nexus` (branch `main`; until 25-10-2026
`bc250-bazzite-suite`, which GitHub redirects: never make a repository of that name again, it would end the
redirect that installed portals update through). It is the umbrella over the suites; the **Windows Portable Suite**
(Windows handhelds, in `windows-portable/`) is planned in MIGRATION.md.
`nexus/` is the Nexus page (robertotorino.github.io/nexus/): the name, the structure and the suites; each suite's
wiki has a folder of its own beside it (the BC250 Bazzite Suite's: `/nexus/bc250-bazzite-suite/`).

The **BC250 Bazzite Suite** (exactly that name): tools for the AMD BC-250 on Bazzite, at the repository's root,
where its paths and tag names stay. A **portal** installs and starts the apps listed in
its manifest. **check** (BC-250 Bazzite Test) is always installed and always listed first; every other listed app is an optional
tile. Standalone apps may live under `apps/` without appearing in the portal.

- `apps/<name>/`: check, gpu, upscaler, compute, cores, oc, acpi,
  overlay, ips35, hdcam, hdcontrol, bios, ace, mesh, vram, fan, wdriver, cec, sftp, consoles, clb, shadps4, rpcs3, ppsspp, pcsx2, vita3k,
  xenia, decky, mtool, package, ncgui, datstation, suite. Each has its
  own VERSION, CHANGELOG, LICENSE (acpi is MIT; consoles is AGPL-3.0, its protocol code ported from
  chiaki-ng: those files AGPL-3.0-only, its own AGPL-3.0-or-later; ncgui is GPL-2.0-only, a port of NetcatGUI; clb
  (Console LinkB, Xbox) is GPL-3.0-or-later with protocol code ported from Greenlight and xal-node, MIT, whose notice
  its README keeps; the rest GPL-3.0-or-later), .gitignore. Every app
  has a `category` in `portal/apps.toml`, the same as its icon's in `icons/categories.toml` (sustainable, graphics,
  gaming, utilities, development): the portal shows a tab per category, with the notice of updates above the tabs
  (owner, 18-10-2026) and check as the first tile on Sustainable (owner, 20-10-2026). Media Tool, the Dependency Checker and Bazzite NetcatGUI are development apps.
  Suite Releases (the release front end) has `.standalone` and `.checkout-only`: it runs
  from the checkout, is never released, and is listed as `[checkout.suite]`, also on the Development tab:
  a portal from a release finds the checkout on the machine (it asks only when there is none) and remembers it, the
  released apps still come from their releases. Install every app through the portal, so what is installed stays in step. BC-250 Installer Tests (`tools/installer-tests/gui`) is
  checkout-only the same way: `.checkout-only` and `[checkout.installer-tests]` with `folder`.
- `core/bc250_core/`: shared Python code. It is **bundled per app** at release time (`tools/stage_app.py`), so each
  app runs on the core it was tested with; the shared venv `~/.local/share/bc250-bazzite-suite/venv` holds only
  PyQt6 and pygame-ce (the portal's controller reader).
- `portal/`: the portal, `apps.toml` (one pinned release per app) and its `install.sh`.
- `tools/`: release and CI tools, `tools/installer-tests/` (installers on Linux with fakeroot shims).

## Rules from the owner

- **Never commit, tag or push.** The owner does every git commit, tag and push. Finish work in the working tree
  and say what is ready; don't offer to commit.
- **Releases are the owner's, all of it.** See [Releases](#releases): Claude prepares code, never a release.
- **Warn before board changes.** Apps that change how the board runs (CU/core unlocks, GPU governor, GPU
  overclocking, ACPI override, the patched RADV of ace, the DirectMesh RADV of mesh, the VRAM split of vram, the thermal guard of fan, the kernel module of wdriver) are marked `changes_board` and the portal asks first. Frame it as standard caution:
  the apps are software-only and reversible, not "risky".
- **Advice, not reboots.** No app reboots, powers off or logs out the board; when one is needed, the app says so
  (and which command does it). The exception, by design (owner, 15-10-2026): CU Bisect and Cores Bisect, whose
  rounds each need a fresh boot (they ask, or reboot by themselves with `--auto`), and Cores Unlock's boot service,
  which reboots warm once after a cold boot so the cores come up. A second exception (owner, 16-10-2026): the
  thermal guard shuts the board down cleanly at a critical temperature, to protect the hardware; the limits are
  the owner's. A new reboot anywhere else is the owner's decision.
- **The current releases are the baseline.** They were tested extensively on two boards. Moving code must not
  change behaviour; a finding in existing code is "a code path to check", not a known failure. Prove "unchanged"
  (diffs, pixel comparisons, the installer tests) rather than assume it.
- **READMEs and docs/ hold no status, plans, step numbers or decision notes.** Those go in MIGRATION.md, which
  neither links to. The backlog is what MIGRATION.md says is "on hold" (write it so, with the owner's date):
  `.github/workflows/backlog.yml` lists those items every Monday in the "Backlog review" issue (`tools/backlog.py`).
  No placeholder folders that only describe future work. CHANGELOG entries are history and may
  mention steps.
- **CHANGELOG for every change:** the root CHANGELOG for suite-wide changes, the app's (or core's, or portal's)
  for its own. Format: a `Changelog: DD-MM-YYYY HH:MM:SS` line, a blank line, then plain sentences; newest first.
  The time is Europe/Amsterdam (CET/CEST) on both systems, whatever the machine's own zone:
  `python3 -c "import datetime, zoneinfo; print(datetime.datetime.now(zoneinfo.ZoneInfo('Europe/Amsterdam')).strftime('%d-%m-%Y %H:%M:%S'))"`
  (on Windows with `.venv-windows/Scripts/python.exe`). Not `TZ=Europe/Amsterdam date`: Git Bash on Windows has no
  time zone data and silently gives UTC, an hour or two early.
- **Semantic versioning** (owner, 15-10-2026): in an app's, core's or the portal's CHANGELOG, every entry starts
  with its kind: `Breaking.` (removed, or no longer working as before: major), `Added.` (a new feature: minor) or
  `Fixed.` (a bug or security fix: patch). 0.x apps too: a feature takes 0.1.4 to 0.2.0. Suite Releases offers the
  highest kind since the last tag first; `tools/tests/test_changelog_kinds.py` checks it. The number stays the
  owner's (see Releases).
- **VERSION is the single source** of each app's version (all started at 0.1.0). Copies in code (`__version__`,
  shell `VERSION=`, pyproject) must match: `tools/check_versions.py`.
- **Every former repo folder** (each app, `core/`, `portal/`) keeps LICENSE, .gitignore, VERSION and CHANGELOG.
  GitHub workflows live only in the root `.github/`.
- **Not limited to the owner's setup.** The owner's board, TV, cable and settings are one case, not the target:
  apps read what the hardware reports and offer every option it supports (a CEC 2.0 TV, another display mode,
  a second adapter), and say so where an option does not apply, rather than leaving out what the owner's setup
  lacks. Recorded data from the owner's board makes good test fixtures; tests also cover other setups.
- **Consistent architecture.** Every app is built the same way, so one that works is the pattern for the next:
  - Layout: `apps/<name>/` holds its Python package(s) directly (`<package>/__main__.py`, no wrapper folder),
    `<name>` a short name and `<package>` the app's name without its BC-250 or Bazzite prefix
    (`apps/ace/ace_queues/`, `apps/ncgui/netcat_gui/`; owner, 17-10-2026, the apps move to it one at a time,
    MIGRATION.md says which did; a renamed app's old key goes in `RENAMED` in the portal's manifest.py),
    `images/`, `tests/`, `install.sh` and the four files; data the package reads (a catalogue, tables) sits in
    the package or beside it in the app folder. `tools/tests/test_layout.py` checks the layout. An app's icons are
    copies of its category's icon: `icons/categories.toml` assigns them, `tools/sync_icons.py` writes them.
  - Code: shared code comes from `bc250_core` (bundled per app); the installer writes a launcher in
    `~/.local/bin` whose exec line names the app's python, a menu entry and an optional Desktop icon; every app has
    its installer test (see Checks).
  - Window: the first line is the app's icon at 96 px on the left, spanning the title (with the version) and a
    second line below it (status boxes or the app's main controls).
  A new app copies the structure of an existing one; any deviation is the owner's decision. The manual's
  [Architecture and consistency](docs/development/architecture.md) describes it all, with the steps for a new app.
- **A design per system** (owner, 25-10-2026): the Bazzite suites keep the Bazzite design (purple, the apps' theme and
  the wiki's), the Windows suites get a design of their own, and Nexus has its own
  (`nexus/docs/stylesheets/nexus.css`). Never carry one system's design over to another. The Windows Portable Suite's
  apps put far more weight on UX and UI than the board's: a small screen held in the hands, touch and a controller
  instead of a mouse and keyboard.
- **Scope is the suite, not Bazzite.** We answer for the portal and its apps, not for Bazzite itself. A system-wide
  Bazzite package is in scope only where one of our apps uses it (the Dependency Checker lists it then); its
  updates and security fixes are Bazzite's. Our own code, and the Python packages in our apps' environments, are
  ours. One exception (owner, 15-10-2026): the Dependency Checker shows Bazzite's update state (the running image,
  an update waiting for a reboot, uupd's last run) and reminds weekly when one waits; it only reads it, and
  updating stays Bazzite's.
- **Open by default.** Everything about the suite may be public: code, plans, the backlog, issues, test data and
  recordings from the boards. Only personal data stays out (names, addresses, host and user names, serial numbers,
  MAC and IP addresses, keys, account details), as the apps mask it in their logs. When in doubt whether something
  is personal, ask.
- **chiaki-ng is named only where licensing needs it:** Console Link's LICENSE, the License sections of its README
  and manual chapter, the suite's license overview (README, docs/index.md) and this file. Everywhere else (code,
  comments, tests, vectors, log messages, the manual, CHANGELOGs, MIGRATION.md) it is "the reference" (the reference
  implementation); user-facing text does not mention it at all.
- **KROU4's PS5CameraDriver is never named** (owner, 23-10-2026), only in this file: not in code, comments, tests,
  the wiki, CHANGELOGs or MIGRATION.md. Where its tried firmware patch matters, it is "another project's firmware
  patch".
- **Ask** before decisions that are the owner's (what an app does, version numbers, repo layout, anything on the
  board). Do the obvious housekeeping without asking.

## Windows and Linux

The same repository is used from both systems.

- **Line endings:** every text file is LF in git and in the working tree (`.gitattributes`: `* text=auto eol=lf`).
  On Windows, check line endings by counting bytes in Python: Git Bash's grep and sed hide or strip CR.
- **Exec bits:** Windows git records new files as 100644. Before committing, `tools/fix-modes.sh` marks every
  `.sh` executable in the index; CI fails otherwise.
- **Venvs:** one per OS, `.venv-linux/` and `.venv-windows/`; `./test.sh` picks the right one. Bazzite's system
  `python3` has no PyQt6. Create one from the repo root:
  - Linux: `python3 -m venv .venv-linux && .venv-linux/bin/python -m pip install -r requirements-dev.txt`
  - Windows (Git Bash): `py -m venv .venv-windows && .venv-windows/Scripts/python.exe -m pip install -r requirements-dev.txt`
- **Windows-only test failures:** gpu's tests need `os.getuid` and one upscaler test needs the exec bit; both
  pass on Linux and in CI.
- **Tests must not write to the Windows registry** (QSettings' native format there): the conftest fixtures turn
  settings into .ini files in a temp folder.
- Keep path and link case exact: Linux and GitHub are case-sensitive.

## Checks before handing work over

The same checks as CI (`.github/workflows/ci.yml`), from the repo root. `tools/ci-local.sh` runs them as CI does
(Python 3.12, each job with only its own requirements, in a container), which `./test.sh` in the full venv on a
newer Python cannot show; run it before saying work is ready:

```bash
tools/ci-local.sh                                   # every CI job as GitHub runs it (podman); --list shows them
tools/pre-push.sh                                   # CI's quick checks against origin/main (git's pre-push hook)
./test.sh                                           # every test suite, offscreen
python3 tools/check_versions.py                     # versions = VERSION
python3 tools/check_manifest.py --base origin/main  # portal/apps.toml rules, the bump since the last portal release
python3 tools/check_changelogs.py --base origin/main  # no CHANGELOG lost an entry since the last push
find apps portal tools test.sh install.sh -name '*.sh' -print0 | xargs -0 -n1 bash -n
find apps portal tools -name '*.sh' -print0 | xargs -0 shellcheck -x -S error test.sh install.sh
shellcheck -x -S warning portal/install.sh apps/check/install.sh tools/*.sh tools/installer-tests/*.sh test.sh install.sh \
  tools/hooks/pre-push
shellcheck -S warning apps/cores/bc250-cores-bisect.sh apps/cores/bc250-cores-unlock.sh \
  apps/cores/install.sh apps/cores/packaging/bazzite/*.sh
shellcheck -S warning apps/oc/bc250-gpu-oc-bisect.sh apps/oc/install.sh
shellcheck -S warning apps/acpi/bc250-acpi-override.sh apps/acpi/install.sh \
  apps/overlay/install.sh apps/bios/install.sh apps/vram/install.sh apps/fan/install.sh \
  apps/cec/install.sh apps/sftp/install.sh apps/ips35/install.sh apps/hdcam/install.sh apps/hdcontrol/install.sh \
  apps/consoles/install.sh apps/clb/install.sh apps/mtool/install.sh apps/suite/*.sh
shellcheck -S warning apps/ace/bc250-ace-queues.sh apps/ace/bc250-ace-queues-run \
  apps/ace/install.sh apps/ace/mesa/build-in-container.sh
shellcheck -S warning apps/mesh/bc250-mesh-shaders.sh apps/mesh/bc250-mesh-shaders-run \
  apps/mesh/install.sh apps/mesh/mesa/build-in-container.sh
shellcheck -S warning apps/shadps4/install.sh apps/shadps4/bc250-shadps4-run
shellcheck -S warning apps/rpcs3/install.sh apps/rpcs3/bc250-rpcs3-run
shellcheck -S warning apps/ppsspp/install.sh apps/ppsspp/bc250-ppsspp-run \
  apps/pcsx2/install.sh apps/pcsx2/bc250-pcsx2-run apps/vita3k/install.sh \
  apps/vita3k/bc250-vita3k-run
shellcheck -S warning apps/xenia/install.sh apps/xenia/bc250-xenia-run
shellcheck -S warning apps/decky/install.sh apps/ncgui/install.sh \
  apps/datstation/install.sh
for t in tools/installer-tests/*.sh; do [ "${t##*/}" = shims.sh ] || bash "$t"; done   # every installer test
mkdocs build --strict                               # from the venv
mkdocs build --strict -f nexus/mkdocs.yml          # the Nexus page
```

Every app (and every `portal/apps.toml` entry) has an installer test, `tools/installer-tests/<name>.sh`, and CI runs
each one in its own step; a new app adds both (`tools/tests/test_installer_tests.py` checks it). BC-250 Installer
Tests lists the scripts in that folder by itself. The installer tests need `fakeroot` (Linux). On Bazzite, `brew install shellcheck fakeroot`; brew's folder
`/home/linuxbrew/.linuxbrew/bin` may need adding to PATH in a non-interactive shell. CI also checks the layout rules above: no CRLF in the index, every
`.sh` is 100755, every former repo folder has its four files, workflows only in the root `.github/`. CI results
can be read without `gh` through the public API:
`curl -s https://api.github.com/repos/RobertoTorino/nexus/actions/runs?per_page=3`.

## Releases

The owner does every step of a release; Claude does none of them, and doesn't offer to:

- bumping a `VERSION` (and the copies `tools/check_versions.py` checks), or `portal/VERSION`;
- tagging (`<app>-v<x.y.z>` or `portal-v<x.y.z>`, with `tools/tag-release.sh`, which waits until CI passed on the
  commit), which starts `.github/workflows/release.yml` (it, too, builds only a commit CI passed);
- building or publishing release assets (`tools/build_release.py`) and the GitHub releases themselves;
- pinning a release in `portal/apps.toml` (`tools/pin_app.py`, the `tag` and `sha256` lines);
- the release entries in the CHANGELOGs.

`tools/release.sh` starts the owner's front end for the file edits of a release, BC250 Suite Releases
(`apps/suite/`: `main_window.py` on `plan.py`, and `check-release.sh` for the board checks). Claude may
change it and its tests, but never uses it on the repository.

Decky Loader is pinned in decky (`loader.py`); `tools/check_upstream.py`, weekly in
`.github/workflows/upstream.yml`, says when Decky moved past the pin (a new release, a replaced asset, a changed
service unit). Moving the pin is code Claude may prepare (with its CHANGELOG entry); the board test and the
decky release are the owner's, and the handover says so.

Claude may change the release tools and their tests, and runs `tools/installer-tests/release.sh` as a test (it
works in a temp folder and publishes nothing). When finished work will need a release or a version bump, the
handover says which app and why; the owner decides the number.

## Style

Code reads like the code around it: the same comment density, naming and idiom. Docs are plain, short sentences,
written for the person using the tool.

The manual (`docs/`, built with MkDocs) is called **the wiki** in user-facing text: the header link and the Home
page's footer say Wiki. There is no GitHub wiki; the repository's own wiki stays unused.
