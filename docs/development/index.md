<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Development

How the repository is laid out, how to work on it from Linux and Windows, and how versions and releases fit
together. How every app is built, and how to add one: [Architecture and consistency](architecture.md). The repository's settings on GitHub, and how to handle Dependabot's pull requests: [GitHub settings](github-settings.md). The tools a machine needs to work on it, on Bazzite or Windows, and how they stay up to date: [The development machine](machine.md). The portal's release steps are in [Portal](../portal.md#appstoml-and-releases).

## Layout

```
core/bc250_core/   shared Python package, see bc250_core below
portal/            the portal: app, apps.toml (the pinned app releases) and install.sh
apps/<name>/       one folder per app, each with its own VERSION and CHANGELOG
tools/             release and CI tools (build_release, stage_app, pin_app, check_*; release.sh starts the
                   release front end in apps/suite/), installer tests
docs/ mkdocs.yml   the manual (MkDocs Material)
test.sh            runs every test suite (core, portal, tools and each app with tests/)
```

## Development

```bash
# Linux
python3 -m venv .venv-linux && .venv-linux/bin/python -m pip install -r requirements-dev.txt
# Windows (Git Bash)
py -m venv .venv-windows && .venv-windows/Scripts/python.exe -m pip install -r requirements-dev.txt

./test.sh                          # every test suite, offscreen; picks the venv of the OS it runs on
python3 tools/check_versions.py    # hard-coded versions = VERSION
mkdocs build --strict              # from the venv
```

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
The push commands BC250 Suite Releases shows run it first (`tools/ci-local.sh && git push`): no push when a job fails.

`tools/pre-push.sh` runs CI's quick checks in a few seconds: the versions, `portal/apps.toml` with the portal bump
it needs against what the remote has, the CHANGELOGs keeping every entry the remote has (`tools/check_changelogs.py`),
the scripts' exec bits and the line endings. Make it git's pre-push hook once
per checkout, and every `git push` runs it first:

```bash
git config core.hooksPath tools/hooks   # once per checkout
BC250_PRE_PUSH=full git push            # also every CI job (tools/ci-local.sh)
git push --no-verify                    # without the checks
```

To preview the manual locally, run `mkdocs serve` from the repository root with the development venv active,
then open <http://127.0.0.1:8000/bc250-bazzite-suite/>. Stop the server with Ctrl+C.

The picture of the portal on the home page (`docs/images/home/portal.webp`) is taken from the portal itself:
`tools/portal_screenshot.py` opens its window offscreen on this checkout's `apps.toml` and icons, in a home folder
of its own, with a fixed demo state (one update, the Sustainable tab open), and saves it. The wiki's workflow runs it
before every build, so the published picture always shows the portal as it is on main. Run it yourself to see the
same picture in `mkdocs serve`:

```bash
python tools/portal_screenshot.py          # from the venv; --out FILE to save it elsewhere
```

The video tours are made the same way, frame by frame from the real windows, offscreen. `tools/record-tour.sh`
records the portal's tour, about two minutes, with music under it that fades out over the last two seconds
(`tools/sounds/the_quiet_engine_remix_3min.mp3`, made with generative AI tools; `--no-music` leaves it out).
`tools/record-tour.sh --wiki` also writes the copy on the [Portal Tour](../portal-tour.md) page,
`docs/videos/portal-tour.mp4` (1280 × 720, about 6 MB) and its poster: run it after a change to the portal's window.
`tools/record-app-tour.sh` records one app's, about 40 seconds, the same script for every app, with music under it
that fades out over the last two seconds (`tools/sounds/the_quiet_engine.mp3`, made with generative AI tools):

```bash
tools/record-app-tour.sh fan                          # ~/Videos/bc250-fan-tour-v<version>.mp4
tools/record-app-tour.sh compute --package cu_unlock  # compute and cores have two programs
tools/record-app-tour.sh cec cec.mp4 --seconds 30     # another file, another length
tools/record-app-tour.sh fan --no-music               # without sound; --music FILE for another track
```

The app starts from the checkout in a home folder of its own. The tour points at the controls of its header, with
their tooltips as captions, and opens its tabs or pages; it presses no buttons and nothing runs as root. What the
app reads from the board is real, so watch the video before you publish it.

