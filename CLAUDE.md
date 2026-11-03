<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# CLAUDE.md

Instructions for Claude Code in this repository. The owner works on it from both Windows and Bazzite (Linux) and
talks to Claude on both, so this file, not a local memory, carries the standing rules. It holds the rules most
tasks need; the rest is in files it points to, read when the task calls for them:

- [.claude/repository.md](.claude/repository.md): the repository in full (the suites and their folders, the root's
  folders and tools, the `dev/` apps, the CI workflows per suite, the four files of every former repo folder, the
  disclaimer every wiki shares).
- [.claude/checks.md](.claude/checks.md): every check as CI runs it, per system, with the installer tests and the
  tooling they need.
- [.claude/releases.md](.claude/releases.md): what a release is, Nexus's version, the CHANGELOG kinds, and which
  steps are the owner's.
- [bc250-bazzite/CLAUDE.md](bc250-bazzite/CLAUDE.md) and [windows-portable/CLAUDE.md](windows-portable/CLAUDE.md):
  each suite's own rules (the layout of its apps, the board, the scope, the names not to use). Status and plans:
  [MIGRATION.md](MIGRATION.md).

## What this is

The repository is **Nexus**, `github.com/RobertoTorino/nexus` (branch `main`): the umbrella over the suites, every
suite in a folder of its own, with what they share at the root. The **BC250 Bazzite Suite** (the AMD BC-250 on
Bazzite) is `bc250-bazzite/`; the **Windows Portable Suite** (Windows handhelds) is `windows-portable/`. A suite's
`SYSTEM` file names the system it is made for and tested on, its release tags start with its `TAG_PREFIX` (`wp-`;
the BC250 suite has none and is the tools' default suite, `tools/suites.py`), and its folder holds its
`apps/<name>/`, its `portal/` with `apps.toml` (one pinned release per app), its wiki in `docs/`, its `icons/` and
its `tools/`. The root keeps what is Nexus's: `core/bc250_core/` (shared Python code, bundled per app at release
time), `tools/` (the Nexus tools: release and CI, design and icons, tours; a tool that works on a suite takes
`--suite`), `dev/<name>/` (the Nexus apps, run from the checkout and never released: Nexus Dashboard, Nexus Release
Tool, Nexus Demo Recorder, Nexus Installer Tests, Nexus Sound Lab), `nexus/` (the Nexus page,
robertotorino.github.io/nexus/), `DESIGN.md`, `ICONS.md` and `test.sh`.

**Each suite stands apart** (owner, 27-10-2026): a change to one suite never edits another suite's folder, its CI
or its release workflow, and a change both suites want is two changes, one per suite, each with its own release.
`ci-nexus.yml` is Nexus's (core, the Nexus tools, `dev/`, the Nexus page and the repository's rules); `ci.yml` and
`release.yml` are the BC250 suite's; a suite with a tag prefix has its own `ci-<suite>.yml` and
`release-<suite>.yml`.

## Rules from the owner

- **Never commit, tag or push.** The owner does every git commit, tag and push. Finish work in the working tree
  and say what is ready; don't offer to commit.
- **Releases are the owner's, all of it.** Claude never bumps a `VERSION`, tags, builds or publishes release
  assets, pins a release in a suite's `portal/apps.toml` or writes the release entries in the CHANGELOGs, and
  doesn't offer to. When finished work will need a release or a version bump, the handover says which app and why;
  the owner decides the number. Claude may change the release tools and their tests ([.claude/releases.md](.claude/releases.md)).
- **The current releases are the baseline.** They were tested extensively on two boards. Moving code must not
  change behavior; a finding in existing code is "a code path to check", not a known failure. Prove "unchanged"
  (diffs, pixel comparisons, the installer tests) rather than assume it.
