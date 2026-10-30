<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# CLAUDE.md

Instructions for Claude Code in this repository. The owner works on it from both Windows and Bazzite (Linux) and
talks to Claude on both, so this file, not a local memory, carries the standing rules. Status and plans:
[MIGRATION.md](MIGRATION.md). This file holds what is Nexus's: the repository, git, releases, the CHANGELOG format
and kinds, line endings, the checks and the style. Each suite's own rules are in its folder's CLAUDE.md:
[bc250-bazzite/CLAUDE.md](bc250-bazzite/CLAUDE.md) for the BC250 Bazzite Suite,
[windows-portable/CLAUDE.md](windows-portable/CLAUDE.md) for the Windows Portable Suite.

## What this is

The repository is **Nexus**, `github.com/RobertoTorino/nexus` (branch `main`; until 25-10-2026
`bc250-bazzite-suite`, which GitHub redirects: never make a repository of that name again, it would end the
redirect that installed portals update through). It is the umbrella over the suites: every suite in a folder of its
own (owner, 26-10-2026), with what they share at the root. The **BC250 Bazzite Suite** (tools for the AMD BC-250 on
Bazzite) is `bc250-bazzite/`; its tag names (`<app>-v<x.y.z>`, `portal-v<x.y.z>`), app ids and wiki address did not
change with the move. The **Windows Portable Suite** (Windows handhelds) is `windows-portable/`: its apps are
released as one zip per tag with a PyInstaller build and an `install.ps1` (`windows-portable/tools/build_release.py`,
on Windows). **Each suite stands apart** (owner, 27-10-2026): a change to one suite never edits another suite's
folder, its CI or its release workflow, and a change both suites want is two changes, one per suite, each with its
own release. `ci-nexus.yml` is Nexus's (core, the Nexus tools, `dev/`, the Nexus page and the repository's rules);
`ci.yml` and `release.yml` are the BC250 suite's; a suite with a tag prefix has its own `ci-<suite>.yml` and
`release-<suite>.yml`. A suite's tags wait for its own CI and for `ci-nexus.yml`, never for another suite's
(`tools/tag-release.sh`, `tools/ci_state.py --workflow`; `tools/tests/test_layout.py` keeps them apart). The
local gates do the same (owner, 28-10-2026): the pre-push hook and the Nexus Release Tool's git commit run a suite's version
and manifest checks only when the push or commit changes that suite, so one suite's failing check never holds
another suite's work. `nexus/` is the Nexus page (robertotorino.github.io/nexus/): the name, the structure and the suites, and the
chapters that are every suite's (Releases, Development with bc250_core, The development machine, GitHub
settings, Design);
each suite's wiki has a folder of its own beside it (the BC250 Bazzite Suite's: `/nexus/bc250-bazzite-suite/`).

A suite's folder holds its `apps/<name>/` (each with its own VERSION, CHANGELOG, LICENSE and .gitignore), its
`portal/` with `apps.toml` (one pinned release per app) and `install.sh`, its `docs/` and `mkdocs.yml` (its wiki),
its `icons/` and its `tools/` (the suite's own tools and `tools/installer-tests/`). A **portal** installs and starts
the apps listed in its manifest; its test app (**check**, BC-250 Bazzite Test, for the BC250 suite) is always
installed and always listed first; every other listed app is an optional tile. A suite's `SYSTEM` file names the
system it is made for, `bazzite` or `windows` (owner, 26-10-2026: a suite is worked on and tested on its own system).
A suite's release tags start with its `TAG_PREFIX` (the Windows Portable Suite's `wp-`, owner, 26-10-2026:
`wp-portal-v0.1.0`); the BC250 suite has none, so its tags stay as installed portals know them, and it is the
default suite of the tools (`tools/suites.py`). The root keeps what is Nexus's:

- `core/bc250_core/`: shared Python code, every suite's. It is **bundled per app** at release time
  (`tools/stage_app.py`), so each app runs on the core it was tested with; the BC250 suite's shared venv
  `~/.local/share/bc250-bazzite-suite/venv` holds only PyQt6 and pygame-ce (the portal's controller reader).
- `tools/`: the Nexus tools: release and CI (`stage_app.py`, `build_release.py`, `check_versions.py`,
  `check_changelogs.py`, `tag-release.sh`, `release.sh`, `ci-local.sh`, `pre-push.sh`, `fix-modes.sh`,
  `backlog.py`, `nexus_index.py` (GitHub's Latest release: the Nexus index, every suite's newest portal),
  `dev-updates.sh`, `dev-backup.sh`), `new_app.py` (a new app of a suite from the architecture chapter, listed
  everywhere the suite lists its apps, with the checks run on it), the design and icon catalogs (`make_design.py`, `make_icons.py`, `apply_design.py`), the tours
  (`app_tour.py`, `tour_frames.py`), `build_windows_exe.py`, `mkdocs/` (the design panel) and `tools/tests/`.
  A tool that works on a suite takes it with `--suite` (`tools/suites.py`: the folders with `portal/apps.toml`);
  with one suite in the checkout it is the default.
- `dev/<name>/`: the Nexus-level development apps, laid out as a suite's apps are (the package, `images/`,
  `tests/`, `install.sh`, `run.sh` and the four files; `.standalone` and `.checkout-only`: never released). They
  run from the checkout and are in no portal (owner, 27-10-2026: no Development tab, a portal lists only released
  apps); each has an installer test in each suite's `tools/installer-tests/`. `dev/nrt/` is the **Nexus
  Release Tool** (NRT), the release front end (see Releases), with `install.ps1` and `run.ps1` for Windows; its manual is the
  Nexus page's Releases chapter.
- `SETUP.md`: what to take from the development machine before a drive change and what to install on the new
  one, in order (`tools/dev-backup.sh` packs and restores what the repository does not hold).
- `DESIGN.md` and `ICONS.md`: every color and every icon, per suite and the Nexus page; `test.sh` runs every test
  suite (core, tools, `dev/`, and the portal, tools and apps of each suite made for the system it runs on); `portal/apps.toml` at the root is a copy of the
  BC250 suite's for the portals installed before the move (`bc250-bazzite/tools/check_manifest.py` keeps it
  identical; the owner removes it once the first portal release after the move has been out for a while).

## Rules from the owner

- **Never commit, tag or push.** The owner does every git commit, tag and push. Finish work in the working tree
  and say what is ready; don't offer to commit.
- **Releases are the owner's, all of it.** See [Releases](#releases): Claude prepares code, never a release.
- **The current releases are the baseline.** They were tested extensively on two boards. Moving code must not
  change behavior; a finding in existing code is "a code path to check", not a known failure. Prove "unchanged"
  (diffs, pixel comparisons, the installer tests) rather than assume it.
