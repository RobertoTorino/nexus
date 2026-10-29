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
.github/workflows/            every workflow: ci-nexus.yml (Nexus's checks), ci.yml and release.yml (the BC250
                              Bazzite Suite), each other suite's ci-<suite>.yml and release-<suite>.yml,
                              nexus-index.yml, docs.yml (the wikis)
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

A new app of a suite starts with `tools/new_app.py`: it writes the app from the suite's template and lists it
wherever the suite lists its apps (the portal's `apps.toml`, the wiki, the installer test, CI), then runs the checks
on it. Each suite has its template: the BC250 Bazzite Suite's (see its architecture chapter) and the Windows
Portable Suite's, an app on the portable window with `install.ps1`, `run.ps1` and the installer test `<name>.ps1`,
its icon its category's (`windows-portable/icons/<category>/`, copied by `tools/make_icons.py`). On the suite's wiki
home page the app gets a paragraph in its category's card (a new card when the category has none yet), to be written
over with what the app does:

```powershell
.venv-windows\Scripts\python.exe tools\new_app.py windows-portable pcsx2 "PCSX2 Manager" --category gaming --summary "What it does."
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
| `platform` | XDG folders, `xdg_open()`, `launch_in_terminal()` (with an exit file the caller can watch); for Windows, a suite's folders under `%LOCALAPPDATA%` and `%APPDATA%`, `open_path()`, a PowerShell window and Start-menu shortcuts; `private()`, a path or a text with the user's folders as `%LOCALAPPDATA%`, `%APPDATA%` and `%USERPROFILE%` (`~` on Linux), never the user's name, which `applog.setup(private=True)` applies to every line of a log | the bisect GUIs' `terminal.py` |
| `steam` | Steam's folders and users, `with_steam_closed()`, `shortcuts.vdf` and the shortcuts' artwork in `grid/` (standard library only) | consoles |
| `steam_art` | `draw_icon_art()`: a shortcut's four pictures drawn from an app's icon, in the icon's color | consoles |
| `upstream` | `publish()` / `read_all()`: the updates outside the suite an app can install now, for the portal's notice (standard library only; HelixSR carries a copy) | new: helixsr, pcsx2, portal |
| `sensors` | `Sensors.read()`: the board's live values from `/proc` and `/sys` without root (CPU, GPU, the governor's range, VRAM, RAM, temperatures, network, disk, fans), `Reading`, `Fan` | System Overlay; used by USB IPS3.5 too |
| `portable` | The portable window of the Windows Portable Suite: `PortableWindow` (the d-pad and A, the focus kept in a pane once it is there, so only B leaves it; the buttons every window shares: B goes back with `go_back()`, from a pane to its card and nowhere on a card, View (⧉) exits with `exit_app()`, which an app overrides to ask first while it is busy, and Menu (☰) opens the information icon of the pane that shows; `common_items()` ends a legend with ☰ Info, B Back and ⧉ Exit app, and `update_legend()` is called on every move of the focus; `bind()` for a page's own buttons, `act()`, `show_popup()`; each stack of the window keeps one page visible, `one_page()`), `PortableHeader`, `Card`, `Pane`, `Pill`, `InfoPill` (an information icon that shows more text than fits, in an `InfoPopup` over the window), `Legend` (the row of actions at the bottom: an entry tapped does what its button does), `Tabs` (LB and RB step through them), `TextView` (a long text read in the pane, the log: the d-pad scrolls it), `Pane.tapped` (a tap on a pane, for its A where that is safe), the information icon touch only (Menu opens it), `status_clock()`, `px()` and `scale()` (the layout drawn to the screen's size, larger or smaller; `pin_scale()` for tests), the suite's wallpaper behind every window (`WALLPAPER`, on or off for the suite in `<suite>\suite.ini`: `wallpaper_on()`, `PortableWindow.set_wallpaper()`), `glass()` and `restyle()` (see-through cards over it) | new |
| `browse` | Choosing a folder or a file with the controller, where Windows' own windows cannot be used: `places()` (the user's Games, Downloads, Documents and Desktop folders, then every drive), `Browser` (`rows()`, `open()`: A into a folder or on a file, `up()`: B), `listing()` without the hidden and system ones (standard library only) | new |
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
mkdocs build --strict -f nexus/mkdocs.yml   # the Nexus page; -f <suite>/mkdocs.yml for a suite's wiki
```

A suite is worked on and tested on its own system: `./test.sh` runs the `bazzite` suites on Linux and the `windows`
suites on Windows, and core, tools and `dev/` on both.

### CI on your own machine

GitHub runs `ci-nexus.yml` on every push: Nexus's checks (core, the Nexus tools, `dev/`, the Nexus page and the
repository's rules: line endings, exec bits, the four files of every former repo, no CHANGELOG losing an entry). A
suite's own CI (`ci.yml` for the BC250 Bazzite Suite, `ci-<suite>.yml` for the others) runs when the push changes
that suite's folder or what its releases are built from (core, `tools/`, `dev/`), never for a push to another suite
alone. A suite's release tags wait for its own CI and for Nexus's, never for another suite's, so one suite's failure
never holds another's releases; a commit that has no run of the suite's CI (nothing of the suite changed) gets no
tag: `tools/ci_state.py` says so within five minutes instead of waiting the hour.

The Windows Portable Suite's CI runs its installer tests and release builds as one job per app and the portal
(`installers`, a matrix): each installs the app from the checkout, builds its release zip as the release workflow
does (never published) and installs it from that zip. A new app is one more entry in that matrix
(`tools/new_app.py` adds it).

`./test.sh` runs every suite in one venv that holds everything, on whatever Python your system has. GitHub's CI runs
each job on Python 3.12 with only that job's own requirements, so a test can pass here and still fail there: a
Python 3.13 function, or a package only the full venv has. `tools/ci-local.sh` runs the jobs of `ci.yml` and
`ci-nexus.yml` the way GitHub does, in a container (podman, which Bazzite has, or docker):

```bash
tools/ci-local.sh                            # every job of both workflows, about a minute and a half once the image is built
tools/ci-local.sh shell nexus-pytest/tools   # some jobs; a matrix job by its value, pytest for all of the suite's
tools/ci-local.sh --list                     # the jobs; ci-nexus.yml's have nexus- before the name (nexus-shell)
```

It reads the jobs from the workflows themselves, so a new app in the matrix or a new installer step needs no change. The
first run builds the image from `tools/ci-local/Containerfile` (Python 3.12 and the packages GitHub's runner has)
and Console Link's FFmpeg; both are kept, with the venvs and the logs, in `~/.cache/bc250-ci-local`. It works on a
copy of the checkout with every change staged, as the commit will have it. Only the Windows job does not run here.
The push commands Nexus Releases shows run it first (`tools/ci-local.sh && git push`): no push when a job fails.

`tools/pre-push.sh` runs CI's quick checks in a few seconds: the versions, each suite's `portal/apps.toml` with the
portal bump it needs against what the remote has, the CHANGELOGs keeping every entry the remote has
(`tools/check_changelogs.py`), the scripts' exec bits and the line endings. A suite's versions and manifest are
checked only when the push changes that suite (its folder), so a failing check of the Windows Portable Suite never
holds a push of the BC250 suite, and the other way round; core and `dev/` are checked on every push. Make it git's
pre-push hook once per checkout, and every `git push` runs it first:

```bash
git config core.hooksPath tools/hooks   # once per checkout
BC250_PRE_PUSH=full git push            # also every CI job (tools/ci-local.sh)
git push --no-verify                    # without the checks
```

When the remote has commits this checkout lacks, pushed from the other machine, the hook says so and stops before
the checks: run `git pull --rebase`, then push again.

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