The controller beside the board on the home page changes with every portal release, in the order of
`docs/images/home/controllers/controllers.toml`. To add one, put its picture in that folder (WebP, 1295 × 1600, with
a transparent background, like the others) and add it at the end of the list with its alt text.

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

## Where things are installed

- **Root-owned `/opt`:** the portal (`/opt/bc250-bazzite-suite`), Bazzite Test (`check`), cores, oc and
  acpi, whose scripts run as root: a normal user cannot change code that sudo runs.
- **Your home folder:** the shared venv `~/.local/share/bc250-bazzite-suite/venv` (PyQt6, used by all suite
  GUIs and removed with the last of them), plus each app's settings, results and launchers.
- **`bc250_core` per app:** each app's release carries the `bc250_core` it was tested with, next to its own code.
  Apps with different release tags never share a core version they were not tested with.

[Portal](../portal.md#install) has the full table.

## Versions and tags

`core/`, `portal/` and every app have a `VERSION` file; it is the single source of the version. Versions that are
also written in a script or package (`VERSION="…"`, `__version__ = "…"`, pyproject `version`) must match it, which
CI checks with `tools/check_versions.py`. Everything started at 0.1.0 with the suite.

Each app is released on its own tag (`check-v0.1.0`, `gpu-v0.4.0`, …); the release workflow builds
`<tag>.tar.gz` and `SHA256SUMS`. The portal has `portal-vX.Y.Z` and pins one release of every app in
`portal/apps.toml`; a change there since the last portal release needs a portal version bump at least as large as the largest app bump.
The release steps are in [Portal](../portal.md#appstoml-and-releases).

### Upstream releases an app pins or follows

Decky Loader Manager installs one Decky Loader release, pinned in
`apps/decky/decky_manager/loader.py` (`VERSION`, `TAG`, `SHA256`), and writes Decky's service unit
itself (`unit_text()`). `tools/check_upstream.py` compares both with Decky's repository: a newer stable release, the
SHA-256 GitHub publishes for the pinned binary, and Decky's `plugin_loader-release.service` at the pinned tag and on
`main` (Decky's own updater installs `main`'s). It exits with 0 when they match, 1 when Decky moved and 2 when it
could not check. The Upstream workflow (`.github/workflows/upstream.yml`) runs it every Monday and can be started by
hand. What moved goes into the open **Upstream review** issue (a new one when none is open, else its list is
updated with a comment), which notifies everyone who watches the repository. The workflow never closes it: close
it once every item on it is handled on `main`, else next Monday's run opens it again. **Close issues** in Suite
Releases (tab Test on this board) does it, or a command with a gh login:

```bash
gh issue list                                                  # the open issues, with their numbers
gh issue close <number> --comment "Decky pinned at v3.3.0."    # close one, saying how it was handled
```

The run fails only when an upstream could not be checked. A moved pin means a new version of the app is due, with
the new pin tried on the board first.

The shadPS4 Manager installs one shadPS4 release, pinned in `apps/shadps4/shadps4_manager/emulator.py`
(`VERSION`, `TAG`, `ASSET`, `SHA256`). The same tool checks it: a newer stable release, with the Linux zip and the
SHA-256 GitHub publishes for it that a new pin needs, and the SHA-256 of the pinned zip. A new shadPS4 can change
what the app relies on (its `config.json`, the shadNet protocol), so a new pin also needs a look at what changed.

The PPSSPP, PCSX2 (its stable channel) and RPCS3 Managers and Mesh Shaders each pin one release: `VERSION` or
`LANDMARK` in the app's `emulator.py`, and `DIRECTMESH` in `apps/mesh/bc250-mesh-shaders.sh`. RPCS3's `emulator.py`
also holds the size of the pinned AppImage (`SIZE`), by which the app sees that RPCS3 replaced itself with another
build, so a new pin moves it too.
The same tool reports a newer stable release than the pin (for DirectMesh the newest `directmesh-v*` tag); the apps
check the checksum of what they download themselves. The governor has no pin in the repository (its version is the
one COPR built); the GPU Governor Manager compares the installed package with filippor's latest release.

The BC-250 Upscaler Manager pins no HelixSR release: it gets the latest of one major version (`SUPPORTED_MAJOR`), or the
fallback HelixSR's developer names. Its `apps/upscaler/upscaler/acquire.py` holds `SUPPORTED_MAJOR`,
`KNOWN_VERSION`, the newest release the app was checked against, and `FALLBACK_VERSION`. The same tool reports a newer
stable release (users get it at once, so what changed in its setup, its zip and `helixsr.ini` needs a look and a try
on the board; then `KNOWN_VERSION` moves), a newer major version (users do not get it until the app is moved to it), a fallback
named in the latest release's notes that is not `FALLBACK_VERSION`, and a fallback release without its zip.

The Vita3K Manager installs one Vita3K build, pinned in `apps/vita3k/vita3k_manager/emulator.py`
(`BUILD`, `SEMVER`, `COMMIT`, `SHA256`, `SIZE`). Vita3K has no stable releases: every change is a build, kept as a
release of `Vita3K/Vita3K-builds` tagged with its number, with `Vita3K-x86_64.AppImage` and the SHA-256 GitHub
publishes for it. Builds come almost daily, so the tool does not check them; the app itself says when a newer build
is out. A new pin takes the asset's digest and size from that release, and a look at what the app relies on in
Vita3K's source at the new build:

- the command line (`vita3k/config/src/config.cpp`): `-r <title ID>`, `--frontend sdl`, `--firmware`,
  `--pkg` with `--zrif`, and a `.vpk`, `.zip` or folder as the positional argument;
- the folders (`vita3k/app/src/app_init.cpp`, `init_paths`): settings in `$XDG_CONFIG_HOME/Vita3K/config.yml`, the
  storage in `$XDG_DATA_HOME/Vita3K/Vita3K` unless `pref-path` in config.yml moves it, games in its `ux0/app`;
- the firmware's three parts (`vita3k/app/src/app.cpp`, `get_firmware_state`): `vs0`, `sa0` and `pd0` counted as
  installed when they hold anything;
- the SDL frontend (`vita3k/sdl-frontend`): it runs the game given by `-r` and quits with it, and has no full screen
  of its own. `--fullscreen` is not used: Vita3K writes it into config.yml as `boot-apps-full-screen`;
- the AppImage's self-updater (`bin/10-self-updater.hook` in the AppImage): it overwrites the AppImage with the
  newest continuous build unless `DISABLE_AUTO_UPDATES=1`, which the run wrapper sets. `vita3k --version` on the new
  AppImage confirms the build and commit.

The tests hold the `config.yml` the pinned build writes on its first start (`tests/fixtures/config-4186.yml`); a new
pin replaces it with the new build's, renamed for it.

The Xenia Manager installs one Xenia Canary build, pinned in `apps/xenia/xenia_manager/emulator.py` (`BUILD`,
`COMMIT`, `PUBLISHED`, `SHA256`, `SIZE`). Xenia has no stable releases either: every change is a release of
`xenia-canary/xenia-canary`, tagged with its commit, with `xenia_canary_linux.AppImage` and the SHA-256 GitHub
publishes for it. A tag is no number, so the app takes a release published after `PUBLISHED` as a newer build; the
tool does not check them. A new pin takes the asset's digest and size and the release's date, and a look at what the
app relies on in Xenia's source at the new commit: the `--fullscreen` option and the positional path
(`src/xenia/app/xenia_main.cc`), the storage root in `$XDG_DATA_HOME/Xenia` (the same file, and `GetUserFolder` in
`src/xenia/base/filesystem_posix.cc`), the places of the game partition in a disc image
(`src/xenia/vfs/devices/disc_image_device.cc`, which `GAME_PARTITIONS` in the app's `games.py` copies), and GTK on
X11 (`GDK_BACKEND` in `src/xenia/ui/windowed_app_main_posix.cc`).

```bash
python3 tools/check_upstream.py            # all of them
python3 tools/check_upstream.py helixsr    # one: decky, shadps4, helixsr, ppsspp, pcsx2, rpcs3 or directmesh
```

## bc250_core

Code shared by the suite's apps. Nothing in it imports an app: each app passes its constants in as an `AppInfo`.

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
| `platform` | XDG folders, `xdg_open()`, `launch_in_terminal()` (with an exit file the caller can watch) | the bisect GUIs' `terminal.py` |
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

`tests/test_parity.py` renders core's widgets next to the copies in `apps/gpu` and `apps/upscaler` and requires
identical pixels; a case is skipped once its app no longer has its own copy.
