<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Architecture and consistency

Every app of the suite is built the same way: the same folders, the same files, the same start-up, the same window
header, the same installer and the same tests. Once you know one app, you can find your way in all of them, and a
new app starts as a copy of that structure. This chapter describes the structure and lists the checks that keep it
in place.

## Principles

- **One layout.** Every app folder looks the same; nothing is wrapped in an extra folder.
- **One way to do a thing.** Shared code lives in `bc250_core`. An app adds only what is its own.
- **Our tools, not Bazzite.** The suite answers for the portal and its apps. A Bazzite system package is in scope
  only where one of our apps uses it; its updates are Bazzite's.
- **Not limited to one setup.** Apps read what the hardware reports and offer every option it supports. The
  owner's board and TV are test data, not the target.
- **Released code is the baseline.** Moving code must not change what an app does. Prove it with the tests, the
  installer tests and screenshots.
- **Checked by CI.** Each rule below names the check that enforces it, so a mistake fails a test instead of
  waiting for a review.

## The app folder

The suite lives in `bc250-bazzite/` of the repository (Nexus), beside `core/` and the Nexus tools in `tools/`,
which every suite shares; paths here are written from the root of the repository. The folder name is the app's
key: the same name is used in `bc250-bazzite/portal/apps.toml`, the release tag (`<name>-v<x.y.z>`), the
installer test and the manual chapter.

```
bc250-bazzite/apps/<name>/
├── <package>/                 the Python package, directly in the app folder
│   ├── __init__.py            APP_NAME, APP_ID, __version__, ROOT, LOGO_PATH, INFO
│   ├── __main__.py            start-up: python -m <package>
│   ├── main_window.py         the window
│   └── ...                    the app's own modules, and data it reads (a catalog, tables)
├── images/                    <app-id>.webp (512 px) and <app-id>-128.png for the menu entry
├── native/                    only an app with a native core (consoles): a Rust crate, see below
├── tests/                     conftest.py and test_*.py
├── install.sh                 install, update and uninstall for your own user
├── requirements.txt           runtime Python packages (PyQt6, ...)
├── requirements-dev.txt       -r requirements.txt plus pytest
├── VERSION                    the version: the single source
├── CHANGELOG                  the history, newest first
├── LICENSE                    GPL-3.0-or-later (acpi: MIT)
├── .gitignore
└── README.md                  title, one paragraph, link to the manual, license
```