- **READMEs and docs/ hold no status, plans, step numbers or decision notes.** Those go in MIGRATION.md, which
  neither links to. The backlog is what MIGRATION.md says is "on hold" (write it so, with the owner's date):
  `.github/workflows/backlog.yml` lists those items every Monday in the "Backlog review" issue (`tools/backlog.py`).
  No placeholder folders that only describe future work. CHANGELOG entries are history and may mention steps.
- **What touches every suite is documented on the Nexus page** (owner, 27-10-2026): `nexus/docs/` holds the central
  parts (the repository, Nexus Release Tool, GitHub's releases and the Nexus index, Nexus's tools and workflows,
  general information). A suite's wiki holds what is that suite's and links to the Nexus page for the rest.
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
- **Every entry starts with its kind** (owner, 15-10-2026): `Breaking.` (removed, or no longer working as before:
  major), `Added.` (a new feature: minor) or `Fixed.` (a bug or security fix: patch); 0.x apps too. The number
  stays the owner's.
- **VERSION is the single source** of each app's version. Copies in code (`__version__`, shell `VERSION=`,
  pyproject) must match: `tools/check_versions.py`. The root `VERSION` is Nexus's own, bumped by the owner.
- **Every former repo folder** (each app, `core/`, each suite's `portal/`, each `dev/` app) keeps LICENSE,
  .gitignore, VERSION and CHANGELOG. GitHub workflows live only in the root `.github/`.
- **A design per system** (owner, 25-10-2026): the Bazzite suites keep the Bazzite design (purple), the Windows
  suites have a design of their own, and Nexus has its own (`nexus/docs/stylesheets/nexus.css`); a Nexus app
  (`dev/`) takes Nexus's design and icon (core's `nexus.py`, the theme `NEXUS`, set with `create_app(theme=)`; its
  icon copies from `tools/make_icons.py`). Never carry one system's design over to another. The Windows Portable
  Suite's apps put far more weight on UX and UI than the board's: a small screen held in the hands, touch and a
  controller instead of a mouse and keyboard.
- **An info symbol where space is limited** (owner, 01-11-2026): a window never carries long lines of explanation.
  Where a line of hint text would take the room, a small round "i" (core's `InfoButton`) opens the text on a click,
  with its links; a short line under a control stays a `hint_label`. The Nexus page's Design chapter says so.
- **Consistent architecture:** every app of a suite is built the same way (the suite's CLAUDE.md has the layout;
  `tools/tests/test_layout.py` checks every suite).
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
  whose `SYSTEM` matches (`NEXUS_SYSTEM=bazzite` or `windows` picks them by hand). The tests of the shared parts
  that need Linux (sysfs, file modes, bash) skip on Windows with their reason.
- **Tests must not write to the Windows registry** (QSettings' native format there): the conftest fixtures turn
  settings into .ini files in a temp folder.
- Keep path and link case exact: Linux and GitHub are case-sensitive.

## Checks before handing work over

`tools/ci-local.sh` runs every CI job as GitHub runs it (Python 3.12, each job with only its own requirements, in a
container, which `./test.sh` in the full venv on a newer Python cannot show); run it before saying work is ready.
`tools/pre-push.sh` is CI's quick checks against `origin/main` (git's pre-push hook), `./test.sh` every test suite
of this system. The full list, with the Windows Portable Suite's PowerShell checks, the installer tests and the
tooling, is [.claude/checks.md](.claude/checks.md).

**Missing tooling is installed, not worked around** (owner, 26-10-2026): when a check needs a tool the machine
lacks (Node.js for the design panel's script, shellcheck, fakeroot, podman), get it (`brew install` on Bazzite)
and run the check, rather than reviewing by eye.

## Style

Code reads like the code around it: the same comment density, naming and idiom. Docs are plain, short sentences,
written for the person using the tool.

**American English** (owner, 26-10-2026) in everything written: color, gray, center, canceled, license, catalog,
labeled. Identifiers, settings keys, file names and recorded data keep the spelling they have.

**Pictures are WebP wherever WebP is accepted** (owner, 26-10-2026): a picture put on a page (the wikis, the Nexus
page, a README on GitHub) or in an app's window is a `.webp` copy of its source (`make_icons.py` and the wiki's
hook already convert); a PNG stays only where WebP is not accepted or expected: a favicon, the `-128.png` menu and
Desktop icons, the source drawings in `nexus/images/` and a suite's `icons/`, and pictures a ported tool brought
with it.

A suite's manual (its `docs/`, built with MkDocs) is called **the wiki** in user-facing text: the header link and the
Home page's footer say Wiki. There is no GitHub wiki; the repository's own wiki stays unused.
