<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# The repository

The long form of the root [CLAUDE.md](../CLAUDE.md)'s What this is: every folder and tool of Nexus, and the rules
about the repository's shape. Read it when a task moves files, adds an app or a tool, touches a workflow or the
wikis' shared parts. Paths are written from the repository root.

## Nexus and its suites

The repository is **Nexus**, `github.com/RobertoTorino/nexus` (branch `main`; until 25-10-2026
`bc250-bazzite-suite`, which GitHub redirects: never make a repository of that name again, it would end the
redirect that installed portals update through). It is the umbrella over the suites: every suite in a folder of its
own (owner, 26-10-2026), with what they share at the root. The **BC250 Bazzite Suite** (tools for the AMD BC-250 on
Bazzite) is `bc250-bazzite/`; the BC250 suite's tag names (`<app>-v<x.y.z>`, `portal-v<x.y.z>`), app ids and wiki address did not
change with the move. The **Windows Portable Suite** (Windows handhelds) is a repository of its own,
`github.com/RobertoTorino/windows-portable` (owner, 13-11-2026: one repository per suite; the Bazzite Console Suite
left first, to `bazzite-console`, with a copy of the tools). It keeps no copy of core or the tools: it is cloned into
this checkout as `windows-portable/` (in `.gitignore`), where the tools find it as any suite (`tools/suites.py`:
`OWN_REPOSITORIES`, `own_repository()`, and `of_repository()` for the suites that are folders of Nexus's own
repository). git in that folder is the suite's: `tools/tag-release.sh` tags it there and asks for its `ci.yml`
(`tools/ci_state.py --repo`), and the Nexus Release Tool does not list it. Its workflows (`ci.yml`, `release.yml`,
`upstream.yml`) are in its repository and start each job with `.github/actions/suite` (Nexus at the commit the
suite's `NEXUS_REF` names, the suite inside it as `windows-portable/`). Nexus's `docs.yml` and `nexus-index.yml`
check the suite out the same way: its wiki keeps its address under the Nexus page, and the index keeps its section.
What is listed per suite and written by a tool goes where the suite is: `tools/make_icons.py` writes the suite's
icons to `windows-portable/ICONS.md`, not the root's. A checkout of Nexus alone has no such folder: the tests about
the suite skip there and run in the suite's CI (its `nexus-tools` job). **Each suite stands apart** (owner, 27-10-2026): a change to one suite never edits another suite's
folder, its CI or its release workflow, and a change both suites want is two changes, one per suite, each with its
own release. `ci-nexus.yml` is Nexus's (core, the Nexus tools, `dev/`, the Nexus page and the repository's rules);
`ci.yml` and `release.yml` are the BC250 suite's; a suite in a repository of its own has its `ci.yml` and
`release.yml` there. A suite's tags wait for its own CI and for `ci-nexus.yml`, never for another suite's
(`tools/tag-release.sh`, `tools/ci_state.py --workflow`; `tools/tests/test_layout.py` keeps them apart). The
local gates do the same (owner, 28-10-2026): the pre-push hook and the Nexus Release Tool's Commit step run a suite's version
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
default suite of the tools (`tools/suites.py`).

## The root

The root keeps what is Nexus's:

- `core/bc250_core/`: shared Python code, every suite's. It is **bundled per app** at release time
  (`tools/stage_app.py`), so each app runs on the core it was tested with; the BC250 suite's shared venv
  `~/.local/share/bc250-bazzite-suite/venv` holds only PyQt6 and pygame-ce (the portal's controller reader).
  `nexus.py` in it is Nexus's design for the Nexus apps (the theme `NEXUS`, `create_app(theme=NEXUS)`).
- `tools/`: the Nexus tools: release and CI (`stage_app.py`, `build_release.py`, `check_versions.py`, `tag-release.sh`, `release.sh`, `ci-local.sh`, `pre-push.sh`, `git-setup.sh` (once per
  checkout: the pre-push hook; owner, 01-11-2026), `fix-modes.sh`, `dev_versions.py` (the dev/ apps' versions),
  `backlog.py`, `nexus_index.py` (GitHub's Latest release: the Nexus index, every suite's newest portal),
  `dev-backup.sh`), `features.py` (the Nexus page's Apps and features chapter from
  `nexus/features.toml`: every app of every suite and its features, a mark per suite; its test fails while an app
  is in no family or the chapter is stale), `new_app.py` (a new app of a suite from the architecture chapter, listed
  everywhere the suite lists its apps, with the checks run on it), the design and icon catalogs (`make_design.py`, `make_icons.py`, `apply_design.py`),
  `sync_icons.py` (a suite's category icons and their copies in its apps; owner, 02-11-2026: a Nexus tool, the
  BC250 suite's before), the tours
  (`app_tour.py`, `tour_frames.py`), `build_windows_exe.py`, `mkdocs/` (the design panel) and `tools/tests/`.
  A tool that works on a suite takes it with `--suite` (`tools/suites.py`: the folders with `portal/apps.toml`);
  with one suite in the checkout it is the default.
- `dev/<name>/`: the Nexus-level development apps, laid out as a suite's apps are (the package, `images/`,
  `tests/`, `install.sh`, `run.sh` and the four files; `.standalone` and `.checkout-only`: never released). They
  run from the checkout and are in no portal (owner, 27-10-2026: no Development tab, a portal lists only released
  apps); each has an installer test in each suite's `tools/installer-tests/` (`<name>.sh`; `<name>.ps1` where it
  has an `install.ps1`), takes Nexus's design and icon, and its manual is on the Nexus page. **The tools for
  working on the suites are Nexus's, in one place** (owner, 02-11-2026): `dev/dash/` is the **Nexus Dashboard**,
  the one door to them (its tiles start the other Nexus apps and open the chosen suite's video tours and icons;
  manual: the Nexus page's Dashboard chapter); `dev/nrt/` is the **Nexus
  Release Tool** (NRT), the release front end (see [releases.md](releases.md)), with `install.ps1` and `run.ps1` for Windows; its manual is the
  Nexus page's Releases chapter; `dev/demo/` is **Nexus Demo Recorder** (a portal installation recorded with OBS,
  the BC250 suite's on Linux and the Windows Portable Suite's on Windows, with `run.ps1`; the OBS part of the BC250 suite's Media Tool, which is gone from the suite); `dev/itests/` is **Nexus
  Installer Tests** (a suite's installer tests one at a time; BC-250 Installer Tests, made every suite's);
  `dev/sounds/` is **Nexus Sound Lab** (short sound effects for the suites' windows, such as the tick when the
  controller moves the focus, made from sliders and saved as WAV; owner, 03-11-2026); `dev/deps/` is **Nexus Deps**
  (a suite's Python packages and tools on this machine, Fix for what is missing or outdated with pip, Homebrew or
  rpm-ostree, Bazzite's update state, every update of the machine with Update per source, and an hourly
  reminder; its catalog per suite in
  `nexus_deps/catalogs/<suite>.toml`; the BC250 suite's Dependency Checker, `apps/package`, until 07-11-2026). A
  suite's own scripts (its manifest, pins, board checks, tours, installer tests) stay in its `tools/`: the
  dashboard runs them there.
- `DESIGN.md` and `ICONS.md`: every color and every icon, per suite and the Nexus page; `test.sh` runs every test
  suite (core, tools, `dev/`, and the portal, tools and apps of each suite made for the system it runs on); `portal/apps.toml` at the root is a copy of the
  BC250 suite's for the portals installed before the move (`bc250-bazzite/tools/check_manifest.py` keeps it
  identical; the owner removes it once the first portal release after the move has been out for a while).

## Rules about the shape

- **Every former repo folder** (each app, `core/`, each suite's `portal/`, each `dev/` app) keeps LICENSE,
  .gitignore, VERSION and CHANGELOG. GitHub workflows live only in the root `.github/`. CI checks it, with no CRLF
  in the index and every `.sh` at 100755 (see [checks.md](checks.md)).
- **Consistent architecture** (the suite's CLAUDE.md has the layout): every app of a suite is built the same way;
  `tools/tests/test_layout.py` checks every suite. The rules that are a suite's (the board warnings, reboots, the
  baseline, the owner's setup, the scope, the names not to use) are in that suite's CLAUDE.md.
- **One disclaimer for every wiki** (owner, 28-10-2026): `tools/mkdocs/disclaimer.py` holds it; every wiki lists
  the hook, and its home page shows it once, in the footer: `<strong>Disclaimer:</strong>
  {{ config.extra.disclaimer }}` (owner, 28-10-2026: no Disclaimer section of its own on the home page;
  `tools/tests/test_disclaimer.py`). Every other Disclaimer
  section (a README, an app's README and manual chapter, which ships as its MANUAL.md) has the same text written
  out; the test compares each one word for word. A change to the text is a change to every one of them.