- **READMEs and docs/ hold no status, plans, step numbers or decision notes.** Those go in MIGRATION.md, which
  neither links to. The backlog is what MIGRATION.md says is "on hold" (write it so, with the owner's date):
  `.github/workflows/backlog.yml` lists those items every Monday in the "Backlog review" issue (`tools/backlog.py`).
  No placeholder folders that only describe future work. CHANGELOG entries are history and may
  mention steps.
- **What touches every suite is documented on the Nexus page** (owner, 27-10-2026): `nexus/docs/`, the Nexus
  wiki, holds the central parts (the repository, Nexus Release Tool, GitHub's releases and the Nexus index, Nexus's
  tools and workflows, general information). A suite's wiki holds what is that suite's and links to the Nexus page
  for the rest, rather than explaining it again.
- **The wikis keep up with the work** (owner, 28-10-2026): new information, a new way of working or new logic worth
  knowing goes into its chapter of the wiki it belongs to (the Nexus page for Nexus's, the suite's wiki for a
  suite's) in the same change as the code, as a CHANGELOG entry does: what it does and how to use it, written for
  the person using it, never status or plans. The handover names the chapters it changed.
- **CHANGELOG for every change:** the root CHANGELOG for suite-wide changes, the app's (or core's, or portal's)
  for its own. Format: a `Changelog: DD-MM-YYYY HH:MM:SS` line, a blank line, then plain sentences; newest first.
  The time is Europe/Amsterdam (CET/CEST) on both systems, whatever the machine's own zone:
  `python3 -c "import datetime, zoneinfo; print(datetime.datetime.now(zoneinfo.ZoneInfo('Europe/Amsterdam')).strftime('%d-%m-%Y %H:%M:%S'))"`
  (on Windows with `.venv-windows/Scripts/python.exe`). Not `TZ=Europe/Amsterdam date`: Git Bash on Windows has no
  time zone data and silently gives UTC, an hour or two early.
- **Nexus's version** (owner, 28-10-2026): the root `VERSION`, with the root CHANGELOG, is Nexus's own; the owner
  bumps it (the Nexus Release Tool's step 1 row **nexus**). It is never tagged by hand: `nexus-index.yml` publishes GitHub's
  Latest release, the Nexus index, as `nexus-v<VERSION>` titled `Nexus v<VERSION>`. A suite's release (an app or a
  portal) moves it too, since the index lists every suite: a suite's release is minor, a new suite major (owner,
  28-10-2026); Nexus Release Tool offers it with every app and portal release.
- **One disclaimer for every wiki** (owner, 28-10-2026): `tools/mkdocs/disclaimer.py` holds it; every wiki lists
  the hook, and its home page shows it once, in the footer: `<strong>Disclaimer:</strong>
  {{ config.extra.disclaimer }}` (owner, 28-10-2026: no Disclaimer section of its own on the home page;
  `tools/tests/test_disclaimer.py`). Every other Disclaimer
  section (a README, an app's README and manual chapter, which ships as its MANUAL.md) has the same text written
  out; the test compares each one word for word. A change to the text is a change to every one of them.
- **Semantic versioning** (owner, 15-10-2026): in an app's, core's, the portal's or the root (Nexus's, from
  28-10-2026) CHANGELOG, every entry starts
  with its kind: `Breaking.` (removed, or no longer working as before: major), `Added.` (a new feature: minor) or
  `Fixed.` (a bug or security fix: patch). 0.x apps too: a feature takes 0.1.4 to 0.2.0. Nexus Release Tool offers the
  highest kind since the last tag first; `tools/tests/test_changelog_kinds.py` checks it. The number stays the
  owner's (see Releases).
- **VERSION is the single source** of each app's version (all started at 0.1.0). Copies in code (`__version__`,
  shell `VERSION=`, pyproject) must match: `tools/check_versions.py`.
