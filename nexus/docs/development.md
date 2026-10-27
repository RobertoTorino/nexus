<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Development

How the repository is laid out, and how to work on it from Linux and Windows. What is a suite's own, how its apps
are built and released, is in its wiki: the BC250 Bazzite Suite's
[Development](https://robertotorino.github.io/nexus/bc250-bazzite-suite/development/). The repository's settings on
GitHub: [GitHub settings](github-settings.md). What a machine needs to work on it, on Bazzite or Windows:
[The development machine](machine.md). How releases are made and published: [Releases](releases.md).

## Layout

The repository is Nexus: every suite in a folder of its own, with what they share at the root. Paths in the wikis
are written from the root of the repository.

```
core/bc250_core/              shared Python package, every suite's; bundled into each app at release time (below)
tools/                        the Nexus tools: release and CI (build_release, stage_app, check_versions,
                              check_changelogs, tag-release.sh, release.sh, ci-local.sh, pre-push.sh, nexus_index),
                              new_app, the design and icon catalogs, the tours, the design panel
dev/<name>/                   the Nexus development apps, run from the checkout: dev/releases/ is Nexus Releases
test.sh                       runs every test suite (core, tools, dev/, and the portal, tools and apps of each suite
                              made for the system it runs on: SYSTEM in the suite's folder)
bc250-bazzite/                the BC250 Bazzite Suite
windows-portable/             the Windows Portable Suite (its tags start with wp-, TAG_PREFIX)
nexus/                        the Nexus page
DESIGN.md ICONS.md            every color and every icon, per suite and the Nexus page
SETUP.md                      what to take from the development machine and install on the next one
.github/workflows/            every workflow: ci.yml and release.yml (Nexus and the BC250 Bazzite Suite), each other
                              suite's ci-<suite>.yml and release-<suite>.yml, nexus-index.yml, docs.yml (the wikis)
```

Every suite's folder is laid out the same way:

```
<suite>/
  portal/                       the portal: app, apps.toml (one pinned release per app) and its installer
  apps/<name>/                  one folder per app, each with its own VERSION, CHANGELOG, LICENSE and .gitignore
  tools/                        the suite's tools and its installer tests
  docs/ mkdocs.yml              its wiki (MkDocs Material), when it has one
  icons/                        the category icons
  SYSTEM                        the system it is made for: bazzite or windows
  TAG_PREFIX                    what its release tags start with, when not nothing
```

## bc250_core

Code shared by every suite's apps (`core/`). Nothing in it imports an app: each app passes its constants in as an `AppInfo`.

| Module | What it holds | Merged from |
|---|---|---|
| `appinfo` | `AppInfo` (id, name, version, logo, tag prefix, settings names) | new |
| `theme` | The suite's theme (`THEMES`, `theme_name()`, `save_theme_name()`, `apply_theme()`, `surface_style()`, `muted()`), `STATE_COLORS`, bundled Inter font, `header_font()`, `HOVER_STYLESHEET`; self-contained, so an app not on core carries a copy | all six GUIs |
| `text` | `fmt()` (`%1` placeholders), `fill()` (`{name}` placeholders), `plain_tooltip()`, `window_title()` | governor, upscaler |
| `widgets` | `AppHeader` (the window header), `StatusPill`, `MetricBox`, `Pill` (a `MetricBox` that is a button), `same_width()`, `ClickableLogo`, `Terminal`, `TextDialog`, `RoundedToolTip`, `show_tooltip()`, `page_header()`, `hint_label()`, `accent_button()`, `set_button_active()` | governor + helixsr's Wayland tooltip + bazzite-test's manual tooltips |
| `app` | `create_app()` / `run_app()` / `exec_app()`: names, Fusion with the theme, tooltip, icon, SIGTERM | the apps' `__main__` |
| `settings` | `open_settings(info)` at each app's existing file, geometry helpers, `SettingsStore` (typed defaults) | bazzite-test's `AppSettings` |
| `help` | `HelpView` (the content stays in the app) | upscaler |
| `updates` | `latest_release()` (with a tag prefix for the suite's per-app tags), `UpdateStatus`, `UpdateChecker` (any job, off the GUI thread) | upscaler + governor |
| `platform` | XDG folders, `xdg_open()`, `launch_in_terminal()` (with an exit file the caller can watch); for Windows, a suite's folders under `%LOCALAPPDATA%` and `%APPDATA%`, `open_path()`, a PowerShell window and Start-menu shortcuts | the bisect GUIs' `terminal.py` |
| `steam` | Steam's folders and users, `with_steam_closed()`, `shortcuts.vdf` and the shortcuts' artwork in `grid/` (standard library only) | consoles |
| `steam_art` | `draw_icon_art()`: a shortcut's four pictures drawn from an app's icon, in the icon's color | consoles |
| `upstream` | `publish()` / `read_all()`: the updates outside the suite an app can install now, for the portal's notice (standard library only; HelixSR carries a copy) | new: helixsr, pcsx2, portal |
| `sensors` | `Sensors.read()`: the board's live values from `/proc` and `/sys` without root (CPU, GPU, the governor's range, VRAM, RAM, temperatures, network, disk, fans), `Reading`, `Fan` | System Overlay; used by USB IPS3.5 too |
| `wifi` | The Wi-Fi adapters and whether the running kernel has a driver and firmware for them, `report()` (standard library only; `python3 -m bc250_core.wifi`) | new: check's test 53, wdriver |

Core is **bundled per app**: `tools/stage_app.py` copies `bc250_core/` next to the package of every app that
imports it, so each release runs on the core it was tested with.

### Tests

```bash
cd core && QT_QPA_PLATFORM=offscreen python -m pytest -q tests
```

`tests/test_parity.py` renders core's widgets next to the copies in `bc250-bazzite/apps/gpu` and `bc250-bazzite/apps/upscaler` and requires
identical pixels; a case is skipped once its app no longer has its own copy.

## Set up and test

```bash
# Linux
python3 -m venv .venv-linux && .venv-linux/bin/python -m pip install -r requirements-dev.txt
# Windows (Git Bash)
py -m venv .venv-windows && .venv-windows/Scripts/python.exe -m pip install -r requirements-dev.txt

./test.sh                                   # every test suite of this system, offscreen; picks this OS's venv
NEXUS_SYSTEM=bazzite ./test.sh              # the Bazzite suites' tests too, on another system
python3 tools/check_versions.py             # hard-coded versions = VERSION
mkdocs build --strict -f nexus/mkdocs.yml   # the Nexus page; -f bc250-bazzite/mkdocs.yml for that suite's wiki
```

A suite is worked on and tested on its own system: `./test.sh` runs the `bazzite` suites on Linux and the `windows`
suites on Windows, and core, tools and `dev/` on both.

### CI on your own machine

`./test.sh` runs every suite in one venv that holds everything, on whatever Python your system has. GitHub's CI runs
each job on Python 3.12 with only that job's own requirements, so a test can pass here and still fail there: a
Python 3.13 function, or a package only the full venv has. `tools/ci-local.sh` runs the jobs of
`.github/workflows/ci.yml` the way GitHub does, in a container (podman, which Bazzite has, or docker):

```bash
tools/ci-local.sh                      # every job, about a minute and a half once the image is built
tools/ci-local.sh pytest/tools shell   # some jobs; a matrix job by its value, pytest for all of them
tools/ci-local.sh --list               # the jobs, read from ci.yml
```

It reads the jobs from `ci.yml` itself, so a new app in the matrix or a new installer step needs no change. The
first run builds the image from `tools/ci-local/Containerfile` (Python 3.12 and the packages GitHub's runner has)
and Console Link's FFmpeg; both are kept, with the venvs and the logs, in `~/.cache/bc250-ci-local`. It works on a
copy of the checkout with every change staged, as the commit will have it. Only the Windows job does not run here.
The push commands Nexus Releases shows run it first (`tools/ci-local.sh && git push`): no push when a job fails.

`tools/pre-push.sh` runs CI's quick checks in a few seconds: the versions, `bc250-bazzite/portal/apps.toml` with the
portal bump it needs against what the remote has, the CHANGELOGs keeping every entry the remote has
(`tools/check_changelogs.py`), the scripts' exec bits and the line endings. Make it git's pre-push hook once per
checkout, and every `git push` runs it first:

```bash
git config core.hooksPath tools/hooks   # once per checkout
BC250_PRE_PUSH=full git push            # also every CI job (tools/ci-local.sh)
git push --no-verify                    # without the checks
```

### Working from both Linux and Windows

The repo is used from both systems, so it is set up to behave the same on each:

- **Line endings:** `.gitattributes` makes every text file LF in the repository and in the working tree on both
  systems, regardless of `core.autocrlf` (Git for Windows sets it to `true`). Scripts, units and `.desktop` files
  reach the board with LF, and moving between systems never shows files as changed. CI rejects CRLF.
- **Executable bit:** Git for Windows runs with `core.fileMode=false` and records new files as not executable. After
  `git add` and before committing, run `tools/fix-modes.sh`: it marks every `.sh` as executable in the index (this
  works the same on both systems). CI fails when a script is missing the bit.
- **Venvs:** a venv only runs on the OS that created it, so keep one per system (`.venv-linux/`, `.venv-windows/`).
  Both are ignored by git.
- **Tests:** some app tests use Linux-only calls (`os.getuid`, file modes) and fail on Windows; Linux and CI are
  the reference. Core's tests run on both and never write to the Windows registry.
- **File names:** Linux is case-sensitive and Windows is not, so a link or path whose case only matches on Windows
  breaks on Linux and on GitHub. Keep links and asset names in exactly the case of the file.