- The **package** sits directly in `bc250-bazzite/apps/<name>/`, never in a wrapper folder such as `bc250-bazzite/apps/<name>/<name>/<package>`.
  `<name>` is a short name for the app and the package is the app's name without its BC-250 or Bazzite prefix, as
  a Python identifier: `bc250-bazzite/apps/ace/ace_queues/` for BC-250 ACE Queues, `bc250-bazzite/apps/ncgui/netcat_gui/` for Bazzite
  NetcatGUI, `bc250-bazzite/apps/datstation/datstation/` for Bazzite DatStation (the two names may be the same word), `bc250-bazzite/apps/check/bazzite_check/`
  for BC-250 Bazzite Test (a short name chosen apart from the app's, so that no folder is called test). Apps
  from before this convention still have a `bc250_<something>` or `bazzite_<something>` package;
  they move to it one at a time.
- **Data** the package reads ships inside the package (the Dependency Checker's `dependencies.toml`) or next to it
  in the app folder (acpi's `tables/`). Never one folder up from where the installer copies the app.
- An app with a shell script as its engine keeps that script in the app folder too
  (`bc250-bazzite/apps/cores-bisect/bc250-cores-bisect.sh`).
- **No placeholder folders** for future work. Plans and status go in MIGRATION.md, not in the app or the manual.
- **A native core** (only Console Link so far) is a Rust crate in `native/`, with PyO3 for Python. Its protocol
  code builds and tests without Python (`cargo test`); maturin builds the Python module from `native/pyproject.toml`
  as a wheel for Python 3.10 and newer. Its version equals the app's VERSION (`tools/check_versions.py` reads
  `Cargo.toml` and `pyproject.toml`). Cargo's build output, `native/target/`, is never installed or staged. CI's
  `native` job runs the Rust tests, clippy and the module's Python tests. Console Link's video decoder (cargo
  feature `decoder`) links FFmpeg statically, built by `native/ffmpeg/build.sh` from pinned sources; the release
  workflow builds the wheel with it into `native/wheel/`, which ships in the tarball (`tools/build_release.py`
  refuses the release without it), and `install.sh` installs that wheel, so users need no compiler.

Checked by `tools/tests/test_layout.py` (packages and `images/` at the app root, no wrapper folder) and by CI's
layout job (`VERSION`, `CHANGELOG`, `LICENSE` and `.gitignore` in every folder, LF line endings, executable `.sh`
files).

## The package

`__init__.py` holds the app's constants and nothing that needs Qt:

```python
APP_NAME = "BC-250 Example"
APP_ID = "bc250-example"
__version__ = "0.1.0"                     # equal to VERSION; tools/check_versions.py checks it

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="example-v",
               settings_ini=True)
```

`__main__.py` starts the app the same way in every app: `create_app()` sets the names, style, fonts and icon; `instance.already_running()` brings an open window to the front instead of opening a second one;
`exec_app()` runs the event loop and handles SIGTERM.

```python
def main() -> int:
    app = create_app(INFO, sys.argv[1:])
    if instance.already_running(INFO.app_id):
        return 0
    window = MainWindow()
    window.show()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    return exec_app(app)
```

An app that opens what it is given on the command line (a file from its menu entry's `%f`, a host and port) hands
those arguments to the open window instead of losing them: `instance.already_running(INFO.app_id, args)` sends them
along, and `instance.serve(INFO.app_id, window, on_args=...)` gives them to the running window, which opens them as
it would at start-up (the shadPS4 Manager opens the package in Extract PKG, Bazzite NetcatGUI opens the tab).

`--version` prints the app's version and the core it runs on.

## The window

Every window starts with the same header: the app's icon at 96 px on the left, spanning two rows. The first row
has the name with the version, then the app's states, and its actions on the right. The second row has the status
boxes or the app's main controls.

```
┌────────┐  BC-250 Example  v0.1.0   ● Ready                              [Refresh]
│  icon  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ 96 px  │  │  6.0 GiB │ │   on     │ │  1.0.0.0 │ │    —     │
└────────┘  └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

Apps on core build it with `AppHeader`:

```python
from bc250_core.widgets import AppHeader, MetricBox, StatusText

header = AppHeader(LOGO_PATH, APP_NAME, __version__)
self.badge = StatusText()
header.add_state(self.badge)               # beside the title
header.add_action(self.refresh_button)     # right end of the title row
for box in (self.vram_box, self.gtt_box):
    header.add_second(box)                 # the second row, left to right
layout.addLayout(header)
```

Apps that are not on core yet build the same layout in their own code, with the same sizes: a 96 px icon, a 24 px
bold title with the version in gray at 14 px, and 6 px between the rows.

Below the header, the rest of the window uses core's widgets: `MetricBox` for figures, `StatusPill` and
`StatusText` for states (`ok`, `warn`, `bad`, `info`, `neutral`, in the theme's colors), `hint_label()` for
explanations, `accent_button()` for the page's main action. Secondary windows are titled with `window_title()`.

Every app has the suite's theme: gunmetal (the default), silver or warm, one choice for all the apps, made in the
portal and kept in `~/.config/bc250-bazzite-suite/theme`. `create_app()` applies it (an app not on core calls
`apply_theme()` from its copy of `theme.py`). The theme gives the window, the buttons, the tabs and the fields
their colors. A status box, pill or banner is the theme's surface with its state or color as a thick left edge
(`MetricBox.set_colour()`, `surface_style()`), never a filled box with white text, so it reads in a light and a
dark theme alike. Text takes the theme's colors (`THEME.text`, `muted()`), not white or a fixed gray.

An app may have its own color, taken from its icon, in a `style.py` beside its window (the shadPS4 Manager's is
the pattern): the main buttons, the table headers, the selection and the links take it, over the theme. White text
on the color reads at 4.5:1 or more, links on a dark window use a lighter shade of it, and the color stays easy on
the eye. Without a `style.py` the app takes the theme's accent.

### Icons

Every app in a category has the same icon. Each category's icon is kept once, in `bc250-bazzite/icons/<category>/`, at 1024, 512,
256 and 128 px. `bc250-bazzite/icons/categories.toml` gives each app its category and names its copies: `images/<app-id>.webp`
(512 px) and `images/<app-id>-128.png` in the app, and its tile in `bc250-bazzite/portal/images/apps/<name>.webp` (256 px). The
copies stay in the repository, so the installers, the portal and the wiki find them where they always did.

The icons are WebP, a fraction of the size of PNG, which the apps (through Qt) and the wiki show. Only the 128 px one
is PNG: the menu entry, the Desktop icon, a Steam shortcut and a notification use it, because a desktop or Steam may
not read WebP. In code, `LOGO_PATH` is the WebP icon; `steam.shortcut_icon()` gives the PNG beside it.

To give a category a new icon, drop the new images in `bc250-bazzite/icons/<category>/` and run `python3 bc250-bazzite/tools/sync_icons.py`.
An image named `<category>-<size>` (any extension) replaces that size only; an image by any other name replaces all
four. The tool scales each to its size, saves it as WebP (the 128 px one as PNG) under the category's names, removes
the dropped file, then writes the copies. Images must be square. An image elsewhere works too:

```bash
python3 bc250-bazzite/tools/sync_icons.py --category sustainable --from ~/Pictures/leaf.png              # all four sizes
python3 bc250-bazzite/tools/sync_icons.py --category sustainable --from ~/Pictures/leaf-small.png --size 128
```

[Media Tool](../other-tools/media-tool.md#convert-the-suites-icons) does the same from a window.
`python3 bc250-bazzite/tools/sync_icons.py --check` lists what is not converted or copied yet, and `bc250-bazzite/tools/tests/test_icons.py`
fails when a copy is out of date or an app icon has no category.

## Shared code: bc250_core

`core/bc250_core` holds what more than one app needs: theme, widgets, start-up, settings, help, update checks and
platform helpers. Nothing in it imports an app; each app passes its constants in as `AppInfo`. The module table is
in [Development](https://robertotorino.github.io/nexus/development/#bc250_core) on the Nexus page.

Core is **bundled per app**. `tools/stage_app.py` copies `bc250_core/` next to the package of every app that
imports it, so each release runs on the core it was tested with. From a checkout, the installer bundles the
checkout's core the same way. The shared venv holds only PyQt6 and pygame-ce (the portal's controller reader).

Before you write a helper in an app, look in core. If two apps need the same code, move it into core and give it a
test. Apps that are not on core yet keep a copy of core's `instance.py`; `tools/tests/test_instance_copies.py`
keeps those copies equal to core's.

## Steam shortcuts and their artwork

Apps that add something to Steam's library for Game Mode do it through core's `steam` module: the shortcut in
`shortcuts.vdf` and its four pictures in `grid/` (portrait, wide, banner and the logo Steam lays over the banner).
Where the pictures come from depends on what the app has:

| App | What the Steam card shows |
|---|---|
| Console Link | Drawn from the app's icon (`steam_art`), with the console's name and model |
| PCSX2 Manager | Drawn from the app's icon (`steam_art`), with the game's title: a PS2 disc has no pictures |
| Bazzite DatStation | Drawn from the app's icon (`steam_art`), with the app's name |
| shadPS4 Manager | The game's own pictures (`icon0.png`, `pic1.png`), its icon as the logo |
| RPCS3 Manager | The game's own pictures (`ICON0.PNG`, `PIC1.PNG`), its icon as the logo |
| Xenia Manager | Drawn from the app's icon (`steam_art`), with the game's title |
| PPSSPP Manager | The game's own pictures (`ICON0.PNG`, `PIC1.PNG`), its icon as the logo |
| Vita3K Manager | The game's own pictures (`icon0.png`, `pic0.png`), its icon as the logo |

`steam_art.draw_icon_art()` is for an app with no pictures of its own: the background is near black in the icon's
own color with a glow of it, the portrait and the wide picture show the icon with a title and a line under it, the
banner shows the title centered, and the icon file itself is the logo. A new icon changes the cards by itself. The
emulator managers keep the games' own pictures and draw only what a game lacks.

## Inside an app, and code style

### The technical layout of an app

Each module of a package has one job, so the logic can be tested without a window and the window stays small:

| Module | What it holds |
|---|---|
| `__init__.py` | The app's constants (`APP_NAME`, `APP_ID`, `__version__`, paths, `INFO`). No Qt. |
| `__main__.py` | Start-up only: arguments, `create_app()`, single instance, the window, `exec_app()`. |
| `main_window.py` | The window: layout, signals, and turning results into text and states. Little logic of its own. |
| Logic modules | Reading the board, parsing, deciding, building command lines: `system.py`, `cmos.py`, `cec.py`, `options.py`, `gate.py`, `dependencies.py`. No Qt, so they are tested on their own. |
| `runner.py`, `privileged.py` | The one place that runs commands. Steps that need root go through pkexec or sudo here. The result comes back as a small object (exit code, output) or, for a running `QProcess`, as signals; never as an exception the window has to guess about. |

- **The outside world comes in as parameters.** A window or function takes its folders and command runner as
  arguments with the real ones as defaults: `MainWindow(sys_root=Path("/sys"), runner=privileged.run)`. Tests pass
  a fake `/sys` and a fake runner; nothing in a test touches the board.
- **Nothing blocks the window.** Network checks and long jobs run off the GUI thread (core's `UpdateChecker`) or
  as a `QProcess`, and report back with a signal.
- **State lives in the XDG folders:** settings in `~/.config/` (through `AppInfo` and core's settings helpers),
  results and data in `~/.local/share/`, each in a folder named after the app. `install.sh --uninstall --purge` removes exactly
  those.
- **Scripts that do the board work** (the bisect and unlock scripts, `test-bazzite.sh`) stand on their own: the
  window builds their command line and shows their output, and the script can be run by hand with the same
  result.

### Code style

- **Read like the code around it:** the same comment density, naming and idiom as the file you change.
- **Python:** 3.10 or newer (Bazzite ships 3.13 or newer), `from __future__ import annotations`, type hints on functions, `dataclass` for
  results, `pathlib` for paths, f-strings. Lines up to about 120 characters.
- **Every file** starts with its SPDX line (`# SPDX-License-Identifier: GPL-3.0-or-later`); a module or script
  starts with a docstring or comment that says what it is for.
- **Comments say why,** not what the next line does: the reason for a choice, a board quirk, a finding on the
  owner's board with its date.
- **Core imports no app;** logic modules import no Qt; an app imports core, never another app.
- **Text in the window** is plain, short sentences for the person using the app, in English. The apps are not
  translated: no `self.tr()`, and Qt's own dialog buttons stay English too. Errors say what happened and what to
  do next.
- **Shell:** `#!/usr/bin/env bash`, `set -euo pipefail`, `info`/`die` helpers, the usage text in the header
  comment (shown by `--help`), quoted variables, and no shellcheck warnings.
- **Files** use LF line endings; scripts are executable (`tools/fix-modes.sh` sets the bit in the index).

## The installer

`install.sh` sits in the app folder. It runs as your own user and refuses to run with sudo; it uses sudo or pkexec
only for the steps that need root. Every installer takes these options, and `--help` shows them (an app may add
its own, such as `--bisect-only` and `--unlock-only` for the bisect apps with two windows):

```
./install.sh                         install or update
./install.sh --no-desktop-shortcut   app menu entry only, no icon on the Desktop
./install.sh --uninstall             remove the app; keeps its settings and results
./install.sh --uninstall --purge     also remove its settings and results
```

It installs:

- **The app** under `~/.local/share/<app-id>/`, or root-owned under `/opt/<app-id>-v<version>` (with a link
  `/opt/<app-id>`) when the app runs scripts as root, so a normal user cannot change code that sudo runs.
- **Python:** PyQt6 in the suite's shared venv `~/.local/share/bc250-bazzite-suite/venv`. An app with its own
  packages has its own venv. The shared venv goes when the last app that uses it is removed. pip runs with
  `--upgrade`, so installing again brings every package to the newest version the requirements allow, a security
  fix within that range included.
- **A launcher** `~/.local/bin/<app-id>` that changes into the app folder and runs
  `exec "<venv>/bin/python" -m <package>`. An app that takes file or folder paths on its command line (the
  shadPS4 Manager) stays in the folder it is started from, so a relative path means what it
  says: `exec "<venv>/bin/python" -c '$RUN_MODULE' "<app folder>" <package> "$@"`, which puts the app folder first
  on `sys.path` instead (see its `install.sh`), and its `__main__.py` makes the path absolute before it uses or
  hands it on. Keep the `exec "<venv>/bin/python"` start of that line: the Dependency Checker reads it to find the
  app's Python environment.
- **A menu entry and a Desktop icon,** both pointing at the launcher by its full path.

The installer checks that its files are there before it changes anything, works the same from a checkout and from
an extracted release, and needs no network except for pip.

## Tests

- **`bc250-bazzite/apps/<name>/tests/`:** pytest, offscreen. `conftest.py` puts core from the checkout on the path, provides a
  `qapp` fixture, and points QSettings and the XDG folders at a temp folder, so tests never touch your settings or
  the Windows registry. Fake `/sys`, `/proc` and command runners stand in for the board; data recorded on a real
  board makes good fixtures. Tests also cover other setups.
- **Every app has `tests/`** and a `requirements-dev.txt` (its `requirements.txt` plus pytest), and is listed in
  the pytest matrix of `.github/workflows/ci.yml`.
- **The installer test:** `bc250-bazzite/tools/installer-tests/<name>.sh` installs from the checkout and from a staged release,
  with and without the Desktop icon, and uninstalls. It runs without root or network: `shims.sh` turns sudo into
  fakeroot and pip into a stub. CI runs each installer test in its own step. BC-250 Installer Tests lists the
  scripts in that folder by itself.
- **`./test.sh`** runs every test suite in the repository: core, tools, `dev/`, and the suites made for the
  system it runs on (this suite's `SYSTEM` says `bazzite`).

`bc250-bazzite/tools/tests/test_installer_tests.py` fails when an app or a portal entry has no installer test, or when CI does
not run one.

## Versions, changelogs and releases

- `VERSION` is the single source of an app's version. Copies (`__version__`, shell `VERSION=`, pyproject) must
  match it: `tools/check_versions.py`.
- Every change gets a `CHANGELOG` entry in the folder it changes (the app, core, the portal, or the root for
  suite-wide changes): a `Changelog: DD-MM-YYYY HH:MM:SS` line in Europe/Amsterdam time, a blank line, then plain
  sentences, newest first.
- Versions follow semantic versioning. In an app's, core's or the portal's `CHANGELOG`, each entry starts with the
  kind of change it is, and a release takes the highest kind since its last tag:

  | The entry starts with | What changed                                                     | Release | Example         |
  |-----------------------|------------------------------------------------------------------|---------|-----------------|
  | `Breaking.`           | something removed, or no longer working as before (settings, options, files) | major | 1.2.3 → 2.0.0 |
  | `Added.`              | a new feature, everything that worked still works                | minor   | 1.2.3 → 1.3.0   |
  | `Fixed.`              | a bug or security fix                                            | patch   | 1.2.3 → 1.2.4   |

  An app at 0.x follows the same table: a new feature takes 0.1.4 to 0.2.0, a breaking change to 1.0.0. The portal
  moves at least as far as the largest app release it pins, and a minor step when an app is added or removed.
  Nexus Releases offers that version first; `tools/tests/test_changelog_kinds.py` checks the entries.
- Each app is released on its own tag, `<name>-v<x.y.z>`. The portal pins one release of each app in
  `bc250-bazzite/portal/apps.toml`. The steps are in [Portal](../portal.md#appstoml-and-releases).

## Adding a new app

`tools/new_app.py` writes a new app from this chapter and lists it wherever the suite lists its apps, so the
template cannot drift from the checks; it then runs the checks on it:

```bash
python3 tools/new_app.py bc250-bazzite fan2 "BC-250 Fan Two" --category sustainable --summary "What it does."
python3 tools/new_app.py --help     # --id, --package: the app id and the package, when the defaults are not yours
```

It writes `bc250-bazzite/apps/<name>/` (the package with `__main__.py` and a window on `AppHeader`, `images/`,
`tests/`, `install.sh`, the requirements, `VERSION` 0.1.0, `CHANGELOG`, `LICENSE`, `.gitignore`, `README.md`),
the installer test `bc250-bazzite/tools/installer-tests/<name>.sh` and the chapter `bc250-bazzite/docs/apps/<name>.md`,
and adds the app to `portal/apps.toml`, `icons/categories.toml` (with the icon copies), `mkdocs.yml`, the apps
overview and categories tables, the suite README, the Dependency Checker's catalog and CI's pytest matrix,
installer step and shellcheck list. What it does by hand, step by step, for an app that does not fit the template
(the owner's decision):

1. Copy the folder of the app closest to yours, rename the package, and set `APP_NAME`, `APP_ID`, `VERSION`
   (0.1.0) and `__version__`. Clear its `CHANGELOG` and start it with one entry.
2. Add the app to `bc250-bazzite/icons/categories.toml` with its category and run `python3 bc250-bazzite/tools/sync_icons.py`: it writes the
   icons in `images/` and the portal's tile ([Icons](#icons)).
3. Build the window on `AppHeader` and core's widgets.
4. Write `install.sh` from the copied one, with the same options and launcher.
5. Write `tests/` and `requirements-dev.txt`, and add the app folder to the pytest matrix in
   `.github/workflows/ci.yml`. Write `bc250-bazzite/tools/installer-tests/<name>.sh` and add its step to the same file.
6. Add the app to `bc250-bazzite/portal/apps.toml` (name, summary, `changes_board`, `category` (its icon's: the portal's tab for
   it), install, uninstall, detect, launch).
7. Add the app to the Dependency Checker's catalog (`[app.<name>]` with its launchers), its Python packages and
   the external tools it runs (`bc250-bazzite/apps/package/package_checker/dependencies.toml`).
8. Write its manual chapter, `bc250-bazzite/docs/apps/<name>.md`, add it to `mkdocs.yml`, and give it a row in the apps overview,
   `bc250-bazzite/docs/apps/index.md`.
9. Run the checks from [Development](index.md) and every installer test.

The tests in step 9 tell you what you missed: an app without an installer test, a catalog that does not match
the requirements files, a version copy that does not match `VERSION`, a package in a wrapper folder. After the
generator, what is left is the app itself: its window and tests, its chapter, its CHANGELOG entries, the catalog
for a package or tool beyond PyQt6, and the portal bump the new entry asks for.

## The checks at a glance

| Rule | Checked by |
|---|---|
| Packages and `images/` at the app root, no wrapper folder | `tools/tests/test_layout.py` |
| `install.sh` at the app root, with the standard options, refusing root | `tools/tests/test_layout.py` |
| Every app has `tests/` and `requirements-dev.txt`, and CI runs them | `tools/tests/test_layout.py` |
| `VERSION`, `CHANGELOG`, `LICENSE`, `.gitignore` in every folder; LF; executable scripts | CI layout job |
| Version copies equal `VERSION` | `tools/check_versions.py` |
| Every app and portal entry has an installer test, and CI runs it | `bc250-bazzite/tools/tests/test_installer_tests.py` |
| Copies of `instance.py` equal core's | `tools/tests/test_instance_copies.py` |
| The Dependency Checker's catalog matches the requirements files, the portal's apps, and the tools the apps use | `bc250-bazzite/apps/package/tests/test_dependencies.py` |
| `bc250-bazzite/portal/apps.toml` rules and version bumps | `bc250-bazzite/tools/check_manifest.py` |
| A CHANGELOG keeps every entry it had at the last push | `tools/check_changelogs.py` |
| The manual builds with no broken link | `mkdocs build --strict` |