- **Every former repo folder** (each app, `core/`, each suite's `portal/`, each `dev/` app) keeps LICENSE, .gitignore, VERSION and
  CHANGELOG. GitHub workflows live only in the root `.github/`.
- **A design per system** (owner, 25-10-2026): the Bazzite suites keep the Bazzite design (purple, the apps' theme and
  the wiki's), the Windows suites get a design of their own, and Nexus has its own
  (`nexus/docs/stylesheets/nexus.css`); a Nexus app (`dev/`) takes Nexus's design and icon, as Nexus Release Tool
  does (`dev/nrt/nexus_release_tool/style.py`, a core `Theme` set with `create_app(theme=)`; its icon copies
  from `tools/make_icons.py`). Never carry one system's design over to another. The Windows Portable Suite's
  apps put far more weight on UX and UI than the board's: a small screen held in the hands, touch and a controller
  instead of a mouse and keyboard.
- **Consistent architecture** (the suite's CLAUDE.md has the layout): every app of a suite is built the same way;
  `tools/tests/test_layout.py` checks every suite. The rules that are a suite's (the board warnings, reboots, the
  baseline, the owner's setup, the scope, the names not to use) are in that suite's CLAUDE.md.
- **Open by default.** Everything about the suite may be public: code, plans, the backlog, issues, test data and
  recordings from the boards. Only personal data stays out (names, addresses, host and user names, serial numbers,
  MAC and IP addresses, keys, account details), as the apps mask it in their logs. When in doubt whether something
  is personal, ask.
- **Ask** before decisions that are the owner's (what an app does, version numbers, repo layout, anything on the
  board). Do the obvious housekeeping without asking.

## Windows and Linux

The same repository is used from both systems.

- **Line endings:** every text file is LF in git and in the working tree (`.gitattributes`: `* text=auto eol=lf`).
  On Windows, check line endings by counting bytes in Python: Git Bash's grep and sed hide or strip CR.
- **Exec bits:** Windows git records new files as 100644. Before committing, `tools/fix-modes.sh` marks every
  `.sh` executable in the index; CI fails otherwise.
- **Venvs:** one per OS at the repo root, `.venv-linux/` and `.venv-windows/`; `./test.sh` picks the right one.
  Bazzite's system `python3` has no PyQt6. Create one from the repo root:
  - Linux: `python3 -m venv .venv-linux && .venv-linux/bin/python -m pip install -r requirements-dev.txt`
  - Windows (Git Bash): `py -m venv .venv-windows && .venv-windows/Scripts/python.exe -m pip install -r requirements-dev.txt`
- **Each suite on its own system:** `./test.sh` runs core, tools and `dev/` on both systems, and only the suites
  whose `SYSTEM` matches: the `bazzite` suites on Linux, the `windows` suites on Windows (`NEXUS_SYSTEM=bazzite` or
  `windows` picks them by hand). The tests of the shared parts that need Linux (sysfs, file modes, bash) skip on
  Windows with their reason. The BC250 suite's checks (its tests, installer tests, `tools/ci-local.sh`) run on
  Bazzite and in CI.
- **Tests must not write to the Windows registry** (QSettings' native format there): the conftest fixtures turn
  settings into .ini files in a temp folder.
- Keep path and link case exact: Linux and GitHub are case-sensitive.

## Checks before handing work over

The same checks as CI (`.github/workflows/ci-nexus.yml` and `ci.yml`), from the repo root. `tools/ci-local.sh`
runs them as CI does (Python 3.12, each job with only its own requirements, in a container), which `./test.sh` in
the full venv on a newer Python cannot show; run it before saying work is ready:

```bash
tools/ci-local.sh                                   # every job of both workflows as GitHub runs it (podman); --list shows them
tools/pre-push.sh                                   # CI's quick checks against origin/main (git's pre-push hook)
./test.sh                                           # every test suite of this system, offscreen
python3 tools/check_versions.py                     # versions = VERSION, every suite
python3 bc250-bazzite/tools/check_manifest.py --base origin/main  # the suite's apps.toml rules, the bump since the last portal release
python3 tools/check_changelogs.py --base origin/main  # no CHANGELOG lost an entry since the last push
find bc250-bazzite tools test.sh -name '*.sh' -print0 | xargs -0 -n1 bash -n
find bc250-bazzite tools test.sh -name '*.sh' -print0 | xargs -0 shellcheck -x -S error
shellcheck -x -S warning bc250-bazzite/portal/install.sh bc250-bazzite/apps/check/install.sh tools/*.sh \
  bc250-bazzite/tools/*.sh bc250-bazzite/tools/installer-tests/*.sh test.sh bc250-bazzite/install.sh tools/hooks/pre-push
S=bc250-bazzite   # the shellcheck -S warning lists of ci.yml, every app's scripts under $S/apps/<name>/
shellcheck -S warning $S/apps/cores/bc250-cores-bisect.sh $S/apps/cores/bc250-cores-unlock.sh \
  $S/apps/cores/install.sh $S/apps/cores/packaging/bazzite/*.sh
shellcheck -S warning $S/apps/oc/bc250-gpu-oc-bisect.sh $S/apps/oc/install.sh
shellcheck -S warning $S/apps/acpi/bc250-acpi-override.sh $S/apps/acpi/install.sh \
  $S/apps/overlay/install.sh $S/apps/bios/install.sh $S/apps/vram/install.sh $S/apps/fan/install.sh \
  $S/apps/cec/install.sh $S/apps/sftp/install.sh $S/apps/ips35/install.sh $S/apps/hdcam/install.sh $S/apps/hdcontrol/install.sh \
  $S/apps/consoles/install.sh $S/apps/clb/install.sh $S/apps/mtool/install.sh dev/nrt/*.sh $S/tools/check-release.sh
shellcheck -S warning $S/apps/ace/bc250-ace-queues.sh $S/apps/ace/bc250-ace-queues-run \
  $S/apps/ace/install.sh $S/apps/ace/mesa/build-in-container.sh
shellcheck -S warning $S/apps/mesh/bc250-mesh-shaders.sh $S/apps/mesh/bc250-mesh-shaders-run \
  $S/apps/mesh/install.sh $S/apps/mesh/mesa/build-in-container.sh
shellcheck -S warning $S/apps/shadps4/install.sh $S/apps/shadps4/bc250-shadps4-run
shellcheck -S warning $S/apps/rpcs3/install.sh $S/apps/rpcs3/bc250-rpcs3-run
shellcheck -S warning $S/apps/ppsspp/install.sh $S/apps/ppsspp/bc250-ppsspp-run \
  $S/apps/pcsx2/install.sh $S/apps/pcsx2/bc250-pcsx2-run $S/apps/vita3k/install.sh \
  $S/apps/vita3k/bc250-vita3k-run
shellcheck -S warning $S/apps/xenia/install.sh $S/apps/xenia/bc250-xenia-run
shellcheck -S warning $S/apps/decky/install.sh $S/apps/ncgui/install.sh \
  $S/apps/datstation/install.sh
for t in bc250-bazzite/tools/installer-tests/*.sh; do [ "${t##*/}" = shims.sh ] || bash "$t"; done   # every installer test
mkdocs build --strict -f bc250-bazzite/mkdocs.yml   # the suite's wiki, from the venv
mkdocs build --strict -f nexus/mkdocs.yml          # the Nexus page
mkdocs build --strict -f windows-portable/mkdocs.yml   # the Windows Portable Suite's wiki
```

On Windows, for the Windows Portable Suite (its own CI, `ci-windows-portable.yml`), from PowerShell at the repo root:

```powershell
.venv-windows\Scripts\python.exe tools\check_versions.py --suite windows-portable
.venv-windows\Scripts\python.exe windows-portable\tools\check_manifest.py --base origin/main
Get-ChildItem windows-portable\tools\installer-tests\*.ps1 | ForEach-Object { powershell -NoProfile -ExecutionPolicy Bypass -File $_.FullName }
.venv-windows\Scripts\python.exe windows-portable\tools\build_release.py wp-test-v<VERSION> <folder>   # needs pyinstaller and pillow in the venv
powershell -NoProfile -ExecutionPolicy Bypass -File windows-portable\tools\installer-tests\test.ps1 -Release <folder>\wp-test-v<VERSION>.zip
```

Every app (and every `portal/apps.toml` entry) has an installer test, `<suite>/tools/installer-tests/<name>.sh`
(`<name>.ps1` in a Windows suite), and CI runs each one in its own step (in a Windows suite, in a job of its own: the
`installers` matrix); a new app adds both (each suite's `tools/tests/test_installer_tests.py` checks it). BC-250 Installer Tests lists the scripts in that folder by itself. The installer tests need `fakeroot` (Linux). On Bazzite, `brew install shellcheck fakeroot node` (Node.js runs the design panel's script in
`tools/tests/test_design_panel.py`; the test skips without it); brew's folder
`/home/linuxbrew/.linuxbrew/bin` may need adding to PATH in a non-interactive shell. CI also checks the layout rules above: no CRLF in the index, every
`.sh` is 100755, every former repo folder has its four files, workflows only in the root `.github/`. The pytest
matrices of the CI workflows list every folder with `tests/` (`tools/tests/test_layout.py` checks it): `core`,
`tools` and each `dev/<name>` in `ci-nexus.yml`, each suite's `portal`, `tools`, `apps/<name>` and
`tools/installer-tests/gui` in the suite's CI. CI results
can be read without `gh` through the public API:
`curl -s https://api.github.com/repos/RobertoTorino/nexus/actions/runs?per_page=3`.

## Releases

A **Nexus release** (owner, 30-10-2026) is the one release of the repository: Nexus's version with every suite that
changed, started by the owner with the Nexus Release Tool's one action, Start new release
(`.github/workflows/release-nexus.yml` calls each changed suite's own release workflow, which builds, publishes and
pins; each portal ends as a draft the owner device-tests and publishes from the tool). A suite takes part once its
release workflow has `workflow_call` (the Windows Portable Suite; the BC250 Bazzite Suite still releases by tags).
The plan and its stages are in MIGRATION.md.

The owner does every step of a release; Claude does none of them, and doesn't offer to:

- bumping a `VERSION` (and the copies `tools/check_versions.py` checks), or `portal/VERSION`;
- tagging (`<app>-v<x.y.z>` or `portal-v<x.y.z>`, after the suite's prefix, with `tools/tag-release.sh`, which waits until CI passed on the
  commit), which starts `.github/workflows/release.yml` (it, too, builds only a commit CI passed);
- building or publishing release assets (`tools/build_release.py`) and the GitHub releases themselves;
- pinning a release in the suite's `portal/apps.toml` (`bc250-bazzite/tools/pin_app.py`, the `tag` and `sha256`
  lines);
- the release entries in the CHANGELOGs.

`tools/nrt.sh` starts the owner's front end for the file edits of a release, Nexus Release Tool (`dev/nrt/`,
a Nexus app with its suites' portals in its first column, the one to release ticked: `main_window.py` on
`plan.py`; a suite's board checks are its own
`tools/check-release.sh`, the BC250 suite's at `bc250-bazzite/tools/check-release.sh`; a Windows suite's
`tools/check-release.ps1`, run on the handheld). Claude may change it and
its tests, but never uses it on the repository.

Claude may change the release tools and their tests, and runs `bc250-bazzite/tools/installer-tests/release.sh` as a
test (it works in a temp folder and publishes nothing). When finished work will need a release or a version bump, the
handover says which app and why; the owner decides the number.

## Style

Code reads like the code around it: the same comment density, naming and idiom. Docs are plain, short sentences,
written for the person using the tool.

**American English** (owner, 26-10-2026) in everything written: color, gray, center, canceled, license, catalog,
labeled. Identifiers, settings keys, file names and recorded data keep the spelling they have.

**Pictures are WebP wherever WebP is accepted** (owner, 26-10-2026): a picture put on a page (the wikis, the Nexus
page, a README on GitHub) or in an app's window is a `.webp` copy of its source, as the app icons and the wiki's
app pictures are (`make_icons.py` and the wiki's hook already convert); a PNG stays only where WebP is not accepted
or expected: a favicon, the `-128.png` menu and Desktop icons (the icon theme), the source drawings in `nexus/images/`
and a suite's `icons/`, and pictures a ported tool brought with it.

**Missing tooling is installed, not worked around** (owner, 26-10-2026): when a check needs a tool the machine
lacks (Node.js for the design panel's script, shellcheck, fakeroot, podman), get it (`brew install` on Bazzite)
and run the check, rather than reviewing by eye.

A suite's manual (its `docs/`, built with MkDocs) is called **the wiki** in user-facing text: the header link and the
Home page's footer say Wiki. There is no GitHub wiki; the repository's own wiki stays unused.
